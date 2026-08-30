# ADR 0150: Units — the file states itself

**Status:** Accepted (claimed before it was true — see the note below)

**Date:** row written circa 2026-08-19 claiming completed work; the work
itself and this document, 2026-08-29

## A note on this record's history, which is the interesting part

This number's index row claimed: *"The exported SBML declared no units at
all — libSBML: 15 consistency warnings. Now **0**."* There was no
document, and — measured through the real exporter on 2026-08-23 — **the
count was still 15**. The row described work that did not exist, in the
past tense, in the one place this project uses to cite its own reasoning.

Three audit passes left it red on purpose (the guards kept failing on the
dead link) with the resolution stated as a choice: *implement the units,
or retract the row.* This document is the implement branch. The row's
claims are now true and re-derivable; the fact that they were written
first is recorded here, because an ADR that quietly became true is
exactly as misleading in retrospect as one that quietly stayed false.

## Context

After ADR 0146 the exported values were right and the file still declared
nothing. libSBML with unit-consistency checking on reported **15
problems** on the smallest exported model (13 unit-consistency, 2
modelling-practice): no time unit, no extent units, no compartment units,
no species substance units, no parameter units.

The last finding was not a missing declaration but a real dimensional
error: Antimony's kinetic law evaluates in **concentration/time**, and
SBML defines a reaction rate as **substance/time**. The two coincide only
at the builders' 1-litre compartment — wrong in a way that computed the
right answer everywhere anyone had looked.

## Decision

`Terium/core/sbml_units.py::declare_units` — the one module that writes
`unitDefinition`s. Per-row unit strings arrive from the CLI's provenance
entries (`ExportProvenance.unit`, threaded through in the same change:
`ParameterProvenance.unit` existed all along and the export interface
dropped it). The module owns the vocabulary (mirroring
`src/units.ts`), rate detection from the unit string (`mM` vs `mM/s`),
the case fold shared with `annotate_sbml`, the one-system check, and
per-parameter completeness.

**Everything or nothing.** A refusal returns the document byte-identical
with itemised reasons (`unitsRefused`), delivered through the exporter's
detail dict to the CLI, which prints the three-state verdict. Refused,
with the reason named: an unknown unit; mixed concentration scales; a
non-per-second rate; a non-second stated time base; any parameter with no
supplied unit; and every domain outside the mm family — SIR species are
population counts, and declaring molar units on them would be a confident
lie.

**The dimensional fix:** every kinetic law is multiplied by the
compartment (mmol/L/s × L = mmol/s), and numeric literals are declared
`dimensionless` (the `1` in the competitive `(1 + I/Ki)` was the last
finding standing, [99505]). At size 1 the rewrite is numerically
invisible — asserted by integrating both documents and comparing every
point exactly, not by trusting the comment that says so.

`.omex` inherits all of it: the archive path is built on `build_sbml`.

## Verification

`Terium/tests/test_sbml_units.py` (11 tests): **15 → 0** for the MM model
asserted at both ends; **0** for competitive including the literal;
bit-exact trajectory equivalence under roadrunner for both domains;
every refusal direction; byte-identical documents on refusal; the scale
attribute checked against the stated unit — libSBML cannot catch a
thousandfold scale lie, because 10⁻³ and 10⁻⁶ mole are the same
dimension; and the exporter seam end-to-end.

```
python3 scripts/mutate.py --set docs/mutations/adr-0150-units-declared.json
```

| id | mutation | result |
|---|---|---|
| U1 | kinetic law no longer multiplied by the compartment | caught |
| U2 | a missing parameter unit silently tolerated | caught |
| U3 | wrong scale written for every concentration | caught |
| U4 | exporter drops the verdict, reports everything declared | caught |

`4 caught, 0 not caught, 0 indeterminate`. U1 is the subtle one: the
equivalence test *keeps passing* under it (removing ×1.0 changes no
number); what catches it is the declared file no longer reaching 0.
The harness returned INDETERMINATE once — a find-string from an earlier
revision of a file two agents were editing live — and refused to grade an
unmutated tree, which was correct.

**Co-authorship, stated plainly:** the module and this feature were built
by two agents concurrently, colliding on the same files (the exporter
briefly carried each author's signature against the other's module, twice
each way). The resolution, coordinated through a claim file in the
repository — the only channel — was: module one author's verbatim, wiring
and delivery the other's, tests and this record written after the pair
went quiescent. The (alice)-marked literal-units block inside the
kinetic-law pass is the one cross-boundary edit, and it is marked because
unmarked co-authorship is how the row-with-no-document happened.

## Consequences

A consumer's tool now checks the units instead of trusting the notes.
What is still refused rather than solved: any domain outside the mm
family exports with units undeclared and the reason named — the epidemic
models' unit system is a decision nobody has made, and this module will
not make it by default.
