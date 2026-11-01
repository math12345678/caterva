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

THE REPOSITORY FACTS THE PAGE SHOWS
-----------------------------------
`src/lib/generated/repoFacts.json` holds the counts the page shows that are
facts about the repository rather than measurements of a run: the number
of guard scripts (`scripts/check_*.py`), the engine and literature test
counts README.md states (and check_documented_counts.py holds to pytest's
collection), and the data sources docs/data-sources.json attributes. They
were hand-typed in domains.ts and testResults.ts, and on 2026-10-31 the
page said 76 guards against 79 on disk, and 6,696 / 1,589 engine and
literature tests against the README's 7,057 / 1,622.

It also holds the release tag the page names (`releaseTag`), "v" plus
`__version__` in caterva/__init__.py, the one place the version lives. On
2026-11-01 the page still offered v0.4.0 as the download, its 404 page
showed "v0.7.0", and the roadmap labelled released work "In v0.4.0", four
days after v0.6.0 was published on 2026-10-28: the tag was typed in
domains.ts and GetCaterva.tsx and nothing compared it to the package.

The default run regenerates that file's content in memory and fails when
the checked-in copy differs; `--write` writes it. It also fails when the
engine or literature row of testResults.ts states a `collected:` figure
other than the suite size in repoFacts.json: a pass count measured
against a suite that has since grown or shrunk is a measurement of
something else, so adding a test now fails the build until somebody
re-measures.

Usage:
    python scripts/check_landing_test_counts.py
    python scripts/check_landing_test_counts.py --full
    python scripts/check_landing_test_counts.py --write
    python scripts/check_landing_test_counts.py --selftest
"""

from __future__ import annotations

import argparse
import json
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

LANDING = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "caterva-landing"
REPO_FACTS = LANDING / "src" / "lib" / "generated" / "repoFacts.json"
DATA_SOURCES = REPO_ROOT / "docs" / "data-sources.json"
VERSION_FILE = REPO_ROOT / "caterva" / "__init__.py"

#: The keys of repoFacts.json that are derived from the tree and compared.
FACT_KEYS = ("guardScripts", "tests", "dataSources", "releaseTag")

#: testResults.ts rows whose suite size README.md states, keyed by
#: workingDirectory, naming the key in repoFacts.json's "tests".
COLLECTED_SUITES: Dict[str, str] = {"caterva/": "engine", "Tests/": "literature"}

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
    # The root TypeScript package (src/, the `scientific` CLI), run by jest
    # from the repository root -- CI's root-typescript job, `make test-ts`.
    # Keyed "./" because that is where the suite runs, as every other key
    # here is. The glob is every test file under src/, not jest's testMatch
    # (`__tests__/**/*.test.ts`): a file jest would not collect still
    # counts here, so the figure cannot quietly agree with a runner that
    # dropped it; check_typescript_suites_discovered names such a file.
    # `npx jest` prints "Tests: N passed, M total" last, which run_suite's
    # last-match reading takes.
    "./": {
        "glob": "src/**/*.test.ts",
        "run": ["npx", "jest", "--ci"],
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
        collected: Optional[int] = None,
    ) -> None:
        self.name = name
        self.working_directory = working_directory
        self.files_claimed = files_claimed
        self.passed = passed
        self.skipped = skipped
        self.failed = failed
        # The suite size the pass count was measured against, where the
        # row states one (the engine and literature rows must).
        self.collected = collected


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
        c = re.search(r"collected:\s*(\d+)", files_body)
        collected = int(c.group(1)) if c else None
        claims.append(
            Claim(name, wd, files_claimed, passed, skipped, failed, collected)
        )
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


def expected_facts() -> Tuple[Optional[dict], List[str]]:
    """What repoFacts.json should say, derived from the tree now.

    Returns (facts, problems). A count that cannot be read is a problem,
    never a guess: facts is None then, and nothing is written.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from check_documented_counts import documented_numbers
    finally:
        sys.path.pop(0)

    problems: List[str] = []
    readme = REPO_ROOT / "README.md"
    documented = (
        documented_numbers(readme.read_text(encoding="utf-8"))
        if readme.is_file()
        else {}
    )
    tests = {}
    for key in ("engine", "literature"):
        if key not in documented:
            problems.append(f"README.md states no {key} test count to derive from")
        else:
            tests[key] = documented[key]

    sources: List[str] = []
    try:
        data = json.loads(DATA_SOURCES.read_text(encoding="utf-8"))
        sources = [s["tokens"][0] for s in data["sources"]]
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        problems.append(f"could not read the source list in {DATA_SOURCES}: {exc}")
    if not sources and not problems:
        problems.append(f"{DATA_SOURCES} lists no sources")

    # Read as text, not imported: importing caterva loads the engine and
    # its native libraries, which a fact about a string does not need.
    version = None
    try:
        m = re.search(
            r'^__version__\s*=\s*"([^"]+)"',
            VERSION_FILE.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        version = m.group(1) if m else None
    except OSError:
        pass
    if version is None:
        problems.append(f"could not read __version__ from {VERSION_FILE}")

    if problems:
        return None, problems
    return (
        {
            "_readme": [
                "Generated by `python3 scripts/check_landing_test_counts.py "
                "--write`; do not edit by hand.",
                "guardScripts: files matching scripts/check_*.py.",
                "tests: the engine and literature test counts README.md "
                "states, which scripts/check_documented_counts.py holds to "
                "pytest's collection.",
                "dataSources: the first token of each source "
                "docs/data-sources.json attributes. KEGG is not one: it is "
                "off unless CATERVA_ENABLE_KEGG is set.",
                "releaseTag: \"v\" + __version__ in caterva/__init__.py, the "
                "release the page offers and labels capabilities with.",
            ],
            "guardScripts": len(list((REPO_ROOT / "scripts").glob("check_*.py"))),
            "tests": tests,
            "dataSources": sources,
            "releaseTag": f"v{version}",
        },
        [],
    )


def facts_failures(current: Optional[dict], expected: dict) -> List[str]:
    """Each field of the checked-in facts that differs from the tree."""
    if current is None:
        return [f"{REPO_FACTS.relative_to(REPO_ROOT)} is missing or not JSON"]
    return [
        f"repoFacts.json {key} is {current.get(key)!r}, the tree says "
        f"{expected[key]!r}. Run this script with --write."
        for key in FACT_KEYS
        if current.get(key) != expected[key]
    ]


def collected_failures(claims: List[Claim], facts: dict) -> List[str]:
    """Rows measured against a suite size other than the current one."""
    failures = []
    by_wd = {c.working_directory: c for c in claims}
    for wd, key in COLLECTED_SUITES.items():
        claim = by_wd.get(wd)
        size = facts.get("tests", {}).get(key)
        if claim is None:
            failures.append(f"testResults.ts has no {wd} row to hold to {key}")
        elif claim.collected is None:
            failures.append(
                f"{claim.name}: states no 'collected:' figure, so nothing says "
                "which suite its pass count was measured against"
            )
        elif claim.collected != size:
            failures.append(
                f"{claim.name}: measured against {claim.collected} collected "
                f"tests; the suite is {size} now. Re-run it and paste the "
                "real numbers."
            )
        elif claim.passed + claim.failed > claim.collected:
            failures.append(
                f"{claim.name}: claims more passing and failing tests "
                f"({claim.passed + claim.failed}) than were collected "
                f"({claim.collected})"
            )
    return failures


def read_facts() -> Optional[dict]:
    try:
        return json.loads(REPO_FACTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_facts() -> List[str]:
    """Write repoFacts.json from the tree. Returns problems, if any."""
    facts, problems = expected_facts()
    if facts is None:
        return problems
    REPO_FACTS.parent.mkdir(parents=True, exist_ok=True)
    REPO_FACTS.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    return []


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

    facts, problems = expected_facts()
    failures.extend(problems)
    if facts is not None:
        failures.extend(facts_failures(read_facts(), facts))
        failures.extend(collected_failures(claims, facts))

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


def _package_version() -> Optional[str]:
    """__version__ as caterva/__init__.py states it, read independently of
    expected_facts so the selftest does not check the parser against itself."""
    for line in VERSION_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return None


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

    # The repository facts. Checked through the pure functions, on copies,
    # so the selftest never rewrites a file another process may be reading.
    facts, fact_problems = expected_facts()
    if facts is None:
        problems.extend(f"could not derive repoFacts: {p}" for p in fact_problems)
    else:
        if facts_failures(json.loads(json.dumps(facts)), facts):
            problems.append("facts derived from the tree were reported as stale")
        for key, wrong in (
            ("guardScripts", facts["guardScripts"] - 3),
            ("tests", {**facts["tests"], "engine": facts["tests"]["engine"] - 361}),
            ("dataSources", facts["dataSources"] + ["kegg"]),
            # The tag the page carried from v0.4.0's release on 2026-09-27
            # until 2026-11-01, the last four days of it after v0.6.0 was
            # published.
            ("releaseTag", "v0.4.0"),
        ):
            if not facts_failures({**facts, key: wrong}, facts):
                problems.append(f"a stale repoFacts {key} was NOT caught")
        if facts.get("releaseTag") != f"v{_package_version()}":
            problems.append(
                f"releaseTag {facts.get('releaseTag')!r} is not derived from "
                f"__version__ {_package_version()!r}"
            )
        if facts_failures(None, facts) == []:
            problems.append("a missing repoFacts.json was NOT caught")

        rows = [c for c in claims if c.working_directory in COLLECTED_SUITES]
        if len(rows) != len(COLLECTED_SUITES):
            problems.append("could not find the engine and literature rows")
        else:
            row = rows[0]
            key = COLLECTED_SUITES[row.working_directory]
            size = facts["tests"][key]
            for collected, what in ((size + 1, "a suite that has since grown"),
                                    (None, "a row with no 'collected:'")):
                stale = Claim(row.name, row.working_directory, row.files_claimed,
                              min(row.passed, size), row.skipped, 0, collected)
                if not collected_failures([stale] + rows[1:], facts):
                    problems.append(f"{what} was NOT caught")
            inflated = Claim(row.name, row.working_directory, row.files_claimed,
                             size + 1, 0, 0, size)
            if not collected_failures([inflated] + rows[1:], facts):
                problems.append("more passes than collected tests was NOT caught")

    if problems:
        for p in problems:
            print(f"SELFTEST FAIL: {p}", file=sys.stderr)
        return 1
    print(
        "selftest: OK -- the guard parses four suites and catches a wrong "
        "count, a stale repoFacts.json (release tag included) and a row "
        "measured against another suite size"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run every suite and compare pass counts exactly (~40 min)",
    )
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate src/lib/generated/repoFacts.json from the tree",
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.write:
        problems = write_facts()
        if problems:
            for p in problems:
                print(f"NOT WRITTEN: {p}", file=sys.stderr)
            return 1
        print(f"wrote {REPO_FACTS.relative_to(REPO_ROOT)}")

    failures = check(full=args.full)
    if failures:
        print("Landing-page test counts are wrong:\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nRe-run the affected suite and paste the real numbers into\n"
            "  Science-Agent-Pipeline/artifacts/caterva-landing/src/lib/testResults.ts\n"
            "and regenerate the repository facts with\n"
            "  python3 scripts/check_landing_test_counts.py --write\n"
            "This figure is displayed in the hero, the metrics bar and the\n"
            "trust section, on a page whose claim is that every number is\n"
            "verifiable.",
            file=sys.stderr,
        )
        return 1

    scope = "file counts and pass counts" if args.full else "file counts"
    scope += ", repoFacts.json, measured suite sizes"
    print(f"landing test counts: OK ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
