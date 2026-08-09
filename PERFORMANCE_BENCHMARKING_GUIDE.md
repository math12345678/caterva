# Performance Benchmarking & Optimization Guide

**Purpose:** Establish baselines, measure improvements, and optimize critical paths  
**Last Updated:** 2026-08-09  
**Owner:** Performance Team  

---

## Performance Baseline Targets

### API Latency

```typescript
interface LatencyTargets {
  // Endpoints
  healthz: { p50: 20, p95: 50, p99: 100 },        // milliseconds
  resolve: { p50: 300, p95: 800, p99: 2000 },
  simulate: { p50: 50, p95: 200, p99: 500 },      // Initial response
  status: { p50: 100, p95: 300, p99: 1000 },
  
  // Overall system
  avgEndpointLatency: 250,
  p95EndpointLatency: 600,
  p99EndpointLatency: 1500
}
```

### Throughput Targets

```typescript
interface ThroughputTargets {
  healthz: 2000,              // requests/second
  resolve: 200,               // requests/second (rate limited to 10/min)
  simulate: 100,              // requests/second (rate limited to 5/min)
  status: 500,                // requests/second
  globalMaxThroughput: 3500   // requests/second
}
```

### Resource Utilization

```typescript
interface ResourceTargets {
  memory: {
    idle: 300,                // MB
    peak: 1200,               // MB
    alert: 2000               // MB
  },
  cpu: {
    idle: 5,                  // %
    peak: 85,                 // %
    alert: 90                 // %
  },
  disk: {
    used: '< 50%',
    iops: 1000,               // operations/second
    alert: '> 80%'
  }
}
```

### Cache Performance

```typescript
interface CacheTargets {
  hitRate: 0.75,              // 75% of queries should hit cache
  missRate: 0.25,             // 25% miss rate acceptable
  evictionRate: 0.05,         // < 5% eviction due to capacity
  avgLookupTime: 2,           // milliseconds
  maxCacheSize: 500           // MB
}
```

---

## Benchmarking Tools & Setup

### 1. Load Testing with Artillery

**Installation:**
```bash
npm install -g artillery
```

**Configuration:**
```yaml
# artillery.yml
config:
  target: "https://api.staging.terrium.dev"
  phases:
    - duration: 60
      arrivalRate: 10        # 10 requests/second
      name: "Warmup"
    - duration: 300
      arrivalRate: 50        # 50 requests/second
      name: "Sustained load"
    - duration: 60
      arrivalRate: 100       # 100 requests/second
      name: "Peak load"

  variables:
    apiKey: "{{ $env.API_KEY }}"

scenarios:
  - name: "Query Resolution"
    flow:
      - post:
          url: "/api/resolve"
          headers:
            Authorization: "Bearer {{ apiKey }}"
          json:
            query: "lactate dehydrogenase km=5"
          expect:
            - statusCode: 200
            - contentType: json

  - name: "Job Simulation"
    flow:
      - post:
          url: "/api/simulate"
          headers:
            Authorization: "Bearer {{ apiKey }}"
          json:
            query: "michaelis menten enzyme"
          capture:
            json: "$.jobId"
            as: "jobId"
      - get:
          url: "/api/simulate/{{ jobId }}"
          headers:
            Authorization: "Bearer {{ apiKey }}"
          expect:
            - statusCode: 200
```

**Run Test:**
```bash
API_KEY=$YOUR_API_KEY artillery run artillery.yml
```

### 2. Performance Profiling in Node.js

**Enable CPU Profiling:**
```bash
# Profile the application
NODE_OPTIONS=--prof npm start

# Process the profile
node --prof-process isolate-*.log > report.txt

# Analyze key metrics
grep "Total" report.txt
```

**Enable Memory Profiling:**
```typescript
// profiling.ts
import v8 from 'v8';

const startHeap = v8.getHeapStatistics();

// Run your code

const endHeap = v8.getHeapStatistics();
console.log('Heap growth:', {
  initial: startHeap.total_heap_size,
  peak: endHeap.total_heap_size,
  growth: endHeap.total_heap_size - startHeap.total_heap_size
});

// Save heap snapshot
v8.writeHeapSnapshot();
```

### 3. Real User Monitoring (RUM)

**Browser-side Performance:**
```typescript
// Collect real user metrics
function captureMetrics() {
  const metrics = {
    navigationTiming: performance.getEntriesByType('navigation')[0],
    resourceTiming: performance.getEntriesByType('resource'),
    paintTiming: performance.getEntriesByType('paint'),
    userTiming: performance.getEntriesByType('measure')
  };
  
  // Send to analytics
  fetch('/api/metrics', {
    method: 'POST',
    body: JSON.stringify(metrics)
  });
}

// Measure critical path
performance.mark('query-start');
// ... query logic
performance.mark('query-end');
performance.measure('query', 'query-start', 'query-end');
```

---

## Benchmarking Procedures

### Procedure 1: Baseline Establishment (Quarterly)

**Objective:** Establish performance baseline for comparison

**Steps:**

1. **Preparation (Day 1)**
   ```bash
   # Ensure clean state
   - Clear caches
   - Reset metrics
   - Restart services
   - Warm up with light load (5 req/s for 5 minutes)
   ```

2. **Execution (Days 2-5)**
   ```bash
   # Run sustained load test
   artillery run artillery.yml
   
   # Collect system metrics
   - CPU usage (top, htop)
   - Memory usage (ps, free)
   - Disk I/O (iostat)
   - Network throughput (iftop)
   ```

3. **Analysis (Day 6)**
   ```
   Key metrics to capture:
   - Response time distribution (p50, p95, p99)
   - Error rate and types
   - Throughput (requests/second)
   - Resource consumption
   - Cache hit rates
   ```

4. **Documentation**
   - Record baseline in BASELINE_METRICS.csv
   - Document system configuration
   - Note any anomalies

**Expected Baseline:**
```
Query Resolution:
  - p50: 300ms
  - p95: 800ms
  - p99: 2000ms
  - Throughput: 200 req/s
  - Error rate: <0.1%

Resource Usage:
  - Memory: 400-600 MB
  - CPU: 30-40%
  - Cache hit rate: 72%
```

### Procedure 2: Performance Testing (Before Deployment)

**Objective:** Verify no performance regression before deploying

**Steps:**

1. **Pre-Deployment Test (Staging)**
   ```bash
   artillery run artillery.yml --target staging-api
   ```

2. **Compare Against Baseline**
   ```
   Acceptable variance: ±5% on latency, ±10% on throughput
   
   If p95 latency increased 5%+:
   - Investigate code changes
   - Profile for bottlenecks
   - Consider rollback if critical
   ```

3. **Production Deployment (Canary)**
   ```bash
   # Deploy to 5% of traffic
   - Monitor error rate
   - Monitor latency
   - Monitor resource usage
   - Wait 30 minutes
   
   # If metrics stable, expand to 50%
   # Then full rollout
   ```

### Procedure 3: Hot Path Profiling (Monthly)

**Objective:** Identify and optimize performance bottlenecks

**Steps:**

1. **Identify Hot Paths**
   ```typescript
   // Using timing decorators
   @measurePerformance()
   async resolveQuery(query: string) {
     // Track which operations take longest
   }
   ```

2. **Profile Hot Paths**
   ```bash
   # Enable detailed profiling
   NODE_OPTIONS=--prof npm start
   
   # Run targeted load
   artillery run --scenario "Query Resolution" artillery.yml
   
   # Analyze results
   node --prof-process isolate-*.log > report.txt
   ```

3. **Optimize**
   - Identify top 3 bottlenecks
   - Implement optimizations
   - Re-profile to verify improvement

4. **Document**
   - Record optimization in PERFORMANCE_IMPROVEMENTS.md
   - Measure performance gain
   - Estimate impact

---

## Key Performance Metrics

### 1. Latency Metrics

```typescript
interface LatencyMetrics {
  // How long endpoints take
  p50: number;              // Median response time
  p95: number;              // 95th percentile
  p99: number;              // 99th percentile
  max: number;              // Maximum observed
  
  // Distribution
  min: number;
  stdDev: number;
  mean: number;
}

// Healthy latency distribution:
// p50: < 300ms (most requests fast)
// p95: < 1000ms (95% fast)
// p99: < 3000ms (99% tolerable)
// max: < 10000ms (outliers acceptable)
```

### 2. Throughput Metrics

```typescript
interface ThroughputMetrics {
  requestsPerSecond: number;     // Actual throughput
  successRate: number;            // % of successful requests
  errorRate: number;              // % of failed requests
  rateLimitedRate: number;        // % rate limited (expected)
}

// Healthy throughput:
// requestsPerSecond: 200-500
// successRate: > 99.9%
// errorRate: < 0.1%
```

### 3. Cache Metrics

```typescript
interface CacheMetrics {
  hitRate: number;                // % cache hits
  missRate: number;               // % cache misses
  evictionRate: number;           // % evicted due to capacity
  avgLookupTime: number;          // Milliseconds
  currentSize: number;            // Current cache size (MB)
  maxSize: number;                // Maximum cache size (MB)
}

// Healthy cache:
// hitRate: > 70%
// avgLookupTime: < 5ms
// evictionRate: < 5%
```

### 4. Resource Metrics

```typescript
interface ResourceMetrics {
  memoryMB: number;               // Current memory usage
  cpuPercent: number;             // CPU utilization %
  openConnections: number;        // Open database/network connections
  diskUsedPercent: number;        // Disk utilization %
  uptime: number;                 // Seconds since startup
}

// Healthy resources:
// memoryMB: < 1000 (idle) to 2000 (peak)
// cpuPercent: < 85%
// openConnections: < 500
// diskUsedPercent: < 80%
```

### 5. Error Metrics

```typescript
interface ErrorMetrics {
  totalErrors: number;
  byType: {
    validation: number;           // Input validation failures
    notFound: number;              // Resource not found
    rateLimit: number;            // Rate limit exceeded
    internal: number;             // Server errors (5xx)
  };
  errorRate: number;              // % of all requests
}

// Healthy error rates:
// errorRate: < 0.1%
// internal errors: < 0.01%
```

---

## Performance Optimization Techniques

### 1. Caching Strategy

**Current State:**
```typescript
// Cache query results
const cache = new Map<string, CachedResult>();

// Cache hit: O(1) lookup
const cached = cache.get(normalizeQuery(query));

// Cache miss: Resolve and store
if (!cached) {
  const result = resolveQuery(query);
  cache.set(normalizeQuery(query), result);
}
```

**Optimization Opportunities:**
```typescript
// 1. Redis backend for distributed caching
const redis = new Redis();
const cached = await redis.get(`query:${normalizeQuery(query)}`);

// 2. Hierarchical caching (L1: Memory, L2: Redis)
const memoryCache = new Map();
const l1 = memoryCache.get(key);
if (!l1) {
  const l2 = await redisCache.get(key);
  if (l2) memoryCache.set(key, l2);
  return l2 || await resolveQuery(query);
}

// 3. Cache warming on startup
async function warmCache() {
  const popularQueries = await getPopularQueries();
  for (const query of popularQueries) {
    const result = await resolveQuery(query);
    cache.set(normalizeQuery(query), result);
  }
}
```

### 2. Query Optimization

**Identify Slow Queries:**
```typescript
// Log queries that exceed threshold
const SLOW_QUERY_THRESHOLD = 500; // milliseconds

function measureQueryPerformance(query: string) {
  const start = performance.now();
  const result = resolveQuery(query);
  const duration = performance.now() - start;
  
  if (duration > SLOW_QUERY_THRESHOLD) {
    logger.warn({ query, duration }, 'Slow query detected');
  }
  
  return result;
}
```

**Optimize Query Resolution:**
```typescript
// Before: Sequential resolution
async function resolveQuery(query: string) {
  const domain = await detectDomain(query);      // 100ms
  const llmResults = await callLLM(query);       // 300ms
  const parameters = await resolveParameters(llmResults);  // 200ms
  const provenance = await buildProvenance(parameters);    // 150ms
  return { domain, parameters, provenance };    // Total: 750ms
}

// After: Parallel resolution
async function resolveQuery(query: string) {
  const domain = await detectDomain(query);      // 100ms
  
  // Parallel paths
  const [llmResults, defaultParams] = await Promise.all([
    callLLM(query),                   // 300ms (parallel)
    getDefaultParameters(domain)      // 100ms (parallel)
  ]);
  
  const parameters = mergeParameters(llmResults, defaultParams);  // 50ms
  const provenance = await buildProvenance(parameters);          // 150ms
  
  return { domain, parameters, provenance };    // Total: 400ms (47% faster!)
}
```

### 3. Memory Optimization

**Identify Memory Leaks:**
```bash
# Capture heap snapshots
node --expose-gc app.js

# In app
setInterval(() => {
  gc(); // Force garbage collection
  const used = process.memoryUsage();
  logger.info('Memory:', {
    heapUsed: Math.round(used.heapUsed / 1024 / 1024),
    heapTotal: Math.round(used.heapTotal / 1024 / 1024)
  });
}, 60000);
```

**Optimize Object Allocation:**
```typescript
// Before: Excessive allocations
for (const job of jobs) {
  results.push({
    jobId: job.jobId,
    status: job.status,
    progress: calculateProgress(job),
    metrics: extractMetrics(job)
  });
}
// Allocates N objects

// After: Reuse object structure
const result = {
  jobId: '',
  status: '',
  progress: 0,
  metrics: {}
};
const results = jobs.map(job => {
  result.jobId = job.jobId;
  result.status = job.status;
  result.progress = calculateProgress(job);
  result.metrics = extractMetrics(job);
  return { ...result };  // Single spread
});
```

### 4. Database Optimization

**Query Optimization:**
```sql
-- Before: Full table scan
SELECT * FROM jobs WHERE status = 'completed';

-- After: Index on status
CREATE INDEX idx_jobs_status ON jobs(status);
SELECT * FROM jobs WHERE status = 'completed';

-- Before: Inefficient join
SELECT * FROM jobs
JOIN results ON jobs.jobId = results.jobId;

-- After: Use foreign key
CREATE INDEX idx_results_jobId ON results(jobId);
SELECT * FROM jobs
JOIN results ON jobs.jobId = results.jobId;
```

### 5. Python Bridge Optimization

**Reduce Startup Overhead:**
```typescript
// Before: Spawn new process per simulation
async function runSimulation(parameters) {
  const proc = spawn('python', [SCRIPT_PATH]);
  const result = await executeSimulation(proc, parameters);
  proc.kill();
  return result;
}
// Each spawn: ~500ms overhead

// After: Connection pool
class PythonProcessPool {
  private processes: ChildProcess[] = [];
  
  async initialize(poolSize: number) {
    for (let i = 0; i < poolSize; i++) {
      this.processes.push(spawn('python', [SCRIPT_PATH]));
    }
  }
  
  async run(parameters) {
    const proc = this.processes[Math.random() * this.processes.length];
    return executeSimulation(proc, parameters);
  }
}
// Reuse: ~50ms overhead per request
```

---

## Monitoring & Alerting

### Key Dashboards

**Operations Dashboard (Grafana):**
```
┌──────────────────────────────┐
│ Error Rate (5m)              │  Should be < 0.1%
├──────────────────────────────┤
│ p95 Latency (5m)             │  Should be < 1000ms
├──────────────────────────────┤
│ Memory Usage                 │  Should be < 2000MB
├──────────────────────────────┤
│ CPU Utilization              │  Should be < 85%
├──────────────────────────────┤
│ Queue Depth                  │  Should be < 1000
├──────────────────────────────┤
│ Cache Hit Rate (24h)         │  Should be > 75%
└──────────────────────────────┘
```

### Alert Rules

```yaml
alerts:
  - name: HighErrorRate
    condition: error_rate > 1%
    duration: 5m
    severity: critical
    
  - name: HighLatency
    condition: p95_latency > 1000ms
    duration: 10m
    severity: high
    
  - name: HighMemory
    condition: memory > 1500MB
    duration: 15m
    severity: high
    
  - name: LowCacheHitRate
    condition: cache_hit_rate < 50%
    duration: 30m
    severity: medium
```

---

## Performance Testing Checklist

Before deployment:

```
Pre-Deployment Checklist:
- [ ] Run baseline tests on staging
- [ ] Compare latency metrics (p50, p95, p99)
- [ ] Verify throughput within targets
- [ ] Check error rates < 0.1%
- [ ] Verify cache hit rates > 70%
- [ ] Test under peak load (2x expected)
- [ ] Check memory doesn't leak over 1 hour
- [ ] Verify database performance
- [ ] Test Python bridge performance
- [ ] Run security scan
- [ ] Get performance approval from team lead
```

---

## Conclusion

Systematic performance benchmarking enables:
1. **Early detection** of performance regressions
2. **Continuous optimization** of hot paths
3. **Capacity planning** based on metrics
4. **SLA compliance** with metrics-driven targets

Review this guide quarterly and update based on:
- New deployment targets
- Changed traffic patterns
- New optimization opportunities
- Hardware upgrades

**Next review:** 2026-11-09
