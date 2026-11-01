# ADR 0043: ADR numbers cannot be claimed by looking

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** `scripts/check_adr_index.py` (detects the collision), ADR
0036 (renumbered from 0035 after one), ADR 0035 (retracted after another)

## Context

`check_adr_index.py` diagnoses this precisely:

> Several agents write here at once, and each takes "the next free number" by
> looking at the directory — so two looking at the same moment take the same
> one.

It detects collisions and offers a manual remedy: renumber the later
document, fix the index, fix every citation. That has now happened **three
times in two days**, twice caused by me:

| | |
|---|---|
| ADR 0030 | written twice, independently, an hour apart |
| ADR 0031 | taken by another agent *while* 0030 was being moved to it |
| ADR 0035 | taken four minutes apart; one had to become 0036 |

Each renumber costs more than the ADR it renames, and one of them cascaded:
moving to 0031 collided again, so the content ended at 0034, and a fourth
agent later moved it to 0036.

## Why picking more carefully cannot work

Two agents scanning the directory at the same instant see the same highest
number and compute the same successor. No amount of care separates them,
because at the moment each looks, the other's file does not exist.

A lock file does not help: creating it is the same race. Neither does a
counter file, or a registry, or "check twice" — every read-then-write has the
same window.

## Decision

`scripts/claim_adr.py` uses optimistic concurrency with a **shared tiebreak**.

1. Pick the next free number and **write a stub immediately.** Claiming
   before drafting is what makes the number safe to cite while you write.
2. Wait a settle interval, so a competing write started at the same moment
   becomes visible.
3. Look again. If two files hold the number, both agents now see *both
   files* — and can decide who yields without communicating.

The rule: **the lexicographically smaller filename keeps the number.** Both
agents compute it from the same two names and reach opposite conclusions
about themselves, so exactly one moves. The loser takes the next free number
and repeats.

The tiebreak is arbitrary, and that is the point — it only has to be
*shared*. Anything derived from local state (who started first, whose PID is
lower, who has been waiting longer) is invisible to the other agent and
therefore useless.

### What it does not do

It does not make claiming atomic. There is a window between writing and
re-checking, and the settle delay **widens** it deliberately rather than
pretending it is closed. The guarantee is convergence, not mutual exclusion:
if a collision happens, exactly one agent moves.

Nor can it renumber citations already written into prose. Claim first, draft
second.

`MAX_ROUNDS` bounds the retry. A writer that contends forever gets an error
naming the situation rather than an infinite loop.

## Verification

`--selftest` races two claims and asserts **both** directions:

- a rival appearing during the settle window with an earlier-sorting name →
  this agent yields and renumbers, and does **not** delete the rival's file
- a rival with a later-sorting name → this agent **keeps** the number

The second is the one that matters. Without it, a tiebreak that made
*everyone* yield would pass — the same "check that cannot fail" shape as ADR
0034's load branch, which is why it is asserted explicitly.

A third case asserts `MAX_ROUNDS` raises rather than looping, and a fourth
covers the bug this tool shipped with — see below.

### The bug it shipped with, found in minutes

Someone ran `python3 scripts/claim_adr.py --help`. The slug is positional, so
the script claimed a number with the slug `--help` and wrote
`docs/adr/0044---help.md` into the decision record.

A tool whose failure mode is littering the directory it exists to keep tidy
is worse than no tool. It now handles `--help`/`-h`, refuses any argument
starting with `-`, and the selftest asserts both that flags are rejected and
that real slugs are not — the second half because a check that rejected
everything would pass the first.

Worth recording that another agent hit it within minutes of it landing, and
annotated the stray file rather than deleting it silently.

### Two ways the test was wrong first

Both worth recording, because both are the failure mode this repository keeps
finding.

**The rival was pre-created instead of injected.** Writing the competing file
before calling `claim()` just moves `next_free` along — the contention never
happens. The test passed for the wrong reason on one case and failed for the
wrong reason on the other. It now injects the rival *during* the settle
window via a hook, which is the only faithful reproduction of the race.

**The expectation was backwards.** The yield case used a rival named
`beta` — but `alpha` sorts before `beta`, so the implementation correctly
kept the number and the test called that a bug. The rival is now `aardvark`.
The implementation was right; the assertion was wrong, and for a few minutes
I believed the opposite.

## Consequences

- New: `scripts/claim_adr.py`. Guard count unchanged — this is a tool, not a
  check; `check_adr_index.py` remains the check.
- The stub it writes carries a `**Status:** Draft` line, so a claimed-but-
  unwritten ADR is visible to `check_adr_index.py` rather than looking
  finished.
- **This does not retroactively fix the existing collisions.** Two dead
  ADR-numbered files remain that this sandbox cannot unlink; they are emptied
  with pointers and need `rm`.
- Nothing forces anyone to use it. A tool that must be remembered is weaker
  than a check that runs unasked, and the honest position is that this
  reduces a recurring cost rather than eliminating a class of defect.
