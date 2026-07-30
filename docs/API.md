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
result.colnames        # list[str] - column names, e.g. ["time", "[S]"]
result.data            # list[list[float]] - one row per time/cycle point
result.model_name       # str
result.flagged          # bool - shortcut for result.validation.flagged
result.column("S")      # list[float] - tolerates roadrunner's "[S]" form
result.time             # list[float] - shortcut for result.column("time")
result.final("S")       # float - last value of a column
len(result)             # number of rows
```

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
) -> ParameterValidation

simulate_wright_fisher(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    seed: int | None = None,
) -> SimulationResult
```

**Not** built through antimony/roadrunner -- discrete-generation stochastic
process (binomial sampling each generation). Same category as PCR and Monte
Carlo. See ``docs/adr/0002-pcr-not-modeled-as-an-ode.md`` and
``docs/adr/0005-rng-convention.md``.

Models neutral drift at a single biallelic locus in a diploid Wright-Fisher
population. Each generation, the next generation's ``2N`` allele copies are
drawn ``Binomial(2N, p_t)`` from the current generation's allele pool.

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
- ``seed`` -- optional RNG seed per ADR 0005. Omit for nondeterministic
  output.

Result columns are ``["generation", "mean_frequency", "heterozygosity",
"n_A_fixed", "n_a_fixed"]`` -- one row per generation from 0 to
``generations`` inclusive. Stats are aggregated across all replicate
populations: mean frequency, mean heterozygosity, count of populations
fixed for allele A, count fixed for allele a.

Verified in ``tests/test_popgen_correctness.py``:
- Heterozygosity decays at the exact rate ``(1 - 1/(2N))^t`` (Target A,
  within 0.02 absolute).
- Fixation probability equals the starting frequency p0, per Kimura 1962
  (Target B, within 0.04).
- Fixed-seed reproducibility and seed-dependent divergence (Targets C-D).
- ADR 0005 RNG compliance checked automatically by
  ``scripts/check_rng_convention.py`` and
  ``tests/test_rng_convention.py``.

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
validate_wright_fisher_params(population_size, starting_frequency, generations, replicate_runs=1) -> ParameterValidation
```
