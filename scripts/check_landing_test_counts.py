#!/usr/bin/env python3
"""The landing page may not claim a test count nobody checked.

WHAT THIS COMES FROM
--------------------
`Science-Agent-Pipeline/artifacts/caterva-landing/src/lib/testResults.ts`
feeds the "N tests passing" figure in the hero, the metrics bar and the
trust section. Its own header says:

    Whoever updates this file after adding/removing tests should re-run all
    four suites and paste the real numbers -- that's the entire point of the
    terminal panel this feeds: it should never show a number nobody checked.

Nobody did. Measured 2026-09-03, the file claimed:

    agent pipeline API   55 test files,  627 passed   actual  62 files
    landing app           2 test files,   11 passed   actual   4 files
    literature layer     77 test files, 1116 passed   actual 1130 passed

`scripts/check_documented_counts.py` guards exactly this class of claim in
README.md and the other docs a newcomer is told to trust. It does not look
at the landing page, so the most-read numbers in the product were the only
ones with no guard behind them -- on a page whose entire pitch is that
every number is verifiable.

WHAT THIS CHECKS
----------------
Default (fast, safe to run unasked, and therefore wired into `make guards`):
the "NN test files" figure in each suite's description is compared against
the actual number of test files on disk. Adding tests almost always means
adding or removing a test file, so this catches the drift that happened
without paying for four suites.

`--full` additionally RUNS each suite and compares the pass/skip/fail
counts exactly. That is the complete check and it takes roughly forty
minutes, so it is not in the default path -- Stage 4's amendment says a
guard is not delivered until something runs it unasked, and a guard nobody
can afford to run is not run unasked.

Usage:
    python scripts/check_landing_test_counts.py
    python scripts/check_landing_test_counts.py --full
    python scripts/check_landing_test_counts.py --selftest
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_RESULTS = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "caterva-landing"
    / "src"
    / "lib"
    / "testResults.ts"
)

# How to count test files, and how to run the suite, for each declared
# workingDirectory. Keyed by the exact string in testResults.ts so a
# renamed directory fails loudly here rather than being skipped silently.
SUITES: Dict[str, Dict[str, object]] = {
    "caterva/": {
        "glob": "tests/test_*.py",
        "run": ["python3", "-m", "pytest", "-q"],
    },
    "Tests/": {
        "glob": "test_*.py",
        "run": ["python3", "-m", "pytest", "-q"],
    },
    "Science-Agent-Pipeline/artifacts/api-server/": {
        # Not just src/__tests__: scienceAgent.test.ts sits beside the
        # module it tests. Globbing only the __tests__ directory undercounts
        # by one and would have had this guard demanding the wrong number.
        "glob": "src/**/*.test.ts",
        "run": ["npx", "vitest", "run"],
    },
    "Science-Agent-Pipeline/artifacts/caterva-landing/": {
        "glob": "src/**/*.test.tsx",
        "run": ["npx", "vitest", "run"],
    },
}


class Claim:
    """One suite's declared numbers, as written in testResults.ts."""

    def __init__(
        self,
        name: str,
        working_directory: str,
        files_claimed: Optional[int],
        passed: int,
        skipped: int,
        failed: int,
    ) -> None:
        self.name = name
        self.working_directory = working_directory
        self.files_claimed = files_claimed
        self.passed = passed
        self.skipped = skipped
        self.failed = failed


def parse_claims(text: str) -> List[Claim]:
    """Read the declared suites out of testResults.ts.

    Deliberately parses the SOURCE rather than importing a compiled
    artifact: the guard must fail when the checked-in file is wrong, not
    when a build output is.
    """
    claims: List[Claim] = []
    # Each suite: name, workingDirectory, then one or more file entries.
    for block in re.finditer(
        r"name:\s*\"([^\"]+)\",\s*workingDirectory:\s*\"([^\"]+)\",\s*files:\s*\[(.*?)\n    \],",
        text,
        re.DOTALL,
    ):
        name, wd, files_body = block.group(1), block.group(2), block.group(3)
        files_claimed: Optional[int] = None
        m = re.search(r"(\d+)\s+test files", files_body)
        if m:
            files_claimed = int(m.group(1))
        passed = sum(int(x) for x in re.findall(r"passed:\s*(\d+)", files_body))
        skipped = sum(int(x) for x in re.findall(r"skipped:\s*(\d+)", files_body))
        failed = sum(int(x) for x in re.findall(r"failed:\s*(\d+)", files_body))
        claims.append(Claim(name, wd, files_claimed, passed, skipped, failed))
    return claims


def actual_file_count(working_directory: str) -> Optional[int]:
    spec = SUITES.get(working_directory)
    if spec is None:
        return None
    root = REPO_ROOT / working_directory
    if not root.is_dir():
        return None
    return len(list(root.glob(str(spec["glob"]))))


def run_suite(working_directory: str) -> Optional[Tuple[int, int, int]]:
    """Run a suite and return (passed, skipped, failed), or None."""
    spec = SUITES.get(working_directory)
    if spec is None:
        return None
    root = REPO_ROOT / working_directory
    proc = subprocess.run(
        spec["run"],  # type: ignore[arg-type]
        cwd=root,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    # pytest: "1130 passed, 1 skipped in 1777s" / vitest: "Tests  22 passed (22)"
    passed = _last_int(out, r"(\d+) passed")
    skipped = _last_int(out, r"(\d+) skipped")
    failed = _last_int(out, r"(\d+) failed")
    if passed is None:
        return None
    return (passed, skipped or 0, failed or 0)


def _last_int(text: str, pattern: str) -> Optional[int]:
    hits = re.findall(pattern, text)
    return int(hits[-1]) if hits else None


def check(full: bool) -> List[str]:
    if not TEST_RESULTS.is_file():
        return [f"{TEST_RESULTS} is missing"]
    text = TEST_RESULTS.read_text(encoding="utf-8")
    claims = parse_claims(text)

    failures: List[str] = []
    if not claims:
        # A parser that silently matched nothing would make this guard
        # pass forever, which is the failure mode it exists to prevent.
        return ["could not parse any suite out of testResults.ts"]

    known = set(SUITES)
    for claim in claims:
        if claim.working_directory not in known:
            failures.append(
                f"{claim.name}: workingDirectory {claim.working_directory!r} is "
                "not one this guard knows how to check. Add it to SUITES, or "
                "fix the path."
            )
            continue

        actual_files = actual_file_count(claim.working_directory)
        if claim.files_claimed is None:
            failures.append(
                f"{claim.name}: no 'NN test files' figure to check. State one "
                "so the count is guarded."
            )
        elif actual_files is not None and claim.files_claimed != actual_files:
            failures.append(
                f"{claim.name}: claims {claim.files_claimed} test files, "
                f"found {actual_files} in {claim.working_directory}"
            )

        if claim.failed != 0:
            failures.append(
                f"{claim.name}: claims {claim.failed} failing tests. The page "
                "must not advertise a suite that does not pass."
            )

        if full:
            measured = run_suite(claim.working_directory)
            if measured is None:
                failures.append(
                    f"{claim.name}: could not run the suite to verify its "
                    "counts. 'could not check' is not 'checked and fine'."
                )
                continue
            passed, skipped, failed = measured
            if (passed, skipped, failed) != (claim.passed, claim.skipped, claim.failed):
                failures.append(
                    f"{claim.name}: claims {claim.passed} passed / "
                    f"{claim.skipped} skipped / {claim.failed} failed, "
                    f"measured {passed} / {skipped} / {failed}"
                )
    return failures


def selftest() -> int:
    """Prove the guard can fail. A check that cannot fail is worse than none."""
    text = TEST_RESULTS.read_text(encoding="utf-8")
    claims = parse_claims(text)
    problems: List[str] = []

    if len(claims) < 4:
        problems.append(f"expected 4 suites in testResults.ts, parsed {len(claims)}")
    for claim in claims:
        if claim.files_claimed is None:
            problems.append(f"{claim.name}: no 'NN test files' figure parsed")
        if claim.passed <= 0:
            problems.append(f"{claim.name}: parsed a non-positive pass count")

    # A wrong file count must be caught.
    broken = re.sub(r"(\d+)(\s+test files)", r"999999\2", text, count=1)
    if broken == text:
        problems.append("selftest could not mutate a file count")
    else:
        original = TEST_RESULTS.read_text(encoding="utf-8")
        try:
            TEST_RESULTS.write_text(broken, encoding="utf-8")
            if not check(full=False):
                problems.append("a wrong 'NN test files' figure was NOT caught")
        finally:
            TEST_RESULTS.write_text(original, encoding="utf-8")

    if problems:
        for p in problems:
            print(f"SELFTEST FAIL: {p}", file=sys.stderr)
        return 1
    print("selftest: OK -- the guard parses four suites and catches a wrong count")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run every suite and compare pass counts exactly (~40 min)",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    failures = check(full=args.full)
    if failures:
        print("Landing-page test counts are wrong:\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nRe-run the affected suite and paste the real numbers into\n"
            "  Science-Agent-Pipeline/artifacts/caterva-landing/src/lib/testResults.ts\n"
            "This figure is displayed in the hero, the metrics bar and the\n"
            "trust section, on a page whose claim is that every number is\n"
            "verifiable.",
            file=sys.stderr,
        )
        return 1

    scope = "file counts and pass counts" if args.full else "file counts"
    print(f"landing test counts: OK ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
