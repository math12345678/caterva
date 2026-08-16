#!/usr/bin/env python3
"""
check_thrown_values_are_errors.py

Fail the build when TypeScript code throws an object literal instead of an
Error.

WHY THIS GUARD EXISTS
---------------------
`ScientificPipeline.execute` signalled failure like this:

    throw {
      jobId,
      error: 'SIMULATION_ERROR',
      message: error instanceof Error ? error.message : 'Unknown error',
      executionTimeMs: Date.now() - startTime
    };

Note the care over `message`: the real cause is extracted and preserved.

Every consumer then read it with the standard idiom --

    error instanceof Error ? error.message : String(error)

-- and a plain object is not an Error, so `String(obj)` ran instead and
produced the literal string **"[object Object]"**.

That string reached the `error` field of `GET /api/jobs/:jobId`, the
`errorMessage` in metrics, the `error` column of the batch and comparison
CSV exports, and the CLI. A student whose run failed because a Km could not
be resolved -- the most common and most actionable failure this project has
-- was told `[object Object]`.

WHY A GUARD RATHER THAN A TEST
------------------------------
Three properties of this defect together make it a build-check rather than a
unit test:

1. **TypeScript permits it.** `throw` accepts `any`. Reintroducing the
   object throw compiles with zero errors -- verified by mutation.
2. **The readers were hardened too** (`describeError` in src/errors.ts
   recovers a message from a non-Error). That is deliberate defence in
   depth, and it means a mutation reverting the throw changes no observable
   behaviour, so no test can fail on it. A fix protected by a second fix is
   untestable at its own level -- the ADR 0058 M1 situation.
3. **It is a whole-codebase property**, not a property of one function. The
   next `throw { message }` will be written by somebody who has not read
   src/errors.ts, in a file that does not exist yet.

So the rule is enforced where it lives: over the source.

WHAT IT ALLOWS
--------------
- `throw new Error(...)`, `throw new SimulationError(...)`, any `new X(...)`
- `throw err` / `throw error` -- rethrowing something already caught
- `throw someFactory()` -- a function returning an Error
- Object literals in .test.ts files, which deliberately reproduce the legacy
  shape to prove `describeError` recovers from it. Excluding tests is not a
  loophole: those files ASSERT the bad shape is handled, so forbidding it
  there would delete the regression test for the thing this guard protects.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories holding first-party TypeScript.
SEARCH_ROOTS = [
    REPO_ROOT / "src",
    REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src",
]

SKIP_DIR_NAMES = {"node_modules", "dist", "build", ".git", "coverage"}

#: `throw` followed by `{` -- an object literal. Whitespace and newlines
#: between them are allowed because the original defect was written across
#: five lines, and a pattern that only matched `throw {` on one line would
#: have missed the very case that motivated this file.
THROW_OBJECT_RE = re.compile(r"\bthrow\s*\{")

#: A test file may reproduce the legacy shape on purpose.
TEST_SUFFIXES = (".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")


def is_test_file(path: Path) -> bool:
    if path.name.endswith(TEST_SUFFIXES):
        return True
    return "__tests__" in path.parts


def typescript_files() -> list[Path]:
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.ts"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name.endswith(".d.ts"):
                continue
            found.append(path)
    return sorted(found)


def line_number_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def blank_comments(text: str) -> str:
    """
    Replace comment content with spaces, preserving line and column offsets.

    The first version of this guard scanned raw source and reported two
    violations in `src/errors.ts` -- both inside the docstring that QUOTES
    the offending pattern in order to explain it. A guard that fires on the
    prose describing a defect punishes the documentation of that defect, and
    the cheapest way to make it green is to delete the explanation.

    Offsets are preserved rather than the comments being deleted, so the
    line numbers in any real violation still point at the right line.

    Only block comments and whole-line `//` comments are blanked. A trailing
    `//` after code is left alone: it cannot contain a `throw {` that
    matters, and parsing it correctly would mean tracking string literals,
    which is more machinery than the benefit justifies.
    """

    def blank_match(match: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    # /* ... */ including /** ... */
    text = re.sub(r"/\*.*?\*/", blank_match, text, flags=re.DOTALL)
    # whole-line // comments
    text = re.sub(r"(?m)^[ \t]*//.*$", blank_match, text)
    return text


def selftest() -> int:
    """Check the comment-stripper against a failure that happened next door.

    ADR 0079 records a sibling guard whose TypeScript comment-stripper was
    `re.sub(r"//.*$", "", line)`. `//` is both the comment marker and half
    of every URL, so it deleted from the `//` in `https://` onward --
    removing the licence URI from the very text being searched for the
    licence URI. The guard passed a violation it was written to catch.

    This file also strips `//`, so the same bug was available here. It does
    not have it, because only WHOLE-LINE comments are blanked: a trailing
    `//` after code is left alone, which is exactly the case that broke the
    other guard.

    That distinction was a judgement call when it was written, defended in
    a comment and never tested. A property defended only in prose is a
    property that stops being checked -- which is the finding of ADR 0058's
    M3 and is now stated for the third time in this repository. So it is
    asserted here, with the neighbouring guard's own failing input.
    """
    cases: list[tuple[str, bool, str]] = [
        # (source, should the stripper leave a detectable `throw {`, label)
        (
            'const u = "https://creativecommons.org/licenses/by/4.0/";',
            False,
            "a URL is not a comment (ADR 0079's exact failure)",
        ),
        (
            'fetch("https://x"); throw { y: 2 };',
            True,
            "a URL and a real violation on one line",
        ),
        ("const bad = 1; throw { a: 1 };", True, "a trailing violation stays visible"),
        ("  // throw { this is prose }", False, "a whole-line comment is blanked"),
        ("/* throw { in a block */ const x = 1;", False, "a block comment is blanked"),
    ]

    failures = 0
    print("Self-test: the comment-stripper against ADR 0079's failing input.\n")
    for source, should_detect, label in cases:
        detected = bool(THROW_OBJECT_RE.search(blank_comments(source)))
        ok = detected == should_detect
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"        expected detect={should_detect}, got {detected}")
            print(f"        source: {source}")

    # A URL must survive stripping intact, not merely fail to look like a
    # violation. The other guard's bug was that the URL VANISHED, and a
    # `throw {` check would not have noticed that.
    url = "https://creativecommons.org/licenses/by/4.0/"
    stripped = blank_comments(f'const u = "{url}";')
    ok = url in stripped
    failures += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] the URL itself survives stripping")

    print()
    if failures:
        print(f"FAIL: {failures} self-test case(s) failed.", file=sys.stderr)
        return 1
    print("OK: comments are blanked; URLs and trailing code are not.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    files = typescript_files()

    if not files:
        # A guard that examined nothing must not print OK. Same rule as the
        # citation guard that parsed zero entries and reported success:
        # a check with an empty input is a check that cannot fail.
        print("FAIL: found no TypeScript files to check.", file=sys.stderr)
        print(f"  Looked in: {[str(r) for r in SEARCH_ROOTS]}", file=sys.stderr)
        return 1

    violations: list[tuple[Path, int, str]] = []
    scanned = 0
    skipped_tests = 0

    for path in files:
        if is_test_file(path):
            skipped_tests += 1
            continue
        scanned += 1
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = blank_comments(raw)
        for match in THROW_OBJECT_RE.finditer(text):
            line_no = line_number_of(text, match.start())
            line = raw.splitlines()[line_no - 1].strip()
            violations.append((path.relative_to(REPO_ROOT), line_no, line))

    print(f"Checked {scanned} TypeScript file(s); skipped {skipped_tests} test file(s).")

    if not violations:
        print("\nOK: every thrown value is an Error, so `instanceof Error` works on it.")
        return 0

    print(f"\nThrown object literals ({len(violations)}):", file=sys.stderr)
    for rel, line_no, line in violations:
        print(f"  - {rel}:{line_no}  {line}", file=sys.stderr)

    print(
        "\nA thrown object literal is not an Error, so the standard idiom\n"
        "    error instanceof Error ? error.message : String(error)\n"
        'takes the String() branch and yields the literal text "[object Object]".\n'
        "\n"
        "That is what users saw for every failed simulation until ADR 0065:\n"
        "the pipeline preserved the real cause in a `message` field and every\n"
        "consumer discarded it.\n"
        "\n"
        "Throw an Error subclass instead -- see SimulationError in src/errors.ts.\n"
        "It carries the same fields and satisfies `instanceof Error`, so every\n"
        "existing catch site works unchanged, including ones not written yet.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
