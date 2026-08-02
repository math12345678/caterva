"""Shared helpers: antimony formatting, model-name guard, roadrunner loader."""

from __future__ import annotations


import roadrunner
try:
    from Tellurium.core.data_structures import (ModelBuildError, SimulationError, DEFAULT_RELATIVE_TOLERANCE, DEFAULT_ABSOLUTE_TOLERANCE)
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ModelBuildError, SimulationError, DEFAULT_RELATIVE_TOLERANCE, DEFAULT_ABSOLUTE_TOLERANCE)  # type: ignore[no-redef]

def _fmt(value: float) -> str:
    """Format a float for Antimony without losing precision to repr quirks."""
    return repr(float(value))



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
