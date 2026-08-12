# 📊 Terrium Export & Analysis Guide

**Export results, compare jobs, and analyze sensitivity with 7 new endpoints**

---

## Quick Overview

### What You Can Export
- ✅ Full job history (all completed simulations)
- ✅ Parameter sweep results (all sweep points)
- ✅ Batch job results (all batch jobs with summary)
- ✅ Model comparison results (all 4 models ranked)
- ✅ System statistics (aggregate metrics)

### What You Can Analyze
- ✅ Compare 2+ job results side-by-side
- ✅ Identify differences between kinetic models
- ✅ Analyze parameter sensitivity from sweeps
- ✅ Generate automated insights
- ✅ Export comparisons as CSV

---

## Export Endpoints

### 1. Export All Job History

**Endpoint:** `GET /api/export/jobs/csv`

Downloads a CSV file with all completed jobs and metadata.

```bash
curl http://localhost:3000/api/export/jobs/csv -o jobs.csv
```

**CSV Columns:**
- jobId
- query (kinetic model used)
- status
- startTime (ISO 8601)
- endTime (ISO 8601)
- durationMs
- finalValue (substrate concentration at end)
- confidence (0-1)
- validated (literature match: yes/no)
- parameters (JSON)

**Use Cases:**
- Audit trail of all simulations
- Statistical analysis across conditions
- Track model usage over time
- Quality assessment via confidence scores

---

### 2. Export Sweep Results

**Endpoint:** `GET /api/export/sweep/:sweepId/csv`

Downloads sweep results as CSV (one row per sweep point).

```bash
# First, run a sweep
SWEEP=$(curl -X POST http://localhost:3000/api/sweep \
  -d '{"query":"michaelis-menten","baseParameters":{"vmax":12.8,"s0":10},"sweepParameters":[{"name":"km","spec":"1:10:0.5"}]}' \
  | jq -r '.sweepId')

# Wait for completion (or poll)
sleep 2

# Export as CSV
curl http://localhost:3000/api/export/sweep/$SWEEP/csv -o sweep.csv
```

**CSV Includes:**
- Parameter set for each point
- Final value at that point
- Confidence score
- Validation status

**CSV Tail (Summary Statistics):**
```
# Analysis
optimalParameters,{"km":5.5}
meanFinalValue,2.34
minFinalValue,0.45
maxFinalValue,9.87
stdDeviation,2.15
```

**Use Cases:**
- Plot parameter sensitivity curves in Excel/Python
- Find optimal parameters numerically
- Identify inflection points or thresholds
- Document parameter exploration

---

### 3. Export Batch Results

**Endpoint:** `GET /api/export/batch/:batchId/csv`

Downloads batch results as CSV (one row per job).

```bash
curl http://localhost:3000/api/export/batch/$BATCH_ID/csv -o batch.csv
```

**CSV Columns:**
- jobIndex (1, 2, 3, ...)
- finalValue
- confidence
- validated
- executionTimeMs
- parameters (JSON)

**CSV Tail (Summary):**
```
# Summary
totalJobs,5
successfulJobs,5
failedJobs,0
averageExecutionTimeMs,75
```

**Use Cases:**
- Compare enzyme batches quantitatively
- Assess reproducibility across replicates
- Identify outliers or failed runs
- Calculate batch statistics

---

### 4. Export Model Comparison

**Endpoint:** `GET /api/export/comparison/:compareId/csv`

Compares all 4 kinetic models for the same substrate.

```bash
# Run comparison
COMPARE=$(curl -X POST http://localhost:3000/api/compare \
  -d '{"parameters":{"km":5.2,"vmax":12.8,"s0":10}}' \
  | jq -r '.compareId')

sleep 2

# Export
curl http://localhost:3000/api/export/comparison/$COMPARE/csv -o models.csv
```

**CSV Output:**
```
model,finalValue,confidence,validated,executionTimeMs,rank
michaelis-menten,2.34,0.95,yes,75,1
competitive-inhibition,2.12,0.88,no,82,2
non-competitive-inhibition,2.45,0.91,no,78,3
product-inhibition,2.01,0.85,no,79,4

# Analysis
bestModel,michaelis-menten
meanFinalValue,2.23
modelVariability,0.18
```

**Use Cases:**
- Determine which model fits experimental data
- Assess model sensitivity to parameters
- Publish model comparison table
- Choose best model for downstream work

---

### 5. Export Statistics

**Endpoint:** `GET /api/export/stats/csv`

Exports aggregate system statistics.

```bash
curl http://localhost:3000/api/export/stats/csv -o stats.csv
```

**CSV Output:**
```
Metric,Value
totalJobs,42
successfulJobs,40
failedJobs,2
averageExecutionTimeMs,78

# Query Distribution
michaelis-menten,25
competitive-inhibition,10
non-competitive-inhibition,5
product-inhibition,2
```

**Use Cases:**
- Track system usage over time
- Report simulation statistics
- Identify most-used kinetic models
- Monitor success rates

---

## Analysis Endpoints

### 6. Compare Multiple Job Results

**Endpoint:** `POST /api/compare/jobs`

Compare 2 or more completed jobs to identify differences.

```bash
curl -X POST http://localhost:3000/api/compare/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "jobIds": ["job_1726074000_abc", "job_1726074015_def", "job_1726074030_ghi"]
  }'
```

**Response (2 Jobs):**
```json
{
  "job1Id": "job_1726074000_abc",
  "job2Id": "job_1726074015_def",
  "job1Query": "michaelis-menten",
  "job2Query": "competitive-inhibition",
  "job1FinalValue": 2.34,
  "job2FinalValue": 2.12,
  "metrics": {
    "difference": 0.22,
    "percentDifference": 9.87,
    "ratio": 1.10,
    "isDifferenceSignificant": false
  },
  "similarity": "very_similar",
  "insights": [
    "Models differ: michaelis-menten vs competitive-inhibition",
    "9.87% difference in final values",
    "Confidence difference: 0.950 vs 0.880"
  ]
}
```

**Response (3+ Jobs):**
```json
{
  "jobIds": ["job_1", "job_2", "job_3"],
  "queries": ["michaelis-menten", "michaelis-menten", "competitive-inhibition"],
  "finalValues": [2.34, 2.41, 2.12],
  "mean": 2.29,
  "median": 2.34,
  "stdDev": 0.15,
  "min": { "jobId": "job_3", "value": 2.12 },
  "max": { "jobId": "job_2", "value": 2.41 },
  "range": 0.29,
  "coefficientOfVariation": 6.55,
  "ranking": [
    { "jobId": "job_2", "query": "michaelis-menten", "value": 2.41, "rank": 1 },
    { "jobId": "job_1", "query": "michaelis-menten", "value": 2.34, "rank": 2 },
    { "jobId": "job_3", "query": "competitive-inhibition", "value": 2.12, "rank": 3 }
  ],
  "insights": [
    "3 jobs compared",
    "Results vary by ±0.150 (CV: 6.55%)",
    "2 different kinetic models used",
    "Range: 2.120 to 2.410"
  ]
}
```

**Use Cases:**
- Compare two kinetic models directly
- Assess variability across enzyme batches
- Identify best-performing condition
- Quantify differences between approaches

---

### 7. Analyze Sweep Sensitivity

**Endpoint:** `GET /api/analyze/sweep/:sweepId`

Analyzes parameter sensitivity from a completed sweep.

```bash
curl http://localhost:3000/api/analyze/sweep/$SWEEP_ID
```

**Response:**
```json
{
  "sensitivity": 78.5,
  "inflectionPoints": [8, 12, 16],
  "mean": 2.98,
  "min": 0.45,
  "max": 9.87,
  "range": 9.42,
  "stdDev": 2.75,
  "totalPoints": 20,
  "optimalParameterIndex": 15
}
```

**Metrics Explained:**
- **sensitivity** (78.5%) — How much response varies with parameter
  - <10% = Low sensitivity
  - 10-50% = Moderate sensitivity
  - >50% = High sensitivity

- **inflectionPoints** [8,12,16] — Indices where response changes significantly
  - Indicates regions of rapid change
  - Useful for focusing future sweeps

- **optimalParameterIndex** (15) — Index of best result (0-19)
  - Combine with sweep parameters to find optimal value

**Use Cases:**
- Quantify parameter importance
- Identify critical regions for optimization
- Plan next sweep (zoom into inflection points)
- Assess parameter robustness

---

## Real-World Workflows

### Workflow 1: Optimize Km for Maximum Conversion

```bash
# 1. Run sweep from 0.5 to 10 mM
SWEEP=$(curl -X POST http://localhost:3000/api/sweep \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"vmax": 12.8, "s0": 10},
    "sweepParameters": [{"name": "km", "spec": "0.5:10:0.5"}]
  }' | jq -r '.sweepId')

# 2. Poll until complete
while true; do
  STATUS=$(curl http://localhost:3000/api/sweeps/$SWEEP | jq -r '.status')
  [ "$STATUS" = "complete" ] && break
  sleep 1
done

# 3. Export results
curl http://localhost:3000/api/export/sweep/$SWEEP/csv > km-optimization.csv

# 4. Analyze sensitivity
curl http://localhost:3000/api/analyze/sweep/$SWEEP | jq '.'

# 5. Plot in Excel/Python to visualize
#    Find knee point and optimal Km
```

### Workflow 2: Compare Enzyme Batches

```bash
# Run batch with different enzyme Km/Vmax values
BATCH=$(curl -X POST http://localhost:3000/api/batch \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"s0": 10},
    "parameterSets": [
      {"km": 2.1, "vmax": 10.5},
      {"km": 2.3, "vmax": 10.8},
      {"km": 2.0, "vmax": 11.2},
      {"km": 2.4, "vmax": 10.3},
      {"km": 2.2, "vmax": 11.0}
    ],
    "concurrency": 3
  }' | jq -r '.batchId')

# Wait & export
sleep 3
curl http://localhost:3000/api/export/batch/$BATCH/csv > batches.csv

# Compare all batches
curl -X POST http://localhost:3000/api/compare/jobs \
  -d '{"jobIds": ["job_1", "job_2", "job_3", "job_4", "job_5"]}' | jq '.'
```

### Workflow 3: Model Selection for Publication

```bash
# Run all 4 models on same substrate
COMPARE=$(curl -X POST http://localhost:3000/api/compare \
  -d '{"parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}}' \
  | jq -r '.compareId')

sleep 3

# Export comparison table
curl http://localhost:3000/api/export/comparison/$COMPARE/csv > models.csv

# Look at detailed analysis
curl http://localhost:3000/api/compare/jobs \
  -d '{"jobIds": ["compare_id_1", "compare_id_2", "compare_id_3", "compare_id_4"]}' \
  | jq '.ranking'

# Use top-ranked model for further work
```

---

## Data Format Details

### CSV Quoting Rules
- Fields with commas are quoted: `"km,vmax"`
- Fields with quotes have internal quotes doubled: `"say ""hello"""`
- Numbers and booleans are unquoted: `5.2` or `true`

### Parameter JSON Serialization
Parameters in CSV are JSON-encoded for portability:
```
{"km":5.2,"vmax":12.8,"s0":10}
```

Use a CSV parser with JSON support, or:
```bash
# Extract parameters from CSV in Python
import csv, json
with open('sweep.csv') as f:
  for row in csv.DictReader(f):
    params = json.loads(row['parameterDetails'])
    value = float(row['finalValue'])
```

### Timestamps
All timestamps are ISO 8601 format:
```
2026-08-11T15:30:45.123Z
```

Use standard parsing:
```bash
# Python
from datetime import datetime
dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
```

---

## Combining Exports with Python

```python
import requests
import pandas as pd
from datetime import datetime

# Get all jobs
jobs_csv = requests.get('http://localhost:3000/api/export/jobs/csv').text
df_jobs = pd.read_csv(pd.StringIO(jobs_csv))

# Filter to last 24 hours
df_jobs['startTime'] = pd.to_datetime(df_jobs['startTime'])
yesterday = datetime.now() - pd.Timedelta(days=1)
recent = df_jobs[df_jobs['startTime'] > yesterday]

# Get stats
stats_csv = requests.get('http://localhost:3000/api/export/stats/csv').text
print(stats_csv)

# Analyze
print(f"Success rate: {recent['status'].value_counts()}")
print(f"Mean duration: {recent['durationMs'].mean():.1f}ms")
print(f"Models used: {recent['query'].value_counts()}")
```

---

## Integration with Jupyter

```python
# Fetch and visualize in Jupyter
import requests
import pandas as pd
import matplotlib.pyplot as plt

# Get sweep results
sweep_id = "sweep_1726074000_abc"
csv_url = f"http://localhost:3000/api/export/sweep/{sweep_id}/csv"
df = pd.read_csv(csv_url)

# Plot results
plt.plot(range(len(df)), df['finalValue'])
plt.xlabel('Sweep Point')
plt.ylabel('Final Value')
plt.title(f'Sweep {sweep_id}')
plt.grid()
plt.show()

# Analyze sensitivity
analysis = requests.get(f"http://localhost:3000/api/analyze/sweep/{sweep_id}").json()
print(f"Sensitivity: {analysis['sensitivity']:.1f}%")
print(f"Optimal at index: {analysis['optimalParameterIndex']}")
```

---

## Summary

| Task | Endpoint | Method |
|------|----------|--------|
| Export all jobs | `/api/export/jobs/csv` | GET |
| Export sweep | `/api/export/sweep/:id/csv` | GET |
| Export batch | `/api/export/batch/:id/csv` | GET |
| Export comparison | `/api/export/comparison/:id/csv` | GET |
| Export stats | `/api/export/stats/csv` | GET |
| Compare jobs | `/api/compare/jobs` | POST |
| Analyze sweep | `/api/analyze/sweep/:id` | GET |

All endpoints return data suitable for further analysis in Excel, Python, R, or any data tool.

🚀 **Happy analyzing!**
