
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
