# ADR 0148: A table nobody had checked for a month, and a `contains` that was not an assertion

**Status:** Accepted, implemented

**Date:** 2026-08-21

**Context:** `docs/mutations/adr-0013-vmax-from-kcat.json`,
`docs/mutations/adr-0144-documented-citations.json`,
`Tests/test_documented_citations_guard.py`, `scripts/check_guard_wiring.py`

**Follows:** ADR 0144, which fixed the guard that made all of this visible

## What happened

ADR 0144 fixed `check_mutation_tables_reproducible.py` so it could see a
mutation table indented inside a bullet. Everything below is what that fix
then surfaced.

### ADR 0013's table had never been checked by anything

Written 2026-07. Four mutations on `vmax_from_kcat` — the bridge that makes
a literature kcat simulable, and the foundation ADR 0142 built the lab
report's `derived` origin on. Invisible to the guard for a month because of
the anchor bug, so nobody had ever re-run it.

It reproduces: **4 caught, 0 not caught.** The decision was sound; only the
evidence for it was unverified.

Two things had to be fixed to get there, and both are the harness refusing
to guess rather than producing a confident wrong answer:

1. **`-q` had to go.** `caterva/pytest.ini` suppresses the summary line under
   `-q`, so the harness could not count tests and **refused to run at all**,
   reporting that every verdict would be meaningless. A silent `0 total`
   read as `0 failed` is one of the three ways hand-run mutations were wrong
   before ADR 0069.
2. **One find string matched three sites.** `v.flagged = True` occurs three
   times in `validation.py`, and the harness returned `INDETERMINATE` —
   naming the ambiguity instead of mutating whichever it found first.

### ADR 0144 was flagged by the rule ADR 0144 had just restored

It published a mutation table and shipped no set file. The guard caught its
own author within a day, which is the most convincing evidence available
that the fix works.

Producing the set file needed a countable suite, because a guard script
exits 0 or 1 and the harness grades on test counts. So
`Tests/test_documented_citations_guard.py` exists — and it fixed a second
problem at the same time: the guard had been wired into `verify_build.py`
**and nothing else**, verified only in the direction where it passes. A
guard nobody has watched fail is a guard nobody has watched.

## The finding worth carrying forward

Two of the three mutations came back **NOT CAUGHT**. ADR 0144 had claimed
both behaviours in prose — "an empty fixture directory fails loudly rather
than passing vacuously", "`_MIN_SURFACES` floor" — and tested neither. That
is a claim in an ADR standing in for evidence, which is exactly what the set
file requirement exists to prevent.

Adding a test closed one. **The other still survived**, and the reason is
the important part:

```python
assert "fixtures" in result.stdout.lower()
```

The guard's own header prints `Reference ids in fixtures: 0` on every run,
so the assertion matched output that is always present. The test passed with
the branch it was written to cover deleted.

> **When the output being tested contains an explanation of itself, a
> document-wide `contains` is not an assertion.**

That is ADR 0133's sentence, and this is the **third** time this repository
has hit it — 0133 (prose below a table matched `"**yours**"`), 0136 (a
negative assertion against remembered wording), and now here, *inside the
test written to close a NOT CAUGHT*. Fixed by asserting the sentence that
branch alone writes: `"No reference ids found"`.

Three occurrences is no longer a coincidence; it is the default failure mode
of testing a program that explains itself. The rule now has a name and three
citations, and the next person to write `assert "x" in output` on this
codebase should have to argue for it.

## Consequences

- `check_mutation_tables_reproducible.py`: 0013 and 0144 closed. The four
  still open — 0125, 0128, 0133, 0146 — belong to other authors and to
  work currently in flight, and grandfathering another contributor's
  evidence on their behalf would be deciding for them that it need not
  reproduce.
- `check_documented_counts.py` is green again via `make counts-fix`; the
  drift was ADRs added faster than the four files that count them.
- `check_guard_wiring.py` is green, and the citations guard now runs in two
  harnesses rather than one.
- Total re-derived this session: **22 mutations across six set files**, all
  caught, zero indeterminate.
