"""Core data structures and constants for the Terrium simulation engine.

This module contains the fundamental classes, dataclasses, and constants that
are used throughout the simulation engine. These include exception classes,
data containers for simulation results and parameter validation, and various
plausibility bounds and default values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Exceptions
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

# Monte Carlo parameters
MC_PLAUSIBLE_MIN_SAMPLES = 1000

# Wright-Fisher population genetics bounds
WF_PLAUSIBLE_MIN_POPULATION_SIZE = 2
WF_PLAUSIBLE_MAX_GENERATIONS = 10000
WF_PLAUSIBLE_MIN_REPLICATE_RUNS = 1
WF_PLAUSIBLE_MAX_MUTATION_RATE = 0.5
WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT = 10.0

# Molecular dynamics parameters
MD_PLAUSIBLE_MIN_PARTICLES = 2
MD_PLAUSIBLE_MAX_TIMESTEP = 0.05
MD_PLAUSIBLE_TEMPERATURE_LOW = 0.01
MD_PLAUSIBLE_TEMPERATURE_HIGH = 10.0

# Numerical solver tolerances (roadrunner defaults are 1e-12, 1e-15)
DEFAULT_RELATIVE_TOLERANCE = 1e-6
DEFAULT_ABSOLUTE_TOLERANCE = 1e-9

# Michaelis-Menten gamma parameter for steady-state calculation
GAMMA_PARAM = 1.0


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
    replicate_data: Optional[List[List[float]]] = None
    replicate_colnames: Optional[List[str]] = None
    wright_fisher_params: Optional[Dict[str, Any]] = None

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

    def fixation_analysis(self) -> Dict[str, Any]:
        """Return fixation statistics from per-replicate tracking.

        Requires ``wright_fisher_params`` (set automatically by
        ``simulate_wright_fisher``). Returns the generation each
        replicate first reached frequency 1.0 (A) or 0.0 (a), the
        proportion of replicates that fixed for each allele, and the
        mean time to fixation among those that fixed. Also reports the
        unconditional absorption statistics: how many replicates
        reached either boundary within the window and the mean time to
        absorption among those (replicates still polymorphic at the
        end of the window are censored and excluded from the mean --
        they are counted in ``n_polymorphic`` instead).

        Replicates that never fix within the simulation window have
        ``-1`` for their fixation generation.
        """
        if self.wright_fisher_params is None:
            return {"error": "no Wright-Fisher parameters stored"}
        fix_A = self.wright_fisher_params.get("fixation_gen_A", [])
        fix_a = self.wright_fisher_params.get("fixation_gen_a", [])
        if not fix_A and not fix_a:
            return {"error": "no fixation data available"}
        n_reps = len(fix_A)
        n_fixed_A = sum(1 for g in fix_A if g >= 0)
        n_fixed_a = sum(1 for g in fix_a if g >= 0)
        n_poly = n_reps - n_fixed_A - n_fixed_a
        times_A = [g for g in fix_A if g >= 0]
        times_a = [g for g in fix_a if g >= 0]
        info: Dict[str, Any] = {
            "n_replicates": n_reps,
            "n_fixed_A": n_fixed_A,
            "n_fixed_a": n_fixed_a,
            "n_polymorphic": n_poly,
            "prop_fixed_A": n_fixed_A / n_reps if n_reps else 0.0,
            "prop_fixed_a": n_fixed_a / n_reps if n_reps else 0.0,
            "fixation_gen_A": fix_A,
            "fixation_gen_a": fix_a,
        }
        if times_A:
            info["mean_fixation_time_A"] = float(np.mean(times_A))
            info["sd_fixation_time_A"] = float(np.std(times_A, ddof=1))
            info["min_fixation_time_A"] = int(min(times_A))
            info["max_fixation_time_A"] = int(max(times_A))
        if times_a:
            info["mean_fixation_time_a"] = float(np.mean(times_a))
            info["sd_fixation_time_a"] = float(np.std(times_a, ddof=1))
            info["min_fixation_time_a"] = int(min(times_a))
            info["max_fixation_time_a"] = int(max(times_a))
        absorbed = times_A + times_a
        n_absorbed = n_fixed_A + n_fixed_a
        info["n_absorbed"] = n_absorbed
        if absorbed:
            info["mean_absorption_time"] = float(np.mean(absorbed))
            if len(absorbed) > 1:
                info["sd_absorption_time"] = float(
                    np.std(absorbed, ddof=1))
        return info

    def theoretical_heterozygosity(self) -> List[float]:
        """Return the expected heterozygosity trajectory under neutral drift.

        Computed as ``H_t = H_0 * (1 - 1/(2N))^t`` for constant N, or
        the cumulative product when ``population_size_series`` was used.

        Returns an empty list when selection or mutation was active
        (theoretical H is more complex), or when WF params are not
        available.
        """
        p = self.wright_fisher_params
        if p is None:
            return []
        if p.get("selection_coefficient", 0.0) != 0.0:
            return []
        if p.get("mutation_rate", 0.0) != 0.0:
            return []
        if p.get("n_demes", 1) > 1:
            return []
        pop_size = p.get("population_size")
        if not pop_size:
            return []
        if isinstance(pop_size, list):
            # Variable population size
            het = []
            h_prev = p.get("starting_heterozygosity", 0.5)
            for n in pop_size:
                h_prev *= (1 - 1 / (2 * n)) if n > 0 else 0
                het.append(h_prev)
            return het
        else:
            # Constant population size
            n_generations = len(self.time)
            h0 = p.get("starting_heterozygosity", 0.5)
            if pop_size <= 0:
                return [0.0] * n_generations
            return [
                h0 * ((1 - 1 / (2 * pop_size)) ** t)
                for t in range(n_generations)
            ]
