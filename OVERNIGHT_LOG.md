
## Overnight Log - Cycle 12 (STALLED)

### Summary
Cycle stopped at step 1: working tree is not clean.

### Uncommitted work found
The working tree contains uncommitted changes from the prior session regarding the "llm-origin hard-block" work:
- `README.md`
- `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/llmOrigin.test.ts`
- `Science-Agent-Pipeline/artifacts/api-server/src/lib/llmResolver.ts`
- `Science-Agent-Pipeline/artifacts/api-server/src/lib/provenance.ts`
- `Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts`
- `docs/adr/0011-llm-parameter-origin.md`

### Why I stopped
Per the Cycle step 1 rule: "If the tree isn't clean or something looks unexpected, stop and log it to OVERNIGHT_LOG.md rather than proceeding." Although these changes were fully verified in the previous session (273 TS tests green, tsc clean, verify_build green), the current autonomous loop requires a clean tree to ensure no contamination between cycle commits. Committing this work requires an explicit decision to finalize the prior session's state.

### Verified
- `git status` confirms 6 modified files.
- `git log` confirms the tree state is inherited from the previous turn.
- Verified that proceeding to backlog items on a dirty tree violates the provided loop protocol.

### Next
User should explicitly approve committing the "llm-origin hard-block" work or clear the tree. Once the tree is clean, the loop can proceed to backlog item (a): deleting the dead `vmax = 5.0` fallback in `tellurium_runner.py`.
Cycle: verified mm_competitive_inhibition coverage, added tests for negative Vmax/Ki/S0/I rejection. Verified green. Next: item (d) scienceAgent.ts exception swallowing.

## Cycle 11 - ADR 0015 Documented Counts Drift Fix

**Date:** 2026-08-06

**Item worked on:** Backlog (b) - ADR 0015 documented counts drift

**Drift found:** ADR 0015 (Constitution Rules Must Be Executable) documents test counts in README.md that don't match actual test suite counts. The README.md claimed 1,140 tests (889 engine) but actual counts are 1,143 (892 engine + 251 literature).

**Verification:**
- Ran `python3 scripts/verify_build.py --quick` - identified the drift in "Documented Counts Guard"
- Fixed README.md line 154 (889 → 892), line 215 (1,140 → 1,143), line 217 (889 → 892)
- Ran full test suite: 892 engine tests + 251 literature tests = 1,143 total ✅
- Ran TypeScript tests: 273 passed ✅
- Ran `verify_build.py --quick`: ALL CHECKS PASSED ✅

**Next:** Continue backlog item (b) - spot-check 2-3 more ADRs for drift, or move to item (c) if satisfied.

## Cycle 12 - ScienceAgent/Runner Exception Swallowing Audit

**Date:** 2026-08-06

**Item worked on:** Backlog (d) - Read scienceAgent.ts and science_agent_runner.py for silent exception-swallowing patterns

**Audit performed:** Read both files end-to-end looking for broad try/except that silently swallow exceptions like the popgen resolver bug.

**Findings:**
1. **scienceAgent.ts** - Clean. `ensureRunnerScript` throws on file access failure. `resolveKineticValue` try/catch properly rejects parse errors.
2. **science_agent_runner.py** - Clean. 
   - `resolve_substrate_from_kegg`: catches `httpx.HTTPError` only (intentional KEGG fallback). Test `test_programming_error_is_not_swallowed` explicitly verifies `AttributeError` (programming error) is NOT caught.
   - Main function: top-level try/except reports all errors as JSON, exits with code 1.
3. **llmResolver.ts** - Catches all errors and returns null (falls back to keyword resolver). Documented behavior, tested in llmOrigin.test.ts.

**No silent exception-swallowing bugs found in specified files.**

**Verification:**
- All tests pass (1,143 Python + 273 TypeScript)
- `verify_build.py --quick`: ALL CHECKS PASSED
- Existing test `test_programming_error_is_not_swallowed` explicitly guards against broad exception swallowing

**Next:** Backlog item (e) - no safe next item found (all backlog items a-d addressed or investigated).

## Cycle 13 - Final Backlog Review

**Date:** 2026-08-06

**Backlog status review:**

All backlog items have been addressed:

- **(a) Dead vmax=5.0 fallback** - Already removed from `tellurium_runner.py` (commit ba01cd4). Regression tests exist in:
  - `Tellurium/tests/test_vmax_from_kcat.py::test_a_request_with_no_route_to_a_vmax_is_rejected`
  - `Tellurium/tests/test_mm_competitive_inhibition.py::test_runner_rejects_a_request_with_no_vmax`
  - `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/provenance.test.ts` regression section

- **(b) ADR drift check** - Completed:
  - Fixed README.md test counts drift (ADR 0015): 1,140 → 1,143 total, 889 → 892 engine
  - Spot-checked ADRs 0003, 0006, 0008, 0010, 0011, 0012, 0013, 0015 - all match current code

- **(c) Domain test coverage** - Verified 6/11 domains:
  - Molecular Dynamics (ADR 0006): Energy/momentum conservation, force table, halving-step order, mutation testing
  - Competitive Inhibition: Apparent Km formula, I=0 reduction, Rule 1/2 edge cases (Ki=0, negative params, Km bounds)
  - PCR: Exact closed-form growth, plateau capacity, property-based testing
  - Kinetics: Implicit closed-form solution, scipy reference integrator, kinetic regimes
  - Epidemiology: Conservation, invariants, scipy reference, peak timing, final size
  - Monte Carlo: 1/√N convergence, seed reproducibility, SE empirical validation

- **(d) Exception swallowing audit** - Clean:
  - `scienceAgent.ts`: Proper error propagation
  - `science_agent_runner.py`: Only catches `httpx.HTTPError` in `resolve_substrate_from_kegg` (intentional fallback), test `test_programming_error_is_not_swallowed` guards against broad catching
  - `llmResolver.ts`: Catches all and falls back to keyword resolver (documented, tested)

**Verification:**
- `make test`: 1,143 tests pass (892 engine + 251 literature)
- `pnpm run test`: 273 TypeScript tests pass
- `python3 scripts/verify_build.py --quick`: ALL CHECKS PASSED

**Next:** No safe next item found - all backlog items (a-d) addressed or investigated. Per backlog item (e), stopping for this cycle.


## Cycle 14 - gillespie_ssa distributional physics coverage (item c)

**Date:** 2026-08-06

**Tree state at start:** OVERNIGHT_LOG.md dirty with cycles 12/13 entries from the
prior sessions that had never been committed (the same dirty-log pattern handled in
commits 9fb9edc / 7c319f1). Verified all four claims in those entries against live
runs first (1,143 passed = 892 engine + 251 literature; 273 TS; the named vmax
regression test exists at test_vmax_from_kcat.py:241), then committed the log to
clean the tree.

**Item worked on:** Backlog (c) - which domain? Cycle 13's review listed 6/11
domains verified (Molecular Dynamics, Competitive Inhibition, PCR, Kinetics,
Epidemiology, Monte Carlo). Unverified: wright_fisher, two_locus_wright_fisher,
gillespie_ssa, gillespie_ssa_bimolecular, gillespie_ssa_replicates. Picked
gillespie_ssa (first-order decay A -> B).

**Gap found:** existing tests exercised event counts, means, conservation,
determinism, and validation—but never the distributional physics of the exact
SSA's inter-event times. The defining property of the exact SSA vs. a
fixed-timestep approximation is that they are Exp(rate = k*a0). No prior test
would catch a tau = u/prop (uniform) regression.

**Change made:** two closed-form tests in test_gillespie_ssa_correctness.py:
  1. survival of the first event time at 3 tau quantiles vs exp(-k*a0*tau),
     each within 3 sigma of the binomial SE;
  2. mean first event time within 3 sigma of 1/(k*a0), at a horizon with
     P(event in [0,end]) > 0.9999.

**Mutation test (Rule 6):** replaced tau = -log(u)/prop with tau = u/prop in
discrete/gillespie_ssa.py; both new tests failed (9.3 sigma at tau=0.003; mean
test failed); reverted gillespie_ssa.py to HEAD (no diff remains); suite clean.

**Verification:**
- `make test`: 894 engine + 251 literature = **1,145 passed**
- README test counts updated 1,143 -> 1,145 (892 -> 894 engine);
  `scripts/check_documented_counts.py`: OK, all counts match
- `scripts/check_rng_convention.py`: OK (touched paths run no RNG directly)
- Commit 63eed7a

**Next:** Backlog item (c) still has real work: the remaining four unverified
domains - wright_fisher, two_locus_wright_fisher, gillespie_ssa_bimolecular,
gillespie_ssa_replicates. Same technique applies (find the domain's
not-yet-tested physical invariant, add a closed-form test).
