"""
Stage 6 Part 2: the SSA golden trajectory.

For provenance-style domains (mm/sir/...) the golden set pins
hand-verified *literature* values. The SSA domain has no literature
lookup — its ground truth is the stochastic algorithm itself plus the
closed form. The golden here is a fixed-seed trajectory, pinned in
full, with the random-number consumption hand-verified against numpy's
own stream:

    seed 12345, a0=100, k=0.5, end=3.0
    u1 = np.random.default_rng(12345).uniform(0.0, 1.0)
    tau1 = -ln(u1) / (k * a0) = 0.029626521616845532  (hand-computed)
    engine first event: t = 0.029626521616845532      (must match)
    final row: [3.0, 24.0, 76.0]   (a+b = a0 on every row)

A fixed seed guarantees bit-identical output (ADR 0005), so the pinned
table doubles as a mutation trap: any change to the sampling (propensity,
event decrement, RNG consumption order) changes the trajectory and this
suite fails.
"""

import math

import numpy as np

from caterva import caterva_engine as te

GOLDEN = {
    "seed": 12345,
    "a0": 100,
    "k": 0.5,
    "end": 3.0,
    "rows": 78,
    "first_event_time": 0.029626521616845532,
    "second_event_time": 0.052851089922515,
    "final": [3.0, 24.0, 76.0],
}


def _run():
    return te.simulate_gillespie_ssa(
        a0=GOLDEN["a0"], k=GOLDEN["k"], end=GOLDEN["end"], seed=GOLDEN["seed"]
    )


class TestGoldenTrajectory:
    def test_golden_shape_is_bit_identical_on_rerun(self):
        r1 = _run()
        r2 = _run()
        assert r1.data == r2.data  # ADR 0005: bit-identical

    def test_golden_row_count(self):
        assert len(_run().data) == GOLDEN["rows"]

    def test_golden_initial_row(self):
        assert _run().data[0] == [0.0, GOLDEN["a0"], 0]

    def test_golden_first_two_event_times(self):
        res = _run()
        assert res.data[1][0] == GOLDEN["first_event_time"]
        assert res.data[2][0] == GOLDEN["second_event_time"]

    def test_golden_final_row(self):
        assert _run().data[-1] == GOLDEN["final"]

    def test_golden_conservation_every_row(self):
        for row in _run().data:
            assert row[1] + row[2] == GOLDEN["a0"]


class TestHandVerification:
    """The engine consumes uniforms in the documented order: one draw per
    event, tau = -ln(u)/(k*a). Re-derive the first tau from numpy's own
    stream for this seed and compare."""

    def test_first_tau_equals_closed_form_from_numpy_stream(self):
        rng = np.random.default_rng(GOLDEN["seed"])
        u1 = rng.uniform(0.0, 1.0)
        tau1 = -math.log(u1) / (GOLDEN["k"] * GOLDEN["a0"])
        assert tau1 == GOLDEN["first_event_time"]
        assert _run().data[1][0] == tau1

    def test_second_tau_consumes_second_uniform(self):
        # Event times in the data are cumulative: data[2][0] = tau1 + tau2.
        rng = np.random.default_rng(GOLDEN["seed"])
        u1 = rng.uniform(0.0, 1.0)
        u2 = rng.uniform(0.0, 1.0)
        tau1 = -math.log(u1) / (GOLDEN["k"] * GOLDEN["a0"])
        tau2 = -math.log(u2) / (GOLDEN["k"] * (GOLDEN["a0"] - 1))
        assert _run().data[2][0] == pytest.approx(tau1 + tau2, rel=1e-15)


class TestMutationTraps:
    """Local copies of the Direct Method with a single injected mutation.
    Each must break the golden (the pinned table is the tripwire)."""

    @staticmethod
    def _mutated(first_tau_fn):
        """Run the loop with a swapped tau function; return the first event time."""
        a0, k, end = GOLDEN["a0"], GOLDEN["k"], GOLDEN["end"]
        rng = np.random.default_rng(GOLDEN["seed"])
        t, a = 0.0, float(a0)
        first = None
        while t < end and a > 0 and k > 0:
            u = rng.uniform(0.0, 1.0)
            t += first_tau_fn(u, k, a)
            if t >= end:
                break
            if first is None:
                first = t
            a -= 1
        return first

    def test_constant_propensity_mutation_is_detected(self):
        # Mutated: tau = -ln(u)/k (constant propensity), not -ln(u)/(k*a)
        first_tau = self._mutated(lambda u, k, a: -math.log(u) / k)
        assert first_tau != GOLDEN["first_event_time"]

    def test_wrong_rate_constant_mutation_is_detected(self):
        # Mutated: propensity k*(a-1) (off-by-one after decrement)
        first_tau = self._mutated(lambda u, k, a: -math.log(u) / (k * (a - 1)))
        assert first_tau != GOLDEN["first_event_time"]

    def test_double_decrement_mutation_is_detected(self):
        # Mutated: each event destroys 2 molecules. a+b stays == a0 by
        # construction (both change by 2), so the tripwire is the golden
        # final state / event count, not conservation.
        def tau_fn(u, k, a):
            return -math.log(u) / (k * a)

        a0, k, end = GOLDEN["a0"], GOLDEN["k"], GOLDEN["end"]
        rng = np.random.default_rng(GOLDEN["seed"])
        t, a, b = 0.0, float(a0), 0.0
        n_events = 0
        while t < end and a > 0 and k > 0:
            tau = tau_fn(rng.uniform(0.0, 1.0), k, a)
            t += tau
            if t >= end:
                break
            a -= 2
            b += 2
            n_events += 1
        # 2x events consumed -> fewer events and a different final A than the
        # golden (76 events -> final a=24; the mutation yields fewer, larger
        # decrements).
        assert n_events != GOLDEN["rows"] - 2
        assert a != GOLDEN["final"][1]


class TestCli:
    """The `ssa` CLI subcommand wraps the engine; smoke-test the wiring."""

    def _run_cli(self, *args: str):
        import subprocess
        import sys
        from pathlib import Path

        return subprocess.run(
            [sys.executable, "-m", "caterva.cli", "ssa", *args],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )

    def test_cli_prints_events_and_closed_form(self):
        proc = self._run_cli("--a0", "200", "--k", "0.5", "--end", "5", "--seed", "9")
        assert proc.returncode == 0
        assert "time" in proc.stdout and "expected B(end)" in proc.stdout
        # seeded golden: 190 events, final A 10 (matches the pinned run above)
        assert "events = 190" in proc.stdout
        assert "final A = 10" in proc.stdout

    def test_cli_rejects_invalid_params(self):
        proc = self._run_cli("--a0", "0")
        assert proc.returncode == 1
        assert "error:" in proc.stderr


import pytest  # noqa: E402  (used by TestHandVerification)
