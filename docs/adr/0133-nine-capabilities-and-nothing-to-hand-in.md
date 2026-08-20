# ADR 0133: Nine capabilities and nothing to hand in

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `Tests/lab_report.py`, `scripts/report_lab.py`,
`src/cli/scientificCLI.ts`

**Relates to:** ADR 0124 (`catalog`, the command before this one), ADR 0111
and ADR 0129 (the ensembles this quotes), ADR 0113 (the assay conditions it
carries)

## The problem, stated by the owner

> Terrium is a tool. People should use Terrium.

Terrium could, separately: resolve a literature value, record its
provenance, parse the assay conditions it was measured under, grade it on
Bakker's axes, run an ensemble across values the evidence cannot rank,
export BibTeX and RIS, write an annotated SBML model, build a COMBINE
archive, and integrate the system.

**Nine capabilities, and nothing a person could hand to a teacher.**

Every one of them answers a question nobody asks in isolation. A student in
a teaching lab has one job — run the simulation, and show where the numbers
came from — and Terrium could do both halves while leaving them to assemble
the result from a terminal transcript, two export files and a screen they
had already scrolled past.

This is not a missing feature. It is nine features that were never joined
up, which is a harder problem to see, because every part of it passes its
own tests.

## Decision

`scientific report --ec N --organism O --substrate S [--out PATH]` produces
one document:

1. **Parameters** — value, unit, origin, citation. Values the student chose
   are in the same table, marked **yours**, with the sentence *"a value
   marked yours describes the experiment, not the enzyme."*
2. **Conditions the values were measured under** — pH, temperature, buffer,
   and which of those the source did not report.
3. **Where the literature disagrees** — the ensemble, with each candidate
   value and what the model does at it.
4. **What Terrium would not do.**
5. **Result** — first and last row of the trajectory, and a pointer to the
   CSV for the rest. A lab report is not a data dump.
6. **Citations** — BibTeX, ready for a reference manager.

### Section 4 is the reason this exists

Every other tool's output is what it managed to produce. A refusal that
appears nowhere is indistinguishable from a question nobody asked, and the
student can neither act on it nor defend the gap to a teacher.

So an unsourced parameter is not skipped — it becomes a line with the
reason and the remedy: a value exists in another organism and was not
substituted; the name matched more than one EC number; the substrate name
matched nothing though the enzyme reports these others; the value returned
was measured on an immobilised enzyme. The report is honest about its own
limits in the one place a reader will look.

### Nothing is restated

Every sentence about a value comes from the module that owns that value's
reasoning. The ensemble paragraph is `spread_consequence`'s `reason`
**quoted verbatim** — a test asserts `verdict.reason in markdown`, so a
paraphrase fails. Two renderers of one fact drift, and this repository has
spent most of its effort on instances of exactly that.

## What mutation caught, including in my own tests

Six mutations, all caught after two test repairs:

- Skipping unsourced parameters — the printout behaviour this exists to
  replace.
- Paraphrasing the ensemble reason instead of quoting it.
- Presenting supplied values as literature-sourced.
- Dropping the substrate hint from a refusal.
- Dumping the whole trajectory.
- Calling an empty report defensible.

**The third escaped first.** `test_a_value_the_student_chose_is_marked_as_theirs`
asserted `"**yours**" in text`, and labelling supplied values `literature`
in the table left it green — because the explanatory sentence *below* the
table contains the words "A value marked **yours** describes the
experiment". The assertion matched prose that is always present. It now
reads the `| s0 |` row.

That is the third time this session that explanatory prose has handed a
test something to match for free (see ADR 0128). The pattern is worth
naming: **when the output being tested contains an explanation of itself,
document-wide `contains` is not an assertion.** Assert on the row, the
line, or the field.

## Consequences

- There is now one command whose output is the thing the user came for.
- `catalog` and `report` compose: the report's refusal names `catalog` and
  the exact label BRENDA uses, so an incomplete request teaches the next
  one.
- `flagValue` returns undefined rather than the next flag, so
  `--out --json` cannot write a file called `--json`. A jest test pins it.
- Not yet done: the report does not embed the trajectory it describes
  unless a caller supplies one, and the CLI does not yet run the simulation
  as part of `report`. The section renders and is tested; wiring the engine
  into this command is the next step and is small.
