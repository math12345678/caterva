# Engine package split — status as of 2026-08-01

`Tellurium/tellurium_engine.py` (4283 lines) is being split into a package
per `REFACTORING_PROPOSAL.md`. This file records exactly where that stands,
because the state is ambiguous from the tree alone and was mid-flight during
the Stage 4 Part 3 audit.

## Current state: package exists, engine does not use it

    Tellurium/core/{data_structures,validation,utils}.py
    Tellurium/continuous/{model_building,simulations}.py
    Tellurium/discrete/{pcr,monte_carlo,molecular_dynamics}.py
    Tellurium/discrete/population_genetics/{core,analysis,probability,
                                            theoretical,two_locus}.py
    Tellurium/scenarios/wf_scenarios.py

**The package is complete.** All 67 names in `tellurium_engine.__all__`
resolve from these modules — verified by importing every module directly and
matching against `__all__`, with zero missing.

**The engine does not import it.** `tellurium_engine.py` currently holds the
original monolithic implementation. An earlier revision converted it into a
re-export shim; that was rolled back. The package is therefore orphaned: it
exists, it is complete, and nothing loads it.

## Why the intermediate state was dangerous

While the shim was in place, `tellurium_engine.py` imported every name from
the package **and then redefined all 64 of them below**. Python takes the
later definition, so the package was imported and immediately shadowed. Every
test passed — not because the split worked, but because the monolith was
still doing the work. A green suite proved nothing about the refactor.

Worth stating plainly: *"tests pass"* is not evidence that a refactor took
effect. It is evidence that something is producing correct answers.

## Fixes applied during the audit (kept — they are correct either way)

1. **`ModelBuildError` / `SimulationError` added to `core/data_structures.py`.**
   The package could not import without them; they belong there because every
   layer raises them and a module everything imports must not import from a
   sibling domain.
2. **Relative imports throughout the package** (13 files). Each module had a
   `try: from Tellurium.X import ... except ModuleNotFoundError: from X
   import ...` pair. That pattern created a circular import through
   `core/__init__.py` *and* masked the real error, so every submodule failed
   with a misleading `No module named 'core'`. Relative imports resolve
   correctly in both package and flat mode. One deliberate deferred import
   inside a method was left alone — it breaks a genuine cycle.
3. **`Tellurium/pytest.ini`: `pythonpath = . ..`.** The repo root must be on
   `sys.path` or the shim falls back to treating `continuous`/`discrete` as
   top-level packages, whose relative imports then fail with *"attempted
   relative import beyond top-level package."*
4. **`scripts/check_dependencies_declared.py`** now registers every directory
   containing an `__init__.py` as a local package, at any depth. Without it,
   `from continuous.simulations import ...` looked like an undeclared
   third-party dependency. Same blind spot as the package-level import fixed
   in Stage 4 Part 1, one level deeper.
5. Removed two stray `* 2.py` duplicate files under `core/`.

## Semantic divergence found in `core/validation.py` — UNRESOLVED

`core/validation.py` does **not** reproduce the engine's validation
semantics. It converts plausibility flags into hard rejections:

    engine  validate_md_params(108, 0.9, ...)  -> ok=True,  flagged=True
    core/   validate_md_params(108, 0.9, ...)  -> ok=False (appends to errors)

Affected: MD temperature above/below bounds, timestep above bound,
`n_particles` below minimum. All four are `flagged` in the engine and
`errors` in the package copy.

This directly violates Rule 2 — *"Do not collapse this distinction in either
direction"* — and would invert Stage 3's deliberate decision that a hot
cluster is valid-but-implausible physics a student may legitimately want to
model. It is latent only because nothing imports the package.

**This must be fixed before the split is completed.** A byte-exact extraction
would not have this problem; the validators were evidently rewritten rather
than moved.

## To finish the split

1. Fix the four semantic inversions in `core/validation.py` above.
2. Add a test asserting engine and package validators agree, for every
   domain, across ok/flagged/rejected — Rule 4 applies: two copies of one
   constraint need an executable test or they drift.
3. Only then replace the monolith body with the re-export shim.
4. Confirm the split actually took effect — e.g. assert
   `tellurium_engine.simulate_pcr.__module__` is the package module, not
   `tellurium_engine`. Without a check like that, step 3 is unverifiable.
