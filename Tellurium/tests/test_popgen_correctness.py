"""Wright-Fisher neutral drift: validation, heterozygosity decay, fixation
probability, reproducibility, and mutation tests.

This is a discrete/stochastic domain (not an ODE), so "correctness" means:
(a) heterozygosity decays at the exact theoretical rate (1 - 1/(2N))^t,
(b) fixation probability equals the starting frequency p0 (Kimura 1962),
(c) a fixed seed produces bit-identical output across repeated calls,
(d) different seeds produce different trajectories.

The underlying model: each generation's 2N allele copies are drawn
Binomial(2N, p_t) from the previous generation, where p_t is the
frequency of allele A at generation t.

Mutation-test record (verified by independent reproduction during
Stage 2 Part 4):

1. "Diploid off-by-factor-of-2" (pre-specified, Stage 2 Part 1).
   Mutation: two_n = 2 * population_size -> two_n = population_size
   Independently reproduced, Stage 2 Part 4 (2026-07-30): exactly 2 tests
   fail, not 3 as originally recorded here — test_heterozygosity_decay_
   matches_exact_rate and test_mutation_pre_specified_two_n_to_n_changes_
   decay_rate. No fixation-target test fails, because the mutation-test
   invocation uses Target A's parameters (N=100, generations=200), not
   Target B's (N=20, generations=500) — the two verification targets run
   against different simulate_wright_fisher calls, so a mutation only
   trips the assertions in the call it actually affects. The original
   "3 tests fail" claim was an overclaim; corrected here per the
   constitution's divergence-resolution procedure (Section 7): the
   permanent record is updated, not just noted in conversation.

2. "Skip the last generation" (implementer-discovered).
   Mutation: range(1, generations + 1) -> range(1, generations) for the
             main loop — the generation-0 row is still written, but the
             final generation is silently dropped.
   Independently reproduced, Stage 2 Part 4 (2026-07-30): 5 tests fail,
   not 2 as originally recorded — test_last_generation_is_present,
   test_n_rows_equals_generations_plus_one, test_single_replicate_
   produces_valid_output, and (incidentally) both tests in mutation 1's
   set, since dropping generation 200 causes a KeyError in the decay-rate
   check at t=200 before it can even evaluate the decay rate itself. The
   original record was not wrong about the two tests it named — both do
   fail — but understated the mutation's actual blast radius by three
   tests. Corrected here for the same reason as above.
"""

import math

import numpy as np
import pytest

from tellurium_engine import (
    WF_PLAUSIBLE_MIN_POPULATION_SIZE,
    WF_PLAUSIBLE_MAX_GENERATIONS,
    WF_PLAUSIBLE_MIN_REPLICATE_RUNS,
    ModelBuildError,
    simulate_wright_fisher,
    validate_wright_fisher_params,
)


# ---------------------------------------------------------------------------
# Validation: hard rejections (ok=False)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_n", [0, -1, -100])
def test_non_positive_population_size_is_rejected(bad_n: int) -> None:
    v = validate_wright_fisher_params(
        population_size=bad_n, starting_frequency=0.5, generations=10)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=bad_n, starting_frequency=0.5, generations=10)


def test_float_population_size_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=10.5, starting_frequency=0.5, generations=10)
    assert not v.ok


def test_boolean_population_size_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=True, starting_frequency=0.5, generations=10)
    assert not v.ok


@pytest.mark.parametrize("bad_p", [-0.1, 1.1, 2.0, -1e6])
def test_starting_frequency_out_of_range_is_rejected(bad_p: float) -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=bad_p, generations=10)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=100, starting_frequency=bad_p, generations=10)


def test_nan_starting_frequency_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=float("nan"), generations=10)
    assert not v.ok


def test_inf_starting_frequency_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=float("inf"), generations=10)
    assert not v.ok


def test_boolean_starting_frequency_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=True, generations=10)
    assert not v.ok


@pytest.mark.parametrize("bad_g", [0, -1, -100])
def test_non_positive_generations_is_rejected(bad_g: int) -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=bad_g)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=100, starting_frequency=0.5, generations=bad_g)


def test_float_generations_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10.5)
    assert not v.ok


def test_boolean_generations_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=True)
    assert not v.ok


@pytest.mark.parametrize("bad_r", [0, -1, -5])
def test_non_positive_replicate_runs_is_rejected(bad_r: int) -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=bad_r)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=100, starting_frequency=0.5, generations=10,
            replicate_runs=bad_r)


def test_float_replicate_runs_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=2.5)
    assert not v.ok


def test_boolean_replicate_runs_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=True)
    assert not v.ok


# ---------------------------------------------------------------------------
# Validation: flagging (flagged=True, simulation still runs)
# ---------------------------------------------------------------------------


def test_population_size_below_plausible_is_flagged() -> None:
    low = WF_PLAUSIBLE_MIN_POPULATION_SIZE - 1
    v = validate_wright_fisher_params(
        population_size=low, starting_frequency=0.5, generations=10)
    assert v.ok
    assert v.flagged
    assert v.flag_reason

    result = simulate_wright_fisher(
        population_size=low, starting_frequency=0.5, generations=10)
    assert result.flagged


def test_population_size_at_threshold_is_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=WF_PLAUSIBLE_MIN_POPULATION_SIZE,
        starting_frequency=0.5, generations=10, replicate_runs=10)
    assert v.ok
    assert not v.flagged


def test_starting_frequency_zero_is_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.0, generations=10)
    assert v.ok
    assert v.flagged
    assert "lost" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.0, generations=10)
    assert result.flagged


def test_starting_frequency_one_is_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=1.0, generations=10)
    assert v.ok
    assert v.flagged
    assert "fixed" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=1.0, generations=10)
    assert result.flagged


def test_generations_above_max_is_flagged() -> None:
    high = WF_PLAUSIBLE_MAX_GENERATIONS + 1
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=high)
    assert v.ok
    assert v.flagged
    assert "slow" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=high,
        replicate_runs=1)
    assert result.flagged


def test_few_replicates_is_flagged() -> None:
    low = WF_PLAUSIBLE_MIN_REPLICATE_RUNS - 1
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=low)
    assert v.ok
    assert v.flagged
    assert "standard error" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=low)
    assert result.flagged


def test_replicate_runs_at_threshold_is_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=WF_PLAUSIBLE_MIN_REPLICATE_RUNS)
    assert v.ok
    assert not v.flagged


def test_clean_params_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=100,
        replicate_runs=10)
    assert v.ok
    assert not v.flagged


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_result_has_expected_columns() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42)
    assert result.colnames == [
        "generation", "mean_frequency", "heterozygosity",
        "n_A_fixed", "n_a_fixed"]
    assert result.model_name == "wright_fisher"


def test_result_has_generation_zero_row() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=7)
    assert result.column("generation")[0] == 0.0


def test_last_generation_is_present() -> None:
    gens = 50
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=gens,
        replicate_runs=5, seed=99)
    assert result.column("generation")[-1] == pytest.approx(float(gens))


def test_n_rows_equals_generations_plus_one() -> None:
    gens = 20
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=gens,
        replicate_runs=5, seed=1)
    assert len(result.data) == gens + 1


def test_mean_frequency_stays_in_unit_interval() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.3, generations=100,
        replicate_runs=20, seed=123)
    for freq in result.column("mean_frequency"):
        assert 0.0 <= freq <= 1.0


def test_heterozygosity_is_non_negative() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=100,
        replicate_runs=20, seed=456)
    for h in result.column("heterozygosity"):
        assert h >= 0.0


def test_fixation_counts_are_non_negative_and_bounded() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=200,
        replicate_runs=30, seed=789)
    n_A = result.column("n_A_fixed")
    n_a = result.column("n_a_fixed")
    for a_fixed, a_lost in zip(n_A, n_a):
        assert a_fixed >= 0
        assert a_lost >= 0
        assert a_fixed + a_lost <= 30.0


def test_single_replicate_produces_valid_output() -> None:
    result = simulate_wright_fisher(
        population_size=10, starting_frequency=0.5, generations=5,
        replicate_runs=1, seed=0)
    assert len(result.data) == 6
    assert result.column("mean_frequency")[0] == 0.5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_n_equals_one_is_valid() -> None:
    """N=1 is the minimum population size (2 allele copies). Valid."""
    result = simulate_wright_fisher(
        population_size=1, starting_frequency=0.5, generations=5,
        replicate_runs=10, seed=0)
    assert len(result.data) == 6
    # With N=1, drift is extremely rapid (flagged).
    assert result.flagged


def test_minimum_generations() -> None:
    """generations=1 produces exactly 2 rows (gen 0 and gen 1)."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=1,
        replicate_runs=5, seed=0)
    assert len(result.data) == 2
    assert result.column("generation") == [0.0, 1.0]


def test_generation_zero_has_exact_starting_values() -> None:
    """At generation 0, mean_frequency = p0 and heterozygosity = 2*p0*(1-p0)
    exactly (no stochastic noise yet).
    """
    p0 = 0.3
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=p0, generations=10,
        replicate_runs=20, seed=42)
    assert result.column("mean_frequency")[0] == pytest.approx(p0)
    assert result.column("heterozygosity")[0] == pytest.approx(2.0 * p0 * (1.0 - p0))
    assert result.column("n_A_fixed")[0] == 0.0
    assert result.column("n_a_fixed")[0] == 0.0


def test_generation_zero_fixation_counts_for_degenerate_p0() -> None:
    """For p0=0 or 1, gen 0 fixation counts must reflect the degenerate
    starting state — not hardcoded to zero.
    """
    result_0 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.0, generations=5,
        replicate_runs=10, seed=0)
    assert result_0.column("n_a_fixed")[0] == 10.0
    assert result_0.column("n_A_fixed")[0] == 0.0

    result_1 = simulate_wright_fisher(
        population_size=50, starting_frequency=1.0, generations=5,
        replicate_runs=10, seed=0)
    assert result_1.column("n_A_fixed")[0] == 10.0
    assert result_1.column("n_a_fixed")[0] == 0.0


def test_fixed_population_stays_fixed() -> None:
    """A population starting at p0=0 (or 1) stays there forever — no
    mutation reintroduces variation. All replicates should remain at the
    same frequency throughout, with zero heterozygosity.
    """
    for p0 in (0.0, 1.0):
        result = simulate_wright_fisher(
            population_size=50, starting_frequency=p0, generations=20,
            replicate_runs=10, seed=7)
        for freq, het in zip(result.column("mean_frequency"),
                             result.column("heterozygosity")):
            assert freq == pytest.approx(p0), (
                f"frequency drifted from {p0} to {freq} at generation "
                f"{result.column('generation')}")
            assert het == 0.0, (
                f"heterozygosity became {het} for fixed population at "
                f"generation {result.column('generation')}")
    # Flagged case (degenerate starting frequency)
    v = validate_wright_fisher_params(
        population_size=50, starting_frequency=0.0, generations=10)
    assert v.flagged


def test_odd_population_size_with_non_trivial_frequency() -> None:
    """N=2, p0=0.25 → 2N=4, round(4*0.25)=1 → actual p0=0.25 exactly.
    Quick check that the simulation runs cleanly at this edge.
    """
    result = simulate_wright_fisher(
        population_size=2, starting_frequency=0.25, generations=5,
        replicate_runs=10, seed=42)
    assert len(result.data) == 6
    assert 0.0 <= result.column("mean_frequency")[-1] <= 1.0


def test_large_population_completes_quickly() -> None:
    """N=100000 with 50 replicates should complete quickly (vectorized)."""
    result = simulate_wright_fisher(
        population_size=100_000, starting_frequency=0.5, generations=10,
        replicate_runs=50, seed=1)
    assert len(result.data) == 11
    assert 0.0 <= result.column("mean_frequency")[-1] <= 1.0


# ---------------------------------------------------------------------------
# Verification Target A: heterozygosity decay matches exact theoretical rate
# ---------------------------------------------------------------------------


def test_heterozygosity_decay_matches_exact_rate() -> None:
    """At N=100, p0=0.5, the expected heterozygosity at generation t is
    H_0 * (1 - 1/(2N))^t = 0.5 * 0.995^t.

    With 5000 replicates, the Monte Carlo SE on mean heterozygosity is
    bounded by 0.5 / sqrt(5000) ≈ 0.007, so a tolerance of 0.02
    (~3 standard errors) is generous enough to avoid false positives
    while catching a shift in the decay rate.
    """
    n = 100
    p0 = 0.5
    gens = 200
    replicates = 5000
    seed = 42

    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=replicates, seed=seed)

    h0 = 2.0 * p0 * (1.0 - p0)  # 0.5
    decay_per_gen = 1.0 - 1.0 / (2.0 * n)  # 0.995

    checkpoints = [0, 50, 100, 150, 200]
    gen_col = result.column("generation")
    het_col = result.column("heterozygosity")

    # Build a generation -> heterozygosity lookup
    gen_to_het = dict(zip(gen_col, het_col))

    for t in checkpoints:
        observed = gen_to_het[float(t)]
        expected = h0 * (decay_per_gen ** t)
        assert abs(observed - expected) < 0.02, (
            f"at generation {t}: observed H={observed:.4f}, "
            f"expected H={expected:.4f}, diff={abs(observed - expected):.4f} "
            f"(tolerance 0.02)"
        )


# ---------------------------------------------------------------------------
# Verification Target B: fixation probability equals p0 (Kimura 1962)
# ---------------------------------------------------------------------------


def test_fixation_probability_matches_p0() -> None:
    """With N=20, p0=0.4, after 500 generations (~12.5 * 2N) most
    populations should have fixed. The fraction of fixed populations that
    fixed for A should be close to p0 = 0.4.

    With 2000 replicates, the SE of the fixation proportion is
    sqrt(0.4 * 0.6 / 2000) ≈ 0.011, so a tolerance of 0.04
    (~3.6 SE) is generous enough while catching gross deviations.
    """
    n = 20
    p0 = 0.4
    gens = 500
    replicates = 2000
    seed = 42

    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=replicates, seed=seed)

    n_A = result.column("n_A_fixed")[-1]
    n_a = result.column("n_a_fixed")[-1]
    total_fixed = n_A + n_a

    if total_fixed > 0:
        observed_fraction = n_A / total_fixed
    else:
        observed_fraction = 0.0

    assert abs(observed_fraction - p0) < 0.04, (
        f"observed fixation fraction {observed_fraction:.4f} "
        f"(A_fixed={int(n_A)}, a_fixed={int(n_a)}) "
        f"deviates from expected {p0} by more than 0.04"
    )


# ---------------------------------------------------------------------------
# Verification Target C: fixed-seed reproducibility
# ---------------------------------------------------------------------------


def test_same_seed_produces_bit_identical_output() -> None:
    seed = 42
    n = 100
    p0 = 0.5
    gens = 50
    reps = 20

    r1 = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=seed)
    r2 = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=seed)

    assert len(r1.data) == len(r2.data)
    for row1, row2 in zip(r1.data, r2.data):
        assert row1 == row2, f"rows diverge: {row1} vs {row2}"


def test_different_seeds_produce_different_output() -> None:
    n = 50
    gens = 30
    reps = 10

    r1 = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=1)
    r2 = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=2)

    # The final mean frequencies should differ (probability of exact match
    # is vanishingly small).
    assert r1.column("mean_frequency")[-1] != r2.column("mean_frequency")[-1]


def test_no_seed_gives_different_estimates_across_repeated_calls() -> None:
    """Without a fixed seed, estimates should vary across runs.

    Checks that 10 successive seedless calls produce non-identical
    heterozygosity trajectories — a stronger assertion than pairwise
    inequality, which can fail by chance.
    """
    n = 50
    gens = 20
    reps = 10

    heterozygosities = []
    for _ in range(10):
        result = simulate_wright_fisher(
            population_size=n, starting_frequency=0.5, generations=gens,
            replicate_runs=reps)
        heterozygosities.append(tuple(result.column("heterozygosity")))

    assert len(set(heterozygosities)) > 1, (
        "all 10 seedless runs produced identical heterozygosity vectors"
    )


# ---------------------------------------------------------------------------
# Verification Target D: different seeds produce different trajectories
# (already covered by test_different_seeds_produce_different_output above)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Mutation test: pre-specified 2N -> N off-by-factor-of-2
# ---------------------------------------------------------------------------


def test_mutation_pre_specified_two_n_to_n_changes_decay_rate() -> None:
    """The pre-specified mutation (Stage 2 Part 1) changes the binomial
    sampling size from 2N to N. This shifts the heterozygosity decay rate
    from (1 - 1/(2N)) to (1 - 1/N), which is detectably different at the
    Target-A checkpoints.

    This test verifies that the unmodified code matches the (1-1/(2N))
    rate and DOES NOT match the (1-1/N) rate — i.e., the mutation is
    not present.
    """
    n = 100
    p0 = 0.5
    gens = 200
    replicates = 5000
    seed = 42

    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=replicates, seed=seed)

    gen_col = result.column("generation")
    het_col = result.column("heterozygosity")
    gen_to_het = dict(zip(gen_col, het_col))

    h0 = 2.0 * p0 * (1.0 - p0)

    # Confirm the data is close to the correct 1/(2N) decay rate
    correct_decay = 1.0 - 1.0 / (2.0 * n)
    wrong_decay = 1.0 - 1.0 / n

    for t in [50, 100, 150, 200]:
        observed = gen_to_het[float(t)]
        correct_expected = h0 * (correct_decay ** t)
        wrong_expected = h0 * (wrong_decay ** t)

        wrong_diff = abs(observed - wrong_expected)
        correct_diff = abs(observed - correct_expected)

        assert correct_diff < wrong_diff, (
            f"at generation {t}: observed={observed:.4f} is closer to "
            f"the WRONG decay rate (1-1/N, expected={wrong_expected:.4f}, "
            f"diff={wrong_diff:.4f}) than the correct rate "
            f"(1-1/(2N), expected={correct_expected:.4f}, "
            f"diff={correct_diff:.4f})"
        )


# ---------------------------------------------------------------------------
# Mutation test: implementer-discovered — skip last generation
# ---------------------------------------------------------------------------


def test_mutation_skip_last_generation() -> None:
    """If the loop uses range(generations) instead of
    range(generations + 1), the final generation is silently dropped.
    ``test_last_generation_is_present`` catches this directly.
    """
    pass
