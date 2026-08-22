# ADR 0160 — A reproducibility claim with nothing behind it

**Date:** 2026-08-22
**Status:** Accepted

## Context

Every lab report Terrium produces has contained this sentence since the band
section was built:

> Seed 1 — re-running with it reproduces this band exactly.

True, and unusable. Re-running with **which version**?

A report carried no commit, no date, and no record of the command. So the
one document this project exists to produce — the thing a student hands in,
and the thing a reviewer would examine — asserted reproducibility and
withheld the only fact needed to act on it.

That is the house defect at the worst possible address. *Computed and not
delivered* has been found eight times in this repository; this is its
inverse and its most expensive form: **the claim delivered, the means
withheld**, in a tool whose entire argument is that its numbers can be
re-derived, whose most engaged correspondent directs the NIH Center for
Reproducible Biomedical Modeling.

## Decision

Every report ends with how it was produced: the Terrium commit, the UTC
timestamp, and either an invitation to reproduce it or a refusal to claim
it is reproducible.

### Three states, because a dirty tree is not the commit

Printing `commit abc1234` while the working tree has uncommitted changes is
the most confident kind of wrong. A reader checks out `abc1234`, gets
different numbers, and has no way to discover why — the code that ran was
not that commit.

| tree | printed | verdict |
|---|---|---|
| clean | `abc1234` | "re-run with the same seed and every number should come back identical" |
| modified | `abc1234 plus 12 uncommitted change(s)` | **"This document is not reproducible as it stands"** |
| not a git checkout | `unknown` | same refusal, different reason |

The third state is real — a tarball install, a copied directory — and "I do
not know" must not render as a blank line a reader takes for "nothing to
report".

The first report produced after this change refused to vouch for itself,
because the working tree was dirty. That is the feature working on its first
run.

### Deliberately absent

A hash of the inputs. `scientificPipeline` already computes one; this
function cannot see it, and a second implementation would be a second thing
to keep true. Named as absent rather than half-built.

## The mistake I made writing the tests, which is the useful part

The first four tests monkeypatched `_code_version` wholesale and asserted on
the rendered markdown. They passed.

Then the mutation: replacing `if dirty.returncode == 0 and dirty.stdout.strip():`
with `if False:` — deleting dirty detection entirely — and **all four still
passed.** They were tests of the wording standing in for tests of the logic,
which is the exact shape this repository has recorded five times in one
session and which I had just written a paragraph about avoiding.

The fix was not another assertion. `_code_version` now takes a `root`, so
`test_the_dirty_tree_DETECTION_works_against_a_real_repository` builds a
real git repository in `tmp_path`, commits, checks clean, modifies a file,
and checks dirty. The same mutation now fails it.

A function that can only be tested by stubbing it is a function whose logic
nothing tests.

## Verification

- 23 cases in `Tests/test_lab_report.py`, up from 19.
- **Mutation, twice on the same line.** Before the refactor: not caught.
  After: `test_the_dirty_tree_DETECTION_works_against_a_real_repository`
  fails. Both restores verified by `diff`.
- The rendering tests are kept — they check the three verdicts read
  correctly — but they are no longer the only thing standing between this
  and a silent regression.

## Consequences

- Every report can be traced to the code that produced it, or says why it
  cannot be.
- Test count +4.
- A report generated from a dirty tree now carries a visible warning. That
  will be most reports during development, which is correct and will feel
  noisy — the alternative is a document that quietly claims more than it
  can support.

## Related

- [ADR 0027](0027-one-reliability-score-not-two.md) and the *computed and
  not delivered* line of ADRs — this is that defect inverted
- [ADR 0145](0145-the-notice-that-outlives-its-subject.md) — the other ADR
  about a true sentence that stops being usable
