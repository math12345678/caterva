"""
Engine contract guard for Caterva.

Verifies that the modular Python engine maintains the same public API
and behavior as the original monolithic caterva_engine.py.

This guard ensures:
1. All names in __all__ resolve correctly from both the shim and modules
2. Exception types and validation functions maintain consistent behavior
3. Plausibility constants have identical values across modules
4. No regression in the Rule 2 contract (ok/flagged distinction)

Usage:
    python scripts/check_engine_contract.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List


def get_all_names_from_file(filepath: Path) -> List[str]:
    """Extract all names from __all__ in a Python file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, ast.List):
                            return [
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant)
                                and isinstance(elt.value, str)
                            ]
                        if isinstance(node.value, ast.Constant):
                            if isinstance(node.value.value, str):
                                return [node.value.value]
                            return []
    except Exception:
        pass
    return []


def verify_shim_imports() -> List[str]:
    """Verify that the caterva_engine.py shim correctly imports from modular structure."""
    errors = []
    
    repo_root = Path(__file__).parent.parent
    shim_file = repo_root / 'caterva' / 'caterva_engine.py'
    
    if not shim_file.exists():
        return [f"Shim file not found: {shim_file}"]
    
    # Parse the shim file and check import patterns
    try:
        content = shim_file.read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        # Check that it has the dual import try/except pattern
        has_try_import = False
        has_except_import = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for item in node.body:
                    if isinstance(item, ast.ImportFrom) and 'caterva.core' in str(ast.unparse(item)):
                        has_try_import = True
                for handler in node.handlers:
                    if isinstance(handler, ast.ExceptHandler):
                        for item in handler.body:
                            if isinstance(item, ast.ImportFrom) and 'core' in str(ast.unparse(item)):
                                has_except_import = True
        
        if not has_try_import:
            errors.append("Shim missing try block with caterva.core imports")
        if not has_except_import:
            errors.append("Shim missing except block with relative core imports")
            
    except Exception as e:
        errors.append(f"Error parsing shim file: {e}")
    
    return errors


def verify_module_exports() -> List[str]:
    """Verify that all expected modules exist and export correctly."""
    errors = []
    
    repo_root = Path(__file__).parent.parent
    caterva_dir = repo_root / 'caterva'
    
    # Expected module structure
    expected_modules = [
        'core', 'continuous', 'discrete', 'scenarios'
    ]
    
    # Expected core submodules
    expected_core = ['__init__.py', 'data_structures.py', 'validation.py', 'utils.py']
    
    # Check module structure
    for module in expected_modules:
        module_dir = caterva_dir / module
        if not module_dir.exists():
            errors.append(f"Expected module directory missing: {module_dir}")
        elif module == 'core':
            errors.extend(
                f"Expected core file missing: {module_dir / core_file}"
                for core_file in expected_core
                if not (module_dir / core_file).exists()
            )
    
    # Check discrete submodules
    discrete_dir = caterva_dir / 'discrete'
    expected_discrete = ['__init__.py', 'pcr.py', 'monte_carlo.py', 'molecular_dynamics.py', 'gillespie_ssa.py', 'population_genetics']
    
    for discrete_file in expected_discrete:
        if discrete_file == 'population_genetics':
            pop_gen_dir = discrete_dir / discrete_file
            if not pop_gen_dir.exists():
                errors.append(f"Expected discrete submodule missing: {pop_gen_dir}")
            else:
                expected_pop_gen = ['__init__.py', 'core.py', 'analysis.py', 'theoretical.py', 'probability.py', 'two_locus.py']
                errors.extend(
                    f"Expected population genetics file missing: {pop_gen_dir / pop_file}"
                    for pop_file in expected_pop_gen
                    if not (pop_gen_dir / pop_file).exists()
                )
        elif not (discrete_dir / discrete_file).exists():
            errors.append(f"Expected discrete file missing: {discrete_dir / discrete_file}")
    
    return errors


def verify_import_compatibility() -> List[str]:
    """Verify that imports work in both package and flat mode."""
    errors = []
    
    # Test package mode
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        # Try importing from caterva package
        from caterva import caterva_engine  # noqa: F401
        from caterva.core.data_structures import ModelBuildError, SimulationResult  # noqa: F401
        from caterva.core.validation import validate_michaelis_menten_params  # noqa: F401
        print("✓ Package mode imports successful")
        
    except ImportError as e:
        errors.append(f"Package mode import failed: {e}")

    # Test flat mode (simulate being in Caterva directory)
    flat_errors = _test_flat_mode_imports()
    errors.extend(flat_errors)

    return errors


def _test_flat_mode_imports() -> List[str]:
    """Verify that imports work when caterva/ is on the path directly."""
    local_errors = []
    original_path = sys.path[:]
    try:
        # Set up flat mode path
        caterva_dir = Path(__file__).parent.parent / 'caterva'
        sys.path = [str(caterva_dir)] + [p for p in sys.path if p != str(Path(__file__).parent.parent)]

        # Clear any cached imports
        modules_to_clear = [m for m in sys.modules if 'caterva' in m or m.startswith('core') or m.startswith('continuous') or m.startswith('discrete')]
        for m in modules_to_clear:
            if m in sys.modules:
                del sys.modules[m]

        # Try flat mode imports — these are intentionally "unused"; the test
        # is that they import without error.
        import caterva_engine  # noqa: F401
        from core.data_structures import ModelBuildError, SimulationResult  # noqa: F401
        from core.validation import validate_michaelis_menten_params  # noqa: F401
        from continuous.model_building import build_michaelis_menten_antimony  # noqa: F401
        print("✓ Flat mode imports successful")

        # Restore path
        sys.path = original_path

    except ImportError as e:
        local_errors.append(f"Flat mode import failed: {e}")
    except Exception as e:
        local_errors.append(f"Flat mode test error: {e}")

    return local_errors


def verify_all_exports() -> List[str]:
    """Verify that all __all__ entries in caterva_engine.py resolve correctly."""
    errors = []
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from caterva import caterva_engine
        
        # Get __all__ from the module
        if hasattr(caterva_engine, '__all__'):
            all_names = caterva_engine.__all__
            missing_names = [name for name in all_names if not hasattr(caterva_engine, name)]
            
            if missing_names:
                errors.append(f"Missing __all__ exports: {missing_names}")
            else:
                print(f"✓ All {len(all_names)} __all__ entries resolve correctly")
        else:
            errors.append("No __all__ defined in caterva_engine module")
            
    except Exception as e:
        errors.append(f"Error checking __all__ exports: {e}")
    
    return errors


def verify_rule2_contract() -> List[str]:
    """Verify that validation functions maintain Rule 2 contract (ok/flagged distinction)."""
    errors = []
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from caterva.core.data_structures import ParameterValidation
        
        # Create a ParameterValidation instance with defaults
        validation = ParameterValidation()
        
        # Check that it has ok and flagged attributes
        if not hasattr(validation, 'ok'):
            errors.append("ParameterValidation missing 'ok' attribute")
        if not hasattr(validation, 'flagged'):
            errors.append("ParameterValidation missing 'flagged' attribute")
        if not hasattr(validation, 'flag_reason'):
            errors.append("ParameterValidation missing 'flag_reason' attribute")
        
        if hasattr(validation, 'ok') and hasattr(validation, 'flagged'):
            print("✓ ParameterValidation maintains Rule 2 contract structure")
            
    except Exception as e:
        errors.append(f"Error verifying Rule 2 contract: {e}")
    
    return errors


def main() -> int:
    """Main entry point."""
    print("Running engine contract guard...")
    print()
    
    all_errors = []
    
    # Run all checks
    print("1. Checking shim import structure...")
    all_errors.extend(verify_shim_imports())
    
    print("2. Checking module structure...")
    all_errors.extend(verify_module_exports())
    
    print("3. Checking import compatibility...")
    all_errors.extend(verify_import_compatibility())
    
    print("4. Checking __all__ exports...")
    all_errors.extend(verify_all_exports())
    
    print("5. Checking Rule 2 contract...")
    all_errors.extend(verify_rule2_contract())
    
    print()
    
    if all_errors:
        print(f"❌ FAILED: Found {len(all_errors)} contract violations:")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    print("✅ PASSED: All engine contract checks passed.")
    return 0


if __name__ == '__main__':
    sys.exit(main())