"""The ensemble Bakker described and Sauro called "the right way to do it".

These tests are about three things, in descending order of how badly a
regression would hurt:

1. **The weights actually steer the sampling.** If they do not, this is an
   unweighted bootstrap wearing Bakker's name, which is worse than not
   having built it — it would claim a method it does not implement.
2. **It is reproducible.** An ensemble nobody can re-derive is not evidence.
3. **It refuses rather than inventing.** No uniform fallback, no silent
   default for an unknown grade, no empty result presented as an answer.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ensemble import (  # noqa: E402
    DEFAULT_WEIGHT_POLICY,
    Candidate,
    UnknownGrade,
    sample_ensemble,
    weigh,
    weight_of,
)
from reliability import Axis, ReliabilityScore  # noqa: E402


def score(assay: str, condition: str, organism: str) -> ReliabilityScore:
    return ReliabilityScore(
        assay_completeness=Axis(grade=assay, reason=""),
        condition_proximity=Axis(grade=condition, reason=""),
        organism_match=Axis(grade=organism, reason=""),
    )


BEST = score("complete", "near", "exact")
WORST = score("absent", "far", "distant")


def candidate(value: float, s: ReliabilityScore, ref: str | None = None) -> Candidate:
    return Candidate(value=value, score=s, unit="mM", reference_id=ref)


class TestWeightsSteerTheSampling:
    """The load-bearing claim. Without this it is not Bakker's method."""

    def test_a_better_evidenced_value_is_drawn_more_often(self) -> None:
        result = sample_ensemble(
            [candidate(1.0, BEST), candidate(100.0, WORST)],
            draws=4000,
            seed=1,
        )
        good = sum(1 for d in result.draws if d == 1.0)
        # BEST/WORST weights are 1.0 vs 0.25*0.3*0.15 = 0.01125, so the
        # well-evidenced row should dominate overwhelmingly. Asserting a
        # loose bound rather than an exact ratio: the point is that the
        # weighting bites, not that the RNG hits a particular number.
        assert good / len(result.draws) > 0.95

    def test_the_ratio_matches_the_declared_policy(self) -> None:
        """Not just "more often" — the right amount more often.

        A sampler that always returned the best candidate would pass the test
        above and be wrong: it would have thrown away the weaker evidence
        entirely, which is precisely what Bakker said not to do ("do not
        exclude anything a priori").
        """
        a = score("complete", "near", "exact")      # 1.0
        b = score("partial", "near", "exact")       # 0.5
        result = sample_ensemble(
            [candidate(1.0, a), candidate(2.0, b)], draws=8000, seed=7
        )
        share_b = sum(1 for d in result.draws if d == 2.0) / len(result.draws)
        # Expected 0.5/1.5 = 0.333. Tolerance is wide enough for sampling
        # noise at n=8000 and far too tight to pass if the weights were
        # ignored (which would give 0.5) or absolute (which would give ~0).
        assert 0.30 < share_b < 0.37

    def test_the_weakest_evidence_is_still_sampled_sometimes(self) -> None:
        """Bakker: "do not exclude anything a priori."

        A weight of zero is exclusion by another name. The policy's floor is
        small but non-zero on purpose, and this pins it: a poorly-evidenced
        measurement is still a measurement, and the ensemble should show a
        student that it exists.
        """
        result = sample_ensemble(
            [candidate(1.0, BEST), candidate(100.0, WORST)],
            draws=20000,
            seed=3,
        )
        assert any(d == 100.0 for d in result.draws)

    def test_an_axis_where_everyone_is_equal_does_not_tilt_anything(self) -> None:
        """Nobody supplied a physiological reference, so every row is
        `not_assessed`. That axis carries no information and must not change
        the relative weights — otherwise the common case (no reference given)
        would quietly reweight every ensemble Caterva produces.
        """
        with_ref = [
            candidate(1.0, score("complete", "near", "exact")),
            candidate(2.0, score("partial", "near", "exact")),
        ]
        without = [
            candidate(1.0, score("complete", "not_assessed", "exact")),
            candidate(2.0, score("partial", "not_assessed", "exact")),
        ]
        p_with = [w.probability for w in weigh(with_ref)]
        p_without = [w.probability for w in weigh(without)]
        assert p_with == pytest.approx(p_without)


class TestReproducible:
    def test_the_same_seed_gives_the_same_ensemble(self) -> None:
        pool = [candidate(1.0, BEST), candidate(2.0, WORST)]
        first = sample_ensemble(pool, draws=200, seed=42)
        second = sample_ensemble(pool, draws=200, seed=42)
        assert first.draws == second.draws

    def test_a_different_seed_gives_a_different_one(self) -> None:
        pool = [candidate(1.0, BEST), candidate(2.0, WORST)]
        assert (
            sample_ensemble(pool, draws=200, seed=1).draws
            != sample_ensemble(pool, draws=200, seed=2).draws
        )

    def test_the_seed_is_carried_in_the_result(self) -> None:
        # An ensemble whose seed is not written down cannot be re-derived,
        # and this repository's claim is that its numbers can be.
        assert sample_ensemble([candidate(1.0, BEST)], draws=5, seed=99).seed == 99


class TestRefusesRatherThanInventing:
    def test_an_unknown_grade_raises_instead_of_defaulting(self) -> None:
        """A silent 1.0 would let a new grade reweight every ensemble in the
        project without anyone noticing — the "check that cannot fail" shape,
        in the arithmetic rather than in a guard.
        """
        weird = score("complete", "near", "brand_new_grade")
        with pytest.raises(UnknownGrade, match="organism_match"):
            weight_of(weird)

    def test_an_empty_pool_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no candidates"):
            sample_ensemble([], draws=10, seed=1)

    def test_zero_draws_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one draw"):
            sample_ensemble([candidate(1.0, BEST)], draws=0, seed=1)

    def test_an_all_zero_policy_refuses_rather_than_falling_back_to_uniform(
        self,
    ) -> None:
        """Falling back to uniform would be a silent policy change at exactly
        the moment somebody should be looking at the policy.
        """
        zeroed = {
            axis: {grade: 0.0 for grade in table}
            for axis, table in DEFAULT_WEIGHT_POLICY.items()
        }
        with pytest.raises(ValueError, match="weighs zero"):
            sample_ensemble([candidate(1.0, BEST)], draws=10, seed=1, policy=zeroed)


class TestWhatItReportsAboutItself:
    def test_the_disclaimer_travels_with_the_numbers(self) -> None:
        """ADR 0024 declined sampling because spread without a validation step
        reads as an uncertainty estimate. The answer is not to hide the
        spread; it is to make the sentence inseparable from it.
        """
        result = sample_ensemble([candidate(1.0, BEST)], draws=5, seed=1)
        assert "NOT an uncertainty estimate" in result.disclaimer
        assert "validation" in result.disclaimer

    def test_it_never_invents_a_value_nobody_measured(self) -> None:
        """Resampling, not curve-fitting. With three published numbers the
        ensemble contains at most three distinct values, and that discreteness
        is the honest shape of three measurements.
        """
        pool = [candidate(1.0, BEST), candidate(5.0, BEST), candidate(9.0, BEST)]
        result = sample_ensemble(pool, draws=500, seed=4)
        assert set(result.draws) <= {1.0, 5.0, 9.0}
        assert result.distinct_values <= 3

    def test_the_policy_is_echoed_so_a_reader_can_disagree(self) -> None:
        result = sample_ensemble([candidate(1.0, BEST)], draws=5, seed=1)
        assert result.policy is DEFAULT_WEIGHT_POLICY

    def test_every_weight_carries_its_arithmetic(self) -> None:
        """A weight with no derivation is the kind of unexplained number this
        project exists to remove. Each one names its axes, grades and factors.
        """
        weighted = weigh([candidate(1.0, score("partial", "near", "related"))])
        axes = {axis for axis, _, _ in weighted[0].breakdown}
        assert axes == {"assay_completeness", "condition_proximity", "organism_match"}
        product = math.prod(f for _, _, f in weighted[0].breakdown)
        assert weighted[0].raw_weight == pytest.approx(product)

    def test_summary_uses_percentiles_not_a_standard_deviation(self) -> None:
        """The draws come from a handful of discrete values and are rarely
        symmetric; a standard deviation would describe a bell that is not
        there.
        """
        pool = [candidate(1.0, BEST), candidate(100.0, BEST)]
        s = sample_ensemble(pool, draws=1000, seed=5).summary()
        assert set(s) == {"n", "low", "p05", "median", "p95", "high", "fold_range"}
        assert s["low"] == 1.0 and s["high"] == 100.0
        assert s["fold_range"] == pytest.approx(100.0)

    def test_a_percentile_is_always_a_value_somebody_measured(self) -> None:
        """Nearest-rank, not interpolated. Interpolating between two published
        numbers reports a third that nobody observed, which is what resampling
        was chosen to avoid in the first place.
        """
        pool = [candidate(2.0, BEST), candidate(8.0, BEST)]
        s = sample_ensemble(pool, draws=999, seed=6).summary()
        for key in ("p05", "median", "p95"):
            assert s[key] in (2.0, 8.0), f"{key} was interpolated: {s[key]}"
