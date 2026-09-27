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
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories that hold source we care about. Exploratory scripts
# (Tests/big_test*.py) are excluded from pytest collection via
# Tests/pytest.ini. They are also excluded from this check because they
# are not CI dependencies. Their imports are not required to be in
# production dependencies.
SOURCE_DIRS = [
    REPO_ROOT / "caterva",
    REPO_ROOT / "Tests",
]

# api-server's science-agent bridge is Python product code that Tests/
# imports directly (Tests/test_runner_contract.py, Stage 5 Part 4) but that
# lives outside SOURCE_DIRS. Like scripts/, it's local code — its imports
# are stdlib-only — so its stems belong in the local set, not in
# requirements. If it ever grows third-party imports, those must be
# declared; this listing only covers its module names.
API_SERVER_LIB = (
    REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
)

EXCLUDE_NAME_PREFIXES = ("big_test",)
EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".hypothesis", "node_modules", ".venv"}

# import-name -> pip-distribution-name, for the cases where they differ.
# This is exactly the kind of mapping that's easy to get subtly wrong, so
# every entry here is verified against what's actually installed.
IMPORT_TO_DISTRIBUTION = {
    "roadrunner": "libroadrunner",
    "libsbml": "python-libsbml",
    # Same shape: the distribution is `python-libsedml`, the module is
    # `libsedml`. Without this the guard reports a declared dependency as
    # undeclared, which is a false accusation and trains people to ignore it.
    "libsedml": "python-libsedml",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
}


def _stdlib_names() -> set[str]:
    # sys.stdlib_module_names was added in Python 3.10.
    if hasattr(sys, "stdlib_module_names"):
        names = set(sys.stdlib_module_names)
    else:
        # Fallback for Python 3.9: discover stdlib modules by walking
        # the stdlib directory and checking builtins.
        names = set()
        # Builtins are always available.
        names.update(sys.builtin_module_names)
        # Walk the stdlib package directory to discover pure-Python modules.
        stdlib_path = os.path.dirname(os.__file__)
        if stdlib_path:
            for entry in pathlib.Path(stdlib_path).iterdir():
                if entry.is_file() and entry.suffix == ".py":
                    names.add(entry.stem)
                elif entry.is_dir() and (entry / "__init__.py").exists():
                    names.add(entry.name)
        # Also discover C extension modules (like math, cmath, etc.) by
        # checking common known stdlib modules that aren't in the directory.
        # This is a pragmatic list of modules that are part of the stdlib
        # but implemented in C and not discoverable by directory walking.
        known_stdlib_c_extensions = {
            "math", "cmath", "_math", "_cmath", "_socket", "_ssl",
            "_hashlib", "_hmac", "_sha1", "_sha256", "_sha512",
            "_md5", "_blake2", "_crypt", "_dbm", "_gdbm", "_sqlite3",
            "_decimal", "_elementtree", "_csv", "_json", "_pickle",
            "_struct", "_multibytecodec", "_codecs_cn", "_codecs_hk",
            "_codecs_jp", "_codecs_kr", "_codecs_tw", "_tkinter",
            "_curses", "_curses_panel", "_bz2", "_lzma", "zlib",
            "_queue", "_heapq", "_bisect", "_random", "_statistics",
            "_datetime", "_zoneinfo", "_sha3", "_keccak",
        }
        names.update(known_stdlib_c_extensions)
    names.add("__future__")  # pseudo-module, not listed in stdlib_module_names
    return {n.lower() for n in names if not n.startswith("_") or n == "__future__"}


def _local_module_stems() -> set[str]:
    stems: set[str] = set()
    # scripts/ isn't scanned for imports (it's tooling, not product code or
    # tests) but its modules (e.g. check_dependencies_declared itself, used
    # by tests/test_dependencies_declared.py) are still local, not pip deps.
    for src_dir in [*SOURCE_DIRS, REPO_ROOT / "scripts", API_SERVER_LIB]:
        if not src_dir.exists():
            continue
        # The directory itself is a local package root when something
        # imports it by name (e.g. `from caterva.caterva_engine import
        # ...`, used by caterva/cli.py when run as `python -m
        # caterva.cli` from the repo root) -- not just its file stems.
        stems.add(src_dir.name.lower())
        for path in src_dir.rglob("*.py"):
            if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
                continue
            stems.add(path.stem.lower())
            # Any directory holding an __init__.py is an importable package,
            # at any depth. After the engine was split into subpackages
            # (core/, continuous/, discrete/, scenarios/) a bare
            # `from continuous.simulations import ...` looked like a
            # third-party import to this guard purely because only the top
            # source directory was registered. Register every package
            # directory instead -- the same blind spot as the package-level
            # import fixed in Stage 4 Part 1, one level deeper.
            if path.name == "__init__.py":
                stems.add(path.parent.name.lower())
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
    # Every requirements file in the repository root, not a fixed pair.
    #
    # `requirements-popgen.txt` was added when stdpopsim was split out on
    # licence grounds (GPL-3.0-or-later against Caterva's Apache-2.0). It is
    # a real declaration -- it names the package, pins it, and explains the
    # obligation -- but this guard only read two filenames, so it reported a
    # DECLARED dependency as undeclared for two days.
    #
    # A false accusation is worse than a missed one: it trains people to
    # ignore the guard, and this one sits in `make guards`. Globbing means
    # the next optional-extras file is covered on the day it is created
    # rather than on the day someone remembers this list exists.
    for req_path in sorted(REPO_ROOT.glob("requirements*.txt")):
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
        print("OK: every third-party import is declared in a requirements file.")
        return 0

    print("Undeclared dependencies found:\n")
    for import_name, files in sorted(undeclared.items()):
        print(f"  import {import_name}")
        for f in files[:3]:
            print(f"    used in {f}")
        if len(files) > 3:
            print(f"    ...and {len(files) - 3} more file(s)")
    print(
        "\nThese modules are imported somewhere in caterva/ or Tests/ but "
        "are not listed in any requirements*.txt file. A fresh "
        "install (like CI does) will fail to collect the affected tests."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
