"""
Terrium simulation engine: continuous (antimony/SBML/roadrunner) and
discrete (direct Python) domains, built up one stage at a time per
docs/CONSTITUTION.md.

Continuous-time domains (Tier-2 ODE, via antimony -> SBML -> roadrunner):
  * Michaelis-Menten enzyme kinetics
  * SIR / SEIR epidemiological modeling

Continuous-time domains (direct Python, velocity Verlet -- see ADR 0006
for why this bypasses antimony/roadrunner):
  * Molecular dynamics (Lennard-Jones cluster)

Discrete/stochastic domains (direct Python, no ODE solver -- see ADR 0002
for why continuous-vs-discrete is a per-domain decision, not a default):
  * PCR amplification (deterministic recurrence)
  * Monte Carlo pi estimation (stochastic, ADR 0005 RNG convention)
  * Wright-Fisher population genetics / neutral drift (stochastic, ADR 0005)
  * Two-locus linkage disequilibrium (stochastic, ADR 0005)

Design notes
------------
The full ``tellurium`` umbrella package pulls in python-libcombine and
python-libnuml, which are only needed for COMBINE archives and numerical
markup -- neither of which Terrium uses (see ADR 0001). This module targets
the three engines that actually do the work and that install cleanly, for
the continuous-time domains:

    antimony  -- human-readable model definition -> SBML
    libsbml   -- SBML validation
    roadrunner -- ODE integration

Discrete/stochastic domains use numpy directly and never touch antimony/
libsbml/roadrunner at all.

Parameter plausibility checking deliberately mirrors the flagged /
flag_reason pattern already established in Tests/brenda_client.py, so a
value that BRENDA flagged as implausible stays flagged when it reaches the
simulation layer instead of silently becoming a "confirmed" model input.
Every domain in this file follows the same ok/flagged/flag_reason contract
via the shared ParameterValidation and SimulationResult dataclasses below,
regardless of whether it's continuous or discrete.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import antimony
import libsbml
import numpy as np
import roadrunner

__all__ = [
    "DEFAULT_ABSOLUTE_TOLERANCE",
    "DEFAULT_RELATIVE_TOLERANCE",
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
    "WF_PLAUSIBLE_MAX_GENERATIONS",
    "WF_PLAUSIBLE_MAX_MUTATION_RATE",
    "WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT",
    "WF_PLAUSIBLE_MIN_POPULATION_SIZE",
    "WF_PLAUSIBLE_MIN_REPLICATE_RUNS",
    "ModelBuildError",
    "ParameterValidation",
    "SimulationError",
    "SimulationResult",
    "TwoLocusResult",
    "antimony_to_sbml",
    "build_michaelis_menten_antimony",
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
    "simulate_michaelis_menten",
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
    "validate_monte_carlo_params",
    "validate_pcr_params",
    "validate_sbml",
    "validate_seir_params",
    "validate_sir_params",
    "validate_wright_fisher_params",
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
        n_fixed_A = int(np.sum(np.array(fix_A, dtype=np.int64) >= 0))
        n_fixed_a = int(np.sum(np.array(fix_a, dtype=np.int64) >= 0))
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
        gens = p.get("generations", 0)
        p0 = p.get("starting_frequency", 0.5)
        h0 = 2.0 * p0 * (1.0 - p0)
        n_series = p.get("population_size_series")
        result = [h0]
        for t in range(1, gens + 1):
            if n_series is not None:
                n = n_series[t - 1]
            else:
                n = p.get("population_size", 100)
            decay = 1.0 - 1.0 / (2.0 * n)
            result.append(result[-1] * decay)
        return result

    def theoretical_frequency(self) -> List[float]:
        """Return the deterministic allele-frequency trajectory under
        haploid selection (no dominance), or an empty list if the
        params are unavailable or the model includes mutation.

        For ``dominance=None`` with ``selection_coefficient != 0``,
        the closed-form solution is:
        ``p_t = p_0 / (p_0 + (1 - p_0) * (1 + s)^(-t))``.

        For diploid selection with dominance h, an iterative
        deterministic trajectory is computed instead.
        """
        p = self.wright_fisher_params
        if p is None:
            return []
        if p.get("mutation_rate", 0.0) != 0.0:
            return []
        s = p.get("selection_coefficient", 0.0)
        if s == 0.0:
            return []
        gens = p.get("generations", 0)
        p0 = p.get("starting_frequency", 0.5)
        h = p.get("dominance")
        result = [p0]
        p_det = p0
        for _ in range(gens):
            if h is None:
                p_det = p_det * (1.0 + s) / (1.0 + p_det * s)
            else:
                p = p_det
                p2 = p * p
                pq = p * (1.0 - p)
                q2 = (1.0 - p) * (1.0 - p)
                w_bar = (p2 * (1.0 + s) + 2.0 * pq * (1.0 + h * s) + q2)
                p_det = (p2 * (1.0 + s) + pq * (1.0 + h * s)) / w_bar
            result.append(p_det)
        return result

    def describe(self) -> str:
        """Return a human-readable summary of the simulation result."""
        lines = [f"Model: {self.model_name}"]
        gen = self.column("generation")
        lines.append(f"Generations: 0 – {int(gen[-1])}")
        lines.append(f"Rows: {len(self.data)}")
        if self.validation.flagged:
            lines.append(f"Flagged: {self.validation.flag_reason}")
        if "mean_frequency" in self.colnames:
            mf = self.column("mean_frequency")
            lines.append(f"Final mean freq: {mf[-1]:.4f}")
        if "heterozygosity" in self.colnames:
            h = self.column("heterozygosity")
            lines.append(f"Final heterozygosity: {h[-1]:.4f}")
            th = self.theoretical_heterozygosity()
            if th:
                lines.append(f"Expected heterozygosity (final): {th[-1]:.4f}")
        if "n_A_fixed" in self.colnames and "n_a_fixed" in self.colnames:
            nA = int(self.column("n_A_fixed")[-1])
            na = int(self.column("n_a_fixed")[-1])
            lines.append(f"Fixed: A={nA}, a={na}")
        fa = self.fixation_analysis()
        if "prop_fixed_A" in fa:
            lines.append(
                f"Fixation proportions: A={fa['prop_fixed_A']:.3f}, "
                f"a={fa['prop_fixed_a']:.3f}, "
                f"poly={fa['n_polymorphic']}")
        if "mean_fixation_time_A" in fa:
            lines.append(
                f"Mean fixation time A: {fa['mean_fixation_time_A']:.1f} "
                f"± {fa['sd_fixation_time_A']:.1f} gens")
        if "mean_fixation_time_a" in fa:
            lines.append(
                f"Mean fixation time a: {fa['mean_fixation_time_a']:.1f} "
                f"± {fa['sd_fixation_time_a']:.1f} gens")
        return "\n".join(lines)

    def summarize(self) -> Dict[str, Any]:
        """Return a dict of key result statistics for the final generation.

        Includes mean frequency, heterozygosity, fixation counts,
        standard errors, theoretical expectations, and fixation
        analysis (when available).
        """
        info: Dict[str, Any] = {
            "model_name": self.model_name,
            "generations": int(self.final("generation")),
            "n_rows": len(self.data),
            "flagged": self.validation.flagged,
        }
        if "mean_frequency" in self.colnames:
            info["final_mean_frequency"] = self.final("mean_frequency")
        if "heterozygosity" in self.colnames:
            info["final_heterozygosity"] = self.final("heterozygosity")
        if "n_A_fixed" in self.colnames and "n_a_fixed" in self.colnames:
            info["n_A_fixed"] = int(self.final("n_A_fixed"))
            info["n_a_fixed"] = int(self.final("n_a_fixed"))
        if "mean_frequency_se" in self.colnames:
            info["final_mean_frequency_se"] = self.final("mean_frequency_se")
        if "heterozygosity_se" in self.colnames:
            info["final_heterozygosity_se"] = self.final("heterozygosity_se")
        if self.validation.flagged:
            info["flag_reason"] = self.validation.flag_reason
        th = self.theoretical_heterozygosity()
        if th:
            info["expected_heterozygosity_final"] = th[-1]
            info["expected_heterozygosity_trajectory"] = th
        tf = self.theoretical_frequency()
        if tf:
            info["expected_frequency_final"] = tf[-1]
            info["expected_frequency_trajectory"] = tf
        fa = self.fixation_analysis()
        if "prop_fixed_A" in fa:
            info["fixation"] = fa
        return info

    def allele_frequency_spectrum(
            self, generation: int | None = None,
            bins: int = 10) -> Dict[str, Any]:
        """Return the distribution of allele A frequencies across
        replicates at a given generation.

        When ``generation`` is None (default), uses the final generation,
        taken from the per-replicate frequencies stored in
        ``wright_fisher_params``. For other generations,
        ``return_replicate_data=True`` must have been set at simulation
        time.

        For structured populations (``n_demes > 1``), the spectrum pools
        all demes across all replicates.

        Returns a dict with ``generation``, ``bin_edges`` (len bins+1),
        ``counts`` (len bins), and ``n_observations``.
        """
        if self.wright_fisher_params is None:
            return {"error": "no Wright-Fisher parameters stored"}
        if generation is None:
            freqs = self.wright_fisher_params.get("final_frequencies")
            gen = int(self.wright_fisher_params.get("generations", 0))
            if freqs is None:
                return {"error": "no final frequencies stored"}
            freqs = [float(f) for f in freqs]
        else:
            if self.replicate_data is None:
                return {
                    "error": "replicate_data required for non-final "
                             "generations; re-run with "
                             "return_replicate_data=True"}
            gen_row = None
            for row in self.replicate_data:
                if int(row[0]) == generation:
                    gen_row = row
                    break
            if gen_row is None:
                return {
                    "error": f"no data for generation {generation}"}
            freqs = [float(f) for f in gen_row[1:]]
            gen = int(generation)
        if not freqs:
            return {"error": "no frequencies available"}
        hist, edges = np.histogram(freqs, bins=bins, range=(0.0, 1.0))
        return {
            "generation": gen,
            "bin_edges": [float(e) for e in edges],
            "counts": [int(c) for c in hist],
            "n_observations": len(freqs),
        }

    def estimate_ne(self) -> Dict[str, Any]:
        """Estimate the effective population size from the rate of
        heterozygosity decay.

        Under neutral drift the expected heterozygosity decays as
        ``H_t = H_0 * (1 - 1/(2N))^t``, so a linear regression of
        ``ln(H_t)`` on ``t`` gives ``slope = ln(1 - 1/(2N))`` and
        ``Ne_hat = 1 / (2 * (1 - exp(slope)))``.

        Returns a dict with ``method`` ("heterozygosity_decay"),
        ``ne_estimate``, ``decay_rate_per_generation``,
        ``n_generations_used``, and a note that selection, mutation,
        and migration bias the estimate. Use ``estimate_ne_variance()``
        for the variance method (requires replicate data).

        Returns ``{"error": ...}`` when fewer than 3 non-zero
        heterozygosity values are available.
        """
        H = self.column("heterozygosity")
        if not H:
            return {"error": "no heterozygosity data available"}
        return estimate_ne_from_heterozygosity(H)

    def estimate_ne_variance(self) -> Dict[str, Any]:
        """Estimate the effective population size from the variance of
        allele frequency change across replicates (the variance method,
        Nei & Tajima 1981).

        Requires ``return_replicate_data=True`` at simulation time.

        For each generation interval ``t -> t+1``, the per-replicate
        frequency change has variance ``Var(Δp) = p(1-p) / (2 Ne)``
        under pure drift, giving per-generation estimates
        ``Ne_hat = mean(p(1-p)) / (2 * Var(Δp))``. Generations with
        ``Var(Δp) = 0`` (no drift observed) are excluded.

        NOTE: this estimator is biased upward as drift accumulates
        (observed ``p_bar(1-p_bar)`` overestimates ``E[p(1-p)]``), so
        prefer ``estimate_ne()`` for a quantitative answer; this method
        is provided for teaching the classical estimator.

        Returns a dict with ``ne_estimate`` (mean over usable
        generation intervals), ``per_generation_ne``, ``n_generations``
        (usable intervals), ``n_replicates``.

        Returns ``{"error": ...}`` when replicate data is missing or
        there are too few replicates (< 2).
        """
        if self.replicate_data is None or len(self.replicate_data) < 2:
            return {
                "error": "estimate_ne_variance requires "
                         "return_replicate_data=True and at least 2 "
                         "recorded generations"}
        freqs = np.asarray(
            [row[1:] for row in self.replicate_data], dtype=np.float64)
        if freqs.shape[0] < 3:
            return {"error": "at least 3 generations are required"}
        if freqs.shape[1] < 2:
            return {"error": "at least 2 replicates are required"}
        if self.wright_fisher_params is None:
            return {"error": "no Wright-Fisher parameters stored"}

        # Unstructured replicates only: demes within a replicate are not
        # independent drift units, so pool only across replicate index
        structured = self.wright_fisher_params.get("n_demes", 1) > 1
        if structured:
            reps = self.wright_fisher_params.get("replicate_runs", 1)
            n_demes = self.wright_fisher_params.get("n_demes", 1)
            if freqs.shape[1] != reps * n_demes:
                return {"error": "replicate_data shape unexpected"}
            # Mean across demes per replicate -> one frequency per replicate
            freqs = freqs.reshape(freqs.shape[0], reps, n_demes).mean(axis=2)

        deltas = np.diff(freqs, axis=0)  # shape (gens-1, reps)
        p_mean = freqs[:-1].mean(axis=1)  # mean p at start of each interval
        pq_mean = (p_mean * (1.0 - p_mean))
        var_delta = deltas.var(axis=1, ddof=1)  # per-interval variance

        usable = (var_delta > 0.0) & (pq_mean > 0.0)
        if not np.any(usable):
            return {"error": "no usable generation intervals "
                             "(zero variance in frequency change)"}
        per_gen_ne = np.where(usable, pq_mean / (2.0 * var_delta), np.nan)
        ne_estimate = float(np.nanmean(per_gen_ne))
        return {
            "ne_estimate": ne_estimate,
            "per_generation_ne": [float(x) for x in per_gen_ne],
            "n_generations_used": int(np.sum(usable)),
            "n_replicates": int(freqs.shape[1]),
            "note": ("variance-method estimate (Nei & Tajima 1981); "
                     "biased upward as drift accumulates — prefer "
                     "estimate_ne() for quantitative work"),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of the whole result."""
        return {
            "colnames": self.colnames,
            "data": self.data,
            "model_name": self.model_name,
            "flagged": self.validation.flagged,
            "flag_reason": self.validation.flag_reason,
            "replicate_colnames": self.replicate_colnames,
            "replicate_data": self.replicate_data,
            "wright_fisher_params": self.wright_fisher_params,
        }

    def to_csv(self, path: str,
               include_replicate_data: bool = False) -> str:
        """Write the result to a CSV file.

        Args:
            path: output file path
            include_replicate_data: if True and replicate data exists,
                also write it to ``<stem>_replicates.csv``
        Returns:
            the path written
        """
        import csv
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(self.colnames)
            writer.writerows(self.data)
        if include_replicate_data and self.replicate_data is not None:
            from pathlib import Path
            p = Path(path)
            rep_path = p.with_name(p.stem + "_replicates" + p.suffix)
            with open(rep_path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(self.replicate_colnames or [])
                writer.writerows(self.replicate_data)
        return path

    def to_json(self, path: str | None = None,
                include_replicate_data: bool = True) -> str:
        """Return (and optionally write) a JSON serialization.

        Args:
            path: optional output file path; if None, only return the string
            include_replicate_data: if False, omit replicate data from
                the output to keep the file small
        Returns:
            the JSON string
        """
        import json
        doc = self.to_dict()
        if not include_replicate_data:
            doc["replicate_data"] = None
        text = json.dumps(doc)
        if path is not None:
            with open(path, "w") as fh:
                fh.write(text)
        return text


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
    if isinstance(value, (bool, np.bool_)):
        errors.append(f"{label} must be a number, not a boolean")
        return False
    
    if not isinstance(value, (int, float, np.integer, np.floating)):
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

    _finite_positive(km, "Km", errors, allow_zero=False)
    _finite_positive(vmax, "Vmax", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)

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

    _finite_positive(beta, "beta", errors, allow_zero=False)
    _finite_positive(gamma, "gamma", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)
    _finite_positive(i0, "I0", errors, allow_zero=True)
    _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True)

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

    _finite_positive(beta, "beta", errors, allow_zero=False)
    _finite_positive(sigma, "sigma", errors, allow_zero=False)
    _finite_positive(gamma, "gamma", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)
    _finite_positive(i0, "I0", errors, allow_zero=True)
    _finite_positive(e0, "E0", errors, allow_zero=True)
    _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True)

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

    _finite_positive(n0, "n0", errors, allow_zero=False)

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

    if isinstance(cycles, (bool, np.bool_)) or not isinstance(cycles, (int, np.integer)):
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
# RNG convention: see ADR 0005 (docs/adr/0005-rng-convention.md) for the
# formal decision. All discrete/stochastic domains use
# numpy.random.default_rng(seed) with seed: int | None = None.
# This comment was the original judgment call that ADR 0005 superseded.
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

    if isinstance(n_samples, (bool, np.bool_)):
        errors.append("n_samples must be an integer, not a boolean")
    elif not isinstance(n_samples, (int, np.integer)):
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


# ---------------------------------------------------------------------------
# Wright-Fisher population genetics (neutral drift)
#
# Like PCR and Monte Carlo, this is a discrete/stochastic domain, not an ODE.
# Wright-Fisher is fundamentally a discrete-generation model — there is no
# meaningful continuous-time state between generation t and t+1 to integrate
# through. Direct Python + numpy binomial sampling, per ADR 0002 and 0005.
#
# ADR 0005 applies: the RNG is numpy.random.default_rng(seed), with
# seed: int | None = None. A fixed seed guarantees bit-identical output
# within a fixed numpy installation (the default BitGenerator may differ
# across numpy major versions — PCG64 under 1.x, Philox under 2.x).
# ---------------------------------------------------------------------------

# Population size < 10 gives drift so rapid it is unlikely to be the
# intended teaching-lab scenario, but the simulation is valid and will run.
WF_PLAUSIBLE_MIN_POPULATION_SIZE = 10

# More than 10,000 generations is valid but may be slow; flagged rather
# than rejected so a student exploring long-term drift is not blocked.
WF_PLAUSIBLE_MAX_GENERATIONS = 10_000

# Fewer than 10 replicate runs makes the standard error on mean
# heterozygosity too large for a meaningful estimate; flagged, not rejected.
WF_PLAUSIBLE_MIN_REPLICATE_RUNS = 10

# More than 0.01 per-generation mutation rate is biologically implausible
# for most teaching scenarios, but the simulation is valid and will run.
WF_PLAUSIBLE_MAX_MUTATION_RATE = 0.01

# Selection coefficient above 0.5 (or below -0.5) is strong enough to
# dominate drift in most teaching-lab scenarios; flagged, not rejected.
WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT = 0.5


# ---------------------------------------------------------------------------
# Molecular dynamics (Lennard-Jones cluster, velocity Verlet)
#
# This is a continuous-time domain that deliberately bypasses antimony/
# roadrunner — see ADR 0006. MD correctness depends on energy conservation
# from a symplectic, fixed-step integrator, not on the local-error control
# an adaptive general solver (roadrunner) provides. Direct Python + numpy
# with velocity Verlet, per ADR 0005 (RNG) and ADR 0006 (engine choice).
# ---------------------------------------------------------------------------

# Fewer than 10 particles makes "cluster" and the density/temperature
# framing ambiguous — valid but likely not the intended teaching scenario.
MD_PLAUSIBLE_MIN_PARTICLES = 10

# Timestep above 0.01 (reduced units) risks energy-conservation failure
# or numerical explosion from under-resolved r^{-12} repulsive wall.
MD_PLAUSIBLE_MAX_TIMESTEP = 0.01

# Temperature below 0.1: cluster is effectively frozen (numerically valid,
# scientifically inert — the student sees no interesting dynamics).
MD_PLAUSIBLE_TEMPERATURE_LOW = 0.1

# Temperature above 0.8: cluster loses particles within the run — the
# highest measured initialization temperature keeping the LJ108 cluster
# fully intact (0 escaped, Rg growth < 1x). Above this the flag warns
# of evaporation.
MD_PLAUSIBLE_TEMPERATURE_HIGH = 0.8


def validate_wright_fisher_params(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
    population_size_series: Optional[Sequence[int]] = None,
    n_demes: int = 1,
    migration_rate: float = 0.0,
    migration_model: str = "island",
) -> ParameterValidation:
    """Check a Wright-Fisher neutral-drift parameter set.

    Hard rejections (``ok=False``):
        * ``population_size`` is boolean, not an integer, or < 1
        * ``starting_frequency`` is boolean, not a finite float, or outside [0, 1]
        * ``generations`` is boolean, not an integer, or < 1
        * ``replicate_runs`` is boolean, not an integer, or < 1
        * ``mutation_rate`` is boolean, NaN, infinite, < 0, or > 1
        * ``selection_coefficient`` is boolean, NaN, infinite, or <= -1
        * ``dominance`` is not None and not in [0, 2]
        * ``population_size_series`` elements are not positive integers, or
          its length does not match ``generations + 1``
        * ``n_demes`` is boolean, not an integer, or < 1
        * ``migration_rate`` is boolean, NaN, infinite, or outside [0, 1]
        * ``migration_model`` is not "island" or "stepping-stone"
        * ``migration_model="stepping-stone"`` with ``n_demes < 3``
          (a ring of fewer than 3 demes is degenerate)

    Flags (``ok=True, flagged=True``):
        * ``population_size < WF_PLAUSIBLE_MIN_POPULATION_SIZE`` — drift
          extremely rapid, valid but unlikely to be intended
        * ``starting_frequency`` exactly 0.0 or 1.0 — allele already
          lost or fixed, valid but degenerate
        * ``generations > WF_PLAUSIBLE_MAX_GENERATIONS`` — valid, may be slow
        * ``replicate_runs < WF_PLAUSIBLE_MIN_REPLICATE_RUNS`` — standard
          error of mean heterozygosity will be large
        * ``mutation_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE`` — biologically
          implausible, mutation will dominate drift
        * ``|selection_coefficient| > WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT``
          — implausibly strong selection for most teaching scenarios
        * Any value in ``population_size_series`` below
          ``WF_PLAUSIBLE_MIN_POPULATION_SIZE`` — flagged (same as constant N)
        * ``migration_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE`` — flagged
          (strong migration homogenises demes rapidly)
        * ``dominance > 1`` — overdominance (h > 1 with s > 0) or
          underdominance (h > 1 with s < 0); valid, but the heterozygote
          fitness is no longer intermediate between the homozygotes
    """
    errors: List[str] = []

    # --- population_size ---
    if isinstance(population_size, (bool, np.bool_)):
        errors.append("population_size must be an integer, not a boolean")
    elif not isinstance(population_size, (int, np.integer)):
        errors.append(
            f"population_size must be an integer, got "
            f"{type(population_size).__name__}")
    elif population_size < 1:
        errors.append(
            f"population_size must be >= 1 (got {population_size})")

    # --- starting_frequency ---
    if isinstance(starting_frequency, (bool, np.bool_)):
        errors.append("starting_frequency must be a number, not a boolean")
    elif not isinstance(starting_frequency, (int, float)):
        errors.append(
            f"starting_frequency must be a number, got "
            f"{type(starting_frequency).__name__}")
    elif math.isnan(starting_frequency):
        errors.append("starting_frequency must not be NaN")
    elif math.isinf(starting_frequency):
        errors.append("starting_frequency must be finite")
    elif not (0.0 <= starting_frequency <= 1.0):
        errors.append(
            f"starting_frequency must be in [0, 1] (got {starting_frequency})")

    # --- generations ---
    if isinstance(generations, (bool, np.bool_)):
        errors.append("generations must be an integer, not a boolean")
    elif not isinstance(generations, (int, np.integer)):
        errors.append(
            f"generations must be an integer, got "
            f"{type(generations).__name__}")
    elif generations < 1:
        errors.append(f"generations must be >= 1 (got {generations})")

    # --- replicate_runs ---
    if isinstance(replicate_runs, (bool, np.bool_)):
        errors.append("replicate_runs must be an integer, not a boolean")
    elif not isinstance(replicate_runs, (int, np.integer)):
        errors.append(
            f"replicate_runs must be an integer, got "
            f"{type(replicate_runs).__name__}")
    elif replicate_runs < 1:
        errors.append(
            f"replicate_runs must be >= 1 (got {replicate_runs})")

    # --- mutation_rate ---
    if isinstance(mutation_rate, (bool, np.bool_)):
        errors.append("mutation_rate must be a number, not a boolean")
    elif not isinstance(mutation_rate, (int, float, np.integer, np.floating)):
        errors.append(
            f"mutation_rate must be a number, got "
            f"{type(mutation_rate).__name__}")
    elif math.isnan(mutation_rate):
        errors.append("mutation_rate must not be NaN")
    elif math.isinf(mutation_rate):
        errors.append("mutation_rate must be finite")
    elif mutation_rate < 0.0:
        errors.append(
            f"mutation_rate must be >= 0 (got {mutation_rate})")
    elif mutation_rate > 1.0:
        errors.append(
            f"mutation_rate must be <= 1 (got {mutation_rate})")

    # --- selection_coefficient ---
    if isinstance(selection_coefficient, (bool, np.bool_)):
        errors.append("selection_coefficient must be a number, not a boolean")
    elif not isinstance(selection_coefficient, (int, float, np.integer, np.floating)):
        errors.append(
            f"selection_coefficient must be a number, got "
            f"{type(selection_coefficient).__name__}")
    elif math.isnan(selection_coefficient):
        errors.append("selection_coefficient must not be NaN")
    elif math.isinf(selection_coefficient):
        errors.append("selection_coefficient must be finite")
    elif selection_coefficient <= -1.0:
        errors.append(
            f"selection_coefficient must be > -1 (got "
            f"{selection_coefficient})")

    # --- dominance ---
    if dominance is not None:
        if isinstance(dominance, (bool, np.bool_)):
            errors.append("dominance must be a number, not a boolean")
        elif not isinstance(dominance, (int, float, np.integer, np.floating)):
            errors.append(
                f"dominance must be a number, got "
                f"{type(dominance).__name__}")
        elif math.isnan(dominance):
            errors.append("dominance must not be NaN")
        elif math.isinf(dominance):
            errors.append("dominance must be finite")
        elif not (0.0 <= dominance <= 2.0):
            errors.append(
                f"dominance must be in [0, 2] (got {dominance})")

    # --- n_demes ---
    if isinstance(n_demes, (bool, np.bool_)):
        errors.append("n_demes must be an integer, not a boolean")
    elif not isinstance(n_demes, (int, np.integer)):
        errors.append(
            f"n_demes must be an integer, got {type(n_demes).__name__}")
    elif n_demes < 1:
        errors.append(f"n_demes must be >= 1 (got {n_demes})")

    # --- migration_rate ---
    if isinstance(migration_rate, (bool, np.bool_)):
        errors.append("migration_rate must be a number, not a boolean")
    elif not isinstance(migration_rate, (int, float, np.integer, np.floating)):
        errors.append(
            f"migration_rate must be a number, got "
            f"{type(migration_rate).__name__}")
    elif math.isnan(migration_rate):
        errors.append("migration_rate must not be NaN")
    elif math.isinf(migration_rate):
        errors.append("migration_rate must be finite")
    elif migration_rate < 0.0 or migration_rate > 1.0:
        errors.append(
            f"migration_rate must be in [0, 1] (got {migration_rate})")

    # --- migration_model ---
    if not isinstance(migration_model, str):
        errors.append(
            f"migration_model must be a string, got "
            f"{type(migration_model).__name__}")
    elif migration_model not in ("island", "stepping-stone"):
        errors.append(
            f"migration_model must be 'island' or 'stepping-stone' "
            f"(got {migration_model!r})")
    elif migration_model == "stepping-stone" and (
            isinstance(n_demes, (int, float, np.integer, np.floating))
            and n_demes < 3):
        errors.append(
            "migration_model='stepping-stone' requires n_demes >= 3 "
            "(a ring of fewer than 3 demes is degenerate)")

    # --- population_size_series ---
    if population_size_series is not None:
        if not isinstance(population_size_series, (list, tuple, np.ndarray)):
            errors.append(
                f"population_size_series must be a list or tuple, got "
                f"{type(population_size_series).__name__}")
        else:
            series_list = list(population_size_series)
            if len(series_list) != generations + 1:
                errors.append(
                    f"population_size_series length ({len(series_list)}) "
                    f"must equal generations+1 ({generations + 1})")
            for i, val in enumerate(series_list):
                if isinstance(val, (bool, np.bool_)):
                    errors.append(
                        f"population_size_series[{i}] must be an integer, "
                        f"not a boolean")
                elif not isinstance(val, (int, np.integer)):
                    errors.append(
                        f"population_size_series[{i}] must be an integer, "
                        f"got {type(val).__name__}")
                elif val < 1:
                    errors.append(
                        f"population_size_series[{i}] must be >= 1 "
                        f"(got {val})")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()
    flag_reasons: List[str] = []

    if population_size_series is None:
        if population_size < WF_PLAUSIBLE_MIN_POPULATION_SIZE:
            v.flagged = True
            flag_reasons.append(
                f"population_size={population_size} is below "
                f"{WF_PLAUSIBLE_MIN_POPULATION_SIZE}; drift will be "
                "extremely rapid")
    else:
        min_n = min(population_size_series)
        if min_n < WF_PLAUSIBLE_MIN_POPULATION_SIZE:
            v.flagged = True
            flag_reasons.append(
                f"population_size_series minimum ({min_n}) is below "
                f"{WF_PLAUSIBLE_MIN_POPULATION_SIZE}; some generations "
                "will have extremely rapid drift")
    if starting_frequency == 0.0:
        v.flagged = True
        flag_reasons.append(
            "starting_frequency is 0.0; the allele is already lost "
            "and no drift can occur")
    if starting_frequency == 1.0:
        v.flagged = True
        flag_reasons.append(
            "starting_frequency is 1.0; the allele is already fixed "
            "and no drift can occur")
    if generations > WF_PLAUSIBLE_MAX_GENERATIONS:
        v.flagged = True
        flag_reasons.append(
            f"generations={generations} exceeds "
            f"{WF_PLAUSIBLE_MAX_GENERATIONS}; simulation may be "
            "noticeably slow")
    if replicate_runs < WF_PLAUSIBLE_MIN_REPLICATE_RUNS:
        v.flagged = True
        flag_reasons.append(
            f"replicate_runs={replicate_runs} is below "
            f"{WF_PLAUSIBLE_MIN_REPLICATE_RUNS}; the standard error "
            "of mean heterozygosity will be large")
    if mutation_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE:
        v.flagged = True
        flag_reasons.append(
            f"mutation_rate={mutation_rate} exceeds "
            f"{WF_PLAUSIBLE_MAX_MUTATION_RATE}; mutation will "
            "dominate drift")
    if abs(selection_coefficient) > WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT:
        v.flagged = True
        flag_reasons.append(
            f"|selection_coefficient|={abs(selection_coefficient)} "
            f"exceeds {WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT}; "
            "selection will dominate drift")
    if dominance is not None and dominance > 1.0:
        v.flagged = True
        flag_reasons.append(
            f"dominance={dominance} exceeds 1; heterozygote fitness is "
            "not intermediate between the homozygotes "
            "(overdominance if s > 0, underdominance if s < 0)")
    if migration_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE:
        v.flagged = True
        flag_reasons.append(
            f"migration_rate={migration_rate} exceeds "
            f"{WF_PLAUSIBLE_MAX_MUTATION_RATE}; migration will "
            "homogenise demes rapidly")

    if flag_reasons:
        v.flag_reason = "; ".join(flag_reasons)
    return v


_WF_FST_ROUNDOFF_TOLERANCE = 1e-10


def _clamp_wf_fst_roundoff(values: np.ndarray) -> np.ndarray:
    """Remove only float roundoff outside Fst's mathematical [0, 1] range."""
    values = np.asarray(values, dtype=np.float64)
    values = np.where(
        (values < 0.0) & (values >= -_WF_FST_ROUNDOFF_TOLERANCE),
        0.0,
        values,
    )
    return np.where(
        (values > 1.0) &
        (values <= 1.0 + _WF_FST_ROUNDOFF_TOLERANCE),
        1.0,
        values,
    )


def simulate_wright_fisher(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
    seed: int | None = None,
    return_replicate_data: bool = False,
    population_size_series: Optional[Sequence[int]] = None,
    n_demes: int = 1,
    migration_rate: float = 0.0,
    migration_model: str = "island",
    verbose: bool = False,
) -> SimulationResult:
    """Simulate genetic drift in a diploid Wright-Fisher population, with
    optional symmetric mutation, natural selection, and migration.

    Each generation follows these steps in order:
        1. Selection — fitness differences change the expected frequency.
        2. Reproduction — the next generation's 2N allele copies are drawn
           ``Binomial(2N, p_adj)`` from the post-selection frequency.
        3. Mutation — each copy mutates to the other allele with
           probability ``mutation_rate``.
        4. Migration (when ``n_demes > 1``) — allele exchange between
           demes. ``migration_model="island"`` (default) exchanges a
           fraction ``migration_rate`` of each deme's alleles with the
           global pool (Wright's island model);
           ``migration_model="stepping-stone"`` arranges the demes on a
           ring and exchanges each deme with its two neighbours only.

    When ``selection_coefficient=0`` and ``dominance=None`` (the defaults),
    selection is skipped and the model reduces to neutral drift.
    When ``dominance=None``, a haploid selection model is used
    (``p' = p(1+s) / (1+ps)``). When ``dominance`` is given in [0, 1],
    a diploid selection model with dominance h is used.

    Set ``return_replicate_data=True`` to include per-replicate allele
    frequencies in ``result.replicate_data`` (columns: generation,
    rep_0, rep_1, ..., rep_{replicate_runs-1}). Off by default because
    storage scales as O(generations x replicate_runs).

    Use ``population_size_series`` to model time-varying N (bottlenecks,
    founder events, expansion). When given, it must be a sequence of
    length ``generations + 1``, and each element is the census size N
    for that generation. The constant ``population_size`` is used as a
    fallback when this is ``None``.

    Use ``n_demes`` and ``migration_rate`` to model population structure
    via Wright's island model. Each replicate metapopulation contains
    ``n_demes`` demes of equal size. When ``migration_rate > 0``, a
    fraction of each deme's allele pool is replaced by migrants drawn
    from the global pool each generation. When ``n_demes = 1`` (default)
    the model reduces to the standard panmictic WF population.

    Use ``migration_model="stepping-stone"`` to arrange the demes on a
    ring instead: each deme exchanges a fraction ``migration_rate/2``
    of its allele pool with each of its two immediate neighbours,
    so allele flow is local rather than global. Requires
    ``n_demes >= 3``.

    Set ``verbose=True`` to print progress per 10 % of generations
    (useful for long simulations with thousands of generations).

    Returns a ``SimulationResult`` with columns ``["generation",
    "mean_frequency", "heterozygosity", "mean_frequency_se",
    "heterozygosity_se", "n_A_fixed", "n_a_fixed"]``, plus ``"fst"``
    and ``"fst_se"`` when ``n_demes > 1``. One row per generation
    (from 0 to ``generations`` inclusive), aggregated across all
    replicate populations. Standard errors are computed as
    ``std(x, ddof=1) / sqrt(replicate_runs)``.

    Args:
        population_size: number of diploid individuals per deme; 2N
            allele copies per deme
        starting_frequency: initial frequency of allele A, in [0, 1]
        generations: number of generations to simulate forward
        replicate_runs: number of independent replicate metapopulations
        mutation_rate: per-generation probability of mutation per allele
            copy (symmetric, forward and backward); 0 = neutral drift
        selection_coefficient: selective advantage of allele A (s);
            positive = beneficial, negative = deleterious; must be > -1
        dominance: dominance coefficient (h) for diploid selection;
            None = haploid selection; in [0, 2] for diploid
            (h > 1 = overdominance when s > 0, underdominance when s < 0)
        seed: optional seed for reproducibility; passed to
            ``numpy.random.default_rng``
        return_replicate_data: if True, store per-replicate frequencies
        population_size_series: time-varying N per generation
        n_demes: number of demes per replicate (1 = panmictic)
        migration_rate: fraction of alleles exchanged per generation,
            in [0, 1]
        migration_model: "island" (global pool) or "stepping-stone"
            (ring of neighbours); requires n_demes >= 3 for
            "stepping-stone"
        verbose: if True, print progress every 10 % of generations

    Returns:
        SimulationResult with aggregated per-generation statistics

    Raises:
        ModelBuildError: if parameters are invalid
    """
    validation = validate_wright_fisher_params(
        population_size, starting_frequency, generations, replicate_runs,
        mutation_rate, selection_coefficient, dominance,
        population_size_series, n_demes, migration_rate, migration_model)
    validation.raise_if_invalid()

    rng = np.random.default_rng(seed)

    if population_size_series is not None:
        n_series = [int(v) for v in population_size_series]
    else:
        n_series = None

    structured = n_demes > 1
    if structured:
        frequencies = np.full(
            (replicate_runs, n_demes), starting_frequency, dtype=np.float64)
    else:
        frequencies = np.full(  # type: ignore[assignment]
            replicate_runs, starting_frequency, dtype=np.float64)

    n_cols = 9 if structured else 7
    data_arr = np.empty((generations + 1, n_cols), dtype=np.float64)
    row_template = np.empty(n_cols, dtype=np.float64)

    replicate_data: Optional[np.ndarray] = None
    if return_replicate_data:
        flat_width = replicate_runs * (n_demes if structured else 1)
        rep_arr = np.empty((generations + 1, 1 + flat_width),
                           dtype=np.float64)

    sqrt_reps = np.sqrt(replicate_runs)

    fixation_gen_A = np.full(replicate_runs, -1, dtype=np.int64)
    fixation_gen_a = np.full(replicate_runs, -1, dtype=np.int64)

    if verbose and generations > 0:
        report_interval = max(1, generations // 10)

    for gen in range(generations + 1):
        mean_freq = float(np.mean(frequencies))
        het_values = 2.0 * frequencies * (1.0 - frequencies)
        heterozygosity = float(np.mean(het_values))

        if structured:
            rep_mean = np.mean(frequencies, axis=1)
            n_A_fixed = float(np.sum(rep_mean == 1.0))
            n_a_fixed = float(np.sum(rep_mean == 0.0))
            Hs = np.mean(het_values, axis=1)
            Ht = 2.0 * rep_mean * (1.0 - rep_mean)
            # np.where still evaluates Hs / Ht element-wise for every entry
            # (including where Ht == 0, e.g. a deme already fixed) before
            # selecting -- the result is correct (0.0 substituted where
            # Ht <= 0), but numpy raises a RuntimeWarning for the transient
            # 0/0 anyway. Suppress it explicitly rather than let a bogus
            # warning appear in otherwise-clean test output, where it could
            # mask a real one later.
            with np.errstate(divide="ignore", invalid="ignore"):
                fst_rep = np.where(Ht > 0, 1.0 - Hs / Ht, 0.0)
            # Nei's Fst is bounded by [0, 1] here. At the boundary,
            # subtraction can leave a tiny float64 residue; remove only
            # that roundoff-sized residue and preserve material violations.
            fst_rep = _clamp_wf_fst_roundoff(fst_rep)
            fst = float(np.mean(fst_rep))
            rep_val = rep_mean
        else:
            n_A_fixed = float(np.sum(frequencies == 1.0))
            n_a_fixed = float(np.sum(frequencies == 0.0))
            fst = 0.0
            fst_rep = None
            rep_val = frequencies

        not_yet = (fixation_gen_A == -1) & (fixation_gen_a == -1)
        fixation_gen_A[not_yet & (rep_val == 1.0)] = gen
        fixation_gen_a[not_yet & (rep_val == 0.0)] = gen

        if replicate_runs > 1:
            if structured:
                se_freq = float(
                    np.std(rep_mean, ddof=1) / sqrt_reps)
                rep_het = np.mean(het_values, axis=1)
                se_het = float(
                    np.std(rep_het, ddof=1) / sqrt_reps)
                fst_se = float(
                    np.std(fst_rep, ddof=1) / sqrt_reps)
            else:
                se_freq = float(
                    np.std(frequencies, ddof=1) / sqrt_reps)
                se_het = float(
                    np.std(het_values, ddof=1) / sqrt_reps)
                fst_se = 0.0
        else:
            se_freq = 0.0
            se_het = 0.0
            fst_se = 0.0

        row_template[0] = float(gen)
        row_template[1] = mean_freq
        row_template[2] = heterozygosity
        row_template[3] = se_freq
        row_template[4] = se_het
        row_template[5] = n_A_fixed
        row_template[6] = n_a_fixed
        if structured:
            row_template[7] = fst
            row_template[8] = fst_se
        data_arr[gen] = row_template

        if return_replicate_data:
            freqs_flat = frequencies.flatten() if structured else frequencies
            rep_arr[gen, 0] = float(gen)
            rep_arr[gen, 1:] = freqs_flat

        if gen < generations:
            two_n_gen = 2 * (n_series[gen] if n_series is not None
                             else population_size)

            if selection_coefficient != 0.0:
                s = selection_coefficient
                if dominance is None:
                    p_adj = frequencies * (1.0 + s) / (
                        1.0 + frequencies * s)
                else:
                    h = dominance
                    p = frequencies
                    p2 = p * p
                    pq = p * (1.0 - p)
                    q2 = (1.0 - p) * (1.0 - p)
                    w_bar = (p2 * (1.0 + s) + 2.0 * pq * (
                        1.0 + h * s) + q2)
                    p_adj = (p2 * (1.0 + s) + pq * (
                        1.0 + h * s)) / w_bar
            else:
                p_adj = frequencies

            counts = rng.binomial(two_n_gen, p_adj)

            if mutation_rate > 0.0:
                n_a_copies = two_n_gen - counts
                mut_A_to_a = rng.binomial(counts, mutation_rate)
                mut_a_to_A = rng.binomial(n_a_copies, mutation_rate)
                counts = counts - mut_A_to_a + mut_a_to_A

            frequencies = counts.astype(np.float64) / two_n_gen

            # Step 4: Migration — island model (global pool) or
            # stepping-stone (ring of neighbours), vectorized across
            # replicates
            if structured and migration_rate > 0.0:
                m = migration_rate
                if migration_model == "island":
                    p_global = np.mean(frequencies, axis=1, keepdims=True)
                    frequencies = (1.0 - m) * frequencies + m * p_global
                else:
                    p_left = np.roll(frequencies, 1, axis=1)
                    p_right = np.roll(frequencies, -1, axis=1)
                    frequencies = (
                        (1.0 - m) * frequencies
                        + (m / 2.0) * p_left
                        + (m / 2.0) * p_right)

        if verbose and generations > 0 and (
                gen % report_interval == 0 or gen == generations):
            pct = gen * 100 // generations
            print(f"  Wright-Fisher: {pct}% complete "
                  f"(generation {gen}/{generations})")

    data = data_arr.tolist()
    if return_replicate_data:
        replicate_data = rep_arr.tolist()  # type: ignore[assignment]

    base_colnames = ["generation", "mean_frequency", "heterozygosity",
                     "mean_frequency_se", "heterozygosity_se",
                     "n_A_fixed", "n_a_fixed"]
    if structured:
        colnames = [*base_colnames, "fst", "fst_se"]
    else:
        colnames = base_colnames

    if return_replicate_data and replicate_data is not None:
        if structured:
            replicate_colnames = (
                ["generation"] +
                [f"rep_{i}_deme_{d}"
                 for i in range(replicate_runs)
                 for d in range(n_demes)])
        else:
            replicate_colnames = (
                ["generation"] +
                [f"rep_{i}" for i in range(replicate_runs)])
    else:
        replicate_colnames = None

    wf_params: Dict[str, Any] = {
        "population_size": population_size,
        "starting_frequency": starting_frequency,
        "generations": generations,
        "replicate_runs": replicate_runs,
        "mutation_rate": mutation_rate,
        "selection_coefficient": selection_coefficient,
        "dominance": dominance,
        "population_size_series": population_size_series,
        "n_demes": n_demes,
        "migration_rate": migration_rate,
        "migration_model": migration_model,
        "fixation_gen_A": fixation_gen_A.tolist(),
        "fixation_gen_a": fixation_gen_a.tolist(),
        "final_frequencies": frequencies.flatten().tolist(),
    }

    return SimulationResult(
        colnames=colnames,
        data=data,
        model_name="wright_fisher",
        validation=validation,
        replicate_data=replicate_data,  # type: ignore[arg-type]
        replicate_colnames=replicate_colnames,
        wright_fisher_params=wf_params,
    )


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


# ---------------------------------------------------------------------------
# Kimura fixation probability (selection-drift balance)
# ---------------------------------------------------------------------------


def kimura_fixation_probability(
    starting_frequency: float,
    selection_coefficient: float,
    population_size: int,
    dominance: float | None = None,
) -> float:
    """Kimura's (1962) probability that allele A fixes under selection
    and drift in a diploid Wright-Fisher population of size ``N``.

    With ``dominance=None`` (haploid selection over the 2N allele
    copies) the closed form is::

        P_fix = (1 - exp(-4Ns p0)) / (1 - exp(-4Ns))

    With ``dominance=h`` (diploid fitnesses AA: 1+s, Aa: 1+hs, aa: 1),
    the diffusion approximation is evaluated numerically::

        P_fix(p0) = ∫₀^p0 G(x) dx / ∫₀^1 G(x) dx
        G(x) = exp(-4Ns (h x + (1-2h) x² / 2))

    For ``s=0`` the neutral result ``P_fix = p0`` is returned, and for
    very strong positive selection the probability saturates at 1.0.

    NOTE: for ``dominance > 1`` (overdominance/underdominance) the
    diffusion approximation is unreliable (observed error up to ~0.25
    versus simulation); use ``SimulationResult.fixation_analysis()``
    instead for those regimes.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        selection_coefficient: selective advantage of A (s); > -1
        population_size: diploid census size N
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the fixation probability of allele A in [0, 1]

    Raises:
        ValueError: on invalid parameters
    """
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError(
            "starting_frequency must be in [0, 1]")
    if selection_coefficient <= -1.0:
        raise ValueError("selection_coefficient must be > -1")
    if dominance is not None and not 0.0 <= dominance <= 2.0:
        raise ValueError("dominance must be in [0, 2] or None")

    if starting_frequency == 0.0:
        return 0.0
    if starting_frequency == 1.0:
        return 1.0
    if selection_coefficient == 0.0:
        return float(starting_frequency)

    s = selection_coefficient
    N = int(population_size)

    if dominance is None:
        # Closed form for haploid selection over 2N copies
        if s > 0.0 and 4.0 * N * s > 700.0:
            return 1.0
        if s < 0.0 and -4.0 * N * s > 700.0:
            return 0.0
        e1 = math.exp(-4.0 * N * s * starting_frequency)
        e2 = math.exp(-4.0 * N * s)
        return (1.0 - e1) / (1.0 - e2)

    # Diploid with dominance: numerical diffusion integral
    h = dominance
    alpha = 4.0 * N * s
    if alpha * (h + (1.0 - 2.0 * h) * 0.5) > 700.0:
        # exp(-alpha * I(x)) underflows to 0 everywhere -> fixation certain
        return 1.0

    def integrand(x: float) -> float:
        return math.exp(-alpha * (h * x + (1.0 - 2.0 * h) * x * x / 2.0))

    # scipy is a declared runtime dependency; import lazily to keep
    # module import fast for the other models
    from scipy.integrate import quad
    num, _ = quad(integrand, 0.0, starting_frequency)
    den, _ = quad(integrand, 0.0, 1.0)
    if den == 0.0:
        return 1.0
    return float(num / den)


def expected_fixation_time(
    starting_frequency: float,
    population_size: int,
) -> float:
    """Kimura & Ohta's (1969) expected time to fixation of a neutral
    allele, given that it fixes.

    For a diploid population of size N and an allele at initial
    frequency p0::

        t_bar = -4N * (1 - p0) * ln(1 - p0) / p0

    generations. The formula is exact for the diffusion approximation of
    a neutral allele; it requires ``starting_frequency > 0`` (an allele
    at frequency 0 never fixes) and is 0 at ``starting_frequency = 1``
    (already fixed).

    Examples: N=100, p0=0.5 -> t_bar = 4*100*ln(2) ~= 277 generations;
    N=50, p0=0.2 -> t_bar ~= 178 generations.

    Args:
        starting_frequency: initial frequency of allele A, in (0, 1]
        population_size: diploid census size N

    Returns:
        expected generations until fixation, conditioned on fixation

    Raises:
        ValueError: if population_size <= 0, starting_frequency outside
            (0, 1], or NaN/infinite values
    """
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if isinstance(starting_frequency, (bool, np.bool_)):
        raise ValueError("starting_frequency must be a number, not a boolean")
    if not isinstance(starting_frequency,
                      (int, float, np.integer, np.floating)):
        raise ValueError(
            f"starting_frequency must be a number, got "
            f"{type(starting_frequency).__name__}")
    if math.isnan(starting_frequency) or math.isinf(starting_frequency):
        raise ValueError("starting_frequency must be finite")
    if not 0.0 < starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in (0, 1]")

    if starting_frequency == 1.0:
        return 0.0
    n = float(population_size)
    p0 = float(starting_frequency)
    return -4.0 * n * (1.0 - p0) * math.log(1.0 - p0) / p0


# ---------------------------------------------------------------------------
# Effective population size from an observed heterozygosity trajectory
# ---------------------------------------------------------------------------


def estimate_ne_from_heterozygosity(
    heterozygosity: Sequence[float],
) -> Dict[str, Any]:
    """Estimate the effective population size from the rate of
    heterozygosity decay.

    Under neutral drift the expected heterozygosity decays as
    ``H_t = H_0 * (1 - 1/(2N))^t``, so a linear regression of
    ``ln(H_t)`` on ``t`` gives ``slope = ln(1 - 1/(2N))`` and
    ``Ne_hat = 1 / (2 * (1 - exp(slope)))``.

    ``heterozygosity`` is the observed mean heterozygosity at each
    generation (the ``heterozygosity`` column of a simulation result, or
    of an exported CSV). Requires at least 3 non-zero values; zero or
    negative values are dropped (a population in which every replicate
    has fixed contributes no decay information).

    Returns a dict with ``method`` ("heterozygosity_decay"),
    ``ne_estimate``, ``decay_rate_per_generation``,
    ``n_generations_used``, and a note that selection, mutation, and
    migration bias the estimate. Returns ``{"error": ...}`` when fewer
    than 3 usable values are available.
    """
    H = np.asarray(heterozygosity, dtype=np.float64)
    if H.ndim != 1 or H.size == 0:
        return {"error": "heterozygosity must be a non-empty 1-D sequence"}
    valid = H > 1e-12
    if np.sum(valid) < 3:
        return {
            "error": "at least 3 non-zero heterozygosity values "
                     "are required"}
    t = np.arange(H.size)[valid]
    slope, _ = np.polyfit(t, np.log(H[valid]), 1)
    decay = math.exp(slope)
    ne = 1.0 / (2.0 * (1.0 - decay))
    return {
        "method": "heterozygosity_decay",
        "ne_estimate": float(ne),
        "decay_rate_per_generation": float(decay),
        "n_generations_used": int(np.sum(valid)),
        "note": ("inbreeding-effective size from heterozygosity "
                 "decay; biased by selection, mutation, and "
                 "migration"),
    }


def effective_size_harmonic_mean(
    population_size_series: Sequence[int],
) -> float:
    """Effective population size of a time-varying-N population: the
    harmonic mean of the census sizes.

    Drift accumulates ``1/(2N_t)`` of heterozygosity per generation,
    so after a sequence of sizes ``N_1..N_k`` the decay is
    ``H_k = H_0 * prod(1 - 1/(2N_t)) ~ H_0 * exp(-k / (2*Ne))`` with::

        Ne = k / sum(1/N_t)

    -- the harmonic mean of the census sizes. This is the classic
    bottleneck result: a single generation of severe reduction
    (e.g. [100, 10, 100]) dominates the average (Ne = 25 for those
    three generations, far below the arithmetic mean of 70), because
    drift during the bottleneck permanently removes genetic
    diversity.

    The harmonic mean is always <= the arithmetic mean (equality only
    for a constant series).

    Args:
        population_size_series: per-generation diploid census sizes
            N_t (same series accepted by ``simulate_wright_fisher``)

    Returns:
        the effective population size Ne (harmonic mean)

    Raises:
        ValueError: on an empty series or any N_t < 1 (or a non-int
            entry)
    """
    if isinstance(population_size_series, (str, bytes)) or not isinstance(
            population_size_series, (list, tuple, np.ndarray)):
        raise ValueError("population_size_series must be a sequence")
    if len(population_size_series) == 0:
        raise ValueError("population_size_series must not be empty")
    for n in population_size_series:
        if isinstance(n, (bool, np.bool_)) or not isinstance(
                n, (int, np.integer)):
            raise ValueError(
                "each population size must be an int, got "
                f"{n!r}")
        if n < 1:
            raise ValueError(f"population size must be >= 1, got {n}")
    k = float(len(population_size_series))
    inv_sum = sum(1.0 / float(n) for n in population_size_series)
    return float(k / inv_sum)


# ---------------------------------------------------------------------------
# Wright's island-model equilibrium Fst
# ---------------------------------------------------------------------------


def theoretical_fst(
    population_size: int,
    migration_rate: float,
    mutation_rate: float = 0.0,
) -> float:
    """Wright's classical island-model equilibrium Fst.

    For a metapopulation of demes of census size N exchanging migrants
    at rate m per generation (with symmetric mutation rate u), the
    equilibrium level of among-deme differentiation is approximately::

        Fst = 1 / (1 + 4N(m + u))

    (Wright 1931; mutation enters as another force mixing the global
    allele pool). Assumes the number of demes is large (the infinite
    island model); with few demes the observed Fst is lower because the
    finite metapopulation itself drifts toward fixation.

    Args:
        population_size: diploid census size N per deme
        migration_rate: per-generation migration rate m, in [0, 1]
        mutation_rate: per-copy symmetric mutation rate u, in [0, 1)

    Returns:
        the equilibrium Fst in (0, 1]

    Raises:
        ValueError: if N <= 0, migration_rate outside [0, 1], or
            mutation_rate outside [0, 1)
    """
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if not 0.0 <= migration_rate <= 1.0:
        raise ValueError("migration_rate must be in [0, 1]")
    if not 0.0 <= mutation_rate < 1.0:
        raise ValueError("mutation_rate must be in [0, 1)")
    if migration_rate == 0.0 and mutation_rate == 0.0:
        return 1.0  # no mixing at all: demes drift to complete divergence
    return 1.0 / (1.0 + 4.0 * population_size
                  * (migration_rate + mutation_rate))


# ---------------------------------------------------------------------------
# Parameter sweeps over the Wright-Fisher model
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Exact Markov chain: transition matrix and expected fixation time
# ---------------------------------------------------------------------------


def _wf_p_adj(
    p: np.ndarray,
    selection_coefficient: float,
    dominance: float | None,
) -> np.ndarray:
    """Post-selection allele frequency, mirroring simulate_wright_fisher's
    selection step exactly (haploid or diploid-with-dominance scheme)."""
    if selection_coefficient == 0.0:
        return p
    s = selection_coefficient
    if dominance is None:
        return p * (1.0 + s) / (1.0 + p * s)
    h = dominance
    p2 = p * p
    pq = p * (1.0 - p)
    q2 = (1.0 - p) * (1.0 - p)
    w_bar = (p2 * (1.0 + s) + 2.0 * pq * (1.0 + h * s) + q2)
    return (p2 * (1.0 + s) + pq * (1.0 + h * s)) / w_bar  # type: ignore[return-value]


def _binom_pmf_log(k: int, n: int, p: float) -> float:
    """Log of the Binomial(n, p) point mass at k, in lgamma space so it
    never overflows (handles n up to several thousand)."""
    if p == 0.0:
        return 0.0 if k == 0 else -math.inf
    if p == 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1)
            - math.lgamma(n - k + 1) + k * math.log(p)
            + (n - k) * math.log1p(-p))


def wright_fisher_transition_matrix(
    population_size: int,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> np.ndarray:
    """The exact Wright-Fisher one-generation transition matrix.

    ``Q[i, j]`` is the probability that a panmictic population with
    ``i`` copies of allele A (out of ``2N``) has ``j`` copies one
    generation later, applying the same per-generation steps as
    ``simulate_wright_fisher``: selection (haploid, or diploid with
    dominance), binomial reproduction over ``2N`` copies, then
    per-copy symmetric mutation. The matrix has shape
    ``(2N+1) x (2N+1)`` and every row sums to 1.

    With ``mutation_rate=0`` states 0 and 2N are absorbing (the chain
    has no way to leave them); with ``mutation_rate > 0`` the chain is
    ergodic (the mutation step is folded in exactly via the
    convolution of the two mutation Binomials, matching the
    simulation's two-step mutation draw).

    Not applicable (as in the simulation) to structured populations:
    the matrix describes a single panmictic deme, so there are no
    ``n_demes``/``migration``/``population_size_series`` parameters.

    Args:
        population_size: diploid census size N per deme
        mutation_rate: per-copy symmetric mutation rate u, in [0, 1)
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the (2N+1) x (2N+1) transition matrix as a float64 ndarray

    Raises:
        ValueError: on invalid parameters
    """
    if isinstance(population_size, (bool, np.bool_)) or not isinstance(
            population_size, (int, np.integer)) or population_size < 1:
        raise ValueError("population_size must be an integer >= 1")
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        raise ValueError("mutation_rate must be a number")
    if math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 <= mutation_rate < 1.0:
        raise ValueError("mutation_rate must be in [0, 1)")
    if isinstance(selection_coefficient, (bool, np.bool_)) or not isinstance(
            selection_coefficient, (int, float, np.integer, np.floating)):
        raise ValueError("selection_coefficient must be a number")
    if math.isnan(selection_coefficient) or math.isinf(
            selection_coefficient) or selection_coefficient <= -1.0:
        raise ValueError("selection_coefficient must be > -1")
    if dominance is not None:
        if isinstance(dominance, (bool, np.bool_)) or not isinstance(
                dominance, (int, float, np.integer, np.floating)):
            raise ValueError("dominance must be a number or None")
        if not 0.0 <= dominance <= 2.0:
            raise ValueError("dominance must be in [0, 2] or None")

    N = int(population_size)
    K = 2 * N + 1
    copies = np.arange(K, dtype=np.float64)
    p_adj = _wf_p_adj(copies / (2.0 * N),
                      selection_coefficient, dominance)

    Q = np.zeros((K, K), dtype=np.float64)
    log_row = np.empty(K)
    for i in range(K):
        pa = p_adj[i]
        if pa == 0.0:
            Q[i, 0] = 1.0
            continue
        if pa == 1.0:
            Q[i, K - 1] = 1.0
            continue
        for j in range(K):
            log_row[j] = _binom_pmf_log(j, 2 * N, pa)
        Q[i] = np.exp(log_row)
    # Renormalize: log-space exp can shed mass to rounding.
    row_sums = Q.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0.0] = 1.0
    Q /= row_sums

    if mutation_rate > 0.0:
        u = float(mutation_rate)
        M = np.zeros((K, K), dtype=np.float64)
        for k in range(K):
            n_a = 2 * N - k
            pm1 = np.array(
                [math.exp(_binom_pmf_log(m1, k, u)) for m1 in range(k + 1)])
            pm2 = np.array(
                [math.exp(_binom_pmf_log(m2, n_a, u))
                 for m2 in range(n_a + 1)])
            target = np.arange(n_a + 1)
            for m1 in range(k + 1):
                if pm1[m1] > 0.0:
                    M[k, k - m1 + target] += pm1[m1] * pm2
        Q = Q @ M
    return Q


def _wf_chain_setup(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float,
    dominance: float | None,
) -> Tuple[np.ndarray, int]:
    """Shared validation + transition-matrix build for the exact-chain
    functions. Returns ``(Q, i0)`` where ``i0`` is the state closest
    to ``starting_frequency * 2N`` copies of A."""
    if isinstance(starting_frequency, (bool, np.bool_)) or not isinstance(
            starting_frequency, (int, float, np.integer, np.floating)):
        raise ValueError("starting_frequency must be a number")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")
    Q = wright_fisher_transition_matrix(
        population_size, 0.0, selection_coefficient, dominance)
    K = Q.shape[0]
    i0 = int(round(starting_frequency * (K - 1)))
    return Q, i0


def _wf_fixation_vector(q: np.ndarray) -> np.ndarray:
    """Absorption probabilities of the all-A state from every interior
    state, for a transition matrix ``Q`` with absorbing states 0 and
    ``K-1``: ``f[j]`` = P(hit all-A before all-a | start with j+1
    copies of A). Solves ``(I - Q_t) f = p_top`` with boundaries
    ``f_0 = 0``, ``f_{K-1} = 1``."""
    K = q.shape[0]
    transient = slice(1, K - 1)
    q_t = q[transient, transient]
    p_top = q[transient, K - 1]
    return np.linalg.solve(np.eye(q_t.shape[0]) - q_t, p_top)


def wright_fisher_fixation_probability(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Probability that allele A fixes, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    This is the exact value of which ``kimura_fixation_probability``
    (Kimura 1962) is the diffusion approximation: it solves the
    absorption system of ``wright_fisher_transition_matrix`` for
    P(hit the all-A state before the all-a state). For neutrality the
    martingale property makes it exactly ``starting_frequency``; for
    genic selection it matches Kimura's closed form within the
    diffusion error (~0.01-0.02); and — unlike the diffusion
    approximation — it stays reliable for ``dominance > 1``
    (over/underdominance), where Kimura's formula is documented as
    unreliable (error up to ~0.25).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-A state and fixation never strictly occurs,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the exact fixation probability in [0, 1] (0.0 at frequency 0,
        1.0 at frequency 1)

    Raises:
        ValueError: on invalid parameters
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    if i0 <= 0:
        return 0.0
    if i0 >= Q.shape[0] - 1:
        return 1.0
    f = _wf_fixation_vector(Q)
    return float(f[i0 - 1])


def wright_fisher_expected_fixation_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time to fixation of allele A, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    Solves the Markov chain whose transition matrix is
    ``wright_fisher_transition_matrix``: the expected number of
    generations to hit the all-A state (2N copies), conditional on
    fixation occurring, starting from ``starting_frequency``. This is
    the exact value of which ``expected_fixation_time`` (Kimura &
    Ohta's 1969 diffusion closed form) is the continuous
    approximation — the two agree to within ~1-2 % and converge as N
    grows. ``selection_coefficient``/``dominance`` enter through the
    exact transition probabilities, so the result is valid for
    selection of any strength in (0, 1].

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-A state and fixation never strictly occurs,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in (0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to fixation, given that fixation
        occurs (0.0 when the allele is already fixed)

    Raises:
        ValueError: on invalid parameters, or when the allele cannot
            fix from the starting frequency (``starting_frequency``
            of 0)
    """
    if isinstance(starting_frequency, (bool, np.bool_)) or not isinstance(
            starting_frequency, (int, float, np.integer, np.floating)):
        raise ValueError("starting_frequency must be a number")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")
    if starting_frequency == 0.0:
        raise ValueError("an allele at frequency 0 never fixes")
    if starting_frequency == 1.0:
        return 0.0
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    if i0 <= 0:
        raise ValueError("an allele at frequency 0 never fixes")
    if i0 >= Q.shape[0] - 1:
        return 0.0

    K = Q.shape[0]
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    p_top = Q[transient, K - 1]
    f = _wf_fixation_vector(Q)
    # w[j]: E[T * 1_{fixation}], solving (I - Q_t) w = Q_t f + p_top
    # with boundaries w_0 = w_top = 0; then E[T | fixation] = w / f.
    w = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t, Q_t @ f + p_top)
    f_val = f[i0 - 1]
    if f_val <= 1e-15:
        raise ValueError(
            "allele cannot fix from this starting frequency")
    return float(w[i0 - 1] / f_val)


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


def wright_fisher_expected_loss_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time to loss of allele A, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    The mirror image of ``wright_fisher_expected_fixation_time``:
    solves the same transition matrix for ``E[T | loss]``, the mean
    number of generations to hit the all-a state (0 copies of A),
    conditional on loss occurring. Under neutrality it equals
    ``wright_fisher_expected_fixation_time(1 - p)`` by symmetry, and
    both are approximated within ~1-2 % by the Kimura & Ohta 1969
    closed forms (``expected_loss_time`` /
    ``expected_fixation_time``). With selection, the loss time is
    exact for any strength in (0, 1].

    Note the boundary convention difference from the closed form:
    ``expected_loss_time`` returns the diffusion limit 4N at
    ``p0 = 1``, while the exact chain treats the fixed state as
    absorbing and raises (the allele cannot be lost).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-a state and loss never strictly occurs, so
    the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1)
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to loss, given that loss occurs
        (0.0 when the allele is already lost)

    Raises:
        ValueError: on invalid parameters, or when the allele cannot
            be lost from the starting frequency (``starting_frequency``
            of 1)
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    K = Q.shape[0]
    if i0 <= 0:
        return 0.0
    if i0 >= K - 1:
        raise ValueError(
            "an allele fixed at frequency 1 cannot be lost")
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    p_bottom = Q[transient, 0]
    f = _wf_fixation_vector(Q)
    # v[j]: E[T * 1_{loss}], solving (I - Q_t) v = Q_t (1 - f) + p_bottom
    # with boundaries v_0 = v_top = 0; then E[T | loss] = v / (1 - f).
    v = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t,
                        Q_t @ (1.0 - f) + p_bottom)
    f_val = f[i0 - 1]
    if 1.0 - f_val <= 1e-15:
        raise ValueError(
            "allele cannot be lost from this starting frequency")
    return float(v[i0 - 1] / (1.0 - f_val))


def wright_fisher_expected_absorption_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time until allele A is either fixed or lost, exact for
    the discrete Wright-Fisher chain.

    The unconditional mean number of generations to hit either
    absorbing boundary (0 or 2N copies of A): solves
    ``h = (I - Q_t)^{-1} 1`` on the transient states. The diffusion
    closed form (Kimura & Ohta 1969) is::

        t_bar = -4N (p0 ln p0 + (1 - p0) ln (1 - p0))

    which the exact chain approximates within ~1-2 % (at p0 = 0.5 both
    give 4N ln(2) ~= 2.77N).

    Markov-property consistency with the conditional quantities:
    ``absorption_time = fixation_time * P_fix + loss_time * (1 - P_fix)``
    (checked in the test suite).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing states and no strictly-defined absorption time,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to absorption at either boundary
        (0.0 when already fixed or lost)

    Raises:
        ValueError: on invalid parameters
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    K = Q.shape[0]
    if i0 <= 0 or i0 >= K - 1:
        return 0.0
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    h = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t,
                        np.ones(Q_t.shape[0]))
    return float(h[i0 - 1])


def _normalise_stationary_vector(v: np.ndarray) -> np.ndarray:
    """Orient and normalise a Perron-Frobenius probability vector.

    Eigenvectors are defined only up to sign.  This helper deliberately
    orients the vector before clamping so an all-negative eigenvector is not
    turned into all zeros and then divided by zero.
    """
    vector = np.asarray(v, dtype=np.float64)
    if not np.all(np.isfinite(vector)):
        raise ValueError("failed to compute the stationary distribution")
    if vector.sum() < 0.0:
        vector = -vector
    vector = np.maximum(vector, 0.0)
    total = vector.sum()
    if total == 0.0:
        raise ValueError("failed to compute the stationary distribution")
    return vector / total


def wright_fisher_stationary_vector(
    population_size: int,
    mutation_rate: float,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> List[float]:
    """Stationary distribution over A-copy counts of the exact
    Wright-Fisher chain with mutation.

    Computes the Perron-Frobenius eigenvector of
    ``wright_fisher_transition_matrix`` (with ``mutation_rate > 0``
    the chain is ergodic, so the stationary distribution is the
    unique left eigenvector with eigenvalue 1, normalized to sum to
    1): ``pi Q = pi``.

    This is the exact finite-population counterpart of Wright's
    ``Beta(4Nu, 4Nu)`` diffusion density
    (``wright_stationary_distribution``): the two agree within the
    diffusion error, and both match the simulated allele-frequency
    spectrum. It is also the first behavioral check of the mutation
    convolution in the transition matrix -- the vector's shape is
    determined entirely by how the two mutation Binomials are folded
    in.

    Returns ``pi[i]`` = stationary probability of exactly ``i``
    copies of A (out of ``2N``), ``i = 0 .. 2N``.

    Args:
        population_size: diploid census size N
        mutation_rate: per-copy symmetric mutation rate u, in (0, 1)
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the stationary distribution as a list of length 2N+1

    Raises:
        ValueError: on invalid parameters (including
            ``mutation_rate`` of 0, which would make the chain
            absorbing with no unique stationary distribution)
    """
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        raise ValueError("mutation_rate must be a number")
    if math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 < mutation_rate < 1.0:
        raise ValueError("mutation_rate must be in (0, 1)")
    Q = wright_fisher_transition_matrix(
        population_size, mutation_rate,
        selection_coefficient, dominance)
    from scipy.linalg import eig
    # Left eigenvectors are the right eigenvectors of Q^T; the
    # stationary distribution is the one for eigenvalue 1.
    eigvals, eigvecs = eig(Q.T)
    idx = int(np.argmin(np.abs(eigvals - 1.0)))
    v = _normalise_stationary_vector(np.real(eigvecs[:, idx]))
    return [float(x) for x in v]


# ---------------------------------------------------------------------------
# Wright's stationary distribution (mutation-drift balance)
# ---------------------------------------------------------------------------


def wright_stationary_distribution(
    points: Sequence[float],
    mutation_rate: float,
    population_size: int,
) -> List[float]:
    """Wright's (1931) stationary distribution of allele frequency under
    mutation-drift balance.

    For a diploid population of size N with per-copy symmetric mutation
    rate u, the equilibrium distribution of allele frequency is
    Beta(4Nu, 4Nu)::

        phi(p) = C * p^(4Nu-1) * (1-p)^(4Nu-1)

    where C normalizes the density. With 4Nu < 1 the density is
    unbounded at the edges (most populations fixed); with 4Nu > 1 it is
    a single central hump (polymorphism maintained).

    Args:
        points: frequencies at which to evaluate the density
        mutation_rate: per-copy symmetric mutation rate u
        population_size: diploid census size N

    Returns:
        the density evaluated at each point (0.0 outside (0, 1),
        math.inf at the boundaries when 4Nu < 1)

    Raises:
        ValueError: if mutation_rate or population_size is not positive
    """
    if mutation_rate <= 0.0:
        raise ValueError("mutation_rate must be > 0")
    if population_size <= 0:
        raise ValueError("population_size must be positive")

    a = 4.0 * mutation_rate * population_size
    from scipy.special import gammaln
    log_norm = gammaln(2.0 * a) - 2.0 * gammaln(a)

    out: List[float] = []
    for p in points:
        if p <= 0.0 or p >= 1.0:
            out.append(0.0 if a > 1.0 else math.inf)
        else:
            log_d = ((a - 1.0) * math.log(p)
                     + (a - 1.0) * math.log(1.0 - p) + log_norm)
            out.append(math.exp(log_d))
    return out


# ---------------------------------------------------------------------------
# Two-locus Wright-Fisher simulation (haploid, recombination)
# ---------------------------------------------------------------------------

TL_PLAUSIBLE_MIN_POPULATION_SIZE = 1
TL_PLAUSIBLE_MAX_RECOMBINATION = 0.5

_TL_ABS_FREQ_TOL = 1e-6


@dataclass
class TwoLocusResult:
    """Two-locus simulation output: linkage disequilibrium per
    generation, averaged over replicates."""

    colnames: List[str]
    data: List[List[float]]
    params: Dict[str, Any]
    n_replicates: int
    seed: Optional[int] = None
    replicate_data: Optional[List[List[float]]] = None
    replicate_colnames: Optional[List[str]] = None
    validation: ParameterValidation = field(default_factory=ParameterValidation)

    @property
    def flagged(self) -> bool:
        return self.validation.flagged

    def column(self, name: str) -> List[float]:
        if name not in self.colnames:
            raise KeyError(f"no column {name!r} in {self.colnames}")
        idx = self.colnames.index(name)
        return [row[idx] for row in self.data]

    @property
    def colnames_list(self) -> List[str]:
        return list(self.colnames)

    def __len__(self) -> int:
        return len(self.data)

    def final(self, name: str) -> float:
        return self.column(name)[-1]

    def ld_analysis(self) -> Dict[str, Any]:
        """Linkage-disequilibrium summary over replicates.

        Returns the mean and SD of D at the final generation, the
        mean of r2 there, and the D at generation 0, plus a decay
        factor ``d_final/d_initial`` comparing the observed final mean
        D against the initial D (expect ``(1-r)^t * (1-1/N)^t`` in
        expectation).
        """
        d0 = self.column("mean_D")[0]
        dfinal = self.column("mean_D")[-1]
        r2final = self.column("mean_r2")[-1]
        out: Dict[str, Any] = {
            "d_initial": d0,
            "d_final": dfinal,
            "r2_final": r2final,
            "decay_factor": (dfinal / d0 if d0 != 0.0 else float("nan")),
        }
        if self.replicate_data is not None and self.n_replicates > 1:
            reps = np.asarray(self.replicate_data, dtype=np.float64)
            d_last = reps[-1, 1:]
            out["sd_D_final"] = float(np.std(d_last, ddof=1))
        else:
            out["sd_D_final"] = None
        return out


def _tl_validate(
    population_size: int,
    generations: int,
    recombination_rate: float,
    mutation_rate: float,
    f: Tuple[float, float, float, float],
    replicate_runs: int,
) -> ParameterValidation:
    errors: List[str] = []
    flagged: List[str] = []
    if isinstance(population_size, (bool, np.bool_)) or not isinstance(
            population_size, (int, np.integer)):
        errors.append("population_size must be an int")
    elif population_size < TL_PLAUSIBLE_MIN_POPULATION_SIZE:
        errors.append("population_size must be >= 1")
    if isinstance(generations, (bool, np.bool_)) or not isinstance(
            generations, (int, np.integer)):
        errors.append("generations must be an int")
    elif generations < 1 or generations > WF_PLAUSIBLE_MAX_GENERATIONS:
        errors.append(
            f"generations must be between 1 and "
            f"{WF_PLAUSIBLE_MAX_GENERATIONS}")
    if isinstance(recombination_rate, (bool, np.bool_)) or not isinstance(
            recombination_rate, (int, float, np.integer, np.floating)):
        errors.append("recombination_rate must be a number")
    elif math.isnan(recombination_rate) or math.isinf(
            recombination_rate) or not (
                0.0 <= recombination_rate <= TL_PLAUSIBLE_MAX_RECOMBINATION):
        errors.append(
            f"recombination_rate must be in "
            f"[0, {TL_PLAUSIBLE_MAX_RECOMBINATION}]")
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        errors.append("mutation_rate must be a number")
    elif math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 <= mutation_rate <= 1.0:
        errors.append("mutation_rate must be in [0, 1]")
    if isinstance(replicate_runs, (bool, np.bool_)) or not isinstance(
            replicate_runs, (int, np.integer)):
        errors.append("replicate_runs must be an int")
    elif replicate_runs < 1:
        errors.append("replicate_runs must be >= 1")
    if len(f) != 4:
        errors.append(
            "starting_frequencies must have exactly 4 entries "
            "(f_AB, f_Ab, f_aB, f_ab)")
    elif not all(isinstance(x, (int, float, np.integer, np.floating))
                 and not isinstance(x, (bool, np.bool_))
                 and not math.isnan(float(x)) and not math.isinf(float(x))
                 and 0.0 <= float(x) <= 1.0 for x in f):
        errors.append("haplotype frequencies must be numbers in [0, 1]")
    elif abs(sum(f) - 1.0) > _TL_ABS_FREQ_TOL:
        errors.append(
            f"haplotype frequencies must sum to 1, got {sum(f):.8f}")
    return ParameterValidation(ok=not errors, flagged=flagged, errors=errors)  # type: ignore[arg-type]


def simulate_two_locus_wright_fisher(
    population_size: int,
    generations: int,
    recombination_rate: float,
    starting_frequencies: Sequence[float] = (0.25, 0.25, 0.25, 0.25),
    mutation_rate: float = 0.0,
    replicate_runs: int = 1,
    seed: Optional[int] = None,
    return_replicate_data: bool = False,
) -> TwoLocusResult:
    """Haploid two-locus Wright-Fisher simulation with recombination.

    Each individual carries one copy of locus A (alleles A/a) and one
    of locus B (alleles B/b), so the population is described by the
    frequencies of four haplotypes::

        f = (f_AB, f_Ab, f_aB, f_ab)

    Each generation: (1) recombination reassorts the two loci at rate
    ``r`` (per generation, in [0, 0.5]) -- the coupling gametes
    ``AB``/``ab`` lose ``r*D`` and the repulsion gametes ``Ab``/``aB``
    gain it, where ``D = f_AB*f_ab - f_Ab*f_aB`` is the linkage
    disequilibrium -- (2) genetic drift samples ``N`` haploid gametes
    multinomially, and (3) each locus mutates symmetrically at rate
    ``u`` per copy (``AB -> Ab/aB`` with probability ``u(1-u)`` each,
    ``-> ab`` with ``u^2``, and the reverse for the other three
    haplotypes).

    In expectation, recombination decays ``D`` by ``(1-r)`` per
    generation, drift by ``(1 - 1/N)``, and the two mutating loci by
    ``(1-2u)^2`` each generation (each locus contributes one
    ``(1-2u)`` factor), so::

        E[D_t] = D_0 * (1-r)^t * (1-2u)^(2t) * (1 - 1/N)^t

    (see ``theoretical_ld_decay``). Without mutation the per-locus
    frequencies are conserved in expectation; with mutation they
    drift toward 0.5.

    Args:
        population_size: haploid census size N
        generations: number of generations to simulate
        recombination_rate: per-generation recombination fraction r in
            [0, 0.5]
        starting_frequencies: initial haplotype frequencies
            (f_AB, f_Ab, f_aB, f_ab), summing to 1
        mutation_rate: per-copy symmetric mutation rate u per locus,
            in [0, 1]
        replicate_runs: number of replicate populations to average
        seed: RNG seed (numpy default_rng convention, ADR 0005)
        return_replicate_data: keep per-replicate per-generation D
            (rows: generation, replicate D values)

    Returns:
        a TwoLocusResult with columns ``generation``, ``mean_D``,
        ``mean_r2``, ``mean_freq_A``, ``mean_freq_B`` (and
        ``sd_D`` when replicate_runs > 1)

    Raises:
        ModelBuildError: on invalid parameters
    """
    v = _tl_validate(
        population_size, generations, recombination_rate, mutation_rate,
        tuple(float(x) for x in starting_frequencies), replicate_runs)  # type: ignore[arg-type]
    if not v.ok:
        raise ModelBuildError("; ".join(v.errors))

    n, r = int(population_size), float(recombination_rate)
    u = float(mutation_rate)
    f0 = tuple(float(x) for x in starting_frequencies)
    rng = np.random.default_rng(seed)
    p_AB, p_Ab, p_aB, p_ab = f0  # type: ignore[assignment]
    d0 = p_AB * p_ab - p_Ab * p_aB

    rows: List[List[float]] = []
    rep_data: List[List[float]] = []
    for t in range(generations + 1):
        if t > 0:
            d = p_AB * p_ab - p_Ab * p_aB
            p_AB = p_AB - r * d
            p_ab = p_ab - r * d
            p_Ab = p_Ab + r * d
            p_aB = p_aB + r * d
            pvals = np.stack([p_AB, p_Ab, p_aB, p_ab], axis=-1)
            pvals = np.maximum(pvals, 0.0)
            pvals[..., -1] = 1.0 - pvals[..., :3].sum(axis=-1)
            counts = rng.multinomial(n, pvals, size=replicate_runs)
            p_AB = counts[:, 0] / n  # type: ignore[assignment]
            p_Ab = counts[:, 1] / n  # type: ignore[assignment]
            p_aB = counts[:, 2] / n  # type: ignore[assignment]
            p_ab = counts[:, 3] / n  # type: ignore[assignment]
            if u > 0.0:
                uu = u * u
                cu = u * (1.0 - u)
                mu = (1.0 - u) * (1.0 - u)
                n_AB = (mu * p_AB + cu * p_Ab + cu * p_aB + uu * p_ab)
                n_Ab = (mu * p_Ab + cu * p_AB + cu * p_ab + uu * p_aB)
                n_aB = (mu * p_aB + cu * p_AB + cu * p_ab + uu * p_Ab)
                n_ab = (mu * p_ab + cu * p_aB + cu * p_Ab + uu * p_AB)
                p_AB, p_Ab, p_aB, p_ab = n_AB, n_Ab, n_aB, n_ab
        else:
            counts = np.round(np.asarray(f0) * n).astype(int)
            deficit = n - int(counts.sum())
            counts[np.argmax(counts)] += deficit
            counts = np.tile(counts[None, :], (replicate_runs, 1))
            # recompute exact starting frequencies from the counts so
            # replicate averages match generation 0 exactly
            p_AB = counts[:, 0] / n  # type: ignore[assignment]
            p_Ab = counts[:, 1] / n  # type: ignore[assignment]
            p_aB = counts[:, 2] / n  # type: ignore[assignment]
            p_ab = counts[:, 3] / n  # type: ignore[assignment]
        D = p_AB * p_ab - p_Ab * p_aB
        fA = p_AB + p_Ab
        fB = p_AB + p_aB
        denom = fA * (1 - fA) * fB * (1 - fB)
        r2 = np.zeros_like(D)
        ok = denom > 1e-12
        r2[ok] = D[ok] ** 2 / denom[ok]  # type: ignore[index,operator]
        rows.append([
            float(t),
            float(np.mean(D)),
            float(np.mean(r2)),
            float(np.mean(fA)),
            float(np.mean(fB)),
            (float(np.std(D, ddof=1)) if replicate_runs > 1 else 0.0),
        ])
        if return_replicate_data:
            rep_data.append([float(t)] + [float(x) for x in D])  # type: ignore

    colnames = ["generation", "mean_D", "mean_r2", "mean_freq_A",
                "mean_freq_B", "sd_D"]
    params: Dict[str, Any] = {
        "population_size": n,
        "generations": generations,
        "recombination_rate": r,
        "mutation_rate": u,
        "starting_frequencies": f0,
        "d_initial": d0,
        "replicate_runs": replicate_runs,
        "seed": seed,
    }
    return TwoLocusResult(
        colnames=colnames, data=rows, params=params,
        n_replicates=replicate_runs, seed=seed,
        replicate_data=rep_data if return_replicate_data else None,
        replicate_colnames=["generation", "D"] if return_replicate_data
        else None, validation=v)


def theoretical_ld_decay(
    d_initial: float,
    recombination_rate: float,
    generations: int,
    population_size: Optional[int] = None,
    mutation_rate: float = 0.0,
) -> float:
    """Expected linkage disequilibrium after ``generations``::

        E[D_t] = D_0 * (1-r)^t * (1-2u)^(2t) * (1 - 1/N)^t

    -- recombination decays D by ``(1-r)`` per generation (the
    fraction of gametes that keep the original coupling), each
    mutating locus by ``(1-2u)`` (mutation erodes LD because it
    converts coupling haplotypes into repulsion ones and vice versa),
    and haploid genetic drift by ``(1 - 1/N)`` per generation (the
    fraction of pairs of gametes drawn without replacement).

    With ``population_size=None`` only recombination and mutation are
    included (the N -> infinity drift factor of 1).

    Args:
        d_initial: D at generation 0
        recombination_rate: per-generation recombination fraction r
        generations: number of generations t
        population_size: haploid census size N (None = no drift)
        mutation_rate: per-copy symmetric mutation rate u per locus,
            in [0, 1] (default 0 = no mutation)

    Returns:
        expected D_t

    Raises:
        ValueError: on invalid arguments
    """
    if isinstance(recombination_rate, (bool, np.bool_)) or not isinstance(
            recombination_rate, (int, float, np.integer, np.floating)):
        raise ValueError("recombination_rate must be a number")
    if math.isnan(recombination_rate) or math.isinf(recombination_rate) \
            or not 0.0 <= recombination_rate <= TL_PLAUSIBLE_MAX_RECOMBINATION:
        raise ValueError(
            f"recombination_rate must be in "
            f"[0, {TL_PLAUSIBLE_MAX_RECOMBINATION}]")
    if isinstance(generations, (bool, np.bool_)) or not isinstance(
            generations, (int, np.integer)):
        raise ValueError("generations must be an int")
    if generations < 0:
        raise ValueError("generations must be >= 0")
    if population_size is not None:
        if isinstance(population_size, (bool, np.bool_)) or not isinstance(
                population_size, (int, np.integer)):
            raise ValueError("population_size must be an int or None")
        if population_size < 1:
            raise ValueError("population_size must be >= 1")
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        raise ValueError("mutation_rate must be a number")
    if math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 <= mutation_rate <= 1.0:
        raise ValueError("mutation_rate must be in [0, 1]")
    drift = 1.0 if population_size is None else (
        1.0 - 1.0 / float(population_size))
    mut_factor = (1.0 - 2.0 * float(mutation_rate)) ** 2
    return float(d_initial) * (1.0 - float(recombination_rate)) ** generations \
        * mut_factor ** generations * drift ** generations


def expected_fst_after_split(
    population_size: int,
    generations: int,
    starting_frequency: float = 0.5,
) -> float:
    """Expected Fst between two isolated daughter populations, *exact*
    for the Wright-Fisher chain.

    Two demes of size N split from a common ancestral pool (both start
    at the same allele frequency p0) and exchange no migrants. Their
    frequencies are then independent chains, so the exact expectation
    of the engine's Nei-style per-replicate Fst
    (``1 - Hs/Ht``, with ``Hs`` the mean within-deme heterozygosity,
    ``Ht = 2pbar(1-pbar)``, and 0 where ``Ht = 0``) is::

        E[Fst(t)] = sum_{i,j} pi_t(i) pi_t(j) fst(i, j)

    where ``pi_t`` is the single-deme transition matrix applied for t
    generations from ``round(2N*p0)`` copies of A and ``fst(i, j)`` is
    the pairwise Fst of demes with i and j copies of A.

    Key consequences (verified against simulation, N=100, p0=0.5,
    2000 replicates: within 0.01 at every generation, e.g. t=200:
    0.350 observed vs 0.347 exact):

    - Fst rises monotonically from 0.
    - It does NOT approach 1: as t -> inf each deme fixes
      independently, so Fst(t) -> 2*p0*(1-p0), the probability of
      divergent fixation (0.5 at p0=0.5; 0.494 at t=800).
    - The textbook ``1 - (1-1/(2N))^t ~ 1 - e^{-t/(2N)}`` formula is
      the *variance-based* estimator (total variance conserved) and
      runs well above this Nei-style expectation (0.63 vs 0.35 at
      t=200, N=100).

    Args:
        population_size: diploid census size N per deme
        generations: generations since the split t
        starting_frequency: common initial allele frequency p0

    Returns:
        exact expected Fst

    Raises:
        ValueError: on invalid parameters
    """
    if isinstance(population_size, (bool, np.bool_)) or not isinstance(
            population_size, (int, np.integer)):
        raise ValueError("population_size must be an int")
    if population_size < 1:
        raise ValueError("population_size must be >= 1")
    if isinstance(generations, (bool, np.bool_)) or not isinstance(
            generations, (int, np.integer)):
        raise ValueError("generations must be an int")
    if generations < 0:
        raise ValueError("generations must be >= 0")
    if isinstance(starting_frequency, (bool, np.bool_)) or not isinstance(
            starting_frequency, (int, float, np.integer, np.floating)):
        raise ValueError("starting_frequency must be a number")
    if math.isnan(starting_frequency) or math.isinf(starting_frequency) \
            or not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")

    two_n = 2 * population_size
    q = wright_fisher_transition_matrix(
        population_size, mutation_rate=0.0)
    pi = np.zeros(two_n + 1)
    i0 = int(round(two_n * starting_frequency))
    pi[i0] = 1.0
    i_vals = np.arange(two_n + 1) / two_n
    h = 2.0 * i_vals * (1.0 - i_vals)
    for _ in range(generations):
        pi = pi @ q
    if generations == 0:
        return 0.0
    outer = pi[:, None] * pi[None, :]
    hs = (h[:, None] + h[None, :]) / 2.0
    pm = (i_vals[:, None] + i_vals[None, :]) / 2.0
    ht = 2.0 * pm * (1.0 - pm)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(ht > 0.0, 1.0 - hs / ht, 0.0)
    return float(np.sum(outer * f))


# ---------------------------------------------------------------------------
# Molecular dynamics — Lennard-Jones cluster, velocity Verlet
#
# ADR 0006: this is continuous-time but does NOT use antimony/roadrunner.
# MD correctness depends on energy conservation from a symplectic,
# fixed-step integrator — a general adaptive-step solver trades energy
# conservation for local error control, which is the wrong property here.
# Direct Python + numpy with velocity Verlet. ADR 0005 applies to the
# Maxwell–Boltzmann velocity initialization.
#
# Reduced units throughout: epsilon = sigma = mass = 1.
# ---------------------------------------------------------------------------


def lennard_jones_force(
    r_vec: np.ndarray,
) -> np.ndarray:
    """Lennard-Jones force vector on particle i from particle j.

    Args:
        r_vec: separation vector ``r_i - r_j``, shape ``(3,)``.

    Returns:
        force vector on particle i, shape ``(3,)``. The force on particle j
        is the negative of this vector (Newton's third law).

    With reduced units (:math:`\\varepsilon = \\sigma = 1`):

    .. math::

        \\mathbf{F}_{ij} = 24 \\left(
            \\frac{2}{r^{14}} - \\frac{1}{r^8}
        \\right) \\mathbf{r}_{ij}
    """
    r_sq = float(np.dot(r_vec, r_vec))
    if r_sq == 0.0:
        return np.zeros(3, dtype=np.float64)
    r2_inv = 1.0 / r_sq
    r6_inv = r2_inv ** 3
    r8_inv = r6_inv * r2_inv
    r14_inv = r8_inv * r6_inv
    magnitude = 24.0 * (2.0 * r14_inv - r8_inv)
    return magnitude * r_vec


def _fcc_lattice_positions(
    n_particles: int,
    density: float,
) -> Tuple[np.ndarray, int]:
    """Place particles on an fcc lattice and centre the cluster at the origin.

    The conventional fcc cell holds 4 particles. The number of cells per side
    ``k`` is chosen so ``4 * k**3 >= n_particles``. All ``4 * k**3``
    positions are returned (the count is rounded *up*, never truncated —
    per the spec, the simulation runs with the rounded-up count).

    Args:
        n_particles: requested particle count (may be rounded up).
        density: number density :math:`\\rho = N / V` in reduced units.

    Returns:
        ``(positions, actual_n)`` where ``positions`` has shape
        ``(actual_n, 3)`` and ``actual_n`` is the fcc-compatible count.
    """
    # Number of unit cells per dimension
    k = int(math.ceil((n_particles / 4.0) ** (1.0 / 3.0)))
    k = max(k, 1)
    actual_n = 4 * k ** 3

    # Lattice constant from density: rho = 4 / a^3  =>  a = (4 / rho)^{1/3}
    a = (4.0 / density) ** (1.0 / 3.0)

    # fcc conventional-cell basis (fractional coordinates)
    basis = np.array([
        [0.0, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.5, 0.0, 0.5],
        [0.0, 0.5, 0.5],
    ], dtype=np.float64)

    positions = np.empty((actual_n, 3), dtype=np.float64)
    idx = 0
    for ix in range(k):
        for iy in range(k):
            for iz in range(k):
                cell_origin = a * np.array([ix, iy, iz], dtype=np.float64)
                for b in basis:
                    positions[idx] = cell_origin + a * b
                    idx += 1

    # Centre at origin
    centroid = positions.mean(axis=0)
    positions -= centroid

    return positions, actual_n


# Mackay icosahedron shell vertices (cyclic permutations of (0, +/-1, +/-phi))
# with phi = (1+sqrt(5))/2.  Shared between _golden_section_lj13_scale and
# lj_cluster_positions to avoid duplication.
_ICOSAHEDRON_SHELL = np.array([
    [0.0, 1.0, (1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, 1.0, -(1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, -1.0, (1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, -1.0, -(1.0 + math.sqrt(5.0)) / 2.0],
    [1.0, (1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [1.0, -(1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [-1.0, (1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [-1.0, -(1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [(1.0 + math.sqrt(5.0)) / 2.0, 0.0, 1.0],
    [(1.0 + math.sqrt(5.0)) / 2.0, 0.0, -1.0],
    [-(1.0 + math.sqrt(5.0)) / 2.0, 0.0, 1.0],
    [-(1.0 + math.sqrt(5.0)) / 2.0, 0.0, -1.0],
], dtype=np.float64)


def _golden_section_lj13_scale() -> float:
    """One-dimensional golden-section search for the Mackay icosahedron
    scale factor that minimises total LJ potential energy.

    Bracket [0.40, 0.80], ~200 iterations, fully deterministic.
    No scipy/no general-purpose optimizer — the search is hand-written
    so the engine stays numpy-only at runtime.
    """
    phi = (1.0 + math.sqrt(5.0)) / 2.0  # golden ratio (~1.618)
    inv_phi = phi - 1.0  # ~0.618

    lo, hi = 0.40, 0.80
    mid1 = hi - inv_phi * (hi - lo)
    mid2 = lo + inv_phi * (hi - lo)

    def _lj_total(scale: float) -> float:
        pos = np.vstack((np.zeros((1, 3), dtype=np.float64),
                         scale * _ICOSAHEDRON_SHELL))
        return _compute_lj_potential(pos, 13)

    e1 = _lj_total(mid1)
    e2 = _lj_total(mid2)

    for _ in range(200):
        if e1 < e2:
            hi = mid2
            mid2 = mid1
            e2 = e1
            mid1 = hi - inv_phi * (hi - lo)
            e1 = _lj_total(mid1)
        else:
            lo = mid1
            mid1 = mid2
            e1 = e2
            mid2 = lo + inv_phi * (hi - lo)
            e2 = _lj_total(mid2)
        if hi - lo < 1e-12:
            break

    return (lo + hi) / 2.0


def lj_cluster_positions(n_particles: int) -> np.ndarray:
    """Known global-minimum geometry for small Lennard-Jones clusters,
    shape ``(n_particles, 3)``.

    Supports exactly ``n`` in ``{2, 3, 4, 13}``. Reduced units
    (``epsilon = sigma = 1``). Verified constant: ``r_min = 2^(1/6)``.

    * ``n=2`` — two particles separated by ``r_min`` along x.
    * ``n=3`` — equilateral triangle, side ``r_min``.
    * ``n=4`` — regular tetrahedron, edge ``r_min``.
    * ``n=13`` — centered Mackay icosahedron. The scale factor is
      determined by golden-section search over the LJ potential — the
      twelve shell vertices compress inward from their geometric
      positions to minimise total energy.

    Raises ``ModelBuildError`` for any other ``n_particles``.
    """
    r_min = 2.0 ** (1.0 / 6.0)  # LJ equilibrium separation

    if n_particles == 2:
        return np.array([
            [-r_min / 2.0, 0.0, 0.0],
            [r_min / 2.0, 0.0, 0.0],
        ], dtype=np.float64)

    if n_particles == 3:
        h = r_min * math.sqrt(3.0) / 2.0
        return np.array([
            [0.0, 0.0, 0.0],
            [r_min, 0.0, 0.0],
            [r_min / 2.0, h, 0.0],
        ], dtype=np.float64)

    if n_particles == 4:
        # Vertices (1,1,1),(1,-1,-1),(-1,1,-1),(-1,-1,1) scaled to edge r_min.
        # Native edge is 2*sqrt(2).
        scale = r_min / (2.0 * math.sqrt(2.0))
        v = np.array([
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ], dtype=np.float64)
        return scale * v

    if n_particles == 13:
        scale = _golden_section_lj13_scale()
        return np.vstack((
            np.zeros((1, 3), dtype=np.float64),
            scale * _ICOSAHEDRON_SHELL,
        ))

    raise ModelBuildError(
        f"lj_cluster_positions supports n in {{2, 3, 4, 13}}, "
        f"got {n_particles}")


def validate_md_params(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
) -> ParameterValidation:
    """Check molecular dynamics parameter set.

    Hard rejections (``ok=False``):
        * ``n_particles`` is boolean, not an integer, or < 2
        * ``temperature`` is boolean, not a finite float, or <= 0
        * ``timestep`` is boolean, not a finite float, or <= 0
        * ``n_steps`` is boolean, not an integer, or < 1
        * ``density`` is boolean, not a finite float, or <= 0

    Flags (``ok=True, flagged=True``):
        * ``timestep > MD_PLAUSIBLE_MAX_TIMESTEP`` — energy conservation risk
        * ``initialization temperature`` outside ``[MD_PLAUSIBLE_TEMPERATURE_LOW,
          MD_PLAUSIBLE_TEMPERATURE_HIGH]`` — frozen or evaporating cluster
        * ``n_particles`` not an exact fcc count — rounded up; actual_n differs
        * ``n_particles < MD_PLAUSIBLE_MIN_PARTICLES`` — too small for
          meaningful cluster dynamics
    """
    errors: List[str] = []

    # --- n_particles ---
    if isinstance(n_particles, (bool, np.bool_)):
        errors.append("n_particles must be an integer, not a boolean")
    elif not isinstance(n_particles, (int, np.integer)):
        errors.append(
            f"n_particles must be an integer, got "
            f"{type(n_particles).__name__}")
    elif n_particles < 2:
        errors.append(
            f"n_particles must be >= 2 (need at least a pair for a force; "
            f"got {n_particles})")

    # --- temperature ---
    _finite_positive(temperature, "temperature", errors,
                     allow_zero=False)

    # --- timestep ---
    _finite_positive(timestep, "timestep", errors,
                     allow_zero=False)

    # --- n_steps ---
    if isinstance(n_steps, (bool, np.bool_)):
        errors.append("n_steps must be an integer, not a boolean")
    elif not isinstance(n_steps, (int, np.integer)):
        errors.append(
            f"n_steps must be an integer, got {type(n_steps).__name__}")
    elif n_steps < 1:
        errors.append(
            f"n_steps must be >= 1 (got {n_steps})")

    # --- density ---
    _finite_positive(density, "density", errors,
                     allow_zero=False)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    # --- Flags (ok=True; ALL applicable flags accumulate, matching the
    # corrected WF-validator pattern — flags must not be mutually exclusive) ---
    v = ParameterValidation()
    flag_reasons: List[str] = []

    # fcc rounding
    k = int(math.ceil((n_particles / 4.0) ** (1.0 / 3.0)))
    k = max(k, 1)
    actual_n = 4 * k ** 3
    if actual_n != n_particles:
        v.flagged = True
        flag_reasons.append(
            f"n_particles={n_particles} is not an exact fcc count; "
            f"rounded up to {actual_n}")

    if timestep > MD_PLAUSIBLE_MAX_TIMESTEP:
        v.flagged = True
        flag_reasons.append(
            f"timestep {timestep} > {MD_PLAUSIBLE_MAX_TIMESTEP}: "
            "energy conservation at risk — the r^{-12} repulsive wall "
            "is under-resolved")

    if (temperature < MD_PLAUSIBLE_TEMPERATURE_LOW
            or temperature > MD_PLAUSIBLE_TEMPERATURE_HIGH):
        v.flagged = True
        flag_reasons.append(
            f"initialization temperature {temperature} is outside "
            f"[{MD_PLAUSIBLE_TEMPERATURE_LOW}, "
            f"{MD_PLAUSIBLE_TEMPERATURE_HIGH}]: "
            f"{'cluster is effectively frozen' if temperature < MD_PLAUSIBLE_TEMPERATURE_LOW else 'cluster will evaporate within the run — initialization temperatures above this lose particles'}")

    if n_particles < MD_PLAUSIBLE_MIN_PARTICLES:
        v.flagged = True
        flag_reasons.append(
            f"n_particles={n_particles} < {MD_PLAUSIBLE_MIN_PARTICLES}: "
            "too small for meaningful cluster dynamics")

    if flag_reasons:
        v.flag_reason = "; ".join(flag_reasons)

    return v


def simulate_molecular_dynamics(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
    seed: int | None = None,
) -> SimulationResult:
    """Simulate an NVE Lennard-Jones cluster via velocity Verlet integration.

    Particles are placed on an fcc lattice at the requested density. Initial
    velocities are sampled from a Maxwell–Boltzmann distribution at the
    initialization temperature, then the centre-of-mass velocity is subtracted
    (else total momentum would be non-zero at t=0, violating the domain's
    own momentum-conservation verification target before the first step
    runs).

    Args:
        n_particles: requested particle count (rounded up to the next
            fcc-compatible count if necessary).
        temperature: initialization temperature in reduced units (must be > 0).
            This is the temperature of the Maxwell–Boltzmann velocity
            distribution at t=0, NOT the equilibrated temperature — the
            fcc lattice stores excess potential energy that converts to
            kinetic during relaxation, so T_init=0.1 equilibrates UP to
            ~0.288 while T_init=2.0 equilibrates DOWN to ~0.750. The
            validation flags warn based on this initialization temperature.
        timestep: integration step size :math:`\\Delta t` in reduced units.
        n_steps: number of velocity Verlet steps.
        density: number density :math:`\\rho` in reduced units, used to
            set the fcc lattice spacing.
        seed: optional RNG seed for velocity initialization (ADR 0005).

    Returns:
        SimulationResult with columns ``["step", "time", "total_energy",
        "kinetic_energy", "potential_energy", "total_momentum_magnitude"]``,
        one row per step from 0 to ``n_steps`` inclusive.

    Raises:
        ModelBuildError: if parameters are invalid.
    """
    validation = validate_md_params(
        n_particles, temperature, timestep, n_steps, density)
    validation.raise_if_invalid()

    # --- fcc lattice placement ---
    positions, actual_n = _fcc_lattice_positions(n_particles, density)

    # --- Maxwell–Boltzmann velocity initialization (ADR 0005) ---
    rng = np.random.default_rng(seed)
    velocities = rng.normal(
        loc=0.0,
        scale=math.sqrt(temperature),  # kB=1, m=1 => sigma = sqrt(kBT/m)
        size=(actual_n, 3),
    )
    # Subtract centre-of-mass velocity
    com_velocity = velocities.mean(axis=0)
    velocities -= com_velocity

    # --- Initial forces and energies ---
    forces = _compute_pairwise_forces(positions, actual_n)
    accelerations = forces  # m = 1

    ke_initial = 0.5 * float(np.sum(velocities ** 2))
    pe_initial = _compute_lj_potential(positions, actual_n)
    te_initial = ke_initial + pe_initial
    momentum_initial = float(np.linalg.norm(velocities.sum(axis=0)))

    # --- Integration loop ---
    cols = ["step", "time", "total_energy", "kinetic_energy",
            "potential_energy", "total_momentum_magnitude"]
    data: List[List[float]] = [
        [0.0, 0.0, te_initial, ke_initial, pe_initial, momentum_initial]
    ]

    for step in range(1, n_steps + 1):
        # Velocity Verlet step
        # 1. Update positions
        positions += velocities * timestep + 0.5 * accelerations * timestep ** 2

        # 2. Half-step velocities
        velocities += 0.5 * accelerations * timestep

        # 3. New forces / accelerations
        forces = _compute_pairwise_forces(positions, actual_n)
        accelerations = forces  # m = 1

        # 4. Complete velocity update
        velocities += 0.5 * accelerations * timestep

        # Energies and momentum
        ke = 0.5 * float(np.sum(velocities ** 2))
        pe = _compute_lj_potential(positions, actual_n)
        te = ke + pe
        momentum = float(np.linalg.norm(velocities.sum(axis=0)))

        # Divergence guard: a flagged-but-valid timestep (or a
        # high-temperature run) can drive two particles into the steep
        # r^{-12} wall, after which the trajectory explodes. Explosions
        # do NOT always produce NaN/inf — kinetic energy can grow by
        # tens of orders of magnitude while staying finite — so the
        # guard fires on either non-finite values or an energy that
        # grows far beyond the (conserved, bounded-oscillating) initial
        # scale. Stop early and report the truncation as a flag rather
        # than returning a result full of junk rows.
        if not (np.isfinite(positions).all() and np.isfinite(te)
                and np.isfinite(momentum)) or abs(te) > 10.0 * abs(te_initial) + 1e-6:
            validation.flagged = True
            divergence_note = (
                f"trajectory diverged at step {step} "
                f"(|E|={abs(te):.3e} vs |E0|={abs(te_initial):.3e}); "
                f"simulation stopped early after {step - 1} steps")
            validation.flag_reason = (
                f"{validation.flag_reason}; {divergence_note}"
                if validation.flag_reason else divergence_note)
            break

        t = step * timestep
        data.append([
            float(step),
            t,
            te,
            ke,
            pe,
            momentum,
        ])

    return SimulationResult(
        colnames=cols,
        data=data,
        model_name="molecular_dynamics",
        validation=validation,
    )


def _compute_pairwise_forces(
    positions: np.ndarray,
    n: int,
) -> np.ndarray:
    """Compute all pairwise Lennard-Jones forces via vectorised numpy.

    Each pair ``(i, j)`` with ``i < j`` is evaluated once; the force is
    added to particle ``i`` and the negative to particle ``j`` (Newton's
    third law). Self-interactions (``i == j``) are skipped.

    Uses broadcasting: ``dr`` shape ``(n, n, 3)``, then contracts over the
    ``j`` axis to get total force per particle.  Much faster than nested
    Python loops for teaching-scale N (≈ 100–500).

    Args:
        positions: shape ``(n, 3)`` particle positions.
        n: number of particles (redundant with ``positions.shape[0]`` but
            kept for caller convenience).

    Returns:
        forces: shape ``(n, 3)`` total force on each particle.
    """
    # All pairwise displacement vectors  (n, n, 3)
    dr = positions[:, None, :] - positions[None, :, :]

    # Squared distances  (n, n)
    r2 = np.sum(dr * dr, axis=2)

    # Suppress self-interaction (divide-by-zero safe by using inf)
    np.fill_diagonal(r2, np.inf)

    r2_inv = 1.0 / r2
    r6_inv = r2_inv ** 3
    r8_inv = r6_inv * r2_inv
    r14_inv = r8_inv * r6_inv

    # Force magnitudes  (n, n)
    magnitudes = 24.0 * (2.0 * r14_inv - r8_inv)

    # Force vectors  (n, n, 3); contract over j-axis → (n, 3)
    forces = np.sum(magnitudes[:, :, None] * dr, axis=1)
    return forces.astype(np.float64, copy=False)  # type: ignore[return-value]


def _compute_lj_potential(
    positions: np.ndarray,
    n: int,
) -> float:
    """Compute total Lennard-Jones potential energy (sum over i<j).

    Args:
        positions: shape ``(n, 3)`` particle positions.
        n: number of particles.

    Returns:
        total potential energy in reduced units.
    """
    dr = positions[:, None, :] - positions[None, :, :]
    r2 = np.sum(dr * dr, axis=2)
    np.fill_diagonal(r2, np.inf)

    r6_inv = 1.0 / (r2 ** 3)
    r12_inv = r6_inv ** 2

    # Full matrix (symmetric); divide by 2 to get sum over i < j
    pe_matrix = 4.0 * (r12_inv - r6_inv)
    return float(np.sum(pe_matrix) * 0.5)
