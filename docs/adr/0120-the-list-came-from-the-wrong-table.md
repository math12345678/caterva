# ADR 0120: The list came from the wrong table

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Tests/fallback_logic.py`, `Tests/brenda_client.py`

**Supersedes nothing, corrects:** ADR 0118, shipped one day earlier

## The defect

ADR 0118 made a substrate miss name the substrates the enzyme does report.
Building the next feature on top of it exposed that the list can come from a
table nobody asked about.

Measured on `brenda_ldh_fixture.html`, which carries a **"KM Values"** table
and no "Ki Values" table:

```
substrates_present(ec, provider, KI_TABLE_LABEL)
  -> ['(S)-lactate', 'NAD+', 'oxamate', 'pyruvate']
```

Those are the **Km** table's substrates, offered as an answer about Ki. So a
student asking for a Ki with a near-miss substrate name was told:

> No 'L-lactate' row, but this EC number reports: (S)-lactate, NAD+,
> oxamate, pyruvate.

They re-run with `(S)-lactate`, fail again, and now believe Ki data exists
for this enzyme. It does not. The hint sent them in a circle and left them
with a false belief on the way round — a helpful-looking sentence that is
false, introduced while fixing a helpful-looking sentence that was false.

## Why it happened

`_find_table_container` returns `None` when the label is absent, and its
docstring instructs the caller plainly:

> Returns the container Tag if found, else None (caller should fall back to
> whole-page scanning and treat results as less trustworthy).

`parse_brenda_km_html` does exactly that, and for the **resolver** it is
right: a target substrate and a target organism filter foreign rows out, so
the fallback costs nothing. Verified — through the real resolver, a `ki`
query on this page correctly returns `not_found`.

ADR 0118's helper runs in permissive mode: `target_substrates=[]`,
`target_organism=None`, `require_substrate_match=False`. Every filter that
made the fallback safe is switched off, which is precisely what that mode is
for. The documented caveat was read as being about trustworthiness of
*parsing* and not about *which table*.

## Decision

`brenda_client.has_data_table(html, label)` — a public predicate, so a
caller can ask the question the fallback silently answers for it.

`substrates_present` returns `[]` when the labelled table is absent, and
`_nothing_matched` says something better than a corrected list:

> BRENDA's page for 1.1.1.27 carries no 'Ki Values' table at all, so no
> substrate has a value of this kind here. **The substrate name is not what
> went wrong.**

That diagnoses the **quantity**, which is what the reader actually got
wrong. A corrected substrate list would have been accurate and still
useless: it would answer a question they were not asking.

## What this says about the pattern

ADR 0118 was written, mutation-tested four ways, reviewed and shipped. The
defect was not in the logic it tested; it was in an assumption underneath
the logic — that the parser returns rows from the table it was asked for.
The mutations all probed the new code and none probed its input.

The test that would have caught it is the one now written first in the new
class: **assert the premise.** `brenda_ldh_fixture.html` has a Km table and
no Ki table, and if someone adds one later these tests must fail rather than
quietly stop testing anything.

## Consequences

- A student asking for a quantity BRENDA does not hold for an enzyme is told
  that, instead of being handed substrates from another table.
- `has_data_table` is available to anything else that parses permissively;
  the next feature that needs an inventory of a page needs it immediately.
- Two mutations, both caught: reverting the presence check in
  `_nothing_matched`, and dropping the guard inside `substrates_present`.
- The fixture's shape is now pinned, so the tests cannot become vacuous by
  someone enriching it.
