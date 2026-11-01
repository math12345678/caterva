# ADR 0112: The input where the refusals fire

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `scripts/check_both_front_ends_read_it.py`,
`docs/mutations/adr-0112-both-front-ends.json`, `scripts/verify_build.py`

**Follows:** [ADR 0110](0110-the-finding-that-reached-half-the-users.md),
which wrote the guard, could not verify it, and unwired it again.

## The debt, paid

ADR 0110 ended with a guard that was written, green, correct as far as
anyone could tell — and **deliberately kept out of `verify_build.py`**,
because mutation testing returned **0 caught, 3 not caught**.

The guard was not what was wrong. All three mutations delete a failure path,
and against the real tree the guard is green: nothing unreviewed, nothing
stale, both sides non-empty. **Removing a check that is not firing changes
no output**, so no verdict could be had.

The fix was never a better mutation. It was an input where the refusals
fire.

`--selftest` builds one: a temporary tree with two source files, a stubbed
key set, and a baseline it rewrites between cases. Six cases, and the
mutations became expressible the moment it existed.

| # | mutation | before | after |
|---|---|---|---|
| B1 | a new one-sided finding no longer fails | NOT CAUGHT | **caught** |
| B2 | the baseline can be added to but never emptied | NOT CAUGHT | **caught** |
| B3 | an empty side reads as "nothing is one-sided" | NOT CAUGHT | **caught** |

`python3 scripts/mutate.py --set docs/mutations/adr-0112-both-front-ends.json`

## B3 stayed uncaught, and the reason is the more useful half

With the self-test in place B1 and B2 flipped immediately. B3 did not.

The case set `CLI_GLOBS` to a directory that does not exist, so the CLI side
came out empty. Deleting the empty-side check let the guard carry on — and
then **every** key looked one-sided, including one the baseline did not
list, so the *unreviewed* check failed the build anyway.

The guard was defended twice, and the weaker defence was doing the work. A
mutation on the stronger one changed nothing observable.

That is the third time this pattern has appeared — ADR 0100's G2, ADR 0104's
T3, here — and it is worth naming: **a mutation that is a no-op against the
chosen input is not evidence of safety, it is evidence that the input was
chosen badly.** Twice before the honest answer was to withdraw the mutation.
Here it was to fix the fixture, because the dangerous case genuinely exists
and the fixture simply was not it.

The dangerous case is an empty side **when the baseline covers every key**:
the guard then reports "everything one-sided, everything accounted for" and
prints OK on a comparison that never happened. Only the empty-side check
stands between it and that. With the baseline listing both keys, B3 is
caught.

That is the standing trap in a new place — a guard that examined nothing
must not print OK, the same shape as the citation guard that parsed zero
entries.

## Wired now, and the delay was the point

`verify_build.py` runs the self-check and the guard. The comment at the
wiring site records that it arrived a pass late and why, because the rule
that kept it out is more valuable than the guard: *a guard whose refusals
have never been observed to fire does not go into a harness everyone runs.*

It was wired, the mutation run said no, it was unwired, the missing input
was built, and it is wired now. The rule worked on the person who wrote it.

## What the guard is reporting

Unchanged from ADR 0110, and still the reason any of this matters:

**79 keys emitted. 55 read by both front ends. 24 read by one, or neither** —
including `selectionTie` (Bakker's "the evidence did not choose", rendered
by the API, never mentioned by the CLI), `preparation` (ADR 0092), and
`column_taxon`/`commentary_taxon`, read by neither.

The debt can no longer grow silently. Paying it down is the next pass, and
`selectionTie` is the first one worth wiring: a CLI user is currently handed
the lowest of six equally well-evidenced rows spanning 306-fold with nothing
saying so.

## Consequences

- 64 guards, all wired, all with their refusals observed.
- The self-test is the input; the mutations are the evidence; neither works
  without the other. Worth stating because two passes were spent finding
  that out.

## Related

- [ADR 0110](0110-the-finding-that-reached-half-the-users.md) — the guard,
  and the decision not to wire it
- [ADR 0100](0100-the-container-was-not-the-contents.md),
  [ADR 0104](0104-the-title-of-the-paper.md) — the same no-op-mutation
  pattern, resolved by withdrawal rather than by a better fixture
- [ADR 0090](0090-the-capability-nobody-could-reach.md) — a property
  defended only in prose stops being checked
