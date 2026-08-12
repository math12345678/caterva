"""Wright-Fisher post-simulation analysis: sweeps, expected loss time."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

try:
    from Terium.discrete.population_genetics.core import (simulate_wright_fisher)
except ModuleNotFoundError:  # flat mode: Terium/ on sys.path, no repo root
    from discrete.population_genetics.core import (simulate_wright_fisher)  # type: ignore[no-redef]

def wright_fisher_sweep(
    parameter: str,
    values: Sequence[float],
    **fixed_params: Any,
) -> List[Dict[str, Any]]:
    """Run ``simulate_wright_fisher`` once per value of a parameter and
    summarize the final generation of each run.

    Sweep any parameter that ``simulate_wright_fisher`` accepts (e.g.
    ``population_size``, ``starting_frequency``, ``mutation_rate``,
    ``selection_coefficient``, ``dominance``, ``migration_rate``,
    ``n_demes``); all other parameters are fixed at the values given in
    ``**fixed_params`` (defaults are used for the rest). Each run uses a
    shared seed if one is provided in ``**fixed_params`` (then the sweep
    is fully reproducible); otherwise runs are independent.

    Returns a list (one dict per value, in order) with:
    ``parameter`` (name), ``value``, ``final_mean_frequency``,
    ``final_heterozygosity``, ``prop_fixed_A``, ``prop_fixed_a``, and
    ``final_fst`` (only when the run used a structured population).

    Raises:
        ValueError: if ``parameter`` is not a valid
            ``simulate_wright_fisher`` argument, or a value is not
            accepted by validation.
    """
    import inspect
    sig = inspect.signature(simulate_wright_fisher)
    if parameter not in sig.parameters:
        raise ValueError(
            f"'{parameter}' is not a parameter of "
            f"simulate_wright_fisher (got {list(sig.parameters)})")
    if parameter == "starting_frequency" and parameter not in fixed_params:
        raise ValueError(
            "starting_frequency is already being swept; pass the other "
            "parameters as keyword arguments")
    required_defaults = {
        "generations": 200,
        "population_size": 100,
        "starting_frequency": 0.5,
    }
    kwargs = dict(required_defaults)
    kwargs.update(fixed_params)
    out: List[Dict[str, Any]] = []
    for value in values:
        run_kwargs = dict(kwargs)
        run_kwargs[parameter] = value
        result = simulate_wright_fisher(**run_kwargs)  # type: ignore[arg-type]
        fa = result.fixation_analysis()
        row: Dict[str, Any] = {
            "parameter": parameter,
            "value": float(value),
            "final_mean_frequency": result.column("mean_frequency")[-1],
            "final_heterozygosity": result.column("heterozygosity")[-1],
            "prop_fixed_A": fa["prop_fixed_A"],
            "prop_fixed_a": fa["prop_fixed_a"],
        }
        if "fst" in result.colnames:
            row["final_fst"] = result.column("fst")[-1]
        out.append(row)
    return out

def expected_loss_time(
    starting_frequency: float,
    population_size: int,
) -> float:
    """Kimura & Ohta's (1969) expected time to loss of a neutral
    allele, given that it is lost.

    The mirror image of ``expected_fixation_time``: for a diploid
    population of size N and an allele at initial frequency p0::

        t_bar = -4N * p0 * ln(p0) / (1 - p0)

    generations, and ``t_loss(p) = t_fix(1 - p)`` exactly (the two
    closed forms are symmetric). An allele already lost (p0 = 0) has
    loss time 0; as p0 -> 1 the loss time approaches 4N generations (a
    nearly fixed allele destined to be lost must first drift all the
    way down).

    Raises ValueError for N <= 0 or p0 outside [0, 1].
    """
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")
    if starting_frequency == 0.0:
        return 0.0
    if starting_frequency == 1.0:
        return 4.0 * population_size
    p0 = starting_frequency
    N = int(population_size)
    return -4.0 * N * p0 * math.log(p0) / (1.0 - p0)
