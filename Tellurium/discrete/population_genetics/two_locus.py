"""Two-locus Wright-Fisher with recombination (haploid)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
try:
    from Tellurium.core.data_structures import (ParameterValidation, ModelBuildError, WF_PLAUSIBLE_MAX_GENERATIONS)
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ParameterValidation, ModelBuildError, WF_PLAUSIBLE_MAX_GENERATIONS)  # type: ignore[no-redef]

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
    seed: int | None = None
    replicate_data: List[List[float]] | None = None
    replicate_colnames: List[str] | None = None
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
    seed: int | None = None,
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
    population_size: int | None = None,
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
