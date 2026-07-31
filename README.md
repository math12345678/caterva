# Terrium

Scientific computing for teaching labs. Students ask a question in plain
language; Terrium resolves the real parameters from the literature, runs the
simulation, and shows its work — every number traceable to a citation that has
been independently checked.

Five launch domains built so far: enzyme kinetics, SIR/SEIR epidemiological
modeling, PCR amplification, Monte Carlo simulation, and population genetics.
Molecular dynamics setup is a candidate for the next domain, not yet built.

## Quick start

```bash
git clone https://github.com/math12345678/terrium.git
cd terrium
make setup     # creates .venv, installs everything
make check     # verifies the stack genuinely works
make test      # runs all 524 tests
```

`make check` is not a version-string check. It builds a real Michaelis-Menten
model, translates it to SBML, integrates it, and compares the result to the
exact closed-form solution. If it passes, the numerics are trustworthy.

### Sandbox (Docker / Dev Containers)

If you'd rather not touch your local Python at all -- reviewing this for
Kickstart, onboarding as the backend hire, or just don't want a `.venv`
lying around -- there's a container that gives you the exact same verified
environment:

```bash
docker build -t terrium-sandbox .
docker run -it --rm terrium-sandbox
# you're now in a shell where check_env.py has already passed
```

This is also wired up as a [Dev Container](https://containers.dev/) — open
the repo in VS Code with the Dev Containers extension installed and it'll
offer to build and attach automatically.

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

## Domains

Six simulation domains, two pipelines:

**Continuous (antimony → SBML → roadrunner):**
- **Michaelis-Menten** — irreversible single-substrate enzyme kinetics.
  Verified against the implicit closed form `Km·ln(S₀/S) + (S₀−S) = Vmax·t`.
- **SIR** — frequency-dependent epidemic model. Verified against conserved
  population, final-size relation, and peak condition `S = N/R₀`.
- **SEIR** — SIR with an explicit latent (exposed) compartment.

**Discrete/stochastic (direct Python, no ODE solver):**
- **PCR amplification** — exact closed-form recurrence `N(c) = n₀ · (1+E)ᶜ`,
  optionally with a logistic plateau. Verified against copy-number conservation
  and plateau approach.
- **Monte Carlo π estimation** — uniform sampling in [-1,1]². Verified against
  the CLT error rate `1/√N`.
- **Wright-Fisher neutral drift** — binomial sampling of 2N allele copies each
  generation. Verified against the exact heterozygosity decay
  `Hₜ = H₀ · (1 − 1/(2N))ᵗ` and Kimura's fixation probability `P(fix) = p₀`.

All discrete/stochastic domains share a common RNG convention
(`numpy.random.default_rng(seed)` with `seed: int | None = None`), formalised
in ADR 0005 (`docs/adr/0005-rng-convention.md`) and enforced automatically by
`scripts/check_rng_convention.py`.

## Layout

```
Terrium/
├── Tellurium/              simulation engine
│   ├── tellurium_engine.py
│   └── tests/              400 tests (399 run, 1 skipped)
├── Tests/                  literature layer (BRENDA / KEGG / PubMed)
│   ├── brenda_client.py
│   └── ...                 124 tests
├── Docw/                   specs, roadmap, build plan
└── scripts/
    ├── check_env.py            environment verification
    ├── verify_domain.sh        automated verification (Steps 1-3)
    ├── check_rng_convention.py ADR 0005 RNG compliance guard
    └── check_dependencies_declared.py  undeclared import guard
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

The suite is mutation-tested: deliberate scientific errors are injected into
the engine (breaking the rate law, driving SEIR infection off the exposed
compartment instead of the infectious one, disabling validation, loosening
solver tolerances, dropping the diploid factor of 2 in Wright-Fisher's
binomial sampling) and confirmed caught, one at a time, as each domain is
built. Every mutation claimed in an implementation report is independently
reproduced by a reviewer before being trusted — see
`Business/build-stages/STAGE_01_PART_04.md` and `STAGE_02_PART_04.md` for
the worked examples, including two cases where the original claimed blast
radius was wrong and got corrected.

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
