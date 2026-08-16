# ADR 0088: No guard can read a picture

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0071 (the testimonials were not real), ADR 0075 (marketing
copy vs code), ADR 0078 (the deck understated its own evidence),
`docs/PUBLIC_IMAGES.md`

## The gap

`check_public_claims.py` scans the landing pages for text contradicting the
code. Its file filter ends:

```python
and not rel.endswith((".png", ".svg", ".ico"))
```

That exclusion is correct — a PNG is not source — and every other guard
shares it by omission. `check_documented_counts.py`,
`check_public_claims.py`, `check_investor_claims.py` and
`check_no_fabricated_endorsements.py` all read text. **A hero image reading
"10,000 universities trust Terrium" passes all four.**

Fourteen images sit on public surfaces. Before this, none of them was
checked by anything.

That matters here more than it would elsewhere. This project has already
shipped five fabricated testimonials in text that *was* being read (ADR
0071) and four stale counts in text that *was* being read (ADR 0075, 0078).
Assuming the unreadable surface is clean would be assuming the one place
nobody was looking is the one place nothing went wrong.

## Decision

`docs/PUBLIC_IMAGES.md` registers every public-surface image with a content
hash and a review state. `scripts/check_public_images_reviewed.py` fails on
an unregistered image, a registered image that has vanished, and — the case
that matters — **an image whose hash no longer matches**.

A new file is conspicuous in a diff. A screenshot edited to add a number is
one binary blob replacing another, and hashing is the only thing that sees
it.

Three states, and the middle one is the point:

| state | meaning |
|---|---|
| `reviewed` | somebody opened it and read it |
| `hashed` | change-detected, **nobody has looked** |
| `absent` | in the tree, not in the register — fails |

`hashed` exists so the register cannot claim an audit that did not happen.
It shipped with eleven of fourteen in that state and said so.

## What the review actually found

All fourteen are now `reviewed`. The result is worth recording because it
is the opposite of what the last two ADRs found.

**The mockups are meticulous.** `09-microscope-record.png` badges its
parameter record ILLUSTRATIVE, records `SOURCE BASIS: Demo source`, and
footers *"THIS IS AN INTERFACE DEMONSTRATION. IT IS NOT A RESEARCH-READY
PARAMETER."* `05-console-running.png` shows a plausible Km of 0.42 mM
attributed to `DEMO-02`, with temperature flagged `assumed` in amber rather
than silently defaulted. `06-console-complete.png` marks every element of a
completed run as a demonstration.

Somebody built those refusing to let fake data look real, in the same
repository and the same period that shipped five invented testimonials. The
care was available; it was not applied everywhere. That is a more useful
observation than either finding alone.

**No third-party content anywhere:** no other product's UI, no stock
photography, no institutional logos, and a favicon that is thirteen lines
of hand-written SVG. That was the licensing question that prompted the
look.

**One thing recorded rather than fixed.** The atlas images show five
literature sources — PubMed, Semantic Scholar, OpenAlex, CrossRef, arXiv.
In the codebase: PubMed is real (53 files), CrossRef appears only in
comments about hand-verified DOIs, arXiv as one comment URL and one type
field, and Semantic Scholar and OpenAlex in **zero files**.

Every node is captioned `CONCEPTUAL SOURCE` and the page
`ILLUSTRATIVE V1 ARCHITECTURE`, so it is a design diagram honestly
labelled, not a capability claim. It is in the register because **the
caption is the only thing making it honest** — crop it, drop the image in a
deck, and it claims five literature integrations where one exists. Nothing
mechanical can check that a caption stayed.

## What this guard is not

It detects **change**, not **content**. A reviewer reads the picture; the
hash only notices when the picture is no longer the one that was read.

That is a weaker guarantee than any text guard in this repository and the
docstring says so. The real fix, if a metric ever goes into an image, is to
stop putting metrics in images — text can be checked and a screenshot
cannot.

## Two defects in the guard's own tests

**The prose went stale three times.** `docs/PUBLIC_IMAGES.md` states how
many images are unreviewed. It said ten when the answer was eleven, eleven
after four were reviewed, and seven after the rest were done. Every time,
`test_the_register_prose_matches_the_register` caught it. A document about
unchecked numbers is exactly where a stale number hides best, which is why
the count is pinned rather than trusted.

**A test crashed instead of failing.** That same test looked the count up
in a word table covering 10–14 — written on the unexamined assumption that
the number would stay in the range it happened to occupy. Reviewing four
images took it to 7 and the test raised `KeyError`. A crash reads as a
broken test, not as the clear message it was meant to give. The table now
covers 0–14, and 0 is included because that is where this should end up.

**A test punished success.** `test_reviewed_and_hashed_are_kept_distinct`
asserted `"hashed" in states`, so the moment every image had genuinely been
reviewed, it failed. It conflated *"the unreviewed state exists as a
concept"* with *"some row still uses it"*. Only the first belongs in a
test: the next image added starts unreviewed, and without somewhere to say
so it would read as audited on the day it landed.

Three test defects, all in the tests for a guard about unchecked claims,
all found mechanically rather than by reading. That is the argument for the
guard in one paragraph.
