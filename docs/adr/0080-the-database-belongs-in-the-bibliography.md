# ADR 0080: The database belongs in the bibliography

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0079 (one licence table, two languages), ADR 0063
(attribution travels with the model), Katz on citation, and Jeske's CC BY 4.0
obligations

## Context

`Tests/citation_export.py` exists because of Daniel Katz's reply about
per-constant citation, read in its sharper sense: *a citation nobody can act
on is not a citation*. So Caterva emits BibTeX and RIS — the formats Zotero,
Mendeley, EndNote and JabRef import — and a student can put the sources of
their parameters into the same bibliography as the papers they read.

`NOTICE` is unambiguous about what that bibliography owes BRENDA:

> If you use BRENDA data in scientific work, cite BRENDA's current
> publication — see https://www.brenda-enzymes.org/references.php. **Citing
> Caterva is not a substitute for citing BRENDA.**

The export emitted one `@misc` per parameter:

```bibtex
@misc{brenda740253,
  howpublished = {BRENDA database record},
  brenda-reference = {740253},
  note = {Resolved by Caterva as the KM = 10.73 mM. ...}
}
```

**and no entry for BRENDA itself.**

A student importing this into Zotero gets the records and not the database.
They will cite `BRENDA database record 740253` and not BRENDA — in the one
artifact whose entire purpose is to populate a bibliography, the citation
the source actually asks for was the one thing missing.

The attribution work of ADR 0063 and 0079 put BRENDA's licence into the
model, the SBML and the CSV. It did not put BRENDA into the bibliography,
because a licence notice and a citation are different obligations: the
licence is satisfied by naming the licensor in the file, and the citation is
satisfied only by an entry a reference manager can import.

## Decision

`contributing_sources()` returns the described data sources that supplied a
value in this run, and both exporters emit one entry per source after the
per-parameter records.

Read from `docs/data-sources.json` — the same table the model, SBML and CSV
exports read (ADR 0079) — so the citation request cannot drift between the
places that state it.

### It invents nothing

This module's central refusal is that it does not fabricate bibliographic
fields, because a fabricated entry *imports cleanly, looks complete, and is
fiction*. BRENDA's `citation_request` is an instruction and a URL — *"cite
BRENDA's current publication, see .../references.php"* — **not a reference**.

So the entry carries a title, the licensor as `howpublished`, the database
URL, and a note that says plainly:

> Caterva does not record that publication's author, year or volume and has
> **NOT guessed them** — look it up and complete this entry before
> submitting.

No `author`, `year`, `journal` or `volume` is emitted. A tested assertion
enforces that, because the tempting next change is to "improve" the entry by
filling them in.

### Credited only where it contributed

A source appears only when it supplied a value in this run. An entry for a
database that contributed nothing would put a citation in someone's paper
for data they did not use — the same rule as every other export, and under
CC BY 4.0 §2(a)(6) the endorsement the licence forbids implying.

One entry per database regardless of how many parameters it supplied: two
BRENDA-resolved parameters are two records and one database.

## Verification

Five new tests in `Tests/test_citation_export.py` (23 total). Three
mutations, all caught:

| Mutation | Failures |
|---|---|
| the database entry is never emitted (the original defect) | 3 |
| every described source credited, contributed or not | 1 |
| the note stops saying the fields were not guessed | 1 |

### Two existing tests had encoded a count instead of an invariant

Adding a third RIS record broke `test_ris_uses_crlf_and_terminates_every_record`,
which asserted `count("TY  - ") == 2`. The property it names is that every
record is *terminated*; the count was incidental. It now asserts
`count("TY  - ") == count("ER  - ")`, which survives adding entries and
still fails on an unterminated one.

`test_two_parameters_from_one_reference_get_distinct_keys` asserted
`len(keys) == 2`. The property is *uniqueness*, so it now excludes the
`caterva-source-*` block from the parameter count and asserts no duplicate
key anywhere — strictly stronger than before.

Both were correct tests weakened by a literal. A count is the easiest thing
to assert and the first thing to break for a reason that is not a defect.

## Consequences

- An exported bibliography now contains the databases as well as the
  records. A student following it will cite BRENDA.
- The entry is deliberately incomplete and says so. It cannot be submitted
  as-is without the person noticing, which is the intended friction.
- Adding a source with a `citation_request` to `docs/data-sources.json`
  enrols it in both formats with no code change.
- NCBI Taxonomy has no `citation_request` recorded and so produces no entry.
  NOTICE says NCBI "asks to be cited but does not require it as a licence
  condition"; recording that request is a separate decision, not an
  oversight of this one.
