# Engine package split — COMPLETE

`Terium/terium_engine.py` has been split into a package per
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
terium_engine.py                       292 lines  (was 4283)
def simulate_* / validate_* / build_*       0        (was 64)

simulate_michaelis_menten        -> Terium.continuous.simulations
simulate_pcr                     -> Terium.discrete.pcr
simulate_monte_carlo_pi          -> Terium.discrete.monte_carlo
simulate_molecular_dynamics      -> Terium.discrete.molecular_dynamics
simulate_wright_fisher           -> Terium.discrete.population_genetics.core
simulate_two_locus_wright_fisher -> Terium.discrete.population_genetics.two_locus
validate_md_params               -> Terium.core.validation
```

Every public name resolves to a package module. The shim re-exports and
defines nothing.

## Layout

```
Terium/
  terium_engine.py            re-export shim; the only public entry point
  core/          data_structures, validation, utils
  continuous/    model_building, simulations        (antimony/SBML/roadrunner)
  discrete/      pcr, monte_carlo, molecular_dynamics
                 population_genetics/{core,analysis,probability,
                                      theoretical,two_locus}
  scenarios/     wf_scenarios
```

## The regression guard

`Terium/tests/test_validator_agreement.py` — 49 tests, in two halves.

**The split stays in effect.** One test parses `terium_engine.py` and fails
if it defines any `simulate_*`, `validate_*` or `build_*`. Eighteen more
assert each public name's `__module__` ends with its expected package path.
This is constitution amendment (c) applied: *when a refactor claims to
relocate code, assert the relocation directly.*

Verified against the real regression — appending a `simulate_pcr` definition
to the shim produces:

```
AssertionError: terium_engine.py defines implementations instead of
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
   `try: from Terium.X ... except ModuleNotFoundError: from X ...` pair
   that created a circular import through `core/__init__.py` *and masked the
   real error* — every submodule reported a misleading
   `No module named 'core'`.
3. `Terium/pytest.ini`: `pythonpath = . ..`.
4. `Terium/conftest.py`, so the flat `terium_engine` import resolves
   regardless of pytest's rootdir.
5. `scripts/check_dependencies_declared.py` now treats any directory with an
   `__init__.py` as a local package at any depth.
6. Removed two stray `* 2.py` duplicates.

## Nothing outstanding

The split is complete, in effect, and guarded. No follow-up work is carried
from this document.
