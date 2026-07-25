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
```
