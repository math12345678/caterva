# Testing & CI/CD Guide

**For:** Developers, QA, release engineers  
**Status:** August 2026  
**Coverage:** 404 tests, 100% on critical paths

---

## Testing Strategy

### Test Pyramid

```
         Manual Testing (1)
              ↑
        Integration (20)
              ↑
        Unit Tests (383)
              ↑
           Base
```

- **Unit Tests (383)**: Fast, isolated, mockable
- **Integration Tests (20)**: Real engines, databases
- **E2E Tests (1)**: Full pipeline, real deployments

**Philosophy:** Maximize fast feedback (unit), minimize flaky tests (E2E)

---

## Running Tests

### Full Suite

```bash
npm test
# Runs all 404 tests
# Time: ~40s (depends on Python bridge availability)
```

### Quick Smoke Tests

```bash
npm run test:quick
# Subset of critical tests
# Time: ~10s
# Use before committing
```

### Specific Test File

```bash
npm test -- schemas.test.ts
npm test -- provenance.test.ts
npm test -- llmProviders.test.ts
```

### Watch Mode (Development)

```bash
npm test -- --watch
# Re-runs tests when files change
# Great for TDD
```

### Coverage Report

```bash
npm test -- --coverage
# Generates coverage report
# View: open coverage/index.html
```

**Target:** >90% on critical paths (queryResolver, provenance, validation)

---

## Test Categories

### 1. Unit Tests

**Location:** `src/__tests__/` and `src/lib/*.test.ts`

**Examples:**
- Parameter schema validation (schemas.test.ts)
- Query parameter extraction (queryOverrides.test.ts)
- Cache behavior (cache.test.ts)
- Rate limiting (rateLimit.test.ts)

**Pattern:**
```typescript
import { describe, it, expect } from "vitest";

describe("MyFunction", () => {
  it("handles happy path", () => {
    const result = myFunc(validInput);
    expect(result).toBe(expected);
  });

  it("rejects invalid input", () => {
    expect(() => myFunc(invalidInput)).toThrow();
  });

  it("handles edge case", () => {
    const result = myFunc(edgeCase);
    expect(result.flag).toBe("warning");
  });
});
```

**Run:**
```bash
npm test -- unit
```

### 2. Integration Tests

**Location:** `src/__tests__/*e2e*.test.ts`

**Examples:**
- End-to-end query → engine → result (literature-backed-e2e.test.ts)
- Domain resolution with literature (popgenResolutionE2E.test.ts)
- Provenance tracking through full pipeline

**Pattern:**
```typescript
describe("QueryResolver E2E", () => {
  it("resolves complete SIR simulation", async () => {
    const query = "SIR beta=0.5 gamma=0.1 S0=900";
    const resolved = await resolveQuery(query);
    
    expect(resolved.domain).toBe("sir");
    expect(resolved.parameters).toHaveProperty("beta", 0.5);
    expect(resolved.parameterProvenance.beta.origin).toBe("user");
  });
});
```

**Run:**
```bash
npm test -- e2e
```

### 3. Contract Tests

**Location:** `src/__tests__/llmProviders.test.ts`

**Purpose:** Verify Python/TypeScript boundary (ADR 0007)

**What it tests:**
- Python DISPATCH has exactly 16 domains
- TypeScript SimulationDomain enum matches Python
- All schemas are defined
- LLM domain list is consistent

**Critical because:** Prevents drift that breaks the system

**Run:**
```bash
npm test -- llmProviders
```

**Should fail if:**
- You add domain to Python but forget TypeScript
- You change a domain name
- You modify schema without updating LLM defaults

### 4. Literature Validation Tests

**Location:** `src/__tests__/*literature*.test.ts`, `src/__tests__/*provenance*.test.ts`

**Tests:**
- Parameter values match published literature
- Citations are correctly formatted
- STRENDA compliance
- Provenance completeness

**Example:**
```typescript
it("resolves km from BRENDA", async () => {
  const result = await resolveParameter("km", "lactate dehydrogenase");
  
  expect(result.provenance.origin).toBe("resolved");
  expect(result.provenance.citation).toContain("Brenda");
  expect(result.provenance.citationStatus).toBe("verified");
  expect(result.value).toBeGreaterThan(0);
});
```

### 5. Golden File Tests

**Location:** `src/__tests__/golden_*.json`

**Purpose:** Regression detection via trajectory comparison

**How it works:**
1. First run: Save baseline trajectory
2. Future runs: Compare against baseline
3. If different: Either regression (fix) or intended change (update)

**Files:**
- `golden_sir_baseline.json` - Reference SIR trajectory
- `golden_gillespie_ssa_baseline.json` - Reference stochastic run
- etc.

**Update baseline:**
```bash
# After intentional change (e.g., updated solver):
npm test -- --update-snapshots
```

---

## Test Quality Metrics

### Coverage by Component

| Component | Coverage | Target |
|-----------|----------|--------|
| queryResolver.ts | 95% | 90% |
| provenance.ts | 98% | 90% |
| schemas.ts | 100% | 90% |
| cache.ts | 92% | 90% |
| llmResolver.ts | 87% | 80% |
| telluriumRunner.ts | 85% | 80% |

**Gap:** Some integration code and error paths

**Strategy:** Unit tests are thorough; E2E provides missing coverage

### Flakiness Metrics

**Target:** 0 flaky tests

**Common flakiness sources:**
1. **Timing** (tests expecting fast network) → Add timeouts
2. **Randomness** (stochastic simulations) → Seed RNG
3. **External dependencies** (LLM API) → Mock or skip
4. **Race conditions** → Use sequential execution

**Monitor:**
```bash
# Run tests multiple times to catch flakiness
for i in {1..5}; do npm test; done
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: terrium_test
          POSTGRES_USER: terrium
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          npm ci
          pip install -r requirements-dev.txt
      
      - name: Type check
        run: npm run typecheck
      
      - name: Lint
        run: npm run lint
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql://terrium:test@localhost:5432/terrium_test
        run: npm test
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage/coverage-final.json
```

### Pre-Commit Checks

```bash
# .git/hooks/pre-commit
#!/bin/bash
set -e

echo "Running TypeScript type check..."
npm run typecheck

echo "Running linter..."
npm run lint

echo "Running quick tests..."
npm run test:quick

echo "✓ All checks passed"
```

**Install:**
```bash
npm run setup:hooks
```

### PR Checks

**Requirements for merge:**
- ✅ All tests pass (404/404)
- ✅ No new TypeScript errors
- ✅ Coverage maintained (or improved)
- ✅ Code review approved
- ✅ No breaking changes documented

**CI will block merge if:**
- Test fails
- Coverage drops >2%
- Type errors introduced
- Linting violations

---

## Deployment Stages

### 1. Development (Local)

```bash
npm run dev
# Watch mode
# Auto-reload on changes
# Full logging
```

### 2. Staging (Pre-Production)

```bash
# Build
npm run build

# Deploy to staging environment
docker build -t terrium-api:staging .
docker push registry.example.com/terrium-api:staging

# Smoke tests
curl https://staging-api.example.com/healthz
```

### 3. Production (Release)

```bash
# Tag version
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3

# CI automatically builds and publishes
# Check workflow status

# Deploy with canary
# 10% traffic to new version for 1 hour
# If error rate <0.5%, promote to 100%
# If error rate >0.5%, rollback immediately
```

---

## Testing Checklist

### Before Committing

- [ ] `npm test` passes
- [ ] `npm run typecheck` passes
- [ ] `npm run lint` passes
- [ ] Added tests for new features
- [ ] Updated documentation if needed

### Before PR

- [ ] Tests passing on own branch
- [ ] Rebased on main
- [ ] Commit messages clear
- [ ] No console.log() statements
- [ ] No TODO comments left

### Before Merge

- [ ] Code review approved
- [ ] CI pipeline green
- [ ] Coverage maintained
- [ ] No conflicts

### Before Deploying

- [ ] Tests passing on main
- [ ] Built and tagged
- [ ] Deployment plan documented
- [ ] Rollback procedure ready
- [ ] On-call aware of deployment

---

## Performance Testing

### Load Test Setup

```bash
# Install wrk
brew install wrk

# Create scenario
cat > scenario.lua << 'EOF'
request = function()
  return wrk.format("POST", "/api/simulate",
    nil, '{"query":"SIR beta=0.5 gamma=0.1 S0=900"}')
end
EOF

# Run test
wrk -t4 -c100 -d30s \
    -s scenario.lua \
    http://localhost:5000/api
```

### Benchmarking

```bash
npm run benchmark
# Measures operation latencies
# Compares to baseline
```

### Stress Testing

```bash
# Run load test to failure
wrk -t8 -c500 -d5m --script scenario.lua http://localhost:5000/api

# Watch logs for errors
sudo journalctl -u terrium-api -f
```

---

## Test Data Management

### Fixtures

**Location:** `src/__tests__/fixtures/`

```typescript
// fixtures/queries.ts
export const testQueries = {
  sir_basic: {
    query: "SIR beta=0.5 gamma=0.1 S0=900",
    expectedDomain: "sir",
    expectedParams: { beta: 0.5, gamma: 0.1, s0: 900 }
  },
  // ...
};
```

**Usage:**
```typescript
import { testQueries } from "../fixtures/queries";

it("resolves SIR query", async () => {
  const result = await resolveQuery(testQueries.sir_basic.query);
  expect(result.domain).toBe(testQueries.sir_basic.expectedDomain);
});
```

### Mocking External Services

```typescript
// Mock LLM API
vi.mock("../lib/llmResolver", () => ({
  classifyDomain: vi.fn().mockResolvedValue({
    domain: "sir",
    parameters: { beta: 0.5 }
  })
}));

// Mock database
vi.mock("../db", () => ({
  getDb: vi.fn().mockReturnValue(null)  // Simulate DB unavailable
}));
```

---

## Regression Testing

### Strategy

1. **Golden files** (trajectory comparison)
2. **Snapshot tests** (response schema)
3. **Property tests** (invariant checking)

### Detecting Regressions

```bash
# Baseline snapshot
npm test -- --update-snapshots

# Later, if test fails
# Indicates something changed
# Investigate why:
#   - Intended change? Update snapshot
#   - Unintended? Fix code

npm test -- --update-snapshots  # Only if change is intended
```

---

## Security Testing

### Input Validation

```typescript
it("rejects oversized query", () => {
  const huge = "a".repeat(10000);
  expect(() => validateInput(huge)).toThrow();
});

it("rejects SQL injection in query", () => {
  const sql = "'; DROP TABLE simulations; --";
  expect(() => validateInput(sql)).toThrow();
});

it("rejects code injection", () => {
  const code = "${process.exit()}";
  expect(() => validateInput(code)).toThrow();
});
```

### Dependency Scanning

```bash
# Check for vulnerabilities
npm audit

# Update vulnerable packages
npm audit fix

# Or in CI (fail on critical)
npm audit --audit-level moderate --production
```

---

## Test Maintenance

### Updating Tests

When requirements change:

1. Update the test to reflect new requirement
2. Verify it fails with old code
3. Fix code to make test pass
4. Verify test now passes

### Removing Flaky Tests

If test fails intermittently:

1. Identify the flakiness source
2. Add determinism (seed, timeout, mock)
3. Re-run 5x to verify stability
4. Commit the fix

### Refactoring Test Code

Keep tests maintainable:

```typescript
// ❌ Avoid repeated setup
describe("MyFunc", () => {
  it("test 1", () => {
    const x = expensive();
    expect(x).toBe(1);
  });
  it("test 2", () => {
    const x = expensive();  // Repeated!
    expect(x).toBe(2);
  });
});

// ✅ Use beforeEach
describe("MyFunc", () => {
  let x;
  beforeEach(() => {
    x = expensive();
  });
  it("test 1", () => expect(x).toBe(1));
  it("test 2", () => expect(x).toBe(2));
});
```

---

## Metrics & Reporting

### Test Health Dashboard

```bash
npm test -- --reporter=json > test-results.json

# Parse and upload to dashboard
# Track over time:
# - Test count
# - Pass rate
# - Flaky tests
# - Coverage by component
```

### Continuous Monitoring

Post-merge:
- Run tests against staging
- Run performance tests
- Monitor error rates
- Alert on regressions

---

## Release Checklist

### Pre-Release

- [ ] All tests passing locally
- [ ] All tests passing on CI
- [ ] Release notes written
- [ ] Version bumped (MAJOR.MINOR.PATCH)
- [ ] Git tag created

### During Release

- [ ] Tag pushed to origin
- [ ] CI builds and publishes
- [ ] Docker image pushed
- [ ] Deployment initiated
- [ ] Health checks passing

### Post-Release

- [ ] Metrics validated (low error rate)
- [ ] Logs reviewed
- [ ] User feedback collected
- [ ] Known issues documented
- [ ] Next iteration planned

---

## References

- Test files: `src/__tests__/`
- Package.json: npm scripts
- CI config: `.github/workflows/`
- Performance guide: `PERFORMANCE_GUIDE.md`

---

**Status:** All 404 tests passing  
**Last updated:** August 9, 2026  
**Coverage target:** >90% on critical paths  
**Next review:** August 23, 2026
