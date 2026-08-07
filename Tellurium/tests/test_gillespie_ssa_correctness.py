"""Gillespie SSA engine tests (model = ADR 0009).

Covers the exact Gillespie Direct Method implementation for the single
reversible-decay reaction A -> B:

  * closed-form agreement in expectation (mean[a(t)] = a0 * exp(-k t)),
  * exponential inter-event-time law (tau ~ Exp(k * a0); the defining
    property that distinguishes the exact SSA from a fixed-timestep
    approximation),
  * stoichiometric conservation (a + b = a0) on every row,
  * seed determinism (identical RNG sequence -> identical trajectory),
  * parameter edge cases (k = 0, flag thresholds),
  * output contract (columns, model name, endpoint snap, shape).
"""

from __future__ import annotations

import math

import pytest

from Tellurium import tellurium_engine as te


def _run(a0, k, end, seed=1):
    return te.simulate_gillespie_ssa(a0=a0, k=k, end=end, seed=seed)


class TestClosedFormAgreement:
    def test_mean_a_tracks_exp_decay(self):
        """Average final A across seeded replicates is close to a0 e^{-kt}.

        For a first-order death chain the count at time t is exactly
        Binomial(a0, e^{-kt}), so the standard error over N replicates is
        sqrt(a0 e^{-kt} (1 - e^{-kt}) / N); the tolerance is set at ~3 sigma.
        """
        a0, k, end = 4000, 0.5, 10.0
        expected = a0 * math.exp(-k * end)
        finals = [
            _run(a0, k, end, seed=s).data[-1][1]
            for s in range(50)
        ]
        se = math.sqrt(expected * (1 - math.exp(-k * end)) / len(finals))
        assert abs(sum(finals) / len(finals) - expected) < 3.0 * se

    def test_expected_event_time_scale(self):
        """Rough scale check: mean event count is near a0 * (1 - e^{-k end})."""
        a0, k, end = 2000, 1.0, 5.0
        expected_events = a0 * (1 - math.exp(-k * end))
        counts = []
        for s in range(30):
            res = _run(a0, k, end, seed=s)
            counts.append(sum(1 for row in res.data[1:-1]))
        mean = sum(counts) / len(counts)
        assert abs(mean - expected_events) < 0.05 * expected_events

    def test_conservation_holds_every_row(self):
        res = _run(500, 2.0, 3.0, seed=7)
        for row in res.data:
            assert row[1] + row[2] == 500

    def test_initial_and_final_rows(self):
        res = _run(100, 1.0, 5.0, seed=3)
        assert res.data[0][0] == 0.0
        assert res.data[0][1] == 100
        assert res.data[0][2] == 0
        assert res.data[-1][0] == 5.0


class TestExponentialWaitingTimeLaw:
    """The exact-SSA defining property: inter-event times are Exp(k*a0).

    For first-order decay (single reaction, propensity = k*a), the first
    event time T_1 has survival P(T_1 > tau) = exp(-k*a0*tau). This is a
    closed-form distributional claim (Constitution Rule 1) and it is the
    property that makes the SSA *exact* rather than a fixed-timestep
    approximation. A tau drawn uniformly (or with any non-exponential
    distribution) passes every mean/conservation/determinism test while
    failing this one.
    """

    def test_first_event_survival_matches_exponential(self):
        a0, k, end = 1000, 0.5, 0.05
        rate = k * a0
        # end >> 1/rate so (almost) every trajectory has an event.
        assert 1 - math.exp(-rate * end) > 0.9999
        first_times = [
            row[1][0] for row in (_run(a0, k, end, seed=s).data
                                  for s in range(300))
            if len(row) > 1
        ]
        assert len(first_times) >= 280
        for tau in (0.001, 0.003, 0.006):
            p_exact = math.exp(-rate * tau)
            p_obs = sum(1 for t in first_times if t > tau) / len(first_times)
            se = math.sqrt(p_exact * (1 - p_exact) / len(first_times))
            stat = abs(p_obs - p_exact) / se
            assert stat < 3.0, (
                f"tau={tau}: P(T1>{tau}) observed {p_obs:.4f} vs "
                f"closed form {p_exact:.4f} ({stat:.1f} sigma)")

    def test_tau_sampling_consumes_one_uniform_per_unit_propensity(self):
        """Gillespie's Direct Method: tau = -log(u)/propensity per event.

        The empirical mean of the *first* inter-event time must approach
        1/(k*a0); a uniform draw in place of -log(u) would give a mean
        near 1/(2*k*a0) instead and fail this check.
        """
        a0, k, end = 2000, 1.0, 0.05
        rate = k * a0
        first_times = [
            row[1][0] for row in (_run(a0, k, end, seed=s).data
                                  for s in range(200))
            if len(row) > 1
        ]
        theory_mean = 1.0 / rate
        obs_mean = sum(first_times) / len(first_times)
        # Exponential mean 1/rate has std 1/rate, so the sampling error
        # of the mean over N draws is 1/rate/sqrt(N); allow ~3 sigma.
        se = theory_mean / math.sqrt(len(first_times))
        assert abs(obs_mean - theory_mean) < 3.0 * se, (
            f"mean first event time {obs_mean:.5f} vs Exp mean "
            f"{theory_mean:.5f}")


class TestSeedDeterminism:
    def test_same_seed_same_trajectory(self):
        r1 = _run(300, 1.5, 4.0, seed=99)
        r2 = _run(300, 1.5, 4.0, seed=99)
        assert r1.data == r2.data

    def test_different_seed_different_trajectory(self):
        r1 = _run(300, 1.5, 4.0, seed=1)
        r2 = _run(300, 1.5, 4.0, seed=2)
        assert r1.data != r2.data

    def test_no_seed_is_seeded_non_reproducibly_but_valid(self):
        res = _run(200, 1.0, 2.0, seed=None)
        assert res.validation.flagged is False
        assert len(res.data) > 1


class TestEdgeCases:
    def test_k_zero_no_events(self):
        res = _run(50, 0.0, 10.0, seed=4)
        assert len(res.data) == 2          # initial + snapped final
        assert res.data[-1] == [10.0, 50, 0]

    def test_complete_decay_snaps_without_negative_counts(self):
        res = _run(10, 5.0, 10.0, seed=8)
        for row in res.data:
            assert row[1] >= 0 and row[2] >= 0

    def test_flag_below_plausible_population(self):
        res = _run(20, 1.0, 1.0, seed=5)
        assert res.validation.flagged is True
        assert "stochastic effects dominate" in res.validation.flag_reason

    def test_flag_above_plausible_rate(self):
        res = _run(100, 50.0, 0.5, seed=6)
        assert res.validation.flagged is True
        assert "dense random walk" in res.validation.flag_reason

    def test_validation_rejects_bad_params(self):
        with pytest.raises(ValueError):
            _run(0, 1.0, 1.0)
        with pytest.raises(ValueError):
            _run(-5, 1.0, 1.0)
        with pytest.raises(ValueError):
            _run(10, -0.1, 1.0)
        with pytest.raises(ValueError):
            _run(10, 1.0, -1.0)


class TestOutputContract:
    def test_column_names_and_model_name(self):
        res = _run(100, 1.0, 1.0, seed=2)
        assert res.colnames == ["time", "a", "b"]
        assert res.model_name == "gillespie_ssa"

    def test_rows_strictly_increasing_time(self):
        res = _run(1000, 1.0, 2.0, seed=11)
        times = [row[0] for row in res.data]
        assert all(t2 > t1 for t1, t2 in zip(times, times[1:]))

    def test_b_starts_zero_and_accumulates(self):
        res = _run(150, 0.7, 3.0, seed=12)
        assert res.data[0][2] == 0
        bs = [row[2] for row in res.data]
        assert all(b2 >= b1 for b1, b2 in zip(bs, bs[1:]))
