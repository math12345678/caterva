# ADR 0102: The probe nobody read

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `scripts/check_findings_reach_a_surface.py`,
`docs/undelivered-fields-baseline.txt`

**Follows:** [ADR 0100](0100-the-container-was-not-the-contents.md), which
found 71 nested fields the guard had never asked about and closed by stating
that the next step was the runner, not more guard.

## The next step was the fixture

ADR 0100 said the runner "rebuilds its lists rather than forwarding them".
It does not:

```python
"poolFindings": {
    "effectorContrasts": [c.model_dump() for c in result.effector_contrasts],
```

That is a faithful pass-through. The empty lists were a statement about the
**fixture**, and the fixture was in a place nobody looked.

`_emitted_keys()` runs two subprocesses. The first builds a fully populated
`KineticResult`, monkeypatches `resolve_kinetic_value` with it — and then
exits. **Only its exit status is consulted.** Whatever it prints is
discarded; the patch dies with the process. The fixture that matters is
`cases`, in the *second* probe, and those were constructed by hand with
every nested finding left empty.

So ADR 0100's recursive populator went into the dead one. A whole probe
computing something no caller consumes, inside the guard written to detect
things computed and never consumed. The first probe is now what it always
was — an import check — and says so.

## What the measurement actually found, once it worked

| | before | after |
|---|---|---|
| reaching a rendering surface | 26 | **67** |
| stopping short | 0 | **12** (all reviewed) |
| not measurable | 71 | 18 |

The 18 that remain are the pool findings, whose emission depends on runner
branches the three cases do not reach. Still counted, still named, still not
claimed either way.

## Two false accusations, caught by checking rather than trusting

The first run reported 20 fields undelivered. **Eight of those were the
guard being wrong**, and this matters more than the twelve that were real: a
guard that cries wolf is one people learn to skip, which is the same
end-state as no guard at all.

### The wire mixes casing conventions

The runner camelCases the keys it writes by hand (`selectionTie`) and
`model_dump()` under them preserves the model's snake_case
(`reference_id`). The real emitted path is

```
selectionTie.candidates.reference_id
```

which is neither `selection_tie.candidates.reference_id` nor its all-camel
conversion. Testing those two forms reported `reference_id` as **never
emitted by the runner** — a field whose own docstring says it exists so that
"a named alternative is checkable and a bare number is not", and which
`selectionTieFlags` renders as `[ref N]`. Paths are now compared with case
and underscores removed, which asks the question actually being asked.

### The types live in a file the guard did not read

`scienceAgent.ts` does not declare the shapes. It imports them:

```ts
import type { BufferIdentity, Effector } from "./provenance";
```

So `Effector.raw`, `.compound_text`, `.presence`, `.concentration_text` and
`.identity` are fully declared, in the other file, and seven of them were
reported as never received by TypeScript. **A matcher whose scope is
narrower than the thing it measures does not report "I could not see", it
reports "it is not there."** That is ADR 0090's lesson — a baseline is only
as honest as the matcher that fills it — arriving from a third direction.

## The twelve that were real

Nine are **carried as prose**: `selection_tie.low/high/fold_range` sit
inside `SelectionTie.reason`, which `selectionTieFlags` prints verbatim into
`provenance.flags`; `relatedness.shared_rank/shared_name/query_organism/
candidate_organism` sit inside `RelatednessVerdict.reason` on the
`cross_species_too_distant` path — the branch Jeske asked for;
`selected_form.designator/sibling_designators` sit inside
`SelectedForm.reason`.

They reach a student, as English. They are not machine-readable, and the
baseline says so rather than letting "delivered" be read as "delivered as
data". Rewording them in TypeScript is deliberately not done: the client
would become a second place the sentence can drift, which `queryResolver.ts`
explicitly refuses to be.

Three are a **defect, recorded as one**:

> `formatResolvedCitation` composes `BRENDA (ref 740253) — https://…` and
> its parameter type does not declare `title`. The title is resolved,
> emitted, and typed, and a student sees a reference number instead of the
> name of the paper — in a tool whose entire claim is that its values are
> literature-backed.

It is **deferred, not accepted**, and the baseline says which. The display
string is asserted verbatim in 21 places across 9 test files owned by other
agents. Appending the title is safe for all three parsers of that string
(`/\(ref ([^)]*)\)/` twice, `split(' ')[0]` once), so the change is small
and the test churn is not. It belongs in its own pass rather than riding
along with a guard change — the same reasoning that keeps a nineteen-file
autofix from landing under somebody mid-edit.

Filing a real gap in a baseline whose header says *"a line here is a
DECISION"* would be using it as a mute button. So the file now has two
sections, and the second is titled *A real gap, deferred with the cost
stated*.

## Verification

The historical mutations still hold, which is the point of running them
after a change this size:

| # | mutation | result |
|---|---|---|
| G1 | the runner stops emitting `poolFindings` | caught |
| G2 | "not measurable" decided by the wire path | caught |

`--selftest` (5 cases) unchanged and green. The summary line was also split
— `Stopping short: 12 (12 reviewed, 0 not)` — because a bare "12" above an
"OK" is the same mismatch between a number and a verdict that this guard
exists to find.

## Consequences

- 67 of 97 fields are now measured to reach a reader, where 26 were.
- 18 remain unmeasurable; closing them needs runner branches the three
  fixture cases do not exercise. Counted, not claimed.
- `citation.title` is an open defect with a stated cost and a stated owner
  (the next pass). If that section is still there in a month, that is the
  answer to whether "deferred" meant anything.

## Related

- [ADR 0100](0100-the-container-was-not-the-contents.md) — the descent, and
  the wrong guess about why it did not work
- [ADR 0039](0039-computed-and-never-delivered.md) — computed and consumed
  by nobody, which the dead probe was an instance of
- [ADR 0090](0090-the-capability-nobody-could-reach.md) — a matcher narrower
  than what it measures
- [ADR 0051](0051-the-evidence-did-not-choose-the-value.md),
  [ADR 0056](0056-a-column-that-claimed-a-source.md) — why eight false
  accusations mattered more than twelve true ones
