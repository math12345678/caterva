"""The assumptions a composed model inherits, and where composition breaks them.

WHY THIS IS A COMPOSITION PROBLEM SPECIFICALLY
-----------------------------------------------
Each motif's basis is true of the motif alone. Chain two catalytic steps and
the first one's product is the second one's substrate -- and the second step's
QSSA needs [E]0 << [S], where S is now an intermediate whose whole job is to
stay small. The assumption that was safe in isolation is the one most likely
to fail in the chain, and asking each motif about itself never finds it.

These tests pin that, and pin the three-way distinction the module turns on:
a condition that FAILS, one that could not be DECIDED from what the model
carries, and one that was never CHECKABLE. Collapsing any two of those would
make the report unreadable in the specific way that matters -- "undecided"
read as "held" is how a placeholder becomes a conclusion.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from caterva.compose.assumptions import (
    CONDITIONS, HELD, NOT_CHECKABLE, QSSA_RATIO, UNDECIDED, VERDICTS, VIOLATED,
    AssumptionError, Finding, check,
)
from caterva.compose.builder import Composition
from caterva.compose.library import CATALYTIC_STEP, ZERO_ORDER_DEGRADATION
from caterva.compose.pipeline import compose


class TestCompositionBreaksWhatIsolationDoesNot:
    def test_a_consumed_substrate_is_window_dependent_not_violated(self) -> None:
        """The correction that matters more than the finding.

        A substrate consumed and never replenished is what a CLOSED BATCH
        ASSAY is -- a tube with enzyme and substrate in it, which is how
        most kinetics is measured. The saturable law is good while substrate
        remains and wrong only near exhaustion.

        An earlier version returned VIOLATED here, and the verdict page duly
        called every batch reaction in the library BROKEN. That is ADR
        0028's failure exactly: a check that fires on the normal case stops
        being read, and the one time it fires on something real nobody
        looks.
        """
        report = check(compose("sequential feedback inhibition in amino acid synthesis"))

        depletion = [
            f for f in report.findings if f.condition == "substrate_pool_holds"
        ]
        assert depletion
        assert all(f.verdict == UNDECIDED for f in depletion)
        assert report.sound, "a normal batch assay is not a broken model"

    def test_a_chained_step_resolves_its_port_through_the_binding(self) -> None:
        """The bug that made this module not do what it claims.

        Chaining binds step2's substrate port to step1's PRODUCT species, so
        looking up "step2_S" by name finds nothing -- and an earlier version
        returned NOT_CHECKABLE for every chained step. The check quietly did
        not apply to the composition case it was written for, and reported
        that as "nothing to check".
        """
        report = check(compose("sequential feedback inhibition in amino acid synthesis"))
        chained = [
            f for f in report.findings
            if f.instance in ("step2", "step3")
            and f.condition == "qssa_enzyme_excess"
        ]
        assert len(chained) == 2
        assert all(f.verdict == UNDECIDED for f in chained), [
            (f.instance, f.verdict) for f in chained
        ]
        # And it names the upstream species, not a constructed one.
        assert any("step1_P" in f.detail for f in chained)
        assert not any("step2_S" in f.detail for f in chained)

    def test_the_intermediate_is_named_as_the_reason(self) -> None:
        # An intermediate's whole job is to stay small, which is why the
        # QSSA is least safe exactly here.
        report = check(compose("sequential feedback inhibition in amino acid synthesis"))
        step2 = next(
            f for f in report.findings
            if f.instance == "step2" and f.condition == "qssa_enzyme_excess"
        )
        assert "INTERMEDIATE in a chain" in step2.detail

    def test_it_says_what_would_decide_the_window(self) -> None:
        report = check(compose("two enzymes competing for the same substrate"))
        depletion = next(
            f for f in report.findings if f.condition == "substrate_pool_holds"
        )
        assert "closed batch assay" in depletion.detail
        # It names the reading to take, not just the fact that one exists.
        # "simulate and look" was advice; this is a call, with the species
        # already filled in.
        assert "timeseries.depletion(trajectory," in depletion.detail
        assert "how much of the pool is left" in depletion.detail

    def test_the_named_reading_exists_and_takes_that_species(self) -> None:
        """The message would be worse than vague if the call were wrong.

        A refusal that names a function nobody can call is a dead end
        dressed as a next step, and the reader finds out by typing it.
        """
        import inspect

        from caterva.compose import timeseries

        assert hasattr(timeseries, "depletion")
        parameters = inspect.signature(timeseries.depletion).parameters
        assert list(parameters)[:2] == ["source", "species"], parameters

    def test_this_module_no_longer_exports_a_threshold_it_cannot_apply(
        self,
    ) -> None:
        """DEPLETION_FRACTION lived here and nothing read it.

        A documented, exported threshold that no code applies reads as a
        rule in force. This module is structural and never simulates, so it
        could not have applied it; the threshold belongs with the reading
        that uses it.
        """
        from caterva.compose import assumptions, timeseries

        assert not hasattr(assumptions, "DEPLETION_FRACTION")
        assert "DEPLETION_FRACTION" not in assumptions.__all__
        assert timeseries.DEPLETION_FRACTION == 0.1
        assert "DEPLETION_FRACTION" in timeseries.__all__

    def test_the_consequence_is_still_stated_for_a_reader(self) -> None:
        # Undecided does not mean unimportant: the reader still needs to
        # know what goes wrong if the window is too long.
        report = check(compose("two enzymes competing for the same substrate"))
        condition = next(
            c for c in CONDITIONS if c.name == "substrate_pool_holds"
        )
        assert "saturable denominator" in condition.consequence
        assert "largest exactly where the interesting dynamics are" in (
            condition.consequence
        )


class TestTheThreeWayDistinction:
    """Undecided read as held is how a placeholder becomes a conclusion."""

    def test_an_intermediate_substrate_is_undecided_not_held(self) -> None:
        """The QSSA needs a characteristic [S]. An intermediate starts at
        zero, so there is no such number in the model -- and this is exactly
        where the assumption is most likely to be in trouble, which makes
        "undecided" the useful answer and a computed ratio the useless one.
        """
        composition = Composition("chain")
        composition.add(CATALYTIC_STEP, "first")
        composition.add(CATALYTIC_STEP, "second", initials={"S": 0.0})
        network = composition.to_network()

        class _Model:
            class recognition:
                composition = None

        _Model.recognition.composition = composition
        _Model.network = network

        report = check(_Model())
        qssa = [f for f in report.findings if f.condition == "qssa_enzyme_excess"]
        second = [f for f in qssa if f.instance == "second"]
        assert second
        assert second[0].verdict == UNDECIDED
        assert "INTERMEDIATE in a chain" in second[0].detail

    def test_it_says_what_would_decide_it(self) -> None:
        # An undecided verdict with no route to deciding it is a shrug.
        composition = Composition("chain")
        composition.add(CATALYTIC_STEP, "first")
        composition.add(CATALYTIC_STEP, "second", initials={"S": 0.0})

        class _Model:
            class recognition:
                pass

        _Model.recognition.composition = composition
        _Model.network = composition.to_network()

        report = check(_Model())
        undecided = [f for f in report.findings if f.verdict == UNDECIDED]
        assert undecided
        assert any("simulate and compare" in f.detail for f in undecided)

    def test_a_satisfied_qssa_is_held_with_the_ratio(self) -> None:
        composition = Composition("plain")
        composition.add(CATALYTIC_STEP, "reaction")

        class _Model:
            class recognition:
                pass

        _Model.recognition.composition = composition
        _Model.network = composition.to_network()

        report = check(_Model())
        qssa = next(f for f in report.findings if f.condition == "qssa_enzyme_excess")
        assert qssa.verdict == HELD
        # The library's default is S=1, E=1e-3, so the ratio is 1000 --
        # formatted with %g, which renders it as 1e+03.
        assert "1e+03" in qssa.detail
        assert float(qssa.detail.split("= ")[1].split(",")[0]) == pytest.approx(1000.0)

    def test_a_missing_port_is_not_checkable_rather_than_passing(self) -> None:
        from caterva.compose.assumptions import _qssa

        class _Empty:
            species = ()
            reactions = ()
            parameters = ()

        verdict, detail = _qssa("nothing", _Empty())
        assert verdict == NOT_CHECKABLE
        assert "no E and S pair" in detail

    def test_an_unknown_verdict_is_refused(self) -> None:
        # The difference between fails, undecided and never-checkable is the
        # whole content of the module.
        with pytest.raises(AssumptionError, match="whole content"):
            Finding(
                instance="x", motif="m", condition="c",
                verdict="probably-ok", statement="s", detail="d",
            )


class TestTheQssaThresholdIsDerivedNotPicked:
    def test_it_has_a_stated_derivation(self) -> None:
        """The QSSA's error is of order [E]0/([S]+Km), so 1/100 buys about a
        percent. Ten would buy ten percent -- larger than most effects these
        models are built to show.
        """
        import inspect

        from caterva.compose import assumptions

        source = inspect.getsource(assumptions)
        assert "QSSA_RATIO = 100.0" in source
        assert "Segel" in source
        assert "micromolar enzyme meets millimolar substrate" in source

    def test_the_threshold_is_the_comparison_actually_used(self) -> None:
        # A constant that is documented and then not used is decoration.
        composition = Composition("tight")
        composition.add(CATALYTIC_STEP, "reaction", initials={"E": 0.5, "S": 1.0})

        class _Model:
            class recognition:
                pass

        _Model.recognition.composition = composition
        _Model.network = composition.to_network()

        qssa = next(
            f for f in check(_Model()).findings
            if f.condition == "qssa_enzyme_excess"
        )
        assert qssa.verdict == VIOLATED
        assert str(int(QSSA_RATIO)) in qssa.detail


class TestZeroOrderRemovalGoesNegative:
    def test_an_unreplenished_species_is_violated_with_the_time(self) -> None:
        """Not a maybe. A constant removal rate on a finite pool reaches
        zero at t = X0/v_max and the integrator follows it straight past.
        """
        composition = Composition("removal")
        composition.add(ZERO_ORDER_DEGRADATION, "removal")

        class _Model:
            class recognition:
                pass

        _Model.recognition.composition = composition
        _Model.network = composition.to_network()

        report = check(_Model())
        finding = next(f for f in report.findings if f.condition == "needs_a_floor")
        assert finding.verdict == VIOLATED
        assert "goes negative after" in finding.detail
        # And it gives the time, so a reader can pick a window.
        assert "t = " in finding.detail

    def test_the_consequence_names_the_propagation(self) -> None:
        composition = Composition("removal")
        composition.add(ZERO_ORDER_DEGRADATION, "removal")

        class _Model:
            class recognition:
                pass

        _Model.recognition.composition = composition
        _Model.network = composition.to_network()

        finding = next(
            f for f in check(_Model()).findings if f.condition == "needs_a_floor"
        )
        assert "propagates into every rate law that reads it" in finding.describe()


class TestItDoesNotPretendToHaveReadTheProse:
    """The basis strings carry more than any parser can extract.

    A module that claimed to have checked an assumption it had only
    pattern-matched would be worse than one that checked nothing, because
    the reader would stop looking.
    """

    def test_motifs_with_no_checkable_condition_are_listed_not_omitted(
        self,
    ) -> None:
        # A model whose assumptions are unparseable must not read as a model
        # without any.
        report = check(compose("three step phosphorylation cascade"))
        assert report.prose_only
        assert all(basis for basis in report.prose_only.values())

    def test_the_prose_is_carried_through_to_the_summary(self) -> None:
        summary = check(compose("three step phosphorylation cascade")).summary()
        assert "state their assumptions in prose that nothing here can check" in summary
        assert "must not read as a model without any" in summary

    def test_the_summary_says_which_half_is_which(self) -> None:
        summary = check(compose("two enzymes competing for the same substrate")).summary()
        assert "Checked arithmetically where a condition could be written" in summary
        assert "does not pretend to have read them" in summary

    def test_sound_is_not_called_every_assumption_holds(self) -> None:
        from caterva.compose.assumptions import AssumptionReport

        # Whitespace-normalised: the phrase wraps in the source, and a raw
        # substring test would be asserting the line width.
        prose = " ".join(AssumptionReport.sound.__doc__.split())
        assert "NOT" in prose
        assert "most assumptions here are prose that nothing checked" in prose

    def test_conditions_are_declared_not_parsed(self) -> None:
        # Each condition names the motif it belongs to explicitly.
        assert CONDITIONS
        for condition in CONDITIONS:
            assert condition.motif
            assert condition.statement
            assert callable(condition.check)


class TestRefusals:
    def test_a_network_with_no_motifs_is_refused(self) -> None:
        """A network built outside the composer has no basis strings, and
        reporting "no assumptions violated" for it would be true and
        entirely misleading.
        """
        class _Bare:
            class recognition:
                class composition:
                    instances = ()

            network = None

        with pytest.raises(AssumptionError, match="no motif instances"):
            check(_Bare())
