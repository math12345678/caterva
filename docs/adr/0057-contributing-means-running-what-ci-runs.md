# ADR 0057: Contributing means running what CI runs

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0027 / 0046 (a value computed on one side of a boundary and
never received on the other), the Stage 4 amendment (a guard is not
delivered until something runs it unasked)

## The gap

CONTRIBUTING.md said the right thing:

> Run `make test` before opening the PR, not just after CI catches it.
> CI is the backstop, not the first line of defense.

`make test` runs two commands. The `test` job in
`.github/workflows/tests.yml` runs eleven, and the two pytest invocations
are the ninth and tenth. The other nine are guards — citation format,
documented counts, the Python-support claim, forbidden packages, guard
wiring, the whole of `verify_build.py`, silent skips, codegen.

Across the whole workflow the count is 18 run-steps, of which exactly one
appeared in any Makefile recipe.

So a contributor who did precisely what the file told them to do reproduced
two steps of eleven, pushed, and learned about the other nine from a red X
on a PR that had followed the instructions. Nothing in the repository
disagreed with the instruction, because nothing compared it to CI.

This is the shape ADR 0027 and ADR 0046 already name: something computed on
one side of a boundary and never received on the other. The boundary here
is between what CI runs and what a person can run, and the undelivered
thing is the knowledge that thirty-seven guards exist at all.

## Decision

**`make guards`** runs the guards CI runs, in CI's order.
**`make pr`** runs those and then the suites. `make help` names both, and
CONTRIBUTING's pre-PR instruction now says `make pr`.

`make pr` finishes by naming the two things it did **not** run —
`check_codegen_loads.py` and the api-server TypeScript suite, both of which
need a `pnpm install` in `Science-Agent-Pipeline`. Saying what was not
checked is the point; a green run that silently omits two steps is how the
next version of this defect starts.

**`scripts/check_ci_reproducible_locally.py`** keeps it true. Every `run:`
step in the workflow must either appear in a Makefile recipe or be listed
in `CI_ONLY` with a written reason. An unclassified step fails: a new CI
step with no local route is the exact regression this exists to catch, and
a permissive default would let it through on the day it happens.

Both parsers carry a floor — a minimum number of workflow steps and
Makefile recipes below which the script fails rather than reports success.
A reader that silently returns nothing otherwise produces a clean bill of
health for a scan that never happened.

## The second guard, and the defect that produced it

While editing CONTRIBUTING.md to correct a wrong path, I wrote another one:

```
(in `Tests/test_brenda_flags.py`)
```

No such file. The test named in that sentence is in
`Terium/tests/test_brenda_integration.py`. The wrong path was plausible —
right shape, right convention, right directory for a literature test — and
it was typed by someone who was at that moment fixing broken paths.

`check_commands_runnable.py` would not have caught it: that guard checks
`scripts/*.py` mentions, because its own origin was a guard printing an
unrunnable command. Anything under `Terium/tests/` is outside its scope.

**`scripts/check_doc_paths_resolve.py`** now requires every backticked
repo-relative path *with a directory component* in the eleven
contributor-facing documents to exist. It found two more that were already
there: `README.md` pointing at `tests/test_brenda_integration.py` (it is
`Terium/tests/…`) and `SECURITY.md` at `src/lib/llmResolver.ts` (it is
`Science-Agent-Pipeline/artifacts/api-server/src/lib/…`). Both fixed.

Bare filenames are deliberately **not** checked. These documents name
`terium_engine.py` conversationally; demanding a full path there would
either fail constantly or teach people to stop naming files. A token with a
slash is a claim about where something lives and is checkable; a bare name
is a claim about what it is called and is not.

## DOCUMENTATION_INDEX.md

Its opening section was headed *"I'm a new developer — where do I start?"*
and pointed at three documents `docs/ARCHIVE_TRIAGE.md` classifies ARCHIVE,
one of which describes files that never existed.

It is replaced by a short routing table to the documents that are true,
plus a pointer to the triage as the authority on the other 67. Not a
correction banner on top of the old text: the triage's own closing section
explains why that fails — *"a reader who has been told a page is unreliable
still reads its endpoint table, because the table is specific and the
disclaimer is vague."*

## Verification

Re-derivable as a set file — `docs/mutations/adr-0057-ci-reproducible-locally.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0057-ci-reproducible-locally.json
```

The six rows belonging to `check_ci_reproducible_locally.py` all come
back `caught` under the harness. Original run:

Eleven mutations across the two guards, each restored from a `cmp`-verified
backup:

| Mutation | Caught |
| --- | --- |
| `make guards` gutted in the Makefile | 2 failed |
| A CI step exempted with an empty reason | 1 failed |
| Workflow parser silently returns nothing | 3 failed |
| Normalisation collapses every command to one string | 1 failed |
| A stale `CI_ONLY` entry matching no step | 2 failed |
| Unclassified CI steps counted as reachable | **initially NOT caught** |
| An exemption also counted as locally runnable | 1 failed (after fix) |
| A missing doc path skipped instead of reported | 1 failed |
| Path regex stops requiring a directory | 2 failed |
| Path regex stops matching anything | 4 failed |
| An existing file reported as missing | 2 failed |
| A doc listed in `DOCS` but absent tolerated | 2 failed |

**The sixth is the one worth recording.** Changing the guard to count
unclassified steps as reachable — which removes the entire point of it —
passed all eight tests. The repository was clean at the time, so `main()`
returned 0 either way, and every test agreed with a guard that had stopped
guarding.

The fix was to extract `classify(steps, local)` from `main` so a test can
hand it a step with no local route and confirm it lands in `unreachable`.
`test_it_reports_a_step_with_no_local_route` exercises the failing branch
directly. The re-run caught the mutation, and its sibling too.

A guard whose failure path is never run is a guard nobody has checked. That
is the same rule as always, applied one level up: **a check that cannot
fail is worse than no check, because it is trusted.**
