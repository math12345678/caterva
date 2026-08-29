#!/usr/bin/env python3
"""Numbers shown to investors must match the repository.

WHY THIS EXISTS
---------------
ADR 0075 closed the gap between the landing page and the code, and named
the one it did not close:

    Business/ -- the pitch deck and fundraising tracker are investor-facing
    and outside PUBLIC_TREES. The same class of drift is more consequential
    there, and .pptx and .docx are not greppable by this guard.

They are greppable; it just takes ten lines. An Office file is a zip of XML,
and the text lives in `<a:t>` elements (pptx) or `<w:t>` (docx). No
dependency is needed and none is added -- `python-pptx` happens to be
installed in this environment but is not in `requirements.txt`, and a guard
that CI cannot run is not a guard.

WHAT WAS FOUND ON THE FIRST RUN
-------------------------------
`terrium_pitch_deck.pptx`, slides 6 and 11: **"382 automated tests
passing"**. The repository had 1,851. The deck understated its own evidence
by nearly five times.

That is the third instance of the same shape this week -- README counts
(caught by `check_documented_counts.py`), the FAQ's "304+ tests" (ADR
0075), and now the deck. Each was written once, was true once, and was
never looked at again. **All three understated.** A number nobody re-checks
drifts in whichever direction the last edit went, and this project's
particular direction has been modesty rather than exaggeration. That is
luck, not policy, and the next one could go the other way -- in a document
sent to people deciding whether to give you money.

WHAT THIS CHECKS
----------------
Every numeric claim in `CLAIMS` is re-derived from the repository and
compared to what the document says. A mismatch FAILS with both numbers.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
Positioning. The deck pitches "six domains" while fifteen are built; that
is a decision about what is productised versus what compiles, and it is the
founder's to make. This guard checks facts that have one right answer, not
narrative that has several.

Forward-looking statements ("MVP complete by December 2026") are likewise
out of scope. A plan is not a claim about the present.
"""
from __future__ import annotations

import functools
import pathlib
import re
import subprocess
import sys
import zipfile
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Below this the extraction is broken rather than the deck being clean.
_MIN_WORDS = 200

#: Public marketing surfaces, added 2026-08-15.
#:
#: `mule/index.html` carried "1,291 tests / engine + literature" while the
#: repository had ~1,863 -- the SAME stale figure that three onboarding
#: documents were found carrying six passes earlier. It drifted on the
#: public page too, and nothing looked.
#:
#: `check_no_unsourced_ui_numbers.py` documents excluding mule/ on the
#: grounds that "marketing copy makes claims about the project rather than
#: readings from it". That reasoning is sound for THAT guard -- it checks
#: metric displays -- and it left the claims themselves unchecked by
#: anything. A claim to the public is the same category this file already
#: covers for a pitch deck: a number stated to somebody with no way to
#: verify it.
#:
#: Sixth instance of a correct guard on too narrow a scope.
PUBLIC_MARKETING: tuple[str, ...] = (
    "mule/index.html",
)

#: The five Docw/*.docx files were removed from the repository on 2026-08-16.
#: Every one is marked "Confidential" on its own pages and one is also
#: "Internal Use Only", and all five were published in a public repository;
#: two also claimed Tellurium integration, contradicting NOTICE.
#:
#: THIS IS A REAL LOSS AND IS RECORDED AS ONE. The numbers in those documents
#: still go to investors -- they are just no longer in the repository, so this
#: guard can no longer check them. What was an automated check is now a human
#: one. The alternative was continuing to publish confidential documents in
#: order to keep them checkable, which is a worse trade, but it is a trade and
#: not a free win. If they ever return to the repository, re-add them here.
INVESTOR_DOCS: tuple[str, ...] = (
    "terrium_pitch_deck.pptx",
    # A grant/programme application draft. Marked "ready to copy in", so it
    # is operational rather than historical: somebody will paste these
    # numbers into a real submission. It claimed 429 tests and 3 domains --
    # true when drafted on 2026-07-28, and a 77% understatement by the time
    # anyone would submit it.
    #
    # An understatement is not harmless here. It is a claim to an evaluating
    # body about what the project is, made by someone who cannot check it.
    "Business/FYDEMY_APPLICATION_DRAFT.md",
    "Business/FUNDRAISING_TRACKER.md",
    "Business/ROADMAP.md",
    "Business/README.md",
)

#: A number that says WHEN it was true is not a stale claim; it is a dated
#: one, and dated claims age honestly.
#:
#: `Docw/terrium_mvp_timeline.docx` says the literature layer "already
#: exists and passes 124 tests **as of this session**". The live figure is
#: far higher, but that sentence was true when written and says so. The
#: pitch deck's "382 automated tests passing" carried no such qualifier and
#: therefore read as a claim about now.
#:
#: This is the distinction the guard exists to draw. Flagging the timeline
#: would punish the document that did the right thing, and a guard that
#: penalises good practice gets switched off.
_TIMESTAMP_RE = re.compile(
    r"as of (this session|[A-Z][a-z]+ \d|\d{4}-\d{2}|\w+ \d{4})", re.I
)

#: How much text either side of a number counts as "near" its qualifier.
_TIMESTAMP_WINDOW = 120


def office_text(path: pathlib.Path) -> str:
    """Visible text from a .pptx or .docx, using only the standard library.

    An Office file is a zip of XML. Slide text is in `<a:t>`; Word body
    text is in `<w:t>`. Reading both is enough to check a number, which is
    all this needs to do -- it is not a document parser and should not
    grow into one.
    """
    if path.suffix not in {".pptx", ".docx"}:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return ""
    parts: list[str] = []
    for name in archive.namelist():
        if not (name.startswith(("ppt/slides/slide", "word/document"))
                and name.endswith(".xml")):
            continue
        xml = archive.read(name).decode("utf-8", "replace")
        parts.extend(re.findall(r"<(?:a|w):t[^>]*>(.*?)</(?:a|w):t>", xml, re.S))
    return " ".join(parts)


@functools.cache
def _live_test_total() -> int:
    """Engine + literature test counts, from the guard that already knows.

    Cached because it shells out to `check_documented_counts.py`, which
    collects the whole suite. Without this it ran once per claim per
    document -- eight collections -- and the guard timed out, which is its
    own kind of failure: a check too slow to run is a check nobody runs.
    """
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_documented_counts.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    found = dict(re.findall(r"^\s+(engine|literature)\s+(\d+)\s*$", out, re.M))
    if len(found) != 2:
        return -1
    return sum(int(v) for v in found.values())


#: label -> (pattern capturing the claimed number, live value, tolerance)
#:
#: The tolerance exists because the tree moves: several agents commit here
#: and the test count changes hourly. A deck within a few per cent is
#: current; one that is five times out is stale. Flagging a difference of
#: three would train people to ignore this.
def _live_domain_count() -> int:
    """Domains, read from the README's own consistency-checked claim.

    Not counted from DISPATCH: `check_documented_counts.py` explains why --
    that table holds a run-mode and a generic ingest path that are not
    teaching domains, so any automatic count would encode a judgement call.
    The README states it, two guards keep it internally consistent, and this
    reads that rather than making the call a third time.
    """
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    }
    match = re.search(r"\b([A-Za-z]+|\d+)\s+simulation domains\b", readme, re.I)
    if not match:
        raise RuntimeError(
            "README states no domain count; check_documented_counts should "
            "have failed first."
        )
    token = match.group(1).lower()
    return words.get(token) or int(token)


CLAIMS: dict[str, tuple[str, Callable[[], int], float]] = {
    "automated tests passing": (
        r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", _live_test_total, 0.15
    ),
    "tests passing (status slide)": (
        r"(\d[\d,]*)\s+tests passing", _live_test_total, 0.15
    ),
    # The landing page's phrasing: "1,291 tests / engine + literature".
    # A separate entry rather than a looser regex on the two above: a
    # pattern broad enough to catch every phrasing would also catch
    # "3 tests" in a code sample, and a guard that cries wolf on an
    # example gets muted.
    # The application draft said "3 live simulation domains" against a real
    # fifteen. Fixed by hand first, which is exactly how it went stale the
    # first time -- a number nothing checks drifts again.
    #
    # Zero tolerance: a domain count is a small integer that changes when
    # somebody ships a domain, not a figure that moves hourly. "Within 15%"
    # of fifteen would accept thirteen, and the difference between thirteen
    # and fifteen domains is two domains.
    "live simulation domains": (
        r"(\d+)\s+live simulation domains", _live_domain_count, 0.0
    ),
    "tests (marketing footer)": (
        r"(\d[\d,]*)\s+tests\s*/", _live_test_total, 0.15
    ),
}



#: Business/ documents that make a countable claim and are NOT scanned.
#:
#: `build-stages/` is excluded wholesale and that is not an oversight: those
#: files are dated build logs. "Mutation reverted; 124 tests green" was true
#: on the day it was written, and rewriting it to today's total would
#: falsify a record rather than correct a claim. The same reasoning
#: LICENSE's historical narrative gets in check_dependency_licenses.
#:
#: Everything else directly under Business/ is fair game, because the
#: distinction that matters is not "investor" versus "internal" -- it is
#: whether somebody will read the number as current.
HISTORICAL_PREFIXES: tuple[str, ...] = ("Business/build-stages/",)

#: Top-level Business documents deliberately not scanned, with the reason.
#: Empty today. An entry here is a decision, not a default.
UNSCANNED_WITH_REASON: dict[str, str] = {}


def business_docs_making_claims() -> list[tuple[str, str]]:
    """`(path, label)` for every Business/ doc that states a countable claim
    and is not already covered.

    WHY THIS EXISTS
    ---------------
    INVESTOR_DOCS is a hand-written tuple, and this file already calls the
    pattern out by name: "Sixth instance of a correct guard on too narrow a
    scope." A hand-written list covers what its author remembered on the day
    -- ADR 0151 is the same defect on published READMEs, where the surface
    set was made DERIVED for exactly this reason.

    So the list stays (it is the thing that gets CHECKED, and it carries
    real per-document reasoning), and this asks the complementary question:
    is there a Business document making a claim that nothing is checking?
    Today the answer is no. The point is that it stays no when somebody adds
    the next fundraising doc.
    """
    covered = set(INVESTOR_DOCS) | set(UNSCANNED_WITH_REASON)
    found: list[tuple[str, str]] = []
    business = ROOT / "Business"
    if not business.is_dir():
        return found
    for path in sorted(business.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in covered:
            continue
        if any(rel.startswith(prefix) for prefix in HISTORICAL_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, (pattern, _live, _tol) in CLAIMS.items():
            for match in re.finditer(pattern, text):
                # A dated claim ages honestly -- same rule the scanned
                # documents get, applied to the same window of text.
                window = text[max(0, match.start() - 200) : match.end() + 200]
                if _TIMESTAMP_RE.search(window):
                    continue
                found.append((rel, label))
                break
    return found


def check() -> list[str]:
    problems: list[str] = []

    for rel, label in business_docs_making_claims():
        problems.append(
            f"{rel} states a '{label}' figure and is scanned by nothing. "
            "Add it to INVESTOR_DOCS so the number is checked against the "
            "tree, or to UNSCANNED_WITH_REASON with why it should not be. "
            "A claim nobody checks is how the application draft came to "
            "understate the project by 77%."
        )
    for rel in (*INVESTOR_DOCS, *PUBLIC_MARKETING):
        path = ROOT / rel
        if not path.exists():
            problems.append(
                f"{rel} is listed as an audience-facing document but does not "
                f"exist. "
                "Update INVESTOR_DOCS rather than letting the check quietly "
                "cover one document fewer."
            )
            continue
        text = office_text(path)
        if path.suffix == ".pptx" and len(text.split()) < _MIN_WORDS:
            problems.append(
                f"{rel}: extracted only {len(text.split())} words, below the "
                f"floor of {_MIN_WORDS}. The extraction is broken, not the "
                "deck -- a scan that reads nothing must not pass."
            )
            continue
        for label, (pattern, live_fn, tol) in CLAIMS.items():
            live = live_fn()
            if live < 0:
                problems.append(
                    f"{label}: could not re-derive the live value. The check "
                    "has no evidence, so it has not passed."
                )
                continue
            for match in re.finditer(pattern, text, re.I):
                claimed = int(match.group(1).replace(",", ""))
                window = text[
                    max(0, match.start() - _TIMESTAMP_WINDOW):
                    match.end() + _TIMESTAMP_WINDOW
                ]
                if _TIMESTAMP_RE.search(window):
                    continue
                if abs(claimed - live) > live * tol:
                    problems.append(
                        f"{rel} says {claimed:,} {label}; the repository has "
                        f"{live:,}. Off by {abs(claimed - live) / live:.0%}."
                    )
    return problems


def main() -> int:
    problems = check()
    print(f"Investor documents:      {len(INVESTOR_DOCS)}")
    print(f"Claims checked:          {len(CLAIMS)}")
    print(f"Stale or unverifiable:   {len(problems)}")

    if problems:
        print("\nA document shown to investors disagrees with the repository:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nUpdate the document. Every instance of this found so far has "
            "UNDERSTATED the\nevidence, which is luck rather than policy -- "
            "the same neglect points the other\nway just as easily, and this "
            "is the audience where that matters most."
        )
        return 1

    print("\nOK: investor-facing numbers match the repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
