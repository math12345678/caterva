#!/usr/bin/env python3
"""A real reference, printed under the wrong enzyme.

WHAT HAPPENED
-------------
ADR 0144 found that `BRENDA ref 649716` — an **acetylcholinesterase**
reference — was printed on the README's front page under a **lactate
dehydrogenase** example. A real id, a real paper, and the wrong protein.

`check_documented_citations_are_real.py` closed the flagrant half: every
documented ref must occur in a committed fixture, so `ref 12345`, which
existed nowhere, cannot come back. It said plainly that it did not close the
subtle half:

    That the reference belongs to the enzyme in the example. Deciding that
    would mean parsing which fixture the surrounding prose is about, and a
    check that guesses is a check that cries wolf.

That was the right call with the information available. This guard closes it
anyway, because the information turned out to be there.

WHY IT IS NOT A GUESS
---------------------
Measured across the eleven committed fixtures: **no reference id occurs
under more than one EC number.** The mapping from a ref to the enzyme whose
page it appears on is one-to-one, so "which enzyme does this reference
belong to" has a definite offline answer.

What remained was the other side: which enzyme is the surrounding prose
about. That is not inferred either. `ENZYME_NAMES` below is an explicit
table of the names the documentation actually uses, each with its EC, and a
citation is only checked when one of those names appears within
`CONTEXT_LINES` above it. Anything else is reported as **not checked** and
counted — never silently passed.

`scripts/evidence_table.py` listed this as needing live BRENDA one pass
before this was written. That was wrong, and the correction is the reason
this file exists.

THREE STATES
------------
    prose names a known enzyme, ref's fixture agrees   -> checked, OK
    prose names a known enzyme, ref's fixture differs  -> FAIL
    prose names no enzyme this table knows             -> not checked

The third is printed with a count. A guard that checked two of eight
citations and reported "OK" would be the shape this whole repository exists
to refuse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "Tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_documented_citations_are_real import surfaces  # noqa: E402

#: Enzyme names as the documentation writes them, with their EC number.
#:
#: Explicit rather than resolved through UniProt: this must run offline and
#: in CI, and a network lookup would make the guard's verdict depend on a
#: service being up. Short on purpose — an entry here is a claim that the
#: documentation uses this exact name for this exact enzyme.
ENZYME_NAMES: dict[str, str] = {
    "lactate dehydrogenase": "1.1.1.27",
    "acetylcholinesterase": "3.1.1.7",
    "hexokinase": "2.7.1.1",
    "trypsin": "3.4.21.4",
    "chymotrypsin": "3.4.21.1",
}

#: How far above a citation to look for the enzyme it is about.
#:
#: Twelve, because the README's provenance example names the enzyme in the
#: command and prints the citations in the output block below it, and that
#: is eleven lines. Not larger: a window that reaches the previous section
#: would attribute a citation to whatever enzyme was last mentioned on the
#: page, which is the guessing this guard is built to avoid.
CONTEXT_LINES = 12

CITATION = re.compile(r"\bref(?:erence)?\s+(\d{6,})\b", re.IGNORECASE)
EC_NUMBER = re.compile(r"\b\d+\.\d+\.\d+\.\d+\b")


def reference_owners() -> dict[str, set[str]]:
    """ref id -> the EC numbers of the fixtures it appears in."""
    owners: dict[str, set[str]] = {}
    for path in sorted(FIXTURE_DIR.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        ecs = set(EC_NUMBER.findall(text))
        if not ecs:
            # A fixture with no EC on the page cannot attribute anything.
            # Skipped rather than treated as evidence of absence.
            continue
        for ref in set(re.findall(r"\b(\d{6,})\b", text)):
            owners.setdefault(ref, set()).update(ecs)
    return owners


def enzyme_above(lines: list[str], index: int) -> tuple[str, str] | None:
    """The nearest enzyme named in the CONTEXT_LINES above, or None.

    Nearest wins. A block that mentions two enzymes is answered by the one
    closest to the citation, which is what a reader does.
    """
    start = max(0, index - CONTEXT_LINES)
    window = lines[start : index + 1]
    for line in reversed(window):
        lowered = line.lower()
        for name, ec in ENZYME_NAMES.items():
            if name in lowered:
                return name, ec
    return None


def check() -> tuple[list[str], int, list[str]]:
    """Returns (failures, checked_count, unchecked descriptions)."""
    owners = reference_owners()
    if not owners:
        return (
            [f"No reference ids found in {FIXTURE_DIR}; this guard has no "
             "evidence to work from and will not report success."],
            0, [],
        )

    failures: list[str] = []
    unchecked: list[str] = []
    checked = 0

    for relative in surfaces():
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            for match in CITATION.finditer(line):
                ref = match.group(1)
                owning = owners.get(ref)
                if not owning:
                    # Handled by check_documented_citations_are_real, which
                    # fails on a ref no fixture contains. Not repeated here:
                    # two guards reporting one defect is two things to fix.
                    continue
                named = enzyme_above(lines, index)
                if named is None:
                    unchecked.append(
                        f"{relative}:{index + 1} ref {ref} — no enzyme this "
                        f"guard knows is named within {CONTEXT_LINES} lines above"
                    )
                    continue
                name, ec = named
                checked += 1
                if ec not in owning:
                    failures.append(
                        f"{relative}:{index + 1} cites ref {ref} under "
                        f"\"{name}\" (EC {ec}), but that reference appears "
                        f"only on the BRENDA page(s) for EC "
                        f"{', '.join(sorted(owning))}.\n"
                        "      A real reference for the wrong protein is the "
                        "defect ADR 0144 found on this project's front page."
                    )
    return failures, checked, unchecked


def _selftest() -> int:
    """Drives both verdicts on constructed text, not on the tree.

    A guard exercised only against a clean repository passes while doing
    nothing, which is the shape it exists to catch.
    """
    failures = 0
    owners = reference_owners()

    ldh_ref = next(
        (r for r, e in owners.items() if e == {"1.1.1.27"}), None
    )
    ache_ref = next(
        (r for r, e in owners.items() if e == {"3.1.1.7"}), None
    )
    if not ldh_ref or not ache_ref:
        print("  [SELFTEST FAILED] fixtures no longer provide one LDH and "
              "one AChE reference to build the cases from")
        return 1

    good = ["Resolved for lactate dehydrogenase", "", f"  km  BRENDA ref {ldh_ref}"]
    bad = ["Resolved for lactate dehydrogenase", "", f"  km  BRENDA ref {ache_ref}"]

    if enzyme_above(good, 2) == ("lactate dehydrogenase", "1.1.1.27"):
        print("  [ok] finds the enzyme named above a citation")
    else:
        print("  [SELFTEST FAILED] did not find the enzyme above the citation")
        failures += 1

    if enzyme_above(["nothing relevant", "", "ref 999999"], 2) is None:
        print("  [ok] reports no enzyme rather than picking one")
    else:
        print("  [SELFTEST FAILED] invented an enzyme from unrelated text")
        failures += 1

    # The historical defect itself: an AChE reference under an LDH heading.
    name, ec = enzyme_above(bad, 2)  # type: ignore[misc]
    if ec not in owners[ache_ref]:
        print(f"  [ok] would flag ref {ache_ref} (AChE) cited under {name}")
    else:
        print("  [SELFTEST FAILED] the historical ADR 0144 defect reads as OK")
        failures += 1

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed: both verdicts reachable.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    failures, checked, unchecked = check()

    print(f"Documented citations checked against their enzyme: {checked}")
    if unchecked:
        print(f"Not checked (no enzyme named nearby):            {len(unchecked)}")
        for line in unchecked:
            print(f"  {line}")
        print(
            "\n  Not a failure, and not a pass either. Name the enzyme within "
            f"{CONTEXT_LINES} lines\n  of the citation and this guard covers it."
        )

    if failures:
        print(f"\nFAIL: {len(failures)} citation(s) attached to the wrong enzyme.\n")
        for problem in failures:
            print(f"  {problem}\n")
        return 1

    print("\nOK: every citation this guard could attribute names the right enzyme.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
