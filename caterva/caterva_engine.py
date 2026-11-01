"""
Caterva simulation engine (re-export shim).

This module was split into a modular package per REFACTORING_PROPOSAL.md
(Option A: domain-based split). It remains the single public entry point and
re-exports everything the original monolithic module exposed, so all existing
imports keep working unchanged:

    core.data_structures            exceptions, dataclasses, plausibility constants
    core.validation                 validate_* functions and helpers
    core.utils                      _fmt, _check_model_name, _load_runner
    continuous.model_building       antimony model construction, SBML translation
    continuous.simulations          roadrunner-backed ODE simulation entry points
    discrete.gillespie_ssa          exact stochastic chemical kinetics

Population genetics, epidemiology, PCR, Monte Carlo, the oscillators and the
Lennard-Jones toy MD were moved to archive/legacy_domains/ on 2026-09-27,
when Caterva narrowed to enzymes (tag v0.4.0 still runs them).

The dual import guard below lets the shim load both as ``caterva`` package
member (repo root on PYTHONPATH, as the API runner does) and as a flat module
(``pythonpath = .`` from the caterva/ directory, as the pytest suite does).
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


try:
    from caterva.core.data_structures import (
        ModelBuildError,
        SimulationError,
        ParameterValidation,
        SimulationResult,
        KM_PLAUSIBLE_MIN_MM,
        KM_PLAUSIBLE_MAX_MM,
        R0_IMPLAUSIBLE_ABOVE,
        PCR_MIN_EFFICIENCY,
        PCR_MAX_EFFICIENCY,
        PCR_PLAUSIBLE_LOW_EFFICIENCY,
        MC_PLAUSIBLE_MIN_SAMPLES,
        WF_PLAUSIBLE_MIN_POPULATION_SIZE,
        WF_PLAUSIBLE_MAX_GENERATIONS,
        WF_PLAUSIBLE_MIN_REPLICATE_RUNS,
        WF_PLAUSIBLE_MAX_MUTATION_RATE,
        WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT,
        MD_PLAUSIBLE_MIN_PARTICLES,
        MD_PLAUSIBLE_MAX_TIMESTEP,
        MD_PLAUSIBLE_TEMPERATURE_LOW,
        MD_PLAUSIBLE_TEMPERATURE_HIGH,
        SSA_PLAUSIBLE_MAX_RATE,
        SSA_PLAUSIBLE_MIN_POPULATION,
        SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE,
        ENZYME_CONC_MM_RATIO_FLAG_ABOVE,
        SSA_PLAUSIBLE_MIN_REPLICATES,
        DEFAULT_RELATIVE_TOLERANCE,
        DEFAULT_ABSOLUTE_TOLERANCE,
        GAMMA_PARAM,
    )  # type: ignore[no-redef]
    from caterva.core.validation import (
        validate_michaelis_menten_params,
        validate_mm_competitive_params,
        validate_ssa_bimolecular_params,
        vmax_from_kcat,
        validate_ssa_params,
        validate_ssa_replicates_params,
    )  # type: ignore[no-redef]
    from caterva.continuous.model_building import (
        build_michaelis_menten_antimony,
        build_mm_competitive_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
    )  # type: ignore[no-redef]
    from caterva.continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        simulate_mm_competitive_inhibition,
        steady_state,
        parameter_scan,
    )  # type: ignore[no-redef]
    from caterva.discrete.gillespie_ssa import (
        simulate_gillespie_ssa,
        simulate_gillespie_ssa_bimolecular,
        simulate_gillespie_ssa_replicates,
    )  # type: ignore[no-redef]
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.data_structures import (
        ModelBuildError,
        SimulationError,
        ParameterValidation,
        SimulationResult,
        KM_PLAUSIBLE_MIN_MM,
        KM_PLAUSIBLE_MAX_MM,
        R0_IMPLAUSIBLE_ABOVE,
        PCR_MIN_EFFICIENCY,
        PCR_MAX_EFFICIENCY,
        PCR_PLAUSIBLE_LOW_EFFICIENCY,
        MC_PLAUSIBLE_MIN_SAMPLES,
        WF_PLAUSIBLE_MIN_POPULATION_SIZE,
        WF_PLAUSIBLE_MAX_GENERATIONS,
        WF_PLAUSIBLE_MIN_REPLICATE_RUNS,
        WF_PLAUSIBLE_MAX_MUTATION_RATE,
        WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT,
        MD_PLAUSIBLE_MIN_PARTICLES,
        MD_PLAUSIBLE_MAX_TIMESTEP,
        MD_PLAUSIBLE_TEMPERATURE_LOW,
        MD_PLAUSIBLE_TEMPERATURE_HIGH,
        SSA_PLAUSIBLE_MAX_RATE,
        SSA_PLAUSIBLE_MIN_POPULATION,
        SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE,
        ENZYME_CONC_MM_RATIO_FLAG_ABOVE,
        SSA_PLAUSIBLE_MIN_REPLICATES,
        DEFAULT_RELATIVE_TOLERANCE,
        DEFAULT_ABSOLUTE_TOLERANCE,
        GAMMA_PARAM,
    )  # type: ignore[no-redef]
    from core.validation import (
        validate_michaelis_menten_params,
        validate_ssa_bimolecular_params,
        vmax_from_kcat,
        validate_ssa_params,
        validate_ssa_replicates_params,
        validate_mm_competitive_params,
    )  # type: ignore[no-redef]
    from continuous.model_building import (
        build_michaelis_menten_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
        build_mm_competitive_antimony,
    )  # type: ignore[no-redef]
    from continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        steady_state,
        parameter_scan,
        simulate_mm_competitive_inhibition,
    )  # type: ignore[no-redef]
    from discrete.gillespie_ssa import (
        simulate_gillespie_ssa,
        simulate_gillespie_ssa_bimolecular,
        simulate_gillespie_ssa_replicates,
    )  # type: ignore[no-redef]

__all__ = [
    "DEFAULT_ABSOLUTE_TOLERANCE",
    "DEFAULT_RELATIVE_TOLERANCE",
    "ENZYME_CONC_MM_RATIO_FLAG_ABOVE",
    "GAMMA_PARAM",
    "KM_PLAUSIBLE_MAX_MM",
    "KM_PLAUSIBLE_MIN_MM",
    "MC_PLAUSIBLE_MIN_SAMPLES",
    "MD_PLAUSIBLE_MAX_TIMESTEP",
    "MD_PLAUSIBLE_MIN_PARTICLES",
    "MD_PLAUSIBLE_TEMPERATURE_HIGH",
    "MD_PLAUSIBLE_TEMPERATURE_LOW",
    "PCR_MAX_EFFICIENCY",
    "PCR_MIN_EFFICIENCY",
    "PCR_PLAUSIBLE_LOW_EFFICIENCY",
    "R0_IMPLAUSIBLE_ABOVE",
    "SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE",
    "SSA_PLAUSIBLE_MAX_RATE",
    "SSA_PLAUSIBLE_MIN_POPULATION",
    "SSA_PLAUSIBLE_MIN_REPLICATES",
    "WF_PLAUSIBLE_MAX_GENERATIONS",
    "WF_PLAUSIBLE_MAX_MUTATION_RATE",
    "WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT",
    "WF_PLAUSIBLE_MIN_POPULATION_SIZE",
    "WF_PLAUSIBLE_MIN_REPLICATE_RUNS",
    "ModelBuildError",
    "ParameterValidation",
    "SimulationError",
    "SimulationResult",
    "antimony_to_sbml",
    "build_michaelis_menten_antimony",
    "build_mm_competitive_antimony",
    "parameter_scan",
    "sbml_to_antimony",
    "simulate_gillespie_ssa",
    "simulate_gillespie_ssa_bimolecular",
    "simulate_gillespie_ssa_replicates",
    "simulate_michaelis_menten",
    "simulate_mm_competitive_inhibition",
    "simulate_sbml",
    "steady_state",
    "validate_michaelis_menten_params",
    # Competitive inhibition Michaelis-Menten
    "validate_mm_competitive_params",
    "validate_sbml",
    "validate_ssa_bimolecular_params",
    "validate_ssa_params",
    "validate_ssa_replicates_params",
    "vmax_from_kcat",
]
