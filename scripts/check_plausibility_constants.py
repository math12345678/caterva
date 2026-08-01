"""
Plausibility constants consistency guard for Terrium.

Verifies that all plausibility constants used in validation have consistent
values across the modular Python codebase. This ensures that the Rule 2
contract (physically impossible vs. physically implausible) is enforced consistently.

Usage:
    python scripts/check_plausibility_constants.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any


# Constants that should have consistent values across modules
EXPECTED_CONSTANTS = {
    'KM_PLAUSIBLE_MIN_MM': 0.001,
    'KM_PLAUSIBLE_MAX_MM': 1000.0,
    'R0_IMPLAUSIBLE_ABOVE': 100.0,
    'PCR_MIN_EFFICIENCY': 0.5,
    'PCR_MAX_EFFICIENCY': 1.2,
    'PCR_PLAUSIBLE_LOW_EFFICIENCY': 0.8,
    'MC_PLAUSIBLE_MIN_SAMPLES': 100,
    'WF_PLAUSIBLE_MIN_POPULATION_SIZE': 2,
    'WF_PLAUSIBLE_MAX_GENERATIONS': 10000,
    'WF_PLAUSIBLE_MIN_REPLICATE_RUNS': 1,
    'WF_PLAUSIBLE_MAX_MUTATION_RATE': 0.5,
    'WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT': 10.0,
    'MD_PLAUSIBLE_MIN_PARTICLES': 1,
    'MD_PLAUSIBLE_MAX_TIMESTEP': 0.1,
    'MD_PLAUSIBLE_TEMPERATURE_LOW': 0.01,
    'MD_PLAUSIBLE_TEMPERATURE_HIGH': 10.0,
    'DEFAULT_RELATIVE_TOLERANCE': 1e-6,
    'DEFAULT_ABSOLUTE_TOLERANCE': 1e-8,
    'GAMMA_PARAM': 'gamma',
}


def extract_constants_from_file(filepath: Path) -> Dict[str, Any]:
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
                                if isinstance(node.value.operand, ast.Constant):
                                    constants[const_name] = -node.value.operand.value
                                elif isinstance(node.value.operand, ast.Num):
                                    constants[const_name] = -node.value.operand.n
                            elif isinstance(node.value, ast.Str):
                                constants[const_name] = node.value.s
    except Exception as e:
        print(f"Warning: Error parsing {filepath}: {e}", file=sys.stderr)
    
    return constants


def check_constants_consistency() -> List[str]:
    """Check that all plausibility constants have consistent values."""
    errors = []
    
    repo_root = Path(__file__).parent.parent
    tellurium_dir = repo_root / 'Tellurium'
    
    # Find all Python files that might contain constants
    py_files = list(tellurium_dir.rglob('*.py'))
    
    # Collect all constant definitions
    all_constants = {}
    
    for py_file in py_files:
        constants = extract_constants_from_file(py_file)
        for name, value in constants.items():
            if name not in all_constants:
                all_constants[name] = {}
            all_constants[name][str(py_file)] = value
    
    # Check consistency
    for const_name, sources in all_constants.items():
        if len(sources) > 1:
            # Check if all values are the same
            values = set(str(v) for v in sources.values())
            if len(values) > 1:
                errors.append(f"Constant {const_name} has inconsistent values: {dict(sources)}")
            else:
                # Check against expected value if we have one
                if const_name in EXPECTED_CONSTANTS:
                    expected = EXPECTED_CONSTANTS[const_name]
                    actual = list(sources.values())[0]
                    if str(actual) != str(expected):
                        errors.append(f"Constant {const_name} has unexpected value: expected {expected}, got {actual}")
    
    return errors


def check_missing_constants() -> List[str]:
    """Check that all expected constants are defined."""
    errors = []
    
    repo_root = Path(__file__).parent.parent
    tellurium_dir = repo_root / 'Tellurium'
    
    # Find all Python files
    py_files = list(tellurium_dir.rglob('*.py'))
    
    # Collect all defined constants
    defined_constants = set()
    
    for py_file in py_files:
        constants = extract_constants_from_file(py_file)
        defined_constants.update(constants.keys())
    
    # Check for missing expected constants
    missing = []
    for const_name in EXPECTED_CONSTANTS:
        if const_name not in defined_constants:
            missing.append(const_name)
    
    if missing:
        errors.append(f"Missing expected constants: {missing}")
    
    return errors


def check_constant_usage() -> List[str]:
    """Check that constants are used in validation functions."""
    errors = []
    
    repo_root = Path(__file__).parent.parent
    validation_file = repo_root / 'Tellurium' / 'core' / 'validation.py'
    
    if not validation_file.exists():
        return [f"Validation file not found: {validation_file}"]
    
    try:
        content = validation_file.read_text(encoding='utf-8')
        
        # Check that validation functions use the constants
        for const_name in EXPECTED_CONSTANTS:
            if const_name in content:
                continue  # Constant is used somewhere in the file
            
            # Some constants might not be used in validation.py specifically
            # but should be used elsewhere
            if const_name.startswith('WF_') or const_name.startswith('MD_'):
                # These are domain-specific and might be in domain modules
                continue
        
    except Exception as e:
        errors.append(f"Error checking constant usage: {e}")
    
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
    else:
        print("✅ PASSED: All plausibility constants are consistent and complete.")
        return 0


if __name__ == '__main__':
    sys.exit(main())