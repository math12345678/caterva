#!/usr/bin/env python3
"""An image on a public page is a claim no other guard can read.

WHY THIS EXISTS
---------------
`check_public_claims.py` scans the landing pages for text that contradicts
the code. Its file filter ends:

    and not rel.endswith((".png", ".svg", ".ico"))

That exclusion is correct — a PNG is not source — and it leaves a hole
every other guard shares. `check_documented_counts.py`,
`check_public_claims.py`, `check_investor_claims.py` and
`check_no_fabricated_endorsements.py` all read text. A hero image reading
"10,000 universities trust Terrium" would pass every one of them.

Given that this project has already shipped five fabricated testimonials
(ADR 0071) and four stale test counts in text that WAS being read, the
unreadable surface deserves a control rather than an assumption.

WHAT THIS CHECKS
----------------
Every image under a public tree has an entry in `docs/PUBLIC_IMAGES.md`
with a matching content hash.

  * A new image with no entry FAILS.
  * A changed image whose hash no longer matches FAILS.

The second is the one that matters. A new file is conspicuous in a diff; an
existing screenshot edited to add a number is not.

WHAT IT DOES NOT CHECK
----------------------
What the picture says. Nothing here can read a picture, and pretending
otherwise would be worse than the gap. The register carries a per-row state
-- `reviewed` when somebody has actually looked, `hashed` when the image is
only change-detected -- so the file cannot imply an audit that did not
happen. Ten of fourteen are `hashed` today.

This is a weaker guard than the text ones and says so. The real fix, if a
metric ever goes into an image, is to stop putting metrics in images.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "PUBLIC_IMAGES.md"

_BLOCK_START = "PUBLIC-IMAGES-START"
_BLOCK_END = "PUBLIC-IMAGES-END"

#: Below this the scan is broken rather than the tree being empty.
_MIN_IMAGES = 5

#: Trees whose images a member of the public sees.
PUBLIC_TREES: tuple[str, ...] = (
    "mule/",
    "terrium-site/",
    "landing/",
    "Science-Agent-Pipeline/artifacts/terrium-landing/",
)

_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico")

#: The states a row may carry. `hashed` is not a lesser form of `reviewed`
#: -- it is a different fact, and collapsing them would let the register
#: claim an audit nobody performed.
_STATES = {"reviewed", "hashed"}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def public_images() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    return sorted(
        rel for rel in listing
        if rel.startswith(PUBLIC_TREES) and rel.endswith(_SUFFIXES)
        and "node_modules" not in rel
    )


def register() -> dict[str, tuple[str, str]] | None:
    """path -> (hash, state). None when the block is absent."""
    if not REGISTER.exists():
        return None
    text = REGISTER.read_text(encoding="utf-8", errors="replace")
    if _BLOCK_START not in text or _BLOCK_END not in text:
        return None
    start = text.index(_BLOCK_START) + len(_BLOCK_START)
    block = text[start : text.index(_BLOCK_END, start)]
    out: dict[str, tuple[str, str]] = {}
    for line in block.splitlines():
        m = re.match(r"^([0-9a-f]{16})\s+(\w+)\s+(\S+)\s*$", line.strip())
        if m:
            out[m.group(3)] = (m.group(1), m.group(2))
    return out


def check() -> list[str]:
    problems: list[str] = []
    recorded = register()
    if recorded is None:
        return [
            f"docs/PUBLIC_IMAGES.md has no {_BLOCK_START} block. That block is "
            "the register; without it there is nothing to check an image "
            "against, and a missing register must not read as 'no images "
            "need review'."
        ]

    found = public_images()
    if len(found) < _MIN_IMAGES:
        return [
            f"found only {len(found)} public image(s), below the floor of "
            f"{_MIN_IMAGES}. The scan is broken, not the tree."
        ]

    for rel in found:
        if rel not in recorded:
            problems.append(
                f"{rel} is on a public page and not in the register. Look at "
                "it, write down what it depicts, and add a row -- no guard "
                "here can read it for you."
            )
            continue
        want, state = recorded[rel]
        if state not in _STATES:
            problems.append(f"{rel}: unknown state {state!r} (expected one of {_STATES})")
        actual = digest(ROOT / rel)
        if actual != want:
            problems.append(
                f"{rel} changed: register says {want}, file is {actual}. If "
                "the edit added or altered a claim, no other guard in this "
                "repository can see it. Re-review and update the row."
            )

    for rel in recorded:
        if rel not in found:
            problems.append(
                f"{rel} is in the register but not in the tree. Remove the "
                "row rather than leaving a record of a file nobody ships."
            )
    return problems


def main() -> int:
    problems = check()
    recorded = register() or {}
    reviewed = sum(1 for _, s in recorded.values() if s == "reviewed")
    print(f"Public images:           {len(public_images())}")
    print(f"In the register:         {len(recorded)}")
    print(f"Actually reviewed:       {reviewed}")
    print(f"Problems:                {len(problems)}")

    if problems:
        print("\nAn image on a public page is unaccounted for:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    if reviewed < len(recorded):
        print(
            f"\nNote: {len(recorded) - reviewed} image(s) are recorded as "
            "`hashed` -- change-detected\nbut never looked at. That is an "
            "outstanding item, not a failure, and it is\nvisible here so it "
            "does not become invisible."
        )
    print("\nOK: every public image is registered and unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
