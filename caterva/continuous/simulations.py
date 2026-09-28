"""Continuous-domain simulation entry points (ODE via roadrunner)."""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


from typing import Dict, Iterable, List, Sequence

try:
    from caterva.core.data_structures import (ParameterValidation, SimulationError, SimulationResult)  # type: ignore[no-redef]
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.data_structures import (ParameterValidation, SimulationError, SimulationResult)  # type: ignore[no-redef]

try:
    from caterva.core.utils import _load_runner  # type: ignore[no-redef]
    from caterva.core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params)  # type: ignore[no-redef]
    from caterva.continuous.model_building import (
        build_michaelis_menten_antimony, build_mm_competitive_antimony,
        antimony_to_sbml)  # type: ignore[no-redef]
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.utils import _load_runner  # type: ignore[no-redef]
    from core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params)  # type: ignore[no-redef]
    from continuous.model_building import (
        build_michaelis_menten_antimony, build_mm_competitive_antimony,
        antimony_to_sbml)  # type: ignore[no-redef]

def simulate_sbml(sbml_string: str, start: float = 0.0, end: float = 10.0,
                   points: int = 51,
                   selections: Sequence[str] | None = None,
                   model_name: str = "model",
                   validation: ParameterValidation | None = None
                   ) -> SimulationResult:
    """Integrate an SBML model and return a SimulationResult.
    
    This is the core simulation function that uses the RoadRunner engine
    to numerically integrate an SBML model. The function handles parameter
    validation, selections, and error handling for robust simulation.
    
    Args:
        sbml_string: A valid SBML document as a string
        start: Start time for the simulation (default: 0.0)
        end: End time for the simulation (must be > start)
        points: Number of time points to simulate (must be >= 2)
        selections: Optional list of species to include in output
        model_name: Name to assign to this simulated model
        validation: Optional pre-validation result to include in output
        
    Returns:
        SimulationResult containing the time series data and metadata
        
    Raises:
        SimulationError: If the model cannot be loaded, validated, or integrated
    """
    if points < 2:
        raise SimulationError("points must be at least 2")
    if end <= start:
        # roadrunner's own message for this ("Cannot get the time step 1
        # because there are only 0 set for the output") gives the caller
        # nothing to act on, so the check happens here instead.
        raise SimulationError(
            f"end ({end}) must be strictly after start ({start})")

    runner = _load_runner(sbml_string)
    if selections is not None:
        try:
            runner.selections = list(selections)
        except Exception as exc:
            raise SimulationError(f"invalid selections {selections!r}: {exc}") from exc

    try:
        raw = runner.simulate(start, end, points)
    except Exception as exc:
        raise SimulationError(f"integration failed: {exc}") from exc

    colnames = list(raw.colnames)
    data = [[float(v) for v in row] for row in raw]
    return SimulationResult(
        colnames=colnames,
        data=data,
        model_name=model_name,
        validation=validation or ParameterValidation(),
    )


def simulate_michaelis_menten(km: float, vmax: float, s0: float,
                              start: float = 0.0, end: float = 10.0,
                              points: int = 51) -> SimulationResult:
    """Validate, build, translate and integrate a Michaelis-Menten model.
    
    This function creates a complete Michaelis-Menten enzyme kinetics model
    from parameter values, validates them, converts to SBML, and simulates
    the system using RoadRunner.
    
    Args:
        km: Michaelis constant (Km) - must be positive
        vmax: Maximum reaction rate (Vmax) - must be positive  
        s0: Initial substrate concentration (can be zero)
        start: Start time for simulation
        end: End time for simulation
        points: Number of time points for output
        
    Returns:
        SimulationResult containing time series for substrate and product
        
    Raises:
        ModelBuildError: If parameters are invalid (non-numeric, negative, etc.)
        SimulationError: If the integration fails after a valid model is built
    """
    validation = validate_michaelis_menten_params(km, vmax, s0)
    validation.raise_if_invalid()
    model = build_michaelis_menten_antimony(km, vmax, s0)
    sbml = antimony_to_sbml(model, "michaelis_menten")
    return simulate_sbml(sbml, start, end, points,
                         model_name="michaelis_menten", validation=validation)


def simulate_mm_competitive_inhibition(km: float, vmax: float, ki: float,
                                       s0: float, i: float,
                                       start: float = 0.0, end: float = 10.0,
                                       points: int = 51) -> SimulationResult:
    """Validate, build, translate and integrate a competitive-inhibition
    Michaelis-Menten model.

    At I = 0 this must reproduce simulate_michaelis_menten's trajectory
    exactly (the apparent Km, Km*(1 + I/Ki), reduces to plain Km).
    """
    validation = validate_mm_competitive_params(km, vmax, ki, s0, i)
    validation.raise_if_invalid()
    model = build_mm_competitive_antimony(km, vmax, ki, s0, i)
    sbml = antimony_to_sbml(model, "mm_competitive_inhibition")
    return simulate_sbml(sbml, start, end, points,
                         model_name="mm_competitive_inhibition", validation=validation)


def steady_state(sbml_string: str) -> Dict[str, float]:
    """Solve for the steady state and return floating species concentrations."""
    runner = _load_runner(sbml_string)
    try:
        runner.conservedMoietyAnalysis = True
        runner.steadyState()
    except Exception as exc:
        raise SimulationError(f"steady state solve failed: {exc}") from exc
    ids = runner.model.getFloatingSpeciesIds()
    values = runner.model.getFloatingSpeciesConcentrations()
    return {name: float(val) for name, val in zip(ids, values)}


def parameter_scan(sbml_string: str, parameter: str,
                   values: Iterable[float], start: float = 0.0,
                   end: float = 10.0, points: int = 51,
                   selections: Sequence[str] | None = None
                   ) -> List[SimulationResult]:
    """Re-run a model across a range of values for one global parameter."""
    values = list(values)
    if not values:
        raise SimulationError("parameter_scan needs at least one value")

    runner = _load_runner(sbml_string)
    if parameter not in runner.model.getGlobalParameterIds():
        raise SimulationError(
            f"{parameter!r} is not a global parameter of this model "
            f"(have: {list(runner.model.getGlobalParameterIds())})")

    results: List[SimulationResult] = []
    for value in values:
        runner.reset()
        setattr(runner, parameter, float(value))
        if selections is not None:
            runner.selections = list(selections)
        try:
            raw = runner.simulate(start, end, points)
        except Exception as exc:
            raise SimulationError(
                f"integration failed at {parameter}={value}: {exc}") from exc
        results.append(SimulationResult(
            colnames=list(raw.colnames),
            data=[[float(v) for v in row] for row in raw],
            model_name=f"{parameter}={value}",
            validation=ParameterValidation(),
        ))
    return results
