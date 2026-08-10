# Developer Experience & Architecture Guide

## Quick Reference: Common Patterns

### Adding a New Validation

**Pattern:** Use type guard validators

```typescript
// Define once, reuse everywhere
function isValidParameter(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

// Use it
if (isValidParameter(value)) {
  // TypeScript knows value: number here
}
```

### Creating a New Factory

**Pattern:** Consistent object creation

```typescript
// Extract the shape
interface MyResult {
  status: string;
  message: string;
  data?: any;
}

// Create factory
function createMyResult(
  status: string,
  message: string,
  data?: any
): MyResult {
  return { status, message, data };
}

// Use everywhere
return createMyResult('error', 'Failed to fetch', null);
```

### Implementing Status Checks

**Pattern:** Set-based predicates

```typescript
// Define set at module level
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);

// Create predicate
function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

// Use it
if (isTerminal(job.status)) {
  // Handle terminal state
}
```

### Extracting Common Logic

**Pattern:** Helper functions for repeated patterns

```typescript
// Before: Repeated code
const locators = [...];
const doi = locators.find((l) => l.kind === 'doi')?.value;
const pmid = locators.find((l) => l.kind === 'pubmed')?.value;

// After: Helper function
function findLocatorValue(locators, kind) {
  return locators.find((l) => l.kind === kind)?.value;
}

// Usage
const doi = findLocatorValue(locators, 'doi');
const pmid = findLocatorValue(locators, 'pubmed');
```

---

## Architectural Principles

### 1. Single Responsibility Principle (SRP)
Each function/class has one reason to change.

**Good:**
```typescript
// Validation is one concern
function isValidFiniteNumber(value): value is number { ... }

// Creation is another concern
function createResult(data): Result { ... }
```

**Bad:**
```typescript
// Mixing validation and creation
function validateAndCreateResult(value) {
  if (!Number.isFinite(value)) return null;
  return { value };
}
```

### 2. DRY (Don't Repeat Yourself)
If code appears 3+ times, extract it.

**Pattern Detection:**
- Same condition in 3+ places → Extract to predicate
- Same object structure in 3+ places → Extract to factory
- Same type check in 3+ places → Extract to validator

### 3. Dependency Inversion
Depend on abstractions, not concrete implementations.

**Good:**
```typescript
type ValidatorFn = (value: unknown) => boolean;
function processValue(value: unknown, validator: ValidatorFn) {
  if (validator(value)) { ... }
}
```

**Bad:**
```typescript
function processValue(value: unknown) {
  if (typeof value === "number") { ... }
  // Hard-coded concrete check
}
```

### 4. Composition Over Inheritance
Build complex behavior by combining simple parts.

**Good:**
```typescript
function isValidNumberArray(value): value is number[] {
  return Array.isArray(value) && value.every(isValidFiniteNumber);
}
```

**Bad:**
```typescript
class NumberValidator extends Validator {
  // Inheritance hierarchy
}
```

---

## Error Handling Philosophy

### Principles
1. **Be Specific:** Error types matter
2. **Be Helpful:** Include context
3. **Be Consistent:** Same pattern everywhere

### Pattern: Structured Errors

```typescript
// Define error shape
interface AppError {
  code: string;           // Machine-readable
  message: string;        // Human-readable
  statusCode: number;     // HTTP status
  context?: Record<...>; // Debug info
}

// Throw with context
throw new RequiredParametersMissingError(
  ['km', 'vmax'],
  { domain: 'mm', supplied: ['s0'] }
);

// Handle consistently
if (err instanceof RequiredParametersMissingError) {
  res.status(err.statusCode).json({
    error: err.code,
    message: err.message,
    missing: err.context?.missing
  });
}
```

---

## Testing Philosophy

### Test Pyramid

```
        △ E2E Tests
       △△ Integration Tests
      △△△ Unit Tests
```

**Unit Tests (Many):** Test individual helpers in isolation  
**Integration Tests (Some):** Test helper interactions  
**E2E Tests (Few):** Test complete request flows

### Naming Convention

```typescript
describe('[UnitType]', () => {
  it('should [action] when [condition]', () => {
    // arrange
    const input = ...;
    
    // act
    const result = functionUnderTest(input);
    
    // assert
    expect(result).toBe(expected);
  });
});
```

### Testing Helpers

Each helper should have:

```typescript
describe('helperName', () => {
  // Happy path
  it('should return value for valid input', () => { ... });
  
  // Edge cases
  it('should handle null input', () => { ... });
  it('should handle undefined input', () => { ... });
  it('should handle empty input', () => { ... });
  
  // Error conditions
  it('should reject invalid input', () => { ... });
  
  // Type narrowing (for type guards)
  it('narrows type correctly', () => { ... });
});
```

---

## Code Review Checklist

### Before Submitting a PR

- [ ] No TypeScript errors: `pnpm run typecheck` (repo is pnpm-only; the
      real `api-server/package.json` script is `typecheck`, no dash -- there
      is no `type-check` script)
- [ ] Tests pass: `pnpm test`
- [ ] Linting: **not currently set up** -- no ESLint config and no `lint`
      script exist anywhere in this repo, so there is nothing to run yet.
      An earlier version of this checklist told readers to run `npm run
      lint`, which fails with "missing script" every time.
- [ ] No duplicated code (check for 3+ instance rule)
- [ ] All helpers are testable and tested
- [ ] Error messages are specific and helpful
- [ ] No magic strings/numbers (use named constants)
- [ ] Functions have JSDoc for complex logic

### For Reviewers

- [ ] Does this follow existing patterns?
- [ ] Could this be extracted to a helper?
- [ ] Are errors handled consistently?
- [ ] Is type safety maintained?
- [ ] Could this be tested better?

---

## File Organization Strategy

### By Concern (Recommended)
```
src/lib/
├── validators/          # All validation logic
│   ├── kinetic.ts
│   ├── numeric.ts
│   └── parameters.ts
├── factories/           # All object creation
│   ├── results.ts
│   ├── errors.ts
│   └── provenance.ts
├── helpers/             # All utility helpers
│   ├── locators.ts
│   ├── jobs.ts
│   └── queries.ts
└── domain/              # Domain logic
    ├── queryResolver.ts
    ├── llmResolver.ts
    └── scienceAgent.ts
```

### Current Organization (As Shipped)
```
src/lib/
├── [Logic files]        # Each concern in one file
├── cache.ts
├── queue.ts
└── ...
```

**Note:** Both work; current organization is fine given file sizes.

---

## Performance Optimization Guide

### When to Optimize

1. **Measure First:** Use metrics, don't guess
2. **Profile:** Identify actual bottlenecks
3. **Optimize:** Focus on hot paths
4. **Verify:** Measure improvement

### Common Patterns

**Object Allocation in Loops:**
```typescript
// Before: Allocates in every iteration
for (const item of items) {
  const result = { ...item, processed: true };
  results.push(result);
}

// After: Accumulate, spread once
const updates = {};
for (const item of items) {
  updates[item.id] = item;
}
results = { ...results, ...updates };
```

**Repeated Calculations:**
```typescript
// Before: Recalculates every time
function process(data) {
  return data.filter((x) => isValid(x)); // isValid recalculates
}

// After: Cache intermediate results
const validItems = new Set(data.filter(isValid).map(x => x.id));
function process(data) {
  return data.filter((x) => validItems.has(x.id));
}
```

**Module-Level Initialization:**
```typescript
// Before: Creates every time
function getConfig() {
  const SUPPORTED_DOMAINS = ['mm', 'sir', ...];
  return SUPPORTED_DOMAINS;
}

// After: Create once
const SUPPORTED_DOMAINS = ['mm', 'sir', ...];
function getConfig() {
  return SUPPORTED_DOMAINS;
}
```

---

## Debugging Guide

### Using the Logger

```typescript
import { logger } from './logger';

// Info: Normal operation tracking
logger.info({ query }, 'Resolving query');

// Warn: Recoverable issues
logger.warn({ missing }, 'Parameters not found');

// Error: Exception handling
logger.error({ err, jobId }, 'Job failed');
```

### Common Issues & Solutions

**Issue: Type narrowing not working**
```typescript
// Wrong: TypeScript doesn't narrow
if (typeof value === "number" && Number.isFinite(value)) {
  // value is still unknown here
}

// Right: Use type guard
function isValidFiniteNumber(v): v is number {
  return typeof v === "number" && Number.isFinite(v);
}
if (isValidFiniteNumber(value)) {
  // value is number here
}
```

**Issue: Object spreading in loop**
```typescript
// Wrong: Allocates N times
for (const item of items) {
  params = { ...params, [key]: item };
}

// Right: Accumulate then spread
const updates = {};
for (const item of items) {
  updates[key] = item;
}
params = { ...params, ...updates };
```

**Issue: Repeated validation**
```typescript
// Wrong: Same check in 3+ places
if (typeof x === "number" && Number.isFinite(x)) { ... }
if (typeof x === "number" && Number.isFinite(x)) { ... }

// Right: Extract validator
const validator = isValidFiniteNumber(x);
if (validator) { ... }
```

---

## Contribution Workflow

### Step 1: Understand Current State
```bash
pnpm run typecheck  # Verify no TS errors (real script name is "typecheck", no dash)
pnpm test           # Run existing tests
```

### Step 2: Implement Changes
- Follow patterns from existing code
- Extract helpers if repeating 3+ times
- Create type guards for validation

### Step 3: Add Tests
```typescript
describe('newFunction', () => {
  it('should handle happy path', () => { ... });
  it('should handle edge cases', () => { ... });
  it('should reject invalid input', () => { ... });
});
```

### Step 4: Verify Quality
```bash
pnpm run typecheck # Verify types (real script name; there is no "type-check")
pnpm test          # Run all tests
# There is no lint script or ESLint config in this repo yet -- skip this
# step until one exists rather than run a command that doesn't exist.
```

### Step 5: Document
- Add JSDoc for complex functions
- Update README if needed
- Link related ADRs if applicable

---

## Decision Records (ADRs)

### When to Write an ADR
- Significant architectural decision
- Decision between multiple approaches
- Choice affects multiple files/teams
- May need to be revisited later

### ADR Template

```markdown
# ADR-000: [Decision Title]

## Status
Proposed / Accepted / Deprecated

## Context
[Why this decision was needed]

## Decision
[What was decided]

## Consequences
- Positive: [benefits]
- Negative: [tradeoffs]

## Alternatives Considered
- Alternative 1: [why not chosen]
- Alternative 2: [why not chosen]
```

### Existing ADRs
- ADR-0007: Python/TypeScript boundary contract (DISPATCH ↔ SimulationDomain)
- ADR-0008: Parameter provenance tracking
- ADR-0010: Assay conditions in STRENDA compliance
- ADR-0011: Parameter origin tiers (user, llm, default, resolved)
- ADR-0017: Disease parameter resolution
- ADR-0019: Kcat to Vmax bridging
- ADR-0020: R0 to beta/gamma bridging
- ADR-0021: Mutation rate provenance (mutation_rate not STRENDA-governed)

---

## Onboarding Checklist

### Day 1
- [ ] Read CONTRIBUTING.md
- [ ] Review CODE_QUALITY_IMPROVEMENTS_FINAL.md
- [ ] Understand validator pattern
- [ ] Understand factory pattern

### Day 2
- [ ] Review existing tests
- [ ] Run test suite locally
- [ ] Pick a small issue from backlog
- [ ] Submit first PR (review comment)

### Week 1
- [ ] Read all ADRs
- [ ] Understand error handling approach
- [ ] Understand caching strategy
- [ ] Understand metrics collection

### Week 2
- [ ] Contribute 2-3 PRs
- [ ] Review 2-3 PRs from teammates
- [ ] Attend architecture sync
- [ ] Ask questions, lots of them

---

## Quick Links

- **Patterns:** See "Common Patterns" section above
- **Testing:** See TESTING_AND_ROADMAP.md
- **Architecture:** See COMPLETE_REFACTORING_SUMMARY.md
- **Quality:** See CODE_QUALITY_IMPROVEMENTS_FINAL.md
- **Roadmap:** See TESTING_AND_ROADMAP.md (Phase 4+)

---

## Getting Help

### Code Questions
- Ask in code review comments
- Reference related patterns in this guide
- Link to existing examples

### Architecture Questions
- Review relevant ADRs
- Check existing implementations
- Ask in architecture sync

### Performance Questions
- Profile with metrics
- Review performance optimization guide
- Check existing optimizations

### General Questions
- Check CONTRIBUTING.md
- Search documentation
- Ask team leads
