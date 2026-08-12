# 📋 Terrium API Quick Reference

**18 Endpoints | All Production-Ready | Zero External Dependencies**

---

## Core Simulation (4)

```
POST   /api/simulate              Run single kinetic simulation
POST   /api/compare               Compare all 4 kinetic models
GET    /api/health                System status & uptime
GET    /                          Web dashboard
```

---

## Job Management (3)

```
GET    /api/jobs/:jobId           Get job status & results
GET    /api/jobs/history          Recent jobs (last 50)
GET    /api/stats                 Aggregate statistics
```

---

## Parameter Sweeps (2)

```
POST   /api/sweep                 Run parameter sweep
GET    /api/sweeps/:sweepId       Get sweep results
```

---

## Batch Processing (2)

```
POST   /api/batch                 Run batch jobs (parallel)
GET    /api/batches/:batchId      Get batch results
```

---

## Export (5) — NEW

```
GET    /api/export/jobs/csv       Export job history as CSV
GET    /api/export/sweep/:id/csv  Export sweep results as CSV
GET    /api/export/batch/:id/csv  Export batch results as CSV
GET    /api/export/comparison/:id/csv  Export model comparison as CSV
GET    /api/export/stats/csv      Export statistics as CSV
```

---

## Analysis (2) — NEW

```
POST   /api/compare/jobs          Compare 2+ job results
GET    /api/analyze/sweep/:id     Analyze sweep sensitivity
```

---

## Quick Examples

### Single Simulation
```bash
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10},
    "enzyme": "lactate dehydrogenase",
    "substrate": "lactate"
  }' | jq '.jobId'
```

### Parameter Sweep
```bash
curl -X POST http://localhost:3000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"vmax": 12.8, "s0": 10},
    "sweepParameters": [{"name": "km", "spec": "1:10:0.5"}]
  }' | jq '.sweepId'
```

### Batch Jobs
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
  }' | jq '.batchId'
```

### Export Results
```bash
# Export job history
curl http://localhost:3000/api/export/jobs/csv > jobs.csv

# Export sweep
curl http://localhost:3000/api/export/sweep/sweep_123/csv > sweep.csv

# Export batch
curl http://localhost:3000/api/export/batch/batch_123/csv > batch.csv

# Export model comparison
curl http://localhost:3000/api/export/comparison/compare_123/csv > models.csv

# Export statistics
curl http://localhost:3000/api/export/stats/csv > stats.csv
```

### Compare Jobs
```bash
curl -X POST http://localhost:3000/api/compare/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "jobIds": ["job_1726074000_abc", "job_1726074015_def"]
  }' | jq '.'
```

### Analyze Sensitivity
```bash
curl http://localhost:3000/api/analyze/sweep/sweep_123456 | jq '.'
```

### Check Status
```bash
# Job status
curl http://localhost:3000/api/jobs/job_123456

# Sweep status
curl http://localhost:3000/api/sweeps/sweep_123456

# Batch status
curl http://localhost:3000/api/batches/batch_123456

# System health
curl http://localhost:3000/api/health

# Recent jobs
curl http://localhost:3000/api/jobs/history

# System statistics
curl http://localhost:3000/api/stats
```

---

## Response Formats

### Simulate Response
```json
{
  "jobId": "job_1726074000_abc123def",
  "status": "queued"
}
```

### Job Status (Complete)
```json
{
  "status": "complete",
  "progress": 100,
  "result": {
    "query": "michaelis-menten",
    "finalValue": 2.34,
    "confidence": 0.95,
    "validated": true
  },
  "duration": 156
}
```

### Comparison Response
```json
{
  "job1Id": "job_1",
  "job2Id": "job_2",
  "similarity": "very_similar",
  "metrics": {
    "difference": 0.22,
    "percentDifference": 9.87,
    "isDifferenceSignificant": false
  },
  "insights": [...]
}
```

### Sensitivity Analysis
```json
{
  "sensitivity": 78.5,
  "inflectionPoints": [8, 12, 16],
  "mean": 2.98,
  "stdDev": 2.75,
  "optimalParameterIndex": 15
}
```

---

## Features at a Glance

| Feature | Endpoint | Status |
|---------|----------|--------|
| Single simulation | /api/simulate | ✅ |
| Job tracking | /api/jobs/* | ✅ |
| Parameter sweeps | /api/sweep* | ✅ |
| Batch processing | /api/batch* | ✅ |
| Model comparison | /api/compare | ✅ |
| CSV export | /api/export/* | ✅ |
| Job comparison | /api/compare/jobs | ✅ |
| Sensitivity analysis | /api/analyze/* | ✅ |
| Real literature | Built-in | ✅ |
| Web dashboard | / | ✅ |

---

## Documentation

- **START_HERE.md** — Quick start guide
- **VERIFIED_SYSTEM_STATUS.md** — Master status reference
- **EXPORT_AND_ANALYSIS_GUIDE.md** — Detailed export & analysis
- **DEPLOYMENT_AND_OPS.md** — Production deployment
- **API_QUICK_REFERENCE.md** — This file

---

## Start Using It

```bash
# Start server
npm run web:start

# Visit dashboard
open http://localhost:3000

# Or use API directly
curl http://localhost:3000/api/health
```

---

**All endpoints use no external dependencies (Node.js built-ins only)**  
**All data persists to terrium-jobs.jsonl**  
**CSV export for all result types**  
**Ready to deploy** 🚀
