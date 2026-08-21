# ADR 0147: The promises made to a curator, checked one by one

**Status:** Accepted, verified

**Date:** 2026-08-21

**Context:** `Tests/fixtures/brenda_*.html`, `NOTICE`, `LICENSE`,
`Tests/taxonomy.py`, `Tests/brenda_client.py`

**Relates to:** ADR 0024 (cross-species opt-in), ADR 0061 (licence
separation), ADR 0015 (a rule nothing executes is not enforced)

## Why this exists

On 2026-08-13 Terrium wrote to Lisa Jeske of the BRENDA team at DSMZ,
reporting two licence breaches found by reading the page she linked, and
committing to five things. On 2026-08-20 she replied:

> As far as the license is concerned, you've been handling things in an
> exemplary manner. Thank you very much for that :) . I'm really glad my
> response was helpful. I wish you the very best of luck in your career.

That is the first unambiguous endorsement this project has received, and it
is about the one thing it is least able to verify by testing: whether it
keeps its word to a data provider.

**A promise nothing checks is the same as a guard nothing runs.** This
repository has spent most of its effort on that principle applied to code.
The email made five factual claims about the state of the tree, four in the
past tense. They are checked here rather than assumed, because the person
who believed them is now on record praising us for them.

## What was claimed, and what is true

| claim to Jeske | verified | evidence |
|---|---|---|
| "Eleven HTML fixtures ... lacked the required CC BY attribution" — fixed | **true** | 11 `brenda_*.html` fixtures, 0 without an attribution header |
| NOTICE credits BRENDA/DSMZ, names CC BY 4.0, lists modifications | **true** | DSMZ named; CC BY appears 7x; modifications 8x |
| LICENSE no longer says "all rights reserved" | **true** | 3 occurrences remain and all three are *historical narrative* explaining what the file used to say and why it changed — the carve-out itself quotes CC BY 4.0 §2(a)(5)(B) correctly |
| cross-species requires active opt-in, with a relatedness check | **true, and wired** | `taxonomy.assess_relatedness` is called from `fallback_logic.py:1055` on the cross-species path — real lineage comparison with a third "unknown" state, symmetry-tested |
| SABIO-RK kept optional, disabled by default | **true, trivially** | never implemented; the only occurrence is a citation string in a test. Stronger than promised, but the email implies a feature that does not exist |

Four kept. One outstanding, and it is the substantive one.

## The promise not yet kept

> "For the API, I will transition to the CSV downloads. Building against
> SOAP with a REST API on the horizon would be inefficient, and bulk files
> will reduce the load on your servers."

`fetch_brenda_html` still requests one enzyme page per query:

```python
r = retry_get(BRENDA_ENZYME_URL, params={"ecno": ec_number}, timeout=timeout)
```

The bulk download URLs Jeske supplied appear nowhere in the code. Three
things follow, and they are the same fact seen from three sides:

1. **It is a courtesy owed.** Reducing server load was her reason for
   suggesting it, and she gave the exact URLs. ADR 0142 already cut
   per-report fetches from three to one for the same reason; that was a
   fraction of what was promised.
2. **It is the project's largest fragility.** `parse_brenda_km_html` has
   never been validated against live BRENDA markup. Every offline test runs
   against snapshots, so a page-layout change breaks the live path and no
   suite goes red. A CSV corpus removes HTML parsing from the critical path
   entirely.
3. **It is what makes the live path testable at all.** Bulk files can be
   checked into a corpus and exercised; a per-query scrape cannot.

**Not started here, deliberately.** It is a migration of the resolver's data
source, and beginning it at the end of a session would produce exactly the
half-wired seam the last four ADRs have each been about (0136, 0139, 0141,
0142). Recorded with its reasoning so the next session starts from a
decision rather than a rediscovery.

## Two things a human has to do

**The endorsement is not ours to publish.** Jeske wrote it in private
correspondence. Quoting it in `README.md` or `docs/ENDORSEMENTS.md` — where
it would do the most good, and where a reader assessing an unknown student's
project would most want it — requires her permission first. Asking is one
short email; publishing without asking would be a small breach of exactly
the courtesy she just praised, in the same thread.

**The SABIO-RK sentence overstated the tree.** "I will keep it optional and
disabled by default" describes a feature that has never existed. Harmless in
effect and true in outcome, but it is the kind of sentence that becomes
untrue in the other direction later, and this project's credibility with
König was damaged by precisely one overstatement.

## Consequences

- The four kept promises are now recorded with the evidence that they are
  kept, so a future reader does not have to re-derive it from a mailbox.
- The outstanding one is written down where the build's own conventions can
  see it, rather than living in a sent-mail folder.
- No guard is added for the CSV migration. A guard that fails the build for
  unfinished work gets suppressed, and a guard that merely warns is
  decoration. The honest mechanism for a commitment with no code behind it
  yet is a record naming who it was made to.
