# ADR 0094: The guard the fix broke

**Status:** Accepted

**Date:** 2026-08-16

## Context

Two defects, found one after the other, with the same shape: **a check that
computed the right number and compared it to the wrong thing.**

### `make guards` was red, and I made it red

ADR 0093's pass found that `START_HERE.md`, `README.md` and
`git remote get-url origin` gave three different answers to the first
command a newcomer runs. The fix made them agree and wrote an explanation
into `START_HERE.md` recording the disagreement, because an unverified URL
is survivable and an unrecorded one is not.

That explanation quotes three repository slugs in backticks:

    `Terrium-sim/main.git`, `Terrium-sim/terrium.git`, `math12345678/terrium.git`

`check_doc_paths_resolve.py` matches backticked tokens containing a slash
and a short suffix, and reported all three as missing files. Exit 1. `make`
stops at the first failing recipe, so every guard after it stopped running
too, for every contributor.

The guard exists because a wrong path — `Tests/test_brenda_flags.py` — was
typed into `CONTRIBUTING.md` *while its author was fixing other wrong
paths*. It was then taken down by prose typed while fixing prose. The
lesson it was built to teach applied to it.

### The index's first sentence was wrong by a factor of two

`DOCUMENTATION_INDEX.md` opened:

> The repository root holds 81 markdown files.

It holds 41. That sentence is the first line of the file every other
document routes newcomers to, and it survived the archive move that made it
false.

`Tests/test_archive_counts_are_current.py` was written one pass earlier to
stop precisely this, and its own comment draws the distinction correctly:

> The archive count is a live fact about a directory and is asserted. "The
> root went from 98 to 41" is NOT: it is a dated statement about what the
> move achieved.

Both sentences were in the same file. The dated one, on line 43, was
guarded. The undated live one, on line 3, was not — and the module computed
`root_count()` and then never compared it to anything.

## Decision

**A token ending `.git` is a remote repository, not a path claim about this
tree.** It is *delegated* to `Tests/test_clone_instructions_agree.py`
rather than skipped, and the delegation is verified: if that test stops
reading clone commands or stops matching `.git` URLs,
`check_doc_paths_resolve.py` fails rather than continuing to exempt three
tokens nothing checks. Three outcomes — resolved, delegated, broken — not
two.

**The floor counts what was verified, not what was seen.** This is the part
that took two attempts and is the whole reason the ADR is worth writing.
The first version kept the floor on the total token count, so a classifier
that routed *everything* to "somebody else checks this" cleared a floor of
20 with 61 tokens while checking none of them. Green, trusted, vacuous. The
floor now counts in-tree references only, so swallowing the input trips it.

**Tense decides what a number needs.** `holds N` is a live claim and is
pinned to the directory. A sentence carrying `as of YYYY-MM-DD` is a dated
claim and is left alone, but must keep its date. Both are asserted, so
neither style can be quietly swapped for the other to satisfy the test by
deleting what it checks.

**`root_count()` asks git what is in the repository.** It globbed, and
counted `.aider.chat.history.md` — gitignored, untracked, present in no
clone. The prose figures (98, then 41) came from a shell glob, which skips
dotfiles. The function and every number it was destined to be checked
against had been measuring different sets since the day it was written, and
that was invisible for exactly as long as nothing compared them. The first
real assertion failed instantly: 41 against 42.

## Consequences

- `make guards` runs to completion again.
- The `.git` exemption cannot outlive its justification. Deleting the
  delegate fails this guard, with a message naming what stopped being
  checked.
- A vacuous classifier cannot report success, because the floor moved to
  the verified count.
- The opening sentence of `DOCUMENTATION_INDEX.md` now fails a test when it
  drifts, in either direction: wrong number, deleted sentence, or relabelled
  as dated.
- `root_count()` changed meaning by one. `test_the_root_has_actually_been_reduced`
  (`< 60`) is unaffected.

### What this does not fix

Which clone URL is *correct* still needs someone with network access.
`docs/RENAME_PLAN.md` has carried that since the naming review and this
changes nothing about it. What is now guarded is that the entry points
agree with each other and that the disagreement with `origin` stays
recorded.

## Mutations

Re-runnable:

```
python3 scripts/mutate.py --set docs/mutations/adr-0094-the-guard-the-fix-broke.json
```

All ten caught. Two are worth reading:

| id | mutation | result |
|---|---|---|
| P1 | the delegate stops reading `git clone` | caught |
| P2 | the delegate-check drops its `.git` condition | **escaped first, then caught** |
| P3 | the remote classifier matches nothing | caught |
| P4 | the remote classifier matches everything | caught |
| P5 | the floor counts tokens seen, not verified | caught |
| A6 | the index says "holds 81" again | caught |
| A7 | the live sentence is deleted | caught |
| A8 | the live sentence is relabelled as dated | caught |
| A9 | `root_count()` globs dotfiles again | caught |
| A10 | the dated claim stops needing a date | **indeterminate first, then caught** |

**P2 escaped.** `handoff_is_live()` has three conditions — the delegate
exists, reads `git clone`, matches `.git` — and one test between them,
which exercised only the first. Deleting the third condition passed all 22
tests. Three branches and one test is how a branch survives being deleted;
`test_each_condition_on_the_delegate_can_fail_on_its_own` now drives each
separately.

**A10 came back INDETERMINATE**, because its search string had come to
appear twice — in the original assertion and in the presence test added
beside it. The harness refused to guess which one it had edited. That
refusal is the feature: a coin flip between two call sites would have
produced a confident verdict about an edit nobody could identify.

**P5 changed the design.** The hole needs two things at once — a floor
counting tokens seen, and a classifier swallowing them — and `mutate.py`
applies one edit per row. The row was first written with an `also` key the
harness does not have, which would have applied half the mutation, reported
on something that never happened, and been believed. The property is
asserted in a test instead, which supplies the swallowing classifier
itself; the row now mutates only the floor.

## Related

- ADR 0093 — the clone-URL disagreement whose fix broke this guard
- ADR 0091 — the archive move that made the index's opening sentence false
- ADR 0069 — why mutation tables ship as re-runnable set files
- ADR 0089 — `check_no_vacuous_tests.py`, the same failure in test form
