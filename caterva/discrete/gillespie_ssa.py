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


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


import math
from typing import List

import numpy as np

try:
    from caterva.core.data_structures import (
        ParameterValidation,  # type: ignore[no-redef]
        SimulationResult,  # type: ignore[no-redef]
    )
    from caterva.core.validation import (
        validate_ssa_bimolecular_params,  # type: ignore[no-redef]
        validate_ssa_params,  # type: ignore[no-redef]
        validate_ssa_replicates_params,  # type: ignore[no-redef]
    )
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.data_structures import (
        ParameterValidation,  # type: ignore[no-redef]
        SimulationResult,  # type: ignore[no-redef]
    )
    from core.validation import (
        validate_ssa_bimolecular_params,  # type: ignore[no-redef]
        validate_ssa_params,  # type: ignore[no-redef]
        validate_ssa_replicates_params,  # type: ignore[no-redef]
    )


def _run_first_order_once(a0: int, k: float, end: float, rng) -> List[List[float]]:
    """One first-order SSA trajectory (columns time, a, b) from a given RNG."""
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
    return data


def _run_bimolecular_once(
    a0: int, b0: int, k: float, end: float, rng
) -> List[List[float]]:
    """One bimolecular SSA trajectory (columns time, a, b, c) from an RNG."""
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
    return data


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
    data = _run_first_order_once(int(a0), k, end, rng)

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
    data = _run_bimolecular_once(int(a0), int(b0), k, end, rng)

    return SimulationResult(
        colnames=["time", "a", "b", "c"],
        data=data,
        model_name="gillespie_ssa_bimolecular",
        validation=validation,
    )


def _merge_validations(
    reaction: ParameterValidation, replicates: ParameterValidation
) -> ParameterValidation:
    """Combine a reaction validation with the replicate-count validation.

    A rejection in either is a rejection; flag reasons are joined so the
    student sees every implausibility at once.
    """
    if not reaction.ok or not replicates.ok:
        return ParameterValidation(ok=False, errors=reaction.errors + replicates.errors)
    if reaction.flagged or replicates.flagged:
        reasons = [r for r in (reaction.flag_reason, replicates.flag_reason) if r]
        return ParameterValidation(ok=True, flagged=True, flag_reason=" ".join(reasons))
    return ParameterValidation()


def _step_sample(times: np.ndarray, values: np.ndarray,
                 grid: np.ndarray) -> np.ndarray:
    """Sample a right-continuous STEP function onto a uniform grid.

    An SSA trajectory is piecewise constant: the molecule count set by an
    event holds until the next event fires. The value at grid time t is
    therefore the value at the most recent event at or before t -- a
    zero-order hold.

    This replaced ``np.interp``, which draws a straight line between event
    values and so reports counts the system never held. For a monotonically
    decreasing species the error is one-sided, making it a systematic BIAS
    rather than noise, and averaging more replicates cannot remove it.

    Measured against the exact closed form E[a(t)] = a0*exp(-k*t)
    (a0=100, k=0.5, end=10, seed=7), interpolated vs. true mean over
    0.5 < t < 6:

        replicates    mean bias        worst deviation
               500    -0.66 molecules  -6.6 sigma
              2000    -0.53 molecules  -10.9 sigma
              8000    -0.48 molecules  -18.2 sigma

    The bias plateaus while the standard error keeps shrinking, so the
    result got *more* conclusively wrong as the ensemble grew -- the
    opposite of what an ensemble average is for.
    """
    # side="right" gives the first index strictly after t; -1 steps back to
    # the last event at or before t. Clipped at 0 so a grid point at t=0
    # (before or at the first recorded time) takes the initial state.
    indices = np.searchsorted(times, grid, side="right") - 1
    np.clip(indices, 0, len(values) - 1, out=indices)
    return values[indices]


def simulate_gillespie_ssa_replicates(
    a0: float,
    k: float,
    end: float,
    n_replicates: int,
    seed: int | None = None,
    b0: float | None = None,
) -> SimulationResult:
    """Simulate the SSA ensemble view: ``n_replicates`` independent runs.

    The teaching purpose is comparing the *sample* mean and spread of
    the stochastic process against the deterministic reference. Each
    replicate is an independent SSA trajectory; the returned mean
    trajectory is the sample mean of the step functions on a fixed
    uniform time grid, and ``replicate_data`` holds each replicate's
    final counts.

    Args:
        a0: initial number of A molecules (positive integer)
        k: rate constant (first-order per molecule, or second-order per
            molecule pair when ``b0`` is given)
        end: simulation time horizon
        n_replicates: number of independent trajectories (positive
            integer)
        seed: RNG seed for the whole ensemble (ADR 0005). Replicate rngs
            are derived deterministically: the master
            ``numpy.random.default_rng(seed)`` draws one 63-bit integer
            per replicate, and each replicate uses
            ``numpy.random.default_rng(that integer)``. A fixed seed
            therefore reproduces the entire ensemble bit-identically.
        b0: when given, simulate the bimolecular association
            ``A + B -> C`` instead of first-order decay

    Returns:
        SimulationResult with mean-trajectory columns
        ``["time", "mean_a", "mean_b"]`` (plus ``"mean_c"`` when
        ``b0`` is given) on a 101-point grid from 0 to ``end``,
        ``replicate_colnames`` of final counts and ``replicate_data``
        one row per replicate.

    Raises:
        ModelBuildError: if parameters are invalid
    """
    if b0 is None:
        reaction_validation = validate_ssa_params(a0, k, end)
    else:
        reaction_validation = validate_ssa_bimolecular_params(a0, b0, k, end)
    replicate_validation = validate_ssa_replicates_params(n_replicates)
    validation = _merge_validations(reaction_validation, replicate_validation)
    validation.raise_if_invalid()

    master = np.random.default_rng(seed)
    replicate_seeds_arr = master.integers(0, 2**63, size=int(n_replicates))
    replicate_seeds = [int(s) for s in replicate_seeds_arr]

    if b0 is None:
        colnames = ["time", "mean_a", "mean_b"]
        replicate_colnames = ["final_a"]
    else:
        colnames = ["time", "mean_a", "mean_b", "mean_c"]
        replicate_colnames = ["final_a", "final_b", "final_c"]

    grid = np.linspace(0.0, float(end), 101)
    mean_a = np.zeros_like(grid)
    mean_b = np.zeros_like(grid)
    mean_c = np.zeros_like(grid)
    replicate_data: List[List[float]] = []

    for rep_seed in replicate_seeds:
        rep_rng = np.random.default_rng(rep_seed)
        if b0 is None:
            rows = _run_first_order_once(int(a0), k, end, rep_rng)
            finals = [rows[-1][1]]
            replicate_data.append(finals)
            times = np.array([row[0] for row in rows])
            a_col = np.array([row[1] for row in rows])
            b_col = np.array([row[2] for row in rows])
            mean_a += _step_sample(times, a_col, grid)
            mean_b += _step_sample(times, b_col, grid)
        else:
            rows = _run_bimolecular_once(int(a0), int(b0), k, end, rep_rng)
            replicate_data.append([rows[-1][1], rows[-1][2], rows[-1][3]])
            times = np.array([row[0] for row in rows])
            a_col = np.array([row[1] for row in rows])
            b_col = np.array([row[2] for row in rows])
            c_col = np.array([row[3] for row in rows])
            mean_a += _step_sample(times, a_col, grid)
            mean_b += _step_sample(times, b_col, grid)
            mean_c += _step_sample(times, c_col, grid)

    n = int(n_replicates)
    data: List[List[float]] = []
    for i, t in enumerate(grid):
        row = [float(t), float(mean_a[i] / n), float(mean_b[i] / n)]
        if b0 is not None:
            row.append(float(mean_c[i] / n))
        data.append(row)

    return SimulationResult(
        colnames=colnames,
        data=data,
        model_name=(
            "gillespie_ssa_bimolecular_replicates"
            if b0 is not None else "gillespie_ssa_replicates"),
        validation=validation,
        replicate_data=replicate_data,
        replicate_colnames=replicate_colnames,
    )
