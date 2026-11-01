# ADR 0151: The front page the guard never looked at

**Status:** Accepted, implemented

**Date:** 2026-08-21

**Context:** `scripts/check_documented_citations_are_real.py`,
`Tests/pytest.ini`, `Tests/test_lab_report.py`,
`docs/mutations/adr-0133-lab-report.json`

**Follows:** ADR 0144 (which wrote the guard), ADR 0148 (which found its
first two untested branches)

## Three findings, each one a check that could not fail

### 1. The guard listed three files and missed the two that matter

ADR 0144 removed `BRENDA ref 12345` — an invented citation — from
`README.md`, and added a guard so it could not come back.

`docs/readmes/main.md` and `docs/readmes/backend-main.md` still had it.

Those are the **front pages of published repositories**: the page a stranger
lands on from GitHub. The invented citation this project treated as a
credibility emergency sat on both of them for a day after the guard
forbidding it was written, because the guard enumerated three filenames by
hand and neither was among them.

**A hand-written list covers what its author remembered.** The surface set
is now *derived* — `_NAMED_SURFACES` plus every `docs/readmes/*.md`,
discovered the same way `check_published_repo_readmes.py` already treats
that directory. Twenty surfaces instead of three, and the eighteenth
published README is covered on the day it is added, by nobody.

`_MIN_SURFACES` rose from 3 to 10 to match: a floor counting only the
hand-written names would not notice the whole discovered set vanishing.

### 2. `Tests/` was green or red depending on the working directory

`spread_consequence.py` imports the engine lazily:

```python
from caterva.continuous.simulations import simulate_michaelis_menten
```

`caterva` lives at the repository root, so that resolves when pytest runs
from the root and fails when it runs from inside `Tests/`.
`pytest test_lab_report.py` reported **2 failures** from there and 16 passes
from one directory up. A contributor sees red and reasonably concludes they
broke something.

`caterva/pytest.ini` has carried `pythonpath = . ..` since the package split,
for exactly this reason. `Tests/pytest.ini` never got the line. It has it
now, and the suite is green from both directories.

**Found by the mutation harness refusing to work.** Asked to grade ADR
0133's table, it reported:

> The baseline suite has 2 failing test(s) before any mutation. A mutation
> judged against a red baseline says nothing: a test that was already
> failing 'catches' everything.

The tool would not produce a verdict, and the reason it gave was the bug.

### 3. ADR 0133's table claimed a mutation that was not caught

Re-derived, L1 — *"an unsourced parameter is skipped instead of shown as not
sourced"* — came back **NOT CAUGHT**, having been recorded as caught.

The cause is precise and generalises. Deleting the `not sourced` **row from
the Parameters table** leaves the *refusals section* intact, and every test
in the file asserted on the refusal. Two separate code paths inside one
function — one renders the table, one builds the refusal list — and testing
the second says nothing about the first.

That is ADR 0038's rule about call sites, applied *within a single
function*, which is a place nobody thinks to look for it.

`test_an_unsourced_parameter_still_has_a_row_in_the_table` closes it: a
reader scanning the table for `ki` must **find it there, marked**, rather
than have to notice an absence. Absence is precisely what a reader cannot
see — which is the sentence ADR 0133 opens with, about a defect it then
carried.

## Consequences

- `check_documented_citations_are_real` covers 20 surfaces, and a test
  asserts the published-README set is derived rather than enumerated —
  so re-listing them by hand fails.
- Its own set file still reproduces: 3 caught, 0 not caught.
- ADR 0133's table: **6 of 6 caught**, after one test was added.
- `check_mutation_tables_reproducible` is down to four ADRs: 0125 and 0128
  (pre-existing debt), and 0146 and 0150, which are other agents' work
  currently in flight.
- `check_documented_counts` and `check_guard_wiring` both green.

## The pattern this session keeps producing

Every finding above was a check that reported success on work it had not
done, and in each case something *refused to proceed* rather than passing:
the harness would not grade an uncounted suite, would not grade a red
baseline, and would not choose between three identical find-sites.

**A tool that says "I cannot tell" is worth more than one that answers.**
Every defect in this ADR was surfaced by a refusal, not by a failure.
