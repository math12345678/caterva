# ADR 0058: The crashed point won the sweep

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `src/engine/parameter-sweep.ts`, `src/storage/result-comparator.ts`,
`GET /api/analyze/sweep/:sweepId`, `GET /api/export/sweep/:sweepId/csv`

**Follows:** [ADR 0056](0056-a-column-that-claimed-a-source.md), which fixed
one export route and left four uncited. Going after the sweep route's
citations turned up two defects that had nothing to do with citations.

## The defect

`runSweep` recorded a simulation that threw as:

```ts
results.push({
  parameters: { ...currentParams },
  finalValue: 0,        // <-- a crash
  confidence: 0,
  validated: false,
  executionTimeMs: 0
});
```

`analyzeSweep` defines the optimum as the **minimum** final value, and says
why in its own comment: *"minimum substrate remaining = maximum
conversion."*

Zero is the smallest value a substrate concentration can take. **So the
point that crashed scored perfectly and was reported as the best parameter
set in the sweep.** A student sweeping Km to find the best value was told
the answer was whichever point errored.

Measured on a three-point sweep with one failure, before any change:

```
  optimalParams : {"km":3}      <- the point that threw
  optimalValue  : 0
  meanFinalValue: 2.17          <- the true mean of the two real runs is 3.25
  minFinalValue : 0
```

Nothing about the output says a point failed. The sweep looks complete, the
optimum looks determined, and the recommendation is the one parameter set
known not to work.

### Why no filter could have caught it downstream

Zero is also a **legitimate** result. Full substrate consumption is the
normal end state of a Michaelis-Menten run, and it is the best possible
outcome. A crash sentinel of `0` is therefore indistinguishable from the
best real answer, by construction — no consumer, however careful, could
separate them. The sentinel itself had to go.

`finalValue` is now `number | null`, failures record `null` plus an `error`
string, and the successful path uses `?? null` rather than `|| 0` so a
genuine zero survives.

## The second defect: two answers to "which point is best"

`GET /api/analyze/sweep/:sweepId` does not call `analyzeSweep`. It calls
`analyzeSensitivity` in `src/storage/result-comparator.ts`, which ended:

```ts
optimalParameterIndex: values.indexOf(Math.max(...values))
```

**Maximum.** While `analyzeSweep` takes the minimum.

Both reached users: `analyzeSweep`'s answer through the exported CSV's
`optimalParameters`, this one through the API. On the same fully-valid
three-point sweep with values 4.0, 2.5, 9.1, they named opposite ends of the
range — 2.5 and 9.1.

That is not a duplicate implementation, it is a contradiction. One tool,
two opposite answers to the same question, both served.

[ADR 0027](0027-one-reliability-score-not-two.md) met the duplicate case and
ruled: **delete the duplicate rather than bypass it**, because a bypassed
duplicate returns the first time someone needs the value and writes a helper
instead of an ADR. The same applies with more force here, since this copy
was also wrong. `optimalParameterIndex` is gone, and a deletion guard fails
if any key matching `/optim|best/i` reappears on that return value.

Naming an optimum was outside a sensitivity function's remit anyway. Its job
is spread and inflection — how much the response moves — not which point a
user should prefer.

`analyzeSensitivity` also computed every statistic over
`results.map(r => r.finalValue || 0)`, so the fabricated zeros flowed into
its mean, min, max, range, stdDev, and into `sensitivity`, which divides by
the mean.

## The third defect: provenance never reached storage

The task that started this was "put citations on the sweep CSV". They could
not be put there. `runSweep` collected five scalar fields off each pipeline
response and discarded `parameterProvenance`, so the data was gone before it
reached storage — no exporter could have carried a source however it was
written. [ADR 0039](0039-computed-and-never-delivered.md)'s boundary drop,
in the engine rather than at the language boundary.

`parameterProvenance` and `literatureSourcesUsed` are now kept per point.

## Decision

1. `SweepResult.finalValue` is `number | null`; failures carry `error`.
2. `analyzeSweep` and `analyzeSensitivity` compute over points that both
   validated **and** produced a value, and report `pointsAnalyzed` /
   `pointsExcluded` so a reader can see how much of the grid the numbers
   rest on.
3. When nothing is analysable, both **refuse**: every statistic is `null`
   and an `unanalysableReason` says why. Previously `analyzeSweep` returned
   zeros, which present a failure as a result — the same inversion as the
   crashed point scoring perfectly, one level up.
4. `optimalParameterIndex` is deleted, with a guard.
5. The sweep CSV carries an ADR 0050-style `#` provenance header, separating
   **SWEPT** parameters (an experimenter's choice, needing no citation —
   ADR 0012/0013) from those **HELD CONSTANT** (measured quantities, which
   must carry their source).
6. Every summary line in every exporter is now `#`-prefixed.

### The summary blocks were breaking the file they described

`exportSweepToCSV`, `exportBatchToCSV` and `exportComparisonToCSV` each
appended a summary as bare `key,value` rows *below* the data — rows with a
different column count than the header. The new provenance header tells the
reader to parse with `comment="#"`, which would then hit those rows and
mis-parse or throw.

Found by a test asserting one data row per sweep point, which got 11. Worth
recording: the header made a promise about the file, and the file did not
keep it. Fourteen lines across three exporters are now comment-prefixed.

## Mutation testing

| # | mutation | first run | after |
|---|---|---|---|
| M1 | crash recorded as `0` again | **0 failed** | 1 |
| M2 | `parameterProvenance` dropped again | 1 | — |
| M3 | `analyzeSweep` stops checking `validated` | **0 failed** | 1 |
| M4 | `optimalParameterIndex` reintroduced | 1 | — |
| M5 | `analyzeSensitivity` back to `finalValue \|\| 0` | 3 | — |
| M6 | a summary row escapes back into the data | 1 | — |
| M7 | swept parameter listed as HELD CONSTANT | **0 failed** | 1 |

Three of seven survived the first pass. Each was a real gap, and the three
are different in an instructive way.

### M1 — the fix had no test, only its consequence did

Twenty-three tests passed with the crash sentinel restored. Every one of
them builds the `results` array by hand and passes it to `analyzeSweep`;
none runs `runSweep`. The line that *produces* the record was never
executed.

`analyzeSweep`'s filter was still excluding the point, so behaviour stayed
correct — defence in depth working. That is not the same as the fix being
tested, and it would have stopped being true the moment anyone read the
sentinel as harmless.

`parameter-sweep-failure-record.test.ts` runs `runSweep` against a mocked
pipeline that throws on demand. M1 now fails 1 test.

### M3 — a guard that looked redundant against the fixtures

Removing the `validated` check passed all 23 tests, because in every fixture
a point with `validated: false` also had `finalValue: null`. The null check
alone sufficed, so `validated` looked like a belt-and-braces line.

It is not. `scientificPipeline` returns `finalValue: simulationOutput.finalValue || 0`
with an empty trajectory when validation fails, so a point can genuinely
arrive **validated: false with finalValue: 0** — it ran, it returned a
number, it did not validate. Null-checking alone lets that through, and 0 is
the minimum, so it wins the sweep. The original defect returning through a
different door.

This is the ADR 0033/0045 case, not the ADR 0050 case: unreachable *against
the current fixtures*, not unreachable in principle. So it was tested
against the state the type permits, and M3 now fails 1 test.

My own comment above the filter already claimed *"Both conditions are
required and neither implies the other."* It was right, and untested.
Asserting a property in a comment is how it stops getting checked.

### M7 — the provenance block could state something false

Listing the swept parameter under HELD CONSTANT passed every other test.
The two blocks make different claims: HELD CONSTANT says "this did not move,
and here is its source", and `km` moved across the entire sweep by design.
Printing `km = 1 [user]` there is a false statement about the experiment, in
the block a reader consults *because* they want to know what was varied.

## Consequences

- `analyzeSweep`'s return type is nullable throughout. One existing test
  asserted `meanFinalValue === 0` for an empty sweep and was updated: a
  sweep with no points has no mean, and 0 is a number a reader would plot.
- `analyzeSensitivity` requires `validated === true` rather than
  `!== false`, so a point that does not say whether it ran is excluded. Its
  test fixtures were updated to resemble `runSweep` output — the
  [ADR 0056](0056-a-column-that-claimed-a-source.md) lesson applied
  immediately after learning it.
- A bulk edit adding `validated: true` to every sweep fixture in that file
  also hit the one test that deliberately omits it, silently converting it
  into a duplicate of the happy path. Caught, reverted, and the fixture now
  carries a comment saying not to.
- Quote-aware CSV reading moved to `csvTestHelpers.ts`. `line.split(',')`
  produced a wrong assertion three times in that directory, always on a
  column sitting after the JSON-serialised `parameters` cell. Rewriting the
  splitter per file is what let it happen three times.

## What this does not fix

`compareJobs` and `compareMultipleJobs` still read
`job.result?.finalValue || 0`, so a job with no result compares as a real
zero. Same defect class, different function, and a change to comparison
semantics rather than a bug fix — named here rather than half-done.

`/api/export/stats/csv`, `/api/export/batch/:id/csv` and
`/api/export/comparison/:id/csv` still carry no citations. Their summary
blocks are now comment-safe, but the provenance work of item 5 has only been
done for the sweep.

## Related

- [ADR 0050](0050-the-file-that-leaves-the-building.md) — the `#` header
  design this reuses
- [ADR 0056](0056-a-column-that-claimed-a-source.md) — the export route
  audit that led here
- [ADR 0027](0027-one-reliability-score-not-two.md) — delete the duplicate,
  do not bypass it
- [ADR 0039](0039-computed-and-never-delivered.md) — computed and dropped at
  a boundary
