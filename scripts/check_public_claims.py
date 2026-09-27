#!/usr/bin/env python3
"""What the public pages claim must match what the code does.

WHAT THIS COMES FROM
--------------------
`check_documented_counts.py` keeps README.md honest about test and domain
counts. Nothing did the same for the pages an actual visitor reads, and
four claims had drifted:

  * The terminal panel labelled the integrator **"rk4 (adaptive)"**.
    `src/lib/simulate.ts` computes `h = dt / substeps` with a constant 200
    substeps, no error estimate and no step rejection. It is fixed-step.
  * The FAQ said **"304+ tests"**. The real figure is over 1,800.
  * The FAQ listed PCR, Monte Carlo, population genetics and molecular
    dynamics as **"Planned"**. All four ship in `caterva/discrete/`.
  * The FAQ said every simulation is validated **"to 1e-10 tolerance"**.
    The suite ranges from 1e-10 down to 1e-4 depending on the domain; the
    tightest case was being stated as the general one.

Only the third of those flattered the product. That is the point: this is
not a check against exaggeration, it is a check against *unverified*
claims, and three of the four made Caterva look worse than it is. A number
nobody checks drifts in whichever direction the edit happened to go.

WHAT THIS CHECKS
----------------
Each entry in `CLAIMS` pairs a phrase that must NOT appear on a public page
with the fact that makes it wrong, and a predicate that re-derives that
fact from the code. A claim is a failure when the phrase is present; the
predicate exists so the *reason* stays true too — if `simulate.ts` ever
gains real step adaptation, the guard says so rather than silently
continuing to forbid an accurate word.

WHY IT CANNOT QUIETLY PASS
--------------------------
Every predicate is evaluated whether or not its phrase appears. A predicate
that no longer finds the file it reasons about FAILS, because a check whose
evidence has vanished is not a check that passed.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Below this the scan is broken rather than the pages being clean.
_MIN_FILES = 10

PUBLIC_TREES: tuple[str, ...] = (
    "Science-Agent-Pipeline/artifacts/caterva-landing/src",
    "Science-Agent-Pipeline/artifacts/caterva-landing/index.html",
    "caterva-site/src",
    "landing",
)

SIMULATE_TS = (
    ROOT / "Science-Agent-Pipeline" / "artifacts" / "caterva-landing"
    / "src" / "lib" / "simulate.ts"
)


def _integrator_is_fixed_step() -> tuple[bool, str]:
    """True while the browser integrator takes a constant step."""
    if not SIMULATE_TS.exists():
        return False, f"{SIMULATE_TS.name} is missing, so nothing supports this claim"
    text = SIMULATE_TS.read_text(encoding="utf-8", errors="replace")
    fixed = "const h = dt / substeps" in text
    adaptive_markers = ("stepRejected", "errorEstimate", "adaptStep", "h *=", "h /=")
    adapts = any(marker in text for marker in adaptive_markers)
    if fixed and not adapts:
        return True, "simulate.ts uses a constant h = dt / substeps with no adaptation"
    return False, (
        "simulate.ts no longer looks fixed-step. If real adaptation was added, "
        "'adaptive' becomes accurate and this entry should be removed."
    )


def _four_domains_are_built() -> tuple[bool, str]:
    """True while PCR, Monte Carlo, popgen and MD exist in the engine."""
    paths = {
        "PCR": ROOT / "caterva" / "discrete" / "pcr.py",
        "Monte Carlo": ROOT / "caterva" / "discrete" / "monte_carlo.py",
        "population genetics": ROOT / "caterva" / "discrete" / "population_genetics",
        "molecular dynamics": ROOT / "caterva" / "discrete" / "molecular_dynamics.py",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return False, f"these are no longer built: {missing}; 'Planned' may be right again"
    return True, "all four exist under caterva/discrete/"


#: forbidden phrase -> (why it is wrong, predicate re-deriving that from code)
CLAIMS: dict[str, tuple[str, Callable[[], tuple[bool, str]]]] = {
    "rk4 (adaptive)": (
        "the browser integrator is fixed-step: 200 substeps, constant h, no "
        "error estimate and no step rejection",
        _integrator_is_fixed_step,
    ),
    "adaptive rk4": (
        "same as above, written the other way round",
        _integrator_is_fixed_step,
    ),
    "Planned: PCR": (
        "PCR, Monte Carlo, population genetics and molecular dynamics all "
        "ship in caterva/discrete/ -- listing them as planned understates the "
        "product and is simply out of date",
        _four_domains_are_built,
    ),
    "304+ tests": (
        "the real count is over 1,800 and is checked on every build by "
        "check_documented_counts.py; a hardcoded figure here drifts silently",
        _four_domains_are_built,
    ),
    "to 1e-10 tolerance": (
        "tolerances range from 1e-10 on analytic cases to 1e-4 where a "
        "stochastic method makes anything tighter meaningless. Stating the "
        "tightest as the general case is the same defect as a fabricated "
        "number, one step smaller",
        _four_domains_are_built,
    ),
}


def _public_files() -> list[pathlib.Path]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    return [
        ROOT / rel for rel in listing
        if any(rel.startswith(tree) for tree in PUBLIC_TREES)
        and "node_modules" not in rel
        and not rel.endswith((".png", ".svg", ".ico"))
    ]


def find_claims(files: list[pathlib.Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        for line_no, line in enumerate(text.splitlines(), 1):
            # This guard's own docstring quotes the phrases it forbids.
            if "check_public_claims" in str(rel):
                continue
            for phrase, (why, _) in CLAIMS.items():
                if re.search(re.escape(phrase), line, re.I):
                    problems.append(f"{rel}:{line_no} says {phrase!r} -- {why}")
    return problems


def main() -> int:
    files = _public_files()
    if len(files) < _MIN_FILES:
        print(
            f"FAIL: found only {len(files)} public-facing file(s), below the "
            f"floor of {_MIN_FILES}.\n      The scan is broken, not the pages."
        )
        return 1

    stale: list[str] = []
    for phrase, (_, predicate) in CLAIMS.items():
        holds, detail = predicate()
        if not holds:
            stale.append(f"{phrase!r}: {detail}")

    problems = find_claims(files)

    print(f"Public files scanned:    {len(files)}")
    print(f"Claims checked:          {len(CLAIMS)}")
    print(f"Contradicted by code:    {len(problems)}")

    if stale:
        print("\nA reason behind a forbidden phrase no longer holds:\n")
        for line in stale:
            print(f"  {line}")
        print(
            "\nThe code changed under this guard. Re-check the phrase: it may "
            "now be true,\nin which case remove the entry rather than leaving "
            "a rule nobody can justify."
        )
        return 1

    if problems:
        print("\nA public page says something the code contradicts:\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nFix the page, or fix the code and remove the entry from CLAIMS. "
            "Three of the\nfour original defects made Caterva look WORSE than "
            "it is -- an unchecked number\ndrifts whichever way the edit went."
        )
        return 1

    print("\nOK: no public page contradicts the implementation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
