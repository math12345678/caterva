"""Regression: the SSA ensemble mean must converge on the closed form.

`simulate_gillespie_ssa_replicates` placed each trajectory on the output
grid with `np.interp`. An SSA path is right-continuous and piecewise
CONSTANT -- the count set by an event holds until the next event -- so
linear interpolation reports counts the system never held. For a
monotonically decreasing species the error is one-sided, which makes it a
systematic BIAS rather than noise.

The consequence is the opposite of what an ensemble average is for.
Measured against the exact closed form E[a(t)] = a0*exp(-k*t)
(a0=100, k=0.5, end=10, seed=7, averaged over 0.5 < t < 6):

    replicates   mean bias        worst deviation
           500   -0.66 molecules  -6.6 sigma
          2000   -0.53 molecules  -10.9 sigma
          8000   -0.48 molecules  -18.2 sigma

The bias plateaus while the standard error keeps shrinking, so adding
replicates made the answer *more conclusively wrong*. After replacing the
interpolation with a zero-order hold:

           500   -0.17 molecules  -2.6 sigma
          2000   -0.04 molecules  -1.7 sigma
          8000   +0.01 molecules  -0.7 sigma

which is what a consistent estimator looks like.

Why the previous guard missed it: `test_gillespie_ssa_replicates.py` checks
deviations at four checkpoints with a 3-sigma tolerance and a hardcoded
`n_reps = 400`. At 400 replicates the standard error is still wide enough
to hide a half-molecule bias. The test's own docstring claims "a bug that
only shifted mid-trajectory mean_a (e.g. an interpolation error between the
endpoints) would fail here" -- it would not, at that sample size. A
tolerance stated in sigma silently loosens as the sample shrinks.

So the test below is written the other way round: it asserts the bias
SHRINKS as the ensemble grows, which no amount of sample-size tuning can
satisfy while a systematic offset remains.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tellurium_engine import simulate_gillespie_ssa_replicates  # noqa: E402

A0, K, END, SEED = 100, 0.5, 10.0, 7


def _bias_profile(n_replicates: int, seed: int = SEED):
    """(mean bias in molecules, worst deviation in standard errors).

    The count at time t is exactly Binomial(a0, exp(-k*t)), so both the
    true mean and the standard error of the ensemble mean are known in
    closed form -- no reference simulation is involved.
    """
    result = simulate_gillespie_ssa_replicates(
        a0=A0, k=K, end=END, n_replicates=n_replicates, seed=seed
    )
    data = np.asarray(result.data, dtype=float)
    t, observed = data[:, 0], data[:, 1]

    survival = np.exp(-K * t)
    truth = A0 * survival
    standard_error = np.sqrt(A0 * survival * (1 - survival) / n_replicates)
    standard_error[standard_error == 0] = np.inf  # t=0 is deterministic

    # Interior of the decay: at t~0 nothing has happened yet and by t~10
    # almost everything has, so both ends carry little information.
    interior = (t > 0.5) & (t < 6.0)
    bias = observed - truth
    return float(bias[interior].mean()), float(
        np.min(bias[interior] / standard_error[interior])
    )


class TestEnsembleMeanIsUnbiased:
    def test_large_ensemble_agrees_with_the_closed_form(self):
        _, worst_z = _bias_profile(8000)
        assert worst_z > -4.0, (
            f"ensemble mean sits {worst_z:.1f} standard errors below "
            f"a0*exp(-k*t); with 8000 replicates that is a systematic "
            "bias, not sampling noise"
        )

    def test_bias_shrinks_as_the_ensemble_grows(self):
        """The property a biased estimator cannot satisfy.

        A tolerance in sigma can always be met by using fewer replicates.
        Convergence cannot: a systematic offset stays put while the
        standard error shrinks, so the deviation measured in sigma grows.
        """
        small_bias, _ = _bias_profile(500)
        large_bias, _ = _bias_profile(8000)
        assert abs(large_bias) < abs(small_bias), (
            f"bias did not shrink with more replicates "
            f"({small_bias:+.3f} at 500 -> {large_bias:+.3f} at 8000); "
            "an ensemble average that does not converge is not an average"
        )
        assert abs(large_bias) < 0.15, (
            f"residual bias {large_bias:+.3f} molecules at 8000 replicates"
        )

    def test_deviation_in_sigma_does_not_grow_with_the_ensemble(self):
        # The clearest statement of the original defect: -6.6 sigma at 500
        # became -18.2 sigma at 8000.
        _, z_small = _bias_profile(500)
        _, z_large = _bias_profile(8000)
        assert abs(z_large) < abs(z_small) + 2.0, (
            f"deviation grew from {z_small:.1f} to {z_large:.1f} sigma as "
            "replicates increased -- the signature of systematic bias"
        )


class TestStepSemanticsArePreserved:
    def test_counts_are_whole_molecules_at_every_grid_point(self):
        """A single trajectory holds integer counts; interpolation did not.

        With one replicate the ensemble mean IS that trajectory, so every
        sampled value must be a whole number of molecules. Linear
        interpolation produced fractional counts here.
        """
        result = simulate_gillespie_ssa_replicates(
            a0=A0, k=K, end=END, n_replicates=1, seed=SEED
        )
        data = np.asarray(result.data, dtype=float)
        counts = data[:, 1]
        assert np.allclose(counts, np.round(counts)), (
            "a single SSA trajectory reported fractional molecule counts; "
            "the grid sampling is interpolating between events rather than "
            "holding the step"
        )

    def test_a_single_trajectory_never_increases(self):
        # A -> B is monotone. Interpolation cannot violate this, but a
        # mis-indexed step lookup could.
        result = simulate_gillespie_ssa_replicates(
            a0=A0, k=K, end=END, n_replicates=1, seed=SEED
        )
        counts = np.asarray(result.data, dtype=float)[:, 1]
        assert np.all(np.diff(counts) <= 0), "first-order decay increased"

    def test_conservation_holds_on_the_grid(self):
        # a + b = a0 at every sampled time, for any ensemble size.
        result = simulate_gillespie_ssa_replicates(
            a0=A0, k=K, end=END, n_replicates=200, seed=SEED
        )
        data = np.asarray(result.data, dtype=float)
        assert np.allclose(data[:, 1] + data[:, 2], A0, atol=1e-9)
