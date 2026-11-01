"""Tests moved from caterva/tests/test_network_equivalence.py on 2026-09-27 with their domains."""

CASES = [
    (
        "michaelis_menten",
        mm_network(2.0, 5.0, 10.0),
        lambda: simulate_michaelis_menten(2.0, 5.0, 10.0, START, END, POINTS),
    ),
    (
        "mm_competitive_inhibition",
        mm_competitive_network(2.0, 5.0, 1.0, 10.0, 0.5),
        lambda: simulate_mm_competitive_inhibition(
            2.0, 5.0, 1.0, 10.0, 0.5, START, END, POINTS
        ),
    ),
    (
        "sir",
        sir_network(0.5761, 0.1835, 999.0, 1.0, 0.0),
        lambda: simulate_sir(
            0.5761, 0.1835, 999.0, 1.0, 0.0, START, END, POINTS
        ),
    ),
    (
        "seir",
        seir_network(0.5, 0.2, 0.1, 990.0, 5.0, 5.0, 0.0),
        lambda: simulate_seir(
            0.5, 0.2, 0.1, 990.0, 5.0, 5.0, 0.0, START, END, POINTS
        ),
    ),
    (
        "lotka_volterra",
        lotka_volterra_network(1.1, 0.4, 0.1, 0.4, 10.0, 5.0),
        lambda: simulate_lotka_volterra(
            1.1, 0.4, 0.1, 0.4, 10.0, 5.0, START, END, POINTS
        ),
    ),
    (
        "cell_cycle_oscillator",
        cell_cycle_oscillator_network(),
        lambda: simulate_cell_cycle_oscillator(START, END, POINTS),
    ),
    (
        "repressilator",
        repressilator_network(),
        lambda: simulate_repressilator(START, END, POINTS),
    ),
]


