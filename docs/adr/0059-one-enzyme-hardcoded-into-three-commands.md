# ADR 0059: One enzyme, hardcoded into three commands

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0024 (never invent what you could not source), ADR 0055
(deleted `FALLBACK_PARAMETERS`, whose announcement survived it), ADR 0049
(the previous defect found by running the product)

## What was found

`scientific literature "acetylcholinesterase"` prints papers about **lactate
dehydrogenase**.

`commandLiterature()` took no arguments. Whatever the user typed was
discarded, and the body called:

```ts
const literature = await fetchRealLiterature('lactate dehydrogenase', 'lactate');
```

The `simulate --resolve` module header describes this exact call as the old
broken behaviour it replaced. It was replaced *on that path*. The same line
was still live in three other places:

| command | what it fetched | what it did with it |
|---|---|---|
| `literature <anything>` | LDH papers | printed them as the answer |
| `validate <anything>` | LDH papers | counted them as `Literature sources: N` |
| `simulate <anything>` | LDH papers | counted them as `Literature sources: N` |

The last two are worse than the first. `literatureSourcesUsed` is a
provenance count, and it was reporting another organism's enzyme's papers as
the backing for the user's own query.

## Decision

### The system is an argument, and it is required

`literature` now takes `<enzyme> --substrate S` and refuses without both,
with the reason `resolve` already gives: the system is never inferred from
free text, because attaching real papers to a system the user did not name is
provenance for the wrong measurement.

### `validate` and `simulate` fetch nothing

Wiring them to the user's enzyme was considered and rejected. Every entry
`fetchRealLiterature` builds carries `extractedParameters: []`, and every
consumer in `literatureService` reads exactly that field — so the fetch has
never contributed a single value to a verdict, for any enzyme. Pointing it at
the right enzyme would have produced a truthful-looking source count backing
nothing: the same illusion, harder to spot, and now with the tool's own
credibility behind it.

They report zero sources and point at `simulate --resolve`, which is the path
that actually resolves literature.

## The root cause was one layer down

Fixing the call sites exposed that `searchPubMedForEnzymeKinetics` could not
tell the two outcomes apart either. Three query strategies, every failure
branch a bare `continue`, and one error at the end for all of them:

> No real literature found on PubMed for "X" and "Y". The system requires
> verified papers from scientific databases. **Check your network access and
> verify this enzyme/substrate pair has published kinetics data.**

The sentence hedges because the code genuinely did not know which had
happened. A dead network, an NCBI 500, a captive-portal HTML page, and an
enzyme with genuinely no indexed papers all produced that one message — so a
network outage was reported to a student as "this enzyme has no literature".

That is an absence of evidence presented as evidence of absence, in a tool
whose `resolve` help text says, in as many words, that collapsing those two
"teaches you to read an absence of evidence as evidence of absence".

**A strategy that reached PubMed and got a well-formed answer is now counted.
A strategy that could not run is not.** If at least one completed, an empty
result is an answer and `[]` is returned. If none completed, nothing was
learned and `PubMedUnavailableError` is thrown.

The distinction is a **type**, not a phrase in a message. The moment it lives
in prose the only way to act on it is to match a substring, and a caller that
greps an error message is one rewording away from silently reclassifying "we
could not look" as "there is nothing there".

`literature` now exits 0 / 2 / 1 — found / searched and empty / could not
search — matching `resolve`.

## Three smaller things in the same command

1. **`Avg impact factor: 0.00` and `Avg citations: 0`** were printed on every
   run since the command existed. Nothing populates `impactFactor` or
   `citationCount` — PubMed's esummary carries neither — so `getStats()`
   averaged over zero entries and returned its `: 0` fallback. Both read as
   findings about the papers. The same zero-for-null inversion already
   corrected in the perf collector, the response cache and the sweep
   analyser, reached this time through a helper's default rather than a
   literal. Now not printed at all, with a line saying why; a permanent
   "unknown" field is one someone eventually fills in on the assumption that
   the plumbing works.

2. **"PubMed: 50+ million peer-reviewed papers"** sat ten lines below the
   code that deliberately sets `peerReviewed: false` *because PubMed indexes
   preprints, editorials, letters and retracted articles*. The blurb asserted
   precisely what the field refuses to. The round unsourced counts went with
   it.

3. **"No real papers found. Using default parameters."** ADR 0055 deleted
   `FALLBACK_PARAMETERS`; the sentence announcing them survived. A message
   promising defaults that are not applied teaches a reader to distrust a
   refusal that is working correctly — and if they believe it, they go
   looking for which numbers were slipped in.

## Consequences

- `src/integrations/__tests__/pubmedSearchOutcomes.test.ts` stubs `fetch` and
  pins each server behaviour to an outcome: empty result → `[]`; network
  throw, HTTP 500, and non-JSON body → `PubMedUnavailableError`. The
  non-JSON case is the captive-portal one — a coffee-shop wifi login page is
  a 200 that is not an answer, and parsing it as "no idlist, therefore no
  papers" is how a sign-in screen becomes a scientific finding.
- One test asserts the enzyme argument reaches the request URL and that
  `lactate` does not appear. That is the property the three call sites
  violated, stated directly.
- Mutation-tested: removing the `strategiesCompleted++` restores the old
  conflation and fails three tests, while the four unavailable-path tests
  keep passing — so the mutation is targeted rather than merely destructive.
- `src/web/server.ts` also calls the search. Its behaviour is unchanged, and
  its `Literature fetch failed` warning now fires only on real failures
  instead of also on empty results.
