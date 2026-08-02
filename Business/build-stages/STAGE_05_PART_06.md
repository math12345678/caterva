# Stage 5 Part 6: close

Stage: 5 (the provenance contract) · Part: 6 (close) · 2026-08-01

## 1. What Stage 5 was

"Stage 4 made the API honest about what it knows. Stage 5 makes it know
more." The provenance contract's five open questions are now all answered,
implemented, and guarded — no item carried past the stage.

## 2. Deliverables per part

| Part | Question | Deliverable | Guarded by |
|------|----------|-------------|------------|
| 1 | resolved-citation strictness (carried from Stage 4) | locator rule: URL or `(ref <id> ≠ n/a)`; `formatResolvedCitation` refuses to fabricate; unlocatable → `default` + note | `isLocatableCitation` in `validateParameterProvenance`; Target F; Mutation 6 |
| 2 | Rule 1 (golden set); mutation test | 3 hand-verified tuples (LDH 10.73/740253, AChE 0.09/649716, LDH cross-species 0.0026/740001) asserted end to end; API mirror (Target G) | `Tests/test_golden_set.py`; Target G sensitivity test; live demos (Python min→max; TS citation drop) |
| 3 | verified/flagged/rejected contract | `citationStatus` on resolved entries; `crossSpecies` crosses the runner boundary first-class | validation rules; Target H; Mutation 7; live BRENDA check |
| 4 | provenance travels with the parameter | single-record transport end to end; `parseAgentOutput` extracted; boundary pinned from both sides | `Tests/test_runner_contract.py` (4); `scienceAgent.test.ts` (7) |
| 5 | widen vs explicit narrowness | `RESOLVABLE_FIELDS` = `{mm: ["km"]}`; defaults without a lookup state it on the response | Target I (+4) |

## 3. Standing additions to the contract (ADR 0008)

- resolved citations must be locatable (Part 1);
- the golden set is Rule 1 for provenance, asserted end to end (Part 2);
- every resolved entry carries `citationStatus`; `rejected` is not a
  resolved state (Part 3);
- provenance travels with the parameter as one record; the boundary is
  contract-tested; the simulation engine stays flag-only per ADR 0007
  (Part 4);
- the narrowness is deliberate: `RESOLVABLE_FIELDS` is the single source
  of truth and the response states it per parameter (Part 5).

## 4. Verification totals

- pytest: 906 passed, 1 skipped (was 896 at Stage 4 close; +6 golden,
  +4 runner contract, −0 lost).
- vitest: 141 passed, 7 files (was 124 at Stage 4 close; +7 boundary
  contract, +4 Target I, +2 Target G/H units, +2 Target H behavior,
  +1 Mutation 6, +1 Part-1 unit — net +17).
- typecheck clean; `verify_build.py --quick` all green.
- Live checks this stage: real BRENDA confirms golden G1 (10.73 mM,
  Homo sapiens) and the cross-species flag (Mus musculus →
  `crossSpecies: true`).

## 5. Deliberate decisions recorded in writing (not inherited)

1. `(ref n/a)` is never emitted; unlocatable citations degrade honestly.
2. `rejected` is not a fourth status — it is the absence of resolution.
3. The engine boundary remains flag-only (ADR 0007 stands).
4. Widening is refused for now, with a documented extension path.

## 6. Next stage: domains resume — Gillespie SSA first

Stage 4's close set the queue: Gillespie SSA is first when domains resume
(Stage 6). It will need the full provenance treatment this stage built:
a golden tuple for its parameters, closed forms, a flag-only engine
boundary, and Target G/I-style assertions. The provenance machinery
(`RESOLVABLE_FIELDS`, validation, golden set, boundary contract) is ready
to receive it.
