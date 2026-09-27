# Testing & CI/CD Guide

**For:** Developers, QA, release engineers  
**Status:** August 2026  
**Coverage:** 404 vitest test cases across 28 test files in `src/__tests__/` and `src/lib/`
(the real number, from actually running `npx vitest run`, whose own summary line reports
"Test Files 28 passed (28) / Tests 404 passed (404)" — verified 2026-08-09. A prior pass at
this number used `grep -rc "it(\|test(" ...` and got 359, which undercounts: it only counts
matching *lines*, so `it.each(...)`/loop-generated cases that expand to several tests off one
call site are missed. Running the suite, not grepping it, is the number that's actually true).
Code coverage percentage is **not currently measured** — no coverage tool is configured (see
"Test Quality Metrics" below).

---

## Testing Strategy

### Test Composition

This repo does not enforce a strict unit/integration/e2e split through tooling — all 404
test cases run through a single `vitest run` invocation. The closest thing to a category
split is naming convention:

- **E2E-named tests (28 cases, 2 files):** `literature-backed-e2e.test.ts` (24 cases) and
  `popgenResolutionE2E.test.ts` (4 cases) — these exercise the full query → engine → result
  pipeline.
- **Everything else (376 cases, 26 files):** parameter/schema validation, provenance,
  caching, rate limiting, query resolution, LLM provider contracts, etc. — fast, in-process,
  mostly mocked where they touch external services (LLM API, Python bridge).

**Philosophy:** Maximize fast feedback; the two e2e-named files are the only ones expected
to be slower/more end-to-end in character.

---

## Running Tests

This is a pnpm workspace (`packageManager: "pnpm@11.20.0"` at the repo root, `pnpm-lock.yaml`
committed, no `package-lock.json`). The api-server's real `package.json` scripts are:
`dev`, `build`, `start`, `test`, `test:watch`, `typecheck`. There is no `lint`,
`test:quick`, `benchmark`, or `setup:hooks` script — commands referencing those below have
been corrected or explicitly marked as proposed.

### Full Suite

```bash
# From artifacts/api-server:
pnpm test
# "test" runs: vitest run
# Runs all 404 test cases across 28 files

# From the repo root:
pnpm --filter @workspace/api-server run test
```

### Quick Smoke Tests

**Not currently implemented.** There is no `test:quick` script and no subset-of-critical-tests
configuration. To run a fast subset today, filter by filename substring (see "Specific Test
File" below) — vitest does not distinguish "smoke" tests as a category in this repo.

### Specific Test File

```bash
pnpm test -- schemas.test.ts
pnpm test -- provenance.test.ts
pnpm test -- llmProviders.test.ts
```

### Watch Mode (Development)

```bash
pnpm run test:watch
# Runs: vitest (watch mode by default)
# Re-runs tests when files change
```

### Coverage Report

**Not currently implemented.** No coverage provider (`@vitest/coverage-v8`, `c8`, `istanbul`,
`nyc`) is installed, and `vitest.config.ts` has no `test.coverage` block. Running
`vitest run --coverage` today will fail because no coverage provider is available. See "Test
Quality Metrics" below for what would be needed to add real coverage reporting.

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
pnpm test
# There is no "unit" filename substring in this repo, so `pnpm test -- unit`
# would match zero files. Run the full suite, or filter by a real file name
# (see "Specific Test File" above).
```

### 2. E2E-Named Tests

**Location:** `src/__tests__/*e2e*.test.ts` (matches `literature-backed-e2e.test.ts` and
`popgenResolutionE2E.test.ts`). The doc previously called these "Integration Tests"; there is
no separate integration-test tier or tooling in this repo — these are simply the two files
whose names contain "e2e".

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
pnpm test -- e2e
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
pnpm test -- llmProviders
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

### 5. Golden Tests

**Location:** `src/__tests__/gillespieGolden.test.ts` and
`src/__tests__/gillespieBimolecularGolden.test.ts`

**Purpose:** Regression detection via trajectory comparison

**How it actually works here:** there are no separate `golden_*.json` fixture files. Each
golden test hardcodes the expected trajectory inline as a TypeScript object in the test file
itself, e.g. in `gillespieGolden.test.ts`:

```typescript
// The SSA golden (Stage 6 Part 2): seed 12345, a0=100, k=0.5, end=3.0.
// Pinned in Python in caterva/tests/test_gillespie_ssa_golden.py; this
// file pins the SAME trajectory through the real runner boundary so a
// drift between engine and bridge (or a changed engine) breaks here too.
const GOLDEN = {
  rows: 78,
  firstEventTime: 0.029626521616845532,
  secondEventTime: 0.052851089922515,
  final: { time: 3, a: 24, b: 76 },
};
```

The test then asserts the live simulation output matches these hardcoded values exactly. To
"update the baseline" here means editing the `GOLDEN` object by hand after verifying the new
trajectory is correct — there is no `--update-snapshots` mechanism wired to these tests, and
`vitest`'s own snapshot feature is not what's in use.

---

## Test Quality Metrics

### Coverage by Component

**Not currently measured.** No coverage tool is configured for this project: `package.json`
has no `c8`, `istanbul`, or `nyc` dependency, no `@vitest/coverage-v8` (or any
`@vitest/coverage-*` package), and `vitest.config.ts` has no `test.coverage` block. The
per-file percentages that used to appear here (queryResolver.ts 95%, provenance.ts 98%,
schemas.ts 100%, cache.ts 92%, llmResolver.ts 87%, catervaRunner.ts 85%) were not backed by
any coverage run and have been removed rather than corrected, since there is currently no
tooling in this repo that could produce them.

To get real numbers, add `@vitest/coverage-v8` as a dev dependency and a `test.coverage`
block to `vitest.config.ts` (or a `coverage` script), then run `vitest run --coverage`.

**Strategy:** Test breadth is judged today by test-case count (404) and by which modules have
dedicated `*.test.ts` files, not by a measured coverage percentage.

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
for i in {1..5}; do pnpm test; done
```

---

## Continuous Integration

### GitHub Actions Workflow

The real workflow file is `.github/workflows/tests.yml` (repo root), named `tests`, not
`test.yml`. It has **two** jobs, neither of which uses a Postgres service container, neither
of which uploads to codecov, and both of which use **pnpm**, not npm:

```yaml
# .github/workflows/tests.yml (verified current contents, 2026-08-09)
name: tests

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      - name: Verify the environment is genuinely working
        run: python scripts/check_env.py
      - name: Citation-format guard
        run: python scripts/check_citation_format.py
      - name: Documented-counts guard
        run: python scripts/check_documented_counts.py
      - name: Python-support-claim guard
        run: python scripts/check_python_support_claim.py
      - name: Constitution Rules 7 and 8 guard
        run: python scripts/check_forbidden_packages.py
      - name: Guard-wiring guard
        run: python scripts/check_guard_wiring.py
      - name: Build guards
        run: python scripts/verify_build.py --quick
      - name: Simulation engine tests
        working-directory: Caterva
        run: python -m pytest -v
      - name: Literature layer tests
        working-directory: Tests
        run: python -m pytest -v
      - name: Silent-skip guard
        run: python scripts/check_no_silent_skips.py

  api-server:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      - name: Install pnpm
        run: corepack prepare pnpm@11.4.0 --activate
      - name: Install workspace dependencies
        working-directory: Science-Agent-Pipeline
        run: pnpm install --frozen-lockfile
      - name: Application layer tests
        working-directory: Science-Agent-Pipeline
        run: pnpm --filter @workspace/api-server run test
```

The `test` job runs the Python 3.10/3.12/3.13 matrix: the `caterva/tests` suite (970 cases
collected via `python3 -m pytest --collect-only -q`, verified 2026-08-09), the `Tests` suite
(289 cases collected the same way), and a series of "constitution guard" scripts
(`check_env.py`, `check_citation_format.py`, `check_documented_counts.py`,
`check_python_support_claim.py`, `check_forbidden_packages.py`, `check_guard_wiring.py`,
`verify_build.py --quick`, `check_no_silent_skips.py`) that enforce repo-specific invariants
(no forbidden packages, documented counts match reality, no silently-skipped tests, etc.).
The `api-server` job runs this package's 404 vitest cases via
`pnpm --filter @workspace/api-server run test`. There is no `typecheck` or `lint` CI step for
the api-server today, no dependency audit step, and no coverage upload of any kind.

### Pre-Commit Checks

**Not currently implemented.** There is no `.husky/` directory, no `.git/hooks/pre-commit`
script, and no `prepare`/`setup:hooks` script in `package.json`. If you want local
pre-commit checks, running the real scripts by hand is the current option:

```bash
# Manual equivalent — no automated hook exists yet
pnpm run typecheck
pnpm test
```

There is no `lint` script in this repo (no ESLint config was found), so a lint step cannot be
run today.

### PR Checks

**Requirements for merge (informal — not all of these are enforced by CI today):**
- Tests pass: the `tests` workflow's `test` and `api-server` jobs are the only automated gate;
  it does not check coverage (none is measured) or run a linter (none is configured).
- No new TypeScript errors — not currently checked in CI (no `typecheck` step in either job);
  run `pnpm run typecheck` locally before opening a PR.
- Code review approved, no undocumented breaking changes — process expectations, not
  CI-enforced.

---

## Deployment Stages

### 1. Development (Local)

```bash
pnpm run dev
# Real script: "export NODE_ENV=development && pnpm run build && pnpm run start"
```

### 2. Staging (Pre-Production)

```bash
# Build
pnpm run build

# Deploy to staging environment
docker build -t caterva-api:staging .
docker push registry.example.com/caterva-api:staging

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

- [ ] `pnpm test` passes
- [ ] `pnpm run typecheck` passes
- [ ] Added tests for new features
- [ ] Updated documentation if needed

(There is no `lint` script in this repo — no ESLint config exists — so linting is not part
of this checklist today.)

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

**Not currently implemented.** There is no `benchmark` script in `package.json` and no
baseline-comparison tooling in this repo. The `wrk`-based load test above is the closest
thing to a performance test that currently exists (and it's a manual, ad hoc procedure, not
wired into any script or CI job).

### Stress Testing

```bash
# Run load test to failure
wrk -t8 -c500 -d5m --script scenario.lua http://localhost:5000/api

# Watch logs for errors
sudo journalctl -u caterva-api -f
```

---

## Test Data Management

### Fixtures

**Not currently implemented.** There is no `src/__tests__/fixtures/` directory and no
`fixtures/queries.ts` file in this repo. Test data today is defined inline in each test file
(e.g. the `GOLDEN` object shown earlier, or literal query strings written directly in `it(...)`
blocks) rather than centralized in a shared fixtures module. The pattern below is a reasonable
proposal for reducing duplication if the test suite grows, but describes no code that exists:

```typescript
// PROPOSED — src/__tests__/fixtures/queries.ts does not exist
export const testQueries = {
  sir_basic: {
    query: "SIR beta=0.5 gamma=0.1 S0=900",
    expectedDomain: "sir",
    expectedParams: { beta: 0.5, gamma: 0.1, s0: 900 }
  },
  // ...
};
```

### Mocking External Services

Real tests mock `../lib/scienceAgent` (`resolveKineticValue`) and `../lib/llmResolver`
(`resolveQueryWithLLM`) — not a `classifyDomain` function, which doesn't exist in
`llmResolver.ts`. Actual pattern, adapted from `src/__tests__/llmOrigin.test.ts`:

```typescript
vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return { ...original, resolveQueryWithLLM: vi.fn() };
});

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn(async () => ({ found: false })) };
});
```

The database is accessed via `getDb`/`isDbAvailable` imported from the `@workspace/db`
workspace package (`src/routes/simulate.ts`), not a local `../db` module — there is no
`src/db.ts` or `src/db/` in this package to mock directly.

---

## Regression Testing

### Strategy

1. **Golden tests** (inline trajectory comparison — `gillespieGolden.test.ts`,
   `gillespieBimolecularGolden.test.ts`; see "Golden Tests" above)
2. ~~Snapshot tests~~ — **not in use.** No test in this repo calls `toMatchSnapshot()` or
   `toMatchInlineSnapshot()`, so `vitest`'s `--update-snapshots` flag has nothing to act on
   here today.
3. **Property/contract tests** (e.g. `llmProviders.test.ts` checking the Python/TypeScript
   domain-list contract; see "Contract Tests" above)

### Detecting Regressions

In practice, a regression shows up as one of the 404 existing test cases failing. There's no
snapshot workflow to run; the process is: run `pnpm test`, investigate any failure, and either
fix the code (unintended change) or hand-edit the relevant `GOLDEN`/expected-value constant in
the test file (intended change, e.g. an updated solver).

---

## Security Testing

**Proposed — not currently implemented.** There is no `validateInput` function anywhere in
`src/`, and no dedicated `*.security.test.ts` file exercising these payloads today. The
closest real validation is the Zod `ResolveBody` schema in `src/lib/schemas.ts` (length/type
bounds) and the parameterized-query / no-shell-exec properties described in
`SECURITY_HARDENING.md` sections 1 and 2. The examples below are a reasonable shape for
security-specific tests to add, not a description of what exists:

```typescript
// PROPOSED — no validateInput() function exists in src/ today
it("rejects oversized query", () => {
  const huge = "a".repeat(10000);
  expect(() => validateInput(huge)).toThrow();
});
```

### Dependency Scanning

This is a pnpm workspace (see "Running Tests" above) — the npm-specific commands below don't
apply directly:

```bash
# Check for vulnerabilities
pnpm audit

# Update vulnerable packages
pnpm audit --fix

# Or in CI (fail on critical) — not currently wired into any workflow
pnpm audit --audit-level moderate --prod
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

**No dashboard currently exists.** `--reporter=json` is a real vitest flag and can be used to
produce machine-readable output; there is just nothing in this repo yet that consumes it:

```bash
pnpm test -- --reporter=json > test-results.json
# Track over time (proposed, no dashboard wired up yet):
# - Test count, pass rate, flaky tests
# (per-component coverage is not tracked — see "Test Quality Metrics" above)
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

- Test files: `src/__tests__/` and `src/lib/*.test.ts`
- Package.json scripts (pnpm): `dev`, `build`, `start`, `test`, `test:watch`, `typecheck`
- CI config: `.github/workflows/tests.yml` (root of the Caterva repo)
- Performance guide: `PERFORMANCE_GUIDE.md`

---

**Status:** 404 vitest test cases across 28 files (`artifacts/api-server`), counted by running
`npx vitest run` on 2026-08-09 — see "Coverage" note at the top of this doc.  
**Last updated:** August 9, 2026  
**Coverage target:** >90% on critical paths  
**Next review:** August 23, 2026
