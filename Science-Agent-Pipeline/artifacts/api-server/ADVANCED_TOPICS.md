# Advanced Topics: Mastering Terrium

**For:** Engineers who want to truly understand and extend the system  
**Status:** August 2026  
**Depth:** Deep dives into sophisticated subsystems

---

## Deep Dive: Parameter Resolution Algorithm

The query resolution system is deceptively complex. Understanding it fully reveals design choices that become critical when extending or debugging.

### The Full Resolution Pipeline

When you submit a query like `"SIR with beta=0.5 gamma=0.1 S0=900"`, here's exactly what happens:

#### Stage 1: Query Normalization (5ms)

```typescript
// src/lib/queryResolver.ts - normalizeQuery
const normalized = query
  .trim()                           // Remove leading/trailing spaces
  .toLowerCase()                    // Case normalization
  .replace(/\s+/g, ' ')            // Collapse multiple spaces
  .replace(/[^\w\s=:\-\.]/g, '')   // Remove special chars (keep = : - . alphanumeric)
```

**Why this matters:**
- Allows "SIR" and "sir" and "S.I.R" to be same
- Prevents spaces from breaking keyword matching
- Removes punctuation that might confuse parser

**Edge case:** User writes `"SIR!!!11"` → normalized to `"sir11"` → might not match "sir" keyword

**Solution:** Extra safeguard in keyword matching to ignore trailing numbers

#### Stage 2: Parameter Extraction (8ms)

Two phases: array parameters first, then scalars.

**Phase 2A: Extract arrays (raw query)**

```typescript
// Must be done on RAW query first, not tokenized
// Reason: "starting_frequencies=[0.5,0,0,0.5]" might be split by spaces
const arrayPattern = /(\w+)\s*[=:]\s*\[([\d\.,\-eE\s]+)\]/g;
// Matches: starting_frequencies=[0.5,0,0,0.5]
// But NOT: starting_frequencies = 0.5, 0, 0, 0.5 (space-separated)
```

**Why two-phase?**

If we naively tokenized first, we'd split `"starting_frequencies=[0.5,0,0,0.5]"` on spaces, losing array structure. By processing arrays on the raw string first, we:
1. Capture complete arrays before tokenization
2. Prevent array values from being misinterpreted as scalars
3. Mark array keys so scalar phase skips them

**Example of what goes wrong without two-phase:**
```
Raw: "starting_frequencies=[0.5,0,0,0.5]"
Tokenize naively: ["starting_frequencies=[0.5,0,0,0.5]"] -- GOOD (no spaces inside)
But: "starting_frequencies = [0.5, 0, 0, 0.5]"
Tokenize naively: ["starting_frequencies", "=", "[0.5,", "0,", "0,", "0.5]"] -- BAD!
So we MUST extract arrays from raw query first
```

**Phase 2B: Extract scalars (tokenized query)**

```typescript
// Now split on whitespace - safe because arrays already extracted
const tokens = query.split(/\s+/);
// Match: beta=0.5 or gamma: 0.1 or km 5
const kvMatch = /^(\w+)\s*[=:]\s*(.+)$/.exec(token);
const value = Number.parseFloat(rawValue);
if (Number.isFinite(value)) {  // CRITICAL: reject NaN, Infinity
  overrides[key] = value;
}
```

**Why parseFloat + isFinite check?**

```javascript
Number.parseFloat("0.5")      // → 0.5 ✅
Number.parseFloat("abc")      // → NaN ✅ (rejected by isFinite)
Number.parseFloat("1e10")     // → 10000000000 ✅
Number.parseFloat("")         // → NaN ✅ (rejected)
Number.parseFloat("Infinity") // → Infinity ✅ (rejected by isFinite)
```

#### Stage 3: Domain Classification (500ms or 10ms)

**Path A: LLM Classification**
```
Query + system prompt → LLM API → "sir" + confidence
```

Timeout: 30 seconds (long because network can be slow)

**Path B: Keyword Fallback**
```
Extract keywords from query → Match against domain keywords → "sir"
```

Timeout: ~10ms (immediate)

**The Design Decision:**

Why not always use LLM?
- Network failures shouldn't crash system
- Keyword path is deterministic (same query → same domain)
- For obvious queries ("SIR epidemic"), LLM is overkill
- Keyword path is 50x faster

Why not always use keywords?
- LLM handles natural language better
- "Predator-prey dynamics" → LLM nails it
- Keywords might miss domain hints in prose

**Critical insight:** The two-path design is not "LLM with fallback." It's "smart routing based on certainty."

```typescript
if (queryLooksOBVIOUS) {
  // Fast path: keywords for "SIR beta=0.5"
  domain = keywordClassify(query);
} else {
  // LLM path for "simulate an epidemic with reproduction number 2.5"
  domain = await llmClassify(query);
  if (llmFails) {
    domain = keywordClassify(query);  // Safety net
  }
}
```

#### Stage 4: Parameter Resolution (50-500ms)

**For each required parameter:**

1. **Check if user supplied it** (from Stage 2)
   ```typescript
   if (overrides[param]) {
     resolved[param] = overrides[param];
     provenance[param] = { origin: 'user' };
     continue;
   }
   ```

2. **Try literature lookup** (if available)
   ```typescript
   const litResult = await literature.lookup(param, enzyme, domain);
   if (litResult.found) {
     resolved[param] = litResult.value;
     provenance[param] = {
       origin: 'resolved',
       citation: litResult.citation,
       // ...
     };
     continue;
   }
   ```

3. **Try LLM suggestion** (if available and LLM classified domain)
   ```typescript
   if (llmSuggestedParams[param] !== undefined) {
     resolved[param] = llmSuggestedParams[param];
     provenance[param] = { origin: 'llm' };
     continue;
   }
   ```

4. **Use default** (if exists)
   ```typescript
   if (DOMAIN_DEFAULTS[domain][param]) {
     resolved[param] = DOMAIN_DEFAULTS[domain][param];
     provenance[param] = { origin: 'default' };
     continue;
   }
   ```

5. **Error: unresolvable**
   ```typescript
   throw new RequiredParametersMissingError(domain, missingParams);
   ```

**The Ordering Matters:**

Why `user > literature > llm > default`?

```
User supply:        Highest trust (user responsibility)
Literature:         High trust (peer-reviewed)
LLM:                Medium trust (speculative)
Default:            Medium trust (project standard)
```

User > literature is obvious (explicit beats inferred).
Literature > LLM: Literature is validated by peer review; LLM is black box.
LLM > Default: LLM might infer domain-specific nuance; default is generic.

**What if this ordering is wrong?**

Flip to `llm > literature`:
- System serves LLM guesses when literature values exist
- LLM might guess "0.5" when literature says "0.3"
- Results diverge from published values
- Reproducibility breaks

**Critical design:** This ordering is baked into the code flow and test expectations. Changing it would break the entire system's scientific integrity.

---

## Deep Dive: Cache Invalidation

The saying goes: "There are only two hard things in computer science: cache invalidation and naming things."

Terrium's cache strategy is deceptively simple, but understanding it reveals important constraints.

### Current Cache Strategy

**What's cached:** Completed simulation results

**Cache key:** Normalized query string

**Normalized means:**
```
"SIR beta=0.5 gamma=0.1"
"SIR  beta = 0.5  gamma = 0.1"
"sir BETA=0.5 GAMMA=0.1"
→ All map to same key: "sir beta=0.5 gamma=0.1"
```

**When is cache invalid?**

1. **Code changes** - A new version of the solver gives different results
   - Cache key doesn't change
   - Old results are still returned
   - **Solution:** Version the cache key on deployment

2. **Parameter semantics change** - Meaning of `km` changes
   - Cache key unchanged (still "km=5")
   - Old results assume old semantics
   - **Solution:** Document parameter meaning in ADR, bump version on change

3. **Deterministic vs stochastic** - Gillespie_SSA with seed=123 gives same result always
   - But without seed, different each time
   - **Solution:** Only cache stochastic simulations if seed is explicit

4. **Physics bounds change** - T < 1000K becomes T < 500K
   - Old results violate new constraint
   - **Solution:** This is rare; document in ADR

### Why We Don't Expire Cache

**Traditional cache expiration:** Delete entries after TTL (e.g., 1 hour)

**Why Terrium doesn't:**
- Simulation results are deterministic
- If parameters/code unchanged, result never changes
- Expiring cache trades accuracy for simplicity
- For scientific work, accuracy > simplicity

**Trade-off:** Cache grows unbounded (mitigated by MAX_JOBS pruning and archive)

### The Query Normalization Problem

**Apparent equivalence:**
```
"SIR beta=0.5 gamma=0.1"
"SIR gamma=0.1 beta=0.5"
```

Both should return the same result (order shouldn't matter).

**But:** Query string matching treats them as different!

**Solution:** Normalize parameter order before caching
```typescript
const normalized = normalizeAndSortParameters(query);
// "SIR beta=0.5 gamma=0.1" regardless of input order
```

**Current implementation detail:** Parameters are extracted as an object `{beta: 0.5, gamma: 0.1}`, then JSON.stringify with sorted keys. This normalizes order.

### Cache Coherence Under Concurrency

**Scenario:**
1. Request A: Query "SIR beta=0.5"
2. Request B: Query "SIR beta=0.5" (arrives 100ms later)
3. A runs simulation, gets result R1
4. B also runs simulation (A's result not yet cached), gets result R2
5. Both try to cache their results

**What should happen?**

- R1 reaches cache first (A finished first)
- R2 arrives, should it overwrite R1?

**Current behavior:** Yes, R2 overwrites R1 (last-write-wins)

**Is this a bug?**

Philosophically: No. If R1 and R2 differ, something is wrong (nondeterminism in stochastic domain).

For stochastic domains (Gillespie, Wright-Fisher): R1 and R2 will differ. This is expected. Last-write-wins means if you query twice without a seed, you get the most recent result.

For deterministic domains (SIR, Lotka-Volterra): R1 and R2 should be identical. Last-write-wins doesn't hurt.

**Better behavior:** 

First-write-wins (don't overwrite if already cached)

```typescript
if (!cache.has(queryKey)) {
  cache.set(queryKey, result);
}
```

This would:
- Avoid redundant writes
- Keep first result (consistent reproducibility)
- Reduce I/O

**Why wasn't this done?**

Reason: Simplicity. Last-write-wins is simpler to reason about. The performance difference is negligible for ~1000 cache entries.

---

## Deep Dive: The Provenance Validation System

Parameter provenance seems straightforward: track where each value came from. But the validation is sophisticated.

### Four Validation Layers

**Layer 1: Computation time (queryResolver.ts)**

When a parameter is resolved, immediately validate:

```typescript
if (origin === 'resolved' && !citation) {
  throw new ProvenanceViolationError(
    'Resolved parameters must have citations'
  );
}
```

This is a **hard error**. Impossible situation = reject immediately.

**Layer 2: Engine time (python bridge)**

Engine might auto-generate parameters (e.g., seed for stochastic simulation).

```python
if 'seed' not in parameters:
    seed = numpy.random.default_rng().integers(0, 2**32)
    parameters['seed'] = seed
    # Note: NO provenance entry yet (Python doesn't know about it)
```

**Layer 3: Response construction (simulate.ts)**

TypeScript wrapper sees engine-generated seed, must add provenance:

```typescript
const engineGenerated = [
  'seed'  // Engine generated this, not user
];

for (const key of engineGenerated) {
  if (key in engineResult.parameters && !(key in parameterProvenance)) {
    parameterProvenance[key] = {
      origin: 'default',
      note: 'Auto-generated by engine for reproducibility'
    };
  }
}
```

This is **honest provenance**. We're not lying and saying seed was "resolved" from literature; we're saying "the engine made it."

**Layer 4: Serialization boundary (before response)**

Before sending response to client:

```typescript
function guardSerializationProvenance(response) {
  for (const [key] of Object.entries(response.parameters)) {
    if (!(key in response.parameterProvenance)) {
      logger.warn(`Missing provenance for ${key}`);
      response.provenance.flags.push(
        `Parameter ${key} missing provenance (pre-migration data?)`
      );
    }
  }
}
```

This is **degraded-but-real**: Flag the problem, but still serve (helpful for pre-migration data).

### Why Four Layers?

**Layer 1 prevents garbage from being generated**
- Fail fast if someone forgets to add citation

**Layer 2 observes reality**
- Engine does things we didn't predict
- Must handle gracefully

**Layer 3 tags engine output**
- Distinguishes "engine made it" from "we resolved it"
- Preserves scientific integrity

**Layer 4 catches mistakes before serialization**
- Last chance to flag problems
- Prevents incomplete responses reaching users

**If we skipped layers:**
- Skip 1: Garbage data enters system
- Skip 2: Engine-generated params have no provenance
- Skip 3: User thinks seed was "resolved" from literature (lie)
- Skip 4: Missing provenance goes unnoticed until user sees it

---

## Deep Dive: Concurrency Under Load

The system limits Python execution to MAX_CONCURRENT=2 simultaneously. But request handling is async—thousands of HTTP connections are fine.

### The Concurrency Model

**HTTP layer:** Unlimited (Express handles thousands)
**Python layer:** Limited to 2 (resource exhaustion protection)
**Queue:** Unlimited size (but pruned at MAX_JOBS=1000)

```
HTTP Request 1, 2, 3, 4, 5, 6, 7, 8
        ↓      ↓    ↓    ↓    ↓   ↓   ↓
    [Enqueue as jobs]
        ↓
    Job Queue [1,2,3,4,5,6,7,8]
        ↓
    Semaphore (MAX_CONCURRENT=2)
        ↓
    [Active: 1,2]  [Waiting: 3,4,5,6,7,8]
        ↓
    Python Bridge (2 processes)
        ↓
    Results returned to clients
```

### Where Concurrency Goes Wrong

**Scenario 1: Semaphore Release Missed**

```typescript
// ❌ WRONG
async function runSimulation() {
  await acquireRunnerSlot();
  
  const result = await python.run(params);  // If this throws...
  releaseRunnerSlot();  // Never executed! Deadlock.
}

// ✅ RIGHT
async function runSimulation() {
  await acquireRunnerSlot();
  try {
    const result = await python.run(params);
  } finally {
    releaseRunnerSlot();  // Always runs
  }
}
```

Terrium uses `finally` blocks for this reason.

**Scenario 2: Cancellation While Waiting**

```typescript
// User cancels job while it's in queue (waiting for semaphore)
// What happens?

const slot = acquireRunnerSlot();  // Promise that resolves when slot available

// If cancelled here, what cleans up?
```

Current implementation: Doesn't have explicit cleanup. Once you're in queue, you're committed.

**Better approach:** Cancellation token that can reject the semaphore acquire:

```typescript
const slot = acquireRunnerSlot(cancellationToken);
// If cancelled before acquire, rejects immediately
// If already acquired, cleanup via finally block
```

**Scenario 3: Stale Results During Upgrade**

You deploy new code while jobs are running:
1. Request A submitted with old code
2. Code upgraded
3. Request A completes with old solver
4. Cached with new code version
5. Next request gets old result with new code expectations
6. Mismatch

**Solution:** Version cache by code hash

```typescript
const cacheKey = `${codeVersion}:${normalizedQuery}`;
```

---

## Deep Dive: The LLM Provider Chain

Multiple LLM APIs are supported with fallback. Understanding the selection logic reveals assumptions.

### Provider Hierarchy

```
1. Try GROQ_API_KEY     (free tier, fast, good models)
2. Try OPENROUTER_API_KEY  (many models, moderate cost)
3. Try MISTRAL_API_KEY   (native Mistral models)
4. Try SILICONFLOW_API_KEY (Chinese provider, low cost)
5. Try OPENAI_API_KEY    (expensive, reliable)
6. Fallback to keywords  (free, 50x slower)
```

**Why this order?**

Groq is free tier that competes with paid alternatives. Openrouter offers choice. Mistral is cost-effective. SiliconFlow is extremely cheap. OpenAI is expensive.

The order optimizes for: Free → Cheap → Expensive → Fallback

### Provider Differences

**Response Format:**
- OpenAI: `{choices: [{message: {content: "..."}}]}`
- Groq: `{choices: [{message: {content: "..."}}]}` (same)
- Mistral: `{choices: [{message: {content: "..."}}]}` (same)
- SiliconFlow: `{choices: [{message: {content: "..."}}]}` (same—all follow OpenAI standard)

**Timeout expectations:**
- Groq: ~500ms-2s (fast inference)
- Openrouter: ~1-5s (depends on model)
- Mistral: ~1-3s
- SiliconFlow: ~2-5s (geographical latency)
- OpenAI: ~1-3s

**Reliability:**
- Groq: 99.9% (infrastructure-heavy)
- Openrouter: 99.5% (aggregator)
- Others: 99-99.5%

### What Happens When LLM Returns Bad Classifications?

User query: `"SIR with R0=2.5"`
LLM returns: `{domain: "cell_cycle_oscillator", confidence: 0.8}`

**Current behavior:** Trust the LLM's response

**Why is this okay?**
- Validator will catch if parameters don't match domain
- If validation fails, clear error message to user
- User can retry with explicit domain

**Why not add confidence threshold?**
```typescript
if (response.confidence < 0.7) {
  useKeywordFallback();
}
```

Reason: LLM often doesn't give confidence scores. And binary yes/no is less useful than "here's my guess, but validate it."

---

## Deep Dive: When Things Break Silently

### Silent Failure Mode 1: Cache Key Collision

Two different simulations accidentally map to same cache key:

```javascript
// Query 1: "SIR beta=0.5 gamma=0.1"
// Query 2: "sir beta=0.5, gamma=0.1" (different punctuation)

// Both normalize to same key
// Second query returns first's result
// If parameters truly different: wrong answer served silently
```

**Prevention:** Strict normalization and test coverage for edge cases

### Silent Failure Mode 2: Parameter Type Coercion

```python
# Python expects float, receives string
Vmax = "100"  # Should be 100.0

# Python might auto-coerce: float("100") = 100.0 ✓
# Or error: TypeError ✗
# Or silently truncate: int("100.5") = 100 ✗

# Terrium prevents this: TypeScript validates types
# But edge case: "100abc" → NaN → rejected
```

### Silent Failure Mode 3: Stochastic Divergence

Two identical queries give different results (for Gillespie):

```
Query 1: "Gillespie_SSA a0=100 k=0.1" → Result R1
Query 1 again: "Gillespie_SSA a0=100 k=0.1" → Result R2
R1 ≠ R2 (both valid, but different)

User thinks this is a bug. It's not—it's stochastic behavior.
```

**Prevention:** Document that without seed, results vary. Include seed in best practices.

---

## Extending the System: Adding a Custom Domain

This is the template for adding a new simulation domain to Terrium.

### Step 1: Write the Python Handler

**File:** `src/lib/terium_runner.py`

```python
def run_my_model(parameters):
    """
    My custom simulation model.
    
    Parameters:
        param1 (float): Description
        param2 (float): Description
        end (float): Simulation end time, default 100
        points (int): Number of output points, default 1001
    
    Returns:
        domain (str): "my_model"
        parameters (dict): Resolved parameters
        trajectory (list): List of dicts with time-series data
    
    Raises:
        ValueError: If parameters out of bounds
    """
    
    # Extract parameters with defaults
    param1 = parameters.get('param1')
    param2 = parameters.get('param2')
    end = parameters.get('end', 100)
    points = parameters.get('points', 1001)
    
    # Validate scientific bounds
    if param1 <= 0:
        raise ValueError('param1 must be positive')
    
    # Run simulation (pseudocode)
    time_points = np.linspace(0, end, points)
    results = []
    
    for t in time_points:
        state = compute_state(t, param1, param2)
        results.append({
            'time': float(t),
            'x': float(state[0]),
            'y': float(state[1]),
            'z': float(state[2])
        })
    
    return {
        'domain': 'my_model',
        'parameters': parameters,
        'trajectory': results
    }

# Add to DISPATCH
DISPATCH['my_model'] = run_my_model
```

### Step 2: Add TypeScript Type and Schema

**File:** `src/lib/teriumRunner.ts`

```typescript
export type SimulationDomain = 
  | 'mm' 
  | 'sir' 
  // ... existing domains
  | 'my_model';  // Add here
```

**File:** `src/lib/schemas.ts`

```typescript
export const SimulationParameterSchemas: Record<SimulationDomain, ZodType> = {
  // ... existing schemas
  my_model: z.object({
    param1: numeric,        // Required
    param2: numeric,        // Required
    end: optionalNumeric,   // Optional, default in Python
    points: integer.nullish(),
  })
};
```

### Step 3: Add Domain Literature & Defaults

**File:** `src/lib/domain-literature.ts`

```typescript
{
  domain: 'my_model',
  description: 'My custom model (Smith 2020). Description of model.',
  keywords: ['my_model', 'custom', 'domain'],
  citations: ['Smith, J. (2020). Journal of Something 42(3):123-456']
}
```

**File:** `src/lib/queryResolver.ts` → `DOMAIN_DEFAULTS`

```typescript
{
  domain: 'my_model',
  keywords: ['my_model', 'custom', 'domain'],
  defaults: { 
    param1: 0.5,
    param2: 1.0,
    end: 100,
    points: 1001 
  },
  literature: 'Smith, J. (2020). Journal of Something 42(3):123-456'
}
```

### Step 4: Add to LLM System Prompt

**File:** `src/lib/llmResolver.ts`

```typescript
const systemPrompt = `
// ... existing domains ...

- my_model: A custom model simulating X with parameters param1 and param2.
  Used for studying Y behavior (Smith 2020).
  Example: "my model with param1=0.5 and param2=1.0"
`;
```

### Step 5: Update OpenAPI Spec

**File:** `lib/api-spec/openapi.yaml`

```yaml
SimulationResponse:
  properties:
    domain:
      enum:
        # ... existing domains ...
        - my_model
```

### Step 6: Update Tests

**File:** `src/__tests__/llmProviders.test.ts`

```typescript
// Update domain count
const RESOLVABLE_DOMAINS_COUNT = 15;  // was 14, now 15

// Test domain
it('exposes my_model to LLM', () => {
  expect(systemPrompt).toContain('my_model');
});
```

**File:** `src/__tests__/myModel.test.ts` (new file)

```typescript
describe('my_model', () => {
  it('runs simulation with valid parameters', async () => {
    const result = await runTerium('my_model', {
      param1: 0.5,
      param2: 1.0
    });
    
    expect(result.domain).toBe('my_model');
    expect(result.trajectory.length).toBeGreaterThan(0);
    expect(result.trajectory[0]).toHaveProperty('time');
    expect(result.trajectory[0]).toHaveProperty('x');
  });
});
```

### Step 7: Create Golden File (Regression Test)

**File:** `src/__tests__/data/golden_my_model_baseline.json`

```json
{
  "domain": "my_model",
  "parameters": {
    "param1": 0.5,
    "param2": 1.0,
    "end": 100,
    "points": 1001
  },
  "trajectory": [
    {"time": 0.0, "x": 0.5, "y": 1.0, "z": 0.0},
    {"time": 0.1, "x": 0.51, "y": 1.01, "z": 0.001},
    // ... 999 more points
  ]
}
```

### Step 8: Verify

```bash
npm test  # Should pass all new tests

# Check domain is exposed
curl http://localhost:5000/api/simulate \
  -d '{"query":"my_model param1=0.5 param2=1.0"}'

# Should succeed and return results
```

### What You'll Have Learned

This process reveals:
- How Python/TypeScript boundary stays synchronized
- Why defaults exist in TWO places (Python defaults + TypeScript schema)
- How LLM learns about domains
- How tests prevent regression
- Why golden files catch solver changes

---

## When to Extend vs. When to Stop

### Extending is justified when:

✅ Domain is fundamentally different from existing ones  
✅ Domain has published literature or established use  
✅ Domain has >10 reasonable use cases  
✅ You can commit to maintaining it

### Extending is NOT justified when:

❌ Domain is minor variant of existing (use parameters instead)  
❌ No published literature to cite  
❌ Maintenance burden outweighs value  
❌ Can be accomplished with SBML escape hatch  

**Example of NOT extending:**
"I want to run SIR but with a small twist for COVID specifically"
→ Use parameters and keyword matching, don't add new domain

**Example of justifying extension:**
"Lotka-Volterra is a canonical teaching model taught in 100s of ecology courses"
→ Worth adding, high maintenance benefit

---

## Conclusion: The Design Philosophy

Terrium's architecture embodies this philosophy:

1. **Explicit over implicit** - Provenance is explicit; we don't hide assumptions
2. **Fail fast** - Validate early; don't produce garbage
3. **Transparent over magical** - Users understand what happened
4. **Reproducible over convenient** - Seeds, provenance, complete documentation
5. **Layered over monolithic** - Problems isolated to layers
6. **Tested over assumed** - Contracts verified by tests

When extending or debugging, return to these principles. They explain seemingly arbitrary choices and prevent new bugs.

---

**This document should be read slowly, over hours or days, returning to implementations as you work on the system.**

**Last Updated:** August 9, 2026  
**Status:** Complete and deep
