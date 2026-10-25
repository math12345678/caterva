# Performance Metrics & Monitoring Guide

> **⚠️ CORRECTION (2026-08-12):**
> - This guide's `GET /api/metrics` example (line ~52) shows `"successRate": 96.67` and its field table calls `successRate` unconditionally "% of successful runs," but the real code at `src/storage/metrics-collector.ts:47` (`AggregatedMetrics.successRate: number | null`) and `:125-136` returns `successRate: null` — not a number, and not omitted — when zero jobs have ever run. A caller doing `jq '.successRate'` on a fresh server gets `null`, not a percentage.
> - Similarly, the reproducibility example (line ~125) shows `"isReproducible": true` as if the field is always a boolean, but `src/storage/metrics-collector.ts:84` and `:272-286` show `isReproducible` starts `null` and stays `null` until a parameter hash has been run at least twice (`runCount >= 2`) — a single observation makes no claim about reproducibility yet.
> - `GET /api/metrics/percentile` (line ~229) is documented as always returning a number, but `metrics-collector.ts:331-343` (`getPercentile()`) returns `null` when there are no successful executions to compute a percentile from.
> - Throughout this guide, "Convergence" / `convergenceSteps` is described as "Number of steps to converge" / "Mean steps to convergence," and slow/outlier sections treat a high value as a sign of "numerical instability" or a model being "hard to solve." The real field is not that: `metrics-collector.ts:14-20` documents it explicitly as the **trajectory output point count** ("Caterva's engine ... is not an iterative solver reporting a real convergence count -- there is no such number to measure"), and the real call site (`src/web/server.ts:198`, `convergenceSteps: response.results?.trajectory?.length ?? 0`) confirms it is fed the trajectory length, not a solver iteration count. A high value means the simulation produced more output points (e.g. longer time span / finer step size), not that it struggled to converge.

Caterva tracks execution performance, reproducibility, and convergence for every simulation to help researchers:

- ✅ Identify performance bottlenecks
- ✅ Verify reproducibility across runs
- ✅ Compare model efficiency
- ✅ Debug failed simulations
- ✅ Optimize parameter choices

---

## Quick Start

The metrics system is **always on**. No configuration needed. Metrics begin accumulating as soon as simulations run.

### View Overall Performance
```bash
curl http://localhost:3000/api/metrics | jq
```

### View Performance by Model
```bash
curl http://localhost:3000/api/metrics/by-model | jq
```

### View Reproducibility Tracking
```bash
curl http://localhost:3000/api/metrics/reproducibility | jq
```

---

## Available Metrics Endpoints

### 1. **Overall Performance** (`GET /api/metrics`)

Summary statistics across all simulations.

**Response:**
```json
{
  "totalJobs": 150,
  "successfulJobs": 145,
  "failedJobs": 5,
  "averageExecutionTimeMs": 245.3,
  "medianExecutionTimeMs": 210.5,
  "minExecutionTimeMs": 50.2,
  "maxExecutionTimeMs": 1823.4,
  "stdDevExecutionTimeMs": 198.7,
  "averageConvergenceSteps": 48,
  "successRate": 96.67
}
```

**What each field means:**

| Field | Meaning |
|-------|---------|
| `totalJobs` | Total simulations run |
| `successfulJobs` | Completed without error |
| `failedJobs` | Failed (convergence, validation, etc.) |
| `averageExecutionTimeMs` | Mean execution time |
| `medianExecutionTimeMs` | 50th percentile (less affected by outliers) |
| `minExecutionTimeMs` | Fastest simulation |
| `maxExecutionTimeMs` | Slowest simulation |
| `stdDevExecutionTimeMs` | Spread of execution times |
| `averageConvergenceSteps` | Mean steps to convergence |
| `successRate` | % of successful runs |

**Interpret it:**
- If `median << average`, you have some slow outliers
- If `stdDev` is high, performance is inconsistent
- If `successRate < 95%`, investigate failed queries

---

### 2. **Metrics by Model** (`GET /api/metrics/by-model`)

Performance breakdown for each kinetic model.

**Response:**
```json
[
  {
    "query": "michaelis-menten",
    "jobCount": 100,
    "averageExecutionTimeMs": 150.2,
    "medianExecutionTimeMs": 120.5,
    "successRate": 99.0,
    "averageConvergenceSteps": 45
  },
  {
    "query": "competitive-inhibition",
    "jobCount": 35,
    "averageExecutionTimeMs": 420.8,
    "medianExecutionTimeMs": 380.2,
    "successRate": 91.4,
    "averageConvergenceSteps": 62
  }
]
```

**Use cases:**
- Compare which models are fastest
- See which models have lower success rates (may need tuning)
- Decide which model to use based on speed/accuracy tradeoff

---

### 3. **Reproducibility Tracking** (`GET /api/metrics/reproducibility`)

Measures consistency of results when running the same parameters multiple times. Critical for **scientific validity**.

**Response:**
```json
[
  {
    "query": "michaelis-menten",
    "parameterHash": "abc123def456",
    "runCount": 5,
    "results": [45.23, 45.21, 45.24, 45.22, 45.23],
    "variance": 0.000123,
    "stdDev": 0.0111,
    "isReproducible": true
  },
  {
    "query": "competitive-inhibition",
    "parameterHash": "xyz789uvw",
    "runCount": 3,
    "results": [128.5, 115.3, 142.1],
    "variance": 183.47,
    "stdDev": 13.54,
    "isReproducible": false
  }
]
```

**What it means:**

- `runCount` — How many times this parameter set was run
- `results` — All final values from each run
- `variance` — Statistical variance (0 = perfect reproducibility)
- `stdDev` — Standard deviation
- `isReproducible` — True if stdDev < 1% of mean (scientific standard)

**Interpret it:**
- ✅ `isReproducible: true` — Results are consistent, simulation is **scientifically sound**
- ❌ `isReproducible: false` — High variance, may indicate numerical instability

---

### 4. **Slow Queries** (`GET /api/metrics/slow-queries?threshold=1000`)

Find simulations that exceed a time threshold (useful for optimization).

**Query parameters:**
- `threshold` — Milliseconds (default: 1000)

**Response:**
```json
{
  "threshold": 1000,
  "queries": [
    {
      "jobId": "job_1722973200000_abc123",
      "query": "competitive-inhibition",
      "executionTimeMs": 1823.4,
      "convergenceSteps": 105,
      "success": true
    },
    {
      "jobId": "job_1722973210000_def456",
      "query": "product-inhibition",
      "executionTimeMs": 1456.2,
      "convergenceSteps": 89,
      "success": true
    }
  ],
  "count": 2
}
```

**Use cases:**
- Identify parameter combinations that are slow
- Detect numerical instability (too many convergence steps)
- Decide when to timeout long-running jobs

---

### 5. **Failed Queries** (`GET /api/metrics/failed-queries`)

Debug failures (validation errors, convergence issues, etc.).

**Response:**
```json
{
  "queries": [
    {
      "jobId": "job_1722973220000_ghi789",
      "query": "competitive-inhibition",
      "executionTimeMs": 150.0,
      "success": false,
      "errorMessage": "Convergence failed after 200 steps"
    }
  ],
  "count": 1
}
```

**Debugging approach:**
1. Look at `query` — Which model fails most?
2. Look at `errorMessage` — Convergence? Validation? Literature?
3. Check if certain parameters always fail

---

### 6. **Percentile Execution Time** (`GET /api/metrics/percentile?percentile=90`)

Find what time N% of queries are completed by (useful for SLAs).

**Query parameters:**
- `percentile` — 1-99 (default: 50 = median)

**Response:**
```json
{
  "percentile": 90,
  "executionTimeMs": 650.5
}
```

**Useful percentiles:**
- `percentile=50` — Median (half faster, half slower)
- `percentile=90` — 90% of queries finish by this time (SLA definition)
- `percentile=95` — Conservative estimate for capacity planning
- `percentile=99` — Worst-case scenario

---

## Common Workflows

### Monitor System Health

```bash
#!/bin/bash
# Check if success rate is acceptable

METRICS=$(curl -s http://localhost:3000/api/metrics)
SUCCESS_RATE=$(echo $METRICS | jq '.successRate')

if (( $(echo "$SUCCESS_RATE < 95" | bc -l) )); then
  echo "⚠️  Warning: Success rate is $SUCCESS_RATE%"
  curl -s http://localhost:3000/api/metrics/failed-queries | jq '.queries[] | {jobId, errorMessage}'
else
  echo "✅ System healthy: $SUCCESS_RATE% success rate"
fi
```

### Find Performance Regressions

```bash
#!/bin/bash
# Compare average execution time to historical baseline

CURRENT=$(curl -s http://localhost:3000/api/metrics | jq '.averageExecutionTimeMs')
BASELINE=250  # Your baseline in ms

if (( $(echo "$CURRENT > $BASELINE * 1.2" | bc -l) )); then
  echo "⚠️  Regression detected!"
  echo "Baseline: ${BASELINE}ms"
  echo "Current: ${CURRENT}ms"
  echo "Delta: +$((CURRENT - BASELINE))ms"
  
  # Find which model regressed
  curl -s http://localhost:3000/api/metrics/by-model | jq '.[] | select(.averageExecutionTimeMs > 300)'
fi
```

### Verify Reproducibility Before Publishing

```bash
#!/bin/bash
# Ensure all key parameter sets are reproducible

REPRODUCIBILITY=$(curl -s http://localhost:3000/api/metrics/reproducibility)

UNREPRODUCIBLE=$(echo $REPRODUCIBILITY | jq '[.[] | select(.isReproducible == false)]')
COUNT=$(echo $UNREPRODUCIBLE | jq 'length')

if [ $COUNT -gt 0 ]; then
  echo "❌ $COUNT parameter sets have high variance:"
  echo $UNREPRODUCIBLE | jq '.[] | {query, parameterHash, stdDev}'
  exit 1
else
  echo "✅ All runs are reproducible!"
fi
```

### Identify Slow Parameter Combinations

```bash
#!/bin/bash
# Find what makes simulations slow

SLOW=$(curl -s "http://localhost:3000/api/metrics/slow-queries?threshold=1000")
echo "Slow queries (>1s):"
echo $SLOW | jq '.queries | group_by(.query) | .[] | {model: .[0].query, count: length, avgSteps: (map(.convergenceSteps) | add / length)}'
```

---

## Metrics Architecture

### Data Collection

Every simulation automatically records:

1. **Execution Time** — startTime, endTime (in milliseconds)
2. **Convergence** — Number of steps to converge
3. **Success/Failure** — Status and error message if failed
4. **Parameters** — Query model and parameter values
5. **Memory** — Peak memory usage (if tracked)

### Storage

Metrics are stored **in-memory** during server lifetime. For persistent storage:

```typescript
// Save metrics to disk
const metrics = getMetricsCollector().getAllMetrics();
fs.writeFileSync('metrics.json', JSON.stringify(metrics, null, 2));

// Load metrics on startup
const saved = JSON.parse(fs.readFileSync('metrics.json', 'utf-8'));
saved.forEach(m => getMetricsCollector().recordExecution(m));
```

### Reproducibility Tracking

Reproducibility is tracked using a **parameter hash**:

```typescript
import crypto from 'crypto';

function hashParameters(params: Record<string, number>): string {
  const sorted = Object.keys(params)
    .sort()
    .map(k => `${k}:${params[k]}`)
    .join('|');
  return crypto.createHash('md5').update(sorted).digest('hex');
}

// Track reproducibility
const hash = hashParameters({km: 5.2, vmax: 12.8, s0: 10});
metrics.trackReproducibility('michaelis-menten', hash, resultValue);
```

Same parameters = same hash = same execution tracked under reproducibility.

---

## Interpreting Results

### Success Rate < 95%

**Causes:**
1. Bad user input (validation catches this)
2. Model doesn't converge (numerical instability)
3. Parameters outside valid range
4. Literature lookup failed

**Fix:**
```bash
curl http://localhost:3000/api/metrics/failed-queries | jq '.queries[0]'
# Look at errorMessage for specifics
```

### High Variance (Unreproducible Results)

**Causes:**
1. Numerical precision issues
2. Floating-point accumulation errors
3. Stochastic elements (if any)
4. Environmental factors (CPU load)

**Fix:**
1. Run multiple times and average
2. Verify literature parameters are exact
3. Check if model converges consistently

### Performance Outliers

**If max >> median:**
1. Some parameter combinations are hard to solve
2. Check `convergenceSteps` — outliers have more steps?
3. Consider increasing timeout for those models

**If mean >> median:**
1. You have performance-impacting outliers
2. Filter them: `GET /api/metrics/slow-queries?threshold=500`
3. Optimize those parameter combinations

---

## Best Practices

### 1. Monitor Success Rate Daily
```bash
0 9 * * * curl -s http://localhost:3000/api/metrics | jq '.successRate'
```

### 2. Track Reproducibility for Key Results
Before publishing a result:
```bash
curl -s http://localhost:3000/api/metrics/reproducibility | jq '.[] | select(.query == "michaelis-menten" and .isReproducible == true)'
```

### 3. Set Performance Budgets
```bash
# P95 should stay under 500ms
PERCENTILE_95=$(curl -s http://localhost:3000/api/metrics/percentile?percentile=95 | jq '.executionTimeMs')
```

### 4. Alert on Variance Increase
```bash
# If stdDev grows, something broke
curl -s http://localhost:3000/api/metrics | jq '.stdDevExecutionTimeMs'
```

### 5. Compare Models Before Choosing
```bash
curl -s http://localhost:3000/api/metrics/by-model | jq '.[] | {query, avgTime: .averageExecutionTimeMs, success: .successRate}'
```

---

## Exporting Metrics

### As JSON
```bash
curl http://localhost:3000/api/metrics > metrics.json
```

### As CSV (manually)
```bash
curl -s http://localhost:3000/api/metrics | jq -r '.[0] | keys[] as $k | "\($k),\(.[$k])"'
```

### To GraphQL/Analytics Service
```typescript
async function pushMetrics() {
  const data = await fetch('http://localhost:3000/api/metrics').then(r => r.json());
  
  // Push to your analytics system
  await fetch('https://analytics.example.com/api/metrics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
}
```

---

## Troubleshooting

### Metrics Endpoint Returns Empty

**Cause:** No simulations have run yet  
**Fix:** Run some simulations first

```bash
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}
  }'
```

### Reproducibility Shows No Data

**Cause:** Each run needs to report its result  
**Fix:** Ensure simulation results are tracked (automatic in v1.0)

### Success Rate Suddenly Drops

**Cause:** Bad code deployed OR literature lookup started failing  
**Fix:**
```bash
curl http://localhost:3000/api/metrics/failed-queries | jq '.queries[0].errorMessage'
```

---

## Future Enhancements

Planned metrics features:

- [ ] Time-series metrics (minute/hour/day aggregations)
- [ ] Metrics persistence to database
- [ ] Grafana integration
- [ ] Real-time dashboards
- [ ] Anomaly detection (alert on regressions)
- [ ] Cost tracking (CPU time × resource cost)
- [ ] Historical trending (track over weeks/months)

---

## Summary

Caterva's metrics system provides:

✅ **Performance tracking** — Identify bottlenecks  
✅ **Reproducibility verification** — Ensure scientific validity  
✅ **Failure debugging** — Understand why simulations fail  
✅ **Model comparison** — Which model is fastest?  
✅ **Health monitoring** — System success rate and stability  

Use these endpoints to build dashboards, set alerts, and verify your simulations are production-ready.
