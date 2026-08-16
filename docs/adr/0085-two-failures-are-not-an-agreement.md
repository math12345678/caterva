# ADR 0085: Two failures are not an agreement

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `src/storage/result-comparator.ts`, `POST /api/compare/jobs`

## The defect

`compareJobs` read both sides as `job.result?.finalValue || 0`. Measured
before any change, on two jobs that never produced a result:

```
  job1FinalValue : 0
  job2FinalValue : 0
  similarity     : identical
  percentDiff    : 0
```

**Two failed runs, reported as results that agree perfectly.**

A student comparing two runs that did not finish is told their outcomes are
identical — a scientific claim manufactured out of two absences. This is a
live route, unlike `rankModelsByFit` (ADR 0060), which has no production
caller.

The other direction is no better: a failed job against a real one gives
`ratio: 0` and `significantly_different`, which reads as a measured
disagreement rather than a missing measurement.

## Why this one is worth a long comment

The **`confidence` half of this same function was already fixed**, with this
argument spelled out in the code:

> a job that has no result yet has no confidence, not a confidence of zero,
> and printing "0.950 vs 0.000" for a job that has not finished asserts a
> measurement nobody made.

That reasoning was applied to `confidence` and not to `finalValue`, two
lines above it, in the same function, by the same author.

**A lesson applied only where it was first learned is a lesson half-taken.**
That is now the third recorded instance: ADR 0056's fixture-resemblance rule
applied to success shapes and not failure shapes (ADR 0065); ADR 0058's
`validated`/`!error` pairing found in four more places one pass later (ADR
0060); and this.

Carried in "still open" for six passes before being done, which is the same
failure at the level of the record.

## Decision

`jobFinalValue()` returns `number | null`, reading the nested pipeline shape
first and the flat one as fallback (ADR 0056). When either side is null,
`compareJobs` returns `comparable: false`, null metrics, null similarity,
and an `incomparableReason` naming **both** job ids — so a caller can tell
"one side is missing" from "both are".

`ComparisonMetrics` became nullable throughout. The incomparable branch
initially used `as unknown as JobComparison` to satisfy the old types; that
cast was removed and the interface widened instead, because **a cast is a
promise the compiler stops checking**, and it is exactly how a fabricated
value gets back in.

## Mutation testing

| # | mutation | result |
|---|---|---|
| Q1 | a missing final value coalesces to 0 again | caught |
| Q2 | the incomparable branch weakened | **INDETERMINATE — see below** |
| Q3 | the refusal stops naming which job is missing | caught |
| Q4 | a genuine zero in the nested shape treated as absent | **0 → 1** |

### Q2 is type-enforced, not test-enforced

Both weakenings tried — making the branch unreachable, and narrowing it to
`&&` so one missing side slips through — are INDETERMINATE, because either
way `val1` stays `number | null` and the arithmetic below **fails to
compile**.

The guard is enforced by the type system rather than by an assertion. That
is stronger protection than a passing test, and the harness is right to
refuse to report it as a coverage result: a suite that did not run has
judged nothing. It is recorded rather than deleted, because the next person
to widen those types loses the protection silently, and this row is where
they will find out.

### Q4 found a gap in a test written minutes earlier

The zero-value test used the **flat** shape, so a mutation making the
*nested* reader treat 0 as absent passed everything — the flat fallback
still returned 0.

The pipeline emits the nested shape, so that is the path a real job takes.
Covering only the flat one tested the fallback and left the primary reader
unguarded: ADR 0056's defect, in a test written to honour ADR 0056.

## Related

- [ADR 0058](0058-the-crashed-point-won-the-sweep.md) and
  [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md) — the same
  absence-as-zero defect, in the sweep and model engines
- [ADR 0056](0056-a-column-that-claimed-a-source.md) — nested vs flat shape
- [ADR 0083](0083-the-harness-answered-twice.md) — corrected while running
  this table
