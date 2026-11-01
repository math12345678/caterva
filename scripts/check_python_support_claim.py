"""Python-support-window guard for Caterva.

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

Pins are read from `requirements.txt`, environment markers included. Until
2026-10-31 this file kept its own copy of them, and when scipy was split by
interpreter (1.15.3 below 3.11, 1.16.0 from 3.11; ADR 0014) the copy still
said 1.15.3 for every version, so `--online` checked a wheel set the 3.11-3.13
installs no longer use. A pin with a `python_version` marker is checked
against the part of the window its marker selects, and offline the guard
requires every listed dependency to have exactly one pin for each supported
version.

Usage:
    python scripts/check_python_support_claim.py            # offline
    python scripts/check_python_support_claim.py --online   # + PyPI
    python scripts/check_python_support_claim.py --selftest # prove it can fail
"""

from __future__ import annotations

import json
import operator
import re
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Set, Tuple

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
    # Added after this guard was found to have missed the one place the
    # claim is EXECUTABLE rather than prose. check_env.py's check_python()
    # still gated on 3.10-3.12 and warned "SBML wheels may not exist yet"
    # on 3.13 -- the discredited reason, aimed at the interpreter the
    # Makefile resolver prefers first and CI tests. Three documents agreed
    # with each other while the program disagreed with all three, which is
    # the failure this guard exists to make impossible.
    REPO_ROOT / "scripts" / "check_env.py",
]

# Runtime dependencies whose wheel coverage defines the window. Their versions
# come from REQUIREMENTS, not from here: a second copy is how the scipy split
# went unchecked.
WINDOW_DEPENDENCIES = ("antimony", "libroadrunner", "numpy", "python-libsbml", "scipy")

REQUIREMENTS = REPO_ROOT / "requirements.txt"

# `name==version` with an optional `; python_version <op> "3.N"` marker.
PIN_PATTERN = re.compile(
    r"""^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)\s*"""
    r"""(?:;\s*python_version\s*(<=|>=|==|!=|<|>)\s*["']3\.(\d+)["'])?\s*(?:#.*)?$"""
)
MARKER_OPS = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt,
    ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
}

# (version, supported minors the pin applies to), per dependency.
Pins = Dict[str, List[Tuple[str, Tuple[int, ...]]]]


def _claimed_window(text: str) -> Tuple[int, int] | None:
    match = CLAIM_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def read_pins(text: str) -> Tuple[Pins, List[str]]:
    """The WINDOW_DEPENDENCIES pins in a requirements file, by marker.

    A line naming one of them that this cannot read is an error, not a skip:
    a marker it does not understand would otherwise drop out of the check.
    """
    pins: Pins = {}
    errors: List[str] = []
    minors = [minor for _, minor in SUPPORTED]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[\s=<>!~;\[]", line, maxsplit=1)[0].lower()
        if name not in WINDOW_DEPENDENCIES:
            continue
        match = PIN_PATTERN.match(line)
        if match is None:
            errors.append(f"requirements.txt: cannot read the pin {line!r}")
            continue
        _, version, op, bound = match.groups()
        applies = tuple(
            m for m in minors if op is None or MARKER_OPS[op](m, int(bound))
        )
        pins.setdefault(name, []).append((version, applies))
    return pins, errors


def check_pins_cover_window(pins: Pins) -> List[str]:
    """Each window dependency has exactly one pin for each supported version."""
    errors: List[str] = []
    for package in WINDOW_DEPENDENCIES:
        for _, minor in SUPPORTED:
            chosen = [v for v, applies in pins.get(package, []) if minor in applies]
            if len(chosen) != 1:
                errors.append(
                    f"requirements.txt pins {package} {len(chosen)} times for "
                    f"Python 3.{minor} ({chosen}); expected exactly once"
                )
    return errors


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

    if not REQUIREMENTS.exists():
        errors.append("requirements.txt not found")
    else:
        pins, pin_errors = read_pins(REQUIREMENTS.read_text(encoding="utf-8"))
        errors.extend(pin_errors)
        errors.extend(check_pins_cover_window(pins))
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
    """Each pin must cover the part of the window its marker selects."""
    errors: List[str] = []
    pins, _ = read_pins(REQUIREMENTS.read_text(encoding="utf-8"))

    for package, version, applies in sorted(
        (p, v, a) for p, entries in pins.items() for v, a in entries
    ):
        if not applies:
            continue
        needed = {f"cp3{minor}" for minor in applies}
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
            print(f"  {package:<16} {version:<9} {covered} (needs {sorted(needed)})")
    return errors


def _selftest() -> int:
    """Prove the pin reading and the coverage check can fail."""
    split = (
        'numpy==2.2.6\n'
        'scipy==1.15.3; python_version < "3.11"\n'
        'scipy==1.16.0; python_version >= "3.11"\n'
        'antimony==2.14.0\nlibroadrunner==2.8.0\npython-libsbml==5.21.1\n'
    )
    failures: List[str] = []

    pins, errors = read_pins(split)
    if errors or check_pins_cover_window(pins):
        failures.append("a correct marker split was rejected")
    if pins.get("scipy") != [("1.15.3", (10,)), ("1.16.0", (11, 12, 13))]:
        failures.append(f"the scipy split was read as {pins.get('scipy')}")

    cases = [
        ("a pin missing for 3.10", split.replace('scipy==1.15.3; python_version < "3.11"\n', "")),
        ("two pins for 3.11", split.replace('>= "3.11"', '>= "3.10"')),
        ("an unreadable marker", split.replace('python_version >= "3.11"', 'sys_platform == "darwin"')),
        # An extra pin, so dropping it leaves no hole for the coverage check:
        # only the unreadable-pin error can catch this one.
        ("an unreadable extra pin", split + 'scipy==1.17.0; sys_platform == "win32"\n'),
        ("a dependency not pinned at all", split.replace("numpy==2.2.6\n", "")),
    ]
    for label, text in cases:
        pins, errors = read_pins(text)
        if not (errors or check_pins_cover_window(pins)):
            failures.append(f"{label} was accepted")

    if failures:
        print("SELFTEST FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"SELFTEST OK: a correct split passes and all {len(cases)} broken ones are caught.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
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
    print(
        f"OK: every file claims Python {window}, the Makefile gate agrees, and "
        "requirements.txt pins each window dependency once per version."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
