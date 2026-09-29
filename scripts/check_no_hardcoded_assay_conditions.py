#!/usr/bin/env python3
"""No source file may state an assay temperature or pH it did not measure.

WHY THIS EXISTS
---------------
Every entry point in this repository used to open its conditions object with
the same three words:

    conditions: { temperature: 37, pH: 7.4 }

Nine call sites. The web server, three CLI paths, the pipeline itself, the
batch processor, the parameter sweep, and both model-comparison calls. One
literal, copied nine times, sourced nowhere.

Three things were wrong with it, in increasing order of seriousness.

It is a hardcoded value, which this project forbids on principle.

It is a *human body* condition. A student modelling a thermophile, a plant
enzyme or a lysosomal protease got 37 C and pH 7.4 without being asked --
the same silent mammalian assumption ADR 0024 exists to prevent, in
different clothes.

And it made a shipped check unfalsifiable. `AssumptionValidator` warns when
a temperature falls outside 4-45 C and when a pH falls outside 5-9. 37 and
7.4 are the dead centre of both ranges. Those two warnings existed, were
unit-tested, and could not fire from any path a user could reach.

The warning text is the part worth remembering:

    "...confirm the kinetic constants were measured at this temperature."

That confirmation is the one Lisa Jeske (BRENDA/DSMZ) asked for, in the
reply that warned about mixing conditions into "fantasy numbers". It was
unreachable, because the temperature was a fiction.

WHY A SCRIPT AND NOT A TEST
---------------------------
Because a test did not catch it, and I have the run to prove it.

`src/validation/__tests__/runConditions.test.ts` covers `deriveRunConditions`
and `AssumptionValidator` thoroughly -- seventeen tests, five mutations
caught. A sixth mutation re-inserted `temperature: 37, pH: 7.4` into the
pipeline's conditions object, restoring the original defect exactly, and all
seventeen passed.

The tests test the functions. The defect was never in a function. It was in
what nine call sites chose to pass, and no unit test sees a call site.

That is the same shape as ADR 0027's parity test, which pinned two
implementations against a shared fixture and could not see that its two
callers passed different arguments. And it is the shape of this file's own
header comment, which I wrote -- "testing a function is not testing the call
site" -- immediately before making the mistake it describes.

WHAT IT FORBIDS
---------------
A numeric literal assigned to a `temperature`, `temperatureC` or `pH` key in
TypeScript or Python source under the scanned roots.

Not a range check, not a threshold on the value. Any literal. 25 C is no
better sourced than 37 C, and a guard that permitted "reasonable" values
would need a definition of reasonable, which would itself be unsourced.

WHAT IT PERMITS
---------------
Test fixtures, which must state conditions to have anything to assert; the
4-45 and 5-9 range bounds themselves, which are cited in the validator and
are bounds rather than assumed values; and this file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Roots that ship. Tests and examples are excluded below by path, not by
# being left out here, so a new test directory is not silently unscanned.
SCAN_ROOTS = ["src", "scripts", "Tests"]

SUFFIXES = {".ts", ".tsx", ".py"}

# `temperature: 37`, `temperatureC=25.0`, `"pH": 7.4`, `pH = 7`.
# Deliberately matches a bare integer as well as a decimal: the original
# defect was `temperature: 37`, with no decimal point.
ASSIGNMENT = re.compile(
    r"""["']?\b(temperature|temperatureC|temperature_c|ph|pH)\b["']?\s*[:=]\s*(-?\d+(?:\.\d+)?)\b"""
)

# Paths where stating a condition is the point.
EXEMPT_SUBSTRINGS = (
    "__tests__",
    "/tests/",
    "test_",
    "_test.",
    ".test.",
    ".spec.",
    "/examples/",
    "check_no_hardcoded_assay_conditions.py",
    # Fixture corpora: recorded BRENDA rows, which REPORT a temperature
    # because the assay had one. A recorded measurement is the opposite of
    # an assumed condition.
    "/fixtures/",
    "/corpus/",
)

# Literals that are bounds, not values. Each must be justified in the source
# beside it; the guard does not check that, a reader does.
BOUND_LITERALS = {
    # AssumptionValidator's mesophilic range, cited in place as a
    # convention rather than a measurement.
    ("temperature", "4"),
    ("temperature", "45"),
    ("ph", "5"),
    ("ph", "9"),
    ("pH", "5"),
    ("pH", "9"),
}


def offending_lines(text: str) -> list[tuple[int, str, str, str]]:
    """`(line number, line, key, literal)` for each forbidden assignment."""
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # Comments describing the defect are not the defect. This guard's own
        # rationale, and the ADRs, quote `temperature: 37` on purpose.
        if stripped.startswith(("//", "*", "#", "/*")):
            continue
        for match in ASSIGNMENT.finditer(line):
            key, literal = match.group(1), match.group(2)
            if (key, literal) in BOUND_LITERALS:
                continue
            findings.append((number, stripped, key, literal))
    return findings


_MIN_FILES = 60
#: Fewest files this scan must see before "clean" means anything.
#:
#: Measured, not guessed: run in an empty tree this guard printed its success
#: line having read nothing. The claim is a universal over the files scanned,
#: and over zero files every universal is true -- so a reader cannot tell a
#: clean repository from a scan that has stopped reaching its input.
#:
#: The floor is this project's established remedy, not an invention here:
#: `check_public_images_reviewed` refuses with "found only 0 public image(s),
#: below the floor of 5. The scan is broken, not the pages."
#:
#: Set well below the real count so ordinary deletion does not trip it. It is
#: a smoke alarm for a moved root or a glob that no longer matches, not a
#: coverage target.


def scan() -> list[str]:
    scan.files_read = 0
    findings = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            as_posix = path.as_posix()
            if any(part in as_posix for part in EXEMPT_SUBSTRINGS):
                continue
            if "node_modules" in as_posix:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scan.files_read += 1
            for number, line, key, literal in offending_lines(text):
                findings.append(
                    f"{path.relative_to(REPO)}:{number}: {key} = {literal}\n"
                    f"      {line}"
                )
    return findings


def selftest() -> int:
    """Prove the matcher can fail.

    ADR 0034's lesson: a branch no input can reach is not a check. The
    original nine call sites are gone, so on a clean tree this guard reports
    zero findings forever -- and a broken matcher would report zero too.
    """
    must_flag = [
        "        conditions: { temperature: 37, pH: 7.4 }",
        "  temperature: 37,",
        '  {"temperature": 25.0}',
        "temperature_c = 30",
        "pH=7.4",
        "        temperatureC: 37,",
    ]
    must_pass = [
        "// conditions: { temperature: 37, pH: 7.4 }  <- the old defect",
        "  temperature?: number;",
        "  if (conditions.temperature < 4 || conditions.temperature > 45) {",
        "  const t = conditions.temperature;",
        "# temperature: 37 was here before ADR 0055",
    ]

    failures = []
    for line in must_flag:
        if not offending_lines(line):
            failures.append(f"should have flagged, did not: {line!r}")
    for line in must_pass:
        found = offending_lines(line)
        if found:
            failures.append(f"should have passed, flagged {found[0][2]}: {line!r}")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(must_flag)} forbidden form(s) flagged, "
        f"{len(must_pass)} permitted form(s) passed."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="check the matcher itself against known-bad and known-good lines",
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    findings = scan()
    if findings:
        print(f"Hardcoded assay conditions ({len(findings)}):\n")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nA simulation has no temperature of its own. The ODE takes none,"
            "\nand a Km's temperature dependence is already inside the measured"
            "\nKm. The only meaningful temperature is the one the constants were"
            "\nMEASURED at -- a fact about the papers, not a setting.\n"
            "\nUse deriveRunConditions() in src/validation/runConditions.ts,"
            "\nwhich reads it off the parameters' provenance and reports"
            "\nagreed / conflicting / not_reported rather than inventing one.\n"
            "\nSee ADR 0055."
        )
        return 1

    if scan.files_read < _MIN_FILES:
        print(
            f"FAIL: read only {scan.files_read} source file(s), below the "
            f"floor of {_MIN_FILES}.\n"
            "\nThe scan is broken, not the sources. Over zero files "
            "\"no file hardcodes an assay condition\" is true and means "
            "nothing."
        )
        return 1

    print(
        f"OK: {scan.files_read} source file(s) read; none states an assay "
        "temperature or pH it did not measure."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())