# Contributing to Terrium

> **New here? Read [START_HERE.md](START_HERE.md) first.** It is one page and
> gets you to a passing test run and a real first task. This file is the
> reference you come back to — Python version policy, Windows, PR rules —
> not the way in.

This project is pre-launch and the team is small (currently two confirmed
people, one backend/infra role still open -- see `Business/CAP_TABLE.md`),
so this document is written for that scale, not for a large open-source
project with a governance process. It'll need to grow as the team does.

## What your contribution arrives under

You keep your copyright. Opening a pull request licenses that contribution
under **Apache-2.0**, the same licence Terrium ships under — Apache-2.0 §5
says so, which is why there is no CLA to sign and nothing to assign.

Sign your commits with `git commit -s` ([DCO](https://developercertificate.org/)).
Not enforced in CI today, and that is stated rather than implied.

**If you are a student, read
[`docs/INBOUND_LICENSE.md`](docs/INBOUND_LICENSE.md) before your first
substantial contribution.** Your university may have a claim on work you
produce, in which case you are not the one with the right to grant an
Apache-2.0 licence over it. That is a normal thing to check and a bad thing
to discover late.

## Before you start

Read `README.md` first, specifically the "Two gotchas worth knowing"
section. Both gotchas documented there were real bugs that cost real time
to find -- don't rediscover them.

## Getting set up

Two ways to get a working environment, pick whichever you're more
comfortable with:

```bash
# Option 1: native
make setup && make check && make test

# Option 2: container (no local Python needed)
docker build -f .devcontainer/Dockerfile -t terrium-sandbox . \
  && docker run -it --rm terrium-sandbox
```

The `-f` is not optional. The Dockerfile at the repository root builds the
Node API server that `docker-compose.yml` runs and has no Python in it; the
Python sandbox is `.devcontainer/Dockerfile`, which is also what the Dev
Container builds.

`make check` / the Docker build both run `scripts/check_env.py`, which
builds a real Michaelis-Menten model end to end and checks it against the
exact closed-form solution. If that fails, something about the environment
is actually broken -- not just a version mismatch warning.

**When setup fails, run `make doctor` before anything else.** It runs on a
bare interpreter and imports nothing outside the standard library, so it
still works when the venv is the broken thing -- which check_env.py, by
construction, cannot do. It prints every interpreter it found, the venv's
state and which Python built it, each required package's installed version
next to its pin, whether stdpopsim is available and why not, and whether
Node is present for the TypeScript guards.

## Windows

The Makefile is POSIX shell: the interpreter resolver uses `command -v` and
shell functions, and every recipe calls `.venv/bin/...`, which a Windows
venv spells `.venv\Scripts\`. Use **WSL2** or the Dev Container -- those are
the two routes anyone here has actually run.

The underlying steps are plain pip and pytest and carry no POSIX dependency,
so the native equivalents below should work. Nobody has run them on a
Windows machine, so treat that as untested rather than promised; if they
fail, report it -- a setup that only works for the person who wrote it is a
defect.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python scripts\check_env.py
.venv\Scripts\python -m pytest Terium/tests Tests -q
```

## The standard this codebase holds itself to

This is the part that matters most, more than any specific style rule:

**Every numerical claim gets checked against something that isn't the
solver checking itself.** That means one of:
- an exact closed-form solution (see `Terium/tests/test_kinetics_correctness.py`,
  `Terium/tests/test_pcr_correctness.py`)
- an independent integrator, e.g. scipy's `solve_ivp`, which shares no code
  with roadrunner (see `Terium/tests/test_numerical_robustness.py`)
- a physical invariant (conservation, monotonicity, non-negativity) checked
  across the input space with Hypothesis, not just hand-picked values (see
  `Terium/tests/test_properties.py`)

If you add a new domain or a new claim about correctness, it needs one of
these, not just "the output looked reasonable when I ran it once."

**New code should be mutation-tested before you trust the test suite you
wrote for it.** Concretely: deliberately break the logic you just wrote (a
sign flip, a wrong operator, a removed guard) and confirm your own tests
catch it. If they don't, the tests are decorative. This isn't optional
ceremony -- it's how the KM_PLAUSIBLE_MAX_MM bug and the PCR
exponential-vs-linear check were both actually validated, not just written
and assumed correct.

### Use the harness, and ship the table as a file

Do not run mutations by hand. `scripts/mutate.py` exists because the
hand-run approach gave a **wrong answer three separate ways** — a patch that
never applied (so an unmutated suite passed and the mutation was recorded
"not caught", a false accusation against a fine test), a suite that never
ran (`Tests: 0 total` read as `0 failed`), and a restore that silently
failed, leaving five mutations in the working tree. ADR 0069 has the detail.

```bash
python3 scripts/mutate.py \
    --file src/engine/parameter-sweep.ts \
    --find 'finalValue: null,' --replace 'finalValue: 0,' \
    --test 'npx jest src/engine/__tests__/parameter-sweep.test.ts'
```

It reports **three** states, not two. If it cannot establish that the
baseline was green, that the patch applied exactly once, that the bytes
changed, that the suite ran, and that the restore was byte-for-byte, the
verdict is `INDETERMINATE` — never "not caught".

**If your ADR presents a mutation table, it needs a set file:**

```bash
docs/mutations/adr-<NNNN>-<slug>.json
python3 scripts/mutate.py --set docs/mutations/adr-<NNNN>-<slug>.json
```

`check_mutation_tables_reproducible.py` fails the build without one. A
mutation table is the evidence a reader is asked to accept; it should be
something they can re-run rather than something they have to trust.

One trap: the set's `test` command must run **every** suite your record
cites, not the one that looks most relevant. A narrower command produces a
confident `NOT CAUGHT` that is indistinguishable from a real gap. ADR 0026's
set file did exactly that on its first run.

## Supported Python versions

Terrium supports Python 3.10–3.13. This is a hard constraint, but not for the
reason this file used to give. It is **not** "the SBML C extensions stop at
cp312" — `python-libsbml` 5.21.1 already ships cp314 wheels, and `antimony`
2.14.0 ships `py3-none-<platform>` wheels that are Python-version agnostic.

The window is bounded by `libroadrunner` 2.8.0 and `numpy` 2.2.6, which
publish cp310–cp313 wheels (verified against PyPI). The 2.9.x libroadrunner
line drops cp310, so we stay on 2.8.0 to keep the floor — see
[ADR 0014](docs/adr/0014-python-version-support.md).

CI tests 3.10, 3.12 and 3.13 (see
`.github/workflows/tests.yml`); `requirements.txt` pins `numpy==2.2.6` and
`libroadrunner==2.8.0`. A green run with unpinned dependencies is not
evidence about the supported configuration. The eigenvector-sign bug is the
worked example: LAPACK chose different signs across builds, producing silent
NaN rather than an exception; it passed under one numpy build but failed
deterministically under another.

The one-line setup for a correct environment is:

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

## Running tests

```bash
make test        # everything
make test-fast    # skip the slow property/robustness suites
make test-sim     # Terium/ only
make test-lit     # Tests/ (literature layer) only
```

Never skip a test to make the suite pass. If a test is skipping because of
a real, explainable data condition (see
`test_flagged_brenda_entries_do_not_become_confident_numbers`
in `Terium/tests/test_brenda_integration.py` for the one
legitimate example in this codebase), the skip must be explained in a
docstring or comment, and if possible, backed by a deterministic sibling
test that exercises the same contract without depending on the same
lucky/unlucky data condition.

## Running what CI runs

```bash
make pr          # do this before opening a PR
```

Tests are not all CI runs. The `test` job in
`.github/workflows/tests.yml` runs eleven steps; the two pytest invocations
are the ninth and tenth. The rest are **guards** — thirty-six small scripts
that check things a test suite structurally cannot: that documented counts
match reality, that every citation can be looked up, that no guard has
quietly stopped running, that a value computed in Python actually reaches a
reader in TypeScript.

`make guards` runs them. `make pr` runs those and then the suites, in CI's
order.

**What that costs, measured rather than guessed** (2026-08-15):

| step | time |
|---|---|
| 23 of the 25 guard steps, together | **40 s** |
| the two slowest (`check_documented_counts`, `check_dependency_licenses`) | ~9 s each — both collect the test suite |
| `verify_build.py --quick` | **several minutes** — it compiles the TypeScript workspace |
| the test suites (`make pr` only) | 1,800+ tests |

The ordering is deliberate: everything cheap runs first, so a broken doc
link or a stale count fails in seconds rather than after the TypeScript
compile. If you are iterating on documentation or copy, running the
individual guard is fine — `make guards` is for the run before you push.

**A guard will not block you on somebody else's outstanding item.**
`check_dependency_licenses.py` currently reports four `@replit/*` packages
that ship no licence and need a `pnpm` lockfile regeneration to remove. It
prints them loudly and exits 0, because make stops at the first failure and
blocking the whole suite on an item you cannot clear is how `make guards`
stops being run at all. A *new* unlicensed dependency does still fail.

Two things `make pr` does **not** run, and it says so when it finishes:
`check_codegen_loads.py` and the api-server TypeScript suite, both of which
need a `pnpm install` in `Science-Agent-Pipeline` (see `RUN_TESTS.md`). Run
those too if you touched the API server or the OpenAPI spec.

If you add a step to CI, `scripts/check_ci_reproducible_locally.py` will
tell you to give it a local route or to write down why it cannot have one.
That guard exists because this section did not: for most of this project's
life the instruction below said "run `make test`", which reproduced two
steps of eleven, and the other nine arrived as a red X on a PR that had
followed the instructions exactly.

## Pull requests

- Every PR that touches `Terium/terium_engine.py` or `Tests/brenda_client.py`
  needs new or updated tests, not just a description that it was tested
  locally.
- If you add a dependency, it must appear in `requirements.txt` or
  `requirements-dev.txt` -- `Terium/tests/test_dependencies_declared.py` will fail
  the build otherwise, on purpose.
- Run `make pr` before opening the PR, not just after CI catches it.
  CI is the backstop, not the first line of defense. (`make test` alone is
  not enough — see "Running what CI runs" above.)

## Code style

No linter is currently enforced (this should probably change once the
backend hire is confirmed and there's a second engineering opinion on
tooling choice). Until then: match the style of the file you're editing.
Docstrings that explain *why*, not just *what*, are valued highly in this
codebase -- see the module docstring in `Terium/terium_engine.py` for the bar.

## Questions

Open an issue, or if it's about strategic direction rather than a specific
bug, see `Business/ROADMAP.md` for what's already been deliberately
deprioritized and why.
