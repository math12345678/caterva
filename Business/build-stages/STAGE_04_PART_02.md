# Stage 4, Part 2 — Boundary Contract Specification

Stage 4 of 100. This is a mechanical integration stage; no new scientific
domain is introduced.

> **Amendment (2026-08-01):** this document was written as "Part 2 of 2" and
> was accurate for the boundary work it specifies — that work was audited
> independently and holds. The stage does not close here, though. Making all
> eight domains reachable surfaced a problem that was invisible while five of
> them were not: the resolver attaches model citations to hardcoded default
> parameters, so a looked-up value and an invented one are indistinguishable
> in the response. Only `km` in domain `mm` is genuinely resolved. That is
> specified in **Part 3**, which continues this stage rather than reopening
> it. Nothing below is retracted.

## 1. One-sentence definition

Make every public Tellurium simulation reachable through the application
bridge, keep the boundary synchronized by executable tests, and gate the
application layer in CI without duplicating scientific validation rules.

## 2. Governing model

The Python engine remains the source of truth for physical validation and
numerical simulation. The application sends a JSON object `{domain,
parameters}` to `tellurium_runner.py`; the bridge dispatches the domain to the
corresponding exported `simulate_*` function and returns a stable JSON shape:
`ok`, `domain`, `parameters`, `trajectory`, `flagged`, and `flagReason`.
Errors are `{ok: false, error}` and never become successful results.

The boundary itself is verified structurally: the runner's explicit dispatch
inventory must equal the engine's exported `simulate_*` inventory. This is the
boundary equivalent of an independent source of truth; it is not a numerical
claim.

## 3. Continuous or discrete

Not applicable to the integration layer. No simulation algorithm is added.
The existing domain decisions remain authoritative: ODE kinetics and
epidemiology use antimony → SBML → roadrunner; PCR, Monte Carlo,
Wright-Fisher, two-locus Wright-Fisher, and MD use their existing direct
Python implementations, with MD following ADR 0006.

## 4. Public interfaces

### Python bridge domains

The explicit `DISPATCH` table covers:

| Application domain | Engine function |
|---|---|
| `mm` | `simulate_michaelis_menten` |
| `sir` | `simulate_sir` |
| `seir` | `simulate_seir` |
| `pcr` | `simulate_pcr` |
| `monte_carlo_pi` | `simulate_monte_carlo_pi` |
| `wright_fisher` | `simulate_wright_fisher` |
| `two_locus_wright_fisher` | `simulate_two_locus_wright_fisher` |
| `molecular_dynamics` | `simulate_molecular_dynamics` |
| `sbml` | `simulate_sbml` raw-SBML escape hatch |

The first eight are product teaching domains. `sbml` is an internal-capable
raw-SBML entry: it is typed across the API boundary because the engine exports
the primitive, but natural-language resolution does not select it.

Each bridge handler uses conservative defaults documented in the handler and
passes optional seeds through to stochastic domains. Every successful result
contains the same `ok` / `flagged` / `flagReason` contract. Two-locus results
now expose the same flag surface as the other result family; a returned result
is unflagged because invalid inputs are rejected by its validator.

### TypeScript boundary

`SimulationDomain`, the queue result, OpenAPI, generated Zod types, and the
database enum all contain the same ten boundary domains (including internal-capable `sbml`). `findRepositoryRoot`
walks upward for the `Tellurium/` and `Science-Agent-Pipeline/pnpm-workspace.yaml`
markers and is shared by both Python-spawning TypeScript modules.

## 5. Validation contract

Scientific bounds stay in the engine. The API layer performs only structural
required-field checks after resolution, avoiding a second copy of physical
bounds that could drift. Malformed coercions and engine `ModelBuildError` /
simulation errors produce a failed pipeline or `{ok: false}` bridge response.

Two application-runtime ceilings are separate from scientific plausibility:
`n_samples <= 1,000,000` for Monte Carlo and `n_steps <= 10,000` for MD.
These protect the request/response worker from accidental unbounded work; they
are not presented as physical impossibility bounds and do not alter direct
engine calls.

## 6. Verification target

The primary target is the cross-boundary contract test in
`Tellurium/tests/test_boundary_contract.py`. It imports the actual runner
source and asserts:

- every `simulate_*` name in `tellurium_engine.__all__` is dispatched;
- every dispatched engine function exists;
- every dispatch domain has a `run_*` handler and no handler is unreachable;
- the expected nine-domain inventory is explicit;
- each domain produces the stable JSON shape on a small real invocation;
- unknown domains return `ok: false`.

The root-discovery test creates temporary marker repositories and verifies deep
source paths, arbitrary dist depth, root paths, and missing-marker failure.
Existing Python engine/literature correctness suites remain required.

## 7. Relevant decisions and constraints

- ADR 0001: no Tellurium umbrella package.
- ADR 0002: direct Python for discrete domains where appropriate.
- ADR 0005: `numpy.random.default_rng(seed)` convention.
- ADR 0006: direct Python velocity Verlet for MD.
- ADR 0007: explicit dispatch table and contract test at this boundary.
- No new runtime Python dependency. Node 22 and pnpm are CI tooling choices;
  the repository already owns the pnpm lockfile and workspace.

## 8. Shared-constraint check

The executable contract test is the required synchronization mechanism between
engine `__all__` and runner `DISPATCH`. OpenAPI, generated Zod types, queue
types, and database domain enum are regenerated/updated together from the
same domain inventory. A CI TypeScript typecheck and Vitest run prevent those
application representations from drifting unnoticed.

## 9. Out of scope

- Provenance carried with values through the engine (Stage 5).
- Citation verification states, golden provenance tuples, and resolver
  mutation testing (Stage 5).
- New simulation science, Gillespie SSA, or engine algorithm changes.
- Rewriting the queue, resolver, or API architecture.

## 10. Deliverables checklist

- [x] Five previously unreachable scientific domains exposed.
- [x] Raw `simulate_sbml` escape hatch explicitly covered by the contract.
- [x] Stable `ok` / `flagged` / `flagReason` serialization preserved.
- [x] Runtime ceilings selected and documented for Monte Carlo and MD.
- [x] Cross-boundary contract tests include a deleted-dispatch mutation.
- [x] Root discovery is marker-anchored and tested independently of depth.
- [x] Scientific validation decision is explicit: engine authoritative;
      TypeScript structural checks only.
- [x] API schema sources updated; generated clients regenerated.
- [x] Application Vitest is a blocking CI job using the existing pnpm lockfile.
- [ ] Stage 5 provenance contract remains deferred.
