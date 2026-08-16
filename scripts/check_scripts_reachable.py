#!/usr/bin/env python3
"""Every runner script under scripts/ must be reachable from something.

WHY THIS EXISTS
---------------
The same failure has now happened four times in this repository:

  1. `/api/perf` and `/api/cache/stats` were documented in eighteen places
     and never registered as routes.
  2. `reliabilityScore.ts` computed three axes that nothing displayed.
  3. `export_annotated_model.py` and `citation_export.py` were built,
     tested, and callable from nowhere.
  4. `writeExports()` was written into the CLI and, for one commit, never
     called by it.

Each time the tests passed. Each time the repository could point at a module
and claim the capability. A feature nobody can invoke does not exist, and
having the code is worse than not having it, because the code is evidence
for a claim that is false.

WHAT IT CHECKS
--------------
Every `scripts/*.py` that reads stdin or takes argv -- i.e. is a RUNNER
rather than a CI guard -- must be named somewhere outside its own file and
its own tests. Being spawned by name is what makes it reachable.

Guards (files named `check_*.py`) are exempt: they are invoked by CI and by
humans, and requiring each to be named in application code would be the
wrong direction entirely.

PART TWO: DEAD PUBLIC FUNCTIONS
-------------------------------
The first version of this file said, in this docstring, that it could not
catch an unreachable FUNCTION inside a reachable file. That caveat was
tested against the code written immediately after it, and found three:

  * `iter_citations` -- zero mentions anywhere, including its own tests.
    Deleted; it was speculative when written.
  * `strenda_completeness` -- the aggregate STRENDA counter, called only by
    its own test.
  * `read_bytes` -- the BRENDA download decoder, called only by its own
    test.

The last two are now reachable through `scripts/brenda_corpus_stats.py`,
and making them reachable immediately exposed a real bug: `read_bytes`
assumed Latin-1 unconditionally, so a UTF-8 file decoded into mojibake and
every temperature vanished. The statistics reported "0 rows report both pH
and temperature" for a file where six of eleven do. Two passes of unit
tests had not found it, because they fed the decoder bytes rather than
files.

That is the argument for this check in one paragraph: dead code is not
merely unused, it is UNEXERCISED, and unexercised code is where confidently
wrong numbers live.

So `LIBRARY_MODULES` below are scanned for public functions that no
non-test file calls. The list is explicit rather than automatic: a
whole-repo scan would drown in framework entry points, re-exports and
dynamic dispatch, and a guard with false positives is worse than none.

`# reachable: <reason>` on the line above a definition opts it out, and the
reason is required -- an opt-out with no stated reason is how a list of
exceptions becomes a list of everything.

STILL NOT CHECKED
-----------------
A function called only from other dead code. Reachability here is one hop,
not transitive. Stated rather than glossed.

Exit 0 = every runner is spawned and every listed public function is
called. Exit 1 = something is orphaned.
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

#: A file is a RUNNER if it reads a payload or takes arguments. A file that
#: does neither is a library or a guard.
_RUNNER_MARKERS = (
    "sys.stdin.read()",
    "sys.argv",
    "argparse",
)

#: Guards are invoked by CI and by hand. Requiring application code to name
#: them would invert the dependency this project wants.
_GUARD_PREFIX = "check_"

#: Where a spawn could plausibly be written from.
_SEARCH_SUFFIXES = {".ts", ".js", ".mjs", ".py", ".yml", ".yaml", ".json", ".md", ".sh"}
_SEARCH_NAMES = {"Makefile"}


#: Directories never worth walking.
_SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__",
    ".pytest_cache", ".mypy_cache", "coverage", ".next",
}


def _candidate_files() -> list[pathlib.Path]:
    """Every file a spawn could be written in — tracked AND untracked.

    Two wrong versions preceded this one, and both were the same kind of
    mistake this project keeps finding:

      1. `git ls-files` only. Reported "1 runner script" while two brand-new
         unreachable runners sat on disk, because they were untracked. A
         freshly written orphan is untracked BY DEFINITION at the moment it
         is written, so a guard that only sees committed files is blind in
         exactly the window where it is needed.

      2. `Path.rglob("*")` with a skip-list. `rglob` descends into a
         directory before anything can skip it, so it walked all of
         node_modules and took over three minutes before being killed. A
         guard nobody waits for is a guard nobody runs.

    `git ls-files` plus `--others --exclude-standard` gives tracked files
    AND untracked-but-not-ignored ones, in one fast call, honouring
    .gitignore rather than a hand-maintained skip list that would drift.
    """
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
            if path.suffix in _SEARCH_SUFFIXES or path.name in _SEARCH_NAMES:
                seen[line] = path
    return list(seen.values())


def is_runner(path: pathlib.Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(marker in text for marker in _RUNNER_MARKERS)


def _runner_scripts() -> list[pathlib.Path]:
    return [
        path
        for path in sorted(SCRIPTS.glob("*.py"))
        if not path.name.startswith(_GUARD_PREFIX) and is_runner(path)
    ]


def _is_own_test(path: pathlib.Path) -> bool:
    # A test proving a script works does not make it reachable. That is
    # exactly how three of the four orphans passed CI.
    return "test" in path.name.lower() or "__tests__" in str(path)


#: Modules whose public functions must be called by something.
#:
#: Explicit, because a whole-repo scan drowns in framework entry points and
#: dynamic dispatch, and a guard with false positives is worse than none.
#: These are plain libraries: every public function in them is meant to be
#: called by name from application code.
LIBRARY_MODULES = (
    "Tests/brenda_bulk.py",
    "Tests/citation_export.py",
    "Tests/reliability.py",
    "Tests/taxonomy.py",
    "Terium/core/model_provenance.py",
)

#: Opt-out marker. The reason is mandatory.
_REACHABLE_MARKER = "# reachable:"


def _public_functions(path: pathlib.Path) -> list[tuple[str, int]]:
    """(name, line) for each public top-level def, minus opted-out ones."""
    found: list[tuple[str, int]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("def "):
            continue
        name = line[4:].split("(")[0].strip()
        if name.startswith("_"):
            continue
        previous = lines[index - 1].strip() if index > 0 else ""
        if previous.startswith(_REACHABLE_MARKER):
            reason = previous[len(_REACHABLE_MARKER):].strip()
            if reason:
                continue
            # A marker with no reason does not count. An opt-out nobody has
            # to justify is how a list of exceptions becomes a list of
            # everything.
        found.append((name, index + 1))
    return found


def _referenced_names(source: str, *, defining: str) -> set[str]:
    """Names referenced in Python source OUTSIDE the given function's body.

    Comments and docstrings are not code and do not count -- a text scan
    counted a function's mention in its own module docstring as a call.

    `defining` is excluded by SKIPPING THAT FUNCTION'S SUBTREE, not by
    discarding the name from the result. Discarding the name was the
    obvious-looking version and it was wrong: `to_bibtex` calls
    `bibtex_key`, and discarding "bibtex_key" threw that call away along
    with the self-reference, so a live function was reported dead. Two
    sibling functions calling each other is the normal case, not the edge.

    What the subtree skip still misses is a function whose only caller is
    itself. Stated rather than glossed.

    Falls back to an empty set on a syntax error rather than to "everything
    is referenced": a module that will not parse should make the guard
    louder, not quieter.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    referenced: set[str] = set()

    # A manual stack, NOT ast.walk. `ast.walk` yields every node and a
    # `continue` in that loop skips one node, not its subtree -- so the
    # first version of this claimed to exclude the defining function's body
    # and did not. A comment that misdescribes the code it sits on is worse
    # than no comment, and this file exists to catch exactly that kind of
    # gap between claim and behaviour.
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == defining
        ):
            # Do not descend. A function that only calls itself is not
            # reachable, and counting its own recursion would hide that.
            continue
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        stack.extend(ast.iter_child_nodes(node))
    return referenced


def _dead_functions(corpus: list[tuple[pathlib.Path, str]]) -> list[tuple[str, str, int]]:
    """Public functions in LIBRARY_MODULES that nothing references.

    TWO FALSE-POSITIVE CLASSES WERE FOUND BY RUNNING THIS, AND BOTH ARE
    FIXED HERE. The first version flagged seven functions, five of which
    were perfectly reachable:

      1. MATCHING `name(` MISSED REFERENCES WITHOUT A CALL.
         `export_citations.py` holds `FORMATS = {"bibtex": to_bibtex}` --
         the function is passed as a value and invoked through the dict, so
         the literal text `to_bibtex(` never appears anywhere. Matching on
         the bare name as a word catches both forms.

      2. INTRA-MODULE CALLERS WERE EXCLUDED.
         `score_reliability` calls `grade_assay_completeness` in the same
         file, and `assess_relatedness` calls
         `deepest_shared_ranked_node`. Those functions ARE exercised --
         through a public entry point whose own reachability is what the
         runner check covers. Excluding the defining module asked the wrong
         question.

    Both mistakes had the same shape as the ones this file exists to catch:
    a check reporting on less of the world than it appeared to. It is worth
    recording that the guard against confidently wrong answers had to be
    corrected for giving one.

    The three original orphans are still caught, which is the test that
    matters: `iter_citations` had zero mentions anywhere, and
    `strenda_completeness` and `read_bytes` had no caller inside their own
    module either.
    """
    dead: list[tuple[str, str, int]] = []
    for relative in LIBRARY_MODULES:
        module = REPO / relative
        if not module.is_file():
            dead.append((relative, "MODULE MISSING", 0))
            continue

        own_text = module.read_text(encoding="utf-8", errors="replace")

        for name, line in _public_functions(module):
            pattern = re.compile(rf"\b{re.escape(name)}\b")

            # Inside its own module the check is AST-based, not textual.
            #
            # A text scan counted a mention in the module's OWN DOCSTRING as
            # a call. `strenda_completeness` is named in brenda_bulk.py's
            # header prose, so deleting its only real caller changed
            # nothing and the guard stayed green -- a check passing on the
            # strength of a sentence about the code rather than the code.
            #
            # Found by mutation: removing the caller should have failed and
            # did not. Text matching is retained for the cross-module pass,
            # where the corpus spans several languages and JSON, and where a
            # prose-only mention in a DIFFERENT file is at least a sign
            # somebody knows the function exists.
            if name in _referenced_names(own_text, defining=name):
                continue

            if any(
                path != module and pattern.search(text) for path, text in corpus
            ):
                continue

            dead.append((relative, name, line))
    return dead


def main() -> int:
    runners = _runner_scripts()
    if not runners:
        print(
            "No runner scripts found under scripts/. Either the detection is "
            "wrong or they were removed; refusing to report success on an "
            "empty set."
        )
        return 1

    # One walk, one read of each candidate, reused for every runner.
    corpus: list[tuple[pathlib.Path, str]] = []
    for path in _candidate_files():
        if _is_own_test(path):
            continue
        try:
            corpus.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    orphans: list[tuple[str, str]] = []
    reachable: list[tuple[str, int]] = []

    for path in runners:
        callers = [
            other for other, text in corpus
            if other.name != path.name and path.name in text
        ]
        if callers:
            reachable.append((path.name, len(callers)))
        else:
            orphans.append(
                (
                    path.name,
                    "no non-test file names this script, so nothing can spawn it",
                )
            )

    print(
        f"Checked {len(runners)} runner script(s) under scripts/ against "
        f"{len(corpus)} candidate caller file(s)."
    )
    for name, count in sorted(reachable):
        print(f"  {name}: named by {count} file(s)")

    dead = _dead_functions(corpus)
    if dead:
        print()
        print(f"Public function(s) nothing calls ({len(dead)}):")
        for module, name, line in dead:
            print(f"  - {module}:{line} {name}()")
        print()
        print(
            "Dead code is not merely unused, it is UNEXERCISED, and "
            "unexercised code is where confidently wrong numbers live. Wire "
            "it to a caller, delete it, or mark it "
            "`# reachable: <why>` with a real reason."
        )

    if orphans:
        print()
        print(f"Unreachable runner script(s) ({len(orphans)}):")
        for name, reason in orphans:
            print(f"  - {name}: {reason}")
        print()
        print(
            "A feature nobody can invoke does not exist. Wire it to a caller, "
            "or delete it -- code that exists and cannot run is evidence for "
            "a capability the project does not have."
        )
        return 1

    if dead:
        return 1

    print(
        f"OK: every runner script under scripts/ is named by something that "
        f"can spawn it, and every public function in "
        f"{len(LIBRARY_MODULES)} library module(s) is called."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
