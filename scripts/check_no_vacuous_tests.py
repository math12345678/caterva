"""Guard that no test can pass without asserting anything.

THE DEFECT CLASS

    it("rejects a bad value", () => {
      const result = doThing();
      if (result) {
        expect(result.ok).toBe(false);   // <- only runs when result is truthy
      }
    });

When the guard is false the body is skipped, the test passes, and it has
verified nothing. It reports green in exactly the circumstances where it
would have been most useful.

This repository has produced it repeatedly:

  * `cachedProvenance.test.ts` returned early on a failed poll, skipping all
    three of its assertions -- silently, in precisely the conditions where
    the regression it guarded was most likely (Stage 10 Part 5).
  * `kcatProvenance.test.ts` wraps its only assertion in `if (provenance)`,
    and provenance is `undefined` for those keys BY DESIGN, so the assertion
    never executes at all.
  * A regression test I wrote in Part 12 passed against the very bug it was
    written for, because an unreachable registry made it bail before the
    assertion.

A test that cannot fail is worse than a missing test, because the missing
one is visibly missing.

The same defect has a second shape, which accommodates rather than skips:

    it("rejects a bad value", () => {
      if (result.trajectory.length === 0) {
        expect(result.validated).toBe(false);
      } else {
        expect(result.validated).toBe(true);
      }
    });

Every branch asserts, so nothing is skipped -- and the test still cannot
fail, because it has an answer ready for both outcomes and states no
expectation about which one should occur. Both shapes are the same thing: a
test with no way to go red.

WHAT COUNTS

A test body where EVERY `expect(` sits inside a conditional -- counting an
`else` branch as part of the conditional it belongs to. A test with
assertions both inside and outside a conditional is fine: the outer ones
still run. So is a conditional used for setup around assertions that follow
it.

The check is deliberately syntactic and conservative: it looks at brace
depth relative to `if`/`&&`-guards within a single `it(...)`/`test(...)`
body. It will not catch every vacuous test (a `for` over an empty array has
the same effect), and it is tuned to avoid false positives, because a guard
that cries wolf gets suppressed and then catches nothing at all.

ALLOWLIST

A test may legitimately assert conditionally when the environment decides
what is knowable -- e.g. asserting a live registry's answer only when the
network is up. Those must be listed explicitly in ALLOWED, with a reason,
so an exemption is a decision somebody made rather than a pattern that
slipped through.

Run directly: python scripts/check_no_vacuous_tests.py
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

SEARCH_ROOTS = [
    "src",
    "Science-Agent-Pipeline/artifacts/api-server/src",
]

SKIP_PARTS = {"node_modules", "dist", "coverage", ".git", "__pycache__"}

TEST_FILE = re.compile(r".*\.(test|spec)\.tsx?$")

#: `it("...", ...)` / `test("...", ...)`, capturing the name.
TEST_START = re.compile(r"""\b(?:it|test)(?:\.\w+)?\s*\(\s*['"`](.+?)['"`]""")

#: Tests whose conditional assertions are deliberate, with the reason.
#: Empty on purpose: every instance found so far was a defect.
ALLOWED: dict[str, str] = {}


def _test_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root_name in SEARCH_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for current, directories, names in os.walk(root):
            directories[:] = [d for d in directories if d not in SKIP_PARTS]
            here = pathlib.Path(current)
            for name in names:
                if TEST_FILE.match(name):
                    files.append(here / name)
    return sorted(files)


def _scan_body(body: str) -> tuple[int, int]:
    """Return (total expects, expects guarded by a conditional).

    Tracks brace depth, remembering the depth at which each `if (` opened.
    An `expect(` deeper than an open conditional is guarded.
    """
    total = 0
    guarded = 0
    depth = 0
    conditional_depths: list[int] = []
    index = 0

    while index < len(body):
        char = body[index]

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            closed = [d for d in conditional_depths if d >= depth]
            conditional_depths = [d for d in conditional_depths if d < depth]

            # `} else {` continues the same conditional. An else-branch
            # assertion is exactly as skippable as an if-branch one, and a
            # test whose only assertions are
            #
            #     if (cond) { expect(A) } else { expect(B) }
            #
            # cannot fail at all: it accommodates both outcomes and so states
            # no expectation about which should happen. Without this, the
            # closing brace would drop the conditional and the else-branch
            # assertion would be miscounted as unconditional.
            if closed and re.match(r"\s*else\b", body[index + 1 :]):
                conditional_depths.append(depth)
        elif (
            body.startswith("if", index)
            and re.match(r"if\s*\(", body[index:])
            # Word boundary on the left, so an identifier ending in "if"
            # followed by a paren -- `notif (x)`, `verif (y)` -- is not read
            # as a conditional. Without this the guard would invent
            # conditionals and report tests that are perfectly fine, and a
            # guard that cries wolf gets suppressed and then catches nothing.
            and (index == 0 or not (body[index - 1].isalnum() or body[index - 1] in "_$."))
        ):
            # The block this `if` opens will be at depth+1.
            conditional_depths.append(depth)
        elif body.startswith("expect(", index):
            total += 1
            if any(depth > d for d in conditional_depths):
                guarded += 1

        index += 1

    return total, guarded


def _extract_tests(source: str) -> list[tuple[str, int, str]]:
    """(name, line, body) for each test in the file."""
    tests: list[tuple[str, int, str]] = []

    for match in TEST_START.finditer(source):
        name = match.group(1)
        line = 1 + source[: match.start()].count("\n")

        # Walk from the first `{` after the match to its closing brace.
        brace = source.find("{", match.end())
        if brace == -1:
            continue
        depth = 0
        end = brace
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        tests.append((name, line, source[brace : end + 1]))

    return tests


def check() -> list[str]:
    """Returns a list of violation strings, empty when every test asserts."""
    files = _test_files()
    if not files:
        return [
            "No test files found under "
            + ", ".join(SEARCH_ROOTS)
            + ". Refusing to report success -- an empty scan is not a clean "
            "tree."
        ]

    violations: list[str] = []

    for path in files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for name, line, body in _extract_tests(source):
            total, guarded = _scan_body(body)

            # No assertions at all is a different (and rarer) problem; this
            # guard is specifically about assertions that exist but may not
            # run.
            if total == 0 or guarded < total:
                continue

            if name in ALLOWED:
                continue

            relative = path.relative_to(REPO_ROOT)
            violations.append(
                f"{relative}:{line} \"{name}\" -- all {total} assertion(s) "
                "are inside a conditional, so this test cannot fail: either "
                "the branch is skipped and nothing is checked, or every "
                "branch asserts and the test accommodates whatever happened. "
                "Assert the condition itself, or seed the state the test "
                "needs. If the conditionality is deliberate, add the name to "
                "ALLOWED in this script with a reason."
            )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print("OK: every test has at least one assertion that always runs.")
        return 0

    print(f"Vacuous tests found ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA test that cannot fail is worse than a missing test: the missing "
        "one is visibly missing."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
