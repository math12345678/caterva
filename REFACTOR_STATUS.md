# Engine package split — COMPLETE

> **⚠️ CORRECTION (2026-08-12):** the structural claim (shim holds no `simulate_*`/`validate_*`/`build_*` definitions, package split in effect) is still true today — verified directly: `grep -c "^def simulate_\|^def validate_\|^def build_" caterva/caterva_engine.py` returns 0. But the specific numbers below are stale, not current:
> - **"292 lines (was 4283)"** — `caterva_engine.py` is now **356 lines** (it grew after later work added more re-exports for new domains such as `mm_competitive_inhibition`, the SSA variants, `lotka_volterra`, `cell_cycle_oscillator`, `repressilator`).
> - **"49 tests, in two halves"** for `caterva/tests/test_validator_agreement.py` — it currently collects **52** tests (`python3 -m pytest caterva/tests/test_validator_agreement.py --collect-only -q`).
> - **"the shim imported all 84 public names... and then redefined most of them below"** — the test file's own current docstring (`caterva/tests/test_validator_agreement.py:3-5`), which is the authoritative record of this historical incident, says **67** public names were imported and **64** redefined, not 84/"most". These two in-repo sources disagree with each other; neither matches this document.
> - Also worth noting (not a fabrication, a gap): `EXPECTED_HOMES` in that same test file only lists **18** public names, and hasn't been extended to cover domains added after the split (e.g. `simulate_gillespie_ssa*`, `simulate_lotka_volterra`, `simulate_cell_cycle_oscillator`, `simulate_repressilator`) — so the "__module__ assertion" regression guard this document describes as complete does not currently cover those newer domains.

`caterva/caterva_engine.py` has been split into a package per
`REFACTORING_PROPOSAL.md`. This file previously tracked an in-flight,
partially-broken refactor. That work has landed.

## Verified in effect, not merely present

The distinction matters. During the Stage 4 Part 3 audit the shim imported all
84 public names from the package **and then redefined most of them below**.
Python takes the later definition, so the package was imported and immediately
shadowed — and the entire suite passed, because the monolith was still doing
the work. A green suite said nothing about whether the split had taken effect.

Checked directly this time:

```
caterva_engine.py                       292 lines  (was 4283)
def simulate_* / validate_* / build_*       0        (was 64)

simulate_michaelis_menten        -> caterva.continuous.simulations
simulate_pcr                     -> caterva.discrete.pcr
simulate_monte_carlo_pi          -> caterva.discrete.monte_carlo
simulate_molecular_dynamics      -> caterva.discrete.molecular_dynamics
simulate_wright_fisher           -> caterva.discrete.population_genetics.core
simulate_two_locus_wright_fisher -> caterva.discrete.population_genetics.two_locus
validate_md_params               -> caterva.core.validation
```

Every public name resolves to a package module. The shim re-exports and
defines nothing.

## Layout

```
caterva/
  caterva_engine.py            re-export shim; the only public entry point
  core/          data_structures, validation, utils
  continuous/    model_building, simulations        (antimony/SBML/roadrunner)
  discrete/      pcr, monte_carlo, molecular_dynamics
                 population_genetics/{core,analysis,probability,
                                      theoretical,two_locus}
  scenarios/     wf_scenarios
```

## The regression guard

`caterva/tests/test_validator_agreement.py` — 49 tests, in two halves.

**The split stays in effect.** One test parses `caterva_engine.py` and fails
if it defines any `simulate_*`, `validate_*` or `build_*`. Eighteen more
assert each public name's `__module__` ends with its expected package path.
This is constitution amendment (c) applied: *when a refactor claims to
relocate code, assert the relocation directly.*

Verified against the real regression — appending a `simulate_pcr` definition
to the shim produces:

```
AssertionError: caterva_engine.py defines implementations instead of
re-exporting: ['simulate_pcr']. A local definition shadows the package import
and the split stops being in effect, with every test still green.
```

**The flag/reject boundary holds.** Thirty parametrised cases covering every
validator in all three states — accepted, flagged, rejected — because a
validator exercised only on its happy path cannot reveal an inversion.

## The semantic inversion: fixed

While both copies existed, `core/validation.py` converted four
molecular-dynamics plausibility **flags** into hard **rejections**:

```
engine  validate_md_params(108, 0.9, ...)  ->  ok=True,  flagged=True
package validate_md_params(108, 0.9, ...)  ->  ok=False
```

A direct Rule 2 violation, and it would have inverted Stage 3's deliberate
decision that a hot cluster is valid-but-implausible physics a student may
legitimately want to model.

Fixed. Confirmed by a 26-case differential across every validator: **zero
divergences**. The package uses `v.flagged = True` with `flag_reasons` for
temperature, timestep and particle count, matching the engine exactly.

With the shim holding no definitions there is now only one copy of each
constraint, so this class of drift is impossible by construction rather than
merely tested for. The three-state cases remain because they pin the boundary
itself — which is what the drift corrupted.

## Fixes that made the split possible

Applied during the Stage 4 Part 3 audit, when the package could not import at
all:

1. `ModelBuildError` / `SimulationError` added to `core/data_structures.py`.
   Every layer raises them, and a module everything imports must not import
   from a sibling domain.
2. Relative imports across 13 modules. Each had a
   `try: from caterva.X ... except ModuleNotFoundError: from X ...` pair
   that created a circular import through `core/__init__.py` *and masked the
   real error* — every submodule reported a misleading
   `No module named 'core'`.
3. `caterva/pytest.ini`: `pythonpath = . ..`.
4. `caterva/conftest.py`, so the flat `caterva_engine` import resolves
   regardless of pytest's rootdir.
5. `scripts/check_dependencies_declared.py` now treats any directory with an
   `__init__.py` as a local package at any depth.
6. Removed two stray `* 2.py` duplicates.

## Nothing outstanding

The split is complete, in effect, and guarded. No follow-up work is carried
from this document.
