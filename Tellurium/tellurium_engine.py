"""
Terrium Tellurium/roadrunner integration layer.

Covers the two Tier-2 ODE domains from the Terrium spec:
  * Michaelis-Menten enzyme kinetics
  * SIR / SEIR epidemiological modeling

Design notes
------------
The full ``tellurium`` umbrella package pulls in python-libcombine and
python-libnuml, which are only needed for COMBINE archives and numerical
markup -- neither of which Terrium uses. This module targets the three
engines that actually do the work and that install cleanly:

    antimony  -- human-readable model definition -> SBML
    libsbml   -- SBML validation
    roadrunner -- ODE integration

Parameter plausibility checking deliberately mirrors the flagged /
flag_reason pattern already established in Tests/brenda_client.py, so a
value that BRENDA flagged as implausible stays flagged when it reaches the
simulation layer instead of silently becoming a "confirmed" model input.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import antimony
import libsbml
import numpy as np
import roadrunner

__all__ = [
    "ModelBuildError",
    "SimulationError",
    "ParameterValidation",
    "SimulationResult",
    "DEFAULT_RELATIVE_TOLERANCE",
    "DEFAULT_ABSOLUTE_TOLERANCE",
    "GAMMA_PARAM",
    "KM_PLAUSIBLE_MIN_MM",
    "KM_PLAUSIBLE_MAX_MM",
    "validate_michaelis_menten_params",
    "validate_sir_params",
    "validate_seir_params",
    "build_michaelis_menten_antimony",
    "build_sir_antimony",
    "build_seir_antimony",
    "antimony_to_sbml",
    "sbml_to_antimony",
    "validate_sbml",
    "simulate_sbml",
    "simulate_michaelis_menten",
    "simulate_sir",
    "simulate_seir",
    "steady_state",
    "parameter_scan",
    "PCR_MIN_EFFICIENCY",
    "PCR_MAX_EFFICIENCY",
    "PCR_PLAUSIBLE_LOW_EFFICIENCY",
    "validate_pcr_params",
    "simulate_pcr",
    "MC_PLAUSIBLE_MIN_SAMPLES",
    "validate_monte_carlo_params",
    "simulate_monte_carlo_pi",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ModelBuildError(ValueError):
    """Raised when a model cannot be constructed or translated to SBML."""


class SimulationError(RuntimeError):
    """Raised when roadrunner cannot integrate a model."""


# ---------------------------------------------------------------------------
# Plausibility bounds
#
# KM bounds match Tests/brenda_client.py so the same value is judged the same
# way on both sides of the pipeline. The kinetics range is deliberately wide:
# real BRENDA data spans roughly 2.3e-7 mM to >100 mM across enzymes.
# ---------------------------------------------------------------------------

KM_PLAUSIBLE_MIN_MM = 1e-7  # 0.1 nM - below this gets flagged
KM_PLAUSIBLE_MAX_MM = 1e3  # 1000 mM - above this gets flagged
R0_IMPLAUSIBLE_ABOVE = 20.0  # Higher than any documented human pathogen

# PCR amplification efficiency is a fraction: 1.0 means perfect doubling every
# cycle (copies *= 2). Efficiency above 1.0 is not physically possible for a
# single amplicon -- you cannot copy a template more than once per cycle --
# so that is a hard rejection, not a flag. Below ~0.5 the reaction is real but
# poor (bad primers, inhibitors, degraded template), so it is flagged rather
# than rejected: a student may be deliberately modeling a failing reaction.
PCR_MIN_EFFICIENCY = 0.0
PCR_MAX_EFFICIENCY = 1.0
PCR_PLAUSIBLE_LOW_EFFICIENCY = 0.5


@dataclass
class ParameterValidation:
    """Result of checking a parameter set before it reaches the solver.

    ``ok`` False means the model cannot be built at all (physically
    impossible input). ``flagged`` True means the model *can* be built and
    simulated, but a human should look at it -- mirroring the BRENDA layer's
    distinction between a parse failure and an implausible-but-real value.
    """

    ok: bool = True
    flagged: bool = False
    flag_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ModelBuildError("; ".join(self.errors))


@dataclass
class SimulationResult:
    """Simulation output plus the provenance needed for the trust trail."""

    colnames: List[str]
    data: List[List[float]]
    model_name: str
    validation: ParameterValidation

    @property
    def flagged(self) -> bool:
        return self.validation.flagged

    def column(self, name: str) -> List[float]:
        """Return one column by name, tolerating roadrunner's ``[S]`` form."""
        candidates = (name, f"[{name}]")
        for candidate in candidates:
            if candidate in self.colnames:
                idx = self.colnames.index(candidate)
                return [row[idx] for row in self.data]
        raise KeyError(f"no column {name!r} in {self.colnames}")

    @property
    def time(self) -> List[float]:
        return self.column("time")

    def final(self, name: str) -> float:
        return self.column(name)[-1]

    def __len__(self) -> int:
        return len(self.data)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _finite_positive(value: Any, label: str, errors: List[str],
                     allow_zero: bool = False) -> bool:
    """Validate that a value is a finite, non‑negative number.
    
    Args:
        value: The value to validate
        label: Human‑readable name for the value (used in error messages)
        errors: List to which error messages should be appended
        allow_zero: Whether zero is allowed (used for population/counts)
        
    Returns:
        False if the value is invalid, True if valid
    """
    if isinstance(value, bool):
        errors.append(f"{label} must be a number, not a boolean")
        return False
    
    if not isinstance(value, (int, float)):
        errors.append(f"{label} must be a number, got {type(value).__name__}")
        return False
    
    if math.isnan(value):
        errors.append(f"{label} must not be NaN")
        return False
    
    if math.isinf(value):
        errors.append(f"{label} must be finite")
        return False
    
    if value < 0:
        errors.append(f"{label} must be non‑negative (got {value})")
        return False
    
    if value == 0 and not allow_zero:
        errors.append(f"{label} must be greater than zero")
        return False
    
    return True


def validate_michaelis_menten_params(km: float, vmax: float,
                                     s0: float) -> ParameterValidation:
    """Check a Michaelis-Menten parameter set.

    Km and Vmax must be strictly positive (Km = 0 makes the rate law
    degenerate; Vmax = 0 gives a model that provably cannot turn over).
    Initial substrate may legitimately be zero.
    """
    errors: List[str] = []

    km_valid = _finite_positive(km, "Km", errors, allow_zero=False)
    vmax_valid = _finite_positive(vmax, "Vmax", errors, allow_zero=False)
    s0_valid = _finite_positive(s0, "S0", errors, allow_zero=True)
    
    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if km < KM_PLAUSIBLE_MIN_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is below the plausible lower bound "
            f"{KM_PLAUSIBLE_MIN_MM:g} mM"
        )
    elif km > KM_PLAUSIBLE_MAX_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is above the plausible upper bound "
            f"{KM_PLAUSIBLE_MAX_MM:g} mM"
        )
    return v


def validate_sir_params(beta: float, gamma: float, s0: float, i0: float,
                        r0_recovered: float = 0.0) -> ParameterValidation:
    """Check an SIR parameter set.

    An epidemic model with zero initial infected is valid but inert, so it is
    flagged rather than rejected -- a student may genuinely want to see that
    nothing happens.
    """
    errors: List[str] = []

    if not _finite_positive(beta, "beta", errors, allow_zero=False):
        errors.append("beta must be finite and positive")
    if not _finite_positive(gamma, "gamma", errors, allow_zero=False):
        errors.append("gamma must be finite and positive")
    if not _finite_positive(s0, "S0", errors, allow_zero=True):
        errors.append("S0 must be finite and non-negative")
    if not _finite_positive(i0, "I0", errors, allow_zero=True):
        errors.append("I0 must be finite and non-negative")
    if not _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True):
        errors.append("R0_recovered must be finite and non-negative")
    
    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if (s0 + i0 + r0_recovered) <= 0:
        v.ok = False
        v.errors.append("total population must be greater than zero")
        return v

    if i0 == 0:
        v.flagged = True
        v.flag_reason = "I0 is zero: no outbreak can occur"
        return v

    basic_reproduction = beta / gamma
    if basic_reproduction > R0_IMPLAUSIBLE_ABOVE:
        v.flagged = True
        v.flag_reason = (
            f"R0 = beta/gamma = {basic_reproduction:g} exceeds "
            f"{R0_IMPLAUSIBLE_ABOVE:g}, higher than any well-documented "
            "human pathogen"
        )
    return v


def validate_seir_params(beta: float, sigma: float, gamma: float, s0: float,
                          e0: float, i0: float,
                          r0_recovered: float = 0.0) -> ParameterValidation:
    """Check an SEIR parameter set (adds the latent-progression rate sigma)."""
    errors: List[str] = []

    if not _finite_positive(beta, "beta", errors, allow_zero=False):
        errors.append("beta must be finite and positive")
    if not _finite_positive(sigma, "sigma", errors, allow_zero=False):
        errors.append("sigma must be finite and positive")
    if not _finite_positive(gamma, "gamma", errors, allow_zero=False):
        errors.append("gamma must be finite and positive")
    if not _finite_positive(s0, "S0", errors, allow_zero=True):
        errors.append("S0 must be finite and non-negative")
    if not _finite_positive(i0, "I0", errors, allow_zero=True):
        errors.append("I0 must be finite and non-negative")
    if not _finite_positive(e0, "E0", errors, allow_zero=True):
        errors.append("E0 must be finite and non-negative")
    if not _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True):
        errors.append("R0_recovered must be finite and non-negative")
    
    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if (s0 + i0 + r0_recovered + e0) <= 0:
        v.ok = False
        v.errors.append("total population must be greater than zero")
        return v

    if i0 == 0 and e0 == 0:
        v.flagged = True
        v.flag_reason = "both E0 and I0 are zero: no outbreak can occur"
        return v

    base_sir = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    v.flagged = base_sir.flagged and not (base_sir.flag_reason or "").startswith("I0")
    v.flag_reason = v.flag_reason or (base_sir.flag_reason if v.flagged else None)
    if v.flagged and v.flag_reason is None:
        v.flag_reason = base_sir.flag_reason
    return v


# ---------------------------------------------------------------------------
# Antimony model construction
# ---------------------------------------------------------------------------


# ``gamma`` is a built-in function name in Antimony (the gamma function), so a
# parameter called gamma is a hard parse error rather than a shadowing warning.
# The recovery rate is therefore emitted as ``gamma_rate``. The Python API
# still takes ``gamma`` -- the rename is confined to generated model source,
# and the generated model carries a comment so a student reading it is not
# left wondering why the symbol does not match the textbook.
GAMMA_PARAM = "gamma_rate"

_GAMMA_NOTE = (
    "  # 'gamma' is a reserved function name in Antimony; the recovery rate\n"
    "  # (textbook gamma) is written gamma_rate below.\n"
)


def _fmt(value: float) -> str:
    """Format a float for Antimony without losing precision to repr quirks."""
    return repr(float(value))


def build_michaelis_menten_antimony(km: float, vmax: float, s0: float,
                                    model_name: str = "michaelis_menten",
                                    validate: bool = True) -> str:
    """Build an irreversible single-substrate Michaelis-Menten model.

        v = Vmax * [S] / (Km + [S])
    """
    if validate:
        validate_michaelis_menten_params(km, vmax, s0).raise_if_invalid()
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  J0: S -> P; Vmax * S / (Km + S);\n"
        f"  S = {_fmt(s0)};\n"
        f"  P = 0;\n"
        f"  Vmax = {_fmt(vmax)};\n"
        f"  Km = {_fmt(km)};\n"
        f"end\n"
    )


def build_sir_antimony(beta: float, gamma: float, s0: float, i0: float,
                       r0_recovered: float = 0.0, model_name: str = "sir",
                       validate: bool = True) -> str:
    """Build a standard frequency-dependent SIR model.

        dS/dt = -beta*S*I/N
        dI/dt =  beta*S*I/N - gamma*I
        dR/dt =  gamma*I
    """
    if validate:
        validate_sir_params(beta, gamma, s0, i0, r0_recovered).raise_if_invalid()
    _check_model_name(model_name)
    n = s0 + i0 + r0_recovered
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  J0: S -> I; beta * S * I / N;\n"
        f"  J1: I -> R; {GAMMA_PARAM} * I;\n"
        f"  S = {_fmt(s0)};\n"
        f"  I = {_fmt(i0)};\n"
        f"  R = {_fmt(r0_recovered)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  N = {_fmt(n)};\n"
        f"end\n"
    )


def build_seir_antimony(beta: float, sigma: float, gamma: float, s0: float,
                        e0: float, i0: float, r0_recovered: float = 0.0,
                        model_name: str = "seir",
                        validate: bool = True) -> str:
    """Build an SEIR model with an explicit latent (exposed) compartment.

        dS/dt = -beta*S*I/N
        dE/dt =  beta*S*I/N - sigma*E
        dI/dt =  sigma*E - gamma*I
        dR/dt =  gamma*I
    """
    if validate:
        validate_seir_params(beta, sigma, gamma, s0, e0, i0, r0_recovered).raise_if_invalid()
    _check_model_name(model_name)
    n = s0 + e0 + i0 + r0_recovered
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  J0: S -> E; beta * S * I / N;\n"
        f"  J1: E -> I; sigma * E;\n"
        f"  J2: I -> R; {GAMMA_PARAM} * I;\n"
        f"  S = {_fmt(s0)};\n"
        f"  E = {_fmt(e0)};\n"
        f"  I = {_fmt(i0)};\n"
        f"  R = {_fmt(r0_recovered)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  sigma = {_fmt(sigma)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  N = {_fmt(n)};\n"
        f"end\n"
    )


_RESERVED_MODEL_NAMES = {"model", "end", "species", "function", "compartment"}


def _check_model_name(model_name: str) -> None:
    """Validate an Antimony model name.
    
    Args:
        model_name: The proposed model name to validate
        
    Raises:
        ModelBuildError: If the name is invalid for Antimony
    """
    if not isinstance(model_name, str) or not model_name:
        raise ModelBuildError("model_name must be a non-empty string")
    if model_name in _RESERVED_MODEL_NAMES:
        raise ModelBuildError(f"{model_name!r} is a reserved Antimony keyword")
    if not (model_name[0].isalpha() or model_name[0] == "_"):
        raise ModelBuildError(
            f"model_name {model_name!r} must start with a letter or underscore")
    if not all(ch.isalnum() or ch == "_" for ch in model_name):
        raise ModelBuildError(
            f"model_name {model_name!r} may only contain letters, digits and "
            "underscores")


# ---------------------------------------------------------------------------
# Antimony <-> SBML
#
# libantimony keeps global module state, so concurrent loads from different
# threads can clobber each other's results. Terrium's backend will serve
# multiple students at once, so translation is serialised behind a lock and
# every call clears prior loads.
# ---------------------------------------------------------------------------

_ANTIMONY_LOCK = threading.Lock()


def antimony_to_sbml(antimony_string: str,
                     model_name: Optional[str] = None) -> str:
    """Translate Antimony source to an SBML document string."""
    if not isinstance(antimony_string, str):
        raise ModelBuildError("antimony_string must be a string")
    if not antimony_string.strip():
        raise ModelBuildError("antimony_string is empty")

    with _ANTIMONY_LOCK:
        antimony.clearPreviousLoads()
        code = antimony.loadAntimonyString(antimony_string)
        if code < 0:
            raise ModelBuildError(
                f"Antimony failed to parse model: {antimony.getLastError()}")
        if model_name is None:
            model_name = antimony.getMainModuleName()
        sbml = antimony.getSBMLString(model_name)
        if not sbml:
            raise ModelBuildError(
                f"Antimony produced no SBML for module {model_name!r}: "
                f"{antimony.getLastError()}")
        return sbml


def sbml_to_antimony(sbml_string: str) -> str:
    """Translate an SBML document string back to Antimony source.
    
    This function safely converts an SBML document to Antimony representation,
    ensuring thread safety by using a lock and clearing previous Antimony loads.
    
    Args:
        sbml_string: A valid SBML document as a string
        
    Returns:
        The corresponding Antimony source code as a string
        
    Raises:
        ModelBuildError: If the SBML is invalid or cannot be converted
    """
    if not isinstance(sbml_string, str) or not sbml_string.strip():
        raise ModelBuildError("sbml_string is empty")
    with _ANTIMONY_LOCK:
        antimony.clearPreviousLoads()
        code = antimony.loadSBMLString(sbml_string)
        if code < 0:
            raise ModelBuildError(
                f"Antimony failed to read SBML: {antimony.getLastError()}")
        return antimony.getAntimonyString(antimony.getMainModuleName())


def validate_sbml(sbml_string: str) -> List[str]:
    """Validate an SBML document and return all fatal/error-level problems.

    Warnings and informational messages are intentionally excluded: roadrunner
    integrates warning-level documents fine, and surfacing them would train
    users to ignore the list. Only errors (>= LIBSBML_SEV_ERROR) are returned.
    
    Args:
        sbml_string: A potentially valid SBML document as a string
        
    Returns:
        A list of error messages. Empty list if the document is valid.
    """
    doc = libsbml.readSBMLFromString(sbml_string)
    doc.checkConsistency()
    problems: List[str] = []
    for i in range(doc.getNumErrors()):
        err = doc.getError(i)
        if err.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
            problems.append(err.getMessage().strip())
    return problems


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


# roadrunner's stock CVODE relative tolerance is 1e-6, which leaves visible
# error against known analytic solutions (measured: ~2.6e-6 absolute drift on
# a plain exponential decay over 100 time units). Terrium reports numbers to
# students as trustworthy, so the default is tightened here; on these model
# sizes the extra cost is not measurable, and it buys about four orders of
# magnitude of accuracy (same benchmark: ~1.1e-10).
DEFAULT_RELATIVE_TOLERANCE = 1e-10
DEFAULT_ABSOLUTE_TOLERANCE = 1e-12


def _load_runner(sbml_string: str,
                 rtol: float = DEFAULT_RELATIVE_TOLERANCE,
                 atol: float = DEFAULT_ABSOLUTE_TOLERANCE
                 ) -> roadrunner.RoadRunner:
    try:
        runner = roadrunner.RoadRunner(sbml_string)
    except Exception as exc:  # roadrunner raises bare RuntimeError subclasses
        raise SimulationError(f"roadrunner could not load model: {exc}") from exc
    try:
        runner.integrator.relative_tolerance = rtol
        runner.integrator.absolute_tolerance = atol
    except Exception as exc:
        raise SimulationError(f"could not set integrator tolerances: {exc}") from exc
    return runner


def simulate_sbml(sbml_string: str, start: float = 0.0, end: float = 10.0,
                   points: int = 51,
                   selections: Optional[Sequence[str]] = None,
                   model_name: str = "model",
                   validation: Optional[ParameterValidation] = None
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
                   selections: Optional[Sequence[str]] = None
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


# ---------------------------------------------------------------------------
# PCR amplification
#
# This domain is deliberately NOT built through antimony/roadrunner. PCR is a
# discrete-cycle process (you cannot run "half a cycle"), not a continuous-
# time ODE, so modeling it as one would force a fake continuous-time
# reinterpretation just to reuse the SBML pipeline. The exact closed-form
# recurrence below is exact by construction, not an approximation needing a
# solver -- there is no numerical error to manage.
# ---------------------------------------------------------------------------


def validate_pcr_params(n0: float, efficiency: float,
                        cycles: int) -> ParameterValidation:
    """Check a PCR amplification parameter set.

    n0 must be a positive template copy number. efficiency is the fraction of
    template successfully doubled each cycle: 1.0 is ideal (copies exactly
    double), 0.0 is no amplification at all. Above 1.0 is physically
    impossible -- rejected, not flagged. Below
    ``PCR_PLAUSIBLE_LOW_EFFICIENCY`` is a real but poor reaction -- flagged so
    a student modeling a failing PCR still gets a plot, with a visible
    warning attached.
    """
    errors: List[str] = []

    if not _finite_positive(n0, "n0", errors, allow_zero=False):
        errors.append("n0 must be finite and positive")

    if isinstance(efficiency, bool) or not isinstance(efficiency, (int, float)):
        errors.append(
            f"efficiency must be a number, got {type(efficiency).__name__}")
    elif math.isnan(efficiency) or math.isinf(efficiency):
        errors.append("efficiency must be finite")
    elif efficiency < PCR_MIN_EFFICIENCY or efficiency > PCR_MAX_EFFICIENCY:
        errors.append(
            f"efficiency must be between {PCR_MIN_EFFICIENCY} and "
            f"{PCR_MAX_EFFICIENCY} (got {efficiency}) -- a single amplicon "
            "cannot be copied more than once per cycle")

    if isinstance(cycles, bool) or not isinstance(cycles, int):
        errors.append(f"cycles must be an integer, got {type(cycles).__name__}")
    elif cycles <= 0:
        errors.append("cycles must be a positive integer")
    elif cycles > 60:
        errors.append(
            f"cycles must be <= 60 (got {cycles}) -- real qPCR protocols "
            "never run this many cycles; the template would be exhausted "
            "or the reaction would have plateaued long before this point")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    if isinstance(efficiency, (int, float)) and efficiency < PCR_PLAUSIBLE_LOW_EFFICIENCY:
        return ParameterValidation(
            ok=True, flagged=True,
            flag_reason=(
                f"efficiency {efficiency} is below "
                f"{PCR_PLAUSIBLE_LOW_EFFICIENCY} -- amplification will be "
                "real but poor (degraded template, weak primers, or "
                "inhibitors are the usual causes)"),
        )

    return ParameterValidation()


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


# ---------------------------------------------------------------------------
# Monte Carlo simulation (pi estimation)
#
# Like PCR, this is a discrete/stochastic domain, not a continuous-time ODE.
# There is no state to integrate: the estimator is a direct sample mean whose
# convergence properties follow from the Central Limit Theorem. Routing this
# through antimony/roadrunner would be the same category error ADR 0002
# explicitly warned against — forcing a solver into a domain that doesn't
# need one, just for pipeline consistency.
#
# Judgment call: the RNG is numpy's default_rng (PCG64), the NumPy-recommended
# modern generator. If a future stochastic domain (e.g. population genetics)
# needs correlated or low-discrepancy sequences, it should document why it
# deviates from this default rather than picking a different generator
# silently.
# ---------------------------------------------------------------------------

# Fewer than 100 samples gives SE ≈ 0.16 — too large for a meaningful pi
# estimate, but the simulation is physically valid and the student may be
# experimenting, so it is flagged rather than rejected.
MC_PLAUSIBLE_MIN_SAMPLES = 100


def validate_monte_carlo_params(n_samples: int) -> ParameterValidation:
    """Check Monte Carlo pi-estimation parameters.

    ``n_samples`` must be a positive integer. Fewer than
    ``MC_PLAUSIBLE_MIN_SAMPLES`` (100) is flagged as implausible — the
    standard error will be too large for a meaningful estimate — but the
    simulation is still valid and will run.
    """
    errors: List[str] = []

    if isinstance(n_samples, bool):
        errors.append("n_samples must be an integer, not a boolean")
    elif not isinstance(n_samples, int):
        errors.append(
            f"n_samples must be an integer, got {type(n_samples).__name__}")
    elif n_samples <= 0:
        errors.append("n_samples must be a positive integer")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    if n_samples < MC_PLAUSIBLE_MIN_SAMPLES:
        return ParameterValidation(
            ok=True, flagged=True,
            flag_reason=(
                f"n_samples={n_samples} is below "
                f"{MC_PLAUSIBLE_MIN_SAMPLES}; the standard error will be "
                "too large for a meaningful estimate"),
        )

    return ParameterValidation()


def simulate_monte_carlo_pi(
    n_samples: int,
    seed: int | None = None,
) -> SimulationResult:
    """Estimate pi via Monte Carlo sampling with a reported standard error.

    Draw ``n_samples`` points uniformly in [-1, 1] x [-1, 1] and compute
    pi_estimate = 4 * (fraction landing inside the unit circle).
    The standard error is 4 * sqrt(p_hat * (1 - p_hat) / N)
    where p_hat is the sample proportion inside the circle.

    The result includes convergence-checkpoint rows (log-spaced sample counts
    with running estimate and standard error) so callers can plot how the
    estimate stabilizes as samples accumulate.

    Args:
        n_samples: number of random points to draw (must be >= 1)
        seed: optional seed for reproducibility; passed to
            ``numpy.random.default_rng``

    Returns:
        SimulationResult with columns ``["n", "estimate", "se"]``, one row
        per convergence checkpoint. The final row contains the full-sample
        estimate and standard error.

    Raises:
        ModelBuildError: if ``n_samples`` is invalid
    """
    validation = validate_monte_carlo_params(n_samples)
    validation.raise_if_invalid()

    rng = np.random.default_rng(seed)

    # Sample points uniformly in [-1, 1] x [-1, 1]
    xs = rng.uniform(-1.0, 1.0, size=n_samples)
    ys = rng.uniform(-1.0, 1.0, size=n_samples)

    # Indicator: 1.0 if (x, y) falls inside the unit circle, 0.0 otherwise
    inside = (xs ** 2 + ys ** 2) <= 1.0

    # Running estimate of pi at each sample index
    cumulative_n = np.arange(1, n_samples + 1, dtype=np.float64)
    cumulative_p_hat = np.cumsum(inside, dtype=np.float64) / cumulative_n
    cumulative_estimate = 4.0 * cumulative_p_hat

    # Running standard error: SE = 4 * sqrt(p_hat * (1 - p_hat) / n)
    cumulative_se = 4.0 * np.sqrt(
        cumulative_p_hat * (1.0 - cumulative_p_hat) / cumulative_n
    )

    # Build convergence checkpoints: log-spaced integers plus explicit
    # milestones so the first few data points are always visible.
    milestones: set[int] = {1, 2, 5, 10, 20, 50, 100, 200, 500,
                            1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
                            100_000, 200_000, 500_000, 1_000_000}
    milestones = {m for m in milestones if m <= n_samples}
    milestones.add(n_samples)

    if n_samples > 1:
        log_points = np.geomspace(1, n_samples,
                                  num=min(150, n_samples),
                                  dtype=int)
        milestones.update(int(p) for p in log_points)

    checkpoints = sorted(milestones)

    # Build data rows
    data: List[List[float]] = []
    for n in checkpoints:
        idx = n - 1  # 0-based
        data.append([
            float(n),
            float(cumulative_estimate[idx]),
            float(cumulative_se[idx]),
        ])

    return SimulationResult(
        colnames=["n", "estimate", "se"],
        data=data,
        model_name="monte_carlo_pi",
        validation=validation,
    )
