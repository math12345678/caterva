# Caterva Engine Refactoring Proposal

## Overview

The current `caterva/caterva_engine.py` file is 4,283 lines with 64 top-level definitions. This proposal outlines a modular refactoring to improve maintainability while preserving all functionality.

## Current Structure Analysis

### File Size and Complexity
- **Total lines**: 4,283
- **Top-level definitions**: 64 (4 classes, 60 functions)
- **Imports**: ~30 external dependencies
- **Logical sections**: ~8 distinct functional areas

### Identified Functional Areas

#### 1. Core Data Structures (Lines ~133-185, ~53 lines)
- `ModelBuildError` (Exception)
- `SimulationError` (Exception) 
- `ParameterValidation` (dataclass)
- `SimulationResult` (dataclass)
- Constants: DEFAULT_RELATIVE_TOLERANCE, DEFAULT_ABSOLUTE_TOLERANCE, etc.

#### 2. Validation Functions (Lines ~635-780, ~145 lines)
- `_finite_positive()` (helper)
- `validate_michaelis_menten_params()`
- `validate_sir_params()`
- `validate_seir_params()`
- `validate_pcr_params()`
- `validate_monte_carlo_params()`
- `validate_wright_fisher_params()`
- `validate_md_params()`

#### 3. SBML/Model Building (Lines ~807-1050, ~243 lines)
- `_fmt()` (helper)
- `build_michaelis_menten_antimony()`
- `build_sir_antimony()`
- `build_seir_antimony()`
- `_check_model_name()` (helper)
- `antimony_to_sbml()`
- `sbml_to_antimony()`
- `validate_sbml()`
- `_load_runner()` (helper)
- `simulate_sbml()`

#### 4. Continuous Domain Simulations (Lines ~1050-1350, ~300 lines)
- `simulate_michaelis_menten()`
- `simulate_sir()`
- `simulate_seir()`
- `steady_state()`
- `parameter_scan()`

#### 5. Discrete/Population Genetics (Lines ~1571-3400, ~1829 lines)
**Note**: This is the largest section, containing:
- Core Wright-Fisher functions: `validate_wright_fisher_params()`, `simulate_wright_fisher()`
- Wright-Fisher analysis: `_clamp_wf_fst_roundoff()`, `wright_fisher_sweep()`
- Probability calculations: `_wf_p_adj()`, `_binom_pmf_log()`, `wright_fisher_transition_matrix()`
- Fixation analysis: `_wf_chain_setup()`, `_wf_fixation_vector()`, `wright_fisher_fixation_probability()`, `wright_fisher_expected_fixation_time()`, `wright_fisher_expected_loss_time()`, `wright_fisher_expected_absorption_time()`, `_normalise_stationary_vector()`, `wright_fisher_stationary_vector()`
- Population genetics: `wright_fisher_stationary_vector()`, `wright_stationary_distribution()`
- Theoretical calculations: `kimura_fixation_probability()`, `expected_fixation_time()`, `estimate_ne_from_heterozygosity()`, `effective_size_harmonic_mean()`, `theoretical_fst()`, `expected_fst_after_split()`
- Two-locus: `TwoLocusResult` (class), `_tl_validate()`, `simulate_two_locus_wright_fisher()`
- Scenarios: `list_scenarios()`, `wright_fisher_scenario()`

#### 6. PCR Simulations (Lines ~1258-1390, ~132 lines)
- `validate_pcr_params()`
- `simulate_pcr()`

#### 7. Monte Carlo Simulations (Lines ~1390-1480, ~90 lines)
- `validate_monte_carlo_params()`
- `simulate_monte_carlo_pi()`

#### 8. Molecular Dynamics (Lines ~3775-4283, ~508 lines)
- `lennard_jones_force()`
- `_fcc_lattice_positions()` (helper)
- `_golden_section_lj13_scale()` (helper)
- `lj_cluster_positions()`
- `validate_md_params()`
- `simulate_molecular_dynamics()`
- `_compute_pairwise_forces()` (helper)
- `_compute_lj_potential()` (helper)

## Proposed Refactoring Structure

### Option A: Domain-Based Split (Recommended)

This preserves the existing domain organization and creates clear separation:

```
caterva/
├── __init__.py                    # Current exports preserved
├── caterva_engine.py           # Keep as main entry point with imports
├── core/
│   ├── __init__.py               # Re-export everything
│   ├── data_structures.py        # ModelBuildError, SimulationError, ParameterValidation, SimulationResult, constants
│   ├── validation.py             # All validate_* functions
│   └── utils.py                  # Helper functions (_finite_positive, _fmt, _check_model_name, etc.)
│
├── continuous/
│   ├── __init__.py
│   ├── model_building.py         # SBML-related functions
│   └── simulations.py            # simulate_sbml, simulate_michaelis_menten, simulate_sir, simulate_seir
│
├── discrete/
│   ├── __init__.py
│   ├── pcr.py                    # validate_pcr_params, simulate_pcr
│   ├── monte_carlo.py            # validate_monte_carlo_params, simulate_monte_carlo_pi
│   ├── molecular_dynamics.py     # All MD functions
│   └── population_genetics/      # Large population genetics domain
│       ├── __init__.py
│       ├── core.py               # simulate_wright_fisher, validate_wright_fisher_params
│       ├── analysis.py           # Wright-Fisher analysis functions
│       ├── probability.py        # Probability calculation functions
│       ├── theoretical.py         # Theoretical calculations (kimura, fst, etc.)
│       └── two_locus.py          # TwoLocusResult, simulate_two_locus_wright_fisher
│
└── scenarios/
    ├── __init__.py
    └── wf_scenarios.py            # list_scenarios, wright_fisher_scenario
```

### Option B: Function-Based Split

Alternative organization by function type:

```
caterva/
├── __init__.py
├── caterva_engine.py           # Main entry point
├── core.py                      # Data structures and constants
├── validation.py                # All validation functions
├── model_building.py           # SBML/antimony functions
├── simulations/
│   ├── continuous.py            # Continuous domain simulations
│   ├── discrete.py              # Discrete simulations
│   └── special.py               # Special cases (PCR, Monte Carlo)
└── population_genetics.py       # All Wright-Fisher and related functions
```

## Recommended: Option A (Domain-Based)

This aligns with the existing mental model of "domains" in the codebase and makes it easier to:
1. Add new domains without affecting existing code
2. Test domains in isolation
3. Understand the codebase organization

## Implementation Plan

### Phase 1: Create Module Structure (No Breaking Changes)
1. Create new module files
2. Move functions to appropriate modules with proper imports
3. Update `caterva_engine.py` to import from new modules
4. Ensure all tests still pass

### Phase 2: Update __init__.py
1. Update imports to pull from new module structure
2. Ensure backward compatibility

### Phase 3: Cleanup and Optimization
1. Remove circular dependencies
2. Optimize imports
3. Add module-level docstrings

## Dependency Analysis

### Internal Dependencies
The main dependencies between sections are:
- **Core data structures** → Used by everything
- **Validation functions** → Used by simulation functions
- **SBML functions** → Used by continuous simulations
- **Population genetics** → Mostly self-contained
- **Molecular dynamics** → Self-contained

### Circular Dependencies Risk
Low risk identified. The codebase appears to have a clear hierarchy:
- Core structures at the bottom
- Validation in the middle
- Simulation functions at the top

## Migration Strategy

### Step 1: Create data_structures.py
Move these classes and constants:
- `ModelBuildError`
- `SimulationError` 
- `ParameterValidation`
- `SimulationResult`
- All constants (DEFAULT_RELATIVE_TOLERANCE, etc.)

### Step 2: Create validation.py
Move all `validate_*` functions and helpers like `_finite_positive`

### Step 3: Create continuous/ directory
Move SBML and continuous simulation functions

### Step 4: Create discrete/ directory with subdirectories
Move all discrete domain functions with logical grouping

### Step 5: Update caterva_engine.py
Convert to import statements from the new modules

## Verification Strategy
1. Run full test suite after each module extraction
2. Use `python -c "import caterva; print('OK')"` to verify imports work
3. Check that all exported names are still available

## Benefits of This Refactoring

1. **Improved Maintainability**: Smaller, focused files are easier to understand
2. **Better Testability**: Domains can be tested in isolation
3. **Enhanced Collaboration**: Multiple developers can work on different domains
4. **Clearer Organization**: New developers can understand the structure faster
5. **Easier Debugging**: Issues can be isolated to specific modules

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing imports | Keep backward compatibility in __init__.py |
| Circular dependencies | Analyze dependencies before moving functions |
| Test failures | Run tests after each change |
| Performance impact | Minimal - only import structure changes |

## Files to Create

1. `caterva/core/__init__.py`
2. `caterva/core/data_structures.py`
3. `caterva/core/validation.py`
4. `caterva/core/utils.py`
5. `caterva/continuous/__init__.py`
6. `caterva/continuous/model_building.py`
7. `caterva/continuous/simulations.py`
8. `caterva/discrete/__init__.py`
9. `caterva/discrete/pcr.py`
10. `caterva/discrete/monte_carlo.py`
11. `caterva/discrete/molecular_dynamics.py`
12. `caterva/discrete/population_genetics/__init__.py`
13. `caterva/discrete/population_genetics/core.py`
14. `caterva/discrete/population_genetics/analysis.py`
15. `caterva/discrete/population_genetics/probability.py`
16. `caterva/discrete/population_genetics/theoretical.py`
17. `caterva/discrete/population_genetics/two_locus.py`
18. `caterva/scenarios/__init__.py`
19. `caterva/scenarios/wf_scenarios.py`

## Estimated Effort

- **Analysis**: Complete ✓
- **Implementation**: 2-3 hours for full refactoring
- **Testing**: 1-2 hours for comprehensive verification
- **Cleanup**: 30-60 minutes for final touches

Total: ~4-6 hours

## Next Steps

1. **Approve this proposal** - Confirm the domain-based structure (Option A)
2. **Implement Phase 1** - Start with core modules that have minimal dependencies
3. **Verify each step** - Run tests after each module extraction
4. **Complete migration** - Move all functions to appropriate modules
