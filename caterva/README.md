# `caterva/` — the simulation engine

The Python that actually integrates the models. Everything else in this
repository exists to get correct parameters *into* here and honest results
*out of* here.

Named `caterva/` since 2026-09-27; before that `Terium/`, and before
2026-08-11 `Tellurium/`. **The upstream
Tellurium project is unrelated to this code and always was** —
`requirements.txt` has always said *"do NOT `pip install tellurium`"*
([ADR 0001](../docs/adr/0001-no-tellurium-umbrella-package.md)), and this code
calls `libroadrunner` and `antimony` directly. The old name implied a
relationship that does not exist.

## Importing it

```python
import caterva
from caterva.core import validation
```

If you see `No module named 'Caterva'`, your install is fine — you have
typed the product name where the package name goes.
`scripts/check_package_spelling.py` fails the build on it.

Do **not** find-and-replace "tellurium" here. The string is still correct in
`requirements.txt`'s warning, in ADR 0001, in
`scripts/check_forbidden_packages.py`, and anywhere in `Business/build-stages/`.
A blind replace already inverted that guard once, so that it forbade this
project's own name and permitted the package it exists to block.

## Layout

| path | what it holds |
|---|---|
| `caterva_engine.py` | the entry point. Read its module docstring first — it is the bar for the rest of the codebase |
| `cli.py` | `python -m caterva.cli` |
| `core/` | `validation.py` (the physical-validity rules), `data_structures.py`, provenance (`model_provenance.py`, `sbml_provenance.py`, `miriam.py`), `import_mode.py` |
| `continuous/` | `model_building.py`, `simulations.py` — ODE domains |
| `discrete/` | `gillespie_ssa.py`, `molecular_dynamics.py`, `monte_carlo.py`, `pcr.py` — stochastic domains |
| `scenarios/` | `wf_scenarios.py` — Wright-Fisher population-genetics scenarios |
| `tests/` | the engine's own suite |

## What "correct" means here

This is the part that makes the directory unusual, and it is not negotiable:

**Every numerical claim is checked against something that is not the solver
checking itself.** One of:

- **an exact closed-form solution** — `tests/test_kinetics_correctness.py`,
  `tests/test_pcr_correctness.py`
- **an independent integrator** — scipy's `solve_ivp`, which shares no code
  with roadrunner. `tests/test_numerical_robustness.py`
- **a physical invariant** — conservation, monotonicity, non-negativity,
  checked across the input space with Hypothesis rather than at hand-picked
  points. `tests/test_properties.py`

"The output looked reasonable when I ran it once" is not one of these. If
you add a domain or a correctness claim, it needs one of the three.

## Running it

```bash
make test-sim                      # this directory only
python -m pytest caterva/tests -q
python -m caterva.cli --help
```

## Things that will bite you

**`validation.py` is shared with the TypeScript side.** `vmax_from_kcat()`
and `beta_gamma_from_r0()` are called from the API server through the runner
bridge, deliberately, so the arithmetic and its bounds have one
implementation rather than two ([ADR 0019](../docs/adr/), ADR 0020). Changing
a bound here changes it there.

**The engine is the contract** ([ADR 0007](../docs/adr/)). Physical validity
is decided here, not by callers. A TypeScript caller that reimplements a
check has created a second source of truth, which is the defect ADR 0027
records the cost of.

**A missing parameter raises rather than defaults.** `MissingParameterError`
is the intended behaviour, not a rough edge to smooth over. See
[`START_HERE.md`](../START_HERE.md) for why.
