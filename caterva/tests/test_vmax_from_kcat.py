"""Vmax = kcat * [E]0 — the bridge that makes a resolved kcat simulable.

ADR 0012 closed the kcat extraction and deliberately stopped short of
simulating it: the engine takes Vmax, and converting a turnover number
requires a total enzyme concentration that BRENDA does not report. ADR 0013
supplies that concentration as an explicit caller input rather than a
default, which is what makes the conversion honest.

The ground truth here is not the engine's own output. `test_end_to_end`
feeds a kcat-derived Vmax into the real Michaelis-Menten simulation and
checks it against the **implicit closed form**

    Km * ln(S0/S) + (S0 - S) = Vmax * t

which is independently derivable and is what Stage 1 established as Rule 1
for this domain.
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
    ENZYME_CONC_MM_RATIO_FLAG_ABOVE,
    simulate_michaelis_menten,
    vmax_from_kcat,
)


class TestTheArithmetic:
    def test_vmax_is_the_product(self):
        vmax, validation = vmax_from_kcat(kcat=10.0, enzyme_conc=0.001)
        assert vmax == pytest.approx(0.01)
        assert validation.ok is True

    def test_units_compose_as_documented(self):
        """kcat (1/s) x [E]0 (mM) -> Vmax (mM/s).

        Uses the real captured AChE golden value: 118 s^-1
        (6-monoacetylmorphine, Homo sapiens, pH 7.4, 37 C, BRENDA ref
        750291) at a dilute 10 nM enzyme concentration.
        """
        vmax, validation = vmax_from_kcat(kcat=118.0, enzyme_conc=1e-5, km=0.1)
        assert vmax == pytest.approx(118.0 * 1e-5)
        assert validation.ok is True
        assert validation.flagged is False

    def test_scaling_is_linear_in_enzyme(self):
        """Doubling the enzyme doubles Vmax. This is the whole physical
        content of the relation, and it is what distinguishes kcat (a
        per-molecule property) from Vmax (an assay property)."""
        base, _ = vmax_from_kcat(kcat=50.0, enzyme_conc=1e-4)
        doubled, _ = vmax_from_kcat(kcat=50.0, enzyme_conc=2e-4)
        assert doubled == pytest.approx(2.0 * base)


class TestRule2Contract:
    """Impossible is rejected; implausible is flagged. Never collapsed."""

    @pytest.mark.parametrize(
        ("kcat", "enzyme_conc", "expect_in_error"),
        [
            (0.0, 1e-5, "kcat"),
            (10.0, 0.0, "enzyme_conc"),
            (-1.0, 1e-5, "kcat"),
            (10.0, -1e-5, "enzyme_conc"),
            (float("nan"), 1e-5, "kcat"),
            (float("inf"), 1e-5, "kcat"),
        ],
    )
    def test_impossible_inputs_are_rejected(self, kcat, enzyme_conc, expect_in_error):
        vmax, validation = vmax_from_kcat(kcat=kcat, enzyme_conc=enzyme_conc)
        assert validation.ok is False
        assert vmax == 0.0
        assert any(expect_in_error in e for e in validation.errors), validation.errors

    def test_zero_enzyme_is_rejected_here_with_the_real_reason(self):
        """Vmax = 0 is already rejected downstream as 'a model that provably
        cannot turn over'. Catching it here names the actual cause -- there
        is no enzyme -- instead of a symptom the student has to work back
        from."""
        _, validation = vmax_from_kcat(kcat=100.0, enzyme_conc=0.0)
        assert validation.ok is False
        assert any("enzyme_conc" in e for e in validation.errors)

    def test_dilute_enzyme_is_not_flagged(self):
        _, validation = vmax_from_kcat(kcat=10.0, enzyme_conc=1e-6, km=1.0)
        assert validation.ok is True
        assert validation.flagged is False

    def test_enzyme_comparable_to_km_is_flagged_not_rejected(self):
        """The MM rate law assumes [E]0 << Km. Past that the ES complex
        holds a non-negligible share of substrate (tight-binding/Morrison
        regime). The run still happens -- the warning travels with it."""
        _, validation = vmax_from_kcat(kcat=10.0, enzyme_conc=1.0, km=1.0)
        assert validation.ok is True, "must not be rejected: the model still runs"
        assert validation.flagged is True
        assert "Km" in (validation.flag_reason or "")

    def test_the_flag_boundary_is_exact(self):
        """At exactly the ratio: not flagged. Just above: flagged.
        An off-by-one here would either nag on every valid run or stay
        silent through the regime it exists to warn about."""
        km = 0.1
        at = ENZYME_CONC_MM_RATIO_FLAG_ABOVE * km
        _, at_boundary = vmax_from_kcat(kcat=10.0, enzyme_conc=at, km=km)
        _, just_over = vmax_from_kcat(kcat=10.0, enzyme_conc=at * 1.01, km=km)
        assert at_boundary.flagged is False
        assert just_over.flagged is True

    def test_no_km_means_no_ratio_check(self):
        """The ratio check needs a Km. Without one the conversion still
        works -- it must not silently invent a Km to check against."""
        vmax, validation = vmax_from_kcat(kcat=10.0, enzyme_conc=5.0)
        assert vmax == pytest.approx(50.0)
        assert validation.flagged is False


class TestEndToEndAgainstTheClosedForm:
    def test_a_kcat_derived_vmax_reproduces_the_implicit_solution(self):
        """Rule 1: check the simulation against independently derivable
        ground truth, not against itself.

        Km*ln(S0/S) + (S0-S) = Vmax*t holds for the MM ODE regardless of
        where Vmax came from -- so if the conversion is wrong, the residual
        will not vanish.
        """
        kcat, enzyme_conc, km, s0 = 118.0, 1e-5, 0.1, 1.0
        vmax, validation = vmax_from_kcat(kcat=kcat, enzyme_conc=enzyme_conc, km=km)
        assert validation.ok and not validation.flagged

        result = simulate_michaelis_menten(
            km=km, vmax=vmax, s0=s0, end=100.0, points=51
        )
        times = result.column("time")
        substrate = result.column("S")

        # Skip t=0 (trivially satisfied) and any point where S has been
        # driven so low that log amplifies integrator noise.
        checked = 0
        for t, s in zip(times[1:], substrate[1:]):
            if s <= 1e-6 * s0:
                continue
            lhs = km * math.log(s0 / s) + (s0 - s)
            rhs = vmax * t
            assert lhs == pytest.approx(rhs, rel=1e-3), (
                f"closed form violated at t={t}: {lhs} vs {rhs}"
            )
            checked += 1

        assert checked >= 10, f"only {checked} points checked; test is too weak"

    def test_the_conversion_is_reachable_through_the_api_runner(self):
        """The engine function existing is not the same as a request being
        able to use it.

        `parse_brenda_turnover_html` sat with no caller for a whole commit
        because "built" and "reachable" were conflated. This drives
        `run_mm` -- the actual API entry point -- rather than the engine
        function directly.
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

        import caterva_runner  # noqa: PLC0415

        payload = caterva_runner.run_mm(
            {"km": 0.1, "kcat": 118.0, "enzyme_conc": 1e-5, "s0": 1.0,
             "end": 1.0, "points": 3}
        )

        assert payload["parameters"]["vmax"] == pytest.approx(118.0 * 1e-5)
        # The inputs it was derived FROM are echoed back, so a student can
        # see the number came from a turnover value and a concentration
        # they chose -- not from thin air.
        assert payload["parameters"]["kcat"] == 118.0
        assert payload["parameters"]["enzyme_conc"] == 1e-5
        assert "derived from kcat" in payload["derivedNote"]
        assert payload["flagged"] is False

    def test_the_runner_surfaces_the_stretched_approximation_flag(self):
        """A conversion flag must survive to the response. The simulation
        itself is fine here, so if the flag were only read off the
        simulation result it would be silently dropped."""
        runner_dir = (
            _REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
        )
        if not runner_dir.is_dir():
            pytest.skip("api-server runner not present in this checkout")
        if str(runner_dir) not in sys.path:
            sys.path.insert(0, str(runner_dir))

        import caterva_runner  # noqa: PLC0415

        payload = caterva_runner.run_mm(
            {"km": 0.1, "kcat": 10.0, "enzyme_conc": 0.05, "s0": 1.0,
             "end": 1.0, "points": 3}
        )

        assert payload["flagged"] is True
        assert "Km" in payload["flagReason"]

    def test_half_a_conversion_is_rejected(self):
        """kcat alone cannot produce a Vmax, and [E]0 alone has nothing to
        multiply. Silently falling back to the default Vmax would run a
        simulation the caller did not ask for."""
        runner_dir = (
            _REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
        )
        if not runner_dir.is_dir():
            pytest.skip("api-server runner not present in this checkout")
        if str(runner_dir) not in sys.path:
            sys.path.insert(0, str(runner_dir))

        import caterva_runner  # noqa: PLC0415

        for partial in ({"kcat": 118.0}, {"enzyme_conc": 1e-5}):
            with pytest.raises(ValueError, match="cannot be derived"):
                caterva_runner.run_mm({"km": 0.1, "s0": 1.0, **partial})

    def test_a_request_with_no_route_to_a_vmax_is_rejected(self):
        """No vmax, no kcat, no enzyme_conc: there is no route to a Vmax at
        all. The runner used to silently fall back to vmax = 5.0 here -- a
        number nobody chose and nothing verified. resolveQuery()'s hard rule
        (RequiredParametersMissingError on any default-origin vmax) already
        stops any such query before the runner is spawned, so the fallback
        was dead code; it has been replaced by an explicit rejection so it
        cannot quietly become live again.
        """
        runner_dir = (
            _REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
        )
        if not runner_dir.is_dir():
            pytest.skip("api-server runner not present in this checkout")
        if str(runner_dir) not in sys.path:
            sys.path.insert(0, str(runner_dir))

        import caterva_runner  # noqa: PLC0415

        with pytest.raises(ValueError, match="needs a Vmax"):
            caterva_runner.run_mm(
                {"km": 0.1, "s0": 1.0, "end": 1.0, "points": 3}
            )

    def test_an_explicit_vmax_wins_over_a_derivable_one(self):
        """vmax is what the engine integrates. Honouring the derived value
        over a stated one would silently overwrite the caller's request."""
        runner_dir = (
            _REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
        )
        if not runner_dir.is_dir():
            pytest.skip("api-server runner not present in this checkout")
        if str(runner_dir) not in sys.path:
            sys.path.insert(0, str(runner_dir))

        import caterva_runner  # noqa: PLC0415

        payload = caterva_runner.run_mm(
            {"km": 0.1, "vmax": 7.0, "kcat": 118.0, "enzyme_conc": 1e-5,
             "s0": 1.0, "end": 1.0, "points": 3}
        )
        assert payload["parameters"]["vmax"] == 7.0
        assert "derivedNote" not in payload

    def test_doubling_enzyme_halves_the_time_to_a_given_conversion(self):
        """A consequence a student can see on the plot, and one that would
        break if the conversion were, say, additive instead of
        multiplicative."""
        km, s0 = 0.1, 1.0
        target = 0.5 * s0

        def time_to_target(enzyme_conc: float) -> float:
            vmax, _ = vmax_from_kcat(kcat=118.0, enzyme_conc=enzyme_conc, km=km)
            # Closed form solved for t at S = target.
            return (km * math.log(s0 / target) + (s0 - target)) / vmax

        assert time_to_target(2e-5) == pytest.approx(0.5 * time_to_target(1e-5))
