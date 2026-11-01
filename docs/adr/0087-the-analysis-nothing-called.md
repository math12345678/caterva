# ADR 0087: The analysis nothing called

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `src/engine/model-comparison.ts`, `POST /api/compare`

## The defect

`rankModelsByFit` answers the most consequential question this codebase can
be asked: **which mechanism does my bench data support?** A student runs the
four kinetic models, measures a real final substrate concentration, and asks
which model matches.

It had **no production caller.** Written, tested, exported — and invoked by
nothing. `compareModelPair` likewise.

So the answer was computed by nobody and reached no one.

This is [ADR 0039](0039-computed-and-never-delivered.md)'s defect class at
the scale of a whole capability. 0039 was a field dropped at a language
boundary; this is an entire analysis that never had an entry point. And
[ADR 0045](0045-a-guard-for-the-boundary.md)'s guard cannot see it: that
walks `KineticResult` fields to a rendering surface, which is the same
question one level down.

It is also why [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md)
could sit inside this function unnoticed — a model that never ran ranking
**first**, because its fabricated `0` sat closest to a small experimental
value. A defect in code nobody calls has no symptoms.

**Named as open for five consecutive passes before being fixed.** That is
the same failure at the level of the record, and it is exactly what
[ADR 0085](0085-two-failures-are-not-an-agreement.md) was written about one
pass earlier.

## Decision

`POST /api/compare` accepts an optional `experimentalFinalValue`. When
present, the response carries a `fit` block: models ranked by
`|finalValue − experimental|`, plus the models excluded and why.

**Optional by design, and absent means absent.** An experimental value is a
number the experimenter measured. Caterva cannot resolve it from literature
and must not invent one, so its absence means *no fit ranking* — never a
default. That is ADR 0012/0013's measured-quantity-versus-experimental-
condition rule applied to an input rather than a parameter.

Non-finite input is refused for a sharper reason: `Math.abs(x - NaN)` is
NaN, `.sort()` on NaN comparisons leaves the array in input order, and the
result would **look like a ranking** while being an artefact of argument
order. The worst kind of wrong answer is a correctly shaped one.

## The test proved a copy of itself

The first version of this work put the decision inline in the route, and the
test file defined **its own copy** of the condition:

```ts
function fitFor(models, experimental) {
  return typeof experimental === 'number' && Number.isFinite(experimental)
    ? rankModelsByFit(models, experimental)
    : undefined;
}
```

Mutating the route then changed nothing the tests could see. The harness
reported **NOT CAUGHT** — a test written to prove the wiring, which proved
only that a local copy agreed with itself.

That is [ADR 0027](0027-one-reliability-score-not-two.md)'s
duplicate-source-of-truth defect, committed **inside a test written to
demonstrate delivery**. The reliability parity test deleted in 0027 failed
the same way: two implementations agreeing perfectly, on a question neither
was being asked.

The decision now lives in `fitRankingFor`, the route calls it, and the test
imports it — the same split as `buildTrajectoryCsv` in
[ADR 0050](0050-the-file-that-leaves-the-building.md), for the same reason:
a decision reachable only through an HTTP server is a decision nobody tests.

## Mutation testing

| # | mutation | before extraction | after |
|---|---|---|---|
| F1 | a non-finite measurement is ranked against | **NOT CAUGHT** | caught |
| F2 | a non-number measurement is coerced rather than refused | — | caught |

F1's first result is the finding, not the failure: it is what exposed the
duplicated condition. A mutation that cannot fail because the test tests
something else is the same shape as a check that cannot fail, moved from the
product into the test suite.

## Consequences

- `POST /api/compare` gains an optional request field and an optional
  response block. Callers that send nothing see byte-identical behaviour.
- `compareModelPair` **still has no production caller** and is not wired
  here. Wiring it would need a route that compares exactly two models, which
  nothing asks for yet; inventing a caller to satisfy a guard would be worse
  than the gap. Recorded rather than quietly fixed.
- Two runs were killed by the sandbox ceiling during this pass and both were
  recovered from the journal ([ADR 0074](0074-a-journal-that-crossed-sandboxes.md)),
  now the fourth and fifth times that mechanism has worked under real
  conditions.

## Related

- [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md) — the defect
  that lived in this function while nothing called it
- [ADR 0039](0039-computed-and-never-delivered.md) — computed and never
  delivered, one level down
- [ADR 0027](0027-one-reliability-score-not-two.md) — the duplicate the test
  reproduced
