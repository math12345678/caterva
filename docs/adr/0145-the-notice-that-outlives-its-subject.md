# ADR 0145 — The notice that outlives its subject

**Date:** 2026-08-21
**Status:** Accepted
**Supersedes:** nothing. Extends [ADR 0143](0143-the-first-command-a-stranger-runs.md).

## Context

ADR 0143 established that every documented `git clone` in this project fails
for a user with no credentials, and wired `check_quickstart_clone_works.py`
into CI **red on purpose** — a true finding about the project's single most
important sentence, left visible rather than baselined.

That decision is correct and this one does not revisit it.

What it does not do is reach anybody outside the building.

A CI log is read by people with push access. The person the finding is
*about* — "a stranger who found this on GitHub", in START_HERE.md's own
opening line — never sees it. Their experience today is unchanged by the
guard existing: they read the front page, run line one, are asked for a
username, and draw the only available conclusion, which is that they did
something wrong.

Confirmed rather than assumed, on 2026-08-21:

| repository | anonymous `git ls-remote` |
|---|---|
| `Terrium-sim/main` (documented) | not readable |
| `Terrium-sim/terrium` | not readable |
| `math12345678/terrium` (origin) | not readable |

Nineteen `git clone` commands across README.md, START_HERE.md,
CONTRIBUTING.md and `docs/readmes/` point at the first of those. The
documented URL is not a typo — `Tests/test_clone_instructions_agree.py`
records the deliberate choice of `Terrium-sim/main` over `origin` as the
intended public home. The repositories simply are not published.

## Decision

**The front page says so, and a guard makes that sentence expire.**

README.md and START_HERE.md now carry a short notice above the quickstart
stating that the repositories are private and that line one is as far as an
outside reader gets.

`scripts/check_availability_notice_matches_reality.py` checks the notice
against reality **in both directions**.

## Why the second direction is the whole point

A one-directional check here would have been easy and nearly worthless.

This notice rots in a specific, predictable way. On the day the repositories
are published it stops being helpful and becomes actively harmful: a front
page telling qualified visitors that the thing they can plainly clone is
unavailable to them. Nothing would go red. Nothing goes red when a *true*
sentence stops being true — every guard in this tree fires on claims that
were wrong when written.

And the people positioned to notice are exactly the people who cannot: they
have had access all along, so the notice has never applied to them and their
eyes pass over it.

That is this repository's most-repeated defect wearing the other face.
*Computed and not delivered* (ADR 0027, 0038, 0039, 0047, 0113) is a fact
that never reached the page. This is a fact that reached the page and then
stopped being a fact.

## The four states

Reachability and the notice are independent, so there are four cases, and
the guard answers each rather than collapsing them into a boolean:

| clone reachable | notice present | verdict |
|---|---|---|
| no | yes | **OK** — today. The honest state. |
| yes | no | **OK** — published, notice removed. |
| no | no | **FAIL** — private and undisclosed. |
| yes | yes | **FAIL** — stale notice turning visitors away. |

The fifth state is the one a boolean would hide: *the probe could not run*.
No network, GitHub down. That exits **3** and asserts nothing about the
notice, because "I could not see" must never become "it is fine" — the
standing three-state rule, and the reason ADR 0143's probe has two positive
controls and a negative one. This guard imports that probe rather than
writing a second one, so there is one thing to keep true about GitHub and
not two.

## What counts as a notice

The sentinel `**Not public yet.**` **and** a link to ADR 0143 in the same
document. Both are load-bearing, and the selftest proves it by rejecting a
document carrying the sentinel alone.

Requiring both is deliberate. A bare marker string is a guard you satisfy by
typing the marker. A marker that must carry its reasoning with it makes the
cheapest way to pass also the correct one, and keeps the notice and the
decision behind it from drifting apart.

## Verification

- `--selftest` drives all four states plus the sentinel-without-ADR case and
  asserts the exit code of each. A guard whose verdict did not actually
  depend on both inputs would pass an entire dimension while vouching for it.
- **Mutation, on the real tree:** replacing `**Not public yet.**` with
  `**Heads up.**` in README.md turned the guard from exit 0 to exit 1 naming
  README.md. Restored from a pristine copy and the restore verified by
  `diff` — this project has once before left a mutation in the tree after a
  `cp` restore silently failed.

## Consequences

- Guard count 69 → 70.
- The first guard here that fires on a sentence being *no longer* true
  rather than *never* true. Worth naming as a class: every other check in
  `scripts/` asks "was this wrong when written".
- The notice is deletable in one edit per file, and CI tells you the day it
  should be. The publication checklist does not have to remember it.
- Not in `make guards`: it reaches GitHub twice, and a slow local target
  stops being run (ADR 0028). CI-only, registered as such, for the same
  reason as its sibling.
- **Still not fixed:** the repositories are private. This ADR makes the
  situation honest to a visitor; it does not make Terrium obtainable. That
  remains one action by the owner, and ADR 0143's red CI step remains the
  thing that goes green on the day it happens.

## Related

- [ADR 0143](0143-the-first-command-a-stranger-runs.md) — the guard this one
  extends, and the red build it is right to keep
- [ADR 0028](0028-buffer-identity-from-pubchem.md) — where the "a guard that
  cries wolf gets suppressed" reasoning is recorded, and why this one is not
  in the fast local path
- `Tests/test_clone_instructions_agree.py` — why the documented URL is
  `Terrium-sim/main` and not `origin`
