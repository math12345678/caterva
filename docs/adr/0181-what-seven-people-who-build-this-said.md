# ADR 0181: What seven people who build these tools said

**Status:** Accepted, partially implemented. **Two design questions are left
open for the owner** — see "Not decided here".

**Date:** 2026-08-25

**Context:** `Tests/lab_report.py`, `Terium/core/model_provenance.py`,
`Terium/core/combine_archive.py`, `scripts/export_annotated_model.py`

## Context

Seven researchers who build simulation, standards and curation tools were
asked directly about Terrium's design and all seven replied. Their answers
are the first outside evidence this project has had, and two of them
contradict its central thesis.

Recorded here because a private mailbox is not a place a design decision can
be checked from, and because the two contradictions should not quietly
evaporate.

## What was confirmed

**The COMBINE/SBML shape is right.** Frank Bergmann (SED-ML, COMBINE
archive) was asked whether SED-ML should carry per-parameter provenance:

> SED-ML is not intended to carry provenance reports. […] IMO there is no
> good place to put disagreements between sources in a computer readable
> way. Thus I'd currently recommend to keep most such information in notes.
> Using CVTerms in the suggested way sort of changes the semantic intent of
> CVTerms, as tools reading them would expect them to be ontology-based not
> a form of provenance.

Terrium already does this and for the stated reason: CVTerms carry only
things with resolvable identifiers (`bqbiol:isDescribedBy` a publication,
`bqbiol:hasTaxon` an organism — which is MIRIAM's actual use), prose goes in
notes. `sbml_provenance.py`'s "Why both, rather than CVTerms alone" section
is the same argument, reached independently.

**Antimony has an answer for the readable half.** Lucian Smith:

> the correct way to add human-readable text to an element is to use
> 'notes': `a notes "Smith 1998, pH 7.4, 30 C, rat liver"`

## What was implemented

**1. The reproducibility claim was addressed to a reader who cannot act on
it.** Jonathan Karr (BioSimulators):

> If your source code is private, Git hashes will only be useful to you
> because other people won't know what they mean.

The repositories are private and staying that way (ADR 0179), and the
report told *every* reader to "check out that commit and re-run" — in the
one section whose job is to say how the numbers can be checked. It now says
who can follow the instruction, and states plainly that for anyone else the
hash identifies code they cannot obtain.

Karr's second point is also now in the document: a hash pins code, not
environment. Terrium pins its dependencies, which is what makes the claim
worth making at all, but those pins are in `requirements.txt` and not in the
report — so it claims reproducibility of the code and not of the stack a
container would capture.

**2. The archive gained the entry Bergmann named.** He recommended an OMEX
containing model, experiment, "some kind of structured format of your
provenance report (could be json, markdown, anything really)", and the rest.
The archive had the first two and kept provenance only in notes, whose
weakness he named exactly: "this makes automated extraction difficult".

`provenance.json` is rendered from **the same dict that writes the SBML
notes** — passed out of `build_sbml` rather than rebuilt in `build_archive`,
because a second construction from the same payload would agree today and
drift the first time one learned a field. A structured report disagreeing
with the model shipped beside it would be worse than none: a consumer would
parse the easy one and get an answer the simulation never used. The test
asserts the agreement, on the reference id rather than the word "BRENDA",
which appears in the surrounding prose and would match either way (ADR 0128).

Eduard Kerkhoven (Yeast-GEM) arrived at the same file from the other side:

> It is essential though that the metadata is provided in flat-text format,
> so that Git can easily diff any changes that are made, instead of
> recording the whole set of metadata anew with each release.

Hence sorted keys and one field per line.

It is labelled `application/json` and carries a `_note` saying it is not a
COMBINE standard, because it is not one.

## Not decided here

**Two experts contradicted the refusal thesis, and this record does not
resolve it.** Ursula Kummer (COPASI), asked whether refusing to run without
a literature value is defensible:

> there is a rather clear answer to that question: Yes, it is certainly
> better to have an estimated parameter than nothing at all.

Her reasons are not about convenience. You will not find a reasonably sized
system with every parameter known; Km values are "often measured in vitro
under non-physiological conditions […] so in most cases, these are not the
real values anyway"; and — the argument that bites hardest — **some
parameters carry no control over the system at all, and without initial
values you cannot find out which.** Refusing to run does not merely withhold
an answer; it withholds the sensitivity analysis that would show the
parameter did not matter.

Ron Milo declined a general rule and proposed a shape instead:

> I would tend to allow using rough numbers, but when supplying the results
> give them a very clear different "form" using color or the like that would
> be connected to a clear statement of how they were derived.

Olaf Wolkenhauer endorsed provenance-first and put it in sequence: a
sourced model is "a starting point […] There is no true or correct model",
and the insight comes from revising it, sensitivity analysis included.

John Gennari supplied the mechanism that would make Milo's "different form"
rigorous — **evidence codes**, as the Gene Ontology uses them, to mark
whether an annotation was curated or computed. Terrium's four origins
(`resolved` / `user` / `llm` / `default`) are already an evidence-code
system in everything but name and standardisation.

A synthesis is available — keep refusal as the default, allow an explicitly
graded estimate, and mark it with something GO-shaped — but **which
default a teaching tool should ship is the owner's decision, not a
mechanical consequence of this feedback, and it is not made here.** Nothing
in this commit changes what Terrium refuses.

## Consequences

- Every report now says who can check it, which for a private repository is
  a smaller set than "the reader".
- An `.omex` now carries provenance a program can read, agreeing by
  construction with the model beside it.
- The project has outside evidence for the first time, including
  disagreement, on the record rather than in a mailbox.

**What this does not check.**

- ~~**Nobody has opened the archive in COPASI or Tellurium.**~~
  **Tellurium has, on 2026-08-28** — see
  [ADR 0189](0189-a-tool-that-did-not-write-it.md).
  `te.executeCombineArchive()` opened the archive, resolved all four SED-ML
  data generators against the model and ran the recorded time course.
  COPASI is still untried.
- **`provenance.json` is not a standard** and nothing consumes it yet. It
  is a format invented here because, in Bergmann's words, there is currently
  no good computer-readable place for source disagreement.
- ~~**The Antimony `notes` syntax Smith gave is not implemented.**~~
  **Closed by
  [ADR 0182](0182-the-provenance-that-did-not-survive-being-used.md),** and
  it was worse than unimplemented. Every parameter's provenance was written
  as comments, and comments do not survive a conversion — measured in both
  directions. The assay conditions, which decide whether two published
  values may legitimately be compared, were the first thing discarded.
- **Evidence codes are not adopted**, only noted as the answer to a
  question this project already half-solved.