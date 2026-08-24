# ADR 0178: Three checks that reported on their fixtures

**Status:** Accepted, implemented

**Date:** 2026-08-24

**Context:** `scripts/check_documented_counts.py`, `Tests/test_lab_report.py`,
`docs/mutations/adr-0133-lab-report.json`,
`docs/mutations/adr-0144-documented-citations.json`

**Follows:** ADR 0151 (whose mutation table this makes re-runnable), ADR 0173
(the dev-dependency guard this reuses), ADR 0069 (the mutation harness)

## Context

Three failures in one sitting, each the same shape: a check that reported a
result about **the environment it happened to run in** rather than about the
code it named.

### 1. The fixer that undercounted the tests it was fixing

`check_documented_counts.py --write` exists so a contributor who adds a test
does not hand-edit six lines across two files. It was run twice from an
interpreter without `cffconvert` and `python-libsedml`.

A module that skips at import is **not collected**. pytest reports a clean
run that is roughly 38 tests short. So the fixer wrote 1,179 where CI
measures 1,217 — and wrote it with every appearance of a fresh verification,
which is worse than the stale number it replaced.

Nothing failed, so the existing `skipped` path could not see it. That path
watches for a suite that *could not be collected*; this suite collected
perfectly and was simply missing whole modules.

### 2. A refusal the guard announced but did not perform

The first fix set `skipped = True` and printed
`REFUSING to write test counts`. `rewrite()` never reads `skipped` — it gates
on `{"make_test", "engine", "literature"} <= set(actual)`. So the guard
printed its refusal and rewrote the counts underneath it.

Caught by diffing README across the run instead of believing the message.
**A guard that announces a refusal it has not performed is worse than the bug
it was added to stop**, because it converts a silent error into a documented
one that is still wrong. The fix withholds the three keys from `actual`,
which is the thing `rewrite` actually consults.

### 3. A test that reached its branch by luck

`test_the_absence_of_refusals_is_stated_rather_than_left_blank` asserted that
`report()` — the default fixture — contains *"Nothing was withheld"*. It never
constructed a report with no refusals. It passed because that fixture happened
to have none.

When the tissue-source check landed, the fixture's Km began refusing
**correctly**: it differs between diseased and healthy breast, and saying so is
the product working. The default grew a refusal, the else-branch stopped being
reached, and the test went red with nothing it describes broken.

The consequence reached further than the file. One red test makes every
mutation look caught, so `mutate.py` refuses to grade the suite at all:

> The baseline suite has 1 failing test(s) before any mutation.

`docs/mutations/adr-0133-lab-report.json` was therefore ungradable, and ADR
0151's *"6 of 6 caught"* had stood since it was written with no way for a
reader to re-run it.

## Decision

**1.** `--write` checks the declared dev dependencies directly (reusing
`check_dev_dependencies.missing_python()`) and removes the test-count keys
from `actual` when any are absent — naming the missing package. Guard and ADR
counts, which do not depend on collection, are still written.

**2.** The test constructs both branches. `resolved={}` reaches the empty case
on purpose, and a second assertion requires the claim to be **conditional**: a
report that does refuse must not say nothing was withheld. That half guards
itself — if the default ever stops refusing, it fails and says the case proves
nothing rather than passing vacuously.

**3.** ADR 0151 is declared on the sets that are its evidence, via `covers`.

That last one corrects a misreading of my own. I had recorded 0151 as a
**design gap** — a record reporting a re-run of someone else's set having no
honest route through the guard. It is not a gap. `covers` is exactly that
route, added for ADR 0033/0035 when two records shared one suite. 0151
presents no mutations of its own; its table is 0133's set re-graded and 0144's
set re-run. Copying those mutations into a file named for 0151 would put one
fact in two places and let the copies drift, which is the thing a set file
exists to prevent.

## Verification

Both directions, not one:

- The short interpreter leaves `README.md` **byte-identical** (`md5` compared
  across the run) and names `python-libsedml, cffconvert, pyinstaller`.
- The provisioned interpreter restores 1,217 / 1,115 and the guard reports
  `OK: README test counts and domain counts match the repository.`
- `check_documented_counts.py --selftest`: 4 guard-count, 6 ADR-count and 6
  welded-number forms; `rewrite()` changed digits and nothing else.
- `Tests/test_lab_report.py`: 23 passed.
- `adr-0144-documented-citations.json`: **3 caught, 0 not caught**.
- `adr-0133-lab-report.json`, against a green baseline for the first time:
  **6 caught, 0 not caught** — reproducing 0151's claim exactly.
- Mutation Table guard: 70 ADRs presenting results, 51 reproducible, 19
  grandfathered. Its selftest still passes.

## Consequences

- The counts fixer can no longer manufacture an authoritative undercount, and
  says which package is missing rather than which number it wrote.
- ADR 0151's mutation table is re-runnable by a reader, which it was not on
  the day it was written.
- The lab-report suite has a green baseline, so its set can be graded at all.

**What this does not check.**

- **Only Python dev dependencies.** `missing_python()` covers what
  `requirements-dev.txt` declares. A test skipped for any other reason — a
  missing binary, an absent env var, a platform guard — removes tests from the
  count in exactly the same way and is still invisible here.
- **The check is on the writer, not the reader.** Running the guard *without*
  `--write` from a short interpreter still compares README against an
  undercount and fails, giving a red build for an environment problem. The
  message does not yet say so.
- **Nothing prevents the third failure recurring.** A test can still reach its
  branch through a fixture rather than by construction, and no guard detects
  it. This one surfaced because the fixture changed; the ones whose fixtures
  have not changed are still passing for reasons nobody has checked.
