# ADR 0022: ODE Oscillator Domains

**Date:** August 2026  
**Status:** Accepted  
**Stakeholders:** Science team, Backend architecture

## Problem

Terrium initially supported kinetic (Michaelis-Menten), epidemiological (SIR/SEIR), genetic (Wright-Fisher), and stochastic (Gillespie) domains. But three classical ODE models from biology are missing:

1. **Lotka-Volterra** (predator-prey dynamics) — foundational in ecology
2. **Cell Cycle Oscillator** (cyclin/CDK dynamics) — central to cell biology
3. **Repressilator** (synthetic genetic circuit) — key in synthetic biology

These are canonical teaching models and have well-established parameter sets from literature.

## Solution

**Add three new primary API domains for ODE oscillators.**

Each is a fixed literature model with non-negotiable parameter sets:

### 1. Lotka-Volterra

**Citation:** Lotka (1925), Volterra (1926)

**Model:**
```
dP/dt = α·P - β·P·V    (predator growth/decline)
dV/dt = γ·P·V - δ·V    (prey growth/predation)
```

**Parameters:** α, β, γ, δ, P₀, V₀ (all user-tunable for pedagogical purposes)

**Defaults:** From classic Lotka-Volterra parameter set (α=0.5, β=0.02, γ=0.02, δ=0.5)

### 2. Cell Cycle Oscillator

**Citation:** Tyson (1991) "Modeling the cell division cycle: M-phase trigger, DNA replication, and gap zeros"

**Model:** Cyclin/CDK-mediated cell cycle with limit cycle oscillations

**Parameters:** Integration window only (end, points) — all rate constants are literature-fixed

**Why fixed:** Tyson's parameter set is tuned for the specific biology of budding yeast and is not a "knob" users should turn. It's a published result.

### 3. Repressilator

**Citation:** Elowitz & Leibler (2000) "A synthetic oscillatory network of transcriptional regulators"

**Model:** Three-node synthetic gene circuit with mutual repression

**Parameters:** Integration window only (end, points) — all repression constants are from Elowitz & Leibler's design

**Why fixed:** This is a synthetic circuit with experimentally-validated parameters. Users study its dynamics, not tune it.

## Design Rationale

### Why These Three?

1. **Pedagogical importance:** Each is a cornerstone model in its discipline
2. **Literature backing:** Each has canonical parameter sets
3. **User demand:** These are requested repeatedly in biology education contexts
4. **Simplicity:** ODE oscillators are easier to explain than complex stochastic models

### Parameter Philosophy

**Lotka-Volterra:** Tunable  
- This is a classic mathematical model
- The parameters ARE the point—students explore how α, β affect dynamics
- User-supplied parameters are scientifically interesting

**Cell Cycle & Repressilator:** Fixed  
- These are empirical models validated against real data
- Changing parameters breaks the model's correspondence to biology
- Users are studying the model's dynamics, not tuning parameters

This split is intentional and reflects the models' scientific role.

## Implementation

### In Python (tellurium_runner.py)

Three new handlers:

```python
def run_lotka_volterra(parameters):
    # User can override alpha, beta, gamma, delta, p0, v0
    # Or use defaults
    # Returns: time, P, V

def run_cell_cycle_oscillator(parameters):
    # Only accepts end, points (integration window)
    # Uses Tyson's parameter set internally
    # Returns: time, cyclin, CDK

def run_repressilator(parameters):
    # Only accepts end, points (integration window)
    # Uses Elowitz & Leibler's parameter set internally
    # Returns: time, protein_A, protein_B, protein_C
```

### In TypeScript (schemas.ts)

```typescript
lotka_volterra: z.object({
  alpha: optionalNumeric,
  beta: optionalNumeric,
  gamma: optionalNumeric,
  delta: optionalNumeric,
  p0: optionalNumeric,
  v0: optionalNumeric,
  end: optionalNumeric,
  points: integer.nullish(),
}),

cell_cycle_oscillator: z.object({
  end: optionalNumeric,
  points: integer.nullish(),
  seed: integer.nullish(),
}),

repressilator: z.object({
  end: optionalNumeric,
  points: integer.nullish(),
  seed: integer.nullish(),
}),
```

### In queryResolver.ts

Domain defaults for keyword fallback:

```typescript
{
  domain: "lotka_volterra",
  keywords: ["lotka-volterra", "predator-prey", "population dynamics"],
  defaults: { end: 20, points: 201 },
  literature: "Lotka (1925) J Wash Acad Sci 15:461-465; Volterra (1926) J Cons Perm Int Explor Mer 3:3-14"
}
```

### In llmResolver.ts

Added to SUPPORTED_DOMAINS and SYSTEM_PROMPT:

```typescript
{
  domain: "lotka_volterra",
  description: "Lotka-Volterra predator-prey dynamics (Lotka 1925, Volterra 1926). Classical two-species model: predator and prey populations with cyclic oscillations.",
  keywords: ["predator", "prey", "population", "dynamics", "lotka", "volterra"]
}
```

## Keyword Detection

Users can trigger these domains with natural language:

- "simulate predator-prey" → lotka_volterra
- "cell cycle dynamics" → cell_cycle_oscillator
- "repressilator circuit" → repressilator

The keyword resolver extracts these from the query if LLM is unavailable.

## Testing Strategy

1. **Golden file tests** (like Gillespie models):
   - Reference trajectory computed once with known parameters
   - Compare future runs to catch regressions

2. **Literature validation**:
   - Tyson (1991) paper describes expected oscillation period
   - Verify computed trajectories match published behavior

3. **Parameter override tests**:
   - Verify Lotka-Volterra accepts user overrides
   - Verify cell_cycle/repressilator reject parameter attempts (or silently use defaults)

4. **Integration tests**:
   - Full pipeline: query → resolve → validate → run → serialize
   - Verify provenance tracks correctly

## Related ADRs

- **ADR 0003**: Shape validation (structure) vs. scientific validation (bounds)
- **ADR 0007**: Python/TypeScript boundary contract—these three are added to both DISPATCH and SimulationDomain
- **ADR 0013**: Parameter derivation (kcat/Vmax)—these models show the opposite: fixed parameters

## References

- Tyson, John J. (1991). "Modeling the cell division cycle: M-phase trigger, DNA replication, and gap zeros." *Journal of Theoretical Biology* 152.3: 183-192.
- Elowitz, Michael B., and Stanislas Leibler (2000). "A synthetic oscillatory network of transcriptional regulators." *Nature* 403.6767: 335-338.
- Lotka, Alfred J. (1925). "Elements of Physical Biology." Williams & Wilkins.
- Volterra, Vito (1926). "Variazioni e fluttuazioni del numero d'individui in specie." *Mem. Acad. Lincei* 2: 31-113.

## Test Files

- `src/__tests__/domains/*.test.ts` — Individual domain tests
- `src/__tests__/literature-backed-e2e.test.ts` — Full pipeline tests
- Golden files: `src/__tests__/data/golden_lotka_volterra.json`, etc.
