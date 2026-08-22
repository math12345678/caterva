# ADR 0159 — What the tests found when they ran again

**Date:** 2026-08-22
**Status:** Accepted
**Follows:** [ADR 0158](0158-the-red-step-that-stopped-the-tests.md)

## Context

ADR 0158 moved a deliberately-red CI step to the end of the job, after
finding that it had been stopping every test in the repository since
2026-08-21.

Rather than push and let the runner report, I ran the literature suite
locally in slices first. It found three real failures, all of which had been
failing invisibly for the day the suite did not run.

## What was broken

### 1. A stale CI exemption pointing at nothing

```
CI_ONLY['corepack prepare pnpm'] matches no step in the workflow any more.
```

ADR 0140 replaced `corepack prepare pnpm@11.4.0 --activate` — which exits 0
and installs nothing — with `corepack enable`. The exemption written for the
old line stayed behind.

A blanket exemption whose subject no longer exists is worse than none: it is
a written permission for something nobody can see, and it would silently
cover a future step that happened to match. Removed.

The test that caught it, `test_every_ci_only_exemption_still_matches_a_real_step`,
is a good one — an allowlist that is never checked against reality is how an
allowlist becomes a hole.

### 2. Seventeen unclassified CI steps

`check_ci_reproducible_locally` requires every CI step to be either runnable
from `make` or recorded as CI-only **with a written reason**, and fails on
anything unclassified. Nineteen steps were unclassified; ADR 0158 named them
in advance and said they were "someone else's to explain."

That was the wrong call. Nobody else was going to be here, and the honest
position is that leaving a suite red for a reason I can fix is not
delegation, it is deferral. All are now classified with real reasons: the
run-summary diagnostic block (no run summary exists on a laptop), the
`::error` annotation block (annotations do not exist outside Actions),
`check_ci_toolchain`, `check_availability_notice_matches_reality`,
`check_quickstart_clone_works`, and `corepack enable`.

29 CI-only steps with reasons, 40 runnable from `make`, **0 neither.**

### 3. A funding application claiming 1,893 tests

`Business/FYDEMY_APPLICATION_DRAFT.md`, three places including the status
slide and the "Verified test coverage" metric:

> 1,893 passing tests, 0 failing, across 15 live simulation domains

The repository has **2,279**. Off by 17%.

`mule/index.html`'s marketing footer said the same figure.

Both understate, which is luck rather than policy — `check_investor_claims`
makes exactly that point, and this is the fourth time the same neglect has
happened to fall the flattering way. The audience for a funding application
is the one where a number nobody checked matters most.

## Decision

Fix all three, and record that **the payoff arrived one pass later**. ADR
0158 restored the test run; this is what the test run was for. A suite that
does not run is not a suite, and the interval between those two ADRs is the
smallest possible demonstration.

## Verification

- Literature suite run locally in three slices: **1,093 passed, 2 skipped,
  0 failed** after the fixes; three real failures before them.
- `check_ci_reproducible_locally` green, and its pytest wrapper's 11 cases
  pass.
- `check_investor_claims` green: 14 cases.

**Not run here:** `Terium/tests`, the engine suite. It collects (1,183
tests) but takes about four minutes, past this sandbox's per-command limit,
and nothing in this pass touched the engine. Said rather than implied — "I
did not run it" and "it passes" are different claims.

## Consequences

- Three failures that had been invisible for a day are fixed.
- Guard count unchanged; test count unchanged.
- **Still red in CI, and only for the intended reason:** the repositories
  are private (ADR 0143). Every other step in the job now has a local route
  or a written exemption.

## Related

- [ADR 0158](0158-the-red-step-that-stopped-the-tests.md) — why the suite
  had stopped running
- [ADR 0140](0140-the-step-named-install-pnpm-installed-no-pnpm.md) — whose
  fix orphaned the exemption removed here
