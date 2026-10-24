#!/usr/bin/env python3
"""No tracked Markdown file may print a placeholder DOI.

WHY THIS EXISTS
---------------
`docs/ARCHITECTURE_RIGOR.md` ended with the sentence "Every citation has
DOI/PMID" and, two hundred lines above it, showed a "Provenance Chain
Example" whose two citations carried DOIs under the example prefix 10.1234,
which is what documentation reaches for when it needs something DOI-shaped
and which no reader can follow to a paper. The same document described a
language-model tier that ADR 0011's amendment had removed, counted eleven
guards where there were seventy-seven, and declared the project ready for
publication. Run before it was wired, this guard also found an invented
citation ("Smith et al. (2020)", template DOI) in two root design documents;
those lines now say that no paper is cited. It was deleted on 2026-10-17 (ADR 0179) and replaced by
`docs/ARCHITECTURE.md`.

The README once carried `BRENDA ref 12345` the same way, and
`check_documented_citations_are_real.py` (ADR 0144) now refuses a BRENDA
reference that occurs in no fixture. Nothing did the equivalent for a DOI.
A reader who follows a citation and finds nothing has the suspicion that the
claims were invented confirmed by the project's own documentation, and no
later argument undoes that.

WHAT IT CHECKS
--------------
Every tracked `*.md` file (`git ls-files`), line by line, for the example
prefixes 10.1234 and 10.0000 followed by a slash, and for `doi:` followed by
the template `10.xxxx`, ignoring case. A hit fails unless the file is on
ALLOWED with a reason. `docs/archive/` is not read at all (EXCLUDED says
why), and nothing under a `node_modules` directory ever is.

An allowance that no longer applies -- the file is gone, or no longer
matches -- fails too. The list may only shrink.

WHAT IT DOES NOT CHECK
----------------------
Whether a real-looking DOI resolves. That needs the network and is
`scripts/verify_citations_live.py`'s job under `verify_build.py --live`.
Source files: a test may use an invented DOI as an input, and the TypeScript
suites do. This guard is about documentation, where a DOI reads as a
citation.

Usage:
    python scripts/check_no_placeholder_dois.py             # exit 1 on a hit
    python scripts/check_no_placeholder_dois.py --selftest  # prove it matches
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Built from pieces so that a future guard reading this file as text does not
#: trip on the very strings this one refuses.
_EXAMPLE_PREFIX = "10." + "1234/"
_ZERO_PREFIX = "10." + "0000/"
_TEMPLATE = "doi:" + "10.xxxx"
PATTERN = re.compile(
    r"(?:10\.1234/|10\.0000/|doi:\s*10\.xxxx)",
    re.IGNORECASE,
)

#: Directories (prefixes ending in "/") that are not read, and why.
EXCLUDED: dict[str, str] = {
    "docs/archive/": (
        "documents moved out of the repository root as records of what was "
        "true on a date (docs/ARCHIVE_TRIAGE.md); they are never rewritten, so "
        "a placeholder there is history, not a claim"
    ),
}

#: Tracked Markdown files allowed to contain a match, and why. Each reason
#: names what the match is, so a reader can decide whether it still holds.
ALLOWED: dict[str, str] = {
    "TESTING_AND_ROADMAP.md": (
        "quotes jest examples in which the invented DOI is a test INPUT -- the "
        "value the api-server's literature-verifier.test.ts and the root "
        "critical-paths.test.ts use; the document mirrors those tests, and a "
        "different DOI here would misdescribe them"
    ),
    "SCIENTIFIC_VALIDATION_FRAMEWORK.md": (
        "shows the refusal printed for a DOI that cannot be resolved, with an "
        "invented DOI as the thing being refused; an example of a bad citation "
        "being rejected is not a bad citation"
    ),
}

#: Below this, `git ls-files` is broken rather than the tree being small:
#: the repository holds several hundred tracked Markdown files.
MIN_FILES = 50

MAX_BYTES = 2_000_000


def tracked_markdown(root: Path = ROOT) -> list[str]:
    """Every tracked `*.md`, as git lists it, with vendored trees left out."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    names = [n for n in out.decode("utf-8", "surrogateescape").split("\0") if n]
    return [n for n in names if "node_modules/" not in n]


def excluded(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in EXCLUDED)


def allowed(rel: str) -> bool:
    return rel in ALLOWED


def hits_in(text: str) -> list[tuple[int, str]]:
    return [
        (number, line.strip()[:160])
        for number, line in enumerate(text.splitlines(), 1)
        if PATTERN.search(line)
    ]


def _read(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def findings(root: Path = ROOT, names: list[str] | None = None) -> list[str]:
    """`path:line: text` for every placeholder DOI in a file that may not hold one."""
    problems: list[str] = []
    for rel in names if names is not None else tracked_markdown(root):
        if excluded(rel) or allowed(rel):
            continue
        text = _read(root / rel)
        if text is None:
            continue
        for number, line in hits_in(text):
            problems.append(f"{rel}:{number}: {line}")
    return problems


def stale_allowances(root: Path = ROOT, allowances: dict[str, str] | None = None) -> list[str]:
    """Allowed files that are gone or no longer contain a match.

    An allowance nobody needs is an allowance nobody re-reads, and the next
    placeholder added to that file would pass under a reason written for a
    different line. The list may only shrink.
    """
    stale: list[str] = []
    for rel in (ALLOWED if allowances is None else allowances):
        text = _read(root / rel)
        if text is None:
            stale.append(f"{rel}: on ALLOWED but not a readable tracked file")
        elif not hits_in(text):
            stale.append(f"{rel}: on ALLOWED but contains no placeholder DOI any more")
    return stale


def selftest() -> int:
    """Plant each pattern and confirm it is caught; confirm clean text passes.

    A guard nobody has seen fail is a guard nobody knows works.
    """
    import tempfile

    planted = (
        "fine\n"
        f'"doi": "{_EXAMPLE_PREFIX}example"\n'
        "also fine\n"
        f"see {_ZERO_PREFIX}placeholder for the shape\n"
        f"cite as {_TEMPLATE.upper()}\n"
    )
    got = [n for n, _ in hits_in(planted)]
    if got != [2, 4, 5]:
        print(f"selftest FAILED: expected hits on lines 2, 4 and 5, got {got}")
        return 1

    clean = (
        "doi:10.1093/nar/gkaa1025 (Chang et al. 2021)\n"
        "https://doi.org/10.1002/pro.2473\n"
        "the example prefix 10.1234 is refused when a slash follows it\n"
        "10.0000 as a bare number is a tolerance, not a DOI\n"
    )
    if hits_in(clean):
        print(f"selftest FAILED: a real DOI or a bare number matched: {hits_in(clean)}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs" / "archive").mkdir(parents=True)
        (root / "docs" / "archive" / "old.md").write_text(planted, encoding="utf-8")
        (root / "docs" / "live.md").write_text(planted, encoding="utf-8")
        (root / "TESTING_AND_ROADMAP.md").write_text(planted, encoding="utf-8")
        names = ["docs/archive/old.md", "docs/live.md", "TESTING_AND_ROADMAP.md"]
        problems = findings(root, names)
        if [p.split(":")[0] for p in problems] != ["docs/live.md"] * 3:
            print(f"selftest FAILED: expected three findings in docs/live.md only, got {problems}")
            return 1
        stale = stale_allowances(root, {"TESTING_AND_ROADMAP.md": "x", "missing.md": "y"})
        if len(stale) != 1 or not stale[0].startswith("missing.md"):
            print(f"selftest FAILED: expected exactly the missing allowance to be stale, got {stale}")
            return 1

    # The real allow-list, against the real tree: every entry must still be
    # needed, or the list has stopped being a decision somebody re-reads.
    stale = stale_allowances()
    if stale:
        print("selftest FAILED: a stale allowance in ALLOWED:")
        for line in stale:
            print(f"  {line}")
        return 1
    short = [k for k, reason in {**ALLOWED, **EXCLUDED}.items() if len(reason) < 40]
    if short:
        print(f"selftest FAILED: these allowances state no real reason: {short}")
        return 1

    print(
        "selftest ok: matches the two example prefixes and the doi template, "
        "leaves real DOIs and bare numbers alone, skips the archive, and every "
        "allowance is still needed"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--selftest" in args:
        return selftest()
    names = tracked_markdown()
    if len(names) < MIN_FILES:
        print(
            f"FAIL: git ls-files returned {len(names)} Markdown files; the "
            "listing is broken and nothing was checked"
        )
        return 1
    problems = findings(names=names)
    stale = stale_allowances()
    if problems or stale:
        if problems:
            print(f"FAIL: {len(problems)} line(s) print a placeholder DOI:")
            for line in problems[:60]:
                print(f"  {line}")
            print(
                "A citation a reader cannot follow is worse than none: cite the "
                "paper, or say in prose that there is no citation."
            )
            print(
                "A document that must keep one goes on ALLOWED in "
                "scripts/check_no_placeholder_dois.py, with the reason."
            )
        if stale:
            print(f"FAIL: {len(stale)} allowance(s) no longer apply; remove them:")
            for line in stale:
                print(f"  {line}")
        return 1
    print(
        f"ok: {len(names)} tracked Markdown files, none prints a placeholder DOI "
        f"({len(ALLOWED)} allowed to, each with a reason; "
        f"{', '.join(EXCLUDED)} not read, as a record)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
