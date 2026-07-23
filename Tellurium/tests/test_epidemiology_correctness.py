"""SIR / SEIR simulation correctness.

As with the kinetics suite, every numerical claim is checked against something
external to roadrunner: the exact SIR conserved quantity, the closed-form
final-size relation, the analytic peak condition, or scipy's solve_ivp.
"""

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from tellurium_engine import (
    ModelBuildError,
    simulate_seir,
    simulate_sir,
)


def scipy_sir(beta, gamma, s0, i0, r0, t_eval):
    n = s0 + i0 + r0

    def rhs(t, y):
        s, i, r = y
        infection = beta * s * i / n
        recovery = gamma * i
        return [-infection, infection - recovery, recovery]

    sol = solve_ivp(rhs, (float(t_eval[0]), float(t_eval[-1])), [s0, i0, r0],
                    t_eval=t_eval, rtol=1e-10, atol=1e-12)
    assert sol.success
    return sol.y


def scipy_seir(beta, sigma, gamma, s0, e0, i0, r0, t_eval):
    n = s0 + e0 + i0 + r0

    def rhs(t, y):
        s, e, i, r = y
        infection = beta * s * i / n
        progression = sigma * e
        recovery = gamma * i
        return [-infection, infection - progression, progression - recovery,
                recovery]

    sol = solve_ivp(rhs, (float(t_eval[0]), float(t_eval[-1])),
                    [s0, e0, i0, r0], t_eval=t_eval, rtol=1e-10, atol=1e-12)
    assert sol.success
    return sol.y


# ---------------------------------------------------------------------------
# Conservation
# ---------------------------------------------------------------------------


def test_sir_population_is_conserved():
    s0, i0, r0 = 999.0, 1.0, 0.0
    res = simulate_sir(beta=0.3, gamma=0.1, s0=s0, i0=i0, r0_recovered=r0,
                       end=200.0, points=101)
    totals = [s + i + r for s, i, r in
              zip(res.column("S"), res.column("I"), res.column("R"))]
    np.testing.assert_allclose(totals, [s0 + i0 + r0] * len(totals),
                               rtol=1e-8, atol=1e-6)


def test_seir_population_is_conserved():
    s0, e0, i0, r0 = 990.0, 10.0, 0.0, 0.0
    res = simulate_seir(beta=0.5, sigma=0.2, gamma=0.1, s0=s0, e0=e0, i0=i0,
                        r0_recovered=r0, end=200.0, points=101)
    totals = [s + e + i + r for s, e, i, r in
              zip(res.column("S"), res.column("E"), res.column("I"),
                  res.column("R"))]
    np.testing.assert_allclose(totals, [s0 + e0 + i0 + r0] * len(totals),
                               rtol=1e-8, atol=1e-6)


def test_no_compartment_goes_negative():
    res = simulate_sir(beta=0.6, gamma=0.2, s0=999, i0=1, end=300.0,
                       points=151)
    for name in ("S", "I", "R"):
        assert all(v >= -1e-6 for v in res.column(name)), f"{name} went negative"


def test_susceptible_never_increases_and_recovered_never_decreases():
    res = simulate_sir(beta=0.3, gamma=0.1, s0=999, i0=1, end=200.0,
                       points=101)
    s, r = res.column("S"), res.column("R")
    assert all(b <= a + 1e-9 for a, b in zip(s, s[1:]))
    assert all(b >= a - 1e-9 for a, b in zip(r, r[1:]))


# ---------------------------------------------------------------------------
# Exact conserved quantity
#
# For SIR, S + I - (N/R0)*ln(S) is invariant along any trajectory. This is an
# exact analytic property, independent of the integrator.
# ---------------------------------------------------------------------------


def test_sir_invariant_is_conserved_along_the_trajectory():
    beta, gamma, s0, i0 = 0.3, 0.1, 999.0, 1.0
    n = s0 + i0
    r0_basic = beta / gamma
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=150.0,
                       points=76)

    def invariant(s, i):
        return s + i - (n / r0_basic) * math.log(s)

    values = [invariant(s, i)
              for s, i in zip(res.column("S"), res.column("I")) if s > 1e-6]
    reference = values[0]
    for v in values:
        assert abs(v - reference) < 1e-3 * max(1.0, abs(reference)), (
            "SIR invariant drifted, indicating an integration error")


# ---------------------------------------------------------------------------
# Independent integrator
# ---------------------------------------------------------------------------


def test_sir_matches_scipy_reference():
    beta, gamma, s0, i0 = 0.3, 0.1, 999.0, 1.0
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=100.0,
                       points=51)
    s_ref, i_ref, r_ref = scipy_sir(beta, gamma, s0, i0, 0.0,
                                    np.array(res.time))
    np.testing.assert_allclose(res.column("S"), s_ref, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(res.column("I"), i_ref, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(res.column("R"), r_ref, rtol=1e-4, atol=1e-4)


def test_seir_matches_scipy_reference():
    beta, sigma, gamma = 0.5, 0.2, 0.1
    s0, e0, i0 = 990.0, 10.0, 0.0
    res = simulate_seir(beta=beta, sigma=sigma, gamma=gamma, s0=s0, e0=e0,
                        i0=i0, end=100.0, points=51)
    s_ref, e_ref, i_ref, r_ref = scipy_seir(beta, sigma, gamma, s0, e0, i0,
                                            0.0, np.array(res.time))
    np.testing.assert_allclose(res.column("S"), s_ref, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(res.column("E"), e_ref, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(res.column("I"), i_ref, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(res.column("R"), r_ref, rtol=1e-4, atol=1e-4)


# ---------------------------------------------------------------------------
# R0 threshold behaviour
# ---------------------------------------------------------------------------


def test_r0_below_one_produces_no_outbreak():
    # beta/gamma = 0.5 < 1: infections must decay monotonically from the start.
    res = simulate_sir(beta=0.05, gamma=0.1, s0=999, i0=1, end=100.0,
                       points=101)
    i = res.column("I")
    assert all(b <= a + 1e-9 for a, b in zip(i, i[1:])), (
        "an epidemic grew despite R0 < 1")
    assert res.final("I") < 1.0


def test_r0_above_one_produces_an_outbreak():
    res = simulate_sir(beta=0.5, gamma=0.1, s0=999, i0=1, end=100.0,
                       points=101)
    i = res.column("I")
    assert max(i) > 10 * i[0], "R0 > 1 should produce clear epidemic growth"


def test_epidemic_peaks_when_susceptibles_cross_n_over_r0():
    # Analytic result: dI/dt = 0 exactly when S = N/R0.
    beta, gamma, s0, i0 = 0.5, 0.1, 999.0, 1.0
    n = s0 + i0
    expected_s_at_peak = n / (beta / gamma)

    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=200.0,
                       points=2001)
    i = res.column("I")
    peak_index = i.index(max(i))
    s_at_peak = res.column("S")[peak_index]
    assert s_at_peak == pytest.approx(expected_s_at_peak, rel=0.02)


def test_final_size_matches_the_analytic_relation():
    # Final size equation: S_inf = S0 * exp(-R0 * (1 - S_inf/N)).
    beta, gamma, s0, i0 = 0.4, 0.1, 999.0, 1.0
    n = s0 + i0
    r0_basic = beta / gamma

    def equation(s_inf):
        return s_inf - s0 * math.exp(-r0_basic * (1 - s_inf / n))

    analytic_s_inf = brentq(equation, 1e-9, s0 - 1e-9)

    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=1000.0,
                       points=201)
    assert res.final("S") == pytest.approx(analytic_s_inf, rel=1e-3)


def test_larger_r0_infects_more_of_the_population():
    mild = simulate_sir(beta=0.15, gamma=0.1, s0=999, i0=1, end=1000.0,
                        points=201)
    severe = simulate_sir(beta=0.8, gamma=0.1, s0=999, i0=1, end=1000.0,
                          points=201)
    assert severe.final("R") > mild.final("R")


def test_epidemic_burns_out_rather_than_persisting():
    res = simulate_sir(beta=0.5, gamma=0.1, s0=999, i0=1, end=2000.0,
                       points=201)
    assert res.final("I") < 1e-3, "infection should die out in a closed SIR model"


def test_susceptibles_are_not_fully_depleted():
    # A real SIR epidemic always leaves some susceptibles untouched.
    res = simulate_sir(beta=0.5, gamma=0.1, s0=999, i0=1, end=2000.0,
                       points=201)
    assert res.final("S") > 0.0


# ---------------------------------------------------------------------------
# SEIR-specific behaviour
# ---------------------------------------------------------------------------


def test_seir_outbreak_can_start_from_exposed_only():
    res = simulate_seir(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=0,
                        end=200.0, points=201)
    assert max(res.column("I")) > 1.0, (
        "exposed individuals must progress into the infectious compartment")


def test_seir_infectious_compartment_starts_empty_and_fills():
    res = simulate_seir(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=0,
                        end=200.0, points=201)
    i = res.column("I")
    assert i[0] == pytest.approx(0.0, abs=1e-12)
    assert max(i) > 0.0


def test_seir_peaks_later_than_sir_with_matched_parameters():
    # The latent period delays the epidemic; this is the whole point of SEIR.
    common = dict(beta=0.5, gamma=0.1, end=300.0, points=601)
    sir = simulate_sir(s0=999, i0=1, **common)
    seir = simulate_seir(sigma=0.2, s0=999, e0=1, i0=0, **common)

    sir_peak_t = sir.time[sir.column("I").index(max(sir.column("I")))]
    seir_peak_t = seir.time[seir.column("I").index(max(seir.column("I")))]
    assert seir_peak_t > sir_peak_t


def test_faster_progression_moves_seir_toward_sir():
    # As sigma grows, the latent stage vanishes and SEIR should approach SIR.
    common = dict(beta=0.5, gamma=0.1, end=300.0, points=601)
    sir = simulate_sir(s0=999, i0=1, **common)
    slow = simulate_seir(sigma=0.05, s0=999, e0=1, i0=0, **common)
    fast = simulate_seir(sigma=50.0, s0=999, e0=1, i0=0, **common)

    def peak_time(res):
        return res.time[res.column("I").index(max(res.column("I")))]

    assert abs(peak_time(fast) - peak_time(sir)) < abs(
        peak_time(slow) - peak_time(sir))


def test_seir_exposed_compartment_empties_eventually():
    res = simulate_seir(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=0,
                        end=2000.0, points=201)
    assert res.final("E") < 1e-3


# ---------------------------------------------------------------------------
# Degenerate but valid inputs
# ---------------------------------------------------------------------------


def test_zero_infected_produces_a_flat_trajectory():
    res = simulate_sir(beta=0.5, gamma=0.1, s0=1000, i0=0, end=100.0)
    assert res.flagged
    assert all(s == pytest.approx(1000.0) for s in res.column("S"))
    assert all(abs(i) < 1e-12 for i in res.column("I"))


def test_everyone_already_recovered_decays_at_exactly_the_recovery_rate():
    # With no susceptibles left there is no new infection, so the infectious
    # compartment must follow pure exponential decay I(t) = I0*exp(-gamma*t).
    gamma, i0, end = 0.1, 1.0, 100.0
    res = simulate_sir(beta=0.5, gamma=gamma, s0=0, i0=i0,
                       r0_recovered=999, end=end, points=51)

    expected = [i0 * math.exp(-gamma * t) for t in res.time]
    np.testing.assert_allclose(res.column("I"), expected, rtol=1e-6,
                               atol=1e-12)
    assert res.final("R") == pytest.approx(1000.0 - i0 * math.exp(-gamma * end),
                                           rel=1e-6)


def test_invalid_epidemic_parameters_raise():
    with pytest.raises(ModelBuildError):
        simulate_sir(beta=-0.5, gamma=0.1, s0=999, i0=1)
    with pytest.raises(ModelBuildError):
        simulate_seir(beta=0.5, sigma=0.0, gamma=0.1, s0=990, e0=10, i0=0)


def test_flag_survives_to_the_epidemic_result():
    res = simulate_sir(beta=100.0, gamma=0.1, s0=999, i0=1, end=10.0)
    assert res.flagged
    assert "R0" in res.validation.flag_reason
