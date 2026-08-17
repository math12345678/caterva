# Quick Start: Sweep & Batch Metrics

> **⚠️ CORRECTION (2026-08-12):** The `POST /api/sweep` example body (line ~17) uses `"sweptParameters": [{"name": "Km", "min": 0.5, "max": 2.0, "step": 0.1}]`. The real field name is `sweepParameters` (not `sweptParameters`), and each entry must be `{name, spec}` with `spec` as a `"min:max:step"` string (e.g. `"0.5:2.0:0.1"`), not separate `min`/`max`/`step` fields — see `src/validation/request-validator.ts:104-126` and `src/web/server.ts:457`. Copy-pasting this example as written fails request validation. (Same issue also present in `SWEEP_BATCH_METRICS.md`, corrected there too.)

## 60-Second Overview

Terrium now automatically tracks metrics from parameter sweeps and batch operations. Every simulation within a sweep/batch is counted, and aggregate statistics (success rate, timing, counts) are exposed via REST APIs and Prometheus.

## Basic Usage

### 1. Run a Sweep (metrics automatically recorded)

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

Response includes a `sweepId`:
```json
{
  "sweepId": "sweep_1692201600123_a1b2c",
  "query": "michaelis-menten",
  "results": [...],
  "totalSimulations": 16,
  "successRate": 0.9375
}
```

### 2. Query Sweep Metrics

```bash
# Get specific sweep
curl http://localhost:3000/api/metrics/sweeps/sweep_1692201600123_a1b2c

# Get all sweeps
curl http://localhost:3000/api/metrics/sweeps

# Group by query
curl http://localhost:3000/api/metrics/sweeps-by-query
```

### 3. Same for Batches

```bash
# Query batch metrics (replace "sweep" with "batch" in the URL)
curl http://localhost:3000/api/metrics/batches/batch_1692201600456_x9y8z
curl http://localhost:3000/api/metrics/batches
curl http://localhost:3000/api/metrics/batches-by-query
```

## API Response Format

```json
{
  "sweepId": "sweep_1692201600123_a1b2c",
  "query": "michaelis-menten",
  "totalSimulations": 16,
  "successfulSimulations": 15,
  "failedSimulations": 1,
  "completedSimulations": 16,
  "totalTimeMs": 7200,
  "averageTimeMs": 450,
  "minTimeMs": 200,
  "maxTimeMs": 800,
  "successRate": 93.75
}
```

## Monitoring in Grafana

1. Start Prometheus and Grafana:
   ```bash
   docker-compose -f docker-compose-monitoring.yml up
   ```

2. Prometheus scrapes `/metrics` every 15 seconds

3. Metrics available:
   - `terrium_sweeps_total` — number of sweeps
   - `terrium_sweep_avg_success_rate` — average success rate
   - `terrium_sweep_avg_execution_time_ms` — average time per sweep
   - `terrium_batches_total` — number of batches
   - `terrium_batch_avg_success_rate` — average batch success rate
   - `terrium_batch_avg_execution_time_ms` — average batch time

4. View in Grafana: http://localhost:3001

## Key Data Points Per Sweep/Batch

| Metric | Meaning |
|--------|---------|
| `totalSimulations` / `totalJobs` | How many simulations/jobs ran |
| `successfulSimulations` / `successfulJobs` | How many passed validation |
| `failedSimulations` / `failedJobs` | How many failed validation |
| `successRate` | Percentage of successful runs (0-100) |
| `totalTimeMs` | Sum of all execution times |
| `averageTimeMs` | Mean time per simulation/job |
| `minTimeMs` | Fastest simulation/job |
| `maxTimeMs` | Slowest simulation/job |

## Common Workflows

### Debug a Slow Sweep

```bash
# Find all sweeps
curl http://localhost:3000/api/metrics/sweeps

# Check the slowest one
curl http://localhost:3000/api/metrics/sweeps/sweep_XXX

# If avgTime > 1000ms, investigate parameters or model
```

### Compare Success Rates Across Models

```bash
# Group by query
curl http://localhost:3000/api/metrics/sweeps-by-query

# Each query shows its success rates
# Example: michaelis-menten: [sweep1: 95%, sweep2: 92%, ...]
# vs competitive-inhibition: [sweep1: 88%, ...]
```

### Monitor Batch Job Reliability

```bash
# Check batch success rate
curl http://localhost:3000/api/metrics/batches/batch_XXX

# If successRate < 90%, review failed jobs
curl http://localhost:3000/api/metrics/failed-queries
```

## Testing

```bash
# Run sweep/batch metrics tests
npm test -- src/storage/__tests__/sweep-batch-metrics.test.ts

# All tests pass: 19/19 ✓
```

## Important Notes

- **In-Memory:** Metrics are cleared on server restart. For persistence, use Prometheus scraping or CSV export.
- **Session-Scoped:** Each server instance has its own metrics cache.
- **No Breaking Changes:** Existing `/api/sweep` and `/api/batch` endpoints work unchanged.
- **Automatic:** Metrics are recorded automatically—no code changes needed on client side.

## Troubleshooting

**Q: I don't see any metrics**
A: Run a sweep/batch first. Endpoints return empty arrays until operations complete.

**Q: Metrics vanished after restart**
A: Expected—metrics are in-memory. Set up Prometheus for persistent monitoring.

**Q: Why is success rate 0%?**
A: All simulations failed validation. Check parameters or review errors in `/api/metrics/failed-queries`.

## Next Steps

- Set up Prometheus scraping for historical trends
- Configure Grafana alerts (success rate < 80%, avg time > 1s)
- Export metrics to CSV for reports
- Use metrics in decision logic (e.g., auto-retry if success rate drops)

See `SWEEP_BATCH_METRICS.md` for full documentation and advanced usage.
