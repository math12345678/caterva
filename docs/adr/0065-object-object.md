# ADR 0065: `[object Object]`

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `src/errors.ts`, `src/integration/scientificPipeline.ts`,
`scripts/check_thrown_values_are_errors.py`

**Follows:** [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md),
whose closing observation was that twice in two passes the untested
behaviour had been the one behind a mock. This is what looking there found.

## The defect

`ScientificPipeline.execute` signalled failure by throwing a plain object:

```ts
throw {
  jobId,
  error: 'SIMULATION_ERROR',
  message: error instanceof Error ? error.message : 'Unknown error',
  executionTimeMs: Date.now() - startTime
};
```

Note the care taken over `message`. The real cause is extracted and
preserved, deliberately.

Every consumer then read it with the standard idiom:

```ts
error instanceof Error ? error.message : String(error)
```

A plain object is not an `Error`. So `String(obj)` ran, and produced the
literal string **`"[object Object]"`**.

Measured on the real throw shape:

```
  error recorded : "[object Object]"
  real message   : "Cannot simulate: km could not be resolved from literature"
```

That string reached the `error` field of `GET /api/jobs/:jobId`, the
`errorMessage` recorded in metrics, the `error` columns added to the batch
and comparison CSV exports one pass earlier, and the CLI.

**A student whose run failed because a Km could not be resolved was told
`[object Object]`.** That is the most common failure this project has, and
the most actionable one — the refusal message names the parameter and tells
you how to supply it (ADR 0024, and Sauro's `--cite` work). All of it was
replaced by eight characters of noise at the last step.

Sauro's warning was that a tool which blocks without explaining pushes the
researcher into hardcoding a number. Terrium had built the explanation
carefully and then deleted it on the way out of the door.

## Why every test passed

The mocks written one pass earlier, in `batch-success-accounting.test.ts`
and `model-selection-excludes-failures.test.ts`, throw:

```ts
throw new Error('solver diverged');
```

A real `Error`. The pipeline throws a plain object.

This is [ADR 0056](0056-a-column-that-claimed-a-source.md)'s lesson — *a
test can only be as honest as the resemblance between its fixture and its
producer* — applied to the **failure** shape rather than the success shape.
The success shapes in this repository had been transcribed from the
pipeline's `return` statement precisely because of ADR 0056. The error
shapes were invented, and invented an easier problem than the real one.

Worth stating plainly: the fixture-resemblance rule was learned, written
down, and then applied to only half of the interface.

## Decision

Two fixes, at different levels, and the pairing is deliberate.

**1. `SimulationError extends Error`** fixes the source. Every existing
`instanceof Error` check works unchanged, including in code nobody has
written yet. It keeps `code`, `jobId` and `executionTimeMs`, so the fields
the object shape carried are still there.

`Object.setPrototypeOf(this, SimulationError.prototype)` is in the
constructor because the build target permits ES5, where `instanceof` on a
subclassed built-in silently returns false. Without it this file would
reintroduce, in a new form, exactly the bug it exists to fix.

**2. `describeError(value)`** fixes the readers. It recovers a message from
a non-`Error` that carries one, and is now used at all eight catch sites
that had the `String(error)` idiom.

Its fallback order is deliberate: `Error.message`, then a string `message`
property, then a thrown string, then a `code` rendered as
`"SIMULATION_ERROR (no message was recorded)"`, then `String(value)`. That
last step will still produce `"[object Object]"` for an object with neither
— which is correct. There is genuinely nothing better to say, and inventing
a friendlier sentence would claim knowledge of a cause nobody recorded.

It never returns an empty string. An empty `error` field reads as "no
error", which is a failure rendering as success — the inversion this
codebase treats as its core defect.

## Why a guard, not a test

`scripts/check_thrown_values_are_errors.py` fails the build on
`throw {`. Three properties made a unit test the wrong instrument:

1. **TypeScript permits it.** `throw` accepts `any`. Reintroducing the
   object throw verbatim compiles with **zero** errors — verified by
   mutation, not assumed.
2. **The readers were hardened too.** Because `describeError` recovers the
   message either way, reverting the throw changes no observable behaviour.
   No test can fail on it. This is the ADR 0058 M1 situation exactly: a fix
   protected by a second fix is untestable at its own level.
3. **It is a whole-codebase property.** The next `throw { message }` will be
   written by someone who has not read `src/errors.ts`, in a file that does
   not exist yet.

Verified by re-applying the original defect verbatim: the guard reports
`src/integration/scientificPipeline.ts:569  throw {` and exits 1.

Wired into `verify_build.py` and registered in `check_guard_wiring.py`'s
`EXPECTED_WIRING`, per the Stage 4 amendment — a guard is not delivered
until something runs it unasked.

### The guard's first run failed on its own documentation

It reported two violations, both inside the docstring of `src/errors.ts` —
the prose that **quotes** the offending pattern in order to explain it.

A guard that fires on the description of a defect punishes documenting it,
and the cheapest way to make it green is to delete the explanation. Comments
are now blanked before matching, with offsets preserved so line numbers in
real violations still point at the right line.

## Mutation testing

| # | mutation | result |
|---|---|---|
| P1 | `describeError` stops reading `.message` off an object | 2 failed |
| P2 | pipeline throws the plain object again | tests: **0 failed**; guard: **exits 1** |

P2 is the interesting one and is recorded as a split result on purpose.
No test failed, and that is by design rather than by omission — see "Why a
guard, not a test" above. The guard is what catches it.

### A mutation that did not compile

The first attempt at P1 replaced a condition with `if (false)`, which made
the block unreachable and broke the build. Jest reported `Tests: 0 total`.

`0 total` is not `0 failed`. A suite that cannot compile has not judged
anything, and reading that line as "caught" would have credited the test
with a detection it never made — the mutation-harness equivalent of a false
green, and the third distinct way a mutation has lied in this project after
the no-op patches recorded in ADR 0051 and ADR 0056. Re-run with a mutation
that compiles: 2 tests failed.

## Consequences

- Callers that inspected the thrown object's `.error === 'SIMULATION_ERROR'`
  would break. Checked before changing the type: **there are none.** The
  only mention of that string in the codebase was the throw site itself.
- `describeError` is defence in depth, not redundancy. It exists because
  `"[object Object]"` fails silently: it does not throw, does not warn, and
  looks like a rendering bug rather than a lost diagnosis.
- The error-path mocks in two test files now throw the legacy object shape
  and assert the real message survives. The success-shape fixtures were
  already transcribed from the producer; the failure shapes now are too.

## Related

- [ADR 0056](0056-a-column-that-claimed-a-source.md) — fixture resemblance,
  learned for success shapes and not applied to failure shapes
- [ADR 0058](0058-the-crashed-point-won-the-sweep.md) — a fix protected by a
  second fix is untestable at its own level
- [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md) — the
  observation that pointed here
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) —
  the refusal message this was deleting
