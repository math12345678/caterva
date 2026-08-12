# Terrium Architecture Quick Reference

> **⚠️ CORRECTION (2026-08-10):** line numbers throughout this doc were wrong even at the commit that introduced it (files have grown since, so treat every `:NNN` reference as approximate, not exact — always grep for the symbol). One structural (not just stale) error: the Python dispatch table (§5, "Python Dispatch") is named `DISPATCHER` with type `Dict[str, Callable]` below — the real object in `Science-Agent-Pipeline/artifacts/api-server/src/lib/terium_runner.py:646` is named `DISPATCH` with type `Dict[str, str]` (maps domain name → handler function *name*, not the callable itself — dispatch resolves the string via `getattr`/lookup, it doesn't store callables directly). `DOMAIN_DEFAULTS` in `queryResolver.ts` is currently at line 513, not 236-555 as shown below (file is now 1589 lines, was shorter when this doc was written).

## File Dependency Map

```
User Query
    ↓
Route Handler (routes/simulate.ts)
    ↓
resolveQuery() [queryResolver.ts]
    ├── resolveQueryWithLLM() [llmResolver.ts]
    │   └── SYSTEM_PROMPT domain union ← [CRITICAL: Line 40]
    │       ├── Validated against whitelist (lines 262-275)
    │       └── Returns: {domain, parameters, reasoning}
    ├── applyKineticResolution() [same file, lines 882-895]
    │   ├── Checks RESOLVABLE_FIELDS [provenance.ts:81]
    │   └── Calls resolveKineticValue() [scienceAgent.ts]
    │       └── Spawns Python: science_agent_runner.py
    ├── queryResolver fallback path (lines 960-1050)
    │   ├── DOMAIN_DEFAULTS keyword matching [lines 236-555]
    │   ├── Fallback kinetic resolution [lines 989-1000]
    │   └── Hard rule check [lines 944-947]
    └── Returns: {domain, parameters, parameterProvenance}
        └── Passed to Python runner
    ↓
teriumRunner.ts / terium_runner.py
    ├── SimulationDomain type [teriumRunner.ts:8]
    ├── DISPATCHER lookup [terium_runner.py:585-586]
    │   ├── "mm" → run_mm()
    │   ├── "mm_competitive_inhibition" → run_mm_competitive_inhibition()
    │   └── ... (11 more)
    └── Engine simulation call
    ↓
terium_engine module (Python)
    └── simulate_mm_competitive_inhibition()
    ↓
Trajectory result → Return to client
```

## Critical Wiring Points

### 1. LLM Domain Classification
**File**: `llmResolver.ts`  
**Lines**: 35-70  
**Contract**: LLM returns JSON with "domain" field

```typescript
const SYSTEM_PROMPT = `...
{
  "domain": "mm" | "mm_competitive_inhibition" | "sir" | ...,
  "parameters": { ... },
  "reasoning": "...",
  "modelCitations": [ ... ],
  "entities": { ... }
}

Domain meanings:
- "mm": Michaelis-Menten enzyme kinetics (no inhibitor).
- "mm_competitive_inhibition": Michaelis-Menten with competitive inhibitor (requires ki parameter).
...
`;
```

**Validation** (lines 262-275): Checks domain is in whitelist

### 2. Domain Defaults & Keywords
**File**: `queryResolver.ts`  
**Lines**: 236-555  
**Contract**: Each domain has keywords and defaults

```typescript
const DOMAIN_DEFAULTS: DomainDefaults[] = [
  {
    domain: "mm_competitive_inhibition",
    parameters: {
      km: 2,
      ki: 1.0,        // ← Separate from km
      vmax: 5,
      s0: 10,
      i0: 0.1,        // Inhibitor concentration
      end: 10,
      points: 51,
    },
    keywords: [
      "competitive inhibition",
      "competitive",
      "inhibition",
      "inhibitor",
    ],
    // ...
  },
  // ... other domains
];
```

### 3. Resolvable Fields & Hard Rule
**File**: `provenance.ts`  
**Lines**: 72-86 (RESOLVABLE_FIELDS), 433-441 (unverifiedOriginKeys)

```typescript
export const RESOLVABLE_FIELDS: Record<string, string[]> = {
  mm: ["km"],
  mm_competitive_inhibition: ["km", "ki"],  // ← Both must resolve
  wright_fisher: ["mutation_rate"],
};

// Hard rule rejects parameters with:
function unverifiedOriginKeys(parameterProvenance) {
  return Object.entries(parameterProvenance)
    .filter(([, p]) => p.origin === "default" || p.origin === "llm")
    .map(([key]) => key);
}
```

**In queryResolver** (lines 944-947):
```typescript
const missing = unverifiedOriginKeys(parameterProvenance);
if (missing.length > 0) {
  throw new RequiredParametersMissingError(llmResult.domain, missing);
}
```

### 4. Kinetic Resolution (Two Paths)

#### Path A: LLM + Literature Fallback (lines 882-895)
```typescript
if ((llmResult.domain === "mm" || llmResult.domain === "mm_competitive_inhibition") &&
    llmResult.parameters.km === undefined) {
  // Attempt to resolve km from literature
  const kinetics = await resolveKineticValue({
    enzymeName: entities.enzymeName,
    substrate: entities.substrate,
    organism: entities.organism,
    ecNumber: entities.ecNumber,
    quantity: "km",  // ← "km" for mm, then "ki" in loop
  });
  // Merge resolved value into parameters
}
```

#### Path B: Fallback Keyword Matching (lines 989-1000)
```typescript
if ((best.domain === "mm" || best.domain === "mm_competitive_inhibition") &&
    !Object.keys(overrides).some((k) => ["km", "ki"].includes(k))) {
  // Fallback kinetic resolution
}
```

### 5. Python Dispatch
**File**: `terium_runner.py`  
**Lines**: 585-586

```python
DISPATCHER: Dict[str, Callable] = {
    "mm": run_mm,
    "mm_competitive_inhibition": run_mm_competitive_inhibition,
    "sir": run_sir,
    # ... (11 more)
}

# Later in run():
if domain not in DISPATCHER:
    raise ValueError(f"Unknown domain: {domain}")
handler = DISPATCHER[domain]
result = handler(params)
```

### 6. mm_competitive_inhibition Handler
**File**: `terium_runner.py`  
**Lines**: 227-257

```python
def run_mm_competitive_inhibition(params: Dict[str, Any]) -> Dict[str, Any]:
    km = float(params.get("km", 2.0))
    ki = float(params.get("ki", 1.0))         # ← Per-key default
    vmax = float(params["vmax"])              # ← Hard required (raises if missing)
    s0 = float(params.get("s0", 10.0))
    i0 = float(params.get("i0", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = terium_engine.simulate_mm_competitive_inhibition(
        km=km, vmax=vmax, ki=ki, s0=s0, i=i0, end=end, points=points
    )

    reported: Dict[str, Any] = {
        "km": km, "vmax": vmax, "ki": ki, "s0": s0, "i0": i0,
        "end": end, "points": points,
    }
    return _serialise_result(result, "mm_competitive_inhibition", reported)
```

---

## Parameter Resolution State Machines

### For `mm` Domain
```
Query: "simulate enzyme km=2 vmax=5"

LLM Path:
  km: "user" (from override)
  vmax: "user" (from override)
  → resolveKineticValue NOT called (both supplied)
  
Keyword Path (if LLM unavailable):
  km: "keyword" (matched DOMAIN_DEFAULTS)
  vmax: "keyword" (matched DOMAIN_DEFAULTS)

Hard Rule Result: ✅ PASS (no "default" or "llm" origin)
```

### For `mm_competitive_inhibition` Domain
```
Query: "simulate competitive inhibition km=2 vmax=5"

LLM Path:
  domain: "mm_competitive_inhibition" (LLM classifies correctly)
  km: "user" (from override)
  vmax: "user" (from override)
  ki: ??? (missing!)
  → RESOLVABLE_FIELDS["mm_competitive_inhibition"] = ["km", "ki"]
  → resolveKineticValue({quantity: "ki"})
  → Returns: ki = 1.2, origin = "resolved"

Hard Rule Result: ✅ PASS (ki has "resolved" origin with citation)

Failure Case:
Query: "simulate competitive inhibition km=2 vmax=5"
(No ki, no literature available)
  ki: "default" (from DOMAIN_DEFAULTS)
  → Hard rule rejects
  → RequiredParametersMissingError("mm_competitive_inhibition", ["ki"])
```

---

## Test Suite Mapping

| Test File | Validates | Status |
|-----------|-----------|--------|
| competitiveInhibitionDomain.test.ts | Domain detection + Ki provenance | ✅ Ready |
| kiProvenance.test.ts | Per-key Ki resolution + citations | ✅ Ready |
| routes.test.ts | HTTP routing | ✅ Ready |
| queryOverrides.test.ts | Parameter override parsing | ✅ Ready |
| provenance.test.ts | Provenance validation rules | ✅ Ready |

---

## Deployment Checklist

- [x] LLM domain union includes all 13 domains
- [x] Domain meanings documented in SYSTEM_PROMPT
- [x] RESOLVABLE_FIELDS configured correctly
- [x] Hard rule logic blocks unverified parameters
- [x] Python DISPATCHER routes all domains
- [x] Handler functions implement domain logic
- [x] Type contracts align (TS ↔ JSON ↔ Python)
- [x] Tests exercise critical paths
- [x] Error messages are explicit and actionable

---

## Common Patterns

### Adding a New Domain

1. **Add to type** (teriumRunner.ts:8)
   ```typescript
   export type SimulationDomain = "mm" | "mm_competitive_inhibition" | ... | "new_domain";
   ```

2. **Add to LLM prompt** (llmResolver.ts:40)
   ```typescript
   "domain": "mm" | "mm_competitive_inhibition" | ... | "new_domain",
   ```

3. **Add description** (llmResolver.ts:52-65)
   ```typescript
   - "new_domain": Description of what this simulates (parameters needed).
   ```

4. **Add domain validation** (llmResolver.ts:262-275)
   ```typescript
   "new_domain",
   ```

5. **Add to DOMAIN_DEFAULTS** (queryResolver.ts:236-555)
   ```typescript
   {
     domain: "new_domain",
     parameters: { /* defaults */ },
     keywords: [ /* keywords */ ],
     reasoning: "...",
   },
   ```

6. **Add to RESOLVABLE_FIELDS** (provenance.ts:72)
   ```typescript
   new_domain: ["param1", "param2"],
   ```

7. **Implement Python handler** (terium_runner.py)
   ```python
   def run_new_domain(params):
       # Extract and validate
       # Call engine
       # Return result
   
   DISPATCHER["new_domain"] = run_new_domain
   ```

8. **Implement engine** (terium_engine module)
   ```python
   def simulate_new_domain(...):
       # Simulation logic
       return trajectory
   ```

---

## References

- **Michaelis-Menten**: BRENDA, https://www.brenda-enzymes.org/
- **Competitive Inhibition**: Lineweaver-Burk plot with competitive inhibitor
- **ADR 0008**: Provenance tracking for parameters
- **ADR 0010**: STRENDA guidelines for kinetic data reporting
- **ADR 0011**: Origin classification (resolved/keyword/llm/user/default)
- **ADR 0017**: CORE + PubMed literature bridge
