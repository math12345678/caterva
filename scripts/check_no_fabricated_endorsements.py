#!/usr/bin/env python3
"""No public page may claim an endorsement that is not on record.

WHAT THIS COMES FROM
--------------------
Until 2026-08-15 the landing page carried a testimonial carousel with five
quotes under the heading "Built for teaching labs. Trusted by educators."
Each was attributed to a named person with a title at a named institution:
Stanford, MIT, Johns Hopkins, UC Berkeley, Cambridge.

Caterva is pre-launch. It has a waitlist and no users. None of those people
had used it, because nobody had.

Every other compliance finding in this repository has been a paperwork
problem — an unattributed dependency, an unrecorded database. This was a
false statement of fact about named third parties, published for commercial
advantage, by a project with a fundraising tracker.

WHAT THIS CHECKS
----------------
Public-facing pages are scanned for the name of a well-known research
institution. Each hit must either

  * appear in `docs/ENDORSEMENTS.md`, which requires a verifiable person,
    their actual words, and written permission; or
  * sit in a context this file records as legitimate — the MIT *licence*,
    an author's own affiliation, a citation.

Anything else FAILS. The default is "an institution named in marketing copy
is a claim about that institution", because that is what a reader takes
from it.

WHAT IT DOES NOT CHECK
----------------------
Whether a recorded endorsement is genuine. Nothing mechanical can do that;
`docs/ENDORSEMENTS.md` demands the evidence and a person has to supply it.
This checks that the claim and the record exist together, which is the part
that failed.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENDORSEMENTS = ROOT / "docs" / "ENDORSEMENTS.md"

#: Below this the scan is broken rather than the pages being clean.
_MIN_FILES = 10

#: Directories whose contents are shown to the public.
PUBLIC_TREES: tuple[str, ...] = (
    "Science-Agent-Pipeline/artifacts/caterva-landing/src",
    "Science-Agent-Pipeline/artifacts/caterva-landing/index.html",
    "caterva-site",
    "landing",
    "src/web",
)

#: Institution names that read as an endorsement when they appear in
#: promotional copy. Not exhaustive and not meant to be -- it covers the
#: names actually used, plus the obvious neighbours someone would reach for.
INSTITUTIONS: tuple[str, ...] = (
    "Stanford", "MIT", "Johns Hopkins", "UC Berkeley", "Berkeley",
    "Cambridge", "Oxford", "Harvard", "Yale", "Caltech", "Princeton",
    "ETH Zurich", "Max Planck", "CERN", "NASA",
)

#: Substrings that make an institution name legitimate rather than a claim.
#: Each needs a reason: an exemption nobody can evaluate becomes a hole.
LEGITIMATE_CONTEXTS: dict[str, str] = {
    "MIT License": "the SPDX licence identifier, not the university",
    "MIT-0": "an SPDX licence identifier",
    "licence": "a sentence about licensing",
    "license": "a sentence about licensing",
    "University of Washington": (
        "libRoadRunner's copyright holder -- an attribution Caterva is "
        "obliged to make, and the opposite of a claimed endorsement"
    ),
    "not Tellurium": "the non-affiliation notice, which disclaims rather than claims",
    "unaffiliated": "the non-affiliation notice",
    "Cambridge Cluster Database": (
        "a real, citable database of Lennard-Jones cluster minima that the "
        "molecular-dynamics domain checks its results against. Citing a "
        "source is the opposite of claiming its endorsement, and flagging "
        "it would train people to ignore this guard"
    ),
}

#: Contexts that must be matched CASE-SENSITIVELY and anchored, because a
#: case-insensitive substring would exempt the very thing being checked.
#:
#: `Source:` at the start of a line is a prose citation. `source: "Stanford
#: University"` is a field in a testimonial object. A case-insensitive
#: check for "Source:" matches both -- and the first version of this file
#: did exactly that, which meant the guard would NOT have caught the five
#: fabricated testimonials it was written for. An exemption added to stop
#: crying wolf had silently switched off the alarm. Found by the replay
#: test, not by reading.
LEGITIMATE_PATTERNS: dict[str, str] = {
    r"^\s*Source: [A-Z]": (
        "a prose citation line -- capital S, start of line, followed by an "
        "author or title. Distinct from a lowercase `source:` object field, "
        "which is what a testimonial record looks like"
    ),
}


def _public_files() -> list[pathlib.Path]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    out = []
    for rel in listing:
        if not any(rel.startswith(tree) for tree in PUBLIC_TREES):
            continue
        if "node_modules" in rel or rel.endswith((".png", ".svg", ".ico", ".json")):
            continue
        out.append(ROOT / rel)
    return out


_BLOCK_START = "REAL-ENDORSEMENTS-START"
_BLOCK_END = "REAL-ENDORSEMENTS-END"


def _recorded() -> str | None:
    """Only the delimited block, never the whole document.

    THE HOLE THIS CLOSES
    --------------------
    The first version returned the entire file. `docs/ENDORSEMENTS.md`
    contains a table of the fabrications that were REMOVED, listing
    Stanford, MIT, Johns Hopkins and UC Berkeley -- and the record-match
    (`"| Stanford" in recorded`) matched those rows. So the document that
    exists to say those endorsements were fake was excusing them from the
    check. Verified, not theorised: four of the five institutions were
    already exempt on any public page.

    Returns None when the block is absent, which the caller treats as a
    failure rather than as an empty allowlist.
    """
    if not ENDORSEMENTS.exists():
        return None
    text = ENDORSEMENTS.read_text(encoding="utf-8", errors="replace")
    if _BLOCK_START not in text or _BLOCK_END not in text:
        return None
    start = text.index(_BLOCK_START) + len(_BLOCK_START)
    return text[start : text.index(_BLOCK_END, start)]


def find_claims(files: list[pathlib.Path], recorded: str) -> list[str]:
    """Institution names in public copy with no matching record."""
    problems: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A path outside the repository should be reported, not crash the
        # reporter. The tests hand this function files in a tmp_path to
        # replay the real fabricated testimonial, and `relative_to` raises
        # on anything not under ROOT -- which would make the guard
        # untestable on the exact input it was written for.
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(ctx.lower() in line.lower() for ctx in LEGITIMATE_CONTEXTS):
                continue
            if any(re.search(pat, line) for pat in LEGITIMATE_PATTERNS):
                continue
            for name in INSTITUTIONS:
                if not re.search(rf"\b{re.escape(name)}\b", line):
                    continue
                # A recorded endorsement names the institution in
                # docs/ENDORSEMENTS.md's own table of permissions.
                if f"| {name}" in recorded or f"({name})" in recorded:
                    continue
                problems.append(f"{rel}:{line_no} names {name!r}: {line.strip()[:90]}")
    return problems


def main() -> int:
    files = _public_files()
    if len(files) < _MIN_FILES:
        print(
            f"FAIL: found only {len(files)} public-facing file(s), below the "
            f"floor of {_MIN_FILES}.\n"
            "      The scan is broken, not the pages. A check that examines "
            "nothing must not\n      report that nothing is wrong."
        )
        return 1

    if not ENDORSEMENTS.exists():
        print(
            "FAIL: docs/ENDORSEMENTS.md is missing. It records which "
            "endorsements are real\n      and what permission backs them. "
            "Without it there is nothing to check a claim\n      against, and "
            "'no file' must not mean 'no rules'."
        )
        return 1

    recorded = _recorded()
    if recorded is None:
        print(
            f"FAIL: docs/ENDORSEMENTS.md has no {_BLOCK_START} block.\n"
            "      That block is the allowlist. Without it there is nothing "
            "to check a claim\n      against, and a missing allowlist must "
            "not read as 'everything is allowed'."
        )
        return 1

    problems = find_claims(files, recorded)

    print(f"Public files scanned:    {len(files)}")
    print(f"Unbacked claims:         {len(problems)}")

    if problems:
        print("\nAn institution is named in public copy with no record:\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nNaming an institution in marketing implies its endorsement. "
            "Record it in\ndocs/ENDORSEMENTS.md with the person, their actual "
            "words and written permission,\nor remove it. Five invented "
            "testimonials attributed to Stanford, MIT, Johns\nHopkins, "
            "Berkeley and Cambridge were live on this site until 2026-08-15."
        )
        return 1

    print("\nOK: no public page claims an endorsement that is not on record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
