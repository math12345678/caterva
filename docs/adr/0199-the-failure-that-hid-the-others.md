# ADR 0199: The failure that hid the others

**Status:** Accepted

**Date:** 2026-08-23

## Context

`make guards` is a sequential list of recipe lines, and make stops at the
first one that fails. That is correct for a gate. It is wrong for a report,
and the two had been the same command.

Across this entire session, `make guards` died at the **5th of 28** guards —
`check_forbidden_packages.py`, failing on two ADR index entries pointing at
another agent's uncommitted files. **Twenty-three guards never executed
once.**

Worse than the fact is what I did with it. I reported "only the two
pre-existing failures remain" **five times**, in five ADRs and five commit
messages, on the strength of having seen five guards out of twenty-eight. The
silence of the other twenty-three read exactly like success, and I passed it
on as such.

Running them individually found, immediately:

- A **guard wiring violation introduced by me**, that same session.
  `check_dev_dependencies.py` (ADR 0198) had no `EXPECTED_WIRING` entry, and
  the repository's Stage 4 amendment is that a guard is not delivered until
  something runs it unasked. Nothing had told me, because
  `check_guard_wiring.py` runs *after* the guard that was failing.
- A **TypeScript syntax error committed at HEAD**, in
  `terrium-landing/src/cli/CliApp.tsx`. Line 686 opens a JSX comment
  `{/* TESTIMONIALS -- removed ...` and line 700 closes it with `*/` and no
  `}`. One character. The file has not compiled since commit `982ebca`.

The second one is the sharper illustration. `check_typescript_compiles.py`
catches it correctly and is wired into `verify_build.py` — which fails on the
same ADR index entry, before it reaches the TypeScript stage. A guard that
works, a defect it detects, and a harness that never got there.

## Decision

**`make guards-all` runs every guard and reports all of them.**

`scripts/run_all_guards.py` reads the guard list from the Makefile's `guards`
target — read, not duplicated, since two lists would drift in exactly the way
this record exists to prevent — runs all 41 invocations, and prints a table.

Four outcomes per guard, not two:

| | |
|---|---|
| `OK` | exit 0 |
| `FAIL` | exit 1 or 2: it checked and found a problem |
| `UNDETERMINED` | exit 3: it could not check |
| `TIMEOUT` | it did not finish, so its verdict is unknown |

`TIMEOUT` is its own state because one guard (`check_no_silent_skips.py`)
runs both pytest suites and legitimately takes eleven minutes. A timeout is
this runner's limit, not the guard's verdict, and printing it as a failure
would be the runner making a claim the guard never made.

`make guards` is left exactly as it was. Fail-fast is right for the inner
loop; the first failure is the one to fix and the rest cost time nobody needs
to spend. `guards-all` is the command for *"what is the whole state?"*.

And the JSX comment gets its closing brace.

## Verification

The whole picture, for the first time:

```
41 guards in 793s.
  ok 37 · failed 4 · undetermined 0 · timed out 0

FAILED:
  scripts/check_forbidden_packages.py   FAIL: the ADR record is inconsistent
  scripts/check_doc_links.py            (links to those same two ADRs)
  scripts/verify_build.py --quick       FAIL: the ADR record is inconsistent
  scripts/check_no_silent_skips.py      FAIL: 5 skipped test(s), expected at most 0
```

**All four reduce to two causes**, and neither is a defect in this
repository's code:

1. Three of them are the same two ADR index entries — `0146` and `0150` —
   linking files another agent has not yet committed.
2. The fourth is ADR 0198's missing dependencies wearing a **third costume**.
   All five skips are `could not import 'cffconvert'` and `could not import
   'libsedml'` — the exact two packages `make deps-check` names. A guard
   whose subject is silent skips, failing for a reason that has nothing to do
   with skipping being wrong.

`check_guard_wiring.py` now passes with **73 guards**, after adding the
missing entry for `check_dev_dependencies` — declared `pytest` only, and
deliberately not CI, because CI installs from the manifest it would be
checking and could therefore only ever report success there.

The syntax fix, measured rather than assumed: TS1005 and TS1382 in
`CliApp.tsx` go from 2 to **0**. The workspace's total error count stays at
21, and that is not a null result — `terrium-landing` goes from 2 errors to
6, because a file that cannot be parsed reports only its parse error. Fixing
it *revealed* four errors that were behind it. All six are
`Cannot find type definition file for 'vite/client'` and `'vitest/globals'`:
missing packages, not code.

## Consequences

The state of this repository is now knowable in one command, and it is
better than I had been reporting: 37 of 41 guards pass, and every failure
traces to another agent's in-flight work or to two uninstalled packages.

**What this does not check.**

- **`guards-all` is not wired into anything.** It is a human command. Adding
  it to CI would double the pipeline's wall-clock for a report CI does not
  read, and `make guards` already gates. Nothing runs it unasked, which is
  the very property `check_guard_wiring.py` exists to complain about — it
  does not, because it is a runner rather than a `check_*.py`, and that is a
  gap in the wiring guard rather than a virtue of this one.
- **The Makefile is parsed with a regular expression.** Restructuring the
  `guards` target could silently reduce what `guards-all` discovers. It
  refuses to run rather than reporting zero guards if it can parse nothing at
  all, but a partial parse would go unnoticed.
- **`check_typescript_compiles.py` still exits 1**, and this record does not
  fix that. Nineteen of its twenty-one error lines are missing `node_modules`
  in four workspaces. Whether those workspaces should be installed, or the
  guard should distinguish "no dependencies" from "does not compile" the way
  ADR 0198's checker does, is a separate decision.
- **The one-character fix was not reviewed by whoever wrote that comment.**
  It restores a JSX comment to what it plainly intended to be, and nothing
  about the page's content changed — but it is a change to another author's
  file, made because it was broken, not because it was mine.
