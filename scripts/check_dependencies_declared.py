"""Guard against the class of bug that broke CI on 2026-07-23.

That day, brenda_client.py imported httpx and pydantic at module level, but
neither was listed in requirements.txt. Nothing caught it locally because
whoever last set up their environment happened to have both installed from
some other project. It only surfaced when CI did a genuinely fresh install
and the whole literature-layer test suite failed to even collect.

This script re-derives, from the actual source, every top-level import that
isn't stdlib and isn't a local module -- and checks each one against what
requirements.txt + requirements-dev.txt actually declare. It is intentionally
static (ast-based, no imports executed) so it works even when the environment
is broken, which is exactly when you need it most.

Run directly: python scripts/check_dependencies_declared.py
Also exercised by tests/test_dependencies_declared.py in both suites.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories that hold source we care about. Exploratory one-off scripts
# (Tests/big_test*.py) are deliberately excluded from pytest collection by
# Tests/pytest.ini and are excluded here for the same reason: they're not
# part of what CI actually runs, so their imports (e.g. openai) don't need
# to be production dependencies.
SOURCE_DIRS = [
    REPO_ROOT / "Tellurium",
    REPO_ROOT / "Tests",
]

EXCLUDE_NAME_PREFIXES = ("big_test",)
EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".hypothesis", "node_modules", ".venv"}

# import-name -> pip-distribution-name, for the cases where they differ.
# This is exactly the kind of mapping that's easy to get subtly wrong, so
# every entry here is verified against what's actually installed.
IMPORT_TO_DISTRIBUTION = {
    "roadrunner": "libroadrunner",
    "libsbml": "python-libsbml",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
}


def _stdlib_names() -> set[str]:
    names = set(sys.stdlib_module_names) | set(sys.builtin_module_names)
    names.add("__future__")  # pseudo-module, not listed in stdlib_module_names
    return {n.lower() for n in names if not n.startswith("_") or n == "__future__"}


def _local_module_stems() -> set[str]:
    stems: set[str] = set()
    # scripts/ isn't scanned for imports (it's tooling, not product code or
    # tests) but its modules (e.g. check_dependencies_declared itself, used
    # by tests/test_dependencies_declared.py) are still local, not pip deps.
    for src_dir in [*SOURCE_DIRS, REPO_ROOT / "scripts"]:
        if not src_dir.exists():
            continue
        for path in src_dir.rglob("*.py"):
            if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
                continue
            stems.add(path.stem.lower())
    return stems


def _iter_source_files():
    for src_dir in SOURCE_DIRS:
        if not src_dir.exists():
            continue
        for path in src_dir.rglob("*.py"):
            if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
                continue
            if path.name.startswith(EXCLUDE_NAME_PREFIXES):
                continue
            yield path


def collect_third_party_imports() -> dict[str, list[str]]:
    """Map import root name -> list of files that import it."""
    stdlib = _stdlib_names()
    local = _local_module_stems()
    found: dict[str, list[str]] = {}

    for path in _iter_source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative import, definitely local
                if node.module:
                    roots = [node.module.split(".")[0]]

            for root in roots:
                key = root.lower()
                if key in stdlib or key in local:
                    continue
                found.setdefault(root, []).append(str(path.relative_to(REPO_ROOT)))

    return found


def declared_distributions() -> set[str]:
    declared: set[str] = set()
    for req_file in ("requirements.txt", "requirements-dev.txt"):
        req_path = REPO_ROOT / req_file
        if not req_path.exists():
            continue
        for line in req_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r"):
                continue
            name = line.split("==")[0].split(">=")[0].split("<")[0].strip()
            declared.add(name.lower().replace("_", "-"))
    return declared


def find_undeclared() -> dict[str, list[str]]:
    imports = collect_third_party_imports()
    declared = declared_distributions()

    undeclared: dict[str, list[str]] = {}
    for import_name, files in imports.items():
        dist_name = IMPORT_TO_DISTRIBUTION.get(import_name.lower(), import_name)
        normalized = dist_name.lower().replace("_", "-")
        if normalized not in declared:
            undeclared[import_name] = files
    return undeclared


def main() -> int:
    undeclared = find_undeclared()
    if not undeclared:
        print("OK: every third-party import is declared in requirements.txt "
              "or requirements-dev.txt.")
        return 0

    print("Undeclared dependencies found:\n")
    for import_name, files in sorted(undeclared.items()):
        print(f"  import {import_name}")
        for f in files[:3]:
            print(f"    used in {f}")
        if len(files) > 3:
            print(f"    ...and {len(files) - 3} more file(s)")
    print(
        "\nThese modules are imported somewhere in Tellurium/ or Tests/ but "
        "are not listed in requirements.txt or requirements-dev.txt. A fresh "
        "install (like CI does) will fail to collect the affected tests."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
