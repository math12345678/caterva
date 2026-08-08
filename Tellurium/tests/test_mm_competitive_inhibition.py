"""Tests for competitive inhibition Michaelis-Menten domain.

Verify that the apparent Km under competitive inhibition is Km_app = Km*(1 + I/Ki)
and that the initial reaction rate matches Vmax * S / (Km_app + S). Also
check that at I=0 the kinetics reduce exactly to plain Michaelis-Menten.

Rule 1/2 edge cases (Constitution):
- Ki = 0 is physically impossible (division by zero in the inhibition term)
  and must be rejected with ok=False.
- Negative Km is physically impossible and must be rejected.
- Km outside the plausible bounds [1e-7, 1e3] mM must be flagged, not rejected.

The inhibitor is a constant (not consumed), so the trajectory obeys the
exact implicit closed form of the apparent-Michaelis-Menten ODE:

    dS/dt = -Vmax*S/(Km_app + S),   Km_app = Km*(1 + I/Ki)
    Km_app*ln(S0/S) + (S0 - S) = Vmax*t

Every numerical claim below is checked against that closed form, scipy's
solve_ivp (an independent integrator), or a defining physical limit of the
competitive-inhibition rate law — never against roadrunner vs. roadrunner.
"""

import math
import pathlib
import sys

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from tellurium_engine import (
    ModelBuildError,
    simulate_mm_competitive_inhibition,
    simulate_michaelis_menten,
)

_REPO = pathlib.Path(__file__).resolve().parents[2]


def approx_initial_rate(res):
    # estimate initial dS/dt by finite difference over a short interval
    s = res.column("S")
    dt = res.time[1] - res.time[0]
    dsdt = (s[1] - s[0]) / dt
    return -dsdt


def mm_competitive_implicit_residual(s, s0, km_app, vmax, t):
    """Exact solution of dS/dt = -Vmax*S/(Km_app+S), rearranged to equal zero.

        Km_app*ln(S0/S) + (S0 - S) - Vmax*t = 0
    """
    return km_app * math.log(s0 / s) + (s0 - s) - vmax * t


# ---------------------------------------------------------------------------
# Exact closed form (the inhibitor is constant, so the ODE is apparent-MM)
# ---------------------------------------------------------------------------


def test_trajectory_satisfies_the_exact_implicit_solution():
    km, vmax, ki, s0, i = 2.0, 5.0, 2.0, 10.0, 0.5
    km_app = km * (1.0 + i / ki)
    res = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=ki, s0=s0, i=i,
                                             end=1.5, points=16)
    for t, s in zip(res.time, res.column("S")):
        if s <= 1e-9 or t == 0:
            continue
        residual = mm_competitive_implicit_residual(s, s0, km_app, vmax, t)
        assert abs(residual) < 1e-4, (
            f"trajectory departs from the exact apparent-MM solution at t={t}: "
            f"residual {residual:.2e}")


@pytest.mark.parametrize("km,vmax,ki,s0,i", [
    (2.0, 5.0, 2.0, 10.0, 0.5),      # Km_app comparable to S
    (100.0, 2.0, 1.0, 50.0, 2.0),    # Km_app >> S: first-order regime
    (0.01, 1.0, 0.5, 10.0, 1.0),     # Km_app << S: zeroth-order regime
])
def test_exact_solution_holds_across_kinetic_regimes(km, vmax, ki, s0, i):
    km_app = km * (1.0 + i / ki)
    res = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=ki, s0=s0, i=i,
                                             end=min(1.0, 0.5 * s0 / vmax),
                                             points=11)
    for t, s in zip(res.time, res.column("S")):
        if s <= 1e-9 or t == 0:
            continue
        assert abs(mm_competitive_implicit_residual(s, s0, km_app, vmax, t)) < 1e-4


def test_matches_scipy_reference_integration():
    km, vmax, ki, s0, i = 2.0, 5.0, 2.0, 10.0, 0.5
    km_app = km * (1.0 + i / ki)
    res = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=ki, s0=s0, i=i,
                                             end=1.5, points=16)
    sol = solve_ivp(
        lambda t, y: [-vmax * y[0] / (km_app + y[0])],
        (0.0, 1.5), [s0], t_eval=np.array(res.time), rtol=1e-10, atol=1e-12,
    )
    assert sol.success
    np.testing.assert_allclose(res.column("S"), sol.y[0], rtol=1e-5, atol=1e-7)


# ---------------------------------------------------------------------------
# Conservation and monotonicity
# ---------------------------------------------------------------------------


def test_substrate_plus_product_is_conserved():
    s0 = 10.0
    res = simulate_mm_competitive_inhibition(km=2.0, vmax=5.0, ki=2.0, s0=s0, i=0.5,
                                             end=5.0, points=51)
    totals = [s + p for s, p in zip(res.column("S"), res.column("P"))]
    np.testing.assert_allclose(totals, [s0] * len(totals), rtol=1e-8, atol=1e-8)


def test_substrate_never_goes_negative():
    # Integrated well past exhaustion: a naive solver can undershoot to
    # negative concentrations, which are physically meaningless.
    res = simulate_mm_competitive_inhibition(km=2.0, vmax=5.0, ki=2.0, s0=10.0,
                                             i=0.5, end=100.0, points=101)
    assert all(s >= -1e-6 for s in res.column("S"))


# ---------------------------------------------------------------------------
# Defining physical behaviour of the inhibitor
# ---------------------------------------------------------------------------


def test_higher_inhibitor_concentration_slows_the_reaction():
    # A competitive inhibitor competes with the substrate for the active
    # site: at fixed Km, Vmax, S, a higher [I] must consume S more slowly.
    common = dict(km=2.0, vmax=5.0, ki=2.0, s0=10.0, end=2.0, points=21)
    low = simulate_mm_competitive_inhibition(i=0.5, **common)
    high = simulate_mm_competitive_inhibition(i=8.0, **common)
    assert high.final("S") > low.final("S"), (
        "more inhibitor should leave more substrate unconsumed")


def test_inhibitor_in_excess_halts_the_reaction():
    # Km_app -> infinity as [I] -> infinity, so the rate
    # Vmax*S/(Km_app + S) -> 0: an overwhelming inhibitor stalls the
    # reaction almost completely.
    s0 = 10.0
    res = simulate_mm_competitive_inhibition(km=2.0, vmax=5.0, ki=2.0, s0=s0,
                                             i=1e6, end=2.0, points=21)
    assert res.final("S") > 0.99 * s0, (
        "overwhelming inhibitor should leave substrate essentially untouched")


def test_weaker_binding_inhibitor_has_less_effect():
    # A larger Ki means weaker binding: at the same [I], a high-Ki inhibitor
    # must impede the reaction less than a low-Ki one (Km_app grows by I/Ki).
    common = dict(km=2.0, vmax=5.0, s0=10.0, i=4.0, end=2.0, points=21)
    tight = simulate_mm_competitive_inhibition(ki=0.5, **common)
    loose = simulate_mm_competitive_inhibition(ki=50.0, **common)
    assert tight.final("S") > loose.final("S"), (
        "weakly binding inhibitor (large Ki) should slow the reaction less")


def test_initial_rate_matches_apparent_km():
    km, vmax, ki, s0, i = 2.0, 5.0, 2.0, 7.0, 0.5
    km_app = km * (1.0 + i / ki)
    expected = vmax * s0 / (km_app + s0)
    res = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=ki, s0=s0, i=i,
                                             end=1e-4, points=3)
    initial_rate = approx_initial_rate(res)
    assert initial_rate == pytest.approx(expected, rel=1e-3)


def test_i_zero_reduces_to_plain_mm():
    km, vmax, s0 = 2.0, 5.0, 7.0
    res_comp = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=1.0, s0=s0, i=0.0,
                                                  end=1e-4, points=3)
    res_mm = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1e-4, points=3)
    # compare initial rate
    rate_comp = approx_initial_rate(res_comp)
    rate_mm = approx_initial_rate(res_mm)
    assert rate_comp == pytest.approx(rate_mm, rel=1e-6)


def test_ki_zero_is_rejected():
    """Ki = 0 makes the inhibition term divide by zero; must be rejected."""
    with pytest.raises(ModelBuildError, match="Ki"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=5.0, ki=0.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_negative_km_is_rejected():
    """Negative Km is physically impossible; must be rejected."""
    with pytest.raises(ModelBuildError, match="Km"):
        simulate_mm_competitive_inhibition(
            km=-1.0, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_negative_vmax_is_rejected():
    """Negative Vmax is physically impossible; must be rejected."""
    with pytest.raises(ModelBuildError, match="Vmax"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=-5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_negative_ki_is_rejected():
    """Negative Ki is physically impossible; must be rejected."""
    with pytest.raises(ModelBuildError, match="Ki"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=5.0, ki=-2.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_negative_s0_or_i_is_rejected():
    """Negative concentrations are physically impossible; must be rejected."""
    with pytest.raises(ModelBuildError, match="S0"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=5.0, ki=2.0, s0=-7.0, i=0.5, end=1e-4, points=3
        )
    with pytest.raises(ModelBuildError, match="I"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=5.0, ki=2.0, s0=7.0, i=-0.5, end=1e-4, points=3
        )


def test_km_below_plausible_bound_is_flagged():
    """Km = 1e-8 mM is below the 1e-7 mM plausible floor; must be flagged."""
    res = simulate_mm_competitive_inhibition(
        km=1e-8, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
    )
    assert res.flagged is True
    reason = res.validation.flag_reason or ""
    assert "below" in reason.lower() or "plausible" in reason.lower()


def test_km_above_plausible_bound_is_flagged():
    """Km = 2000 mM is above the 1000 mM plausible ceiling; must be flagged."""
    res = simulate_mm_competitive_inhibition(
        km=2000.0, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
    )
    assert res.flagged is True
    reason = res.validation.flag_reason or ""
    assert "above" in reason.lower() or "plausible" in reason.lower()


def test_runner_rejects_a_request_with_no_vmax():
    """The API runner must not silently fall back to vmax = 5.0.

    resolveQuery()'s hard rule (RequiredParametersMissingError on any
    default-origin vmax) already stops any such request before the runner
    is spawned, so the fallback was dead code through the API. This test
    pins the runner-side rejection so the dead default cannot quietly
    become live again if the runner ever receives a bare request.
    """
    runner_dir = (
        _REPO
        / "Science-Agent-Pipeline"
        / "artifacts"
        / "api-server"
        / "src"
        / "lib"
    )
    if not runner_dir.is_dir():
        pytest.skip("api-server runner not present in this checkout")
    if str(runner_dir) not in sys.path:
        sys.path.insert(0, str(runner_dir))

    import tellurium_runner  # noqa: PLC0415

    with pytest.raises(ValueError, match="needs a Vmax"):
        tellurium_runner.run_mm_competitive_inhibition(
            {"km": 2.0, "ki": 1.0, "s0": 7.0, "i0": 0.5, "end": 1e-4, "points": 3}
        )
