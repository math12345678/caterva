# Start here

You are in the right place whether you are an intern joining the team or a
stranger who found this on GitHub. This is the only document you have to
read before you do something useful. Everything else is linked from here and
can wait until you need it.

**Want to use Terrium rather than work on it?** [`docs/USING_TERRIUM.md`](docs/USING_TERRIUM.md) is the user's guide; this file is for people changing the code.

## What Terrium is, in one paragraph

A simulation engine for teaching labs. A student asks a question in plain
language; Terrium finds the real parameters in the scientific literature,
runs the simulation, and shows where every number came from. Fifteen
domains — enzyme kinetics, epidemics, population genetics, molecular
dynamics.

## The one idea

**Terrium refuses to invent.** If it cannot find a real value for a
parameter, it stops and says so rather than filling in something plausible.

That sounds obvious. It is unusual. Most tools default a missing value to
something reasonable-looking and the student never learns the number was
made up.

Everything else follows from that, including the distinction you will use
most:

| | example | needs a citation? |
|---|---|---|
| **Measured quantity** | Km, Ki, kcat, Vmax | **Yes.** Somebody measured it in a lab. |
| **Experimental condition** | s0, i0, end, points | **No.** *You* chose it. |

Asking for a citation for a substrate concentration you picked is a category
error. It has broken this codebase twice.

Temperature and pH look like conditions but are **neither** — they are facts
about the papers your parameters came from, not settings you choose. Getting
that wrong shipped a hardcoded 37 °C into every entry point for months
([ADR 0055](docs/adr/0055-a-simulation-has-no-temperature-of-its-own.md)).

## Get it running

> **Not public.** This document opens by addressing "a stranger who found
> this on GitHub", and then hands them a clone of a repository that is
> private and staying that way — so for that reader everything this page
> describes sits behind a credential prompt, unreached.> (Removed 2026-08-23 on a probe that had silently authenticated
> through a developer keychain; restored 2026-08-29 after CI — which
> holds no credentials — and an unauthenticated API check both said
> private. The probe now strips credential helpers so this cannot
> recur.)
>
> Said here rather than discovered at a credential prompt. See
> [ADR 0143](docs/adr/0143-the-first-command-a-stranger-runs.md).
>
> (No test or guard counts in this notice on purpose. They are stated once,
> where `check_documented_counts.py` watches them; a second copy inside a
> warning would be a number drifting with nothing looking at it.)

> **Private repository.** These repositories are private and are staying
> that way, so `gh repo clone` — which uses your GitHub credentials — is
> the command that works. A plain `git clone` URL stops at a username
> prompt. See [ADR 0179](docs/adr/0179-the-guard-that-could-not-go-green.md).```bash
gh repo clone Terrium-sim/main
cd main
make setup     # creates .venv, installs everything — 2–5 min, ~120 MB
make check     # verifies the stack genuinely works
make test      # the full suite
```

> **`git remote get-url origin` says something else** — it says
> `math12345678/terrium.git`. That is the remote this working copy pushes
> to; `Terrium-sim/main` is where the project is published, confirmed by
> the owner on 2026-08-16. Both being true at once is normal for a repo
> that moved, and it is recorded here because a newcomer who runs
> `git remote -v` after cloning will see the difference and otherwise have
> no way to tell which is wrong.
>
> This is worth knowing about how it got fixed. The URL was stated three
> different ways — this file said `Terrium-sim/main`, `README.md` said
> `Terrium-sim/terrium`, `origin` said neither — and the first repair made
> all three agree on `terrium` **without checking which was more widely
> used**. It was the minority spelling: 3 references against 126, and the
> 126 included every link on the GitHub New Issue page. Agreement reached
> by looking at three files is not agreement.
>
> `--recursive` was removed: there is no `.gitmodules` here, so it did
> nothing. `docs/PUBLISHING.md` describes an 18-repository split in which
> `main` becomes an umbrella of submodules; if that happens, the flag comes
> back, and `Tests/test_clone_instructions_agree.py` will start requiring
> it the moment a `.gitmodules` appears.

`make setup` is the slow one. It downloads prebuilt wheels rather than
compiling anything (libroadrunner alone is 50 MB), and pip prints nothing
while it resolves. A silent terminal is not a hang.

`make check` is not a version check. It builds a real Michaelis-Menten
model, integrates it, and compares the result against the exact closed-form
solution. If it passes, the numerics can be trusted.

**If a step fails, run `make doctor` first.** It runs on a bare interpreter
and imports nothing outside the standard library, so it still works when the
venv is the broken thing. It prints every interpreter it found, the venv's
state and which Python built it, each required package's version against its
pin, and whether Node is present.

If any of this fails on your machine, **that is a bug and we want to know.**
A setup that only works for the person who wrote it is a real defect, and a
newcomer is the best-placed person in the project to find it. Paste the
`make doctor` output into the report — it is the whole environment in one
block.

Windows: use WSL2 or the Dev Container. The Makefile is POSIX shell. See
[CONTRIBUTING.md](CONTRIBUTING.md#windows).

## One letter that will confuse you

The Python package is **`Terium`** — one r. The product, this repository and
the GitHub organisation are **`Terrium`** — two.

```python
import Terium          # correct
import Terrium         # ModuleNotFoundError, always
```

Both spellings are right in their place and you will see both everywhere.
If you hit `No module named 'Terrium'`, **your environment is fine** — you
have typed the product name where the package name goes. `make doctor` will
tell you the install is healthy, which is true and unhelpful.

`scripts/check_package_spelling.py` fails the build on the wrong import, so
this costs you a CI run at worst rather than an afternoon.

Whether the product should be renamed altogether is a live question — it
shares a field and nearly a name with the Sauro lab's
[Tellurium](https://tellurium.analogmachine.org/). See
[`docs/RENAME_PLAN.md`](docs/RENAME_PLAN.md) for the cost, and the
non-affiliation notice near the top of the README for why it matters.

## Where things live

| directory | what is in it |
|---|---|
| [`Terium/`](Terium/README.md) | the simulation engine — fifteen domains, and the Python that integrates them |
| [`Tests/`](Tests/README.md) | the literature layer — BRENDA and PubMed clients, resolvers, the fallback chain |
| [`src/`](src/README.md) | the TypeScript surface — CLI, web server, dashboard, engine bridge |
| [`Science-Agent-Pipeline/`](Science-Agent-Pipeline/README.md) | the Express API server and the agent pipeline |
| [`scripts/`](scripts/README.md) | the guards — the scripts that fail the build when a claim stops being true |
| [`docs/`](docs/README.md) | ADRs, the constitution, the expert-feedback record |
| [`examples/`](examples/README.md) | runnable end-to-end examples |

## Your first task

Pick one from **[docs/FIRST_TASKS.md](docs/FIRST_TASKS.md)**. Every entry
there is a real open gap with a file to open, a command that shows it
failing, and a way to know when you are done. None of them are made-up
exercises.

If none appeal, the most valuable thing a new person does is **find
something wrong that everyone else stopped seeing**:

```bash
npx ts-node src/cli/scientificCLI.ts resolve "made up enzyme" \
  --substrate nonsense --organism "Homo sapiens"
```

Does it fail cleanly and tell you why? Try nonsense units, negative
concentrations, an enzyme with a Unicode name, a substrate with an
apostrophe. Try it with no network.

A good report has three parts: **what you ran**, **what happened**, **what
you expected.** That is enough. You do not need to know the fix.

## The standard

One rule shapes the whole project:

> **A check that cannot fail is worse than no check, because it is trusted.**

Practically, when you fix something:

1. **Reproduce it first.** Do not trust a bug report, including your own
   from an hour ago. Run it and watch it fail.
2. **Mutation-test the fix.** Break it on purpose, confirm your test goes
   red, put it back. A test that passes before and after your change tested
   nothing.
3. **Never report success on failure.** If something failed, say so. That
   sounds too obvious to state; it has shipped here three times, most
   recently in a script that printed *"All 16 repositories pushed"* after
   every push had failed.

Step 2 is the one people skip. It is also the one that has caught the most
real defects in this codebase — including several in checks that were
themselves written to catch defects.

## Before you open a pull request

```bash
make pr
```

That is the whole checklist. It runs the guards CI runs, in CI's order, then
the test suites — so a green `make pr` means a green PR.

It exists because it did not, and the omission was the kind this project
cares about: `CONTRIBUTING.md` told contributors to run `make test`, which
is two commands, while CI ran eleven. Someone who followed the instructions
exactly still got a red X, from checks the instructions never mentioned
([ADR 0057](docs/adr/0057-contributing-means-running-what-ci-runs.md)).

If you want the pieces separately:

```bash
make guards                                # the guards only, no suites
python -m pytest Terium/tests Tests -q     # the Python suites
npx tsc --noEmit -p .                      # both trees must compile
```

If a guard fails, fix the cause. **Do not weaken a guard to make the build
green.** If you think a guard is wrong, say so in the PR and explain why —
that is a legitimate position and has been right before.

In the PR, say what you verified and how. "Should work" is not a result.

Branch naming: `yourname/what-it-does`, e.g. `priya/fix-csv-zero-export`.

Work in **`main`**. Do not commit directly into `terium`, `tests`,
`backend-main` and the rest — those are regenerated from here by
`scripts/split_repos.sh`, and a commit made straight into one gets
overwritten on the next split.

## Things that are genuinely fine

- Asking a question that turns out to have an obvious answer.
- Reporting a bug that turns out to be your environment. That is still a
  documentation bug.
- Disagreeing with a decision in the codebase. Several were wrong.
- Not knowing the biology. Most of the work is software.
- Taking a week on your first task. The standard here is unusual and it
  takes a while to stop fighting it.

## When you need more

| what | where |
|---|---|
| the engineering rules, in full | [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) |
| why a design is the way it is | [`docs/adr/`](docs/adr/) — start with the [index](docs/adr/README.md) |
| what reviewers outside the project said, and what changed | [`docs/EXPERT_FEEDBACK.md`](docs/EXPERT_FEEDBACK.md) |
| setup detail, Python version policy, PR rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| the HTTP API | [`docs/API.md`](docs/API.md) |
| what lives in which of the 18 repositories | [`docs/REPO_MAP.md`](docs/REPO_MAP.md) |
| how it was actually built, mistakes included | `Business/build-stages/` |
| if you are an AI agent | [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md) |

`Business/build-stages/` is the honest one. Every stage records what broke
and what the failure taught. If you want to understand why the project is
paranoid about certain things, the reasons are there.

Those records are **never rewritten** to match the present. They describe
what was true on a date, including counts that have since changed. That is
deliberate, and it is why the staleness guard
(`scripts/check_documented_counts.py`) covers this file and the other
present-tense docs but not the historical ones.