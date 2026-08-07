"""The SSA ensemble (replicates) view — Stage 7 Part 2.

``simulate_gillespie_ssa_replicates`` runs ``n_replicates`` independent
SSA trajectories from one master seed (ADR 0005) and returns the sample
mean trajectory on a fixed grid plus per-replicate final counts. The
teaching claim: as the replicate count grows, the sample mean converges
to the deterministic reference — for first-order decay the final count
is exactly Binomial(a0, e^{-kt}), so both the mean and the standard
deviation have closed forms.
"""

import math

import numpy as np

from Tellurium import tellurium_engine as te

A0, K, END = 200, 0.5, 4.0
P = math.exp(-K * END)  # survival probability per molecule
THEORY_MEAN_FINAL_A = A0 * P
THEORY_SD_FINAL_A = math.sqrt(A0 * P * (1.0 - P))


def _run(n_replicates, seed=12345, a0=A0, k=K, end=END):
    return te.simulate_gillespie_ssa_replicates(
        a0=a0, k=k, end=end, n_replicates=n_replicates, seed=seed)


class TestMeanTrajectory:
    def test_grid_is_101_uniform_points_0_to_end(self):
        r = _run(50)
        times = [row[0] for row in r.data]
        assert len(times) == 101
        assert times[0] == 0.0 and times[-1] == END
        spacing = times[1] - times[0]
        assert all(abs((b - a) - spacing) < 1e-12 for a, b in zip(times, times[1:]))

    def test_mean_columns_are_consistent(self):
        r = _run(50)
        for row in r.data:
            assert abs(row[1] + row[2] - A0) < 1e-9  # mean_a + mean_b == a0

    def test_mean_final_a_agrees_with_binomial_mean(self):
        r = _run(400)
        mean_final = sum(x[0] for x in r.replicate_data) / 400
        sd_of_mean = THEORY_SD_FINAL_A / math.sqrt(400)
        assert abs(mean_final - THEORY_MEAN_FINAL_A) < 3 * sd_of_mean

    def test_mean_trajectory_matches_mean_of_finals_at_end(self):
        r = _run(100)
        mean_final = sum(x[0] for x in r.replicate_data) / 100
        assert abs(r.data[-1][1] - mean_final) < 1e-9

    def test_mean_trajectory_tracks_closed_form_on_interior_grid(self):
        """Sample mean of intermediate grid points matches a0 e^{-kt}.

        Per replicate the count at time t is Binomial(A0, e^{-kt}), so the
        ensemble mean is a0 e^{-kt} for every t on the grid, not just the
        horizon. With N replicates the SE of the sample mean at t is
        sqrt(a0 p (1-p) / N) with p = e^{-kt}; each interior checkpoint is
        checked within 3 sigma. A bug that only shifted mid-trajectory
        mean_a (e.g. an interpolation or drift error between the endpoints)
        would fail here while all end-to-end mean tests still pass.
        """
        a0, k, end, n_reps = 200, 0.5, 4.0, 400
        r = te.simulate_gillespie_ssa_replicates(
            a0=a0, k=k, end=end, n_replicates=n_reps, seed=12345)
        grid = np.linspace(0.0, float(end), len(r.data))
        for idx in (10, 50, 75, 100):
            t = grid[idx]
            p = math.exp(-k * t)
            theory = a0 * p
            se = math.sqrt(a0 * p * (1.0 - p) / n_reps)
            stat = abs(r.data[idx][1] - theory) / se
            assert stat < 3.0, (
                f"t={t:.2f}: mean_a={r.data[idx][1]:.3f} vs closed form "
                f"{theory:.3f} ({stat:.1f} sigma)")


class TestSpread:
    def test_sample_sd_approaches_binomial_sd(self):
        r = _run(400)
        finals = np.array([x[0] for x in r.replicate_data])
        obs_sd = finals.std(ddof=1)
        assert abs(obs_sd - THEORY_SD_FINAL_A) < 0.5 * THEORY_SD_FINAL_A

    def test_finals_fill_more_than_two_distinct_values(self):
        """A degenerate ensemble (all identical finals) would be broken."""
        r = _run(200)
        finals = {x[0] for x in r.replicate_data}
        assert len(finals) > 2


class TestDeterminism:
    def test_same_seed_bit_identical_ensemble(self):
        r1 = _run(100, seed=7)
        r2 = _run(100, seed=7)
        assert r1.data == r2.data
        assert r1.replicate_data == r2.replicate_data

    def test_different_seeds_diverge(self):
        assert _run(50, seed=1).replicate_data != _run(50, seed=2).replicate_data

    def test_derived_replicate_seeds_are_documented(self):
        """Master seed -> one 63-bit integer per replicate, in order."""
        master = np.random.default_rng(12345)
        derived = [int(s) for s in master.integers(0, 2**63, size=3)]
        r = _run(3, seed=12345)
        assert len(r.replicate_data) == 3
        # The first derived seed is pinned as the documented derivation;
        # re-running the derivation above must reproduce it exactly.
        assert derived[0] == 2096804712593481934
        assert derived[1] == 2921580012919480943
        assert derived[2] == 7354398262316660716


class TestBimolecularMode:
    def test_mean_final_a_approaches_ode_reference(self):
        a0, b0, k, end = 60, 40, 0.01, 5.0
        r = te.simulate_gillespie_ssa_replicates(
            a0=a0, b0=b0, k=k, end=end, n_replicates=400, seed=12345)
        expected = (a0 - b0) / (1.0 - (b0 / a0) * math.exp(-k * (a0 - b0) * end))
        mean_final = sum(x[0] for x in r.replicate_data) / 400
        assert abs(mean_final - expected) < 1.0

    def test_bimolecular_columns_and_conservation_of_means(self):
        r = te.simulate_gillespie_ssa_replicates(
            a0=60, b0=40, k=0.01, end=5.0, n_replicates=50, seed=9)
        assert r.colnames == ["time", "mean_a", "mean_b", "mean_c"]
        assert r.replicate_colnames == ["final_a", "final_b", "final_c"]
        for row in r.data:
            assert abs(row[1] + row[3] - 60) < 1e-9
            assert abs(row[2] + row[3] - 40) < 1e-9

    def test_bimolecular_finals_conserve_per_replicate(self):
        r = te.simulate_gillespie_ssa_replicates(
            a0=60, b0=40, k=0.01, end=5.0, n_replicates=50, seed=3)
        for row in r.replicate_data:
            assert row[0] + row[2] == 60
            assert row[1] + row[2] == 40


class TestValidation:
    def test_few_replicates_flags(self):
        r = _run(5)
        assert r.flagged is True
        assert "n_replicates" in r.validation.flag_reason

    def test_small_population_flag_merges_with_replicate_flag(self):
        r = te.simulate_gillespie_ssa_replicates(
            a0=10, k=0.5, end=2.0, n_replicates=5, seed=1)
        assert r.flagged is True
        assert "a0=10" in r.validation.flag_reason
        assert "n_replicates=5" in r.validation.flag_reason

    def test_accepts_nominal(self):
        r = _run(100)
        assert r.flagged is False and r.validation.ok is True

    def test_rejects_invalid_replicate_counts(self):
        for bad in (0, -1, 2.5, True, "ten"):
            try:
                te.simulate_gillespie_ssa_replicates(
                    a0=100, k=0.5, end=2.0, n_replicates=bad)
            except ValueError:
                continue
            raise AssertionError(f"n_replicates={bad!r} was not rejected")

    def test_rejects_invalid_reaction_params(self):
        try:
            te.simulate_gillespie_ssa_replicates(a0=0, k=0.5, end=2.0, n_replicates=10)
        except ValueError:
            pass
        else:
            raise AssertionError("a0=0 was not rejected")


class TestOutputContract:
    def test_single_replicate_ensemble_has_one_row(self):
        r = _run(1, seed=12345)
        assert len(r.replicate_data) == 1
        assert r.data[-1][1] == r.replicate_data[0][0]

    def test_to_dict_round_trip_includes_replicates(self):
        r = _run(10)
        d = r.to_dict()
        assert d["replicate_data"] is not None
        assert d["replicate_colnames"] == ["final_a"]
