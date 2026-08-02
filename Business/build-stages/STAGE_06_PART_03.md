# Stage 6 Part 3: API E2E + CLI for the SSA domain

Stage: 6 (domains resume) · Part: 3 (surface completion) · 2026-08-02

## 1. What this part delivers

The engine and runner were wired in Part 1; the golden + provenance
treatment in Part 2. Part 3 completes the domain's user-facing surface
so every way a user can reach the engine is exercised and pinned.

## 2. Deliverables

| File | Change |
|------|--------|
| `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/routes.test.ts` | E2E: POST /api/simulate "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9" → 202 → poll → completed with domain gillespie_ssa, trajectory rows, initial point a=200/b=0, final row snapped exactly to time=5, and **seeded reproducibility**: a second identical query reproduces a bit-identical trajectory through the whole queue→runner→JSON chain |
| `Tellurium/cli.py` | new `ssa` subcommand: `--a0 --k --end --seed --out`, prints a sampled event table plus event count, final A, and the closed-form expectation `a0*(1-e^(-k*end))`; ModelBuildError → exit 1 |
| `Tellurium/tests/test_gillespie_ssa_golden.py` | +2 CLI smoke tests: happy path (seeded run prints `events = 190`, `final A = 10` — the same pinned seed) and invalid-params exit 1 |
| `docs/API.md` | CLI section documents `ssa` |

## 3. Verification totals

- pytest: **936 passed, 1 skipped** (934 → 936; +2 CLI).
- vitest: **151 passed, 8 files** (150 → 151; +1 E2E).
- `tsc --noEmit` clean; `verify_build.py --quick` ALL CHECKS PASSED.

## 4. Deliberate decisions

1. The E2E uses a fixed seed so the trajectory is reproducible through
   the queue — the API-level equivalent of the Part 2 golden, and the
   strongest claim the stage can make: same query, same seed, same
   trajectory, no engine/bridge drift.
2. The CLI prints the closed-form expectation beside the observed
   event count — a teaching-facing number, matching the `ld` command's
   theory-vs-observation style rather than inventing a new format.
3. No changes to the queue/runner internals were needed: the domain was
   already fully reachable; this part only proves it under load paths.

## 5. Where Stage 6 stands

- Part 1: domain, guards repaired, boundary contract, ceilings.
- Part 2: golden trajectory (hand-verified + mutation traps), runner
  boundary golden, OpenAPI codegen, engine-contract guard, landing
  ledger, API docs.
- Part 3: API E2E with seeded reproducibility, CLI, CLI tests.

Remaining for Stage 6 (next parts): the close report, or a further
improvement (e.g. resolving `a0`/`k` from free text more aggressively,
a golden for a second SSA regime, or documenting the domain in the
landing walkthrough).
