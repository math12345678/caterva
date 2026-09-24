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

One function, with the union of both scorers, and the refusal moved one
layer out.

`classifyDomainByKeyword()` keeps main's parameter-token stripping and its
enzyme signal, and this branch's length-weighted scoring, negation awareness
and `resolveNesting()`. It returns `{ defaults, matched }` and does not
throw. When nothing matched it reports `matched: false`; the returned
defaults are a placeholder, not a guess anyone is entitled to run.

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

### Why the union, and not either scorer

The first attempt kept main's scorer whole and discarded this branch's.
That is what the evidence said to do -- main's was newer -- and it was
wrong. Measured against both sides' own assertions, it broke two things:

- **Negation (ADR 0192).** Main's `keywordMatches` is a substring-or-stem
  test with no negation awareness; this branch's `matchesTerm` filters
  occurrences that `isNegatedAt` marks. With main's, *"how the reaction
  speed changes as I add more substrate, no inhibitor involved"* classified
  as `mm_competitive_inhibition` -- the negation work undone outright, by a
  merge that had no opinion about negation at all.
- **Specificity (ADR 0190/0191).** Counting matched keywords rather than
  weighting them by length let *"a random trajectory for A + B to C using
  the Gillespie approach"* land on `molecular_dynamics`, which owns
  "trajectories", over a domain the query named outright.

So the scoring is length-weighted (this branch), the literal match is
negation-filtered (this branch), stemming is kept (main), and a **stem-only
match scores half**. That last is new to the merge. A stem match is real
evidence -- "measles spreads" is about the keyword "spread" -- but it is
weaker than the query having written the term, and scoring them equally is
exactly what let a stemmed plural outvote a named domain.

Main's enzyme signal is kept and restated in the new unit. Main gave `mm`
+2 and `mm_competitive_inhibition` +1, which are counts; under length
weighting a match is worth 5-15, so those numbers would have been noise.
The credit is now the matched enzyme's own name length, whole for `mm` and
half for `mm_competitive_inhibition` -- the same 2:1, in the unit every
other score uses, and defensible on its own terms: naming "lactate
dehydrogenase" *is* matching a long, specific term.

## Consequences

The distinction that matters is preserved: **refusing to classify and
refusing to run are different events.** A question Terrium cannot place is
still recorded as having been asked -- that is exactly the question the
query log exists to count -- and is still refused rather than simulated as
something else.

**This was measured, not reasoned about.** `node` and the npm cache are
unreachable in the environment this merge was resolved in, and the first
version of this record said so and left the merge unverified. That was
avoidable: `bun` is present, runs TypeScript directly, and needed exactly
one stub package (`pino`, which classification never calls) to import the
module. Every classification assertion in `nestedDomains.test.ts`,
`classifierEval.test.ts` and `domainClassification.test.ts` was then run
directly -- 22 cases, the three-state contract, the negation case and the
no-shared-terms invariant, all passing -- and the benchmark scores 53/53 on
the labelled set with the held-out split at least equalling dev, which is
the assertion `classifierEval` actually makes.

Still not run here: the parts of those suites that need `resolveQuery` end
to end (network, LLM, the mocked science agent) and every other api-server
suite. The lesson is narrower than "CI will tell me" and worth keeping:
**"the tests cannot run here" was a claim about the toolchain I had looked
for, not about the machine.**

See [ADR 0205](0205-an-enzyme-called-acc.md) for the defect this measurement
uncovered on the way past.
