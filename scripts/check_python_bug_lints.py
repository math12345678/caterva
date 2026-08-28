#!/usr/bin/env python3
"""
check_python_bug_lints.py

Run the ruff rules that catch BUGS, and fail the build on them.

WHY THIS EXISTS RATHER THAN "just run ruff"
-------------------------------------------
`pyproject.toml` configures ruff with forty-odd rule families selected. It
is executed by **nothing** -- not CI, not the Makefile, not
`verify_build.py`. A linter that is configured and never run reads as
coverage and is not: the config block is the most convincing possible
statement that this project lints thoroughly.

What that cost, measured rather than supposed:

    scripts/verify_build.py:813  F821  Undefined name `TERIUM_DIR`
    scripts/verify_build.py:822  F821  Undefined name `TERIUM_DIR`

`run_python_tests()` referenced a constant that did not exist, so the
non-`--quick` path of the build verification script raised `NameError`
before running a single Python test -- and every check sequenced after it
never ran either. **The script that verifies the build was broken in the
branch that runs the tests.** F821 finds it in under a second.

Also found: one duplicate pytest fixture (F811), the same
duplicate-definition class that TypeScript's compiler catches for free
(TS2300) and Python accepts silently.

WHY A NARROW SELECTION
----------------------
The full configured ruleset reports 249 findings across `Tests/` and
`scripts/`. Wiring that into a shared build would make it red on arrival,
which this project has a standing rule against: *never put an unverified or
failing check into a harness everyone runs*. A red guard is one people learn
to skip.

So this runs the subset that finds **defects rather than style**, and that
is green today:

    F821  undefined name          -- a NameError waiting for the line to run
    F811  redefinition            -- two definitions, the last silently wins
    E9    syntax / IO errors      -- the file does not parse

F401 and F841 are bug-class too and are deliberately NOT wired: they find 23
findings today, and a check that fails on arrival is one people learn to
skip. They are counted in `NOT_YET_GREEN` and printed on every run, so the
gap is a number somebody can decide about rather than a silence. Same
shrinking-baseline arrangement as the mutation tables (ADR 0072) and the
unwired exports (ADR 0090).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Rules that indicate a defect rather than a preference. Widening this list
#: is welcome and should come with the findings fixed first -- adding a rule
#: that fires is how a guard becomes something people disable.
BUG_RULES = ["F821", "F811", "E9"]

#: Bug-class rules that are NOT wired, because they are not green today.
#:
#: F401 (unused import) and F841 (unused variable) find 23 real findings
#: across this tree. They belong in BUG_RULES -- an unused import is often
#: the residue of a deleted call site, which is a fact about the code -- and
#: they are left out because wiring a check that fails on arrival is how a
#: guard becomes something people learn to skip.
#:
#: Counted rather than hidden, and the count is the whole point: 23 is a
#: number somebody can decide about. "We should lint sometime" is not.
#:
#: They are also not mine to fix in bulk. Most sit in files other agents are
#: actively writing, and a 19-file autofix landing under somebody mid-edit
#: is a worse outcome than the lint.
NOT_YET_GREEN = {"F401": 17, "F841": 3}
#
#: 23 when this guard was written; 20 now. The three cleared were the ones
#: this agent owned, and one of them was worth the trip:
#:
#:   scripts/check_findings_reach_a_surface.py had `runner_src = RUNNER
#:   .read_text()` assigned and never consulted -- the fossil of the v1/v2
#:   NAME-MATCHING approach that ADR 0045 records as having failed, left
#:   behind when the guard was rewritten to execute the runner instead. It
#:   outlived the method by two rewrites, and a guard that opens a file it
#:   does not read is a small lie about what it checks.
#:
#: That is precisely what F841 is for, and it is the argument for wiring
#: these rules rather than carrying them: an unused binding is usually the
#: residue of something that was removed.

TARGETS = ["Tests", "scripts", "Terium"]

#: Fewest Python files that must exist under TARGETS for a clean lint to
#: mean anything. Well below the real count so ordinary deletion does not
#: trip it -- a smoke alarm for a checkout that did not finish, not a
#: coverage target. See ADR 0185 for the idiom.
_MIN_PY_FILES = 50


def main() -> int:
    if shutil.which("ruff") is None and not _module_available():
        # Not installed is NOT "passed". A check that silently skips when its
        # tool is missing is the "check that cannot fail" shape -- it would
        # report OK on every machine that lacks ruff, which is every machine
        # where nobody installed it, which is how it went unrun in the first
        # place.
        print(
            "FAIL: ruff is not installed, so nothing was checked.\n"
            "  It is a declared dev dependency (pyproject.toml, ruff==0.11.11).\n"
            "  Install it, or this guard is reporting on nothing:\n"
            "      pip install ruff==0.11.11",
            file=sys.stderr,
        )
        return 1

    existing = [t for t in TARGETS if (REPO_ROOT / t).is_dir()]
    if not existing:
        print(f"FAIL: none of {TARGETS} exist; nothing was checked.", file=sys.stderr)
        return 1

    # A target that EXISTS and is EMPTY is the same nothing, and the check
    # above does not see it.
    #
    # Measured (ADR 0186): with Tests/, scripts/ and Terium/ present but
    # containing no files, ruff finds nothing and this prints "OK: no
    # bug-class lint findings" -- a clean bill of health over zero lines.
    # The existing refusal covers a deleted directory; it does not cover a
    # directory whose contents moved, or a checkout that failed halfway.
    #
    # Floor is on files handed to ruff, not on findings: zero findings is
    # exactly what a healthy repository is supposed to produce.
    py_files = sum(
        1
        for t in existing
        for p in (REPO_ROOT / t).rglob("*.py")
        if not {"__pycache__", ".venv", "venv", "node_modules"} & set(p.parts)
    )
    if py_files < _MIN_PY_FILES:
        print(
            f"FAIL: only {py_files} Python file(s) under {', '.join(existing)}, "
            f"below the floor of {_MIN_PY_FILES}.\n"
            "  The directories exist but are effectively empty, so ruff was "
            "handed nothing\n"
            "  and 'no bug-class lint findings' is true of nothing. The scan "
            "is broken, not the code.",
            file=sys.stderr,
        )
        return 1

    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", ",".join(BUG_RULES), *existing],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    print(f"Checked {py_files} Python file(s) under {', '.join(existing)} "
          f"for {', '.join(BUG_RULES)}.")
    outstanding = ", ".join(f"{r} x{n}" for r, n in sorted(NOT_YET_GREEN.items()))
    print(f"  not yet wired (bug-class, not green): {outstanding}")

    if proc.returncode == 0:
        print("\nOK: no bug-class lint findings.")
        return 0

    print("\n" + (proc.stdout or proc.stderr).strip(), file=sys.stderr)
    print(
        "\nThese are defects, not style. F821 in particular is a NameError\n"
        "waiting for its line to run -- it is how `verify_build.py` came to\n"
        "crash before executing any Python test, undetected, because the\n"
        "linter that finds it was configured and never invoked.",
        file=sys.stderr,
    )
    return 1


def _module_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


if __name__ == "__main__":
    sys.exit(main())