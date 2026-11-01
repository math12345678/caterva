# ADR 0095: The exemption inside the widening

**Status:** Accepted

**Date:** 2026-08-16

## Context

`check_documented_counts.py` opens with a comment naming its own recurring
failure:

> A correct guard on too narrow a scope. Same shape as ADR 0055 [...] and as
> ADR 0027 before it. Third time.

It was written when the guard scanned `README.md` alone and three other
documents had drifted beside it. The fix widened it to eleven present-tense
contributor documents and added an ADR-count matcher, because
`docs/INTERN_ONBOARDING.md` had been offering newcomers "23 decision
records" when there were 56.

Inside that widening sits an exemption:

```python
if relative == "README.md":
    continue  # already checked above, in more detail
```

The detailed check above covers test counts, domain counts and guard
counts. **It has never covered ADRs.** So the ADR matcher ran against every
contributor document except the one every newcomer opens, and
`README.md:449` read:

```
│   └── adr/                    23 decision records (and counting)
```

`docs/adr/` held 93.

The matcher was never broken. `--selftest` asserts it catches
``"`docs/adr/` — 23 decision records"``, verbatim, and had been passing the
whole time. **The guard proved it could find this exact sentence, and was
never pointed at the file containing it.**

That is the fourth instance of the shape, and a different one from the
first three. Those were fixed by widening scope. This one was created by
the widening — an exemption justified by a claim about other coverage that
was not true.

### The other half: a correct check as a contribution barrier

At the same time, five counts were failing:

```
make_test:   README says 1,998, actual is 1,967
engine:      README says 1,179, actual is 1,141
literature:  README says 819,   actual is 826
line 451:    claims 61 guard scripts; scripts/ contains 62
line 537:    claims 61 guard scripts; scripts/ contains 62
```

All five drifted within about an hour of concurrent agent work, and the
guard's advice was *"Update README.md"* — a six-line hand-edit across two
sections of a 24 KB file, for figures the script had just computed. A
contributor whose change adds one test gets a red build and a scavenger
hunt.

This is not hypothetical drift. While this ADR was being written, adding
eleven tests moved three more numbers.

## Decision

**The README is held to the ADR rule.** `adr_failures()` is split out and
called for the README from `main()`. `check_other_docs()` still skips it,
but only to avoid reporting the same line twice, and the comment now says
that instead of claiming coverage that does not exist.

**`--write` corrects the counts the guard derives**, exposed as
`make counts-fix` and documented in `CONTRIBUTING.md`. Deliberately not
folded into `make guards`: a check that silently edits your working tree is
not a check. You ask for the write.

**What `--write` refuses to touch is the substance of the design**, and is
where most of the tests went:

- **the simulation-domain count.** The guard already declines to derive it,
  because `DISPATCH` includes a run-mode and a generic ingest path that are
  not teaching domains, so any automatic figure encodes a judgment call. It
  checks the two claims agree with *each other* and leaves the number to a
  person. A `--write` that picked one would bury that judgment in a script
  and present the result as measured.
- **quoted counts.** `docs/README.md` explains an exclusion by quoting a
  stale figure. "Correcting" a quotation edits the evidence to match the
  claim.
- **approximate figures inside tolerance.** `~60` becoming `~62` converts a
  deliberately loose statement into a false-precise one and teaches writers
  that hedging buys nothing.
- **test counts from an incomplete collection.** If any suite fails to
  collect, the test counts are unknown, and an invented number a tool has
  just written reads as *freshly verified* — strictly worse than a stale
  one.

That last rule lives in `rewrite()`, not in `main()`. The first version was
a wholesale refusal in `main()`, which turned out to be both unreachable
and wrong: unreachable because with no test counts to compare there are no
failures, so `--write` is never entered; wrong because guard and ADR counts
come from file globs and have nothing to do with whether pytest can
collect. Blocking those on an unrelated collection failure leaves a
contributor unable to fix the thing they actually broke.

`CONTRIBUTING.md` also said the guards were *"thirty-six small scripts"*
when there are 62. The number is spelled out in words, so no matcher reads
it. It has been removed rather than replaced: the sentence is about the
guards in one CI job, not the contents of `scripts/`, so any digit put
there would be a differently-wrong number that then *looks* checked.

## Consequences

- `make guards` runs green again, and a contributor who adds a test fixes
  the README with one command.
- The README can no longer carry a stale ADR count.
- Six numbers in the README are now maintained mechanically; the domain
  count is still maintained by a person, on purpose, and the guard still
  fails if the two claims disagree.

### What this does not fix

`--write` only knows what the guard derives. A count in prose form
("thirty-six"), or in a document outside `PRESENT_TENSE_DOCS`, is still
unchecked and unfixable. The honest response to one of those is to delete
it rather than to guess.

## Mutations

Re-runnable:

```
python3 scripts/mutate.py --set docs/mutations/adr-0095-the-exemption-inside-the-widening.json
```

| id | mutation | result |
|---|---|---|
| R1 | the README is exempted from the ADR rule again | caught |
| R2 | the ADR tolerance widens enough to swallow a gap of 70 | caught |
| W3 | `--write` starts rewriting the domain count | caught |
| W4 | `--write` corrects quoted examples too | caught |
| W5 | `--write` sharpens an approximate figure | caught |
| W6 | `--write` writes a test count from a partial collection | caught |
| W7 | `--write` drops the thousands separators | caught |
| W8 | `--write` is not idempotent | caught |

**The mutation run found a defect in the tests rather than the code.** The
first version of `test_main_with_write_never_touches_the_real_readme`
called `main()` with `--write` against the live tree. `scripts/mutate.py`
keeps its backup beside the file it mutates, so during the run
`scripts/check_*.py` globbed to 63, and `--write` faithfully recorded
*"63 guard scripts"* in the real `README.md`. The harness restored the
script it had mutated and had no reason to restore the README, so the edit
survived — a plausible number nobody typed, left in the file this ADR is
about.

The test now writes to a `tmp_path` copy. A test that writes to the working
tree can leave the repository wrong when it fails, and this one did.

## Related

- ADR 0094 — the previous pass; a check that computed the right number and
  compared it to the wrong thing
- ADR 0055, ADR 0027 — instances one and two of "a correct guard on too
  narrow a scope"
- ADR 0069 — why mutation tables ship as re-runnable set files
