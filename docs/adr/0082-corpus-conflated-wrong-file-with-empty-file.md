# ADR 0082: `corpus` reported the wrong file as a successful analysis

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0031 (the corpus reader), ADR 0024 (three outcomes, three
exit codes), ADR 0077 (`--json` as a scripting contract)

## What was found

Auditing every command that advertises `--json` after ADR 0077. `resolve` is
clean on all four of its branches — found, cross-species, nothing,
unavailable — with 0 / 0 / 2 / 1. `sweep` is clean including its
every-point-failed branch. `corpus` was not:

```
$ scientific corpus notes.txt --json
{ "ok": true, "parse": { "rows": 0, "malformed": 1, ... },
  "strenda": { "measured_rows": 0, "both_conditions": 0, ... } }
$ echo $?
0
```

A file containing the single line `garbage not tsv` was reported as a
successful corpus analysis in which every STRENDA figure happens to be zero.
A script sees a pass.

**The code already knew this was wrong.** The comment beside it read:

> Not an error, and not a silent zero either. A file that parsed cleanly but
> contained no measurements is a real outcome and **the reader needs to know
> which of the two happened**.

and the message it printed was

> `(0 row(s), all prose-only **or** malformed)`

That `or` is the tell. The code could not say which had happened, so it said
both, and returned 0 for either. The requirement was written down and not
met — the most expensive kind of near-miss, because the comment reassures the
next reader that the case was handled.

## Decision

Three outcomes, three exit codes, matching `resolve`.

| situation | exit | why |
|---|---|---|
| rows parsed, measured values present | 0 | figures reported |
| rows parsed, **all** `additional information` | 2 | a genuine download with no measured values — the analysis ran, and this is its answer |
| **zero** rows matched the nine-field schema | 1 | this is not a BRENDA bulk download; nothing was read |

The last is **not a threshold**. "Zero of N lines parsed" is categorical, so
no invented cutoff is involved — which matters here, because Jeske's
"fantasy numbers" warning is the reason this project refuses to invent
thresholds elsewhere. A file where nothing at all matched is almost always
the wrong file, which is a mistake in the invocation, and exits the way the
existing `No such file` branch already does.

The prose-only case keeps its own message and now names what it found —
`all 'additional information' — BRENDA's prose-only form` — rather than
offering the reader a disjunction to resolve themselves.

## Why this survived

`scripts/brenda_corpus_stats.py` **had no tests at all.** `pytest -k corpus`
matched nothing.

It is not obscure: the CLI `corpus` command spawns it, and it is the script
that answers Jeske's STRENDA question — how much of BRENDA states the pH and
temperature a value was measured under — so its figures get quoted. ADR 0031
exists because a figure from this area had already been quoted in outreach
when it was not a claim about the literature at all.

`Tests/test_brenda_corpus_stats.py` now covers all three outcomes, plus the
missing-file case (already correct, pinned so it stays that way) and a
parametrised check that `--json` emits one parsable document on every branch.

The fixtures are written by the test rather than requiring a real bulk
download. A test that needs a file the user must fetch by hand is a test that
gets skipped — and this suite already carries two such skips (`libsedml`,
`stdpopsim`), which is precisely why this script went untested.

## Consequences

- Mutation-tested: collapsing the two branches back into one fails exactly
  the two tests that distinguish them, and the other seven keep passing.
- `corpus --json` on an unrecognised file now carries `"error":
  "unrecognised-format"` alongside the parse evidence, so a caller can see
  *why* nothing parsed without re-running without `--json`.
- The audit that found this also confirmed `resolve`, `sweep` and
  `commandSensitivity` emit one clean document per branch. Recording the
  negative result too: three of the four were already right, and knowing
  which is worth as much as the fix.
