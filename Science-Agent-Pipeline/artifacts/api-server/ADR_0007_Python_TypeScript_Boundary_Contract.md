# ADR 0007: Python/TypeScript Boundary Contract

**Date:** August 2026  
**Status:** Accepted  
**Stakeholders:** Backend architecture, Integration team

## Problem

The Caterva pipeline bridges Python (Caterva engine) and TypeScript (API server). The two layers must agree on:

1. **Which domains exist** (16 total: 14 primary API, 2 engine-internal, 1 escape hatch)
2. **What parameters each domain accepts** (structure and type)
3. **What the engine returns** (response shape, trajectory format)

Misalignment causes:
- API accepts a domain that the engine doesn't implement → 500 error
- API validates a parameter schema that the engine ignores → data loss
- Engine returns a field the API doesn't expect → serialization errors

## Solution

**Automated contract verification between layers:**

1. **Single source of truth: Python DISPATCH**
   - `src/lib/caterva_runner.py` defines DISPATCH: `{domain → handler function}`
   - This is the engine's canonical list of what it can do
   - Must have exactly 16 entries

2. **TypeScript mirrors this in two places:**
   - `src/lib/catervaRunner.ts`: `SimulationDomain` type enum (all 16 domains)
   - `src/__tests__/llmProviders.test.ts`: Validates SUPPORTED_DOMAINS against schema (14 primary only)

3. **Automated test enforcement:**
   - Test reads Python DISPATCH dynamically
   - Verifies TypeScript SUPPORTED_DOMAINS includes all 14 primary domains
   - Fails the build if there's drift
   - See: `src/__tests__/llmProviders.test.ts` line ~XX

## The 16 Domains

```
Primary API (14) - exposed via LLM:
  1. mm                          (Michaelis-Menten kinetics)
  2. mm_competitive_inhibition   (inhibition variant)
  3. sir                         (epidemiology)
  4. seir                        (epidemiology with exposed)
  5. wright_fisher               (population genetics)
  6. two_locus_wright_fisher     (two-locus variant)
  7. gillespie_ssa               (stochastic)
  8. gillespie_ssa_bimolecular   (two-species stochastic)
  9. pcr                         (PCR amplification)
  10. molecular_dynamics         (particle dynamics)
  11. lotka_volterra             (ODE: predator-prey)
  12. cell_cycle_oscillator      (ODE: cell cycle)
  13. repressilator              (ODE: genetic circuit)

Engine-Internal (2) - NOT exposed via LLM:
  14. monte_carlo_pi             (utility for testing)
  15. gillespie_ssa_replicates   (ensemble wrapper)

Escape Hatch (1) - raw SBML:
  16. sbml                       (user-provided XML)
```

## Contract Points

### At Python/TypeScript Boundary

Each domain must have:

1. **Python side** (`caterva_runner.py`):
   - Entry in DISPATCH dict
   - Handler function (e.g., `run_sir()`)
   - Parameter validation in that function

2. **TypeScript side** (`catervaRunner.ts` + `schemas.ts`):
   - Entry in SimulationDomain union type
   - Entry in SimulationParameterSchemas with Zod validation
   - Literature citations and domain defaults (for keyword fallback)

### Verification Checklist

- [ ] Python DISPATCH has entry
- [ ] TypeScript SimulationDomain includes it
- [ ] TypeScript SimulationParameterSchemas has schema
- [ ] Test suite runs the domain end-to-end
- [ ] OpenAPI spec includes domain in enum

## Implementation Details

**Making changes:**

1. **Adding a new domain:**
   - Add handler to `caterva_runner.py`
   - Add to DISPATCH
   - Add type to TypeScript SimulationDomain
   - Add schema to SimulationParameterSchemas
   - Update llmProviders.test.ts RESOLVABLE_DOMAINS count
   - Update OpenAPI spec
   - Add literature backing and domain defaults
   - Update SUPPORTED_DOMAINS in llmResolver.ts
   - Test with: `npm test -- llmProviders.test.ts`

2. **Changing parameters for a domain:**
   - Update Python handler function signature
   - Update Zod schema in TypeScript
   - Update parameter defaults in queryResolver.ts
   - Update test expectations
   - Run full test suite to catch drift

**Why automated tests matter:**

The test `llmProviders.test.ts` reads `caterva_runner.py` at runtime, extracts the DISPATCH dict, and verifies TypeScript knows about all primary domains. If you add a domain to Python but forget TypeScript, the build fails. This prevents silent drift.

## Related ADRs

- **ADR 0003**: Shape validation lives in TypeScript, scientific bounds in Python
- **ADR 0005**: Auto-generated seeds for stochastic domains
- **ADR 0022**: ODE oscillator domains (lotka_volterra, cell_cycle_oscillator, repressilator)

## References

- DISPATCH table: `src/lib/caterva_runner.py` lines ~650–680
- TypeScript mirror: `src/lib/catervaRunner.ts` line ~13
- Contract test: `src/__tests__/llmProviders.test.ts` line ~75
- OpenAPI spec: `lib/api-spec/openapi.yaml` (SimulationResponse.domain enum)
