"""beta = R0 * gamma, gamma = 1/infectious_period_days -- the bridge that
makes a literature-resolved disease R0 simulable.

`simulate_sir` takes beta and gamma directly, not R0 -- and R0 (plus a
characteristic infectious period / generation time) is what epidemiological
literature actually reports for a named disease. `validate_sir_params`
already defines R0 as beta/gamma internally (it rejects beta/gamma above
R0_IMPLAUSIBLE_ABOVE), so converting a resolved R0 back into (beta, gamma)
is arithmetic, not a new physical claim -- exactly the same shape of bridge
ADR 0012/0013 built for kcat -> Vmax. See
docs/adr/0017-epidemiology-parameter-resolution.md for the literature this
applies to and the serial-interval-as-generation-time caveat.

The ground truth here is not the engine's own output. `test_end_to_end`
feeds an R0-derived (beta, gamma) into the real SIR simulation and checks
it against the independently-derivable peak condition S(t_peak) = N/R0 and
population conservation S+I+R = N -- Stage 1's Rule 1 for this domain.
"""

from __future__ import annotations

import math
import pathlib
import sys

import pytest

_CATERVA = pathlib.Path(__file__).resolve().parents[1]
_REPO = _CATERVA.parent
for _p in (str(_REPO), str(_CATERVA)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from caterva_engine import (  # noqa: E402
    R0_IMPLAUSIBLE_ABOVE,
    beta_gamma_from_r0,
    simulate_sir,
)


class TestTheArithmetic:
    def test_gamma_is_the_reciprocal_of_infectious_period(self):
        _, gamma, validation = beta_gamma_from_r0(r0=2.0, infectious_period_days=5.0)
        assert gamma == pytest.approx(0.2)
        assert validation.ok is True

    def test_beta_is_r0_times_gamma(self):
        beta, gamma, validation = beta_gamma_from_r0(
            r0=3.14, infectious_period_days=5.45
        )
        assert gamma == pytest.approx(1.0 / 5.45)
        assert beta == pytest.approx(3.14 * (1.0 / 5.45))
        assert validation.ok is True

    def test_real_captured_covid19_ancestral_values(self):
        """Hussein et al. (2021), Ann Surg 273(3):416-423,
        DOI 10.1097/SLA.0000000000004400: pooled R0 = 3.14 (95% CI
        2.69-3.59), mean serial interval = 5.45 days (95% CI 4.23-6.66),
        both from the same 39-study meta-analysis (searches through
        2020-05-10, so this is the ancestral/pre-Alpha strain)."""
        beta, gamma, validation = beta_gamma_from_r0(
            r0=3.14, infectious_period_days=5.45
        )
        assert validation.ok is True
        assert validation.flagged is False
        assert beta / gamma == pytest.approx(3.14)

    def test_scaling_is_linear_in_r0(self):
        """Doubling R0 (at fixed infectious period) doubles beta. This is
        the whole physical content of the relation."""
        base, _, _ = beta_gamma_from_r0(r0=2.0, infectious_period_days=5.0)
        doubled, _, _ = beta_gamma_from_r0(r0=4.0, infectious_period_days=5.0)
        assert doubled == pytest.approx(2.0 * base)

    def test_longer_infectious_period_lowers_gamma(self):
        """A longer infectious period means slower recovery -- gamma must
        fall, not rise, as infectious_period_days grows."""
        _, gamma_short, _ = beta_gamma_from_r0(r0=2.0, infectious_period_days=2.0)
        _, gamma_long, _ = beta_gamma_from_r0(r0=2.0, infectious_period_days=10.0)
        assert gamma_long < gamma_short


class TestRule2Contract:
    """Impossible is rejected. (No flagged/implausible tier lives in the
    bridge itself -- validate_sir_params re-derives R0 = beta/gamma from
    whatever reaches it and applies R0_IMPLAUSIBLE_ABOVE there, so an
    implausible R0 is still caught, just one layer downstream, avoiding
    two thresholds that could drift apart.)"""

    @pytest.mark.parametrize(
        ("r0", "infectious_period_days", "expect_in_error"),
        [
            (0.0, 5.0, "r0"),
            (2.0, 0.0, "infectious_period_days"),
            (-1.0, 5.0, "r0"),
            (2.0, -5.0, "infectious_period_days"),
            (float("nan"), 5.0, "r0"),
            (float("inf"), 5.0, "r0"),
        ],
    )
    def test_impossible_inputs_are_rejected(
        self, r0, infectious_period_days, expect_in_error
    ):
        beta, gamma, validation = beta_gamma_from_r0(
            r0=r0, infectious_period_days=infectious_period_days
        )
        assert validation.ok is False
        assert beta == 0.0 and gamma == 0.0
        assert any(expect_in_error in e for e in validation.errors), validation.errors

    def test_zero_infectious_period_is_rejected_here_with_the_real_reason(self):
        """A zero-day infectious period would make gamma infinite. Catching
        it here names the actual cause instead of a downstream ZeroDivision
        or an inf silently reaching the engine."""
        _, _, validation = beta_gamma_from_r0(r0=2.0, infectious_period_days=0.0)
        assert validation.ok is False
        assert any("infectious_period_days" in e for e in validation.errors)

    def test_implausible_r0_is_still_caught_downstream(self):
        """The bridge itself does not reject an implausible R0 -- but
        validate_sir_params, which every simulate_sir call runs through,
        must still catch it via the same R0 = beta/gamma check it already
        performs. validate_sir_params *flags* (not rejects) an R0 above
        R0_IMPLAUSIBLE_ABOVE -- Rule 2's impossible/implausible distinction,
        the same tier vmax_from_kcat's enzyme-concentration ratio check
        uses. This proves the layering choice documented above doesn't
        quietly lose the check, just moves it to the tier the engine
        already applies it at."""
        from caterva_engine import validate_sir_params

        beta, gamma, validation = beta_gamma_from_r0(
            r0=R0_IMPLAUSIBLE_ABOVE + 5.0, infectious_period_days=5.0
        )
        assert validation.ok is True, "the bridge itself only rejects impossibility"

        downstream = validate_sir_params(beta=beta, gamma=gamma, s0=999.0, i0=1.0)
        assert downstream.ok is True, "implausible is flagged, not rejected"
        assert downstream.flagged is True
        assert "R0" in (downstream.flag_reason or "")


class TestEndToEndAgainstThePeakCondition:
    def test_an_r0_derived_beta_gamma_reproduces_the_peak_condition(self):
        """Rule 1: check the simulation against independently derivable
        ground truth, not against itself.

        At the epidemic peak, dI/dt = 0, so S(t_peak) = gamma/beta * N =
        N/R0 -- true regardless of where beta and gamma came from. If the
        R0 -> (beta, gamma) conversion were wrong, the simulated peak would
        land at the wrong S.
        """
        r0, infectious_period_days = 3.14, 5.45  # Hussein et al. 2021, COVID-19
        beta, gamma, validation = beta_gamma_from_r0(
            r0=r0, infectious_period_days=infectious_period_days
        )
        assert validation.ok and not validation.flagged

        s0, i0 = 999.0, 1.0
        n = s0 + i0
        result = simulate_sir(
            beta=beta, gamma=gamma, s0=s0, i0=i0, end=200.0, points=2001
        )
        s = result.column("S")
        i = result.column("I")
        r = result.column("R")

        # Population conservation at every point.
        for si, ii, ri in zip(s, i, r):
            assert (si + ii + ri) == pytest.approx(n, rel=1e-3)

        peak_index = max(range(len(i)), key=lambda k: i[k])
        # Not at either boundary -- otherwise the "peak" is meaningless.
        assert 0 < peak_index < len(i) - 1

        s_at_peak = s[peak_index]
        expected_s_at_peak = n / r0
        assert s_at_peak == pytest.approx(expected_s_at_peak, rel=0.03)

    def test_doubling_r0_speeds_up_the_outbreak(self):
        """A consequence a student can see on the plot: higher R0 (same
        infectious period) burns through susceptibles faster, so the peak
        arrives earlier."""
        s0, i0 = 999.0, 1.0

        def time_to_peak(r0: float) -> float:
            beta, gamma, _ = beta_gamma_from_r0(r0=r0, infectious_period_days=5.0)
            result = simulate_sir(
                beta=beta, gamma=gamma, s0=s0, i0=i0, end=200.0, points=2001
            )
            times = result.column("time")
            i = result.column("I")
            peak_index = max(range(len(i)), key=lambda k: i[k])
            return times[peak_index]

        assert time_to_peak(6.0) < time_to_peak(3.0)
