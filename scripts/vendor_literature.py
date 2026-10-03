#!/usr/bin/env python3
"""Copy the literature layer's import closure into caterva/_literature/.

WHY
---
The modules that read BRENDA and resolve a measured constant for a model live
in `Tests/` as flat modules. `caterva.checkout.literature_module` imports them
by name. `MANIFEST.in` prunes `Tests/` from the sdist, and the wheel is built
from the sdist, so before this script a wheel and the frozen app contained no
literature layer: `caterva compose --subject 2.7.1.1` printed that the search
could not run, and Studio reported its Constants and Binding screens
unavailable.

WHAT IT DOES
------------
1. Finds the roots: every module name Caterva itself asks for, read with
   `ast` from `literature_module("name")` calls and `from Tests.name import`
   statements in the non-test sources under `caterva/`.
2. Computes the import closure over `Tests/*.py`, again with `ast` (imports
   nested inside functions count). Test modules (`test_*.py`) and debug
   scripts are in the closure only if something reachable imports them,
   which is refused.
3. Adds the two repository scripts Studio's Constants screen runs in
   process (`scripts/cite.py` and `scripts/report_lab.py`, see
   caterva/studio/adapters/constants.py) and follows their imports into
   `Tests/` the same way.
4. Copies exactly those files, byte for byte, into `caterva/_literature/`,
   removes anything else there, and writes `README.txt` listing them.

The output is deterministic: sorted names, copied bytes, mode 0644, no
timestamps in anything it writes, so the wheel built from it is
byte-reproducible. The directory is git-ignored (a build product, like the
Studio page), and `check_no_generated_files_tracked` keeps it that way.

Fixtures are NOT copied. The BRENDA pages under `Tests/fixtures/` are third
party data under CC BY 4.0 and stay out of every release artifact; the
offline replay the frozen-app smoke test uses reads them from the checkout.

Usage:
    python3 scripts/vendor_literature.py            # write caterva/_literature/
    python3 scripts/vendor_literature.py --check    # exit 1 if it is missing or stale
    python3 scripts/vendor_literature.py --list     # print the closure
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "Tests"
PACKAGE = ROOT / "caterva"
TARGET = PACKAGE / "_literature"

README_NAME = "README.txt"

#: Subdirectories of caterva/ whose sources never ask for a literature module
#: in production (test code, and the directory this script writes).
SKIP_PARTS = ("tests", "_literature", "__pycache__")

#: Scripts the Studio's Constants screen imports by path; copied beside the
#: modules they import so the installed package and the app can run them.
SCRIPTS = ROOT / "scripts"
SCRIPT_ROOTS = ("cite", "report_lab")


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _py_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if not any(part in SKIP_PARTS for part in p.relative_to(directory).parts))


def tests_modules() -> set[str]:
    return {p.stem for p in TESTS.glob("*.py")}


def roots() -> list[str]:
    """Every literature module the package names, from its own non-test sources."""
    found: set[str] = set()
    for path in _py_files(PACKAGE):
        if path.name == "checkout.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if name == "literature_module" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.add(arg.value)
                    else:
                        raise SystemExit(
                            f"{_shown(path)}:{node.lineno}: literature_module() is called with a "
                            "name that is not a string literal, so the vendored closure cannot be computed"
                        )
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module == "Tests":
                    found.update(a.name for a in node.names)
                elif node.module.startswith("Tests."):
                    found.add(node.module.split(".")[1])
    return sorted(found)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "Tests":
                names.update(a.name for a in node.names)
            elif node.module.startswith("Tests."):
                names.add(node.module.split(".")[1])
            else:
                names.add(node.module.split(".")[0])
    return names


def closure(start: list[str] | None = None) -> list[str]:
    """The Tests/ modules reachable from `start` (default: roots() and what
    the vendored scripts import), sorted."""
    available = tests_modules()
    if start is None:
        pending = list(roots())
        for script in SCRIPT_ROOTS:
            pending.extend(m for m in _imports(SCRIPTS / f"{script}.py") if m in available)
    else:
        pending = list(start)
    missing = [m for m in pending if m not in available]
    if missing:
        raise SystemExit(f"Caterva asks for literature modules that Tests/ does not have: {missing}")
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for imported in _imports(TESTS / f"{name}.py"):
            if imported in available and imported not in seen:
                pending.append(imported)
    tests = sorted(m for m in seen if m.startswith("test_") or m.endswith("_test"))
    if tests:
        raise SystemExit(f"the literature closure reaches test modules, which must not ship: {tests}")
    return sorted(seen)


def expected_files() -> dict[str, bytes]:
    """Target file name -> bytes, for the closure plus the README."""
    modules = closure()
    files = {f"{m}.py": (TESTS / f"{m}.py").read_bytes() for m in modules}
    clash = [m for m in SCRIPT_ROOTS if f"{m}.py" in files]
    if clash:
        raise SystemExit(f"Tests/ has modules named like the vendored scripts: {clash}")
    for script in SCRIPT_ROOTS:
        files[f"{script}.py"] = (SCRIPTS / f"{script}.py").read_bytes()
    listing = "\n".join(f"  {name}" for name in sorted(files))
    files[README_NAME] = (
        "Caterva's literature layer, as the release build copies it.\n"
        "\n"
        "These files are copies of modules in the repository's Tests/ directory\n"
        "and of scripts/cite.py and scripts/report_lab.py, written by\n"
        "scripts/vendor_literature.py: the modules the package imports through\n"
        "caterva.checkout.literature_module, and the modules those import.\n"
        "Do not edit them here; the directory is generated and is not tracked.\n"
        "No fixture or recorded answer is copied: the literature layer fetches\n"
        "live from BRENDA, NCBI, UniProt and PubChem, and BRENDA's data is CC BY 4.0\n"
        "(see NOTICE).\n"
        "\n"
        "Files:\n"
        f"{listing}\n"
    ).encode("utf-8")
    return files


def problems() -> list[str]:
    """What differs between caterva/_literature/ and what the build would write."""
    want = expected_files()
    if not TARGET.is_dir():
        return [f"{_shown(TARGET)} does not exist"]
    have = {p.name: p for p in TARGET.iterdir() if p.is_file()}
    out = [f"stale file {n}" for n in sorted(set(have) - set(want))]
    out += [f"missing {n}" for n in sorted(set(want) - set(have))]
    out += [f"{n} differs from its source" for n in sorted(set(want) & set(have)) if have[n].read_bytes() != want[n]]
    return out


def vendor() -> list[str]:
    """Write caterva/_literature/ and return the module names written."""
    want = expected_files()
    TARGET.mkdir(exist_ok=True)
    for path in TARGET.iterdir():
        if path.is_dir():
            if path.name == "__pycache__":
                import shutil

                shutil.rmtree(path)
            continue
        if path.name not in want:
            path.unlink()
    for name in sorted(want):
        dest = TARGET / name
        dest.write_bytes(want[name])
        os.chmod(dest, 0o644)
    return sorted(n[:-3] for n in want if n.endswith(".py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if caterva/_literature/ is missing or stale")
    parser.add_argument("--list", action="store_true", help="print the closure and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(closure()))
        return 0
    if args.check:
        found = problems()
        for line in found:
            print(f"  - {line}", file=sys.stderr)
        return 1 if found else 0
    names = vendor()
    print(f"vendored {len(names)} literature modules into {_shown(TARGET)}/: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
