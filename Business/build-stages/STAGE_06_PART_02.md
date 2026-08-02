# Stage 6 Part 2: the SSA golden trajectory + provenance treatment

Stage: 6 (domains resume) · Part: 2 (golden + narrowness for Gillespie SSA) · 2026-08-02

## 1. Why a golden for a stochastic domain

Stage 5's golden set pinned hand-verified *literature* values
(km/ref-id/URL tuples). SSA has no literature lookup — its ground truth
is the algorithm itself plus the closed form. So the golden is a
**fixed-seed trajectory**, pinned in full, whose random-number
consumption is hand-verified against numpy's own stream:

    seed 12345, a0=100, k=0.5, end=3.0
    u1 = default_rng(12345).uniform(0,1)          → 0.22733602246716966
    tau1 = −ln(u1)/(k·a0)                         → 0.029626521616845532
    engine first event time                       → 0.029626521616845532 ✓
    final row [3.0, 24.0, 76.0]                   (a+b = a0 every row)
    78 rows total

## 2. Deliverables

| File | Content |
|------|---------|
| `Tellurium/tests/test_gillespie_ssa_golden.py` | 11 tests: bit-identical rerun (ADR 0005), pinned row count/initial/two event times/final, conservation every row, hand-verified tau1 and cumulative tau1+tau2 from numpy's stream, plus 3 mutation traps (constant propensity, off-by-one propensity, double decrement) all detected by the pinned table |
| `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/gillespieGolden.test.ts` | same golden through the REAL runner boundary (`runTellurium` spawns Python): 78 rows, exact first/second event times, exact final point, params echoed; plus Target I-style narrowness: gillespie resolution has no `resolved` origin, no citations, and no "No literature lookup" notes |
| `Science-Agent-Pipeline/lib/api-spec/openapi.yaml` + regenerated clients | domain enum + `gillespie_ssa` (api-client-react, api-zod, `SimulationResponseDomain`) |
| `scripts/check_engine_contract.py` | `expected_discrete` + `gillespie_ssa.py` |
| `landing/src/lib/pipeline.ts` | EVIDENCE LEDGER row: `E[a(t)] = a₀·e^(−kt), a+b ≡ a₀` — exact SSA mean vs closed form (50 seeds), ref Gillespie 1977 |
| `docs/API.md` | domain overview section + deep section (signature, model, params, verification targets A–D, flags, hard rejections, API ceiling); `validate_ssa_params` added to the validation list |

## 3. Verification totals

- pytest: **934 passed, 1 skipped** (923 → 934; +11 golden).
- vitest: **150 passed, 8 files** (146 → 150; +4 boundary golden +
  narrowness).
- Typecheck clean (`tsc --noEmit` api-server; libs rebuilt by orval
  codegen which runs `tsc --build`).

## 4. Deliberate decisions

1. The golden is a seeded trajectory rather than a literature value —
   the stochastic equivalent of Rule 1 for this domain; the mutation
   traps prove the pinned table detects sampling bugs.
2. The runner boundary reproduces the exact same golden (bit-identical
   float64s survive the JSON bridge), so engine↔bridge drift is caught
   from both sides.
3. Double-decrement mutation is detected via event count/final state,
   not conservation — `a−=2, b+=2` trivially conserves the sum; the
   tripwire must be the trajectory, not the invariant.
4. Narrowness stands: gillespie_ssa is not in `RESOLVABLE_FIELDS`; the
   API states this by emitting no notes at all (vs mm's explicit notes).
