#!/usr/bin/env python3
"""The numbers a paper about Terrium would need, each one measured now.

WHY THIS EXISTS
---------------
Terrium's measurable facts are real and scattered. Its parser coverage is
printed by `check_commentary_coverage.py` as a side effect of passing. Its
test counts live inside `check_documented_counts.py`. Its guard and decision
counts are file globs nobody runs by hand. Every one of them is a number
somebody writing about this project would want, and none of them is
reachable without knowing which guard to run and how to read its prose.

So a figure destined for a paper gets typed from memory, and then it is a
number nobody is watching — which is how a funding application came to claim
1,893 tests against 2,279 (ADR 0159), and a pitch deck 1,852 against 2,220
before that. Both understated, both by about the same margin, neither
noticed for weeks.

WHAT MAKES THIS DIFFERENT FROM A SUMMARY
----------------------------------------
Every row is COMPUTED when this runs. Nothing is transcribed, and there is
no cached copy to drift. A row that cannot be computed offline is printed as
`not measurable here` with the reason — never estimated, never carried over
from a previous run.

Each row also carries the command that produced it, so a reviewer can
re-derive any single figure without reading this file.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Anything requiring the network. BRENDA coverage across the real database,
how many published Km values Terrium can resolve in the wild, whether a
citation it emits describes the enzyme it was attached to — all three are
the questions a reviewer would most want answered, and all three need
credentials and live data this cannot reach. They are listed at the end as
open rather than approximated from eleven committed fixtures, because a
number measured on eleven pages and presented as a property of the database
would be exactly the overreach this project exists to refuse.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


class Row:
    def __init__(self, label: str, command: str, measure: Callable[[], str]):
        self.label = label
        self.command = command
        self.measure = measure


def _count_tests(directory: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", directory, "-q", "--co", "-p", "no:randomly"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=600,
    )
    # TWO OUTPUT SHAPES, because the two suites have different pytest.ini
    # files. `Tests/` ends with "1102 tests collected in 2.93s"; the engine
    # suite prints one `path: N` line per file and no summary at all.
    #
    # The first version matched only the summary and reported the engine
    # suite as "not measurable here — pytest collection returned 0", which
    # is a message naming a successful exit code as the reason for failure.
    # A parser that understands one of two formats and blames the subject is
    # worse than one that says it did not understand.
    lines = [l for l in done.stdout.splitlines() if l.strip()]
    for line in reversed(lines):
        if "test" in line and "collected" in line:
            return line.strip()

    total = 0
    counted = 0
    for line in lines:
        head, _, tail = line.rpartition(":")
        if head.endswith(".py") and tail.strip().isdigit():
            total += int(tail.strip())
            counted += 1
    if counted:
        return f"{total} tests collected across {counted} files"

    return (
        "not measurable here — pytest exited "
        f"{done.returncode} and printed neither a summary nor per-file counts"
    )


def _commentary_coverage() -> str:
    """Reuses the guard's own collector rather than re-parsing BRENDA.

    Two implementations of "how much commentary do we understand" would be
    two numbers to keep true, and this repository has spent most of its
    effort on instances of exactly that.
    """
    try:
        from check_commentary_coverage import collect_commentaries, residue_counts
    except ImportError as exc:
        return f"not measurable here — {exc}"
    commentaries = collect_commentaries()
    if not commentaries:
        return "not measurable here — no commentaries collected"
    # `residue_counts`, not a fresh loop over `residue_of`. The first
    # version of this function did the latter and omitted the guard's
    # minimum-length floor, so the two printed 92% and 87% for the same
    # fact under the same words. See that function's docstring.
    unread_total = sum(residue_counts(commentaries).values())
    understood = len(commentaries) - unread_total
    pct = round(100 * understood / len(commentaries))
    return (
        f"{understood} of {len(commentaries)} commentaries fully parsed "
        f"({pct}%); {unread_total} carry text the parser does not read"
    )


def _citation_attribution() -> str:
    """Was listed here as needing live BRENDA. It did not (ADR 0161)."""
    try:
        from check_citations_match_their_enzyme import check
    except ImportError as exc:
        return f"not measurable here — {exc}"
    failures, checked, unchecked = check()
    return (
        f"{checked} attributed and correct, {len(failures)} wrong, "
        f"{len(unchecked)} with no enzyme named nearby"
    )


def _file_count(pattern: str, what: str) -> Callable[[], str]:
    def measure() -> str:
        return f"{len(list(REPO_ROOT.glob(pattern)))} {what}"
    return measure


def _domains() -> str:
    catalogue = REPO_ROOT / "src" / "cli" / "domainCatalogue.ts"
    if not catalogue.is_file():
        return "not measurable here — domainCatalogue.ts is missing"
    text = catalogue.read_text(encoding="utf-8")
    # Counted from the catalogue the CLI actually reads, not from the README
    # sentence that describes it. The sentence is checked against this by
    # check_documented_counts; counting the sentence here would make this
    # table agree with the prose and disagree with the product.
    return f"{text.count('id:')} entries in DOMAIN_CATALOGUE"


ROWS: tuple[Row, ...] = (
    Row("Simulation engine tests", "pytest Terium/tests --co -q",
        lambda: _count_tests("Terium/tests")),
    Row("Literature layer tests", "pytest Tests --co -q",
        lambda: _count_tests("Tests")),
    Row("Guard scripts", "ls scripts/check_*.py",
        _file_count("scripts/check_*.py", "guards")),
    Row("Architecture decisions", "ls docs/adr/[0-9]*.md",
        _file_count("docs/adr/[0-9]*.md", "ADRs")),
    Row("Simulation domains", "src/cli/domainCatalogue.ts", _domains),
    Row("BRENDA pages committed as fixtures", "ls Tests/fixtures/*.html",
        _file_count("Tests/fixtures/*.html", "saved pages")),
    Row("BRENDA commentary the parser reads",
        "python scripts/check_commentary_coverage.py", _commentary_coverage),
    Row("Documented citations checked against their enzyme",
        "python scripts/check_citations_match_their_enzyme.py",
        _citation_attribution),
)

OPEN: tuple[tuple[str, str], ...] = (
    ("Coverage across BRENDA as a whole",
     "measured on eleven committed pages here. Presenting that as a property "
     "of the database would be the overreach this project refuses; it needs "
     "a bulk download, which BRENDA asks tools not to fetch automatically."),
    ("Whether a student's report survives peer review",
     "not a thing any script measures. Four professors have been asked; "
     "their answers are in docs/EXPERT_FEEDBACK.md, not in this table."),
)


def main() -> int:
    print("Terrium — measured now, not transcribed\n")
    width = max(len(row.label) for row in ROWS)
    for row in ROWS:
        try:
            value = row.measure()
        except Exception as exc:  # noqa: BLE001 — a row that cannot be
            # measured is a result, not a crash. One broken collector must
            # not cost the other six.
            value = f"not measurable here — {type(exc).__name__}: {exc}"
        print(f"  {row.label:<{width}}  {value}")
        print(f"  {'':<{width}}  $ {row.command}")
        print()

    print("Open, and not approximated:\n")
    for question, why in OPEN:
        print(f"  {question}")
        print(f"      {why}\n")
    print("Every figure above was computed by this run. There is no cached")
    print("copy in the repository, because a second copy is a number nobody")
    print("is watching — which is how a funding application came to claim")
    print("1,893 tests against 2,279 (ADR 0159).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
