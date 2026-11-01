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

## The literature resolvers followed on 2026-11-01

Until 2026-11-01 a section here said the literature layer's epidemiology
and population-genetics resolvers were still in `Tests/`, because removing
them touched the science agent, the parameteriser and several guards. The
science agent stopped importing them on 2026-10-31 (ADR 0180), which left
nothing reachable calling them, so on 2026-11-01 they moved here:

| moved from | now, under this directory |
|---|---|
| `Tests/epidemiology_resolver.py` | `epidemiology_resolver.py` |
| `Tests/popgen_resolver.py` | `popgen_resolver.py` |
| `Tests/test_epidemiology_resolver.py` | `tests/test_epidemiology_resolver.py` |
| `Tests/test_popgen_resolver.py` | `tests/test_popgen_resolver.py` |
| `Tests/test_e2e_architecture_integration.py.disabled` | `tests/test_e2e_architecture_integration.py.disabled` |
| `requirements-popgen.txt` | `requirements-popgen.txt` |

Why each one: the two resolvers answered R0, infectious period and
germline mutation rate, which only the SIR, SEIR and Wright-Fisher domains
asked for. `requirements-popgen.txt` existed only to install `stdpopsim`
(GPL-3.0-or-later, opt-in since ADR 0061) for `popgen_resolver.py`, so it
goes with it; `make setup` has never installed that file (stdpopsim itself
was in `requirements.txt` only from 2026-08-04 to 2026-08-16). The disabled
end-to-end test imported `epidemiology_resolver` at module level and
called `beta_gamma_from_r0`, which is already in this directory's
`validation.py`, so it could not have been re-enabled in `Tests/`; it had
not run since it was disabled.

The guards and set-up checks that named these files changed in the same
step: `verify_citations_live.py` no longer reads the resolvers for DOIs,
`check_no_silent_skips.py` no longer expects the stdpopsim skip,
`check_forbidden_packages.py` and `check_pins_resolve.py` no longer list
`requirements-popgen.txt`, and `check_env.py` and `doctor.py` no longer
tell a contributor to install stdpopsim for a resolver nothing uses.

v0.4.0 is the last release whose shell runs those domains. The resolvers
outlived them: the API server's science agent runner still imported and
called both through v0.6.0, until 2026-10-31 (ADR 0180), so v0.6.0 is the
last release that ships them. Check out the `v0.6.0` tag to use the
resolvers, or `v0.4.0` for the domains, as described above.

## Still in the tree

The API server's epidemiology bridge (`applyBetaGammaFromR0Resolution`,
`resolveEpidemiologyParameters`, `diseases.ts`) and the
`wright_fisher: ["mutation_rate"]` entry in `RESOLVABLE_FIELDS` were removed
on 2026-10-31 (ADR 0180).

The API's database enum and OpenAPI spec still list the archived domain
names, because stored rows may carry them. A request for one is refused
with a message naming this archive and v0.4.0.
