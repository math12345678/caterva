"""Antimony model construction and SBML translation (continuous domains).

Antimony/libterium are intentionally isolated to this module: discrete
domains never import them (ADR 0001, ADR 0002, ADR 0006).
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


import threading
from typing import List

import antimony
import libsbml
try:
    from Terium.core.data_structures import (ModelBuildError, GAMMA_PARAM, _GAMMA_NOTE)  # type: ignore[no-redef]
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.data_structures import (ModelBuildError, GAMMA_PARAM, _GAMMA_NOTE)  # type: ignore[no-redef]

try:
    from Terium.core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params,
        validate_sir_params, validate_seir_params,
        validate_lotka_volterra_params)  # type: ignore[no-redef]
    from Terium.core.utils import _fmt, _check_model_name  # type: ignore[no-redef]
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.validation import (
        validate_michaelis_menten_params, validate_mm_competitive_params,
        validate_sir_params, validate_seir_params,
        validate_lotka_volterra_params)  # type: ignore[no-redef]
    from core.utils import _fmt, _check_model_name  # type: ignore[no-redef]

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


def build_mm_competitive_antimony(km: float, vmax: float, ki: float, s0: float,
                                  i: float, model_name: str = "mm_competitive_inhibition",
                                  validate: bool = True) -> str:
    """Build a single-substrate Michaelis-Menten model with competitive
    inhibition:

        v = Vmax * [S] / (Km * (1 + [I]/Ki) + [S])

    At I = 0 this reduces exactly to build_michaelis_menten_antimony's rate
    law (the (1 + I/Ki) factor becomes 1).
    """
    if validate:
        validate_mm_competitive_params(km, vmax, ki, s0, i).raise_if_invalid()
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  J0: S -> P; Vmax * S / (Km * (1 + I / Ki) + S);\n"
        f"  S = {_fmt(s0)};\n"
        f"  P = 0;\n"
        f"  Vmax = {_fmt(vmax)};\n"
        f"  Km = {_fmt(km)};\n"
        f"  Ki = {_fmt(ki)};\n"
        f"  I = {_fmt(i)};\n"
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

def build_lotka_volterra_antimony(alpha: float, beta: float, gamma: float,
                                  delta: float, p0: float, v0: float,
                                  model_name: str = "lotka_volterra",
                                  validate: bool = True) -> str:
    """Build a Lotka-Volterra predator-prey model (Lotka 1925; Volterra 1926).

        dP/dt = alpha*P - beta*P*V   (prey: growth, predation loss)
        dV/dt = gamma*P*V - delta*V  (predator: growth from predation, death)

    P and V are declared with direct rate rules (Antimony ``P' = ...``
    syntax), not mass-action reactions -- there is no real chemical
    species here, just two coupled populations, and a rate rule is the
    faithful translation of the ODE as the source states it.
    """
    if validate:
        validate_lotka_volterra_params(alpha, beta, gamma, delta, p0, v0).raise_if_invalid()
    _check_model_name(model_name)
    # 'gamma' is a reserved function name in Antimony (the gamma function) --
    # same collision the SIR/SEIR recovery rate hits (see GAMMA_PARAM /
    # _GAMMA_NOTE above). The predator growth-from-predation rate is
    # therefore emitted as 'gamma_rate' below; the Python API still takes
    # 'gamma'.
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  P' = alpha * P - beta * P * V;\n"
        f"  V' = {GAMMA_PARAM} * P * V - delta * V;\n"
        f"  P = {_fmt(p0)};\n"
        f"  V = {_fmt(v0)};\n"
        f"  alpha = {_fmt(alpha)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  delta = {_fmt(delta)};\n"
        f"end\n"
    )


# ---------------------------------------------------------------------------
# Cell cycle oscillator: Tyson (1991) 2-variable reduction.
#
# Tyson JJ, "Modeling the cell division cycle: cdc2 and cyclin
# interactions", Proc Natl Acad Sci USA 88(16):7328-7332, 1991,
# DOI 10.1073/pnas.88.16.7328.
#
# The paper presents a 6-variable mechanistic model and a 2-variable
# relaxation-oscillator reduction of it; the reduction is used here for a
# teaching-lab domain since it is simpler while remaining Tyson's own
# derivation, not a third party's simplification. Equations and the
# standard oscillatory parameter set below were cross-checked against the
# curated SBML for both BioModels encodings of this paper (BIOMD0000000005,
# 6-variable; BIOMD0000000006, 2-variable reduction), which explicitly cite
# PMID 1831270 -- see docs/adr/0022 for the verification trail.
#
#   u = [active MPF] / [CT]              (CT = total cdc2, conserved)
#   v = ([cyclin] + [preMPF] + [active MPF]) / [CT]
#
#   du/dt = k4*(v - u)*(alpha + u^2) - k6*u
#   dv/dt = kappa - k6*u
#   alpha = k4prime / k4
#
# Standard parameter set (Tyson's own, reproduced identically in both
# curated encodings): kappa=0.015, k6=1, k4=180, k4prime=0.018.
# Initial conditions u=0, v=0 match the curated model exactly; v moves
# immediately (dv/dt = kappa > 0 at t=0) so this is not a fixed point.
# ---------------------------------------------------------------------------

TYSON_KAPPA = 0.015
TYSON_K6 = 1.0
TYSON_K4 = 180.0
TYSON_K4PRIME = 0.018


def build_cell_cycle_oscillator_antimony(
        model_name: str = "cell_cycle_oscillator") -> str:
    """Build Tyson's (1991) 2-variable cdc2-cyclin relaxation oscillator.

    No caller-supplied kinetic parameters: every rate constant is the
    literature's own standard oscillatory set (see module-level comment
    above), so there is nothing here for a caller to get wrong. This
    mirrors how ``molecular_dynamics`` treats its Lennard-Jones constants.
    """
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  u' = k4 * (v - u) * (alpha + u^2) - k6 * u;\n"
        f"  v' = kappa - k6 * u;\n"
        f"  u = 0;\n"
        f"  v = 0;\n"
        f"  kappa = {_fmt(TYSON_KAPPA)};\n"
        f"  k6 = {_fmt(TYSON_K6)};\n"
        f"  k4 = {_fmt(TYSON_K4)};\n"
        f"  k4prime = {_fmt(TYSON_K4PRIME)};\n"
        f"  alpha := k4prime / k4;\n"
        f"  cyclin_fraction := v - u;\n"
        f"end\n"
    )


# ---------------------------------------------------------------------------
# Repressilator: Elowitz & Leibler (2000) synthetic oscillatory network.
#
# Elowitz MB, Leibler S, "A synthetic oscillatory network of
# transcriptional regulators", Nature 403:335-338, 2000,
# DOI 10.1038/35002125.
#
# Dimensionless "deterministic, continuous approximation" equations from
# p.337 of the paper (three genes cyclically repressing: lacI -| tetR -|
# cI -| lacI):
#
#   dm_i/dt = -m_i + alpha/(1 + p_j^n) + alpha0     (j represses i)
#   dp_i/dt = -beta*(p_i - m_i)
#
# m_i: scaled mRNA concentration (time in units of mRNA lifetime).
# p_i: scaled protein concentration (units of K_M, the repressor's
# Hill-function half-max).
#
# Parameter values below are transcribed directly from the curated SBML's
# own <parameter value=...> attributes for BIOMD0000000012 (fetched from
# the BioModels GitHub mirror -- see docs/adr/0024), not reconstructed:
# alpha=216.404, alpha0=0.2164, beta=0.2, n=2. Corrects an earlier value
# of beta=5 (ADR 0024): a first pass took beta=5 from a course exercise's
# Fig-2b-axis convention without noticing that exercise's own footnote --
# "beta as defined on the y-axis of Fig. 2(b) is the inverse of that
# described on p.337 of the paper" -- meant 5 was the WRONG convention for
# this file's dp_i/dt = -beta*(p_i - m_i) equation, which is written in
# the p.337 form. The curated model's own derivation confirms the p.337
# value directly: beta = tau_mRNA/tau_prot = 2min/10min = 0.2 (the ratio
# of the mRNA to protein half-lives, in time units where mRNA decay is
# rescaled to 1). Both values happen to produce sustained oscillation
# (verified for both, see tests/test_repressilator_correctness.py), so the
# earlier value shipped without an exception or a visibly broken plot --
# only a wrong parameter, the same failure shape as ADR 0023.
# ---------------------------------------------------------------------------

REPRESSILATOR_ALPHA = 216.404
REPRESSILATOR_ALPHA0 = 0.2164
REPRESSILATOR_BETA = 0.2
REPRESSILATOR_N = 2.0


def build_repressilator_antimony(
        model_name: str = "repressilator") -> str:
    """Build the Elowitz & Leibler (2000) repressilator.

    No caller-supplied kinetic parameters, for the same reason as the
    cell cycle oscillator: the model is defined by the literature's own
    standard oscillatory parameter set.
    """
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  m1' = -m1 + alpha / (1 + p3^n) + alpha0;\n"
        f"  m2' = -m2 + alpha / (1 + p1^n) + alpha0;\n"
        f"  m3' = -m3 + alpha / (1 + p2^n) + alpha0;\n"
        f"  p1' = -beta * (p1 - m1);\n"
        f"  p2' = -beta * (p2 - m2);\n"
        f"  p3' = -beta * (p3 - m3);\n"
        f"  m1 = 0; m2 = 0; m3 = 0;\n"
        f"  p1 = 1; p2 = 2; p3 = 3;\n"
        f"  alpha = {_fmt(REPRESSILATOR_ALPHA)};\n"
        f"  alpha0 = {_fmt(REPRESSILATOR_ALPHA0)};\n"
        f"  beta = {_fmt(REPRESSILATOR_BETA)};\n"
        f"  n = {_fmt(REPRESSILATOR_N)};\n"
        f"end\n"
    )


# every call clears prior loads.
# ---------------------------------------------------------------------------

_ANTIMONY_LOCK = threading.Lock()


def antimony_to_sbml(antimony_string: str,
                     model_name: str | None = None) -> str:
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
