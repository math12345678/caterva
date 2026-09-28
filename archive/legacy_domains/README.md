# Archived domains

On 2026-09-27 Caterva narrowed to enzyme kinetics, stochastic chemical
kinetics, structures and molecular dynamics. The domains below were moved
here, with their tests, rather than deleted.

| domain | code here | last release that runs it |
|---|---|---|
| SIR / SEIR epidemiology | `simulations.py`, `model_building.py`, `networks.py` | v0.4.0 |
| Lotka-Volterra, Tyson cell cycle, repressilator | same | v0.4.0 |
| PCR amplification | `pcr.py` | v0.4.0 |
| Monte Carlo π | `monte_carlo.py` | v0.4.0 |
| Population genetics (Wright-Fisher, two-locus) | `population_genetics/`, `cli_popgen.py` | v0.4.0 |
| Lennard-Jones cluster MD | `molecular_dynamics.py` | v0.4.0 |
| Scenario presets | `scenarios/` | v0.4.0 |

To run any of them, use v0.4.0: check out the `v0.4.0` tag, or install the
wheel attached to the
[v0.4.0 release](https://github.com/math12345678/caterva/releases/tag/v0.4.0).

## What this directory is not

- **Not imported.** Nothing in `caterva/` or the API server imports from
  here, and the files are kept as they were when they left, so their
  import paths point at modules that no longer hold them.
- **Not tested.** `tests/`, `api-server-tests/` and `root-cli-tests/` are
  the suites that covered these domains, kept next to the code they
  covered. They are not collected by `make test` or CI.
- **Not the Lennard-Jones code's successor.** Molecular dynamics continues
  as `caterva md`, which sets up real GROMACS runs of enzymes; the toy LJ
  integrator was a different thing with the same name.

## Still in the tree

The literature layer's epidemiology and population-genetics resolvers
(`Tests/epidemiology_resolver.py`, `Tests/popgen_resolver.py`) are still in
`Tests/`. No simulation path reaches them now. Removing them touches the
science agent, the parameteriser and several guards, so it is a separate
change.

The API's database enum and OpenAPI spec still list the archived domain
names, because stored rows may carry them. A request for one is refused
with a message naming this archive and v0.4.0.
