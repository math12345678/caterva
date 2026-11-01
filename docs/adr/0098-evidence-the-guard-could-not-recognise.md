# ADR 0098: Evidence the guard could not recognise

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `scripts/check_mutation_tables_reproducible.py`,
`scripts/claim_adr.py`, `docs/mutations/NOT-YET-REPRODUCIBLE.txt`

**Follows:** [ADR 0072](0072-evidence-that-can-be-re-derived.md), which built
the guard, and [ADR 0069](0069-the-harness-that-lied.md), which is the record
it could not recognise.

## The record that could not be discharged

`NOT-YET-REPRODUCIBLE.txt` lists ADR records whose mutation tables came from
the hand-run harness that ADR 0069 found had been wrong three separate ways.
It is supposed to shrink. One entry had been sitting on it with this note:

> **0069** — the harness that lied; its own self-test **is** reproducible
> (`mutate.py --selftest`, wired into verify_build) … this entry is close to
> discharged already and should be the first to go.

It was not close to discharged. It could not be discharged at all, and the
reason is a property of the guard rather than of the record.

ADR 0069's table is not mutations of product source. It is the harness
proving that a patch which does not apply, a replacement identical to the
original, and a suite reporting no test count are each reported
INDETERMINATE rather than "not caught" — the three ways the old harness gave
a wrong answer. There is no set of mutations that reproduces that.
`mutate.py --selftest` reproduces it exactly, and `verify_build.py` runs it
on **every build**.

So the evidence was not merely re-runnable. It was being re-run — a stronger
guarantee than any set file in that directory, all of which are re-runnable
and none of which are re-run automatically. The guard counted it as
unchecked debt regardless, because it recognised exactly one shape of
evidence.

Verified before acting on it, rather than taken from the note:

```
  [ok] search string absent: INDETERMINATE
  [ok] replacement identical to the original: INDETERMINATE
  [ok] suite reports no test count: INDETERMINATE
  [ok] file restored after every case
  [ok] a real mutation against a passing suite: NOT CAUGHT
```

Five lines, against the ADR's five rows, label for label. They agree.

## Why this is Sauro's warning, in the tooling

Herbert Sauro's objection to a tool that refuses too readily was that it
**pushes researchers to hardcode** — faced with a check they cannot satisfy
honestly, people satisfy it dishonestly, and the check ends up certifying
the thing it was built to prevent.

The two ways to clear 0069 were:

1. write a set file that does not actually reproduce the table, or
2. leave the record on the debt list forever.

Option 1 is fabricating evidence to satisfy an evidence guard. Option 2
makes the count at the top of the file a number that includes discharged
items, and **a debt list that counts discharged items sends people to work
on things already done.**

Neither is acceptable, and the refusal was the guard's fault, not the
record's.

## Decision

A set file may present its evidence as a **command the build already runs**:

```json
{ "reproduced_by": "scripts/mutate.py --selftest" }
```

and `check_mutation_tables_reproducible.py` **fails** unless
`verify_build.py` really runs it.

The check is the whole design. An alternative route nobody verifies is a
hole, not an alternative — without it, any future record could opt out by
naming a command, and the guard would be back to trusting a label. The gate
is also self-limiting in a useful way: to use `reproduced_by` you must get
your command into `verify_build.py`, which means it runs on every build,
which is a cost nobody pays except for something genuinely cheap and
genuinely self-verifying.

Matching is by script basename plus every argument, on one line, because
`verify_build.py` *composes* its commands:

```python
f"python {SCRIPTS_DIR / 'mutate.py'} --selftest"
```

An exact string match on `scripts/mutate.py --selftest` finds nothing there
and would report every honest claim as unwired — the confident false
negative this project hit when a matcher built from one imagined format
found 3 of 37 tables and reported the other 34 as clean.

## The guard had no self-test

It was wired into `verify_build.py` enforcing on other people's records a
rule it did not meet itself: *a property defended only in prose is a
property that stops being checked* (ADR 0058's M3, ADR 0072's set file, ADR
0079's comment-stripper, ADR 0090's four hand-run scenarios).

Eleven cases now, and **the mutations found two of them by finding their
absence.**

## What the mutations found

| # | mutation | expected | result |
|---|---|---|---|
| M1 | `reproduced_by` matching: `and` → `or` | caught | caught |
| M2 | delete the unrunnable-set check (`elif False`) | caught | **NOT CAUGHT**, then caught |
| M4 | neuter the per-entry key check | caught | caught |
| M3 | revert `slugify` to what the tool shipped with | caught | caught |

Re-derivable: `python3 scripts/mutate.py --set
docs/mutations/adr-0098-evidence-the-guard-could-not-recognise.json`

### M2: eight cases, one unexercised branch

I wrote eight self-test cases and believed them thorough. Replacing the
unrunnable-set check with `elif False:` was **not caught**: every case
either shipped a valid set file or took the new `reproduced_by` branch that
sits in front of it. The branch the guard had enforced since the day it was
written was the one branch nothing exercised.

That is the argument for mutating a guard rather than reading it. Two cases
added; now caught.

### M2, second time: a crash is not a refusal

With the per-entry check added, M2 stopped being *not caught* and became
**INDETERMINATE** — the mutant crashed. The new loop read `spec["mutations"]`
directly, which is safe only because the `elif` above it establishes the key
exists. Mutating that `elif` made the line raise.

An invisible coupling between two branches, and the cost was concrete: no
verdict could be obtained on the mutation at all. Changed to
`spec.get("mutations") or []`. This is the harness refusing to call a crash
a detection, working exactly as ADR 0045 built it to.

## The set file that passed the guard and killed the harness

This record's own set file was written with entries keyed `search` instead
of `find`. The guard called it reproducible. `mutate.py` then died on
`KeyError: 'find'` — after the baseline had run.

The guard's docstring says *"an unrunnable set file is worse than none: it
reads as coverage"*, and it was deciding runnability from the **outer shape
only**: `test` present, `mutations` present, nothing asked about what was
inside. The presence of a container taken as evidence about its contents —
the same half-check as a baseline whose matcher could not see classes
(ADR 0090) and a citation guard that parsed zero entries and printed OK.

`REQUIRED_MUTATION_KEYS = {"file", "find", "replace"}` — the keys `mutate.py`
indexes with no default — are now checked per entry. All 32 existing set
files pass, so the check is real and not merely newly-added.

## A documentation filename with spaces in it

`claim_adr.py` was invoked as

```
claim_adr.py "evidence the guard could not recognise"
```

and produced `docs/adr/0098-evidence the guard could not recognise.md`. The
tool's own error text invited it: *"Quote it if the title contains spaces."*
Quoting is how the spaces get **into** the name.

This is the third instance of one bug in that file. It already refuses a
flag passed as a slug, and refuses a stringification artefact passed as a
slug (`0065-object-object.md` exists because that check did not). Both ask
what the slug **means**. Neither looked at its **shape**.

Spaces in a path here are not cosmetic. This repository's advice is
copy-pasteable shell, its link checker walks markdown paths, and
`split_repos.sh` copies these files by name — and each of those breaks
somewhere other than where the name was chosen.

`slugify()` now normalises rather than rejects, because the intent is
unambiguous and `claim()` prints the path it actually created. Six cases in
the self-test, including one asserting that an already-correct slug passes
through untouched — a normaliser that rewrites valid input silently changes
every existing caller.

## An aside that argues for `--write` better than its docstring does

`check_documented_counts.py` was red on arrival this pass, for counts that
had drifted under concurrent work. Correcting them took two rounds, because
**the ADR count went from 97 to 98 between two consecutive runs of the same
command** — another agent landed a record while this one was being checked.

Three literature-test counts in `docs/readmes/` were hand-corrected, which
that tool deliberately declines to do: `863 tests.` with no antecedent on
the line could mean any suite, and a fixer that picked one would be
inventing an attribution. Both lines here name the literature layer in
prose, so the attribution was a reader's call and a reader made it.

The ADR counts were not hand-corrected. `--write` already covers every
checked document for guard and ADR counts, and in a tree with several
agents writing, hand-editing a derived number is a race you lose while
typing.

## Consequences

- The debt count was **18 and is 17**, and the correction is downward. The
  entry removed was the only one on the list written by this agent, which
  the previous pass's record described as "none of them mine". That was
  wrong, and it was wrong in the direction that lets a debt sit.
- Seventeen entries remain, all written by concurrent agents, all raised
  rather than claimed.
- `reproduced_by` is deliberately narrow. It is not "explain why you have no
  mutations"; it is "name a command this build runs", checked.

## Related

- [ADR 0069](0069-the-harness-that-lied.md) — the record this could not
  recognise
- [ADR 0072](0072-evidence-that-can-be-re-derived.md) — the guard amended
  here
- [ADR 0045](0045-a-guard-for-the-boundary.md) — `exit_code` verdicts, and
  the refusal to call a crash a detection
- [ADR 0090](0090-the-capability-nobody-could-reach.md) — a baseline only as
  honest as the matcher that fills it
- [ADR 0093](0093-a-linter-configured-and-never-run.md) — configured, and
  running nothing
