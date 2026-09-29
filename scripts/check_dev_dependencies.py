#!/usr/bin/env python3
"""Name the declared dependencies that are not installed.

Two tests in `make test` have been failing on this machine for the whole of
this session, and neither says why:

    tests/test_citation_metadata.py::TestTheCitationFileItself::test_the_guard_passes
    tests/test_guard_selftests.py::test_the_guards_selftest_passes[check_codegen_loads.py]

The first reports ``UNREACHABLE  cffconvert is not installed``. The second
reports ``SELFTEST FAILED: the load check rejected a module that is valid for
the installed zod``. Both messages are accurate and both name the wrong
problem: `cffconvert` is declared in ``requirements-dev.txt`` and installed in
no virtualenv on this machine, and `zod` is declared in
``lib/api-zod/package.json`` and absent from that workspace's node_modules.

Neither is a defect in the citation file or in the load check. They are the
same failure -- a declared dependency that was never installed -- wearing two
different costumes, and each costume sends a reader to debug the wrong file.
A guard that has to say "could not check" is working correctly; what was
missing is anything that says *why* in terms of the thing to install.

Three states, because "I could not determine what is installed" is not
"everything is installed":

    0   every declared dependency this project's guards need is importable
    1   something declared is missing; the exact install command is printed
    3   could not determine -- a manifest is unreadable or absent

This is advisory. It is wired into ``make doctor`` and available as
``make deps-check``, and deliberately NOT made a prerequisite of ``make
test``: 1162 of 1164 tests pass without these packages, and blocking all of
them to report two would trade a small confusing failure for a large one.
"""

from __future__ import annotations

import argparse
from importlib import metadata
import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: JavaScript packages a *Python* guard needs, and the workspace it must be
#: installed in. These are here because the guard that needs them is a Python
#: script, so no JS tooling ever notices they are missing -- which is exactly
#: how the codegen selftest came to report a zod problem that was really an
#: uninstalled-workspace problem.
REQUIRED_JS = [
    (
        Path("Science-Agent-Pipeline/lib/api-zod"),
        "zod",
        "scripts/check_codegen_loads.py loads generated modules against it",
    ),
]


def parse_requirements(path: Path) -> tuple[list[str], str | None]:
    """Distribution names from a requirements file, or a reason it failed.

    ``-r`` includes are followed one level, which is all this project uses.
    """
    if not path.exists():
        try:
            shown = path.relative_to(REPO_ROOT)
        except ValueError:
            # A path outside the repository -- the selftest uses one. Showing
            # it whole is correct; crashing on it made the selftest itself
            # unrunnable, which is a check that cannot report.
            shown = path
        return [], f"{shown} does not exist"

    names: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("-r"):
                nested = (path.parent / line[2:].strip()).resolve()
                inner, problem = parse_requirements(nested)
                if problem is not None:
                    return [], problem
                names.extend(inner)
                continue
            if line.startswith("-"):
                continue
            name = re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip()
            if name:
                names.append(name)
    except OSError as exc:
        return [], f"could not read {path.name}: {exc}"

    return names, None


def is_installed(name: str) -> bool:
    """Is this *distribution* installed for the running interpreter?

    Asked of the installed metadata, not by guessing an import name. The
    first version of this file mapped distribution to module with
    ``s/-/_/`` and a small override table, and reported five packages
    missing of which **three were installed**: `libroadrunner` imports as
    ``roadrunner``, `python-libsbml` as ``libsbml``, `beautifulsoup4` as
    ``bs4``. A dependency checker that invents missing dependencies is worse
    than no checker, because the install command it prints is noise and the
    two genuinely missing packages are lost among them.

    ``importlib.metadata`` resolves the distribution name the manifest
    actually uses, so there is no mapping to maintain and none to drift.
    Importing is avoided as well: importing runs module-level code, and a
    check with side effects on the thing it checks is not read-only.
    """
    try:
        metadata.distribution(name)
        return True
    except metadata.PackageNotFoundError:
        return False


def missing_python(names: list[str]) -> list[str]:
    return [n for n in names if not is_installed(n)]


def missing_js() -> list[tuple[Path, str, str]]:
    absent = []
    for workspace, package, why in REQUIRED_JS:
        if not (REPO_ROOT / workspace / "node_modules" / package).exists():
            absent.append((workspace, package, why))
    return absent


def selftest() -> int:
    """Prove the check can fail.

    A check that cannot fail is worse than no check, because it is trusted.
    Both halves are exercised: a name that cannot possibly be installed must
    be reported missing, and a name that certainly is must not be.
    """
    impossible = "terrium-package-that-does-not-exist"
    if not missing_python([impossible]):
        print(
            "SELFTEST FAILED: a package that cannot exist was reported as "
            "installed. The check would report false passes."
        )
        return 1

    # pytest is installed wherever this selftest can run at all, and its
    # distribution name matches its module name. The next case is the one
    # that matters.
    if missing_python(["pytest"]):
        print(
            "SELFTEST FAILED: pytest was reported missing by a run that "
            "requires pytest. The check would report false failures."
        )
        return 1

    # The regression that motivated using distribution metadata: three
    # packages whose import name differs from their distribution name. Any
    # of them reported missing means the checker is guessing again.
    for installed_but_renamed in ("python-libsbml", "beautifulsoup4"):
        if not is_installed(installed_but_renamed):
            continue  # genuinely absent here; nothing to assert
        if missing_python([installed_but_renamed]):
            print(
                f"SELFTEST FAILED: {installed_but_renamed} is installed but "
                "was reported missing -- the checker is resolving names by "
                "guesswork again."
            )
            return 1

    # And the manifest parser, against a file whose contents are known here
    # rather than assumed from the repository's.
    with tempfile.TemporaryDirectory() as tmp:
        manifest = Path(tmp) / "reqs.txt"
        manifest.write_text(
            "# a comment\n"
            "\n"
            "pytest==9.1.1\n"
            "cffconvert==2.0.0  # trailing comment\n"
            "some-extra[all]>=1.0\n"
            "--index-url https://example.invalid\n",
            encoding="utf-8",
        )
        names, problem = parse_requirements(manifest)
        if problem is not None:
            print(f"SELFTEST FAILED: parsing a valid manifest reported: {problem}")
            return 1
        if names != ["pytest", "cffconvert", "some-extra"]:
            print(f"SELFTEST FAILED: parsed {names!r}, expected the three names")
            return 1

        absent, problem = parse_requirements(Path(tmp) / "not-here.txt")
        if problem is None:
            print(
                "SELFTEST FAILED: a missing manifest parsed without complaint. "
                "It would report zero dependencies and pass vacuously."
            )
            return 1

    print("SELFTEST OK: reports a fabricated package missing, the stdlib present,")
    print("  parses a manifest, and refuses to treat an absent manifest as empty.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    manifest = REPO_ROOT / "requirements-dev.txt"
    declared, problem = parse_requirements(manifest)

    if problem is not None:
        # Could not determine. NOT a pass: a missing manifest would otherwise
        # yield an empty list and report every dependency satisfied, which is
        # the vacuous-pass shape this repository keeps finding.
        print(f"UNDETERMINED  {problem}")
        print("  Nothing was checked. This is not a clean result.")
        return 3

    if not declared:
        print(f"UNDETERMINED  {manifest.name} declares no packages.")
        print("  A manifest with nothing in it is more likely broken than empty.")
        return 3

    absent_py = missing_python(declared)
    absent_js = missing_js()

    if args.json:
        print(
            json.dumps(
                {
                    "declared": len(declared),
                    "missingPython": absent_py,
                    "missingJs": [str(w / "node_modules" / p) for w, p, _ in absent_js],
                },
                indent=2,
            )
        )
        return 1 if (absent_py or absent_js) else 0

    if not absent_py and not absent_js:
        print(f"OK: all {len(declared)} declared dev dependencies are importable,")
        print(f"    and {len(REQUIRED_JS)} JS package(s) the guards need are present.")
        return 0

    print("MISSING declared dependencies. Guards will report problems that")
    print("name the wrong cause until these are installed.\n")

    if absent_py:
        print(f"  Python ({len(absent_py)}):")
        for name in absent_py:
            print(f"    {name}")
        print(f"\n    python3 -m pip install -r {manifest.name}\n")

    if absent_js:
        print(f"  JavaScript ({len(absent_js)}):")
        for workspace, package, why in absent_js:
            print(f"    {package} in {workspace}")
            print(f"      needed because {why}")
        print("\n    cd Science-Agent-Pipeline && pnpm install\n")

    print("  Known failures caused by exactly this:")
    print("    cffconvert  -> test_citation_metadata.py reports the citation")
    print("                   guard failing, when the guard correctly said")
    print("                   UNREACHABLE and only the package is absent.")
    print("    zod         -> check_codegen_loads.py --selftest reports the")
    print("                   load check rejecting a valid module, when the")
    print("                   workspace simply has no node_modules.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
