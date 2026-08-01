"""Wright-Fisher scenario presets."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from Tellurium.core.data_structures import (SimulationResult)
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (SimulationResult)

try:
    from Tellurium.discrete.population_genetics.core import simulate_wright_fisher
except ModuleNotFoundError:
    from discrete.population_genetics.core import simulate_wright_fisher


# ---------------------------------------------------------------------------
# Scenario presets for the Wright-Fisher model
# ---------------------------------------------------------------------------

_SCENARIO_REGISTRY: Dict[str, Dict[str, Any]] = {
    "neutral-drift": {
        "description": "Neutral drift at a moderate population size",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 50,
    },
    "rapid-drift": {
        "description": "Small population — drift is fast and visible",
        "population_size": 10,
        "starting_frequency": 0.5,
        "generations": 50,
        "replicate_runs": 50,
    },
    "mutation-drift": {
        "description": "Mutation-drift balance — heterozygosity reaches H_eq",
        "population_size": 50,
        "starting_frequency": 0.5,
        "generations": 500,
        "replicate_runs": 100,
        "mutation_rate": 0.02,
    },
    "weak-selection": {
        "description": "Weak positive selection (s=0.03) — slight bias",
        "population_size": 100,
        "starting_frequency": 0.3,
        "generations": 300,
        "replicate_runs": 100,
        "selection_coefficient": 0.03,
        "dominance": None,
    },
    "strong-selection": {
        "description": "Strong positive selection (s=0.2) — beneficial allele fixes rapidly",
        "population_size": 100,
        "starting_frequency": 0.2,
        "generations": 100,
        "replicate_runs": 100,
        "selection_coefficient": 0.2,
        "dominance": None,
    },
    "purifying-selection": {
        "description": "Negative selection (s=-0.1) — deleterious allele rarely fixes",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 300,
        "replicate_runs": 100,
        "selection_coefficient": -0.1,
        "dominance": None,
    },
    "bottleneck": {
        "description": "Population bottleneck: N=100 drops to N=5 at gen 50, then recovers",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 100,
    },
    "island-model": {
        "description": "Wright's island model: 10 demes, low migration (m=0.01)",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 50,
        "n_demes": 10,
        "migration_rate": 0.01,
    },
    "structured-neutral": {
        "description": "10 demes, no migration — demes drift independently",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 50,
        "n_demes": 10,
        "migration_rate": 0.0,
    },
    "founder-effect": {
        "description": "Founder event: N=20, rare allele (p0=0.1) — drift decides its fate",
        "population_size": 20,
        "starting_frequency": 0.1,
        "generations": 200,
        "replicate_runs": 100,
    },
    "population-expansion": {
        "description": "Population expansion: N=10 grows to N=1000 over 200 generations",
        "population_size": 10,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 100,
    },
    "balancing-selection": {
        "description": "Overdominance (h=2, s=0.2): heterozygote advantage keeps both alleles at p*=2/3",
        "population_size": 100,
        "starting_frequency": 0.1,
        "generations": 300,
        "replicate_runs": 100,
        "selection_coefficient": 0.2,
        "dominance": 2.0,
    },
    "stepping-stone": {
        "description": "Stepping-stone: 10 demes on a ring, m=0.01 — Fst rises faster than island model",
        "population_size": 100,
        "starting_frequency": 0.5,
        "generations": 200,
        "replicate_runs": 50,
        "n_demes": 10,
        "migration_rate": 0.01,
        "migration_model": "stepping-stone",
    },
}


def list_scenarios() -> List[str]:
    """Return the names of all available WF scenario presets."""
    return list(_SCENARIO_REGISTRY.keys())


def wright_fisher_scenario(
    name: str, seed: int | None = None,
    return_replicate_data: bool = False,
    **overrides: Any,
) -> SimulationResult:
    """Run a named WF teaching scenario.

    Available scenarios (use ``list_scenarios()`` to list them):
        - neutral-drift, rapid-drift
        - mutation-drift
        - weak-selection, strong-selection, purifying-selection
        - balancing-selection (overdominance, h=2)
        - bottleneck
        - island-model, structured-neutral, stepping-stone
        - founder-effect, population-expansion

    Any keyword ``**overrides`` is merged into the scenario's parameter
    dict before running, so callers can tweak e.g. ``generations`` or
    ``replicate_runs`` without modifying the preset.

    Args:
        name: scenario name (must be in the registry)
        seed: optional RNG seed
        return_replicate_data: forward to ``simulate_wright_fisher``
        **overrides: parameter overrides for this run

    Returns:
        SimulationResult from the scenario's parameter set
    """
    if name not in _SCENARIO_REGISTRY:
        known = ", ".join(sorted(_SCENARIO_REGISTRY))
        raise KeyError(
            f"unknown scenario {name!r}; choose from: {known}")

    params = dict(_SCENARIO_REGISTRY[name])
    params.pop("description", None)
    params.update(overrides)

    # Build population_size_series for scenarios that define it
    if name == "bottleneck" and "population_size_series" not in overrides:
        n_before = params.get("population_size", 100)
        gens = params.get("generations", 200)
        series = [n_before] * (gens + 1)
        # Bottleneck at generation 50: drops to 5 for 10 generations
        bottleneck_start = 50
        bottleneck_end = 60
        for i in range(bottleneck_start, min(bottleneck_end, gens + 1)):
            series[i] = 5
        params["population_size_series"] = series

    if (name == "population-expansion"
            and "population_size_series" not in overrides):
        n_start = params.get("population_size", 10)
        n_end = 1000
        gens = params.get("generations", 200)
        series = []
        for i in range(gens + 1):
            frac = i / gens if gens > 0 else 1.0
            series.append(int(round(n_start + (n_end - n_start) * frac)))
        params["population_size_series"] = series

    return simulate_wright_fisher(
        **params,
        seed=seed,
        return_replicate_data=return_replicate_data,
    )
