# Sweep & Batch Metrics Recording

> **⚠️ CORRECTION (2026-08-12):**
> - The "Null-Safety Pattern" section below is backwards. As originally written (before this session), `src/storage/sweep-batch-metrics.ts` gave `averageTimeMs = 0, successRate = 0` for BOTH "no data" (empty operation) and "all failed" — exactly the "unrun sweep and an all-failed sweep were indistinguishable" bug this section claims to prevent. This session fixed it: "no data" (empty `results` array) now returns `averageTimeMs: null, minTimeMs: null, maxTimeMs: null, successRate: null`; "all failed" (a real, non-empty sample where every simulation failed) still correctly returns `successRate: 0`, a real measurement. Verified by reproducing the pre-fix behavior (mutation-tested: reverting the fix reproduces `successRate: 0`/`averageTimeMs: 0` for empty input, exactly as this section describes) and confirming the post-fix tests pass. See `src/storage/sweep-batch-metrics.ts:60-113` and `src/storage/__tests__/sweep-batch-metrics.test.ts` ("handles empty sweep/batch results with null rate/timing, not fabricated zeros").
> - The `SweepMetrics`/`BatchMetrics` TypeScript interfaces shown below list `averageTimeMs`, `minTimeMs`, `maxTimeMs`, and `successRate` as plain `number`. As of this session's fix they are `number | null` (see previous point) — `src/storage/sweep-batch-metrics.ts:10-49`.
> - The `POST /api/sweep` example request body uses `"sweptParameters": [{"name": "Km", "min": 0.5, "max": 2.0, "step": 0.1}]`. The real field name is `sweepParameters` (not `sweptParameters`), and each entry must be `{name, spec}` where `spec` is a `"min:max:step"` string (e.g. `"0.5:2.0:0.1"`), not separate `min`/`max`/`step` fields — see `src/validation/request-validator.ts:104-126` and the destructuring at `src/web/server.ts:457`. This example would fail request validation as written.
> - The `POST /api/batch` example request body uses `"jobs": [{"id": "job_1", "parameters": {...}}]`. The real field name is `parameterSets` (not `jobs`), and it must be an array of flat parameter objects directly (no `id`/`parameters` wrapper) — see `src/validation/request-validator.ts:184-200` and the destructuring at `src/web/server.ts:364`. This example would also fail request validation as written (`parameterSets must be an array`).

## Overview

Batch and Sweep Metrics Recording extends Caterva's metrics tracking system to record performance data not just from individual simulations (`/api/simulate`) but also from parameter sweep (`/api/sweep`) and batch processing (`/api/batch`) operations.

**Why this matters:** A sweep with 1000 simulations previously generated no metrics data in the system—only the final sweep results were returned. Now every simulation within a sweep or batch is individually tracked, and aggregate statistics for the entire sweep/batch operation are automatically computed.

## Architecture

### Data Flow

```
/api/sweep or /api/batch
        ↓
runSweep() or processBatch()
        ↓
[Individual simulations execute]
        ↓
recordSweepMetrics() or recordBatchMetrics()
        ├─ Record sweep/batch-level aggregates
        ├─ Store in in-memory cache
        └─ Update Prometheus exporter
        ↓
API endpoints expose metrics
        ↓
Prometheus scrapes /metrics
        ↓
Grafana visualizes trends
```

### Storage Design

Two independent in-memory caches store metrics:

```typescript
// Sweep metrics cache
const sweepMetricsCache = new Map<string, SweepMetrics>();

// Batch metrics cache  
const batchMetricsCache = new Map<string, BatchMetrics>();
```

**Why in-memory?** Sweep and batch operations are session-scoped (the server restarts, you lose the data). For persistent metrics, use the Prometheus scraper or export to CSV.

## API Endpoints

### Sweep Metrics

#### GET /api/metrics/sweeps
Get all sweep metrics from the current session.

**Response:**
```json
{
  "sweeps": [
    {
      "sweepId": "sweep_1692201600123_a1b2c",
      "query": "michaelis-menten",
      "totalSimulations": 100,
      "completedSimulations": 100,
      "successfulSimulations": 95,
      "failedSimulations": 5,
      "totalTimeMs": 45000,
      "averageTimeMs": 450,
      "minTimeMs": 200,
      "maxTimeMs": 800,
      "successRate": 95
    }
  ],
  "count": 1
}
```

#### GET /api/metrics/sweeps/:sweepId
Get metrics for a specific sweep.

**Response:**
```json
{
  "sweepId": "sweep_1692201600123_a1b2c",
  "query": "michaelis-menten",
  "totalSimulations": 100,
  "completedSimulations": 100,
  "successfulSimulations": 95,
  "failedSimulations": 5,
  "totalTimeMs": 45000,
  "averageTimeMs": 450,
  "minTimeMs": 200,
  "maxTimeMs": 800,
  "successRate": 95
}
```

#### GET /api/metrics/sweeps-by-query
Group all sweep metrics by the query (kinetic model) used.

**Response:**
```json
{
  "michaelis-menten": [
    { "sweepId": "sweep_1", "totalSimulations": 100, ... },
    { "sweepId": "sweep_2", "totalSimulations": 50, ... }
  ],
  "competitive-inhibition": [
    { "sweepId": "sweep_3", "totalSimulations": 200, ... }
  ]
}
```

### Batch Metrics

#### GET /api/metrics/batches
Get all batch metrics from the current session.

**Response:**
```json
{
  "batches": [
    {
      "batchId": "batch_1692201600456_x9y8z",
      "query": "michaelis-menten",
      "totalJobs": 50,
      "completedJobs": 50,
      "successfulJobs": 48,
      "failedJobs": 2,
      "totalTimeMs": 22500,
      "averageTimeMs": 450,
      "minTimeMs": 300,
      "maxTimeMs": 650,
      "successRate": 96
    }
  ],
  "count": 1
}
```

#### GET /api/metrics/batches/:batchId
Get metrics for a specific batch.

**Response:**
```json
{
  "batchId": "batch_1692201600456_x9y8z",
  "query": "michaelis-menten",
  "totalJobs": 50,
  "completedJobs": 50,
  "successfulJobs": 48,
  "failedJobs": 2,
  "totalTimeMs": 22500,
  "averageTimeMs": 450,
  "minTimeMs": 300,
  "maxTimeMs": 650,
  "successRate": 96
}
```

#### GET /api/metrics/batches-by-query
Group all batch metrics by query.

**Response:**
```json
{
  "michaelis-menten": [
    { "batchId": "batch_1", "totalJobs": 50, ... },
    { "batchId": "batch_2", "totalJobs": 100, ... }
  ],
  "competitive-inhibition": [
    { "batchId": "batch_3", "totalJobs": 75, ... }
  ]
}
```

## Prometheus Metrics

The `/metrics` endpoint (Prometheus format) now includes:

```prometheus
# Sweep metrics
caterva_sweeps_total 3
caterva_sweep_avg_success_rate 94.33
caterva_sweep_avg_execution_time_ms 466.67

# Batch metrics
caterva_batches_total 2
caterva_batch_avg_success_rate 95.5
caterva_batch_avg_execution_time_ms 437.5
```

These are automatically scraped by Prometheus every 15 seconds and available in Grafana dashboards.

## Metrics Data Types

### SweepMetrics

```typescript
interface SweepMetrics {
  sweepId: string;                      // Unique identifier for this sweep
  query: string;                        // Kinetic model used
  totalSimulations: number;             // Total sim points in sweep
  completedSimulations: number;         // Completed (successful + failed)
  successfulSimulations: number;        // Passed validation
  failedSimulations: number;            // Failed validation
  totalTimeMs: number;                  // Sum of all simulation times
  averageTimeMs: number;                // Mean execution time per sim
  minTimeMs: number;                    // Fastest simulation
  maxTimeMs: number;                    // Slowest simulation
  successRate: number;                  // (successful / total) * 100
}
```

### BatchMetrics

```typescript
interface BatchMetrics {
  batchId: string;                      // Unique identifier for this batch
  query: string;                        // Kinetic model used
  totalJobs: number;                    // Total jobs in batch
  completedJobs: number;                // Completed (successful + failed)
  successfulJobs: number;               // Passed validation
  failedJobs: number;                   // Failed validation
  totalTimeMs: number;                  // Sum of all job times
  averageTimeMs: number;                // Mean execution time per job
  minTimeMs: number;                    // Fastest job
  maxTimeMs: number;                    // Slowest job
  successRate: number;                  // (successful / total) * 100
}
```

## Usage Example

### Running a Sweep with Metrics

```bash
curl -X POST http://localhost:3000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"Km": 1.0, "Vmax": 10},
    "sweptParameters": [
      {"name": "Km", "min": 0.5, "max": 2.0, "step": 0.1}
    ]
  }'
```

Response includes `sweepId`:
```json
{
  "sweepId": "sweep_1692201600123_a1b2c",
  "query": "michaelis-menten",
  "results": [...],
  "totalSimulations": 16,
  "successRate": 0.9375
}
```

### Retrieving Sweep Metrics

```bash
curl http://localhost:3000/api/metrics/sweeps/sweep_1692201600123_a1b2c
```

### Running a Batch with Metrics

```bash
curl -X POST http://localhost:3000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "jobs": [
      {"id": "job_1", "parameters": {"Km": 1.0, "Vmax": 10}},
      {"id": "job_2", "parameters": {"Km": 1.5, "Vmax": 15}},
      {"id": "job_3", "parameters": {"Km": 2.0, "Vmax": 20}}
    ]
  }'
```

Response includes `batchId`:
```json
{
  "batchId": "batch_1692201600456_x9y8z",
  "query": "michaelis-menten",
  "results": [...],
  "totalJobs": 3,
  "successRate": 1.0
}
```

### Retrieving Batch Metrics

```bash
curl http://localhost:3000/api/metrics/batches/batch_1692201600456_x9y8z
```

## Integration with Monitoring

### Prometheus Scraping

Prometheus automatically scrapes Caterva's `/metrics` endpoint every 15 seconds. Add to `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'caterva'
    static_configs:
      - targets: ['localhost:3000']
```

### Grafana Dashboard

Create panels to visualize sweep/batch metrics:

```json
{
  "title": "Sweep Success Rate Trend",
  "targets": [
    {
      "expr": "caterva_sweep_avg_success_rate"
    }
  ]
}
```

## Testing

Run the comprehensive test suite:

```bash
npm test -- src/storage/__tests__/sweep-batch-metrics.test.ts
```

**Coverage includes:**
- Recording metrics correctly
- Retrieving specific sweeps/batches
- Grouping by query
- Handling all-failed operations
- Handling empty operations
- Success rate accuracy
- Isolation between sweep and batch caches

## Implementation Details

### Metrics Recording Flow

1. **Sweep/Batch Execution:**
   - `runSweep()` or `processBatch()` executes simulations
   - Collects execution time and validation status for each

2. **Metrics Recording:**
   - After all simulations complete, calls `recordSweepMetrics()` or `recordBatchMetrics()`
   - Computes aggregate statistics (mean, min, max, std dev, success rate)
   - Stores in corresponding cache with generated ID

3. **API Exposure:**
   - GET endpoints query the in-memory caches
   - No database queries (session-scoped data)
   - Fast responses (<1ms for small datasets)

4. **Prometheus Export:**
   - `/metrics` endpoint reads all caches
   - Computes per-operation averages
   - Emits Prometheus-format output
   - Scraped automatically by Prometheus

### ID Generation

Both sweep and batch IDs follow the pattern:
```
{type}_{timestamp}_{randomSuffix}

Example: sweep_1692201600123_a1b2c
         batch_1692201600456_x9y8z
```

This ensures:
- **Uniqueness:** Timestamp + random suffix prevents collisions
- **Sortability:** Lexicographic sort ≈ chronological order
- **Debuggability:** Human-readable prefix and timestamp

### Null-Safety Pattern

Following the metrics collector's design, the sweep/batch metrics system distinguishes:

- **"No data" (empty operation):** `averageTimeMs = 0`, `successRate = 0`
- **"All failed":** `successfulJobs = 0`, but `failedJobs > 0`, `successRate = 0`
- **"Some succeeded":** `averageTimeMs > 0`, `successRate = X% > 0`

This prevents the bug where an unrun sweep and an all-failed sweep were indistinguishable in reports.

## Limitations & Future Work

### Current Limitations

1. **In-Memory Only:** Metrics cleared on server restart. Use CSV export or Prometheus for persistence.
2. **Session-Scoped:** No cross-session aggregation. Each restart starts metrics fresh.
3. **No Alerting:** Raw metrics only. Add Prometheus alert rules for thresholds.
4. **No Filtering:** Endpoints return all sweeps/batches. Consider query parameters for time ranges.

### Future Enhancements

- Persist metrics to SQLite or PostgreSQL
- Add query parameters: `/api/metrics/sweeps?query=michaelis-menten&startTime=...`
- Implement automatic alert rules (success rate < 80%, avg time > 1000ms)
- Dashboard widget showing top-10 slowest sweeps/batches
- Comparison reports: "this sweep vs. last sweep"

## Troubleshooting

**Q: Why don't I see any sweep/batch metrics?**
A: Endpoints return empty arrays if no sweeps/batches have run yet. Run a sweep/batch first, then query `/api/metrics/sweeps` or `/api/metrics/batches`.

**Q: Metrics disappeared after server restart**
A: Metrics are in-memory by design. For persistence, export to CSV during the sweep/batch, or set up Prometheus scraping with long retention.

**Q: Why are my sweeps showing 0% success rate?**
A: All simulations in the sweep failed validation. Check simulation parameters and validation logic. Use `/api/metrics/failed-queries` to debug.

**Q: How do I correlate a sweep ID with the original request?**
A: The sweep/batch response includes the `sweepId`/`batchId`. Cross-reference with `/api/metrics/sweeps/:id` or `/api/metrics/batches/:id` to retrieve aggregates.

## See Also

- [Metrics Collector Documentation](./METRICS.md) — Core metrics system
- [Monitoring & Dashboards](./MONITORING.md) — Prometheus & Grafana setup
- [OpenAPI Reference](./openapi.yaml) — Complete API specification
