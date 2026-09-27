# ADR 0071: The testimonials were not real

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0062 and 0068 (licensing audits), `docs/ENDORSEMENTS.md`,
`docs/ARCHIVE_TRIAGE.md`

## What was live

The landing page rendered a testimonial carousel — `CliApp.tsx:689` — with
five quotes under the heading **"Built for teaching labs. Trusted by
educators."** Each was attributed to a named individual with a title at a
named institution: Stanford, MIT, Johns Hopkins, UC Berkeley, Cambridge.

Caterva is pre-launch. It has a waitlist and no users. Nobody had used it,
so nobody had said any of those things.

The quotes are gone, `TestimonialCarousel.tsx` is deleted, and
`docs/ENDORSEMENTS.md` records what was there rather than letting the
deletion pass as a design change.

## Why this is a different category from the other findings

Every previous compliance finding in this repository was a **paperwork**
problem: a dependency without attribution, a database queried without
reading its terms, a missing privacy notice. All real, all fixable by
writing something down.

This was a false statement of fact, about named third parties, published to
the public, for commercial advantage, by a project with a fundraising
tracker and a pitch deck.

- The FTC's Rule on the Use of Consumer Reviews and Testimonials (16 CFR
  Part 465, 2024) prohibits fabricated testimonials; civil penalties attach
  per violation.
- Naming five universities implies their endorsement. Those are protected
  marks and those institutions enforce them.
- If a real biochemist named Sarah Chen works at Stanford, the page put
  words in her mouth.

*Not legal advice — but unlike the licence questions, this one does not
need a lawyer to identify, only to quantify.*

## It is the defect this project already documented about itself

`docs/ARCHIVE_TRIAGE.md` classified 58 root documents as archive-quality,
found eighteen "fixed" by adding a correction banner rather than by
correcting the content, and drew the lesson:

> The fix for a false claim is to make it true or remove it, and then to
> make it mechanically checkable so it cannot rot again.

That lesson had been applied to the documentation and to the numbers. It
had never been applied to the marketing, because the compliance work
audited what Caterva *consumes* and never what Caterva *says*.

## Decision

`docs/ENDORSEMENTS.md` is the register. A claim about a person or
institution on a public surface requires an entry naming a verifiable
person, their actual words, and the date written permission was given.

`scripts/check_no_fabricated_endorsements.py` fails when a public page
names an institution without a matching record.

**The register does not cover the real expert feedback.** Five named
experts have reviewed Caterva and their comments are in
`docs/EXPERT_FEEDBACK.md`. None of it is an endorsement. It is criticism,
given in reply to a cold email, and König read that email as a claim on
Tellurium's work. Quoting a critic as a supporter is the same fabrication
with a real name attached.

## Verification, and two holes the mutations found

Re-derivable as a set file — `docs/mutations/adr-0071-fabricated-endorsements.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0071-fabricated-endorsements.json
```

Five of the original eight rows, all `caught` under the harness. The
original table came from a hand-run loop and one of its rows was the no-op
described at the end of this section; the set file carries the corrected
form instead of the false negative. The remaining two rows were replays of
already-covered branches.

Original run, eight mutations with `cmp`-verified backups:

| Mutation | Caught |
| --- | --- |
| The citation exemption reverts to case-insensitive | 2 failed |
| The institution list is emptied | 3 failed |
| A claim is found but not reported | 3 failed |
| `ENDORSEMENTS.md` stops saying there are none | 1 failed |
| The whole file counts as the allowlist | 2 failed |
| A missing allowlist block reads as permissive | 1 failed |
| The block delimiters move so the removal table leaks in | 1 failed |
| Any mention anywhere in the file excuses a claim | **NOT caught** |

### Hole 1: the exemption that would have disabled the guard

I added `"Source:"` to `LEGITIMATE_CONTEXTS` so that a real citation —
`Source: Hoare & Pal, Adv. Phys. 20, 161 (1971)` — would not be flagged.

Matched case-insensitively, `"Source:"` also matches
`source: "Stanford University"` — **the exact field in the fabricated
testimonial**. The guard would have passed the carousel it was written to
catch.

An exemption added to stop crying wolf had switched off the alarm. Only the
replay test — which feeds the guard the verbatim fabricated record — found
it. The rule is now anchored and case-sensitive: `^\s*Source: [A-Z]`.

### Hole 2: the record of the defect became the exemption for it

The record-match asked whether `"| Stanford"` appeared in
`docs/ENDORSEMENTS.md`. That document contains a table of the **removed**
fabrications, with rows like `| Stanford University |`.

So the file written to say those endorsements were fake was excusing them
from the check. Verified rather than theorised: four of the five
institutions — Stanford, MIT, Johns Hopkins, UC Berkeley — were already
exempt on every public page at the moment the guard was declared working.

The allowlist is now a delimited `REAL-ENDORSEMENTS-START` block, read
alone, with a missing block treated as a failure rather than as an empty
and therefore permissive list.

### A note on the eighth mutation

The first attempt at "the delimiters move" was a no-op: the block sits
above the removal table, so moving the start marker earlier changed
nothing, and it reported a false "not caught". Re-run with the end marker
moved below the table — verified by asserting the table was actually inside
the block before running the suite — it failed as it should.

A mutation that does not mutate is not evidence. This is the third time
this session that has come up, and checking the mutation took effect is now
part of the procedure rather than an afterthought.

## What is not fixed

The FAQ says "304+ tests and counting". The real figure is an order of
magnitude higher, so the claim understates rather than inflates — but it is
an unverified number on a public page, and `check_documented_counts.py`
only governs `README.md`. Extending it to the landing copy is the obvious
next step and is not done here.
