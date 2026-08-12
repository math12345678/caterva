# Working on Terrium

For students joining to do error-finding, testing and writing. Read this
first; it is shorter than it looks and the last section is the important
one.

## What Terrium is, in one paragraph

A simulation engine for teaching labs. A student asks a question in plain
language; Terrium finds the real parameters in the scientific literature,
runs the simulation, and shows where every number came from. Fifteen
domains — enzyme kinetics, epidemics, population genetics, molecular
dynamics — and roughly 1,291 tests.

## The one idea you need

**Terrium refuses to invent.** If it cannot find a real value for a
parameter, it stops and says so, rather than filling in something
plausible.

That sounds obvious. It is unusual. Most tools default a missing value to
something reasonable-looking, and the student never learns the number was
made up.

Everything else follows from that, including two distinctions you will use
constantly:

| | example | needs a citation? |
|---|---|---|
| **Measured quantity** | Km, Ki, kcat, Vmax | **Yes.** Somebody measured it in a lab. |
| **Experimental condition** | s0, i0, temperature, pH | **No.** *You* chose it. |

Asking for a citation for a substrate concentration you picked is a
category error. It has broken this codebase twice.

## Setting up

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
cd main
make setup     # creates .venv, installs everything
make check     # verifies the stack genuinely works
make test      # 1,291 tests
```

`make check` is not a version check. It builds a real Michaelis-Menten
model, integrates it, and compares the result to the exact closed-form
solution. If it passes, the numerics can be trusted.

If any of this fails on your machine, **that is a bug and we want to know**
— a setup that only works for the person who wrote it is a real defect, and
you are the best-placed person in the project to find it.

## Where to commit

Work in **`main`** (this repo). Commit there.

Do not commit directly into `terium`, `tests`, `backend-main` and the rest —
those are regenerated from here by `scripts/split_repos.sh`, and a commit
made straight into one of them gets overwritten on the next split.

Branch naming: `yourname/what-it-does`, e.g. `priya/fix-csv-zero-export`.

## Good first work

Ordered by how quickly you can be useful.

### 1. Break something and report it precisely

The most valuable thing a new person does is find something wrong that
everyone else stopped seeing. Try to make Terrium behave badly:

```bash
npx ts-node src/cli/scientificCLI.ts resolve "made up enzyme" \
  --substrate nonsense --organism "Homo sapiens"
```

Does it fail cleanly and tell you why? Try nonsense units, negative
concentrations, an enzyme with a Unicode name, a substrate with an
apostrophe. Try running it with no network.

A good report has three parts: **what you ran**, **what happened**, **what
you expected**. That is enough. You do not need to know the fix.

### 2. Read the docs against the code

Documentation rots faster than code. Pick any document and check its claims
against the source. This is not busywork — a sweep like this recently found
that a 725-line API reference described endpoints that had never existed.

If a document says a command exists, run it. If it quotes output, produce
that output and compare.

### 3. Write a test for something already true

Find behaviour that works but is untested, and pin it. The rule: **break it
deliberately and confirm your test goes red.** A test that passes before and
after your change tested nothing.

We have a guard for the most common failure — `check_no_vacuous_tests.py`
catches assertions that can never run — and it found twelve on its first
pass.

### 4. Improve an error message

Find a message that tells you something failed without telling you what to
do. Rewrite it to name the problem and the fix. Small, real, and you will
learn the codebase doing it.

## The standard

One rule shapes the whole project:

> **A check that cannot fail is worse than no check, because it is
> trusted.**

Practically, when you fix something:

1. **Reproduce it first.** Do not trust a bug report, including your own
   from an hour ago. Run it and watch it fail.
2. **Mutation-test the fix.** Break it on purpose. Confirm the test goes
   red. Put it back.
3. **Never report success on failure.** If something failed, say so.

That last one sounds too obvious to state. It has shipped here three times,
most recently in a script that printed *"All 16 repositories pushed"* after
every single push had failed.

## Before you open a pull request

```bash
python scripts/verify_build.py --quick     # 22 guards
python -m pytest Terium/tests Tests -q
npx tsc --noEmit -p .
```

If a guard fails, fix the cause. **Do not weaken a guard to make the build
green.** If you think a guard is wrong, say so in the PR and explain why —
that is a legitimate position and has been right before.

In the PR, say what you verified and how. "Should work" is not a result.

## Things that are genuinely fine

- Asking a question that turns out to have an obvious answer.
- Reporting a bug that turns out to be your environment. That is still a
  documentation bug.
- Disagreeing with a decision in the codebase. Several were wrong.
- Not knowing the biology. Most of the work is software.

## Where to look things up

| what | where |
|---|---|
| the nine engineering rules | `docs/CONSTITUTION.md` |
| why a design is the way it is | `docs/adr/` — 23 decision records |
| how it was actually built, mistakes included | `Business/build-stages/` |
| the HTTP API | `docs/API.md` |
| what lives in which repo | `docs/REPO_MAP.md` |

`Business/build-stages/` is the honest one. Every stage records what broke
and what the failure taught. If you want to understand why the project is
paranoid about certain things, that is where the reasons are.
