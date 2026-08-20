# ADR 0137: The fixture a student does not have

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `Tests/fallback_logic.py`, `Tests/ensemble.py`,
`Tests/test_ensemble_live_path.py`, `src/cli/commandEnsemble.ts`

**Completes:** [ADR 0135](0135-the-band-reaches-a-person.md), which made the
ensemble a command and left it requiring a file nobody has.

## The command existed and could not be run

`scientific ensemble --fixture some-brenda-table.html` was the only way in.
A student does not have a saved BRENDA table — obtaining one means knowing
BRENDA's HTML structure well enough to save the right page.

So the flagship command was runnable by the people who built it and nobody
else. That is [ADR 0122](0122-fifteen-domains-nobody-could-find.md)'s
"capability nobody can reach", one level up: not hidden, just gated behind a
prerequisite the intended user cannot satisfy.

Now:

```
scientific ensemble --enzyme "lactate dehydrogenase" \
    --substrate pyruvate --seed 1 --simulate michaelis_menten
```

## Why this needed a change to the resolver, not just the command

The obvious fix — have `ensemble` call the resolver — does not work, and the
reason is the same one that kept the sampling unbuilt for a week.

`resolve_kinetic_value` returns a `KineticResult`: **one** value, plus a
`SelectionTie` whose candidates carry value, unit, organism, reference and
commentary. What they do not carry is `assay_ph`, `assay_temperature_c` or
`assay_unreported` — which is exactly what `score_reliability` grades on.

By the time a caller holds a result, the rows have been collapsed. Rebuilding
the scores downstream would mean re-parsing BRENDA: resolving the same query
twice, which is the duplicate-source-of-truth defect the selection function's
own comment already refuses one level up.

So `_best_evidenced` now returns the frontier alongside the winner and the
tie — for the reason its existing comment gives, extended one step:

> The tie is computed HERE, where `kept` exists […] Recomputing it at the
> call site would need the frontier again, and a second frontier is a second
> implementation.

and `KineticResult.ensemble_candidates` carries every surviving row with the
grades `score_reliability` produced. **One implementation, not two** — a test
asserts the candidate grades match what that function returns directly, which
is where drift would show.

## The dependency runs one way

`ensemble_candidates` holds plain dicts, not `ensemble.Candidate` objects.
Building the objects in the resolver would make the literature layer import
the sampler — backwards, since the sampler is what consumes resolutions, and
a circular import waiting to happen.

`candidates_from_scored` is the adapter, on the sampler's side of that line.
A test reads `fallback_logic.py` and asserts it contains no import of
`ensemble`, so the line stays where it is.

## One BRENDA request, not one per draw

The live path runs the ordinary resolver: the same `resolve_kinetic_value`
behind `scientific resolve`, hitting BRENDA exactly once. The ensemble then
draws from the frontier that resolution already scored, so **sampling two
thousand times costs no additional requests**.

That is not an optimisation, it is the constraint. Lisa Jeske asked that
tools be gentle with BRENDA's servers, and a command that re-queried per draw
would be the opposite — two thousand requests to answer one question.

`--fixture` is kept, and not as a legacy path: it is offline, deterministic,
and what every test uses. The help text now says which is which.

## What "no ensemble" means

An empty `ensemble_candidates` is *nothing was resolved*, and the caller
reports it as a resolution failure. It is never a band with no members, and
`sample_ensemble` raises rather than returning an empty result — pinned by
two tests, because the difference between "the literature has nothing" and
"the ensemble is empty" is exactly the kind of collapse this repository keeps
finding.

The `len(entries) < 2` early return yields a **one-row** frontier rather than
an empty one, for the same reason: an ensemble over a single measurement is a
legitimate if narrow ensemble, and an empty list there would read downstream
as a failed resolution.

## Verification

**78 tests** across the four affected suites, all passing, including the 36
pre-existing `fallback_logic` tests that guard the resolver this changed.

10 are new and specific to the join. The ones that matter most:

| | |
|---|---|
| the winner does not replace the others | `min()` returns 0.03; 0.398 must still be in the pool, or there is nothing to weigh |
| grades match `score_reliability` directly | one implementation, and this is where drift would show |
| `fallback_logic` imports no ensemble | the dependency direction, asserted rather than assumed |
| nothing resolved → no candidates → raise | a failed resolution is not an empty band |

Network is stubbed at the provider seam the resolver already exposes — the
same seam `test_fallback_logic.py` uses — so the real resolution logic runs
without touching BRENDA.

## Consequences

- The flagship command is runnable by the person it is for.
- Every resolution now carries its scored frontier, whether or not anybody
  samples it. That is a few dicts on a result object, and it is what makes
  the ensemble possible from any caller — including the API route, which is
  still the outstanding piece.
- `condition_proximity` grades `not_assessed` for every row on this path: the
  physiological reference is a runner-level input the resolver never sees.
  Honest, and it costs the weighting nothing, because an axis where every
  candidate scores alike cancels under normalisation.

## Related

- [ADR 0135](0135-the-band-reaches-a-person.md) — the command
- [ADR 0122](0122-fifteen-domains-nobody-could-find.md) — the reachability
  rule this follows
- [ADR 0027](0027-one-reliability-score-not-two.md) — why the grades come
  from `score_reliability` rather than a second grader
