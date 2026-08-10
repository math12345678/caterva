"""Regression: the two-locus domain had no Rule 2 tier at all.

`_validate_two_locus_params` built a `flagged: List[str]` that nothing ever
appended to, then passed it into `ParameterValidation`'s **boolean**
`flagged` field, silencing the type error with
`# type: ignore[arg-type]`. An empty list is falsy, and
`_serialise_result` in the API bridge wraps the field in `bool(...)`, so
every two-locus run reported `flagged: false` regardless of its inputs.

It was the only domain in the engine with no implausible-but-valid tier.
A population of 2, a mutation rate of 0.5, a single replicate — all
accepted silently, while every other domain flags each of them.

Rule 2 (`docs/CONSTITUTION.md`): a value that is arithmetically valid but
outside anything observed is FLAGGED, not rejected. The run completes; the
student is told the number is unusual.

The thresholds are the single-locus ones, imported rather than redefined,
so the two domains cannot drift apart on what counts as a small population
or an implausible mutation rate.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.data_structures import (  # noqa: E402
    WF_PLAUSIBLE_MAX_MUTATION_RATE,
    WF_PLAUSIBLE_MIN_POPULATION_SIZE,
    WF_PLAUSIBLE_MIN_REPLICATE_RUNS,
)
from tellurium_engine import simulate_two_locus_wright_fisher  # noqa: E402

BASE = dict(generations=20, recombination_rate=0.1, mutation_rate=0.0)


class TestFlaggedIsABooleanThatCanActuallyBeTrue:
    def test_flagged_is_a_bool_not_a_list(self):
        """The type confusion itself. `bool([])` is False forever."""
        result = simulate_two_locus_wright_fisher(
            population_size=100, replicate_runs=50, **BASE
        )
        assert isinstance(result.validation.flagged, bool), (
            f"flagged is {type(result.validation.flagged).__name__}; a list "
            "is always falsy once coerced, so no input could ever flag"
        )

    def test_an_extreme_parameter_set_is_flagged(self):
        result = simulate_two_locus_wright_fisher(
            population_size=2, replicate_runs=2, generations=20,
            recombination_rate=0.1, mutation_rate=0.5,
        )
        assert result.validation.ok is True, "Rule 2: flagged, never rejected"
        assert result.flagged is True, (
            "population_size=2, mutation_rate=0.5, replicate_runs=2 — every "
            "other domain flags each of these individually"
        )
        assert result.validation.flag_reason, "flagged with no reason given"


class TestEachThresholdIndividually:
    def test_tiny_population_is_flagged(self):
        result = simulate_two_locus_wright_fisher(
            population_size=WF_PLAUSIBLE_MIN_POPULATION_SIZE - 1,
            replicate_runs=50, **BASE
        )
        assert result.flagged is True
        assert "population_size" in (result.validation.flag_reason or "")

    def test_implausible_mutation_rate_is_flagged(self):
        result = simulate_two_locus_wright_fisher(
            population_size=100, replicate_runs=50, generations=20,
            recombination_rate=0.1,
            mutation_rate=WF_PLAUSIBLE_MAX_MUTATION_RATE * 10,
        )
        assert result.flagged is True
        assert "mutation_rate" in (result.validation.flag_reason or "")

    def test_too_few_replicates_is_flagged(self):
        result = simulate_two_locus_wright_fisher(
            population_size=100,
            replicate_runs=WF_PLAUSIBLE_MIN_REPLICATE_RUNS - 1, **BASE
        )
        assert result.flagged is True
        assert "replicate_runs" in (result.validation.flag_reason or "")

    def test_multiple_problems_are_all_reported(self):
        result = simulate_two_locus_wright_fisher(
            population_size=2, replicate_runs=2, generations=20,
            recombination_rate=0.1, mutation_rate=0.5,
        )
        reason = result.validation.flag_reason or ""
        for expected in ("population_size", "replicate_runs", "mutation_rate"):
            assert expected in reason, (
                f"{expected} missing from the flag reason; only the first "
                "problem is being reported"
            )


class TestOrdinaryParametersAreNotFlagged:
    def test_a_normal_run_is_clean(self):
        result = simulate_two_locus_wright_fisher(
            population_size=100, replicate_runs=50, **BASE
        )
        assert result.flagged is False, (
            f"unexpected flag: {result.validation.flag_reason}"
        )

    def test_exactly_at_the_threshold_is_not_flagged(self):
        # The bounds flag BELOW the minimum, not at it.
        result = simulate_two_locus_wright_fisher(
            population_size=WF_PLAUSIBLE_MIN_POPULATION_SIZE,
            replicate_runs=WF_PLAUSIBLE_MIN_REPLICATE_RUNS, **BASE
        )
        assert result.flagged is False, (
            f"unexpected flag: {result.validation.flag_reason}"
        )

    def test_rejected_input_is_still_rejected_not_flagged(self):
        # Rule 1 must survive: impossible input raises, it does not flag.
        with pytest.raises(Exception):
            simulate_two_locus_wright_fisher(
                population_size=-5, replicate_runs=50, **BASE
            )
