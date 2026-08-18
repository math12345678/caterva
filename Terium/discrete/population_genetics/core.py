"""Wright-Fisher simulation core (neutral drift, ADR 0002/0005)."""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


from typing import Any, Dict, Sequence

import numpy as np
try:
    from Terium.core.data_structures import (SimulationResult)
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.data_structures import (SimulationResult)  # type: ignore[no-redef]

try:
    from Terium.core.validation import validate_wright_fisher_params
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.validation import validate_wright_fisher_params  # type: ignore[no-redef]

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
    population_size_series: Sequence[int] | None = None,
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

    replicate_data: np.ndarray | None = None
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
