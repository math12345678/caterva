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

## The first version of this shipped as zero bytes

Everything above was written, run and sabotage-tested. Then the file was
committed **empty**, and CI went green.

The restore after the third sabotage was
`git checkout $G || gh api ... > $G`. There is no git metadata in a tarball,
so the checkout failed; the shell created and truncated the redirect target
before the API call ran; the API call errored. A 12 KB file became 0 bytes.

**Every check downstream was satisfied by a file that merely existed.** An
empty Python file exits 0, so both CI steps passed. `check_guard_wiring`
found the name in the workflow. `check_ci_reproducible_locally` found the
`make` route. The record said 73 guards were being starved while nothing
was. And the verification run immediately afterwards — grepping the file for
stray content left by the sabotage — reported clean, **because grepping an
empty file finds nothing**.

That is this repository's own defect, produced by the commit that added the
guard against it, and it survived four checks and one hand-verification.

`_MIN_SELF_BYTES` closes it for this file: below 2 KB it has been truncated
and says so. Sibling guards are checked too — a zero-byte guard is reported
as *empty*, not as "passes on nothing", because the second understates it:
there is no guard there at all. The selftest asserts an empty file exits 0,
so the reason the size check exists is recorded next to it.

Found only because a later probe — a tree shaped like the repository but
containing no files — showed this guard passing with no output at all.

## Consequences

- A new guard must refuse on an empty tree or be listed as conditional with
  its reason. The default is now the safe one.
- The five floors added in ADR 0183 and 0185 are held in place by something
  that runs unasked.

**What this does not check.**

- **Only one kind of broken.** An empty tree is not a tree with the right
  shape and the wrong content. Probed separately: with every top-level
  directory present but empty, six guards still pass. Four are the listed
  conditionals; the fifth was this file when it was empty; the sixth is
  `check_python_bug_lints`, whose refusal covers *absent* targets
  (`none of ['Tests', 'scripts', 'Terium'] exist`) and not present-but-empty
  ones. That last is a real gap and is **not fixed here** — the shaped probe
  is not wired into anything, so it remains a measurement someone took once.
- **It does not read the exemption reasons.** They are strings; nothing
  verifies the sentence quoted is the sentence the guard prints, only that
  the guard still passes on nothing.
- **A guard that crashes counts as refusing.** See above. Nothing here
  distinguishes a reasoned refusal from an ImportError.
- **The four conditional guards were judged by hand,** by the same procedure
  this record calls a coin flip. They were each read individually, which is
  what made the difference before, and that is not a check either.