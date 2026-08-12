"""Scientific verification for the Lotka-Volterra predator-prey domain.

Lotka, A.J. (1925) *Elements of Physical Biology*, Williams & Wilkins.
Volterra, V. (1926) "Fluctuations in the abundance of a species considered
mathematically", *Nature* 118, 558-560. DOI 10.1038/118558a0.

The engine integrates

    dP/dt = alpha*P - beta*P*V      (prey)
    dV/dt = gamma*P*V - delta*V     (predator)

so `gamma` is the predator's growth-from-predation (conversion) rate and
`delta` its death rate.

Following this project's rule that the solver is never checked against
itself, every assertion below is against a quantity derivable by hand from
those two equations, or against an independent integrator:

1. **The conserved quantity.** The system has an exact first integral

       H(P, V) = gamma*P - delta*ln P + beta*V - alpha*ln V

   with dH/dt identically zero:

       dH/dt = (gamma - delta/P)*P*(alpha - beta*V)
             + (beta - alpha/V)*V*(gamma*P - delta)
             = (gamma*P - delta)(alpha - beta*V)
             + (beta*V - alpha)(gamma*P - delta)
             = 0

   This is the strongest available check: it is a property of the ODE, not
   of any trajectory, and a wrong rate law breaks it immediately.

2. **The coexistence fixed point** (P*, V*) = (delta/gamma, alpha/beta).
   Started exactly there, the populations must not move.

3. **The small-oscillation period.** Linearising about the fixed point
   gives a Jacobian with eigenvalues +/- i*sqrt(alpha*delta), hence
   T = 2*pi/sqrt(alpha*delta) for orbits close to it. Independent of both
   the conserved quantity and the fixed point.

4. **An independent integrator** (scipy's `solve_ivp`, which shares no code
   with roadrunner).
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from terium_engine import (  # noqa: E402
    simulate_lotka_volterra,
    validate_lotka_volterra_params,
)

# A parameter set whose fixed point (delta/gamma, alpha/beta) = (4.0, 2.75)
# sits at the same order of magnitude as the initial condition (10, 5), so
# the orbit is a well-conditioned closed curve rather than a near-extinction
# excursion. See TestDefaultParametersAreWellConditioned for why that
# matters and what happens when it does not hold.
ALPHA, BETA, GAMMA, DELTA = 1.1, 0.4, 0.1, 0.4
P0, V0 = 10.0, 5.0


def _conserved(P, V, alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA):
    """H(P, V) -- the exact first integral of the Lotka-Volterra system."""
    return gamma * P - delta * np.log(P) + beta * V - alpha * np.log(V)


def _columns(result):
    data = np.asarray(result.data, dtype=float)
    idx = {name: i for i, name in enumerate(result.colnames)}
    return data[:, idx["time"]], data[:, idx["P"]], data[:, idx["V"]]


class TestConservedQuantity:
    """Verification 1: dH/dt = 0, derived by hand from the rate laws."""

    def test_first_integral_is_conserved_along_the_orbit(self):
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=P0, v0=V0, end=20.0, points=2001,
        )
        _, P, V = _columns(result)
        H = _conserved(P, V)
        drift = (H.max() - H.min()) / abs(H[0])
        # Tolerance is set by the integrator, not by the physics: the
        # quantity is exactly conserved, so anything above solver noise is
        # a broken rate law.
        assert drift < 1e-5, f"conserved quantity drifted by {drift:.3e}"

    def test_conservation_holds_on_a_second_independent_orbit(self):
        # A different energy level of the same system -- guards against a
        # tolerance that happens to pass for one trajectory.
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=6.0, v0=3.0, end=20.0, points=2001,
        )
        _, P, V = _columns(result)
        H = _conserved(P, V)
        assert (H.max() - H.min()) / abs(H[0]) < 1e-5


class TestFixedPoint:
    """Verification 2: (delta/gamma, alpha/beta) is a stationary state."""

    def test_populations_do_not_move_from_the_coexistence_equilibrium(self):
        p_star = DELTA / GAMMA
        v_star = ALPHA / BETA
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=p_star, v0=v_star, end=20.0, points=201,
        )
        _, P, V = _columns(result)
        assert np.allclose(P, p_star, rtol=1e-6), "prey left the fixed point"
        assert np.allclose(V, v_star, rtol=1e-6), "predator left the fixed point"

    def test_the_fixed_point_is_where_both_derivatives_vanish(self):
        # Stated independently of the simulation: this is arithmetic on the
        # rate laws, and pins the P*/V* formulas the test above relies on.
        p_star, v_star = DELTA / GAMMA, ALPHA / BETA
        assert ALPHA * p_star - BETA * p_star * v_star == pytest.approx(0.0)
        assert GAMMA * p_star * v_star - DELTA * v_star == pytest.approx(0.0)


class TestSmallOscillationPeriod:
    """Verification 3: T = 2*pi/sqrt(alpha*delta) near the fixed point."""

    def test_period_matches_the_linearised_prediction(self):
        p_star, v_star = DELTA / GAMMA, ALPHA / BETA
        expected_period = 2 * math.pi / math.sqrt(ALPHA * DELTA)

        # A 2% displacement stays in the linear regime.
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=p_star * 1.02, v0=v_star, end=4 * expected_period, points=8001,
        )
        t, P, _ = _columns(result)

        # Period from successive upward crossings of the mean, linearly
        # interpolated -- more robust than peak-picking on a sampled curve.
        centred = P - p_star
        crossings = [
            t[i] + (t[i + 1] - t[i]) * (-centred[i]) / (centred[i + 1] - centred[i])
            for i in range(len(t) - 1)
            if centred[i] < 0 <= centred[i + 1]
        ]
        assert len(crossings) >= 2, "no full oscillation observed"
        measured = float(np.mean(np.diff(crossings)))
        assert measured == pytest.approx(expected_period, rel=0.02), (
            f"measured period {measured:.4f} vs linearised "
            f"prediction {expected_period:.4f}"
        )


class TestAgainstIndependentIntegrator:
    """Verification 4: scipy's solve_ivp shares no code with roadrunner."""

    def test_trajectory_matches_scipy(self):
        scipy_integrate = pytest.importorskip("scipy.integrate")

        end, points = 20.0, 401
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=P0, v0=V0, end=end, points=points,
        )
        t, P, V = _columns(result)

        def rhs(_t, y):
            prey, pred = y
            return [
                ALPHA * prey - BETA * prey * pred,
                GAMMA * prey * pred - DELTA * pred,
            ]

        reference = scipy_integrate.solve_ivp(
            rhs, (0.0, end), [P0, V0], t_eval=t, rtol=1e-10, atol=1e-12,
        )
        assert reference.success

        assert np.allclose(P, reference.y[0], rtol=1e-4, atol=1e-6)
        assert np.allclose(V, reference.y[1], rtol=1e-4, atol=1e-6)


class TestPhysicalInvariants:
    def test_populations_never_go_negative(self):
        # A negative population is not a small numerical blemish -- it is a
        # state the model cannot represent. See the class below.
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=P0, v0=V0, end=40.0, points=4001,
        )
        _, P, V = _columns(result)
        assert P.min() > 0.0, f"prey went negative: {P.min():.3e}"
        assert V.min() > 0.0, f"predator went negative: {V.min():.3e}"

    def test_orbit_is_closed(self):
        # Trajectories are periodic, so after one full period the state
        # must return to its start. Independent of H: this checks the
        # trajectory, H checks the vector field.
        period = 2 * math.pi / math.sqrt(ALPHA * DELTA)
        p_star, v_star = DELTA / GAMMA, ALPHA / BETA
        result = simulate_lotka_volterra(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA,
            p0=p_star * 1.02, v0=v_star, end=period, points=4001,
        )
        _, P, V = _columns(result)
        assert P[-1] == pytest.approx(P[0], rel=1e-3)
        assert V[-1] == pytest.approx(V[0], rel=1e-3)


class TestDefaultParametersAreWellConditioned:
    """The engine's own defaults must produce a physically meaningful run.

    This class exists because they did not. The shipped defaults were
    alpha=1.1, beta=0.4, gamma=0.4, delta=0.1 with p0=10, v0=5 -- putting
    the coexistence fixed point at (delta/gamma, alpha/beta) = (0.25, 2.75)
    while starting the prey at 10, a 40x excursion. The resulting orbit
    drove prey to -5.9e-11 (a negative population) and drifted the exactly
    conserved quantity by 49%, i.e. the integrator lost the physics
    entirely. Nothing caught it because the domain shipped with no tests.

    gamma and delta were transposed: gamma is the prey-to-predator
    conversion efficiency and delta the predator death rate, so gamma <
    delta is the biologically ordinary case, and the transposed pair
    described predators that convert prey to offspring four times faster
    than they die.
    """

    def test_signature_defaults_conserve_the_first_integral(self):
        import inspect

        params = inspect.signature(simulate_lotka_volterra).parameters
        defaults = {
            name: params[name].default
            for name in ("alpha", "beta", "gamma", "delta", "p0", "v0")
        }
        result = simulate_lotka_volterra(**defaults, end=20.0, points=2001)
        _, P, V = _columns(result)

        assert P.min() > 0.0, (
            f"default parameters drive prey to {P.min():.3e}; a negative "
            "population is not a representable state"
        )
        H = _conserved(P, V, defaults["alpha"], defaults["beta"],
                       defaults["gamma"], defaults["delta"])
        drift = (H.max() - H.min()) / abs(H[0])
        assert drift < 1e-4, (
            f"default parameters drift the conserved quantity by {drift:.2%}"
        )

    def test_default_fixed_point_is_comparable_to_the_default_start(self):
        # The condition the old defaults violated, stated directly: an
        # initial state orders of magnitude from the fixed point is a
        # near-extinction orbit, not a teaching demonstration.
        import inspect

        params = inspect.signature(simulate_lotka_volterra).parameters
        d = {n: params[n].default for n in ("alpha", "beta", "gamma", "delta", "p0", "v0")}
        p_star = d["delta"] / d["gamma"]
        v_star = d["alpha"] / d["beta"]
        assert 0.1 < d["p0"] / p_star < 10.0, (
            f"prey starts at {d['p0']} but the fixed point is {p_star}"
        )
        assert 0.1 < d["v0"] / v_star < 10.0, (
            f"predator starts at {d['v0']} but the fixed point is {v_star}"
        )


class TestValidation:
    """Rule 1/2: impossible inputs rejected, implausible ones flagged."""

    @pytest.mark.parametrize("field", ["alpha", "beta", "gamma", "delta"])
    def test_negative_rates_are_rejected(self, field):
        kwargs = dict(alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, p0=P0, v0=V0)
        kwargs[field] = -1.0
        assert validate_lotka_volterra_params(**kwargs).ok is False

    @pytest.mark.parametrize("field", ["p0", "v0"])
    def test_negative_populations_are_rejected(self, field):
        kwargs = dict(alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, p0=P0, v0=V0)
        kwargs[field] = -1.0
        assert validate_lotka_volterra_params(**kwargs).ok is False

    def test_the_documented_parameter_set_validates(self):
        v = validate_lotka_volterra_params(
            alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, p0=P0, v0=V0
        )
        assert v.ok is True
