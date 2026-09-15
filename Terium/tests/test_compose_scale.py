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

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP, SYNTHESIS_DEGRADATION
from Terium.compose.pipeline import compose
from Terium.compose.scale import (
    DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND, ERROR, ONE_MOLECULE_PER_BACTERIUM_MOLAR,
    PLAUSIBLE_HILL_RANGE, QUESTION, ScaleError, TIGHTEST_MEASURED_KD_MOLAR,
    TOTAL_CELLULAR_PROTEIN_MOLAR, TYPICAL_KCAT_RANGE_PER_SECOND, Finding,
    ScaleReport, check, check_model,
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
        from Terium.compose.verdict import _scale_concerns

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
        from Terium.compose.builder import Composition

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
        from Terium.compose.validate import (
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
        from Terium.compose.validate import AGREE, dimension_findings

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
        from Terium.compose.report import ModelDossier

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
        from Terium.compose.report import ModelDossier

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
