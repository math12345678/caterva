"""Guard that every TypeScript test file on disk is found by its runner.

THE GAP THIS CLOSES

`check_documented_counts.py` counts only `caterva/tests` and `Tests/` --
Python. `check_no_silent_skips.py` counts pytest's "N skipped" line -- also
Python. Roughly six hundred TypeScript tests across two runners were
invisible to both, so a whole suite could stop being discovered and nothing
anywhere would move.

That is not hypothetical in this repository. Stage 10 Part 21 recorded
nineteen Python tests that silently stopped running when a
`pytest.importorskip` was added; the count guard caught it because the
number went down. There is no equivalent number for TypeScript.

WHY DISCOVERY RATHER THAN A COUNT

The obvious fix -- count TypeScript test cases and put the number in the
README -- fails twice:

  * `vitest list` imports every test file to enumerate cases. It takes
    ~150s here, which is too slow for the fast path, and a guard that is
    too slow to run is a guard that stops being run (see
    `check_rng_convention`, which sat dead for a whole stage).
  * A total is easy to satisfy accidentally. Deleting one suite and adding
    tests elsewhere leaves the number flat.

`vitest list --filesOnly` and `jest --listTests` answer a better question in
about two seconds each: WHICH FILES will actually run. Comparing that
against the files on disk catches the real failure mode exactly -- a rename,
a moved directory, or an `include` glob edited in a config, any of which
makes a suite vanish while every remaining test still passes.

It cannot catch a single `it()` being deleted from a file that still runs.
That is what `check_no_vacuous_tests` and code review are for, and saying so
is better than implying coverage this does not have.

Run directly: python scripts/check_typescript_suites_discovered.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
API_SERVER = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server"

SKIP_PARTS = {"node_modules", "dist", "coverage", ".git", "__pycache__"}
TEST_FILE = re.compile(r".*\.(test|spec)\.tsx?$")

#: (label, working directory, command that lists the files it will run).
#:
#: Both are file-listing modes, NOT case-listing: they do not import the
#: test files, which is what keeps this under five seconds total.
SUITES = [
    (
        "root (jest)",
        REPO_ROOT,
        ["npx", "jest", "--listTests"],
    ),
    (
        "api-server (vitest)",
        API_SERVER,
        ["npx", "vitest", "list", "--filesOnly"],
    ),
]

TIMEOUT_S = 180


def _files_on_disk(root: pathlib.Path, exclude: list[pathlib.Path]) -> set[pathlib.Path]:
    found: set[pathlib.Path] = set()
    for current, directories, names in os.walk(root):
        directories[:] = [d for d in directories if d not in SKIP_PARTS]
        here = pathlib.Path(current)
        if any(here == e or e in here.parents for e in exclude):
            continue
        for name in names:
            if TEST_FILE.match(name):
                found.add((here / name).resolve())
    return found


def _discovered(label: str, cwd: pathlib.Path, command: list[str]) -> set[pathlib.Path] | str:
    """Files the runner says it will run, or an error string."""
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"{label}: listing timed out after {TIMEOUT_S}s"
    except OSError as exc:
        return f"{label}: could not run {' '.join(command)} ({exc})"

    out = proc.stdout.strip()
    if not out:
        return (
            f"{label}: the runner listed NO files "
            f"(exit {proc.returncode}). {proc.stderr.strip()[:200]}"
        )

    paths: set[pathlib.Path] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or not TEST_FILE.match(line):
            # jest --listTests can emit a JSON array when configured to.
            if line.startswith("["):
                try:
                    for entry in json.loads(line):
                        paths.add(pathlib.Path(entry).resolve())
                except (ValueError, TypeError):
                    pass
            continue
        candidate = pathlib.Path(line)
        paths.add(
            candidate.resolve() if candidate.is_absolute() else (cwd / candidate).resolve()
        )

    if not paths:
        return f"{label}: no test file paths could be parsed from the runner's output"
    return paths


def check() -> list[str]:
    """Returns a list of violation strings, empty when every suite is found."""
    violations: list[str] = []

    # The api-server tree lives inside the repo, so the root jest scan must
    # not claim its files; jest's own config already excludes them, and
    # counting them as "missed by jest" would be a false positive.
    root_disk = _files_on_disk(REPO_ROOT / "src", [])
    api_disk = _files_on_disk(API_SERVER / "src", [])

    expected = {
        "root (jest)": root_disk,
        "api-server (vitest)": api_disk,
    }

    total_found = 0

    for label, cwd, command in SUITES:
        result = _discovered(label, cwd, command)
        if isinstance(result, str):
            violations.append(
                f"{result}. A runner that listed nothing has an unknown set "
                "of tests, which is not the same as an empty one."
            )
            continue

        on_disk = expected[label]
        if not on_disk:
            violations.append(
                f"{label}: found zero test files on disk. Refusing to report "
                "success -- an empty scan is not a clean tree."
            )
            continue

        missed = sorted(on_disk - result)
        total_found += len(result)
        print(f"  {label:<22} {len(result):>3} discovered, {len(on_disk):>3} on disk")

        for path in missed:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} exists but {label} does not "
                "discover it, so none of its tests run. Check the runner's "
                "include globs and testMatch: a suite that is never "
                "collected reports green forever."
            )

    if not violations:
        print(
            f"OK: all {total_found} TypeScript test files on disk are "
            "discovered by a runner."
        )
    return violations


def main() -> int:
    print("Listing what each TypeScript runner will actually run...")
    violations = check()
    if not violations:
        return 0

    print(f"\nUndiscovered or unlistable suites ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA test file nothing collects is indistinguishable from a passing "
        "one, and cheaper to write."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
