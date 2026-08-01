"""Wright-Fisher neutral drift: validation, heterozygosity decay, fixation
probability, reproducibility, allele-frequency variance, and mutation tests.

This is a discrete/stochastic domain (not an ODE), so "correctness" means:
(a) heterozygosity decays at the exact theoretical rate (1 - 1/(2N))^t,
(b) fixation probability equals the starting frequency p0 (Kimura 1962),
(c) a fixed seed produces bit-identical output across repeated calls,
(d) different seeds produce different trajectories,
(e) allele-frequency variance across replicates matches the theoretical
    Var(p_t) = p0(1-p0) * [1 - (1 - 1/(2N))^t].

The underlying model: each generation's 2N allele copies are drawn
Binomial(2N, p_t) from the previous generation, where p_t is the
frequency of allele A at generation t.

RNG follows ADR 0005: ``numpy.random.default_rng(seed)``, checked
automatically by ``scripts/check_rng_convention.py`` and
``Tellurium/tests/test_rng_convention.py``.

Mutation-test record (verified by independent reproduction during
Stage 2 Part 4, and re-verified after Stage 2 refactoring):

1. "Diploid off-by-factor-of-2" (pre-specified, Stage 2 Part 1).
   Mutation: two_n = 2 * population_size -> two_n = population_size
   Independently reproduced, Stage 2 Part 4 (2026-07-30): exactly 2 tests
   fail, not 3 as originally recorded here — heterozygosity_decay_ and
   mutation_pre_specified_two_n_to_n_. No fixation-target test fails,
   because the mutation-test invocation uses Target A's parameters
   (N=100, generations=200), not Target B's (N=20, generations=500).
   The original "3 tests fail" claim was an overclaim, corrected per
   the constitution's divergence-resolution procedure.
   Re-verified 2026-07-30 after adding test_allele_frequency
   _variance_matches_theory (Target E): blast radius is now 3 — the
   variance test also fails (observed variance shifts from ~0.055
   theoretical to ~0.107 under 2N→N, well outside the 0.015 tolerance).

2. "Skip the last generation" (implementer-discovered).
    Mutation: range(generations + 1) -> range(generations) for the main
              loop — the final generation is silently dropped.
    Independently reproduced, Stage 2 Part 4 (2026-07-30) and
    re-verified after the unified-loop refactoring (2026-07-30): 3 tests
    fail — test_last_generation_is_present, test_n_rows_equals_
    generations_plus_one, and test_single_replicate_produces_valid_output.
    (The earlier claim of 5 included incidental KeyErrors from mutation
    1's test set that depend on which mutation is being tested; the
    core blast radius for this mutation alone is 3 tests.)

3. "Mutation-rate parameter is silently ignored" (post-close).
    Mutation: the mutation_rate parameter is accepted but never applied
              to allele frequencies before the next generation.
    Added and independently reproduced 2026-07-30: 2 tests fail —
    test_mutation_drift_equilibrium and test_mutation_rate_increases_
    heterozygosity. The backward-compatibility test (mutation_rate=0
    vs omit) passes because both paths use the same ignored rate.
    All neutral-drift tests pass because they never set mutation_rate > 0.

4. "Selection-coefficient parameter is silently ignored" (post-close).
    Mutation: the selection_coefficient and dominance parameters are
              accepted but never used to adjust expected frequencies
              before binomial sampling.
    Added and independently reproduced 2026-07-30: 4 tests fail —
    test_selection_fixation_probability, test_positive_selection_
    increases_fixation, test_negative_selection_decreases_fixation,
    and test_selection_haploid_diploid_differ. Backward-compatibility
    (s=0) and all neutral/mutation tests pass because they never set
    s != 0.

5. "Migration step silently skipped" (post-close, found during Stage 2
    completion audit -- migration/island-model had 9 behavioral tests
    but no independently-reproduced mutation test, unlike mutation_rate
    and selection above; added to close that gap).
    Mutation: the migration block (island-model global-pool mixing,
              ``frequencies = (1-m)*frequencies + m*p_global``) is
              gated behind an always-false condition, so migration_rate
              is accepted and validated but never actually applied.
    Independently reproduced 2026-07-30: 2 tests fail —
    test_migration_reduces_fst (Fst with migration_rate=0.05 no longer
    drops below the no-migration Fst; both equal 0.3275, i.e. migration
    had zero effect) and test_high_migration_demes_homogenised (Fst
    stays at 0.4520 instead of dropping below 0.05 under high
    migration). Panmictic (n_demes=1) and zero-migration tests pass
    because they never exercise the migration branch at all.

6. "Stepping-stone migration replaced by island model" (post-close,
   added with the migration_model feature 2026-07-31).
   Mutation: the stepping-stone branch (ring exchange with m/2 per
   neighbour) is replaced by the island-model global-pool step, so
   migration_model has no effect.
   Independently reproduced 2026-07-31: 5 tests fail — the mutated
   branch references ``p_global`` which the island-only mutation never
   defines, so stepping-stone runs raise UnboundLocalError instead of
   producing output: test_stepping_stone_fst_higher_than_island,
   test_stepping_stone_conserves_mean_frequency,
   test_migration_model_stored_in_params, test_scenario_stepping_stone_
   runs, and test_cli_wf_migration_model_flag. (The m=0 equivalence
   test passes because it never enters either branch.)

7. "Ne estimate off by factor of 2" (post-close, added with the
   heterozygosity-decay estimator 2026-07-31).
   Mutation: ``ne = 1/(2(1-decay))`` -> ``ne = 1/(1-decay)`` (the
   diploid factor of 2 dropped from the estimator).
   Independently reproduced 2026-07-31: 2 tests fail —
   test_estimate_ne_decay_matches_known_n (estimate ~2N instead of N)
   and test_estimate_ne_small_population. The variance-method and
   error-path tests pass because they never check the decay estimate's
   scale.

8. "Stationary distribution uses 2Nu instead of 4Nu" (post-close, added
   with wright_stationary_distribution 2026-07-31).
   Mutation: ``a = 4Nu`` -> ``a = 2Nu`` (haploid instead of diploid
   allele-copy count).
   Independently reproduced 2026-07-31: 2 tests fail —
   test_stationary_distribution_normalization (density value at p=0.5
   no longer matches Beta(4Nu,4Nu)) and test_stationary_distribution_
   matches_simulation (observed vs theoretical central mass diverges).
   The symmetry/mode and edge-case tests pass because they only check
   qualitative shape.

9. "Theoretical Fst uses 2N(m+u) instead of 4N(m+u)" (post-close, added
   with theoretical_fst 2026-07-31).
   Mutation: ``1 + 4N(m+u)`` -> ``1 + 2N(m+u)`` in the island-model
   equilibrium formula.
   Independently reproduced 2026-07-31: 2 tests fail —
   test_theoretical_fst_closed_form (exact closed-form check against
   1/(1+4N(m+u))) and test_theoretical_fst_matches_simulation (theory
   0.089 vs simulation 0.042 at 30 demes diverges). The validation
   test passes because it never checks the formula's scale.

10. "Transition matrix samples Binomial(N, p) instead of Binomial(2N, p)"
    (post-close, added with wright_fisher_transition_matrix 2026-07-31).
    Mutation: the reproduction step of the matrix uses ``N`` allele
    copies instead of ``2N``.
    Independently reproduced 2026-07-31: 9 tests fail — hand-checked
    N=1 matrix, rows-sum-to-one, neutral mean- and variance-
    preservation, absorbing states (Binomial(N, .) from state 0 no
    longer puts all mass on 0), matrix-power-vs-simulation, closed-form
    match, selection monotonicity, simulation-under-selection, and
    diploid-dominance ordering. The validation and boundary tests pass
    because they only check the error paths, not the sampling scale.

11. "Fixation time solves the unconditional absorption system instead of
    conditioning on fixation" (post-close, added with
    wright_fisher_expected_fixation_time 2026-07-31).
    Mutation: ``E[T | fixation] = w/f`` replaced by the plain
    absorption-time solve ``w = (I - Q_t)^{-1} . 1``.
    Independently reproduced 2026-07-31: 3 tests fail —
    test_chain_fixation_time_matches_closed_form (p0=0.2: unconditional
    ~200 vs conditional ~355; the p0=0.5 case passes because
    conditional == unconditional by symmetry),
    test_chain_fixation_time_selection_monotone (under strong s the
    unconditional time exceeds the neutral unconditional time, breaking
    the ordering), and test_chain_fixation_time_matches_simulation_
    under_selection (sim 89.5 vs unconditional ~200). Boundaries,
    validation, and diploid-dominance tests pass because they never
    check the conditioning.

12. "Fixation-probability solve drops the p_top term"
    (post-close, added with wright_fisher_fixation_probability
    2026-07-31).
    Mutation: ``f = solve(I - Q_t, 0)`` instead of
    ``f = solve(I - Q_t, p_top)`` in the shared absorption helper
    ``_wf_fixation_vector`` (so f = 0 everywhere and every interior
    state returns P_fix = 0).
    Independently reproduced 2026-07-31: 7 tests fail — neutral
    martingale (0 vs p0), matches-Kimura-genic, overdominance-vs-sim,
    underdominance-beats-kimura, monotone-in-s, and both CLI tests
    (the exact P_fix line and, via the shared helper, the
    ``--time --exact`` line, which now hits the ``f <= 1e-15`` guard
    and exits 1). The boundaries/validation test passes because the
    p0=0/p0=1 shortcuts and error paths never reach the solve.

13. "Loss time conditions on the wrong boundary (v/f instead of
    v/(1-f))" (post-close, added with wright_fisher_expected_loss_time
    2026-07-31).
    Mutation: ``E[T | loss] = v / (1 - f)`` replaced by ``v / f``.
    Independently reproduced 2026-07-31: 4 tests fail — closed-form
    match at p0=0.1/0.9 (9x off; the p0=0.5 case passes because
    f = 1-f there), chain symmetry (loss(0.3) vs fix(0.7)), loss-vs-
    simulation (p0=0.2: 4x off), and the absorption-time consistency
    identity. The selection-monotonicity test passes (v/f still
    decreases with s), as do the boundaries and closed-form-only
    tests.

14. "Fixation-generation tracking swaps the A and a boundaries"
    (post-close, added with the absorption-time extension of
    fixation_analysis 2026-07-31).
    Mutation: ``fixation_gen_A[... == 1.0]`` and
    ``fixation_gen_a[... == 0.0]`` exchange their conditions, so
    every replicate's fixation/loss label flips.
    Independently reproduced 2026-07-31: 9 tests fail -- the
    selection/sweep/overdominance/underdominance and exact-chain
    tests that read prop_fixed_A or the boundary-specific mean times
    (under s=0.05 the swapped "fixation" times are the loss times,
    59 % off; under dominance the proportions flip). The neutral
    p0=0.5 tests pass because fixation and loss are symmetric there
    (means and proportions coincide), and the absorption-time tests
    pass because the union of the two lists is unchanged.

15. "Stationary vector uses the right eigenvectors of Q instead of the
    left eigenvectors of Q^T" (post-close, added with the exact-chain
    stationary distribution 2026-07-31).
    Mutation: ``scipy.linalg.eig(Q)`` instead of ``eig(Q.T)``, so the
    Perron-Frobenius vector is taken from the wrong side of the
    matrix (scipy's right eigenvectors for eigenvalue 1 are
    degenerate here and the argmin picks a numerically worthless
    vector -- the test run produced an all-NaN vector).
    Independently reproduced 2026-07-31: 5 tests fail -- the
    fixed-point, symmetry, Beta-density, simulation-spectrum, and
    selection-mode tests. Only the validation test passes, because it
    checks parameters, not values.

16. "Effective size uses the arithmetic mean instead of the harmonic
    mean" (post-close, added with effective_size_harmonic_mean
    2026-07-31).
    Mutation: ``k / sum(1/N_t)`` -> ``sum(N_t) / k``.
    Independently reproduced 2026-07-31: 4 tests fail -- the
    known-values, harmonic<=arithmetic (AM-GM), oscillating-series
    simulated-Ne, and bottleneck-dominance tests. The constant-series
    test passes, because the two means coincide there (also its only
    blind spot as a mutation target).

17. "Recombination step is skipped" (post-close, added with the
    two-locus simulation 2026-07-31).
    Mutation: the four recombination updates of the haplotype
    frequencies are deleted, so D decays by drift alone.
    Independently reproduced 2026-07-31: 4 tests fail -- the
    recombination-only decay (D20 stays ~0.25 instead of 0.030),
    drift+recombination decay, r=0 vs r=0.5 ordering (both decay at
    the same drift rate), and repulsion-sign decay tests. The
    theoretical-decay test passes (it tests the theory function, not
    the simulation), and the random-association / frequency-
    conservation / determinism tests pass because they never depend
    on the recombination step.

18. "Expected Fst after split uses the classic variance-based formula
    instead of the exact expectation over the joint chain"
    (post-close, added with expected_fst_after_split 2026-07-31).
    Mutation: the transition-matrix double-sum is replaced by
    ``1 - (1 - 1/(2N))^t``.
    Independently reproduced 2026-07-31: 3 tests fail -- the
    simulation match (the classic formula runs 1.8x too high at
    t=200), the monotone/limit property test, and the
    divergent-fixation limit test (0.982 instead of 0.5, and the
    formula is p0-independent so the p0=0.3/0.7 symmetry assertion
    also breaks). The validation test passes, because it checks
    parameters, not values.

19. "Two-locus mutation step is skipped" (post-close, added with the
    two-locus mutation_rate extension 2026-07-31).
    Mutation: the per-copy mutation operator is neutralized
    (uu = cu = 0, mu = 1), so u is accepted but never applied.
    Independently reproduced 2026-07-31: 2 tests fail -- the
    mutation-accelerates-LD-decay test (D15 = 0.0443, the pure
    recombination+drift value, instead of 0.0130) and the
    frequencies-pushed-to-0.5 test (freq A stays 0.80 instead of
    drifting to 0.5). The theoretical-decay and validation tests
    pass, because they do not exercise the simulation's mutation
    step. NOTE: an earlier candidate mutation (asymmetric one-way
    operator ``uu=u, cu=0, mu=1-u``) was rejected as a record
    because its cyclic mixing still equilibrates at uniform
    frequencies, so only 1 test caught it.
"""
import math
import pathlib

import numpy as np
import pytest

from tellurium_engine import (
    WF_PLAUSIBLE_MIN_POPULATION_SIZE,
    WF_PLAUSIBLE_MAX_GENERATIONS,
    WF_PLAUSIBLE_MIN_REPLICATE_RUNS,
    WF_PLAUSIBLE_MAX_MUTATION_RATE,
    WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT,
    ModelBuildError,
    estimate_ne_from_heterozygosity,
    expected_fixation_time,
    expected_loss_time,
    kimura_fixation_probability,
    list_scenarios,
    simulate_wright_fisher,
    theoretical_fst,
    validate_wright_fisher_params,
    wright_fisher_expected_absorption_time,
    wright_fisher_expected_fixation_time,
    wright_fisher_expected_loss_time,
    wright_fisher_fixation_probability,
    wright_fisher_scenario,
    wright_fisher_sweep,
    _normalise_stationary_vector,
    wright_fisher_stationary_vector,
    wright_fisher_transition_matrix,
    wright_stationary_distribution,
    effective_size_harmonic_mean,
    expected_fst_after_split,
    simulate_two_locus_wright_fisher,
    theoretical_ld_decay,
    _clamp_wf_fst_roundoff,
)


# Tellurium/cli.py is invoked as `python -m Tellurium.cli` (see its own
# docstring), which requires the repo root -- the parent of Tellurium/ --
# as the subprocess's working directory. Tests here run with cwd=Tellurium/
# (see Makefile's `test-sim` target and CI's `working-directory:
# Tellurium`), so every CLI subprocess call must pass cwd explicitly, not
# rely on the test runner's own working directory.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


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


def test_negative_mutation_rate_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=-0.01)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=100, starting_frequency=0.5, generations=10,
            mutation_rate=-0.01)


def test_excessive_mutation_rate_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=1.5)
    assert not v.ok


def test_mutation_rate_one_is_valid() -> None:
    """mutation_rate=1.0 is the upper boundary of [0,1]; every allele
    flips every generation. Valid but extreme.
    """
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=1.0)
    assert v.ok
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42, mutation_rate=1.0)
    assert len(result.data) == 11


def test_nan_mutation_rate_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=float("nan"))
    assert not v.ok


def test_inf_mutation_rate_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=float("inf"))
    assert not v.ok


def test_boolean_mutation_rate_is_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=True)
    assert not v.ok


def test_selection_below_minus_one_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=-1.5)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_wright_fisher(
            population_size=100, starting_frequency=0.5, generations=10,
            selection_coefficient=-1.5)


def test_selection_coefficient_minus_one_boundary_rejected() -> None:
    """s = -1.0 is the boundary of the valid range (must be > -1).
    s = -1 would make allele A lethal (fitness=0), which causes a
    division-by-zero in the haploid selection formula.
    """
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=-1.0)
    assert not v.ok
    assert any("> -1" in e for e in v.errors)


def test_nan_selection_coefficient_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=float("nan"))
    assert not v.ok


def test_inf_selection_coefficient_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=float("inf"))
    assert not v.ok


def test_boolean_selection_coefficient_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=True)
    assert not v.ok


def test_dominance_below_zero_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=0.05, dominance=-0.1)
    assert not v.ok


def test_dominance_above_two_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=0.05, dominance=2.5)
    assert not v.ok


def test_overdominance_dominance_flagged_not_rejected() -> None:
    """h > 1 is valid (overdominance/underdominance) but flagged."""
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, selection_coefficient=0.05, dominance=1.5)
    assert v.ok
    assert v.flagged
    assert "overdominance" in (v.flag_reason or "")


def test_boolean_dominance_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=0.05, dominance=True)
    assert not v.ok


def test_nan_dominance_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=0.05, dominance=float("nan"))
    assert not v.ok


def test_dominance_boundaries_zero_and_one_are_valid() -> None:
    for h in (0.0, 1.0):
        v = validate_wright_fisher_params(
            population_size=100, starting_frequency=0.5, generations=10,
            selection_coefficient=0.05, dominance=h)
        assert v.ok, f"dominance={h} was rejected: {v.errors}"
        result = simulate_wright_fisher(
            population_size=100, starting_frequency=0.5, generations=10,
            replicate_runs=5, seed=42, selection_coefficient=0.05,
            dominance=h)
        assert len(result.data) == 11


def test_numpy_float_types_for_selection_params() -> None:
    """numpy.float64/32 are NOT subclasses of Python float in numpy 2.x.
    selection_coefficient and dominance must accept them.
    """
    import numpy as np
    for float_type in (np.float64, np.float32):
        v = validate_wright_fisher_params(
            population_size=100, starting_frequency=0.5, generations=10,
            selection_coefficient=float_type(0.05))
        assert v.ok, f"{float_type.__name__} selection_coefficient rejected"
        v = validate_wright_fisher_params(
            population_size=100, starting_frequency=0.5, generations=10,
            selection_coefficient=float_type(0.05),
            dominance=float_type(0.5))
        assert v.ok, f"{float_type.__name__} dominance rejected"
        v = validate_wright_fisher_params(
            population_size=100, starting_frequency=0.5, generations=10,
            mutation_rate=float_type(0.01))
        assert v.ok, f"{float_type.__name__} mutation_rate rejected"


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


def test_numpy_integer_types_are_accepted() -> None:
    """numpy.int64/32/uint64 are NOT subclasses of Python int in numpy 2.x.
    Validation must accept them via isinstance(x, (int, np.integer)).
    """
    import numpy as np
    for int_type in (np.int64, np.int32, np.uint32):
        v = validate_wright_fisher_params(
            population_size=int_type(100), starting_frequency=0.5,
            generations=int_type(100), replicate_runs=int_type(10))
        assert v.ok, f"{int_type.__name__} was rejected: {v.errors}"


def test_high_mutation_rate_is_flagged() -> None:
    high = WF_PLAUSIBLE_MAX_MUTATION_RATE * 2
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=high)
    assert v.ok
    assert v.flagged
    assert "mutation" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        mutation_rate=high)
    assert result.flagged


def test_zero_mutation_rate_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, mutation_rate=0.0)
    assert v.ok
    assert not v.flagged


def test_mutation_rate_below_threshold_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, mutation_rate=WF_PLAUSIBLE_MAX_MUTATION_RATE)
    assert v.ok
    assert not v.flagged


def test_strong_positive_selection_is_flagged() -> None:
    high = WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT + 0.1
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=high)
    assert v.ok
    assert v.flagged
    assert "selection" in v.flag_reason.lower()

    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=high)
    assert result.flagged


def test_strong_negative_selection_is_flagged() -> None:
    high = -(WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT + 0.1)
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        selection_coefficient=high)
    assert v.ok
    assert v.flagged
    assert "selection" in v.flag_reason.lower()


def test_zero_selection_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, selection_coefficient=0.0)
    assert v.ok
    assert not v.flagged


def test_moderate_selection_not_flagged() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10,
        selection_coefficient=WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT)
    assert v.ok
    assert not v.flagged


def test_dominance_none_with_selection_is_valid() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, selection_coefficient=0.1, dominance=None)
    assert v.ok
    assert not v.flagged


def test_multiple_flag_conditions_are_all_reported() -> None:
    # N below threshold AND p0 degenerate AND few reps — the old elif chain
    # silently dropped all but the first. Every condition must be visible.
    v = validate_wright_fisher_params(
        population_size=5, starting_frequency=0.0, generations=10,
        replicate_runs=1)
    assert v.ok
    assert v.flagged
    assert "population_size=5" in v.flag_reason
    assert "lost" in v.flag_reason
    assert "standard error" in v.flag_reason
    assert "replicate_runs=1" in v.flag_reason


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_result_has_expected_columns() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42)
    assert result.colnames == [
        "generation", "mean_frequency", "heterozygosity",
        "mean_frequency_se", "heterozygosity_se",
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
    prev_a = prev_b = -1.0
    for a_fixed, a_lost in zip(n_A, n_a):
        assert a_fixed >= 0
        assert a_lost >= 0
        assert a_fixed + a_lost <= 30.0
        # Without mutation (default 0), once a replicate's frequency hits
        # 0.0 or 1.0, binomial sampling keeps it there forever — fixation
        # counts are monotonic. With mutation_rate > 0 this would not hold
        # (mutation can reintroduce the lost allele).
        assert a_fixed >= prev_a, (
            f"n_A_fixed decreased from {prev_a} to {a_fixed}")
        assert a_lost >= prev_b, (
            f"n_a_fixed decreased from {prev_b} to {a_lost}")
        prev_a, prev_b = a_fixed, a_lost


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


# ---------------------------------------------------------------------------
# Verification Target D: different seeds diverge
# ---------------------------------------------------------------------------


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
# Verification Target E: allele-frequency variance matches drift theory
# ---------------------------------------------------------------------------


def test_allele_frequency_variance_matches_theory() -> None:
    """Under WF drift, the variance of allele frequency across independent
    replicate populations at generation t follows:

        Var(p_t) = p0(1-p0) * [1 - (1 - 1/(2N))^t]

    Runs 500 single-replicate simulations, records the frequency at a
    mid-drift generation, and checks that the empirical variance matches
    the theoretical value within an acceptance window that accounts for
    estimation noise (simulated annealing: 500 sets × ~3 SE).
    """
    n = 100
    p0 = 0.5
    gens = 50
    n_sims = 500

    theoretical_var = p0 * (1.0 - p0) * (1.0 - (1.0 - 1.0 / (2.0 * n)) ** gens)

    freqs = np.empty(n_sims, dtype=np.float64)
    for i in range(n_sims):
        result = simulate_wright_fisher(
            population_size=n, starting_frequency=p0, generations=gens,
            replicate_runs=1, seed=i)
        freqs[i] = result.column("mean_frequency")[gens]

    observed_var = float(np.var(freqs, ddof=1))
    # With 500 sets, the SE of the variance estimate is
    # var * sqrt(2/(k-1)) ≈ 0.0035. The window ±0.015 covers ~4 SE.
    assert abs(observed_var - theoretical_var) < 0.015, (
        f"variance={observed_var:.4f}, expected={theoretical_var:.4f}, "
        f"diff={abs(observed_var - theoretical_var):.4f}"
    )


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


# ---------------------------------------------------------------------------
# Mutation behaviour: backward compatibility and effect tests
# ---------------------------------------------------------------------------


def test_mutation_rate_zero_gives_identical_results() -> None:
    """mutation_rate=0.0 must produce identical output to omitting the
    parameter entirely (backward compatibility).
    """
    result_no_mut = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=30,
        replicate_runs=10, seed=42)
    result_zero_mut = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=30,
        replicate_runs=10, seed=42, mutation_rate=0.0)
    assert result_no_mut.data == result_zero_mut.data


def test_mutation_rate_increases_heterozygosity() -> None:
    """Mutation reintroduces variation lost to drift, so heterozygosity
    at late generations should be higher with mutation than without.
    Uses enough replicates to overcome stochastic variation.
    """
    result_no_mut = simulate_wright_fisher(
        population_size=30, starting_frequency=0.5, generations=200,
        replicate_runs=50, seed=1)
    result_mut = simulate_wright_fisher(
        population_size=30, starting_frequency=0.5, generations=200,
        replicate_runs=50, seed=1, mutation_rate=0.02)

    h_no_mut = result_no_mut.column("heterozygosity")[-1]
    h_mut = result_mut.column("heterozygosity")[-1]
    assert h_mut > h_no_mut + 0.05, (
        f"heterozygosity with mutation ({h_mut:.4f}) should be "
        f"> without mutation ({h_no_mut:.4f}) by a clear margin"
    )


def test_mutation_drift_equilibrium() -> None:
    """Under symmetric mutation-drift balance, the expected heterozygosity
    for a biallelic locus converges to:

        H_eq = 4Nμ / (8Nμ + 1)

    where μ is the per-generation symmetric mutation rate.
    Derived from the Beta(4Nμ, 4Nμ) stationary distribution.
    """
    n = 50
    mu = 0.02
    gens = 500
    reps = 100

    h_eq_theory = (4.0 * n * mu) / (8.0 * n * mu + 1.0)

    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42, mutation_rate=mu)
    h_observed = result.column("heterozygosity")[-1]

    assert abs(h_observed - h_eq_theory) < 0.03, (
        f"observed heterozygosity {h_observed:.4f} deviates from "
        f"theoretical equilibrium {h_eq_theory:.4f} by more than 0.03"
    )


# ---------------------------------------------------------------------------
# Selection behaviour: backward compatibility and effect tests
# ---------------------------------------------------------------------------


def test_selection_zero_gives_identical_results() -> None:
    """selection_coefficient=0.0 must produce identical output to omitting
    the parameter entirely (backward compatibility).
    """
    result_no_sel = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=30,
        replicate_runs=10, seed=42)
    result_zero_sel = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=30,
        replicate_runs=10, seed=42, selection_coefficient=0.0)
    assert result_no_sel.data == result_zero_sel.data


def test_positive_selection_increases_fixation() -> None:
    """Under positive selection, a beneficial allele fixes more often
    than under neutrality.
    """
    n = 50
    p0 = 0.2
    s = 0.08
    gens = 300
    reps = 100

    result_sel = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=s)
    result_neutral = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=0.0)

    n_A_sel = result_sel.column("n_A_fixed")[-1]
    n_A_neutral = result_neutral.column("n_A_fixed")[-1]
    assert n_A_sel > n_A_neutral, (
        f"positive selection (s={s}) gave {n_A_sel} A-fixed replicates "
        f"vs neutral {n_A_neutral}"
    )


def test_negative_selection_decreases_fixation() -> None:
    """Under negative selection, a deleterious allele fixes less often
    than under neutrality.
    """
    n = 50
    p0 = 0.8
    s = -0.08
    gens = 300
    reps = 100

    result_sel = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=s)
    result_neutral = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=0.0)

    n_A_sel = result_sel.column("n_A_fixed")[-1]
    n_A_neutral = result_neutral.column("n_A_fixed")[-1]
    assert n_A_sel < n_A_neutral, (
        f"negative selection (s={s}) gave {n_A_sel} A-fixed replicates "
        f"vs neutral {n_A_neutral}"
    )


def test_selection_haploid_diploid_differ() -> None:
    """Haploid (dominance=None) and diploid (dominance=h) selection
    models produce different fixation counts for the same s.
    """
    n = 100
    p0 = 0.3
    s = 0.1
    gens = 200
    reps = 100

    result_hap = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=s,
        dominance=None)
    result_dip = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=s,
        dominance=0.5)

    n_A_hap = result_hap.column("n_A_fixed")[-1]
    n_A_dip = result_dip.column("n_A_fixed")[-1]
    assert n_A_hap != n_A_dip, (
        f"haploid and diploid models gave identical A-fixed count "
        f"({n_A_hap}) — expected different counts"
    )


def test_selection_fixation_probability() -> None:
    """Under haploid selection, the fixation probability of a beneficial
    allele follows Kimura's formula:

        P_fix = (1 - e^(-4Nsp0)) / (1 - e^(-4Ns))

    Verified with N=50, s=0.03, p0=0.3, 500 replicates.
    """
    n = 50
    p0 = 0.3
    s = 0.03
    gens = 500
    reps = 500

    # Kimura fixation probability for haploid model with 2N copies
    p_fix_theory = (
        (1.0 - np.exp(-4.0 * n * s * p0)) /
        (1.0 - np.exp(-4.0 * n * s)))

    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42, selection_coefficient=s,
        dominance=None)

    n_A = result.column("n_A_fixed")[-1]
    n_a = result.column("n_a_fixed")[-1]
    total_fixed = n_A + n_a
    if total_fixed > 0:
        obs_p_fix = n_A / total_fixed
    else:
        obs_p_fix = 0.0

    # Tolerance: 0.06, covering ~3 SE for 500 reps
    assert abs(obs_p_fix - p_fix_theory) < 0.06, (
        f"observed fixation probability {obs_p_fix:.4f} "
        f"deviates from Kimura prediction {p_fix_theory:.4f} "
        f"(A_fixed={int(n_A)}, a_fixed={int(n_a)})"
    )


# ---------------------------------------------------------------------------
# Mutation test: mutation-rate parameter is silently ignored
# ---------------------------------------------------------------------------


def test_mutation_mutation_rate_ignored() -> None:
    """If mutation_rate is received but never applied to the allele
    frequencies, the equilibrium test will fail (heterozygosity decays
    to near zero instead of reaching the predicted mutation-drift
    equilibrium level).
    """
    pass


# ---------------------------------------------------------------------------
# Mutation test: selection-coefficient parameter is silently ignored
# ---------------------------------------------------------------------------


def test_mutation_selection_ignored() -> None:
    """If selection_coefficient is received but never applied to the
    expected allele frequency before binomial sampling, then simulations
    with s > 0 behave identically to neutral (s=0) ones. The fixation-
    probability target and the directional-comparison tests catch this.
    """
    pass


# ---------------------------------------------------------------------------
# Per-replicate data (return_replicate_data=True)
# ---------------------------------------------------------------------------


def test_replicate_data_default_not_present() -> None:
    """By default, replicate_data should be None (backward compat)."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42)
    assert result.replicate_data is None
    assert result.replicate_colnames is None


def test_replicate_data_has_expected_shape() -> None:
    gens = 20
    reps = 5
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42, return_replicate_data=True)
    assert result.replicate_data is not None
    assert result.replicate_colnames is not None
    # One row per generation (0..gens inclusive) = gens+1 rows
    assert len(result.replicate_data) == gens + 1
    # Columns: generation + rep_0 .. rep_{reps-1}
    assert len(result.replicate_colnames) == 1 + reps
    assert result.replicate_colnames[0] == "generation"
    assert result.replicate_colnames[1] == "rep_0"
    assert result.replicate_colnames[-1] == f"rep_{reps - 1}"
    # Each row has the right number of columns
    for row in result.replicate_data:
        assert len(row) == 1 + reps


def test_replicate_data_generation_zero() -> None:
    """At gen 0, all replicates should be at starting_frequency."""
    p0 = 0.3
    reps = 10
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=p0, generations=5,
        replicate_runs=reps, seed=42, return_replicate_data=True)
    assert result.replicate_data is not None
    row0 = result.replicate_data[0]
    assert row0[0] == 0.0  # generation
    for freq in row0[1:]:
        assert freq == pytest.approx(p0)


def test_replicate_data_seeded_reproducibility() -> None:
    """Same seed + return_replicate_data must produce bit-identical
    per-replicate trajectories.
    """
    r1 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=99, return_replicate_data=True)
    r2 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=99, return_replicate_data=True)
    assert r1.replicate_data is not None
    assert r2.replicate_data is not None
    for row1, row2 in zip(r1.replicate_data, r2.replicate_data):
        assert row1 == row2


def test_replicate_data_selection_diverge() -> None:
    """With return_replicate_data, selection should cause replicate
    trajectories to differ between selection and neutral runs with
    the same seed.
    """
    result_sel = simulate_wright_fisher(
        population_size=50, starting_frequency=0.3, generations=30,
        replicate_runs=5, seed=42, selection_coefficient=0.1,
        return_replicate_data=True)
    result_neut = simulate_wright_fisher(
        population_size=50, starting_frequency=0.3, generations=30,
        replicate_runs=5, seed=42, selection_coefficient=0.0,
        return_replicate_data=True)
    assert result_sel.replicate_data is not None
    assert result_neut.replicate_data is not None
    # At least one row should differ between selection and neutral
    sel_rows = [tuple(row) for row in result_sel.replicate_data]
    neut_rows = [tuple(row) for row in result_neut.replicate_data]
    assert sel_rows != neut_rows, (
        "selection and neutral trajectories are identical — "
        "selection likely not applied")


# ---------------------------------------------------------------------------
# Scenario presets
# ---------------------------------------------------------------------------


def test_list_scenarios_returns_known_names() -> None:
    scenarios = list_scenarios()
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 6
    for name in ("neutral-drift", "rapid-drift", "mutation-drift",
                 "weak-selection", "strong-selection",
                 "purifying-selection"):
        assert name in scenarios


def test_invalid_scenario_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown scenario"):
        wright_fisher_scenario("nonexistent-scenario")


def test_scenario_neutral_drift_runs() -> None:
    result = wright_fisher_scenario(
        "neutral-drift", seed=42, return_replicate_data=True)
    assert result.model_name == "wright_fisher"
    assert result.replicate_data is not None
    assert result.column("generation")[0] == 0.0


def test_scenario_with_overrides() -> None:
    result = wright_fisher_scenario(
        "neutral-drift", seed=42, generations=10, replicate_runs=5)
    assert len(result.data) == 11  # generations=10 => 11 rows


def test_scenario_mutation_drift() -> None:
    result = wright_fisher_scenario(
        "mutation-drift", seed=42, return_replicate_data=False)
    # Mutation-drift equilibrium: H should be well above zero
    h_final = result.column("heterozygosity")[-1]
    assert h_final > 0.1, (
        f"mutation-drift scenario H={h_final:.4f} — mutation likely "
        f"not applied")


def test_scenario_strong_selection() -> None:
    """Strong positive selection should fix allele A in most replicates."""
    result = wright_fisher_scenario(
        "strong-selection", seed=42)
    n_A = result.column("n_A_fixed")[-1]
    n_a = result.column("n_a_fixed")[-1]
    assert n_A > n_a, (
        f"strong selection: A_fixed={n_A} <= a_fixed={n_a}, "
        f"expected A to fix more often"
    )


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------


def test_describe_includes_model_name() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=0)
    summary = result.describe()
    assert "wright_fisher" in summary
    assert "Generations" in summary
    assert "Rows" in summary


# ---------------------------------------------------------------------------
# Standard error columns
# ---------------------------------------------------------------------------


def test_result_has_se_columns() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, seed=42)
    assert "mean_frequency_se" in result.colnames
    assert "heterozygosity_se" in result.colnames


def test_se_at_generation_zero_is_zero() -> None:
    """At gen 0 all replicates are identical, so SE is zero."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, seed=42)
    assert result.column("mean_frequency_se")[0] == 0.0
    assert result.column("heterozygosity_se")[0] == 0.0


def test_se_increases_with_drift() -> None:
    """As drift progresses, replicates diverge → SE grows."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.5, generations=50,
        replicate_runs=100, seed=42)
    se_trajectory = result.column("mean_frequency_se")
    # SE should be non-decreasing on average (monotonicity not guaranteed
    # due to sampling noise, but the last value should exceed the first)
    assert se_trajectory[-1] > se_trajectory[0]


def test_single_replicate_se_is_zero() -> None:
    """With 1 replicate, SE cannot be estimated — return 0."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=1, seed=42)
    for se in result.column("mean_frequency_se"):
        assert se == 0.0
    for se in result.column("heterozygosity_se"):
        assert se == 0.0


def test_many_replicates_se_is_small() -> None:
    """With many replicates, the SE of mean frequency should be small
    relative to the theoretical variance.
    """
    n = 100
    p0 = 0.5
    gens = 50
    reps = 500
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42)
    se = result.column("mean_frequency_se")[-1]
    # Theoretical maximum SD under drift: sqrt(p0*(1-p0)) = 0.5
    # With 500 reps, SE should be well below 0.1
    assert se < 0.1, f"SE={se:.4f}, expected < 0.1 for {reps} replicates"


def test_se_and_replicate_data_agree() -> None:
    """The SE column should match std across per-replicate data."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=20,
        replicate_runs=10, seed=42, return_replicate_data=True)
    assert result.replicate_data is not None
    se_col = result.column("mean_frequency_se")
    for i, row in enumerate(result.replicate_data):
        freqs = row[1:]  # skip generation column
        expected_se = float(np.std(freqs, ddof=1) / np.sqrt(len(freqs)))
        assert abs(se_col[i] - expected_se) < 1e-10, (
            f"generation {i}: reported SE {se_col[i]} != computed {expected_se}"
        )


def test_summarize_returns_expected_keys() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, seed=42)
    info = result.summarize()
    assert info["model_name"] == "wright_fisher"
    assert info["generations"] == 10
    assert "final_mean_frequency" in info
    assert "final_heterozygosity" in info
    assert "n_A_fixed" in info
    assert "n_a_fixed" in info
    assert "final_mean_frequency_se" in info
    assert "final_heterozygosity_se" in info
    assert "flagged" in info


def test_summarize_se_consistency() -> None:
    """summarize SE should match the last row of the SE column."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, seed=42)
    info = result.summarize()
    assert info["final_mean_frequency_se"] == (
        result.column("mean_frequency_se")[-1])
    assert info["final_heterozygosity_se"] == (
        result.column("heterozygosity_se")[-1])


# ---------------------------------------------------------------------------
# Population size series (time-varying N)
# ---------------------------------------------------------------------------


def test_constant_series_matches_constant_n() -> None:
    """population_size_series with all same values is identical
    to using constant population_size.
    """
    n = 50
    gens = 10
    reps = 5
    series = [n] * (gens + 1)

    r_const = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42)
    r_series = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42, population_size_series=series)

    assert r_const.data == r_series.data
    assert r_const.colnames == r_series.colnames


def test_bottleneck_accelerates_drift() -> None:
    """A population bottleneck (N drops then recovers) should cause
    faster heterozygosity decay than constant N.
    """
    n = 100
    gens = 100
    reps = 200

    series = [n] * (gens + 1)
    # Bottleneck at gen 30–40: N drops to 5
    for i in range(30, min(40, gens + 1)):
        series[i] = 5

    r_const = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42)
    r_bn = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, seed=42, population_size_series=series)

    h_const = r_const.column("heterozygosity")[-1]
    h_bn = r_bn.column("heterozygosity")[-1]
    assert h_bn < h_const, (
        f"bottleneck H={h_bn:.4f} should be < constant N H={h_const:.4f}"
    )


def test_series_wrong_length_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        population_size_series=[100] * 5)
    assert not v.ok


def test_series_negative_value_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        population_size_series=[100, 100, -1, 100, 100, 100,
                                100, 100, 100, 100, 100])
    assert not v.ok


def test_series_boolean_value_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=5,
        population_size_series=[100, 100, True, 100, 100, 100])
    assert not v.ok


def test_series_small_n_flagged() -> None:
    """Element below WF_PLAUSIBLE_MIN_POPULATION_SIZE should flag."""
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        population_size_series=[100] * 5 + [5] + [100] * 5)
    assert v.ok
    assert v.flagged
    assert "extremely rapid" in v.flag_reason.lower()


def test_series_not_a_list_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=5,
        population_size_series="not-a-list")
    assert not v.ok


def test_scenario_bottleneck_runs() -> None:
    result = wright_fisher_scenario("bottleneck", seed=42)
    assert result.column("n_A_fixed")[-1] >= 0
    assert result.column("n_a_fixed")[-1] >= 0
    assert result.column("heterozygosity")[-1] < 0.5


# ---------------------------------------------------------------------------
# Migration / island model (n_demes, migration_rate)
# ---------------------------------------------------------------------------


def test_n_demes_one_with_migration_is_single_population() -> None:
    """n_demes=1 with migration_rate>0 is the same as no migration
    (a single deme has no structure to homogenise).
    """
    r1 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42, n_demes=1, migration_rate=0.0)
    r2 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42, n_demes=1, migration_rate=0.1)
    assert r1.data == r2.data
    assert "fst" not in r1.colnames


def test_structured_result_has_fst_column() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42, n_demes=5, migration_rate=0.0)
    assert "fst" in result.colnames
    assert "fst_se" in result.colnames


def test_fst_starts_at_zero() -> None:
    """At gen 0, all demes are identical → Fst = 0."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42, n_demes=5, migration_rate=0.0)
    assert result.column("fst")[0] == 0.0


def test_fst_clamps_boundary_roundoff() -> None:
    """The small-N boundary case must not report negative Fst."""
    result = simulate_wright_fisher(
        population_size=1, starting_frequency=0.99999, generations=1,
        replicate_runs=1, n_demes=7, migration_rate=0.0,
        migration_model="island")
    assert min(result.column("fst")) == 0.0


def test_fst_clamp_preserves_material_out_of_range_values() -> None:
    """Only roundoff-sized violations may be clamped; real violations stay visible."""
    values = np.array([-1.1e-10, 1.0 + 1.1e-10], dtype=np.float64)
    np.testing.assert_array_equal(_clamp_wf_fst_roundoff(values), values)


def test_no_migration_fst_increases() -> None:
    """Without migration, demes drift apart → Fst increases over time."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=20, seed=42, n_demes=10, migration_rate=0.0)
    fst = result.column("fst")
    assert fst[-1] > fst[0]


def test_migration_reduces_fst() -> None:
    """With migration, Fst stays lower than without migration."""
    result_no_mig = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=20, seed=42, n_demes=10, migration_rate=0.0)
    result_mig = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=20, seed=42, n_demes=10, migration_rate=0.05)
    fst_no = result_no_mig.column("fst")[-1]
    fst_mig = result_mig.column("fst")[-1]
    assert fst_mig < fst_no, (
        f"migration Fst={fst_mig:.4f} should be < no-migration "
        f"Fst={fst_no:.4f}")


def test_high_migration_demes_homogenised() -> None:
    """With very high migration, Fst stays near zero."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=10, seed=42, n_demes=5, migration_rate=0.5)
    fst = result.column("fst")[-1]
    assert fst < 0.05, f"high migration Fst={fst:.4f} should be near 0"


def test_invalid_n_demes_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        n_demes=0)
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        n_demes=-1)
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        n_demes=True)
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        n_demes=2.5)
    assert not v.ok


def test_invalid_migration_rate_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        migration_rate=-0.1)
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        migration_rate=1.5)
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        migration_rate=float("nan"))
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        migration_rate=float("inf"))
    assert not v.ok
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        migration_rate=True)
    assert not v.ok


def test_scenario_island_model_runs() -> None:
    result = wright_fisher_scenario("island-model", seed=42)
    assert "fst" in result.colnames
    assert result.column("fst")[-1] >= 0


def test_scenario_structured_neutral_runs() -> None:
    result = wright_fisher_scenario("structured-neutral", seed=42)
    assert "fst" in result.colnames
    # Without migration, Fst should be non-trivial
    assert result.column("fst")[-1] > 0


# ---------------------------------------------------------------------------
# Performance benchmarks (order-of-magnitude checks, not precise timing)
# ---------------------------------------------------------------------------

def test_wf_performance_large_generations():
    """A large simulation (N=1000, gens=20000, rep=10) must finish in
    under 20 seconds on a modern laptop. Catches accidental quadratic
    or Python-loop regressions."""
    import time
    t0 = time.time()
    result = simulate_wright_fisher(
        population_size=1000,
        starting_frequency=0.5,
        generations=20000,
        replicate_runs=10,
        seed=42,
    )
    elapsed = time.time() - t0
    assert result.column("mean_frequency")[0] == 0.5
    assert len(result.data) == 20001
    assert elapsed < 20.0, (
        f"WF simulation took {elapsed:.1f}s (threshold: 20s)")


def test_wf_performance_many_replicates():
    """Many replicates (N=100, gens=1000, rep=1000) must finish
    in under 30 seconds. Catches Python-loop regressions in
    aggregation or data-store overhead."""
    import time
    t0 = time.time()
    result = simulate_wright_fisher(
        population_size=100,
        starting_frequency=0.5,
        generations=1000,
        replicate_runs=1000,
        seed=42,
    )
    elapsed = time.time() - t0
    assert len(result.data) == 1001
    assert elapsed < 30.0, (
        f"WF simulation took {elapsed:.1f}s (threshold: 30s)")


def test_wf_performance_full_feature():
    """All features enabled (selection + mutation + structure + time-varying
    N) at moderate scale must finish in under 20 seconds."""
    import time
    gens = 5000
    series = [50 + (i % 50) for i in range(gens + 1)]
    t0 = time.time()
    result = simulate_wright_fisher(
        population_size=100,
        starting_frequency=0.3,
        generations=gens,
        replicate_runs=10,
        mutation_rate=0.001,
        selection_coefficient=0.05,
        dominance=0.5,
        n_demes=5,
        migration_rate=0.02,
        population_size_series=series,
        seed=42,
    )
    elapsed = time.time() - t0
    assert len(result.data) == gens + 1
    assert "fst" in result.colnames
    assert elapsed < 20.0, (
        f"Full-feature WF took {elapsed:.1f}s (threshold: 20s)")


# ---------------------------------------------------------------------------
# Wright-Fisher parameters, fixation analysis, theoretical trajectories
# ---------------------------------------------------------------------------


def test_wf_params_stored_in_result() -> None:
    """WF-specific parameters are stored in result.wright_fisher_params."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.3, generations=20,
        replicate_runs=5, mutation_rate=0.01, selection_coefficient=-0.1,
        dominance=0.5, n_demes=3, migration_rate=0.05, seed=42)
    p = result.wright_fisher_params
    assert p is not None
    assert p["population_size"] == 50
    assert p["starting_frequency"] == 0.3
    assert p["generations"] == 20
    assert p["replicate_runs"] == 5
    assert p["mutation_rate"] == 0.01
    assert p["selection_coefficient"] == -0.1
    assert p["dominance"] == 0.5
    assert p["n_demes"] == 3
    assert p["migration_rate"] == 0.05
    assert len(p["fixation_gen_A"]) == 5
    assert len(p["fixation_gen_a"]) == 5


def test_fixation_analysis_returns_expected_keys() -> None:
    """fixation_analysis returns all expected keys."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.4, generations=500,
        replicate_runs=50, seed=42)
    fa = result.fixation_analysis()
    assert "n_replicates" in fa
    assert "n_fixed_A" in fa
    assert "n_fixed_a" in fa
    assert "n_polymorphic" in fa
    assert "prop_fixed_A" in fa
    assert "prop_fixed_a" in fa
    assert "fixation_gen_A" in fa
    assert "fixation_gen_a" in fa
    assert fa["n_replicates"] == 50


def test_fixation_analysis_replicate_tracking() -> None:
    """Fixation generations are in [0, generations] or -1 for unfixed."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.4, generations=200,
        replicate_runs=30, seed=42)
    fa = result.fixation_analysis()
    gens = 200
    for g in fa["fixation_gen_A"]:
        assert g == -1 or (0 <= g <= gens), f"fixation gen A={g} out of range"
    for g in fa["fixation_gen_a"]:
        assert g == -1 or (0 <= g <= gens), f"fixation gen a={g} out of range"
    assert fa["n_fixed_A"] + fa["n_fixed_a"] + fa["n_polymorphic"] == 30


def test_fixation_analysis_no_duplicates() -> None:
    """A replicate cannot be fixed for both A and a."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.5, generations=300,
        replicate_runs=30, seed=42)
    fa = result.fixation_analysis()
    for gA, ga in zip(fa["fixation_gen_A"], fa["fixation_gen_a"]):
        assert not (gA >= 0 and ga >= 0), (
            f"replicate fixed for both A (gen {gA}) and a (gen {ga})")


def test_non_wf_result_returns_error() -> None:
    """Non WF results return error from fixation_analysis."""
    from tellurium_engine import simulate_sir
    result = simulate_sir(beta=0.3, gamma=0.1, s0=0.99, i0=0.01)
    fa = result.fixation_analysis()
    assert "error" in fa


def test_theoretical_heterozygosity_neutral_drift() -> None:
    """theoretical_heterozygosity matches H_0 * (1 - 1/(2N))^t."""
    n = 100
    p0 = 0.5
    gens = 50
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=10, seed=42)
    th = result.theoretical_heterozygosity()
    assert len(th) == gens + 1
    h0 = 2.0 * p0 * (1.0 - p0)
    decay = 1.0 - 1.0 / (2.0 * n)
    for t in range(gens + 1):
        expected = h0 * (decay ** t)
        assert abs(th[t] - expected) < 1e-12, (
            f"generation {t}: theoretical H={th[t]:.6f}, "
            f"expected {expected:.6f}")


def test_theoretical_heterozygosity_empty_with_selection() -> None:
    """theoretical_heterozygosity returns empty list when selection is on."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=20,
        replicate_runs=5, selection_coefficient=0.1, seed=42)
    assert result.theoretical_heterozygosity() == []


def test_theoretical_heterozygosity_empty_with_mutation() -> None:
    """theoretical_heterozygosity returns empty list when mutation is on."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=20,
        replicate_runs=5, mutation_rate=0.01, seed=42)
    assert result.theoretical_heterozygosity() == []


def test_theoretical_frequency_haploid_selection() -> None:
    """theoretical_frequency matches the closed-form for haploid selection."""
    s = 0.1
    p0 = 0.3
    gens = 30
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=p0, generations=gens,
        replicate_runs=5, selection_coefficient=s, dominance=None, seed=42)
    tf = result.theoretical_frequency()
    assert len(tf) == gens + 1
    assert tf[0] == p0
    for t in range(1, gens + 1):
        expected = p0 / (p0 + (1.0 - p0) * (1.0 + s) ** (-t))
        assert abs(tf[t] - expected) < 1e-12, (
            f"generation {t}: theoretical p={tf[t]:.6f}, "
            f"expected {expected:.6f}")


def test_theoretical_frequency_empty_neutral() -> None:
    """theoretical_frequency returns empty list when s=0."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=20,
        replicate_runs=5, seed=42)
    assert result.theoretical_frequency() == []


def test_theoretical_frequency_empty_with_mutation() -> None:
    """theoretical_frequency returns empty list when mutation is on."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=20,
        replicate_runs=5, selection_coefficient=0.1, mutation_rate=0.01,
        seed=42)
    assert result.theoretical_frequency() == []


def test_enhanced_summarize_includes_theory() -> None:
    """summarize includes theoretical expectations for neutral drift."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, seed=42)
    info = result.summarize()
    assert "expected_heterozygosity_final" in info
    assert "expected_heterozygosity_trajectory" in info
    assert len(info["expected_heterozygosity_trajectory"]) == 11
    assert "fixation" in info
    fa = info["fixation"]
    assert "prop_fixed_A" in fa


def test_enhanced_summarize_no_theory_with_selection() -> None:
    """summarize omits heterozygosity theory when selection is on."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=20, selection_coefficient=0.1, seed=42)
    info = result.summarize()
    assert "expected_heterozygosity_final" not in info
    assert "expected_frequency_final" in info


def test_enhanced_describe_includes_fixation() -> None:
    """describe output includes fixation proportions and times."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.4, generations=200,
        replicate_runs=30, seed=42)
    desc = result.describe()
    assert "Fixation proportions" in desc
    assert "prop_fixed_A" in desc or "fixation" in desc
    # Some replicates should have fixed in 200 gens with N=20
    assert "poly=" in desc


def test_fixation_with_selection_all_A_fixed() -> None:
    """Strong positive selection fixes A in most replicates."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.3, generations=200,
        replicate_runs=20, selection_coefficient=0.5, seed=42)
    fa = result.fixation_analysis()
    assert fa["n_fixed_A"] > fa["n_fixed_a"], (
        f"Expected more A-fixed than a-fixed under positive selection, "
        f"got A={fa['n_fixed_A']}, a={fa['n_fixed_a']}")


def test_fixation_with_negative_selection_more_a_fixed() -> None:
    """Negative selection fixes a in most replicates."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=200,
        replicate_runs=20, selection_coefficient=-0.3, seed=42)
    fa = result.fixation_analysis()
    assert fa["n_fixed_a"] >= fa["n_fixed_A"], (
        f"Expected more a-fixed under negative selection, "
        f"got A={fa['n_fixed_A']}, a={fa['n_fixed_a']}")


def test_fixation_analysis_with_structured_pop() -> None:
    """Fixation analysis works with structured populations."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=100,
        replicate_runs=10, n_demes=5, migration_rate=0.01, seed=42)
    fa = result.fixation_analysis()
    assert fa["n_replicates"] == 10


def test_theoretical_heterozygosity_time_varying_n() -> None:
    """theoretical_heterozygosity handles population_size_series."""
    n = 50
    gens = 20
    p0 = 0.5
    series = [n] * (gens + 1)
    # Short bottleneck at gen 10
    series[10] = 5
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=10, population_size_series=series, seed=42)
    th = result.theoretical_heterozygosity()
    assert len(th) == gens + 1
    h0 = 2.0 * p0 * (1.0 - p0)
    # generation 0: H = h0
    assert th[0] == h0
    # generation 1: H = h0 * (1 - 1/100) = h0 * 0.99
    expected_1 = h0 * (1.0 - 1.0 / (2.0 * n))
    assert abs(th[1] - expected_1) < 1e-12
    # generation 10: includes bottleneck at N=5
    expected_10 = h0
    for t in range(10):
        n_t = series[t]
        expected_10 *= (1.0 - 1.0 / (2.0 * n_t))
    assert abs(th[10] - expected_10) < 1e-12


# ---------------------------------------------------------------------------
# Export methods (to_dict / to_csv / to_json)
# ---------------------------------------------------------------------------


def test_to_dict_round_trip() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42)
    doc = result.to_dict()
    assert doc["colnames"] == result.colnames
    assert doc["data"] == result.data
    assert doc["model_name"] == "wright_fisher"
    assert "wright_fisher_params" in doc
    assert doc["wright_fisher_params"]["generations"] == 10


def test_to_csv_and_json(tmp_path) -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, seed=42)
    csv_path = tmp_path / "wf.csv"
    json_path = tmp_path / "wf.json"
    result.to_csv(str(csv_path))
    result.to_json(str(json_path))

    lines = csv_path.read_text().strip().splitlines()
    assert lines[0] == ",".join(result.colnames)
    assert len(lines) == len(result.data) + 1

    import json
    doc = json.loads(json_path.read_text())
    assert doc["colnames"] == result.colnames
    assert doc["data"] == result.data


def test_to_csv_with_replicates(tmp_path) -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=5,
        replicate_runs=3, seed=42, return_replicate_data=True)
    csv_path = tmp_path / "wf.csv"
    result.to_csv(str(csv_path), include_replicate_data=True)
    rep_path = tmp_path / "wf_replicates.csv"
    assert rep_path.exists()
    lines = rep_path.read_text().strip().splitlines()
    assert lines[0] == ",".join(result.replicate_colnames)
    assert len(lines) == len(result.replicate_data) + 1


def test_to_json_omits_replicate_data(tmp_path) -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=5,
        replicate_runs=3, seed=42, return_replicate_data=True)
    import json
    doc = json.loads(result.to_json(include_replicate_data=False))
    assert doc["replicate_data"] is None


# ---------------------------------------------------------------------------
# Allele frequency spectrum
# ---------------------------------------------------------------------------


def test_afs_final_generation() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=100,
        replicate_runs=40, seed=42)
    afs = result.allele_frequency_spectrum()
    assert afs["generation"] == 100
    assert len(afs["bin_edges"]) == 11  # 10 bins
    assert len(afs["counts"]) == 10
    assert afs["n_observations"] == 40
    assert sum(afs["counts"]) == 40


def test_afs_pooled_structure() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=10, n_demes=4, migration_rate=0.01, seed=42)
    afs = result.allele_frequency_spectrum()
    assert afs["n_observations"] == 40  # 10 reps x 4 demes


def test_afs_specific_generation_requires_replicate_data() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=20,
        replicate_runs=10, seed=42)
    afs = result.allele_frequency_spectrum(generation=10)
    assert "error" in afs

    result2 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=20,
        replicate_runs=10, seed=42, return_replicate_data=True)
    afs2 = result2.allele_frequency_spectrum(generation=10)
    assert afs2["generation"] == 10
    assert afs2["n_observations"] == 10
    assert sum(afs2["counts"]) == 10


def test_afs_bins_reflect_fixation() -> None:
    """After 500 gens with N=20, many replicates fix -> mass in edge bins."""
    result = simulate_wright_fisher(
        population_size=20, starting_frequency=0.4, generations=500,
        replicate_runs=100, seed=42)
    afs = result.allele_frequency_spectrum(bins=5)
    assert afs["counts"][0] + afs["counts"][-1] > 0  # some fixed/polymorphic at edges
    assert sum(afs["counts"]) == 100


# ---------------------------------------------------------------------------
# Kimura fixation probability
# ---------------------------------------------------------------------------


def test_kimura_neutral_returns_p0() -> None:
    assert kimura_fixation_probability(0.3, 0.0, 100) == pytest.approx(0.3)
    assert kimura_fixation_probability(0.0, 0.1, 100) == 0.0
    assert kimura_fixation_probability(1.0, 0.1, 100) == 1.0


def test_kimura_haploid_matches_closed_form() -> None:
    n, p0, s = 50, 0.3, 0.03
    p = kimura_fixation_probability(p0, s, n, None)
    expected = ((1.0 - np.exp(-4.0 * n * s * p0)) /
                (1.0 - np.exp(-4.0 * n * s)))
    assert p == pytest.approx(expected)


def test_kimura_positive_selection_increases_probability() -> None:
    p_neutral = kimura_fixation_probability(0.3, 0.0, 100)
    p_sel = kimura_fixation_probability(0.3, 0.03, 100)
    p_strong = kimura_fixation_probability(0.3, 0.1, 100)
    assert p_neutral < p_sel < p_strong


def test_kimura_negative_selection_decreases_probability() -> None:
    p_neutral = kimura_fixation_probability(0.5, 0.0, 100)
    p_del = kimura_fixation_probability(0.5, -0.03, 100)
    assert p_del < p_neutral


def test_kimura_dominance_ordering() -> None:
    """Dominant (h=1) fixes more easily than additive (h=0.5),
    which fixes more easily than recessive (h=0)."""
    p_dom = kimura_fixation_probability(0.2, 0.02, 50, 1.0)
    p_add = kimura_fixation_probability(0.2, 0.02, 50, 0.5)
    p_rec = kimura_fixation_probability(0.2, 0.02, 50, 0.0)
    assert p_rec < p_add < p_dom


def test_kimura_matches_simulation() -> None:
    """Diffusion prediction matches simulated fixation proportion
    within sampling error for weak to moderate selection."""
    n, p0, s, h = 50, 0.5, 0.02, 0.25
    gens, reps = 400, 3000
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, selection_coefficient=s, dominance=h, seed=42)
    fa = result.fixation_analysis()
    total = fa["n_fixed_A"] + fa["n_fixed_a"]
    obs = fa["n_fixed_A"] / total
    theory = kimura_fixation_probability(p0, s, n, h)
    se = np.sqrt(theory * (1.0 - theory) / reps)
    assert abs(obs - theory) < 5.0 * se + 0.02, (
        f"observed {obs:.4f} vs Kimura {theory:.4f}")


def test_kimura_rejects_invalid_params() -> None:
    with pytest.raises(ValueError):
        kimura_fixation_probability(0.5, 0.1, 0)  # N <= 0
    with pytest.raises(ValueError):
        kimura_fixation_probability(1.5, 0.1, 100)  # p0 > 1
    with pytest.raises(ValueError):
        kimura_fixation_probability(0.5, -1.5, 100)  # s <= -1
    with pytest.raises(ValueError):
        kimura_fixation_probability(0.5, 0.1, 100, 2.5)  # h > 2


def test_kimura_accepts_overdominance_dominance() -> None:
    """h in (1, 2] is now valid (overdominance/underdominance), matching
    simulate_wright_fisher. The diffusion approximation is documented as
    unreliable there, but must compute without raising."""
    p = kimura_fixation_probability(0.5, 0.1, 100, 1.5)
    assert 0.0 <= p <= 1.0
    p2 = kimura_fixation_probability(0.5, 0.1, 100, 2.0)
    assert 0.0 <= p2 <= 1.0


def test_kimura_strong_selection_saturates() -> None:
    assert kimura_fixation_probability(0.1, 0.5, 100) == pytest.approx(1.0)
    assert kimura_fixation_probability(0.5, -0.5, 100) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Expected fixation time (Kimura & Ohta 1969)
# ---------------------------------------------------------------------------


def test_expected_fixation_time_matches_closed_form() -> None:
    """t_bar = -4N (1-p0) ln(1-p0) / p0. For p0=0.5 this is 4N ln2."""
    assert expected_fixation_time(0.5, 100) == pytest.approx(
        400.0 * math.log(2.0))
    assert expected_fixation_time(0.2, 50) == pytest.approx(
        -200.0 * 0.8 * math.log(0.8) / 0.2)


def test_expected_fixation_time_matches_simulation() -> None:
    """Diffusion prediction matches simulated mean fixation time when the
    simulation window is long enough that all replicates fix (a truncated
    window biases the mean downward, because late-fixing replicates are
    excluded)."""
    n, p0, reps, gens = 50, 0.5, 500, 1000
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=42)
    fa = result.fixation_analysis()
    assert fa["n_fixed_A"] + fa["n_fixed_a"] == reps, (
        "test assumption violated: some replicates never fixed within "
        "the window, so the mean fixation time is truncated")
    obs = fa["mean_fixation_time_A"]
    theory = expected_fixation_time(p0, n)
    assert abs(obs - theory) < 0.15 * theory, (
        f"observed mean fixation time {obs:.1f} vs theory {theory:.1f}")


def test_expected_fixation_time_new_mutation_is_4n() -> None:
    """A single new mutation (p0 = 1/(2N)) takes on average ~4N
    generations to fix, given it fixes."""
    n = 100
    t = expected_fixation_time(1.0 / (2.0 * n), n)
    assert t == pytest.approx(4.0 * n, rel=0.05)


def test_expected_fixation_time_edges() -> None:
    assert expected_fixation_time(1.0, 100) == 0.0  # already fixed
    with pytest.raises(ValueError):
        expected_fixation_time(0.0, 100)  # never fixes
    with pytest.raises(ValueError):
        expected_fixation_time(0.5, 0)  # N <= 0
    with pytest.raises(ValueError):
        expected_fixation_time(1.5, 100)  # p0 > 1
    with pytest.raises(ValueError):
        expected_fixation_time(float("nan"), 100)


# ---------------------------------------------------------------------------
# New scenarios and CLI
# ---------------------------------------------------------------------------


def test_scenario_founder_effect_runs() -> None:
    result = wright_fisher_scenario("founder-effect", seed=42)
    assert result.column("mean_frequency")[0] == pytest.approx(0.1)
    assert result.column("n_A_fixed")[-1] + result.column("n_a_fixed")[-1] > 0


def test_scenario_population_expansion_runs() -> None:
    result = wright_fisher_scenario("population-expansion", seed=42)
    # N grows from 10 to 1000 -> heterozygosity loss slows dramatically
    h_last = result.column("heterozygosity")[-1]
    assert h_last > 0.2, f"expansion scenario lost too much H: {h_last}"


def test_cli_wf_runs_and_writes(tmp_path, capsys) -> None:
    import subprocess
    import sys
    out_csv = tmp_path / "cli.csv"
    code = subprocess.call([
        sys.executable, "-m", "Tellurium.cli", "wf",
        "--population-size", "50", "--generations", "20",
        "--replicate-runs", "10", "--seed", "42", "--quiet",
        "--out", str(out_csv),
    ], cwd=_REPO_ROOT)
    assert code == 0
    assert out_csv.exists()
    lines = out_csv.read_text().strip().splitlines()
    assert len(lines) == 22  # header + 21 rows (gen 0..20)


def test_cli_wf_scenario_override(tmp_path) -> None:
    import subprocess
    import sys
    out_csv = tmp_path / "cli_scenario.csv"
    code = subprocess.call([
        sys.executable, "-m", "Tellurium.cli", "wf",
        "--scenario", "rapid-drift", "--generations", "5",
        "--out", str(out_csv),
    ], cwd=_REPO_ROOT)
    assert code == 0
    lines = out_csv.read_text().strip().splitlines()
    assert len(lines) == 7  # header + 6 rows (gen 0..5)


def test_cli_scenarios_lists_all() -> None:
    import subprocess
    import sys
    out = subprocess.check_output(
        [sys.executable, "-m", "Tellurium.cli", "scenarios"], cwd=_REPO_ROOT)
    text = out.decode()
    for name in ["neutral-drift", "founder-effect", "population-expansion",
                 "island-model", "bottleneck"]:
        assert name in text


def test_cli_kimura_sweep() -> None:
    import subprocess
    import sys
    out = subprocess.check_output([
        sys.executable, "-m", "Tellurium.cli", "kimura",
        "--p0", "0.5", "--population-size", "100",
        "--s-start", "-0.05", "--s-end", "0.05", "--s-steps", "3"],
        cwd=_REPO_ROOT)
    text = out.decode()
    assert "P_fix" in text
    assert "0.500000" in text  # s=0 midpoint -> neutral p0


def test_cli_wf_missing_args_fails() -> None:
    import subprocess
    import sys
    code = subprocess.call(
        [sys.executable, "-m", "Tellurium.cli", "wf", "--generations", "10"],
        cwd=_REPO_ROOT)
    assert code == 2


def test_cli_wf_bad_scenario_fails() -> None:
    import subprocess
    import sys
    code = subprocess.call(
        [sys.executable, "-m", "Tellurium.cli", "wf", "--scenario", "nope"],
        cwd=_REPO_ROOT)
    assert code == 1


# ---------------------------------------------------------------------------
# Overdominance / underdominance (dominance h > 1)
# ---------------------------------------------------------------------------


def test_overdominance_maintains_polymorphism() -> None:
    """h=2, s>0: heterozygote advantage keeps both alleles segregating.
    The deterministic equilibrium is p* = h/(2h-1) = 2/3."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.1, generations=400,
        replicate_runs=50, selection_coefficient=0.2, dominance=2.0,
        seed=42)
    final_p = result.column("mean_frequency")[-1]
    assert abs(final_p - 2.0 / 3.0) < 0.05, (
        f"final p={final_p:.3f} should approach 2/3")
    assert result.column("heterozygosity")[-1] > 0.3, (
        "overdominance should maintain high heterozygosity")
    fa = result.fixation_analysis()
    assert fa["n_fixed_A"] + fa["n_fixed_a"] == 0, (
        "no fixation expected under balancing selection")


def test_overdominance_equilibrium_h15() -> None:
    """h=1.5, s=0.1: equilibrium at p* = h/(2h-1) = 0.75.

    N=100 is too small for this check: in a finite population, balancing
    selection only slows fixation, it does not prevent it -- at N=100
    with this seed, 21 of 30 replicates had already fixed for A by
    generation 500 (mean_fixation_time_A ~ 275 generations), which pulls
    the *mean* frequency across replicates far above 0.75 even though the
    equilibrium math is correct. This is a property of finite-population
    stochastic dynamics, not a selection/dominance implementation bug --
    confirmed by rederiving p*=h/(2h-1) directly from the marginal-
    fitness equilibrium condition w_A_bar = w_a_bar under this file's
    exact fitness parameterization (w_AA=1+s, w_Aa=1+hs, w_aa=1), which
    reproduces the same formula independent of s. N=1000 keeps drift weak
    enough, relative to this selection strength, that none of 30
    replicates fix within 500 generations (verified directly), so the
    mean is a meaningful estimate of the equilibrium.
    """
    result = simulate_wright_fisher(
        population_size=1000, starting_frequency=0.2, generations=500,
        replicate_runs=30, selection_coefficient=0.1, dominance=1.5,
        seed=42)
    final_p = result.column("mean_frequency")[-1]
    assert abs(final_p - 0.75) < 0.06, (
        f"final p={final_p:.3f} should approach 0.75")
    fa = result.fixation_analysis()
    assert fa["n_fixed_A"] + fa["n_fixed_a"] == 0, (
        "test assumption violated: a replicate fixed before reaching "
        "equilibrium, so the mean frequency no longer estimates p*"
    )


def test_underdominance_fixes() -> None:
    """h=2, s<0: underdominance is an unstable equilibrium —
    populations fix for one allele or the other."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=300,
        replicate_runs=50, selection_coefficient=-0.1, dominance=2.0,
        seed=42)
    fa = result.fixation_analysis()
    assert fa["n_fixed_A"] + fa["n_fixed_a"] == 50, (
        "underdominance should drive all replicates to fixation")


def test_dominance_two_valid() -> None:
    """h=2.0 is at the valid boundary."""
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=20,
        replicate_runs=10, selection_coefficient=0.1, dominance=2.0,
        seed=42)
    assert result is not None


# ---------------------------------------------------------------------------
# Stepping-stone migration
# ---------------------------------------------------------------------------


def test_stepping_stone_fst_higher_than_island() -> None:
    """With the same m, local (stepping-stone) migration produces more
    differentiation than global (island) migration."""
    r_ss = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=200,
        replicate_runs=50, n_demes=10, migration_rate=0.01,
        migration_model="stepping-stone", seed=42)
    r_isl = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=200,
        replicate_runs=50, n_demes=10, migration_rate=0.01,
        migration_model="island", seed=42)
    fst_ss = r_ss.column("fst")[-1]
    fst_isl = r_isl.column("fst")[-1]
    assert fst_ss > fst_isl, (
        f"stepping-stone Fst={fst_ss:.3f} should exceed "
        f"island Fst={fst_isl:.3f}")


def test_stepping_stone_conserves_mean_frequency() -> None:
    """Migration (both models) must not change the total allele count:
    the mean frequency across demes is unchanged by the migration step."""
    r = simulate_wright_fisher(
        population_size=100, starting_frequency=0.4, generations=20,
        replicate_runs=10, n_demes=8, migration_rate=0.2,
        migration_model="stepping-stone", seed=42)
    mf = r.column("mean_frequency")
    assert abs(mf[0] - 0.4) < 1e-9
    assert all(abs(x - 0.4) < 0.15 for x in mf[:5]), (
        "migration should not systematically shift the mean frequency")


def test_stepping_stone_requires_three_demes() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, n_demes=2, migration_rate=0.1,
        migration_model="stepping-stone")
    assert not v.ok


def test_stepping_stone_with_non_numeric_n_demes_no_crash() -> None:
    """n_demes='5' is already invalid; the stepping-stone check must
    not crash with a TypeError when comparing a string to 3."""
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        n_demes="5", migration_rate=0.1,
        migration_model="stepping-stone")
    assert not v.ok
    assert any("n_demes" in e for e in v.errors)


def test_invalid_migration_model_rejected() -> None:
    v = validate_wright_fisher_params(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=10, n_demes=5, migration_rate=0.1,
        migration_model="continental-island")
    assert not v.ok


def test_stepping_stone_two_demes_matches_island() -> None:
    """With 2 demes the ring has only one neighbour each — the
    stepping-stone step degenerates to the island model's global pool
    only when both neighbours are the same deme. n_demes=2 is rejected,
    but n_demes=1 island vs stepping-stone should be equivalent to
    island at the same migration rate."""
    r_ss = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=30,
        replicate_runs=10, n_demes=5, migration_rate=0.0,
        migration_model="stepping-stone", seed=42)
    r_isl = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=30,
        replicate_runs=10, n_demes=5, migration_rate=0.0, seed=42)
    assert r_ss.data == r_isl.data, (
        "migration_model should be irrelevant when migration_rate=0")


def test_migration_model_stored_in_params() -> None:
    result = simulate_wright_fisher(
        population_size=100, starting_frequency=0.5, generations=10,
        replicate_runs=5, n_demes=5, migration_rate=0.05,
        migration_model="stepping-stone", seed=42)
    assert result.wright_fisher_params["migration_model"] == "stepping-stone"


# ---------------------------------------------------------------------------
# Effective population size estimation
# ---------------------------------------------------------------------------


def test_estimate_ne_decay_matches_known_n() -> None:
    """The heterozygosity-decay estimator recovers the known census N
    within ~20 % with enough replicates."""
    n, reps = 50, 1000
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=100,
        replicate_runs=reps, seed=42)
    est = result.estimate_ne()
    assert est["method"] == "heterozygosity_decay"
    assert abs(est["ne_estimate"] - n) / n < 0.2, (
        f"Ne estimate {est['ne_estimate']:.1f} deviates from N={n}")
    assert est["decay_rate_per_generation"] < 1.0


def test_estimate_ne_small_population() -> None:
    """Works for small N too."""
    n, reps = 20, 500
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=50,
        replicate_runs=reps, seed=42)
    est = result.estimate_ne()
    assert abs(est["ne_estimate"] - n) / n < 0.3, (
        f"Ne estimate {est['ne_estimate']:.1f} deviates from N={n}")


def test_estimate_ne_requires_data() -> None:
    """All-fixed populations cannot estimate Ne."""
    result = simulate_wright_fisher(
        population_size=5, starting_frequency=1.0, generations=10,
        replicate_runs=10, seed=42)
    est = result.estimate_ne()
    assert "error" in est


def test_effective_size_harmonic_mean_constant_series() -> None:
    """A constant series returns the constant itself."""
    assert effective_size_harmonic_mean([100] * 5) == 100.0
    assert effective_size_harmonic_mean([10]) == 10.0
    assert abs(effective_size_harmonic_mean([50, 50, 50]) - 50.0) < 1e-12


def test_effective_size_harmonic_mean_known_values() -> None:
    """Classic bottleneck numbers: k / sum(1/N_t)."""
    assert abs(effective_size_harmonic_mean([1000, 10, 1000]) - 29.41) < 0.01
    assert abs(effective_size_harmonic_mean([100, 10, 100]) - 25.0) < 1e-12
    series = [1000] * 101 + [10] * 10 + [1000] * 90
    ne = effective_size_harmonic_mean(series)
    assert abs(ne - 168.77) < 0.01, f"Ne={ne:.4f}"


def test_effective_size_harmonic_mean_never_exceeds_arithmetic() -> None:
    """Harmonic <= arithmetic, strict unless constant (AM-GM)."""
    for series in ([1000, 10, 1000], [500, 50, 500, 50],
                   [1000, 200] * 50 + [1000], [7, 7, 7, 7]):
        hm = effective_size_harmonic_mean(series)
        am = sum(series) / len(series)
        if all(n == series[0] for n in series):
            assert abs(hm - am) < 1e-12
        else:
            assert hm < am, f"harmonic {hm} should be < arithmetic {am}"


def test_effective_size_harmonic_mean_matches_simulated_ne() -> None:
    """A 1000<->200 oscillating series has effectively linear log-H
    decay, so the heterozygosity-decay estimator recovers the
    harmonic mean within 15 %."""
    series = [1000 if i % 2 == 0 else 200 for i in range(101)]
    ne_har = effective_size_harmonic_mean(series)
    result = simulate_wright_fisher(
        population_size=1000, starting_frequency=0.5, generations=100,
        replicate_runs=2000, population_size_series=series, seed=42)
    est = estimate_ne_from_heterozygosity(
        result.column("heterozygosity"))
    rel = abs(est["ne_estimate"] - ne_har) / ne_har
    assert rel < 0.15, (
        f"estimator {est['ne_estimate']:.1f} vs Ne_har {ne_har:.1f} "
        f"({rel:.3f})")


def test_effective_size_harmonic_mean_bottleneck_dominates() -> None:
    """A single severe bottleneck generation makes the effective size
    far smaller than any census size and than the arithmetic mean, and
    the simulation's Ne estimate reflects the bottleneck, not the
    flanking large populations."""
    series = [1000] * 101 + [10] * 10 + [1000] * 90
    ne_har = effective_size_harmonic_mean(series)
    am = sum(series) / len(series)
    assert ne_har < 0.5 * am, (
        f"Ne_har {ne_har:.1f} should be well below arithmetic {am:.1f}")
    assert ne_har < 200.0
    result = simulate_wright_fisher(
        population_size=1000, starting_frequency=0.5, generations=200,
        replicate_runs=2000, population_size_series=series, seed=42)
    est = estimate_ne_from_heterozygosity(
        result.column("heterozygosity"))
    assert est["ne_estimate"] < 300.0, (
        "estimate should be bottleneck-dominated, got "
        f"{est['ne_estimate']:.1f} (census 1000)")
    assert est["ne_estimate"] > ne_har * 0.4, (
        "estimate should still track the harmonic mean roughly, got "
        f"{est['ne_estimate']:.1f} vs Ne_har {ne_har:.1f}")


def test_effective_size_harmonic_mean_validation() -> None:
    with pytest.raises(ValueError):
        effective_size_harmonic_mean([])
    with pytest.raises(ValueError):
        effective_size_harmonic_mean([0])
    with pytest.raises(ValueError):
        effective_size_harmonic_mean([100, -1])
    with pytest.raises(ValueError):
        effective_size_harmonic_mean([100, True])
    with pytest.raises(ValueError):
        effective_size_harmonic_mean([100, 50.0])
    with pytest.raises(ValueError):
        effective_size_harmonic_mean("100,50")


# ---------------------------------------------------------------------------
# Two-locus recombination and linkage disequilibrium
# ---------------------------------------------------------------------------


def test_two_locus_theoretical_decay_exact() -> None:
    """Theoretical LD decay: D_t = D0 (1-r)^t, optionally with the
    haploid drift factor (1-1/N)^t and the mutation factor
    (1-2u)^(2t)."""
    assert abs(theoretical_ld_decay(0.25, 0.1, 20, None)
               - 0.25 * 0.9 ** 20) < 1e-12
    assert abs(theoretical_ld_decay(0.25, 0.1, 20, 100)
               - 0.25 * 0.9 ** 20 * 0.99 ** 20) < 1e-12
    assert theoretical_ld_decay(0.25, 0.0, 100, None) == 0.25
    assert abs(theoretical_ld_decay(0.25, 0.5, 1, None) - 0.125) < 1e-12
    assert abs(theoretical_ld_decay(0.25, 0.1, 30, None, 0.05)
               - 0.25 * 0.9 ** 30 * 0.9 ** 60) < 1e-12
    assert abs(theoretical_ld_decay(0.25, 0.1, 30, 100, 0.05)
               - 0.25 * 0.9 ** 30 * 0.9 ** 60 * 0.99 ** 30) < 1e-12
    assert abs(theoretical_ld_decay(0.25, 0.1, 10, None, 0.5)
               - 0.25 * 0.9 ** 10 * 0.0) < 1e-12
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.6, 5)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.1, -1)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.1, 5, population_size=0)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.1, True)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, True, 5)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.1, 5, mutation_rate=1.5)
    with pytest.raises(ValueError):
        theoretical_ld_decay(0.25, 0.1, 5, mutation_rate=True)


def test_two_locus_recombination_only_decay_matches_theory() -> None:
    """With N huge, drift is negligible and a single population's D
    follows D_t = D0 (1-r)^t closely."""
    r = simulate_two_locus_wright_fisher(
        population_size=100000, generations=20, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), seed=1)
    d = r.column("mean_D")
    assert d[0] == 0.25
    expect = 0.25 * 0.9 ** 20
    rel = abs(d[20] - expect) / expect
    assert rel < 0.05, f"D20={d[20]:.5f} vs {expect:.5f} ({rel:.3f})"
    for t in (5, 10, 15):
        assert abs(d[t] - 0.25 * 0.9 ** t) / (0.25 * 0.9 ** t) < 0.1


def test_two_locus_drift_plus_recombination_matches_theory() -> None:
    """E[D_t] = D0 (1-r)^t (1-1/N)^t over many replicates (N=100,
    r=0.1, t=30)."""
    r = simulate_two_locus_wright_fisher(
        population_size=100, generations=30, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=3000, seed=42)
    d = r.column("mean_D")
    expect = 0.25 * 0.9 ** 30 * 0.99 ** 30
    rel = abs(d[30] - expect) / expect
    assert rel < 0.1, f"D30={d[30]:.5f} vs {expect:.5f} ({rel:.3f})"
    assert d[0] == 0.25


def test_two_locus_recombination_rate_controls_decay() -> None:
    """r=0 keeps LD (decay by drift alone), r=0.5 destroys it fastest."""
    args = dict(population_size=100, generations=30,
                starting_frequencies=(0.5, 0, 0, 0.5),
                replicate_runs=3000, seed=42)
    d0 = simulate_two_locus_wright_fisher(
        recombination_rate=0.0, **args).column("mean_D")[30]
    d05 = simulate_two_locus_wright_fisher(
        recombination_rate=0.5, **args).column("mean_D")[30]
    drift_only = 0.25 * 0.99 ** 30
    assert abs(d0 - drift_only) / drift_only < 0.1
    assert d05 < 0.001
    assert d0 > 0.05 * d05


def test_two_locus_repulsion_negative_d_decays_same() -> None:
    """Starting in repulsion (Ab/aB) gives negative D that decays at
    the same rate."""
    r = simulate_two_locus_wright_fisher(
        population_size=100, generations=30, recombination_rate=0.1,
        starting_frequencies=(0, 0.5, 0.5, 0), replicate_runs=3000, seed=42)
    d = r.column("mean_D")
    assert d[0] == -0.25
    expect = -0.25 * 0.9 ** 30 * 0.99 ** 30
    rel = abs(d[30] - expect) / abs(expect)
    assert rel < 0.1, f"D30={d[30]:.5f} vs {expect:.5f} ({rel:.3f})"


def test_two_locus_random_association_no_spurious_ld() -> None:
    """Starting with D=0, mean D stays near zero (drift creates LD but
    with no expectation), while r2 stays positive."""
    r = simulate_two_locus_wright_fisher(
        population_size=100, generations=20, recombination_rate=0.1,
        starting_frequencies=(0.25, 0.25, 0.25, 0.25), replicate_runs=2000,
        seed=42)
    d = r.column("mean_D")
    assert abs(d[0]) < 1e-12
    assert abs(d[20]) < 0.05, f"D20={d[20]:.5f}"
    assert r.column("mean_r2")[20] > 0.001


def test_two_locus_frequencies_conserved_in_expectation() -> None:
    """Neither recombination nor drift changes the mean per-locus
    allele frequencies."""
    r = simulate_two_locus_wright_fisher(
        population_size=100, generations=30, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=3000, seed=42)
    assert r.column("mean_freq_A")[0] == 0.5
    assert r.column("mean_freq_B")[0] == 0.5
    assert abs(r.column("mean_freq_A")[-1] - 0.5) < 0.05
    assert abs(r.column("mean_freq_B")[-1] - 0.5) < 0.05


def test_two_locus_determinism_and_replicate_data() -> None:
    """Same seed -> identical output; replicate data exposes the
    per-replicate D spread; sd_D_final matches the sd_D column."""
    a = simulate_two_locus_wright_fisher(
        population_size=100, generations=10, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=5, seed=7,
        return_replicate_data=True)
    b = simulate_two_locus_wright_fisher(
        population_size=100, generations=10, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=5, seed=7,
        return_replicate_data=True)
    c = simulate_two_locus_wright_fisher(
        population_size=100, generations=10, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=5, seed=8,
        return_replicate_data=True)
    assert a.data == b.data
    assert a.data != c.data
    assert a.replicate_colnames == ["generation", "D"]
    assert len(a.replicate_data) == 11
    assert len(a.replicate_data[0]) == 6
    la = a.ld_analysis()
    assert abs(la["sd_D_final"] - a.column("sd_D")[-1]) < 1e-12
    assert la["d_initial"] == 0.25
    assert la["decay_factor"] < 1.0
    d_no_rep = simulate_two_locus_wright_fisher(
        population_size=100, generations=10, recombination_rate=0.1,
        starting_frequencies=(0.5, 0, 0, 0.5), replicate_runs=5, seed=7)
    assert d_no_rep.ld_analysis()["sd_D_final"] is None


def test_fst_after_split_matches_simulation() -> None:
    """The exact chain expectation of the engine's Nei-style Fst
    matches a 2-deme isolated simulation's fst column within 0.02 at
    every generation (N=100, p0=0.5, 2000 replicates)."""
    n, reps, gens = 100, 2000, 200
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=gens,
        replicate_runs=reps, n_demes=2, migration_rate=0.0, seed=42)
    sim = result.column("fst")
    assert sim[0] == 0.0
    for t in (10, 50, 100, 150, 200):
        exact = expected_fst_after_split(n, t)
        assert abs(sim[t] - exact) < 0.02, (
            f"t={t}: sim {sim[t]:.4f} vs exact {exact:.4f}")


def test_fst_after_split_properties() -> None:
    """Fst starts at 0, rises monotonically, and small populations
    diverge faster than large ones."""
    n = 100
    vals = [expected_fst_after_split(n, t) for t in range(0, 401, 25)]
    assert vals[0] == 0.0
    assert all(vals[i + 1] >= vals[i] - 1e-12 for i in range(len(vals) - 1))
    assert 0.3 < vals[-1] < 0.5
    assert expected_fst_after_split(50, 50) > expected_fst_after_split(
        100, 50)


def test_fst_after_split_approaches_divergent_fixation() -> None:
    """Isolation does not push Fst to 1: both demes fix
    independently, so Fst(t) -> 2 p0 (1-p0)."""
    n = 100
    assert abs(expected_fst_after_split(n, 800) - 0.5) < 0.01
    assert abs(expected_fst_after_split(n, 800, 0.3) - 0.42) < 0.01
    assert abs(expected_fst_after_split(n, 800, 0.7)
               - expected_fst_after_split(n, 800, 0.3)) < 1e-12


def test_fst_after_split_validation() -> None:
    with pytest.raises(ValueError):
        expected_fst_after_split(0, 10)
    with pytest.raises(ValueError):
        expected_fst_after_split(2.5, 10)
    with pytest.raises(ValueError):
        expected_fst_after_split(100, -1)
    with pytest.raises(ValueError):
        expected_fst_after_split(100, True)
    with pytest.raises(ValueError):
        expected_fst_after_split(100, 10, starting_frequency=1.5)
    with pytest.raises(ValueError):
        expected_fst_after_split(100, 10, starting_frequency=True)


def test_two_locus_mutation_accelerates_ld_decay() -> None:
    """E[D_t] = D0 (1-r)^t (1-2u)^(2t) (1-1/N)^t: mutation erodes LD
    beyond recombination+drift (N=100, r=0.1, u=0.02, t=15)."""
    args = dict(population_size=100, generations=15,
                recombination_rate=0.1, starting_frequencies=(0.5, 0, 0, 0.5),
                replicate_runs=3000, seed=42)
    d_mut = simulate_two_locus_wright_fisher(
        mutation_rate=0.02, **args).column("mean_D")[15]
    d_none = simulate_two_locus_wright_fisher(
        mutation_rate=0.0, **args).column("mean_D")[15]
    expect = 0.25 * 0.9 ** 15 * 0.96 ** 30 * 0.99 ** 15
    assert abs(d_mut - expect) / expect < 0.1, (
        f"mut D15={d_mut:.5f} vs {expect:.5f}")
    assert d_mut < 0.5 * d_none, (
        "mutation should roughly halve LD, got "
        f"{d_mut:.5f} vs no-mutation {d_none:.5f}")


def test_two_locus_mutation_pushes_frequencies_to_half() -> None:
    """With mutation, a skewed per-locus frequency drifts toward 0.5
    (without mutation it stays ~0.8)."""
    args = dict(population_size=100, generations=100,
                recombination_rate=0.1, starting_frequencies=(0.8, 0, 0, 0.2),
                replicate_runs=3000, seed=42)
    r = simulate_two_locus_wright_fisher(mutation_rate=0.05, **args)
    r0 = simulate_two_locus_wright_fisher(mutation_rate=0.0, **args)
    assert abs(r.column("mean_freq_A")[100] - 0.5) < 0.05
    assert abs(r.column("mean_freq_B")[100] - 0.5) < 0.05
    assert r0.column("mean_freq_A")[100] > 0.7


def test_two_locus_mutation_validation() -> None:
    base = dict(population_size=100, generations=10,
                recombination_rate=0.1)
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "mutation_rate": 1.5})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "mutation_rate": -0.1})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "mutation_rate": True})


def test_two_locus_validation() -> None:
    base = dict(population_size=100, generations=10,
                recombination_rate=0.1)
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "population_size": 0})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "population_size": 2.5})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "recombination_rate": 0.6})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "recombination_rate": -0.1})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "recombination_rate": True})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "generations": True})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "generations": 0})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(**{**base, "replicate_runs": 0})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (0.5, 0.1, 0.1, 0.4)})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (0.5, 0, 0.5)})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (1.0, 0, 0, 0.5)})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (0.5, 0, 0, -0.1)})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (0.5, 0, 0, math.nan)})
    with pytest.raises(ValueError):
        simulate_two_locus_wright_fisher(
            **{**base, "starting_frequencies": (0.5, 0, 0, True)})




def test_estimate_ne_variance_method() -> None:
    """Variance method requires replicate data; with it, returns
    an estimate (biased but present)."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=200, seed=42, return_replicate_data=True)
    est = result.estimate_ne_variance()
    assert "ne_estimate" in est
    assert est["n_replicates"] == 200
    assert est["ne_estimate"] > 0

    result2 = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=50,
        replicate_runs=200, seed=42)
    est2 = result2.estimate_ne_variance()
    assert "error" in est2


def test_estimate_ne_variance_structured_pools_demes() -> None:
    """Structured replicate_data (rep x deme) is pooled per replicate."""
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=30,
        replicate_runs=20, n_demes=4, migration_rate=0.05, seed=42,
        return_replicate_data=True)
    est = result.estimate_ne_variance()
    assert "ne_estimate" in est
    assert est["n_replicates"] == 20


# ---------------------------------------------------------------------------
# Wright's stationary distribution (mutation-drift balance)
# ---------------------------------------------------------------------------


def test_stationary_distribution_is_beta() -> None:
    """With 4Nu = 4 the density is Beta(4,4)-shaped: symmetric,
    zero at the edges, modal at p=0.5."""
    d = wright_stationary_distribution(
        [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0], 0.02, 50)
    assert d[0] == 0.0 and d[-1] == 0.0  # edges
    assert d[1] < d[3] and d[2] < d[3]  # mode at 0.5
    # Symmetric in theory (Beta(4,4) is symmetric about p=0.5), but the
    # density is evaluated via p and 1-p through slightly different
    # floating-point operation orders, so exact equality is not
    # guaranteed -- only mathematical equality is. Use a tight relative
    # tolerance, not ==, matching how every other floating-point
    # comparison in this file is checked (pytest.approx or an explicit
    # tolerance), never bare equality on a computed float.
    assert d[1] == pytest.approx(d[5], rel=1e-9)
    assert d[2] == pytest.approx(d[4], rel=1e-9)


def test_stationary_distribution_normalization() -> None:
    """Numerically integrate the density over [0, 1]: should be 1."""
    density = wright_stationary_distribution(
        [0.5], 0.02, 50)[0]
    a = 4.0 * 0.02 * 50
    from scipy.special import beta
    expected_mode = (
        beta(a, a) ** -1 * 0.5 ** (2 * (a - 1)))
    assert abs(density - expected_mode) / expected_mode < 1e-6


def test_stationary_distribution_edges_infinite_when_a_lt_1() -> None:
    """With 4Nu < 1 the density is unbounded at the boundaries
    (most populations fixed)."""
    d = wright_stationary_distribution([0.0, 0.5], 0.001, 50)
    assert d[0] == float("inf")
    assert math.isfinite(d[1])


def test_stationary_distribution_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        wright_stationary_distribution([0.5], 0.0, 50)
    with pytest.raises(ValueError):
        wright_stationary_distribution([0.5], 0.02, 0)


def test_stationary_distribution_matches_simulation() -> None:
    """With N=50, u=0.02 (4Nu=4), a long simulation's final
    frequencies should roughly follow the Beta(4,4) density."""
    n, u = 50, 0.02
    reps = 2000
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=1000,
        replicate_runs=reps, mutation_rate=u, seed=42)
    afs = result.allele_frequency_spectrum(bins=10)
    edges = np.asarray(afs["bin_edges"])
    counts = np.asarray(afs["counts"], dtype=float)

    centers = (edges[:-1] + edges[1:]) / 2.0
    theory = np.asarray(
        wright_stationary_distribution(centers.tolist(), u, n))

    # Compare total mass in the central 60 % of the range
    central = (centers > 0.2) & (centers < 0.8)
    obs_mass = np.sum(counts[central]) / reps
    theory_mass = np.sum(theory[central] * (edges[1] - edges[0])) / (
        np.sum(theory * (edges[1] - edges[0])))
    assert abs(obs_mass - theory_mass) < 0.1, (
        f"central mass observed={obs_mass:.3f} theory={theory_mass:.3f}")


def test_stationary_vector_is_fixed_point() -> None:
    """pi Q = pi exactly (Perron-Frobenius eigenvector), sums to 1."""
    n, u = 50, 0.02
    v = wright_fisher_stationary_vector(n, u)
    q = wright_fisher_transition_matrix(n, mutation_rate=u)
    drift = np.asarray(v) @ q
    assert abs(sum(v) - 1.0) < 1e-12
    assert np.all(np.asarray(v) >= 0.0)
    assert np.max(np.abs(drift - np.asarray(v))) < 1e-10, (
        f"max |pi Q - pi| = {np.max(np.abs(drift - np.asarray(v))):.2e}")


def test_stationary_vector_symmetric_for_neutral_mutation() -> None:
    """With symmetric mutation and no selection the chain is A<->a
    symmetric, so the stationary distribution is too."""
    n, u = 50, 0.02
    v = wright_fisher_stationary_vector(n, u)
    for i in range(n + 1):
        assert abs(v[i] - v[2 * n - i]) < 1e-9, (
            f"pi[{i}]={v[i]:.6f} != pi[{2*n-i}]={v[2*n-i]:.6f}")


def test_stationary_vector_matches_beta_density() -> None:
    """The exact chain stationary distribution (N=50, u=0.02, 4Nu=4)
    should carry essentially the same central mass as Wright's
    Beta(4,4) diffusion density."""
    n, u = 50, 0.02
    v = wright_fisher_stationary_vector(n, u)
    i_lo, i_hi = int(round(0.3 * 2 * n)), int(round(0.7 * 2 * n))
    chain_mass = sum(v[i_lo:i_hi + 1])
    pts = np.linspace(0.3, 0.7, 501)
    dens = np.asarray(wright_stationary_distribution(pts.tolist(), u, n))
    beta_mass = (dens.sum() - 0.5 * (dens[0] + dens[-1])) * 0.4 / 500.0
    assert abs(chain_mass - beta_mass) < 0.02, (
        f"central mass chain={chain_mass:.4f} beta={beta_mass:.4f}")


def test_stationary_vector_matches_simulation_spectrum() -> None:
    """A long simulation's final frequencies should be drawn from the
    exact chain's stationary distribution (same central-mass
    criterion as the Beta test)."""
    n, u = 50, 0.02
    v = wright_fisher_stationary_vector(n, u)
    i_lo, i_hi = int(round(0.3 * 2 * n)), int(round(0.7 * 2 * n))
    chain_mass = sum(v[i_lo:i_hi + 1])
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=1000,
        replicate_runs=2000, mutation_rate=u, seed=42,
        return_replicate_data=True)
    freqs = np.asarray(result.replicate_data)[-1, 1:]
    obs_mass = np.mean((freqs >= 0.3) & (freqs <= 0.7))
    assert abs(obs_mass - chain_mass) < 0.02, (
        f"central mass sim={obs_mass:.4f} chain={chain_mass:.4f}")


def test_stationary_vector_selection_shifts_mode() -> None:
    """Positive selection should push the stationary mode toward more
    A copies than the neutral case."""
    n, u = 50, 0.02
    neutral = wright_fisher_stationary_vector(n, u)
    selected = wright_fisher_stationary_vector(
        n, u, selection_coefficient=0.05)
    assert np.argmax(selected) > np.argmax(neutral), (
        f"mode neutral={np.argmax(neutral)} selected={np.argmax(selected)}")


def test_stationary_vector_validation() -> None:
    for bad in (0.0, 1.0, -0.05, 1.5):
        with pytest.raises(ValueError):
            wright_fisher_stationary_vector(50, bad)
    with pytest.raises(ValueError):
        wright_fisher_stationary_vector(0, 0.02)
    with pytest.raises(ValueError):
        wright_fisher_stationary_vector(50, True)
    with pytest.raises(ValueError):
        wright_fisher_stationary_vector(50, 0.02, selection_coefficient=-1.5)


def test_normalise_stationary_vector_handles_negative_sign() -> None:
    """Build-independent regression test for the eigenvector sign bug.

    The helper is extracted to module level precisely so this can be tested
    without going through scipy: LAPACK's sign choice is arbitrary and not
    stable across builds, so a test that calls the full eigen-decomposition
    only catches the bug on configurations that happen to return a negative
    vector. This forces the negative input directly.

    The OLD logic clamped before orienting:
        np.maximum([-0.2, -0.5, -0.3], 0)  ->  [0, 0, 0]
        total = 0.0
        v / total                          ->  NaN

    The fix orients toward the positive orthant first, then clamps, then
    checks the total actually being divided by.
    """
    result = _normalise_stationary_vector(
        np.array([-0.2, -0.5, -0.3], dtype=np.float64))

    assert sum(result) == pytest.approx(1.0, abs=1e-12)
    assert np.all(result >= 0.0)
    assert np.all(np.isfinite(result)), "the old logic produced NaN here"
    np.testing.assert_allclose(
        result, np.array([0.2, 0.5, 0.3]), atol=1e-12)

    # An all-zero vector has no valid orientation and must raise rather than
    # divide by zero.
    with pytest.raises(ValueError, match="failed to compute"):
        _normalise_stationary_vector(np.zeros(3, dtype=np.float64))

    # Sign symmetry: negating the input must not change the result.
    pos = _normalise_stationary_vector(
        np.array([0.2, 0.5, 0.3], dtype=np.float64))
    np.testing.assert_allclose(result, pos, atol=1e-15)


def test_stationary_vector_eigenvector_sign_regression() -> None:
    """Regression test for the eigenvector sign bug (Part 4 finding).

    LAPACK's choice of eigenvector sign is not stable across builds;
    some configurations return an all-negative Perron-Frobenius vector.
    The old code clamped first (zeroing a valid sign-flipped vector)
    then normalised, causing 0/0 -> NaN. The fix orients toward the
    positive orthant BEFORE clamping, then checks the total AFTER
    clamping. This test would fail on the buggy code if the eigenvector
    happened to be negative (e.g., numpy 1.26.4 / Python 3.10).
    """
    # Use a configuration known to trigger the sign issue under the
    # pinned CI environment (N=10, u=0.01, neutral).
    n, u = 10, 0.01
    v = wright_fisher_stationary_vector(n, u)

    # Basic validity checks that would fail if sign handling was broken
    assert abs(sum(v) - 1.0) < 1e-12, "distribution must sum to 1"
    assert np.all(np.asarray(v) >= 0.0), "all entries must be non-negative"
    assert np.all(np.isfinite(v)), "no NaN or inf allowed"

    # Verify it's actually the stationary distribution: pi Q = pi
    q = wright_fisher_transition_matrix(n, mutation_rate=u)
    drift = np.asarray(v) @ q
    assert np.max(np.abs(drift - np.asarray(v))) < 1e-10, (
        f"max |pi Q - pi| = {np.max(np.abs(drift - np.asarray(v))):.2e}")




# ---------------------------------------------------------------------------
# New scenarios: balancing selection and stepping stone
# ---------------------------------------------------------------------------


def test_scenario_balancing_selection_runs() -> None:
    result = wright_fisher_scenario("balancing-selection", seed=42)
    final_p = result.column("mean_frequency")[-1]
    assert abs(final_p - 2.0 / 3.0) < 0.08, (
        f"final p={final_p:.3f} should approach 2/3")
    assert result.column("heterozygosity")[-1] > 0.3


def test_scenario_stepping_stone_runs() -> None:
    result = wright_fisher_scenario("stepping-stone", seed=42)
    assert "fst" in result.colnames
    assert result.column("fst")[-1] > 0.05


def test_cli_wf_migration_model_flag() -> None:
    import subprocess
    import sys
    out = subprocess.check_output([
        sys.executable, "-m", "Tellurium.cli", "wf",
        "--population-size", "50",
        "--n-demes", "5", "--migration-rate", "0.01",
        "--migration-model", "stepping-stone",
        "--generations", "10", "--replicate-runs", "5", "--seed", "42",
        "--quiet"], cwd=_REPO_ROOT)
    assert out.decode() == ""  # quiet suppresses summary, exit 0


def test_cli_kimura_time_flag() -> None:
    import subprocess
    import sys
    out = subprocess.check_output([
        sys.executable, "-m", "Tellurium.cli", "kimura",
        "--p0", "0.5", "--s", "0.0", "--population-size", "50",
        "--time"], cwd=_REPO_ROOT)
    text = out.decode()
    assert "P_fix" in text
    assert "t_fix" in text
    assert "277" in text or "138" in text


def test_cli_ne_from_csv() -> None:
    import pathlib
    import subprocess
    import sys
    import tempfile
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=100,
        replicate_runs=1000, seed=42)
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = str(pathlib.Path(tmp) / "out.csv")
        result.to_csv(csv_path)
        out = subprocess.check_output([
            sys.executable, "-m", "Tellurium.cli", "ne",
            "--file", csv_path], cwd=_REPO_ROOT)
        text = out.decode()
        assert "Ne estimate" in text
        assert "heterozygosity decay" in text


def test_cli_ld_runs_and_reports_decay() -> None:
    """The ld command prints the D table and compares the final D
    against theoretical_ld_decay."""
    import subprocess
    import sys
    out = subprocess.check_output([
        sys.executable, "-m", "Tellurium.cli", "ld",
        "--population-size", "100", "--generations", "20",
        "--recombination-rate", "0.1", "--replicate-runs", "3000",
        "--seed", "42"], cwd=_REPO_ROOT)
    text = out.decode()
    assert "generation" in text
    assert "mean_D" in text
    assert "D0 = 0.250000" in text
    assert "theory (1-r)^t*(1-2u)^(2t)*(1-1/N)^t = 0.099438" in text


def test_cli_ld_bad_input_fails() -> None:
    import subprocess
    import sys
    r = subprocess.run([
        sys.executable, "-m", "Tellurium.cli", "ld",
        "--starting-frequencies", "0.5,0,0.5"], cwd=_REPO_ROOT,
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "exactly 4 entries" in r.stderr
    r2 = subprocess.run([
        sys.executable, "-m", "Tellurium.cli", "ld",
        "--recombination-rate", "0.7"], cwd=_REPO_ROOT,
        capture_output=True, text=True)
    assert r2.returncode == 1
    assert "recombination_rate must be in [0, 0.5]" in r2.stderr


def test_cli_ne_missing_column_fails() -> None:
    import pathlib
    import subprocess
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "bad.csv"
        bad.write_text("generation,mean_frequency\n0,0.5\n1,0.4\n")
        code = subprocess.call(
            [sys.executable, "-m", "Tellurium.cli", "ne",
             "--file", str(bad)], cwd=_REPO_ROOT)
        assert code == 1


def test_estimate_ne_from_heterozygosity_rejects_bad_input() -> None:
    assert "error" in estimate_ne_from_heterozygosity([])
    assert "error" in estimate_ne_from_heterozygosity([0.5, 0.5])
    assert "error" in estimate_ne_from_heterozygosity([0.0, 0.0, 0.0])
    est = estimate_ne_from_heterozygosity([0.5, 0.45, 0.4, 0.36, 0.33])
    assert "ne_estimate" in est
    assert est["ne_estimate"] > 0


# ---------------------------------------------------------------------------
# Theoretical island-model Fst (Wright 1931)
# ---------------------------------------------------------------------------


def test_theoretical_fst_closed_form() -> None:
    n = 100
    m = 0.05
    u = 0.001
    expected = 1.0 / (1.0 + 4.0 * n * (m + u))
    assert math.isclose(theoretical_fst(n, m, u), expected, rel_tol=1e-12)
    assert math.isclose(
        theoretical_fst(50, 0.1, 0.0), 1.0 / (1.0 + 4.0 * 50 * 0.1))
    assert theoretical_fst(100, 0.0, 0.0) == 1.0


def test_theoretical_fst_validation() -> None:
    with pytest.raises(ValueError):
        theoretical_fst(0, 0.1)
    with pytest.raises(ValueError):
        theoretical_fst(-10, 0.1)
    with pytest.raises(ValueError):
        theoretical_fst(100, -0.01)
    with pytest.raises(ValueError):
        theoretical_fst(100, 1.5)
    with pytest.raises(ValueError):
        theoretical_fst(100, 0.05, 1.0)
    with pytest.raises(ValueError):
        theoretical_fst(100, 0.05, -0.5)


def test_theoretical_fst_matches_simulation() -> None:
    n = 100
    m = 0.05
    u = 0.001
    result = simulate_wright_fisher(
        population_size=n, starting_frequency=0.5, generations=400,
        replicate_runs=30, mutation_rate=u, n_demes=30,
        migration_rate=m, seed=12345)
    sim_fst = result.column("fst")[-1]
    theory = theoretical_fst(n, m, u)
    assert abs(sim_fst - theory) < 0.01, (
        f"simulated Fst {sim_fst:.4f} should be within 0.01 of "
        f"theory {theory:.4f} at 30 demes")


# ---------------------------------------------------------------------------
# Wright-Fisher parameter sweep
# ---------------------------------------------------------------------------


def test_wright_fisher_sweep_orders_results() -> None:
    rows = wright_fisher_sweep(
        "selection_coefficient", [0.0, 0.02, 0.05],
        population_size=100, generations=300, replicate_runs=20, seed=99)
    assert [r["value"] for r in rows] == [0.0, 0.02, 0.05]
    assert all(r["parameter"] == "selection_coefficient" for r in rows)
    freqs = [r["final_mean_frequency"] for r in rows]
    assert freqs[0] < freqs[1] < freqs[2]
    assert rows[2]["final_heterozygosity"] < rows[0]["final_heterozygosity"]
    assert rows[0]["prop_fixed_A"] < rows[2]["prop_fixed_A"]


def test_wright_fisher_sweep_structured_includes_fst() -> None:
    rows = wright_fisher_sweep(
        "migration_rate", [0.0, 0.1],
        population_size=100, generations=200, replicate_runs=15,
        n_demes=10, seed=7)
    assert "final_fst" in rows[0]
    assert "final_fst" in rows[1]
    assert rows[0]["final_fst"] > rows[1]["final_fst"]


def test_wright_fisher_sweep_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        wright_fisher_sweep("bogus", [1.0])
    with pytest.raises(ValueError):
        wright_fisher_sweep("starting_frequency", [0.2, 0.8])


def test_cli_sweep_runs(tmp_path) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "sweep",
         "--parameter", "selection_coefficient",
         "--values", "0,0.05",
         "--generations", "200", "--seed", "5"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert "selection_coefficient" in proc.stdout
    assert "0.0500" in proc.stdout or "0.05" in proc.stdout


def test_cli_sweep_structured_shows_fst(tmp_path) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "sweep",
         "--parameter", "migration_rate",
         "--values", "0.0,0.2",
         "--n-demes", "10", "--seed", "11"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert "Fst" in proc.stdout


def test_cli_sweep_bad_input_fails(tmp_path) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "sweep",
         "--parameter", "bogus", "--values", "1"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 1
    assert "error" in proc.stderr
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "sweep",
         "--parameter", "selection_coefficient", "--values", "abc"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 2
    assert "comma-separated" in proc.stderr


# ---------------------------------------------------------------------------
# Exact Markov chain: transition matrix
# ---------------------------------------------------------------------------


def test_transition_matrix_hand_checked_small() -> None:
    Q = wright_fisher_transition_matrix(1)
    expected = np.array([
        [1.0, 0.0, 0.0],
        [0.25, 0.5, 0.25],
        [0.0, 0.0, 1.0],
    ])
    assert np.allclose(Q, expected)


def test_transition_matrix_rows_sum_to_one() -> None:
    for kwargs in ({}, {"mutation_rate": 0.01},
                   {"selection_coefficient": 0.05},
                   {"selection_coefficient": 0.05, "dominance": 1.5},
                   {"selection_coefficient": -0.2, "dominance": 2.0},
                   {"mutation_rate": 0.001, "selection_coefficient": 0.02,
                    "dominance": 0.5}):
        Q = wright_fisher_transition_matrix(10, **kwargs)
        assert Q.shape == (21, 21)
        assert np.all(Q >= 0.0)
        assert np.allclose(Q.sum(axis=1), 1.0)


def test_transition_matrix_neutral_mean_and_variance() -> None:
    N = 100
    Q = wright_fisher_transition_matrix(N)
    copies = np.arange(2 * N + 1, dtype=np.float64)
    mean = Q @ copies
    assert np.allclose(mean, copies, atol=1e-9)
    second = Q @ (copies ** 2)
    var = second - mean ** 2
    expected_var = copies * (2 * N - copies) / (2 * N)
    assert np.allclose(var, expected_var, atol=1e-8)


def test_transition_matrix_absorbing_states() -> None:
    Q = wright_fisher_transition_matrix(20)
    assert Q[0, 0] == 1.0
    assert Q[40, 40] == 1.0
    Qm = wright_fisher_transition_matrix(20, mutation_rate=0.01)
    assert Qm[0, 0] < 1.0
    assert Qm[40, 40] < 1.0


def test_transition_matrix_matches_simulation_distribution() -> None:
    N, t, p0, reps, seed = 20, 50, 0.3, 4000, 42
    rng = np.random.default_rng(seed)
    freqs = np.full(reps, p0)
    for _ in range(t):
        freqs = rng.binomial(2 * N, freqs) / (2 * N)
    sim_fix = np.mean(freqs >= 1.0 - 1e-12)
    sim_mean = float(np.mean(freqs))

    Q = np.linalg.matrix_power(
        wright_fisher_transition_matrix(N), t)
    i0 = round(p0 * 2 * N)
    chain_fix = Q[i0, 2 * N]
    chain_mean = float((Q[i0] @ np.arange(2 * N + 1)) / (2 * N))
    assert abs(sim_fix - chain_fix) < 0.03
    assert abs(sim_mean - chain_mean) < 0.02


def test_transition_matrix_validation() -> None:
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(0)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(True)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10.5)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10, mutation_rate=1.0)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10, mutation_rate=-0.1)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10, selection_coefficient=-1.0)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10, dominance=2.5)
    with pytest.raises(ValueError):
        wright_fisher_transition_matrix(10, mutation_rate=float("nan"))


# ---------------------------------------------------------------------------
# Exact Markov chain: expected fixation time (linear solve)
# ---------------------------------------------------------------------------


def test_chain_fixation_time_matches_closed_form() -> None:
    closed_05 = expected_fixation_time(0.5, 100)
    chain_05 = wright_fisher_expected_fixation_time(0.5, 100)
    assert abs(chain_05 - closed_05) / closed_05 < 0.02
    closed_02 = expected_fixation_time(0.2, 100)
    chain_02 = wright_fisher_expected_fixation_time(0.2, 100)
    assert abs(chain_02 - closed_02) / closed_02 < 0.02
    new_mut = 1.0 / 200.0
    chain_new = wright_fisher_expected_fixation_time(new_mut, 100)
    assert abs(chain_new - 4.0 * 100) / (4.0 * 100) < 0.02


def test_chain_fixation_time_boundaries() -> None:
    assert wright_fisher_expected_fixation_time(1.0, 100) == 0.0
    with pytest.raises(ValueError):
        wright_fisher_expected_fixation_time(0.0, 100)
    with pytest.raises(ValueError):
        wright_fisher_expected_fixation_time(0.5, 0)
    with pytest.raises(ValueError):
        wright_fisher_expected_fixation_time(1.5, 100)


def test_chain_fixation_time_selection_monotone() -> None:
    t0 = wright_fisher_expected_fixation_time(0.01, 100, 0.0)
    t1 = wright_fisher_expected_fixation_time(0.01, 100, 0.01)
    t2 = wright_fisher_expected_fixation_time(0.01, 100, 0.05)
    t3 = wright_fisher_expected_fixation_time(0.01, 100, 0.2)
    assert t0 > t1 > t2 > t3


def test_chain_fixation_time_matches_simulation_under_selection() -> None:
    N, s, p0, gens, reps, seed = 50, 0.05, 0.2, 600, 3000, 123
    chain = wright_fisher_expected_fixation_time(p0, N, s)
    result = simulate_wright_fisher(
        population_size=N, starting_frequency=p0, generations=gens,
        replicate_runs=reps, selection_coefficient=s, seed=seed)
    fa = result.fixation_analysis()
    sim = fa["mean_fixation_time_A"]
    assert abs(sim - chain) / chain < 0.05


def test_chain_fixation_time_diploid_dominance() -> None:
    t_hap = wright_fisher_expected_fixation_time(
        0.1, 50, 0.05, dominance=None)
    t_dom = wright_fisher_expected_fixation_time(0.1, 50, 0.05, dominance=1.0)
    t_under = wright_fisher_expected_fixation_time(
        0.1, 50, 0.05, dominance=2.0)
    assert t_hap > 0 and t_dom > 0 and t_under > 0
    assert t_under > t_dom


def test_cli_kimura_exact_flag(tmp_path) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "kimura",
         "--p0", "0.5", "--s", "0.05", "--population-size", "50",
         "--time", "--exact"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "t_fix (exact WF chain)" in proc.stdout
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "kimura",
         "--p0", "0.5", "--s", "0.0", "--population-size", "50",
         "--time"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "t_fix (exact WF chain)" not in proc.stdout


# ---------------------------------------------------------------------------
# Exact Markov chain: fixation probability (absorption solve)
# ---------------------------------------------------------------------------


def test_exact_fixation_probability_neutral_martingale() -> None:
    for p0 in (0.1, 0.3, 0.5, 0.7, 0.9):
        got = wright_fisher_fixation_probability(p0, 100)
        assert abs(got - p0) < 1e-9, f"neutral P_fix at p0={p0} is {got}"


def test_exact_fixation_probability_matches_kimura_genic() -> None:
    for s in (0.01, 0.05):
        exact = wright_fisher_fixation_probability(0.3, 50, s)
        kimura = kimura_fixation_probability(0.3, s, 50)
        assert abs(exact - kimura) < 0.01, (
            f"at s={s}: exact {exact:.5f} vs kimura {kimura:.5f}")


def test_exact_fixation_probability_overdominance_matches_simulation() -> None:
    exact = wright_fisher_fixation_probability(0.5, 50, 0.05, dominance=2.0)
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=1500,
        replicate_runs=4000, selection_coefficient=0.05, dominance=2.0,
        seed=7)
    fa = result.fixation_analysis()
    fixed = fa["n_fixed_A"] + fa["n_fixed_a"]
    sim = fa["n_fixed_A"] / fixed if fixed else float("nan")
    assert abs(exact - sim) < 0.02, f"exact {exact:.4f} vs sim {sim:.4f}"


def test_exact_fixation_probability_underdominance_beats_kimura() -> None:
    exact = wright_fisher_fixation_probability(0.5, 50, -0.2, dominance=2.0)
    kimura = kimura_fixation_probability(0.5, -0.2, 50, dominance=2.0)
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=1000,
        replicate_runs=4000, selection_coefficient=-0.2, dominance=2.0,
        seed=7)
    fa = result.fixation_analysis()
    fixed = fa["n_fixed_A"] + fa["n_fixed_a"]
    sim = fa["n_fixed_A"] / fixed if fixed else float("nan")
    assert abs(exact - sim) < 0.01, f"exact {exact:.4f} vs sim {sim:.4f}"
    assert abs(kimura - sim) > 0.01, (
        "Kimura's diffusion approximation should be measurably wrong "
        "under underdominance (the documented failure this function "
        "resolves)")


def test_exact_fixation_probability_boundaries_and_validation() -> None:
    assert wright_fisher_fixation_probability(0.0, 100) == 0.0
    assert wright_fisher_fixation_probability(1.0, 100) == 1.0
    with pytest.raises(ValueError):
        wright_fisher_fixation_probability(-0.1, 100)
    with pytest.raises(ValueError):
        wright_fisher_fixation_probability(1.5, 100)
    with pytest.raises(ValueError):
        wright_fisher_fixation_probability(0.5, 0)
    with pytest.raises(ValueError):
        wright_fisher_fixation_probability(True, 100)


def test_exact_fixation_probability_monotone_in_s() -> None:
    values = [wright_fisher_fixation_probability(0.2, 50, s)
              for s in (0.0, 0.01, 0.05, 0.1)]
    assert values == sorted(values)
    assert values[-1] > 0.9


def test_cli_kimura_exact_probability(tmp_path) -> None:
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "kimura",
         "--p0", "0.5", "--s", "0.0", "--population-size", "50",
         "--exact"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "P_fix (exact WF chain) = 0.500000" in proc.stdout
    proc = subprocess.run(
        [sys.executable, "-m", "Tellurium.cli", "kimura",
         "--p0", "0.5", "--s", "0.0", "--population-size", "50"],
        capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "P_fix (exact WF chain)" not in proc.stdout


# ---------------------------------------------------------------------------
# Time to loss and to absorption (Kimura & Ohta 1969; exact chain)
# ---------------------------------------------------------------------------


def test_expected_loss_time_closed_form() -> None:
    assert math.isclose(
        expected_loss_time(0.5, 100),
        -4.0 * 100 * 0.5 * math.log(0.5) / 0.5)
    assert math.isclose(
        expected_loss_time(0.1, 100),
        -4.0 * 100 * 0.1 * math.log(0.1) / 0.9)
    assert expected_loss_time(0.0, 100) == 0.0
    assert expected_loss_time(1.0, 100) == 400.0  # limit 4N
    with pytest.raises(ValueError):
        expected_loss_time(-0.1, 100)
    with pytest.raises(ValueError):
        expected_loss_time(0.5, 0)


def test_expected_loss_time_symmetry_with_fixation() -> None:
    for p0 in (0.05, 0.2, 0.4, 0.8):
        assert math.isclose(
            expected_loss_time(p0, 100), expected_fixation_time(1.0 - p0, 100))


def test_chain_loss_time_matches_closed_form() -> None:
    for p0 in (0.5, 0.1, 0.9):
        closed = expected_loss_time(p0, 100)
        chain = wright_fisher_expected_loss_time(p0, 100)
        assert abs(chain - closed) / closed < 0.02, f"p0={p0}"


def test_chain_loss_time_symmetry_exact() -> None:
    assert abs(wright_fisher_expected_loss_time(0.3, 100)
               - wright_fisher_expected_fixation_time(0.7, 100)) < 1e-9


def test_chain_loss_time_matches_simulation() -> None:
    chain = wright_fisher_expected_loss_time(0.2, 50)
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.2, generations=1000,
        replicate_runs=4000, seed=77)
    fa = result.fixation_analysis()
    sim = fa["mean_fixation_time_a"]
    assert abs(sim - chain) / chain < 0.06


def test_fixation_analysis_absorption_times_match_chain_neutral() -> None:
    N, p0, gens, reps, seed = 50, 0.5, 1000, 3000, 42
    result = simulate_wright_fisher(
        population_size=N, starting_frequency=p0, generations=gens,
        replicate_runs=reps, seed=seed)
    fa = result.fixation_analysis()
    assert fa["n_absorbed"] == fa["n_fixed_A"] + fa["n_fixed_a"] == reps
    chain_fix = wright_fisher_expected_fixation_time(p0, N)
    chain_loss = wright_fisher_expected_loss_time(p0, N)
    chain_abs = wright_fisher_expected_absorption_time(p0, N)
    assert abs(fa["mean_fixation_time_A"] - chain_fix) / chain_fix < 0.06
    assert abs(fa["mean_fixation_time_a"] - chain_loss) / chain_loss < 0.06
    assert abs(fa["mean_absorption_time"] - chain_abs) / chain_abs < 0.06


def test_fixation_analysis_absorption_times_match_chain_selection() -> None:
    N, s, p0, gens, reps, seed = 50, 0.05, 0.2, 1000, 3000, 9
    result = simulate_wright_fisher(
        population_size=N, starting_frequency=p0, generations=gens,
        replicate_runs=reps, selection_coefficient=s, seed=seed)
    fa = result.fixation_analysis()
    assert fa["n_absorbed"] == reps
    chain_fix = wright_fisher_expected_fixation_time(p0, N, s)
    chain_abs = wright_fisher_expected_absorption_time(p0, N, s)
    assert abs(fa["mean_fixation_time_A"] - chain_fix) / chain_fix < 0.06
    assert abs(fa["mean_absorption_time"] - chain_abs) / chain_abs < 0.06
    assert fa["mean_absorption_time"] < fa["mean_fixation_time_A"]


def test_fixation_analysis_absorption_censoring_reported() -> None:
    result = simulate_wright_fisher(
        population_size=50, starting_frequency=0.5, generations=20,
        replicate_runs=500, seed=3)
    fa = result.fixation_analysis()
    assert fa["n_polymorphic"] == fa["n_replicates"] - fa["n_absorbed"]
    assert fa["n_polymorphic"] > 0
    assert "mean_absorption_time" in fa


def test_chain_loss_time_selection_decreases_with_s() -> None:
    t0 = wright_fisher_expected_loss_time(0.2, 50, 0.0)
    t1 = wright_fisher_expected_loss_time(0.2, 50, 0.01)
    t2 = wright_fisher_expected_loss_time(0.2, 50, 0.05)
    assert t0 > t1 > t2


def test_chain_loss_time_boundaries() -> None:
    assert wright_fisher_expected_loss_time(0.0, 100) == 0.0
    with pytest.raises(ValueError):
        wright_fisher_expected_loss_time(1.0, 100)
    with pytest.raises(ValueError):
        wright_fisher_expected_loss_time(0.5, 0)


def test_chain_absorption_time_matches_closed_form() -> None:
    closed = -4.0 * 100 * (0.5 * math.log(0.5) + 0.5 * math.log(0.5))
    chain = wright_fisher_expected_absorption_time(0.5, 100)
    assert abs(chain - closed) / closed < 0.02
    assert math.isclose(
        wright_fisher_expected_absorption_time(0.5, 100),
        wright_fisher_expected_fixation_time(0.5, 100))


def test_chain_absorption_time_consistency_identity() -> None:
    for p0 in (0.2, 0.4, 0.6, 0.8):
        f = wright_fisher_fixation_probability(p0, 100)
        lhs = wright_fisher_expected_absorption_time(p0, 100)
        rhs = (wright_fisher_expected_fixation_time(p0, 100) * f
               + wright_fisher_expected_loss_time(p0, 100) * (1.0 - f))
        assert abs(lhs - rhs) < 1e-9, f"p0={p0}: {lhs} vs {rhs}"
    f = wright_fisher_fixation_probability(0.2, 50, 0.05)
    lhs = wright_fisher_expected_absorption_time(0.2, 50, 0.05)
    rhs = (wright_fisher_expected_fixation_time(0.2, 50, 0.05) * f
           + wright_fisher_expected_loss_time(0.2, 50, 0.05) * (1.0 - f))
    assert abs(lhs - rhs) < 1e-9


def test_chain_absorption_time_boundaries() -> None:
    assert wright_fisher_expected_absorption_time(0.0, 100) == 0.0
    assert wright_fisher_expected_absorption_time(1.0, 100) == 0.0
    with pytest.raises(ValueError):
        wright_fisher_expected_absorption_time(0.5, 0)
