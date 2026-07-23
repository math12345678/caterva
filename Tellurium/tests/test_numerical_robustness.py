"""Numerical robustness: stiff systems, extreme ratios, long horizons.

A student is free to type in parameters that are physically real but
numerically nasty -- a Km eight orders of magnitude below the substrate
concentration, or an epidemic run for a simulated century. These cases must
either produce a correct answer or fail loudly. What they must never do is
return a plausible-looking wrong number.
"""

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from tellurium_engine import (
    SimulationError,
    simulate_michaelis_menten,
    simulate_sir,
)

pytestmark = pytest.mark.timeout(120)


def scipy_mm(km, vmax, s0, t_eval):
    sol = solve_ivp(lambda t, y: [-vmax * y[0] / (km + y[0])],
                    (float(t_eval[0]), float(t_eval[-1])), [s0],
                    t_eval=t_eval, rtol=1e-11, atol=1e-13)
    assert sol.success
    return sol.y[0]


# ---------------------------------------------------------------------------
# Stiffness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ratio", [1e3, 1e6, 1e9])
def test_extreme_km_to_substrate_ratios_stay_accurate(ratio):
    """Km << S0 by many orders of magnitude: a classic stiff MM regime."""
    km = 1.0 / ratio
    vmax, s0 = 1.0, 1.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=0.5,
                                    points=11)
    reference = scipy_mm(km, vmax, s0, np.array(res.time))
    np.testing.assert_allclose(res.column("S"), reference, rtol=1e-4,
                               atol=1e-8)


@pytest.mark.parametrize("ratio", [1e3, 1e6, 1e9])
def test_extreme_substrate_to_km_ratios_stay_accurate(ratio):
    """S0 << Km: deep first-order regime.

    Checked against the exact ODE solution, not the first-order approximation.
    That distinction matters: at S0/Km = 1e-3 the approximation is itself
    wrong by 6.3e-4, so asserting against it would have flagged a solver that
    is in fact accurate to 1e-10.
    """
    km, vmax, s0 = ratio, 1.0, 1.0
    k = vmax / km
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0 / k,
                                    points=11)
    reference = scipy_mm(km, vmax, s0, np.array(res.time))
    np.testing.assert_allclose(res.column("S"), reference, rtol=1e-7,
                               atol=1e-12)


@pytest.mark.parametrize("ratio,tolerance", [(1e3, 1e-3), (1e6, 1e-6),
                                             (1e9, 1e-8)])
def test_first_order_limit_converges_at_the_predicted_rate(ratio, tolerance):
    """The exponential approximation's error must shrink as O(S0/Km).

    This pins the physics rather than the solver: as substrate falls further
    below Km, the MM rate law must converge on first-order kinetics at a rate
    set by the ratio itself.
    """
    km, vmax, s0 = ratio, 1.0, 1.0
    k = vmax / km
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0 / k,
                                    points=11)
    approximation = [s0 * math.exp(-k * t) for t in res.time]
    np.testing.assert_allclose(res.column("S"), approximation, rtol=tolerance,
                               atol=1e-12)


def test_very_fast_reaction_completes_correctly():
    # Vmax enormous relative to S0: the reaction finishes almost instantly.
    res = simulate_michaelis_menten(km=1e-3, vmax=1e6, s0=1.0, end=1.0,
                                    points=11)
    assert res.final("S") < 1e-6
    assert res.final("P") == pytest.approx(1.0, rel=1e-6)
    totals = [s + p for s, p in zip(res.column("S"), res.column("P"))]
    np.testing.assert_allclose(totals, [1.0] * len(totals), rtol=1e-6)


def test_very_slow_reaction_barely_moves():
    res = simulate_michaelis_menten(km=1.0, vmax=1e-9, s0=1.0, end=1.0,
                                    points=11)
    assert res.final("S") == pytest.approx(1.0, rel=1e-6)
    assert res.final("S") < 1.0, "some substrate must still be consumed"


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6, 1e9])
def test_results_are_scale_invariant(scale):
    """Scaling S0 and Vmax together must scale the trajectory identically.

    The MM equation is homogeneous under (S, Km, Vmax) -> (cS, cKm, cVmax),
    so the normalised trajectory is invariant. A solver whose tolerances are
    secretly absolute rather than relative breaks this.
    """
    base = simulate_michaelis_menten(km=1.0, vmax=1.0, s0=10.0, end=5.0,
                                     points=11)
    scaled = simulate_michaelis_menten(km=1.0 * scale, vmax=1.0 * scale,
                                       s0=10.0 * scale, end=5.0, points=11)
    normalised = [v / scale for v in scaled.column("S")]
    np.testing.assert_allclose(normalised, base.column("S"), rtol=1e-5,
                               atol=1e-8)


# ---------------------------------------------------------------------------
# Long horizons
# ---------------------------------------------------------------------------


def test_long_horizon_does_not_drift_off_conservation():
    res = simulate_michaelis_menten(km=1.0, vmax=0.1, s0=10.0, end=1e5,
                                    points=201)
    totals = [s + p for s, p in zip(res.column("S"), res.column("P"))]
    np.testing.assert_allclose(totals, [10.0] * len(totals), rtol=1e-6,
                               atol=1e-6)


def test_century_long_epidemic_conserves_population():
    res = simulate_sir(beta=0.3, gamma=0.1, s0=1e6, i0=10.0, end=36500.0,
                       points=201)
    n = 1e6 + 10.0
    totals = [s + i + r for s, i, r in
              zip(res.column("S"), res.column("I"), res.column("R"))]
    np.testing.assert_allclose(totals, [n] * len(totals), rtol=1e-9)


def test_epidemic_does_not_revive_after_burnout():
    # Once I hits zero it must stay there; a solver that lets it go negative
    # and rebound would invent a second wave that does not exist.
    res = simulate_sir(beta=0.6, gamma=0.15, s0=1e5, i0=1.0, end=5000.0,
                       points=501)
    i = res.column("I")
    peak_index = i.index(max(i))
    tail = i[peak_index:]
    assert all(b <= a * (1 + 1e-6) + 1e-6 for a, b in zip(tail, tail[1:])), (
        "infections increased again after the epidemic peak")


# ---------------------------------------------------------------------------
# Large populations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1e3, 1e6, 1e9])
def test_epidemics_scale_to_large_populations(n):
    i0 = n * 1e-5
    res = simulate_sir(beta=0.4, gamma=0.1, s0=n - i0, i0=i0, end=200.0,
                       points=51)
    totals = [s + i + r for s, i, r in
              zip(res.column("S"), res.column("I"), res.column("R"))]
    np.testing.assert_allclose(totals, [n] * len(totals), rtol=1e-9)
    assert res.final("R") > i0, "an epidemic should have occurred"


def test_epidemic_shape_is_population_invariant():
    """The attack rate depends only on R0, not on absolute population size."""
    small = simulate_sir(beta=0.4, gamma=0.1, s0=1e3 - 1, i0=1, end=2000.0,
                         points=101)
    large = simulate_sir(beta=0.4, gamma=0.1, s0=1e6 - 1e3, i0=1e3,
                         end=2000.0, points=101)
    assert (small.final("R") / 1e3) == pytest.approx(
        large.final("R") / 1e6, rel=1e-2)


# ---------------------------------------------------------------------------
# Resolution independence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("points", [3, 11, 101, 1001])
def test_final_value_is_independent_of_output_resolution(points):
    """Output sampling must not change the physics.

    If the reported endpoint moves when you only ask for more sample points,
    the solver is stepping to the output grid instead of controlling error.
    """
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, end=1.0,
                                    points=points)
    reference = scipy_mm(2.0, 5.0, 10.0, np.array([0.0, 1.0]))[-1]
    assert res.final("S") == pytest.approx(reference, rel=1e-5)


@pytest.mark.parametrize("points", [11, 501])
def test_epidemic_endpoint_is_independent_of_resolution(points):
    res = simulate_sir(beta=0.4, gamma=0.1, s0=999, i0=1, end=500.0,
                       points=points)
    assert res.final("S") == pytest.approx(19.8058, rel=1e-3)


# ---------------------------------------------------------------------------
# Failure modes stay loud
# ---------------------------------------------------------------------------


def test_absurd_but_finite_parameters_either_work_or_raise_clearly():
    # Whatever happens, it must not be a silent wrong answer.
    try:
        res = simulate_michaelis_menten(km=1e-300, vmax=1e300, s0=1.0,
                                        end=1.0, points=5)
    except SimulationError as exc:
        assert str(exc)
    else:
        assert all(math.isfinite(v) for v in res.column("S"))
        assert all(math.isfinite(v) for v in res.column("P"))


def test_no_nan_or_inf_ever_reaches_the_caller():
    for km, vmax, s0 in [(1e-8, 1e6, 1e6), (1e6, 1e-6, 1e-6),
                         (1.0, 1.0, 1e12)]:
        res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0,
                                        points=7)
        for row in res.data:
            assert all(math.isfinite(v) for v in row), (
                f"non-finite output for km={km} vmax={vmax} s0={s0}")
