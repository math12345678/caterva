# Terrium Backend Architecture Guide

**Last Updated:** August 9, 2026  
**Status:** Complete audit and documentation  
**Test Coverage:** 404/404 tests passing

## Overview

The Terrium Science-Agent Pipeline backend is a TypeScript/Express API that bridges natural language queries to scientific simulations. Users describe what they want to simulate ("show me predator-prey dynamics"), and the system resolves the domain, parameters, and runs the computation.

The architecture emphasizes:
- **Scientific integrity** through parameter provenance tracking
- **Graceful degradation** when external services fail
- **Clear separation of concerns** between the API and engine layers
- **Comprehensive testing** with literature-backed validation

## High-Level Flow

```
User Query
    ↓
[HTTP Request: POST /api/simulate]
    ↓
[Query Resolution] → Classify domain, extract/resolve parameters
    ↓
[Parameter Validation] → Shape check (TypeScript) + Science check (Python)
    ↓
[Simulation Engine] → Python Terium with ODE solver
    ↓
[Response] → Parameters, trajectory, full provenance
    ↓
[Persistence] → Cache (JSON) + Database (optional, PostgreSQL)
```

## System Architecture

### 1. HTTP API Layer (Express)

**File:** `src/app.ts`, `src/routes/`

**Responsibility:** 
- Request validation and parsing
- Rate limiting (1000 req/15min global)
- Response serialization
- Error handling and logging

**Key Middleware:**
- `pinoHttp`: Structured logging
- `express.json()`: Body parsing
- Custom rate limit tracker
- Global error handler

**Endpoints:**
- `GET /healthz` - Health check
- `POST /api/simulate` - Submit job
- `GET /api/simulate` - List recent jobs
- `GET /api/simulate/{jobId}` - Get job status
- `GET /api/simulate/{jobId}/stream` - SSE progress stream
- `POST /api/simulate/{jobId}/cancel` - Cancel job
- `GET /api/simulate/{jobId}/export` - Export as CSV
- And others (waitlist, resolve, metrics)

### 2. Query Resolution Layer

**File:** `src/lib/queryResolver.ts`

**Responsibility:**
- Parse natural language queries
- Extract parameter overrides from text
- Classify domain (via LLM or keywords)
- Resolve missing parameters from literature
- Track provenance for all parameters

**Two Resolution Paths:**

#### Path A: LLM Resolution (When Available)
1. Send query + all domains to LLM
2. LLM returns: domain classification + suggested parameters
3. Tag those parameters `origin: "llm"`
4. Proceed to fill missing values from literature

#### Path B: Keyword Fallback (Always Available)
1. Extract domain keywords from query
2. Match against domain keyword list
3. Extract parameter tokens (km=5, beta=0.3, etc.)
4. Use defaults for any missing parameters
5. Tag those parameters `origin: "default"`

**Why Two Paths?**
- LLM may be unavailable or slow
- Keyword fallback is deterministic and always works
- Users can explicitly control parameters

**Provenance Tracking:**

Every parameter gets an origin tag:
- `resolved`: From literature lookup (BRENDA, ChEMBL, etc.)
- `user`: Explicitly supplied in query
- `llm`: Language model suggestion
- `default`: Project standard value

### 3. Parameter Validation Layer

**File:** `src/lib/schemas.ts`, `src/routes/simulate.ts`

**Responsibility:**
- Shape validation (type, presence, array length)
- Scientific plausibility bounds checking (delegated to Python)
- Error messages for malformed input

**Two-Layer Validation (ADR 0003):**

**TypeScript validates SHAPE:**
- Is `km` present? Is it a number? Is it finite?
- Do haplotype arrays have exactly 4 entries?
- Is `efficiency` numeric?

**Python validates SCIENCE:**
- Is km > 0?
- Is efficiency ∈ [0, 1]?
- Is temperature < max_temperature?

**Why Separate?**
- Prevents layer drift
- Each layer has a single source of truth
- Faster error feedback at API boundary

**Zod Schemas:**

Each of 16 domains has a schema in `SimulationParameterSchemas`:

```typescript
mm: z.object({
  km: numeric,
  vmax: optionalNumeric,
  kcat: optionalNumeric,
  enzyme_conc: optionalNumeric,
  s0: numeric,
  end: optionalNumeric,
  points: integer.nullish(),
}).refine(/* vmax derivation logic */)
```

Schemas include:
- Type constraints (numeric, integer, array length)
- Interdependency rules (e.g., vmax OR (kcat AND enzyme_conc))
- Default value hints (via optionalNumeric)

### 4. Job Queue & Concurrency Control

**File:** `src/lib/queue.ts`

**Responsibility:**
- Track job lifecycle (pending → resolving → validating → running → completed)
- Manage progress tracking
- Control Python bridge concurrency (MAX_CONCURRENT=2)
- Cancellation support

**Job State Machine:**

```
     pending
       ↓
   resolving ←─┐
       ↓       │
 validating    │
       ↓       │
    running    │
       ↓       │
┌─ completed   │
│  failed  ────┴─ cancelled
└─────────────────────────
```

**Concurrency Control (Semaphore):**

The Python bridge can only run 2 simulations at a time to prevent resource exhaustion. Other jobs queue up and acquire slots as they're released.

```typescript
// Acquire slot (wait if needed)
await acquireRunnerSlot();
try {
  // Run engine
} finally {
  releaseRunnerSlot();  // Always release
}
```

**Cancellation:**

- When cancel requested: `setJobCancelled(jobId)`
- This aborts the job's AbortController
- Pipeline checks `isCancelled(jobId)` between stages
- If cancelled mid-run: stop and mark as cancelled

**Job Cleanup:**

- Jobs stay queryable forever (via cache)
- Listeners cleaned up when job terminal (prevents memory leaks)
- In-memory store pruned to MAX_JOBS=1000 (LRU by updatedAt)

### 5. Python Bridge

**File:** `src/lib/terium_runner.ts` (TypeScript wrapper), `src/lib/terium_runner.py` (Python implementation)

**Responsibility:**
- Execute simulation in Python/Terium
- Populate any engine-generated parameters (e.g., seed)
- Return trajectory and domain

**The DISPATCH Contract (ADR 0007):**

Python has a `DISPATCH` dict mapping domains to handler functions:

```python
DISPATCH = {
    "mm": run_mm,
    "sir": run_sir,
    "cell_cycle_oscillator": run_cell_cycle_oscillator,
    # ... 16 total
}
```

TypeScript mirrors this in:
- `SimulationDomain` type union
- Test verification in `llmProviders.test.ts`

If you add a domain: update both or tests fail.

**The 16 Domains:**

| Type | Domain | LLM Exposed? |
|------|--------|--------------|
| **Kinetics** | mm, mm_competitive_inhibition | ✓ |
| **Epidemiology** | sir, seir | ✓ |
| **Genetics** | wright_fisher, two_locus_wright_fisher | ✓ |
| **Stochastic** | gillespie_ssa, gillespie_ssa_bimolecular | ✓ |
| **Dynamics** | molecular_dynamics, lotka_volterra | ✓ |
| **ODE Oscillators** | cell_cycle_oscillator, repressilator | ✓ |
| **Other** | pcr | ✓ |
| **Engine-Internal** | monte_carlo_pi, gillespie_ssa_replicates | ✗ |
| **Escape Hatch** | sbml | ✓ (raw XML) |

### 6. Caching & Persistence

**File:** `src/lib/cache.ts`, `lib/db/`

**Two-Tier Caching:**

#### Tier 1: In-Memory (Always Available)

- Maps query string → SimulationResponse
- Normalized query matching (trim, lowercase, collapse whitespace)
- Limited to MAX_JOBS=1000 entries
- Newest result wins if query re-run with different parameters

#### Tier 2: Disk/Database (Optional)

**Disk Cache** (JSON file):
- Persistent cache file (path: CACHE_FILE env var)
- Loaded at startup into memory
- Append-only: new results added to file
- Schema version tracked for migration

**Database** (PostgreSQL via Drizzle ORM):
- Optional; works if DATABASE_URL configured
- `simulations` table stores run history
- Normalized query lookup for cache hits
- Graceful degradation if DB unavailable

**Why Two Tiers?**
- In-memory: fast, always available
- Disk: persists across server restarts
- Database: analytics, audit trail, multi-server scenarios

### 7. Error Handling Philosophy

**Principle:** "Impossible errors = 500, Implausible-but-real = flag and serve"

**Impossible Error Examples (→ 500):**
- Unstructured violation: parameter isn't numeric when schema says it must be
- Database transaction failure
- Unhandled exception in pipeline

**Implausible-but-Real Examples (→ flag and serve):**
- Cached result with missing per-parameter provenance (pre-migration data)
- LLM returns a parameter we don't recognize (flag it, but include in response)
- STRENDA requirements not met (flag, but still return result)

**Error Response Format:**

```json
{
  "error": "MISSING_REQUIRED_INPUT",
  "message": "Cannot simulate 'sir': beta, gamma could not be resolved from literature and were not supplied in the query. Add beta=<value> gamma=<value> to your query and try again."
}
```

Error codes:
- `BAD_REQUEST` - Invalid request structure
- `MISSING_REQUIRED_INPUT` - User can fix by adding parameters
- `PIPELINE_ERROR` - Internal system error (user can't fix)
- `INTERNAL_SERVER_ERROR` - Unexpected exception
- `ALREADY_TERMINAL` - Job already completed/failed/cancelled
- `NO_DATA` - Export requested but no trajectory

### 8. Literature Verification

**File:** `src/lib/literature-verifier.ts`, `src/lib/citeVerify.ts`

**Responsibility:**
- Verify parameter values against published literature
- Track citation status (verified cross-species match? flagged fallback?)
- STRENDA compliance checking (assay conditions reported?)

**Verification Layers:**

1. **Citation locator verification:**
   - DOI is resolvable?
   - PubMed ID returns expected paper?
   - URL is accessible?

2. **Parameter value verification:**
   - Does cited value match resolved value?
   - Is organism a match or cross-species fallback?
   - Are assay conditions reported?

3. **STRENDA compliance:**
   - Kinetic constants require pH + temperature
   - Tracks "complete" vs. "incomplete"

**Citation Locators:**

Machine-checkable references:
```json
{
  "kind": "pubmed",
  "value": "1234567",
  "deepLink": "https://pubmed.ncbi.nlm.nih.gov/1234567/"
}
```

Kinds: `pubmed`, `doi`, `brenda_ref`, `brenda_ec`, `url`

### 9. Metrics & Observability

**File:** `src/lib/verifiable-metrics.ts`, `src/routes/metrics.ts`

**Metrics Collected:**

- Queue length (Little's Law: L = λW)
- Success rate with Wilson confidence interval
- Latency percentiles
- Domain frequency
- Parameter resolution origin distribution
- LLM provider performance
- Cache hit rate

**Verifiable Metrics:**

Every metric includes:
- Literature reference (author, year, DOI)
- Calculation method
- Confidence interval

Example:
```json
{
  "metric": "avgQueueLength",
  "value": 2.3,
  "literatureReference": "Little (1961) - L = λW",
  "confidence": 0.95
}
```

**Endpoints:**
- `GET /api/metrics` - Aggregate metrics
- `GET /api/metrics/snapshot` - Current state
- `GET /api/metrics/health` - System health

## Key Design Patterns

### Pattern 1: Defensive Programming

```typescript
// Type checking
if (Number.isNaN(value) || !Number.isFinite(value)) {
  reject("not a valid number");
}

// Graceful degradation
const db = getDb();
if (db) {
  await db.insert(...);
} else {
  logger.debug("DB unavailable; continuing");
}

// Error isolation
try {
  // risky operation
} catch (err) {
  logger.error({ err }, "Component failed");
  // continue with fallback
}
```

### Pattern 2: Provenance Tracking at Every Layer

Every time a parameter is set:

```typescript
parameterProvenance[key] = {
  origin: "resolved",
  source: "BRENDA",
  citation: "...",
  // ... all details
};
```

At the end, verify completeness:

```typescript
for (const key of Object.keys(parameters)) {
  if (!parameterProvenance[key]) {
    flag(`Missing provenance for ${key}`);
  }
}
```

### Pattern 3: Serialization Boundary Guards

Before responses leave the API, validate:

```typescript
function guardSerializationProvenance(response: SimulationResponse) {
  for (const [key] of Object.entries(response.parameters)) {
    if (!response.parameterProvenance?.[key]) {
      logger.warn({ key }, "Missing provenance at serialization");
      response.provenance.flags.push(`Parameter ${key} missing provenance`);
    }
  }
}
```

### Pattern 4: Finalization Guarantees

```typescript
const abortController = new AbortController();
const timeoutId = setTimeout(() => abortController.abort(), 30_000);
try {
  response = await fetch(..., { signal: abortController.signal });
} finally {
  clearTimeout(timeoutId);  // Always clean up
}
```

## File Structure

```
src/
├── app.ts                      # Express setup
├── index.ts                    # Server startup
├── lib/
│   ├── cache.ts               # In-memory + file caching
│   ├── logger.ts              # Pino logging setup
│   ├── python.ts              # Python interpreter resolution
│   ├── queue.ts               # Job queue & concurrency
│   ├── schemas.ts             # Zod parameter schemas (16 domains)
│   ├── teriumRunner.ts      # Python bridge wrapper
│   ├── terium_runner.py     # Python simulation engine
│   ├── queryResolver.ts        # Domain + parameter resolution
│   ├── llmResolver.ts          # LLM provider integration
│   ├── literature-verifier.ts  # Citation verification
│   ├── citeVerify.ts           # Citation locator checking
│   ├── strenda-validator.ts    # STRENDA compliance
│   ├── domain-literature.ts    # Literature defaults
│   ├── verifiable-metrics.ts   # Metrics collection
│   └── rateLimit.ts            # Rate limiting
├── routes/
│   ├── index.ts                # Route mounts
│   ├── simulate.ts             # Simulation endpoints
│   ├── health.ts               # Health checks
│   ├── resolve.ts              # Query resolution preview
│   ├── metrics.ts              # Metrics endpoints
│   └── ...
└── __tests__/
    ├── llmProviders.test.ts     # Python/TypeScript boundary contract
    ├── provenance.test.ts       # Provenance logic
    ├── cache.test.ts            # Caching behavior
    ├── schemas.test.ts          # Parameter validation
    ├── routes.test.ts           # HTTP endpoints
    └── ... (28 test files, 404 tests)
```

## Architecture Decision Records

See the `ADR_*.md` files in this directory:

- **ADR 0003:** Layer separation (shape vs. science)
- **ADR 0007:** Python/TypeScript boundary contract
- **ADR 0008:** Parameter provenance tracking
- **ADR 0022:** ODE oscillator domains

These document major architectural choices and their rationale.

## Deployment Checklist

- [ ] Set `PORT` environment variable
- [ ] Set `NODE_ENV` (development/production)
- [ ] Optional: Set `DATABASE_URL` for PostgreSQL persistence
- [ ] Optional: Set `CACHE_FILE` path (defaults to `data/cache.json`)
- [ ] Optional: Configure LLM provider (GROQ_API_KEY, etc.)
- [ ] Optional: Set `METRICS_ADMIN_TOKEN` for metrics endpoints
- [ ] Ensure Python 3.10+ installed with requirements-dev.txt
- [ ] Run tests: `npm test`
- [ ] Start: `npm run dev` or `npm start`

## Performance Characteristics

- **Query resolution:** ~500ms (LLM) or ~10ms (keyword fallback)
- **Parameter validation:** ~5ms (Zod schemas)
- **Simulation runtime:** 50ms–5s depending on domain and steps
- **Total response:** ~100ms–6s typical

**Bottlenecks:**
1. LLM API latency (30s timeout)
2. Python process startup (cold start ~500ms)
3. Simulation computation (depends on domain complexity)

## Testing Strategy

**404 total tests across 28 files:**

- **Unit tests:** Individual function behavior
- **Integration tests:** Multi-layer flows (query → engine → response)
- **Contract tests:** Python/TypeScript boundary synchronization
- **Golden file tests:** Regression detection (compare trajectory shape)
- **Literature tests:** Parameter values match published data
- **End-to-end tests:** Full pipeline with realistic queries

**Test Coverage:**
- All parameter schemas (16 domains)
- All resolution paths (LLM + keyword fallback)
- Error cases and edge cases
- Provenance tracking completeness
- STRENDA compliance checking
- Cache behavior (hit, miss, expiration)
- Concurrency and cancellation

**Continuous Testing:**
- Pre-commit: Quick smoke tests
- PR: Full 404-test suite
- Production: Canary runs with golden files

## Future Improvements

1. **GraphQL Layer:** Alternative to REST for flexible queries
2. **Batch API:** Submit multiple simulations at once
3. **WebSocket:** Real-time job monitoring (replace polling)
4. **Data Export:** More formats (CSV, NetCDF, HDF5)
5. **Caching:** Redis for multi-server scenarios
6. **Monitoring:** Prometheus metrics, APM integration
7. **Rate Limiting:** Per-user/API-key rate limits
8. **Authentication:** OAuth2 for managed access

## References

**Papers & Specs:**
- ADRs in this directory (0003, 0007, 0008, 0022, etc.)
- CONSTITUTION.md (error handling philosophy)
- OpenAPI spec: `lib/api-spec/openapi.yaml`

**Code:**
- `package.json` - Dependencies and scripts
- `tsconfig.json` - TypeScript configuration
- `.env.example` - Environment variable reference

**Related Documents:**
- User API Guide: (frontend documentation)
- Operator Runbook: (deployment & troubleshooting)
- Science Model Reference: (domain descriptions)
