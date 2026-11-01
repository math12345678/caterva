# Developer Quick Start Guide

**For:** Developers working on the Caterva backend  
**Status:** August 2026 — All 404 tests passing

## 5-Minute Setup

```bash
# 1. Install dependencies
npm install

# 2. Set environment variables
export PORT=5000
export NODE_ENV=development
export CATERVA_PYTHON=$(which python3.12)

# 3. Run tests
npm test                    # Full suite (404 tests)
npm run test:quick          # Smoke tests only

# 4. Start dev server
npm run dev                 # Watches for changes
```

Visit `http://localhost:5000` in your browser.

## Common Tasks

### Running Simulations Locally

```bash
# Via curl
curl -X POST http://localhost:5000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"query":"SIR beta=0.5 gamma=0.1 S0=900"}'

# Response: 202 Accepted with job ID
{
  "jobId": "abc-123",
  "status": "pending",
  "progress": 0
}

# Poll for result
curl http://localhost:5000/api/simulate/abc-123

# Or stream progress
curl http://localhost:5000/api/simulate/abc-123/stream
```

### Adding a New Domain

If adding domain `new_domain`:

1. **Python** (`src/lib/caterva_runner.py`):
   ```python
   def run_new_domain(parameters):
       # Implementation
       return domain, parameters, trajectory
   
   DISPATCH["new_domain"] = run_new_domain
   ```

2. **TypeScript** (`src/lib/catervaRunner.ts`):
   ```typescript
   export type SimulationDomain = 
     | "mm" | "sir" | ... | "new_domain";
   ```

3. **Schemas** (`src/lib/schemas.ts`):
   ```typescript
   new_domain: z.object({
     param1: numeric,
     param2: optionalNumeric,
   }),
   ```

4. **Literature** (`src/lib/domain-literature.ts`):
   ```typescript
   {
     domain: "new_domain",
     keywords: ["..."],
     defaults: { ... },
     literature: "Citation (Year)..."
   }
   ```

5. **LLM** (`src/lib/llmResolver.ts`):
   ```typescript
   if (domain === "new_domain") {
     systemPrompt += "\n- new_domain: description...";
   }
   ```

6. **OpenAPI** (`lib/api-spec/openapi.yaml`):
   ```yaml
   domain:
     enum: [..., new_domain]
   ```

7. **Test** (`src/__tests__/llmProviders.test.ts`):
   ```typescript
   RESOLVABLE_DOMAINS_COUNT = 15; // was 14
   ```

8. **Run tests:**
   ```bash
   npm test
   ```

### Fixing a Parameter Validation Bug

Example: `km` parameter is being accepted when it shouldn't

1. **Identify where it fails:**
   ```bash
   npm test -- schemas.test.ts
   # Look for failing test
   ```

2. **Update schema** (`src/lib/schemas.ts`):
   ```typescript
   mm: z.object({
     km: numeric.positive(), // Add constraint
     // ...
   })
   ```

3. **Update Python** (if needed) (`src/lib/caterva_runner.py`):
   ```python
   def run_mm(parameters):
       if parameters["km"] <= 0:
           raise ValueError("km must be positive")
   ```

4. **Add test** (`src/__tests__/schemas.test.ts`):
   ```typescript
   it("rejects negative km", () => {
     const invalid = { km: -5, ... };
     expect(() => validateParameters("mm", invalid)).toThrow();
   });
   ```

5. **Verify:**
   ```bash
   npm test -- schemas.test.ts
   ```

### Debugging a Failed Simulation

```bash
# 1. Get the job details
curl http://localhost:5000/api/simulate/{jobId}

# If status is "failed", check the error:
{
  "error": "PIPELINE_ERROR",
  "message": "..."
}

# 2. Check logs for detailed stack trace
tail -f logs/app.log
# Look for jobId in output

# 3. Reproduce locally
# Get the query from the job, run it again with logging enabled

# 4. Common issues:
# - Missing required parameter → Update schema defaults
# - Scientific bound violation → Check Python engine validation
# - Type mismatch → Verify Zod schema vs. Python type checking
```

### Adding Comprehensive Tests

```typescript
// src/__tests__/newFeature.test.ts
import { describe, it, expect } from "vitest";
import { myNewFunction } from "../lib/myFeature";

describe("MyFeature", () => {
  it("handles the happy path", () => {
    const result = myNewFunction(validInput);
    expect(result).toBeDefined();
  });

  it("rejects invalid input", () => {
    expect(() => myNewFunction(invalidInput))
      .toThrow("Expected error message");
  });

  it("gracefully handles edge case", () => {
    const result = myNewFunction(edgeCase);
    expect(result.flag).toBe("warning");
  });
});
```

Run: `npm test -- newFeature.test.ts`

### Checking Test Coverage

```bash
npm test -- --coverage

# View detailed report
open coverage/index.html
```

Target: Keep coverage >90% on critical paths

### Understanding Error Messages

**User sees:** `"MISSING_REQUIRED_INPUT: Cannot simulate 'sir': beta, gamma could not be resolved..."`

**This means:** The resolver couldn't find `beta` and `gamma` parameters. User needs to add them to query.

**Developer sees:** `RequiredParametersMissingError` thrown from `queryResolver.ts` line X

**Root cause:** Either:
1. Literature lookup failed
2. LLM didn't suggest them
3. User didn't supply them

**Fix:** Update domain defaults, improve LLM prompt, or add literature source

### Profiling a Slow Query

```bash
# Add timing logging
const start = Date.now();
const result = await resolveQuery(query);
console.log(`Resolution took ${Date.now() - start}ms`);

# Run with specific query
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"your slow query here"}'
# Watch logs for timing

# If LLM is slow:
# - Check network latency to LLM provider
# - Consider caching LLM responses
# - Fall back to keyword resolution

# If Python is slow:
# - Profile with: python -m cProfile
# - Check domain complexity (Gillespie >> ODE)
# - Verify step count isn't huge
```

## Architecture Overview

```
HTTP Request (Express)
    ↓
[Input Validation] Zod + JSON schema
    ↓
[Query Resolution] LLM or keyword fallback
    ↓
[Parameter Validation] Check shape & science
    ↓
[Job Queue] MAX_CONCURRENT=2 semaphore
    ↓
[Python Bridge] Spawn and communicate
    ↓
[Simulation Engine] caterva/ODE solver
    ↓
[Provenance Tracking] Record all origins
    ↓
[Caching] In-memory + DB
    ↓
[Response] JSON + provenance metadata
```

## Key Files to Know

| File | What | When to Edit |
|------|------|--------------|
| `src/lib/schemas.ts` | Parameter validation | Adding domain or parameter |
| `src/lib/queryResolver.ts` | Domain/param detection | Improving resolution logic |
| `src/lib/caterva_runner.py` | Simulation engine | Adding domain or fixing engine |
| `src/lib/llmResolver.ts` | LLM integration | Changing LLM behavior |
| `src/routes/simulate.ts` | HTTP endpoints | Adding/changing API routes |
| `src/__tests__/llmProviders.test.ts` | Python/TS contract | Verifying domain sync |

## Environment Variables

**Development:**
```bash
PORT=5000                              # Server port
NODE_ENV=development                   # Log level
CATERVA_PYTHON=/path/to/python3.12    # Python exe
```

**Optional (with defaults):**
```bash
LOG_LEVEL=debug                        # pino log level
CACHE_FILE=./data/cache.json          # Cache location
DATABASE_URL=...                       # PostgreSQL (optional)
GROQ_API_KEY=...                       # LLM (optional, fallback to keyword)
```

## Testing Strategy

### Before Committing

```bash
npm run typecheck    # TypeScript errors
npm test            # All tests pass
npm run lint        # Code style
```

### Quick Test Run

```bash
npm run test:quick   # Fast subset (~30s)
```

### Full Suite

```bash
npm test             # All 404 tests (~40s with Python bridge)
```

### Specific Test File

```bash
npm test -- llmProviders.test.ts
npm test -- schemas.test.ts
npm test -- provenance.test.ts
```

## Debugging Tips

### Enable Verbose Logging

```bash
LOG_LEVEL=debug npm run dev
```

### Inspect a Job

```bash
curl http://localhost:5000/api/simulate/{jobId}
```

### Check Queue State

```bash
curl http://localhost:5000/api/simulate
# Shows all recent jobs
```

### Stream Progress

```bash
curl http://localhost:5000/api/simulate/{jobId}/stream
# Real-time SSE updates
```

### View System Metrics

```bash
curl http://localhost:5000/api/metrics
# Queue length, success rate, latency distribution
```

## Common Mistakes

### ❌ Modifying Python DISPATCH without updating TypeScript

**Will cause:** Test failure in `llmProviders.test.ts`

**Fix:** Update `SimulationDomain` type + schema + defaults

### ❌ Adding schema constraint without Python validation

**Will cause:** Inconsistent behavior—TypeScript accepts, Python rejects

**Fix:** Add same check to Python handler

### ❌ Forgetting to update OpenAPI spec

**Will cause:** Documentation drift, API clients confused

**Fix:** Add domain to `SimulationResponse.domain.enum` in `openapi.yaml`

### ❌ Changing parameter name without updating keyword list

**Will cause:** Keyword fallback doesn't recognize parameter

**Fix:** Update `PARAMETER_NAMES` regex and keyword defaults

### ❌ Not validating provenance before serializing

**Will cause:** Response missing provenance entries, audit trail breaks

**Fix:** Call `guardSerializationProvenance()` before sending

## Getting Help

### Read the Docs

- `BACKEND_ARCHITECTURE.md` — System design
- `ADR_*.md` — Design decisions
- `PERFORMANCE_GUIDE.md` — Optimization strategies
- Code comments — Implementation details

### Understand a Component

```bash
# Grep for usage
grep -r "resolveQuery" src/ --include="*.ts"

# Read tests
cat src/__tests__/queryResolver.test.ts

# Follow the code path
# src/routes/simulate.ts → resolveQuery → queryResolver.ts
```

### Check Test Coverage

```bash
npm test -- --coverage
# View which lines are untested
```

### Profile Performance

```bash
npm run benchmark
# Measure operation latencies
```

## Submitting Changes

### PR Checklist

- [ ] Tests pass: `npm test`
- [ ] TypeScript clean: `npm run typecheck`
- [ ] Linting passes: `npm run lint`
- [ ] Python/TS boundary in sync (if editing schema/DISPATCH)
- [ ] OpenAPI spec updated (if API changed)
- [ ] New ADRs written (if major design decision)
- [ ] Documentation updated

### Commit Message

```
feat: Add support for new_domain simulation

- Implement run_new_domain handler in Python
- Add schema validation in TypeScript
- Update OpenAPI spec and tests
- All 404 tests pass

Closes #123
```

## Quick Reference

```bash
# Start
npm run dev                  # Watch + reload

# Test
npm test                     # All tests
npm run test:quick           # Quick smoke tests

# Build
npm run build                # Compile TypeScript

# Type Check
npm run typecheck            # Find type errors

# Lint
npm run lint                 # Code style

# Profile
npm run benchmark            # Performance profiling

# Database
npm run db:migrate           # Apply migrations (if using DB)

# Format
npm run format               # Auto-format code
```

---

**Questions?** Check `BACKEND_ARCHITECTURE.md` or look at existing tests for examples.

**Found a bug?** Add a test first, then fix the code.

**Want to optimize?** See `PERFORMANCE_GUIDE.md` for strategies.

Happy coding! 🚀
