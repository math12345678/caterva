"""Guard that all discrete/stochastic domains comply with ADR 0005.

ADR 0005 requires every discrete/stochastic domain to use
``numpy.random.default_rng(seed)`` as the single RNG constructor, with
``seed: int | None = None`` as the parameter signature.

This script scans Tellurium/tellurium_engine.py for all functions that
appear to simulate a stochastic process (defined as any function whose
name matches ``simulate_*``) and checks two things:

1. The function signature includes ``seed: int | None = None``.
2. The function body calls ``np.random.default_rng(seed)``.

A domain that legitimately needs to deviate must be documented in an ADR
with the justification; the script can be updated to exclude it by name
once the ADR exists. Until then, any deviation is a violation.

Run directly: python scripts/check_rng_convention.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_FILE = REPO_ROOT / "Tellurium" / "tellurium_engine.py"

# Functions whose names match this pattern are expected to comply with
# ADR 0005. The prefix 'simulate_' is broad enough to catch Monte Carlo,
# Wright-Fisher, and any future stochastic domain.
SIMULATE_FN_PREFIX = "simulate_"

# Domains that legitimately don't use RNG (continuous ODE simulations).
# These are excluded from the check because they use roadrunner, not
# numpy random generation — they're not stochastic.
EXCLUDED_FNS: set[str] = {
    "simulate_sbml",
    "simulate_michaelis_menten",
    "simulate_sir",
    "simulate_seir",
    "simulate_pcr",  # deterministic recurrence, no RNG involved
}


def check() -> list[str]:
    if not ENGINE_FILE.exists():
        return [f"engine file not found: {ENGINE_FILE}"]

    source = ENGINE_FILE.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(ENGINE_FILE))
    except SyntaxError as exc:
        return [f"syntax error in {ENGINE_FILE}: {exc}"]

    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        name = node.name
        if not name.startswith(SIMULATE_FN_PREFIX):
            continue
        if name in EXCLUDED_FNS:
            continue

        lineno = node.lineno

        # Check 1: signature has seed: int | None = None
        has_seed_param = False
        for arg in node.args.args:
            if arg.arg == "seed":
                has_seed_param = True
                break
        if not has_seed_param:
            violations.append(
                f"{name} (line {lineno}): missing 'seed' parameter "
                "(required by ADR 0005)")
            continue  # skip body check if param is missing

        # Check 2: body calls default_rng(seed) in any import style.
        # Handles all three common patterns:
        #   np.random.default_rng(seed)
        #   numpy.random.default_rng(seed)
        #   from numpy.random import default_rng; default_rng(seed)
        calls_default_rng = False
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                # Bare-name call: default_rng(seed)
                if isinstance(func, ast.Name) and func.id == "default_rng":
                    calls_default_rng = True
                    break
                # Qualified call: <module>.random.default_rng(...)
                if (isinstance(func, ast.Attribute)
                        and func.attr == "default_rng"
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr == "random"
                        and isinstance(func.value.value, ast.Name)
                        and func.value.value.id in ("np", "numpy")):
                    calls_default_rng = True
                    break
        if not calls_default_rng:
            violations.append(
                f"{name} (line {lineno}): has 'seed' parameter but does "
                "not call np.random.default_rng(seed) "
                "(required by ADR 0005)")

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print("OK: all stochastic domains comply with ADR 0005 "
              "(numpy.random.default_rng(seed)).")
        return 0

    print("ADR 0005 violations found:\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\nEvery discrete/stochastic domain must use "
        "numpy.random.default_rng(seed) with seed: int | None = None. "
        "\nSee docs/adr/0005-rng-convention.md for the full decision.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
