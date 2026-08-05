"""
Terrium simulation engine (re-export shim).

This module was split into a modular package per REFACTORING_PROPOSAL.md
(Option A: domain-based split). It remains the single public entry point and
re-exports everything the original monolithic module exposed, so all existing
imports keep working unchanged:

    core.data_structures            exceptions, dataclasses, plausibility constants
    core.validation                 validate_* functions and helpers
    core.utils                      _fmt, _check_model_name, _load_runner
    continuous.model_building       antimony model construction, SBML translation
    continuous.simulations          roadrunner-backed ODE simulation entry points
    discrete.pcr / monte_carlo      discrete simulations
    discrete.molecular_dynamics     Lennard-Jones velocity Verlet (ADR 0006)
    discrete.population_genetics    Wright-Fisher family (core/analysis/
                                    probability/theoretical/two_locus)
    scenarios.wf_scenarios          scenario presets

The dual import guard below lets the shim load both as ``Tellurium`` package
member (repo root on PYTHONPATH, as the API runner does) and as a flat module
(``pythonpath = .`` from the Tellurium/ directory, as the pytest suite does).
"""

from __future__ import annotations

try:
    from Tellurium.core.data_structures import (
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
    from Tellurium.core.validation import (
        validate_michaelis_menten_params,
        validate_mm_competitive_params,
        validate_sir_params,
        validate_seir_params,
        validate_pcr_params,
        validate_monte_carlo_params,
        validate_wright_fisher_params,
        validate_md_params,
        validate_ssa_bimolecular_params,
        vmax_from_kcat,
        validate_ssa_params,
        validate_ssa_replicates_params,
    )  # type: ignore[no-redef]
    from Tellurium.continuous.model_building import (
        build_michaelis_menten_antimony,
        build_mm_competitive_antimony,
        build_sir_antimony,
        build_seir_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
    )  # type: ignore[no-redef]
    from Tellurium.continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        simulate_mm_competitive_inhibition,
        simulate_sir,
        simulate_seir,
        steady_state,
        parameter_scan,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.pcr import simulate_pcr  # type: ignore[no-redef]
    from Tellurium.discrete.monte_carlo import simulate_monte_carlo_pi  # type: ignore[no-redef]
    from Tellurium.discrete.gillespie_ssa import (
        simulate_gillespie_ssa,
        simulate_gillespie_ssa_bimolecular,
        simulate_gillespie_ssa_replicates,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.molecular_dynamics import (
        lennard_jones_force,
        lj_cluster_positions,
        _compute_lj_potential,
        simulate_molecular_dynamics,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.population_genetics.core import (
        simulate_wright_fisher,
        _clamp_wf_fst_roundoff,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.population_genetics.analysis import (
        wright_fisher_sweep,
        expected_loss_time,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.population_genetics.probability import (
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
        _normalise_stationary_vector,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.population_genetics.theoretical import (
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
    )  # type: ignore[no-redef]
    from Tellurium.discrete.population_genetics.two_locus import (
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )  # type: ignore[no-redef]
    from Tellurium.scenarios.wf_scenarios import (
        _SCENARIO_REGISTRY,
        list_scenarios,
        wright_fisher_scenario,
    )  # type: ignore[no-redef]
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
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
        validate_sir_params,
        validate_seir_params,
        validate_pcr_params,
        validate_monte_carlo_params,
        validate_wright_fisher_params,
        validate_md_params,
        validate_ssa_bimolecular_params,
        vmax_from_kcat,
        validate_ssa_params,
        validate_ssa_replicates_params,
        validate_mm_competitive_params,
    )  # type: ignore[no-redef]
    from continuous.model_building import (
        build_michaelis_menten_antimony,
        build_sir_antimony,
        build_seir_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
        build_mm_competitive_antimony,
    )  # type: ignore[no-redef]
    from continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        simulate_sir,
        simulate_seir,
        steady_state,
        parameter_scan,
        simulate_mm_competitive_inhibition,
    )  # type: ignore[no-redef]
    from discrete.pcr import simulate_pcr  # type: ignore[no-redef]
    from discrete.monte_carlo import simulate_monte_carlo_pi  # type: ignore[no-redef]
    from discrete.gillespie_ssa import (
        simulate_gillespie_ssa,
        simulate_gillespie_ssa_bimolecular,
        simulate_gillespie_ssa_replicates,
    )  # type: ignore[no-redef]
    from discrete.molecular_dynamics import (
        lennard_jones_force,
        lj_cluster_positions,
        _compute_lj_potential,
        simulate_molecular_dynamics,
    )  # type: ignore[no-redef]
    from discrete.population_genetics.core import (
        simulate_wright_fisher,
        _clamp_wf_fst_roundoff,
    )  # type: ignore[no-redef]
    from discrete.population_genetics.analysis import (
        wright_fisher_sweep,
        expected_loss_time,
    )  # type: ignore[no-redef]
    from discrete.population_genetics.probability import (
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
        _normalise_stationary_vector,
    )  # type: ignore[no-redef]
    from discrete.population_genetics.theoretical import (
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
    )  # type: ignore[no-redef]
    from discrete.population_genetics.two_locus import (
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )  # type: ignore[no-redef]
    from scenarios.wf_scenarios import (
        _SCENARIO_REGISTRY,
        list_scenarios,
        wright_fisher_scenario,
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
    "_SCENARIO_REGISTRY",
    "ModelBuildError",
    "ParameterValidation",
    "SimulationError",
    "SimulationResult",
    "TwoLocusResult",
    "_clamp_wf_fst_roundoff",
    "_compute_lj_potential",
    "_normalise_stationary_vector",
    "antimony_to_sbml",
    "build_michaelis_menten_antimony",
    "build_mm_competitive_antimony",
    "build_seir_antimony",
    "build_sir_antimony",
    "effective_size_harmonic_mean",
    "estimate_ne_from_heterozygosity",
    "expected_fixation_time",
    "expected_fst_after_split",
    "expected_loss_time",
    "kimura_fixation_probability",
    "lennard_jones_force",
    "list_scenarios",
    "lj_cluster_positions",
    "parameter_scan",
    "sbml_to_antimony",
    "simulate_gillespie_ssa",
    "simulate_gillespie_ssa_bimolecular",
    "simulate_gillespie_ssa_replicates",
    "simulate_michaelis_menten",
    "simulate_mm_competitive_inhibition",
    "simulate_molecular_dynamics",
    "simulate_monte_carlo_pi",
    "simulate_pcr",
    "simulate_sbml",
    "simulate_seir",
    "simulate_sir",
    "simulate_two_locus_wright_fisher",
    "simulate_wright_fisher",
    "steady_state",
    "theoretical_fst",
    "theoretical_ld_decay",
    "validate_md_params",
    "validate_michaelis_menten_params",
    # Competitive inhibition Michaelis-Menten
    "validate_mm_competitive_params",
    "validate_monte_carlo_params",
    "validate_pcr_params",
    "validate_sbml",
    "validate_seir_params",
    "validate_sir_params",
    "validate_ssa_bimolecular_params",
    "validate_ssa_params",
    "validate_ssa_replicates_params",
    "validate_wright_fisher_params",
    "vmax_from_kcat",
    "wright_fisher_expected_absorption_time",
    "wright_fisher_expected_fixation_time",
    "wright_fisher_expected_loss_time",
    "wright_fisher_fixation_probability",
    "wright_fisher_scenario",
    "wright_fisher_stationary_vector",
    "wright_fisher_sweep",
    "wright_fisher_transition_matrix",
    "wright_stationary_distribution",
]
