# ADR 0104: The title of the paper

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts`,
`scripts/check_findings_reach_a_surface.py`,
`docs/undelivered-fields-baseline.txt`

**Follows:** [ADR 0102](0102-the-probe-nobody-read.md), which found this and
deferred it with a cost written down. The cost was wrong.

## What a student was reading

```
BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27
```

`Citation.title` is resolved by the Python side, emitted by the runner, and
declared on the TypeScript interface. `formatResolvedCitation`'s parameter
type did not mention it, so the composer dropped it. In a tool whose entire
claim is that its values are literature-backed, **the one human-readable
part of the evidence was the part not shown** — the student could not tell
what paper backed the number without opening the link.

For the population-genetics and epidemiology paths this is worse than
cosmetic: there, `title` carries the whole formatted reference
(`popgen_result["citation"]`, `epi_result.citation`), so what was dropped
was the citation itself, leaving an accession number in its place.

Now:

```
BRENDA (ref 740253) "Kinetic properties of human lactate dehydrogenase
isoenzymes" — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27
```

## The deferral was made on a number that meant nothing

ADR 0102 deferred this, saying the display string is *"asserted verbatim in
21 places across 9 test files owned by other agents"*.

That was a count of assertions **on** the string, not of assertions that
would **change**. Not one of those fixtures carries a title, so appending it
broke none of them: 100 tests across `provenance.test.ts` and
`citeVerify.test.ts` passed unmodified. The real cost was one line and a new
test file.

Counting the thing that is easy to count and calling it the thing you meant
is how a small job stays undone. That is worth more than the fix, and it is
why the fix is in this pass rather than another one.

## Position is load-bearing

Three things parse this string — `/\(ref ([^)]*)\)/` in `provenance.ts` and
twice in `citeVerify.ts`, plus `split(' ')[0]` in the CLI's SBML annotator.
The title goes **after** the ref parenthesis and **before** the URL so every
one of them still matches the same span.

A title is also not a locator, and the `hasRef || hasUrl` gate stays
upstream of it: a citation carrying a beautifully descriptive name and
nothing to find it by is still unfindable, and must still degrade.

`locatableCitation`'s signature now declares `title` even though it never
reads it. The object is passed whole to the composer, so the title survived
through structural typing while being invisible in the signature — which is
how it came to be dropped in the first place. **A field that travels through
a function unnamed is one destructuring away from being lost again.**

## The first version of the test could not fail

It asserted on string constants spelling out what the formatter was believed
to produce. Six cases, all green, and every one of them would have stayed
green with the formatter unchanged — a test checking my expectation instead
of the code.

`formatResolvedCitation` is not exported, and exporting it to make it
testable would have moved the weakness one layer down: what matters is not
what the function returns, it is what lands in `parameterProvenance`. So the
mocked runner supplies a title and the real `resolveQuery` runs, with a
phrase nothing at that call site could invent — the same device
`reliabilityFromRunner.test.ts` uses.

Running it also corrected a second case. "A title does not make an
unlocatable citation locatable" was asserting only that the title was
absent; what actually happens is that the value degrades to unresolved and
the whole simulation is **refused** with `RequiredParametersMissingError`.
The weaker assertion would have passed with the gate moved below the title.
The test now asserts the refusal.

## Mutations

| # | mutation | result |
|---|---|---|
| T1 | the title stops being appended (the original defect) | caught |
| T2 | the title placed before the ref group, where the parsers read | caught |

`python3 scripts/mutate.py --set docs/mutations/adr-0104-citation-title.json`

**T3 was withdrawn, and why is a finding.** It moved the locator gate below
the title so a title-only citation would be admitted, and came back NOT
CAUGHT — correctly. `locatableCitation` has two independent gates: the
composer returning `undefined`, and `locators.length === 0`. A title-only
citation produces no locators either, so the second refuses it whatever the
first does. Mutating either alone changes no observable behaviour.

That is defence in depth a mutation **demonstrated** rather than assumed.
Recording it as NOT CAUGHT would have put a gap in the table that does not
exist — the same judgement as ADR 0100's G2.

## The guard acquitted a field it should not have

Fixing this made the reachability guard report `literature_candidates.title`
as delivered. Nothing about that field changed. The last hop is decided by
looking for a bare **leaf name** in the rendering surfaces, and the word
`title` now appears there — for an entirely different field, on a different
code path.

**A false acquittal is worse than the false accusations found last pass.**
An accusation gets investigated and corrected. An acquittal is the blind
spot restored, with the guard's blessing on it.

Leaf matching was defensible while the walk was flat, because
`KineticResult`'s own attributes are near-unique. Descending into nested
models (ADR 0100) made `title`, `reason`, `raw`, `status`, `source`,
`organism`, `unit`, `url`, `value`, `evidence`, `reference_id` and
`concentration_text` each belong to several fields — and nobody noticed,
because the consequence only appears when one of a colliding pair gets
wired.

An ambiguous leaf can no longer produce a "delivered" verdict:

```
Reaching a rendering surface:   38
Verdict not trustworthy:        31  (leaf name shared)
Stopping short:                 10  (10 reviewed, 0 not)
Not measurable by this probe:   18
```

**31 of the 69 deliveries the guard was asserting could not be
distinguished from a same-named sibling.** It had been confidently reporting
all of them. A stop is never reclassified as ambiguous — a field no surface
mentions at all is undelivered regardless of who shares its name — so this
can only ever weaken a pass, never excuse a failure.

Resolving one means checking its renderer by hand, or teaching the last hop
to see the parent. Neither is done here, and the guard says so.

## Consequences

- The paper's title reaches the reader. 7 tests, 2 mutations, both caught.
- `citation.title` is **removed** from the undelivered baseline rather than
  annotated: a baseline that only grows records problems instead of solving
  them.
- `literature_candidates.title/pmid` stay open, and deliberately without a
  hand-waved cost this time — nobody has measured that one either, and
  saying so is the point.
- The guard reports four states now. Only one of them is good news.

## Related

- [ADR 0102](0102-the-probe-nobody-read.md) — where this was found, and
  mis-costed
- [ADR 0100](0100-the-container-was-not-the-contents.md) — the descent that
  made leaf collisions matter
- [ADR 0010](0010-a-citation-must-be-locatable.md) — why a title is not a
  locator
- [ADR 0027](0027-one-reliability-score-not-two.md) — the pass-through test
  device reused here
