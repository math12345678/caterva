# Stage 7 Part 1: the bimolecular Gillespie SSA domain

## 1. What this part delivers

The second stochastic domain: the bimolecular association
A + B → C, simulated with the same exact Direct Method as the
first-order decay of Stage 6 (ADR 0009 amendment), but with the
second-order propensity `k·a·b`. The teaching point is the
conservation structure of an association reaction and its ODE closed
form, which the exact stochastic mean must reproduce.

Deliverables:

- `simulate_gillespie_ssa_bimolecular(a0, b0, k, end, seed=None)` in
  `Tellurium/discrete/gillespie_ssa.py` — columns `["time","a","b","c"]`,
  one uniform per event, `τ = −ln(u)/(k·a·b)`, loop
  `while t < end and a > 0 and b > 0 and k > 0`, final row snapped to
  `end`, ADR 0005 RNG (`seed: int | None = None` +
  `np.random.default_rng(seed)`).
- `validate_ssa_bimolecular_params` in `Tellurium/core/validation.py`
  with flags for small populations (< 30) and dense-event rates
  (`k > SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE = 0.1`).
- Full engine, runner, API, LLM resolver, zod schema, DB enum, OpenAPI
  + orval codegen, provenance, and CLI-facing surfaces wired (ten
  domains total).
- Golden trajectory pinned at three levels (engine, runner boundary,
  HTTP E2E through the queue).

## 2. Files

- `Tellurium/discrete/gillespie_ssa.py` — bimolecular simulator (both
  SSA domains in one module).
- `Tellurium/core/validation.py` — `validate_ssa_bimolecular_params`.
- `Tellurium/core/data_structures.py` — `SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE`.
- `Tellurium/tellurium_engine.py` — wiring (`__all__` + imports, both
  try/flat branches).
- `Tellurium/tests/test_gillespie_ssa_bimolecular_correctness.py` (14)
  — closed form, conservation, determinism, edge cases, output contract.
- `Tellurium/tests/test_gillespie_ssa_bimolecular_golden.py` (11) —
  pinned trajectory + mutation traps.
- `Tellurium/tests/test_boundary_contract.py` — expected sets,
  `SMALL_PARAMS`, summed-population ceiling row.
- `Science-Agent-Pipeline/artifacts/api-server/src/lib/tellurium_runner.py`
  — `run_gillespie_ssa_bimolecular`, `DISPATCH`, `_RUNNERS`; ceiling
  on `a0 + b0`.
- `.../src/lib/telluriumRunner.ts`, `queryResolver.ts` (defaults,
  keywords, PARAMETER_PATTERN + b0, priority ordering),
  `llmResolver.ts`, `schemas.ts`.
- `.../src/__tests__/gillespieBimolecularGolden.test.ts` (4),
  `schemas.test.ts`, `provenance.test.ts`, `routes.test.ts` (resolve +
  E2E: 2).
- `Science-Agent-Pipeline/lib/db/src/schema/simulations.ts` — enum,
  package rebuilt.
- `Science-Agent-Pipeline/lib/api-spec/openapi.yaml` + orval codegen
  (api-client-react, api-zod regenerated).
- `scripts/check_plausibility_constants.py` — `SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE: 0.1`.
- `docs/adr/0009-gillespie-ssa.md` (amendment), `docs/API.md`,
  `README.md` (ten domains, 830 tests), `landing/src/lib/pipeline.ts`
  (ledger row), this document.

## 3. The golden trajectory (how it was pinned)

Seed 12345, a0=60, b0=40, k=0.01, end=5.0:

- 38 rows; first event `t = 0.06172192003509486` — hand-verified:
  `u1 = np.random.default_rng(12345).uniform()` =
  0.22733602246716966, `τ1 = −ln(u1)/(k·a0·b0)`; the engine consumes
  exactly one uniform per event in stream order (second event
  `τ2 = −ln(u2)/(k·59·39)` verified the same way).
- Final row `[5.0, 24.0, 4.0, 36.0]`: `a+c = 60`, `b+c = 40` on every
  row; the event count `c` never exceeds `min(a0,b0) = 40`.
- Mutation traps: constant propensity, first-order-only propensity
  (`k·a`), and an unequal-decrement mutation (2 A + 1 B per event) —
  all detected by the pinned trajectory and conservation.

## 4. Verification

- pytest: 829 passed, 1 skipped (was 936 → 949 total across repo:
  830 collected in Tellurium/tests).
- vitest: 161 passed (was 151) — includes the bimolecular golden
  through the runner boundary and the HTTP E2E through the queue,
  which reproduces the seeded trajectory bit-identically.
- `pnpm run typecheck` clean across all artifacts; orval + tsc codegen
  clean.
- `scripts/check_plausibility_constants.py` and
  `scripts/check_rng_convention.py` both PASSED with the new constant
  and the new simulator.
- `python3 scripts/verify_build.py --quick` — ALL CHECKS PASSED.

## 5. Deliberate decisions

- **One constant for the bimolecular rate ceiling**
  (`SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE = 0.1`): the first-order ceiling
  (10.0) makes no sense for a second-order propensity (units
  molecules⁻¹·time⁻¹), so the guard now tracks both.
- **Ceiling on `a0 + b0`, not `max(a0,b0)`**: event count is bounded by
  `min(a0,b0)`, but the summed population bounds the worst-case state
  work; both are simple and conservative.
- **Keyword priority for `gillespie_ssa_bimolecular`**: the
  deterministic resolver is first-match, so "reaction" alone would fall
  into first-order decay; the bimolecular domain is listed first and
  its keywords (bimolecular, association, binding, second order, …)
  capture the query before the generic SSA entry is reached.
- **ODE closed form as test ground truth** (not Monte Carlo of the SSA
  itself): `a(t) = (a₀−b₀)/(1 − (b₀/a₀)e^(−k(a₀−b₀)t))` for unequal
  counts, `a(t) = a₀/(1 + k·a₀·t)` for equal counts — the same
  deterministic reference students learn, so the stochastic mean is
  checked against something independently derivable.
