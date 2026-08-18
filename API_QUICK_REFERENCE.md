# API Quick Reference

> **⚠️ CORRECTION (2026-08-12):**
> - The "Query jobs with filters" examples (`curl ".../api/jobs/query?..."`) and the `GET /api/jobs/history` endpoint listed above do not work. In `src/web/server.ts`, `GET /api/jobs/:jobId` (`pathname.match(/^\/api\/jobs\/[a-z0-9_]+$/i)`, line 235) is registered before `/api/jobs/history` (line 251) and `/api/jobs/query` (line 259), and its regex matches the literal strings `history` and `query` as valid job IDs. Reproduced live: both routes currently return `404 {"error":"Job not found"}` instead of their documented behavior. This is a routing bug in `server.ts` (out of scope for this audit to fix), not a wording issue.
> - This doc's endpoint list also omits `GET /api/jobs/{jobId}` (get a single job's status/result) entirely — it is a real, working route in `server.ts` that should be documented alongside `/api/jobs/history` and `/api/jobs/query`.
> - "Required Parameters (by model)" claims `ki`/`i0` are required for `competitive-inhibition`/`non-competitive-inhibition` and `ki`/`p0` for `product-inhibition`. Reading `src/validation/request-validator.ts` (`validateSimulationRequest()`, line 54) shows the actual required-parameter check is `['km', 'vmax', 's0']` for every model — `ki`/`i0`/`p0` are never validated as required, regardless of which `query` model is chosen (this matches `openapi.yaml`'s `/api/simulate` schema, which correctly lists only `km`/`vmax`/`s0` as `required`).

## Endpoints at a Glance

### Health & Status
```
GET  /api/health          System status and uptime
GET  /api/stats           Aggregate statistics
```

### Simulations
```
POST /api/simulate        Run single simulation
```

### Sweeps (Parameter ranges)
```
POST /api/sweep           Sweep parameters across range
GET  /api/sweeps/{id}     Get sweep results
```

### Batch Processing
```
POST /api/batch           Run multiple parameter sets
GET  /api/batches/{id}    Get batch results
```

### Comparison & Analysis
```
POST /api/compare         Compare parameter sets
POST /api/compare/jobs    Compare completed jobs
GET  /api/analyze/sweep/{id}  Sensitivity analysis
```

### Queries
```
GET  /api/jobs/history    Recent 50 jobs
GET  /api/jobs/query      Advanced filtering
```

### Export
```
GET  /api/export/jobs/csv          Jobs to CSV
GET  /api/export/stats/csv         Statistics to CSV
GET  /api/export/sweeps/{id}/csv   Sweep to CSV
GET  /api/export/batches/{id}/csv  Batch to CSV
GET  /api/export/comparisons/{id}/csv  Comparison to CSV
```

### Documentation
```
GET  /api/docs            Swagger UI (interactive)
GET  /api/docs/redoc      ReDoc (alternative UI)
GET  /api/openapi.json    Raw OpenAPI 3.0 spec
```

---

## Common Requests

### Run a simulation
```bash
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": {
      "km": 5.2,
      "vmax": 12.8,
      "s0": 10.0
    }
  }'
```

### Parameter sweep
```bash
curl -X POST http://localhost:3000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"vmax": 12.8, "s0": 10},
    "sweepParameters": [
      {"name": "km", "spec": "1:10:0.5"}
    ]
  }'
```

### Batch processing
```bash
curl -X POST http://localhost:3000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"s0": 10},
    "parameterSets": [
      {"km": 1, "vmax": 10},
      {"km": 2, "vmax": 12},
      {"km": 3, "vmax": 14}
    ],
    "concurrency": 3
  }'
```

### Compare jobs
```bash
curl -X POST http://localhost:3000/api/compare/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "jobIds": ["job_1722973200000_abc", "job_1722973210000_def"]
  }'
```

### Query jobs with filters
```bash
# Completed jobs with high confidence
curl "http://localhost:3000/api/jobs/query?status=complete&minConfidence=0.9"

# Failed jobs
curl "http://localhost:3000/api/jobs/query?status=error"

# Specific model
curl "http://localhost:3000/api/jobs/query?model=michaelis-menten"

# Date range
curl "http://localhost:3000/api/jobs/query?startTime=2026-08-01&endTime=2026-08-15"

# Sorting and pagination
curl "http://localhost:3000/api/jobs/query?sortBy=confidence&sortOrder=desc&limit=10&offset=0"
```

### Export data
```bash
# Export all jobs to CSV
curl -s http://localhost:3000/api/export/jobs/csv > jobs.csv

# Export statistics
curl -s http://localhost:3000/api/export/stats/csv > stats.csv
```

---

## Response Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Validation failed (bad request) |
| 404 | Resource not found |
| 500 | Server error |

All error responses include detailed validation messages.

---

## Supported Models

- `michaelis-menten` — Standard MM kinetics
- `competitive-inhibition` — With competitive inhibitor
- `non-competitive-inhibition` — With non-competitive inhibitor
- `product-inhibition` — With product inhibition

---

## Required Parameters (by model)

### michaelis-menten
- `km` — Michaelis constant
- `vmax` — Maximum velocity
- `s0` — Initial substrate concentration

### competitive-inhibition
- `km` — Michaelis constant
- `vmax` — Maximum velocity
- `s0` — Initial substrate concentration
- `ki` — Inhibitor constant
- `i0` — Initial inhibitor concentration

### non-competitive-inhibition
- `km` — Michaelis constant
- `vmax` — Maximum velocity
- `s0` — Initial substrate concentration
- `ki` — Inhibitor constant
- `i0` — Initial inhibitor concentration

### product-inhibition
- `km` — Michaelis constant
- `vmax` — Maximum velocity
- `s0` — Initial substrate concentration
- `ki` — Product inhibition constant
- `p0` — Initial product concentration

---

## Clients & SDKs

### Use generated clients

```bash
# Generate TypeScript client
npm run generate:client:ts

# Generate Python client
npm run generate:client:python

# Generate Go client
npm run generate:client:go

# Generate Rust client
npm run generate:client:rust
```

### TypeScript usage
```typescript
import { DefaultApi } from './generated-client';

const api = new DefaultApi({ basePath: 'http://localhost:3000' });
const job = await api.simulate({
  query: 'michaelis-menten',
  parameters: { km: 5.2, vmax: 12.8, s0: 10 }
});
```

### Python usage
```python
from openapi_client import ApiClient, DefaultApi

api = DefaultApi(ApiClient())
job = api.simulate({
    'query': 'michaelis-menten',
    'parameters': {'km': 5.2, 'vmax': 12.8, 's0': 10}
})
```

---

## Documentation

| Resource | Link |
|----------|------|
| Interactive UI | http://localhost:3000/api/docs |
| Alternative UI | http://localhost:3000/api/docs/redoc |
| Raw Spec | http://localhost:3000/api/openapi.json |
| Full Guide | `./OPENAPI_GUIDE.md` |
| Integration Guide | `./QUICK_START_DEPLOYMENT.md` |

---

## Authentication (Future)

Currently: No authentication required

Future support for:
- API keys
- OAuth 2.0
- JWT tokens

See `openapi.yaml` for spec-level auth definitions.

---

## Rate Limiting (Future)

Currently: No rate limiting

Future limits:
- Public endpoints: 100 req/min per IP
- Authenticated: 1000 req/min per user

---

## Quick Start

### 1. Start the server
```bash
npm run web:start
```

### 2. Visit the docs
```bash
open http://localhost:3000/api/docs
```

### 3. Try an endpoint
Click "Try it out" on any endpoint in Swagger UI

### 4. Generate a client (optional)
```bash
npm run generate:client:ts
```

---

## Support

- **Issue reports** → GitHub
- **Questions** → Documentation at `/api/docs`
- **Integration help** → See `OPENAPI_GUIDE.md`

---

**Last updated:** 2026-08-12  
**API Version:** 1.0.0  
**Specification:** OpenAPI 3.0.0
