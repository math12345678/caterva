"""Which unmeasured constant to measure first.

A three-tier cascade has twelve rate constants and none is measured until
somebody names an enzyme. "Measure twelve things" is not advice. These tests
pin the ranking that turns the gap list into a priority list, and pin the
refusals that keep it honest -- a derivative through a choice between
attractors, and a relative sensitivity around zero.
"""

from __future__ import annotations

import math

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP, SYNTHESIS_DEGRADATION
from Terium.compose.pipeline import compose
from Terium.compose.sensitivity import (
    DOMINANT, MACHINE_PRECISION, NEGLIGIBLE, NEGLIGIBLE_INFLUENCE,
    RELATIVE_STEP, SAFETY,
    SOLVER_PRECISION, STARTS_PER_SPECIES, SensitivityUnavailable, analyse,
    rank_unmeasured, resolution_for, settling_time, steady_state_of, step_for,
)


# -- shared, because these are expensive ------------------------------------
#
# `rank_unmeasured` on the cascade re-solves the steady state twice per
# constant, twelve times over. Eight tests want the same report, and
# recomputing it eight times added minutes to the engine suite for no extra
# coverage. Module-scoped rather than session-scoped so a failure here
# cannot leak into another file's fixtures, and safe to share because both
# values are frozen dataclasses that no test mutates.


@pytest.fixture(scope="module")
def cascade():
    return compose("three step phosphorylation cascade")


@pytest.fixture(scope="module")
def cascade_ranking(cascade):
    return rank_unmeasured(cascade, "tier3_Xp")


class TestAgainstAnAnalyticAnswer:
    def test_a_first_order_steady_state_has_sensitivity_plus_and_minus_one(self) -> None:
        """The case where the answer is exact.

        dX/dt = ks - kd*X settles at ks/kd. The relative sensitivity to ks
        is exactly +1 and to kd exactly -1, for every value of both. If the
        machinery cannot reproduce that, its ranking of anything harder is
        not worth reading.
        """
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(
            composition.to_network(), steady_state_of("x_X"),
            quantity_name="steady-state x_X",
        )
        by_name = {s.parameter: s.relative for s in report.sensitivities}
        assert by_name["x_ks"] == pytest.approx(1.0, rel=1e-4)
        assert by_name["x_kd"] == pytest.approx(-1.0, rel=1e-4)

    def test_both_are_dominant_by_the_stated_threshold(self) -> None:
        # |S| = 1 means the answer moves proportionally with the parameter,
        # which is where the line is drawn.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), steady_state_of("x_X"))
        assert len(report.dominant) == 2
        assert DOMINANT == 1.0

    def test_settling_time_depends_only_on_the_degradation_constant(self) -> None:
        # The approach has time constant 1/kd. ks sets WHERE it lands, not
        # how fast it gets there -- so its sensitivity is zero and kd's is
        # exactly -1.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), settling_time())
        by_name = {s.parameter: s.relative for s in report.sensitivities}
        assert by_name["x_kd"] == pytest.approx(-1.0, rel=1e-3)
        # Against the floor for THIS quantity, which is five orders coarser
        # than an exact one's -- see the class below.
        assert abs(by_name["x_ks"]) < report.resolution


class TestTheStepIsSetByTheQuantity:
    """The defect that made this class necessary.

    One fixed step of 1e-6 was used for everything, on the rule of thumb
    about machine epsilon -- which assumes the function is accurate to
    machine epsilon. The settling time is not: it is read off an eigenvalue
    of a finite-difference Jacobian and is accurate to about 1e-8. Dividing
    a 1e-8 error by a 1e-6 step reported a sensitivity of 0.004 for a
    parameter whose true sensitivity is exactly zero.
    """

    def test_the_two_quantities_do_not_get_the_same_step(self) -> None:
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        network = composition.to_network()
        exact = analyse(network, steady_state_of("x_X"))
        approximate = analyse(network, settling_time())
        assert approximate.step > exact.step
        assert approximate.resolution > exact.resolution

    def test_the_coarser_floor_is_orders_of_magnitude_coarser(self) -> None:
        # Not a rounding difference. If the two floors were within an order
        # of magnitude, one constant would have served and this whole
        # mechanism would be ceremony.
        assert resolution_for(SOLVER_PRECISION) > 1e4 * resolution_for(
            MACHINE_PRECISION
        )

    def test_the_fixed_step_would_have_reported_the_noise_as_signal(self) -> None:
        """The regression, run against the value that produced the bug.

        With the old step the settling time's sensitivity to ks came back at
        4e-3 -- three orders of magnitude above the floor, so it would have
        been printed, ranked, and read as a real dependency.
        """
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        network = composition.to_network()

        wrong = analyse(network, settling_time(), step=1e-6, precision=SOLVER_PRECISION)
        noise = abs(
            next(s for s in wrong.sensitivities if s.parameter == "x_ks").relative
        )
        assert noise > 1e-4, (
            "the old step no longer reproduces the bug; if the analysis "
            "module's Jacobian became exact, SOLVER_PRECISION is now a "
            "pessimistic claim and should be re-measured"
        )

        right = analyse(network, settling_time())
        better = abs(
            next(s for s in right.sensitivities if s.parameter == "x_ks").relative
        )
        assert better < noise

    def test_a_step_from_precision_balances_the_two_error_terms(self) -> None:
        # h = cbrt(eps_f) is where truncation (h^2) meets cancellation
        # (eps_f/h), and the floor that leaves is eps_f^(2/3).
        for precision in (MACHINE_PRECISION, SOLVER_PRECISION, 1e-12):
            step = step_for(precision)
            assert step**3 == pytest.approx(precision, rel=1e-9)
            assert resolution_for(precision) == pytest.approx(
                SAFETY * precision / step, rel=1e-9
            )

    def test_a_plain_callable_is_taken_to_be_exact(self) -> None:
        # It is the caller's own function and nothing here can measure it.
        # The alternative -- assuming the worst case for everything -- would
        # call real sensitivities noise.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), lambda n: 2.0)
        assert report.step == RELATIVE_STEP
        assert report.resolution == NEGLIGIBLE

    def test_a_precision_outside_zero_to_one_is_refused(self) -> None:
        # A caller passing an absolute tolerance would otherwise get a step
        # with no relationship to anything.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        with pytest.raises(ValueError, match="relative accuracy"):
            analyse(composition.to_network(), lambda n: 2.0, precision=5.0)


class TestContinuationStaysOnOneBranch:
    """The property that makes a difference quotient a derivative.

    `analyse` evaluates the quantity at p+h and p-h. If those two searches
    can return different steady states, their difference over 2h is the gap
    between two attractors divided by a tiny number -- large, meaningless,
    and indistinguishable from a real sensitivity.

    Tested on `follow` DIRECTLY rather than through `analyse`, because
    through `analyse` it currently cannot be violated: the only models with
    more than one branch are refused at the base point, so no perturbed
    evaluation ever has a second branch to jump to. Exercising it here keeps
    the guarantee load-bearing instead of decorative, and keeps it honest --
    a test that could not fail would be worse than none.
    """

    def _toggle(self):
        from Terium.compose.analysis import analyse as analyse_stability

        model = compose("a toggle switch between two repressors")
        report = analyse_stability(model.network, starts_per_species=STARTS_PER_SPECIES)
        assert len(report.stable_points) == 2, "the premise"
        return model.network, report.stable_points

    def test_each_branch_continues_to_itself(self) -> None:
        network, states = self._toggle()
        quantity = steady_state_of("geneA_X")

        for point in states:
            anchor = tuple(point.state[s.id] for s in network.species)
            assert quantity.follow(network, anchor) == pytest.approx(
                point.state["geneA_X"], abs=1e-9
            )

    def test_the_two_branches_do_not_continue_to_the_same_place(self) -> None:
        # Without this the test above would pass on an implementation that
        # ignored the anchor and always returned the same state.
        network, states = self._toggle()
        quantity = steady_state_of("geneA_X")

        values = [
            quantity.follow(network, tuple(p.state[s.id] for s in network.species))
            for p in states
        ]
        assert abs(values[0] - values[1]) > 1.0

    def test_a_branch_survives_a_perturbation_of_the_size_analyse_uses(
        self,
    ) -> None:
        """The actual step, not a token one.

        A continuation that only holds for infinitesimal moves would not
        help: `analyse` moves each parameter by `step_for(precision)` and
        both halves must land on the branch it started from.

        The assertion is branch IDENTITY, not an unchanged value. The value
        does move -- by about 6e-5 here, which is the sensitivity being
        measured and the whole reason for the exercise. What must not happen
        is landing nearer the other branch, nine units away.
        """
        from dataclasses import replace

        network, states = self._toggle()
        quantity = steady_state_of("geneA_X")
        step = step_for(MACHINE_PRECISION)
        target = network.parameters[0].id
        branches = [p.state["geneA_X"] for p in states]

        for point in states:
            anchor = tuple(point.state[s.id] for s in network.species)
            here = point.state["geneA_X"]
            other = next(v for v in branches if v != here)
            for direction in (+1.0, -1.0):
                moved = replace(
                    network,
                    parameters=tuple(
                        replace(p, value=p.value * (1.0 + direction * step))
                        if p.id == target else p
                        for p in network.parameters
                    ),
                )
                landed = quantity.follow(moved, anchor)
                assert abs(landed - here) < abs(landed - other) / 1000
                # And it moved by something -- a continuation that returned
                # the anchor unchanged would pass the line above trivially.
                assert landed != here

    def test_a_continuation_that_fails_refuses_rather_than_searching(self) -> None:
        """A fallback would re-enable branch-jumping exactly when it is
        most likely -- a continuation failing is itself evidence the branch
        is doing something interesting.
        """
        network, states = self._toggle()
        quantity = steady_state_of("geneA_X")

        # An anchor of the wrong shape cannot be continued from. The refusal
        # must surface, not be papered over by a global search that would
        # return some other branch and look like success.
        with pytest.raises(Exception) as caught:
            quantity.follow(network, (1.0,))
        assert "coordinates" in str(caught.value)


class TestTheDominantThresholdIsNotACoinFlip:
    """|S| = 1 is the commonest exact answer in the subject.

    Every first-order rate constant has it. The arithmetic lands on either
    side of 1.0 by a few parts in 1e11, and `>=` therefore classified the
    most ordinary case in biochemistry on the last digit: ks came back at
    0.9999999999621 and was called not-dominant, kd at -1.0000000000510 and
    was called dominant, for the same model and the same true answer.
    """

    def test_both_constants_of_a_first_order_turnover_are_dominant(self) -> None:
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), steady_state_of("x_X"))
        assert {s.parameter for s in report.dominant} == {"x_ks", "x_kd"}

    def test_the_slack_is_the_resolution_and_not_a_second_threshold(self) -> None:
        """A separate epsilon here would be a second opinion about the same
        arithmetic, free to drift from the first.

        Stated on a constructed row rather than on a computed one, on
        purpose: which side of 1.0 the turnover model happens to land is the
        very thing this behaviour exists to stop mattering, so a test that
        depended on it would break every time the solver improved.
        """
        from Terium.compose.sensitivity import Sensitivity

        floor = resolution_for(MACHINE_PRECISION)
        just_under = Sensitivity("p", 1.0, 1.0 - floor / 2, 1.0, floor)
        assert abs(just_under.relative) < DOMINANT
        assert just_under.dominant

        clearly_under = Sensitivity("p", 1.0, 1.0 - 10 * floor, 1.0, floor)
        assert not clearly_under.dominant

    def test_both_signs_of_an_exact_one_agree(self) -> None:
        # An inhibitory constant with S = -1 is exactly as dominant as an
        # activating one with S = +1, and the arithmetic must not decide
        # otherwise.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), steady_state_of("x_X"))
        by_name = {s.parameter: s for s in report.sensitivities}
        assert by_name["x_ks"].dominant == by_name["x_kd"].dominant is True

    def test_a_genuinely_sub_unit_sensitivity_is_not_dominant(self) -> None:
        # The slack must not swallow a real difference: 0.5 is not 1.
        from Terium.compose.sensitivity import Sensitivity

        assert not Sensitivity("p", 1.0, 0.5, 0.5, NEGLIGIBLE).dominant


class TestTheRanking:
    def test_a_saturated_cascade_is_insensitive_upstream(self, cascade_ranking) -> None:
        """A correct answer that looks like a broken one.

        At the library's default constants a three-tier cascade runs to
        saturation: the bottom tier is 99.99% phosphorylated, and nothing
        upstream can push it further. Most of the twelve constants therefore
        have influence too small to act on, which is a real property of a
        saturated cascade and precisely why the report says its numbers are
        local.
        """
        report = cascade_ranking

        assert report.base_value > 0.999, "saturated, which is the premise"

        # Every constant is below the act-on threshold: at saturation there
        # is nothing to be gained by measuring any of them, which is a real
        # answer and not a failure to compute one.
        assert all(s.negligible for s in report.sensitivities)

        # And the structure inside that: the bottom tier's own constants
        # outweigh everything upstream by orders of magnitude.
        by_tier = {
            tier: max(
                abs(s.relative) for s in report.sensitivities
                if s.parameter.startswith(tier)
            )
            for tier in ("tier1_", "tier2_", "tier3_")
        }
        assert by_tier["tier3_"] > 100 * by_tier["tier2_"]
        assert by_tier["tier3_"] > 100 * by_tier["tier1_"]
        assert report.ranked[0].parameter.startswith("tier3_")

    def test_the_kinase_and_phosphatase_constants_are_exactly_opposed(
        self, cascade_ranking,
    ) -> None:
        """A free analytic check the ranking must reproduce.

        A phosphorylation cycle's steady state depends on kcat_kin and
        kcat_pptase only through their RATIO, so the two sensitivities are
        equal and opposite -- for every tier, at every value. Numbers that
        merely looked plausible would not do this.
        """
        report = cascade_ranking
        by_name = {s.parameter: s.relative for s in report.sensitivities}

        for tier in ("tier1", "tier2", "tier3"):
            kinase = by_name[f"{tier}_kcat_kin"]
            phosphatase = by_name[f"{tier}_kcat_pptase"]
            assert kinase == pytest.approx(-phosphatase, rel=1e-4), tier
            assert kinase > 0, f"{tier}: more kinase must raise the answer"

    def test_the_summary_reports_an_empty_priority_list_as_a_finding(self, cascade_ranking) -> None:
        """Silence would read as "the ranking had nothing to say".

        The opposite is true: it found that no unmeasured constant moves
        this answer, which is what saturation means. And it must say the
        saturation is itself an artefact of the placeholder values -- not a
        licence to leave them unmeasured.
        """
        report = cascade_ranking
        assert not [s for s in report.priorities() if not s.negligible], "premise"

        summary = report.summary()
        assert "would not move it" in summary
        assert "not a licence to leave the constants unmeasured" in summary
        assert "the placeholders themselves that put the model here" in summary

    def test_the_upstream_constants_have_real_influence_not_no_influence(
        self, cascade_ranking,
    ) -> None:
        """The finding that split one threshold into two.

        With a single cutoff at 1e-6 these eight read as "no measurable
        influence". Putting the noise floor where the arithmetic actually is
        -- around 4e-10 -- showed their influence is about 1e-8: real,
        clear of the noise, and still not worth a week at the bench. Saying
        "no influence" overstated what had been found.
        """
        report = cascade_ranking

        upstream = [
            s for s in report.sensitivities
            if s.parameter.startswith(("tier1_", "tier2_")) and s.negligible
        ]
        assert upstream, "the premise"
        measured = [s for s in upstream if not s.unresolvable]
        assert measured, (
            "every upstream constant fell below the noise floor, so this "
            "model no longer distinguishes the two thresholds and the case "
            "needs re-choosing"
        )
        for entry in measured:
            assert report.resolution < abs(entry.relative) < NEGLIGIBLE_INFLUENCE

    def test_the_summary_keeps_the_two_kinds_of_small_apart(self, cascade_ranking) -> None:
        summary = cascade_ranking.summary()
        assert "too little to act on" in summary
        assert "influence is real and was measured" in summary
        # And it does not reach for the word that started the confusion.
        assert "no measurable influence" not in summary

    def test_the_priority_list_holds_only_unmeasured_constants(
        self, cascade, cascade_ranking,
    ) -> None:
        report = cascade_ranking
        unmeasured = {q.parameter_id for q in cascade.resolvable}
        assert {s.parameter for s in report.priorities()} <= unmeasured

    def test_the_ranking_is_by_absolute_value(self, cascade_ranking) -> None:
        # A parameter that lowers the answer by 2% per 1% matters as much as
        # one that raises it by 2%, and ranking by signed value would bury
        # every inhibitory constant at the bottom.
        report = cascade_ranking
        magnitudes = [abs(s.relative) for s in report.ranked]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_the_summary_says_measuring_first_is_not_the_same_as_mattering(self) -> None:
        """On a model that HAS priorities.

        The cascade at library defaults is saturated and has none, so this
        sentence has to be pinned somewhere it actually appears -- a test
        that asserted it on the cascade would only ever have checked that
        the paragraph was absent.
        """
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(
            composition.to_network(), steady_state_of("x_X"),
            unmeasured=("x_ks", "x_kd"),
        )
        assert report.priorities(), "the premise"
        summary = report.summary()
        assert "the answer depends most on" in summary
        assert "different statement from saying the others do not matter" in summary


class TestRefusals:
    def test_a_bistable_model_refuses_a_steady_state_derivative(self) -> None:
        """Differentiating through a choice between attractors.

        The result would describe which state the root finder happened to
        return, not the model.
        """
        model = compose("a toggle switch between two repressors")
        with pytest.raises(SensitivityUnavailable, match="stable states"):
            steady_state_of("geneA_X")(model.network)

    def test_the_refusal_does_not_call_a_continuum_a_set_of_attractors(self) -> None:
        # The competition model consumes its substrate completely; after
        # that every split of the products summing to the conserved total is
        # a fixed point. That is a line of them, not a choice between two,
        # and the message must cover both readings.
        model = compose("two enzymes competing for the same substrate")
        with pytest.raises(SensitivityUnavailable) as caught:
            steady_state_of("enzyme1_P")(model.network)
        message = str(caught.value)
        assert "continuum" in message
        assert "decided by the transient" in message

    def test_the_refusal_searches_at_least_as_hard_as_the_analysis_default(
        self,
    ) -> None:
        """The defect that made both refusals above silent.

        These quantities passed `starts_per_species=4` to be quick, below
        the analysis module's own MEASURED default of 8. At 4 the toggle
        switch reports one stable state when it has two, so the refusal
        never fired and a derivative was taken straight through a bistable
        system. A quantity is free to search harder than the default; it is
        not free to search less hard and keep claiming a unique state.
        """
        from Terium.compose.analysis import DEFAULT_STARTS_PER_SPECIES

        assert STARTS_PER_SPECIES >= DEFAULT_STARTS_PER_SPECIES

    def test_the_toggle_is_bistable_at_the_depth_actually_used(self) -> None:
        # Pins the measurement the constant rests on, so that a later change
        # to the search cannot quietly restore the silent case.
        from Terium.compose.analysis import analyse as analyse_stability

        model = compose("a toggle switch between two repressors")
        shallow = analyse_stability(model.network, starts_per_species=4)
        deep = analyse_stability(model.network, starts_per_species=STARTS_PER_SPECIES)
        assert len(shallow.stable_points) == 1, (
            "the shallow search no longer misses the second state; if the "
            "search improved, STARTS_PER_SPECIES can be re-measured"
        )
        assert len(deep.stable_points) == 2

    def test_a_single_stable_state_is_a_search_result_not_a_proof(self) -> None:
        """The honest limit of the refusal, stated where it is made.

        At 8 starting points per species -- the analysis module's measured
        default -- the five-species competition model still reports one
        stable state when it has two. No number of starting points turns
        "did not find another" into "there is not another", and the module
        must not read as though it did.
        """
        from Terium.compose import sensitivity

        prose = " ".join(sensitivity.__doc__.lower().split())
        assert "search result rather than a proof" in prose
        assert "no number of starting points" in prose

    def test_a_zero_valued_parameter_is_skipped_with_the_reason(self) -> None:
        # A fractional change in zero is undefined. An absolute step would
        # work and would answer a different question.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x", initials={})
        network = composition.to_network()
        from dataclasses import replace

        zeroed = replace(
            network,
            parameters=tuple(
                replace(p, value=0.0) if p.id == "x_ks" else p
                for p in network.parameters
            ),
        )
        report = analyse(zeroed, lambda n: 1.0)
        assert "x_ks" in report.skipped
        assert "undefined" in report.skipped["x_ks"]

    def test_an_unknown_parameter_names_the_real_ones(self) -> None:
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        with pytest.raises(KeyError, match="x_ks"):
            analyse(composition.to_network(), lambda n: 1.0, parameters=["nope"])

    def test_a_quantity_that_fails_at_the_base_point_refuses(self) -> None:
        # Nothing to differentiate.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")

        def broken(network):
            raise RuntimeError("no")

        with pytest.raises(SensitivityUnavailable, match="nothing to differentiate"):
            analyse(composition.to_network(), broken)


class TestHonesty:
    def test_it_says_the_result_is_local(self) -> None:
        # A parameter with sensitivity 0.01 here can dominate two decades
        # away, and the report must not read as a global ranking.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        summary = analyse(composition.to_network(), steady_state_of("x_X")).summary()
        assert "Local:" in summary
        assert "two decades away" in summary

    def test_a_number_below_the_floor_is_not_printed_as_a_sensitivity(self) -> None:
        # The settling time does not depend on ks at all. What comes back is
        # the quantity's own error divided by the step, and printing
        # "S = 1.1e-06" invites a reader to believe it means something.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), settling_time())
        ks = next(s for s in report.sensitivities if s.parameter == "x_ks")

        assert ks.unresolvable
        described = ks.describe()
        assert "noise floor" in described
        assert f"{ks.relative:+.2g}" not in described
        # And it does not overclaim in the other direction either.
        assert "not the same as having none" in described

    def test_a_real_but_tiny_influence_is_printed_with_its_number(self, cascade_ranking) -> None:
        """The other side of the same distinction.

        A saturated cascade's upstream constants sit at 1e-8: far above the
        floor, so the number IS meaningful and is shown, and far below what
        is worth measuring, so it is called negligible in the same breath.
        """
        report = cascade_ranking
        upstream = next(
            s for s in report.sensitivities if s.parameter == "tier1_kcat_kin"
        )
        assert upstream.negligible and not upstream.unresolvable

        described = upstream.describe()
        assert "negligible" in described
        assert f"{upstream.relative:+.2g}" in described
        assert "under anything an assay would resolve" in described

    def test_the_absolute_derivative_is_kept_alongside_the_relative(self) -> None:
        # The relative form is what makes parameters comparable; the
        # absolute is the only one with units, and a reader checking the
        # arithmetic needs it.
        composition = Composition("turnover")
        composition.add(SYNTHESIS_DEGRADATION, "x")
        report = analyse(composition.to_network(), steady_state_of("x_X"))
        for entry in report.sensitivities:
            assert entry.absolute == pytest.approx(
                entry.relative * report.base_value / entry.value, rel=1e-6
            )


class TestAnAllZeroRankingHasTwoCauses:
    """The same symptom, opposite advice.

    A ranking where nothing clears the act-on threshold can mean the
    mechanism is saturated -- nothing upstream can push it further -- or
    that the quantity is not a function of the rate constants at all,
    because a conservation law fixes it at whatever total the initial
    condition set. Under saturation there is nothing to gain anywhere;
    under conservation the question was asked of the wrong quantity, and a
    time course answers it.

    Reporting the second as the first would attach a plausible wrong reason
    to a correct number, which is the failure this module has already made
    once (calling a continuum a set of attractors).
    """

    def test_a_closed_system_is_pinned_by_its_conservation_law(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        report = rank_unmeasured(model, "reaction_P")

        assert report.conserved_by == "reaction_S + reaction_P"
        assert all(s.relative == 0.0 for s in report.sensitivities)

    def test_the_pinned_summary_names_the_law_and_redirects(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        summary = rank_unmeasured(model, "reaction_P").summary()

        assert "reaction_S + reaction_P" in summary
        assert "how FAST the system arrives, never WHERE" in summary
        assert "settling time or a time course" in summary
        # And it does not reach for the other explanation.
        assert "saturat" not in summary

    def test_a_saturated_model_is_not_called_conserved(self, cascade_ranking) -> None:
        """The discriminator, on the case that would fool a weaker one.

        `tier3_Xp` IS in a conservation law -- every phosphorylation tier
        conserves its own total protein -- so a test for "the species
        appears in a law" alone would call the cascade pinned. Its
        sensitivities are 1e-5 and 1e-8: small, but four orders above the
        noise floor and therefore real. Both signals are required for
        exactly this case.
        """
        assert cascade_ranking.conserved_by is None
        assert not all(s.unresolvable for s in cascade_ranking.sensitivities)
        assert "saturat" in cascade_ranking.summary()

    def test_the_species_must_actually_appear_in_the_law(self) -> None:
        from Terium.compose.sensitivity import conservation_pinning

        model = compose("substrate inhibition at high substrate concentration")
        report = rank_unmeasured(model, "reaction_P")
        assert conservation_pinning(model.network, "reaction_E", report) == "reaction_E"
        assert conservation_pinning(model.network, "nonexistent", report) is None

    def test_the_law_it_names_is_one_that_holds_the_species(self) -> None:
        from Terium.compose.sensitivity import (
            Sensitivity, SensitivityReport, conservation_pinning,
        )

        model = compose("reversible binding of a ligand to a receptor")
        zeroed = SensitivityReport(
            quantity="q", base_value=1.0,
            sensitivities=(Sensitivity("p", 1.0, 0.0, 0.0, NEGLIGIBLE),),
        )
        law = conservation_pinning(model.network, "complex_AB", zeroed)
        assert law is not None
        assert "complex_AB" in law.split()

    def test_a_report_with_no_sensitivities_is_never_pinned(self) -> None:
        # Nothing was measured, so nothing was found to be zero. An empty
        # report satisfies "all unresolvable" vacuously, which is exactly
        # the shape of check that must not fire.
        from Terium.compose.sensitivity import conservation_pinning, SensitivityReport

        model = compose("substrate inhibition at high substrate concentration")
        empty = SensitivityReport(quantity="q", base_value=1.0, sensitivities=())
        assert conservation_pinning(model.network, "reaction_P", empty) is None


class TestTheBindingMotifGetsARankingAtAll:
    """It declares a COMPLEX, not a product.

    `_default_target` looked only for product ports, so "reversible binding
    of a ligand to a receptor" produced no ranking whatsoever -- not a
    refusal with a reason, just silence. `complex_AB` is plainly what a
    reader means by the answer.
    """

    def test_the_complex_is_ranked_and_the_ranking_is_real(self) -> None:
        model = compose("reversible binding of a ligand to a receptor")
        report = rank_unmeasured(model, "complex_AB")

        assert report.conserved_by is None, "the complex is not pinned"
        assert report.sensitivities
        assert max(abs(s.relative) for s in report.sensitivities) > NEGLIGIBLE_INFLUENCE

    def test_on_and_off_rates_are_what_it_points_at(self) -> None:
        # A binding equilibrium's occupancy depends on kon and koff, and
        # they are what a reader would go and measure.
        model = compose("reversible binding of a ligand to a receptor")
        report = rank_unmeasured(model, "complex_AB")
        priorities = {s.parameter for s in report.priorities() if not s.negligible}
        assert {"complex_kon", "complex_koff"} <= priorities

    def test_binding_more_tightly_raises_the_complex(self) -> None:
        # A sign check the arithmetic must reproduce: more on-rate means
        # more complex, more off-rate means less.
        model = compose("reversible binding of a ligand to a receptor")
        by_name = {
            s.parameter: s.relative
            for s in rank_unmeasured(model, "complex_AB").sensitivities
        }
        assert by_name["complex_kon"] > 0
        assert by_name["complex_koff"] < 0


class TestLawMentions:
    """Whole-token matching, tested where it can actually fail.

    A mutation replacing this with a plain substring test came back NOT
    CAUGHT. Inspecting it showed the mutation was INERT rather than the
    tests weak: in every law the library currently produces, a species that
    is a substring of another token is also a token of the same law --
    `complex_A + complex_AB` names both -- so the two rules agree on real
    inputs and the distinction could not be exercised through a real model.

    A guard indistinguishable from its own bug is not yet a guard. These
    drive it with the law strings that separate the rules, which are laws no
    motif generates today and might generate tomorrow.
    """

    def test_a_prefix_of_another_token_is_not_a_mention(self) -> None:
        from Terium.compose.sensitivity import law_mentions

        # The species is a strict substring of every token here and a token
        # of none of them. A substring test says yes; the truth is no.
        assert not law_mentions("tier1_Xp + tier1_Xpp", "tier1_X")
        assert not law_mentions("complex_AB + complex_ABC", "complex_A")

    def test_a_real_token_is_a_mention(self) -> None:
        from Terium.compose.sensitivity import law_mentions

        assert law_mentions("tier1_X + tier1_Xp", "tier1_X")
        assert law_mentions("tier1_X + tier1_Xp", "tier1_Xp")
        assert law_mentions("complex_A + complex_AB", "complex_AB")

    def test_a_coefficient_does_not_hide_a_token(self) -> None:
        # Laws are rendered with integer coefficients, e.g.
        # `complex_A + -1 complex_B`. The name is still a whole token.
        from Terium.compose.sensitivity import law_mentions

        assert law_mentions("complex_A + -1 complex_B", "complex_B")
        assert not law_mentions("complex_A + -1 complex_B", "complex")

    def test_a_substring_test_would_disagree_on_these(self) -> None:
        """Pins that these cases actually separate the two rules.

        Without this, the tests above could all pass under a substring
        implementation and would be checking nothing -- the exact failure
        that produced them.
        """
        from Terium.compose.sensitivity import law_mentions

        separating = [
            ("tier1_Xp + tier1_Xpp", "tier1_X"),
            ("complex_AB + complex_ABC", "complex_A"),
            ("complex_A + -1 complex_B", "complex"),
        ]
        for law, species in separating:
            assert species in law, "the substring rule would say yes"
            assert not law_mentions(law, species), "the token rule says no"
