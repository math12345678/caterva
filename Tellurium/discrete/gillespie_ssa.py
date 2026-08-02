"""Gillespie stochastic simulation algorithm (SSA): exact reaction kinetics.

Two reaction types (ADR 0009):

1. First-order decay ``A -> B`` with rate constant ``k`` (per molecule,
   per time unit). A population of ``a0`` molecules of A decays
   stochastically; B is conserved: ``b = a0 - a``.
2. Bimolecular association ``A + B -> C`` (second order, propensity
   ``k * a * b``, rate per molecule pair per time unit). The
   deterministic ODE solution is the reference trajectory:

   ``a(t) = (a0 - b0) / (1 - (b0/a0) * exp(-k (a0 - b0) t))``  for a0 != b0
   ``a(t) = a0 / (1 + k a0 t)``                                for a0 == b0

The exact SSA (Gillespie's Direct Method) samples, for each reaction
event, the waiting time ``tau = -ln(u1) / propensity`` and the reaction
itself — with a single reaction the choice is trivial. First-order
trajectories follow the closed form ``E[a(t)] = a0 * exp(-k t)``;
individual trajectories are discrete and noisy, which is the point of
the domain.

RNG: ``numpy.random.default_rng(seed)`` per ADR 0005; a fixed seed gives
bit-identical trajectories.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

import numpy as np

try:
    from Tellurium.core.data_structures import (ModelBuildError, SimulationResult)
    from Tellurium.core.validation import (
        validate_ssa_bimolecular_params,
        validate_ssa_params,
    )
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ModelBuildError, SimulationResult)
    from core.validation import (
        validate_ssa_bimolecular_params,
        validate_ssa_params,
    )


def simulate_gillespie_ssa(
    a0: float,
    k: float,
    end: float,
    seed: int | None = None,
) -> SimulationResult:
    """Simulate first-order decay ``A -> B`` with the exact SSA.

    Args:
        a0: initial number of A molecules (positive integer)
        k: first-order rate constant, per molecule per time unit (>= 0)
        end: simulation time horizon
        seed: RNG seed for the trajectory (ADR 0005)

    Returns:
        SimulationResult with columns ["time", "a", "b"], one row per
        reaction event plus the initial point at t=0 and a final point
        snapped to ``end``. A is a step function of the number of A
        molecules surviving at each event time.

    Raises:
        ModelBuildError: if parameters are invalid
    """
    validation = validate_ssa_params(a0, k, end)
    validation.raise_if_invalid()

    rng = np.random.default_rng(seed)

    a = int(a0)
    b = 0
    t = 0.0
    data: List[List[float]] = [[0.0, float(a), float(b)]]

    # k == 0: propensity is identically zero, no reaction ever fires.
    while t < end and a > 0 and k > 0:
        propensity = k * a
        tau = -math.log(rng.uniform(0.0, 1.0)) / propensity
        if t + tau > end:
            break
        t += tau
        a -= 1
        b += 1
        data.append([t, float(a), float(b)])

    # Final row snapped to the horizon, so the trajectory is comparable
    # across domains (all other engines include their endpoint).
    data.append([float(end), float(a), float(b)])

    return SimulationResult(
        colnames=["time", "a", "b"],
        data=data,
        model_name="gillespie_ssa",
        validation=validation,
    )


def simulate_gillespie_ssa_bimolecular(
    a0: float,
    b0: float,
    k: float,
    end: float,
    seed: int | None = None,
) -> SimulationResult:
    """Simulate bimolecular association ``A + B -> C`` with the exact SSA.

    Args:
        a0: initial number of A molecules (positive integer)
        b0: initial number of B molecules (positive integer)
        k: second-order rate constant, per molecule pair per time unit (>= 0)
        end: simulation time horizon
        seed: RNG seed for the trajectory (ADR 0005)

    Returns:
        SimulationResult with columns ["time", "a", "b", "c"], one row per
        reaction event plus the initial point at t=0 and a final point
        snapped to ``end``. Conservation ``a + c == a0`` and
        ``b + c == b0`` hold on every row.

    Raises:
        ModelBuildError: if parameters are invalid
    """
    validation = validate_ssa_bimolecular_params(a0, b0, k, end)
    validation.raise_if_invalid()

    rng = np.random.default_rng(seed)

    a = int(a0)
    b = int(b0)
    c = 0
    t = 0.0
    data: List[List[float]] = [[0.0, float(a), float(b), float(c)]]

    # k == 0 or either species exhausted: propensity is zero, no event.
    while t < end and a > 0 and b > 0 and k > 0:
        propensity = k * a * b
        tau = -math.log(rng.uniform(0.0, 1.0)) / propensity
        if t + tau > end:
            break
        t += tau
        a -= 1
        b -= 1
        c += 1
        data.append([t, float(a), float(b), float(c)])

    data.append([float(end), float(a), float(b), float(c)])

    return SimulationResult(
        colnames=["time", "a", "b", "c"],
        data=data,
        model_name="gillespie_ssa_bimolecular",
        validation=validation,
    )
