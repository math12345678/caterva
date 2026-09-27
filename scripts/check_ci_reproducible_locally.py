#!/usr/bin/env python3
"""Everything CI runs must be runnable locally from a documented command.

THE GAP THIS COMES FROM
-----------------------
CONTRIBUTING.md said, and still says, the right thing:

    Run `make test` before opening the PR, not just after CI catches it.
    CI is the backstop, not the first line of defense.

`make test` runs two commands: pytest in caterva/ and pytest in Tests/.
The `test` job in .github/workflows/tests.yml runs eleven, of which those
two are the ninth and tenth. The other nine are guards -- citation format,
documented counts, the Python-support claim, forbidden packages, guard
wiring, the whole of verify_build.py, silent skips, codegen.

So a contributor who did exactly what CONTRIBUTING told them to do
reproduced two of eleven steps, pushed, and found out about the other nine
from a red X. Nothing in the repository disagreed with the instruction,
because nothing compared it to CI.

That is the same shape as ADR 0027 and ADR 0046: a value computed on one
side of a boundary and never received on the other. Here the boundary is
between what CI runs and what a person can run, and the undelivered thing
is the knowledge that a guard exists at all.

WHAT THIS CHECKS
----------------
Every `run:` step in the workflow is classified exactly once:

  * **reachable** -- its command appears in a Makefile recipe, so a
    contributor has a documented way to run it before pushing.
  * **CI_ONLY** -- it cannot reasonably run on a laptop, and the reason is
    written down here rather than left to be inferred.

An unclassified step FAILS. The default is deliberately "you must decide",
not "assume it's fine": a new CI step added without a local route is the
exact regression this exists to catch, and a permissive default would let
it through silently on the day it happens.

WHY IT CANNOT QUIETLY PASS
--------------------------
A checker that parses a file and finds nothing reports "all clear", which
is indistinguishable from a clean bill of health and is how a guard becomes
decoration. Two floors prevent that here:

  * the workflow must yield at least `_MIN_STEPS` run-steps, and
  * the Makefile must yield at least `_MIN_RECIPES` recipes,

both far below the real counts and both fatal when unmet. If the parse
breaks, this script fails loudly rather than congratulating anyone.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
MAKEFILE = ROOT / "Makefile"

# Below these, the parse is broken rather than the repository being clean.
# Set well under the real counts (11 run-steps, 15 recipes at time of
# writing) so ordinary edits do not trip them and a parser regression does.
_MIN_STEPS = 8
_MIN_RECIPES = 6

# Steps that genuinely cannot run from a plain `make` on a contributor's
# machine. Each needs a reason, because "CI only" with no reason is how a
# step nobody can run locally becomes permanent by default.
#
# Keyed by a distinctive substring of the command.
CI_ONLY: dict[str, str] = {
    # --- Classified 2026-08-22 (ADR 0159) ------------------------------
    #
    # These were unclassified, so this guard failed, so the pytest wrapper
    # around it failed -- inside a suite that had not run in CI for a day
    # because of the step-ordering bug in ADR 0158. Fixing the ordering
    # uncovered them; they are not new.
    "$GITHUB_STEP_SUMMARY": (
        "writes a diagnostic into the GitHub run summary. There is no run "
        "summary on a laptop, and `make doctor` already prints the same "
        "interpreter and package facts locally."
    ),
    "python -c \"import sys, platform;": (
        "part of the run-summary block above; same reason."
    ),
    "python -m pip --version": (
        "part of the run-summary block above; same reason."
    ),
    "python -m pip list --format=freeze": (
        "part of the run-summary block above; same reason."
    ),
    "echo '```'": (
        "markdown fencing inside the run-summary block; not a check."
    ),
    "echo \"### Resolved environment": (
        "the run-summary block's heading; not a check."
    ),
    "::error title=tests/": (
        "emits a GitHub annotation on failure so the cause is legible from "
        "the run page without opening a log. Annotations do not exist "
        "outside Actions; locally the failing command's own output is right "
        "there in the terminal."
    ),
    "A step above this one failed.": (
        "continuation line of the annotation above."
    ),
    "job summary. Every guard in this job passes": (
        "continuation line of the annotation above."
    ),
    "(checked 2026-08-21), so suspect the installed set": (
        "continuation line of the annotation above."
    ),
    "restored by setup-python, which the api-server job does not use.": (
        "continuation line of the annotation above."
    ),
    "python scripts/check_availability_notice_matches_reality.py": (
        "probes GitHub over the network to decide whether the front page's "
        "'not public yet' notice is still true. A local target that reaches "
        "GitHub stops being fast, and a slow local target stops being run "
        "(ADR 0028). Its --selftest drives all four verdicts offline."
    ),
    "python scripts/check_ci_toolchain.py": (
        "reads .github/workflows and checks that a step named after "
        "installing something installs it. Nothing to say on a developer's "
        "machine, and it must fail BEFORE the job it describes."
    ),
    "python scripts/check_quickstart_clone_works.py": (
        "makes real network calls to GitHub. Expected RED until the "
        "repositories are published (ADR 0143), and deliberately the LAST "
        "step in the job (ADR 0158) so it stops nothing behind it."
    ),
    "corepack enable": (
        "activates pnpm on the runner. The local equivalent is having pnpm "
        "installed, which CONTRIBUTING states; replaced "
        "`corepack prepare pnpm@X --activate`, which exited 0 and installed "
        "nothing (ADR 0140)."
    ),
    "python scripts/check_ci_red_step_is_last.py": (
        "reads .github/workflows/tests.yml and checks the ORDER of its own "
        "job's steps. On a laptop it can only ever repeat what CI already "
        "knows, and a guard with nothing to say locally is one people learn "
        "to scroll past (ADR 0028). Its selftest drives both verdicts on "
        "text rather than on the tree, so the logic is exercised offline."
    ),
    "python scripts/check_ci_red_step_is_last.py --selftest": (
        "same script; the selftest is the offline half and is wired in CI "
        "beside it."
    ),
    "pip install -r requirements-dev.txt": (
        "`make setup` is the local equivalent and CONTRIBUTING opens with "
        "it; CI installs into the runner's system Python instead of a venv."
    ),
    "pip install --upgrade pip": (
        "Part of CI's install step, not a check. `make setup` upgrades pip "
        "inside .venv itself."
    ),
    "pnpm install --frozen-lockfile": (
        "Needs a network install of the JS workspace. Documented in "
        "RUN_TESTS.md for the api-server workspace."
    ),
    "pnpm run typecheck": (
        "Compiles the TypeScript workspace, so it needs the Node toolchain "
        "and a completed pnpm install -- the same reason as the api-server "
        "suite below. `make pr` names it as one of the things it did not "
        "run. It exists because vitest only compiles what a test imports: "
        "the landing app is imported by no test, and an unterminated JSX "
        "comment in CliApp.tsx broke `pnpm run build` for five days without "
        "reddening anything."
    ),
    "pnpm --filter @workspace/api-server run test": (
        "The TypeScript suite runs under pnpm in Science-Agent-Pipeline, "
        "outside the Python Makefile's world. RUN_TESTS.md covers it."
    ),
    "check_identifier_patterns_fresh.py": (
        "Consults the live identifiers.org registry, so it needs network "
        "access to a third party and cannot be part of the offline fast "
        "path. Its comparison logic IS reproducible locally: "
        "Tests/test_identifier_pattern_freshness.py drives all three "
        "verdicts -- matched, drifted, unreachable -- against a stubbed "
        "fetch, and runs under `make test` like everything else. What is "
        "CI-only is the network call, not the logic."
    ),
    "check_codegen_loads.py": (
        "Runs orval, so it needs the Node toolchain and a completed pnpm "
        "install -- which is why the workflow comment puts it here rather "
        "than in verify_build --quick, 'the fast path that stops getting "
        "run the moment it stops being fast'."
    ),
}


def _run_steps(text: str) -> list[str]:
    """Every command in a `run:` step, one per returned entry.

    Handles both `run: cmd` and the block form:

        run: |
          cmd one
          cmd two

    Written against this workflow rather than against YAML in general. It
    is checked by the `_MIN_STEPS` floor and by
    Tests/test_ci_reproducible_locally.py, which pins the parse against the
    real file -- a hand-rolled reader that silently returns [] is worse
    than no reader.
    """
    out: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)-?\s*run:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        indent, rest = m.group(1), m.group(2).strip()
        if rest and rest not in {"|", ">", "|-", ">-"}:
            out.append(rest)
            i += 1
            continue
        # Block scalar: take the more-indented lines that follow.
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                i += 1
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip())
            if nxt_indent <= len(indent):
                break
            out.append(nxt.strip())
            i += 1
    return out


def _recipe_bodies(text: str) -> dict[str, list[str]]:
    """Makefile target -> its recipe lines (tab-indented), continuations joined."""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    pending = ""
    for raw in text.splitlines():
        if raw.startswith("\t"):
            if current is None:
                continue
            body = raw[1:].strip()
            if pending:
                body = pending + " " + body
                pending = ""
            if body.endswith("\\"):
                pending = body[:-1].strip()
                continue
            recipes[current].append(body)
            continue
        pending = ""
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", raw)
        if m and not raw.startswith("."):
            current = m.group(1)
            recipes.setdefault(current, [])
        elif raw.strip() and not raw.startswith((" ", "#")):
            current = None
    return recipes


def _normalise(cmd: str) -> str:
    """Compare intent, not spelling.

    CI writes `python scripts/check_env.py`; a recipe writes
    `@"$(PY)" scripts/check_env.py`. Same command, and a comparison that
    called them different would report a gap that is not there -- which
    trains people to ignore this guard.
    """
    c = cmd.strip().lstrip("@-")
    c = re.sub(r'"?\$[({][A-Za-z_]+[)}]"?', "python", c)
    c = re.sub(r"\bpython3(\.\d+)?\b", "python", c)
    c = re.sub(r"\s+", " ", c)
    # `cd caterva && python -m pytest` in a recipe and `python -m pytest` under
    # `working-directory: caterva` in CI are the same command run in the same
    # place, spelled by the two systems' different conventions.
    c = re.sub(r"^cd [A-Za-z0-9_./-]+ && ", "", c)
    # -v changes what is printed, not what is checked.
    c = re.sub(r"(?<= )-v\b", "", c)
    return re.sub(r"\s+", " ", c).strip()


def classify(
    steps: list[str], local: set[str]
) -> tuple[list[str], list[str], list[str]]:
    """Split CI steps into (reachable, ci_only, unreachable).

    Separated from `main` so a test can hand it a step with no local route
    and confirm it lands in `unreachable`. That is not a hypothetical
    refactor for testability: the first version of this guard had the
    judgement inline, and a mutation that counted unclassified steps as
    reachable passed all eight tests -- because the repository was clean at
    the time, so the return value was 0 either way. Every test agreed with a
    guard that had stopped guarding.
    """
    reachable: list[str] = []
    ci_only: list[str] = []
    unreachable: list[str] = []
    for step in steps:
        if any(marker in step for marker in CI_ONLY):
            ci_only.append(step)
            continue
        want = _normalise(step)
        if any(want in have or have in want for have in local if have):
            reachable.append(step)
        else:
            unreachable.append(step)
    return reachable, ci_only, unreachable


def main() -> int:
    if not WORKFLOW.exists():
        print(f"FAIL: {WORKFLOW.relative_to(ROOT)} is missing.")
        return 1
    if not MAKEFILE.exists():
        print("FAIL: Makefile is missing.")
        return 1

    steps = _run_steps(WORKFLOW.read_text())
    recipes = _recipe_bodies(MAKEFILE.read_text())

    if len(steps) < _MIN_STEPS:
        print(
            f"FAIL: parsed only {len(steps)} run-step(s) from "
            f"{WORKFLOW.relative_to(ROOT)}, below the floor of {_MIN_STEPS}.\n"
            "      The workflow parser is broken, not the workflow. A guard "
            "that finds nothing must not report success."
        )
        return 1
    if len(recipes) < _MIN_RECIPES:
        print(
            f"FAIL: parsed only {len(recipes)} Makefile recipe(s), below the "
            f"floor of {_MIN_RECIPES}. The Makefile parser is broken."
        )
        return 1

    local = {_normalise(c) for body in recipes.values() for c in body}

    reachable, ci_only, unreachable = classify(steps, local)

    print(f"CI run-steps parsed:     {len(steps)}")
    print(f"Runnable from `make`:    {len(reachable)}")
    print(f"CI-only, with a reason:  {len(ci_only)}")
    print(f"Neither:                 {len(unreachable)}")

    if unreachable:
        print("\nCI runs these and nothing local does (%d):\n" % len(unreachable))
        for step in unreachable:
            print(f"  {step}")
        print(
            "\nA contributor cannot run this before pushing, so they find out "
            "from a red X.\nEither add it to a Makefile recipe -- `guards` is "
            "where the CI guards live --\nor add it to CI_ONLY in this file "
            "with the reason it cannot run locally.\n"
            "'CI only' without a reason is how a step nobody can reproduce "
            "becomes permanent."
        )
        return 1

    print("\nOK: every CI step is either runnable from `make` or recorded as CI-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
