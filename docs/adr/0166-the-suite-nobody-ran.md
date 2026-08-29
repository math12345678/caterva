# ADR 0166: The suite nobody ran, and the setup that could not run the guards

**Status:** Accepted

**Date:** 2026-08-23

## Context

ADR 0165 closed with a list headed *"What I did not check"*. This pass
checked it. Everything below was measured; the reds it names were all
present at `874b191`.

### The product's own test suite was run by nothing

`src/` holds **115 TypeScript sources and 65 test files**, including
`src/cli/scientificCLI.ts` — the CLI that `START_HERE.md` and `make demo`
both tell a new user to run. `package.json` defines `test` (jest),
`type-check` and `build` for it.

Nothing invokes any of them. `make guards` and `make test` are Python;
CI's Node job runs `pnpm install` and the api-server suite inside
`Science-Agent-Pipeline/`, which is a different workspace. `grep` for
`jest`, `ts-node` or `npm run` across the Makefile and the workflow
returns nothing.

Run for the first time: **918 tests, 7 failing across 4 suites.**

The failures were not exotic. They are what a suite drifts into when
nothing runs it:

1. **`documentedExamplesRun.test.ts` rejected `report`.** Its set of "commands
   the CLI actually dispatches" was hand-written, listed ten names, and
   missed four the CLI really dispatches — `report`, `ensemble`, `catalog`,
   `domains`. `report` is the flagship command. The file's own header
   explains that a hardcoded copy "would keep passing after someone edited
   the help text"; the copy was four lines below that paragraph. Its
   comment read "covers all nine" over a list of ten.

2. **The same file reported two working examples as broken.** It extracted
   `Example:` lines with a single-line regex, and two examples are
   continued with a trailing `\`. It ran `report --ec 1.1.1.27 --organism
   "Homo sapiens" \` — everything after the backslash discarded — and the
   CLI correctly refused a request with no substrate. The documentation was
   right and the reader was wrong. Tenth instance in this repository of a
   matcher narrower than its subject.

3. **`queriesTheEngineCanRun.test.ts` contradicted itself.** One test
   asserts every alias the pipeline advertises is accepted; another
   required rejecting `competitive-inhibition`, `non-competitive-inhibition`
   and `product-inhibition`, which ADR 0157 taught the pipeline to dispatch
   and which `knownDomainAliases()` now advertises. The file could not go
   green whatever the code did, and it read as "the validator accepts junk".

4. **`reportCommand.test.ts` pinned prose.** `toContain('scientific catalog
   1.1.1.27')` broke when the message switched its example from an EC
   number to an enzyme name. Both invocations are real; the behaviour never
   changed.

5. **Three COMBINE-archive tests could not pass on a correctly set-up
   machine.** Their helper spawned a bare `python3` from PATH while the CLI
   under test resolves `.venv/bin/python3`. `make setup` installs libsedml
   and roadrunner into `.venv`; the test looked somewhere else and reported
   `ModuleNotFoundError: No module named 'libsedml'` about a module the
   project installs. A fourth assertion listed the archive's contents and
   had gone stale when `CITATION.cff` started being bundled — invisible,
   because the Python test that checks the same thing skips when libsedml
   is absent.

### A file the user asked for, not written, and exit 0

Found while reproducing (5): with `libsedml` absent,
`simulate --resolve --export-model out.omex` printed a raw Python
traceback, wrote no archive, and **exited 0**.

The verdict was never missing. `exportModel` returns
`{ ok: false, error }`; `writeExports` read it, printed a red line, and
was declared `Promise<void>`. Under `--json` the red line is suppressed by
design — one machine-readable document on stdout — and the document's
`exports` block was byte-identical to a successful run:

    "exports": { "model": "out.omex", "citations": null }

Two comments in that file disagree about this. One, ten lines above the
call, says *"the outcome is reported inside it instead, which is where a
script can act on it."* The other, over the block itself, says only paths
are reported because *"stating `written: true` here would be this function
asserting the success of a write it does not observe."* It is the one
thing it does observe. Computed and not delivered, to the only consumer
with no other way to learn it.

### `make setup` produced an environment that could not run the guards

Two guard dependencies are not installed by any documented path:

| package | declared | installed by |
|---|---|---|
| `PyYAML` | **nowhere** | nothing |
| `ruff` | `pyproject.toml` dev extra | nothing |

`make setup` and CI both install `requirements-dev.txt`. `pyproject.toml`'s
`[project.optional-dependencies] dev` is read by nothing — two dependency
lists that overlap without agreeing: pyproject has ruff and mypy and no
cffconvert; requirements-dev had cffconvert and neither of those.

Nobody noticed because an Anaconda base ships both. So the guards passed
for anyone who ignored CONTRIBUTING and failed for anyone who followed it:
`check_ci_toolchain.py` exited 3 (`PyYAML is not installed`), taking
`test_the_guards_selftest_passes` down with it, and
`check_python_bug_lints.py` reported `No module named ruff`.

### `verify_build.py` graded the tree with an interpreter nobody chose

All **78** guard invocations were built as `f"python {script}"` — a bare
`python` resolved from PATH, not `sys.executable`. Run through
`.venv/bin/python3` on a machine with Anaconda first on PATH, it spawned
Anaconda for every guard: the Citation Metadata guard reported cffconvert
missing and Documented Counts reported different totals, while both passed
when run directly. The same defect as (5), one layer up.

### The documented test counts are a fact about the machine

Same checkout, same commit, same day:

| suite | system python | `.venv` from `make setup` |
|---|---|---|
| engine | 1,167 | **1,205** |
| literature | 1,130 | **1,116** |

Both directions at once. The engine collects *more* under `.venv` because
libsedml and roadrunner let several modules import at all; the literature
suite collects *fewer* because `test_popgen_resolver.py` needs `stdpopsim`
from the optional `requirements-popgen.txt`, which `make setup` does not
install and Anaconda happened to satisfy.

ADR 0165 wrote 1,167/1,130 into the README from the wrong interpreter.
Honestly measured, and wrong for this project.

### `npm ci` could not install the root project

`package.json` declares `js-yaml` and `@types/js-yaml` and states
`Apache-2.0`; the committed `package-lock.json` had neither dependency and
said `MIT`. Measured on the committed pair:

    npm error `npm ci` can only install packages when your package.json
    and package-lock.json are in sync.
    npm error Missing: @types/js-yaml@4.0.9 from lock file

### The notice that outlived its subject — the good failure

`check_availability_notice_matches_reality.py` went red.
**`https://github.com/Terrium-sim/main.git` is now public**, confirmed
independently: `GIT_TERMINAL_PROMPT=0 git ls-remote` exits 0, with no
credential prompt. README.md and START_HERE.md still opened with **"Not
public yet."**

ADR 0145 wrote that guard for exactly this day, on the argument that
*nothing in this tree fires when a true sentence stops being true*, and
that the people positioned to notice are the ones who cannot — they have
had access all along. It fired, and it was right.

## Decision

- **Derive, don't restate.** The examples test reads the dispatch switch
  the same way `check_cli_surface_documented.py` does, and joins
  backslash-continued examples. `report` and `ensemble` are added to the
  excluded set with their reasons (both need live services).
- **Correct the two stale tests**, and add the direction each was missing:
  a test that the three inhibition domains ARE placeable — without it,
  deleting them takes the suite from red to green — and an assertion on
  the claim ("points at `catalog`") rather than on one example of it.
- **Deliver the export verdict.** `writeExports` returns
  `{ model, citations }` per file, `null` for not-requested and `false`
  for requested-and-failed, and the `--json` document carries it. The exit
  code is left alone: the comment at the last call site records a
  deliberate decision that an export failure does not fail the run, and
  overturning that is the owner's call, not a side effect of this pass.
- **Use the project's Python.** The archive tests resolve it through
  `resolvePythonExecutable`, and `verify_build.py` spawns
  `shlex.quote(sys.executable)`.
- **Declare what the guards need.** `PyYAML==6.0.3` and `ruff==0.11.11`
  in `requirements-dev.txt`, both with the licence read from the LICENSE
  the wheel ships, recorded in `check_dependency_licenses.py`.
- **Make the counts say which interpreter produced them**, and warn when
  that is not a `.venv`.
- **Record the three unrecorded boundary fields** — `ensemble_candidates`
  and `substrates_available` mapped to the wire keys the runner really
  emits, `cross_species_candidates` as `None` with the reason it stays
  inside Python.
- **Document `domains`, `--points` and `--yes`**, read out of the code
  rather than described from memory.
- **Delete the availability notice** from README.md and START_HERE.md.

## Verification

Suites, before and after, on this machine with `make setup` done:

| suite | before | after |
|---|---|---|
| root jest (`src/`) | 7 failed / 918 | **918 passed** |
| engine (`Terium`) | 1 failed | **all passed** |
| literature (`Tests`) | 4 failed | 1 failed (pitch deck) |
| api-server (vitest) | 625 passed | 625 passed |
| `verify_build --quick` | 11 failed | **6 failed** |

The `verify_build` figures are like-for-like: working tree stashed, guard
run against a clean `874b191`, stash restored, `git status` byte-identical
either side.

**Mutations, hand-run.** No set file, and the reason is not convenience:
`scripts/mutate.py` grades a pytest suite by counting its tests, and every
change here is either a guard with no pytest coverage or a jest test.
Pointing its `--test` at `npx jest` would report NOT CAUGHT on any machine
without `node_modules` — the confident wrong answer the harness exists to
prevent. It refused this outright when first tried, reporting *"the
baseline suite did not execute any tests"* rather than grading one, which
is the harness behaving correctly on me.

| mutation | result |
|---|---|
| `ensemble_candidates` mapped to a wire key the runner never emits | caught — `check_runner_boundary` exit 1, naming ADR 0039's defect |
| `domains` removed from help | caught — `check_cli_surface_documented` exit 1 |
| `written: exportOutcomes` replaced by a constant `null` | caught — 2 of 3 tests in `exportOutcomeReachesTheDocument` |
| the `written` block deleted entirely | caught — same file |

Every restore verified with `diff` against a pristine copy, and each guard
re-run to exit 0 afterwards.

The new jest file forces its failure with an unwritable destination rather
than by removing `libsedml`: the defect was found that way, but a test
that reproduced it that way would go quiet the moment somebody ran
`make setup`. It asserts both directions — `false` on a failed write and
`true` on a successful one — because a `written` field hardcoded to
`false` would satisfy the first alone.

## Consequences

**Still red, and why.**

*The ADR record.* Unchanged from ADR 0165: the index links `0146` and
`0150`, neither file has ever existed, and `0150` claims libSBML warnings
reached 0 where the exporter still emits 15. Owner's call.

*The pitch deck.* 1,852 tests claimed; the tree has 2,321.

*Prompt injection.* Four findings, and the guard says each needs a human
verdict, with an unreviewed baseline being "a suppression list nobody
read". Three are `trust-assertion` hits inside mutation set files and a
test module; one is `START_HERE.md:244`, a conditional addressed to an AI
reader. Deliberately not cleared here: I am the kind of reader that guard
exists to protect against, and an AI adding its own findings to the
allowlist is the conflict it was built to catch.

*Mutation table reproducibility.* ADRs 0125, 0128, 0151 and 0163 present
tables with no set file. Re-deriving another author's mutations risks a
confident NOT CAUGHT, which is worse than the gap.

**The network question ADR 0165 left open, now half-answered.**

That record said it was *not determined* whether the literature suite
reaches the network beyond the one test it fixed. It does. A second case
is proven, by the same A/B, and it runs the other way round:

`test_evidence_rank.py::test_no_fixture_pool_reaches_the_frontier_with_two_different_depths`
— **passes online in 9s, fails with the network blocked.** The stack names
the path: `resolve_kinetic_value` → `find_form_mixtures` → `_is_compound`
→ `buffer_identity.fetch_cid_json` → `retry_get`, a live call to PubChem.

The test is not careless — it injects five providers (`html_provider`,
`uniprot_provider`, `taxon_id_provider`, `lineage_provider`, and
`search_literature=False`). **There is no seam for this one.**
`resolve_kinetic_value` takes no `cid_provider`; the lookup happens two
layers down against a module default. An author who stubbed every
documented seam still got a live request.

Left alone deliberately. Monkeypatching `buffer_identity` from the test
would change which mixtures are found, and a green test that passes
because compound identification was neutered is worse than a red one. The
fix is a seam — threading the provider through `resolve_kinetic_value` as
the other four already are — and that is a change to the core resolver's
signature, not to this pass's subject.

A full enumeration still did not complete: with the network blocked,
`http_retry.retry_get` sleeps between attempts, and three attempts to run
the suite offline ran past forty minutes without finishing. So the honest
count of network-dependent tests is **at least two, proven; total
unknown**, and nothing in the tree — no `conftest.py`, no socket policy,
no `network` marker — stops a third being written tomorrow.

**What this pass did not check.** `Business/` (79 markdown files) was
listed and not read. `mule/` was confirmed to be covered by five guards,
all green, but its 30 JavaScript files were not reviewed and nothing
type-checks them. `terrium-site/` has its own `package.json` and was not
installed, so its TypeScript is still compiled by nothing here;
`landing/` type-checks clean but is reached by no guard, since
`check_typescript_compiles.py` only walks `Science-Agent-Pipeline/`.
Whether CI was red across the five days in ADR 0165 still needs the CI
logs. `mypy`, declared alongside `ruff` in the same unread pyproject
extra, is still installed by nothing and no guard invokes it.
