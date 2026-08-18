# ADR 0107: The twenty-seventh citation

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Tests/citation_export.py`, `scripts/export_citations.py`

## How this was found

Reading ruff's `F401` list — the other bug class `check_python_bug_lints.py`
names and does not enforce. Most entries were unused `pytest` imports. Three
were a test module importing a symbol it never exercises, which reads as
coverage that does not exist. Two of those were covered elsewhere. The third
was `bibtex_key`, imported by `test_citation_export.py` and never called
there.

It takes a `seen` set, so it handles key collisions. That is worth reading,
because a BibTeX key collision makes a citation disappear.

## Defect 1: the uniqueness guard broke worse than the problem it prevented

```python
suffix = ord("a")
while key in seen:
    key = f"{stem}{chr(suffix)}"
    suffix += 1
```

Past `z`, ASCII continues `{`, `|`, `}`, `~`. Measured with 30 parameters
sharing one BRENDA reference:

```
@misc{brenda740253z,
@misc{brenda740253{,
@misc{brenda740253|,
@misc{brenda740253},
```

The docstring explains that the guard exists because *"BibTeX silently keeps
one of them ... the bibliography would be short by an entry and nothing
would say so."* But `@misc{brenda740253}` **closes the entry group early**:
BibTeX reads a complete empty entry and parses the remaining body at top
level. A duplicate key costs one entry. This costs every entry after it.

Reachable: `scripts/export_citations.py` builds the list from a JSON payload
of arbitrary length, and one BRENDA reference routinely supplies several
constants for one enzyme.

**The property was already asserted.**
`test_keys_are_valid_bibtex_identifiers` requires `[A-Za-z0-9_:-]+` — exactly
right — and ran on three parameters, which reaches one collision. The
assertion was correct and the input could not exercise it. That is the
session's recurring shape once more: not a missing test, a test that cannot
reach the case it describes.

Fixed with the spreadsheet-column sequence (`a`…`z`, `aa`, `ab`), which is
also the convention BibTeX styles use for same-author-same-year keys.

## Defect 2: found by mutating the fix

Mutating `_disambiguator` to cycle `a..z..a` instead of carrying to `aa` did
not fail the suite. **It hung the test run.** `while key in seen` had no
bound, so every candidate past the 26th was already taken.

In a script driven by a JSON payload, that is not a wrong answer — it is no
answer, and no error either. The loop is now bounded by `len(seen) + 1`,
which is always sufficient when the suffixes are distinct, and raises when
it is not:

> could not find an unused BibTeX key for 'brenda740253' in N attempts.
> That is only possible if the disambiguating suffixes have stopped being
> distinct, which would silently merge two entries into one.

A wrong answer can be seen. A hang cannot.

## Defect 3: the script had not run since the source table landed

Proving the fix end-to-end through the real entry point instead of the
library, `scripts/export_citations.py` died on its import line:

```
ModuleNotFoundError: No module named 'Terium'
```

It inserts `REPO_ROOT / "Tests"` on `sys.path` and not `REPO_ROOT`, and
`citation_export` imports `Terium.core.data_sources` — the shared source
table (ADR 0079). **Committed in HEAD**, not a working-tree artifact.

Every test in the file imports `citation_export` directly, where pytest has
already put the repository root on the path. The library was covered; the
door a user actually walks through was not. This script's own docstring
calls it *"the reachable end of Tests/citation_export.py — which was built
and then callable from nowhere"*, and it had quietly become unreachable
again, with a green suite.

## Decision

- Alphabetic disambiguation that cannot leave `[a-z]`.
- A bounded search that raises rather than spins.
- `test_the_script_runs_end_to_end` and
  `test_the_script_survives_many_parameters_from_one_reference` invoke the
  script as a **subprocess**, from a temporary directory, so neither
  pytest's `sys.path` nor the working directory can supply an import the
  script cannot supply itself.

Verified through the real script: 60 parameters, one reference, 61 unique
keys (the sixtieth plus BRENDA's own entry), braces balanced, suffixes
running `aa`, `ab`, `ac`.

## Consequences

- A bibliography with more than 26 values from one reference is now valid
  rather than corrupt from the 27th entry onward.
- The export script is executable again, and a test fails if it stops being.
- `F401` was worth reading for the same reason `F841` was (ADR 0105): both
  are ways of saying *this was written and is not used*, and in a codebase
  whose defining defect is "computed and not delivered", that sentence is
  worth following every time.
- Left alone, deliberately: `_note_for` builds its `missing` list from a
  tuple of hardcoded `None` values, so the comprehension can only ever
  return all three field names. It produces the correct sentence today —
  Terrium genuinely holds no author, year or journal — but it is a constant
  wearing the costume of a computation. Recorded rather than changed,
  because changing it needs a decision about whether `title` (which *is*
  sometimes known, and is emitted) belongs in that sentence when absent.
