# ADR 0050: The file that leaves the building

**Status:** Accepted

**Date:** 2026-08-14

**Context:** `GET /api/simulate/:jobId/export`

## The defect

The export route's own docstring described it as *"great for researchers who
want to import results into R, Python, or Excel."*

It returned a header row and numbers. Nothing else.

No citation. No organism. No pH or temperature. No indication that the Km
came from a mutant, from a different tissue, or from another species. In a
project whose entire claim is that every number traces to a source, the one
file a student actually takes away had no source on it at all.

Every other surface Caterva has is attached to a session that ends. The CLI
warning scrolls past. The API `flags` array is discarded with the response.
The Antimony comment is read once, at the moment of generation. The CSV is
the artifact that **outlives the session** — it gets opened in Excel, plotted,
pasted into a lab report, and mailed to a supervisor three months later.

That is the worst possible place to drop provenance, because a plot in a
finished report cannot be re-interrogated. By the time the number is being
argued about, the context that qualified it is gone and there is no way back
to it.

This is the same defect class as [ADR 0039](0039-computed-and-never-delivered.md)
— a fact computed correctly and never delivered — at the surface where the
consequence is least recoverable.

## Decision

`buildTrajectoryCsv` (`src/lib/trajectoryCsv.ts`) prepends a `#`-commented
provenance header to the export:

- run id, domain, completion time
- `PARAMETERS AND WHERE THEY CAME FROM` — for each parameter: value,
  `[origin]`, citation, organism, assay conditions, and the `note` that
  explains a refusal
- `MODEL CITATIONS`
- `WHAT TO KNOW ABOUT THESE NUMBERS` — every resolver flag, verbatim
- a line telling the reader how to skip all of it

## Why `#` comment lines

CSV has no comment standard, so this is a trade-off and it deserves its
reason stated.

| consumer | behaviour |
|---|---|
| `pandas.read_csv(path, comment="#")` | skips them |
| `read.csv(path, comment.char="#")` | skips them |
| Excel | shows them as rows down column A |

The Excel case is the one worth arguing about, and it is why `#` won: a
student opening this in Excel **sees** the provenance. A sidecar
`.provenance.json` would parse more cleanly and would be separated from its
data the first time anybody emailed one of the two files. The provenance has
to be inside the artifact that travels, or it does not travel.

Stripping the `#` lines yields byte-identical data to the previous export, so
no existing consumer breaks. A test asserts exactly that.

## What it refuses to do

It does not summarise, rank, or soften. Every flag the resolver produced is
written out in full, including the pool-level findings of
[ADR 0033](0033-half-an-experiment.md), [0035](0035-a-pool-that-mixes-enzyme-forms.md) and
[0037](0037-the-organism-column-is-not-the-source.md).

A header that quietly dropped the inconvenient flags would be worse than no
header, because it would look complete. That is the same rule as
[ADR 0029](0029-a-mutants-constant-is-not-the-enzymes.md): a reader who sees no variant line assumes wild
type, so absence must be spelled, not implied. `origin ?? "unknown"` exists
for the identical reason — a parameter with no provenance entry must not read
as resolved.

## Mutation testing

Seven mutations against `src/__tests__/trajectoryCsv.test.ts`:

| # | mutation | tests failed |
|---|---|---|
| C1 | drop the header entirely | 9 |
| C2 | describe only resolved parameters | 3 |
| C3 | drop `note` | 2 |
| C4 | emit only the first flag | 1 |
| C6 | missing provenance reads as `resolved` | 1 |
| C7 | empty-string field loses the header | 1 |
| C5 | remove `.replace(/\r?\n/g, " ")` | **0** |

### C5, and the sixth branch that cannot fail

C5 was not caught, and the reason was not a weak test. The line was dead.
`commentLines` ran two substitutions in sequence:

```ts
.replace(/\r?\n/g, " ")
.replace(/\s+/g, " ")
```

`\s` matches `\n` in JavaScript, so the second substitution already did the
whole job. The first could never change an output. No test could fail it,
because removing it changed nothing.

Per [ADR 0033](0033-half-an-experiment.md) and
[ADR 0045](0045-a-guard-for-the-boundary.md), the standing rule is that an
unreachable branch gets tested at a level where it *can* fail rather than
deleted. That rule does not apply here, and the distinction matters:

- In 0033 and 0045 the branch was unreachable **because the extractor does
  not yet emit that state**. The type permits it, a future extractor will
  produce it, and the guard is load-bearing the day it does. Those are tested
  against the state the type allows.
- Here the branch was unreachable **because a second line already covered
  it unconditionally**. There is no future input that reaches it. It is not
  early — it is redundant.

So it was deleted, with a comment recording why, and the test was re-pointed
at the surviving mechanism. Re-running C5 against `.replace(/\s+/g, " ")` now
fails 1 test: the flattening is asserted where it is actually performed.

A dead line reads as load-bearing to the next person. Keeping it would have
meant two mechanisms for one job, only one of which works, with no test able
to tell them apart.

This is the sixth "check that cannot fail" found this cycle — after 0026's
origin filter, 0031's never-matched input, 0033's `unstated` filter, and both
of 0045's. Five were premature and got tests. This one was redundant and got
deleted. Mutation testing is what distinguishes the two; reading the code
does not, because both look like a line that is doing something.

## Consequences

- The exported CSV is now self-describing. A supervisor reading a plot three
  months later can get back to BRENDA ref 740253.
- Consumers using `comment="#"` are unaffected; consumers that were not
  skipping comments will see the header as leading rows. This is a
  deliberate, breaking-ish change to a route that previously made a promise
  ("great for researchers") it did not keep.
- `buildTrajectoryCsv` is exported separately from the route so it is
  testable without an HTTP server. The route it replaced was untested for
  exactly that reason.

## Related

- [ADR 0039](0039-computed-and-never-delivered.md) — same defect class,
  different surface
- [ADR 0045](0045-a-guard-for-the-boundary.md) — the guard that catches this
  class automatically
- [ADR 0049](0049-a-refusal-still-owes-you-what-it-found.md) — a refusal that
  cannot say what it refused, which is this problem for the not-found path
