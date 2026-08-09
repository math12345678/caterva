# Comprehensive Test Suite Blueprint

## Test Implementation Priority & Examples

### Tier 1: Critical Path (Implement First)

#### Unit Tests: Validators

```typescript
// File: src/lib/__tests__/validators.test.ts

import {
  isValidFiniteNumber,
  isValidNonEmptyString,
  isValidNumberArray,
  isValidFiniteNumberArray
} from '../validators';

describe('Validators Suite', () => {
  describe('isValidFiniteNumber', () => {
    describe('positive cases', () => {
      it('accepts zero', () => {
        expect(isValidFiniteNumber(0)).toBe(true);
      });

      it('accepts positive integers', () => {
        expect(isValidFiniteNumber(1)).toBe(true);
        expect(isValidFiniteNumber(999999)).toBe(true);
      });

      it('accepts positive decimals', () => {
        expect(isValidFiniteNumber(3.14159)).toBe(true);
        expect(isValidFiniteNumber(0.0001)).toBe(true);
      });

      it('accepts negative numbers', () => {
        expect(isValidFiniteNumber(-1)).toBe(true);
        expect(isValidFiniteNumber(-3.14)).toBe(true);
      });

      it('accepts very small numbers', () => {
        expect(isValidFiniteNumber(1e-100)).toBe(true);
      });

      it('accepts very large numbers', () => {
        expect(isValidFiniteNumber(1e100)).toBe(true);
      });
    });

    describe('negative cases', () => {
      it('rejects NaN', () => {
        expect(isValidFiniteNumber(NaN)).toBe(false);
      });

      it('rejects Infinity', () => {
        expect(isValidFiniteNumber(Infinity)).toBe(false);
        expect(isValidFiniteNumber(-Infinity)).toBe(false);
      });

      it('rejects strings', () => {
        expect(isValidFiniteNumber("5")).toBe(false);
        expect(isValidFiniteNumber("3.14")).toBe(false);
      });

      it('rejects null and undefined', () => {
        expect(isValidFiniteNumber(null)).toBe(false);
        expect(isValidFiniteNumber(undefined)).toBe(false);
      });

      it('rejects objects and arrays', () => {
        expect(isValidFiniteNumber({})).toBe(false);
        expect(isValidFiniteNumber([])).toBe(false);
      });

      it('rejects booleans', () => {
        expect(isValidFiniteNumber(true)).toBe(false);
        expect(isValidFiniteNumber(false)).toBe(false);
      });
    });

    describe('type narrowing', () => {
      it('narrows type to number in conditional', () => {
        const value: unknown = 5;
        if (isValidFiniteNumber(value)) {
          // TypeScript should know value is number
          const result: number = value + 1;
          expect(result).toBe(6);
        }
      });
    });
  });

  describe('isValidNonEmptyString', () => {
    describe('positive cases', () => {
      it('accepts non-empty strings', () => {
        expect(isValidNonEmptyString("hello")).toBe(true);
        expect(isValidNonEmptyString("a")).toBe(true);
      });

      it('rejects whitespace-only strings', () => {
        expect(isValidNonEmptyString("   ")).toBe(false);
        expect(isValidNonEmptyString("\t")).toBe(false);
        expect(isValidNonEmptyString("\n")).toBe(false);
      });

      it('rejects empty string', () => {
        expect(isValidNonEmptyString("")).toBe(false);
      });

      it('rejects non-strings', () => {
        expect(isValidNonEmptyString(123)).toBe(false);
        expect(isValidNonEmptyString(null)).toBe(false);
        expect(isValidNonEmptyString(undefined)).toBe(false);
      });
    });
  });

  describe('isValidNumberArray', () => {
    describe('positive cases', () => {
      it('accepts arrays of finite numbers', () => {
        expect(isValidNumberArray([1, 2, 3])).toBe(true);
        expect(isValidNumberArray([0])).toBe(true);
        expect(isValidNumberArray([-1, -2, -3])).toBe(true);
      });

      it('accepts empty array', () => {
        expect(isValidNumberArray([])).toBe(true);
      });

      it('accepts arrays with decimals', () => {
        expect(isValidNumberArray([1.5, 2.5, 3.5])).toBe(true);
      });
    });

    describe('negative cases', () => {
      it('rejects array with NaN', () => {
        expect(isValidNumberArray([1, NaN, 3])).toBe(false);
      });

      it('rejects array with Infinity', () => {
        expect(isValidNumberArray([1, Infinity])).toBe(false);
        expect(isValidNumberArray([1, -Infinity])).toBe(false);
      });

      it('rejects non-arrays', () => {
        expect(isValidNumberArray("123")).toBe(false);
        expect(isValidNumberArray(123)).toBe(false);
        expect(isValidNumberArray(null)).toBe(false);
        expect(isValidNumberArray(undefined)).toBe(false);
      });

      it('rejects array with non-numbers', () => {
        expect(isValidNumberArray([1, "2", 3])).toBe(false);
        expect(isValidNumberArray([1, null, 3])).toBe(false);
      });
    });
  });
});
```

#### Unit Tests: Factories

```typescript
// File: src/lib/__tests__/factories.test.ts

import {
  createVerificationResult,
  notFoundResult,
  createViolation
} from '../factories';

describe('Factory Functions', () => {
  describe('createVerificationResult', () => {
    it('creates complete result with all fields', () => {
      const result = createVerificationResult(
        'verified',
        'Test message',
        0.95,
        false
      );

      expect(result).toEqual({
        level: 'verified',
        message: 'Test message',
        reference: undefined,
        confidence: 0.95,
        requiresManualReview: false
      });
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

    it('handles all verification levels', () => {
      const levels = ['verified', 'flagged', 'pending', 'unverifiable'] as const;
      levels.forEach(level => {
        const result = createVerificationResult(level, 'msg', 0.5, false);
        expect(result.level).toBe(level);
      });
    });

    it('maintains confidence range 0-1', () => {
      expect(createVerificationResult('verified', 'msg', 0, false).confidence).toBe(0);
      expect(createVerificationResult('verified', 'msg', 1, false).confidence).toBe(1);
      expect(createVerificationResult('verified', 'msg', 0.5, false).confidence).toBe(0.5);
    });
  });

  describe('notFoundResult', () => {
    it('creates not-found result', () => {
      const result = notFoundResult('Entity not found');

      expect(result).toEqual({
        found: false,
        literatureCandidates: [],
        logs: ['Entity not found']
      });
    });

    it('preserves message', () => {
      const message = 'Custom not found message';
      const result = notFoundResult(message);
      expect(result.logs[0]).toBe(message);
    });
  });

  describe('createViolation', () => {
    it('creates violation with all fields', () => {
      const violation = createViolation(
        1,
        'pH',
        'pH not provided'
      );

      expect(violation).toEqual({
        requirement: 1,
        field: 'pH',
        message: 'pH not provided'
      });
    });

    it('maintains requirement numbering', () => {
      for (let i = 1; i <= 7; i++) {
        const v = createViolation(i, `field${i}`, `msg${i}`);
        expect(v.requirement).toBe(i);
      }
    });
  });
});
```

#### Unit Tests: Predicates

```typescript
// File: src/lib/__tests__/predicates.test.ts

import {
  isTerminal,
  isPersistable
} from '../predicates';
import type { Job, JobStatus } from '../queue';

describe('Predicates', () => {
  describe('isTerminal', () => {
    it('identifies terminal statuses', () => {
      expect(isTerminal('completed')).toBe(true);
      expect(isTerminal('failed')).toBe(true);
      expect(isTerminal('cancelled')).toBe(true);
    });

    it('rejects non-terminal statuses', () => {
      expect(isTerminal('pending')).toBe(false);
      expect(isTerminal('resolving')).toBe(false);
      expect(isTerminal('validating')).toBe(false);
      expect(isTerminal('running')).toBe(false);
    });
  });

  describe('isPersistable', () => {
    const mockResult = {
      runId: 'run-1',
      domain: 'mm' as const,
      parameters: { km: 5 },
      trajectory: [],
      provenance: {
        reasoning: 'test',
        modelCitations: [],
        flags: []
      },
      parameterProvenance: {}
    };

    const mockError = {
      error: 'TEST_ERROR',
      message: 'Test error message'
    };

    it('returns true for completed jobs with result', () => {
      const job: Job = {
        jobId: '1',
        query: 'test',
        status: 'completed',
        progress: 100,
        result: mockResult,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(isPersistable(job)).toBe(true);
    });

    it('returns true for failed jobs with error', () => {
      const job: Job = {
        jobId: '2',
        query: 'test',
        status: 'failed',
        progress: 100,
        error: mockError,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(isPersistable(job)).toBe(true);
    });

    it('returns true for cancelled jobs with result', () => {
      const job: Job = {
        jobId: '3',
        query: 'test',
        status: 'cancelled',
        progress: 50,
        result: mockResult,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(isPersistable(job)).toBe(true);
    });

    it('returns false for non-terminal jobs', () => {
      const job: Job = {
        jobId: '4',
        query: 'test',
        status: 'running',
        progress: 50,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(isPersistable(job)).toBe(false);
    });

    it('returns false for terminal jobs without result or error', () => {
      const job: Job = {
        jobId: '5',
        query: 'test',
        status: 'completed',
        progress: 100,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      expect(isPersistable(job)).toBe(false);
    });
  });
});
```

### Tier 2: Integration Tests

```typescript
// File: src/__tests__/integration/query-resolution.test.ts

import { resolveQuery } from '../lib/queryResolver';
import { findCachedResultByQuery } from '../lib/cache';

describe('Query Resolution Integration', () => {
  describe('end-to-end resolution', () => {
    it('resolves michaelis-menten query completely', async () => {
      const result = await resolveQuery('lactate dehydrogenase km=5 vmax=10');

      expect(result).toHaveProperty('runId');
      expect(result.domain).toBe('mm');
      expect(result.parameters).toHaveProperty('km', 5);
      expect(result.parameters).toHaveProperty('vmax', 10);
      expect(result.parameterProvenance).toBeDefined();
    });

    it('consolidates provenance correctly', async () => {
      const result = await resolveQuery('mm test');

      // Every parameter should have provenance
      Object.keys(result.parameters).forEach(key => {
        expect(result.parameterProvenance).toHaveProperty(key);
        expect(result.parameterProvenance[key].origin).toMatch(/user|llm|default|resolved/);
      });
    });

    it('accumulates flags without duplication', async () => {
      const result = await resolveQuery('enzyme test');

      // Flags should be unique
      const uniqueFlags = new Set(result.provenance.flags);
      expect(uniqueFlags.size).toBe(result.provenance.flags.length);
    });
  });

  describe('cache integration', () => {
    it('caches identical queries', async () => {
      const query = 'lactate dehydrogenase km=5';

      const result1 = await resolveQuery(query);
      const cachedResult = findCachedResultByQuery(query);

      expect(cachedResult).toBeDefined();
      expect(cachedResult?.domain).toBe(result1.domain);
    });

    it('normalizes query strings for caching', async () => {
      const query1 = 'lactate   dehydrogenase';
      const query2 = 'lactate dehydrogenase'; // normalized version

      await resolveQuery(query1);
      const cached = findCachedResultByQuery(query2);

      expect(cached).toBeDefined();
    });
  });
});
```

### Tier 3: E2E Tests

```typescript
// File: src/__tests__/e2e/simulate.e2e.test.ts

import request from 'supertest';
import app from '../app';

describe('Simulation E2E', () => {
  describe('POST /api/simulate', () => {
    it('enqueues job and returns 202', async () => {
      const response = await request(app)
        .post('/api/simulate')
        .send({ query: 'michaelis menten enzyme' });

      expect(response.status).toBe(202);
      expect(response.body).toHaveProperty('jobId');
      expect(response.body).toHaveProperty('status', 'pending');
    });

    it('validates required fields', async () => {
      const response = await request(app)
        .post('/api/simulate')
        .send({});

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('error');
    });

    it('applies rate limiting', async () => {
      const requests = Array(15).fill(null).map(() =>
        request(app)
          .post('/api/simulate')
          .send({ query: 'test' })
      );

      const responses = await Promise.all(requests);
      const rateLimited = responses.filter(r => r.status === 429);

      expect(rateLimited.length).toBeGreaterThan(0);
    });
  });

  describe('GET /api/simulate/:jobId', () => {
    it('returns job status', async () => {
      const createRes = await request(app)
        .post('/api/simulate')
        .send({ query: 'test' });

      const jobId = createRes.body.jobId;

      const getRes = await request(app)
        .get(`/api/simulate/${jobId}`);

      expect(getRes.status).toBe(200);
      expect(getRes.body).toHaveProperty('jobId', jobId);
      expect(getRes.body).toHaveProperty('status');
    });
  });
});
```

## Test Configuration

### Jest Setup

```json
{
  "jest": {
    "preset": "ts-jest",
    "testEnvironment": "node",
    "roots": ["<rootDir>/src"],
    "testMatch": ["**/__tests__/**/*.test.ts"],
    "collectCoverageFrom": [
      "src/**/*.ts",
      "!src/**/*.d.ts",
      "!src/**/*.test.ts"
    ],
    "coverageThreshold": {
      "global": {
        "branches": 90,
        "functions": 90,
        "lines": 90,
        "statements": 90
      },
      "./src/lib/validators.ts": {
        "branches": 100,
        "functions": 100,
        "lines": 100,
        "statements": 100
      }
    }
  }
}
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific file
npm test -- validators.test.ts

# Watch mode
npm test -- --watch

# Update snapshots
npm test -- -u
```

## Coverage Goals by Category

| Category | Target | Current |
|----------|--------|---------|
| Validators | 100% | To implement |
| Factories | 100% | To implement |
| Predicates | 100% | To implement |
| Helpers | 95% | To implement |
| Routes | 85% | To implement |
| Integration | 80% | To implement |
| E2E | 70% | To implement |

## Test Maintenance

### Weekly Tasks
- [ ] Review coverage reports
- [ ] Add tests for new functions
- [ ] Fix flaky tests
- [ ] Update test data

### Monthly Tasks
- [ ] Review test strategy
- [ ] Identify untested code paths
- [ ] Refactor test helpers
- [ ] Update documentation

### Quarterly Tasks
- [ ] Performance benchmark tests
- [ ] Load testing
- [ ] Security testing
- [ ] Regression test review
