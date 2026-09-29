# ADR 0182: The provenance that did not survive being used

**Status:** Accepted, implemented

**Date:** 2026-08-25

**Context:** `Terium/core/model_provenance.py`,
`Terium/tests/test_model_provenance.py`

**Closes a gap named in:** [ADR 0181](0181-what-seven-people-who-build-this-said.md)

## Context

Terrium's Antimony export wrote every parameter's provenance into the file
as `//` comments: a trailing comment on each assignment, and a
"PROVENANCE IN FULL" block at the end carrying citation, organism, and the
assay conditions the measurement was made under.

**None of it survived being loaded into a tool.**

Lucian Smith, asked where per-parameter provenance should live in Antimony
given that a comment is the intuitive place (personal communication,
2026-08-25):

> the correct way to add human-readable text to an element is to use
> 'notes':
>
>     a = 3
>     a notes "Smith 1998, pH 7.4, 30 C, rat liver"

Measured against the antimony library rather than taken on trust — the same
model carrying a comment and a note on one parameter:

| | comment | note |
|---|---|---|
| Antimony → SBML | **gone** | present |
| Antimony → SBML → Antimony | **gone** | present |

So the export whose entire purpose is that a value travels with its source
was handing over a file that lost the source the first time anyone used it.
A student reading the `.ant` file saw the citations; the moment they opened
it in Tellurium or COPASI they had bare numbers with no indication anything
had been removed.

**The worst of it was the assay conditions.** pH, temperature, buffer and
what the source failed to report lived *only* in the footer block — comments
— and those are the fields that decide whether two published values may
legitimately be compared at all. They were the first thing discarded.

## Decision

**Emit an Antimony `notes` statement for every parameter, alongside the
comments.**

The comment is for the person reading the file; the note is the only part
that survives being used. Both are rendered from the same
`ParameterProvenance` in one pass, so they cannot disagree.

The note carries the **full** record — exactly the footer's
`[origin]` + `detail_lines()` rendering, one rendering reused rather than a
third one invented — because the inline summary omits the assay conditions,
and those were the point.

**Unsourced parameters get a note too.** This file's header states the rule:
*"an absent comment would read as approval, so there is never one."* That
holds after a conversion only if the marker survives. Without it a converted
model arrives with citations on every parameter except one, and silence
beside a number surrounded by sourced ones is the strongest endorsement the
file could give it.

**Quotes are replaced, not escaped.** Antimony has no escape for `"` inside
a notes string — `\"` is a syntax error, measured, not assumed. A citation
containing a quotation mark would otherwise produce a model file that will
not load, and a tool that emits a broken model is worse than one that emits
a plain number: the failure arrives later and somewhere else.

`strip_annotations` removes the notes as well, matched as a whole line
rather than by containment, so a model that legitimately carries its own
notes is not misreported.

## Verification

Four tests, all going through the real library, since the claim is about
what a conversion keeps:

- **Both directions.** The note survives and the comment does not. Asserting
  only the first would pass on a library that preserved everything, and
  would not establish that the comment this project used for months was
  being discarded.
- Every assay field — `pH 7.4`, `30 C`, `phosphate`, `cofactors` — plus the
  citation and organism, present after a full round trip.
- `NO PROVENANCE RECORDED` survives.
- A citation containing `"` still produces a model that loads.

The invariant `strip_annotations(annotated) == original` still holds, and
still means what it says: `annotated_model_still_translates_to_sbml`
compares **parsed** models through libSBML, so "annotation does not change
what the model computes" is checked against the parser and not against our
own inverse.

41/41 guards green.

## Consequences

- An exported model keeps its provenance when someone opens it in the tools
  it was exported for, which is the only condition under which the export
  was ever worth anything.
- The assay conditions travel, so a downstream reader can still tell whether
  the value applies to their system.

**What this does not check.**

- **No tool other than antimony/libSBML has opened one of these files.**
  COPASI and Tellurium read SBML notes and are expected to display them; no
  one here has watched either do it.
- **A round trip still loses the comments**, so the file that comes back is
  less readable than the one that went out. Strictly more than the nothing
  it carried before, and still a loss.
- **`'` comes back as `&apos;`** after a round trip through libSBML, which
  escapes it and Antimony does not unescape. Cosmetic, in a library this
  project does not own, and named rather than worked around.
- **The `notes` are prose.** Bergmann's point stands: prose is not
  machine-extractable, which is why `provenance.json` (ADR 0181) exists
  beside it. This makes the human-readable artifact durable; it does not
  make it structured.
