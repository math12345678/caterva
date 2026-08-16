"""Every guard that ships a `--selftest` must have it run unasked.

WHY THIS EXISTS
---------------
The Stage 4 amendment is already executable for guards:

    A guard is not delivered until something runs it unasked.

`check_guard_wiring.py` enforces it, because `check_rng_convention.py` and
`check_citation_format.py` both shipped correct and wired to nothing.

**It was never applied one level up.** Five guards grew a `--selftest`
entry point -- `check_adr_index.py`, `check_codegen_loads.py`,
`check_documented_counts.py`, `check_no_hardcoded_assay_conditions.py`,
`claim_adr.py` -- and *nothing ran any of them*. Not the Makefile, not CI,
not verify_build, not a test. Measured, not assumed:

    grep -rn selftest scripts/verify_build.py .github/workflows/tests.yml \
        Makefile Tests/ Terium/tests/
    (no output)

A selftest is a guard on a guard, and it rots the same way — worse, in fact,
because its existence is *reassuring*. Reading `--selftest` in a script is
easily mistaken for evidence the script is verified. For months it meant
only that somebody could have run it.

That this was worth doing is not hypothetical. The first run of
`check_adr_index.py --selftest` failed and exposed a real bug: the status
regex used `\\s*\\S`, and `\\s` matches newlines regardless of `re.M`, so a
document whose status line read `**Status:**` with nothing after it matched
the first word of the *body* and passed. A second attempt was wrong
differently — the optional `\\*?\\*?:?` groups could match nothing, letting
`\\S` match the `:` inside `**Status:**` itself. Both accepted a status line
that answers nothing. Neither would have been found by reading.

WHAT THIS ASSERTS
-----------------
Each selftest exits 0. That is all — the selftests own their own detail.
The point is that they *run*, on every CI push, without anyone remembering.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _scripts_with_a_selftest() -> list[pathlib.Path]:
    """Discovered, not listed.

    A hardcoded list would go stale the moment someone adds the sixth
    selftest, and it would go stale *silently* -- which is the failure this
    file exists to stop. `test_discovery_finds_the_known_selftests` pins
    that discovery keeps working.

    The matcher's first version required `sys.argv`, which found four of the
    five: `check_no_hardcoded_assay_conditions.py` registers `--selftest`
    with `argparse` instead and was silently skipped. Caught by
    `test_discovery_finds_the_known_selftests`, which is the whole reason
    that test is written as a named list rather than trusting discovery.
    """
    found = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if '"--selftest"' in text:
            found.append(path)
    return found


def test_discovery_finds_the_known_selftests() -> None:
    """The premise. Without it, a broken matcher makes this whole file
    vacuous: zero scripts discovered means zero selftests run and a green
    suite, which is precisely the "check that cannot fail" shape."""
    names = {path.name for path in _scripts_with_a_selftest()}
    known = {
        "check_adr_index.py",
        "check_codegen_loads.py",
        "check_documented_counts.py",
        "check_no_hardcoded_assay_conditions.py",
        "claim_adr.py",
    }
    missing = known - names
    assert not missing, (
        f"these scripts expose --selftest but discovery missed them: "
        f"{sorted(missing)}. Fix the matcher; do not shorten the list."
    )


@pytest.mark.parametrize(
    "script", _scripts_with_a_selftest(), ids=lambda p: p.name
)
def test_the_guards_selftest_passes(script: pathlib.Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(script), "--selftest"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=300,
    )
    assert completed.returncode == 0, (
        f"{script.name} --selftest failed (exit {completed.returncode}).\n"
        "A guard whose own selftest is red cannot be trusted about the "
        "thing it guards.\n\n"
        f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
    )
