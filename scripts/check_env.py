#!/usr/bin/env python3
"""Verify a Caterva development environment actually works.

Not a version-string check: this imports every engine, builds a real model,
translates it to SBML, integrates it, and compares the answer to a known
closed-form solution. A green run here means the stack is genuinely usable,
not merely installed.

    python3 scripts/check_env.py
"""

from __future__ import annotations

import math
import pathlib
import platform
import sys

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def bad(msg: str, fix: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")
    print(f"        fix: {fix}")
    failures.append(msg)


def warn(msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET}  {msg}")
    warnings.append(msg)


def check_python() -> None:
    """Gate on the supported window: Python 3.10-3.13.

    This function used to stop at 3.12 and WARN on anything above it, with
    the reason "python-libsbml and friends publish wheels up to cp312".
    That reason is the exact false claim `check_python_support_claim.py`
    was written to kill -- python-libsbml 5.21.1 ships cp314 and antimony
    2.14.0 is version-agnostic; the real ceiling comes from libroadrunner
    2.8.0 and numpy 2.2.6 (ADR 0014). The guard survived here because its
    CLAIM_FILES list covered requirements.txt, README.md and
    CONTRIBUTING.md but not this file, so `make check` on Python 3.13 --
    the version the Makefile's resolver prefers first and CI tests --
    printed a warning telling the contributor their supported interpreter
    might not work. That file list now includes this one.
    """
    print("\nPython")
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info[2]}"
    if major == 3 and 10 <= minor <= 13:
        ok(f"Python {version} on {platform.machine()}")
    else:
        bad(f"Python {version} is outside the supported window 3.10-3.13",
            "install python3.13 (or 3.10-3.12), then: "
            "rm -rf .venv && make setup")


def check_imports() -> None:
    print("\nEngines")
    for module, label in [
        ("roadrunner", "libroadrunner (ODE integration)"),
        ("antimony", "antimony (model definition)"),
        ("libsbml", "python-libsbml (SBML validation)"),
        ("numpy", "numpy"),
        ("scipy", "scipy (independent reference integrator)"),
    ]:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            ok(f"{label} {version}")
        except ImportError as exc:
            bad(f"{label} missing ({exc})",
                "pip install -r requirements.txt")


# `check_resolver_deps()` stood here until 2026-11-01. It warned when
# `stdpopsim` was missing, because `Tests/popgen_resolver.py` took its
# mutation rates from it and `Tests/test_popgen_resolver.py` skipped
# without it. That day both moved to archive/legacy_domains/ with the
# Wright-Fisher domain they served (archived on 2026-09-27, after
# v0.4.0, the last release that runs it), and
# requirements-popgen.txt went with them. A warning telling a contributor
# to install a GPL package, with a system library, for a resolver nothing
# calls is advice that costs them an afternoon for nothing, so the check
# went too rather than being left to describe a path that no longer exists.


def check_test_deps() -> None:
    print("\nTest tooling")
    for module, label in [("pytest", "pytest"), ("hypothesis", "hypothesis")]:
        try:
            mod = __import__(module)
            ok(f"{label} {getattr(mod, '__version__', '?')}")
        except ImportError:
            bad(f"{label} missing", "pip install -r requirements-dev.txt")


def check_end_to_end() -> None:
    """Build, translate, integrate, and check against the exact solution."""
    print("\nEnd-to-end numerical check")
    if failures:
        warn("skipped: fix the failures above first")
        return
    try:
        import antimony
        import roadrunner
    except ImportError:
        warn("skipped: engines unavailable")
        return

    km, vmax, s0, t = 2.0, 5.0, 10.0, 1.0
    source = (
        "model check\n"
        "  J0: S -> P; Vmax * S / (Km + S);\n"
        f"  S = {s0}; P = 0; Vmax = {vmax}; Km = {km};\n"
        "end\n"
    )

    antimony.clearPreviousLoads()
    if antimony.loadAntimonyString(source) < 0:
        bad(f"antimony failed to parse: {antimony.getLastError()}",
            "reinstall antimony")
        return
    ok("antimony parsed a Michaelis-Menten model")

    sbml = antimony.getSBMLString("check")
    if not sbml or "<sbml" not in sbml:
        bad("antimony produced no SBML", "reinstall antimony")
        return
    ok("translated to SBML")

    # The tolerances come from the ENGINE's constants, not from literals
    # here.
    #
    # They were `1e-10` and `1e-12`, hardcoded, and identical to
    # `DEFAULT_RELATIVE_TOLERANCE` / `DEFAULT_ABSOLUTE_TOLERANCE` in
    # `caterva/core/data_structures.py`. Two statements of one fact, and the
    # README leans the project's most load-bearing claim on this check:
    #
    #     "If it passes, the numerics are trustworthy."
    #
    # Loosen the engine's defaults -- ADR 0005 shows they have been tuned
    # once already -- and this check would go on certifying the OLD
    # settings, for a configuration the product no longer runs. The claim
    # would become false with nothing turning red.
    #
    # A failed import is reported, not swallowed. Falling back to literals
    # would rebuild the defect the import exists to remove, and "could not
    # read the engine's tolerances" is a different fact from "the numerics
    # are fine".
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from caterva.core.data_structures import (
            DEFAULT_ABSOLUTE_TOLERANCE,
            DEFAULT_RELATIVE_TOLERANCE,
        )
    except Exception as exc:
        bad(f"could not read the engine's integrator tolerances: {exc}",
            "this check cannot verify the settings the product uses; "
            "fix the import before trusting a green run")
        return

    runner = roadrunner.RoadRunner(sbml)
    runner.integrator.relative_tolerance = DEFAULT_RELATIVE_TOLERANCE
    runner.integrator.absolute_tolerance = DEFAULT_ABSOLUTE_TOLERANCE
    result = runner.simulate(0, t, 2)
    simulated = float(result[-1][1])
    ok("roadrunner integrated the model")

    # Exact implicit solution: Km*ln(S0/S) + (S0 - S) = Vmax*t.
    lo, hi = 1e-12, s0
    for _ in range(200):
        mid = (lo + hi) / 2
        if km * math.log(s0 / mid) + (s0 - mid) - vmax * t > 0:
            lo = mid
        else:
            hi = mid
    exact = (lo + hi) / 2

    error = abs(simulated - exact) / exact
    if error < 1e-6:
        ok(f"result matches the exact solution (relative error {error:.2e}) "
           f"at the engine's own tolerances "
           f"({DEFAULT_RELATIVE_TOLERANCE:.0e}/{DEFAULT_ABSOLUTE_TOLERANCE:.0e})")
    else:
        bad(f"numerical result is wrong: got {simulated:.10f}, "
            f"expected {exact:.10f} (relative error {error:.2e})",
            "reinstall libroadrunner; do not trust results until this passes")


def main() -> int:
    print("=" * 66)
    print("Caterva environment check")
    print("=" * 66)

    check_python()
    check_imports()
    check_test_deps()
    check_end_to_end()

    print("\n" + "=" * 66)
    if failures:
        print(f"{RED}{len(failures)} check(s) failed.{RESET} "
              "The environment is not ready.")
        return 1
    if warnings:
        print(f"{GREEN}Environment OK{RESET} "
              f"({len(warnings)} warning(s) above).")
        return 0
    print(f"{GREEN}Environment OK.{RESET} Run `make test` next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
