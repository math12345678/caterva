# Performance & Optimization Guide

**Last Updated:** August 9, 2026  
**Focus:** Identifying and addressing backend bottlenecks

## Performance Profile

### Current Baseline (Measured with 404-test suite)

| Operation | Time | Bottleneck |
|-----------|------|------------|
| Query Resolution (keyword fallback) | ~10ms | Regex parsing + literature lookup |
| Query Resolution (LLM path) | ~500–2000ms | LLM API latency (30s timeout cap) |
| Parameter Validation (Zod schemas) | ~5ms | Type checking + interdependency rules |
| Python Interpreter Resolution | ~50ms (cold) / ~1ms (cached) | Python binary discovery |
| Simulation Execution | 50ms–5s | Domain complexity (stochastic >> deterministic) |
| Database Insert | ~10ms | PostgreSQL + network |
| Serialization | ~2ms | JSON encoding |
| **Total Round-Trip** | **100ms–6000ms** | Dominated by LLM + simulation |

### Key Insights

1. **LLM is the biggest latency driver** (500ms–2000ms)
2. **Keyword fallback is fast** (~10ms)
3. **Simulation time varies wildly** (50ms–5s) by domain
4. **System is I/O bound**, not CPU bound (JavaScript async handling is sufficient)

## Optimization Opportunities

### Tier 1: High-Impact, Low-Effort

#### 1.1: Request-Level Caching

**Current State:** Caches by normalized query string

**Problem:** Query like `"simulate predator prey dynamics with p0=100"` and `"predator prey, p0=100, simulate"` are different strings but same intent

**Optimization:**
```typescript
// Parse overrides first
const overrides = extractParameterOverrides(query);
const baseQuery = removeParametersFromQuery(query);

// Cache key: hash(domain) + hash(parameters)
const cacheKey = `${domain}:${JSON.stringify(overrides)}`;
```

**Impact:** ~5–10% cache hit rate improvement

**Effort:** 30 min

#### 1.2: Parameter Lookup Batching

**Current State:** Literature lookups happen sequentially (one parameter at a time)

**Optimization:**
```typescript
// Current: for each parameter, lookup individually
// Optimized: batch lookup all missing parameters
const allMissing = parameters.filter(p => !isKnown(p));
const results = await literature.batchLookup(allMissing);
```

**Impact:** ~50% faster for queries with many missing parameters (3+ parameters)

**Effort:** 1–2 hours

#### 1.3: LLM Response Caching

**Current State:** Every query goes to LLM if configured

**Optimization:**
```typescript
// Cache LLM responses by query hash
const llmCache = new Map<string, LLMResponse>();
const cached = llmCache.get(queryHash);
if (cached) return cached;

const response = await llm.classify(query);
llmCache.set(queryHash, response);
return response;
```

**Impact:** ~70% reduction in LLM calls for similar queries

**Effort:** 1 hour (beware: cache invalidation is hard)

### Tier 2: Medium-Impact, Medium-Effort

#### 2.1: Parallel Python Initialization

**Current State:** Python interpreter resolved on first request (spawnSync blocks)

**Problem:** Cold start causes 500ms latency on first query

**Optimization:**
```typescript
// On server startup, not on first request
import { resolvePythonExecutable } from "./lib/python";
export const pythonExe = resolvePythonExecutable(repoRoot);
// Now first request doesn't block on interpreter discovery
```

**Impact:** Eliminates first-request latency (~500ms)

**Effort:** 30 min

#### 2.2: Streaming Simulation Output

**Current State:** Waits for simulation to complete, then returns full trajectory

**Problem:** Large trajectories (10k+ points) cause response parsing delays

**Optimization:** Use SSE to stream trajectory points as they're computed

```typescript
// Client: receive updates in real-time
for (const point of streamedTrajectory) {
  updateChart(point);
}
```

**Impact:** Perceived latency reduced (user sees results immediately), memory reduced on server

**Effort:** 2–3 hours (requires Python side changes too)

#### 2.3: Structured Query Parser

**Current State:** Uses regex patterns to extract parameters

**Optimization:** Build a proper parser

```
query = "SIR with beta=0.5 gamma=0.1 S0=900"
↓ [tokenize]
[SIR, beta=0.5, gamma=0.1, S0=900]
↓ [parse]
{ domain: "sir", overrides: { beta: 0.5, ... } }
```

**Impact:** More accurate extraction, handles edge cases

**Effort:** 2–4 hours

### Tier 3: High-Impact, High-Effort

#### 3.1: Database Query Optimization

**Current State:** Normalized query string match is O(n) scan

**Optimization:** Add database index
```sql
CREATE INDEX idx_simulations_query 
  ON simulations(LOWER(TRIM(REGEXP_REPLACE(query, '\s+', ' ', 'g'))));
```

**Impact:** ~100x faster cache hits for large datasets (millions of runs)

**Effort:** 30 min (but requires DB migration)

#### 3.2: Lazy Loading of Schemas

**Current State:** All 16 domain schemas loaded at startup

**Optimization:** Load on-demand

```typescript
const schemaCache = new Map<SimulationDomain, ZodSchema>();

function getSchema(domain: SimulationDomain) {
  if (!schemaCache.has(domain)) {
    schemaCache.set(domain, loadSchema(domain));
  }
  return schemaCache.get(domain);
}
```

**Impact:** Negligible (schemas are tiny), but good practice

**Effort:** 1 hour

#### 3.3: Worker Thread Pool for Python

**Current State:** Single Python process, MAX_CONCURRENT=2

**Problem:** Python GIL limits concurrency; only 2 runs at once

**Optimization:** Use worker threads
```typescript
const workers = new WorkerThreadPool(4);
const result = await workers.run('simulation', parameters);
```

**Impact:** 2x–4x throughput increase

**Effort:** 4–6 hours (complex, requires testing)

#### 3.4: WebAssembly ODE Solver (Speculative)

**Current State:** All simulations run in Python

**Problem:** Python startup and bridging overhead

**Optimization:** Compile certain domains to WASM (Lotka-Volterra, cell cycle)

```
deterministic ODE → Rust → WebAssembly → JavaScript
```

**Impact:** 50x–100x speedup for ODE domains

**Effort:** 2–3 days (requires Rust knowledge)

## Monitoring & Profiling

### Enable Request Profiling

```typescript
// app.ts
app.use((req, res, next) => {
  const start = performance.now();
  res.on('finish', () => {
    const duration = performance.now() - start;
    logger.info({ duration, path: req.path }, "Request completed");
  });
  next();
});
```

### Identify Slow Queries

```sql
-- PostgreSQL: queries taking >1s
SELECT query, COUNT(*), AVG(execution_ms) 
FROM simulations_audit_log
WHERE execution_ms > 1000
GROUP BY query
ORDER BY COUNT(*) DESC;
```

### Profile Python Execution

```bash
python -m cProfile -s cumulative src/lib/caterva_runner.py 2>&1 | head -20
```

## Caching Strategy

### Cache Tiers (Current)

| Tier | Mechanism | TTL | Scalability |
|------|-----------|-----|-------------|
| L1 | In-memory Map | None | Single server only |
| L2 | Disk JSON file | None | Single server only |
| L3 | PostgreSQL | None | Multi-server |

### Recommended L4: Redis (For Scale)

```typescript
import redis from "redis";

const cache = redis.createClient();

async function getCachedResult(query: string) {
  const cached = await cache.get(`result:${queryHash}`);
  if (cached) return JSON.parse(cached);
  
  const result = await runSimulation(query);
  await cache.setEx(`result:${queryHash}`, 86400, JSON.stringify(result));
  return result;
}
```

**When to add:** 10k+ daily queries

## Batch Operations

### Future API: Batch Submit

```json
POST /api/simulate/batch
{
  "queries": [
    "SIR beta=0.5 gamma=0.1",
    "predator-prey with p0=100",
    "cell cycle dynamics"
  ]
}

→ Returns array of job IDs
```

**Benefit:** Amortize LLM cost, better resource utilization

## Load Testing

### Test Setup

```bash
# Install wrk
brew install wrk

# Test 100 concurrent users for 30s
wrk -t4 -c100 -d30s \
  -s test_scenario.lua \
  http://localhost:5000/api/simulate
```

### Lua Scenario

```lua
request = function()
  return wrk.format("POST", "/api/simulate", nil,
    '{"query":"SIR beta=0.5 gamma=0.1 S0=900"}')
end
```

### Targets

- **p50 latency:** < 500ms
- **p95 latency:** < 2000ms
- **p99 latency:** < 5000ms
- **Success rate:** > 99.9%

## Memory Management

### Current Memory Profile

| Component | Memory |
|-----------|--------|
| Node process | ~100 MB |
| In-memory job queue | ~10 MB (1000 jobs × ~10 KB each) |
| Cached trajectories | ~50 MB (depends on cache size) |
| Python process | ~300 MB |

### Limits

- Max concurrent jobs: 2 (limited by MAX_CONCURRENT)
- Max in-memory jobs: 1000 (pruned LRU)
- Python heap: Unlimited (configure via PYTHONMALLOC)

### Optimization: Job Metadata Cleanup

```typescript
// After job completed, remove verbose fields
function archiveJob(job: Job) {
  return {
    jobId: job.jobId,
    status: job.status,
    createdAt: job.createdAt,
    // Don't keep: query, result, error (save to DB only)
  };
}
```

## Scaling Strategies

### Single Server (Current)

- Max throughput: ~10–20 jobs/second
- Bottleneck: Python concurrency (MAX_CONCURRENT=2)
- Memory: ~500 MB

### Multi-Server (Future)

**Architecture:**
```
[Load Balancer]
    ↓
[API Server 1] → [Redis Cache]
[API Server 2] → [Shared PostgreSQL]
[API Server 3] →
```

**Changes needed:**
- Replace in-memory cache with Redis
- Use PostgreSQL for all persistence
- Implement distributed job queue (Bull, RabbitMQ)
- Add session stickiness (or use Redis for pending jobs)

## Benchmarking

### Create Benchmark File

```typescript
// benchmark/resolve.bench.ts
import { resolveQuery } from "../src/lib/queryResolver";

async function benchmark() {
  const query = "SIR beta=0.5 gamma=0.1 S0=900";
  
  const iterations = 1000;
  const start = performance.now();
  
  for (let i = 0; i < iterations; i++) {
    await resolveQuery(query);
  }
  
  const duration = performance.now() - start;
  console.log(`${iterations} iterations: ${duration}ms`);
  console.log(`Per-iteration: ${duration/iterations}ms`);
}
```

### Run & Track

```bash
npm run benchmark
# Compare across versions to detect regressions
```

## Quick Wins (Do These First)

### Week 1

- [ ] Add Redis caching layer
- [ ] Enable Python interpreter pre-warming
- [ ] Implement request profiling middleware
- [ ] Create load test scenario

### Week 2

- [ ] Add database query indexes
- [ ] Batch literature lookups
- [ ] Implement cache key normalization

### Week 3

- [ ] Profile Python execution
- [ ] Implement streaming trajectories
- [ ] Add query parser improvements

## Monitoring Dashboards

### Key Metrics to Track

1. **Response latency (p50, p95, p99)**
2. **Cache hit rate**
3. **LLM API latency**
4. **Python execution time**
5. **Queue depth**
6. **Error rate**
7. **Throughput (jobs/sec)**

### Example Prometheus Query

```promql
# 95th percentile request latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

## Profiling Tools

### Node.js Profiling

```bash
# CPU profiling
node --prof src/index.ts
node --prof-process isolate-*.log | head -50

# Heap snapshot
node --inspect-brk src/index.ts
# Then visit chrome://inspect
```

### Python Profiling

```bash
python -m cProfile -s cumulative src/lib/caterva_runner.py
python -m memory_profiler src/lib/caterva_runner.py
```

## References

- `BACKEND_ARCHITECTURE.md` - System design
- `ADR_0007_Python_TypeScript_Boundary_Contract.md` - Concurrency model
- Test files: Regression detection via golden files
- `.env.example` - Configuration options

## Next Steps

1. Run `npm run benchmark` to get baseline metrics
2. Set up Prometheus/Grafana for continuous monitoring
3. Profile a real workload with production queries
4. Prioritize optimizations based on actual bottlenecks (measure first!)
