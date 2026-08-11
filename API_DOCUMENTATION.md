# Terrium Backend API Documentation

> **⚠️ This REST API does not exist -- read before treating this as real.**
> The root `src/` tree this document claims to document (package
> `terrium-scientific-backend`) is a TypeScript **library and CLI**
> (`src/cli/scientificCLI.ts`), not an HTTP server: `package.json` has no
> `dependencies` key at all (only `devDependencies` -- jest, ts-node,
> eslint, typescript), and no `express`/`cors`/`createServer` call exists
> anywhere in `src/` (confirmed by grep, 2026-08-10). There is no
> `https://api.terrium.dev`, no `status.terrium.dev`, no `@terrium/sdk` npm
> package, no `pip install terrium-sdk`, and no webhook system. Terrium's
> REAL, deployed REST API lives in a different codebase entirely --
> `Science-Agent-Pipeline/artifacts/api-server/` -- documented accurately in
> that project's own `API_USER_GUIDE.md` and `INTEGRATION_EXAMPLES.md`
> (which were themselves corrected earlier for similar issues; see that
> project's real routes under `src/routes/`: `simulate.ts`, `health.ts`,
> `metrics.ts`, `pipeline.ts`, `dashboard.ts`, `waitlist.ts`, `enzymes.ts`).
> The 8 endpoints below do not match that real API either -- they are an
> independent invention. Kept below as a design sketch, not documentation
> of a running service.

**Version:** 1.0  
**Last Updated:** 2026-08-09  
**Base URL:** `https://api.terrium.dev/api`  
**Status Page:** https://status.terrium.dev

---

## Authentication

All API endpoints require valid API credentials.

```bash
# Option 1: Bearer Token (Recommended)
curl -H "Authorization: Bearer YOUR_API_KEY" https://api.terrium.dev/api/resolve

# Option 2: API Key Header
curl -H "X-API-Key: YOUR_API_KEY" https://api.terrium.dev/api/resolve
```

**API Key Management:**
- Generate keys at: https://app.terrium.dev/settings/api-keys
- Rotate keys every 90 days
- Never commit keys to git
- Revoke unused keys immediately

---

## Core Endpoints

### 1. Query Resolution

#### POST `/resolve`

Resolve a scientific query to domain-specific parameters.

**Request:**
```json
POST /api/resolve
Content-Type: application/json

{
  "query": "lactate dehydrogenase with km=5 and vmax=10"
}
```

**Response (200 OK):**
```json
{
  "runId": "run_123456789",
  "domain": "mm",
  "parameters": {
    "km": 5,
    "vmax": 10,
    "s0": 1.0,
    "t0": 0
  },
  "parameterProvenance": {
    "km": {
      "origin": "user",
      "citation": null,
      "note": "Supplied by user"
    },
    "vmax": {
      "origin": "user",
      "citation": null,
      "note": "Supplied by user"
    },
    "s0": {
      "origin": "default",
      "citation": "BRENDA_123",
      "note": "Resolved from literature"
    },
    "t0": {
      "origin": "default",
      "citation": null,
      "note": "System default"
    }
  },
  "provenance": {
    "reasoning": "Resolved as Michaelis-Menten enzyme kinetics...",
    "modelCitations": ["BRENDA_123", "KEGG_456"],
    "flags": [
      "parameter_range_warning: km value unusually high"
    ]
  }
}
```

**Error Responses:**

```json
// 400 Bad Request - Missing required fields
{
  "error": "RequiredParametersMissingError",
  "message": "Missing required parameters for domain mm",
  "missingKeys": ["km", "vmax"]
}

// 422 Unprocessable Entity - Invalid parameter type
{
  "error": "InvalidParameterError",
  "message": "Parameter 'km' must be a positive number",
  "field": "km",
  "value": "invalid"
}

// 429 Too Many Requests - Rate limit exceeded
{
  "error": "RateLimitExceeded",
  "message": "Rate limit exceeded: 1000 requests per 15 minutes",
  "retryAfter": 30
}
```

**Query Parameter Support:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Scientific query (1-1000 characters) |

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Authorization` | Bearer API_KEY | Yes |
| `Content-Type` | application/json | Yes |

**Rate Limiting:**
- 1000 requests per 15 minutes (global)
- 10 requests per endpoint per minute
- Remaining quota in response headers:
  - `X-RateLimit-Limit: 1000`
  - `X-RateLimit-Remaining: 999`
  - `X-RateLimit-Reset: 1691606400`

---

### 2. Job Simulation

#### POST `/simulate`

Enqueue a new simulation job.

**Request:**
```json
POST /api/simulate
Content-Type: application/json

{
  "query": "michaelis menten enzyme with parameters"
}
```

**Response (202 Accepted):**
```json
{
  "jobId": "job_abc123def456",
  "status": "pending",
  "createdAt": "2026-08-09T12:34:56.789Z",
  "estimatedWait": 45
}
```

**Response (400 Bad Request):**
```json
{
  "error": "InvalidQueryError",
  "message": "Query must be a non-empty string"
}
```

---

#### GET `/simulate/:jobId`

Poll job status and retrieve results.

**Request:**
```
GET /api/simulate/job_abc123def456
Authorization: Bearer YOUR_API_KEY
```

**Response (200 OK - Completed):**
```json
{
  "jobId": "job_abc123def456",
  "query": "michaelis menten enzyme",
  "status": "completed",
  "progress": 100,
  "completedAt": "2026-08-09T12:35:30.123Z",
  "result": {
    "runId": "run_xyz789",
    "domain": "mm",
    "parameters": {
      "km": 5.2,
      "vmax": 12.8,
      "s0": 1.0,
      "t0": 0
    },
    "trajectory": [
      { "t": 0, "s": 1.0, "v": 0 },
      { "t": 1, "s": 0.95, "v": 0.05 },
      { "t": 2, "s": 0.89, "v": 0.11 }
    ],
    "parameterProvenance": { /* ... */ },
    "provenance": { /* ... */ }
  }
}
```

**Response (200 OK - Running):**
```json
{
  "jobId": "job_abc123def456",
  "query": "michaelis menten enzyme",
  "status": "running",
  "progress": 45,
  "estimatedTimeRemaining": 30
}
```

**Response (200 OK - Pending):**
```json
{
  "jobId": "job_abc123def456",
  "query": "michaelis menten enzyme",
  "status": "pending",
  "progress": 0,
  "queuePosition": 23,
  "estimatedWait": 120
}
```

**Response (404 Not Found):**
```json
{
  "error": "JobNotFound",
  "message": "Job job_abc123def456 not found"
}
```

**Job Statuses:**
| Status | Description |
|--------|-------------|
| `pending` | Queued, waiting to start |
| `resolving` | Resolving parameters |
| `validating` | Validating resolved parameters |
| `running` | Simulation in progress |
| `completed` | Successfully completed |
| `failed` | Error occurred |
| `cancelled` | Cancelled by user |

---

#### DELETE `/simulate/:jobId`

Cancel a queued or running job.

**Request:**
```
DELETE /api/simulate/job_abc123def456
Authorization: Bearer YOUR_API_KEY
```

**Response (200 OK):**
```json
{
  "jobId": "job_abc123def456",
  "status": "cancelled",
  "cancelledAt": "2026-08-09T12:35:30.123Z"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "JobAlreadyTerminal",
  "message": "Cannot cancel job with status 'completed'"
}
```

---

### 3. Literature Search

#### POST `/literature/search`

Search literature database for parameters and citations.

**Request:**
```json
POST /api/literature/search
Content-Type: application/json

{
  "enzyme": "lactate dehydrogenase",
  "parameter": "km",
  "organism": "Homo sapiens",
  "substrate": "lactate"
}
```

**Response (200 OK):**
```json
{
  "results": [
    {
      "doi": "10.1234/test",
      "title": "Kinetics of Lactate Dehydrogenase...",
      "authors": ["Smith J", "Johnson K"],
      "year": 2020,
      "journal": "Enzyme Reviews",
      "citations": 45,
      "value": 5.2,
      "unit": "mM",
      "confidence": 0.95,
      "organism": "Homo sapiens",
      "conditions": {
        "temperature": "37°C",
        "pH": 7.4,
        "buffer": "phosphate"
      }
    }
  ],
  "total": 1,
  "averageValue": 5.2,
  "rangeMin": 4.8,
  "rangeMax": 5.6
}
```

---

### 4. Validation & Compliance

#### POST `/validate/strenda`

Validate parameters against STRENDA compliance guidelines.

**Request:**
```json
POST /api/validate/strenda
Content-Type: application/json

{
  "domain": "mm",
  "parameters": {
    "km": 5.0,
    "vmax": 10.0,
    "s0": 1.0,
    "t0": 0
  },
  "conditions": {
    "temperature": "37°C",
    "pH": 7.4
  }
}
```

**Response (200 OK):**
```json
{
  "compliant": true,
  "warnings": [
    {
      "requirement": 1,
      "field": "km",
      "message": "pH not provided, assuming 7.4"
    }
  ],
  "violations": [],
  "score": 0.95
}
```

**Response (200 OK - Non-Compliant):**
```json
{
  "compliant": false,
  "warnings": [
    {
      "requirement": 2,
      "field": "temperature",
      "message": "Temperature should be specified"
    }
  ],
  "violations": [
    {
      "requirement": 1,
      "field": "pH",
      "message": "pH is required for enzyme kinetics"
    }
  ],
  "score": 0.65
}
```

---

### 5. Health & Status

#### GET `/healthz`

Basic health check.

**Request:**
```
GET /api/healthz
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-08-09T12:34:56.789Z",
  "version": "1.0.0"
}
```

---

#### GET `/status`

Detailed system status.

**Request:**
```
GET /api/status
Authorization: Bearer YOUR_API_KEY
```

**Response (200 OK):**
```json
{
  "status": "operational",
  "timestamp": "2026-08-09T12:34:56.789Z",
  "components": {
    "database": "healthy",
    "cache": "healthy",
    "queue": "healthy",
    "pythonBridge": "healthy",
    "llmProvider": "healthy"
  },
  "metrics": {
    "queueDepth": 12,
    "activeJobs": 3,
    "cacheHitRate": 0.82,
    "errorRate": 0.0012,
    "avgLatencyMs": 245
  }
}
```

---

## Webhooks

### Event Subscription

Subscribe to job completion events via webhook.

**Setup:**
```bash
curl -X POST https://api.terrium.dev/api/webhooks \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-server.com/webhook",
    "events": ["job.completed", "job.failed"],
    "active": true
  }'
```

**Webhook Payload:**
```json
POST https://your-server.com/webhook

{
  "id": "evt_123456",
  "timestamp": "2026-08-09T12:35:30.123Z",
  "event": "job.completed",
  "jobId": "job_abc123def456",
  "data": {
    "jobId": "job_abc123def456",
    "status": "completed",
    "result": { /* ... */ }
  }
}
```

**Webhook Events:**
- `job.created` - Job enqueued
- `job.started` - Job started processing
- `job.progress` - Progress update (sent every 10%)
- `job.completed` - Job completed successfully
- `job.failed` - Job failed
- `job.cancelled` - Job cancelled

---

## Client Libraries

### JavaScript/TypeScript

```bash
npm install @terrium/sdk
```

```typescript
import { Terrium } from '@terrium/sdk';

const client = new Terrium({
  apiKey: process.env.TERRIUM_API_KEY
});

// Resolve query
const result = await client.resolve({
  query: 'lactate dehydrogenase km=5'
});

// Simulate
const job = await client.simulate({
  query: 'michaelis menten enzyme'
});

// Poll for completion
const completed = await client.pollJob(job.jobId);
```

### Python

```bash
pip install terrium-sdk
```

```python
from terrium import Terrium

client = Terrium(api_key=os.environ['TERRIUM_API_KEY'])

# Resolve query
result = client.resolve(
    query="lactate dehydrogenase km=5"
)

# Simulate
job = client.simulate(
    query="michaelis menten enzyme"
)

# Poll for completion
completed = client.poll_job(job['jobId'])
```

---

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
  "error": "ErrorCode",
  "message": "Human-readable error message",
  "statusCode": 400,
  "context": {
    "field": "fieldName",
    "value": "user_value"
  }
}
```

### Common Errors

| Code | Status | Meaning |
|------|--------|---------|
| `ValidationError` | 400 | Input validation failed |
| `RequiredParametersMissingError` | 422 | Missing required parameters |
| `InvalidParameterError` | 422 | Parameter has wrong type/value |
| `RateLimitExceeded` | 429 | Rate limit exceeded |
| `JobNotFound` | 404 | Job ID not found |
| `Unauthorized` | 401 | Invalid or missing API key |
| `InternalError` | 500 | Server error |

---

## Rate Limiting

### Global Rate Limit

- **Limit:** 1,000 requests per 15 minutes
- **Window:** Sliding 15-minute window
- **Headers:** Returned in every response

### Per-Endpoint Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /resolve | 10 | 1 minute |
| POST /simulate | 5 | 1 minute |
| GET /simulate/:id | 100 | 1 minute |
| POST /literature/search | 20 | 1 minute |
| POST /validate/strenda | 10 | 1 minute |

### Rate Limit Headers

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1691606400
Retry-After: 30
```

---

## Pagination

Results are paginated with cursor-based pagination:

```json
{
  "data": [ /* results */ ],
  "pagination": {
    "cursor": "crs_abc123",
    "limit": 50,
    "hasMore": true,
    "next": "/api/jobs?cursor=crs_abc123"
  }
}
```

**Query Parameters:**
- `cursor` - Pagination cursor
- `limit` - Results per page (max 100, default 50)

---

## Versioning

API versioning is handled via URL path:

- Current: `/api/v1/` (latest)
- Legacy: `/api/v0/` (deprecated, supported until 2026-12-31)

To use a specific version:
```bash
curl https://api.terrium.dev/api/v1/resolve \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Changelog

### v1.0.0 (2026-08-09)
- **Added:** Initial API release
- **Features:** Query resolution, simulation, literature search, STRENDA validation
- **Status:** Production ready

### v0.1.0 (2026-03-15)
- **Status:** Deprecated, end-of-life: 2026-12-31

---

## Support

**Documentation:** https://docs.terrium.dev  
**Status Page:** https://status.terrium.dev  
**Support Email:** support@terrium.dev  
**Community Slack:** https://terrium-community.slack.com  

---

## FAQ

**Q: How do I get an API key?**  
A: Sign up at https://app.terrium.dev, then generate a key in Settings → API Keys.

**Q: What's the maximum query length?**  
A: 1,000 characters.

**Q: How long does simulation take?**  
A: Typically 30-120 seconds depending on query complexity. Use webhooks for large batches.

**Q: Can I batch multiple requests?**  
A: Not yet, but it's on the roadmap. Use job IDs for concurrent polling.

**Q: How long are results retained?**  
A: 30 days. Use webhooks or polling to retrieve results before expiration.

**Q: Is the API available in production?**  
A: Yes, at https://api.terrium.dev. Use https://staging-api.terrium.dev for testing.

---

## Document Control

**Version:** 1.0  
**Last Updated:** 2026-08-09  
**Next Review:** 2026-11-09  
**Owner:** API Team
