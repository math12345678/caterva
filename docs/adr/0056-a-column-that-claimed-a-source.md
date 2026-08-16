# ADR 0056: A column that claimed a source

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Context:** `GET /api/export/jobs/csv`, `src/storage/csv-exporter.ts`

**Follows:** [ADR 0050](0050-the-file-that-leaves-the-building.md), which put
provenance on the *other* CSV route and prompted the question "how many
export routes are there?" The answer was six.

## The defect

The job-history export had a column named `literatureFound`. Its value:

```ts
row.push(escapeCsvField((job.result?.validated || false) ? 'yes' : 'no'));
```

`validated` does not mean what that column name claims, and the codebase
already said so. From `src/cli/scientificCLI.ts`:

> `validated: false` no longer means "unbacked" — **a run on entirely
> user-supplied values validates fine** and simply scores zero confidence.
> It now means the run could not be performed at all.

So: a student types `km=5.2` from memory, runs a simulation, exports the job
history, and the file says **`literatureFound = yes`**.

That is a false claim of provenance, in a downloadable file, produced by the
tool whose entire premise is that every number traces to a source. It is the
exact inverse of the `user_cited` discipline adopted for Sauro's feedback:
there, a number with a real source was losing it, and the fix was to carry
the source while marking it unverified. Here a number with *no* source
acquires one by passing through Terrium.

Of the two directions, this is the damaging one. A lost citation is a gap
the reader can see. A manufactured one is a gap the reader cannot.

**The honest number was one field away.** The pipeline response already
carries `metadata.literatureSourcesUsed`, a real count, and `server.ts`
stores the response verbatim. The exporter reached past it for a boolean
that means something else.

## The second defect, found by the same probe

`finalValue` and `confidence` were **blank on every real job**, for the life
of the route.

`scientificPipeline.runSimulation` returns:

```ts
{ validated, validationConfidence, results: { finalValue, ... },
  parameterProvenance, metadata: { literatureSourcesUsed, ... } }
```

The exporter read `job.result.finalValue` and `job.result.confidence`.
Neither exists on that object. Verified by running the real exporter against
the real shape before changing anything:

```
jobId,query,status,startTime,endTime,durationMs,finalValue,confidence,validated,parameters,literatureFound
job_real,michaelis-menten,complete,...,1,,,true,"{""km"":5.2,...}",yes
```

Two empty cells where 2.34 and 0.95 were sitting in the record, and `yes`
next to a `literatureSourcesUsed` of 0.

## Why nineteen tests did not catch it

The fixtures in `csv-exporter.test.ts` are:

```ts
result: { finalValue: 2.34, confidence: 0.95, validated: true }
```

A flat shape the pipeline never produces. The tests asserted that the
exporter reads the fixture correctly, and it does. Nothing asked whether the
fixture resembles production.

This is [ADR 0027](0027-one-reliability-score-not-two.md)'s blindness in a
different file: *a test that agrees with the code about a question
production never asks.* There, two graders agreed perfectly because both
received an argument the API server never supplies. Here, exporter and
fixture agree perfectly on a shape the pipeline never emits.

The fix for that class is not a sharper assertion. It is **a fixture
transcribed from the producer's own `return` statement**, which is what
`csv-exporter-production-shape.test.ts` is. Its header comment says where
the shape came from and instructs the next person to update it from
`scientificPipeline.ts` rather than from whatever makes the tests pass.

## Decision

1. `literatureFound` → **`literatureSourcesUsed`**, carrying
   `metadata.literatureSourcesUsed`. A breaking rename, deliberately: the
   old column made a false claim, and preserving it for compatibility
   preserves the claim.
2. Absent count renders as **`unknown`, never `0`**. A record predating the
   field, or a job that errored before metadata was assembled, did not find
   zero sources — nobody looked. This is the three-state discipline of
   [ADR 0037](0037-the-organism-column-is-not-the-source.md): "could not
   check" must never render as "checked, and there was nothing."
3. `finalValue` and `confidence` read the nested location first and fall
   back to the flat one.

### Why both shapes, rather than fixing the fixtures

The flat shape is real. `src/engine/parameter-sweep.ts` flattens correctly
at the point it builds a sweep result:

```ts
finalValue: response.results?.finalValue || 0,
confidence: response.validationConfidence,
```

so `exportSweepToCSV` reading `result.finalValue` is **right**, and was
never broken. Checked before assuming the defect generalised — it did not.
Only the jobs route stores a raw pipeline response.

## Mutation testing

| # | mutation | tests failed |
|---|---|---|
| J1 | literature column derived from `validated` again | 4 |
| J2 | `unknown` rendered as `0` | 1 |
| J3 | `finalValue` read from the flat path only | 2 |
| J4 | flat-shape fallback dropped | 2 |

J1's strongest catch is the test that exports two jobs identical in
literature (both zero sources) and opposite in `validated`, then asserts the
two literature cells are equal. Any re-derivation from `validated` fails it,
including one written by someone who has not read this ADR.

### The test helper made the same mistake as the code

The first `columnValue` helper was `line.split(',')`, with a comment
asserting that every column under test sat before the JSON-quoted
`parameters` cell. `literatureSourcesUsed` sits *after* it, so three
assertions compared against a fragment of a serialised parameter object —
`"vmax":12.8` instead of `unknown`.

A helper carrying a confident comment that the data does not honour, inside
a test file about a column carrying a confident claim the data does not
honour. Replaced with a quote-aware splitter rather than by reordering the
columns to suit the helper.

### An interrupted mutation run left a mutation in the tree

A batched mutation loop hit the sandbox's per-call timeout mid-iteration and
left J2 applied — `unknown` silently rendering as `0` in the working tree.

Same failure as the `/tmp`-not-writable incident recorded earlier: the
restore never ran, and nothing announced it. Caught because the next command
was an integrity grep for mutation residue rather than a test run, which
would have gone green and said nothing.

Mutations are now run **one per call**, each with its own verified restore,
and the batching is not worth the risk of the tree keeping a mutation.

## Consequences

- Anyone reading `literatureFound` breaks. Documented in `docs/API.md` with
  the reason, not just the rename.
- Two columns that were always empty now carry values, which will look like
  new data appearing in an old report. It is not new; it was always there.
- `resultField` exists as a shape-tolerant reader. It is a smell, and the
  right long-term fix is one shape. That is out of scope here and is not
  pretended otherwise: the stored `job.result` is `any`, and typing it is a
  change across `server.ts`, the database, and every consumer.

## Related

- [ADR 0050](0050-the-file-that-leaves-the-building.md) — the sibling route,
  and the reason this one was looked at
- [ADR 0027](0027-one-reliability-score-not-two.md) — the same test
  blindness, in a different file
- [ADR 0037](0037-the-organism-column-is-not-the-source.md) — three-state
  discipline; `unknown` is not `0`
