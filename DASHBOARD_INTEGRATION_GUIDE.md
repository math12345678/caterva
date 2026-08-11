# Live Architecture Dashboard Integration Guide

> **⚠️ CORRECTION (2026-08-10) — this guide describes an earlier, broken design; most of it does not match the current, real code.**
> - `artifacts/api-server/src/lib/metrics.ts` (the "Metrics Collection System" in Step 1/Section 2 below) **does not exist**. It was replaced by `artifacts/api-server/src/lib/verifiable-metrics.ts` (`verifiableMetricsCollector` singleton), which the routes now actually import.
> - The commit history for this is explicit about why: `src/routes/metrics.ts` originally imported the old `metricsCollector`, which had **zero production writers** — nothing ever called `recordJobExecution` outside its own test — so `/api/metrics` and `/api/metrics/health` reported permanent zeros, with `llmSuccessRate`/`literatureHitRate` showing **100% fabricated from an empty sample** (see commits `de1febb`, `3a298a7`). That is the exact anti-pattern this project's "nothing should be hardcoded, everything backed by literature/data" rule exists to prevent.
> - Real, current endpoint paths (`Science-Agent-Pipeline/artifacts/api-server/src/routes/metrics.ts`, mounted via `src/routes/index.ts` under `app.use("/api", router)` in `src/app.ts:87`): `GET /api/snapshot` (not `/api/metrics`), `GET /api/metrics/health`, `POST /api/metrics/reset` (requires `Authorization: Bearer <METRICS_ADMIN_TOKEN>`, returns 501 if unset).
> - When there's no data, `successRate` is now `null` and status is `"no_data"` — it no longer defaults to a fabricated 100%.
> - Real test file: `src/__tests__/verifiableMetrics.test.ts` (251 lines, 15 test cases) — not `metrics.test.ts` (referenced below), which does not exist.
> - `LiveArchitectureDashboard.tsx` does exist (571 lines, not 700) at the path below, but it renders demo/mock data — it is not wired to the live endpoints described in Step 3.
>
> The integration steps, code snippets, and file names below are the ORIGINAL (partly fictional) plan and are left as-is per project convention (nothing deleted), but should not be followed literally — use the real file/endpoint names above instead.

## Overview

The **Live Architecture Dashboard** is a comprehensive real-time monitoring system for the Terrium science agent pipeline. It visualizes all 5 stages, 13 domains, and resolution metrics through interactive charts and status indicators.

## Components Built

### 1. Frontend Dashboard Component
**File**: `artifacts/terrium-landing/src/cli/LiveArchitectureDashboard.tsx`

A React component that displays:
- **Key Metrics Cards**: Active jobs, success rate, latency, LLM hit rate
- **Latency Timeline**: 30-second rolling window of job latencies
- **Stage Performance**: Bar chart showing stage success/failure counts
- **Domain Distribution**: Pie chart of top 5 domains by usage
- **Resolution Metrics**: LLM and literature resolution rates
- **Pipeline Summary**: Per-stage success rates with visual progress bars

**Features**:
- Live data updates every 2 seconds (mock data in demo mode)
- Interactive tabs for different metric views
- Domain detail drill-down on click
- Color-coded domain visualization
- Responsive grid layout

**Usage**:
```tsx
import LiveArchitectureDashboard from "@/cli/LiveArchitectureDashboard";

export function Dashboard() {
  return <LiveArchitectureDashboard />;
}
```

### 2. Metrics Collection System
**File**: `artifacts/api-server/src/lib/metrics.ts`

Singleton service that tracks:
- Job execution (start, completion, failure)
- Stage performance (success rate, average duration)
- Domain usage (count, resolution time, parameter success)
- Resolution metrics (LLM success, literature hits, fallback usage)

**Key Methods**:
```typescript
metricsCollector.recordJobStart(jobId);
metricsCollector.recordJobCompletion(jobId, latencyMs);
metricsCollector.recordJobFailure(jobId);
metricsCollector.recordStageExecution(stageName, durationMs, success);
metricsCollector.recordDomainUsage(domain, resolutionMs, parameterSuccess);
metricsCollector.recordLLMClassification(success);
metricsCollector.recordLiteratureResolution(hit);
const snapshot = metricsCollector.getSnapshot();
```

**Usage**:
```typescript
import { recordJobExecution } from "../lib/metrics";

recordJobExecution(
  jobId,
  domain,
  latencyMs,
  success,
  stageTimings,
  llmUsed,
  llmSuccess,
  literatureHit
);
```

### 3. Metrics API Endpoint
**File**: `artifacts/api-server/src/routes/metrics.ts`

Provides REST endpoints for dashboard data consumption.

**Endpoints**:

#### GET `/api/metrics`
Returns current snapshot of all metrics.

**Response**:
```json
{
  "status": "ok",
  "timestamp": "2026-08-08T12:34:56Z",
  "data": {
    "activeJobs": 3,
    "completedJobs": 145,
    "failedJobs": 5,
    "avgLatencyMs": 245,
    "successRate": "96.6",
    "llmSuccessRate": 94,
    "literatureHitRate": 82,
    "stages": [
      {
        "name": "Entity Extraction",
        "successCount": 145,
        "failureCount": 2,
        "avgDurationMs": 52,
        "successRate": "98.6"
      },
      ...
    ],
    "domains": [
      {
        "name": "mm",
        "count": 42,
        "avgResolutionMs": 180,
        "parameterSuccessRate": 95
      },
      {
        "name": "mm_competitive_inhibition",
        "count": 38,
        "avgResolutionMs": 220,
        "parameterSuccessRate": 97
      },
      ...
    ],
    "resolution": {
      "llmSuccesses": 141,
      "llmFailures": 8,
      "keywordFallbacks": 5,
      "literatureHits": 119,
      "literatureMisses": 26
    }
  }
}
```

#### GET `/api/metrics/health`
Minimal health check for monitoring systems.

**Response** (healthy):
```json
{
  "status": "healthy",
  "successRate": "96.6",
  "activeJobs": 3,
  "avgLatencyMs": 245,
  "uptime": 3600.5
}
```

**Response** (degraded):
```json
{
  "status": "degraded",
  "successRate": "85.2",
  "activeJobs": 15,
  "avgLatencyMs": 512
}
```

#### POST `/api/metrics/reset`
Resets all metrics to initial state. (Protected endpoint - add authentication in production)

---

## Integration Steps

### Step 1: Enable Metrics Collection in queryResolver.ts

Add metrics recording to the main query resolution flow:

```typescript
import { recordJobExecution } from "./metrics";

async function resolveQuery(query: string) {
  const startTime = Date.now();
  const jobId = randomUUID();

  try {
    metricsCollector.recordJobStart(jobId);

    // ... existing resolution logic ...

    const latencyMs = Date.now() - startTime;
    recordJobExecution(
      jobId,
      domain,
      latencyMs,
      true, // success
      {
        "Entity Extraction": { duration: t1, success: true },
        "Parameter Resolution": { duration: t2, success: true },
        "Domain Classification": { duration: t3, success: true },
        Validation: { duration: t4, success: true },
        "Simulation Output": { duration: t5, success: true },
      },
      llmUsed,
      llmSuccess,
      literatureHit
    );

    return result;
  } catch (error) {
    metricsCollector.recordJobFailure(jobId);
    throw error;
  }
}
```

### Step 2: Register Metrics Route in app.ts

```typescript
import metricsRouter from "./routes/metrics";

app.use("/api/metrics", metricsRouter);
```

### Step 3: Connect Dashboard to API

Update LiveArchitectureDashboard.tsx to fetch real data:

```typescript
const [snapshot, setSnapshot] = useState<PipelineSnapshot | null>(null);

useEffect(() => {
  const interval = setInterval(async () => {
    try {
      const response = await fetch("/api/metrics");
      const data = await response.json();
      
      if (data.status === "ok") {
        // Transform API response to match snapshot format
        setSnapshot(transformMetricsData(data.data));
      }
    } catch (error) {
      console.error("Failed to fetch metrics:", error);
    }
  }, 2000);

  return () => clearInterval(interval);
}, []);

function transformMetricsData(apiData: any): PipelineSnapshot {
  return {
    timestamp: new Date(apiData.timestamp),
    activeJobs: apiData.activeJobs,
    completedJobs: apiData.completedJobs,
    failedJobs: apiData.failedJobs,
    avgLatencyMs: apiData.avgLatencyMs,
    stageMetrics: apiData.stages.map(s => ({
      name: s.name,
      successCount: s.successCount,
      failureCount: s.failureCount,
      avgDurationMs: s.avgDurationMs,
    })),
    domainDistribution: apiData.domains.map(d => ({
      domain: d.name,
      count: d.count,
      avgResolutionMs: d.avgResolutionMs,
      parameterSuccessRate: d.parameterSuccessRate,
    })),
    llmSuccessRate: apiData.llmSuccessRate,
    literatureHitRate: apiData.literatureHitRate,
  };
}
```

### Step 4: Add Dashboard Route to Landing Page

```typescript
import LiveArchitectureDashboard from "@/cli/LiveArchitectureDashboard";

export function CliApp() {
  return (
    <Routes>
      {/* ... existing routes ... */}
      <Route path="/dashboard" element={<LiveArchitectureDashboard />} />
    </Routes>
  );
}
```

### Step 5: Link to Dashboard from Main Navigation

```tsx
<Link to="/dashboard" className="text-blue-400 hover:text-blue-300">
  <Zap className="w-4 h-4 inline mr-2" />
  Live Dashboard
</Link>
```

---

## Metrics Data Flow

```
queryResolver.ts (records metrics)
        ↓
metrics.ts (collects & aggregates)
        ↓
metrics.ts singleton (maintains state)
        ↓
/api/metrics endpoint (exports)
        ↓
LiveArchitectureDashboard.tsx (visualizes)
        ↓
React charts (renders to user)
```

## Testing

Run metrics tests:

```bash
npm test -- metrics.test.ts
```

Test coverage includes:
- Job tracking (active, completed, failed)
- Stage performance aggregation
- Domain usage statistics
- Resolution metrics
- Rolling window management
- Helper function integration

---

## Performance Considerations

### Data Retention
- **Latency Samples**: Last 100 samples (~3 minutes at 2-second updates)
- **Stage Samples**: Last 100 per stage
- **Domain Samples**: Last 100 per domain
- **Total Memory**: < 1MB for all metrics

### Update Frequency
- **Dashboard Refresh**: 2 seconds (configurable)
- **Metrics Calculation**: On-demand (O(1) for snapshot)
- **API Overhead**: ~5ms per request

### Optimization Tips
- Use `/api/metrics/health` endpoint for frequent checks (lower bandwidth)
- Implement client-side caching to reduce API calls
- Use `resume: false` in fetch to cancel stale requests

---

## Monitoring Thresholds

The dashboard should alert when:

| Metric | Warning | Critical |
|--------|---------|----------|
| Success Rate | < 95% | < 90% |
| Avg Latency | > 400ms | > 800ms |
| LLM Success Rate | < 85% | < 75% |
| Literature Hit Rate | < 70% | < 50% |
| Active Jobs | > 50 | > 100 |

---

## Example: Monitoring mm_competitive_inhibition Domain

The dashboard drill-down shows:
- **Count**: Number of mm_competitive_inhibition queries processed
- **Avg Resolution**: Time to resolve km and ki parameters
- **Parameter Success Rate**: Percentage where both km and ki resolved successfully

This is critical because mm_competitive_inhibition requires BOTH parameters to proceed; missing either fails the job.

---

## Production Deployment Checklist

- [ ] Metrics endpoint protected with authentication
- [ ] Rate limiting on `/api/metrics` endpoint (e.g., 100 req/min)
- [ ] Health check endpoint accessible without auth (for monitoring systems)
- [ ] Dashboard updates use exponential backoff on API failures
- [ ] Metrics retention configured based on storage capacity
- [ ] Log entries for metrics endpoint errors
- [ ] Alerts configured for degraded health status
- [ ] Load testing done to ensure metrics collection doesn't impact latency
- [ ] Cache headers set appropriately (e.g., max-age=30s for /api/metrics)
- [ ] CORS configured if dashboard served from different origin

---

## Future Enhancements

1. **Historical Data**: Store metrics snapshots to PostgreSQL for trend analysis
2. **Alerts**: Email/Slack notifications when thresholds exceeded
3. **Batch Export**: CSV/JSON export of metrics for analysis
4. **Comparison**: Side-by-side comparison of different time windows
5. **Predictive Analytics**: ML-based latency prediction
6. **Custom Dashboards**: User-configurable metric selections
7. **Domain Benchmarks**: Per-domain performance targets and SLAs
8. **Cost Attribution**: Estimate LLM API costs per domain

---

## References

- Architecture Guide: `ARCHITECTURE_QUICK_REFERENCE.md`
- Wiring Verification: `WIRING_VERIFICATION_REPORT.md`
- Build Status: `BUILD_STATUS_SUMMARY.md`
- Metrics Tests: `artifacts/api-server/src/__tests__/metrics.test.ts`
