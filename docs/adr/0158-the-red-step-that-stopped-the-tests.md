# ADR 0158 — The red step that stopped the tests

**Date:** 2026-08-22
**Status:** Accepted
**Amends:** [ADR 0143](0143-the-first-command-a-stranger-runs.md) — the
placement, not the decision

## Context

Seven passes have ended with "CI is red, and one step is red on purpose."
This one asked what the rest of the job was doing.

`check_quickstart_clone_works.py` was **step 32 of 52**. A GitHub Actions
job stops at its first failing step. So the twenty steps after it never ran:

- Build guards (`verify_build.py --quick`)
- Simulation engine tests
- Literature layer tests

**Every test in this repository stopped running in CI on 2026-08-21.**

The signal was in plain sight for a day and nobody read it, including me,
across three passes that quoted the run durations: every run finished in
**about 55 seconds**. A real suite takes seven minutes. I had the number in
front of me and treated it as noise.

## Decision

Move the two clone-guard steps to the end of the job.

ADR 0143's argument survives intact and is not revisited: the finding is
true, muting it would be recording the problem instead of fixing it, and the
build stays red on every push until the repositories are published. **What
changes is only where it sits.** ADR 0143 said nothing about ordering,
because the cost of the ordering was not noticed — a guard can be correct,
verified, honest about its limits, and still disable everything behind it.

`scripts/check_ci_red_step_is_last.py` now fails if any expected-red step
precedes a step that runs a test suite or a build guard.

It is wired **above** the step it protects. Placed after, a guard against a
step that stops the job would itself be stopped by that step — the bug,
committed by its own fix.

`EXPECTED_RED` is an explicit list, not something inferred from the YAML:
"which steps are allowed to fail" is a decision somebody makes, not a
property a script can read off a file.

## Verification

- `--selftest` drives both verdicts on constructed step lists rather than on
  the tree, so it cannot pass by matching nothing.
- **Mutation:** re-inserting a clone-guard step after
  `check_pins_resolve` failed the guard, naming steps #32–#47 as the range
  that would not run. Restored, verified by `diff`.
- Every Python guard in the job was run locally first: 22 of them, all
  green. That is what made the ordering the only remaining explanation.

## What this will surface, and it is not new breakage

`check_ci_reproducible_locally.py` is **already failing** with 19
unclassified CI steps, of which 17 predate this pass — the diagnostic `echo`
steps added on 2026-08-21, `check_ci_toolchain`, and
`check_availability_notice_matches_reality`. It runs in the pytest wrapper,
which is one of the suites that has not been running.

So the ordering bug was also concealing a guard's own failure. The next CI
run will show it. That is the guard working, not a regression, and it is
said here so the next reader does not spend a pass re-diagnosing it.

The two steps added by this ADR are classified; the other seventeen are
someone else's to explain, and inventing reasons for them would be worse
than leaving them named.

## Consequences

- 2,278 tests run in CI again.
- The badge stays red until publication, which is the point of ADR 0143.
- Guard count 70 → 71.
- A new class is covered: **a guard whose position, not whose logic, is the
  defect.** Everything in `scripts/` until now checked what a step does.
- The `test` job will get slower — seven minutes rather than 55 seconds —
  because it is finally doing the work it claimed to.

## Related

- [ADR 0143](0143-the-first-command-a-stranger-runs.md) — the deliberate
  red, whose reasoning is unchanged
- [ADR 0028](0028-buffer-identity-from-pubchem.md) — where the "a guard that
  cries wolf gets suppressed" reasoning is recorded; this is the harder
  version, a guard that suppresses everything else
