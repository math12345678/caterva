"""Bimolecular Gillespie SSA engine tests (ADR 0009, Stage 7).

Second-order association A + B -> C with propensity k*a*b. The
deterministic ODE reference is the closed form:

    a(t) = (a0 - b0) / (1 - (b0/a0) * exp(-k (a0 - b0) t))   for a0 != b0
    a(t) = a0 / (1 + k a0 t)                                 for a0 == b0

The stochastic mean tracks the ODE solution as counts grow; at small
counts the noise is the teaching point. Conservation a + c = a0 and
b + c = b0 hold on every row.
"""

from __future__ import annotations

import math

import pytest

from Tellurium import tellurium_engine as te


def _run(a0, b0, k, end, seed=1):
    return te.simulate_gillespie_ssa_bimolecular(a0=a0, b0=b0, k=k, end=end, seed=seed)


def _ode_a(t, a0, b0, k):
    """Deterministic solution for A(t) in A + B -> C."""
    if a0 == b0:
        return a0 / (1 + k * a0 * t)
    return (a0 - b0) / (1 - (b0 / a0) * math.exp(-k * (a0 - b0) * t))


class TestOdeReference:
    def test_mean_tracks_ode_for_unequal_stoichiometry(self):
        a0, b0, k, end = 4000, 3000, 1e-4, 10.0
        expected = _ode_a(end, a0, b0, k)
        finals = [_run(a0, b0, k, end, seed=s).data[-1][1] for s in range(40)]
        assert abs(sum(finals) / len(finals) - expected) < 0.03 * expected

    def test_mean_tracks_ode_for_equal_stoichiometry(self):
        a0, k, end = 3000, 2e-4, 10.0
        expected = _ode_a(end, a0, a0, k)
        finals = [_run(a0, a0, k, end, seed=s).data[-1][1] for s in range(40)]
        assert abs(sum(finals) / len(finals) - expected) < 0.03 * expected

    def test_ode_closed_form_sanity(self):
        # Reference implementation sanity: limits and monotonic decay.
        assert _ode_a(0, 10, 5, 0.1) == pytest.approx(10.0)
        assert _ode_a(1, 10, 10, 0.1) == pytest.approx(10 / (1 + 1.0))
        assert _ode_a(0, 10, 5, 0.1) > _ode_a(5, 10, 5, 0.1) > 0
        # Exhaustion: as t -> inf with a0 > b0, a -> a0 - b0.
        assert _ode_a(1e6, 10, 5, 0.1) == pytest.approx(5.0, rel=1e-3)


class TestConservation:
    def test_conservation_every_row(self):
        a0, b0 = 500, 300
        res = _run(a0, b0, 0.001, 20, seed=7)
        for row in res.data:
            a, b, c = row[1], row[2], row[3]
            assert a + c == a0
            assert b + c == b0

    def test_exhaustion_never_goes_negative(self):
        res = _run(8, 4, 0.05, 50, seed=3)
        for row in res.data:
            assert row[1] >= 0 and row[2] >= 0 and row[3] >= 0

    def test_stoichiometry_limiter_stops_at_minor_species(self):
        # b0 < a0: when B exhausts, C must equal b0 and B must hit 0.
        res = _run(50, 20, 0.01, 1000, seed=5)
        last = res.data[-1]
        assert last[2] == 0
        assert last[3] == 20
        assert last[1] == 30


class TestSeedDeterminism:
    def test_same_seed_same_trajectory(self):
        r1 = _run(100, 80, 0.005, 10, seed=99)
        r2 = _run(100, 80, 0.005, 10, seed=99)
        assert r1.data == r2.data

    def test_different_seed_different_trajectory(self):
        r1 = _run(100, 80, 0.005, 10, seed=1)
        r2 = _run(100, 80, 0.005, 10, seed=2)
        assert r1.data != r2.data


class TestEdgeCases:
    def test_k_zero_no_events(self):
        res = _run(50, 30, 0.0, 10, seed=4)
        assert len(res.data) == 2
        assert res.data[-1] == [10.0, 50, 30, 0]

    def test_flag_small_population(self):
        res = _run(20, 20, 0.01, 10, seed=6)
        assert res.validation.flagged is True
        assert "stochastic effects dominate" in res.validation.flag_reason

    def test_flag_high_rate(self):
        res = _run(100, 100, 5.0, 0.5, seed=6)
        assert res.validation.flagged is True
        assert "dense" in res.validation.flag_reason

    def test_validation_rejects_bad_params(self):
        with pytest.raises(ValueError):
            _run(0, 10, 0.01, 1.0)
        with pytest.raises(ValueError):
            _run(10, 0, 0.01, 1.0)
        with pytest.raises(ValueError):
            _run(10, 10, -0.01, 1.0)
        with pytest.raises(ValueError):
            _run(10, 10, 0.01, 0.0)
        with pytest.raises(ValueError):
            _run(10.5, 10, 0.01, 1.0)
        with pytest.raises(ValueError):
            _run(True, 10, 0.01, 1.0)


class TestOutputContract:
    def test_columns_and_model_name(self):
        res = _run(100, 50, 0.01, 5, seed=2)
        assert res.colnames == ["time", "a", "b", "c"]
        assert res.model_name == "gillespie_ssa_bimolecular"

    def test_rows_strictly_increasing_and_snapped(self):
        res = _run(200, 150, 0.002, 7, seed=11)
        times = [row[0] for row in res.data]
        assert all(t2 > t1 for t1, t2 in zip(times, times[1:]))
        assert res.data[0][0] == 0.0
        assert res.data[-1][0] == 7.0
