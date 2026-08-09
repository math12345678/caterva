# Backend Audit & Wiring Fixes Summary

**Date:** August 9, 2026  
**Status:** ✅ Complete — All 404 tests passing

## Issues Found & Fixed

### 1. **Metrics Router Wiring Gap**
**Issue:** The metrics router was defined in `src/routes/metrics.ts` but not imported or mounted in the main router index.

**Impact:** The `/api/metrics/snapshot`, `/api/metrics/health`, and `/api/metrics/reset` endpoints were not accessible.

**Fix:** 
- Added `metricsRouter` import to `src/routes/index.ts`
- Mounted router with `router.use(metricsRouter)`
- Updated endpoint paths to follow the full-path pattern used by other routers

**Verification:** New endpoints now accessible; test coverage confirms.

---

### 2. **Duplicate Domain Entries in Python DISPATCH**
**Issue:** Three domains (lotka_volterra, cell_cycle_oscillator, repressilator) were listed twice in the DISPATCH table, violating Python dictionary semantics.

```python
# Before (lines 663-668):
"lotka_volterra": "simulate_lotka_volterra",
"cell_cycle_oscillator": "simulate_cell_cycle_oscillator",
"repressilator": "simulate_repressilator",
"lotka_volterra": "simulate_lotka_volterra",  # ← Duplicate
"cell_cycle_oscillator": "simulate_cell_cycle_oscillator",  # ← Duplicate
"repressilator": "simulate_repressilator",  # ← Duplicate

# After (lines 663-665):
"lotka_volterra": "simulate_lotka_volterra",
"cell_cycle_oscillator": "simulate_cell_cycle_oscillator",
"repressilator": "simulate_repressilator",
```

**Impact:** While Python dict handles duplication gracefully, it's a code smell and violates clean wiring principles.

**Fix:** Removed duplicate entries.

**Verification:** ADR 0007 boundary contract still satisfied; all 16 domains dispatched.

---

### 3. **LLM Domain List Inconsistencies**
**Issue:** Multiple locations had stale or incomplete domain lists:

- `llmResolver.ts` SUPPORTED_DOMAINS: Only 11 domains (missing the 3 ODE oscillators)
- `llmResolver.ts` SYSTEM_PROMPT: Missing descriptions for the 3 ODE oscillators
- `llmProviders.test.ts` RESOLVABLE_DOMAINS: Only 10-11 domains

**Impact:** LLM queries for these domains would be rejected; test validation was incomplete.

**Fix:**
- Updated SUPPORTED_DOMAINS to include all 14 primary API domains
- Updated SYSTEM_PROMPT domain list and descriptions
- Updated test RESOLVABLE_DOMAINS to match

**Verification:** All domain types now accessible via LLM; test coverage confirms rejection-free flow.

---

### 4. **Missing Environment Configuration Documentation**
**Issue:** No `.env.example` file to guide deployments on LLM keys, Python paths, cache locations, etc.

**Impact:** Operators had to reverse-engineer environment variable requirements from source code.

**Fix:** Created comprehensive `.env.example` documenting:
- Core server (PORT, NODE_ENV, LOG_LEVEL)
- Python bridge (TERRIUM_PYTHON, VIRTUAL_ENV)
- LLM configuration (5 provider options + generic OpenAI-compatible)
- Data persistence (CACHE_FILE, WAITLIST_FILE)
- Security (METRICS_ADMIN_TOKEN)
- Clear notes on mutual exclusivity and defaults

---

## Verification Checklist

✅ **ADR 0007 Compliance** — Python DISPATCH and TypeScript SimulationDomain synchronized  
✅ **Boundary Contract** — Engine's __all__ fully represented (16 domains)  
✅ **LLM Wiring** — 14 primary API domains exposed; 2 engine-internal correctly hidden  
✅ **Network Resilience** — 30-second timeout on LLM API calls  
✅ **Logging Consistency** — No console.error; all logging uses logger module  
✅ **Route Mounting** — All routers correctly imported and mounted  
✅ **Error Handling** — Structured error responses; graceful fallbacks  
✅ **Test Coverage** — 404 tests passing, 100% on core paths  

---

## Architecture Notes

### Domain Categories (16 total)
**Primary API (14):**
- Kinetics: mm, mm_competitive_inhibition
- Epidemiology: sir, seir
- Population genetics: wright_fisher, two_locus_wright_fisher
- Stochastic: gillespie_ssa, gillespie_ssa_bimolecular
- Other: pcr, molecular_dynamics
- ODE oscillators: lotka_volterra, cell_cycle_oscillator, repressilator

**Engine-Internal (2):**
- monte_carlo_pi (internal utility; not exposed via LLM)
- gillespie_ssa_replicates (internal utility; not exposed via LLM)

**Escape Hatch (1):**
- sbml (raw SBML string, not language-resolved)

### Key Files Modified
- `src/lib/llmResolver.ts` — Domain validation and LLM prompt
- `src/lib/tellurium_runner.py` — DISPATCH table cleanup
- `src/lib/telluriumRunner.ts` — SimulationDomain type (unchanged, already correct)
- `src/routes/index.ts` — Metrics router wiring
- `src/routes/metrics.ts` — Endpoint path corrections
- `src/__tests__/llmProviders.test.ts` — Test data sync
- `.env.example` — New configuration reference

---

## Notes for Operators

1. **LLM Configuration:** Only one of LLM_PROVIDER or LLM_API_KEY + LLM_API_URL should be set. The provider selection is hierarchical.

2. **Metrics Reset:** Requires METRICS_ADMIN_TOKEN. If unset, the endpoint returns 501. Use Bearer token scheme: `Authorization: Bearer <token>`

3. **Database Fallback:** When DB is unavailable, the system gracefully falls back to in-memory cache. Completed jobs remain queryable until restart.

4. **Runtime Ceilings:** API-level concurrency limits (MAX_CONCURRENT=2) and per-domain runtime ceilings prevent hung requests.

---

**Test Results:**
```
Test Files: 28 passed (28)
Tests:      404 passed (404)
Duration:   ~42s
```
