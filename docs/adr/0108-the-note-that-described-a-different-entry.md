# ADR 0108: The note that described a different entry

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Tests/citation_export.py`; resolves the open item recorded in
ADR 0107's Consequences

## The decision ADR 0107 deferred

ADR 0107 closed by recording something found and not changed:

> `_note_for` builds its `missing` list from a tuple of hardcoded `None`
> values, so the comprehension can only ever return all three field names.
> It produces the correct sentence today [...] Recorded rather than changed,
> because changing it needs a decision about whether `title` (which *is*
> sometimes known, and is emitted) belongs in that sentence when absent.

The sentence was not correct today. Printing it against both cases shows two
false notes, one in each direction.

```
TITLED   -> ... Terrium records the source identifier only; author, year,
             journal are NOT known to it ...
UNTITLED -> ... Terrium records the source identifier only; author, year,
             journal are NOT known to it ...
```

They are identical, and the entries are not.

**The titled entry emits `title = {LDH kinetics in human}`** and the note
sitting inside it says Terrium records the source identifier *only*. False
about the very entry it is attached to.

**The untitled entry has no `title` field at all**, and the note lists
author, year and journal as absent while saying nothing about title — the
field every reference manager displays first. The absence a user is
guaranteed to notice was the one absence the note did not explain. This
module's stated purpose is that "every entry carries a `note` saying exactly
what was and was not known", and it omitted the most visible item precisely
when it applied.

## Decision

Ask the citation instead of asserting the answer:

```python
_BIBTEX_WANTS = ("author", "year", "journal", "title")

def _known_and_missing(citation):
    known, missing = [], []
    for field in _BIBTEX_WANTS:
        (known if getattr(citation, field, None) else missing).append(field)
    return known, missing
```

`getattr` rather than a literal list. `Citation` today has `title` and no
author, year or journal, so the answer matches the old constant for three of
the four fields. The difference is that this **asks**. If `Citation` ever
gains a `year`, the note starts telling the truth about it instead of
continuing to report it unknown — and a field added to the model without the
note noticing is exactly how the original constant came to be wrong.

Both renderers already share this derivation: `to_ris` calls `_note_for`
too, so BibTeX and RIS cannot drift apart on it (ADR 0003).

## What this is an instance of

A constant wearing the costume of a computation. The comprehension had a
loop, a condition and a filter, and could return exactly one value. It read
as though it adapted, so nobody checked whether it did — the same reason a
check that cannot fail is worse than no check.

Mutation confirms the tests distinguish the two: reverting to the constant
fails the titled case, and dropping `title` from the wanted list fails all
three.

## Consequences

- A student importing an untitled entry is told the title is unknown rather
  than left to wonder whether the export dropped it.
- An entry carrying a title no longer denies carrying it.
- ADR 0107's open item is closed. The note is now derived from the citation
  it describes, so it can be wrong only if `Citation` and `_BIBTEX_WANTS`
  disagree — which `test_the_answer_is_asked_of_the_citation_not_assumed`
  pins by handing it a citation with every field filled and requiring
  nothing to be reported missing.
