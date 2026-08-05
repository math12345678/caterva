# OVERNIGHT_LOG

Unsupervised overnight loop log for Terrium. One committed change per cycle;
each entry records what was done, what it was verified against, and what's
next. See the loop task spec for the backlog.

---

## Cycle 1 — 2026-08-04 (backlog item a: dead `vmax = 5.0` fallback)

**What I did.** Deleted the dead `else: vmax = 5.0` fallback in
`run_mm()` in `Science-Agent-Pipeline/artifacts/api-server/src/lib/tellurium_runner.py`,
replacing it with an explicit `ValueError` that mirrors the zod schema
message ("mm needs a Vmax: supply vmax directly, or supply BOTH kcat and
enzyme_conc (Vmax = kcat * [E]0)").

Note on authorship: while I was running the test gates, a concurrent
process (repo owner Smyan's account) committed the identical change as
`ba01cd4` ("fix: reject any mm query with no route to a Vmax (dead vmax=5.0
fallback)", 3 files: provenance.test.ts +49, tellurium_runner.py +10/-1,
test_vmax_from_kcat.py +24). My working tree is byte-identical to that
commit (empty `git diff HEAD` for all three files), and every gate below
ran against this exact tree, so the verification stands regardless of who
typed the commit.

**Why it was dead (call-path trace).** `POST /api/simulate` ->
`runPipeline()` -> `resolveQuery()` throws `RequiredParametersMissingError`
on any default-origin vmax before the runner is ever spawned (both the LLM
and fallback branches), and `validateParameters()` (zod `mm` schema) also
requires vmax OR kcat+enzyme_conc. `runTellurium()` is only invoked from
`routes/simulate.ts` and golden tests that supply full params. So the branch
that runs with no vmax, no kcat, no enzyme_conc is unreachable from any API
query. It was also a lie: `schemas.ts` documents "the runner rejects a
request that supplies neither" — the runner silently defaulted instead.

**Verified against.**
- New TS regression test (provenance.test.ts): "simulate enzyme kinetics
  km=2 s0=10 end=10 points=51" -> `RequiredParametersMissingError` with
  `missing == ["vmax"]` exactly (s0/end/points are user-supplied, so vmax is
  the precise key the fallback would have fabricated). Plus a half-conversion
  case (kcat alone / enzyme_conc alone) still blocked.
- New Python test (test_vmax_from_kcat.py): `run_mm()` with no route to a
  Vmax raises ValueError.
- Mutation test (Rule 6, personally run): re-added `vmax = 5.0`, the new
  Python test failed with "DID NOT RAISE ValueError", reverted from backup
  (steps `;`-separated), suite green again.
- Gates: api-server `tsc --noEmit` clean; `pnpm --filter @workspace/api-server
  run test` 271/271 (was 269); `make test` engine 884 + literature 237 (was
  883 engine) — all green.

**What's next.**
- Backlog item b: spot-check 2-3 "Accepted" ADRs in docs/adr/ against the
  files they describe.
- Follow-up candidate (judgment call, not done this cycle to keep scope to
  one item): `run_mm_competitive_inhibition()` has the same dead-default
  idiom via `params.get("vmax", 5.0)`. It is equally unreachable (vmax is a
  hard-blocked default for that domain too) but uses the conventional `.get()`
  pattern shared by every domain's runner function, so I did not change it
  under item (a). A future cycle could decide whether the whole
  runner-side `.get(default)` idiom should be tightened the same way.
- Also noticed (not acted on): `.aider.chat.history.md`, `.freebuff/`, and
  `Science-Agent-Pipeline/artifacts/api-server/data/` are untracked tool/runtime
  artifacts; they predate this cycle and were left untouched.

---

## Cycle 2 — 2026-08-04 (backlog item c: competitive inhibition edge cases)

**What I did.** Added four Rule 1/2 edge-case tests to
`Tellurium/tests/test_mm_competitive_inhibition.py`:

- `test_ki_zero_is_rejected` — Ki=0 causes division by zero in the inhibition
  term; `ModelBuildError` is raised.
- `test_negative_km_is_rejected` — negative Km is physically impossible;
  `ModelBuildError` is raised.
- `test_km_below_plausible_bound_is_flagged` — Km=1e-8 mM (below the 1e-7 mM
  floor) produces `ok=True, flagged=True`.
- `test_km_above_plausible_bound_is_flagged` — Km=2000 mM (above the 1000 mM
  ceiling) produces `ok=True, flagged=True`.

These were the missing Rule 1/2 tests: the existing suite only covered
happy-path physics (apparent Km formula, I=0 reduction to plain MM).

**Verified against.**
- `python -m pytest Tellurium/tests/test_mm_competitive_inhibition.py` — 6/6
  pass (was 2/2 before this cycle).
- Full suite: `python -m pytest Tests/ Tellurium/tests/ -q` — 1125 passed.
- No existing test was weakened; new tests only.

**What's next.**
- Backlog item b: spot-check 2-3 "Accepted" ADRs in docs/adr/ against the
  files they describe (started but not yet completed).
- Backlog item d: read `scienceAgent.ts` and `science_agent_runner.py` for
  silent exception-swallowing patterns.

---

## Cycle 3 — 2026-08-04 (backlog item d: narrow KEGG exception handler)

**What I did.** In `science_agent_runner.py`, `resolve_substrate_from_kegg()`
had `except Exception:` around `enzyme_lookup.fetch_kegg_enzyme_text()`. This
swallowed every error including genuine programming errors (AttributeError,
TypeError, etc.) that should surface immediately.

Narrowed the handler to `except httpx.HTTPError:`, which is the correct base
class for both HTTP status errors and transport errors (timeouts, connection
failures). Added `import httpx` to the module.

**Verified against.**
- New regression tests (`Tests/test_science_agent_runner.py`):
  - HTTP 404 degrades to None (intended behavior preserved)
  - Timeout degrades to None (intended behavior preserved)
  - AttributeError is NOT swallowed (regression guard)
- Full suite: 1128 tests pass (1125 + 3 new).

**What's next.**
- Backlog item b: spot-check remaining ADRs (0001, 0006, 0007 verified this
  cycle; 0005, 0012, 0013, 0014 verified in prior cycles).
- Backlog item e: if no more safe items, log "no safe next item found".

---

## Cycle 4 — 2026-08-04 (backlog item e: no safe next item found)

**What I did.** Completed spot-check of ADRs 0001, 0005, 0006, 0007, 0012,
0013, 0014, 0015 against current code. All match. Searched production code
(`Science-Agent-Pipeline/artifacts/api-server/src/lib/`, `Tellurium/`) for
additional silent exception-swallowing patterns beyond the KEGG handler fixed
in cycle 3 — none found. No safe next backlog item remains.

**What's next.** Wait for new backlog items or explicit "continue" instruction.

## Cycle 5 — 2026-08-05 (backlog item b: remaining ADR spot-checks)

**What I did.** Spot-checked all 8 ADRs that weren't verified in cycles 3-4:
0002, 0003, 0004, 0008, 0009, 0010, 0011, 0016.

**Results:**
- **0002 (PCR not ODE)**: ✅ `simulate_pcr` in `Tellurium/discrete/pcr.py` is direct Python recurrence, not antimony/roadrunner.
- **0003 (shared plausibility bounds)**: ✅ `KM_PLAUSIBLE_MIN_MM = 1e-7` and `KM_PLAUSIBLE_MAX_MM = 1e3` defined identically in `Tellurium/core/data_structures.py` and `Tests/brenda_client.py`. Test `test_km_lower_bound_matches_the_brenda_layer` pins them equal.
- **0004 (gamma reserved keyword)**: ✅ `GAMMA_PARAM = "gamma_rate"` in `data_structures.py`. Public API `simulate_sir`/`simulate_seir` still use `gamma` as argument name.
- **0008 (parameter provenance)**: ✅ `modelCitations` renamed from `citations`. `ParameterProvenance` interface exists. `validateParameterProvenance` enforces structure. Origins are `resolved|user|llm|default`.
- **0009 (Gillespie SSA)**: ✅ `simulate_gillespie_ssa` implements single first-order decay A→B. `SSA_PLAUSIBLE_MIN_POPULATION = 30`, `SSA_PLAUSIBLE_MAX_RATE = 10.0`. `MAX_API_SSA_POPULATION = 1_000_000`. Conservation tests exist.
- **0010 (STRENDA assay conditions)**: ✅ `assayConditions` and `strendaStatus` fields in `ParameterProvenance`. `STRENDA_GOVERNED_FIELDS` includes km, vmax, kcat, ki. Incomplete conditions degrade to `flagged` in `buildResolvedKineticProvenance`.
- **0011 (LLM parameter origin)**: ✅ `ParameterOrigin` includes `llm`. LLM entries must carry a note. LLM entries cannot carry citation or citationStatus. Tests in `llmOrigin.test.ts`.
- **0016 (cached results provenance)**: ✅ `parameter_provenance` column in schema. `guardSerializationProvenance` called on cache path, job result, and SSE stream.

**No drift found.** All 16 ADRs now verified against code. All match.

**What's next.** All backlog items (a-e) are complete. Wait for new items or explicit instruction.
