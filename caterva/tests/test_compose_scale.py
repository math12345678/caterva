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

import pathlib
from dataclasses import replace

import pytest

from caterva.compose.builder import Composition
from caterva.compose.library import CATALYTIC_STEP, SYNTHESIS_DEGRADATION
from caterva.compose.pipeline import compose
from caterva.compose.scale import (
    DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND, ERROR, ONE_MOLECULE_PER_BACTERIUM_MOLAR,
    PLAUSIBLE_HILL_RANGE, QUESTION, ScaleError, TIGHTEST_MEASURED_KD_MOLAR,
    TOTAL_CELLULAR_PROTEIN_MOLAR, TYPICAL_KCAT_RANGE_PER_SECOND, Finding,
    ScaleReport, check, check_model,
)
from caterva.compose.scale import (
    _as_per_molar_per_second, _check_rate, _is_second_order,
)


#: What the catalytic-step motif declares. Kept explicit so these tests
#: drive `check` directly on a bare network, which is the path that still
#: has no units of its own: `core.network.Parameter` now carries a unit and
#: the builder populates it, so a COMPOSED network describes itself, but a
#: network assembled by hand here does not.
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
    # The catalytic step's E is an enzyme -- a protein -- and the protein
    # bound now reaches only species named as such. `check_model` reads
    # this off the composition; a bare network has to be told.
    kwargs.setdefault("proteins", ("reaction_E",))
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
        from caterva.compose.scale import units_from_model

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
        """A unit the module cannot convert leaves the number unexamined.

        Built by hand rather than by the composer: a composed network now
        carries units the motifs declared, so the only way to hold an
        unrecognised one is to construct it.
        """
        network = replace(
            _network(),
            parameters=tuple(
                replace(p, unit="furlongs per fortnight")
                for p in _network().parameters
            ),
        )
        report = check(network)
        assert not report.findings
        assert len(report.unchecked) == len(network.parameters)
        assert "not one this module recognises" in next(iter(report.unchecked.values()))

    def test_a_parameter_with_no_unit_at_all_is_unchecked(self) -> None:
        # What a network built outside the composer looks like. Silence
        # about it must not read as approval.
        network = replace(
            _network(),
            parameters=tuple(replace(p, unit="") for p in _network().parameters),
        )
        summary = check(network).summary()
        assert "were NOT checked" in summary
        assert "absence of examination, not" in summary

    def test_the_parameters_own_unit_beats_a_supplied_one(self) -> None:
        """The motif is the authority on what its own constant means.

        Letting an argument silently reinterpret a declared mM as something
        else would be a worse failure than the gap `units=` was added for.
        """
        network = _network()
        assert all(p.unit for p in network.parameters), "the premise"

        report = check(
            network,
            units={p.id: "furlongs per fortnight" for p in network.parameters},
        )
        assert not report.unchecked, "the declared units should have won"

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
        from caterva.compose import scale

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
        from caterva.compose.scale import units_from_model

        model = compose("substrate inhibition at high substrate concentration")
        units = units_from_model(model)
        assert units, "the motifs declare units even though the IR drops them"
        assert units["reaction_kcat"] == "1/s"
        assert units["reaction_Km"] == "mM"

        # And with them, nothing is unchecked.
        assert not check_model(model).unchecked

    def test_a_composed_network_now_describes_itself(self) -> None:
        """The fix, from the outside.

        This test asserted the opposite until the unit moved onto
        `core.network.Parameter`: a bare composed network reported EVERY
        parameter unchecked, because the builder read the motif's unit and
        dropped it one line later. `units_from_model` was the workaround.
        Now the network arrives already saying what its numbers mean.
        """
        model = compose("substrate inhibition at high substrate concentration")
        bare = check(model.network)          # no units= argument

        assert not bare.unchecked, bare.unchecked
        assert all(p.unit for p in model.network.parameters)
        assert bare.physically_possible


class TestTheOneLumpedParameterSaysSo:
    """ADR 0013: Caterva never resolves kcat times a concentration.

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

        from caterva.compose.library import LIBRARY

        lumped = [
            f"{motif.name}.{p.name}"
            for motif in LIBRARY.values()
            for p in motif.parameters
            if re.search(r"v_?max", p.name, re.I)
        ]
        assert lumped == ["zero_order_degradation.v_max"], lumped

    def test_it_says_it_cannot_be_transferred(self) -> None:
        from caterva.compose.library import ZERO_ORDER_DEGRADATION

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

        from caterva.compose.motifs import Motif

        offenders = []
        for name in (
            "library_expression", "library_enzymology", "library_transport",
            "library_signaling", "library_metabolic",
        ):
            module = importlib.import_module(f"caterva.compose.{name}")
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


class TestCleanIsNotTheSameAsUnexamined:
    """The two states a `findings=()` report used to conflate.

    `unchecked` was added so that "no findings" could not be read as
    "everything is fine" when half the parameters had no recognised unit.
    It only ever recorded the SKIPS, though, so the case where nothing was
    looked at AT ALL still printed as a clean report -- and a composed
    three-tier cascade, twelve parameters with every unit recognised,
    returned a value byte-for-byte identical to a check over an empty
    network.

    A caller cannot tell those apart from the outside, and the one it would
    get wrong is the one that matters.
    """

    class _EmptyNetwork:
        parameters = ()
        species = ()

    def test_an_empty_network_says_it_examined_nothing(self) -> None:
        report = check(self._EmptyNetwork())
        assert report.examined_nothing
        assert report.coverage == "nothing was examined"

    def test_a_real_model_does_not(self) -> None:
        report = check_model(compose("three step phosphorylation cascade"))
        assert not report.examined_nothing
        assert report.checked, "a twelve-parameter model examined nothing"

    def test_every_parameter_is_either_examined_or_skipped(self) -> None:
        """The partition, which is the real invariant.

        The weaker form of this test asserted only that `checked` was
        non-empty -- and a mutation that stopped recording PARAMETERS
        entirely still passed it, because the species loop kept appending
        and five species names were enough to satisfy "non-empty". An
        assertion that looks specific and is not.

        Every parameter must land in exactly one of the two sets. That is
        what makes the counts mean something, and it is what makes
        `examined_nothing` trustworthy rather than merely present.
        """
        for query in (
            "three step phosphorylation cascade",
            "repressilator oscillations",
            "enzyme kinetics with a competitive inhibitor",
        ):
            model = compose(query)
            report = check_model(model)
            names = {p.id for p in model.network.parameters}
            examined = names & set(report.checked)
            skipped = names & set(report.unchecked)

            assert examined | skipped == names, (
                query,
                "parameters in neither set: "
                f"{sorted(names - examined - skipped)}",
            )
            assert not (examined & skipped), (
                query, sorted(examined & skipped),
            )
            assert examined, (query, "no PARAMETER was examined")

    def test_species_are_recorded_separately_from_parameters(self) -> None:
        # `checked` holds both, which is only safe because the names cannot
        # collide. If they ever could, the partition above would go quiet.
        model = compose("three step phosphorylation cascade")
        parameters = {p.id for p in model.network.parameters}
        species = {s.id for s in model.network.species}
        assert not (parameters & species), sorted(parameters & species)

    def test_the_two_reports_are_distinguishable(self) -> None:
        """The whole point. Before `checked`, this assertion was false.

        Both are clean, both have no findings, both have nothing skipped.
        The only thing that separates them is what was looked at.
        """
        empty = check(self._EmptyNetwork())
        real = check_model(compose("three step phosphorylation cascade"))

        assert empty.findings == real.findings == ()
        assert dict(empty.unchecked) == dict(real.unchecked) == {}
        assert empty.physically_possible and real.physically_possible
        # ...and yet:
        assert empty.examined_nothing is not real.examined_nothing
        assert empty.coverage != real.coverage

    def test_physically_possible_is_true_over_nothing(self) -> None:
        """Vacuously, and the docstring now says so.

        Left as-is rather than made to return False: a network with no
        parameters genuinely breaks no physical law, and a bound that
        answered "impossible" for an empty model would be stating something
        untrue in order to be cautious. The honest fix is the separate
        question, not a corrupted answer to this one.
        """
        assert check(self._EmptyNetwork()).physically_possible

        prose = " ".join(ScaleReport.physically_possible.__doc__.split())
        assert "says nothing about COVERAGE" in prose
        assert "examined_nothing" in prose

    def test_a_skipped_parameter_is_not_counted_as_examined(self) -> None:
        # The repressilator carries Hill exponents and rates this module
        # recognises, plus units it does not. The two sets must not overlap.
        report = check_model(compose("repressilator oscillations"))
        assert report.unchecked, "expected some unrecognised units here"
        assert not (set(report.checked) & set(report.unchecked)), (
            "a parameter was reported both examined and skipped"
        )
        assert report.coverage.endswith("for want of a recognised unit")

    def test_coverage_counts_match_the_fields(self) -> None:
        # A summary line that disagreed with the fields it summarises would
        # be worse than not having one.
        report = check_model(compose("repressilator oscillations"))
        assert str(len(report.checked)) in report.coverage
        assert str(len(report.unchecked)) in report.coverage


class TestTheCleanSentenceIsEarned:
    """Three places printed a clean verdict over an unexamined model.

    `summary()` said "every checked number is physically possible", the
    verdict page said "every number physically possible", and the CLI
    explained the gap with a sentence about the architecture that had
    stopped being true. All three are read by someone deciding whether to
    trust a number, and all three read as approval.
    """

    class _EmptyNetwork:
        parameters = ()
        species = ()

    def test_the_summary_refuses_a_clean_bill_over_nothing(self) -> None:
        text = check(self._EmptyNetwork()).summary()
        assert "NOTHING WAS EXAMINED" in text
        assert "physically possible and within the ranges" not in text
        assert "absence of examination" in text

    def test_the_summary_says_how_many_it_examined(self) -> None:
        report = check_model(compose("three step phosphorylation cascade"))
        text = report.summary()
        assert f"All {len(report.checked)} of the numbers examined" in text
        assert "NOTHING WAS EXAMINED" not in text

    def test_the_verdict_note_leads_with_coverage(self) -> None:
        from caterva.compose.verdict import _scale_concerns

        _, note = _scale_concerns(compose("three step phosphorylation cascade"))
        assert "examined" in note
        # The bare claim, with no count attached, is what this replaces.
        assert note != "every number physically possible"

    def test_the_cli_no_longer_claims_parameter_carries_no_unit(self) -> None:
        """The sentence went stale when `Parameter` gained a unit field.

        It is the kind of prose nobody re-reads: an explanation of a
        limitation, printed under a section, that outlived the limitation.
        A reader would conclude the composer cannot check its own units.
        """
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "compose" / "__main__.py"
        ).read_text(encoding="utf-8")
        assert "carries a value and no unit" not in source
        assert "COMPOSED network describes itself" in source


class TestTheDimensionalCheckSaysWhatItLookedAt:
    """`unit_findings() == ()` conflated "all balanced" with "none existed".

    Three callers printed a verdict from that empty tuple: the dossier's
    Dimensions section said "Every rate law balances", `validate` returned
    AGREE, and both are read as a clean result. A composition with no
    instances, or whose motifs declare no reactions, produced the same
    empty tuple as one whose every law balanced.
    """

    class _NoReactions:
        """A composition that declares nothing to check."""

        name = "empty"
        concentration_unit = "mM"
        _instances: tuple = ()

        def unit_environment(self):
            return {}

    def _empty(self):
        from caterva.compose.builder import Composition

        empty = self._NoReactions()
        # Borrow the real implementation rather than reimplementing it,
        # so this cannot drift from what the production path does.
        empty.unit_check = Composition.unit_check.__get__(empty)
        return empty

    def test_a_real_composition_reports_what_it_examined(self) -> None:
        composition = compose(
            "three step phosphorylation cascade"
        ).recognition.composition
        examined, findings = composition.unit_check()
        assert examined > 0
        assert findings == ()
        # The old API still answers the old question.
        assert composition.unit_findings() == findings

    def test_examining_nothing_is_unchecked_not_agreement(self) -> None:
        from caterva.compose.validate import (
            AGREE, CHECK_DIMENSIONS, UNCHECKED, dimension_findings,
        )

        findings = dimension_findings(self._empty())
        assert len(findings) == 1
        assert findings[0].check == CHECK_DIMENSIONS
        assert findings[0].severity == UNCHECKED, (
            "agreement between a check and nothing is not agreement"
        )
        assert findings[0].severity != AGREE
        assert "nothing to run against" in findings[0].detail

    def test_a_real_composition_still_agrees(self) -> None:
        # The check must not have been turned into a permanent UNCHECKED.
        from caterva.compose.validate import AGREE, dimension_findings

        composition = compose(
            "three step phosphorylation cascade"
        ).recognition.composition
        findings = dimension_findings(composition)
        assert len(findings) == 1
        assert findings[0].severity == AGREE
        assert "rate laws evaluate to an amount" in findings[0].detail

    def test_the_dossier_section_does_not_claim_a_clean_check(self) -> None:
        """Run, not read.

        The first version of this test scanned report.py for the honest
        wording. It passed against a mutation that made that wording
        unreachable -- `if not examined:` changed to `if False:` left every
        string in place. A phrase in a source file that no input can reach
        is not a behaviour, and a test that only reads the file cannot tell
        the difference.
        """
        from caterva.compose.report import ModelDossier

        dossier = ModelDossier.__new__(ModelDossier)
        object.__setattr__(
            dossier, "model", self._model_with_no_rate_laws(),
        )
        lines = "\n".join(dossier.units_section())

        assert "No rate law was checked" in lines
        assert "absence of examination" in lines
        assert "Every rate law balances" not in lines

    def test_the_dossier_section_states_the_count_when_it_is_clean(
        self,
    ) -> None:
        from caterva.compose.report import ModelDossier

        model = compose("three step phosphorylation cascade")
        examined, _ = model.recognition.composition.unit_check()

        dossier = ModelDossier.__new__(ModelDossier)
        object.__setattr__(dossier, "model", model)
        lines = "\n".join(dossier.units_section())

        assert f"All {examined} rate laws balance" in lines
        assert "No rate law was checked" not in lines

    def _model_with_no_rate_laws(self):
        """A model whose composition declares nothing to check."""
        empty = self._empty()

        class _Recognition:
            composition = empty

        class _Model:
            recognition = _Recognition()

        return _Model()


class TestTheDiffusionLimitActuallyRuns:
    """The one hard physical law in this module, on no model at all.

    `DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND` is the Smoluchowski bound: two
    molecules in water cannot find each other faster than diffusion allows,
    and unlike every other constant in this file that is a property of
    water rather than an observation about enzymes. It is the strongest
    claim the module makes.

    It never ran. `_is_second_order` matched `/M/s`, `M^-1s^-1` and
    `1/(M*s)`, and the motif library emits `1/(mM*s)` -- so the only
    second-order constant the composer produces fell through to
    `unchecked`, reported honestly and never examined.

    Underneath that sat a worse one. The comparison comes AFTER the match,
    and it compared the stated value against a limit expressed per MOLAR
    with no conversion. A kon in per-millimolar is a thousand times larger
    per molar, so had the match ever succeeded, the check would have passed
    values a thousandfold over the limit -- which is the precise error this
    module was written to catch, committed by this module.
    """

    def test_the_library_kon_is_recognised(self) -> None:
        model = compose("reversible binding of a ligand to a receptor")
        kon = next(
            p for p in model.network.parameters if p.id.endswith("_kon")
        )
        assert kon.unit == "1/(mM*s)", "the library changed its unit"
        assert _is_second_order(kon.unit)

    def test_the_binding_model_no_longer_skips_its_kon(self) -> None:
        report = check_model(
            compose("reversible binding of a ligand to a receptor")
        )
        assert not report.unchecked, dict(report.unchecked)
        assert any(n.endswith("_kon") for n in report.checked)

    def test_a_millimolar_rate_converts_up_by_a_thousand(self) -> None:
        # 1 /(mM*s) is 1e3 /(M*s): the same rate divided by a concentration
        # a thousand times smaller. Backwards here is a thousandfold hole.
        assert _as_per_molar_per_second(1.0, "1/(mM*s)") == pytest.approx(1e3)
        assert _as_per_molar_per_second(1.0, "1/(uM*s)") == pytest.approx(1e6)
        assert _as_per_molar_per_second(1.0, "1/(M*s)") == pytest.approx(1.0)
        assert _as_per_molar_per_second(1.0, "1/s") is None

    def test_an_impossible_kon_in_millimolar_is_caught(self) -> None:
        """The case that motivated all of this.

        1e8 /(mM*s) is 1e11 /(M*s), ten times the diffusion limit. Before
        the fix this produced no finding at all -- first because the unit
        did not match, and then, had it matched, because 1e8 is smaller
        than the 1e10 limit it would have been compared against.
        """
        findings = _check_rate("complex_kon", 1e8, "1/(mM*s)")
        assert len(findings) == 1
        assert findings[0].severity == ERROR
        assert "diffusion limit" in findings[0].against
        # And it reports the CONVERTED value, so the reader can check it.
        assert "1e+11" in findings[0].detail

    def test_a_possible_kon_in_millimolar_is_not_caught(self) -> None:
        # The bound has to let real association constants through, or it
        # would flag every binding model in the library.
        assert _check_rate("complex_kon", 1.0, "1/(mM*s)") == []
        assert _check_rate("complex_kon", 1e6, "1/(mM*s)") == []

    def test_the_molar_spellings_still_work(self) -> None:
        # The forms that DID match must keep matching, unconverted.
        for unit in ("1/(M*s)", "/M/s", "M^-1s^-1"):
            assert _is_second_order(unit), unit
            assert _check_rate("k", 1e11, unit), unit
            assert _check_rate("k", 1e6, unit) == [], unit

    @pytest.mark.parametrize("unit,expected", [
        ("mM^-1s^-1", 1e3), ("mM^-1*s^-1", 1e3), ("/mM/s", 1e3),
        ("uM^-1s^-1", 1e6), ("µM^-1s^-1", 1e6), ("nM^-1s^-1", 1e9),
        ("M^-1s^-1", 1.0), ("1/(M*s)", 1.0),
    ])
    def test_a_prefixed_caret_spelling_keeps_its_prefix(self, unit, expected) -> None:
        """`M^-1s^-1` is a substring of `mM^-1s^-1`.

        The first version of the matcher iterated the concentration units
        in declaration order -- bare molar first -- and returned "M" for a
        rate stated per millimolar, so the conversion was a factor of one
        where it should have been a thousand. For per-micromolar, a
        million. That is the error the matcher exists to prevent,
        surviving inside it for every spelling the library does not use;
        the library writes `1/(mM*s)`, which happened to work.

        Longest unit first, and the match must start at a boundary.
        """
        assert _as_per_molar_per_second(1.0, unit) == pytest.approx(expected)

    def test_the_boundary_check_is_not_fooled_by_a_bare_M_inside(self) -> None:
        # A rate written per millimolar must never resolve to molar even
        # if a later shape would match the trailing "M...". The boundary
        # check is what enforces that, independent of iteration order.
        from caterva.compose.scale import _second_order_concentration

        assert _second_order_concentration("mM^-1s^-1") == "mM"
        assert _second_order_concentration("nM^-1*s^-1") == "nM"
        # And a genuine bare-molar spelling still resolves to molar.
        assert _second_order_concentration("M^-1s^-1") == "M"

    def test_a_first_order_rate_is_not_read_as_second_order(self) -> None:
        # `1/s` must not match any second-order shape, or every rate
        # constant in the library would be measured against diffusion.
        for unit in ("1/s", "/s", "s^-1", "1/min"):
            assert not _is_second_order(unit), unit


class TestNegativeIsNotPhysicallyPossible:
    """`physically_possible` used to answer yes about a negative Km.

    Each check compared against an UPPER bound only, and `_check_rate`
    returned early on a non-positive value -- so a negative rate constant,
    a negative concentration and a negative affinity all passed the
    module whose one job is to say whether a number breaks a physical law.
    `_check_exponent` already refused a non-positive Hill coefficient, so
    the bound was in the file; it was applied to one of the four kinds.

    Zero stays allowed. `perturbation.catalytically_dead` produces exactly
    a zero rate, and an absent species is zero, so a check that refused
    zero would reject the deliberate experiments this package supports.
    """

    @staticmethod
    def _one(value, unit):
        from caterva.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        return check(ReactionNetwork(
            name="one",
            species=(Species("X", 0.0),),
            parameters=(Parameter("k", value, unit),),
            reactions=(Reaction("r", {}, {"X": 1}, "k * X"),),
        ))

    @pytest.mark.parametrize("unit", ["1/s", "mM", "1/(mM*s)", "mM/s"])
    def test_a_negative_value_is_an_error(self, unit) -> None:
        report = self._one(-5.0, unit)
        assert not report.physically_possible, unit
        assert report.errors[0].severity == ERROR
        assert "negative" in report.errors[0].detail, unit

    def test_a_dimensionless_negative_keeps_the_sharper_message(self) -> None:
        """`_check_exponent` says something this check cannot.

        A Hill coefficient below ONE is negative cooperativity, which is
        real, so the interesting boundary for an exponent is one rather
        than zero. The generic message would be true and less useful, and
        replacing a specific diagnosis with a generic one is a loss even
        when both are errors.
        """
        report = self._one(-2.0, "dimensionless")
        assert not report.physically_possible
        assert "BELOW one, not below zero" in report.errors[0].detail

    def test_it_reaches_units_with_no_converter(self) -> None:
        """The reason it runs before the unit dispatch.

        `mM/s` is a zero-order synthesis rate and `scale` has no converter
        for it, so those parameters are reported unchecked. Negativity
        needs no converter -- the sign of a number is readable without
        knowing what it measures -- and a check placed after the dispatch
        would have skipped every one of them.
        """
        report = self._one(-1.0, "mM/s")
        assert not report.physically_possible
        assert "negative" in report.errors[0].detail
        assert "k" in report.checked, "it was examined, so say so"

    def test_zero_is_allowed(self) -> None:
        # A dead mutant IS a zero rate. Refusing zero would reject the
        # perturbation this package offers.
        assert self._one(0.0, "1/s").physically_possible
        assert self._one(0.0, "mM").physically_possible

    def test_a_positive_value_is_unaffected(self) -> None:
        assert self._one(5.0, "1/s").physically_possible
        assert self._one(0.1, "mM").physically_possible

    def test_a_hill_coefficient_keeps_its_stricter_rule(self) -> None:
        # Zero is fine for a rate and wrong for an exponent: a Hill
        # coefficient of zero makes the response flat, which is not a
        # weaker version of cooperativity but the absence of a response.
        assert not self._one(0.0, "dimensionless").physically_possible
        assert self._one(0.0, "1/s").physically_possible

    def test_a_finding_means_the_parameter_was_examined(self) -> None:
        """The report must not contradict itself.

        A non-finite parameter produced an error and was not recorded in
        `checked`, so `coverage` read "nothing was examined" while the
        error sat in the same report. The partition test did not catch it
        because it runs over library models, where nothing is non-finite.
        """
        for value, unit in (
            (float("nan"), "1/s"), (-5.0, "1/s"), (-1.0, "mM/s"),
        ):
            report = self._one(value, unit)
            assert report.findings, (value, unit)
            assert not report.examined_nothing, (
                value, unit, "a report with a finding examined something",
            )
            assert "k" in report.checked, (value, unit)

    def test_no_library_model_is_made_impossible_by_this(self) -> None:
        # The cry-wolf direction. A bound that fired on real models would
        # stop being read, and every motif default is positive.
        for query in (
            "three step phosphorylation cascade",
            "repressilator oscillations",
            "reversible binding of a ligand to a receptor",
            "an open system with constant substrate inflow",
        ):
            report = check_model(compose(query))
            assert report.physically_possible, (
                query, [f.describe() for f in report.errors],
            )


class TestSpeciesGetTheSameBoundsAsParameters:
    """A species at -5 mM was physically possible.

    The species loop was `if initial > 0.0:` and nothing else. That is
    False for a negative amount and False for NaN, so both were skipped
    ENTIRELY -- not checked, not reported unchecked, not counted in
    coverage. The module whose one job is to say whether a number breaks a
    physical law returned True for a concentration below zero.

    The parameters loop had just been given this bound. The species loop
    sits twenty lines below it and did not.
    """

    @staticmethod
    def _with(initial):
        from caterva.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        return check(ReactionNetwork(
            name="one",
            species=(Species("X", initial),),
            parameters=(Parameter("k", 1.0, "1/s"),),
            reactions=(Reaction("r", {}, {"X": 1}, "k * X"),),
        ))

    def test_a_negative_starting_amount_is_an_error(self) -> None:
        report = self._with(-5.0)
        assert not report.physically_possible
        assert report.errors[0].parameter == "X"
        assert "cannot be less than none" in report.errors[0].detail

    def test_a_non_finite_starting_amount_is_an_error(self) -> None:
        report = self._with(float("nan"))
        assert not report.physically_possible
        assert report.errors[0].parameter == "X"
        assert "first step of the integration is undefined" in (
            report.errors[0].detail
        )

    def test_an_absent_species_is_examined_not_skipped(self) -> None:
        """Zero is a real state, not a missing one.

        A knockout is a species at zero, and so is the baseline of every
        dose-response. Skipping them made `coverage` understate what had
        been looked at -- and a report that undercounts its own examination
        is the same defect as one that overcounts it, facing the other way.
        """
        report = self._with(0.0)
        assert report.physically_possible
        assert "X" in report.checked
        assert not report.findings

    def test_a_normal_species_still_passes(self) -> None:
        report = self._with(1.0)
        assert report.physically_possible
        assert "X" in report.checked

    def test_every_library_species_is_counted(self) -> None:
        """Across the eleven models, no species falls out of the report.

        The partition that already holds for parameters, now for species:
        each one is examined or skipped, never neither. The old loop
        dropped any species at zero, which several library models have.
        """
        for query in (
            "three step phosphorylation cascade",
            "repressilator oscillations",
            "a toggle switch between two repressors",
            "reversible binding of a ligand to a receptor",
            "sequential feedback inhibition in amino acid synthesis",
        ):
            model = compose(query)
            report = check_model(model)
            names = {s.id for s in model.network.species}
            missing = names - set(report.checked) - set(report.unchecked)
            assert not missing, (query, sorted(missing))

    def test_no_library_model_is_made_impossible(self) -> None:
        # The cry-wolf direction: every library initial is non-negative.
        for query in (
            "three step phosphorylation cascade",
            "repressilator oscillations",
            "an open system with constant substrate inflow",
        ):
            report = check_model(compose(query))
            assert report.physically_possible, (
                query, [f.describe() for f in report.errors],
            )


class TestTheProteinBoundReachesOnlyProteins:
    """Glutamate at its measured concentration was physically impossible.

    `TOTAL_CELLULAR_PROTEIN_MOLAR` is about five millimolar and was applied
    to every species. Bennett et al. (2009, Nat Chem Biol) put glutamate in
    E. coli near a hundred millimolar and ATP near ten -- the two most
    abundant metabolites there are, both measured, both reported as
    impossible. That is the cry-wolf failure ADR 0028 names, on a metabolic
    model's most ordinary numbers.

    The bound is right for a protein and wrong by a factor of twenty for a
    metabolite. Which a species is comes from the composition's port
    roles: an enzyme or a Hill regulator is a protein without exception,
    and every other role is left undecided and given the weaker bound.
    """

    @staticmethod
    def _species(name, mM, proteins=()):
        from caterva.core.network import (
            Parameter, Reaction, ReactionNetwork, Species,
        )

        return check(ReactionNetwork(
            name="one",
            species=(Species(name, mM),),
            parameters=(Parameter("k", 1.0, "1/s"),),
            reactions=(Reaction("r", {name: 1}, {}, f"k * {name}"),),
        ), proteins=proteins)

    def test_measured_glutamate_is_possible(self) -> None:
        report = self._species("glutamate", 96.0)
        assert report.physically_possible, [f.describe() for f in report.errors]

    def test_measured_atp_is_possible(self) -> None:
        assert self._species("ATP", 9.6).physically_possible

    def test_a_protein_at_ten_millimolar_is_still_impossible(self) -> None:
        # The cry-wolf fix must not have switched the bound off.
        report = self._species("kinase", 9.6, proteins=("kinase",))
        assert not report.physically_possible
        assert "total cellular protein" in report.errors[0].against
        assert "a single protein" in report.errors[0].detail

    def test_a_solute_past_a_molar_is_impossible(self) -> None:
        # The bound a non-protein DOES get: past a molar it has displaced
        # the water and the cytoplasm is not one.
        report = self._species("NaCl", 1500.0)
        assert not report.physically_possible
        assert "displaced the water" in report.errors[0].detail

    def test_above_every_measured_metabolite_is_a_question(self) -> None:
        # 150 mM: above glutamate, below a molar. Unusual, not impossible.
        report = self._species("X", 150.0)
        assert report.physically_possible
        assert len(report.questions) == 1
        assert "not known to be a protein" in report.questions[0].detail

    def test_not_known_and_known_not_say_different_things(self) -> None:
        # Three-valued on purpose: the two get the same bound and different
        # words, because "we could not tell" and "we could tell" differ.
        from caterva.compose.scale import _check_concentration

        unknown = _check_concentration("X", 150.0, "mM", protein=None)
        known = _check_concentration("X", 150.0, "mM", protein=False)
        assert "not known to be a protein" in unknown[0].detail
        assert "not a protein" in known[0].detail
        assert "not known" not in known[0].detail

    def test_the_composition_names_its_proteins(self) -> None:
        from caterva.compose.motifs import ROLE_ENZYME, ROLE_REGULATOR

        composition = compose(
            "three step phosphorylation cascade"
        ).recognition.composition
        proteins = composition.protein_species()
        assert proteins, "the premise: a cascade has kinases"
        # Everything in the set was wired as an enzyme or a regulator.
        for instance in composition.instances:
            for port in instance.motif.ports:
                species = instance.species_for(port.name)
                if port.role in (ROLE_ENZYME, ROLE_REGULATOR):
                    assert species in proteins, (instance.prefix, port.name)

    def test_check_model_uses_the_composition(self) -> None:
        """The wiring, end to end: a library protein over the bound errors,
        the same amount on a non-protein species does not."""
        from dataclasses import replace

        model = compose("a toggle switch between two repressors")
        proteins = model.recognition.composition.protein_species()
        target = sorted(proteins)[0]
        raised = replace(model.network, species=tuple(
            replace(s, initial=20.0) if s.id == target else s
            for s in model.network.species
        ))
        report = check_model(replace(model, network=raised))
        assert not report.physically_possible, "a repressor at 20 mM passed"

    def test_no_library_model_is_made_impossible(self) -> None:
        for query in (
            "three step phosphorylation cascade",
            "a toggle switch between two repressors",
            "enzyme kinetics with a competitive inhibitor",
            "sequential feedback inhibition in amino acid synthesis",
        ):
            report = check_model(compose(query))
            assert report.physically_possible, (
                query, [f.describe() for f in report.errors],
            )


class TestCheckModelUsesTheDeclaredSpeciesUnit:
    """`check_model` left `species_unit` at the library default.

    It filled in the parameter units and the protein set from the
    composition and not the species unit, so a composition declared in
    uM would have had every starting amount checked as though it were mM.
    Every library composition is mM, which is why nothing noticed.
    """

    def test_a_micromolar_composition_is_checked_in_micromolar(self) -> None:
        from dataclasses import replace

        model = compose("a toggle switch between two repressors")
        composition = model.recognition.composition
        # A species at 500 in uM is 0.5 mM: fine for a protein. Read as
        # 500 mM it would be a hundred times over the protein bound.
        target = sorted(composition.protein_species())[0]
        network = replace(model.network, species=tuple(
            replace(s, initial=500.0) if s.id == target else s
            for s in model.network.species
        ))
        composition.concentration_unit = "uM"
        try:
            report = check_model(replace(model, network=network))
        finally:
            composition.concentration_unit = "mM"
        assert report.physically_possible, [
            f.describe() for f in report.errors
        ]

    def test_the_same_amount_in_millimolar_is_not(self) -> None:
        # The other side: 500 mM of a repressor is impossible, and must
        # still be caught when the composition really is in mM.
        from dataclasses import replace

        model = compose("a toggle switch between two repressors")
        target = sorted(model.recognition.composition.protein_species())[0]
        network = replace(model.network, species=tuple(
            replace(s, initial=500.0) if s.id == target else s
            for s in model.network.species
        ))
        assert not check_model(replace(model, network=network)).physically_possible

    def test_an_explicit_species_unit_still_wins(self) -> None:
        # setdefault, not override: a caller who names the unit is trusted.
        from dataclasses import replace

        model = compose("a toggle switch between two repressors")
        target = sorted(model.recognition.composition.protein_species())[0]
        network = replace(model.network, species=tuple(
            replace(s, initial=500.0) if s.id == target else s
            for s in model.network.species
        ))
        assert check_model(
            replace(model, network=network), species_unit="uM"
        ).physically_possible
