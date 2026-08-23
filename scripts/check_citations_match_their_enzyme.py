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

AND THEN A THIRD LAYER
----------------------
Building the above surfaced the next one down. ADR 0144 closed "the
reference does not exist"; the check below closes "the reference is for
another enzyme"; `value_mismatches()` closes "the reference is real, the
enzyme is right, and the page does not report that number".

That last one was live on the front page while this file was being written:

    km    0.14 mM    brenda_exact  BRENDA ref 740253

`740253` is a real lactate dehydrogenase reference. `0.14` occurs nowhere in
that fixture — the rows under it read 10.73 and 21.78 mM. A reader who
followed the citation, which is the entire behaviour this tool exists to
make possible, would have found a different number.

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



#: A documented value/unit followed by the reference it is attributed to.
VALUE_AND_REF = re.compile(
    r"([\d.]+)\s*(mM/s|mM|uM|µM|1/s)\s+.*?\bref(?:erence)?\s+(\d{6,})",
    re.IGNORECASE,
)

#: Markers that the printed number was COMPUTED, not quoted off the page.
#:
#: `vmax 0.25 mM/s  brenda_cross_species -> kcat x [E]0  BRENDA ref 741355`
#: is honest: the reference supports the kcat, and the Vmax is that kcat
#: times an enzyme concentration the student chose (ADR 0142). Demanding
#: that 0.25 appear on the BRENDA page would fail a line that is telling the
#: truth, and a guard that fires on the correct case gets suppressed
#: (ADR 0028).
DERIVED_MARKERS = ("→", "->", "kcat x", "kcat ×")


def value_mismatches() -> tuple[list[str], int, int]:
    """Documented values that the page they cite does not report.

    THE THIRD LAYER.
    ----------------
    ADR 0144 closed "the reference does not exist". ADR 0161 closed "the
    reference is for another enzyme". This closes "the reference is real,
    the enzyme is right, and the page does not report that number".

    Found on the front page, three times, the day it was written:

        km    0.14 mM    brenda_exact  BRENDA ref 740253

    `740253` is a real reference on the lactate dehydrogenase page. The
    string `0.14` does not occur anywhere in that fixture; the rows under
    that reference read 10.73 and 21.78 mM. A reader who followed the
    citation — which is the entire behaviour this tool exists to make
    possible — would have found a different number and no way to tell which
    was wrong.

    Returns (failures, checked, skipped_as_derived).
    """
    pages: dict[str, str] = {
        path.name: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(FIXTURE_DIR.glob("*.html"))
    }
    failures: list[str] = []
    checked = 0
    derived = 0

    for relative in surfaces():
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for match in VALUE_AND_REF.finditer(line):
                value, unit, ref = match.groups()
                if any(marker in line for marker in DERIVED_MARKERS):
                    derived += 1
                    continue
                citing = [n for n, t in pages.items() if re.search(r"\b" + ref + r"\b", t)]
                if not citing:
                    # check_documented_citations_are_real owns this case.
                    continue
                checked += 1
                if not any(value in pages[n] for n in citing):
                    failures.append(
                        f"{relative}:{number} shows {value} {unit} citing ref "
                        f"{ref}, and {value} does not occur on the page(s) "
                        f"that reference appears on ({', '.join(citing)}).\n"
                        "      A real reference for a number it does not "
                        "report is the third and quietest way a citation can "
                        "be wrong."
                    )
    return failures, checked, derived


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
    value_failures, value_checked, derived = value_mismatches()

    print(f"Documented citations checked against their enzyme: {checked}")
    print(f"Documented values checked against the cited page:  {value_checked}"
          + (f"  ({derived} derived, so not quoted off a page)" if derived else ""))
    if unchecked:
        print(f"Not checked (no enzyme named nearby):            {len(unchecked)}")
        for line in unchecked:
            print(f"  {line}")
        print(
            "\n  Not a failure, and not a pass either. Name the enzyme within "
            f"{CONTEXT_LINES} lines\n  of the citation and this guard covers it."
        )

    if failures or value_failures:
        if failures:
            print(f"\nFAIL: {len(failures)} citation(s) attached to the wrong enzyme.\n")
            for problem in failures:
                print(f"  {problem}\n")
        if value_failures:
            print(f"\nFAIL: {len(value_failures)} value(s) the cited page does not report.\n")
            for problem in value_failures:
                print(f"  {problem}\n")
        return 1

    print("\nOK: every citation this guard could attribute names the right")
    print("    enzyme, and every quoted value occurs on the page it cites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
