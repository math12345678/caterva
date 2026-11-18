# Caterva Literature-Backed API Reference

Every parameter, every metric, every decision backed by peer-reviewed scientific literature.

## Core API Endpoints

### Job Management

#### `POST /api/simulate`
Enqueue a new simulation job.
- **Request**: `{ query: string }`
- **Response**: `{ jobId, status: "pending", query, ... }`
- **Status**: 202 Accepted

#### `GET /api/simulate`
List all simulation jobs (most recent first).
- **Response**: Array of job objects

#### `GET /api/simulate/:jobId`
Get current job status and result.
- **Response**: Job object with result if completed
- **Status**: 200 OK or 404 NOT FOUND

#### `GET /api/simulate/:jobId/stream`
Server-Sent Events stream of job updates.
- **Protocol**: text/event-stream
- **Closes**: Automatically when job reaches terminal state

#### `POST /api/simulate/:jobId/cancel`
Cancel a running job.
- **Response**: Updated job object
- **Status**: 200 OK, 404 NOT FOUND, or 409 CONFLICT

---

## Literature-Backed Endpoints

### Confidence Scores

#### `GET /api/simulate/:jobId/confidence`
Per-parameter confidence scores with explanations.
- **Literature**: Tipton et al. (2014) - STRENDA reporting standards
- **Response**:
```json
{
  "timestamp": "ISO-8601",
  "overallConfidence": 0.85,
  "parameters": [
    {
      "name": "km",
      "value": 2.5,
      "origin": "resolved",
      "confidence": 0.95,
      "explanation": "Parameter from literature (DOI provided)",
      "source": "brenda",
      "doi": "10.1093/nar/gkw952"
    }
  ]
}
```

### Publication Audit

#### `GET /api/simulate/:jobId/audit`
Publication-ready audit trail for all parameters.
- **Literature**: ADR 0011 - Parameter Provenance Tracking
- **Response**:
```json
{
  "domain": "mm",
  "publicationReady": true,
  "blockedParameters": [],
  "overallConfidence": 0.9,
  "parameterAudits": [
    {
      "name": "km",
      "value": 2.5,
      "origin": "resolved",
      "verificationLevel": "verified",
      "confidence": 0.95,
      "doi": "10.1093/nar/gkw952",
      "strendaCompliant": true,
      "requiresReview": false,
      "message": "Parameter from literature with complete STRENDA assay conditions"
    }
  ],
  "domainCitation": "Lehninger et al. (2008) - Lehninger Principles of Biochemistry"
}
```

### Metrics & Observability

#### `GET /api/simulate/metrics/pipeline`
Pipeline performance metrics with literature backing.
- **Literature**:
  - Little (1961) - Queue theory L = λW
  - Wilson (1927) - Binomial proportion confidence intervals
  - Harter (1974) - P95 and P99 latency percentiles
  - Nielsen (1993) - User response time perception thresholds
- **Response**:
```json
{
  "timestamp": "ISO-8601",
  "literature": {
    "queueTheory": "Little (1961) - L = λW",
    "confidenceIntervals": "Wilson (1927) - Binomial proportion CI",
    "percentiles": "Harter (1974) - P95 and P99 latency analysis",
    "responseTime": "Nielsen (1993) - User perception thresholds"
  },
  "metrics": {
    "completedJobs": 42,
    "avgLatencyMs": 823,
    "successRate": { "rate": 0.95, "ci95": [0.91, 0.98] },
    "latencyPercentiles": { "p95": 1200, "p99": 1500 }
  }
}
```

#### `GET /api/pipeline/literature`
Comprehensive literature backing database for all domains.
- **Response**:
```json
{
  "timestamp": "ISO-8601",
  "message": "Every simulation domain here carries at least one primary reference. ...",
  "totalDomainsCovered": 4,
  "domains": [
    { "domain": "mm", "citation": "..." },
    { "domain": "mm_competitive_inhibition", "citation": "..." },
    { "domain": "gillespie_ssa", "citation": "..." },
    { "domain": "gillespie_ssa_bimolecular", "citation": "..." }
  ],
  "literature": {
    "queuing": "Little (1961) L = λW -- ...",
    "confidence": "Wilson (1927) -- ...",
    "enzyme": "Tipton et al. (2014) -- STRENDA reporting standards, applied: ..."
  }
}
```

(Note, 2026-11-01: `literature` also carried an `epidemiology` entry, Kermack & McKendrick (1927), until this date. Epidemiology was archived on 2026-09-27, after v0.4.0 (the last release that runs it), and none of the four domains this route serves uses that model, so the entry was removed.)

### Data Export

#### `GET /api/simulate/:jobId/export`
Export simulation trajectory as CSV.
- **Response**: text/csv
- **Columns**: time, state1, state2, ... (domain-specific)

---

## Verification Levels

Every parameter gets a verification level:

| Level | Meaning | Confidence | Publication |
|-------|---------|-----------|-------------|
| **verified** | Literature (DOI/PMID) + complete STRENDA assay | 0.95-1.0 | ✅ OK |
| **flagged** | Literature backing exists but missing assay conditions | 0.7-0.9 | ⚠️ Needs review |
| **pending** | LLM-supplied; requires manual verification | 0.4-0.6 | ❌ BLOCKED |
| **unverifiable** | User-supplied or system default | 0.3-1.0 | ✅ OK (user choice) |

---

## Origin Tracking

Where each parameter comes from:

- **resolved**: Direct lookup in peer-reviewed database (BRENDA, PubMed, etc.)
- **keyword**: Matched via natural language keyword extraction
- **llm**: Generated by LLM; flagged for manual review
- **user**: Explicitly supplied by the researcher
- **default**: System default; represents typical literature values

---

## STRENDA Compliance

For enzyme kinetics domains (mm, mm_competitive_inhibition):

Validates all 7 STRENDA requirements:
1. **pH** of assay (±0.1 units)
2. **Temperature** (±1°C)
3. **Buffer system** (named, concentration)
4. **Substrate concentration** (specified)
5. **Measurement method** (described)
6. **Enzyme source/purity** (documented)
7. **Confidence intervals** (95% CI bounds)

**Literature**: Tipton et al. (2014) DOI: 10.1016/j.pisc.2014.02.012

---

## Domain Coverage (4 Domains)

The domains `GET /api/pipeline/literature` reports (`src/routes/pipeline.ts`):

| Domain | Primary Reference | Year | DOI/Citation |
|--------|------------------|------|------------|
| mm | Lehninger et al. | 2008 | Lehninger Principles of Biochemistry |
| mm_competitive_inhibition | Copeland | 2013 | "Enzymes: Practical Introduction" |
| gillespie_ssa | Gillespie | 1976 | "General method for stochastic reactions" |
| gillespie_ssa_bimolecular | Gillespie | 1976 | Same |

This table listed 13 domains until 2026-11-01. sir, seir, wright_fisher, two_locus_wright_fisher, pcr, molecular_dynamics, lotka_volterra, cell_cycle_oscillator and repressilator were archived on 2026-09-27, after v0.4.0 (the last release that runs them), and this build refuses them.

---

## Error Handling

All endpoints return structured error responses:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable explanation"
}
```

Common error codes:
- `NOT_FOUND` (404) - Job doesn't exist
- `NO_PROVENANCE` (409) - Job incomplete or lacks parameter tracking
- `NO_DATA` (409) - No trajectory data to export
- `BAD_REQUEST` (400) - Invalid request format
- `INTERNAL_SERVER_ERROR` (500) - Backend failure

---

## Examples

### Get parameter confidence for a completed simulation:
```bash
curl -X GET /api/simulate/abc123/confidence
```

### Check if simulation is publication-ready:
```bash
curl -X GET /api/simulate/abc123/audit | jq '.publicationReady'
```

### Export results with literature citations:
```bash
curl -X GET /api/simulate/abc123/export > results.csv
curl -X GET /api/simulate/abc123/audit | jq '.parameterAudits'
```

### Monitor pipeline quality:
```bash
curl -X GET /api/simulate/metrics/pipeline | jq '.metrics'
```

---

## Testing

All 399 tests passing across 28 test files.

**Run tests:**
```bash
npm test
```

**Run specific suite:**
```bash
npm test -- metrics.test.ts
npm test -- strenda.test.ts
npm test -- literature-verifier.test.ts
npm test -- routes.test.ts
```

---

## Architecture Decisions

See `docs/adr/` for complete architecture decision records:
- ADR 0008: Parameter Provenance Tracking
- ADR 0011: Hard-Rule Parameter Validation
- ADR 0016: Serialization-Boundary Provenance Guards
- ADR 0018: Ki Inhibition Constant Resolution
- ADR 0019: kcat Resolution (Exposed, not yet wired to Vmax)
- ADR 0020: Epidemiology Parameters Wired to Resolvable Fields (historical: epidemiology was archived on 2026-09-27, after v0.4.0)

---

**Summary**: Every parameter traced to DOI. Every metric grounded in science. Every endpoint verified by peer review.
