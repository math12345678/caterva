# ADR 0117: The unit that was checked and then discarded

**Status:** Accepted

**Date:** 2026-08-18

## Context

Run the first example in `help`:

```bash
simulate "michaelis menten" --km 5.2mM --vmax 12.8uM/min --s0 10mM
```

Now run it with `--vmax 12.8mM/s` — a Vmax **60,000 times larger**. The two
produced byte-identical trajectories:

```
       0.0 |         10.000
       1.1 |          2.710
       2.2 |          0.288
```

Checked against scipy, that is the answer for **12.8 mM/s**. So every user
who wrote `uM/min` — the unit BRENDA reports Vmax in, and the one the help
text uses in its own example — got a curve 60,000× too fast, presented with
a job ID, a reproducibility key and a validation pass.

And the run logged:

```
"User supplied a bare number; unit was ASSUMED, not declared"   vmax → μM/min
```

for a unit the user had typed. **The one visible symptom pointed away from
the cause.**

### Three places dropped it, and two of them looked like the fix

1. `commandSimulate` and `commandValidate` read flags with
   `parseFloat(value)`. `parseFloat('12.8mM/s')` is `12.8`.
2. The `simulate` dispatcher *did* call `parseQuantity` — validating the
   unit, rejecting typos, using it to decide whether to warn — and then
   stored `String(quantity.value)`, discarding it before the command ran.
3. `runSimulation` unwrapped `{value, unit}` and kept only `.value`, so even
   a correctly-labelled parameter reached the engine as a bare number.

`src/cli/parseQuantity.ts` was written to fix precisely this. Its docstring
names the 60,000:

> Someone with a Vmax in mM/s got their number silently reinterpreted as
> μM/min — a factor of 60,000 — and the run continued.

It was wired into `--resolve` and `sweep`, and those two paths threw the
unit away one line later as well. **The fix corrected the reporting and left
the arithmetic**, which is the worst possible half to fix: the typo check
works, the assumed-unit message is right, the number is still wrong, and
every surface a reader would check now says the problem is handled.

The conversion layer existed and was correct. `src/units.ts` has
`vmaxInSubstrateUnitsPerSecond` and `convertConcentration`;
`scientificPipeline.ts` already imported and used both — twenty lines above
`runSimulation` — **to feed the depletion check, never the run it was
checking.** The validator was doing correct arithmetic about a trajectory
computed from different numbers. Both halves were internally consistent,
which is why nothing failed.

## Decision

**Carry the declared unit to the engine, and convert there.**

- `readQuantities()` replaces `parseFloat` in both commands, keeps the
  unit, and forwards it as `providedProvenance[key].unit` — a channel that
  already existed and that `resolveParameters` already preferred over the
  name-based assumption.
- The `simulate` dispatcher forwards the value **as typed**.
- `runSimulation` converts into one system before integrating:
  concentrations in s0's unit, rates in s0's unit per second — the system
  the output already claims, since `end` is in seconds and `[S]` is
  reported in the substrate's unit.

**Only declared units are forwarded.** A bare `--km 5.2` still gets the
conventional unit and still warns — and that warning is now true.

**Missing units make the converters throw** rather than assume, which
surfaces as a validation failure instead of a confident trajectory nobody
can interpret.

## Consequences

- `--vmax 12.8uM/min` and `--vmax 12.8mM/s` now differ, and both match an
  independent scipy integration to 4 significant figures.
- A Km in μM against an s0 in mM is no longer integrated as if both were mM.
- The false "you supplied a bare number" warnings are gone.

### What this does not fix

`--vmax 12.8` with no unit still means μM/min by convention. That is a
documented assumption rather than a silent one, and it is now the only
remaining guess on this path.

The Python CLI (`python -m Terium.cli`) exposes population genetics and SSA
only — none of the enzyme-kinetics or literature-resolution capability
described in the README is reachable from it. That is a separate gap and is
not addressed here.

## Verification

Constitution Rule 1: checked against an exact closed form, not against the
engine's previous answer. For Michaelis-Menten the integrated form is
implicit,

    Km ln(S0/S) + (S0 - S) = Vmax·t

so `declaredUnitsReachTheEngine.test.ts` evaluates the residual for the
reported final substrate. It balances for the Vmax the user **declared**,
and does not balance for the one the name-based table would have assumed.

| check | result |
|---|---|
| Vmax in mM/s integrated as mM/s | pass |
| Vmax in μM/min integrated as μM/min, residual < 1e-3 | pass |
| the two units give different answers at all | pass |
| Km in μM converted into the substrate's units | pass |
| existing `scientificPipeline.integration.test.ts` (21 tests) | pass |
| `parseQuantity.test.ts` (15 tests) | pass |

Independent confirmation outside the codebase:

```
scipy, 12.8 uM/min : t=1.1  9.9998    Terrium 10.000
scipy, 12.8 mM/s   : t=1.1  2.7098    Terrium  2.710
```

## Related

- ADR 0013 — never default an enzyme concentration
- ADR 0055 — a simulation has no temperature of its own
- `src/cli/parseQuantity.ts` — the fix that stopped one line short, twice
