# Stage 10, Part 23 — a full audit, and three guards that were lying

Stage: 10 · Part: 23 · 2026-08-11

## 1. What the audit found

Two subagents read the open findings independently; every claim below was
then reproduced by hand before anything was changed. Three of the findings
were guards reporting green on work they had not done — the defect class
this repository spends most of its effort on, this time inside the tools
built to catch it.

## 2. `check_no_silent_skips` said "every collected test ran" when 275 did not

```python
result = run_suite(path)
if result is None:
    continue          # <- a suite that could not run
ran_any = True
...
if not ran_any:       # <- needs only ONE suite to have worked
```

`run_suite` returns `None` on a timeout, an `OSError`, or output with no
parseable counts — a collection error or a module-scope import failure.
Stubbing the literature suite to fail reproduced it exactly:

```
  engine        857 passed, 0 skipped
  ! could not run Tests: simulated collection error

OK: 0 skipped (limit 0). Every collected test ran.
EXIT CODE: 0
```

275 tests did not run. In CI the `!` line scrolls past inside a green step.
That is this guard's own docstring — *"a green suite cannot distinguish
'ran and passed' from 'declined to run'"* — reproduced inside the guard
written to close it.

A suite that did not run now fails, and the success line names its
denominator: `OK: 2/2 suites ran, 1132 tests, 0 skipped`.

## 3. `check_guard_wiring` promised regression detection it never implemented

Its docstring:

> `EXPECTED_WIRING` records where each guard runs today, so that a guard
> silently *losing* a harness is caught too.

`EXPECTED_WIRING` appeared in exactly one place in the repository: that
sentence. The loop meant to enforce it was:

```python
for harness, present in (("verify_build", b), ("ci", c), ("pytest", p)):
    if present:
        continue
    key = (guard, ...)
    if key in DELIBERATE_OMISSIONS:
        continue
                                    # <- nothing appended, ever
```

A loop that computes a key, tests it, and falls off the end. So a guard
dropped from CI while remaining in `verify_build` was reported as *"all 19
guards run in at least one harness"* — the weaker claim the code actually
made.

**Third appearance of this exact shape**: `check_constant_usage` had a loop
with two `continue`s and no `errors.append` (Part 12), and
`check_citation_format` printed OK on a zero parse (Part 20). A loop that
cannot append is a check that cannot fail.

`EXPECTED_WIRING` now exists as a snapshot of fact, and records a floor:
adding a harness is accepted silently, removing one fails. Mutation-verified
three ways — dropping a guard from CI, a guard with no entry, and the clean
tree.

## 4. `verify_citations_live`'s URL section checked zero URLs

```python
print("\nStatic modelCitations URLs in queryResolver.ts (must resolve):")
...
if url and not url.endswith("/") and url not in urls:
```

`queryResolver.ts` contains exactly two URLs, both
`https://www.brenda-enzymes.org/`, and both end in a slash. Verified
directly: **2 raw URLs found, 0 survive the filter.** The section printed a
header saying "must resolve", iterated nothing, added zero to `failures`,
and fed a summary reading *"all literature checks passed live"*.

Not dormant. Live, and already vacuous.

Fixed along with the four dormant skips in the same file:

| skip | what it silently disabled |
|---|---|
| `DOI_SOURCE_FILES` per-file `continue` | moving `domain-literature.ts` drops 11 of 13 DOIs from the check |
| `claimed_titles()` early `return {}` | the TITLE-MISMATCH check, for every DOI, while every tick stayed green |
| CrossRef title `except: registered = ""` | the same, per DOI |
| the URL filter | the entire URL section |

The title check is the only part that verifies the *citation* rather than
the identifier. It exists because `10.1038/ng.3285` — a **recombination**-rate
paper — was cited to justify a **mutation** rate, resolved cleanly, and
passed. Degrading silently to "does this DOI exist" is the exact regression
it was written to prevent.

The summary now prints coverage it can be held to:

```
Coverage: 13 DOI(s) checked, 11 with title verification, 1 URL(s) checked.
  ! 2 DOI(s) got an existence check only — the DOI resolves, but nothing
    confirmed it is the paper being cited
```

Those two were previously indistinguishable from the eleven that were fully
verified.

## 5. Citation locators: exempt if you produced none

Every locator rule sat inside `citationLocators !== undefined`, and
`buildResolvedKineticProvenance` **stripped the property when the array was
empty**. So the one violation that catches "resolved, but nothing can
re-find the source" was unreachable from production and reachable only from
a hand-written test literal — which is what made it look enforced.

The net rule was: **produce zero locators and you are exempt from every
locator check; produce a wrong one and you are caught.** That inverts the
incentive.

Locators are now required on `resolved`, the constructor carries empty
arrays through, and `citationLocators` is a required argument — the same
argument the docstring already makes for `parameterKey`: *"an optional
parameter would have defaulted to the old, wrong behaviour and let the same
bug reappear at the next call site that forgot it."*

### The hazard that made this dangerous to land naively

Two definitions of "locatable" disagreed:

- `isLocatableCitation` accepts **any** ref id that is not empty or `n/a`.
- `buildCitationLocators` only yields one for a **DOI or a numeric id**.

A source supplying an accession — `SABIO:1234`, `P00338` — satisfies the
first and fails the second. Under the new hard rule it would be admitted as
`resolved` with zero locators, and `provenanceViolations` would **throw**:
`Internal error: invalid parameter provenance` in place of a working
literature answer. That is the ADR 0021 failure exactly, arriving through a
source nobody had added yet.

So the decision and the record are now one computation (`locatableCitation`),
and four accession shapes are pinned in `citeVerify.test.ts` with a
companion asserting a DOI and a PMID still resolve — so the test cannot pass
by everything returning empty.

## 6. `examples/python_integration.py`: ten of eleven endpoints did not exist

The orphan guard had flagged this file for stages as "imported by nothing",
which is the wrong diagnosis for an example — and a diagnosis nobody could
act on. Reading it against the real route table:

```
/api/health           the route is /api/healthz
/api/jobs/<id>        the route is /api/simulate/<jobId>
/api/export/jobs/csv  the route is /api/simulate/<jobId>/export
/api/jobs/query, /api/batch, /api/batches/<id>, /api/sweep,
/api/sweeps/<id>, /api/compare/jobs, /api/stats
                      no such routes, at all
```

Only `POST /api/simulate` was real. It also taught a parameter model the
product does not have — `{"query": ..., "parameters": {...}}` — where
Terrium reads parameters *out of the query text* and refuses to invent the
ones it cannot find.

The file was simultaneously unreachable and wrong, and the two conditions
hid each other: nothing imported it, so nothing tested it; nothing tested
it, so nobody read it.

Rewritten against the real API, and given a real job:
`scripts/check_example_endpoints.py` resolves every documented endpoint
against the routes Express actually registers. Examples are now exempt from
the orphan guard **and** checked by something stronger — an importer would
only have proven the file parses.

## 7. The domain classifier was one string test

```ts
const domain = request.query.toLowerCase().includes('michaelis') ? 'mm' : 'sir';
```

Every query without the literal word "michaelis" was classified as an
**epidemic model**. `simulate mm`, `enzyme kinetics`, `lactate
dehydrogenase` — all SIR. And it appeared **twice**, in `execute()` and
`resolveParameters()`, so the two halves of one request could disagree
about what was being simulated.

The CLI end-to-end test caught it in the most legible way possible: the run
resolved Km and Vmax from BRENDA, printed a correct enzyme provenance
table, and was then blocked for having no `beta`, `gamma` or `i0`.

Two things let it survive:

1. **Duplicated**, so the copies could never visibly disagree.
2. **The fallback was a specific domain, not "unknown"** — so a failure to
   recognise the query was indistinguishable from a confident answer.

Defaulting to a domain is defaulting a parameter, one level up.
`classifyDomain` now returns `undefined` when it cannot tell, and an
unplaced query is a validation failure — which matters because
`runSimulation` builds `km/vmax/s0` unconditionally, so an unplaced query
would otherwise have been silently simulated as Michaelis-Menten.

`SimulationRequest.domain` lets a caller that already knows say so. The CLI
knew: it parsed `--model mm`, then built the query string `"lactate
dehydrogenase / pyruvate"` and left the pipeline to infer a model from an
enzyme name. The interface already made this argument about `system` —
*"NOT inferred from `query` when absent"* — and it is the same argument.

### A test that was passing because of the bug

`should stop immediately on Layer 1 failure (no literature)` sent `'Unknown
enzyme kinetics'` and passed — because that was classified SIR, and the
sample literature (all Michaelis-Menten) had no beta. The name said "no
literature"; the literature was right there. Rewritten to assert what now
genuinely stops at Layer 1, with two companions pinning both directions of
the classification.

## 8. Retired, with the lesson kept

`brenda-real.ts`, `real-literature-service.ts` and `tellurium-real.py` are
gone. A subagent verified empirically that the "make it a test fixture"
route does not even work here — the orphan guard rejects test-only imports
with its own separate violation — and that a test asserting their defects
would be **defect-preserving**: it goes red the day someone fixes the file.

What was worth keeping was ~15 lines of prose, now in `provenance.ts` above
`STRENDA_GOVERNED_FIELDS`:

```ts
kmUnit:      entry.kmUnit  || 'mM',
temperature: entry.temperature || 25,
pH:          entry.pH || 7.0,
dataQuality: this.scoreDataQuality(entry)
```

Every `||` is a STRENDA-governed fact being invented when the source did not
report it — and `scoreDataQuality` then read back the fields the same
function had fabricated two lines earlier and rated the record
`'excellent'`. The lesson should outlive the code; a defect preserved in a
live module is a defect waiting for someone to import it.

## 9. New guards

| guard | catches |
|---|---|
| `check_example_endpoints` | a documented endpoint the API does not serve |
| `check_typescript_suites_discovered` | a test file on disk that its runner does not collect |

The second closes the gap Part 22 left open. `vitest list` takes 150s
because it imports every file; `vitest list --filesOnly` and `jest
--listTests` answer *which files will run* in ~2s each. Comparing that
against disk catches the real failure — a rename, a moved directory, an
edited `include` glob — and it is exact rather than a count that can be
satisfied by accident. Mutation-verified by excluding `src/validation` from
jest: four files reported.

`check_documented_counts` now also checks the README's guard-script count,
which claimed 14 on one line and ~20 on another while `scripts/` held 21.
Both had been true once; nothing checked either.

## 10. Verification

| check | result |
|---|---|
| all 21 static guards | **21/21 pass** |
| api-server (vitest) | **433 / 433** |
| root (jest), excluding untracked `src/storage` | **358 / 358** |
| `tsc --noEmit`, both trees | 0 errors |
| mutation tests | 14, across 6 guards, every one caught |

## 11. Not mine to commit, and worth your eye

Two things in the working tree come from a concurrent agent and are **not**
in this commit:

**(a) `src/storage/` is untracked and 9 of its tests fail.** The failures
are design decisions, not bugs I should silently make: whether the CSV
exporter emits `1.0` or `1`, whether a date-range filter is inclusive,
whether the stats key is `successful` or `successfulJobs`. The feature
author should decide.

**(b) `src/cli/scientificCLI.ts` has been changed to let unvalidated runs
proceed.** Uncommitted:

```diff
-      error('SIMULATION FAILED - No real literature found');
-      process.exit(1);
+      warning('SIMULATION RUNNING WITHOUT LITERATURE BACKING');
+      console.log('  ⚠️  Results are NOT suitable for publication');
```

The instinct behind it is defensible — Part 16 established that blocking on
`s0` was wrong, because an experimental **condition** cannot be cited. But
the fix for that is the measured/condition distinction `canPublish` already
encodes, not removing the gate. As written this turns Constitution Rule 2's
*"rejected, or flagged — never silently accepted"* into "always proceed",
and it is the same shape as everything else in this report: a check that can
no longer fail.

## 12. Open

- The `--live` citation script is exempt from `check_guard_wiring` by
  naming convention alone: the wiring guard globs `check_*.py`, so a file
  named `verify_*` that performs a check is structurally invisible to the
  "must run unasked" rule.
- `check_typescript_suites_discovered` cannot see a single `it()` deleted
  from a file that still runs. That is what the vacuous-test guard and
  review are for.
