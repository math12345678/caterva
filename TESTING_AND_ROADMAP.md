# Testing Strategy & Future Roadmap

## Testing Infrastructure Requirements

### Phase 1: Unit Tests for Extracted Helpers

#### Validators (Priority: High)
**Files: queryResolver.ts, provenance.ts, simulate.ts, strenda-validator.ts**

```typescript
// isValidFiniteNumber() tests
describe('isValidFiniteNumber', () => {
  it('returns true for finite positive numbers', () => {
    expect(isValidFiniteNumber(5)).toBe(true);
    expect(isValidFiniteNumber(0)).toBe(true);
    expect(isValidFiniteNumber(-5)).toBe(true);
  });

  it('returns false for non-finite numbers', () => {
    expect(isValidFiniteNumber(NaN)).toBe(false);
    expect(isValidFiniteNumber(Infinity)).toBe(false);
    expect(isValidFiniteNumber(-Infinity)).toBe(false);
  });

  it('returns false for non-numbers', () => {
    expect(isValidFiniteNumber("5")).toBe(false);
    expect(isValidFiniteNumber(null)).toBe(false);
    expect(isValidFiniteNumber(undefined)).toBe(false);
  });
});

// isValidNumberArray() tests
describe('isValidNumberArray', () => {
  it('returns true for arrays of finite numbers', () => {
    expect(isValidNumberArray([1, 2, 3])).toBe(true);
    expect(isValidNumberArray([0])).toBe(true);
    expect(isValidNumberArray([])).toBe(true);
  });

  it('returns false if any element is non-finite', () => {
    expect(isValidNumberArray([1, NaN, 3])).toBe(false);
    expect(isValidNumberArray([1, Infinity])).toBe(false);
  });

  it('returns false for non-arrays', () => {
    expect(isValidNumberArray("123")).toBe(false);
    expect(isValidNumberArray(null)).toBe(false);
  });
});
```

#### Factories (Priority: High)
**Files: queryResolver.ts, literature-verifier.ts, scienceAgent.ts**

```typescript
// createVerificationResult() tests
describe('createVerificationResult', () => {
  it('creates result with all required fields', () => {
    const result = createVerificationResult(
      'verified',
      'Test message',
      0.95,
      false
    );
    expect(result.level).toBe('verified');
    expect(result.message).toBe('Test message');
    expect(result.confidence).toBe(0.95);
    expect(result.requiresManualReview).toBe(false);
  });

  it('includes optional reference field', () => {
    const ref = { doi: '10.1234/test', source: 'BRENDA' };
    const result = createVerificationResult(
      'flagged',
      'Message',
      0.8,
      false,
      ref
    );
    expect(result.reference).toBe(ref);
  });
});
```

#### Predicates (Priority: Medium)
**Files: cache.ts, queue.ts**

```typescript
// isTerminal() tests
describe('isTerminal', () => {
  it('returns true for terminal statuses', () => {
    expect(isTerminal('completed')).toBe(true);
    expect(isTerminal('failed')).toBe(true);
    expect(isTerminal('cancelled')).toBe(true);
  });

  it('returns false for non-terminal statuses', () => {
    expect(isTerminal('pending')).toBe(false);
    expect(isTerminal('running')).toBe(false);
    expect(isTerminal('resolving')).toBe(false);
  });
});

// isPersistable() tests
describe('isPersistable', () => {
  it('returns true for terminal jobs with result or error', () => {
    expect(isPersistable({
      jobId: '1',
      status: 'completed',
      result: { /* result */ },
      query: 'test',
      progress: 100
    })).toBe(true);

    expect(isPersistable({
      jobId: '2',
      status: 'failed',
      error: { error: 'E', message: 'M' },
      query: 'test',
      progress: 100
    })).toBe(true);
  });

  it('returns false for non-terminal jobs', () => {
    expect(isPersistable({
      jobId: '3',
      status: 'running',
      query: 'test',
      progress: 50
    })).toBe(false);
  });

  it('returns false for terminal jobs without result/error', () => {
    expect(isPersistable({
      jobId: '4',
      status: 'completed',
      query: 'test',
      progress: 100
      // no result or error
    })).toBe(false);
  });
});
```

#### Helpers (Priority: Medium)
**Files: simulate.ts, citeVerify.ts, queue.ts**

```typescript
// findLocatorValue() tests
describe('findLocatorValue', () => {
  it('finds locator by kind', () => {
    const locators = [
      { kind: 'doi', value: '10.1234/test' },
      { kind: 'url', value: 'https://example.com' }
    ];
    expect(findLocatorValue(locators, 'doi')).toBe('10.1234/test');
  });

  it('returns undefined for missing kind', () => {
    const locators = [{ kind: 'doi', value: '10.1234/test' }];
    expect(findLocatorValue(locators, 'pubmed')).toBeUndefined();
  });
});

// getOldestJob() tests
describe('getOldestJob', () => {
  it('returns oldest job matching predicate', () => {
    const jobs = [
      { jobId: '1', updatedAt: '2026-08-01', status: 'completed' },
      { jobId: '2', updatedAt: '2026-08-02', status: 'failed' },
      { jobId: '3', updatedAt: '2026-07-31', status: 'completed' }
    ];
    const oldest = getOldestJob(jobs, (j) => j.status === 'completed');
    expect(oldest?.jobId).toBe('3');
  });

  it('returns undefined if no matches', () => {
    const jobs = [{ jobId: '1', status: 'running' }];
    const oldest = getOldestJob(jobs, (j) => j.status === 'completed');
    expect(oldest).toBeUndefined();
  });
});
```

---

### Phase 2: Integration Tests for Refactored Functions

#### QueryResolver Integration
```typescript
describe('queryResolver - kinetic resolution', () => {
  it('applies kinetic resolution without repeating object spreads', async () => {
    const result = await resolveQuery('lactate dehydrogenase');
    
    expect(result.parameters).toBeDefined();
    expect(result.parameterProvenance).toBeDefined();
    expect(Object.keys(result.parameters))
      .toEqual(Object.keys(result.parameterProvenance));
  });

  it('consolidates provenance creation correctly', async () => {
    const result = await resolveQuery('ldh km=5');
    
    // Verify that unresolved kinetics use consolidated helper
    const unresolvedKeys = Object.entries(result.parameterProvenance)
      .filter(([_, p]) => p.origin === 'default' && !p.citation);
    
    unresolvedKeys.forEach(([_, p]) => {
      expect(p.note).toBeTruthy();
      expect(p.note).toMatch(/Could not resolve|no locator/);
    });
  });
});
```

#### Cache and Queue Integration
```typescript
describe('cache and queue - persistability', () => {
  it('only persists terminal jobs with results', async () => {
    const pendingJob = queue.createJob('test query');
    expect(await cache.persistJob(pendingJob)).toEqual(Promise.resolve());
    
    const completedJob = queue.setJobResult(pendingJob.jobId, mockResult);
    // Should actually persist now
    expect(cache.findCachedJob(completedJob.jobId)).toBeDefined();
  });

  it('terminal status check is consistent', () => {
    ['completed', 'failed', 'cancelled'].forEach(status => {
      expect(queue.isTerminal(status as JobStatus)).toBe(true);
    });
    
    ['pending', 'running', 'resolving'].forEach(status => {
      expect(queue.isTerminal(status as JobStatus)).toBe(false);
    });
  });
});
```

---

### Phase 3: Route Handler Tests

#### Error Handling Consistency
```typescript
describe('route handlers - error handling', () => {
  it('handles RequiredParametersMissingError consistently', async () => {
    const response = await request(app)
      .post('/api/resolve')
      .send({ query: 'mm' }); // Missing required params

    expect(response.status).toBe(422);
    expect(response.body).toHaveProperty('error', 'RequiredParametersMissingError');
    expect(response.body).toHaveProperty('missingKeys');
  });

  it('passes unhandled errors to global error handler', async () => {
    const response = await request(app)
      .post('/api/resolve')
      .send({ query: 'invalid' });

    // Should be caught by error handler, not crash
    expect(response.status).toBe(500);
  });
});
```

---

## Test Coverage Targets

### Critical Paths (100% coverage required)
- **Validators:** All type guards in simulate.ts, provenance.ts
- **Factories:** All factory functions across all files
- **Predicates:** Status checks, persistability logic
- **Error handling:** Required parameter errors, validation errors

### High Priority (>90% coverage)
- **Route handlers:** All endpoints
- **Query resolution:** All resolution steps
- **Cache operations:** Load, save, find operations

### Medium Priority (>80% coverage)
- **Metrics collection:** Stage tracking, domain tracking
- **Job queue:** Job creation, status updates, pruning

---

## Future Development Roadmap

### Phase 4: Route Handler Pattern Extraction (Q3 2026)

**Goal:** Consolidate try/catch/next pattern across all routes

```typescript
// Current pattern (repeated in all routes)
router.post("/path", async (req, res, next) => {
  try {
    // handler logic
  } catch (err) {
    next(err);
  }
});

// Proposed extraction
interface RouteHandler<T> {
  (req: Request<T>, res: Response): Promise<any>;
}

function asyncRoute<T>(handler: RouteHandler<T>) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      await handler(req, res);
    } catch (err) {
      next(err);
    }
  };
}

// Usage
router.post("/path", asyncRoute<T>(async (req, res) => {
  // handler logic without try/catch
}));
```

**Files to refactor:** All route handlers  
**Benefit:** Eliminates 40+ lines of repeated error handling

### Phase 5: Schema Validation Consolidation (Q3 2026)

**Goal:** Unified validation registry

```typescript
// Current: Scattered schema definitions
const ResolveBody = z.object({ query: z.string() });

// Proposed: Validation registry
interface ValidationRule {
  schema: ZodSchema;
  middleware?: Middleware[];
  errorHandler?: ErrorHandler;
}

class ValidationRegistry {
  private rules = new Map<string, ValidationRule>();

  register(endpoint: string, rule: ValidationRule) {
    this.rules.set(endpoint, rule);
  }

  getValidator(endpoint: string) {
    return this.rules.get(endpoint)?.schema;
  }
}
```

### Phase 6: Parameter Registry System (Q4 2026)

**Goal:** Centralized parameter metadata

```typescript
interface ParameterMetadata {
  name: string;
  type: 'scalar' | 'array';
  resolvable: boolean;
  literature: LiteratureReference[];
  defaults: Record<string, number>;
  validation?: ValidationRule;
}

class ParameterRegistry {
  private params = new Map<string, ParameterMetadata>();

  register(name: string, metadata: ParameterMetadata) {
    this.params.set(name, metadata);
  }

  getResolvable(domain: string): string[] {
    return Array.from(this.params.values())
      .filter(p => p.resolvable && isDomainSupported(domain))
      .map(p => p.name);
  }
}
```

### Phase 7: Error Hierarchy Refactoring (Q4 2026)

**Goal:** Structured error types with consistent handling

```typescript
// Current: Scattered error types
class RequiredParametersMissingError extends Error { ... }

// Proposed: Error hierarchy
abstract class BaseAppError extends Error {
  abstract statusCode: number;
  abstract errorCode: string;
  context?: Record<string, any>;
}

class RequiredParametersMissingError extends BaseAppError {
  statusCode = 422;
  errorCode = 'REQUIRED_PARAMETERS_MISSING';
  constructor(missing: string[]) {
    super(...);
    this.context = { missing };
  }
}

// Consistent error handler
app.use((err: Error, req, res, next) => {
  if (err instanceof BaseAppError) {
    return res.status(err.statusCode).json({
      error: err.errorCode,
      message: err.message,
      context: err.context
    });
  }
  // Default 500 handling
});
```

---

## Performance Optimization Targets

### 1. Caching Improvements
- Implement Redis layer for distributed caching
- Add cache versioning strategy
- Implement cache invalidation rules

### 2. Metrics Aggregation
- Move from in-memory to time-series database
- Implement real-time metrics streaming
- Add percentile calculations for latency

### 3. Query Resolution
- Cache LLM classification results
- Pre-warm domain keyword indices
- Implement parallel resolver pathways

### 4. Python Bridge
- Connection pooling for Tellurium spawning
- Reduce startup overhead
- Implement result caching layer

---

## Documentation Priorities

### High Priority
- [ ] Unit testing guide with examples
- [ ] Route handler patterns documentation
- [ ] Error handling strategy guide
- [ ] Performance benchmarking guide

### Medium Priority
- [ ] Metrics collection guide
- [ ] Cache strategy documentation
- [ ] LLM provider integration guide
- [ ] Literature resolver architecture

### Low Priority
- [ ] Historical decision records
- [ ] Troubleshooting guide
- [ ] Performance tuning guide

---

## Quality Metrics Dashboard

### Proposed Monitoring Targets

```typescript
interface QualityMetrics {
  // Code quality
  duplicateCodeBlocks: number;      // Target: 0
  extractedHelpers: number;          // Target: >50
  typeGuardCoverage: number;         // Target: 100%

  // Test quality
  unitTestCoverage: number;          // Target: >90%
  integrationTestCoverage: number;   // Target: >80%
  criticalPathCoverage: number;      // Target: 100%

  // Performance
  avgResolveLatencyMs: number;       // Target: <500ms
  avgSimulateLatencyMs: number;      // Target: <2000ms
  cacheHitRate: number;              // Target: >75%

  // Reliability
  errorRate: number;                 // Target: <0.1%
  documentationCoverage: number;     // Target: >95%
}
```

---

## Security Review Checklist

### Input Validation
- [ ] All route parameters validated with Zod
- [ ] SQL injection protection (N/A - no SQL layer)
- [ ] Command injection protection for Python bridge
- [ ] Rate limiting on all endpoints

### Data Protection
- [ ] Sensitive parameters not logged
- [ ] Cache contents sanitized
- [ ] Error messages don't leak implementation details
- [ ] Database credentials not in code

### Error Handling
- [ ] Stack traces not exposed to clients
- [ ] Failed auth attempts logged
- [ ] Rate limit bypasses impossible
- [ ] Timeouts implemented for long operations

### Dependencies
- [ ] npm/pip dependencies regularly updated
- [ ] Security advisories checked
- [ ] Test coverage for dependency updates

---

## Deployment Readiness Checklist

### Code Quality
- [x] Zero TypeScript errors
- [x] All helpers unit testable
- [x] Type coverage >95%
- [ ] All routes have error handlers
- [ ] All async operations have timeouts

### Documentation
- [ ] API documentation complete
- [ ] Deployment guide written
- [ ] Runbook for common issues
- [ ] Performance tuning guide

### Testing
- [ ] Unit tests >90% coverage
- [ ] Integration tests >80% coverage
- [ ] End-to-end tests for critical paths
- [ ] Load testing completed

### Operations
- [ ] Monitoring dashboard configured
- [ ] Alerting rules defined
- [ ] Logging strategy documented
- [ ] Backup/recovery procedures tested

---

## Conclusion

This refactoring establishes a strong foundation for:
1. **Scalability** through consistent patterns
2. **Testability** through modular helpers
3. **Maintainability** through centralized logic
4. **Performance** through optimized hot paths

The roadmap above outlines the natural progression toward a production-ready, enterprise-grade backend system.

**Current Status: Foundation Ready for Testing & Operations**
