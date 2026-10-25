#!/usr/bin/env python3
"""The checker in caterva/check/ imports the standard library and nothing else.

WHY THIS EXISTS
---------------
`caterva verify` (ADR 0179) re-derives every claim id, re-reads every
certified span and re-finds every cited row from the bytes a bundle kept.
Its value is that it is a second program: a test that constructs the state
it means to verify can only confirm the code's mistakes back to it (ADR
0178 said so of its own tests), and a checker that imported the producer's
canonical JSON, its digests or its row parser would be the producer
checking itself. So the checker repeats those definitions from the spec
rather than importing them, and this guard is what keeps the next edit from
quietly undoing that with a `from caterva.evidence.canonical import digest`
-- a one-line change that would leave every test green and the whole claim
false (ADR 0015: a rule nothing executes is not enforced).

WHAT IT CHECKS
--------------
Every `*.py` under caterva/check/, by AST, every `import` and `from ...
import` statement:

  * an absolute import must name a module in `sys.stdlib_module_names`
    (the interpreter's own list, so no hand-kept allow-list rots);
  * nothing may name `caterva`, `Tests`, `bs4`, `pydantic` or `numpy`, in
    any position of the dotted name -- `caterva` is the producer, `Tests`
    is the literature layer whose parser produced the rows, and the other
    three are what the producer is built on;
  * a relative import may reach a sibling module in the package (`from
    .verify import ...`) and nothing above it: `from ..evidence import x`
    is `caterva.evidence` under another name;
  * `importlib` and `__import__` are refused outright, because a dynamic
    import can name producer code the AST does not show.

An empty package, or one with no imports at all, is not a pass: a scan
that found nothing to check has checked nothing.

Usage:
    python scripts/check_checker_independence.py             # exit 1 on a hit
    python scripts/check_checker_independence.py --selftest  # prove it matches
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_DIR = ROOT / "caterva" / "check"

#: Names refused in any position of a dotted import, and why.
FORBIDDEN: dict[str, str] = {
    "caterva": "the producer: the checker would be the producer checking itself",
    "Tests": "the literature layer, whose parser produced the rows the checker re-finds",
    "bs4": "the producer's HTML parser; the checker re-finds rows by regular expression",
    "pydantic": "the literature layer's record types",
    "numpy": "the engine's arithmetic; the checker uses Decimal",
}

#: Modules refused by name because they import at run time, out of the AST's sight.
DYNAMIC: tuple[str, ...] = ("importlib", "__import__")


def _modules(package_dir: Path) -> list[Path]:
    return sorted(p for p in package_dir.rglob("*.py") if "__pycache__" not in p.parts)


def _dotted_parts(name: str) -> list[str]:
    return [part for part in name.split(".") if part]


def _absolute_problem(name: str) -> str | None:
    """Why an absolute import of `name` is refused, or None when it is standard library."""
    parts = _dotted_parts(name)
    if not parts:
        return "an empty module name"
    for part in parts:
        if part in FORBIDDEN:
            return f"names {part!r} ({FORBIDDEN[part]})"
    if parts[0] in DYNAMIC:
        return f"{parts[0]!r} imports at run time, out of the AST's sight"
    if parts[0] not in sys.stdlib_module_names:
        return f"{parts[0]!r} is not in the standard library (sys.stdlib_module_names)"
    return None


def _relative_problem(node: ast.ImportFrom, package_dir: Path) -> str | None:
    if node.level >= 2:
        return f"a relative import of level {node.level} leaves the package"
    targets = _dotted_parts(node.module or "")
    if targets:
        head = targets[0]
        if not ((package_dir / f"{head}.py").is_file() or (package_dir / head).is_dir()):
            return f"'.{node.module}' is not a module of the package"
        return None
    # `from . import x, y`: each name must be a sibling module.
    for alias in node.names:
        if not ((package_dir / f"{alias.name}.py").is_file() or (package_dir / alias.name).is_dir()):
            return f"'from . import {alias.name}' names no module of the package"
    return None


def imports_in(tree: ast.AST) -> list[tuple[int, ast.Import | ast.ImportFrom]]:
    return [
        (node.lineno, node) for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def findings(package_dir: Path = CHECK_DIR) -> list[str]:
    """`path:line: <import> -- why` for every import the checker may not have."""
    problems: list[str] = []
    for path in _modules(package_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            problems.append(f"{path}: does not parse: {exc}")
            continue
        rel = path.relative_to(package_dir.parent) if package_dir.parent in path.parents else path
        for lineno, node in imports_in(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    why = _absolute_problem(alias.name)
                    if why:
                        problems.append(f"{rel}:{lineno}: import {alias.name} -- {why}")
            elif node.level:
                why = _relative_problem(node, package_dir)
                if why:
                    problems.append(f"{rel}:{lineno}: from {'.' * node.level}{node.module or ''} import ... -- {why}")
            else:
                why = _absolute_problem(node.module or "")
                if why:
                    problems.append(f"{rel}:{lineno}: from {node.module} import ... -- {why}")
    return problems


def scanned(package_dir: Path = CHECK_DIR) -> tuple[int, int]:
    """(modules, import statements) the scan covered: a premise the verdict rests on."""
    modules = _modules(package_dir)
    statements = 0
    for path in modules:
        try:
            statements += len(imports_in(ast.parse(path.read_text(encoding="utf-8"))))
        except SyntaxError:
            continue
    return len(modules), statements


def selftest() -> int:
    """Plant each kind of bad import and confirm it is caught; confirm a clean package passes.

    A guard nobody has seen fail is a guard nobody knows works.
    """
    planted = {
        "bad_numpy.py": ("import numpy as np\n", "numpy"),
        "bad_caterva.py": ("from caterva.evidence.canonical import digest\n", "caterva"),
        "bad_tests.py": ("import Tests.brenda_client\n", "Tests"),
        "bad_third_party.py": ("import httpx\n", "not in the standard library"),
        "bad_parent.py": ("from ..evidence import claims\n", "leaves the package"),
        "bad_dynamic.py": ("import importlib\n", "run time"),
        "bad_sibling.py": ("from .nowhere import x\n", "not a module of the package"),
    }
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "check"
        package.mkdir()
        (package / "__init__.py").write_text('"""clean"""\n', encoding="utf-8")
        (package / "helper.py").write_text("import json\nimport re\n", encoding="utf-8")
        (package / "good.py").write_text(
            "from __future__ import annotations\nimport gzip, hashlib\nfrom decimal import Decimal\n"
            "from .helper import *\nfrom . import helper\n",
            encoding="utf-8",
        )
        clean = findings(package)
        if clean:
            print(f"selftest FAILED: a clean package was refused: {clean}")
            return 1
        for name, (text, expected) in planted.items():
            (package / name).write_text(text, encoding="utf-8")
            found = [p for p in findings(package) if p.startswith(f"check/{name}:")]
            (package / name).unlink()
            if len(found) != 1 or expected not in found[0]:
                print(f"selftest FAILED: {name} should give one finding mentioning {expected!r}, got {found}")
                return 1
        empty = Path(tmp) / "empty"
        empty.mkdir()
        if scanned(empty) != (0, 0):
            print("selftest FAILED: an empty directory should scan as nothing")
            return 1
    print(
        f"selftest ok: {len(planted)} kinds of forbidden import are each caught, a clean "
        "package with sibling-relative imports passes, and an empty scan counts as nothing"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--selftest" in args:
        return selftest()
    if not CHECK_DIR.is_dir():
        print(f"FAIL: {CHECK_DIR} is missing; there is no checker to hold independent")
        return 1
    modules, statements = scanned()
    if modules == 0 or statements == 0:
        print(f"FAIL: {CHECK_DIR} holds {modules} module(s) with {statements} import(s); nothing was checked")
        return 1
    problems = findings()
    if problems:
        print(f"FAIL: {len(problems)} import(s) would make the checker share code with what it checks:")
        for line in problems:
            print(f"  {line}")
        print(
            "The checker re-implements canonical JSON, the digests and the row search from "
            "their definitions (ADR 0179). Repeat the definition; do not import it."
        )
        return 1
    print(
        f"ok: {modules} module(s) under caterva/check with {statements} import statement(s), "
        "every one standard library or a sibling in the package"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
