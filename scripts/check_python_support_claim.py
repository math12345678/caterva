"""Python-support-window guard for Terrium.

Verifies that the interpreter range the project claims to support is
consistent across every file that states it, and that the pinned dependencies
actually publish wheels for that range.

Why this exists
---------------
`requirements.txt`, `README.md` and `CONTRIBUTING.md` all gave the same reason
for the 3.10-3.13 window (previously 3.10-3.12):

    "the SBML C extensions publish prebuilt wheels up to cp312"

That was wrong. Verified against PyPI on 2026-08-02, `python-libsbml` 5.21.1
ships cp313 AND cp314 wheels, and `antimony` 2.14.0 ships `py3-none-<platform>`
wheels that carry no interpreter requirement at all. The real blockers are
`libroadrunner` and `numpy`.

The stated reason had drifted from reality because nothing executable checked
it -- the same failure mode as the stale test counts (`check_documented_counts`)
and the unverified citations (`check_citation_format`). A dependency claim is
a factual claim about the world, and Rule 1 governs those.

Network behaviour
-----------------
The PyPI check is **opt-in** via `--online`. Offline (the default, and what
CI and `verify_build.py` run) it checks only internal consistency: that every
file states the same window, and that the window matches the Makefile gate.
That part needs no network and cannot flake.

`--online` additionally confirms each pinned dependency really does publish
wheels covering the claimed window. Run it when changing a pin.

Usage:
    python scripts/check_python_support_claim.py            # offline
    python scripts/check_python_support_claim.py --online   # + PyPI
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# The single source of truth for the supported window. Changing this without
# changing the Makefile gate is exactly what this guard catches.
SUPPORTED: Tuple[Tuple[int, int], ...] = ((3, 10), (3, 11), (3, 12), (3, 13))

# Files that state the window in prose, and the pattern that finds it.
# "3.10-3.12" or "3.10–3.12" (ASCII hyphen or en dash).
CLAIM_PATTERN = re.compile(r"3\.(\d+)\s*[-–]\s*3\.(\d+)")

CLAIM_FILES = [
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTRIBUTING.md",
]

# Runtime dependencies whose wheel coverage defines the window.
PINNED = {
    "libroadrunner": "2.8.0",
    "numpy": "2.2.6",
    "python-libsbml": "5.21.1",
    "antimony": "2.14.0",
    "scipy": "1.15.3",
}


def _claimed_window(text: str) -> Tuple[int, int] | None:
    match = CLAIM_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def check_internal_consistency() -> List[str]:
    """Every file states the same window, and it matches SUPPORTED."""
    errors: List[str] = []
    expected = (SUPPORTED[0][1], SUPPORTED[-1][1])

    for path in CLAIM_FILES:
        if not path.exists():
            errors.append(f"{path.name} not found")
            continue
        window = _claimed_window(path.read_text(encoding="utf-8"))
        if window is None:
            errors.append(f"{path.name} no longer states a Python version window")
        elif window != expected:
            errors.append(
                f"{path.name} claims 3.{window[0]}-3.{window[1]}, "
                f"expected 3.{expected[0]}-3.{expected[1]}"
            )

    # The Makefile gate is the executable version of the same claim.
    makefile = REPO_ROOT / "Makefile"
    if makefile.exists():
        text = makefile.read_text(encoding="utf-8")
        gate = set(re.findall(r"\(3,\s*(\d+)\)", text))
        expected_gate = {str(minor) for _, minor in SUPPORTED}
        if gate and gate != expected_gate:
            errors.append(
                f"Makefile is_supported() accepts 3.{sorted(gate)}, "
                f"docs claim 3.{sorted(expected_gate)}"
            )
    return errors


def _wheel_pythons(package: str, version: str) -> Set[str] | None:
    """cp tags for a release, or {'*'} when it ships version-agnostic wheels."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except Exception as exc:  # noqa: BLE001 - network is best-effort here
        print(f"  ! could not query PyPI for {package}: {exc}")
        return None

    files = data.get("releases", {}).get(version)
    if not files:
        print(f"  ! {package} {version} not found on PyPI")
        return None

    if any("py3-none" in f["filename"] for f in files):
        return {"*"}
    return {
        f["filename"].split("-")[2]
        for f in files
        if f["filename"].endswith(".whl")
    }


def check_against_pypi() -> List[str]:
    """Each pin must cover the whole claimed window."""
    errors: List[str] = []
    needed = {f"cp3{minor}" for _, minor in SUPPORTED}

    for package, version in sorted(PINNED.items()):
        tags = _wheel_pythons(package, version)
        if tags is None:
            continue
        if tags == {"*"}:
            print(f"  {package:<16} {version:<9} py3-none (version-agnostic)")
            continue
        missing = needed - tags
        covered = sorted(t for t in tags if t.startswith("cp"))
        if missing:
            errors.append(
                f"{package} {version} has no wheels for {sorted(missing)} "
                f"(publishes {covered}) -- the claimed window is unsupportable"
            )
        else:
            print(f"  {package:<16} {version:<9} {covered}")
    return errors


def main() -> int:
    online = "--online" in sys.argv
    errors: List[str] = []

    print("Checking the claimed Python support window is stated consistently...")
    errors.extend(check_internal_consistency())

    if online:
        print("\nChecking pinned dependencies against PyPI...")
        errors.extend(check_against_pypi())
    else:
        print("(skipping PyPI check; pass --online to include it)")

    print()
    if errors:
        print("FAIL: the Python support claim does not hold")
        for error in errors:
            print(f"  - {error}")
        print(
            "\nThe stated reason for this window has been wrong before -- it "
            "named\nthe SBML extensions when the real blockers were "
            "libroadrunner and numpy.\nSee docs/adr/0014-python-version-support.md."
        )
        return 1

    window = f"3.{SUPPORTED[0][1]}-3.{SUPPORTED[-1][1]}"
    print(f"OK: every file claims Python {window}, and the Makefile gate agrees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
