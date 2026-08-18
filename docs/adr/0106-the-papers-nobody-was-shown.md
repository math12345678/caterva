# ADR 0106: The papers nobody was shown

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts`,
`src/lib/provenance.ts`, `scripts/check_findings_reach_a_surface.py`

**Follows:** [ADR 0104](0104-the-title-of-the-paper.md), which left 31
verdicts resting on ambiguous leaf names and named the next step: teach the
last hop to see the parent.

## Teaching the last hop to see the parent

The surface check matched a bare leaf name anywhere in three files. It now
requires a **surface function that both names the parent and reads the leaf
as a member** — `c.reference_id`, `x["title"]`, `{ title: ... }`, not the
bare word in a comment.

| | before | after |
|---|---|---|
| reaching a rendering surface | 38 | **69** |
| verdict not trustworthy | 31 | **1** |

The member-reference requirement is what makes it worth having: block-scope
co-occurrence alone resolved 31, and tightening to a real property access
put two back into "unknown" that co-occurrence had cleared by accident.
Stated plainly in the code — this is stronger evidence than a file-wide
match, and it is **not proof**: nothing here understands scope. So it can
only move a field from *unknown* to *delivered*, never from *undelivered* to
anything.

The splitter is guarded too. If it ever produces fewer than two blocks, the
guard fails rather than resolving every ambiguity against the whole file —
which would be the file-wide matching this replaces, wearing the new name.

## What the last unresolved ambiguity was hiding

Three of the four survivors were `literature_candidates.source/title/url`.
Chasing them found this:

> `literatureCandidates` had **two** non-test references in the entire tree
> — the interface declaration and an empty-array initialiser. **Nothing read
> it.**

When BRENDA holds no value, `fallback_logic.py` does not stop. It searches
PubMed and CORE, and on a hit returns `source: "literature_candidates"` with
the list attached — the fallback whose entire job is the case where the
primary path failed. The runner emits it faithfully on two branches. The
TypeScript declares it.

And a student asking for a constant BRENDA does not carry was told *"could
not be resolved from literature"* while the system held papers that probably
report it, fetched at the cost of two API calls.

That is [ADR 0039](0039-computed-and-never-delivered.md)'s defect on the one
path that exists to help when everything else failed. It is also Bakker's
principle inverted — *do not exclude anything a priori* — and excluding the
entire remaining evidence base by not mentioning it is the most complete
exclusion available.

### My own baseline entry asserted a renderer that did not exist

The previous pass filed these with the note *"the CLI renders its own
summary of them from the structured array"*. It does not. I wrote a claim I
had not looked for, into the file whose whole purpose is recording decisions
somebody checked. Left in the baseline as a correction rather than deleted.

## A flag would have reached nobody either

The first fix pushed a flag, and every test case came back empty. A probe
showed why: when a kinetic constant cannot be resolved **and was not
supplied, `resolveQuery` throws**. There is no response, so there are no
flags. The papers were unreachable by construction on the exact path where
they matter, and a flag-based fix would have been a second delivery that
delivered nothing.

The offer belongs in the refusal, because the refusal is the message telling
the student to go and find the value themselves.

`missingKeyDetails` already promotes a per-key note into that error, and
that mechanism exists for precisely this reasoning, in its own words:

> Telling a user the literature has nothing, when it has something they
> could have had by flipping a flag, is the true-sounding-and-misleading
> shape this project treats as a defect everywhere else.

Terrium holding papers it does not mention is that sentence again, so
`unresolvedReason` gains `literature_candidates`. Every other member of that
union means *a value existed and Terrium declined it*; this one means *no
value, but here is where to look* — and it belongs there for the same
reason, because it makes the generic sentence false by omission. **The
literature was not silent. Nobody read it out.**

## The test caught the regression the code warned about

Promoting a note **drops the generic sentence** — and the generic sentence
is where `Add km=<value> to your query` lives. Attaching the offer therefore
removed the one instruction a student can act on. `missingKeyDetails`'s own
comment records that regression happening once before, and it happened again
here, and the test caught it rather than the comment:

```
it("still tells them how to supply the value themselves")
  expect(message).toMatch(/km=/);   →  failed
```

The note now restates the instruction, and the `--cite` flag with it, so a
value the student finds is recorded rather than lost.

Titles carry a locator each, and which one differs by source: PubMed's
esummary never supplies a DOI, CORE has no PMID. Covering one silently drops
half the offers' provenance — a title with no locator is a claim, a title
with one is checkable.

## Verification

- 6 new tests; 118 pass across the five affected files; `tsc` clean.
- Reachability guard: 69 delivered, 1 not trustworthy, 10 reviewed stops,
  18 unmeasurable. Exit 0.
- The remaining ambiguity is `selected_form.value`, verified by hand as
  prose-carried inside `form.reason` and baselined as such.

## Consequences

- A student who hits a genuine gap is now handed the papers instead of a
  refusal that pretends the literature is empty.
- `literature_candidates.*` removed from the baseline; the wrong note kept
  as a correction.
- The scope check clears fields, never condemns them. That asymmetry is the
  reason it can be trusted at all.

## Related

- [ADR 0104](0104-the-title-of-the-paper.md) — the ambiguity this resolves
- [ADR 0039](0039-computed-and-never-delivered.md) — computed, transported,
  dropped
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) —
  refusing without saying what you are holding
