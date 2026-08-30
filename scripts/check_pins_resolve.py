#!/usr/bin/env python3
"""Every pinned version exists on PyPI, for some platform.

WHY THIS EXISTS, AND THE MISTAKE THAT WROTE IT
----------------------------------------------
CI had failed on every push for six consecutive commits. Investigating on
this machine, `pip install -r requirements-dev.txt` said:

    ERROR: Could not find a version that satisfies the requirement
           libroadrunner==2.8.0 (from versions: 2.7.0)

I read that as "2.8.0 does not exist", changed the pin to 2.7.0, changed
numpy to match, dropped Python 3.13 from the CI matrix, and wrote a long
comment about a claim nobody had verified.

**All of it was wrong.** libroadrunner 2.8.0 exists and ships
cp310/cp311/cp312/cp313 wheels -- exactly what the original comment said.
What it does not ship is an **aarch64** wheel, and this sandbox is aarch64
Linux. GitHub's `ubuntu-latest` is x86_64, where the pin installs fine.

So pip's message was accurate and I misread its scope: `from versions:
2.7.0` means "for THIS interpreter on THIS architecture", not "in the
world". A tool reporting what it can see, read as a statement about what
exists -- the same defect this repository has recorded three times in
matchers (ADR 0102, ADR 0104, ADR 0122), committed here against the
project's dependency manifest on the strength of one command's output.

The changes were reverted. This guard is what remains, and its job is to
make that specific error impossible to repeat.

THE SAME ERROR, INVERTED, ON 2026-08-20 -- READ THIS BEFORE PROBING PINS
------------------------------------------------------------------------
Hunting the still-unexplained `test` job failure, I tried to ask the right
question this time: resolve for the RUNNER's platform rather than this one,

    pip install --dry-run --only-binary=:all: \
        --platform manylinux_2_28_x86_64 --python-version 310 --abi cp310 \
        -r requirements-dev.txt

and it reported:

    ERROR: Could not find a version that satisfies the requirement
           antimony==2.14.0 (from versions: 2.15.0, 3.0.0, 3.1.0, ...)

on all three Pythons -- a perfect match for the symptom (all four jobs dying
in under forty seconds, before any suite). I edited the pin to 2.15.0.

**It was wrong.** `--platform` matches wheel tags EXACTLY; it does not know
that a manylinux_2_28 machine also runs manylinux_2_17 and manylinux2014
wheels. Passing the full set the runner actually accepts:

    antimony-2.14.0-py3-none-manylinux2014_x86_64.whl   <- it was always there

The pin was reverted before it was committed. Two more probes in the same
hour failed the same way: `python-libsedml==2.0.33` "did not exist" until the
platform list was widened, and a `cffconvert` dependency conflict turned out
to be `docopt`, which is sdist-only and was excluded by my own
`--only-binary=:all:` -- a flag CI does not pass.

So this is not one mistake with a fix; it is a SHAPE, and it is the
repository's most frequent one:

    a matcher narrower than the thing it measures reports "it is not there",
    when what it means is "I could not see".

Three times in matchers (ADR 0102, 0104, 0122), once against the dependency
manifest (above), and now three times in a single hour against pip's own
platform flags -- twice nearly rewriting a pin that was correct.

IF YOU ARE ABOUT TO CHANGE A PIN BECAUSE A TOOL SAID A VERSION IS MISSING:
the burden is on the probe, not the package. Widen the matcher until it
says the version is missing for reasons you can name, or get the actual
build log. Do not edit requirements.txt on the strength of one command.

WHAT IT CHECKS
--------------
Every `name==version` pin has at least one file published on PyPI, asked of
**PyPI's API** rather than of local pip. That question is
platform-independent and has one true answer.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
Whether the set installs HERE. `pip install --dry-run` answers a question
about this interpreter and this architecture, and a guard that failed the
build on it would go red for every developer on an ARM laptop while CI on
x86_64 was perfectly healthy -- turning a machine-specific absence into a
project-wide alarm. That is the mistake above, wired in permanently.

A pin that resolves nowhere at all is still caught, because a version with
no files fails the check below.

NETWORK
-------
If PyPI cannot be reached this reports UNAVAILABLE and exits non-zero rather
than green. "Could not check" must never render as "checked, and it was
fine" -- though note that this exit code means *ask again*, not *the pins
are wrong*, and the message says which.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Every requirements file that pins a version. `-r` includes are followed
#: by pip itself; listed explicitly here so a new file is a deliberate add.
REQUIREMENTS = [
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "requirements-dev.txt",
    # Added after the two below were found unchecked. Explicit rather than
    # globbed, keeping the property the comment above asks for.
    REPO_ROOT / "requirements-popgen.txt",
    REPO_ROOT / "advanced_analysis" / "requirements.txt",
]

#: A requirement naming a distribution, whatever the operator -- `==`,
#: `>=`, `~=` or a bare name.
#:
#: The version check above only ever looked at `==`, so a file using `>=`
#: was parsed into zero pins and contributed nothing. That is how
#: `advanced_analysis/requirements.txt` came to contain THREE entries that
#: could not work:
#:
#:   * `python>=3.10`, which is not a distribution at all and made
#:     `pip install -r requirements.txt` -- the command that file's README
#:     documents -- fail outright on its first line;
#:   * `timeit>=1.0.0`, a STANDARD LIBRARY module, absent from PyPI;
#:   * `excalidraw-export>=0.1.0`, also absent from PyPI.
#:
#: The last two are the reason this check is about NAMES and not only
#: versions. An unregistered name on PyPI is an open slot: the file is a
#: standing instruction to install whatever a stranger uploads under it.
#: Rule 7 of docs/CONSTITUTION.md is about exactly this shape, and nothing
#: was looking at these files.
NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:[=<>!~]|$)")

#: Names that are standard-library modules, so asking PyPI for them is
#: always wrong even if somebody has registered the name.
STDLIB_NAMES = frozenset(sys.stdlib_module_names)

#: `name==version`, ignoring comments, blank lines, `-r` includes and any
#: environment markers after a semicolon.
PIN_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)")


def pins(path: pathlib.Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = PIN_RE.match(line)
        if match:
            out.append((match.group(1), match.group(2)))
    return out


def named_distributions(path: pathlib.Path) -> list[str]:
    """Every distribution name a requirements file asks for."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        match = NAME_RE.match(stripped)
        if match:
            out.append(match.group(1))
    return out


def released_versions(package: str) -> set[str] | None:
    """Versions with at least one published file. None if PyPI is unreachable.

    Asked of PyPI, not of local pip: "does this version exist" has one
    answer, while "can I install it here" has a different answer for every
    interpreter and architecture. Conflating those two is the error the
    module docstring records.

    A version key with an EMPTY file list is not a release -- reserved,
    yanked, or never uploaded -- so files are counted rather than keys.
    """
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            releases = json.load(response).get("releases", {})
            return {
                version for version, files in releases.items()
                if isinstance(files, list) and len(files) > 0
            }
    except urllib.error.HTTPError as exc:
        # 404 is an answer: the package does not exist. Distinguished from
        # "could not ask", because they need different responses.
        if exc.code == 404:
            return set()
        return None
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    all_pins: list[tuple[pathlib.Path, str, str]] = []
    for path in REQUIREMENTS:
        for name, version in pins(path):
            all_pins.append((path, name, version))

    if not all_pins:
        # A guard that examined nothing must not print OK.
        print(
            f"FAIL: no `name==version` pins parsed out of {[p.name for p in REQUIREMENTS]}. "
            "Either the files moved or the matcher stopped matching; nothing was checked.",
            file=sys.stderr,
        )
        return 1

    missing: list[str] = []
    unreachable: list[str] = []
    for path, name, version in all_pins:
        available = released_versions(name)
        if available is None:
            unreachable.append(name)
        elif version not in available:
            newest = sorted(available)[-1] if available else "(no releases at all)"
            missing.append(
                f"  {path.name}: {name}=={version} does not exist "
                f"(PyPI has {len(available)} release(s); newest {newest})"
            )

    # --- every NAMED distribution exists, whatever the operator ---------
    #
    # Separate from the version loop above, because "this version is wrong"
    # and "this package has never existed" are different facts and the
    # second is the more dangerous one: an unregistered name is a slot
    # anybody can fill.
    all_names: list[tuple[pathlib.Path, str]] = []
    for path in REQUIREMENTS:
        for name in named_distributions(path):
            all_names.append((path, name))

    phantom: list[str] = []
    stdlib_asks: list[str] = []
    for path, name in all_names:
        if name.lower().replace("_", "-") in {"python"}:
            phantom.append(
                f"  {path.relative_to(REPO_ROOT)}: `{name}` is not a "
                "distribution -- the interpreter version belongs in a "
                "comment or pyproject.toml, not in a resolver's input"
            )
            continue
        if name.replace("-", "_") in STDLIB_NAMES:
            stdlib_asks.append(
                f"  {path.relative_to(REPO_ROOT)}: `{name}` is a standard "
                "library module. Asking PyPI for it installs whoever "
                "registered the name, not the module you meant."
            )
            continue
        available = released_versions(name)
        if available is None:
            unreachable.append(name)
        elif not available:
            phantom.append(
                f"  {path.relative_to(REPO_ROOT)}: `{name}` has no releases "
                "on PyPI"
            )

    print(f"Pinned versions checked against PyPI: {len(all_pins)}")
    print(f"Distribution names checked against PyPI: {len(all_names)}")

    if stdlib_asks:
        print(
            f"\nStandard-library names asked of PyPI ({len(stdlib_asks)}):",
            file=sys.stderr,
        )
        for line in stdlib_asks:
            print(line, file=sys.stderr)

    if phantom:
        print(
            f"\nRequirements naming something that is not on PyPI "
            f"({len(phantom)}):",
            file=sys.stderr,
        )
        for line in phantom:
            print(line, file=sys.stderr)

    if stdlib_asks or phantom:
        print(
            "\nA name with no package behind it is not a harmless typo. It is\n"
            "an unclaimed slot, and this file is a standing instruction to\n"
            "install whatever appears in it. See Rule 7 of docs/CONSTITUTION.md.",
            file=sys.stderr,
        )
        return 1

    if unreachable:
        print(
            f"\nUNAVAILABLE: could not reach PyPI for {len(unreachable)} package(s): "
            f"{', '.join(sorted(set(unreachable)))}\n"
            "Nothing was verified, so this is not a pass. Re-run with network.",
            file=sys.stderr,
        )
        return 1

    if missing:
        print(f"\nPins naming a version that does not exist ({len(missing)}):", file=sys.stderr)
        for line in missing:
            print(line, file=sys.stderr)
        print(
            "\n`pip install -r requirements-dev.txt` is the first substantial step\n"
            "of every CI job. A pin like this fails all of them, in about thirty\n"
            "seconds, on every push -- which is how this repository stayed red for\n"
            "six commits with the reason visible only in an inbox.",
            file=sys.stderr,
        )
        return 1

    print("  every pin has at least one file published.")
    print(
        "\n  NOT checked: whether they install on THIS machine. That is a\n"
        "  question about one interpreter and one architecture -- the reading\n"
        "  error this guard exists because of. See the module docstring."
    )
    print("\nOK: every pinned version exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
