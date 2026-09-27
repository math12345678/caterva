#!/usr/bin/env python3
"""The importable package is `caterva`. The product is `Caterva`. One r, two r.

WHY THIS EXISTS
---------------
This repository ships two spellings of its own name, and they are not
interchangeable:

    Caterva      the Python package you import  -- caterva/, python -m caterva.cli
    Caterva     the product, the repo, the org, the site, the docs

Both are correct in their place. `docs/RENAME_PLAN.md` counts 767
occurrences of the first and 1,470 of the second across 452 tracked files.

For anyone already here that is a quirk. For a newcomer it is a trap with no
signpost: `import Caterva` is the spelling they have read everywhere, it
raises `ModuleNotFoundError: No module named 'Caterva'`, and nothing in the
error or the repository explains that the package deliberately drops a
letter. The natural conclusion is that their environment is broken -- which
sends them to `make doctor`, which will report a perfectly healthy install.

**A newcomer who hits an unexplained failure assumes they are lost.** That
is the cost this guard exists to prevent, and it is the same reason
`check_doc_paths_resolve.py` exists.

WHAT IT CHECKS
--------------
No Python file imports the two-r spelling. `import Caterva`,
`from Caterva.core import x`, `importlib.import_module("Caterva")` are all
errors, always -- there is no module by that name and there never has been.

This is not a style rule. Every match is a guaranteed runtime failure.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
**Prose.** "Caterva resolves parameters from the literature" is correct and
appears thousands of times. A guard that policed the product name in
sentences would fire constantly and be muted within a day.

**Paths in documentation.** `Caterva/` as a repository-root reference is
correct in some contexts (the folder on a contributor's disk is often called
`Caterva`) and wrong in others. Deciding which needs to read intent, and a
guard that guesses at intent produces exactly the false positives that teach
people to ignore it. `check_doc_paths_resolve.py` covers the case that is
mechanically checkable: a path that does not exist.

**The rename question itself.** Whether the product should be called
something else at all is a trademark judgement for a lawyer, and
`docs/RENAME_PLAN.md` holds the engineering cost. This guard is agnostic:
it enforces that the import spelling matches the package on disk, whatever
either is called next year.

WHY A GUARD AND NOT A DOCUMENTED WARNING
----------------------------------------
Both. `START_HERE.md` warns, because a person who has not yet made the
mistake is best served by a sentence. This catches it in CI, because the
warning only helps someone who read it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent

#: Roots that ship Python. Globbed, not enumerated file by file: an
#: enumeration fails open, which is the defect four separate guards in this
#: repository were found to have on 2026-08-15.
SCAN_ROOTS = ["caterva", "Tests", "scripts", "examples"]

SKIP_PARTS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "build", "dist"}

#: `import Caterva`, `from Caterva import x`, `from Caterva.core import y`,
#: and the string form used by importlib.
#:
#: Anchored on the two-r spelling followed by a word boundary, so `Caterva`
#: as part of a longer identifier is not matched -- the failure mode to
#: avoid is a guard that fires on something legitimate.
PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*import\s+Caterva\b"), "import Caterva"),
    (re.compile(r"^\s*from\s+Caterva(\.\w+)*\s+import\b"), "from Caterva import"),
    (re.compile(r"""import_module\(\s*["']Caterva\b"""), 'import_module("Caterva")'),
    (re.compile(r"""__import__\(\s*["']Caterva\b"""), '__import__("Caterva")'),
]


def offending_lines(text: str) -> List[Tuple[int, str, str]]:
    """`(line number, stripped line, what matched)` for each bad import."""
    findings: List[Tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # A comment describing the mistake is not the mistake. This file and
        # the ADRs quote `import Caterva` on purpose.
        if stripped.startswith("#"):
            continue
        for pattern, label in PATTERNS:
            if pattern.search(line):
                findings.append((number, stripped, label))
                break
    return findings


_MIN_FILES = 40

#: Fewest files this scan must see before "clean" means anything.
#:
#: Measured, not guessed at: run in an empty tree this guard printed its
#: success line having read nothing. "no Python file imports `Terrium`" is a
#: universal over the files it scanned, and over zero files every universal
#: is true -- so a reader could not tell a clean repository from a broken
#: scan, which is the shape this project calls worse than no check.
#:
#: The floor is the established remedy here, not an invention:
#: `check_public_images_reviewed` already refuses with "found only 0 public
#: image(s), below the floor of 5. The scan is broken, not the pages."
#:
#: Set well below the real count (hundreds today) so ordinary deletion does not
#: trip it. It is a smoke alarm for a scan that has stopped reaching its
#: input -- a renamed directory, a moved root, a glob that no longer matches
#: -- not a coverage target.


def scan() -> List[str]:
    scan.files_read = 0
    findings: List[str] = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.name == "check_package_spelling.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scan.files_read += 1
            for number, line, label in offending_lines(text):
                findings.append(
                    f"{path.relative_to(REPO)}:{number}: {label}\n"
                    f"      {line}"
                )
    return findings


def selftest() -> int:
    """Prove the matcher can fail, and that it leaves prose alone.

    The tree is clean, so this guard reports zero findings forever and a
    matcher that matched nothing would report zero too. That is how four
    guards in this repository were found on one day to be checking a narrower
    scope than anyone believed.

    The `must_pass` half matters as much as the `must_flag` half here. A
    guard on a product name that fired on sentences would be muted within a
    day, and a muted guard is worse than none.
    """
    must_flag = [
        "import Caterva",
        "    import Caterva",
        "from Caterva import caterva_engine",
        "from Caterva.core import validation",
        "from Caterva.core.validation import vmax_from_kcat",
        'importlib.import_module("Caterva")',
        "__import__('Caterva')",
    ]
    must_pass = [
        # The correct spelling, which is the whole point.
        "import caterva",
        "from caterva import caterva_engine",
        "from caterva.core.validation import vmax_from_kcat",
        # Prose and identifiers. A guard that flags these is unusable.
        '"""Caterva resolves parameters from the literature."""',
        "# import Caterva is wrong -- the package is Caterva",
        "CATERVA_ROOT = Path(__file__).parent",
        'parser = argparse.ArgumentParser(description="Caterva build check")',
        "print('Caterva is not Tellurium')",
        # A path string, not an import. check_doc_paths_resolve covers these.
        'path = Path("Caterva/docs")',
    ]

    failures: List[str] = []
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
        f"SELFTEST OK: {len(must_flag)} bad import form(s) flagged, "
        f"{len(must_pass)} legitimate form(s) — including the correct "
        "spelling and prose — left alone."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    findings = scan()
    if findings:
        print(f"Imports of a package that does not exist ({len(findings)}):\n")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nThe importable package is `caterva` — one r. `Caterva` is the"
            "\nproduct, the repository and the organisation, and there is no"
            "\nPython module by that name.\n"
            "\nEvery line above raises ModuleNotFoundError at runtime. Change"
            "\nthe import to `caterva`.\n"
            "\nIf you are new and this is confusing: it is, and you are not"
            "\nlost. See the note in START_HERE.md."
        )
        return 1

    if scan.files_read < _MIN_FILES:
        print(
            f"FAIL: read only {scan.files_read} Python file(s), below the "
            f"floor of {_MIN_FILES}.\n"
            "\nThe scan is broken, not the imports. Over zero files "
            "\"no file imports `Terrium`\" is true and means nothing."
        )
        return 1

    print(
        f"OK: {scan.files_read} Python file(s) read; none imports "
        "`Caterva`. The package is spelled `caterva` everywhere it is "
        "imported."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())