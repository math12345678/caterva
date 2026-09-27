# ADR 0165: The build nothing compiled, and two values nothing delivered

**Status:** Accepted

**Date:** 2026-08-23

## Context

A full pass over the tree, asked for as an audit rather than aimed at a
known defect. Everything below was measured on `874b191` with a clean
working tree, so every red described here predates this session.

**The landing app had not compiled for five days.** `CliApp.tsx` line 686
opens a JSX comment with `{/*`, closes it at line 699 with `*/`, and never
emits the `}`. One character. `pnpm run build:landing` and
`pnpm run typecheck` both failed:

```
src/cli/CliApp.tsx:701:11: ERROR: Expected "}" but found "className"
```

Introduced in `982ebca` (2026-08-18), found 2026-08-23.

**My first account of why was wrong, and the correction is the finding.**
I wrote that nothing in the tree asked whether the TypeScript compiles.
Then I ran it. `scripts/check_typescript_compiles.py` exists, is wired
into `verify_build.py`, covers seven workspaces including
`caterva-landing`, and catches this exact defect — with the bug restored
it exits 1 and prints `src/cli/CliApp.tsx(701,12): error TS1005: '}'
expected.` The guard was never the problem.

**It never ran.** `make guards` is a sequence of `@` recipe lines, so it
stops at the first non-zero exit. `check_documented_counts.py` is the
third step; `verify_build.py --quick` is second from last. The README
said 2,286 tests and the tree had 2,297 — a number stale by eleven — and
that one line meant roughly two dozen later guards, the TypeScript
compile check among them, did not execute. I only found the other two red
guards by running all 27 individually after the make target died.

So this is the project's own "computed and not delivered" applied to
guard results: the check was written, wired, and correct, and its verdict
never reached anybody because something upstream exited first.

**The second half is about where the compiler lives.** The guard needs a
local `node_modules/typescript` and, lacking one, reports each workspace
as `NOT type-checked` rather than passing it — correct under rule 2, and
the reason it cannot quietly degrade. But `verify_build --quick` runs in
CI's Python `test` job, which does `pip install` and no `pnpm install`,
while the Node job that does run `pnpm install` runs only the api-server
suite. Whether CI was therefore red throughout those five days is **not
determined** — that needs the CI logs, which are not visible from here.

And the api-server suite could not have caught it in any case: it is
genuinely good — **55 files, 625 tests**, all passing — but vitest
compiles only the modules some test imports, and no test imports the
landing app.

**Two values were computed and dropped, in the familiar direction.**

*The taxon ids.* `test_runner_contract.py` stubs `resolve_kinetic_value`
and nothing else. `taxon_id_for` calls `enzyme_lookup.fetch_taxon_id`,
which is a live HTTP GET to NCBI Taxonomy — so the "contract" test
reached the network on every run. Measured both ways on the same commit:

| network | result |
|---|---|
| available | **FAILED** — `taxonId` was `'9606'`, expected `None` |
| blocked (`HTTP_PROXY=http://127.0.0.1:9`) | **passed** |

The test's own comment explained the `None` as "the honest report of a
lookup that did not happen." Exactly backwards: not stubbing NCBI meant
the lookup *did* happen. The assertion held only on machines that could
not reach NCBI. A contract test that green-lights the shape when the
network is down is not pinning a contract; it is reporting the weather.
Worse, because every test in the file ran with the lookup unresolved, the
path where an id actually reaches the JSON was covered by nothing —
deleting both assignments in the runner changed no assertion.

*The refusals sentence.* `lab_report.py` ends its "What Caterva would not
do" section with an else-branch stating "Nothing was withheld…" when there
are no refusals. The test named for that branch built its report from the
shared fixture — which now resolves a km whose candidate rows mix diseased
and healthy breast tissue, and therefore carries a source-mixture refusal.
So the test asserted the no-refusal sentence against a document containing
a refusal, and had been failing rather than covering anything. The
else-branch was reachable only by a report with nothing withheld, and no
test built one.

**One list of domains kept in three places.** `llmResolver.ts` held the
resolver's domain list twice — once as the `SUPPORTED_DOMAINS` array that
validates the model's reply, once as prose inside `SYSTEM_PROMPT` that
tells the model what it may return — with the array's docstring reading
"Must match SYSTEM_PROMPT's domain enum" and nothing checking that it did.
A third copy sits in `llmProviders.test.ts`. That test pins one direction
only: it asks whether the allowlist *accepts* each domain. A domain
dropped from the prompt is never proposed by the model, silently stops
being reachable, and the test still passes.

## Decision

**Close the comment.** One `}`. The landing app builds; the whole
workspace typechecks clean (`api-server`, `mockup-sandbox`,
`caterva-landing` all "Done").

**Put a compile check in the job that has a compiler.** `pnpm run
typecheck` now runs in CI's Node job — after `pnpm install`, where
`node_modules/typescript` actually exists — registered as CI-only in
`check_ci_reproducible_locally.py` with its reason, and named in
`make pr`. This does not replace `check_typescript_compiles.py`, which is
the better guard and stays where it is; it makes sure the question gets
asked somewhere the toolchain can answer it, rather than only in a job
that must report "could not check".

**Stub NCBI in the runner contract test**, via a `taxon_id` parameter on
`run_main` rather than a fixed `None` — a hardcoded `None` would have
locked in the same blind spot from the other side. Added
`test_a_resolved_taxon_reaches_the_output` for the delivered path, and
corrected the comment that had the causality backwards.

**Build the no-refusal report explicitly** (`resolved={}`), assert
`refusals == []` first so a change that stopped emitting refusals
altogether cannot make the test pass for the wrong reason, and assert the
whole sentence rather than a fragment.

**Make the domain lists one list.** `SYSTEM_PROMPT` now interpolates
`DOMAIN_UNION`, built from `SUPPORTED_DOMAINS`. Verified the generated
line is byte-identical to the hand-written one it replaced, so the prompt
the model receives is unchanged.

**Corrected the documented counts** with
`check_documented_counts.py --write` — README and three `docs/readmes/`
pages claimed 2,286 / 1,184 / 1,102 against an actual 1,167 and 1,130.

## Verification

Mutation results, re-runnable:

```
python3 scripts/mutate.py --set docs/mutations/adr-0165-delivered-and-compiled.json
```

Baseline green (45 tests), then:

| id | mutation | result |
|---|---|---|
| T1 | runner resolves a taxon id, emits `None` instead | caught |
| T2 | refusals section left blank instead of stating nothing was withheld | caught |

`2 caught, 0 not caught, 0 indeterminate`.

T1 is the load-bearing one: run against the suite as it stood before this
pass, that same mutation was invisible.

**The JSX fix is deliberately not in the set file**, because grading it
means shelling out to `pnpm run typecheck`, which reports NOT CAUGHT on
any machine without a completed pnpm install — a confident wrong answer of
exactly the kind the harness exists to prevent. Verified by hand instead:
restored the original byte, `pnpm run typecheck` exited 2 with
`TS1005: '}' expected`; restored the fix, exit 0; confirmed the restore
with `diff` against a pristine copy and with `git diff`, which shows one
line changed. This is the weakest evidence in the record and is named as
such.

Suites after the change:

| suite | before | after |
|---|---|---|
| engine (`caterva`) | 2 failed | 1 failed |
| literature (`Tests`) | 4 failed | 1 failed |
| api-server (vitest) | 625 passed | 625 passed |
| wired guards | 3 red of 27 | 2 red of 27 |
| `verify_build --quick` | 11 failed | 9 failed |

The `verify_build` figures are a like-for-like comparison: the working
tree was stashed, the guard run against a clean `874b191`, and the stash
restored — `git status` byte-identical before and after. The two that went
green are Documented Counts and **TypeScript Compile**. Nothing that
passed at HEAD fails now. The nine that remain are the pre-existing set,
none of which name a file this pass touched: Investor Claims, Doc Links,
Constitution 7+8, ADR Index, Runner Boundary (two `KineticResult` fields
with no `EMITTED_AS` entry), Prompt Injection, CLI Surface Documentation,
Citation Metadata (`cffconvert`), and Mutation Table Reproducibility
(0125, 0128, 0151, 0163 — not 0165).

## Consequences

**What is still red, and why it was left.**

*The ADR record itself.* `check_forbidden_packages.py` (Rule 8) and
`check_doc_links.py` are both red on one cause: the index links
`0146-the-artifact-that-did-not-reproduce.md` and
`0150-units-the-file-states-itself.md`, and **neither file has ever
existed** — no commit in any branch adds or deletes them. Two decisions
exist only as index rows. Their contents were checked against the tree
rather than assumed:

- 0146's row describes work that IS present — the SBML export writes
  Vmax in the substrate's units per second, and the row's own caveat
  ("units are still only in `<notes>`") matches a comment in
  `scientificCLI.ts` verbatim. A real decision, missing its document.
- 0150's row claims libSBML consistency warnings went to **0** and that
  `unitDefinition` support was added. Measured — build the mm model
  through `scripts/export_annotated_model.py`, load it with antimony,
  run `checkConsistency` with `LIBSBML_CAT_UNITS_CONSISTENCY` on:
  **15 problems** (13 unit-consistency warnings, 2 modelling-practice),
  and `unitDefinition` appears nowhere in the output. That is the same
  15 the row says it fixed. The work is not in the tree.

Left for the owner on purpose. The two honest resolutions — implement the
units, or retract the row — lead to materially different trees, and this
is the record the whole project rests on. The guards stay red so it cannot
be quietly forgotten.

*The pitch deck.* `test_investor_claims.py` fails: `caterva_pitch_deck.pptx`
says 1,852 tests on two slides, the repository has 2,297. Investor-facing
material and outward-facing; the number is the owner's to change.

*The dev dependencies are not installed here.* `check_citation_cff.py`
reports UNREACHABLE rather than passing; one engine test fails on it; and
`check_no_silent_skips.py` counts 5 skips, every one of them an import
failure for `cffconvert` or `libsedml`. Both are declared in
`requirements-dev.txt` and this worktree has no `.venv`, so `make setup`
clears all seven at once. Not defects — a guard refusing to call "could
not check" a pass is exactly the behaviour the constitution asks for, and
it is worth saying that the three separate red signals here are one
missing command.

*`make guards` stops at the first failure.* Not changed, and it is the
reason this defect lived. One stale count in README.md hid every later
guard, including the one that would have named the parse error. Running
all of them and reporting at the end would have surfaced three red guards
on the first command instead of one — but fail-fast may be deliberate
(the last step is minutes long), so this is flagged rather than altered.

**What I did not check.** The `Business/`, `mule/`, `caterva-site/`,
`advanced_analysis/` and `landing/` trees were not audited. The
`mockup-sandbox` and `caterva-landing` suites were not run — only
typechecked. Whether the *rest* of the literature suite depends on the
network is **not determined**: a full offline run was attempted twice and
did not complete (it reached 57% in over twenty minutes against a 5m19s
online run, which indicates live calls well beyond the one test proven
here, but an unfinished run is not a measurement). Nothing was checked
against live BRENDA, NCBI or KEGG behaviour. The three
`error TS7006` implicit-`any` reports in `simulate.ts` appear only when
`api-server` is typechecked standalone and vanish under the workspace
build; they were noted, not investigated.
