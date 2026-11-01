#!/usr/bin/env python3
"""Every file that names a licence must name the same one.

WHY THIS EXISTS
---------------
For months this repository said three different things about its own terms:

    LICENSE       "all rights reserved, no permission granted to copy"
    CITATION.cff  license: LicenseRef-Caterva-Proprietary
    package.json  "license": "MIT"

Nobody noticed, because nothing read more than one of them at a time. A
project whose entire claim is that every number is traceable to a source was
shipping a contradiction about the one fact a user checks first.

It surfaced only because a BRENDA curator linked the CC BY licence page in
an unrelated reply, and reading it forced someone to open LICENSE.

WHAT IT CHECKS
--------------
1. Every declared licence identifier agrees.
2. LICENSE actually contains the licence it claims to be.
3. The third-party carve-out is still present. Apache 2.0 does not conflict
   with CC BY 4.0, so the carve-out is no longer strictly load-bearing — but
   it is the only place a reader learns that the BRENDA fixtures are not
   Apache-licensed, and deleting it would quietly remove that.
4. NOTICE exists and credits BRENDA. Apache 2.0 §4(d) makes NOTICE the
   mechanism by which the CC BY attribution reaches downstream users; an
   empty or missing NOTICE breaks the chain silently.

WHAT IT DOES NOT CHECK
----------------------
Whether Apache 2.0 is the right licence. That is a decision for a lawyer at
incorporation, and a script that appeared to validate it would be worse than
no script — the "check that cannot fail" failure, applied to a legal
question.

Exit 0 = consistent. Exit 1 = a real disagreement.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The licence this repository is under. Changing it here is not enough --
#: every file below must change too, which is the entire point.
EXPECTED = "Apache-2.0"

#: A phrase that must appear in LICENSE for it to really BE that licence.
#: A file can say "Apache-2.0" in a comment while containing MIT's text.
LICENCE_BODY_MARKERS = {
    "Apache-2.0": [
        "Apache License",
        "Version 2.0, January 2004",
        "Grant of Patent License",
    ],
    "MIT": ["Permission is hereby granted, free of charge"],
}

#: Phrases that contradict any permissive licence. Present in the file that
#: caused this whole problem.
CONTRADICTIONS = [
    "all rights reserved, no permission granted",
    "no permission granted to copy",
    "LicenseRef-Caterva-Proprietary",
]


def tracked(pattern: str) -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", pattern], cwd=REPO, capture_output=True, text=True
    )
    return [REPO / line for line in out.stdout.split() if line]


def declared_licences() -> list[tuple[pathlib.Path, str]]:
    """(file, identifier) for every file that declares one."""
    found: list[tuple[pathlib.Path, str]] = []

    for path in tracked("*package.json"):
        if "node_modules" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        licence = data.get("license")
        if isinstance(licence, str):
            found.append((path, licence))

    for path in tracked("*.cff"):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^license:\s*(\S+)\s*$", text, re.M)
        if match:
            found.append((path, match.group(1).strip('"\'')))

    return found


def main() -> int:
    problems: list[str] = []
    checked = 0

    # --- 1. identifiers agree ------------------------------------------
    declarations = declared_licences()
    for path, licence in declarations:
        checked += 1
        if licence != EXPECTED:
            problems.append(
                f"{path.relative_to(REPO)} declares license '{licence}', "
                f"but the repository is {EXPECTED}. Two files claiming "
                "different terms is the exact defect this guard was written "
                "for."
            )

    if not declarations:
        problems.append(
            "No file declares a licence at all. Either the guard's search is "
            "wrong or the declarations were deleted; both are failures."
        )

    # --- 2. LICENSE contains the licence it claims ---------------------
    licence_file = REPO / "LICENSE"
    if not licence_file.exists():
        problems.append("LICENSE is missing.")
    else:
        body = licence_file.read_text(encoding="utf-8", errors="replace")
        checked += 1
        for marker in LICENCE_BODY_MARKERS.get(EXPECTED, []):
            if marker not in body:
                problems.append(
                    f"LICENSE does not contain {EXPECTED} marker text "
                    f"{marker!r}. A file can name a licence it does not "
                    "contain; only the body is binding."
                )

        for phrase in CONTRADICTIONS:
            # The historical account of the breach quotes the old wording,
            # so a bare substring search would flag the explanation itself.
            # Only unquoted occurrences count.
            for line in body.splitlines():
                stripped = line.strip()
                if phrase.lower() in stripped.lower() and not (
                    stripped.startswith('"')
                    or '"' in stripped
                    or stripped.startswith("*")
                    or stripped.startswith("#")
                ):
                    problems.append(
                        f"LICENSE still asserts {phrase!r} outside a quotation: "
                        f"{stripped[:90]!r}"
                    )

        # --- 3. the third-party carve-out survives ---------------------
        checked += 1
        if "THIRD-PARTY DATA IS NOT COVERED" not in body:
            problems.append(
                "LICENSE has lost its third-party carve-out. It is the only "
                "place a reader learns that Tests/fixtures/brenda_*.html is "
                "CC BY 4.0 rather than Apache 2.0."
            )

    # --- 4. NOTICE credits BRENDA --------------------------------------
    notice = REPO / "NOTICE"
    checked += 1
    if not notice.exists():
        problems.append(
            "NOTICE is missing. Apache 2.0 §4(d) makes it the mechanism that "
            "carries BRENDA's CC BY attribution downstream; without it the "
            "attribution stops at this repository."
        )
    else:
        notice_text = notice.read_text(encoding="utf-8", errors="replace")
        for required in ["BRENDA", "CC BY", "DSMZ"]:
            if required not in notice_text:
                problems.append(f"NOTICE does not mention {required!r}.")

    # --- 4. the INBOUND licence is stated somewhere a contributor looks --
    #
    # LICENSE names this as one of the three reasons for relicensing:
    #
    #     "An all-rights-reserved repository cannot accept outside
    #      contributions cleanly -- there is no inbound licence for the
    #      contribution to arrive under."
    #
    # The problem was named and the answer was never written down. A
    # contributor who went looking found a paragraph explaining why the old
    # state was bad and nothing saying what the current state is.
    #
    # Apache-2.0 section 5 supplies the answer implicitly, which is exactly
    # why it needs saying explicitly: an implicit term is one a contributor
    # has to already know to find. Somebody deciding whether to spend a
    # weekend on a pull request is deciding what happens to a weekend of
    # their work.
    #
    # Checked here rather than in a new guard because "the repository is
    # unambiguous about its own terms" is this file's subject, and inbound
    # terms are terms.
    inbound = REPO / "docs" / "INBOUND_LICENSE.md"
    if not inbound.exists():
        problems.append(
            "docs/INBOUND_LICENSE.md is missing. Nothing states what a "
            "contribution arrives under, which LICENSE itself names as the "
            "defect that made the old licence unworkable."
        )
    else:
        checked += 1
        inbound_text = inbound.read_text(encoding="utf-8", errors="replace")
        for required, why in [
            ("Apache-2.0", "the inbound licence itself"),
            ("Section 5", "the clause that supplies it"),
            ("copyright", "that the contributor keeps theirs"),
            ("university", "the student IP question, which is the one most "
                           "likely to cause a real problem"),
        ]:
            if required.lower() not in inbound_text.lower():
                problems.append(
                    f"docs/INBOUND_LICENSE.md does not mention {required!r} "
                    f"({why})."
                )

    contributing = REPO / "CONTRIBUTING.md"
    if contributing.exists():
        checked += 1
        contributing_text = contributing.read_text(encoding="utf-8", errors="replace")
        if "INBOUND_LICENSE" not in contributing_text:
            problems.append(
                "CONTRIBUTING.md does not link docs/INBOUND_LICENSE.md. A "
                "statement of inbound terms that contributors are not sent "
                "to is one nobody reads."
            )

    # --- report ---------------------------------------------------------
    print(f"Checked {checked} licence declaration(s) across "
          f"{len(declarations)} manifest file(s), LICENSE and NOTICE.")
    for path, licence in sorted(declarations):
        print(f"  {path.relative_to(REPO)}: {licence}")

    if problems:
        print()
        print(f"Licence declarations disagree ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print(
            "A project about provenance cannot be unclear about its own "
            "terms. Fix every file, not the one the guard names first."
        )
        return 1

    print(f"OK: every declaration says {EXPECTED}, LICENSE contains it, "
          "the third-party carve-out is intact, and NOTICE credits BRENDA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
