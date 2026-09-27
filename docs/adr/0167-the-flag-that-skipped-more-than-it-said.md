# ADR 0167: The flag that skipped more than it said, and why CI was red

**Status:** Accepted

**Date:** 2026-08-23

## Context

The third pass over ADR 0165's *"what I did not check"* list. Two of the
items on it were answerable and are now answered.

### CI was red, and had been for 28 pushes

Both previous records said this was *not determined* because it needed the
CI logs. It did not; `gh` is installed and authenticated. Measured against
`math12345678/caterva`:

- **58 main-branch runs examined. Last green: 2026-08-18T22:11:50Z.**
- **28 consecutive failures since.**

The step failing on every one of them, on both Python 3.12 and 3.13:

    Run python scripts/check_ci_toolchain.py --selftest
    check_ci_toolchain: PyYAML is not installed.
      This is 'could not check', NOT 'checked and fine'. Exiting 3.

That is the defect ADR 0166 found from the other end and fixed by
declaring `PyYAML==6.0.3`. The guard was added 2026-08-20, four days ago,
and has reddened every push since.

Confirmed rather than assumed: a clone of this working tree, with a fresh
venv built only from `requirements-dev.txt`, runs that selftest to
**exit 0**.

**Two further blockers sit behind it**, and CI's fail-fast hides them:

1. `check_doc_links.py`, on the dead `0146`/`0150` links — the ADR record
   this pass and the last two have each declined to rewrite.
2. `verify_build.py --quick`, which was added to CI on **2026-08-22**,
   after the last green run. It **cannot pass where it is placed**: it
   invokes `check_typescript_compiles.py`, which needs a local
   `node_modules/typescript` and correctly reports every workspace as NOT
   type-checked without one — and CI's Python job does `pip install` and
   no `pnpm install`. The job that does install Node runs only the
   api-server suite.

### `--no-typescript` skipped twenty-five guards, one of them TypeScript

Found while working out (2). `verify_build.py` had five guard groups
inside `if not args.no_typescript:`:

    TypeScript Guards          <- belongs there
    Prompt Injection Guard
    Orphan Module Guard
    Test Honesty Guards        <- 22 guards: ADR index, mutation-table
                                  reproducibility, CLI surface, licence
                                  consistency, bug-lints, ...
    Generated Files Guard

The flag is documented as *"Skip TypeScript tests"*. Measured on one tree:

| invocation | failures reported |
|---|---|
| `--quick` | 6 |
| `--quick --no-typescript` | **3** |

The three that disappeared were **ADR Index**, **Mutation Table
Reproducibility** and **Prompt Injection**. None reads a line of
TypeScript. A flag that makes a tree look cleaner by not looking at it is
the shape this repository exists to refuse.

Two of the four carried comments insisting they run in every mode — *"so
it runs in every mode rather than behind the slow-test flag"* and *"A
guard against tests that cannot fail is worth little if it only runs in
the slow path"*. Both were true about the intent and false about the code,
which is worse than no comment: it is why nobody re-read the indentation.

### The compile guard could not see the product

`check_typescript_compiles.py` walked `Science-Agent-Pipeline/` and
stopped — the same defect one level up from the one it was written to fix.
Outside that directory and checked by nothing:

- the repository root, `src/`, **115 TypeScript sources including
  `src/cli/scientificCLI.ts`**, the CLI START_HERE.md and `make demo` tell
  a new user to run;
- `landing/`, whose own `tsconfig.json` opens by explaining that this code
  *"no tsconfig.json covered, so nothing type-checked it"* — the config
  was written and nothing ever ran it;
- `caterva-site/`, its own npm project with a `typecheck` script no
  automation calls.

### A requirements file that could not be installed, naming two packages that do not exist

`advanced_analysis/README.md` line 22 says `pip install -r
requirements.txt`. That command fails on the file's first entry:

    ERROR: Could not find a version that satisfies the requirement
    python>=3.10 (from versions: none)

Two more entries were checked against PyPI directly:

| entry | PyPI |
|---|---|
| `timeit>=1.0.0` | **HTTP 404** — and it is a standard library module |
| `excalidraw-export>=0.1.0` | **HTTP 404** |

An unregistered name is not a harmless typo. It is an open slot, and the
file is a standing instruction to install whatever a stranger uploads
under it — Rule 7 of `docs/CONSTITUTION.md` in its exact shape. Nothing
was looking: `check_pins_resolve.py` held a deliberate two-file list and
matched only `==`, and this file uses `>=` throughout.

## Decision

- **Move the four non-TypeScript groups out of the `--no-typescript`
  branch.** `run_typescript_guards` stays, because
  `check_typescript_compiles.py` genuinely needs a Node toolchain and a
  Node-free run has to be able to turn it off. Nothing else in that branch
  had that property.
- **Widen the compile guard to the whole repository** — root, `landing/`
  and `caterva-site/` alongside the seven pipeline workspaces. Root-level
  configs are matched per directory rather than by `rglob` from the root,
  which would walk `.venv`, `node_modules` and every fixture tree.
- **Teach `check_pins_resolve.py` about names, not only versions**, across
  four requirements files instead of two: a standard-library name asked of
  PyPI, and a name with no releases, each fail with their own message.
- **Make `advanced_analysis/requirements.txt` installable** by removing
  the three entries that cannot work, with the reason in the file. The
  other twenty-five are left alone: they are declared intent for
  components the README describes, and thinning them is the owner's call,
  not a side effect of making pip run.
- **CI is left as it is.** The `verify_build --quick` placement is a real
  defect, and the fix is a choice between three shapes — move it to the
  Node job, split the Node-dependent guards out, or install Node in the
  Python job — with different costs to run time and to what CI covers.
  Recorded, not decided.

## Verification

```
python3 scripts/mutate.py --set docs/mutations/adr-0167-flag-and-scope.json
```

| id | mutation | result |
|---|---|---|
| F1 | prompt-injection guard moved back inside `--no-typescript` | caught |
| F2 | the guard-call extractor returns nothing, so the comparison is two empty sets | caught |

`2 caught, 0 not caught, 0 indeterminate`.

**The harness twice refused a mutation of mine, and was right both
times.** F1 needed a companion — a structural test is worthless if it
locates its subject, extracts nothing and reports a clean match — so F2
exists to prove the second test fires. The first F2 made the finder return
an empty node *only when no branch exists*, and the branch exists, so the
mutated line never ran: NOT CAUGHT, correctly. The second was
`return set() or {...}`, which evaluates to the set literal because an
empty set is falsy: NOT CAUGHT again, also correctly. An inert mutation
reads exactly like an untested claim, and the only reason those two did
not become a false "verified" line in this record is that the harness
graded them instead of me.

**Hand-verified, and named as the weaker evidence.** Two changes are not
in the set file, because grading them needs things a set file cannot
assume:

- *The compile-guard scope.* The old and new guards were run against the
  same tree with a type error injected into `landing/src/lib/drift.ts`
  (`const _guardProbe: number = "not a number"`). **Old: exit 0, "type-checks
  clean in 7 workspace(s)". New: exit 1**, naming
  `src/lib/drift.ts(228,7): error TS2322`. The first comparison was
  invalid — the old copy was run from `/tmp`, so its `REPO_ROOT` resolved
  there and it found no workspaces at all — and was redone with the file
  in `scripts/`. Grading this properly needs three separate `node_modules`
  trees.
- *The requirements-name check.* Restoring the original manifest makes the
  guard exit 1 and name all three entries separately. Grading it needs
  live PyPI.

Restores verified with `diff` against pristine copies, and every guard
re-run to exit 0 afterwards.

Other suites, unchanged by this pass: root jest 918 passed, api-server
625 passed, engine green, `verify_build --quick` 6 failures — the same six
as ADR 0166 left, none of which names a file this pass touched.

## Consequences

**Checked and clean, so recorded as checked.** `caterva-site` installs,
type-checks and builds with its lockfile already in sync. All 30
JavaScript files under `mule/` parse. `landing/` type-checks. None of
these had ever been established; three of them are now inside the compile
guard so they stay established.

**`mypy` was configured and run by nothing — now clean.** `pyproject.toml`
carries a full `[tool.mypy]` section and pins `mypy==1.15.0` in the same
extra nothing installs. Run for the first time: **12 errors in 8 files**.

Ten were one name carrying two types inside one function — `entry` as a
baseline dict and then as a formatted line, `expected` as a list of
strings and then of integers, `unknown` as a set of unrecognised ids and
then a list of verdicts. Renaming is the whole fix and it makes the code
read as what it does.

The eleventh is worth naming separately. `check_guard_wiring.py` narrowed
an AST node with a boolean flag:

    is_table = isinstance(node, ast.AnnAssign) and ...
    if is_table and isinstance(node.value, ast.Dict):

`ast.walk` yields bare `AST`, which has no `.value`. The code is correct
and unverifiable — the flag carries the narrowing where no checker can
follow it. Rewritten with `continue`, which narrows for both readers.

**0 errors across 167 source files.** `mypy`, `types-PyYAML` and the two
`yaml` stub findings are now declared in `requirements-dev.txt` with
licences read from the shipped LICENSE files.

**Installed, not enforced.** Nothing runs mypy yet, and that is left
deliberately: wiring a type checker changes what a green build means, and
the previous pass said so. What has changed is the price — it is now a
one-line addition rather than a one-line addition plus a twelve-item
backlog. The related gap is still open and is the more interesting half:
`check_guard_wiring.py` asks whether a configured tool's *cache* is
gitignored, never whether anything runs it.

**`Business/` is now checked.** 79 files, and the answer is that it is in
better shape than the guards' scope suggested:

- Every repository path referenced from a Business document resolves.
- The architecture assessment's diagram-to-file table maps to eleven real
  files under `api-server`; all eleven exist.
- The countable claims outside `build-stages/` are two, and both are
  already scanned. `FYDEMY_APPLICATION_DRAFT.md`'s "2,279 tests" is 1.8%
  off the live 2,321 and passes deliberately — the guard's 15% tolerance
  exists because "several agents commit here and the test count changes
  hourly", and flagging a difference of three would train people to ignore
  it.
- The 71 files under `build-stages/` are dated build logs. "Mutation
  reverted; 124 tests green" was true when written, and rewriting it to
  today's total would falsify a record rather than correct a claim.

What was wrong is the *scope*, and the file says so itself: "Sixth
instance of a correct guard on too narrow a scope." `INVESTOR_DOCS` is a
hand-written tuple of five. A sixth fundraising document would be scanned
by nothing, which is how the application draft came to understate the
project by 77% in the first place. So the tuple stays — it carries real
per-document reasoning and it is the thing that gets checked — and a
derived pass now asks the complementary question: is there a Business
document making an undated countable claim that nothing covers? Today,
no. `build-stages/` is excluded by prefix with the reason stated, and
`UNSCANNED_WITH_REASON` is empty, so an exclusion is a decision rather
than a default.

**`advanced_analysis/README.md` describes a system that is not there.**
The question left open above — whether those 25 dependencies correspond to
anything — has an answer, and it is broader than the dependencies. The
README's *Directory Structure* names **eleven paths**; checked one by one,
**none of them exists**. Three of its four "main components" are plans
written in the present tense. What is in the directory: one script, its
ten output figures, a requirements file and the README.

The tell was already there and unreadable: one heading says *Figure Suite
(working)* and the others say nothing, so the whole truth was carried by a
single parenthesis. A notice at the top now states what is present, and
*Directory Structure* is labelled planned. The plan is kept rather than
deleted — it is real intent — but a plan in the present tense is a claim.

**And that notice is now guarded, because it is the kind that rots.**
`caterva/tests/test_advanced_analysis_notice_matches_reality.py` fails in
both directions: if a claimed-absent path is built, and if the notice is
removed while they are still absent. This is ADR 0145's argument reused —
nothing else in the tree fires when a *true* sentence stops being true,
and the person who builds `validation/run_validation_pipeline.py` is
exactly the person the stale notice would tell that their work does not
exist. Both directions mutation-verified; a third test pins the path list
against being emptied, which would make the other two vacuous.

**`mule/` — the sentence three passes kept writing, retired.** Each of
them recorded "30 files parse, which is all that has been established
about them", because parsing is all `node --check` establishes. Type-
checked for the first time: **17 findings**.

**Nine were one function.** `interactive()` in `cathedral/render.js` took
a `shape` parameter and drew a circular focus ring when it was
`'circle'`. `shape` occurred exactly three times in the entire tree — the
parameter and its two comparisons — across **ten call sites**, and every
box supplied is `{x, y, w, h}`. The condition was unsatisfiable, so the
circular half had never executed, and removing it **cannot** change what
renders. That is a proof, not an expectation.

Half of a feature, unreachable, is indistinguishable from support that
exists — which is why it is gone rather than commented. A circular node
needs the branch *and* a caller that passes the shape.

The other eight were runtime-correct DOM idioms the checker cannot narrow:
`e.target` typed `EventTarget`, `let x = null` inferring `null`,
`'ResizeObserver' in window` narrowing `window` itself to `never` in the
else branch. Closed with JSDoc annotations and one `typeof` test — all
comments or equivalent expressions, no behaviour changed, re-verified by
parsing all 30 files and re-resolving all 58 imports.

`mule/tsconfig.json` now exists so this stays checked, with `strict` off
deliberately: strict null checking on untyped DOM code produces hundreds
of findings about lines that run correctly, and a guard that cries wolf
gets muted (ADR 0028).

**And the compile guard's discovery was widened again**, from `src/` to
`src/` *or* an explicit `include`. The `src/` test was a proxy for "this
is a real workspace", and it excluded two that are: `mule/`, whose files
live under `assets/js`, and `scripts/`, whose tsconfig was written
precisely so `generate-openapi-clients.ts` would stop being compiled by
nothing. **7 workspaces at the start of this session, 12 now.** Verified
old-against-new on the same tree: with a bad property access added to
`mule/assets/js/pilot.js`, the previous discovery exits 0 and the current
one exits 1 naming the line.

**A guard caught this pass in the act.** The notice added to
`advanced_analysis/README.md` listed the figure generator by its
directory-relative path (`scripts/` + the filename) — which reads as
repo-relative and resolves to nothing. The
Documented Command Guard failed with *"is named by
advanced_analysis/README.md and does not exist"*, which is the exact
defect it was written for, committed by the person adding a notice about
claims that do not match the tree.

**The last red that was not an owner decision.**
`check_no_silent_skips.py` was failing on one skip:
`test_popgen_resolver`, which needs `stdpopsim` from the optional
`requirements-popgen.txt`. `make setup` installs `requirements-dev.txt`
and so does CI — so following CONTRIBUTING produces exactly that skip.
The documented setup failing a guard, for the third time this session
after PyYAML and ruff.

Its only lever was `EXPECTED_MAX_SKIPS`, and the docstring says plainly
*"Do not raise it to make a red build green."* It is also the wrong
shape: raising it to 1 admits the popgen skip **and the next skip,
whatever that turns out to be**, which is precisely what the guard exists
to catch. One number cannot say "this one, for this reason".

So skips are now allowed **by name, with a reason**, and the list shrinks
by the same rule as `EXPECTED_WIRING` and `NOT-YET-REPRODUCIBLE.txt`: an
entry whose test stops skipping fails too. Both directions verified
separately, because the first run returned on the unexpected-skip branch
and left the stale branch untested — an unverified branch being the thing
this file is about:

| mutation | result |
|---|---|
| the real allowance renamed, so the popgen skip is unrecognised | caught — `1 unexpected skipped test(s)` |
| an allowance added for a skip that never happens | caught — `1 entr(y/ies) in ALLOWED_SKIPS no longer skip` |

Its success line said `1 skipped (limit 0)` once allowances existed,
which reads as a contradiction. It now reports the unexpected count —
the one the limit actually governs — and the recorded ones separately.

**A CORRECTION TO THIS RECORD, made before anyone relied on it.** An
earlier draft of this section said the three inhibition domains were
"still reachable through the API and the CLI but not through
`dashboard.html`, which ADR 0149 flagged and no pass since has
revisited." **That is false, and it was false when written.** ADR 0149
flagged it; **ADR 0157 fixed it**, on 2026-08-22. I repeated 0149's
finding without opening the file.

Measured, four options through the real validator:

| dropdown option | accepted | domain |
|---|---|---|
| `michaelis-menten` | yes | `mm` |
| `competitive-inhibition` | yes | `competitive` |
| `non-competitive-inhibition` | yes | `noncompetitive` |
| `product-inhibition` | yes | `product` |
| `allosteric` | **no** | — |

`allosteric` is `disabled` in the markup and labelled *"CLI only, see
`scientific domains`"*, so the control and the validator agree exactly —
which is the behaviour the page's own comment argues for: *"Offering a
control that cannot work is the UI form of a check that cannot fail."*

Left in rather than deleted. This is the fourth pass in a row to find
that a stale claim survives by being repeated, and a record that quietly
drops its own wrong sentence teaches nobody. The lesson is the one this
project keeps relearning from the other side: **an ADR is not a source
about the present tree**. Reading 0149 and reporting its finding as
current is the same act as trusting the index rows for 0146 and 0150 —
the defect this pass has been chasing for three records.
