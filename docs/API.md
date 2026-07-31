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
  ``migration_rate``) plus ``fixation_gen_A`` and ``fixation_gen_a``
  (list of the first generation each replicate reached frequency 1.0
  or 0.0, or -1 if never fixed within the simulation window), and
  ``final_frequencies`` (per-replicate final allele frequencies,
  pooled across demes for structured populations).

- ``result.fixation_analysis()`` -- returns a dict with ``n_replicates``,
  ``n_fixed_A``, ``n_fixed_a``, ``n_polymorphic``, ``prop_fixed_A``,
  ``prop_fixed_a``, and when replicates fixed: ``mean_fixation_time_A``,
  ``sd_fixation_time_A``, ``min/max_fixation_time_A`` (and the
  corresponding keys for allele a).

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
  [0, 1], s <= -1, h outside [0, 1]).

Useful for teaching the classic "selection vs drift" comparison: run a
simulation, compare ``fixation_analysis()["prop_fixed_A"]`` against the
Kimura prediction, then try other values of s.

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
  in ``[0, 1]`` for diploid selection with fitnesses ``AA: 1+s``,
  ``Aa: 1+hs``, ``aa: 1``.
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
  Wright's island model: demes drift partially independently, and
  ``migration_rate`` controls the exchange of alleles between them.
- ``migration_rate`` -- fraction of each deme's allele pool replaced
  by migrants from the global pool each generation, in ``[0, 1]``.
  ``0`` (default) = no migration, demes drift independently.
  Ignored when ``n_demes = 1``.
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

Any ``**overrides`` are merged into the scenario's parameter dict, so
callers can tweak e.g. ``generations=100`` without modifying the preset.

```python
# Quick comparison: neutral vs selection with one seed
neutral = wright_fisher_scenario("neutral-drift", seed=42)
selected = wright_fisher_scenario("strong-selection", seed=42)
```

## Command-line interface

The engine ships a small CLI, runnable as a module:

```bash
python -m Tellurium.cli scenarios
python -m Tellurium.cli wf --population-size 100 --generations 200 --seed 42
python -m Tellurium.cli wf --scenario bottleneck --out results.csv
python -m Tellurium.cli kimura --p0 0.3 --s 0.03 --population-size 50
```

- ``scenarios`` -- list the available scenario presets with descriptions.
- ``wf`` -- run a Wright-Fisher simulation. Either give ``--scenario``
  (preset, overridable by any other option) or the core parameters
  ``--population-size`` and ``--generations``. Optional:
  ``--starting-frequency``, ``--replicate-runs``, ``--mutation-rate``,
  ``--selection-coefficient``, ``--dominance``, ``--n-demes``,
  ``--migration-rate``, ``--seed``, ``--out FILE`` (CSV),
  ``--json FILE`` (full result incl. WF params), ``--replicate-data``,
  ``--verbose``, ``--quiet``. Prints ``result.describe()`` by default.
- ``kimura`` -- compute ``kimura_fixation_probability`` for a single
  ``--s`` or as a sweep over ``--s-start/--s-end/--s-steps`` (prints an
  ``s`` vs ``P_fix`` table).

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
validate_wright_fisher_params(population_size, starting_frequency, generations, replicate_runs=1, mutation_rate=0.0, selection_coefficient=0.0, dominance=None, population_size_series=None, n_demes=1, migration_rate=0.0) -> ParameterValidation
```
