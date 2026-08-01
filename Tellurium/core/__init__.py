"""Core data structures, validation, and utilities for the Terrium simulation engine."""

# Re-export everything from submodules for backward compatibility
try:
    from .data_structures import (
        ModelBuildError,
        SimulationError,
        ParameterValidation,
        SimulationResult,
        DEFAULT_RELATIVE_TOLERANCE,
        DEFAULT_ABSOLUTE_TOLERANCE,
        GAMMA_PARAM,
        KM_PLAUSIBLE_MIN_MM,
        KM_PLAUSIBLE_MAX_MM,
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
    )
except ImportError:
    # Fallback during development when modules aren't complete yet
    pass

try:
    from .validation import (
        validate_michaelis_menten_params,
        validate_sir_params,
        validate_seir_params,
        validate_pcr_params,
        validate_monte_carlo_params,
        validate_wright_fisher_params,
        validate_md_params,
    )
except ImportError:
    # Fallback during development when modules aren't complete yet
    pass

try:
    from .utils import _finite_positive, _fmt, _check_model_name
except ImportError:
    # Fallback during development when modules aren't complete yet
    pass

__all__ = [
    # Exceptions
    "ModelBuildError",
    "SimulationError",
    # Data classes
    "ParameterValidation",
    "SimulationResult",
    # Constants
    "DEFAULT_RELATIVE_TOLERANCE",
    "DEFAULT_ABSOLUTE_TOLERANCE",
    "GAMMA_PARAM",
    "KM_PLAUSIBLE_MIN_MM",
    "KM_PLAUSIBLE_MAX_MM",
    "PCR_MIN_EFFICIENCY",
    "PCR_MAX_EFFICIENCY",
    "PCR_PLAUSIBLE_LOW_EFFICIENCY",
    "MC_PLAUSIBLE_MIN_SAMPLES",
    "WF_PLAUSIBLE_MIN_POPULATION_SIZE",
    "WF_PLAUSIBLE_MAX_GENERATIONS",
    "WF_PLAUSIBLE_MIN_REPLICATE_RUNS",
    "WF_PLAUSIBLE_MAX_MUTATION_RATE",
    "WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT",
    "MD_PLAUSIBLE_MIN_PARTICLES",
    "MD_PLAUSIBLE_MAX_TIMESTEP",
    "MD_PLAUSIBLE_TEMPERATURE_LOW",
    "MD_PLAUSIBLE_TEMPERATURE_HIGH",
    # Validation functions
    "validate_michaelis_menten_params",
    "validate_sir_params",
    "validate_seir_params",
    "validate_pcr_params",
    "validate_monte_carlo_params",
    "validate_wright_fisher_params",
    "validate_md_params",
    # Utility functions
    "_finite_positive",
    "_fmt",
    "_check_model_name",
]
