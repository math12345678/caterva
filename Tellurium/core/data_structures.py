"""Core data structures and plausibility constants shared by every domain.

Byte-exact extraction from the original monolithic `tellurium_engine.py`
(see REFACTORING_PROPOSAL.md, Option A).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
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
        try:
            from Tellurium.discrete.population_genetics.theoretical import (
                estimate_ne_from_heterozygosity,
            )
        except ModuleNotFoundError:  # flat mode
            from discrete.population_genetics.theoretical import (
                estimate_ne_from_heterozygosity,
            )
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

# This comment was the original judgment call that ADR 0005 superseded.
# ---------------------------------------------------------------------------

# Fewer than 100 samples gives SE ≈ 0.16 — too large for a meaningful pi
# estimate, but the simulation is physically valid and the student may be
# experimenting, so it is flagged rather than rejected.
MC_PLAUSIBLE_MIN_SAMPLES = 100

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
