# ADR 0184: The audit ADR 0183 asked for

**Status:** Accepted, implemented

**Date:** 2026-08-25

**Context:** `scripts/mutate.py`

**Follows:** [ADR 0183](0183-the-guard-that-read-the-failures-and-said-ok.md),
which named this as unchecked

## Context

ADR 0183 fixed a guard that read a JUnit report full of failures and printed
OK, and closed by naming what it had not established:

> **Nothing checks that a guard reporting on a suite reports everything the
> suite told it.** This one was found because CI disagreed with it. Whether
> another guard is discarding a category of result the same way has not been
> audited.

This is that audit. Three scripts parse test outcomes:

| script | verdict |
|---|---|
| `check_documented_counts.py` | not affected — uses `--collect-only`, so it counts tests that *exist*; whether they pass is not its question |
| `check_no_silent_skips.py` | fixed in ADR 0183 |
| `check_ci_toolchain.py` | not an outcome parser; the grep hit prose in its docstring |
| `mutate.py` | **defect found** |

## The finding

`mutate.py` decides whether a mutation was *caught*, and its `failures`
property matched only the word `failed`.

pytest reports a **collection** failure as `error`. A mutation that breaks a
module another test imports at module scope produces:

```
===== 22 passed, 1 error in 4.2s =====
```

Read through the failure patterns alone: 22 tests run, zero failures — the
suite ran cleanly and the mutation was **NOT CAUGHT**.

It was caught. The error *is* the suite noticing. And a false NOT CAUGHT is
the verdict this file singles out as the worst it can produce, because it
reads as a real gap in the tests and sends someone to write a test for a
case that is already covered.

**The pure error case was always handled.** `1 error in 0.31s` carries no
test count, so `ran` is False and the verdict is INDETERMINATE — the
existing three-state discipline working exactly as designed. What slipped
through was the **mixed** case: most of the suite collecting and passing,
one module failing to import. That is the ordinary shape of this failure,
not an exotic one.

## Decision

`failures` counts errors as well as failures, summed rather than either/or —
`1 failed, 21 passed, 1 error` is two objections, and reporting one would
understate what happened.

| output | before | after |
|---|---|---|
| `23 passed` | NOT CAUGHT | NOT CAUGHT |
| `1 failed, 22 passed` | caught | caught |
| `1 error` (pure) | INDETERMINATE | INDETERMINATE |
| `22 passed, 1 error` | **NOT CAUGHT** | **caught** |
| `1 failed, 21 passed, 1 error` | caught (1) | caught (2) |

## Verification

- The harness selftest gained three cases, and they are asserted through
  `SuiteRun` rather than by running a suite that errors on collection: the
  *parsing* is what was wrong, and a real erroring suite would also be
  missing a test count — the other path — and would pass for the wrong
  reason.
- Sabotage: reverting the error patterns fails the two new cases and leaves
  the third passing, which is the shape a real regression would have.
- `mutate.py --selftest` passes, and `adr-0144-documented-citations.json`
  still reproduces 3 caught / 0 not caught, so no recorded verdict moved.
- 41/41 guards green.

## Consequences

- A mutation caught by breaking an import is no longer recorded as missed.
- The audit ADR 0183 asked for is done, and found one real defect in the
  three places that could have had it.

**What this does not check.**

- **No existing mutation table was re-graded.** The bug could only produce a
  false NOT CAUGHT, and the tables in `docs/mutations/` record almost
  entirely *caught* verdicts, which this change cannot have altered. A
  recorded NOT CAUGHT that was really a collection error would still be
  wrong today — none is known, and none was searched for.
- **jest and vitest are matched on one pattern each**, guessed from their
  documented output rather than observed. The pytest patterns are the ones
  measured against real output.
- **The audit covered scripts that parse test results.** A guard that
  discards a category of some *other* input — a linter's output, a build
  log — would not have been found by it.
