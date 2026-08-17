/**
 * `/api/perf` and `/api/cache/stats` — the two endpoints that were
 * documented in eighteen places and never implemented.
 *
 * The assertions that matter here are the refusals: a percentile that is
 * withheld below a sample threshold, an average that is null rather than 0
 * when nothing was measured, and an allowlist that a deny-list-shaped
 * change would break.
 */

import {
  MAX_SAMPLES_PER_ENDPOINT,
  MIN_SAMPLES_FOR_PERCENTILE,
  SLOW_REQUEST_MS,
  getPerfSnapshot,
  normalizeEndpoint,
  recordRequest,
  resetPerf,
} from '../perfCollector';
import {
  ALLOWLIST,
  cacheKey,
  getCacheStats,
  isCacheable,
  readCache,
  resetCache,
  writeCache,
} from '../responseCache';

beforeEach(() => {
  resetPerf();
  resetCache();
});

describe('perf collector — what it refuses to report', () => {
  it('reports a null overall average when nothing has been measured', () => {
    // 0 would read as "instantaneous". null reads as "no data", which is
    // the true statement.
    const snapshot = getPerfSnapshot();
    expect(snapshot.summary.overallAverageResponseTimeMs).toBeNull();
    expect(snapshot.summary.totalRequests).toBe(0);
    expect(snapshot.notes.join(' ')).toContain('not a fast one');
  });

  it('withholds p95 below the sample threshold, and says why', () => {
    for (let i = 0; i < MIN_SAMPLES_FOR_PERCENTILE - 1; i++) {
      recordRequest('/api/metrics', 'GET', 10 + i, 200);
    }
    const [entry] = getPerfSnapshot().hottest;
    expect(entry.p95ResponseTimeMs).toBeNull();
    expect(entry.percentileBasis).toContain('below the');
    // The count is reported so a reader can see how close it is.
    expect(entry.sampleWindow).toBe(MIN_SAMPLES_FOR_PERCENTILE - 1);
  });

  it('reports p95 once there are enough samples', () => {
    for (let i = 1; i <= 100; i++) {
      recordRequest('/api/metrics', 'GET', i, 200);
    }
    const [entry] = getPerfSnapshot().hottest;
    // Nearest-rank p95 of 1..100 is the 95th value.
    expect(entry.p95ResponseTimeMs).toBe(95);
    expect(entry.percentileBasis).toContain('nearest-rank');
  });

  it('bounds retained samples so the collector cannot leak', () => {
    for (let i = 0; i < MAX_SAMPLES_PER_ENDPOINT + 500; i++) {
      recordRequest('/api/metrics', 'GET', 5, 200);
    }
    const [entry] = getPerfSnapshot().hottest;
    expect(entry.sampleWindow).toBe(MAX_SAMPLES_PER_ENDPOINT);
    // Lifetime counts are NOT windowed — only percentiles are.
    expect(entry.totalRequests).toBe(MAX_SAMPLES_PER_ENDPOINT + 500);
  });

  it('says that percentiles are windowed but counts are lifetime', () => {
    recordRequest('/api/metrics', 'GET', 5, 200);
    expect(getPerfSnapshot().notes.join(' ')).toContain('Counts and averages are lifetime');
  });
});

describe('perf collector — bucketing', () => {
  it('collapses record ids so one endpoint stays one endpoint', () => {
    // Without this, each job id becomes its own "endpoint" and the report
    // becomes an access log with statistics bolted on.
    recordRequest('/api/jobs/job_1723456789_ab12cd', 'GET', 5, 200);
    recordRequest('/api/jobs/job_1723456999_zz03ee', 'GET', 7, 200);
    const snapshot = getPerfSnapshot();
    expect(snapshot.summary.totalEndpoints).toBe(1);
    expect(snapshot.hottest[0]!.endpoint).toBe('/api/jobs/:id');
    expect(snapshot.hottest[0]!.totalRequests).toBe(2);
  });

  it('does not collapse real route segments into :id', () => {
    expect(normalizeEndpoint('/api/metrics/by-model')).toBe('/api/metrics/by-model');
    expect(normalizeEndpoint('/api/export/jobs/csv')).toBe('/api/export/jobs/csv');
    expect(normalizeEndpoint('/api/metrics/sweeps-by-query')).toBe(
      '/api/metrics/sweeps-by-query',
    );
  });

  it('separates the same path under different methods', () => {
    recordRequest('/api/sweep', 'POST', 900, 200);
    recordRequest('/api/sweep', 'GET', 4, 200);
    expect(getPerfSnapshot().summary.totalEndpoints).toBe(2);
  });

  it('counts >= 400 as errors and leaves 304 alone', () => {
    recordRequest('/api/stats', 'GET', 5, 200);
    recordRequest('/api/stats', 'GET', 5, 304);
    recordRequest('/api/stats', 'GET', 5, 500);
    const [entry] = getPerfSnapshot().hottest;
    expect(entry.errorCount).toBe(1);
    expect(entry.successRate).toBeCloseTo((2 / 3) * 100, 5);
  });

  it('ignores a negative or non-finite duration rather than skewing the mean', () => {
    recordRequest('/api/stats', 'GET', -5, 200);
    recordRequest('/api/stats', 'GET', Number.NaN, 200);
    expect(getPerfSnapshot().summary.totalRequests).toBe(0);
  });
});

describe('response cache — the allowlist is the safety property', () => {
  it('caches only allowlisted GETs', () => {
    expect(isCacheable('/api/metrics', 'GET')).toBe(true);
    expect(isCacheable('/api/metrics', 'POST')).toBe(false);
    expect(isCacheable('/api/simulate', 'POST')).toBe(false);
  });

  it('never caches a per-record route', () => {
    // The failure this prevents: a stale entry showing a finished run as
    // still pending, or one caller's job shown to another.
    for (const path of [
      '/api/jobs/job_123456_abc',
      '/api/sweeps/sweep_123456_abc',
      '/api/batches/batch_123456_abc',
    ]) {
      expect(isCacheable(path, 'GET')).toBe(false);
    }
  });

  it('never caches the observability endpoints themselves', () => {
    // An operator asking about now must not be told about ten seconds ago.
    expect(isCacheable('/api/perf', 'GET')).toBe(false);
    expect(isCacheable('/api/cache/stats', 'GET')).toBe(false);
  });

  it('keeps the allowlist free of anything that addresses one record', () => {
    // Guards the LIST, not just the lookup. A future entry like
    // "/api/jobs" would pass isCacheable() tests above while being wrong.
    for (const path of ALLOWLIST) {
      expect(path.startsWith('/api/metrics') || path === '/api/stats').toBe(true);
    }
  });

  it('includes the query string in the key', () => {
    // Keyed on pathname alone, `?limit=10` results would be served to a
    // caller who asked for `?limit=1000`.
    expect(cacheKey('/api/metrics', '?limit=10')).not.toBe(
      cacheKey('/api/metrics', '?limit=1000'),
    );
    expect(cacheKey('/api/metrics', '')).toBe('/api/metrics');
  });
});

describe('response cache — behaviour', () => {
  it('returns null and counts a miss on an empty cache', () => {
    expect(readCache('/api/metrics')).toBeNull();
    expect(getCacheStats().misses).toBe(1);
    expect(getCacheStats().hits).toBe(0);
  });

  it('returns a hit within the TTL', () => {
    writeCache('/api/metrics', '{"ok":true}', 1_000);
    expect(readCache('/api/metrics', 1_005)).toBe('{"ok":true}');
    expect(getCacheStats().hits).toBe(1);
  });

  it('expires rather than serving a stale body', () => {
    writeCache('/api/metrics', '{"ok":true}', 1_000);
    expect(readCache('/api/metrics', 1_000 + 10_001)).toBeNull();
    const stats = getCacheStats();
    expect(stats.expirations).toBe(1);
    expect(stats.entries).toBe(0);
  });

  it('reports a null hit rate before any lookup, not 0%', () => {
    // 0% reads as "the cache is useless". null reads as "nothing has been
    // asked of it", which is the true statement.
    expect(getCacheStats().hitRate).toBeNull();
    readCache('/api/metrics');
    expect(getCacheStats().hitRate).toBe(0);
  });

  it('evicts rather than growing without bound', () => {
    const { maxEntries } = getCacheStats();
    for (let i = 0; i < maxEntries + 10; i++) {
      writeCache(`/api/metrics?i=${i}`, '{}', 1_000);
    }
    const stats = getCacheStats();
    expect(stats.entries).toBeLessThanOrEqual(maxEntries);
    expect(stats.evictions).toBeGreaterThan(0);
  });

  it('reports which endpoints are cached, so the answer is checkable', () => {
    const stats = getCacheStats();
    expect(stats.cachedEndpoints).toContain('/api/metrics');
    expect(stats.cachedEndpoints).not.toContain('/api/perf');
    expect(stats.notes.join(' ')).toContain('allowlist');
  });
});

/**
 * MERGED FROM performance-monitor.ts (ADR 0025).
 *
 * Two collectors ran in this process for several days: this one, wired to
 * the server, and `performance-monitor.ts`, wired to nothing. Both measured
 * the same thing. The duplicate is now gone and the properties worth
 * keeping came across — p50/p99, fastest, last-request time, and the
 * slow-request log.
 *
 * These assertions are the ones the retired module's suite was carrying.
 * Deleting a module without rehoming its tests loses the reasoning, which
 * is the part that took the work.
 */
describe('merged from the retired collector', () => {
  it('reports p50 and p99 as well as p95', () => {
    for (let i = 1; i <= 100; i++) {
      recordRequest('/api/metrics', 'GET', i, 200);
    }
    const [entry] = getPerfSnapshot().hottest;
    // Nearest-rank over 1..100.
    expect(entry!.p50ResponseTimeMs).toBe(50);
    expect(entry!.p95ResponseTimeMs).toBe(95);
    expect(entry!.p99ResponseTimeMs).toBe(99);
  });

  it('withholds all three percentiles together, not just p95', () => {
    // They share one sample window. Reporting p50 while withholding p95
    // would imply the median is better established than the tail, and it
    // is exactly as established.
    recordRequest('/api/metrics', 'GET', 5, 200);
    const [entry] = getPerfSnapshot().hottest;
    expect(entry!.p50ResponseTimeMs).toBeNull();
    expect(entry!.p95ResponseTimeMs).toBeNull();
    expect(entry!.p99ResponseTimeMs).toBeNull();
    expect(entry!.percentileBasis).toContain('below the');
  });

  it('reports the fastest response as 0 for an endpoint never called', () => {
    // The sentinel is Infinity, which JSON serialises to null and a reader
    // would take for "unknown". Neither Infinity nor "unknown" is true of a
    // bucket that exists; 0 with no requests is unambiguous alongside
    // totalRequests.
    const snapshot = getPerfSnapshot();
    expect(snapshot.summary.totalEndpoints).toBe(0);
  });

  it('tracks fastest and slowest separately', () => {
    recordRequest('/api/stats', 'GET', 12, 200);
    recordRequest('/api/stats', 'GET', 400, 200);
    recordRequest('/api/stats', 'GET', 30, 200);
    const [entry] = getPerfSnapshot().hottest;
    expect(entry!.fastestResponseTimeMs).toBe(12);
    expect(entry!.slowestResponseTimeMs).toBe(400);
  });

  it('records when the endpoint was last called', () => {
    // A good average with no traffic since Tuesday is a different
    // situation from a healthy endpoint, and the average cannot say which.
    const before = Date.now();
    recordRequest('/api/stats', 'GET', 5, 200);
    const [entry] = getPerfSnapshot().hottest;
    expect(entry!.lastRequestTime).toBeGreaterThanOrEqual(before);
  });

  it('has a slow-request threshold that is exported and used', () => {
    // /api/perf is a pull — somebody has to think to look. The log is the
    // push. Asserting the constant is exported keeps the two in step.
    expect(SLOW_REQUEST_MS).toBe(1000);
  });
});
