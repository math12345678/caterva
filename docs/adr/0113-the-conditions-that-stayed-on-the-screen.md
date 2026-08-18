# ADR 0113: The conditions that stayed on the screen

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Terium/core/sbml_provenance.py`, `Terium/core/model_provenance.py`,
`scripts/export_annotated_model.py`, `src/cli/exportArtifacts.ts`,
`src/cli/commandSimulateResolved.ts`

**Relates to:** ADR 0010 (STRENDA conditions parsed), ADR 0026 (pH and
temperature), ADR 0028 (buffer identity), ADR 0032 (cofactors)

## The finding

Lisa Jeske's answer on what makes a resolved value meaningless:

> Reaction conditions: pH value, temperature, cofactors, and buffers play a
> huge role in the reactions. The values in BRENDA come from thousands of
> different papers, each with different laboratory conditions. If you
> simply mix these together, the simulation will end up calculating with
> "fantasy numbers".

Four ADRs answer that sentence. The conditions are parsed, graded, rendered
on the terminal and compared across parameters by `assayCoherence.ts`.

They were not in the exported model. Measured — the notes on an exported Km:

```
Measured in Homo sapiens. Source: BRENDA ref 740253
Reliability, graded on separate axes because they are not commensurable:
  assay completeness: complete — pH and temperature both reported
```

The file tells a reader the conditions **exist** and never says what they
were. Worse than absent: "complete — pH and temperature both reported" reads
as though the document contains them.

The artifact is the thing that outlives the terminal session. It is shared,
attached to a report, opened months later by somebody who never saw the
screen. It is therefore exactly where Jeske's sentence needed to survive,
and it was the one place it did not.

This is also Herbert Sauro's mechanism, unfinished. `export_annotated_model.py`
exists because of his sentence — *"write a warning comment in the antimony
file you generate"* — and the comment it wrote could not tell a reader
whether two parameters came from compatible experiments.

## Decision

`assay_ph`, `assay_temperature_c`, `assay_buffer` and `assay_unreported`
travel on both provenance types and are rendered in **both** exports.

Both, deliberately. The Antimony file and the SBML notes are artifacts a
reader may receive independently, and a fact present in one and missing from
the other is worse than one absent from both: it makes the omission look
like a property of the measurement rather than of the export path.

### `unreported` is carried, not inferred

`assay_ph=None` is ambiguous between *the paper did not report it* and *this
export did not carry it*, and those are facts about different people. An
omitted line reads as an oversight by whoever produced the file; a line
saying the source is silent is a statement about the publication, which is
what ADR 0010 exists to preserve.

A condition cannot be both stated and unreported: the renderers drop from
`unreported` anything they hold a value for, because hand-assembled payloads
arrive in that shape and a document contradicting itself in adjacent
sentences teaches a reader to believe neither.

### The grade and the values are reconciled

The notes now carry both an "assay completeness: complete" grade and the
conditions themselves — two encodings of one fact in one document, which is
ADR 0003's subject. They can disagree two ways, and the two get different
sentences because they are defects in different places:

- **The source was silent and the grade still says complete.** The grade is
  wrong. The note says which to trust: *"a grade is a summary, and this is
  the thing summarised."*
- **The conditions never reached this export.** The grade may be right and
  the file cannot show its working. The note says that instead of implying
  a contradiction that does not exist.

## The mutation that escaped

The first round of tests built their own `ModelExportRequest` and asserted
the written file carried the conditions. Four tests, all green — and
deleting

```ts
assayConditions: row.assayConditions,
```

from the CLI's provenance builder left all four passing. They proved the
export path worked and could not prove anything ever filled it in.

That is precisely what `literatureResolver.ts` records about
`bufferIdentity` — resolved for months, dropped because the receiving type
had no field, and invisible because "the rendering tests mock
`resolveKinetic`, so they assert what the CLI does with an object rather
than whether the object is ever populated. Deleting the plumbing left all
fourteen of them passing."

`assayConditionsReachTheExport.test.ts` starts at a mocked resolver and
finishes at the bytes on disk. Both plumbing mutations now fail it.

## Consequences

- A student who exports a model and shares it hands over a file that says
  what each number was measured under, and which conditions the source
  never stated.
- Two readers can now compare two exported models for the "fantasy numbers"
  risk without either of them having run the query.
- Seven mutations across the two languages, all caught: dropping the
  rendered conditions, omitting the unreported list, removing the
  contradiction dedup, collapsing the two discrepancy sentences, dropping
  the Antimony footer line, and the two plumbing cuts above.
- `_assay_number` refuses to coerce: a payload carrying `"ph": "unknown"`
  yields no pH rather than `0.0`, which is a legal pH and would read as a
  measurement.
