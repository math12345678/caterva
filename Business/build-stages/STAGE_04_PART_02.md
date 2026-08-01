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

## 2b. Completion audit (2026-08-01) — one real defect in the runtime ceilings

The boundary work in this document was audited by reading and measuring, not
by re-running the tests that already pass. Everything specified below holds,
with one exception found in the runtime ceilings.

### 2b.1 The MD runtime ceiling did not bound MD requests

§5 states two ceilings: `n_samples <= 1,000,000` for Monte Carlo and
`n_steps <= 10,000` for MD, described as protecting "the request/response
worker from accidental unbounded work."

`n_steps` does not bound an MD request. MD cost is **O(N² × steps)** —
pairwise forces with no neighbour lists, which ADR 0006 deliberately put out
of scope — and only the linear term was capped. Measured at 200 steps, i.e.
2% of the ceiling:

| `n_particles` | wall clock |
|---|---|
| 108 | 0.15 s |
| 256 | 0.95 s |
| 500 | 3.64 s |
| 800 | 9.94 s |

Meanwhile the engine **accepts** large particle counts. `validate_md_params`
returns `ok=True` for `n_particles=5000`, merely flagged, and the engine then
rounds it *up* to the next fcc count, 5324. A request of
`{n_particles: 5000, n_steps: 10000}` therefore passed every stated ceiling.

Its actual behaviour, confirmed by disabling the new guard and running it: the
worker process was **OOM-killed**, not merely slow. The engine's vectorised
force calculation allocates an N×N×3 array — roughly 680 MB per array at 5324
particles. So the failure mode was worse than a hung request; it was a dead
worker.

### 2b.2 Fix: budget the term that actually drives cost

`MAX_API_MD_PAIR_STEPS = 120_000_000`, applied to
`fcc_round_up(n_particles)² × n_steps`.

Calibrated from measurement rather than chosen: throughput is roughly
1.6 × 10⁷ pair-steps per second, so the budget is about a 7.5-second ceiling.
It was picked to keep the documented reference case — 108 particles ×
10,000 steps, 1.17 × 10⁸ pair-steps — inside the budget, which a
miscalibrated ceiling would have rejected.

The round-up matters and is not cosmetic: the engine simulates
`4k³ ≥ n_particles`, always upward, so budgeting on the *requested* count
would systematically underestimate cost. `_fcc_particle_count()` mirrors the
engine's rule and has its own test asserting `k` is the smallest sufficient
value.

Rejection is now explicit and actionable:

```
n_particles=5000 (simulated as 5324 after fcc round-up) with n_steps=100
is 2.83e+09 pair-steps, exceeding the API runtime ceiling
(MAX_API_MD_PAIR_STEPS) 1.2e+08. MD cost scales as N^2 * steps; reduce either.
```

### 2b.3 The other domains were checked, not assumed

Wright-Fisher looked like it had the same shape — cost across generations,
replicates *and* population size, with only the first two capped. Measured:
flat in `N` (0.09 s at N=100, N=1000 and N=10000), because the engine draws
`rng.binomial(2N, p)` in one numpy call rather than summing Bernoulli trials.
At **both** ceilings simultaneously — 10,000 generations × 1,000 replicates —
the worst case is 1.16 s. Genuinely bounded; no change needed.

Monte Carlo at its ceiling: 0.31 s.

### 2b.4 Two documentation defects in the same file

The measurement comment cited **"STAGE_04_PART_01 §6.3"**. That section does
not exist — Part 1 §6 is "What Part 2 must resolve" and contains no timings —
and its quoted figure of *"MD 10k steps ~11s"* was never measured. Real value
on the pinned configuration: 7.32 s. Citation removed, figures replaced with
measured ones and dated.

This is a small instance of the pattern Stage 3 recorded as a standing
amendment: a plausible-sounding number attached to a source that does not
contain it. Cheap to check, and it was wrong.

Also fixed: the module docstring had `< request.json` and
`Expected input JSON shape:` run together on one line.

### 2b.5 Regression coverage

Four tests added to `test_boundary_contract.py` (18 → 26):

- large particle count rejected below the step ceiling,
- large particle count rejected at the step ceiling,
- the documented 108 × 10k reference case stays inside the budget — a guard
  against a future ceiling being tightened into uselessness,
- `_fcc_particle_count` matches the engine's round-up, including that `k` is
  the smallest sufficient value.

Verified against the mutation: disabling the budget kills the test process.
Re-enabling it, 26 pass.

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
