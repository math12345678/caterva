"""Michaelis-Menten simulation correctness.

Nothing here checks roadrunner against roadrunner. Every numerical claim is
checked against one of:

  * the exact closed-form implicit solution of the MM ODE,
  * an analytically known limiting case (first-order / zeroth-order),
  * scipy's solve_ivp, which is a completely independent integrator.

That matters because the failure this suite exists to catch is a model that
integrates cleanly and reports confident numbers that are simply wrong.
"""

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from caterva_engine import (
    ModelBuildError,
    SimulationError,
    simulate_michaelis_menten,
)


def mm_implicit_residual(s, s0, km, vmax, t):
    """Exact solution of dS/dt = -Vmax*S/(Km+S), rearranged to equal zero.

        Km*ln(S0/S) + (S0 - S) - Vmax*t = 0
    """
    return km * math.log(s0 / s) + (s0 - s) - vmax * t


def scipy_mm(km, vmax, s0, t_eval):
    """Independent reference integration of the same ODE."""
    sol = solve_ivp(
        lambda t, y: [-vmax * y[0] / (km + y[0])],
        (float(t_eval[0]), float(t_eval[-1])),
        [s0],
        t_eval=t_eval,
        rtol=1e-10,
        atol=1e-12,
    )
    assert sol.success
    return sol.y[0]


# ---------------------------------------------------------------------------
# Exact solution
# ---------------------------------------------------------------------------


def test_trajectory_satisfies_the_exact_implicit_solution():
    km, vmax, s0 = 2.0, 5.0, 10.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.5, points=16)
    for t, s in zip(res.time, res.column("S")):
        if s <= 1e-9 or t == 0:
            continue
        residual = mm_implicit_residual(s, s0, km, vmax, t)
        assert abs(residual) < 1e-4, (
            f"trajectory departs from the exact MM solution at t={t}: "
            f"residual {residual:.2e}")


@pytest.mark.parametrize("km,vmax,s0", [
    (0.49, 1.5, 5.0),      # real hexokinase-scale Km
    (2.0, 5.0, 10.0),
    (100.0, 2.0, 50.0),    # Km >> S: first-order regime
    (0.01, 1.0, 10.0),     # Km << S: zeroth-order regime
])
def test_exact_solution_holds_across_kinetic_regimes(km, vmax, s0):
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0,
                                    end=min(1.0, 0.5 * s0 / vmax), points=11)
    for t, s in zip(res.time, res.column("S")):
        if s <= 1e-9 or t == 0:
            continue
        assert abs(mm_implicit_residual(s, s0, km, vmax, t)) < 1e-4


# ---------------------------------------------------------------------------
# Independent integrator
# ---------------------------------------------------------------------------


def test_matches_scipy_reference_integration():
    km, vmax, s0 = 2.0, 5.0, 10.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.5, points=16)
    reference = scipy_mm(km, vmax, s0, np.array(res.time))
    np.testing.assert_allclose(res.column("S"), reference, rtol=1e-5,
                               atol=1e-7)


def test_matches_scipy_for_a_real_enzyme_parameter_set():
    # HKDC1 glucose Km = 0.49 mM (PMID 41187334, verified live previously).
    km, vmax, s0 = 0.49, 1.0, 2.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0, points=21)
    reference = scipy_mm(km, vmax, s0, np.array(res.time))
    np.testing.assert_allclose(res.column("S"), reference, rtol=1e-5,
                               atol=1e-7)


# ---------------------------------------------------------------------------
# Defining properties of the rate law
# ---------------------------------------------------------------------------


def test_rate_is_half_vmax_when_substrate_equals_km():
    # This is the definition of Km. Estimate dS/dt at t=0 by finite difference
    # over a short interval and compare to Vmax/2.
    km, vmax = 2.0, 5.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=km, end=1e-4, points=3)
    s = res.column("S")
    dsdt = (s[1] - s[0]) / (res.time[1] - res.time[0])
    assert dsdt == pytest.approx(-vmax / 2, rel=1e-3)


def test_initial_rate_follows_the_michaelis_menten_equation():
    km, vmax, s0 = 2.0, 5.0, 7.0
    expected = vmax * s0 / (km + s0)
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1e-4, points=3)
    s = res.column("S")
    dsdt = (s[1] - s[0]) / (res.time[1] - res.time[0])
    assert -dsdt == pytest.approx(expected, rel=1e-3)


def test_saturating_substrate_gives_zeroth_order_decay():
    # S >> Km: consumption is nearly linear in time at rate Vmax.
    km, vmax, s0 = 0.001, 2.0, 100.0
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=10.0,
                                    points=11)
    s = res.column("S")
    expected = [s0 - vmax * t for t in res.time]
    np.testing.assert_allclose(s, expected, rtol=1e-3, atol=1e-2)


def test_subsaturating_substrate_gives_first_order_decay():
    # S << Km: reduces to exponential decay with rate constant Vmax/Km.
    km, vmax, s0 = 1000.0, 5.0, 0.1
    k = vmax / km
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=20.0,
                                    points=21)
    expected = [s0 * math.exp(-k * t) for t in res.time]
    np.testing.assert_allclose(res.column("S"), expected, rtol=1e-4,
                               atol=1e-9)


# ---------------------------------------------------------------------------
# Conservation and monotonicity
# ---------------------------------------------------------------------------


def test_substrate_plus_product_is_conserved():
    s0 = 10.0
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=s0, end=5.0,
                                    points=51)
    totals = [s + p for s, p in zip(res.column("S"), res.column("P"))]
    np.testing.assert_allclose(totals, [s0] * len(totals), rtol=1e-8,
                               atol=1e-8)


def test_substrate_decreases_monotonically():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, end=5.0,
                                    points=51)
    s = res.column("S")
    assert all(b <= a + 1e-9 for a, b in zip(s, s[1:]))


def test_product_increases_monotonically():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, end=5.0,
                                    points=51)
    p = res.column("P")
    assert all(b >= a - 1e-9 for a, b in zip(p, p[1:]))


def test_substrate_never_goes_negative():
    # Integrated well past exhaustion: a naive solver can undershoot to
    # negative concentrations, which are physically meaningless.
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, end=100.0,
                                    points=101)
    assert all(s >= -1e-6 for s in res.column("S"))


def test_reaction_runs_effectively_to_completion():
    s0 = 10.0
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=s0, end=100.0,
                                    points=51)
    assert res.final("S") < 1e-3
    assert res.final("P") == pytest.approx(s0, rel=1e-4)


def test_higher_vmax_consumes_substrate_faster():
    slow = simulate_michaelis_menten(km=2.0, vmax=1.0, s0=10.0, end=2.0)
    fast = simulate_michaelis_menten(km=2.0, vmax=10.0, s0=10.0, end=2.0)
    assert fast.final("S") < slow.final("S")


def test_higher_km_consumes_substrate_more_slowly():
    # Higher Km means lower affinity, so a slower rate at fixed [S].
    tight = simulate_michaelis_menten(km=0.1, vmax=5.0, s0=10.0, end=1.0)
    loose = simulate_michaelis_menten(km=100.0, vmax=5.0, s0=10.0, end=1.0)
    assert loose.final("S") > tight.final("S")


# ---------------------------------------------------------------------------
# Degenerate but valid inputs
# ---------------------------------------------------------------------------


def test_zero_substrate_stays_at_zero():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=0.0, end=10.0)
    assert all(abs(s) < 1e-12 for s in res.column("S"))
    assert all(abs(p) < 1e-12 for p in res.column("P"))


def test_flagged_parameters_still_simulate_and_stay_flagged():
    res = simulate_michaelis_menten(km=1e9, vmax=1.0, s0=1.0, end=1.0)
    assert res.flagged, "the flag must survive all the way to the result"
    assert res.validation.flag_reason
    assert len(res) > 0


def test_invalid_parameters_raise_before_simulating():
    with pytest.raises(ModelBuildError):
        simulate_michaelis_menten(km=-1.0, vmax=1.0, s0=1.0)


# ---------------------------------------------------------------------------
# Time grid
# ---------------------------------------------------------------------------


def test_requested_number_of_points_is_returned():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=37)
    assert len(res) == 37


def test_time_column_spans_the_requested_interval():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, start=0.0,
                                    end=7.0, points=15)
    assert res.time[0] == pytest.approx(0.0)
    assert res.time[-1] == pytest.approx(7.0)


def test_time_is_strictly_increasing():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=25)
    assert all(b > a for a, b in zip(res.time, res.time[1:]))


@pytest.mark.parametrize("points", [0, 1, -5])
def test_too_few_points_raises(points):
    with pytest.raises(SimulationError, match="at least 2"):
        simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=points)


def test_end_before_start_raises():
    with pytest.raises(SimulationError, match="strictly after"):
        simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, start=10.0,
                                  end=1.0)


def test_zero_length_interval_raises_an_actionable_error():
    # roadrunner's native message here is "Cannot get the time step 1 because
    # there are only 0 set for the output", which tells the caller nothing.
    with pytest.raises(SimulationError, match="strictly after"):
        simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, start=3.0,
                                  end=3.0, points=2)


def test_nonzero_start_time_is_honoured():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, start=2.0,
                                    end=6.0, points=9)
    assert res.time[0] == pytest.approx(2.0)
    assert res.time[-1] == pytest.approx(6.0)
