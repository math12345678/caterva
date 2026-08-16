# ADR 0055: A simulation has no temperature of its own

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0024 (the silent species assumption), ADR 0026 (assay
coherence), ADR 0027 (the value discarded at a boundary), ADR 0044 (the
forbidden default), ADR 0034 (`--selftest`), ADR 0010 (STRENDA)

## Context

Nine call sites in this repository opened their conditions object with the
same literal:

```ts
conditions: { temperature: 37, pH: 7.4 }
```

The web server, three CLI paths, the pipeline itself, the batch processor,
the parameter sweep, and both model-comparison calls. One number, copied
nine times, sourced nowhere.

### The scientific question, which has a counter-intuitive answer

"What temperature is this simulation at?"

The Michaelis-Menten ODE is

    dS/dt = -Vmax * S / (Km + S)

There is nowhere in it for a temperature to go. `runSimulation` discards the
conditions object entirely — `void conditions;` — and that is **correct**. A
Km's temperature dependence is already inside the measured Km. Km and Vmax
*are* the temperature, encoded.

So a simulation does not run at a temperature the student picks. It runs at
the temperature the papers were measured at, whatever that was, whether or
not anybody recorded it.

### Three things wrong with the literal

**It is hardcoded**, which this project forbids on principle.

**It is a human body condition.** A student modelling a thermophile, a plant
enzyme or a lysosomal protease got 37 C and pH 7.4 without being asked. The
same silent mammalian substitution ADR 0024 exists to prevent — and the same
one ADR 0053 caught me reintroducing as `|| 'Homo sapiens'` one pass ago.

**It made a shipped check unfalsifiable.** `AssumptionValidator` warns when a
temperature is outside 4–45 C and when a pH is outside 5–9. **37 and 7.4 are
the dead centre of both ranges.** Those warnings existed, were unit-tested,
and could not fire from any path a user could reach.

The warning text is the part that stings:

> "...confirm the kinetic constants were measured at this temperature."

That is the confirmation Lisa Jeske asked for, in the reply warning that
mixing pH, temperature, cofactors and buffers produces *"fantasy numbers"*.
It was unreachable, because the temperature was a fiction.

## Decision

### `src/validation/runConditions.ts`

`deriveRunConditions(parameters)` reads the conditions off the parameters'
own provenance and returns a three-state verdict per condition:

| Status | Meaning |
|---|---|
| `agreed` | every parameter that reported a value reported the same one |
| `conflicting` | they reported different ones |
| `not_reported` | none of them reported any |

`conflicting` is Jeske's case. A Km measured at 25 C and a Vmax at 37 C do
not describe one enzyme under one condition; they describe two experiments.
That mixture **has** no temperature, so none is returned. It is not averaged
— the mean of two assay temperatures is not an assay temperature — and not
picked, because picking is choosing which paper to believe, silently.

Three states rather than two, because `not_reported` and `conflicting` are
different facts. One is a gap in BRENDA's record; the other is a defect in
the model being built. Collapsing them would let a real incoherence hide
inside a common absence — the same distinction as ADR 0012/0013's
measurement-versus-choice and ADR 0024's nothing-found-versus-withheld. This
project keeps rediscovering it in new places.

A `conflicting` verdict deliberately carries **no** `value`. The tempting
alternative — first value plus a flag — makes the incoherent case
structurally identical to the coherent one at every call site.

Equality is exact. No tolerance, because a tolerance would be a threshold
with no source; ADR 0026 refused to invent one for the same reason.

### The validator reports `notEvaluated`, not silence

An absent temperature now pushes to `notEvaluated` — the mechanism already
used for the steady-state check when `e0` is missing — with text that
refuses to be read as approval: *"This is NOT a statement that the
temperature was suitable — it is a statement that it is unknown."*

### `temperature` and `pH` removed from `SimulationRequest.conditions`

Deliberately a compile error rather than a silent ignore. Nine call sites
passed them; letting those keep compiling while the values stopped mattering
would leave nine lines that read as if they configured something.

### The dropped boundary, for the fifth time

`ResolvedKinetic` has carried `assayConditions` since ADR 0010.
`ParameterRecommendation` had no field for it, so `resolveFromLiterature`
read it and dropped it one line later — and with nothing downstream able to
know an assay temperature, a hardcoded 37 looked like the only option.

Fifth instance of *computed, correct, discarded at a boundary because the
receiving type has no field for it*. See ADR 0027, 0038, 0039, 0040.

## Verification, and the mutation that says the most

Six mutations against 17 new tests.

| Mutation | Result |
|---|---|
| a conflict carries the first value anyway | 1 failure |
| `not_reported` collapses into `conflicting` | 2 failures |
| unknown temperature silently defaults to 37 | 2 failures |
| `describeConflicts` averages instead of naming both | 1 failure |
| `!value` swallows a genuine 0 C | 1 failure |
| **the pipeline restores `temperature: 37, pH: 7.4`** | **all 17 passed** |

The sixth restores the original defect *exactly*, and every test passed.

The tests cover `deriveRunConditions` and `AssumptionValidator` thoroughly.
The defect was never in a function. It was in what nine call sites chose to
pass, and **no unit test sees a call site.**

Same shape as ADR 0027's parity test, which pinned two implementations
against a shared fixture and could not see that its two callers passed
different arguments. And it is the shape of the sentence I wrote in the new
test file's own header — *"testing a function is not testing the call
site"* — immediately before making the mistake it describes. Eighth
unfalsifiable check this session, seventh in my own work.

### `scripts/check_no_hardcoded_assay_conditions.py`

The fix is a guard, not another test, because the thing to pin is a property
of the whole tree rather than of any function: no source file may state an
assay temperature or pH it did not measure. Any numeric literal, not just
implausible ones — 25 C is no better sourced than 37 C, and permitting
"reasonable" values would need a definition of reasonable, itself unsourced.

It has `--selftest` (ADR 0034): on a clean tree it reports zero findings
forever, and a broken matcher would report zero too. Six known-bad lines
must flag, five known-good must pass.

Under the sixth mutation it fails. The defect is now catchable by the thing
that was blind to it.

### What it found on its first run

A ninth site, which the regex sweep had missed:

```ts
/** Fallback to reasonable defaults when network is unavailable
 *  These values are UNVERIFIED - marked as such in validation */
const FALLBACK_PARAMETERS = {
  km: 5.2, vmax: 12.8, s0: 10.0, temperature: 37, pH: 7.4
};
```

`km: 5.2` and `vmax: 12.8` are the two numbers ADR 0044 removed from the
dashboard form, and ADR 0024 names 5.2 specifically as the default this
project must not have. They were still in the CLI, months later.

Nothing referenced the constant — which is why nobody noticed, and why no
test could have found it. `check_no_unsourced_ui_numbers.py` scans HTML
pages only, so a forbidden default in TypeScript sat outside every guard the
project had. The new guard reached it through the `temperature: 37` two
lines below the Km.

*"Marked as UNVERIFIED in validation"* is not a defence. A number that was
never measured does not become admissible by being labelled; it becomes a
number a reader has to remember to distrust. Deleted with no replacement: a
network failure means the parameters could not be resolved, and the honest
response is to say so and stop.

## Consequences

- The two range warnings are reachable for the first time. A thermophile
  assay at 72 C now warns; under the old literal it could not.
- `metadata.warnings` was the literal `[]` and now carries the conflicts. A
  field that is always empty is not a warnings list, it is a promise that
  nothing is wrong.
- `SimulationResponse.runConditions` lets a surface say what a trajectory is
  a trajectory *of*. Optional only because the early-return failure paths
  have no parameters to derive it from.
- `notEvaluated` will be common. Most BRENDA rows do not report both a
  temperature and a pH, so the honest output is frequently "unknown" where
  it used to be a confident 37. That is a worse-looking product and a
  truer one.

## What it does not do

Nothing renders `runConditions` yet. The pipeline computes it, the response
carries it, `examples/` prints it — and the dashboard does not. That is the
same gap ADR 0027 and ADR 0040 were about, named here in advance rather than
discovered later, and it is the next thing to build.

Temperature still does not affect the ODE. Making it do so means an
Arrhenius or pH-activity model, which needs its own literature and its own
ADR. What changed is that the program no longer claims a temperature it
neither uses nor knows.
