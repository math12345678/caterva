"""Guard that no TypeScript test is disabled without saying so.

TWO DEFECTS, ONE CAUSE

`.only` is the sharper one:

    describe.only("the thing I was debugging", () => { ... });

A single committed `.only` disables EVERY OTHER test in its file. The run
reports green, the count in the summary drops, and nothing anywhere says
why. It is the fastest way to turn a suite into decoration, and it lands by
accident -- someone narrows the run to debug one case and forgets to widen
it again.

`.skip` is the quieter one. Sometimes it is right: three suites here skip
when the Python engine is genuinely absent, because 40 hard failures for a
missing system library are noise rather than signal. That is the same call
`Tests/test_popgen_resolver.py` makes with `pytest.importorskip`.

But Stage 10 Part 21 recorded what that leaves behind: a clean skip is
invisible in a CI summary, so a whole domain's tests can stop running for
months and still read as green. The skip stayed; what was added was the
other half -- `scripts/check_env.py` now reports the gap in the place people
look.

THE RULE

  * `.only` -- never. No allowlist, no exceptions. It is never correct in a
    committed file, and its whole failure mode is that it is quiet.

  * `.skip` / `.todo` / `xit` / `xdescribe` -- allowed, but the file must
    ANNOUNCE it: a `console.warn`/`console.error` whose text distinguishes
    "skipped" from "passed". The three current uses already do:

        console.warn(
          '\\n[telluriumBridge.test] The Python engine could not be ' +
          'imported, so the tests that exercise the real simulation are ' +
          'SKIPPED, not passing.\\n'
        );

    That sentence is the entire point. A reader must be able to tell
    "passed" from "did not run".

This guard cannot tell whether a skip is justified -- only whether it is
audible. That is the part that can be checked mechanically, and it is the
part that was missing.

Run directly: python scripts/check_no_disabled_tests.py
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

#: `describe.only(`, `it.only(`, `test.only(` -- and the `.each().only` and
#: `.concurrent.only` variants the runners also accept.
ONLY = re.compile(r"\b(?:describe|it|test)(?:\.\w+)*\.only\b")

#: Anything that stops a test from running. `describe.skip` used as a VALUE
#: (`const d = cond ? describe : describe.skip`) counts too -- that is
#: exactly how the three legitimate uses here are written.
DISABLED = re.compile(
    r"\b(?:describe|it|test)(?:\.\w+)*\.(?:skip|todo|skipIf)\b"
    r"|\bxit\s*\(|\bxdescribe\s*\("
)

#: An announcement: a console call whose text tells a reader the tests did
#: not run. Deliberately loose about wording, strict about the channel --
#: a comment does not appear in a CI log.
#:
#: The bounded `.` matters. The first version used `[^;]{0,600}?`, meaning
#: "stay inside one statement", and immediately produced two false positives:
#: both `literatureResolver.test.ts` and `inhibitionModels.test.ts` announce
#: themselves properly, but their message text contains a semicolon --
#: "python3 unavailable; subprocess tests are SKIPPED" -- so the scan stopped
#: before reaching the word it was looking for. A semicolon inside a string
#: literal is not a statement boundary, and only a parser can tell the
#: difference. `telluriumBridge.test.ts` passed purely because its wording
#: happened not to need one.
#:
#: That is the failure mode this guard exists to avoid in its own right: a
#: check that flags correct code gets suppressed, and then catches nothing.
ANNOUNCEMENT = re.compile(
    r"console\.(?:warn|error)\s*\(.{0,600}?(?:SKIP|skip|not run|did not run)",
    re.DOTALL,
)


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


def _line_of(source: str, offset: int) -> int:
    return 1 + source[:offset].count("\n")


def check() -> list[str]:
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

        relative = path.relative_to(REPO_ROOT)

        for match in ONLY.finditer(source):
            violations.append(
                f"{relative}:{_line_of(source, match.start())} "
                f"`{match.group(0)}` -- a committed `.only` silently disables "
                "every other test in this file. The suite still reports "
                "green, which is the entire problem. Remove it."
            )

        disabled = list(DISABLED.finditer(source))
        if disabled and not ANNOUNCEMENT.search(source):
            first = disabled[0]
            violations.append(
                f"{relative}:{_line_of(source, first.start())} "
                f"`{first.group(0)}` disables {len(disabled)} test "
                f"declaration(s) with nothing printed to say so. A clean skip "
                "is indistinguishable from a pass in a CI summary. Add a "
                "console.warn naming what was skipped and why -- see "
                "src/engine/__tests__/telluriumBridge.test.ts for the shape."
            )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            "OK: no `.only`, and every disabled test announces itself."
        )
        return 0

    print(f"Disabled tests found ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA reader must be able to tell 'passed' from 'did not run'."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
