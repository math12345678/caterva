"""
Terrium simulation engine: continuous (antimony/SBML/roadrunner) and
discrete (direct Python) domains, built up one stage at a time per
docs/CONSTITUTION.md.

Continuous-time domains (Tier-2 ODE, via antimony -> SBML -> roadrunner):
  * Michaelis-Menten enzyme kinetics
  * SIR / SEIR epidemiological modeling

Discrete/stochastic domains (direct Python, no ODE solver -- see ADR 0002
for why continuous-vs-discrete is a per-domain decision, not a default):
  * PCR amplification (deterministic recurrence)
  * Monte Carlo pi estimation (stochastic, ADR 0005 RNG convention)
  * Wright-Fisher population genetics / neutral drift (stochastic, ADR 0005)

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
    "PCR_MIN_EFFICIENCY",
    "PCR_MAX_EFFICIENCY",
    "PCR_PLAUSIBLE_LOW_EFFICIENCY",
    "validate_pcr_params",
    "simulate_pcr",
    "MC_PLAUSIBLE_MIN_SAMPLES",
    "validate_monte_carlo_params",
    "simulate_monte_carlo_pi",
    "WF_PLAUSIBLE_MIN_POPULATION_SIZE",
    "WF_PLAUSIBLE_MAX_GENERATIONS",
    "WF_PLAUSIBLE_MIN_REPLICATE_RUNS",
    "WF_PLAUSIBLE_MAX_MUTATION_RATE",
    "WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT",
    "validate_wright_fisher_params",
    "simulate_wright_fisher",
    "list_scenarios",
    "wright_fisher_scenario",
    "kimura_fixation_probability",
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
        mean time to fixation among those that fixed.

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
        H = np.asarray(self.column("heterozygosity"), dtype=np.float64)
        t = np.arange(len(H))
        valid = H > 1e-12
        if np.sum(valid) < 3:
            return {
                "error": "at least 3 non-zero heterozygosity values "
                         "are required"}
        slope, _ = np.polyfit(t[valid], np.log(H[valid]), 1)
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
            import os
            stem, ext = os.path.splitext(path)
            rep_path = f"{stem}_replicates{ext}"
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

    km_valid = _finite_positive(km, "Km", errors, allow_zero=False)
    vmax_valid = _finite_positive(vmax, "Vmax", errors, allow_zero=False)
    s0_valid = _finite_positive(s0, "S0", errors, allow_zero=True)
    
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
    elif migration_model == "stepping-stone" and n_demes < 3:
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
        frequencies = np.full(
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
        replicate_data = rep_arr.tolist()

    base_colnames = ["generation", "mean_frequency", "heterozygosity",
                     "mean_frequency_se", "heterozygosity_se",
                     "n_A_fixed", "n_a_fixed"]
    if structured:
        colnames = base_colnames + ["fst", "fst_se"]
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
        replicate_data=replicate_data,
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

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        selection_coefficient: selective advantage of A (s); > -1
        population_size: diploid census size N
        dominance: None = haploid selection; in [0, 1] for diploid

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
    if dominance is not None and not 0.0 <= dominance <= 1.0:
        raise ValueError("dominance must be in [0, 1] or None")

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
