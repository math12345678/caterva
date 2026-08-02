# Stage 6 Part 1: the Gillespie SSA domain

Stage: 6 (domains resume) · Part: 1 (Gillespie SSA) · 2026-08-02

## 1. What this part delivers

The first domain from the Stage 4/5 queue: stochastic chemical kinetics
via Gillespie's exact SSA. Model (ADR 0009): a single first-order decay
reaction A → B, propensity `k·a`, exact Direct Method, with the closed
form `E[a(t)] = a₀·e^(−kt)` as the testable ground truth. Deliberately
narrow — one reaction, three parameters (`a0`, `k`, `end`) plus the
ADR 0005 `seed`.

## 2. Files

| File | Change |
|------|--------|
| `Tellurium/discrete/gillespie_ssa.py` | new engine module: Direct Method, k=0 and complete-decay handling, endpoint snap, flag passthrough, ADR 0005 RNG |
| `Tellurium/core/validation.py` | `validate_ssa_params`: bool/type/range checks; flags a0<30, k>10 (soft, not rejected) |
| `Tellurium/core/data_structures.py` | `SSA_PLAUSIBLE_MIN_POPULATION = 30`, `SSA_PLAUSIBLE_MAX_RATE = 10.0` |
| `Tellurium/tellurium_engine.py` | imports (both try/flat blocks), `__all__` + `simulate_gillespie_ssa`, `validate_ssa_params`, SSA constants re-exported |
| `Tellurium/tests/test_gillespie_ssa_correctness.py` | 17 tests: closed-form mean (3σ on the exact Binomial), conservation every row, seed determinism, k=0, endpoint snap, flags, output contract, validation rejects |
| `Science-Agent-Pipeline/artifacts/api-server/src/lib/tellurium_runner.py` | `run_gillespie_ssa`, `DISPATCH`/`_RUNNERS` entries, `MAX_API_SSA_POPULATION = 1_000_000` ceiling, docstring domain list |
| `Science-Agent-Pipeline/artifacts/api-server/src/lib/telluriumRunner.ts` | `SimulationDomain` + `"gillespie_ssa"` |
| `Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts` | `DOMAIN_DEFAULTS` entry (a0=1000, k=0.5, end=10; keywords; Gillespie 1977 citation); `PARAMETER_PATTERN` + `a0`,`k` |
| `Science-Agent-Pipeline/artifacts/api-server/src/lib/llmResolver.ts` | domain enum + description + allowlist |
| `Science-Agent-Pipeline/artifacts/api-server/src/lib/schemas.ts` | `gillespie_ssa` parameter schema |
| `Science-Agent-Pipeline/lib/db/src/schema/simulations.ts` | domain enum + `gillespie_ssa` (db package rebuilt) |
| `Tellurium/tests/test_boundary_contract.py` | expected-domain sets, `SMALL_PARAMS`, ceiling tests for SSA |
| `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/` | schemas valid/invalid pairs; provenance `DOMAIN_QUERIES` 9th (Target A); routes resolve test |
| `docs/adr/0009-gillespie-ssa.md` | new ADR: model, algorithm, narrow scope, thresholds, ceiling |

## 3. Two guard repairs found while wiring this domain

1. **`scripts/check_plausibility_constants.py` was enforcing stale
   values.** 14 of its 19 `EXPECTED_CONSTANTS` disagreed with the
   engine's actual definitions (e.g. it expected `KM_PLAUSIBLE_MIN_MM
   = 0.001`, the engine defines `1e-7`; `R0_IMPLAUSIBLE_ABOVE = 100.0`
   vs `20.0`). Worse, it only value-checked constants defined in 2+
   files, so single-file constants could drift with no signal. Fixed:
   `EXPECTED_CONSTANTS` aligned to the engine (engine = source of
   truth) and every expected constant is now verified regardless of
   file count. The guard failed loudly on the missing SSA constants
   mid-work, then went green when they landed.
2. **`scripts/check_rng_convention.py` was vacuous.** It scanned
   `tellurium_engine.py`, which re-exports but does not define any
   `simulate_*` function — so zero functions were ever checked. Now it
   walks every module under `Tellurium/` and checks all five stochastic
   definitions (Monte Carlo, Wright-Fisher, two-locus, MD, SSA) for the
   ADR 0005 signature + `default_rng` call. All pass; the SSA domain
   complies by construction.

## 4. Verification

- pytest: **923 passed, 1 skipped** (906 → 923; +17 SSA engine tests).
- vitest: **146 passed, 7 files** (141 → 146; +2 schemas, +2 Target A,
  +1 routes resolve).
- `tsc --noEmit` clean (after rebuilding `@workspace/db`, whose stale
  dist lacked the new enum).
- `verify_build.py --quick`: ALL CHECKS PASSED (citation format, engine
  contract, dependencies, plausibility constants, RNG convention).
- Boundary contract (ADR 0007) green: DISPATCH ↔ `__all__` ↔ handlers
  in lockstep; runtime ceiling rejects `a0 > 1_000_000` before
  simulation.

## 5. Deliberate decisions (ADR 0009)

- Single first-order decay reaction, exact Direct Method; conservation
  `a+b=a₀` on every row; final row snapped to `end`.
- Thresholds are flags, not rejections (student may want the noisy
  regime); the a0 ceiling is a hard API runtime limit.
- Narrow scope stands: no bimolecular/reversible/multi-species networks
  this stage — extension would be a new ADR.
