#!/usr/bin/env python3
"""Every constraint a critic can raise must be honoured by some agent.

THE FAILURE THIS CATCHES
------------------------
`Terium/agents` iterates: a critic finds a problem, emits a `Constraint`,
and the scouts search again inside it. That only works while every kind of
constraint a critic can emit is a kind some agent actually reads.

Add a `Constraint(kind="ph_window", ...)` to a critic and nothing breaks
loudly. The store records it, the fingerprint changes, every agent re-runs,
the scouts search exactly as before because none of them looks at
`ph_window`, the critic finds the same problem and -- because the store
deduplicates -- emits nothing new, and the run converges. The report then
says a requirement was discovered and the model was built under it. Both
halves are false: nothing searched for it and nothing satisfied it.

That is the worst shape a bug can have here. It produces a confident,
well-formatted, entirely unearned claim, and no test fails.

`critics.py` documents which findings become constraints and which stay
findings precisely because of this. The docstring is the argument; this is
the enforcement.

WHAT IT DOES
------------
Reads the AST of every module under `Terium/agents`, collecting:

  emitted   -- literal `kind=` on a `Constraint(...)` construction
  honoured  -- literal arguments to `constraints_of_kind(...)`, and literal
               comparisons against a `.kind` attribute

and fails when `emitted - honoured` is non-empty.

Constant folding is deliberately not attempted. A `kind` built at runtime
would defeat this check, so a non-literal `kind=` is itself a failure: the
vocabulary is small, closed, and has no reason to be computed.
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import Dict, List, Set, Tuple

AGENTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "Terium" / "agents"

#: Kinds that are deliberately raised without any agent acting on them --
#: none today. An entry here needs a reason, because the whole point of the
#: check is that such a constraint makes the report claim something untrue.
ALLOWED_UNACTIONED: Dict[str, str] = {}


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan(tree: ast.AST, filename: str) -> Tuple[Set[str], Set[str], List[str]]:
    emitted: Set[str] = set()
    honoured: Set[str] = set()
    problems: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)

            if name == "Constraint":
                found = False
                for keyword in node.keywords:
                    if keyword.arg != "kind":
                        continue
                    found = True
                    literal = _literal(keyword.value)
                    if literal is None:
                        problems.append(
                            f"{filename}:{node.lineno}: Constraint(kind=...) "
                            f"is computed rather than a literal string. The "
                            f"vocabulary is closed and small; a computed "
                            f"kind cannot be checked against what any agent "
                            f"honours."
                        )
                    else:
                        emitted.add(literal)
                if not found and node.args:
                    literal = _literal(node.args[0])
                    if literal is not None:
                        emitted.add(literal)
                    else:
                        problems.append(
                            f"{filename}:{node.lineno}: Constraint's first "
                            f"positional argument is not a literal kind."
                        )

            if name == "constraints_of_kind":
                for argument in node.args:
                    literal = _literal(argument)
                    if literal is not None:
                        honoured.add(literal)

        # `constraint.kind == "organism"` and its reverse.
        if isinstance(node, ast.Compare) and len(node.comparators) == 1:
            left, right = node.left, node.comparators[0]
            if isinstance(left, ast.Attribute) and left.attr == "kind":
                literal = _literal(right)
                if literal is not None:
                    honoured.add(literal)
            if isinstance(right, ast.Attribute) and right.attr == "kind":
                literal = _literal(left)
                if literal is not None:
                    honoured.add(literal)

    return emitted, honoured, problems


def check(paths) -> Tuple[List[str], Set[str], Set[str]]:
    emitted: Set[str] = set()
    honoured: Set[str] = set()
    problems: List[str] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(), filename=str(path))
        e, h, p = scan(tree, path.name)
        emitted |= e
        honoured |= h
        problems += p

    unactioned = emitted - honoured - set(ALLOWED_UNACTIONED)
    for kind in sorted(unactioned):
        problems.append(
            f"constraint kind {kind!r} is raised but no agent reads it. The "
            f"run would iterate once, change nothing, converge, and report "
            f"that it searched under a requirement it never applied. Either "
            f"make an agent honour it (read it via constraints_of_kind or "
            f"compare against .kind), or leave the finding as a note instead "
            f"of a constraint -- see the 'WHEN A FINDING BECOMES A "
            f"CONSTRAINT' section of Terium/agents/critics.py."
        )
    return problems, emitted, honoured


def selftest() -> int:
    """Plant each violation and confirm it is caught.

    A guard nobody has seen fail is a guard nobody knows works.
    """
    import tempfile

    cases = [
        (
            "an unactioned constraint kind",
            'from x import Constraint\nConstraint(kind="ph_window", subject="*", requirement="7")\n',
            "no agent reads it",
        ),
        (
            "a computed constraint kind",
            'from x import Constraint\nk = "org" + "anism"\nConstraint(kind=k, subject="*", requirement="a")\n',
            "computed rather than a literal",
        ),
        (
            "a positional non-literal kind",
            'from x import Constraint\nConstraint(k, "*", "a")\n',
            "not a literal kind",
        ),
    ]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for label, source, expected in cases:
            path = root / "planted.py"
            path.write_text(source)
            problems, _, _ = check([path])
            if not any(expected in p for p in problems):
                print(f"selftest FAIL: {label} was not caught. Got: {problems}")
                failures += 1

        # And the clean case must pass, or the check fires on everything.
        path = root / "clean.py"
        path.write_text(
            'from x import Constraint\n'
            'Constraint(kind="organism", subject="*", requirement="a")\n'
            'def f(view):\n    return view.constraints_of_kind("organism")\n'
        )
        problems, _, _ = check([path])
        if problems:
            print(f"selftest FAIL: the clean case was flagged: {problems}")
            failures += 1

    if failures:
        return 1
    print(f"selftest OK: {len(cases)} planted violations caught, clean case passed")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

    if not AGENTS_DIR.is_dir():
        print(f"FAIL: {AGENTS_DIR} does not exist")
        return 1

    paths = [p for p in AGENTS_DIR.glob("*.py") if p.name != "__init__.py"]
    if not paths:
        print(f"FAIL: no agent modules found under {AGENTS_DIR}")
        return 1

    problems, emitted, honoured = check(paths)
    if problems:
        print("FAIL: constraints that nothing acts on")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"OK: {len(emitted)} constraint kind(s) raised "
        f"({', '.join(sorted(emitted)) or 'none'}), all honoured by an agent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
