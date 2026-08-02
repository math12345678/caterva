# `tellurium_engine` API reference

Public interface of `Tellurium/tellurium_engine.py`. This is the module a
backend/frontend integration would actually call -- everything else in that
file is implementation detail.

If a signature here ever drifts from the real code, trust the code and file
an issue against this doc, not the other way around.

## The `ok` / `flagged` distinction

Every domain shares one validation contract, returned as a
`ParameterValidation`:

- **`ok=False`** -- the model is physically impossible and cannot be built
  at all. `simulate_*` raises `ModelBuildError` immediately.
- **`ok=True, flagged=True`** -- the model builds and simulates fine, but a
  human should look at the result. `flag_reason` explains why. The
  resulting `SimulationResult.flagged` property is `True`.

This mirrors the same distinction `Tests/brenda_client.py` uses for
literature-derived Km values (see `docs/adr/0003-shared-plausibility-bounds.md`)
-- the two layers agree on what "implausible but real" means, not just
what's outright impossible.

## `SimulationResult`

Returned by every `simulate_*` function.

```python
result.colnames                   # list[str] - column names, e.g. ["time", "[S]"]
result.data                       # list[list[float]] - one row per time/cycle point
result.model_name                 # str
result.flagged                    # bool - shortcut for result.validation.flagged
result.column("S")                # list[float] - tolerates roadrunner's "[S]" form
result.time                       # list[float] - shortcut for result.column("time")
result.final("S")                 # float - last value of a column
result.describe()                 # str - human-readable multi-line summary
result.summarize()                # dict - key result stats (mean, SE, fixation counts)
result.replicate_data             # list[list[float]] | None - per-replicate freqs
result.replicate_colnames         # list[str] | None - column names for replicate_data

# Wright-Fisher specific (None / empty for other model types)
result.wright_fisher_params       # dict | None - all WF input params + fixation tracking
result.fixation_analysis()        # dict - per-replicate fixation times, proportions
result.theoretical_heterozygosity() # list[float] - expected H under neutral drift
result.theoretical_frequency()    # list[float] - deterministic p under selection
result.allele_frequency_spectrum(generation=None, bins=10)  # dict - frequency distribution
result.estimate_ne()              # dict - Ne from heterozygosity decay
result.estimate_ne_variance()     # dict - Ne from replicate frequency variance
result.to_dict()                  # dict - JSON-serializable whole result
result.to_csv("out.csv", include_replicate_data=False)  # str - path written
result.to_json("out.json")        # str - JSON string (also written to path)

len(result)                       # number of rows
```

Wright-Fisher result methods:

- ``result.wright_fisher_params`` -- dict of all WF input parameters
  (``population_size``, ``starting_frequency``, ``generations``,
  ``replicate_runs``, ``mutation_rate``, ``selection_coefficient``,
  ``dominance``, ``population_size_series``, ``n_demes``,
  ``migration_rate``, ``migration_model``) plus ``fixation_gen_A`` and ``fixation_gen_a``
  (list of the first generation each replicate reached frequency 1.0
  or 0.0, or -1 if never fixed within the simulation window), and
  ``final_frequencies`` (per-replicate final allele frequencies,
  pooled across demes for structured populations).

- ``result.fixation_analysis()`` -- returns a dict with ``n_replicates``,
  ``n_fixed_A``, ``n_fixed_a``, ``n_polymorphic``, ``prop_fixed_A``,
  ``prop_fixed_a``, and when replicates fixed: ``mean_fixation_time_A``,
  ``sd_fixation_time_A``, ``min/max_fixation_time_A`` (and the
  corresponding keys for allele a). Also ``n_absorbed`` (replicates
  that reached either boundary within the window) and
  ``mean_absorption_time``/``sd_absorption_time`` over those
  replicates -- replicates still polymorphic at the end of the window
  are censored (counted in ``n_polymorphic``, excluded from the
  means). The observed mean fixation/loss/absorption times match the
  exact chain values within ~1 % (neutral N=50 p0=0.5: 136.3/138.1/
  137.2 observed vs 136.6 exact; under s=0.05: 90.4/82.96 observed vs
  90.2/82.7 exact).

- ``result.theoretical_heterozygosity()`` -- for neutral drift without
  selection or mutation, returns ``[H_0, H_1, ..., H_generations]``
  where ``H_t = H_0 * (1 - 1/(2N))^t`` (cumulative product for
  time-varying N). Returns empty list when selection or mutation is
  active.

- ``result.theoretical_frequency()`` -- when selection is active and
  mutation is off, returns the deterministic frequency trajectory
  under selection (haploid closed-form or diploid iterative). Returns
  empty list for neutral or mutation-active simulations.

- Enhanced ``result.describe()`` -- includes expected heterozygosity
  (neutral drift), fixation proportions, and mean fixation times when
  available.

- Enhanced ``result.summarize()`` -- includes
  ``expected_heterozygosity_final``, ``expected_heterozygosity_trajectory``
  (neutral drift), ``expected_frequency_final``,
  ``expected_frequency_trajectory`` (selection), and a ``fixation`` dict
  with full fixation analysis.

- ``result.allele_frequency_spectrum(generation=None, bins=10)`` --
  returns the distribution of allele A frequencies across replicates:
  ``{"generation", "bin_edges", "counts", "n_observations"}``. Defaults
  to the final generation (from ``final_frequencies``, always
  available); other generations require ``return_replicate_data=True``.
  Structured populations pool all demes.

- ``result.estimate_ne()`` -- effective population size estimated from
  the rate of heterozygosity decay: regress ``ln(H_t)`` on ``t``,
  ``slope = ln(1 - 1/(2N))`` gives ``Ne_hat = 1 / (2(1 - e^slope))``.
  Always available (needs only the heterozygosity column); returns
  ``{"error": ...}`` when fewer than 3 non-zero heterozygosity values
  exist (e.g. everything fixed). Preferred over the variance method.
  Verified to recover the known census N within ~20 % (N=50: 51.4 with
  1000 replicates; N=20: 20.0). Under the hood this delegates to the
  module-level ``estimate_ne_from_heterozygosity(H_values)``, which is
  also what the CLI ``ne`` command uses on exported CSVs.

```python
estimate_ne_from_heterozygosity(
    heterozygosity: Sequence[float],
) -> dict
```

```python
effective_size_harmonic_mean(
    population_size_series: Sequence[int],
) -> float
```

Effective population size of a time-varying-N population: the
*harmonic mean* of the census sizes, ``Ne = k / sum(1/N_t)``. Drift
removes ``1/(2N_t)`` of heterozygosity per generation, so
``H_k/H_0 = prod(1 - 1/(2N_t)) ~ exp(-k/(2Ne))``.

- The classic bottleneck result: one severe generation dominates --
  ``[1000, 10, 1000]`` gives ``Ne = 29.4`` (arithmetic mean 670), and
  a 10-generation bottleneck of N=10 inside a 1000-population window
  gives ``Ne = 168.8`` while the census is 1000.
- Harmonic <= arithmetic, with equality only for a constant series
  (AM-GM).
- Verified against the heterozygosity-decay estimator: a ``1000<->200``
  oscillating series (whose log-H decay is effectively linear)
  recovers ``Ne_har = 335.5`` to within ~1 %; a severe bottleneck
  biases the regression downward (the log-H curve bends), so the
  estimator is used qualitatively there (it stays within ~40 % of
  ``Ne_har`` and far below the census).
- Raises ``ValueError`` for an empty series or any N_t < 1 / non-int.

- ``result.estimate_ne_variance()`` -- the classical variance method  (Nei & Tajima 1981): per generation, ``Ne_hat = mean(p(1-p)) /
  (2 Var(Δp))`` across replicates. Requires
  ``return_replicate_data=True`` and at least 2 replicates. NOTE: this
  estimator is biased upward as drift accumulates (N=50 measured ~81
  uncorrected, ~66 corrected), so prefer ``estimate_ne()`` for a
  quantitative answer; this method is provided for teaching the
  classical estimator. Structured populations pool demes per replicate.

- ``result.to_dict()`` / ``result.to_csv(path, include_replicate_data=False)``
  / ``result.to_json(path=None)`` -- export the result. ``to_csv`` writes
  the main table; with ``include_replicate_data=True`` it also writes
  ``<stem>_replicates.csv``. ``to_json`` returns (and optionally writes)
  a JSON document with everything, including WF parameters.

## Kimura fixation probability

```python
kimura_fixation_probability(
    starting_frequency: float,
    selection_coefficient: float,
    population_size: int,
    dominance: float | None = None,
) -> float
```

Kimura's (1962) probability that allele A fixes under selection and
drift, given its initial frequency p0, selection coefficient s, and
population size N.

- ``dominance=None`` (haploid selection over the 2N allele copies):
  closed form ``P_fix = (1 - e^(-4Ns·p0)) / (1 - e^(-4Ns))``.
- ``dominance=h`` (diploid, fitnesses AA: 1+s, Aa: 1+hs, aa: 1):
  diffusion approximation evaluated numerically,
  ``P_fix(p0) = ∫₀^p0 G(x)dx / ∫₀^1 G(x)dx`` with
  ``G(x) = exp(-4Ns(h·x + (1-2h)·x²/2))``. Verified against simulation
  within ~0.01 for weak-to-moderate selection.
- ``s=0`` returns ``p0`` (neutral); very strong selection saturates at
  1.0 (positive) or 0.0 (negative).
- Raises ``ValueError`` for invalid parameters (N <= 0, p0 outside
  [0, 1], s <= -1, h outside [0, 2]).
- NOTE: for ``dominance > 1`` (overdominance/underdominance) the
  diffusion integral is known to be inaccurate (observed error up to
  ~0.25 for recessive-equivalent regimes); use simulation
  (``fixation_analysis()``) instead.

Useful for teaching the classic "selection vs drift" comparison: run a
simulation, compare ``fixation_analysis()["prop_fixed_A"]`` against the
Kimura prediction, then try other values of s.

```python
expected_fixation_time(
    starting_frequency: float,
    population_size: int,
) -> float
```

Kimura & Ohta's (1969) expected time to fixation of a *neutral* allele,
given that it fixes: ``t_bar = -4N·(1-p0)·ln(1-p0) / p0`` generations.

- ``p0 = 1/(2N)`` (a single new mutation) gives ``t_bar ≈ 4N``.
- ``p0 = 0.5`` gives ``t_bar = 4N·ln(2) ≈ 2.77N``.
- ``p0 = 1`` returns 0 (already fixed); ``p0 = 0`` raises (never fixes).
- Raises ``ValueError`` for N <= 0 or p0 outside (0, 1].

Verified against simulation: the observed mean fixation time matches the
prediction within 15 % when the simulation window is long enough that
all replicates fix (a truncated window biases the mean downward, since
late-fixing replicates are excluded). The CLI ``kimura --time`` prints
both ``P_fix`` and ``t_fix`` for the neutral comparison.

```python
wright_stationary_distribution(
    points: Sequence[float],
    mutation_rate: float,
    population_size: int,
) -> list[float]
```

Wright's (1931) stationary distribution of allele frequency under
mutation-drift balance: with per-copy symmetric mutation rate u in a
diploid population of size N, the equilibrium density is
``Beta(4Nu, 4Nu)``: ``φ(p) = C·p^(4Nu-1)·(1-p)^(4Nu-1)``.

- ``4Nu > 1``: single central hump (polymorphism maintained).
- ``4Nu < 1``: density unbounded at the boundaries (most populations
  fixed) -- returns ``math.inf`` at 0 and 1.
- Raises ``ValueError`` if ``mutation_rate <= 0`` or
  ``population_size <= 0``.

Verified against a long neutral simulation (N=50, u=0.02, 2000
replicates, 1000 generations): observed allele-frequency spectrum
matches the Beta(4,4) density's central mass within ~0.1.

```python
wright_fisher_stationary_vector(
    population_size: int,
    mutation_rate: float,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> list[float]
```

The *exact* stationary distribution of the Wright-Fisher chain with
mutation: the Perron-Frobenius eigenvector (``πQ = π``, eigenvalue 1,
normalized to sum to 1) of ``wright_fisher_transition_matrix``,
returned as probabilities over A-copy counts ``i = 0..2N``.

- Requires ``mutation_rate`` in (0, 1); with no mutation the chain is
  absorbing and has no unique stationary distribution.
- Selection (``s``, ``dominance``) is carried through the same
  transition matrix, so the vector shows how selection bends the
  mutation-drift balance (the mode shifts toward more A copies under
  positive s).
- This is the exact finite-population counterpart of Wright's
  ``Beta(4Nu, 4Nu)`` density: with N=50, u=0.02 the two agree to
  within ~0.007 in central mass, and the vector's central mass
  (0.7547) matches a 2000-replicate, 1000-generation simulation's
  (0.7510) at least as closely as the Beta density does. Because the
  vector's shape is determined entirely by the mutation convolution
  in the transition matrix, it is the first behavioral verification
  of that convolution.
- Raises ``ValueError`` for invalid parameters (including
  ``mutation_rate`` of 0).

```python
theoretical_fst(
    population_size: int,
    migration_rate: float,
    mutation_rate: float = 0.0,
) -> float
```

Wright's (1931) island-model equilibrium Fst:
``Fst = 1 / (1 + 4N·(m + u))``.

- Assumes a large (infinite) number of demes; with few demes the
  observed Fst is lower because the finite metapopulation itself drifts
  toward fixation.
- Returns 1.0 when both rates are 0 (no mixing at all).
- Raises ``ValueError`` for ``N <= 0``, ``m`` outside [0, 1], or ``u``
  outside [0, 1).

Verified against simulation: with 30+ demes the simulated Fst converges
to within ~0.01 of the formula (N=100, m=0.05, u=0.001: sim 0.042 vs
theory 0.047); at 10 demes the simulation sits below the theory because
the deme count is finite.

```python
expected_fst_after_split(
    population_size: int,
    generations: int,
    starting_frequency: float = 0.5,
) -> float
```

Expected Fst between two daughter populations isolated since a split,
*exact* for the Wright-Fisher chain. Both demes start at the same p0
and exchange no migrants, so their allele frequencies are independent
chains and the exact expectation of the engine's Nei-style per-
replicate Fst (``1 - Hs/Ht``, 0 where ``Ht = 0``) is

``E[Fst(t)] = sum_{i,j} pi_t(i) pi_t(j) fst(i, j)``

with ``pi_t`` the single-deme transition matrix from ``round(2N·p0)``
copies of A.

- Verified against a 2-deme, 2000-replicate simulation (N=100, p0=0.5):
  within 0.01 at every generation (t=200: 0.350 observed vs 0.347
  exact).
- Rises monotonically from 0, but does NOT approach 1: both demes fix
  independently, so ``Fst(t) -> 2·p0·(1-p0)`` -- the probability of
  divergent fixation (0.5 at p0=0.5; 0.494 exact at t=800).
- The textbook ``1 - (1-1/(2N))^t ~ 1 - e^{-t/(2N)}`` is the
  *variance-based* estimator (it keeps the total variance, which does
  not decay) and runs well above this Nei-style expectation (0.63 vs
  0.35 at t=200, N=100) -- a useful in-class caveat about estimator
  definitions.
- Raises ``ValueError`` for N < 1, t < 0, or p0 outside [0, 1].

```python
wright_fisher_sweep(
    parameter: str,
    values: Sequence[float],
    **fixed_params,
) -> list[dict[str, Any]]
```

Run ``simulate_wright_fisher`` once per value of any of its parameters
(e.g. ``selection_coefficient``, ``migration_rate``,
``population_size``) with the remaining parameters fixed. Each returned
dict holds ``parameter``, ``value``, ``final_mean_frequency``,
``final_heterozygosity``, ``prop_fixed_A``, ``prop_fixed_a``, and
``final_fst`` (when the run was structured). A shared ``seed`` in
``**fixed_params`` makes the sweep reproducible; sweeping
``starting_frequency`` is rejected (it is already varied by the sweep).

```python
simulate_two_locus_wright_fisher(
    population_size: int,
    generations: int,
    recombination_rate: float,
    starting_frequencies: Sequence[float] = (0.25, 0.25, 0.25, 0.25),
    mutation_rate: float = 0.0,
    replicate_runs: int = 1,
    seed: int | None = None,
    return_replicate_data: bool = False,
) -> TwoLocusResult
```

Haploid two-locus Wright-Fisher simulation with recombination and
optional symmetric mutation: each of ``N`` individuals carries two
loci (A: A/a, B: B/b), tracked as the frequencies of the four
haplotypes ``(f_AB, f_Ab, f_aB, f_ab)``. Each generation recombines
at rate ``r`` (the coupling gametes lose ``r·D``, the repulsion ones
gain it, where ``D = f_AB·f_ab - f_Ab·f_aB`` is the linkage
disequilibrium), samples ``N`` gametes multinomially (genetic
drift), and -- when ``mutation_rate`` u > 0 -- mutates each locus
symmetrically at rate u per copy (``AB`` becomes ``Ab``/``aB`` with
probability ``u(1-u)`` each and ``ab`` with ``u²``, and vice versa).

- Columns: ``generation``, ``mean_D``, ``mean_r2``, ``mean_freq_A``,
  ``mean_freq_B``, ``sd_D`` (across replicates when ``replicate_runs >
  1``). ``result.ld_analysis()`` summarizes D at generation 0 and the
  final generation, the decay factor ``d_final/d_initial``, and the
  across-replicate ``sd_D_final``.
- ``theoretical_ld_decay(D0, r, t, N=None, u=0.0)`` gives the
  expectation ``D0·(1-r)^t·(1-2u)^(2t)·(1-1/N)^t`` (recombination
  factor, the two mutating loci each contributing ``(1-2u)``, and the
  haploid drift factor; ``N=None`` omits drift).
- Verified against simulation: single-replicate decay with N=100000
  follows ``(1-r)^t`` within ~3 %; 3000-replicate means with N=100,
  r=0.1, t=30 match ``E[D_t]`` within ~3 % (0.00808 vs 0.00784), and
  the repulsion start ``(0, 0.5, 0.5, 0)`` decays identically in
  negative D (0.00778 vs 0.00784). r=0 leaves D to drift alone
  (``D_30 = 0.189`` vs ``0.25·0.99^30 = 0.185``); r=0.5 destroys LD
  within a few generations. With u=0.02, r=0.1, t=15 the expected
  ``0.0130`` matches the 3000-replicate mean (``0.0128``, 1 %).
  Mean per-locus frequencies are conserved in expectation without
  mutation and drift to 0.5 with it (from 0.8: 0.500 at t=100).
- No selection across loci -- the decay theory is neutral.
- Raises ``ValueError`` (``ModelBuildError``) for N < 1, generations
  outside [1, max], ``recombination_rate`` outside [0, 0.5],
  ``mutation_rate`` outside [0, 1], fewer than one replicate, or
  haplotype frequencies that are not numbers in [0, 1] summing to 1.

```python
wright_fisher_transition_matrix(
    population_size: int,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> numpy.ndarray
```

The exact one-generation transition matrix of the Wright-Fisher chain:``Q[i, j]`` is the probability that a population with ``i`` copies of A
(out of ``2N``) has ``j`` copies one generation later. Applies the same
steps as ``simulate_wright_fisher`` -- selection (haploid or diploid
with dominance), binomial reproduction over ``2N`` copies, then
per-copy mutation -- so ``Q`` is the exact expectation of the
simulation's stochastic step. With ``mutation_rate = 0`` states 0 and
``2N`` are absorbing; with mutation the chain is ergodic. Verified:
rows sum to 1, the neutral chain is mean-preserving with the exact
binomial variance ``i(2N-i)/(2N)``, and matrix powers match the
simulated frequency distribution at generation t (N=20, t=50, 4000
replicates: fixation proportion 0.1430 vs 0.1374, mean 0.3075 vs
0.3000). Panmictic only -- no demes/migration.

```python
wright_fisher_expected_fixation_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float
```

Expected generations to fixation, *exact* for the discrete
Wright-Fisher chain (no diffusion approximation): solves the
absorption system of ``wright_fisher_transition_matrix`` and returns
``E[T | fixation]``. The Kimura & Ohta 1969 closed form
(``expected_fixation_time``) is the continuous approximation of this
quantity -- the two agree within ~1-2 % and converge as N grows
(N=100, p0=0.5: 275.0 exact vs 277.3 closed form; new mutation
1/(2N): 396.5 exact vs 4N = 400). Works under selection of any
strength: with genic s=0.05, N=50, p0=0.2 the exact value 90.2
matches simulation (89.5, 3000 replicates) within 1 %. Raises for
``starting_frequency`` of 0 (never fixes); returns 0.0 when already
fixed. Takes no mutation parameter -- with mutation the chain has no
absorbing all-A state.

```python
wright_fisher_fixation_probability(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float
```

The probability that allele A fixes, *exact* for the discrete
Wright-Fisher chain: solves the absorption system of
``wright_fisher_transition_matrix`` for P(hit all-A before all-a).
``kimura_fixation_probability`` is the diffusion approximation of this
quantity. Verified:

- Neutrality: exactly ``starting_frequency`` (the martingale
  property, reproduced by the chain to 1e-9).
- Genic selection: matches Kimura's closed form within ~0.003
  (N=50, s=0.01-0.05).
- Overdominance (h=2, s=0.05): 0.9747 exact vs 0.9757 simulation
  (4000 replicates).
- Underdominance (h=2, s=-0.2, p0=0.5): 0.0136 exact vs 0.0155
  simulation, while Kimura's diffusion approximation says 0.0339 --
  the documented `dominance > 1` failure this function resolves; the
  test pins the exact value within 0.01 of simulation *and* asserts
  Kimura's value is measurably wrong there.

```python
expected_loss_time(
    starting_frequency: float,
    population_size: int,
) -> float

wright_fisher_expected_loss_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float

wright_fisher_expected_absorption_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float
```

The loss/absorption counterparts of the fixation times, completing
Kimura & Ohta's (1969) trio:

- ``expected_loss_time`` -- diffusion closed form for a *neutral*
  allele, given that it is lost: ``t_bar = -4N·p0·ln(p0)/(1-p0)``,
  the exact mirror of ``expected_fixation_time``
  (``t_loss(p) = t_fix(1-p)``). ``p0 = 0`` gives 0 (already lost);
  ``p0 = 1`` gives the limit 4N (a nearly fixed allele destined to be
  lost must drift all the way down).
- ``wright_fisher_expected_loss_time`` -- exact chain value
  ``E[T | loss]``, the mirror of
  ``wright_fisher_expected_fixation_time`` (chain symmetry holds to
  1e-9); closed form within ~1 % (N=100, p0=0.1: 100.6 exact vs 102.3)
  and simulation within 1.5 % (N=50, p0=0.2: 78.8 exact vs 79.9 sim).
  Boundary convention: the exact chain treats the fixed state as
  absorbing and raises at ``p0 = 1``, where the closed form returns
  the 4N limit.
- ``wright_fisher_expected_absorption_time`` -- unconditional mean
  time to hit *either* boundary, ``h = (I - Q_t)^{-1} 1``; the
  diffusion closed form is ``-4N(p0 ln p0 + (1-p0) ln(1-p0))``
  (both give 4N ln(2) at p0 = 0.5).

The three exact quantities satisfy the Markov-property identity
``absorption = fixation·P_fix + loss·(1 - P_fix)``, checked to 1e-9
in the test suite for neutral and selected chains.

## Enzyme kinetics (Michaelis-Menten)

```python
simulate_michaelis_menten(
    km: float, vmax: float, s0: float,
    start: float = 0.0, end: float = 10.0, points: int = 51,
) -> SimulationResult
```

Rate law: `dS/dt = -Vmax * S / (Km + S)`.

- `km` -- Michaelis constant, must be positive. Flagged outside
  `[KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM]` (1e-7 to 1e3 mM).
- `vmax` -- maximum reaction rate, must be positive.
- `s0` -- initial substrate concentration, zero allowed (inert but valid).

Raises `ModelBuildError` for invalid parameters, `SimulationError` if
integration fails after a valid model is built.

Verified against the exact implicit solution
`Km*ln(S0/S) + (S0-S) = Vmax*t` in `tests/test_kinetics_correctness.py`.

## Epidemiology (SIR)

```python
simulate_sir(
    beta: float, gamma: float, s0: float, i0: float,
    r0_recovered: float = 0.0,
    start: float = 0.0, end: float = 100.0, points: int = 101,
) -> SimulationResult
```

- `beta` -- transmission rate, must be positive.
- `gamma` -- recovery rate, must be positive. (Emitted internally as
  `gamma_rate` in generated antimony source -- see
  `docs/adr/0004-gamma-reserved-keyword.md`. The Python argument is still
  `gamma`.)
- `s0`, `i0`, `r0_recovered` -- initial compartment sizes, zero allowed.
  Zero `i0` is flagged (valid but inert -- nothing happens).

Verified against the SIR conserved quantity
`S + I - (N/R0)*ln(S) = const` and the final-size equation in
`tests/test_epidemiology_correctness.py`.

## Epidemiology (SEIR)

```python
simulate_seir(
    beta: float, sigma: float, gamma: float, s0: float,
    e0: float, i0: float, r0_recovered: float = 0.0,
    start: float = 0.0, end: float = 100.0, points: int = 101,
) -> SimulationResult
```

Same as SIR, plus:
- `sigma` -- progression rate from exposed to infectious (incubation).
- `e0` -- initial exposed (incubating, not yet infectious) count.

## PCR amplification

```python
simulate_pcr(
    n0: float, efficiency: float, cycles: int,
    plateau_capacity: Optional[float] = None,
) -> SimulationResult
```

**Not** built through antimony/roadrunner -- PCR is a discrete-cycle
recurrence, not a continuous-time process. See
`docs/adr/0002-pcr-not-modeled-as-an-ode.md`.

- `n0` -- initial template copy number, must be positive.
- `efficiency` -- fraction of template copied per cycle, in `[0.0, 1.0]`.
  `1.0` is perfect doubling. Above `1.0` is a hard rejection (a template
  can't be copied more than once per cycle). Below `0.5`
  (`PCR_PLAUSIBLE_LOW_EFFICIENCY`) is flagged, not rejected -- a real but
  poor reaction.
- `cycles` -- must be a positive integer, capped at 60 (no real qPCR
  protocol runs longer).
- `plateau_capacity` -- if given, growth follows a discrete logistic
  recurrence approaching but never exceeding this ceiling (reagents/
  polymerase saturating). If omitted, growth is the exact closed form
  `N(c) = n0 * (1 + efficiency) ** c`, unbounded.

Result columns are `["cycle", "copies"]`, not `["time", ...]` -- there's no
continuous time axis for this domain.

Verified by exact-equality tests against the closed form (no tolerance
band, since there's no numerical integration to have error) in
`tests/test_pcr_correctness.py`.

## Monte Carlo pi estimation

```python
simulate_monte_carlo_pi(
    n_samples: int,
    seed: int | None = None,
) -> SimulationResult
```

**Not** built through antimony/roadrunner -- a direct stochastic sampling
domain, same category as PCR. See ``docs/adr/0002-pcr-not-modeled-as-an-ode.md``
and ``docs/adr/0005-rng-convention.md``.

Draws ``n_samples`` uniform random points in ``[-1, 1] x [-1, 1]`` and
estimates pi as ``4 * (fraction inside the unit circle)``.

- ``n_samples`` -- must be a positive integer. Below 100
  (``MC_PLAUSIBLE_MIN_SAMPLES``) is flagged -- the standard error is large
  but the simulation is still valid.
- ``seed`` -- optional RNG seed per ADR 0005. Omit for nondeterministic
  output.

Result columns are ``["n", "estimate", "se"]`` -- one row per convergence
checkpoint (log-spaced sample counts), not one row per sample.

Verified in ``tests/test_monte_carlo_correctness.py``:
- Error shrinks at the theoretical ``1/sqrt(N)`` rate (Target A).
- Reported standard error is statistically consistent with empirical
  variation across repeated runs (Target B).
- Fixed seed produces bit-identical output; different seeds diverge.

## Molecular dynamics (Lennard-Jones cluster)

```python
validate_md_params(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
) -> ParameterValidation

simulate_molecular_dynamics(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
    seed: int | None = None,
) -> SimulationResult
```

**Not** built through antimony/roadrunner — velocity Verlet is a direct
Python integration, not an ODE (see ``docs/adr/0006-md-direct-python-not-roadrunner.md``).

Simulates an NVE Lennard-Jones cluster with reduced units
(``epsilon = sigma = m = 1``). Particles are placed on an fcc lattice at
the requested density, with Maxwell-Boltzmann velocity initialization
(ADR 0005 RNG, COM velocity subtracted).

- ``n_particles`` — must be an integer >= 2. Below 10
  (``MD_PLAUSIBLE_MIN_PARTICLES``) is flagged — too small for
  meaningful cluster dynamics. If not an exact fcc count
  (``4·k³``) it is rounded *up* and flagged.
- ``temperature`` — initialization temperature in reduced units.
  Must be > 0. Outside ``[MD_PLAUSIBLE_TEMPERATURE_LOW = 0.1,
  MD_PLAUSIBLE_TEMPERATURE_HIGH = 0.8]`` is flagged. The high bound
  is measured: at 0.9 the shipped LJ108 configuration loses particles.
  The flag message explicitly says "initialization temperature" because
  T*_init and T*_equil differ (potential energy converts to kinetic).
- ``timestep`` — integration step ``Δt``, must be > 0. Above
  ``MD_PLAUSIBLE_MAX_TIMESTEP`` (0.01) is flagged — the r⁻¹² repulsive
  wall is under-resolved.
- ``n_steps`` — must be a positive integer.
- ``density`` — number density ``ρ = N/V``, used to set fcc lattice
  spacing. Must be > 0.
- ``seed`` — optional RNG seed per ADR 0005 for velocity initialization.

Result columns: ``["step", "time", "total_energy", "kinetic_energy",
"potential_energy", "total_momentum_magnitude"]``, one row per step from
0 to ``n_steps`` inclusive.

The engine includes a divergence guard: if the trajectory explodes
(e.g. from an under-resolved timestep), the run stops early and the
flag records the step of divergence.

```python
lennard_jones_force(
    r_vec: np.ndarray,
) -> np.ndarray
```

Lennard-Jones force vector on particle i from separation vector
``r_vec = r_i - r_j``, shape ``(3,)``. Returned force shape ``(3,)``.
The force on particle j is the negative (Newton's third law).

```python
lj_cluster_positions(
    n_particles: int,
) -> np.ndarray
```

Known global-minimum geometry for small Lennard-Jones clusters, shape
``(n_particles, 3)``. Supports exactly ``n`` in ``{2, 3, 4, 13}``.
Reduced units. Raises ``ModelBuildError`` for unsupported sizes.

- ``n=2`` — two particles at LJ equilibrium separation ``r_min = 2^(1/6)``.
- ``n=3`` — equilateral triangle, side ``r_min``.
- ``n=4`` — regular tetrahedron, edge ``r_min``.
- ``n=13`` — centered Mackay icosahedron. The scale factor is found by
  1-D golden-section search over the LJ potential, not downloaded
  from any URL — no network dependency. Optimal scale ~0.568756, total
  energy −44.326801 (Hoare & Pal 1971, via the Cambridge Cluster
  Database).

Verified in ``tests/test_molecular_dynamics_correctness.py``:
- Energy conservation: ``|ΔE|/E0 < 1e-3``, halved timestep reduces
  error by factor 3-5 (Target A — velocity Verlet, O(dt²)).
- Momentum conservation: zero to machine precision at every step
  (Target B).
- Closed-form force table: zero at r_min, attractive at r > r_min,
  repulsive at r < r_min (Target C).
- Fixed-seed reproducibility and different-seed divergence (Target D).
- Cluster global-minimum energies: N=2,3,4 exact (-1, -3, -6);
  N=13 vs published -44.326801 within 1e-6 (Target E).

## Population genetics (Wright-Fisher neutral drift)

```python
validate_wright_fisher_params(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
    population_size_series: Sequence[int] | None = None,
    n_demes: int = 1,
    migration_rate: float = 0.0,
    migration_model: str = "island",
) -> ParameterValidation

simulate_wright_fisher(
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
) -> SimulationResult
```

**Not** built through antimony/roadrunner -- discrete-generation stochastic
process (binomial sampling each generation). Same category as PCR and Monte
Carlo. See ``docs/adr/0002-pcr-not-modeled-as-an-ode.md`` and
``docs/adr/0005-rng-convention.md``.

Models evolution at a single biallelic locus in a diploid Wright-Fisher
population, with optional symmetric mutation and natural selection.
Each generation follows three steps:
1. Selection — fitness differences change the expected frequency.
2. Reproduction — the next generation's ``2N`` allele copies are drawn
   ``Binomial(2N, p_adj)`` from the post-selection frequency.
3. Mutation — each copy mutates to the other allele with probability
   ``mutation_rate``.

- ``population_size`` -- diploid census size N, must be a positive integer.
  Below 10 (``WF_PLAUSIBLE_MIN_POPULATION_SIZE``) is flagged -- drift is
  extremely rapid.
- ``starting_frequency`` -- initial frequency of allele A, in ``[0, 1]``.
  Exactly 0 or 1 is flagged (degenerate -- allele already lost or fixed).
- ``generations`` -- number of discrete generations, must be a positive
  integer. Above 10000 (``WF_PLAUSIBLE_MAX_GENERATIONS``) is flagged --
  simulation may be slow.
- ``replicate_runs`` -- number of independent replicate populations, must
  be a positive integer. Below 10 (``WF_PLAUSIBLE_MIN_REPLICATE_RUNS``) is
  flagged -- standard error of mean heterozygosity will be large.
- ``mutation_rate`` -- per-generation symmetric mutation probability per
  allele copy (default 0 = neutral drift). Must be in ``[0, 1]``.
  Above ``WF_PLAUSIBLE_MAX_MUTATION_RATE (0.01)`` is flagged --
  biologically implausible, mutation will dominate drift.
- ``selection_coefficient`` -- selective advantage of allele A (s),
  default 0 = neutral. Must be > -1. ``|s| > 0.5`` is flagged --
  implausibly strong selection for most teaching scenarios.
- ``dominance`` -- dominance coefficient (h) for diploid selection;
  ``None`` (default) = haploid selection ``p' = p(1+s)/(1+ps)``;
  in ``[0, 2]`` for diploid selection with fitnesses ``AA: 1+s``,
  ``Aa: 1+hs``, ``aa: 1``. ``h > 1`` is valid and flagged: with
  ``s > 0`` it is overdominance (heterozygote advantage, balancing
  selection -- equilibrium ``p* = h/(2h-1)``), with ``s < 0`` it is
  underdominance (heterozygote disadvantage -- populations fix).
- ``seed`` -- optional RNG seed per ADR 0005. Omit for nondeterministic
  output.
- ``return_replicate_data`` -- if ``True``, store per-replicate allele
  frequencies in ``result.replicate_data`` (columns: generation,
  rep_0, rep_1, ..., rep_{replicate_runs-1}). Off by default --
  storage scales as O(generations x replicate_runs).
- ``population_size_series`` -- time-varying N, a sequence of length
  ``generations + 1`` where each entry is the census size N for that
  generation. Must contain only positive integers. Overrides the
  constant ``population_size`` when given. Use for bottlenecks, founder
  events, or population expansion.
- ``n_demes`` -- number of subpopulations (demes) per replicate.
  ``1`` (default) = standard panmictic population. ``> 1`` activates
  a structured population: demes drift partially independently, and
  ``migration_rate`` controls the exchange of alleles between them.
- ``migration_rate`` -- fraction of each deme's allele pool replaced
  by migrants each generation, in ``[0, 1]``. ``0`` (default) = no
  migration, demes drift independently. Ignored when ``n_demes = 1``.
- ``migration_model`` -- how migrants are exchanged between demes
  (default ``"island"``): the island model pools all demes and replaces
  a fraction ``m`` of each deme with alleles drawn from the global pool.
  ``"stepping-stone"`` (requires ``n_demes >= 3``) lays the demes on a
  ring: each deme exchanges ``m/2`` with each of its two neighbours,
  so migration is local and differentiation (Fst) grows faster than
  under the island model with the same ``m``. Ignored when
  ``n_demes = 1``.
- ``verbose`` -- if ``True``, print progress every 10 % of generations
  (useful for large simulations with thousands of generations).

Result columns for ``n_demes = 1``: ``["generation", "mean_frequency",
"heterozygosity", "mean_frequency_se", "heterozygosity_se",
"n_A_fixed", "n_a_fixed"]``.

Result columns for ``n_demes > 1``: the same plus ``"fst"`` and
``"fst_se"``. Fst (Wright's fixation index) measures population
differentiation: ``Fst = 1 - Hs/Ht`` where Hs is mean within-deme
heterozygosity and Ht is total metapopulation heterozygosity.

One row per generation from 0 to ``generations`` inclusive. Stats are
aggregated across all replicate populations: mean frequency, mean
heterozygosity, their standard errors (``std(x, ddof=1)/sqrt(reps)``),
and counts of populations fixed for allele A / allele a.

Verified in ``tests/test_popgen_correctness.py``:
- Heterozygosity decays at the exact rate ``(1 - 1/(2N))^t`` (Target A,
  within 0.02 absolute).
- Fixation probability equals the starting frequency p0, per Kimura 1962
  (Target B, within 0.04).
- Fixed-seed reproducibility and seed-dependent divergence (Targets C-D).
- Mutation-drift equilibrium: heterozygosity approaches the predicted
  stationary value ``H_eq = 4Nμ/(8Nμ+1)`` (Target F, within 0.03).
- Selection-drift balance: fixation probability under haploid selection
  follows Kimura's formula ``P_fix = (1-e^{-4Nsp_0})/(1-e^{-4Ns})``
  (Target G, within 0.06).
- Overdominance (``h=2``, ``s=0.2``): the deterministic equilibrium
  ``p* = h/(2h-1) = 2/3`` is approached and heterozygosity is
  maintained (no fixation); verified for ``h=1.5`` (``p* = 0.75``) at
  large N. Underdominance (``h>1``, ``s<0``) drives every replicate to
  fixation. NOTE: with weak overdominance (small ``(h-1)·s``) finite
  populations still fix at the boundaries -- the equilibrium is only
  observed when ``4N·s·(2h-1)`` is large.
- Stepping-stone vs island migration: with identical ``m``, Fst is
  higher under stepping-stone (local exchange) than island (global
  pool); the migration step conserves the mean allele frequency.
- ``estimate_ne()`` recovers the known census N within ~20 % (N=50:
  51.4 with 1000 replicates; N=20: 20.0); ``estimate_ne_variance()`` is
  biased upward as expected (N=50: ~81 uncorrected).
  ``effective_size_harmonic_mean`` gives the textbook Ne of a
  time-varying-N trajectory (harmonic mean of the series) and matches
  the heterozygosity-decay estimator on oscillating series to ~1 %.
- ``wright_stationary_distribution`` matches a long neutral simulation
  (N=50, u=0.02, 2000 replicates): observed vs theoretical central
  mass within ~0.1; the exact chain stationary distribution
  (``wright_fisher_stationary_vector``) matches the same simulation
  within ~0.004 (and the Beta density within ~0.007) and doubles as
  the behavioral check for the transition matrix's mutation
  convolution.
- ``theoretical_fst`` (Wright's island-model equilibrium
  ``1/(1+4N(m+u))``) is matched by simulation to within ~0.01 once the
  number of demes is 30+; with fewer demes the simulated Fst lies
  below the infinite-island prediction.
- ``expected_fst_after_split`` gives the exact Fst trajectory of two
  isolated daughter populations (matching a 2000-replicate simulation
  within 0.01) and its counterintuitive limit ``2·p0·(1-p0)``
  (divergent-fixation probability), not 1.
- Two-locus linkage disequilibrium decays as ``E[D_t] = D_0·(1-r)^t·
  (1-2u)^(2t)·(1-1/N)^t`` (recombination plus mutation plus haploid
  drift): a 3000-replicate N=100 run matches within ~3 % (D_30
  0.00808 vs 0.00784; with u=0.02: D_15 0.0128 vs 0.0130), and a
  single N=100000 population follows the recombination-only decay
  within ~3 %.
- ADR 0005 RNG compliance checked automatically by
  ``scripts/check_rng_convention.py`` and
  ``tests/test_rng_convention.py``.

### Scenario presets for teaching

```python
list_scenarios() -> list[str]

wright_fisher_scenario(
    name: str, seed: int | None = None,
    return_replicate_data: bool = False,
    **overrides,
) -> SimulationResult
```

Run a named teaching scenario without specifying every parameter manually.
Available scenarios (``list_scenarios()`` returns the current list):

- ``neutral-drift`` -- moderate N, neutral (default params)
- ``rapid-drift`` -- N=10, drift is fast and visible
- ``mutation-drift`` -- mutation-drift balance, N=50, μ=0.02
- ``weak-selection`` -- s=0.03, haploid, slight bias
- ``strong-selection`` -- s=0.2, haploid, beneficial allele fixes rapidly
- ``purifying-selection`` -- s=-0.1, haploid, deleterious allele rarely fixes
- ``bottleneck`` -- N=100 drops to N=5 at generation 50 for 10 gens,
  then recovers. Uses ``population_size_series`` internally.
- ``island-model`` -- 10 demes, low migration (m=0.01). Fst tracks
  differentiation.
- ``structured-neutral`` -- 10 demes, no migration. Demes drift
  independently; Fst rises to near 1.
- ``founder-effect`` -- N=20, rare allele (p0=0.1): drift decides
  whether the rare allele survives.
- ``population-expansion`` -- N=10 grows linearly to N=1000 over 200
  generations (time-varying N): heterozygosity loss slows as N grows.
- ``balancing-selection`` -- overdominance (h=2, s=0.2): both alleles
  are maintained at ``p* = 2/3``.
- ``stepping-stone`` -- 10 demes on a ring with local migration
  (m=0.01): Fst rises faster than the island model.

Any ``**overrides`` are merged into the scenario's parameter dict, so
callers can tweak e.g. ``generations=100`` without modifying the preset.

```python
# Quick comparison: neutral vs selection with one seed
neutral = wright_fisher_scenario("neutral-drift", seed=42)
selected = wright_fisher_scenario("strong-selection", seed=42)
```

## Stochastic kinetics (Gillespie SSA)

```python
simulate_gillespie_ssa(
    a0: int,
    k: float,
    end: float,
    seed: int | None = None,
) -> SimulationResult

validate_ssa_params(a0: int, k: float, end: float) -> ParameterValidation
```

**Not** built through antimony/roadrunner -- event-driven stochastic
simulation, same direct Python/numpy category as Monte Carlo and
Wright-Fisher (ADR 0005 RNG). See ``docs/adr/0009-gillespie-ssa.md``.

Exact Gillespie Direct Method for the single first-order decay reaction
$A \to B$ (propensity $k \cdot a$): each event draws the waiting time
$\tau = -\ln(u)/\alpha$ from the total propensity and decrements $a$.
Conservation $a + b = a_0$ holds on every row; the final row is snapped
to `end`. The count at time $t$ is Binomial$(a_0, e^{-kt})$, so
$E[a(t)] = a_0 e^{-kt}$ — the closed form used by the verification
tests (`tests/test_gillespie_ssa_correctness.py`).

- ``a0`` -- initial A molecules, positive integer. Below 30 molecules
  the trajectory is flagged (stochastic effects dominate).
- ``k`` -- per-molecule rate, finite $\ge 0$; $k = 0$ emits no events.
  Above $k = 10$ the trajectory is flagged (dense random walk).
- ``end`` -- simulation time, finite $> 0$; the final row is exactly
  `end`.
- ``seed`` -- optional ADR 0005 seed; fixed seed → bit-identical
  trajectory.

Result columns: ``time``, ``a``, ``b``.

## Command-line interface

The engine ships a small CLI, runnable as a module:

```bash
python -m Tellurium.cli scenarios
python -m Tellurium.cli wf --population-size 100 --generations 200 --seed 42
python -m Tellurium.cli wf --scenario bottleneck --out results.csv
python -m Tellurium.cli kimura --p0 0.3 --s 0.03 --population-size 50
python -m Tellurium.cli ne --file results.csv
python -m Tellurium.cli sweep --parameter selection_coefficient \
    --values 0,0.01,0.05 --seed 7
python -m Tellurium.cli ld --population-size 100 --generations 30 \
    --recombination-rate 0.1 --replicate-runs 3000 --seed 42
```

- ``scenarios`` -- list the available scenario presets with descriptions.
- ``wf`` -- run a Wright-Fisher simulation. Either give ``--scenario``
  (preset, overridable by any other option) or the core parameters
  ``--population-size`` and ``--generations``. Optional:
  ``--starting-frequency``, ``--replicate-runs``, ``--mutation-rate``,
  ``--selection-coefficient``, ``--dominance``, ``--n-demes``,
  ``--migration-rate``, ``--migration-model`` (``island`` or
  ``stepping-stone``), ``--seed``, ``--out FILE`` (CSV),
  ``--json FILE`` (full result incl. WF params), ``--replicate-data``,
  ``--verbose``, ``--quiet``. Prints ``result.describe()`` by default.
- ``kimura`` -- compute ``kimura_fixation_probability`` for a single
  ``--s`` or as a sweep over ``--s-start/--s-end/--s-steps`` (prints an
  ``s`` vs ``P_fix`` table). Add ``--exact`` (single ``--s``) to also
  print the exact fixation probability from the Wright-Fisher Markov
  chain (``wright_fisher_fixation_probability``), which stays
  reliable where the diffusion approximation breaks down
  (``--h > 1``). Add ``--time`` to also print the neutral expected
  fixation time (``expected_fixation_time``); with ``--exact`` and
  ``--time`` the exact expected fixation time under the given
  ``--s``/``--h`` is printed as well
  (``wright_fisher_expected_fixation_time``).
- ``ne`` -- estimate the effective population size from a CSV written
  by ``wf --out`` (needs a ``heterozygosity`` column); uses
  ``estimate_ne_from_heterozygosity``. Exit 1 if the column is missing
  or fewer than 3 usable values exist.
- ``sweep`` -- run ``simulate_wright_fisher`` once per value of
  ``--parameter`` (any WF parameter, e.g. ``selection_coefficient``,
  ``migration_rate``, ``population_size``) over the comma-separated
  ``--values``; fixed parameters are given with the ``wf`` options
  (``--population-size``, ``--starting-frequency``, ``--generations``,
  ``--replicate-runs``, ``--mutation-rate``, ``--selection-coefficient``,
  ``--dominance``, ``--n-demes``, ``--migration-rate``,
  ``--migration-model``, ``--seed``). Prints one row per value with
  final mean frequency, heterozygosity, proportions fixed A/a, and Fst
  (structured runs). Exit 2 if ``--values`` is not numbers, 1 on
  invalid parameters.
- ``ld`` -- run ``simulate_two_locus_wright_fisher`` and print the
  per-generation table (``mean_D``, ``mean_r2``, ``mean_freq_A``,
  ``mean_freq_B``) plus a final comparison of the observed mean D
  against ``theoretical_ld_decay`` (``(1-r)^t*(1-2u)^(2t)*(1-1/N)^t``).
  Options: ``--population-size`` (haploid, default 100), ``--generations``,
  ``--recombination-rate`` (default 0.1), ``--mutation-rate`` (default
  0), ``--starting-frequencies`` (four comma-separated haplotype
  frequencies, default ``0.5,0,0,0.5`` = full coupling, D0 = 0.25),
  ``--replicate-runs`` (default 50), ``--seed``, ``--out FILE``. Exit
  1 on invalid parameters.

Exit codes: 0 success, 1 invalid parameters/unknown scenario,
2 missing required arguments.

`make cli` prints this help from the repository root.

## Lower-level: raw SBML operations

These are what the `simulate_*` convenience functions call internally.
Use them directly if you need to build a model from raw antimony/SBML
rather than going through one of the parameterized domain functions.

```python
build_michaelis_menten_antimony(km, vmax, s0, model_name="michaelis_menten") -> str
build_sir_antimony(beta, gamma, s0, i0, r0_recovered=0.0, model_name="sir") -> str
build_seir_antimony(beta, sigma, gamma, s0, e0, i0, r0_recovered=0.0, model_name="seir") -> str

antimony_to_sbml(antimony_string: str, model_name: str | None = None) -> str
sbml_to_antimony(sbml_string: str) -> str
validate_sbml(sbml_string: str) -> list[str]   # returns error strings, empty if valid

simulate_sbml(sbml_string, start=0.0, end=10.0, points=51, model_name="model", validation=None) -> SimulationResult
steady_state(sbml_string: str) -> dict[str, float]
parameter_scan(sbml_string, parameter, values, start=0.0, end=10.0, points=51, selections=None) -> list[SimulationResult]
```

`antimony_to_sbml` / translation calls are protected by a module-level
`threading.Lock` internally, because libantimony keeps global module
state -- concurrent calls without the lock could return one caller's model
to another. This is transparent to callers; it's mentioned here because
it's the kind of thing that looks removable to someone optimizing for
speed and isn't.

## Validation functions

Each domain has a matching `validate_*_params` function with the same
argument names as its `simulate_*` counterpart, returning a
`ParameterValidation` without building or simulating anything. Useful for
validating user input before committing to a full simulation (e.g., in a
web form) without paying the cost of an actual integration.

```python
validate_michaelis_menten_params(km, vmax, s0) -> ParameterValidation
validate_sir_params(beta, gamma, s0, i0, r0_recovered=0.0) -> ParameterValidation
validate_seir_params(beta, sigma, gamma, s0, e0, i0, r0_recovered=0.0) -> ParameterValidation
validate_pcr_params(n0, efficiency, cycles) -> ParameterValidation
validate_monte_carlo_params(n_samples) -> ParameterValidation
validate_wright_fisher_params(population_size, starting_frequency, generations, replicate_runs=1, mutation_rate=0.0, selection_coefficient=0.0, dominance=None, population_size_series=None, n_demes=1, migration_rate=0.0, migration_model="island") -> ParameterValidation
validate_md_params(n_particles, temperature, timestep, n_steps, density=0.85) -> ParameterValidation
validate_ssa_params(a0, k, end) -> ParameterValidation
```

## Molecular Dynamics (Lennard-Jones, Velocity Verlet)

```python
simulate_molecular_dynamics(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
    seed: int | None = None,
) -> SimulationResult

validate_md_params(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
) -> ParameterValidation

lj_cluster_positions(n_particles: int) -> np.ndarray  # known global-minimum geometries
```

**Not** built through antimony/roadrunner — MD's correctness depends on
energy conservation from a symplectic, fixed-step integrator; a general
adaptive-step solver trades energy conservation for local error control,
which is the wrong property. See ADR 0006 for the rationale.

Reduced units throughout: $\varepsilon = \sigma = m = 1$, $k_B = 1$.

- `n_particles`: requested particle count (rounded up to the next
  fcc-compatible count if necessary; must be $\ge 2$).
- `temperature`: **initialization temperature** in reduced units (must be $> 0$).
  This is the temperature of the Maxwell–Boltzmann velocity distribution
  at $t=0$, NOT the equilibrated temperature — the fcc lattice stores
  excess potential energy that converts to kinetic during relaxation, so
  $T_{\text{init}}=0.1$ equilibrates UP to $\sim 0.288$ while
  $T_{\text{init}}=2.0$ equilibrates DOWN to $\sim 0.750$. The validation
  flags warn based on this initialization temperature.
- `timestep`: integration step $\Delta t$ in reduced units (must be $> 0$).
  Above `MD_PLAUSIBLE_MAX_TIMESTEP = 0.01` risks energy-conservation
  failure or numerical explosion from the $r^{-12}$ repulsive wall.
- `n_steps`: number of velocity Verlet steps (must be $\ge 1$).
- `density`: number density $\rho$ in reduced units (default $0.85$),
  used to set the fcc lattice spacing.
- `seed`: optional RNG seed for velocity initialization (ADR 0005).

Result columns: `step`, `time`, `total_energy`, `kinetic_energy`,
`potential_energy`, `total_momentum_magnitude` — one row per step from
$0$ to `n_steps` inclusive.

**Verification targets** (all in `tests/test_molecular_dynamics_correctness.py`):

- Target A — energy conservation: $| \Delta E | / E_0 < 10^{-3}$ over
  2000 steps at $N=108$, $T_{\text{init}}=0.4$, $\Delta t=0.005$; halving
  $\Delta t$ must shrink the error by $3\times$–$5\times$ (velocity
  Verlet is $O(\Delta t^2)$).
- Target B — momentum conservation: `total_momentum_magnitude` $< 10^{-10}$
  at every step (exact machine-precision algebraic identity of the
  antisymmetric force loop).
- Target C — closed-form force table: `lennard_jones_force` at
  $r = 2^{1/6}$ (equilibrium, force $\approx 0$), $r=1.5$ (attractive),
  $r=0.9$ (repulsive), magnitudes within $10^{-9}$ of the analytic
  values from the potential definition.
- Target D — fixed-seed reproducibility (ADR 0005): same seed $\to$
  bit-identical; different seeds $\to$ diverge.
- Target E — published cluster global-minimum energies: potential energy
  of `lj_cluster_positions(n)` matches Cambridge Cluster Database
  values: $N=2,3,4$ exact at $-1, -3, -6$ (all pairs at $r_{\min}$);
  $N=13$ (Mackay icosahedron, golden-section scale search) matches
  Hoare & Pal (1971) $-44.326801 \pm 10^{-6}$; LJ13 geometry has
  compressed centre-to-shell ($\sim 1.081838 < r_{\min}$) and stretched
  shell-to-shell ($\sim 1.137512 > r_{\min}$) distances.

**Flags** (`ok=True, flagged=True`):
- `timestep > 0.01` — energy conservation at risk
- `initialization temperature` outside $[0.1, 0.8]$ — frozen or
  evaporating cluster (note: this is the *initialization* temperature
  $T_{\text{init}}$, not the equilibrated $T_{\text{equil}}$; the two
  are not related by a fixed factor)
- `n_particles` not an exact fcc count — rounded up
- `n_particles < 10` — too small for meaningful cluster dynamics

**Hard rejections** (`ok=False`): `n_particles` not int or $< 2$;
`temperature`, `timestep`, `density` not finite positive floats;
`n_steps` not int or $< 1$.

```python
lj_cluster_positions(n_particles: int) -> np.ndarray
```

Returns known global-minimum geometries for $N \in \{2, 3, 4, 13\}$,
shape `(n_particles, 3)`, reduced units ($\varepsilon = \sigma = 1$).
$N=2$: pair at $r_{\min}$; $N=3$: equilateral triangle; $N=4$: regular
tetrahedron (vertices $(1,1,1)$, $(1,-1,-1)$, $(-1,1,-1)$,
$(-1,-1,1)$ scaled to edge $r_{\min}$); $N=13$: centred Mackay
icosahedron — 12 vertices from cyclic permutations of $(0, \pm 1,
\pm \phi)$ with $\phi = (1+\sqrt{5})/2$, plus origin, uniformly scaled
by the golden-section minimizer of total LJ potential. Raises
`ModelBuildError` for unsupported $N$.

## Gillespie SSA (exact stochastic simulation, ADR 0009)

```python
simulate_gillespie_ssa(
    a0: int,
    k: float,
    end: float,
    seed: int | None = None,
) -> SimulationResult

validate_ssa_params(a0: int, k: float, end: float) -> ParameterValidation
```

A single irreversible first-order decay reaction $A \to B$ with
per-molecule rate $k$ (propensity $k \cdot a$), simulated with
Gillespie's exact Direct Method — no antimony/roadrunner involved,
direct Python/numpy with the ADR 0005 RNG convention.

- `a0`: initial number of A molecules (integer $\ge 1$).
- `k`: per-molecule decay rate (finite, $\ge 0$). $k = 0$ means no
  reaction: the simulation emits only the initial and final rows.
- `end`: simulation time (finite, $> 0$). The final row is always
  snapped to exactly `end`.
- `seed`: optional RNG seed (ADR 0005); a fixed seed reproduces the
  trajectory bit-identically.

Result columns: `time`, `a`, `b` — one row per event, plus the initial
row at $t=0$ and the final row at `end`. Conservation $a + b = a_0$
holds on every row. The exact distribution of the count at time $t$ is
Binomial$(a_0, e^{-kt})$, so $E[a(t)] = a_0 e^{-kt}$.

**Verification targets** (all in
`tests/test_gillespie_ssa_correctness.py`):

- Target A — closed-form agreement: mean final A across 50 seeded
  replicates within $3\sigma$ of $a_0 e^{-k \cdot \text{end}}$ (using
  the exact binomial variance); mean event count near
  $a_0 (1 - e^{-k \cdot \text{end}})$.
- Target B — conservation: $a + b = a_0$ on every row.
- Target C — seed determinism (ADR 0005): same seed $\to$ bit-identical
  trajectory; different seeds $\to$ diverge.
- Target D — edge cases: $k = 0$ emits no events; complete decay snaps
  to `end` without negative counts; rows strictly increasing in time.

**Flags** (`ok=True, flagged=True`):
- `a0 < 30` molecules — stochastic effects dominate below this size,
  trajectories differ wildly between seeds
- `k > 10` — events so dense the trajectory is a random walk far from
  the smooth closed form

**Hard rejections** (`ok=False`): `a0` not a positive integer (bool
rejected too); `k` not a finite number $\ge 0$ (bool rejected);
`end` not a finite positive number.

The API runtime ceiling (ADR 0007) is `MAX_API_SSA_POPULATION =
1_000_000` molecules: SSA cost is $O(\text{initial population})$,
so `a0` bounds the event count directly.
