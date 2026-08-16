# ADR 0078: The deck understated its own evidence

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0075 (marketing copy vs code), ADR 0071 (fabricated
testimonials), ADR 0068 (KEGG's terms), `docs/LICENSING.md`

## The gap ADR 0075 named and did not close

> `Business/` — the pitch deck and fundraising tracker are investor-facing
> and outside `PUBLIC_TREES`. The same class of drift is more consequential
> there, and `.pptx` and `.docx` are not greppable by this guard.

They are greppable. An Office file is a zip of XML and the text sits in
`<a:t>` (pptx) or `<w:t>` (docx) elements — about ten lines of standard
library. `python-pptx` is installed in this environment but is not in
`requirements.txt`, and a guard CI cannot run is not a guard, so the reader
uses `zipfile` and `re` only.

## What was on the slides

`terrium_pitch_deck.pptx`, slides 6 and 11: **"382 automated tests
passing"**. The repository had 1,852.

The deck understated its own evidence by nearly five times, to the audience
deciding whether to fund it.

That is the third instance of this exact shape:

| where | claimed | actual | direction |
|---|---|---|---|
| `README.md` | various | — | caught for months by `check_documented_counts.py` |
| landing FAQ | "304+ tests" | ~1,850 | understated |
| pitch deck ×2 | "382 tests" | 1,852 | understated |

**All three understated.** That is the finding worth keeping. This project's
neglect happens to point toward modesty, which is luck rather than policy —
the same absence of checking points the other way just as easily, and the
next document to drift might be the one that inflates. In a pitch deck,
that is a different conversation entirely.

The number is now corrected in the deck itself, because a wrong count is a
plain factual error with no upside in either direction.

## What was NOT changed, and why

Slide 11 lists, under "Product proof is done":

> ✓ Live GitHub repo — **BRENDA/KEGG scraper** + simulation engine

Two problems, neither of them the number:

1. It offers as a completed asset an integration whose licence position is
   unresolved. Per ADR 0068, KEGG's own terms say it "is not a public
   database", that non-academic use "requires a commercial license", and
   that academic users providing a service should hold a service-provider
   licence. An asset that may be a liability is what diligence is for.
2. "Scraper". Lisa Jeske of the BRENDA team, replying to this project's own
   outreach, advised using the bulk CSV downloads rather than scraping.

Neither is fixed by editing the slide. **Editing that line out would hide a
live risk from the audience most entitled to know about it.** The wording
is a symptom; the licence is the thing. Recorded in `docs/LICENSING.md`
under the KEGG action item.

Likewise unchanged: the deck pitches "six domains" while fifteen are built.
That is a decision about what is productised versus what compiles, and it
is the founder's. The guard checks facts with one right answer, not
narrative with several — a distinction written into its docstring so the
next person does not "fix" the positioning.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0078-investor-claims.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0078-investor-claims.json
```

All five reproduced rows come back `caught` under the harness, run as
`--only I1,I2,I3` then `--only I4,I5`. Original hand-run:

Six mutations. The first attempt exceeded the tool timeout partway through
and **left the tolerance mutation applied**; the file was found still
mutated on the next check and restored from a `cmp`-verified backup before
anything else. Recorded because an interrupted mutation run is how a
deliberate break becomes a permanent one.

| Mutation | Caught |
| --- | --- |
| The Office reader returns nothing | 2 failed |
| A mismatch computed but not reported | 1 failed |
| Tolerance widened to 99.0 | **NOT caught** |
| — after adding a test of the shipped tolerance | 1 failed |

The escape: `test_a_number_within_tolerance_is_not_flagged` injects its own
tolerance with `monkeypatch.setitem`, so widening the **configured** one to
99.0 — under which a claim of 5 tests passes against a suite of 1,852 — was
invisible to all ten tests. A tolerance is a threshold, and a large enough
threshold is an off switch.

**A test that supplies its own configuration cannot check the
configuration that ships.** That is the fifth assertion this session
satisfied by something other than the thing it was written to check, and
the fourth distinct flavour: a vacuous set identity, a subset relation true
of the empty set, a keyword matched in the wrong section, a case-sensitive
match never given a differently-cased input, and now an injected constant
standing in for the real one.

## Also verified rather than assumed

`python-pptx` rewrote the deck 25% smaller, which looked like data loss.
Comparing the archives showed all 73 content parts present and the media
bytes identical — the difference was directory entries and recompression.
Checked before accepting it, rather than after being asked.
