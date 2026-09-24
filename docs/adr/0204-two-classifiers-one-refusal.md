# ADR 0204: Two classifiers, one refusal

**Status:** Accepted
**Date:** 2026-09-24

## Context

Two sessions changed the same function without seeing each other's work, and
the merge was the first time either change met the other.

This branch had **extracted** keyword classification out of `resolveQuery`
into `classifyDomainByKeyword()`, because `routes/simulate.ts` needed to
record what a student had asked *before* resolution ran (ADR 0196). Logging
the question is the whole point of that record -- including the questions
that end in a refusal -- so the extracted function had to answer for any
query at all, and could not throw.

Main had **grown** the same classification in place:

- parameter-override tokens (`km=2`, `vmax=5`) stripped before scoring, so
  that inline parameter syntax stops inflating `mm` over
  `mm_competitive_inhibition` on a query that explicitly said "competitive
  inhibition";
- a real `matchEnzyme()` hit treated as classification evidence (+2 to `mm`,
  +1 to `mm_competitive_inhibition`), removing a second hardcoded list of
  the same ~25 enzymes;
- and, most importantly, **`UnrecognizedQueryError` instead of a fallback**.
  Classification used to land on whatever domain sat first in
  `DOMAIN_DEFAULTS` when nothing matched, so "predator and prey populations"
  quietly received an enzyme-kinetics simulation with the mismatch invisible
  in the response.

Both sides also added SIR vocabulary, disjointly: main added named diseases
(`measles`, `pertussis`, `mpox`, ...), this branch added compartment and
outcome words (`susceptible`, `herd immunity`, `attack rate`, `wave`).

The two are not alternatives. Main's is the better classifier; this branch's
is the shape the logging caller needs. Taking either side whole would have
lost something real: main's side would have dropped the caller, this
branch's side would have restored a silent fallback that main had just
removed on purpose.

## Decision

One function, with main's logic, and the refusal moved one layer out.

`classifyDomainByKeyword()` keeps main's stripping, enzyme boost and
scoring, then applies this branch's `resolveNesting()` to the winner, and
returns `{ defaults, matched }`. It does not throw. When nothing matched it
reports `matched: false`; the returned defaults are a placeholder, not a
guess anyone is entitled to run.

`resolveQuery()` -- the path that actually simulates -- turns
`matched: false` into the `UnrecognizedQueryError` main introduced. The
refusal is unchanged in behaviour and unchanged in strength; it simply lives
at the caller that resolves rather than inside the function that classifies.

The keyword lists are the union of both sides.

`routes/simulate.ts` takes `classifyDomainByKeyword` from the same deferred
`await import("../lib/queryResolver")` that main introduced for
`resolveQuery`, rather than importing it statically. A static import of the
same module would have pulled the resolution graph back in at module load
and quietly undone main's deferral.

## Consequences

The distinction that matters is preserved: **refusing to classify and
refusing to run are different events.** A question Terrium cannot place is
still recorded as having been asked -- that is exactly the question the
query log exists to count -- and is still refused rather than simulated as
something else.

The risk taken here is that the two sides' tests were written against two
different scorers: `nestedDomains.test.ts` against this branch's
length-weighted scoring, `domainClassification.test.ts` and
`competitiveInhibitionDomain.test.ts` against main's count-based scoring
with the enzyme boost. Main's scorer was kept. **This was not verified
locally**: `node` and the npm cache are unreachable from the environment
this merge was resolved in, so no TypeScript test in this repository was
executed here. CI is the first run of either suite against the merged
function, and any disagreement between the two test sets is a real finding
about the merge, not a flake.
