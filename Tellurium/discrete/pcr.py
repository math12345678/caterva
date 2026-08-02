"""Discrete PCR amplification (deterministic recurrence, ADR 0002)."""

from __future__ import annotations

from typing import List, Optional

try:
    from Tellurium.core.data_structures import (ModelBuildError, SimulationResult)
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ModelBuildError, SimulationResult)  # type: ignore[no-redef]

try:
    from Tellurium.core.validation import _finite_positive, validate_pcr_params
except ModuleNotFoundError:
    from core.validation import _finite_positive, validate_pcr_params  # type: ignore[no-redef]

def simulate_pcr(n0: float, efficiency: float, cycles: int,
                 plateau_capacity: Optional[float] = None) -> SimulationResult:
    """Simulate PCR amplification over a fixed number of cycles.

    Without a plateau capacity, copy number follows the exact closed form
    ``N(c) = n0 * (1 + efficiency) ** c`` -- unbounded exponential growth,
    the textbook idealization.

    With a plateau capacity (reagents exhausted, polymerase saturated), the
    recurrence switches to discrete logistic growth:
    ``N(c+1) = N(c) + efficiency * N(c) * (1 - N(c) / capacity)``, which
    approaches but never exceeds ``capacity`` -- the real-world qPCR
    amplification curve shape (exponential phase, then plateau).

    Args:
        n0: initial template copy number
        efficiency: fraction of template copied per cycle, in [0, 1]
        cycles: number of PCR cycles to simulate
        plateau_capacity: if given, the copy number ceiling the reaction
            saturates toward; if omitted, growth is unbounded exponential

    Returns:
        SimulationResult with columns ["cycle", "copies"], one row per cycle
        from 0 to ``cycles`` inclusive.

    Raises:
        ModelBuildError: if parameters are invalid
    """
    validation = validate_pcr_params(n0, efficiency, cycles)
    validation.raise_if_invalid()

    if plateau_capacity is not None:
        if not _finite_positive(plateau_capacity, "plateau_capacity", []):
            raise ModelBuildError(
                f"plateau_capacity must be finite and positive, got "
                f"{plateau_capacity}")
        if plateau_capacity < n0:
            raise ModelBuildError(
                f"plateau_capacity ({plateau_capacity}) must be >= n0 ({n0})")

    copies = float(n0)
    data: List[List[float]] = [[0.0, copies]]
    for cycle in range(1, cycles + 1):
        if plateau_capacity is None:
            copies = n0 * (1.0 + efficiency) ** cycle
        else:
            copies = copies + efficiency * copies * (1.0 - copies / plateau_capacity)
        data.append([float(cycle), copies])

    return SimulationResult(
        colnames=["cycle", "copies"],
        data=data,
        model_name="pcr_amplification",
        validation=validation,
    )
