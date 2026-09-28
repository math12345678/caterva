"""Tests moved from caterva/tests/test_network_provenance.py on 2026-09-27 with their domains."""

def test_every_problem_is_reported_at_once() -> None:
    """A caller assembling a model wants the whole list.

    Reporting the first failure turns one fix into a sequence of them, and
    a person fixing a model one error at a time stops reading the errors.
    """
    network = sir_network(0.5761, 0.1835, 999.0, 1.0, 0.0)
    problems = unsourced_quantities(network, {})
    # S, I, R, beta, gamma_rate, N -- all six, not just the first.
    assert len(problems) == len(network.quantity_ids()) == 6


