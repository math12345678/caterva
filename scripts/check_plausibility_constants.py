"""
Plausibility constants consistency guard for Caterva.

Verifies that all plausibility constants used in validation have consistent
values across the modular Python codebase. This ensures that the Rule 2
contract (physically impossible vs. physically implausible) is enforced consistently.

Usage:
    python scripts/check_plausibility_constants.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


# Constants that should have consistent values across modules.
# NOTE: the engine's definitions in caterva/core/data_structures.py are
# the single source of truth — these values must match them exactly. The
# list was stale (14 of 19 mismatched) and the old code only value-checked
# constants defined in 2+ files, so the drift was silent; the check below
# now verifies every EXPECTED constant against its actual definition.
EXPECTED_CONSTANTS = {
    'KM_PLAUSIBLE_MIN_MM': 1e-07,
    'KM_PLAUSIBLE_MAX_MM': 1000.0,
    'KCAT_PLAUSIBLE_MIN_PER_S': 1e-06,
    'KCAT_PLAUSIBLE_MAX_PER_S': 1e09,
    'ENZYME_CONC_MM_RATIO_FLAG_ABOVE': 0.01,
    'R0_IMPLAUSIBLE_ABOVE': 20.0,
    'PCR_MIN_EFFICIENCY': 0.0,
    'PCR_MAX_EFFICIENCY': 1.0,
    'PCR_PLAUSIBLE_LOW_EFFICIENCY': 0.5,
    'MC_PLAUSIBLE_MIN_SAMPLES': 100,
    'WF_PLAUSIBLE_MIN_POPULATION_SIZE': 10,
    'WF_PLAUSIBLE_MAX_GENERATIONS': 10000,
    'WF_PLAUSIBLE_MIN_REPLICATE_RUNS': 10,
    'WF_PLAUSIBLE_MAX_MUTATION_RATE': 0.01,
    'WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT': 0.5,
    'MD_PLAUSIBLE_MIN_PARTICLES': 10,
    'MD_PLAUSIBLE_MAX_TIMESTEP': 0.01,
    'MD_PLAUSIBLE_TEMPERATURE_LOW': 0.1,
    'MD_PLAUSIBLE_TEMPERATURE_HIGH': 0.8,
    'SSA_PLAUSIBLE_MIN_POPULATION': 30,
    'SSA_PLAUSIBLE_MAX_RATE': 10.0,
    'SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE': 0.1,
    'SSA_PLAUSIBLE_MIN_REPLICATES': 10,
    'DEFAULT_RELATIVE_TOLERANCE': 1e-10,
    'DEFAULT_ABSOLUTE_TOLERANCE': 1e-12,
    'GAMMA_PARAM': 'gamma_rate',
}


def extract_constants_from_file(
    filepath: Path, errors: List[str]
) -> Dict[str, Any]:
    """Extract constant definitions from a Python file."""
    constants = {}
    
    try:
        content = filepath.read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        const_name = target.id
                        if const_name in EXPECTED_CONSTANTS:
                            # Extract the value
                            if isinstance(node.value, ast.Constant):
                                constants[const_name] = node.value.value
                            elif isinstance(node.value, ast.Num):  # Python 3.7 compatibility
                                constants[const_name] = node.value.n
                            elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
                                if isinstance(node.value.operand, ast.Constant) and isinstance(
                                    node.value.operand.value, (int, float)
                                ):
                                    constants[const_name] = -node.value.operand.value
                                elif isinstance(node.value.operand, ast.Num) and isinstance(
                                    node.value.operand.n, (int, float)
                                ):
                                    constants[const_name] = -node.value.operand.n
                            elif isinstance(node.value, ast.Str):
                                constants[const_name] = node.value.s
    except Exception as e:
        errors.append(f"Error parsing {filepath}: {e}")
    
    return constants


def _normalise(value: Any) -> Any:
    """Compare constants by VALUE, not by how they were spelled.

    `1e3`, `1000` and `1000.0` are the same bound written three ways, and
    they legitimately appear as all three across the engine and the
    literature layer. Comparing `str(v)` reported them as a conflict --
    a false positive, which is worse than useless in a guard: it trains
    people to ignore the output, and the next real drift goes with it.

    Non-numeric constants (e.g. GAMMA_PARAM = 'gamma_rate') fall through
    to string comparison unchanged.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def _collect_py_files(repo_root: Path) -> List[Path]:
    """Python files that may define plausibility constants.

    Both sides of the ADR 0003 contract: the simulation engine and the
    literature layer. Excludes the venv and bytecode caches.
    """
    files: List[Path] = []
    for sub in ('caterva', 'Tests'):
        directory = repo_root / sub
        if not directory.is_dir():
            continue
        files.extend(
            f for f in directory.rglob('*.py')
            if '.venv' not in f.parts and '__pycache__' not in f.parts
        )
    return files


def check_constants_consistency() -> List[str]:
    """Check that all plausibility constants have consistent values."""
    errors: List[str] = []
    repo_root = Path(__file__).parent.parent

    # Both layers, not just the engine. ADR 0003 makes the Km plausibility
    # bounds a contract BETWEEN the literature layer and the simulation
    # layer, and the real bug it was written for was exactly a cross-layer
    # split (engine 1e4 vs BRENDA 1e3, so a Km of 5000 mM was flagged
    # upstream and silently accepted downstream).
    #
    # This guard scanned caterva/ only, so Tests/brenda_client.py -- the
    # other half of the contract -- was outside its search path entirely.
    # Verified: setting brenda_client's KM_PLAUSIBLE_MAX_MM to 9999 while
    # the engine said 1000 PASSED this guard before this change.
    py_files = _collect_py_files(repo_root)

    # Collect all constant definitions
    all_constants: Dict[str, Dict[str, Any]] = {}
    
    for py_file in py_files:
        constants = extract_constants_from_file(py_file, errors)
        for name, value in constants.items():
            if name not in all_constants:
                all_constants[name] = {}
            all_constants[name][str(py_file)] = value
    
    # Check consistency. Every EXPECTED constant is verified against its
    # actual definition(s) — a constant defined in a single file is still
    # checked, so a stale expected value (or a silently changed engine
    # constant) is caught instead of passing because no second definition
    # existed to compare against.
    for const_name, sources in all_constants.items():
        values = {_normalise(v) for v in sources.values()}
        if len(values) > 1:
            errors.append(f"Constant {const_name} has inconsistent values: {dict(sources)}")
        elif const_name in EXPECTED_CONSTANTS:
            expected = EXPECTED_CONSTANTS[const_name]
            actual = next(iter(sources.values()))
            if _normalise(actual) != _normalise(expected):
                errors.append(f"Constant {const_name} has unexpected value: expected {expected}, got {actual}")

    return errors


def check_missing_constants() -> List[str]:
    """Check that all expected constants are defined."""
    errors: List[str] = []
    
    repo_root = Path(__file__).parent.parent

    # Both layers -- see _collect_py_files.
    py_files = _collect_py_files(repo_root)

    # Collect all defined constants
    defined_constants: set[str] = set()
    
    for py_file in py_files:
        constants = extract_constants_from_file(py_file, errors)
        defined_constants.update(constants.keys())
    
    # Check for missing expected constants
    missing = [
        const_name for const_name in EXPECTED_CONSTANTS
        if const_name not in defined_constants
    ]
    
    if missing:
        errors.append(f"Missing expected constants: {missing}")
    
    return errors


def check_constant_usage() -> List[str]:
    """Check that every expected constant is actually USED somewhere.

    A plausibility bound that is defined but referenced by nothing bounds
    nothing. `KM_PLAUSIBLE_MAX_MM` existing in data_structures.py says
    only that a number was written down; the guard has to establish that
    some validator reads it.

    THIS FUNCTION USED TO CHECK NOTHING. Its loop body was:

        for const_name in EXPECTED_CONSTANTS:
            if const_name in content:
                continue
            if const_name.startswith('WF_') or const_name.startswith('MD_'):
                continue

    -- two `continue`s and no `errors.append` anywhere inside. Every path
    fell through, so `errors` could only become non-empty via the missing-
    file guard or the `except` handler. For any readable validation.py it
    returned [] no matter what that file contained: deleting every use of
    every bound would still have printed the guard's OK line.

    It also looked only at caterva/core/validation.py, while the WF_ and
    MD_ constants legitimately live in their domain modules -- which is
    what the second `continue` was papering over. The search now covers
    the whole engine, so those constants can be held to the same standard
    rather than exempted.
    """
    errors: List[str] = []

    repo_root = Path(__file__).parent.parent

    # BOTH layers, matching check_constants_consistency above. ADR 0003
    # makes these bounds a contract between the literature layer
    # (Tests/brenda_client.py) and the simulation layer (caterva/), and
    # the kcat bounds are consumed by the BRENDA parser rather than by a
    # Caterva validator. Scanning only caterva/ reported them as
    # defined-and-unused, which was wrong -- they are used, one layer over.
    search_roots = [repo_root / 'caterva', repo_root / 'Tests']
    missing_roots = [r for r in search_roots if not r.is_dir()]
    if missing_roots:
        return [
            "Expected source directories not found: "
            + ", ".join(str(r) for r in missing_roots)
        ]

    # Files that only DEFINE the constants. A constant appearing in these
    # and nowhere else is defined and unused. Both are listed because the
    # value is deliberately duplicated across the layer boundary (ADR 0003,
    # with the agreement enforced by check_constants_consistency).
    definition_files = {
        repo_root / 'caterva' / 'core' / 'data_structures.py',
        repo_root / 'Tests' / 'brenda_client.py',
    }

    sources: dict[Path, str] = {}
    for root in search_roots:
        for path in root.rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            try:
                sources[path] = path.read_text(encoding='utf-8')
            except OSError as exc:
                errors.append(f"Could not read {path}: {exc}")

    if not sources:
        return [
            "No Python sources found under "
            + ", ".join(r.name for r in search_roots)
            + ". Refusing to report success -- an empty scan is not a "
            "clean tree."
        ]

    for const_name in sorted(EXPECTED_CONSTANTS):
        # A USE is any occurrence that is not the assignment itself.
        #
        # File-level exclusion was wrong: Tests/brenda_client.py both
        # DEFINES the kcat bounds and is their only production reader, so
        # treating it as a definition file hid its own use and the guard
        # failed on a correctly-wired constant.
        #
        # Tests are still not users. A bound referenced only by a test
        # asserting that it exists is not wired into anything: no validator
        # applies it and no simulation is bounded by it. Counting tests let
        # a mutation that inlined the kcat bounds -- removing their only
        # production reader -- pass unnoticed.
        assignment = re.compile(
            rf'^\s*{re.escape(const_name)}\s*(?::[^=]+)?=', re.MULTILINE
        )
        users = []
        for path, content in sources.items():
            if const_name not in content:
                continue
            if path.name.startswith('test_') or path.name.endswith('_test.py'):
                continue
            if 'tests' in path.parts:
                continue
            occurrences = content.count(const_name)
            definitions = len(assignment.findall(content))
            if occurrences > definitions:
                users.append(path)

        if users:
            continue

        defined_in = [
            path
            for path in definition_files
            if path in sources and const_name in sources[path]
        ]
        if defined_in:
            where = ", ".join(sorted(p.name for p in defined_in))
            errors.append(
                f"{const_name} is defined in {where} but read by no other "
                "module in caterva/ or Tests/. A plausibility bound that "
                "nothing reads does not bound anything -- either wire it "
                "into a validator or remove it."
            )
        else:
            errors.append(
                f"{const_name} is expected by this guard but appears in "
                "neither caterva/ nor Tests/."
            )

    return errors



def main() -> int:
    """Main entry point."""
    print("Running plausibility constants guard...")
    print()
    
    all_errors = []
    
    print("1. Checking constant consistency...")
    all_errors.extend(check_constants_consistency())
    
    print("2. Checking for missing constants...")
    all_errors.extend(check_missing_constants())
    
    print("3. Checking constant usage...")
    all_errors.extend(check_constant_usage())
    
    print()
    
    if all_errors:
        print(f"❌ FAILED: Found {len(all_errors)} plausibility constant issues:")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    print("✅ PASSED: All plausibility constants are consistent and complete.")
    return 0


if __name__ == '__main__':
    sys.exit(main())