"""Regression: ADR 0023's defect was fixed only in the DEFAULTS.

ADR 0023 corrected transposed `gamma`/`delta` default arguments, which had
put the coexistence fixed point at (0.25, 2.75) while the prey started at
10 -- a 40x excursion that drove the prey population to -5.79e-11 and
drifted the exactly-conserved first integral by 44%.

The *validator* was never touched. `validate_lotka_volterra_params` checked
each rate against a wide [1e-4, 100] band and nothing else, so the identical
parameters remained fully reachable through the API for any caller
supplying their own rates -- returning a physically impossible trajectory
with `flagged = False`.

Fixing a bad default without fixing the validator that permitted it leaves
the failure one HTTP request away.

The threshold is measured, not guessed (alpha=1.1, beta=0.4, gamma=0.4,
delta=0.1, v0 at the fixed point, end=20, points=2001), varying
p0/(delta/gamma):

    ratio    min prey        relative drift in H
        1    +2.50e-01       0
        5    +8.72e-03       6.8e-09
       10    +1.14e-04       7.7e-08
       20    +1.03e-08       5.5e-05
       40    -5.73e-12       2.4e-01     <- NEGATIVE prey, physics lost
       80    -5.16e-11       6.8e-01

`LV_EXCURSION_RATIO_FLAG_ABOVE = 20` is the last ratio whose drift is small
enough that the trajectory still *is* the modelled system.

Rule 2: flagged, never rejected. The run completes and still shows a
boom-bust cycle; the student is told the numbers are past what the solver
carries faithfully.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.data_structures import LV_EXCURSION_RATIO_FLAG_ABOVE  # noqa: E402
from core.validation import validate_lotka_volterra_params  # noqa: E402
from terium_engine import simulate_lotka_volterra  # noqa: E402

#: The exact parameter set ADR 0023 removed from the defaults.
ADR_0023 = dict(alpha=1.1, beta=0.4, gamma=0.4, delta=0.1, p0=10.0, v0=5.0)
#: The corrected defaults. Must remain unflagged.
CORRECTED = dict(alpha=1.1, beta=0.4, gamma=0.1, delta=0.4, p0=10.0, v0=5.0)


def _conserved(P, V, alpha, beta, gamma, delta):
    return gamma * P - delta * np.log(np.abs(P)) + beta * V - alpha * np.log(np.abs(V))


class TestTheApiReachableFailure:
    def test_adr_0023_parameters_are_flagged(self):
        v = validate_lotka_volterra_params(**ADR_0023)
        assert v.ok is True, "Rule 2: flagged, never rejected"
        assert v.flagged is True, (
            "the exact parameters ADR 0023 removed from the defaults are "
            "still accepted unflagged when supplied through the API"
        )
        assert "fixed point" in (v.flag_reason or "")

    def test_the_flagged_run_is_the_one_that_goes_negative(self):
        # Ties the flag to the physical failure rather than to a number.
        result = simulate_lotka_volterra(**ADR_0023, end=20.0, points=2001)
        data = np.asarray(result.data, dtype=float)
        prey = data[:, 1]

        assert prey.min() < 0.0, (
            "expected the negative-prey excursion here; if this fails the "
            "integrator has changed and the regression no longer reproduces"
        )
        assert result.flagged is True, (
            f"prey reached {prey.min():.3e} -- a population the model cannot "
            "represent -- and the result reported flagged=False"
        )

    def test_the_conserved_quantity_is_genuinely_destroyed_there(self):
        # Establishes that the flag marks lost physics, not mere aesthetics.
        result = simulate_lotka_volterra(**ADR_0023, end=20.0, points=2001)
        data = np.asarray(result.data, dtype=float)
        H = _conserved(data[:, 1], data[:, 2], ADR_0023["alpha"],
                       ADR_0023["beta"], ADR_0023["gamma"], ADR_0023["delta"])
        drift = (H.max() - H.min()) / abs(H[0])
        assert drift > 0.1, f"expected catastrophic drift, measured {drift:.2e}"


class TestTheFixDoesNotCryWolf:
    def test_corrected_defaults_are_not_flagged(self):
        v = validate_lotka_volterra_params(**CORRECTED)
        assert v.flagged is False, f"unexpected flag: {v.flag_reason}"

    def test_a_well_conditioned_orbit_conserves_H(self):
        result = simulate_lotka_volterra(**CORRECTED, end=20.0, points=2001)
        data = np.asarray(result.data, dtype=float)
        H = _conserved(data[:, 1], data[:, 2], CORRECTED["alpha"],
                       CORRECTED["beta"], CORRECTED["gamma"], CORRECTED["delta"])
        assert (H.max() - H.min()) / abs(H[0]) < 1e-5
        assert result.flagged is False

    def test_just_inside_the_threshold_is_not_flagged(self):
        gamma, delta = 0.4, 0.1
        p_star = delta / gamma
        v = validate_lotka_volterra_params(
            alpha=1.1, beta=0.4, gamma=gamma, delta=delta,
            p0=p_star * (LV_EXCURSION_RATIO_FLAG_ABOVE * 0.9), v0=2.75,
        )
        assert v.flagged is False, f"unexpected flag: {v.flag_reason}"

    def test_just_outside_the_threshold_is_flagged(self):
        gamma, delta = 0.4, 0.1
        p_star = delta / gamma
        v = validate_lotka_volterra_params(
            alpha=1.1, beta=0.4, gamma=gamma, delta=delta,
            p0=p_star * (LV_EXCURSION_RATIO_FLAG_ABOVE * 1.1), v0=2.75,
        )
        assert v.flagged is True


class TestBothDirectionsAndBothSpecies:
    def test_a_start_far_BELOW_the_fixed_point_is_also_flagged(self):
        # The ratio is symmetric: 1/40th of the fixed point is as extreme
        # as 40x it, and traces the same large orbit.
        gamma, delta = 0.4, 0.1
        p_star = delta / gamma
        v = validate_lotka_volterra_params(
            alpha=1.1, beta=0.4, gamma=gamma, delta=delta,
            p0=p_star / 40.0, v0=2.75,
        )
        assert v.flagged is True, "only the above-fixed-point direction is checked"

    def test_the_predator_axis_is_checked_too(self):
        # v* = alpha/beta = 2.75; start the PREY at its fixed point so only
        # the predator excursion can trip the flag.
        v = validate_lotka_volterra_params(
            alpha=1.1, beta=0.4, gamma=0.4, delta=0.1,
            p0=0.25, v0=2.75 * 40.0,
        )
        assert v.flagged is True, "excursion is only checked on the prey axis"
        assert "v0" in (v.flag_reason or "")
