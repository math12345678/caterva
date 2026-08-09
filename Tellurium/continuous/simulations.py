"""Continuous-domain simulation entry points (ODE via roadrunner)."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

try:
    from Tellurium.core.data_structures import (ParameterValidation, SimulationError, SimulationResult)  # type: ignore[no-redef]
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ParameterValidation, SimulationError, SimulationResult)  # type: ignore[no-redef]

try:
    from Tellurium.core.utils import _load_runner  # type: ignore[no-redef]
    from Tellurium.core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params,
        validate_sir_params, validate_seir_params,
        validate_lotka_volterra_params)  # type: ignore[no-redef]
    from Tellurium.continuous.model_building import (
        build_michaelis_menten_antimony, build_mm_competitive_antimony,
        build_sir_antimony, build_seir_antimony,
        build_lotka_volterra_antimony, build_cell_cycle_oscillator_antimony,
        build_repressilator_antimony,
        antimony_to_sbml)  # type: ignore[no-redef]
except ModuleNotFoundError:
    from core.utils import _load_runner  # type: ignore[no-redef]
    from core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params,
        validate_sir_params, validate_seir_params,
        validate_lotka_volterra_params)  # type: ignore[no-redef]
    from continuous.model_building import (
        build_michaelis_menten_antimony, build_mm_competitive_antimony,
        build_sir_antimony, build_seir_antimony,
        build_lotka_volterra_antimony, build_cell_cycle_oscillator_antimony,
        build_repressilator_antimony,
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


def simulate_sir(beta: float, gamma: float, s0: float, i0: float,
                  r0_recovered: float = 0.0, start: float = 0.0,
                  end: float = 100.0, points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SIR epidemiological model.
    
    This implements the classic SIR (Susceptible-Infected-Recovered) model
    for disease spread. The model tracks three compartments over time and
    is commonly used in epidemiology teaching and research.
    
    Args:
        beta: Transmission rate (higher = faster spread)
        gamma: Recovery rate (higher = faster recovery)
        s0: Initial number of susceptible individuals
        i0: Initial number of infected individuals
        r0_recovered: Initial number of recovered individuals
        start: Start time for simulation
        end: End time for simulation
        points: Number of time points for output
        
    Returns:
        SimulationResult containing the time evolution of all three compartments
        
    Raises:
        ModelBuildError: If parameters are invalid
        SimulationError: If the integration fails
    """
    validation = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    validation.raise_if_invalid()
    model = build_sir_antimony(beta, gamma, s0, i0, r0_recovered)
    sbml = antimony_to_sbml(model, "sir")
    return simulate_sbml(sbml, start, end, points, model_name="sir",
                         validation=validation)


def simulate_seir(beta: float, sigma: float, gamma: float, s0: float,
                  e0: float, i0: float, r0_recovered: float = 0.0,
                  start: float = 0.0, end: float = 100.0,
                  points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SEIR epidemiological model.
    
    This is an extension of the SIR model that adds an exposed compartment (E)
    representing individuals who have been infected but are not yet infectious.
    This better models diseases with incubation periods like COVID-19.
    
    Args:
        beta: Transmission rate (higher = faster spread)
        sigma: Progression rate from exposed to infectious
        gamma: Recovery rate (higher = faster recovery)
        s0: Initial number of susceptible individuals
        e0: Initial number of exposed individuals (incubating)
        i0: Initial number of infectious individuals
        r0_recovered: Initial number of recovered individuals
        start: Start time for simulation
        end: End time for simulation
        points: Number of time points for output
        
    Returns:
        SimulationResult containing the time evolution of all four compartments
        
    Raises:
        ModelBuildError: If parameters are invalid
        SimulationError: If the integration fails
    """
    validation = validate_seir_params(beta, sigma, gamma, s0, e0, i0,
                                      r0_recovered)
    validation.raise_if_invalid()
    model = build_seir_antimony(beta, sigma, gamma, s0, e0, i0, r0_recovered)
    sbml = antimony_to_sbml(model, "seir")
    return simulate_sbml(sbml, start, end, points, model_name="seir",
                         validation=validation)


def simulate_lotka_volterra(alpha: float = 1.1, beta: float = 0.4,
                            gamma: float = 0.4, delta: float = 0.1,
                            p0: float = 10.0, v0: float = 5.0,
                            start: float = 0.0, end: float = 20.0,
                            points: int = 201) -> SimulationResult:
    """Validate, build, translate and integrate a Lotka-Volterra
    predator-prey model (Lotka 1925; Volterra 1926).

    Defaults reproduce the classic ~10-year lynx-hare oscillation cycle
    on an annual-cycle time axis. See docs/adr/0022.
    """
    validation = validate_lotka_volterra_params(alpha, beta, gamma, delta, p0, v0)
    validation.raise_if_invalid()
    model = build_lotka_volterra_antimony(alpha, beta, gamma, delta, p0, v0)
    sbml = antimony_to_sbml(model, "lotka_volterra")
    return simulate_sbml(sbml, start, end, points, model_name="lotka_volterra",
                         validation=validation)


def simulate_cell_cycle_oscillator(start: float = 0.0, end: float = 100.0,
                                   points: int = 1001,
                                   seed: int | None = None) -> SimulationResult:
    """Integrate Tyson's (1991) 2-variable cdc2-cyclin relaxation
    oscillator using the paper's own standard oscillatory parameter set.

    ``seed`` is accepted for call-signature symmetry with the stochastic
    domains but is unused: this is a deterministic ODE system with no
    randomness anywhere in it. See docs/adr/0022.
    """
    del seed  # deterministic model; kept for API symmetry only
    model = build_cell_cycle_oscillator_antimony()
    sbml = antimony_to_sbml(model, "cell_cycle_oscillator")
    return simulate_sbml(sbml, start, end, points,
                         model_name="cell_cycle_oscillator",
                         validation=ParameterValidation())


def simulate_repressilator(start: float = 0.0, end: float = 200.0,
                           points: int = 2001,
                           seed: int | None = None) -> SimulationResult:
    """Integrate the Elowitz & Leibler (2000) repressilator using the
    paper's own standard oscillatory parameter set.

    ``seed`` is accepted for call-signature symmetry with the stochastic
    domains but is unused: this is a deterministic ODE system with no
    randomness anywhere in it. See docs/adr/0022.
    """
    del seed  # deterministic model; kept for API symmetry only
    model = build_repressilator_antimony()
    sbml = antimony_to_sbml(model, "repressilator")
    return simulate_sbml(sbml, start, end, points, model_name="repressilator",
                         validation=ParameterValidation())


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
