# Terrium

Scientific computing for teaching labs. Students ask a question in plain
language; Terrium resolves the real parameters from the literature, runs the
simulation, and shows its work — every number traceable to a citation that has
been independently checked.

Six launch domains: enzyme kinetics, SIR/SEIR epidemiological modeling, PCR
amplification, Monte Carlo simulation, population genetics, and molecular
dynamics setup.

## Quick start

```bash
git clone https://github.com/math12345678/terrium.git
cd terrium
make setup     # creates .venv, installs everything
make check     # verifies the stack genuinely works
make test      # runs all 382 tests
```

`make check` is not a version-string check. It builds a real Michaelis-Menten
model, translates it to SBML, integrates it, and compares the result to the
exact closed-form solution. If it passes, the numerics are trustworthy.

## Requirements

**Python 3.10–3.12.** This is a hard constraint, not a preference. The SBML C
extensions publish prebuilt wheels up to cp312; past that, pip builds from
source and needs `cmake` and `swig` installed.

## Do not `pip install tellurium`

The umbrella `tellurium` package pulls in `python-libcombine` and
`python-libnuml`, which exist to handle COMBINE archives and numerical markup.
Terrium uses neither. On any platform without prebuilt wheels for them, the
install dies at the cmake step.

Install the three packages that actually do the work instead — they are already
in `requirements.txt`:

| Package | Role |
|---|---|
| `libroadrunner` | ODE integration |
| `antimony` | human-readable model definition → SBML |
| `python-libsbml` | SBML validation |

## Layout

```
Terrium/
├── Tellurium/              simulation engine (Tier 2 ODE domains)
│   ├── tellurium_engine.py
│   └── tests/              258 tests
├── Tests/                  literature layer (BRENDA / KEGG / PubMed)
│   ├── brenda_client.py
│   └── ...                 124 tests
├── Docw/                   specs, roadmap, build plan
└── scripts/check_env.py    environment verification
```

## How the tests are built

The suites deliberately avoid checking the solver against itself. Numerical
claims are verified against one of:

- **Exact closed-form solutions** — the implicit MM solution
  `Km·ln(S₀/S) + (S₀−S) = Vmax·t`, the SIR conserved quantity, the final-size
  relation, and the peak condition `S = N/R₀`.
- **An independent integrator** — scipy's `solve_ivp`, which shares no code
  with roadrunner.
- **Physical invariants** — mass and population conservation, monotonicity,
  non-negativity — checked across the input space with Hypothesis.

The suite has been mutation-tested: 13 deliberate scientific errors were
injected into the engine (breaking the rate law, driving SEIR infection off the
exposed compartment instead of the infectious one, disabling validation,
loosening solver tolerances). All 13 were caught.

## Two gotchas worth knowing

**`gamma` is reserved.** Antimony treats `gamma` as the built-in gamma
function, so a parameter named `gamma` is a hard parse error. The recovery rate
is emitted as `gamma_rate`; the Python API still takes `gamma`, and generated
models carry a comment explaining the rename.

**Plausibility bounds are shared.** `KM_PLAUSIBLE_MIN_MM` and
`KM_PLAUSIBLE_MAX_MM` must stay identical between `brenda_client.py` and
`tellurium_engine.py`. They drifted once (1e3 vs 1e4), which meant a Km of
5000 mM was flagged by the literature layer and then silently accepted as
confirmed by the simulation layer. `tests/test_brenda_integration.py` now pins
them together.

## Common commands

```bash
make test-fast   # skip the slow property/robustness suites
make test-sim    # simulation engine only
make test-lit    # literature layer only
make clean       # remove caches
```
