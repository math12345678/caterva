#!/usr/bin/env python3
"""Verify a Terrium development environment actually works.

Not a version-string check: this imports every engine, builds a real model,
translates it to SBML, integrates it, and compares the answer to a known
closed-form solution. A green run here means the stack is genuinely usable,
not merely installed.

    python3 scripts/check_env.py
"""

from __future__ import annotations

import math
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
    print("\nPython")
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info[2]}"
    if major == 3 and 10 <= minor <= 12:
        ok(f"Python {version} on {platform.machine()}")
    elif major == 3 and minor > 12:
        # Real constraint, not a style preference: python-libsbml and friends
        # publish wheels up to cp312. Past that, pip builds from source and
        # needs cmake + swig present.
        warn(f"Python {version}: SBML wheels may not exist yet; "
             "if install fails, use 3.12")
    else:
        bad(f"Python {version} is too old",
            "install Python 3.12 and recreate the venv")


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

    runner = roadrunner.RoadRunner(sbml)
    runner.integrator.relative_tolerance = 1e-10
    runner.integrator.absolute_tolerance = 1e-12
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
        ok(f"result matches the exact solution (relative error {error:.2e})")
    else:
        bad(f"numerical result is wrong: got {simulated:.10f}, "
            f"expected {exact:.10f} (relative error {error:.2e})",
            "reinstall libroadrunner; do not trust results until this passes")


def main() -> int:
    print("=" * 66)
    print("Terrium environment check")
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
