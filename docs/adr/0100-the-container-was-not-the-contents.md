# ADR 0100: The container was not the contents

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `scripts/check_findings_reach_a_surface.py`,
`docs/mutations/adr-0045-boundary-guard.json`

**Follows:** [ADR 0045](0045-a-guard-for-the-boundary.md), the guard amended
here, and [ADR 0039](0039-computed-and-never-delivered.md), the defect it
exists for.

## A true number about the wrong question

The boundary guard has been reporting:

```
Fields on KineticResult:        26
Reaching a rendering surface:   26
Stopping short:                 0
```

Every one of those statements is true. All of them are about
`KineticResult`'s **own attributes**, and the findings this project spent
twenty passes building are not attributes — they are nested objects.
`selection_tie` counted as delivered because a surface named `selectionTie`.
`SelectionTie` carries `candidates`, `reason`, `low`, `high` and
`fold_range`, and the guard had no opinion about any of them.

Descending one level finds **71 nested fields under 26**. The guard was
measuring 26 of 97 and printing a number that read like 97 of 97.

This is the **presence of a container taken as evidence about its
contents**, and it is the third place this project has found that exact
half-check:

- [ADR 0090](0090-the-capability-nobody-could-reach.md) — a baseline whose
  matcher could not see classes, so it held two thirds of one decision and
  looked complete.
- [ADR 0098](0098-evidence-the-guard-could-not-recognise.md) — a set file
  judged runnable because `test` and `mutations` were present, with nothing
  asked about the entries inside.
- Here.

## The cause was written in the code, as a comment

The guard measures delivery by **executing** the runner against a fully
populated fixture (ADR 0045: name matching passed while the emission was
deleted). The fixture builder said:

```python
if "list" in ann:
    continue  # empty list still emits its key
```

True of the key. False of everything inside it. `poolFindings
.effectorContrasts` emitted as `[]` proves the container travels and says
nothing about `compound`, `reason`, `present_values` or `absent_values`.

The sentence explaining why the lists were left empty is a precise statement
of the blind spot, sitting in the file, for as long as the guard has
existed. It was written by someone answering the shallow question well.

## What could and could not be established

The fixture now populates nested models recursively (`model_construct`, so a
validator rejecting a dummy string cannot turn a question about *delivery*
into a question about *plausibility*).

It was not enough. **The runner rebuilds its lists rather than forwarding
them**, so `poolFindings.effectorContrasts` still emerges empty and the
emitted JSON contains those containers with nothing inside.

So 71 fields cannot be judged by this probe. Both available answers are
wrong:

- *undelivered* — 71 **false accusations**, which is precisely
  [ADR 0051](0051-the-evidence-did-not-choose-the-value.md) and
  [ADR 0056](0056-a-column-that-claimed-a-source.md): a patch that did not
  apply, read as a test that did not catch. A false accusation costs more
  than silence, because it teaches people the guard is wrong.
- *delivered* — the blind spot, restored, now with a bigger number in front
  of it.

They are a third state: **not measurable by this probe**, counted and named.
The success line was narrowed to match, because a guard whose OK message is
wider than its measurement is the shape this whole file exists to catch:

```
OK: all 26 MEASURABLE fields reach a reader or are recorded as internal.
    71 nested field(s) were not measured; see above. This is not a
    statement that they are delivered.
```

## The third state swallowed the defect the guard exists for

Within a minute of adding it, the mutation set said:

> **G1: the runner stops emitting poolFindings (ADR 0039's original defect)
> … NOT CAUGHT**

`is_measurable` was testing the **wire path**. `effector_contrasts` is a
top-level field whose alias is the dotted `poolFindings.effectorContrasts`;
deleting that emission emptied the set of measurable parents, so the field
was reclassified "not measurable" and skipped.

**The new state excused the exact defect the guard was built for — and the
excuse grew stronger the more thoroughly the emission was deleted.** A
guard that gets quieter as the bug gets worse.

Nesting is now decided by the **model path**: a fact about the schema, which
breaking the runner cannot change.

This is the strongest argument yet for mutation-testing every guard change,
including one that looks like added rigour. The third state was added *to
make the guard more honest*, and for about four minutes it made it blind.

### The mutation that could not be a mutation

G2 was first written as a mutation reverting that line, and came back **NOT
CAUGHT** — correctly. The weakness is *conditional on G1*: with the emission
intact, the wire-path version changes no output at all. A no-op mutation
cannot be caught, and recording it as caught would be a verdict the harness
never established.

`is_measurable` was therefore lifted to module level, where the invariant
can be asserted directly rather than reached through a full runner
execution, and `--selftest` states it: with an **empty** set of measurable
parents — the worst case, a runner emitting nothing nested — no top-level
field is excused. Two further cases pin what the third state is *for*, so a
"fix" that deleted it would not pass.

Only then did G2 become expressible. It is now caught.

| # | mutation | result |
|---|---|---|
| G1 | the runner stops emitting `poolFindings` | caught |
| G2 | "not measurable" decided by the wire path | caught |

`python3 scripts/mutate.py --set docs/mutations/adr-0045-boundary-guard.json`

## What the 71 are, and why this is not closed

They are the insides of `Citation`, `Relatedness`, `SelectionTie`,
`SelectedForm`, `EffectorContrast`, `FormMixture`, `OrganismDiscrepancy`,
`SourceMixture`, `SourceCheckUnavailable`, `LiteratureCandidate`,
`Preparation` and `Variant` — every finding built for Jeske's and Bakker's
feedback.

Hand-inspection while writing this found the pattern is mostly *prose
carriage*: `selectionTieFlags` renders `tie.reason`, and the reason string
embeds the spread, so `low`/`high`/`fold_range` reach a student as English
while never reaching a surface as data. That is delivery, and it is also
why `literatureResolver.ts` re-declares narrowed shapes such as
`Array<{ compound: string; reason: string }>` — fields absent from those
declarations cannot be rendered at all, without a type error to say so.

Which of the 71 are prose-carried and which are genuinely dropped is a
question this pass **states rather than answers**. Answering it means
making the runner's rebuilt lists measurable, which is a change to the
runner, not to the guard. Recorded as a count somebody can decide about,
which is the same arrangement as the mutation-table debt (ADR 0072) and the
unwired exports (ADR 0090).

## Consequences

- The guard now reports three numbers where it reported two, and the third
  is the honest one.
- It stays exit 0. A known, stated, counted gap must not turn a shared build
  red; a red guard is one people learn to skip.
- `--selftest` is wired into `verify_build.py` beside the guard.
- The next step is the runner's rebuilt lists, not more guard.

## Related

- [ADR 0045](0045-a-guard-for-the-boundary.md) — the guard, and why it
  executes rather than reads
- [ADR 0039](0039-computed-and-never-delivered.md) — the drop it protects
- [ADR 0090](0090-the-capability-nobody-could-reach.md),
  [ADR 0098](0098-evidence-the-guard-could-not-recognise.md) — the same
  half-check, twice before
- [ADR 0051](0051-the-evidence-did-not-choose-the-value.md),
  [ADR 0056](0056-a-column-that-claimed-a-source.md) — why a false
  accusation was not an option
