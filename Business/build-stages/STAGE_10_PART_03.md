# Stage 10, Part 3 — SEIR's R0 bound was disabled at its own default

Stage: 10 · Part: 3 · 2026-08-09 (overnight)

## 1. The defect

`validate_sir_params` evaluated `R0 = beta/gamma` **after** an early return
on `i0 == 0`:

```python
if i0 == 0:
    v.flagged = True
    v.flag_reason = "I0 is zero: no outbreak can occur"
    return v                      # <- R0 never computed

basic_reproduction = beta / gamma
```

For SIR that is harmless: with no infectives and no exposed compartment,
nothing can happen. **SEIR is a different model.** `e0` alone seeds a full
epidemic, and `i0 = 0` is the API's shipped default for that domain
(`tellurium_runner.py`).

`validate_seir_params` then compounded it. It delegated to the SIR
validator and stripped any flag whose reason began with `"I0"` — correct in
itself, since "no outbreak can occur" is false when `e0 > 0` — but the R0
bound had already been skipped by the early return, so there was nothing
left to inherit.

Net effect: **the R0 plausibility check was disabled at SEIR's normal
operating point.** Measured before the fix:

```
validate_seir_params(beta=100, gamma=0.1, s0=990, e0=10, i0=0)
  -> flagged = False, flag_reason = None            (R0 = 1000)

simulate_seir(same parameters)
  -> ran to completion, peak I = 499.45, flagged = False
```

An R0 of 1000 is roughly fifty times measles. A student saw an ordinary
epidemic curve with no indication the parameters were nonsense — the same
failure shape as the parameter-laundering bug in Part 1: wrong science
delivered silently rather than refused loudly.

Found by the engine audit agent; reproduced independently here before any
change was made.

## 2. The fix

R0 is a property of the disease parameters alone. It does not depend on
initial conditions, so it must not sit behind an initial-condition branch.

A shared `_flag_implausible_r0(v, beta, gamma)` helper now performs the
check, called directly by **both** validators before either inspects `i0`:

- **SIR** keeps both signals when both apply. `R0=1000, i0=0` now reports
  `"R0 = beta/gamma = 1000 exceeds 20...; I0 is zero: no outbreak can
  occur"` — the R0 flag no longer overwrites the no-outbreak message, and
  the no-outbreak message no longer suppresses the R0 flag. Both are true.
- **SEIR** calls the helper itself rather than inheriting through a
  delegate whose flag it then strips. The two concerns are now independent.

Sharing the helper also means the bound cannot drift between the domains —
pinned by a test that asserts both flag at the same threshold.

Removed while restructuring: the three-line flag-merge in
`validate_seir_params` contained a branch
(`if v.flagged and v.flag_reason is None`) that branch coverage confirmed
the suite never executed and that could not execute — the preceding line
always assigned. Deleted rather than left as decoration.

## 3. Verification

8 tests in `Tellurium/tests/test_seir_r0_guard.py`, covering both the
defect and the behaviour that must not change:

- implausible R0 flagged at SEIR's default `i0=0`
- the end-to-end case: an epidemic peaking near 500 infectives is now
  flagged (this is the scenario that ran silently)
- a sane R0 is **not** flagged — the fix must not cry wolf
- just below the bound is not flagged
- SIR reports R0 *and* the zero-`i0` message together
- SIR still reports zero-`i0` alone when R0 is sane
- ordinary SIR unflagged
- SIR and SEIR agree on the threshold

**Mutation-tested.** Restoring the original early return and the
inheriting SEIR wrapper fails 3 of 8, including the end-to-end epidemic
test, with `AssertionError: R0 flag was lost`. Reverted; green.

Rule 2 is preserved throughout: implausible values are **flagged, never
rejected**. The simulation still runs and still teaches; the student is
simply told the number sits outside anything observed.

Full suite: 978 engine tests, 14 guards, `tsc` clean.

## 4. Also this session

- `check_literature_inventory.py`'s own docstring claimed "39 numbers
  across 15 domains". Both figures were wrong — artefacts of the
  hand-rolled regex that mis-parsed inline `parameters: { ... }` entries
  before it was fixed. Corrected to the measured 64 across 14, with the
  error recorded: a guard against unchecked numbers reporting an unchecked
  number of its own would be a poor joke.

- **`seir.sigma` remains UNVERIFIED, deliberately.** A search for a source
  reporting R0 and a *measured latent period* for the same disease under
  compatible methodology did not find one. The nearest candidate —
  Hou et al. (2020), *J Med Virol* 92(7) 841-848,
  DOI 10.1002/jmv.25827, PMID 32243599 — is a single-city SEIR fit whose
  own abstract says other parameters were "suppose as unchanged". It
  *assumes* a latent period rather than measuring one; citing it would
  launder an assumption into a citation, which is exactly what ADR 0017
  refused for measles and influenza.

  The rejection is now recorded in the inventory entry itself, so the next
  person does not re-tread it. Note the distinction that makes this hard:
  a **latent** period (infection → infectiousness) is not the **incubation**
  period (infection → symptoms), and neither is the **serial interval**;
  the three are routinely conflated in the literature, which is precisely
  why a matching source is scarce rather than abundant.

  25% remains 25%. Moving it up requires a real source, and there wasn't
  one to be had tonight.

## 5. Remaining from the audits (§2 of Part 1)

Unchanged and still open, in severity order: the Lotka-Volterra excursion
ratio still reachable via the API (item 2); the biased
`gillespie_ssa_replicates` ensemble mean (item 3); `TwoLocusResult.flagged`
typed as `list` so the two-locus domain has no Rule 2 tier (item 4);
`Tellurium/__init__.py` 25 names behind `__all__` (item 5); and the six
API-layer items — the empty `jobId`, the always-false `strendaCompliant`,
`routes/metrics.ts` wired to a collector production never writes to, the
`"Domain: <name>"` placeholder emitted as a citation, and
`publicationBlocked` ignoring `default`-origin parameters.
