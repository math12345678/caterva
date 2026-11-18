"""The main path's answer, checked against an exact solution.

A Michaelis-Menten reaction has a closed-form time course (Schnell and
Mendoza, 1997): S(t) = Km * W((S0 / Km) * exp((S0 - Vmax * t) / Km)), with W
the Lambert W function and Vmax = kcat * E. This test builds the model the
way a user does -- from a sentence -- integrates it with Caterva's own
window, and compares every point with that formula, computed by SciPy and
not by anything in Caterva. It is checked against an independent answer,
never against Caterva's own earlier output.

It also pins the window: the curve must show the reaction to the end, not
the first tenth of it (human LDH used to stop at t=1.2 with 12% converted).
"""

from __future__ import annotations

import math

import pytest

from caterva.compose.pipeline import compose
from caterva.compose.simulate import run

pytest.importorskip("roadrunner", reason="the time course needs the engine")
special = pytest.importorskip("scipy.special")


def _value(network, name: str) -> float:
    for parameter in network.parameters:
        if parameter.id == name:
            return float(parameter.value)
    for species in network.species:
        if species.id == name:
            return float(species.initial)
    raise KeyError(name)


def _exact_substrate(t: float, s0: float, km: float, vmax: float) -> float:
    argument = (s0 / km) * math.exp((s0 - vmax * t) / km)
    return km * float(special.lambertw(argument).real)


@pytest.mark.parametrize("sentence", [
    "an enzyme converts a substrate to a product",
    "Michaelis-Menten kinetics",
])
def test_the_time_course_is_the_exact_michaelis_menten_solution(sentence: str) -> None:
    model = compose(sentence)
    network = model.network
    km = _value(network, "reaction_Km")
    kcat = _value(network, "reaction_kcat")
    enzyme = _value(network, "reaction_E")
    s0 = _value(network, "reaction_S")
    vmax = kcat * enzyme

    trajectory = run(model)
    substrate = trajectory.columns["reaction_S"]

    worst = 0.0
    for t, simulated in zip(trajectory.times, substrate):
        exact = _exact_substrate(t, s0, km, vmax)
        worst = max(worst, abs(simulated - exact))
    assert worst <= 1e-5 * s0, f"largest gap from the exact solution: {worst:g} (S0={s0:g})"

    # The window shows the whole reaction: at least 99% of the substrate is
    # gone by the end, by the exact solution's own account.
    assert _exact_substrate(trajectory.end, s0, km, vmax) <= 0.01 * s0
    assert substrate[-1] <= 0.01 * s0


def test_a_saturated_enzyme_gets_a_window_long_enough_to_finish() -> None:
    """Km far below S0: the near-equilibrium timescale Km / Vmax is a
    small fraction of the S0 / Vmax the reaction actually takes."""
    model = compose("Michaelis-Menten kinetics")
    network = model.network
    km = _value(network, "reaction_Km")
    s0 = _value(network, "reaction_S")
    vmax = _value(network, "reaction_kcat") * _value(network, "reaction_E")
    if s0 / km < 5:
        pytest.skip("the library's default is not saturating; nothing to pin")
    trajectory = run(model)
    assert trajectory.end >= s0 / vmax
    assert "lengthened" in trajectory.window_basis
