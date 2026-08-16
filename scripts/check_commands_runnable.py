#!/usr/bin/env python3
"""Every script this repository tells someone to run must be runnable.

THE BUG THIS COMES FROM
-----------------------
`check_golden_freshness.py` printed, in its failure output:

    python scripts/verify_golden_against_live.py

That script loaded `Tests/test_golden_set.py` to read the golden tuples, and
its own docstring claimed it did so "without importing pytest". The claim
was false: that module imports pytest at the top. Outside a test
environment the script died on `ModuleNotFoundError: No module named
'pytest'`.

So a guard was instructing people to run a command that could not run, and
nothing in the repository disagreed. The guard passed. The script's tests
passed — they ran under pytest, where pytest is importable, which is exactly
the environment in which the bug is invisible.

WHAT THIS CHECKS
----------------
Two things, both of which that bug is an instance of:

1. **Named and missing.** Every `scripts/<name>.py` mentioned in tracked
   documentation, guard output or CI exists on disk. Docs rot; scripts get
   renamed.

2. **Data modules load without a test framework.** Modules in
   `SHARED_DATA_MODULES` are read by scripts that run OUTSIDE pytest, so
   they must import with pytest unavailable. Checked by importing them in a
   subprocess where `pytest` is blocked — not by grepping for `import
   pytest`, because the failure can arrive through a chain of imports that
   no single grep would see.

WHAT IT DOES NOT CHECK, AND WHY THAT MATTERS HERE
-------------------------------------------------
It does NOT prove a documented command succeeds end to end. Running
`verify_golden_against_live.py` for real needs BRENDA; running
`export_annotated_model.py` needs a payload on stdin. A guard that tried
would either need the network or would be inventing inputs.

**Stated plainly because it is tempting to overclaim: check (1) alone would
NOT have caught the bug above.** The script existed and `--help` worked;
argparse exits before the failing code runs. Check (2) is the one that
catches it, and it catches it by reproducing the condition the tests could
not — an environment with no pytest.

Exit 0 = every named script exists and every shared data module loads
standalone. Exit 1 = something the repository tells you to run cannot run.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

#: Modules that carry DATA rather than tests, and are loaded by scripts
#: running outside pytest. Each must import with no test framework present.
#:
#: `Tests/golden_set.py` is here because the golden tuples moved out of
#: `test_golden_set.py` precisely so guards could read them. If a test
#: framework import ever creeps back in — directly or through something it
#: imports — every consumer outside pytest breaks, and only in the
#: environment nobody tests in.
SHARED_DATA_MODULES = ("Tests/golden_set.py",)

#: A script path under ANY `scripts/` directory, not just the repo root's.
#:
#: The first version matched a bare `scripts/<name>.py` and therefore also
#: matched the TAIL of longer paths: `advanced_analysis/scripts/
#: generate_figures.py` was reported as a missing `scripts/
#: generate_figures.py`, and the file exists exactly where the docs say it
#: does. A guard's first run producing a confident false accusation is a
#: pattern this repository has now seen four times, and the cause is always
#: the same -- the checker understood less of the world than it believed.
#:
#: Capturing the full path also makes the guard STRICTER, not just quieter:
#: it now checks `provenance_visualization/scripts/dashboard.py` too, which
#: the narrow version could not see and which genuinely does not exist.
_COMMAND_RE = re.compile(
    r"(?:python3?\s+|streamlit\s+run\s+)?"
    r"((?:[A-Za-z0-9_.-]+/)*scripts/[A-Za-z0-9_]+\.py)"
)

#: Illustrative names in guard prose, not instructions to anyone.
#:
#: An allowlist rather than a heuristic: "does this look like a
#: placeholder?" is exactly the kind of guess that makes a guard
#: untrustworthy. Each entry names the file it appears in and why, so an
#: entry added without justification is visible as such.
ILLUSTRATIVE = {
    "scripts/check_x.py": "placeholder in check_guard_wiring.py's prose",
    "scripts/foo.py": "regex example in this file's own comments",
    # Stronger than illustrative: this name MUST NOT EXIST.
    #
    # Tests/test_ci_reproducible_locally.py passes it to `classify()` and
    # asserts the result is `unreachable` — it is the fixture that exercises
    # that guard's failing branch, which the test's own docstring records as
    # having been unexercised by all eight of the original tests.
    #
    # So "fix the finding by creating the file" would silently disarm a test
    # written specifically to prove a guard can fail. The negation-marker
    # window does not catch it because the sentence that disowns the name
    # sits two lines BELOW the mention, in the assertion message, and the
    # window only looks up. Widening it to look down as well would let an
    # unrelated later paragraph disown a real command, which is the more
    # expensive mistake.
    "scripts/check_something_new.py": (
        "fixture in test_ci_reproducible_locally.py; the test asserts it is "
        "unreachable, so creating it would break the test it belongs to"
    ),
}

_SEARCH_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".sh", ".ts", ".json"}
_SEARCH_NAMES = {"Makefile"}
_SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__",
    ".pytest_cache", ".mypy_cache", "coverage", ".next",
}

#: Historical records, which QUOTE broken commands as evidence.
#:
#: Added 2026-08-15. This guard reported
#: `../scripts/check_codegen_loads.py` as unrunnable, named by
#: `docs/EXPERT_FEEDBACK.md`. It was right that the path does not resolve --
#: and the sentence around it says so, at length, in a section titled "Two
#: findings from check_commands_runnable, and only one was real". The record
#: was quoting the defect in order to explain how it was fixed.
#:
#: So the guard was failing the build over a document describing the guard
#: working. The only way to go green would have been to edit the quotation,
#: which would falsify a record of what was actually written -- and
#: `docs/README.md` states that historical records are never rewritten.
#:
#: A guard that can only be satisfied by corrupting evidence is worse than
#: no guard, for the same reason a check that cannot fail is: people learn
#: to work around it. Same shape as the quoted-count false positive fixed in
#: `check_documented_counts.py` the same day -- a matcher that could not tell
#: an assertion from a quotation.
#:
#: These files are excluded by NAME rather than by pattern, so the exclusion
#: is a decision somebody made rather than an accident of a regex.
_HISTORICAL_DOCS = {
    "docs/EXPERT_FEEDBACK.md",
    "docs/ARCHIVE_TRIAGE.md",
}

#: Blocks `import pytest` from inside a subprocess, so a module that needs
#: it fails the way it would on a machine that has never installed it.
#:
#: Uninstalling is not an option and monkeypatching sys.modules is not
#: enough — that only masks an already-imported module. A meta_path finder
#: refuses the import itself, which is what a missing package does.
_BLOCK_PYTEST = """
import importlib.abc, importlib.util, pathlib, sys


class _Refuse(importlib.abc.MetaPathFinder):
    BLOCKED = {"pytest", "_pytest", "py"}

    def find_spec(self, name, path=None, target=None):
        root = name.split(".")[0]
        if root in self.BLOCKED:
            raise ImportError(
                f"{root} is deliberately unavailable: this module must load "
                "outside a test environment"
            )
        return None


sys.meta_path.insert(0, _Refuse())

target = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(target.parent))
spec = importlib.util.spec_from_file_location("_under_check", target)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if not any(not name.startswith("_") for name in vars(module)):
    raise SystemExit("module loaded but defines nothing public")
"""


def _candidate_files() -> list[pathlib.Path]:
    """Tracked and untracked files a command could be written in."""
    seen: dict[str, pathlib.Path] = {}
    for args in (
        ["git", "ls-files"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        out = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if not line:
                continue
            path = REPO / line
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if line in _HISTORICAL_DOCS or line.startswith("Business/build-stages/"):
                continue
            if path.suffix in _SEARCH_SUFFIXES or path.name in _SEARCH_NAMES:
                seen[line] = path
    return list(seen.values())


#: Path segments that are not real directories: shell variables written
#: `$ROOT/scripts/x.py`, and prose elisions written `.../scripts/x.py`.
#: The `$` is outside the captured group, so the raw match keeps a segment
#: like `REPO_DIR` that no filesystem has.
_UNRESOLVABLE_SEGMENT = re.compile(r"^([A-Z][A-Z0-9_]*|\.\.\.)$")


def _normalise(match: str) -> str:
    """Resolve a matched path against the repository.

    A command written `$REPO_DIR/scripts/check_x.py` in a shell script is
    satisfied by `scripts/check_x.py` existing -- the variable expands to
    the repository root at run time. Reading the variable name as a
    directory produced seven confident false accusations on this guard's
    second run, all of them scripts that exist and are wired into CI.

    Only leading segments that CANNOT be directories are stripped. A real
    prefix like `advanced_analysis/` is kept, because
    `advanced_analysis/scripts/generate_figures.py` and
    `scripts/generate_figures.py` are different claims and only one of them
    is true.
    """
    parts = match.split("/")
    while len(parts) > 2 and _UNRESOLVABLE_SEGMENT.match(parts[0]):
        parts.pop(0)
    return "/".join(parts)


#: Phrases that turn a mention into a statement ABOUT a command rather than
#: an instruction to run it.
#:
#: Naming a command is the only way to document that it does not exist, so
#: a guard with no way to express that forces a choice between an honest
#: record and a green build. This repository consistently prefers the
#: record, so the guard has to accommodate it.
#:
#: An explicit phrase list rather than sentiment-guessing: "does this
#: paragraph sound negative?" is precisely the sort of inference that makes
#: a guard untrustworthy.
_NEGATION_MARKERS = (
    "not built",
    "does not exist",
    "never existed",
    "no such",
    "has never existed",
    "previously gave",
    "deliberately not",
)

#: How far above a mention to look for a marker. Commands are usually shown
#: in an indented block under the sentence that disowns them, so the marker
#: is rarely on the same line. Six lines covers a short paragraph and a
#: fenced block opener without reaching into unrelated prose.
_NEGATION_WINDOW = 6


def _is_disowned(lines: list[str], index: int) -> bool:
    start = max(0, index - _NEGATION_WINDOW)
    window = " ".join(lines[start : index + 1]).lower()
    return any(marker in window for marker in _NEGATION_MARKERS)


def _named_scripts() -> dict[str, list[str]]:
    """script path -> the files that name it."""
    named: dict[str, list[str]] = {}
    for path in _candidate_files():
        # A guard that documents its own findings would flag itself: the
        # example paths in this file's comments are evidence about past
        # false positives, not instructions to anyone. Excluding the file
        # from its own corpus is the same reasoning as excluding a script's
        # own tests from proving it reachable.
        if path.name == pathlib.Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            for raw in set(_COMMAND_RE.findall(line)):
                match = _normalise(raw)
                if match in ILLUSTRATIVE:
                    continue
                if _is_disowned(lines, index):
                    continue
                named.setdefault(match, []).append(str(path.relative_to(REPO)))
    return named


def _loads_without_pytest(module: pathlib.Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-c", _BLOCK_PYTEST, str(module)],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    if result.returncode == 0:
        return True, ""
    tail = (result.stderr or result.stdout or "").strip().splitlines()
    return False, tail[-1] if tail else f"exit {result.returncode}"


def main() -> int:
    problems: list[str] = []

    # --- 1. named and missing -------------------------------------------
    named = _named_scripts()
    if not named:
        print(
            "No `scripts/*.py` commands are named anywhere. Either nothing "
            "documents a command or this search is broken; refusing to "
            "report success on an empty set."
        )
        return 1

    missing = {
        script: callers
        for script, callers in named.items()
        if not (REPO / script).is_file()
    }
    for script, callers in sorted(missing.items()):
        problems.append(
            f"{script} is named by {', '.join(sorted(callers)[:3])} "
            f"({len(callers)} file(s)) and does not exist."
        )

    # --- 2. shared data modules load standalone -------------------------
    checked_modules = 0
    for relative in SHARED_DATA_MODULES:
        module = REPO / relative
        if not module.is_file():
            problems.append(f"{relative} is listed as a shared data module and is missing.")
            continue
        checked_modules += 1
        ok, reason = _loads_without_pytest(module)
        if not ok:
            problems.append(
                f"{relative} cannot be imported without pytest: {reason}\n"
                "      Anything that reads it outside a test environment is "
                "broken, and the test suite cannot see that because it runs "
                "inside one."
            )

    print(
        f"Checked {len(named)} named command(s) across "
        f"{len(_candidate_files())} file(s), and {checked_modules} shared "
        "data module(s) for standalone loading."
    )

    if problems:
        print()
        print(f"Commands this repository cannot honour ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print(
            "Telling someone to run something that cannot run is worse than "
            "not mentioning it: they conclude the project is broken, and "
            "they are right."
        )
        return 1

    print(
        "OK: every named script exists, and every shared data module loads "
        "with no test framework available."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
