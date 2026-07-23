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

KM_PLAUSIBLE_MIN_MM = 1e-7
KM_PLAUSIBLE_MAX_MM = 1e3

# These two constants MUST stay equal to brenda_client.KM_PLAUSIBLE_MIN_MM /
# KM_PLAUSIBLE_MAX_MM. They were briefly out of sync (engine 1e4 vs BRENDA
# 1e3), which meant a Km of e.g. 5000 mM was flagged by the literature layer
# and then silently accepted as "confirmed" by the simulation layer -- exactly
# the kind of gap the trust trail exists to prevent. The equality is now
# pinned by tests/test_brenda_integration.py so it cannot drift again.

# Epidemiological bounds. R0 above ~20 exceeds even measles (12-18), so
# anything past that is flagged rather than rejected -- flagging keeps the
# human in the loop instead of silently discarding an unusual but real model.
R0_IMPLAUSIBLE_ABOVE = 20.0


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
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be a number, got {type(value).__name__}")
        return False
    if math.isnan(value):
        errors.append(f"{label} must not be NaN")
        return False
    if math.isinf(value):
        errors.append(f"{label} must be finite")
        return False
    if value < 0:
        errors.append(f"{label} must not be negative (got {value})")
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
    km_ok = _finite_positive(km, "Km", errors)
    vmax_ok = _finite_positive(vmax, "Vmax", errors)
    s0_ok = _finite_positive(s0, "S0", errors, allow_zero=True)

    v = ParameterValidation(ok=km_ok and vmax_ok and s0_ok, errors=errors)
    if not v.ok:
        return v

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
    beta_ok = _finite_positive(beta, "beta", errors)
    gamma_ok = _finite_positive(gamma, "gamma", errors)
    s_ok = _finite_positive(s0, "S0", errors, allow_zero=True)
    i_ok = _finite_positive(i0, "I0", errors, allow_zero=True)
    r_ok = _finite_positive(r0_recovered, "R0_recovered", errors,
                            allow_zero=True)

    ok = all([beta_ok, gamma_ok, s_ok, i_ok, r_ok])
    v = ParameterValidation(ok=ok, errors=errors)
    if not v.ok:
        return v

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
    sigma_ok = _finite_positive(sigma, "sigma", errors)
    e_ok = _finite_positive(e0, "E0", errors, allow_zero=True)

    base = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    errors = base.errors + errors
    ok = base.ok and sigma_ok and e_ok
    v = ParameterValidation(ok=ok, errors=errors)
    if not v.ok:
        return v

    # An SEIR outbreak can be seeded from the exposed compartment alone, so
    # the SIR "I0 == 0 means nothing happens" flag does not carry over
    # unchanged.
    if i0 == 0 and e0 == 0:
        v.flagged = True
        v.flag_reason = "both E0 and I0 are zero: no outbreak can occur"
        return v

    v.flagged = base.flagged and not (base.flag_reason or "").startswith("I0")
    v.flag_reason = v.flag_reason or (base.flag_reason if v.flagged else None)
    if v.flagged and v.flag_reason is None:
        v.flag_reason = base.flag_reason
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
        validate_sir_params(beta, gamma, s0, i0,
                            r0_recovered).raise_if_invalid()
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
        validate_seir_params(beta, sigma, gamma, s0, e0, i0,
                             r0_recovered).raise_if_invalid()
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
    """Translate an SBML document string back to Antimony source."""
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
    """Return libSBML's fatal/error-level complaints about a document.

    Warnings and informational messages are intentionally excluded: roadrunner
    integrates warning-level documents fine, and surfacing them would train
    users to ignore the list.
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
    """Integrate an SBML model and return a SimulationResult."""
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
    """Validate, build, translate and integrate a Michaelis-Menten model."""
    validation = validate_michaelis_menten_params(km, vmax, s0)
    validation.raise_if_invalid()
    model = build_michaelis_menten_antimony(km, vmax, s0, validate=False)
    sbml = antimony_to_sbml(model, "michaelis_menten")
    return simulate_sbml(sbml, start, end, points,
                         model_name="michaelis_menten", validation=validation)


def simulate_sir(beta: float, gamma: float, s0: float, i0: float,
                 r0_recovered: float = 0.0, start: float = 0.0,
                 end: float = 100.0, points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SIR model."""
    validation = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    validation.raise_if_invalid()
    model = build_sir_antimony(beta, gamma, s0, i0, r0_recovered,
                               validate=False)
    sbml = antimony_to_sbml(model, "sir")
    return simulate_sbml(sbml, start, end, points, model_name="sir",
                         validation=validation)


def simulate_seir(beta: float, sigma: float, gamma: float, s0: float,
                  e0: float, i0: float, r0_recovered: float = 0.0,
                  start: float = 0.0, end: float = 100.0,
                  points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SEIR model."""
    validation = validate_seir_params(beta, sigma, gamma, s0, e0, i0,
                                      r0_recovered)
    validation.raise_if_invalid()
    model = build_seir_antimony(beta, sigma, gamma, s0, e0, i0, r0_recovered,
                                validate=False)
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
