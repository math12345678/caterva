# Terrium Guard Scripts

This directory contains executable guard scripts that enforce code quality,
contract compliance, and structural integrity across the Terrium codebase.

## Overview

The guards implement **Rule 1** (every numerical claim must be checked against
a closed-form solution or physical invariant) and **Rule 4** (shared constraints
must be enforced by executable tests) at the build level. They run as part of:

- Pre-commit hooks
- CI/CD pipelines  
- Manual verification before deployment

## Available Guards

### 📚 `check_citation_format.py`

**Purpose**: Ensures every `modelCitations` entry carries sufficient bibliographic
detail to be independently verifiable.

**Triggered by**: Stage 4 Part 4 finding that 3 of 7 literature references were
wrong (fabricated or truncated titles).

**Rules**:
- Non-empty
- If contains a URL → accept (database citations are URL-only)
- Otherwise require: authors + year in parentheses + (volume/pages or publisher)

**Usage**:
```bash
python scripts/check_citation_format.py
```

**Scope**: `queryResolver.ts` (only file with static modelCitations entries)

---

### 🏗️ `check_engine_contract.py`

**Purpose**: Verifies that the modular Python engine maintains the same public API
and behavior as the original monolithic `tellurium_engine.py`.

**Checks**:
1. Shim import structure (dual try/except pattern)
2. Module structure (all expected modules exist)
3. Import compatibility (both package and flat mode work)
4. `__all__` exports (all 84 names resolve correctly)
5. Rule 2 contract (ParameterValidation has ok/flagged/flag_reason)

**Usage**:
```bash
python scripts/check_engine_contract.py
```

---

### 📦 `check_dependencies_declared.py`

**Purpose**: Ensures every third-party import is declared in `requirements.txt`
or `requirements-dev.txt`.

**Scope**: All Python files in the Tellurium package.

**Usage**:
```bash
python scripts/check_dependencies_declared.py
```

---

### ⚙️ `check_plausibility_constants.py`

**Purpose**: Verifies that all plausibility constants used in validation have
consistent values across the modular Python codebase.

**Checks**:
1. Constant consistency (same value across all modules)
2. Missing constants (all expected constants are defined)
3. Constant usage (constants are actually used in validation)

**Expected Constants**:
- MM: `KM_PLAUSIBLE_MIN_MM`, `KM_PLAUSIBLE_MAX_MM`
- SIR: `R0_IMPLAUSIBLE_ABOVE`
- PCR: `PCR_MIN_EFFICIENCY`, `PCR_MAX_EFFICIENCY`, `PCR_PLAUSIBLE_LOW_EFFICIENCY`
- MC: `MC_PLAUSIBLE_MIN_SAMPLES`
- WF: `WF_PLAUSIBLE_MIN_POPULATION_SIZE`, `WF_PLAUSIBLE_MAX_GENERATIONS`, etc.
- MD: `MD_PLAUSIBLE_MIN_PARTICLES`, `MD_PLAUSIBLE_MAX_TIMESTEP`, etc.
- General: `DEFAULT_RELATIVE_TOLERANCE`, `DEFAULT_ABSOLUTE_TOLERANCE`, `GAMMA_PARAM`

**Usage**:
```bash
python scripts/check_plausibility_constants.py
```

---

### 🎯 `check_rng_convention.py`

**Purpose**: Enforces the random number generator convention used throughout
Terrium (ADR 0005): every stochastic domain must use
`numpy.random.default_rng(seed)` with `seed: int | None = None`.

**Usage**:
```bash
python scripts/check_rng_convention.py
```

---

### 📊 `check_documented_counts.py`

**Purpose**: Verifies that README test counts, domain counts, and the actual
repository counts match. Any inconsistency — a domain added without updating
the README's claim — is a build failure.

**Usage**:
```bash
python scripts/check_documented_counts.py
```

---

### 🔢 `check_python_support_claim.py`

**Purpose**: Verifies that every file claiming a Python support window
(README, CONTRIBUTING, Makefile gate) states the same range consistently.
With `--online`, also checks PyPI wheel coverage.

**Usage**:
```bash
python scripts/check_python_support_claim.py [--online]
```

---

### 📦 `check_forbidden_packages.py`

**Purpose**: Enforces Rules 7 and 8 of the constitution: no dependency
manifest lists `tellurium` (the umbrella package), and every ADR is indexed
exactly once in `docs/adr/README.md`.

**Usage**:
```bash
python scripts/check_forbidden_packages.py
```

---

### 🔗 `check_guard_wiring.py`

**Purpose**: Ensures every guard script runs in at least one harness
(verify_build, CI, or a pytest wrapper). A guard that runs nowhere is a
guard that rots — this is the executable form of the Stage 4 amendment.

**Usage**:
```bash
python scripts/check_guard_wiring.py
```

---

### 🤫 `check_no_silent_skips.py`

**Purpose**: Runs both test suites and fails if any test is skipped without
explicit reason. Catches `@pytest.mark.skip` with no explanation and
`@unittest.skip` without a message.

**Usage**:
```bash
python scripts/check_no_silent_skips.py
```

**Note**: This guard is deliberately narrow — it runs only in CI because it
executes both full test suites (~5 min).

---

### 🔧 `check_env.py`

**Purpose**: Verifies the installed environment — imports roadrunner,
builds a real Michaelis-Menten model, integrates it, and compares the
result to the exact closed-form solution. This is `make check`.

**Usage**:
```bash
python scripts/check_env.py
```

**Note**: This guard is deliberately narrow — it is an environment probe,
not a repository check. It runs in CI to confirm the container image is
valid before any other step.

---

## Composite Verification

### 🚀 `verify_build.py`

**Purpose**: Runs all static analysis guards and test suites in one command.

**Usage**:
```bash
# Full verification (all guards + all tests)
python scripts/verify_build.py

# Quick verification (guards only, no long tests)
python scripts/verify_build.py --quick

# Custom verification
python scripts/verify_build.py --no-python      # Skip Python tests
python scripts/verify_build.py --no-typescript  # Skip TypeScript tests
python scripts/verify_build.py --quick --no-typescript  # Fastest option
```

**Options**:
- `--quick`: Run only fast guards (skip long-running test suites)
- `--no-python`: Skip Python tests
- `--no-typescript`: Skip TypeScript tests

**Exit Codes**:
- `0`: All checks passed ✅
- `1`: Some checks failed ❌

---

## Integration

### Pre-commit Hook

To add these guards to your pre-commit hook, add to `.git/hooks/pre-commit`:

```bash
#!/bin/sh
python scripts/verify_build.py --quick
```

### CI/CD Pipeline

In your CI configuration (e.g., GitHub Actions):

```yaml
- name: Run Build Verification
  run: python scripts/verify_build.py
```

### Development Workflow

Before committing:
```bash
# Quick check (fast)
python scripts/verify_build.py --quick

# Full verification (thorough, takes ~10-15 minutes)
python scripts/verify_build.py
```

## Guard Development

When adding a new guard:

1. **Identify the contract** being enforced (what rule does this guard implement?)
2. **Define the scope** (which files does it check?)
3. **Implement the check** (what constitutes a violation?)
4. **Add tests** for the guard itself
5. **Integrate into verify_build.py**
6. **Document in this README**

## Historical Context

These guards were developed in response to specific failures:

- **Stage 2**: Mutation report claimed 3 failing tests when only 2 failed
- **Stage 3**: Comment cited non-existent section `STAGE_04_PART_01 §6.3`
- **Stage 4 Part 2**: MD timing of "~11s" was never measured
- **Stage 4 Part 4**: Paper title that does not exist (Hoare & Pal)

Each guard converts "someone should check this" into "this cannot merge if unchecked",
which is the difference between a review habit and a build guard.

## Performance

| Guard | Typical Runtime | Notes |
|-------|----------------|-------|
| Citation Format | <1s | Single file check |
| Engine Contract | 1-2s | Multiple imports |
| Dependencies | <1s | File system scan |
| Plausibility Constants | <1s | AST parsing |
| Python Tests | 120–300s | Full test suite (883 engine + 223 literature) |
| TypeScript Tests | 15–30s | vitest (220 tests across 15 files) |

Use `--quick` for development workflows where you want immediate feedback.