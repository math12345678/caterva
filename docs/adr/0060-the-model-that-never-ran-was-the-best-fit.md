# ADR 0060: The model that never ran was the best fit

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `src/engine/model-comparison.ts`, `src/engine/batch-processor.ts`,
`src/storage/csv-exporter.ts`

**Follows:** [ADR 0058](0058-the-crashed-point-won-the-sweep.md), which found
a crashed sweep point recorded as `finalValue: 0` winning the sweep. This
records the same defect in the two engines 0058 did not reach, where the
consequence is worse.

## The defect, at the point where it costs the most

`rankModelsByFit` answers the most consequential question in this codebase:
*which model best explains my experimental data*. It filtered with:

```ts
results.filter(r => !r.error)
```

That excludes models that **threw**. It admits models that **ran and failed
validation** — and `scientificPipeline` returns
`finalValue: simulationOutput.finalValue || 0` with an empty trajectory in
exactly that case. So such a model arrives carrying a fabricated `0`, with
no `error` string to catch it on.

Fit is scored by `|finalValue - experimentalValue|`. **The closer the
experiment's own measurement is to zero, the better a failed model scores.**

Measured before any change, against an experimental value of 0.4 — ordinary
near-complete conversion in enzyme kinetics:

```
  experimental value: 0.4
  rank 1: uncompetitive    (error 0.40)   <- did not validate. Never ran a trajectory.
  rank 2: competitive      (error 3.50)
  rank 3: michaelis-menten (error 3.80)
```

The model that produced nothing was ranked first, ahead of both models that
ran.

ADR 0058's defect produced a wrong statistic and a wrong optimum. This one
produces a **recommendation**: a student comparing mechanisms against their
own bench data is told which mechanism their data supports, and the answer
can be a model that never executed.

That regime is not a corner case. Sweeps and comparisons are run precisely
to find conditions with high conversion, which means low remaining
substrate, which is where a placeholder zero looks like an excellent fit.

## `!error` and `validated` are different facts

Neither implies the other, and every site that conflated them had the same
shape of bug:

| site | was | consequence |
|---|---|---|
| `rankModelsByFit` | `!r.error` | a failed model ranked first |
| `compareModels` → `validResults` | `!r.error` | a failed model named `bestModel` |
| `compareModels` → no-valid-results branch | `results[0]` | the first model in the list, freshly failed, returned as the winner |
| `processBatch` → `successfulJobs` | `!r.error` | **a batch where every job failed validation reported 100% success** |
| `processBatch` → metrics mapper | `validated: !result.error` | `/api/metrics/*` counted unvalidated batch runs as validated |

All now require `validated === true` **and** a non-null `finalValue`. That
pairing is ADR 0058's M3 finding — a mutation there showed the two
conditions come apart in production — applied to the files that ADR did not
touch.

## Two smaller things found on the way

**Every failed batch job reported an execution time of 0ms.** `jobStartTime`
was declared inside the `try`, so the `catch` had nothing to subtract and
read `Date.now() - Date.now()`. A job that spent a 120-second timeout before
failing was recorded as failing instantly. "Failed immediately" and "failed
after two minutes" are different diagnoses, and one of them was unavailable.

**`compareModelPair` coalesced a missing result to zero**, so the reported
difference between a model that ran and one that did not equalled the
surviving model's entire value — i.e. "these two mechanisms disagree
completely", a strong and fabricated claim. It now returns
`difference: null` with an `incomparableReason`, and both results unchanged
so the caller can see which side is missing.

## Decision

1. `ModelResult.finalValue` and `BatchJobResult.finalValue` are
   `number | null`; failures record `null` plus an `error`, and the success
   path uses `?? null` so a **genuine** zero — full substrate consumption,
   the best possible outcome — survives.
2. A shared `usableResults()` requires `validated === true` and a non-null
   `finalValue`.
3. `compareModels` refuses when nothing is usable: `bestModel: null`,
   `variability: null`, plus `modelsAnalyzed` / `modelsExcluded` and an
   `unanalysableReason`.
4. `rankModelsByFit` returns `{ ranked, excluded }` rather than a bare
   array. Excluded models carry the reason they were left out — a clean
   three-way ranking with no sign a fourth model was attempted would let a
   reader conclude the comparison was complete.
5. `processBatch` reports `successfulJobs` (ran and validated),
   `erroredJobs` (threw) and `didNotValidateJobs` (ran, failed its checks)
   separately.
6. The batch and comparison CSVs gain an `error` column and a `#` banner
   stating how many rows produced no usable value and how they failed. The
   banner is silent when nothing failed: a "0 of 4 failed" line on every
   export is noise, and noise is what gets a real warning skipped.

## Mutation testing

| # | mutation | tests failed |
|---|---|---|
| N1 | `rankModelsByFit` back to `!r.error` | 3 |
| N2 | `successfulJobs` counted as `!r.error` again | 2 |
| N3 | failed job timed as `Date.now() - Date.now()` | 1 |
| N4 | `compareModels` refusal branch made unreachable | **0**, then 1 |
| N5 | failure banner never emitted | 1 |

### N4 — the refusal had no test

Making `compareModels`' no-usable-results branch unreachable failed nothing.
The suite covered `rankModelsByFit` thoroughly and `compareModels` not at
all, because `compareModels` needs the pipeline mocked and
`rankModelsByFit` is a pure function. The easy half was tested and the half
that required setup was not.

That is the same shape as ADR 0058's M1, where the crash sentinel had no
test because every fixture was hand-built and nothing ran the producer.
Twice in two passes, the untested thing was the one behind a mock.

Three `compareModels` tests were added against a mocked pipeline. N4 now
fails 1.

## Consequences

- `analyzeSensitivity`, `analyzeSweep`, `compareModels` and
  `rankModelsByFit` now all report how much of their input they used.
  A reader can tell a four-model comparison from a four-model comparison
  where two models failed, which the old output could not express.
- `rankModelsByFit`'s signature changed from an array to
  `{ ranked, excluded }`. **It has no production callers** — nor does
  `compareModelPair`. Both are exported API surface exercised only by tests.
  Worth stating plainly: the most scientifically consequential function in
  the engine is not currently wired to any route.
- `BatchProcessResult` gains `erroredJobs` and `didNotValidateJobs`.
  `failedJobs` is now their sum, and is larger than before for any batch
  containing a job that ran and failed validation.

## What this does not fix

`compareJobs` and `compareMultipleJobs` in `result-comparator.ts` still read
`job.result?.finalValue || 0`. Same defect class, and a change to comparison
semantics rather than a bug fix — carried forward from ADR 0058's
"what this does not fix" rather than quietly dropped.

`/api/export/stats/csv` carries aggregate counts only and has no
per-parameter provenance to add. It was reviewed and left alone.

## Related

- [ADR 0058](0058-the-crashed-point-won-the-sweep.md) — the same defect in
  the sweep engine, and the M3 finding this generalises
- [ADR 0050](0050-the-file-that-leaves-the-building.md) — why the export has
  to show it
- [ADR 0027](0027-one-reliability-score-not-two.md) — a test that agrees
  with the code about a question production never asks
