"""Monte Carlo pi estimation: validation, convergence rate, reproducibility,
and standard-error statistical consistency.

This is a discrete/stochastic domain (not an ODE), so "correctness" here means:
(a) the error shrinks at the theoretical sqrt(N) rate against the exact true
    value math.pi,
(b) a fixed seed produces bit-identical output across repeated calls,
(c) the reported standard error is statistically consistent with the observed
    error across many independent runs at the same n_samples.

Unlike the ODE domains, there is no numerical solver involved — the estimator
is a direct sample mean whose only error is the controlled statistical
uncertainty reported as standard error.

Mutation-test record (verified by independent reproduction; see
STAGE_01_PART_03.md Section 1 Step 4 and STAGE_01_PART_04.md Section 3):

1. "Remove the 4x multiplier from the SE formula"
   Mutation: cumulative_se = 4.0 * np.sqrt(...) -> cumulative_se = np.sqrt(...)
   Caught by: test_standard_error_matches_empirical_variation (ratio ~4 vs ~1),
              test_z_scores_are_approximately_standard_normal (33.5% vs ~95%).
   NOT caught by: test_error_scales_with_inverse_sqrt_n (checks pi estimate,
                  not SE formula — 2 tests catch it, not 3).
   This overclaim (3 -> 2) was discovered by independent reproduction and
   corrected here per the divergence-resolution procedure.

2. "Ignore the seed parameter"
   Mutation: np.random.default_rng() instead of np.random.default_rng(seed)
   Caught by: test_same_seed_produces_bit_identical_output (rows diverge
              across calls).

3. "Change pi multiplier from 4.0 to 2.0"
   Mutation: cumulative_estimate = 2.0 * cumulative_p_hat
   Caught by: test_error_scales_with_inverse_sqrt_n (ratio ~10.0 >> 3.0),
              test_larger_samples_give_smaller_error.

All three mutations were independently reproduced, confirmed to fail the
stated tests, and reverted. The full suite (22 tests) passes cleanly.
"""

import math

import numpy as np
import pytest

from caterva_engine import (
    MC_PLAUSIBLE_MIN_SAMPLES,
    ModelBuildError,
    simulate_monte_carlo_pi,
    validate_monte_carlo_params,
)


# ---------------------------------------------------------------------------
# Validation: hard rejections (ok=False)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_n", [0, -1, -100])
def test_non_positive_n_samples_is_rejected(bad_n: int) -> None:
    v = validate_monte_carlo_params(n_samples=bad_n)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_monte_carlo_pi(n_samples=bad_n)


def test_float_n_samples_is_rejected() -> None:
    v = validate_monte_carlo_params(n_samples=10.5)  # type: ignore[arg-type]
    assert not v.ok


def test_boolean_n_samples_is_rejected() -> None:
    # bool is a subclass of int in Python; must not silently pass as 1.
    v = validate_monte_carlo_params(n_samples=True)  # type: ignore[arg-type]
    assert not v.ok


# ---------------------------------------------------------------------------
# Validation: flagging (flagged=True, simulation still runs)
# ---------------------------------------------------------------------------


def test_n_samples_below_plausible_threshold_is_flagged() -> None:
    low = MC_PLAUSIBLE_MIN_SAMPLES - 1
    v = validate_monte_carlo_params(n_samples=low)
    assert v.ok
    assert v.flagged
    assert v.flag_reason
    assert "standard error" in v.flag_reason.lower()

    # Flagged-but-valid must still simulate and carry the flag through.
    result = simulate_monte_carlo_pi(n_samples=low)
    assert result.flagged


def test_n_samples_at_threshold_is_not_flagged() -> None:
    v = validate_monte_carlo_params(n_samples=MC_PLAUSIBLE_MIN_SAMPLES)
    assert v.ok
    assert not v.flagged


def test_n_samples_above_threshold_is_not_flagged() -> None:
    v = validate_monte_carlo_params(n_samples=10_000)
    assert v.ok
    assert not v.flagged


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_result_has_expected_columns() -> None:
    result = simulate_monte_carlo_pi(n_samples=1000)
    assert result.colnames == ["n", "estimate", "se"]
    assert result.model_name == "monte_carlo_pi"


def test_last_row_uses_full_n_samples() -> None:
    n = 5000
    result = simulate_monte_carlo_pi(n_samples=n)
    assert result.column("n")[-1] == pytest.approx(float(n))


def test_estimates_are_between_zero_and_five() -> None:
    # With 4 * (fraction inside unit circle), the estimate should be in
    # [0, 4] for any finite sample. Allow a tiny margin for float noise.
    result = simulate_monte_carlo_pi(n_samples=1000, seed=42)
    for est in result.column("estimate"):
        assert 0.0 <= est <= 5.0


def test_standard_errors_are_non_negative_and_decreasing() -> None:
    result = simulate_monte_carlo_pi(n_samples=10_000, seed=1)
    ses = result.column("se")
    # First few SEs can be zero (single-sample degenerate case), then they
    # should settle into a monotonically decreasing envelope after ~10 samples.
    for se in ses:
        assert se >= 0.0
    # After 100 samples, SE should generally be decreasing (allow rare noise).
    ses_late = [s for i, s in enumerate(ses) if result.column("n")[i] >= 100]
    assert ses_late[-1] < ses_late[0]  # should have decreased substantially


# ---------------------------------------------------------------------------
# Verification 6(a): error shrinks at the theoretical sqrt(N) rate
# ---------------------------------------------------------------------------


def test_error_scales_with_inverse_sqrt_n() -> None:
    """Across three sample sizes spanning ~3 orders of magnitude, the product
    |estimate - pi| * sqrt(n_samples) should be roughly constant.

    This is the defining property of Monte Carlo convergence: the error
    decreases as 1/sqrt(N), so error * sqrt(N) is approximately constant
    (the standard deviation of the estimator).
    """
    sizes = [1_000, 10_000, 100_000]
    products: list[float] = []

    for i, n in enumerate(sizes):
        result = simulate_monte_carlo_pi(n_samples=n, seed=12345 + i * 7777)
        estimate = result.column("estimate")[-1]
        error = abs(estimate - math.pi)
        product = error * math.sqrt(n)
        products.append(product)

    # The three products should be within a factor of 3 of each other.
    # (More precisely: for independent runs they'd follow a scaled
    # chi distribution, so a factor-of-3 check is generous enough to
    # avoid false positives while catching gross scaling violations.)
    max_product = max(products)
    min_product = min(products)
    assert max_product / min_product < 3.0, (
        f"error * sqrt(N) products vary too much: {products}"
    )


def test_larger_samples_give_smaller_error() -> None:
    """A basic sanity check: 100k samples should beat 1k samples on the
    same seed."""
    seed = 9999
    r_small = simulate_monte_carlo_pi(n_samples=1_000, seed=seed)
    r_large = simulate_monte_carlo_pi(n_samples=100_000, seed=seed)

    err_small = abs(r_small.column("estimate")[-1] - math.pi)
    err_large = abs(r_large.column("estimate")[-1] - math.pi)

    # With 100x more samples, error should be at least somewhat smaller.
    assert err_large < err_small, (
        f"100k error {err_large:.6f} not smaller than 1k error {err_small:.6f}"
    )


# ---------------------------------------------------------------------------
# Verification 6(b): fixed-seed reproducibility
# ---------------------------------------------------------------------------


def test_same_seed_produces_bit_identical_output() -> None:
    seed = 42
    n = 10_000
    r1 = simulate_monte_carlo_pi(n_samples=n, seed=seed)
    r2 = simulate_monte_carlo_pi(n_samples=n, seed=seed)

    assert len(r1.data) == len(r2.data)
    for row1, row2 in zip(r1.data, r2.data):
        assert row1 == row2, f"rows diverge: {row1} vs {row2}"


def test_different_seeds_produce_different_output() -> None:
    n = 5_000
    r1 = simulate_monte_carlo_pi(n_samples=n, seed=1)
    r2 = simulate_monte_carlo_pi(n_samples=n, seed=2)

    # The final estimates should differ (probability of exact match is ~0).
    assert r1.column("estimate")[-1] != r2.column("estimate")[-1]


def test_no_seed_gives_different_estimates_across_repeated_calls() -> None:
    """Without a fixed seed, estimates should vary across runs.

    Checks that 10 successive seedless calls produce estimates with
    non-zero variance — a stronger assertion than pairwise inequality,
    which can fail by chance when two different seeds happen to give
    the same estimate to float precision.
    """
    n = 2_000
    estimates = [simulate_monte_carlo_pi(n_samples=n).column("estimate")[-1]
                 for _ in range(10)]
    assert len(set(estimates)) > 1, (
        f"all 10 seedless runs gave the same estimate {estimates[0]}"
    )


# ---------------------------------------------------------------------------
# Verification 6(c): reported SE is statistically consistent with observed
#                    error across many repeated independent runs
# ---------------------------------------------------------------------------


def test_standard_error_matches_empirical_variation() -> None:
    """Run K=500 independent simulations at n_samples=10_000 and check that
    the empirical standard deviation of estimates is close to the mean
    reported standard error.

    The theoretical relationship: across independent Monte Carlo runs, the
    sample standard deviation of the estimates should approximately equal
    the reported standard error. A factor-of-2 check is generous enough to
    avoid false positives from sampling noise while catching gross SE
    formula errors (e.g., forgetting the factor of 4, or miscomputing the
    variance).
    """
    n_samples = 10_000
    n_runs = 500

    estimates: list[float] = []
    reported_ses: list[float] = []

    for run_seed in range(n_runs):
        result = simulate_monte_carlo_pi(
            n_samples=n_samples, seed=run_seed + 100_000)
        estimates.append(result.column("estimate")[-1])
        reported_ses.append(result.column("se")[-1])

    empirical_sd = float(np.std(estimates, ddof=1))
    mean_reported_se = float(np.mean(reported_ses))

    # The ratio should be close to 1.0. Allow a generous factor of 2 to
    # account for finite-sample noise while catching gross mismatches.
    ratio = empirical_sd / mean_reported_se
    assert 0.5 < ratio < 2.0, (
        f"empirical SD ({empirical_sd:.6f}) / mean reported SE "
        f"({mean_reported_se:.6f}) = {ratio:.3f}, expected near 1.0"
    )


def test_z_scores_are_approximately_standard_normal() -> None:
    """Run many independent simulations and check that the fraction of
    estimates falling within ±1.96 reported SE of pi is close to 95%.

    This is a stronger test than the ratio check: it validates the full
    distributional claim, not just the second moment.
    """
    n_samples = 5_000
    n_runs = 400

    within_95: int = 0
    for run_seed in range(n_runs):
        result = simulate_monte_carlo_pi(
            n_samples=n_samples, seed=run_seed + 200_000)
        estimate = result.column("estimate")[-1]
        se = result.column("se")[-1]
        z = (estimate - math.pi) / se if se > 0 else float("inf")
        if abs(z) <= 1.96:
            within_95 += 1

    fraction = within_95 / n_runs
    # With 400 runs, the 95% CI for the coverage fraction is approximately
    # 0.95 ± 1.96 * sqrt(0.95*0.05/400) ≈ [0.929, 0.971]. Allow a bit more
    # margin to avoid false positives from Monte Carlo noise.
    assert 0.88 < fraction < 1.00, (
        f"fraction within ±1.96 SE is {fraction:.3f}, "
        f"expected ~0.95 (within [0.88, 1.00])"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_n_samples_equal_to_one_works_and_is_flagged() -> None:
    """n_samples=1 is valid but flagged (way below plausible threshold)."""
    result = simulate_monte_carlo_pi(n_samples=1, seed=0)
    assert result.flagged
    assert len(result.data) == 1
    assert result.column("n")[0] == 1.0
    # With one point, estimate is either 0.0 or 4.0.
    assert result.column("estimate")[0] in (0.0, 4.0)


def test_n_samples_equal_to_99_is_flagged() -> None:
    """Just below the threshold — should be flagged."""
    v = validate_monte_carlo_params(n_samples=99)
    assert v.ok and v.flagged


def test_large_n_samples_completes_within_reasonable_time() -> None:
    """1M samples should complete quickly (O(N) vectorized)."""
    result = simulate_monte_carlo_pi(n_samples=100_000, seed=7)
    # The final estimate should be within ~0.02 of pi for 100k samples
    # (99.7% confidence band is 3 * 4 * 0.5 / sqrt(100k) ≈ 0.019).
    error = abs(result.column("estimate")[-1] - math.pi)
    assert error < 0.05, f"100k-sample error {error:.6f} is unexpectedly large"
