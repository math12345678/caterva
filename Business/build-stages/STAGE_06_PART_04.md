# Stage 6: close

Stage: 6 (domains resume) · Part: 4 (close) · 2026-08-02

## 1. What Stage 6 was

Stage 4's close queued one domain: **Gillespie SSA** — first domain
since the provenance contract made the API honest (Stage 5). Stage 6
delivered it end to end with the full provenance treatment the close
promised: closed forms, a golden, a flag-only engine boundary, and
Target G/I-style assertions — plus two guard repairs found along the
way.

## 2. Deliverables per part

| Part | Deliverable | Guarded by |
|------|-------------|------------|
| 1 | engine (`discrete/gillespie_ssa.py`, `validate_ssa_params`, constants), runner dispatch + `MAX_API_SSA_POPULATION` ceiling, TS domain/defaults/LLM/schemas/DB enum, boundary contract, ADR 0009 | `test_gillespie_ssa_correctness.py` (17); `test_boundary_contract.py`; `check_rng_convention.py`; `check_plausibility_constants.py` |
| 2 | SSA golden: hand-verified seeded trajectory (numpy-stream tau1, 78 rows, final [3.0, 24.0, 76.0]) pinned in Python + through the real runner boundary; 3 mutation traps; OpenAPI codegen; engine-contract guard; landing ledger; API docs | `test_gillespie_ssa_golden.py` (13); `gillespieGolden.test.ts` (4) |
| 3 | API E2E: seeded reproducibility through queue→runner→JSON (same query+seed → bit-identical trajectory); `ssa` CLI subcommand with closed-form comparison | `routes.test.ts` E2E; CLI smoke tests |

## 3. Two guard repairs (real bugs, found by wiring the domain)

1. **`check_plausibility_constants.py` was enforcing stale values** —
   14 of 19 expected constants disagreed with the engine (e.g. expected
   `KM_PLAUSIBLE_MIN_MM = 0.001`, engine defines `1e-7`), and it only
   value-checked constants defined in 2+ files, so single-file
   constants could drift silently. Fixed: expected table aligned to
   the engine (engine = source of truth), every constant verified.
2. **`check_rng_convention.py` was vacuous** — it scanned the engine
   shim, which defines no `simulate_*` functions, so it checked zero
   functions. Fixed: walks every Tellurium submodule; now verifies all
   five stochastic domains comply with ADR 0005.

## 4. Standing additions to the contract

- **ADR 0009** (`docs/adr/0009-gillespie-ssa.md`): SSA model (single
  A → B first-order decay, exact Direct Method), narrow scope,
  plausibility flags (a0<30, k>10), API ceiling
  (`MAX_API_SSA_POPULATION = 1_000_000`), RNG = ADR 0005.
- The seeded golden trajectory is this domain's Rule 1: pinned in
  Python, re-pinned through the runner boundary, and reproduced through
  the live API (Part 3 E2E) — the stochastic equivalent of the Stage 5
  literature golden set.
- Narrowness stands: `gillespie_ssa` is not in `RESOLVABLE_FIELDS`;
  the API emits no notes at all for it (vs mm's explicit notes).

## 5. Verification totals

- pytest: **936 passed, 1 skipped** (906 at Stage 5 close; +17
  correctness, +13 golden incl. CLI, +0 lost).
- vitest: **151 passed, 8 files** (141 at Stage 5 close; +2 schemas,
  +2 Target A, +1 routes resolve, +4 boundary golden + narrowness,
  +1 API E2E).
- `tsc --noEmit` clean; `verify_build.py --quick` all green; CLI
  verified (`ssa` happy path + invalid-params exit 1).
- Note: `verify_domain.sh` run in a bare Python 3.12 venv fails only on
  missing `roadrunner` (the repo's real environment provides it via
  conda-forge); every mechanical step passes under the repo
  environment. The interpreter-policy gate (3.10–3.12) is unchanged.

## 6. Deliberate decisions recorded in writing (not inherited)

1. Golden = seeded trajectory (not a literature value) — the exact
   algorithm IS the ground truth here; the pinned table catches
   sampling bugs (proved by the mutation traps).
2. Double-decrement mutation is detected via event count/final state,
   not conservation — `a−=2, b+=2` trivially conserves the sum; the
   tripwire must be the trajectory.
3. The API ceiling bounds `a0` (cost is O(initial population)), not a
   time-like parameter.
4. CLI prints observed vs closed-form expectation, matching `ld`'s
   theory-vs-observation style.

## 7. Next

Domain queue is empty; the provenance question is settled (narrowness
is deliberate, ADR 0008 + Part 2 narrowness tests). Candidates for
Stage 7: a second SSA regime (bimolecular reaction — genuinely new
algorithm, propensity `k·a·b`, requires ADR amendment), widening
literature resolution to a second domain, or the queued provenance
question "resolved value through the LLM path" (Stage 4 Part 6
§question). None is committed; the stage ends with every guard green
and the domain fully pinned.
