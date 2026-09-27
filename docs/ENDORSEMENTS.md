# Endorsements

**There are none. This file exists so that the absence is on the record.**

The block below is the only part of this file that
`scripts/check_no_fabricated_endorsements.py` reads when deciding whether a
public claim is backed. Everything else here is prose for humans — including
the table of *removed fabrications*, which must never be mistaken for a list
of permissions.

That distinction is not hypothetical. The first version of the guard read
the whole file, and the removal table lists Stanford, MIT, Johns Hopkins and
UC Berkeley — so the document explaining that those endorsements were fake
was itself excusing them from the check. The record of the defect had become
the exemption for the defect.

<!-- REAL-ENDORSEMENTS-START
Add one row per endorsement. Each needs a real person, their actual words,
their affiliation, and the date written permission was given.
| institution | person | permission |
|---|---|---|
REAL-ENDORSEMENTS-END -->

Caterva is pre-launch. It has a waitlist and no users. No person or
institution has endorsed it, and until one does, no page may say otherwise.

## What was here before

Until 2026-08-15 the landing page carried a testimonial carousel with five
quotes, under the heading **"Built for teaching labs. Trusted by
educators."** Each was attributed to a named individual with a title at a
named institution:

| attributed to | claimed affiliation |
|---|---|
| "Dr. Sarah Chen", Biochemistry Faculty | Stanford University |
| "Prof. Marcus Okafor", Computational Biology | MIT |
| "Dr. Elena Rodriguez", Public Health Researcher | Johns Hopkins University |
| "Prof. James Watanabe", Enzyme Kinetics Lab Director | UC Berkeley |
| "Dr. Amara Osei", Systems Biology Instructor | University of Cambridge |

None of them exists in connection with this project. The quotes were
written by whoever built the page. The institutions are real, the people
are not known to be, and the product they praise had not shipped.

They have been removed, and
[ADR 0071](adr/0071-the-testimonials-were-not-real.md) records why rather than
letting the deletion look like a design change.

## Why this mattered more than the other findings

Everything else found in this repository's compliance work was a
**paperwork** problem: an unattributed dependency, an unrecorded database,
a missing privacy notice. Real, worth fixing, fixable by writing something
down.

This was different in kind. It was a false statement of fact made to the
public, about named third parties, for commercial advantage.

- Fabricated testimonials are prohibited by the FTC's Rule on the Use of
  Consumer Reviews and Testimonials (16 CFR Part 465, effective 2024), and
  are deceptive acts under FTC Act §5. Civil penalties attach per
  violation.
- Naming Stanford, MIT, Johns Hopkins, UC Berkeley and Cambridge implies
  their endorsement. Those names are protected marks and those
  institutions do enforce them.
- If any real biochemist named Sarah Chen works at Stanford, the page put
  words in her mouth.
- `Business/FUNDRAISING_TRACKER.md` and the pitch deck exist. Fabricated
  traction shown to investors is a materially worse category of problem
  than fabricated traction shown to users.

*Not legal advice — but this one does not need a lawyer to identify, only
to quantify.*

## It is the same defect this project already documented about itself

`docs/ARCHIVE_TRIAGE.md` found eighteen documents that had been "fixed" by
adding a correction banner rather than by correcting the content, and
recorded the lesson:

> The fix for a false claim is to make it true or remove it, and then to
> make it mechanically checkable so it cannot rot again.

The same failure had reached the public-facing site, where it is not an
internal embarrassment but a representation to third parties. The
compliance work in `docs/LICENSING.md` audited what Caterva *consumes* and
never looked at what Caterva *says*.

## The rule from here

**A claim about a person or institution on any public surface requires a
record in this file**, containing:

1. who said it, verifiably — a real name, affiliation, and a way to check;
2. what they actually said, quoted rather than paraphrased into marketing;
3. written permission to publish it with their name and affiliation;
4. the date, and what version of Caterva they were talking about.

`scripts/check_no_fabricated_endorsements.py` fails the build when a public
page names an institution in a promotional context without a matching entry
here.

## A note on the real expert feedback

Caterva has had substantive review from five named experts — Lisa Jeske
(BRENDA/DSMZ), Barbara Bakker (UMCG), Herbert Sauro (UW), Daniel Katz
(NCSA) and Matthias König (HU Berlin). It is recorded in
`docs/EXPERT_FEEDBACK.md`.

**None of it is an endorsement and none of it may be used as one.** It is
criticism, given in reply to a cold email, and some of it is sharp. König
in particular read that email as a claim on Tellurium's work — using his
name in marketing would repeat the exact injury the project has already
apologised for.

Quoting a critic as if they were a supporter is the same fabrication as
inventing one, with a real person's name attached. If any of them ever
offers an endorsement in writing, it goes here, with the writing.
