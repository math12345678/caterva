# OpenAPI Specification & Integration Guide

> **⚠️ CORRECTION (2026-08-12):** The `GET /api/jobs/query?...` and `GET /api/jobs/history` examples in "IDE Integration" and "API Testing Tools" below do not work as shown. In `src/web/server.ts`, the `GET /api/jobs/:jobId` handler (`pathname.match(/^\/api\/jobs\/[a-z0-9_]+$/i)`, around line 235) is registered *before* the `/api/jobs/history` (line 251) and `/api/jobs/query` (line 259) handlers, and its regex matches the literal strings `history` and `query` as if they were job IDs. Reproduced live: `curl http://localhost:3000/api/jobs/history` and `curl "http://localhost:3000/api/jobs/query?..."` both return `404 {"error":"Job not found"}` instead of the documented behavior — the later handlers are unreachable dead code. This is a routing bug in `server.ts` itself (out of scope for this audit to fix), not a documentation error to correct by rewording; treat both endpoints as currently non-functional until the route order is fixed.
>
> Also, `openapi.yaml` was missing 13 real routes (`GET /api/jobs/{jobId}` and all 12 `GET /api/metrics/*` routes) as of this session; these have been added to `openapi.yaml`'s `paths` section so it now matches all 30 real routes in `server.ts`.

Caterva publishes a complete **OpenAPI 3.0 specification** (`openapi.yaml`) that enables:

- ✅ Interactive API documentation (Swagger UI, ReDoc)
- ✅ Automatic client generation (TypeScript, Python, Go, Rust, etc.)
- ✅ IDE integration and IntelliSense
- ✅ API testing tools (Postman, Insomnia, etc.)
- ✅ Contract testing and mock servers
- ✅ API validation and linting

---

## Quick Start

### 1. Interactive Documentation

**Swagger UI** (Try it out in your browser):
```bash
http://localhost:3000/api/docs
```

**ReDoc** (Alternative documentation):
```bash
http://localhost:3000/api/docs/redoc
```

**Raw OpenAPI JSON**:
```bash
http://localhost:3000/api/openapi.json
```

---

## Client Generation

### TypeScript (Using OpenAPI Generator)

**Install generator:**
```bash
npm install -g @openapitools/openapi-generator-cli
```

**Generate TypeScript client:**
```bash
openapi-generator-cli generate \
  -i http://localhost:3000/api/openapi.json \
  -g typescript-fetch \
  -o ./generated-client
```

**Generated client usage:**
```typescript
import { DefaultApi } from './generated-client';

const api = new DefaultApi({
  basePath: 'http://localhost:3000'
});

// Run simulation
const response = await api.simulate({
  query: 'michaelis-menten',
  parameters: { km: 5.2, vmax: 12.8, s0: 10 }
});

console.log(response.jobId);
```

### Python (Using OpenAPI Generator)

**Generate Python client:**
```bash
openapi-generator-cli generate \
  -i http://localhost:3000/api/openapi.json \
  -g python \
  -o ./generated-python-client
```

**Generated client usage:**
```python
from openapi_client import ApiClient, DefaultApi

api = DefaultApi(ApiClient())

response = api.simulate({
    'query': 'michaelis-menten',
    'parameters': {'km': 5.2, 'vmax': 12.8, 's0': 10}
})

print(response.job_id)
```

### Go

```bash
openapi-generator-cli generate \
  -i http://localhost:3000/api/openapi.json \
  -g go \
  -o ./generated-go-client
```

### Rust

```bash
openapi-generator-cli generate \
  -i http://localhost:3000/api/openapi.json \
  -g rust \
  -o ./generated-rust-client
```

---

## IDE Integration

### IntelliSense in VS Code

**Install REST Client extension:**
```bash
code --install-extension humao.rest-client
```

**Create `requests.http` file:**
```http
### Health check
GET http://localhost:3000/api/health

### Run simulation
POST http://localhost:3000/api/simulate
Content-Type: application/json

{
  "query": "michaelis-menten",
  "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}
}

### Query jobs
GET http://localhost:3000/api/jobs/query?status=complete&limit=10

### Export to CSV
GET http://localhost:3000/api/export/jobs/csv
```

Then use **Ctrl+Alt+R** to execute any request.

---

## API Testing Tools

### Postman

1. Import the OpenAPI spec directly:
   - Open Postman → **File → Import**
   - Choose **URL** tab
   - Paste `http://localhost:3000/api/openapi.json`
   - Postman auto-generates all endpoints with examples

2. Run collections and create test scripts

### Insomnia

1. **Create new request → Design → Import from URL**
2. Paste `http://localhost:3000/api/openapi.json`
3. All endpoints available in left sidebar

### cURL (Manual)

```bash
# Health check
curl -s http://localhost:3000/api/health | jq

# Run simulation
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}
  }' | jq

# Query jobs
curl -s "http://localhost:3000/api/jobs/query?status=complete&limit=10" | jq

# Export CSV
curl -s http://localhost:3000/api/export/jobs/csv > jobs.csv
```

---

## Contract Testing

### Jest + OpenAPI Validator

**Install:**
```bash
npm install --save-dev openapi-typescript jest
```

**Test that actual responses match the spec:**
```typescript
import { createClient } from 'openapi-typescript';

describe('API Contract Tests', () => {
  it('GET /api/health returns valid health response', async () => {
    const response = await fetch('http://localhost:3000/api/health');
    const data = await response.json();
    
    expect(data).toMatchSchema({
      status: { type: 'string', enum: ['ok'] },
      uptime: { type: 'number' },
      jobs: { type: 'object' }
    });
  });
});
```

---

## Mock Servers

### Prism (OpenAPI Mock Server)

**Install:**
```bash
npm install -g @stoplight/prism-cli
```

**Start mock server:**
```bash
prism mock openapi.yaml -p 4010
```

**The mock server:**
- Validates requests against the spec
- Returns realistic example responses
- Great for testing before API is ready
- Useful for frontend development

**Test against mock:**
```bash
curl http://localhost:4010/api/simulate \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "michaelis-menten", "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}}'
```

---

## Specification Validation

### Lint the spec

**Using Spectral (OpenAPI linter):**
```bash
npm install -g @stoplight/spectral-cli
spectral lint openapi.yaml
```

**Common issues it catches:**
- Missing required fields
- Type mismatches in examples
- Undocumented status codes
- Inconsistent naming conventions
- Missing descriptions

### Validate at build time

**Add to `package.json`:**
```json
{
  "scripts": {
    "validate:api": "spectral lint openapi.yaml",
    "build": "npm run validate:api && tsc"
  }
}
```

Now the build fails if the spec is invalid.

---

## Document Generation

### PDF/HTML from OpenAPI

**Using Redoc CLI:**
```bash
npm install -g redoc-cli
redoc-cli bundle openapi.yaml \
  -o api-docs.html \
  --title "Caterva API Documentation"
```

**Share the HTML file with stakeholders:**
- Single-file, self-contained documentation
- No external dependencies
- Offline-accessible
- Professional appearance

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Validate API Specification

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: npm install -g @stoplight/spectral-cli
      - run: spectral lint openapi.yaml
      
      - name: Generate clients
        run: |
          npm install -g @openapitools/openapi-generator-cli
          openapi-generator-cli generate \
            -i openapi.yaml \
            -g typescript-fetch \
            -o ./client-ts
          
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: generated-clients
          path: client-ts/
```

Every push validates the spec and generates fresh clients.

---

## Best Practices

### 1. Keep Spec in Sync with Code

**Add pre-commit hook:**
```bash
#!/bin/sh
# .git/hooks/pre-commit

npm run validate:api || exit 1
```

This prevents committing a spec that doesn't match the code.

### 2. Version the API

**In `openapi.yaml`:**
```yaml
info:
  version: 1.0.0
  # Bump this when making breaking changes
```

Consumers know when to upgrade.

### 3. Use Discriminators for Polymorphism

```yaml
oneOf:
  - $ref: '#/components/schemas/SuccessResponse'
  - $ref: '#/components/schemas/ErrorResponse'
discriminator:
  propertyName: status
  mapping:
    success: '#/components/schemas/SuccessResponse'
    error: '#/components/schemas/ErrorResponse'
```

Client generators use this to pick the right type.

### 4. Document Examples Thoroughly

Every endpoint should have realistic examples:
```yaml
example:
  query: michaelis-menten
  parameters:
    km: 5.2
    vmax: 12.8
    s0: 10.0
  enzyme: lactate dehydrogenase
  substrate: lactate
```

Examples are used by:
- Swagger UI (try-it-out forms)
- Mock servers (response generation)
- Test suites (contract testing)
- Documentation generators

### 5. Status Codes Matter

Define all possible outcomes:
```yaml
responses:
  '200':
    description: Success
  '400':
    description: Validation failed
  '404':
    description: Resource not found
  '500':
    description: Server error
```

Clients expect specific codes to mean specific things.

---

## Troubleshooting

### "OpenAPI spec not found"

Check that `openapi.yaml` exists in the root directory and `/api/openapi.json` endpoint is live:

```bash
curl -s http://localhost:3000/api/openapi.json | head -20
```

### "Generated code has syntax errors"

Some generators produce code that needs manual cleanup. Try a different generator:

```bash
# If typescript-fetch fails, try nodejs:
openapi-generator-cli generate \
  -i openapi.yaml \
  -g nodejs \
  -o ./client-node
```

### "Swagger UI shows 404 errors"

Make sure the server is running with the correct `openapi.yaml` path:

```bash
npm run web:start
# Then visit http://localhost:3000/api/docs
```

---

## Summary

The OpenAPI specification is the **single source of truth** for your API. It enables:

| Use Case | Tool |
|----------|------|
| **Try it now** | Swagger UI at `/api/docs` |
| **Build a client** | OpenAPI Generator |
| **Test contracts** | Spectral + Jest |
| **Share docs** | ReDoc at `/api/docs/redoc` |
| **Mock for testing** | Prism |
| **Catch errors** | Spectral linter |

Keep the spec up to date and everything else follows.
