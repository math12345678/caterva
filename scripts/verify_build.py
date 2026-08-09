#!/usr/bin/env python3
"""
Terrium Build Verification Script.

Comprehensive build verification that runs all static analysis guards
and test suites to ensure the codebase is in a deployable state.

Usage:
    python scripts/verify_build.py [--quick] [--no-python] [--no-typescript] [--live]

Options:
    --quick      Run only the fast guards (skip long-running tests)
    --no-python  Skip Python tests
    --no-typescript Skip TypeScript tests
    --live       Also run network-dependent guards (live citation checks).

Exit codes:
    0: All checks passed
    1: Some checks failed
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
TELLURIUM_DIR = REPO_ROOT / "Tellurium"
API_SERVER_DIR = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server"


def run_command(
    cmd: str,
    cwd: Path | None = None,
    timeout: int = 300,
    capture_output: bool = False
) -> Tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            capture_output=capture_output,
            text=True
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s: {cmd}"
    except Exception as e:
        return False, "", f"Command failed with exception: {e}"
    else:
        success = result.returncode == 0
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        return success, stdout, stderr


def run_guard(
    name: str,
    cmd: str,
    cwd: Path | None = None,
    timeout: int = 120,
) -> Tuple[str, bool, str]:
    """Run a guard and return (name, success, message)."""
    print(f"  Running {name}...", end=" ", flush=True)
    success, stdout, stderr = run_command(cmd, cwd=cwd, timeout=timeout)
    
    if success:
        print("✅", flush=True)
        return name, True, stdout.strip()
    print("❌", flush=True)
    error_msg = stderr.strip() or stdout.strip() or f"Command failed: {cmd}"
    return name, False, error_msg


def run_python_guards() -> List[Tuple[str, bool, str]]:
    """Run all Python guards."""
    guards = []
    
    # Citation format guard
    guards.append(run_guard(
        "Citation Format Guard",
        f"python {SCRIPTS_DIR / 'check_citation_format.py'}"
    ))
    
    # Engine contract guard
    guards.append(run_guard(
        "Engine Contract Guard",
        f"python {SCRIPTS_DIR / 'check_engine_contract.py'}"
    ))
    
    # Dependencies guard
    guards.append(run_guard(
        "Dependencies Guard",
        f"python {SCRIPTS_DIR / 'check_dependencies_declared.py'}"
    ))
    
    # Plausibility constants guard
    guards.append(run_guard(
        "Plausibility Constants Guard",
        f"python {SCRIPTS_DIR / 'check_plausibility_constants.py'}"
    ))

    # Documented counts guard -- README test/domain counts vs reality.
    # Added Stage 7 Part 3 after three counts were found stale by hand.
    guards.append(run_guard(
        "Documented Counts Guard",
        f"python {SCRIPTS_DIR / 'check_documented_counts.py'}"
    ))

    # Python support window stated consistently across requirements.txt,
    # README, CONTRIBUTING and the Makefile gate. Offline; --online adds a
    # PyPI wheel-coverage check. Added Stage 8 after the stated REASON for
    # the window was found wrong in all three files (ADR 0014).
    guards.append(run_guard(
        "Python Support Claim Guard",
        f"python {SCRIPTS_DIR / 'check_python_support_claim.py'}"
    ))

    # Rule 7 (never `pip install tellurium`) made executable. It was one of
    # the nine non-negotiable rules, had ADR 0001 behind it, and adding
    # tellurium to requirements.txt passed every guard in the repo.
    guards.append(run_guard(
        "Constitution Rules 7+8 Guard",
        f"python {SCRIPTS_DIR / 'check_forbidden_packages.py'}"
    ))

    # The Stage 4 amendment made executable: a guard is not delivered until
    # something runs it unasked. check_rng_convention sat wired to nothing
    # for a whole stage, and check_citation_format shipped the same way --
    # both found by hand. This one catches the next occurrence, including
    # itself (it did, on its first run).
    guards.append(run_guard(
        "Guard Wiring Guard",
        f"python {SCRIPTS_DIR / 'check_guard_wiring.py'}"
    ))

    return guards


def run_python_tests(quick: bool = False) -> List[Tuple[str, bool, str]]:
    """Run Python tests."""
    tests: List[Tuple[str, bool, str]] = []

    if quick:
        # Run a representative sample of tests
        test_files = [
            "tests/test_validation.py",
            "tests/test_engine_api.py",
            "tests/test_rng_convention.py",
        ]
        tests.extend(
            run_guard(
                f"Python Test: {test_file}",
                f"python -m pytest {test_file} -v",
                cwd=TELLURIUM_DIR
            )
            for test_file in test_files
        )
    else:
        # Run all Python tests
        tests.append(run_guard(
            "Python All Tests",
            "python -m pytest tests/ -x --tb=short",
            cwd=TELLURIUM_DIR,
            timeout=600  # 10 minutes for full test suite
        ))
    
    return tests


def run_typescript_tests() -> List[Tuple[str, bool, str]]:
    """Run TypeScript tests."""
    tests = []
    
    # Run npm test
    tests.append(run_guard(
        "TypeScript Tests",
        "npm test",
        cwd=API_SERVER_DIR,
        timeout=300
    ))
    
    return tests


def run_live_citation_guard() -> List[Tuple[str, bool, str]]:
    """Run the live citation-verification guard (network required).

    verify_citations_live.py re-fetches every golden-set BRENDA page, PMID,
    and DOI the resolvers cite, plus every static modelCitations URL. It is
    a report, not a gate -- literature pages get restructured -- so it is
    opt-in via --live rather than part of the always-run guard set.
    """
    return [
        run_guard(
            "Live Citation Verification",
            f"python {SCRIPTS_DIR / 'verify_citations_live.py'}",
            timeout=180,
        )
    ]


def run_rng_guard() -> List[Tuple[str, bool, str]]:
    """Run RNG convention guard."""
    guards = []
    
    rng_guard = SCRIPTS_DIR / "check_rng_convention.py"
    if rng_guard.exists():
        guards.append(run_guard(
            "RNG Convention Guard",
            f"python {rng_guard}"
        ))
    
    return guards


def print_results(
    title: str,
    results: List[Tuple[str, bool, str]]
) -> int:
    """Print results and return number of failures."""
    print(f"\n{title}:")
    print("-" * 50)
    
    failures = 0
    for name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")
        if not success and message:
            print(f"    Error: {message}")
            failures += 1
    
    return failures


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Terrium Build Verification Script"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast checks (skip long-running tests)"
    )
    parser.add_argument(
        "--no-python",
        action="store_true",
        help="Skip Python tests"
    )
    parser.add_argument(
        "--no-typescript",
        action="store_true",
        help="Skip TypeScript tests"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run network-dependent guards (live citation checks)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TERRIUM BUILD VERIFICATION")
    print("=" * 60)
    
    start_time = time.time()
    total_failures = 0
    
    # Run guards
    print("\n🛡️  STATIC ANALYSIS GUARDS")
    
    # Python guards
    python_guards = run_python_guards()
    total_failures += print_results("Python Guards", python_guards)
    
    # RNG guard
    rng_results = run_rng_guard()
    if rng_results:
        total_failures += print_results("RNG Guard", rng_results)

    # Live citation guard (network; opt-in so offline builds stay green)
    if args.live:
        print("\n🛡️  LIVE LITERATURE GUARD")
        live_results = run_live_citation_guard()
        total_failures += print_results("Live Citation Guard", live_results)
    
    # Run tests if not quick mode or explicitly requested
    if not args.quick:
        # Python tests
        if not args.no_python:
            print("\n🧪  PYTHON TESTS")
            python_tests = run_python_tests(quick=False)
            total_failures += print_results("Python Tests", python_tests)
        
        # TypeScript tests
        if not args.no_typescript:
            print("\n🧪  TYPESCRIPT TESTS")
            ts_tests = run_typescript_tests()
            total_failures += print_results("TypeScript Tests", ts_tests)
    else:
        print("\n📝  Running in quick mode - skipped long tests")
    
    # Summary
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if total_failures == 0:
        print(f"✅ ALL CHECKS PASSED in {duration:.1f}s")
        print("\n🎉 The codebase is in a deployable state!")
        return 0
    print(f"❌ {total_failures} CHECK(S) FAILED in {duration:.1f}s")
    print("\n⚠️  Please fix the issues above before deploying.")
    return 1


if __name__ == '__main__':
    sys.exit(main())