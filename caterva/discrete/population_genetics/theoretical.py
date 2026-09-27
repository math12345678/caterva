"""Theoretical population-genetics results (Kimura, Fst, Ne estimators)."""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


import math
from typing import Any, Dict, Sequence

import numpy as np
try:
    from caterva.discrete.population_genetics.probability import (wright_fisher_transition_matrix)
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from discrete.population_genetics.probability import (wright_fisher_transition_matrix)  # type: ignore[no-redef]

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
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
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
