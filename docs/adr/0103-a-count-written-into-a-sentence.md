# ADR 0103: A count written into a sentence

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `scripts/check_documented_counts.py`, `README.md`

## What was there

Adding ADR 0101 made four documented ADR counts stale, so I ran the guard
that checks them. It reported the four, and while reading its output I
noticed the line above:

```
├── docs/                       ADRs1,129 engineering constitution, API docs
```

`git show HEAD:README.md` has:

```
├── docs/                       ADRs, engineering constitution, API docs
```

An **engine test count** had been written over the comma in a sentence that
was never about tests. Uncommitted, in a file with 121 uncommitted
insertions from a concurrent agent.

## The part I could not establish

I could not reproduce it. Replaying `rewrite()` against HEAD's README with
`engine=1129` produces the four expected count updates and no corruption.
The intermediate state that produced it is gone, and I am not able to say
which `--write` run, or whose, did it.

So this ADR does **not** claim a root cause. It records a corruption that
reached a tracked file, and what was done about a defect whose cause cannot
be reconstructed.

## Decision 1: make it detectable

`check_documented_counts.py` now checks whether a formatted number is welded
onto a word — `(?<=[A-Za-z])\d{1,3},\d{3}` — across all 28 present-tense
docs.

This is the failure mode a guard about documented counts is uniquely placed
to catch and had no opinion about. It counted the numbers and never looked
at what they were glued to. A corruption nobody can explain will recur, and
the second occurrence should be caught rather than noticed.

Deliberately narrow. Measured against every markdown file in the repository
before being wired in: **one hit, the real one**. `SBML2`, `CC BY 4.0`,
`Python3.11` and `ADR 0055` do not match. A matcher that flagged version
strings would be suppressed within a week and would then catch nothing
(ADR 0028).

`--write` cannot repair these — the original wording is gone — so the
failure message says to restore it by hand. The README's line was restored
from HEAD's wording.

## Decision 2: replace by position, not by text

The writer substituted with:

```python
m.group(0).replace(m.group(2), shown, 1)
```

which replaces the first occurrence of the group's **text** anywhere in the
match. That is the right place only while no pattern can see those same
characters earlier in its own match. Today none can: every prefix is a
literal containing no digits. It is now `_splice(m, 2, shown)`, positional.

**This is not presented as the cause.** It is a latent unsafety found while
looking for one, and `[\d,]+` matching a bare comma is close enough to the
observed shape to be worth closing regardless.

## What made this worth writing up

The first version of the fix was untestable in the way this project keeps
rediscovering. I added a property assertion — *rewriting must change digits
and nothing else* — and then reverted the splice to `.replace` to check the
assertion earned its place.

**It stayed green.** Of course it did: no current pattern can reach the bug,
which is the same fact that makes the fix safe. A fix whose absence nothing
detects is indistinguishable from no fix.

So `_splice` became a named function with a case that *does* separate the
two spellings:

```python
collision = re.compile(r"(~)?12 x (\d+)").search("12 x 12")
_splice(collision, 2, "99")            # '12 x 99'
collision.group(0).replace("12", "99", 1)   # '99 x 12'
```

Three mutations, all now caught: defanging the detector, over-broadening it
(fires on `SBML2` and `Python3.11`), and reverting the splice.

## Consequences

- One class of silent document corruption is now a build failure rather
  than something noticed in passing.
- The guard's own repair path is held to a property — it changes digits and
  nothing else — instead of being trusted because it is a fixer.
- The cause remains unknown and is recorded as unknown. If it recurs, the
  check will name the file and line the moment it happens, which is the
  evidence this pass did not have.
