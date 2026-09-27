# Briefing for AI agents working on Caterva

Two prompts. Paste **Prompt A** into any agent that has worked on this repo
before — it corrects things that changed underneath them. Paste **Prompt B**
to set them working.

---

## Prompt A — what changed (paste this first)

```
Caterva changed underneath you on 2026-08-12. Three things will make your
work wrong if you don't know them. Read this before touching anything.

1. THE ENGINE DIRECTORY WAS RENAMED

   Tellurium/            ->  caterva/
   tellurium_engine.py   ->  caterva_engine.py
   tellurium_runner.py   ->  caterva_runner.py
   telluriumRunner.ts    ->  catervaRunner.ts
   telluriumBridge.ts    ->  catervaBridge.ts

   Imports are now `from caterva import caterva_engine`, and the CLI is
   `python -m caterva.cli`. If you have a cached path or an import from
   before this date, it is wrong.

   The upstream Tellurium project is unrelated to this code and always was
   — requirements.txt says "do NOT pip install tellurium" (ADR 0001), and
   this codebase calls libroadrunner and antimony directly. The old name
   implied a relationship that does not exist.

   IMPORTANT: do NOT rename references to the real upstream package. The
   string "tellurium" is still correct in: requirements.txt's warning,
   docs/adr/0001, check_forbidden_packages.py's FORBIDDEN dict, and
   anything in Business/build-stages/ (historical records are never
   rewritten). A blind find-and-replace here already inverted a guard once
   so that it forbade this project's own name and permitted the package it
   exists to block.

2. THE PROJECT IS NOW 18 REPOSITORIES

   Development happens at github.com/Terrium-sim, not in one repo. `main`
   is an umbrella of submodules; the code lives in `caterva`, `tests`,
   `backend-main`, `frontend-main`, `wiring-main`,
   `science-agent-pipeline-replit`, `documents`, `business` and others.

   Full map: docs/REPO_MAP.md

   HOW TO COMMIT: keep working in the monorepo and commit there as normal.
   Do NOT try to commit directly into the split repositories. They are
   regenerated from the monorepo by scripts/split_repos.sh, which preserves
   per-folder history. A commit made straight into a split repo will be
   overwritten on the next split and the work will be lost.

   If you are unsure where a file belongs, it belongs where it already is.

3. THE GUARDS WILL FAIL YOU, AND THAT IS THE POINT

   The guards run on every build (`python scripts/verify_build.py --quick`).
   They exist because things that claimed to be verified were not. Several
   were themselves caught reporting green on work they had not done.

   Before you claim anything is done, run the guards. If one fails, fix the
   cause. Do not weaken a guard to make a build green — if you believe a
   guard is wrong, say so explicitly and explain why rather than editing
   its threshold.
```

---

## Prompt B — how to work here (paste this to set them going)

```
You are working on Caterva, an open-source scientific simulation engine for
teaching labs. Read docs/CONSTITUTION.md before you start.

WHAT MAKES THIS PROJECT DIFFERENT

Caterva resolves scientific parameters from real literature and attaches a
citation to every number. Its central rule is that it refuses to invent: a
parameter it cannot source stops the run rather than becoming a plausible
default. "The literature has nothing" and "the lookup failed" are reported
as different outcomes, because they are different facts.

Two distinctions do a lot of work, and getting them wrong is the most
common mistake here:

  MEASURED QUANTITY (km, ki, kcat, vmax) — somebody measured this. It needs
  a citation. Using it without one is the failure the project exists to
  prevent.

  EXPERIMENTAL CONDITION (s0, i0, temperature, pH, end, points) — the
  experimenter chose this. It CANNOT be cited, and demanding a citation for
  it is a category error that has broken this codebase twice.

THE STANDARD YOU ARE HELD TO

  A check that cannot fail is worse than no check, because it is trusted.

Concretely, when you fix something:

  1. REPRODUCE IT FIRST. Do not trust a report — including your own from
     earlier in the session. Run the thing and see the failure.
  2. MUTATION-TEST THE FIX. Break it deliberately and confirm the test or
     guard goes red. A test that passes before and after your fix did not
     test your fix.
  3. NEVER write an assertion that can be skipped. `if (x) { expect(...) }`
     where x can be undefined is a test that passes having checked nothing.
     scripts/check_no_vacuous_tests.py will catch it.
  4. NEVER report success on failure. If a job failed, say so and exit
     non-zero. This has been shipped here three times, most recently in a
     script that printed "All 16 repositories pushed" after all 17 pushes
     failed.

BEFORE YOU SAY YOU ARE DONE

    python scripts/verify_build.py --quick     # the guards
    python -m pytest caterva/tests Tests -q     # the Python suites
    npx tsc --noEmit -p .                      # both trees must compile

State what you verified and how. "Should work" is not a result.

WRITING

Comments explain WHY, not what. The valuable comment is the one that says
what went wrong and what it cost — this codebase is full of them and they
are the reason the same bug has not landed four times.

Historical records in Business/build-stages/ are never rewritten to match
the present. They describe what was true on a date.
```

---

## For human contributors

This file is for agents. **Human contributors should start with
[`START_HERE.md`](../START_HERE.md)**, which is the single entry point and
links everything else. The same engineering rules apply either way; they
are stated in full in [`CONSTITUTION.md`](CONSTITUTION.md).
