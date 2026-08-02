"""
Stage 7: the bimolecular SSA golden trajectory (A + B -> C).

Same discipline as the first-order golden (Stage 6 Part 2): a
fixed-seed trajectory pinned in full, with the random-number
consumption hand-verified against numpy's own stream:

    seed 12345, a0=60, b0=40, k=0.01, end=5.0
    u1 = np.random.default_rng(12345).uniform(0.0, 1.0)
    tau1 = -ln(u1) / (k * a0 * b0) = 0.06172192003509486  (hand-computed)
    engine first event: t = 0.06172192003509486            (must match)
    final row: [5.0, 24.0, 4.0, 36.0]   (a+c = a0, b+c = b0 on every row)

A fixed seed guarantees bit-identical output (ADR 0005), so the pinned
table is a mutation trap: any change to the sampling (propensity,
decrement pattern, RNG order) changes the trajectory and fails here.
"""

import math

import numpy as np

from Tellurium import tellurium_engine as te

GOLDEN = {
    "seed": 12345,
    "a0": 60,
    "b0": 40,
    "k": 0.01,
    "end": 5.0,
    "rows": 38,
    "first_event_time": 0.06172192003509486,
    "final": [5.0, 24.0, 4.0, 36.0],
}


def _run():
    return te.simulate_gillespie_ssa_bimolecular(
        a0=GOLDEN["a0"], b0=GOLDEN["b0"], k=GOLDEN["k"],
        end=GOLDEN["end"], seed=GOLDEN["seed"],
    )


class TestGoldenTrajectory:
    def test_golden_shape_is_bit_identical_on_rerun(self):
        assert _run().data == _run().data

    def test_golden_row_count(self):
        assert len(_run().data) == GOLDEN["rows"]

    def test_golden_initial_row(self):
        assert _run().data[0] == [0.0, GOLDEN["a0"], GOLDEN["b0"], 0]

    def test_golden_first_event(self):
        assert _run().data[1] == [
            GOLDEN["first_event_time"], GOLDEN["a0"] - 1,
            GOLDEN["b0"] - 1, 1.0,
        ]

    def test_golden_final_row(self):
        assert _run().data[-1] == GOLDEN["final"]

    def test_golden_conservation_every_row(self):
        for row in _run().data:
            assert row[1] + row[3] == GOLDEN["a0"]
            assert row[2] + row[3] == GOLDEN["b0"]


class TestHandVerification:
    """One uniform per event, tau = -ln(u)/(k*a*b), in numpy stream order."""

    def test_first_tau_equals_closed_form_from_numpy_stream(self):
        rng = np.random.default_rng(GOLDEN["seed"])
        u1 = rng.uniform(0.0, 1.0)
        tau1 = -math.log(u1) / (GOLDEN["k"] * GOLDEN["a0"] * GOLDEN["b0"])
        assert tau1 == GOLDEN["first_event_time"]
        assert _run().data[1][0] == tau1

    def test_second_tau_consumes_second_uniform(self):
        rng = np.random.default_rng(GOLDEN["seed"])
        u1 = rng.uniform(0.0, 1.0)
        u2 = rng.uniform(0.0, 1.0)
        tau1 = -math.log(u1) / (GOLDEN["k"] * GOLDEN["a0"] * GOLDEN["b0"])
        tau2 = -math.log(u2) / (GOLDEN["k"] * (GOLDEN["a0"] - 1) * (GOLDEN["b0"] - 1))
        assert _run().data[2][0] == tau1 + tau2


class TestMutationTraps:
    """Local copies of the Direct Method with one injected mutation each."""

    @staticmethod
    def _first_tau(tau_fn):
        rng = np.random.default_rng(GOLDEN["seed"])
        a, b = GOLDEN["a0"], GOLDEN["b0"]
        u = rng.uniform(0.0, 1.0)
        return tau_fn(u, GOLDEN["k"], a, b)

    def test_constant_propensity_mutation_is_detected(self):
        # Mutated: tau = -ln(u)/k (first-order style), not -ln(u)/(k*a*b)
        tau = self._first_tau(lambda u, k, a, b: -math.log(u) / k)
        assert tau != GOLDEN["first_event_time"]

    def test_first_order_mutation_is_detected(self):
        # Mutated: propensity k*a only (forgets B entirely)
        tau = self._first_tau(lambda u, k, a, b: -math.log(u) / (k * a))
        assert tau != GOLDEN["first_event_time"]

    def test_unequal_decrement_mutation_is_detected(self):
        # Mutated: each event destroys 2 A and 1 B -> a + c = a0 breaks.
        def tau_fn(u, k, a, b):
            return -math.log(u) / (k * a * b)

        rng = np.random.default_rng(GOLDEN["seed"])
        a, b, c, t = GOLDEN["a0"], GOLDEN["b0"], 0, 0.0
        while t < GOLDEN["end"] and a > 0 and b > 0:
            tau = tau_fn(rng.uniform(0.0, 1.0), GOLDEN["k"], a, b)
            t += tau
            if t >= GOLDEN["end"]:
                break
            a -= 2
            b -= 1
            c += 1
        assert a + c != GOLDEN["a0"]  # A-side conservation broken
