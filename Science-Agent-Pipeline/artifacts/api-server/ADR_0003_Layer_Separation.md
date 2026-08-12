# ADR 0003: Layer Separation — Shape vs. Scientific Bounds

**Date:** August 2026  
**Status:** Accepted  
**Stakeholders:** Backend team, Science validation team

## Problem

The simulation pipeline involves both TypeScript (API layer) and Python (engine layer). Both layers perform validation:

1. **TypeScript validates shape**: Are the required parameters present? Are they numeric? Do arrays have the correct length?
2. **Python validates science**: Are the values scientifically plausible? (km > 0, efficiency ∈ [0,1], temperature < ∞, etc.)

Without explicit boundaries, these two layers can drift. For example:
- TypeScript might reject a parameter with a different length check than Python expects
- Python might enforce a range constraint that TypeScript doesn't know about
- A change to the engine's constraints wouldn't be reflected in the API layer

This drift risks inconsistent error messages or, worse, parameters passing validation but failing in the engine.

## Solution

**Clear separation of concerns:**

- **TypeScript (API layer)**: Only validates structural correctness
  - Parameter presence/absence
  - Type correctness (numeric, integer, etc.)
  - Array length (e.g., haplotype arrays must be exactly 4 entries)
  - Format validation (email, UUID, etc.)
  - **Never validate scientific plausibility**

- **Python (engine layer)**: Only validates scientific plausibility
  - Value ranges (km > 0, efficiency ∈ [0,1])
  - Interdependency constraints (temperature < maxTemp)
  - Physical/chemical bounds
  - **Never validate shape**

## Why This Works

1. **Single source of truth for each concern:**
   - Shape constraints are in the Zod schemas (TypeScript)
   - Scientific constraints are in the engine (Python)
   - No duplication = no drift

2. **Clear error messages:**
   - Shape violations: "parameter km: must be a number"
   - Scientific violations: logged to the engine and surfaced as PIPELINE_ERROR

3. **Decoupled evolution:**
   - Adding a new shape constraint only requires TypeScript changes
   - Tightening a scientific bound only requires Python changes
   - Each layer can evolve independently

## Implementation

In `src/lib/schemas.ts`:
- Schemas validate structure only
- Scientific bounds are explicitly excluded (see comments on each schema)

In `src/lib/teriumRunner.ts`:
- Python runner receives pre-validated parameters
- Engine performs all scientific validation
- Shape violations never reach the engine (fail fast at API boundary)

## Trade-offs

**Downside:** If the engine changes a scientific constraint, the TypeScript layer won't know about it. This is deliberate—it maintains separation of concerns.

**Mitigation:** The test suite ensures both layers are in sync through integration tests that actually run the engine.

## References

- ADR 0013 (Enzyme concentration derivation): Relies on this separation to keep kcat/enzyme_conc logic in Python only
- Test: `src/__tests__/schemas.test.ts` validates shape constraints
- Test: `src/__tests__/scienceAgent.test.ts` validates engine constraints
