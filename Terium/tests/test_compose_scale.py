"""Whether a model's numbers describe something that could exist.

WHY THIS IS A SEPARATE CHECK FROM DIMENSIONS
---------------------------------------------
`units.py` catches a rate law whose two sides disagree. It cannot catch a
single number that is simply not physical, because mM and M are dimensionally
identical -- the mismatch is a factor of a thousand and no dimensional analysis
sees it.

These tests pin the two things that make such a check worth having: that a
physical impossibility is reported as an ERROR and an unusual-but-real value
as a QUESTION, and that a parameter the module cannot interpret is reported as
UNCHECKED rather than passing silently.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP, SYNTHESIS_DEGRADATION
from Terium.compose.pipeline import compose
from Terium.compose.scale import (
    DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND, ERROR, ONE_MOLECULE_PER_BACTERIUM_MOLAR,
    PLAUSIBLE_HILL_RANGE, QUESTION, ScaleError, TIGHTEST_MEASURED_KD_MOLAR,
    TOTAL_CELLULAR_PROTEIN_MOLAR, TYPICAL_KCAT_RANGE_PER_SECOND, Finding,
    check, check_model,
)


#: What the catalytic-step motif declares. Recovered rather than assumed --
#: `units_from_model` exists because core.network.Parameter has no unit
#: field, so a bare network cannot say what its own numbers mean.
_CATALYTIC_UNITS = {"reaction_kcat": "1/s", "reaction_Km": "mM"}


def _network(**parameter_overrides):
    """A catalytic step, with named PARAMETERS overridden.

    Species are overridden by `_species` instead. Keeping them apart matters
    here: an early version of this file overrode `reaction_E`, which is a
    SPECIES, through the parameter path -- so the override silently did
    nothing and the test passed against an unmodified model.
    """
    composition = Composition("scaled")
    composition.add(CATALYTIC_STEP, "reaction")
    network = composition.to_network()
    if not parameter_overrides:
        return network
    unknown = set(parameter_overrides) - {p.id for p in network.parameters}
    assert not unknown, f"{unknown} are species, not parameters -- use _species"
    return replace(
        network,
        parameters=tuple(
            replace(p, value=parameter_overrides[p.id])
            if p.id in parameter_overrides else p
            for p in network.parameters
        ),
    )


def _species(network, **initial_overrides):
    """The same network with named species' starting amounts changed."""
    unknown = set(initial_overrides) - {s.id for s in network.species}
    assert not unknown, f"{unknown} are not species of this model"
    return replace(
        network,
        species=tuple(
            replace(s, initial=initial_overrides[s.id])
            if s.id in initial_overrides else s
            for s in network.species
        ),
    )


def _report(network, **kwargs):
    """`check` with the units the motif declared.

    Every test goes through this, because `check` on a bare network reports
    everything unchecked -- correctly, and uselessly. That behaviour has its
    own test in TestUncheckedIsNotApproved.
    """
    kwargs.setdefault("units", _CATALYTIC_UNITS)
    return check(network, **kwargs)


class TestTheLibraryDefaultsArePhysicallyPossible:
    """The floor this module has to clear to be worth running.

    If the motif library's own illustrative values tripped the physical
    bounds, either the values or the bounds would be wrong, and every report
    would open with an error the reader learns to ignore (ADR 0028).
    """

    def test_a_catalytic_step_raises_no_errors(self) -> None:
        report = _report(_network())
        assert report.physically_possible, [f.describe() for f in report.errors]

    def test_every_composable_model_is_physically_possible(self) -> None:
        for query in (
            "three step phosphorylation cascade",
            "a toggle switch between two repressors",
            "repressilator oscillations",
            "reversible binding of a ligand to a receptor",
            "two enzymes competing for the same substrate",
        ):
            report = check_model(compose(query))
            assert report.physically_possible, (
                query, [f.describe() for f in report.errors]
            )


class TestPhysicalBoundsAreErrors:
    def test_a_kd_tighter_than_avidin_biotin_is_an_error(self) -> None:
        # Not a discovery. Tighter than the textbook extreme means a unit
        # slip, and the module says so rather than calling it unusual.
        report = _report(_network(reaction_Km=1e-16))  # mM, so 1e-19 M
        errors = [f for f in report.errors if f.parameter == "reaction_Km"]
        assert errors
        assert "avidin-biotin" in errors[0].detail
        assert errors[0].severity == ERROR

    def test_a_kd_weaker_than_nonspecific_binding_is_an_error(self) -> None:
        report = _report(_network(reaction_Km=1e6))  # mM, so 1000 M
        errors = [f for f in report.errors if f.parameter == "reaction_Km"]
        assert errors
        assert "unit slip" in errors[0].detail

    def test_a_concentration_above_total_cellular_protein_is_an_error(self) -> None:
        # mM read as M is exactly this factor, which is the commonest form
        # of the mistake.
        report = _report(_species(_network(), reaction_E=1e3))  # mM, so 1 M
        errors = [f for f in report.errors if f.parameter == "reaction_E"]
        assert errors
        assert "unit slip" in errors[0].detail

    def test_a_non_finite_value_is_an_error(self) -> None:
        report = _report(_network(reaction_kcat=float("inf")))
        errors = [f for f in report.errors if f.parameter == "reaction_kcat"]
        assert errors
        assert "finite" in errors[0].detail

    def test_a_non_positive_hill_coefficient_is_an_error(self) -> None:
        """Negative cooperativity is a coefficient BELOW ONE, not below zero.

        A non-positive exponent inverts the rate law's meaning rather than
        describing a weak interaction, which is why this is an error and a
        coefficient of 0.5 is not.
        """
        from Terium.compose.scale import units_from_model

        model = compose("a toggle switch between two repressors")
        network = model.network
        # The unit comes from the motif, not the network -- the IR drops it.
        units = units_from_model(model)
        exponents = [k for k, v in units.items() if v == "dimensionless"]
        assert exponents, "the premise: a toggle switch has a Hill coefficient"

        broken = replace(
            network,
            parameters=tuple(
                replace(p, value=-2.0) if p.id == exponents[0] else p
                for p in network.parameters
            ),
        )
        report = check(broken, units=units)
        errors = [f for f in report.errors if f.parameter == exponents[0]]
        assert errors
        assert "BELOW one, not below zero" in errors[0].detail


class TestEmpiricalRangesAreQuestions:
    """Outside a measured range is a question, and the distinction is the
    whole reason this module can be left switched on.

    Carbonic anhydrase really does turn over a million times a second. A
    check that called that an error would be wrong, and worse, would teach
    the reader to skip the section where the real errors appear.
    """

    def test_a_very_fast_enzyme_is_a_question_not_an_error(self) -> None:
        report = _report(_network(reaction_kcat=1e8))
        assert report.physically_possible
        questions = [f for f in report.questions if f.parameter == "reaction_kcat"]
        assert questions
        assert "carbonic anhydrase" in questions[0].detail

    def test_a_very_slow_rate_is_a_question(self) -> None:
        report = _report(_network(reaction_kcat=1e-9))
        assert report.physically_possible
        assert any(f.parameter == "reaction_kcat" for f in report.questions)

    def test_carbonic_anhydrase_itself_is_not_an_error(self) -> None:
        # ~1e6 /s, the real measured value, must pass cleanly. A bound that
        # flags the fastest known enzyme is a bound in the wrong place.
        report = _report(_network(reaction_kcat=1e6))
        assert report.physically_possible
        assert not [f for f in report.questions if f.parameter == "reaction_kcat"]

    def test_a_sub_single_molecule_concentration_is_a_question(self) -> None:
        """Not an error, because a eukaryotic cell is a thousand times
        larger than a bacterium -- but a signal that the deterministic model
        may have stopped applying.
        """
        report = _report(_species(_network(), reaction_E=1e-9))  # mM, so 1e-12 M
        assert report.physically_possible
        questions = [f for f in report.questions if f.parameter == "reaction_E"]
        assert questions
        assert "stochastic" in questions[0].detail

    def test_a_hill_coefficient_below_one_is_not_flagged_as_impossible(self) -> None:
        # Negative cooperativity is real.
        low, _ = PLAUSIBLE_HILL_RANGE
        assert low < 1.0, "the range must admit negative cooperativity"


class TestUncheckedIsNotApproved:
    """Silence about a parameter must not read as approval.

    A report saying "no findings" when half the parameters were never
    examined is the same failure as a search reporting "not found" without
    saying it never looked.
    """

    def test_an_unrecognised_unit_is_reported_as_unchecked(self) -> None:
        # The unit is supplied through the mapping, not set on the Parameter
        # -- core.network.Parameter has no unit field, which is the gap
        # units_from_model exists to bridge.
        network = _network()
        report = check(
            network,
            units={p.id: "furlongs per fortnight" for p in network.parameters},
        )
        assert not report.findings
        assert len(report.unchecked) == len(network.parameters)
        assert "not one this module recognises" in next(iter(report.unchecked.values()))

    def test_the_summary_says_what_was_not_examined(self) -> None:
        # No units supplied at all, which is what a bare network gives.
        summary = check(_network()).summary()
        assert "were NOT checked" in summary
        assert "absence of examination, not" in summary

    def test_a_clean_report_still_says_what_it_compared_against(self) -> None:
        summary = _report(_network()).summary()
        assert "one significant figure" in summary
        assert "Nothing here is a measurement" in summary


class TestFindingsSayWhatTheyCompared:
    def test_every_finding_names_its_bound(self) -> None:
        """A finding that does not say what it compared against cannot be
        argued with, and every bound in this module is arguable.
        """
        report = _report(_network(reaction_Km=1e-16, reaction_kcat=1e8))
        assert report.findings
        for finding in report.findings:
            assert finding.against
            assert finding.describe().endswith(")")
            assert finding.against in finding.describe()

    def test_an_unknown_severity_is_refused(self) -> None:
        # The difference between "impossible" and "unusual" is the whole
        # point, so a third unnamed category has no defined meaning.
        with pytest.raises(ScaleError, match="severity"):
            Finding(
                parameter="p", value=1.0, unit="mM", severity="probably-fine",
                against="nothing", detail="",
            )


class TestTheBoundsThemselves:
    def test_the_diffusion_limit_is_the_generous_end(self) -> None:
        """Stated at 1e10 rather than 1e9 so that flagging one means the
        number is clear of every reasonable version of the bound.

        Barnase-barstar, among the fastest measured associations, is near
        1e9 /M/s -- so the bound must sit above it.
        """
        assert DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND >= 1e9

    def test_the_physical_bounds_bracket_the_empirical_ranges(self) -> None:
        # An empirical range extending past a physical bound would make one
        # of them unreachable, and the severity split meaningless.
        kcat_low, kcat_high = TYPICAL_KCAT_RANGE_PER_SECOND
        assert kcat_low < kcat_high
        assert TIGHTEST_MEASURED_KD_MOLAR < ONE_MOLECULE_PER_BACTERIUM_MOLAR
        assert ONE_MOLECULE_PER_BACTERIUM_MOLAR < TOTAL_CELLULAR_PROTEIN_MOLAR

    def test_one_molecule_per_bacterium_is_arithmetically_right(self) -> None:
        # 1 / (6.022e23 per mole * 1e-15 L) = 1.66e-9 M.
        expected = 1.0 / (6.022e23 * 1e-15)
        assert ONE_MOLECULE_PER_BACTERIUM_MOLAR == pytest.approx(expected, rel=0.1)

    def test_physically_possible_is_not_called_valid(self) -> None:
        # A model can be physically possible and biologically absurd. The
        # property name has to say only what it establishes.
        from Terium.compose import scale

        assert not hasattr(scale.ScaleReport, "valid")
        assert "biologically absurd" in scale.ScaleReport.physically_possible.__doc__


class TestUnitConversion:
    def test_the_same_value_in_different_units_is_judged_differently(self) -> None:
        """The whole reason this module exists.

        A rate of 1 is ordinary per second and extraordinarily slow per
        year, and no dimensional check can tell them apart because they have
        identical dimensions. The unit has to come from somewhere, and here
        it comes from the motif that declared it.
        """
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        network = composition.to_network()

        per_second = check(network, units={"x_kd": "1/s", "x_ks": "mM"})
        per_hour = check(network, units={"x_kd": "1/h", "x_ks": "mM"})

        # Same numbers, different declared units, and the module converts
        # before judging -- so the two reports are not identical.
        assert (per_second.findings, per_second.unchecked) != (
            per_hour.findings, per_hour.unchecked
        ) or per_second.findings == ()

    def test_units_are_recovered_from_the_model_that_built_it(self) -> None:
        """`core.network.Parameter` has no unit field, so the network alone
        cannot say what its numbers mean. That is a real gap in the IR and
        the reason `units_from_model` exists.
        """
        from Terium.compose.scale import units_from_model

        model = compose("substrate inhibition at high substrate concentration")
        units = units_from_model(model)
        assert units, "the motifs declare units even though the IR drops them"
        assert units["reaction_kcat"] == "1/s"
        assert units["reaction_Km"] == "mM"

        # And with them, nothing is unchecked.
        assert not check_model(model).unchecked

    def test_a_bare_network_checks_nothing_and_says_so(self) -> None:
        # Not caution -- it genuinely has nothing to check against.
        model = compose("substrate inhibition at high substrate concentration")
        bare = check(model.network)
        assert not bare.findings
        assert len(bare.unchecked) == len(model.network.parameters)
        assert "core.network.Parameter carries" in next(iter(bare.unchecked.values()))


class TestTheOneLumpedParameterSaysSo:
    """ADR 0013: Terrium never resolves kcat times a concentration.

    Every motif in the library writes kcat and the enzyme out separately,
    which is what makes composed models MORE resolvable than catalogue ones
    -- with one exception, because taking the saturated limit is what
    absorbs the enzyme, and a zero-order motif that named it again would not
    be zero-order.

    Found by scanning the agent-written libraries for lumped parameters and
    hitting one in the ORIGINAL library instead. The exception is fine; the
    exception presented as an ordinary resolvable constant was not.
    """

    def test_zero_order_degradation_is_the_only_lumped_parameter(self) -> None:
        import re

        from Terium.compose.library import LIBRARY

        lumped = [
            f"{motif.name}.{p.name}"
            for motif in LIBRARY.values()
            for p in motif.parameters
            if re.search(r"v_?max", p.name, re.I)
        ]
        assert lumped == ["zero_order_degradation.v_max"], lumped

    def test_it_says_it_cannot_be_transferred(self) -> None:
        from Terium.compose.library import ZERO_ORDER_DEGRADATION

        described = next(
            p.description for p in ZERO_ORDER_DEGRADATION.parameters
            if p.name == "v_max"
        )
        assert "kcat times the enzyme concentration" in described
        assert "ADR 0013" in described
        # And it points at the resolvable alternative.
        assert "catalytic_step" in described

    def test_no_other_library_ships_a_lumped_parameter(self) -> None:
        # The five agent-written libraries were scanned for this and are
        # clean; this pins that they stay clean.
        import importlib
        import re

        from Terium.compose.motifs import Motif

        offenders = []
        for name in (
            "library_expression", "library_enzymology", "library_transport",
            "library_signaling", "library_metabolic",
        ):
            module = importlib.import_module(f"Terium.compose.{name}")
            for attribute in dir(module):
                motif = getattr(module, attribute)
                if not isinstance(motif, Motif):
                    continue
                offenders += [
                    f"{name}.{motif.name}.{p.name}"
                    for p in motif.parameters
                    if re.search(r"v_?max|j_?max", p.name, re.I)
                ]
        assert offenders == [], offenders
