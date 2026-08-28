# ADR 0186: The audit that was a coin flip

**Status:** Accepted, implemented

**Date:** 2026-08-27

**Context:** `scripts/check_guards_refuse_on_empty.py`,
`scripts/check_guard_wiring.py`, `.github/workflows/tests.yml`

**Follows:** [ADR 0185](0185-three-guards-that-passed-on-an-empty-tree.md)

## Context

The guard set was audited twice by hand for guards that report OK having
examined nothing: copy each into an empty directory, run it, see whether it
still says OK.

It found five real defects. **It also produced five false positives**, and
the false ones were not near-misses:

- Four conditional guards (*"the waitlist form does not exist, so nothing
  here collects an email address"*) were flagged because a heuristic looked
  for a digit and they state their denominator in prose.
- `check_python_bug_lints` was flagged although it already refuses with
  *"none of ['Tests', 'scripts', 'Terium'] exist; nothing was checked"* — it
  had passed only because the guard file itself sat in `scripts/`, a real
  target with a real file to lint.

The second round also revealed the tree was **not empty**: the guards had
been copied into `scripts/`, which several of them scan, so
`check_package_spelling` reported reading 54 Python files — its own
siblings — and cleared its new floor on them.

Every real finding survived only because it was checked individually
afterwards. A measurement that is right half the time, and whose errors are
caught by hand, is not a measurement. It is a habit that will lapse.

## Decision

**The procedure becomes a guard.**

`check_guards_refuse_on_empty.py` starves every `scripts/check_*.py`: a
fresh temporary directory, the guard copied into `_starved/` — a name no
guard scans, which is the fault the hand-run version had — and run there.
Exit 0 is a failure, because there was nothing to be clean.

**Conditional guards are exempted with the sentence they print**, not with a
summary of it. If the behaviour changes, the sentence changes, and the
mismatch is visible to whoever reads the list next. Four are listed.

**The exemptions are checked in both directions.** A listed guard that
starts refusing is reported too: the entry has gone stale and is protecting
a case that can no longer arise. An exemption that cannot expire is a rubber
stamp — the rule already applied to `check_no_silent_skips`'s optional-extra
exemption.

**"Refused" means any non-zero exit,** including a guard that crashes on an
import rather than refusing in prose. That is weaker than a clean refusal
and is counted anyway, because the property under test is "does not report
success on nothing" and a traceback does not report success. Said here so
the pass is not read as more than it is.

## Verification

Three sabotages, each caught:

| sabotage | result |
|---|---|
| plant a guard whose whole body is `print("OK: everything is fine")` | named, exit 1 |
| disable the floor ADR 0185 added to `check_rng_convention` | named, exit 1 |
| list a guard that genuinely refuses as conditional | reported as a stale exemption, exit 1 |

The second matters most: it means the floors from ADR 0185 cannot be quietly
removed.

The selftest plants a guard that always passes and one that always refuses,
and asserts the starved tree contains **exactly one file** — so a starve
that silently stopped starving cannot look identical to a working one. That
assertion is the one the hand-run version needed and did not have.

Clean run: **73 starved, 69 refused, 4 conditional.** The report asserts
those numbers reconcile, after an earlier version printed "73 starved, 73
refused, 4 exempt" — three true-looking numbers that cannot describe the
same 73 guards, because the exempt-and-passing ones were folded into
`refused`.

Wired into CI with its selftest as a separate step, and registered in
`check_guard_wiring`'s `EXPECTED_WIRING` so losing that step later is caught
rather than accepted. CI only, deliberately: 73 subprocesses is a minute
nobody wants inside `verify_build --quick`.

## Consequences

- A new guard must refuse on an empty tree or be listed as conditional with
  its reason. The default is now the safe one.
- The five floors added in ADR 0183 and 0185 are held in place by something
  that runs unasked.

**What this does not check.**

- **Only one kind of broken.** An empty tree is not a tree with the right
  shape and the wrong content — a scan root present but silently filtered to
  nothing would still pass.
- **It does not read the exemption reasons.** They are strings; nothing
  verifies the sentence quoted is the sentence the guard prints, only that
  the guard still passes on nothing.
- **A guard that crashes counts as refusing.** See above. Nothing here
  distinguishes a reasoned refusal from an ImportError.
- **The four conditional guards were judged by hand,** by the same procedure
  this record calls a coin flip. They were each read individually, which is
  what made the difference before, and that is not a check either.