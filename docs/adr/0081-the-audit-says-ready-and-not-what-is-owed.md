# ADR 0081: The audit says "ready" without saying what is owed

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0080 (the database belongs in the bibliography), ADR 0079
(one licence table, two languages), ADR 0063 (attribution travels with the
model), and Jeske's CC BY 4.0 obligations

## Context

`GET /api/simulate/:jobId/audit` is described in the route as a
*"Publication-ready audit of parameter provenance"* and returns:

```json
{ "publicationReady": true, "overallConfidence": 0.9, "parameterAudits": [...] }
```

`publicationReady` is computed as `blockedParameters.length === 0` — a green
light for putting these numbers in a paper.

It reported per-parameter DOIs, PMIDs and STRENDA verdicts, and **said
nothing about what publishing the data obliges.** `NOTICE` is explicit:

> If you use BRENDA data in scientific work, cite BRENDA's current
> publication […] **Citing Caterva is not a substitute for citing BRENDA.**

So the one surface in the system that judges publication-readiness was
silent on the requirements of publication.

This completes a sweep that began with ADR 0063. Every artifact that leaves
Caterva carrying BRENDA-derived values has now been checked: the Antimony
model, the SBML, the trajectory CSV, the BibTeX/RIS bibliography, and this.
Each was missing something different, and each was found only by looking at
the artifact rather than at the code that builds it.

## Decision

`AuditReport` gains `dataSourceObligations`: for every source that supplied
a value in **this** run, the creator, licence, licence URI, source URI, and
the citation the source asks for.

Derived from `docs/data-sources.json` (ADR 0079), so the obligation stated
here cannot drift from the licence stated in the exported model, SBML and
CSV.

### What `publicationReady` still means

Unchanged. It remains `blockedParameters.length === 0`.

Folding "has the user cited BRENDA?" into it was considered and rejected:
Caterva cannot observe whether a citation was made, and a boolean that
silently incorporates an unobservable condition is a guess wearing the
costume of a check. The obligations are reported *alongside* the verdict for
a person to act on, which is the honest division — the same reasoning ADR
0024 uses for refusing to default an unsourced parameter.

### Nothing is invented

NCBI Taxonomy is in the table with `citation_request: null` because `NOTICE`
says NCBI *"asks to be cited but does not require it as a licence
condition"* — recording that request is a separate decision, and guessing at
it would put a fabricated obligation in front of someone about to publish.

#### Correction: this ADR first claimed behaviour the code did not have

As accepted, this section read:

> A source with no recorded `citation_request` produces no obligation.

**That was false.** `citationObligations` filtered on `source !== null`, not
on `citation_request`, so a run using NCBI Taxonomy produced an entry with
`citationRequest: null`. The ADR described a filter that was never written.

The test meant to cover it was worse:

```ts
it("omits a source with no recorded citation request ...", () => {
  const ncbi = loadDataSources().find((s) => s.tokens.includes("ncbi"));
  expect(ncbi?.citation_request).toBeNull();
});
```

It asserts a field of the JSON table and never calls the function whose
behaviour its name describes. It could not fail for the reason it claimed,
and it passed while the paragraph above it was wrong.

**The code was right and the ADR was wrong.** A source that contributed
should be *listed*: a reader about to publish should know NCBI Taxonomy was
used, even though it requires no citation. Filtering it out to match the
prose would have removed real information to preserve a sentence.

What was genuinely missing is a statement of what each source *requires*,
rather than a `null` the reader must interpret. `requirement` is now
three-valued:

| value | meaning |
|---|---|
| `cite` | the source asks to be cited; `citationRequest` says how |
| `none` | its terms are recorded and require no citation |
| `unknown` | Caterva has no record of its terms |

`none` and `unknown` both carry `citationRequest: null`, so a reader
inferring from that field alone cannot tell "nothing is owed" from "we do
not know what is owed". Collapsing those two is this project's most
frequently recurring defect, and it had reappeared in the field added to
warn people about their obligations.

Found by re-reading my own work an hour after writing it — not by a guard,
a test, or a reviewer.

A source that contributed nothing to this run is not listed. An obligation
to cite data the run did not use is a false one, and under CC BY 4.0
§2(a)(6) it is the endorsement the licence forbids implying.

## Verification

Four new tests in `src/__tests__/dataSources.test.ts` (14 total), and one in
`routes.test.ts` asserting the field reaches the **live HTTP response**
rather than merely being computable.

That last one is deliberate. Every "computed and not delivered" defect this
project has recorded — ADR 0027, 0038, 0039, 0047 — was a value that existed
correctly one layer below the surface a reader sees, and a unit test on the
builder would have passed in every one of those cases.

Two mutations, both caught:

| Mutation | Failures |
|---|---|
| obligations reported for every described source, contributed or not | 2 |
| the citation request dropped from the obligation | 1 |

And on the three-state `requirement`, in
`src/__tests__/dataSourceObligations.test.ts` (5):

| Mutation | Failures |
|---|---|
| `none` and `unknown` collapse into one state | 1 |
| a no-citation source is omitted entirely (*what this ADR first claimed*) | 2 |
| `cite` reported without the request text | 2 |

The middle row is the point: the behaviour the ADR originally described now
*fails the suite*. The prose was not merely wrong, it was wrong in a
direction that would have removed information from a reader about to
publish.

## Consequences

- A client rendering the audit can show the reader what to cite. Whether it
  does is the client's decision; the data is no longer missing.
- Adding a source with a `citation_request` to `docs/data-sources.json`
  enrols it in the audit, the bibliography, and all three file exports at
  once.
- The audit response grows a field. It is additive, and the existing route
  test asserted five specific properties rather than an exact shape, so no
  consumer contract is broken.
- **Not addressed:** whether NCBI's citation request should be recorded.
  That needs NCBI's own wording, which this environment cannot reach, and
  inventing it is precisely what this ADR refuses.
