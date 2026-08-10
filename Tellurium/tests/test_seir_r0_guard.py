"""Regression: the R0 plausibility bound must not depend on i0.

`validate_sir_params` checked R0 = beta/gamma *after* an early return on
`i0 == 0`. SIR's own semantics make that harmless — with no infectives and
no exposed compartment, nothing can happen. SEIR is different: `e0` alone
seeds a full epidemic, and `i0 = 0` is the API's shipped default for that
domain (`tellurium_runner.py`).

So at SEIR's normal operating point the R0 bound was disabled entirely.
Measured before the fix:

    validate_seir_params(beta=100, gamma=0.1, s0=990, e0=10, i0=0)
      -> flagged = False, flag_reason = None          (R0 = 1000)
    simulate_seir(same parameters)
      -> ran to completion, peak I = 499.45, reporting flagged = False

An R0 of 1000 is roughly fifty times measles. The student saw a normal
epidemic curve with no indication that the parameters were nonsense.

R0 is a property of the disease parameters alone — it does not depend on
initial conditions — so the check now happens before any early return, via
the shared `_flag_implausible_r0` helper both validators call.

Rule 2 (`docs/CONSTITUTION.md`): implausible-but-arithmetically-valid
values are FLAGGED, never rejected. The simulation still runs; the student
is told the number sits outside anything observed.
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

from core.data_structures import R0_IMPLAUSIBLE_ABOVE  # noqa: E402
from core.validation import (  # noqa: E402
    validate_seir_params,
    validate_sir_params,
)
from tellurium_engine import simulate_seir  # noqa: E402

#: Comfortably above the bound; roughly fifty times measles.
ABSURD_BETA, SANE_GAMMA = 100.0, 0.1


class TestSeirR0IsCheckedAtTheShippedDefault:
    """i0 = 0 is SEIR's API default, so this IS the normal path."""

    def test_implausible_r0_is_flagged_when_i0_is_zero(self):
        v = validate_seir_params(
            beta=ABSURD_BETA, sigma=0.2, gamma=SANE_GAMMA,
            s0=990, e0=10, i0=0,
        )
        assert v.ok is True, "Rule 2: flagged, never rejected"
        assert v.flagged is True, (
            "R0 = 1000 went unflagged at SEIR's default i0=0 — the bound "
            "was disabled at the domain's normal operating point"
        )
        assert "R0" in (v.flag_reason or "")

    def test_the_epidemic_that_ran_unflagged_is_now_flagged(self):
        # The end-to-end shape of the bug: a full epidemic with a peak of
        # ~500 infectives, reported as unremarkable.
        result = simulate_seir(
            beta=ABSURD_BETA, sigma=0.2, gamma=SANE_GAMMA,
            s0=990, e0=10, i0=0, r0_recovered=0, end=50, points=201,
        )
        data = np.asarray(result.data, dtype=float)
        infectives = data[:, result.colnames.index("[I]")]

        assert infectives.max() > 100, (
            "expected a real epidemic here; if this fails the scenario has "
            "changed and the regression no longer reproduces"
        )
        assert result.flagged is True, (
            f"an epidemic peaking at {infectives.max():.1f} infectives ran "
            "with flagged=False"
        )

    def test_a_sane_r0_is_not_flagged(self):
        # The other half: the fix must not flag ordinary parameter sets.
        v = validate_seir_params(
            beta=0.3, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=0
        )
        assert v.flagged is False, f"unexpected flag: {v.flag_reason}"

    def test_boundary_is_not_flagged_just_below_the_bound(self):
        gamma = 0.1
        v = validate_seir_params(
            beta=R0_IMPLAUSIBLE_ABOVE * gamma * 0.99,
            sigma=0.2, gamma=gamma, s0=990, e0=10, i0=1,
        )
        assert v.flagged is False


class TestSirKeepsBothSignals:
    """SIR's i0=0 message must survive alongside an R0 flag."""

    def test_implausible_r0_and_zero_i0_both_reported(self):
        v = validate_sir_params(
            beta=ABSURD_BETA, gamma=SANE_GAMMA, s0=990, i0=0
        )
        assert v.flagged is True
        reason = v.flag_reason or ""
        assert "R0" in reason, "R0 flag was lost"
        assert "I0 is zero" in reason, (
            "the no-outbreak signal was overwritten by the R0 flag; both "
            "are true and the student should see both"
        )

    def test_zero_i0_alone_still_reported_with_a_sane_r0(self):
        v = validate_sir_params(beta=0.3, gamma=0.1, s0=990, i0=0)
        assert v.flagged is True
        assert "I0 is zero" in (v.flag_reason or "")
        assert "R0" not in (v.flag_reason or "")

    def test_ordinary_sir_is_unflagged(self):
        v = validate_sir_params(beta=0.3, gamma=0.1, s0=990, i0=10)
        assert v.flagged is False, f"unexpected flag: {v.flag_reason}"


class TestBoundIsSharedNotDuplicated:
    def test_sir_and_seir_agree_on_the_threshold(self):
        """One helper, so the bound cannot drift between the two domains."""
        gamma = 0.1
        just_over = R0_IMPLAUSIBLE_ABOVE * gamma * 1.01
        sir = validate_sir_params(beta=just_over, gamma=gamma, s0=990, i0=10)
        seir = validate_seir_params(
            beta=just_over, sigma=0.2, gamma=gamma, s0=990, e0=10, i0=10
        )
        assert sir.flagged == seir.flagged is True
        assert "R0" in (sir.flag_reason or "")
        assert "R0" in (seir.flag_reason or "")
