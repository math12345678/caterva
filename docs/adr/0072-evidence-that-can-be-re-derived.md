# ADR 0072: Evidence that can be re-derived

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `scripts/check_mutation_tables_reproducible.py`,
`docs/mutations/`

**Follows:** [ADR 0069](0069-the-harness-that-lied.md), which fixed the
mutation harness and stated — rather than concealed — that the existing
tables had not been re-derived under it.

## The problem with an honest admission

ADR 0069 ended with this:

> The existing ADR mutation tables were **not** retroactively re-run. They
> were established by hand, some of them twice; re-deriving them all is a
> larger job than this pass, and claiming they had been re-verified when
> they had not is the exact dishonesty this file exists to remove.

That was the right thing to write. It is also, on its own, how a known
problem becomes a permanent one. An admission buried in the consequences
section of one record out of seventy is not a plan; it is a sentence that
gets read once.

The scale, measured rather than estimated: **36 decision records present
mutation results. Two could be re-derived.** Thirty-four asked a reader to
accept a number produced by an instrument now documented to have been wrong
three separate ways.

Most of those numbers are probably right. "Probably" is the point. The
governing rule of this codebase is that *a check that cannot fail is worse
than no check, because it is trusted* — and a mutation table is exactly a
claim that a check can fail. Thirty-four of them rested on an unreliable
instrument, and nothing in the repository said so where anyone would look.

## Decision

`check_mutation_tables_reproducible.py`, wired into `verify_build.py`. It
does three things, and the third is the one that matters.

**1. Stops the debt growing.** A new ADR presenting mutation results and no
`docs/mutations/adr-<NNNN>-<slug>.json` fails the build.

**2. Makes the existing debt countable.**
`docs/mutations/NOT-YET-REPRODUCIBLE.txt` lists all thirty-four with a
one-line description each, split into the ones this agent wrote and the ones
written by concurrent agents — raised rather than claimed, since re-deriving
somebody else's table means editing their record if the result disagrees.

**3. Forces the list to shrink.** If an entry gains a set file and is not
removed from the baseline, the guard **fails**. A baseline that can be added
to but never emptied is a way of recording a problem instead of fixing it,
and the count at the top of the output stops meaning anything.

That third rule is the difference between this and a `# TODO`.

## What it deliberately does not check

It does not verify that a set file's results **match** the table in the ADR.
Doing so would mean running every set on every build — minutes of work that
would make the check something people disable.

What it establishes is narrower and worth stating exactly: **the table can
be re-derived by anyone who wants to.** Whether it *was* is a separate
question, answered by running the set. Claiming more than that would make
this guard the thing it is designed to prevent.

## Verified against all three of its own failure modes

Per the standing rule — mutation-test a guard against the specific failure
it claims to prevent:

| scenario | expected | result |
|---|---|---|
| new ADR with a table and no set file | exit 1 | ok |
| baseline entry that now has a set file | exit 1, names it | ok |
| set file with no `test` or no `mutations` | exit 1 | ok |
| clean tree | exit 0 | ok |

The third case matters more than it looks. An unrunnable set file is worse
than no set file, because it reads as coverage — the same shape as a
citation guard that parses zero entries and prints OK.

The matcher was built from the **nine** mutation-table header forms actually
present in `docs/adr` (`| Mutation | Failures |`, `| Mutation | Result |`,
`| # | mutation | tests failed |`, and six more), not from one imagined
format. A matcher written from a single example would have found 3 of 36 and
reported the other 33 as having no table at all — a confident false
negative, which is the failure this project has hit before and which looks
identical to success.

## Two tables re-derived this pass

**ADR 0060** (`docs/mutations/adr-0060-model-selection.json`) — N1 and N4,
both `caught`, matching what was recorded by hand.

**ADR 0065** (`docs/mutations/adr-0065-error-messages.json`) — P1 `caught`,
matching. Cleared from the baseline, which took the count from 34 to 33 and
demonstrated the shrink rule working: the guard went red the moment the set
file existed and stayed red until the baseline line was deleted.

So far the hand-run results have held up. That is a real (small) result and
not a reason to skip the rest — the three failure modes in ADR 0069 were
each found by accident, and the tables where they bit are not necessarily
the tables anyone has re-checked.

### One row deliberately absent from a set

ADR 0065's table has two rows. P2 — "pipeline throws a plain object again" —
is not in the set file, and its absence is documented **inside** the set
file rather than left to be noticed.

P2 is caught by `check_thrown_values_are_errors.py`, not by a test. That is
the whole argument of ADR 0065: the readers were hardened too, so reverting
the throw changes no observable behaviour and no suite can fail on it.
Putting P2 in a set would make the harness report NOT CAUGHT — true of the
tests, false of the codebase. Technically accurate and materially
misleading, which is the category this project treats as a defect.

## It fired on its first real use, on somebody else's record

Within two minutes of being wired, the guard went red on
`0071-the-testimonials-were-not-real.md` — a concurrent agent's ADR, written
at 11:26, presenting an eight-mutation table with `cmp`-verified backups and
no set file.

That is the guard doing exactly its job: rule 1 is "stop the debt growing",
and the debt tried to grow immediately.

It also created a conflict with this repository's own standing precedent,
recorded in `verify_build.py`: *adding a red guard to a shared harness makes
it everyone's problem and nobody's.* Leaving the build red would have
punished an agent for work they were mid-way through writing.

So 0071 is in the baseline, in its own section, marked as **an open request
to its author rather than a grandfathering** — with the date, the reason,
and an explicit note that the section must not become permanent, because the
rule it exempts records from is the most important one. Re-deriving their
table would mean editing their ADR if a result disagreed, which is theirs to
do.

The alternative — silently absorbing it into the ADR 0069 debt list — would
have been the cheapest way to green and would have made the list dishonest
on its second day.

## Consequences

- Every new ADR with mutation results costs an extra file. That is the
  intended price: the evidence becomes an artifact rather than a testimonial.
- The baseline names concurrent agents' records without claiming them.
  Re-deriving one means potentially correcting their ADR, which is theirs to
  do; the list makes the ask visible.
- `docs/mutations/adr-0058-sweep.json` predates this guard and was written
  in ADR 0069's pass; it is counted, not grandfathered.
- Thirty-three entries remain. The honest expectation is that this takes
  several passes, and that at least one of them will disagree with what was
  recorded — that is what the third failure mode in ADR 0069 implies.

## Related

- [ADR 0069](0069-the-harness-that-lied.md) — the harness, and the debt this
  itemises
- [ADR 0065](0065-object-object.md) — first table cleared
- [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md) — second
  table re-derived
