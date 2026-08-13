/**
 * Job Query Builder Tests
 */

import { parseQueryString, filterJobs, buildQueryUrl, FilterPresets } from '../job-query-builder';

describe('Job Query Builder', () => {
  const sampleJobs = [
    {
      jobId: 'job_1',
      query: 'michaelis-menten',
      status: 'complete',
      startTime: new Date('2026-08-11T10:00:00Z').getTime(),
      endTime: new Date('2026-08-11T10:00:01Z').getTime(),
      duration: 1000,
      result: { finalValue: 2.34, confidence: 0.95, validated: true }
    },
    {
      jobId: 'job_2',
      query: 'competitive-inhibition',
      status: 'complete',
      startTime: new Date('2026-08-11T11:00:00Z').getTime(),
      endTime: new Date('2026-08-11T11:00:02Z').getTime(),
      duration: 2000,
      result: { finalValue: 2.12, confidence: 0.88, validated: false }
    },
    {
      jobId: 'job_3',
      query: 'michaelis-menten',
      status: 'error',
      startTime: new Date('2026-08-11T12:00:00Z').getTime(),
      duration: 500,
      result: undefined
    },
    {
      jobId: 'job_4',
      query: 'michaelis-menten',
      status: 'complete',
      startTime: new Date('2026-08-10T10:00:00Z').getTime(),
      endTime: new Date('2026-08-10T10:00:03Z').getTime(),
      duration: 3000,
      result: { finalValue: 3.45, confidence: 0.92, validated: true }
    }
  ];

  describe('parseQueryString', () => {
    it('parses status filter', () => {
      const filter = parseQueryString('status=complete');
      expect(filter.status).toBe('complete');
    });

    it('parses query filter', () => {
      const filter = parseQueryString('query=michaelis-menten');
      expect(filter.query).toBe('michaelis-menten');
    });

    it('parses validated filter', () => {
      const filter = parseQueryString('validated=true');
      expect(filter.validated).toBe(true);
    });

    it('parses pagination', () => {
      const filter = parseQueryString('limit=100&offset=50');
      expect(filter.limit).toBe(100);
      expect(filter.offset).toBe(50);
    });

    it('parses sorting', () => {
      const filter = parseQueryString('sortBy=confidence&sortOrder=desc');
      expect(filter.sortBy).toBe('confidence');
      expect(filter.sortOrder).toBe('desc');
    });

    it('parses date range', () => {
      const filter = parseQueryString('dateFrom=2026-08-11T00:00:00Z&dateTo=2026-08-12T00:00:00Z');
      expect(filter.dateFrom).toBeInstanceOf(Date);
      expect(filter.dateTo).toBeInstanceOf(Date);
    });

    it('parses confidence range', () => {
      const filter = parseQueryString('minConfidence=0.9&maxConfidence=0.99');
      expect(filter.minConfidence).toBe(0.9);
      expect(filter.maxConfidence).toBe(0.99);
    });

    it('caps limit to 10000', () => {
      const filter = parseQueryString('limit=999999');
      expect(filter.limit).toBe(10000);
    });

    it('defaults limit to 50', () => {
      const filter = parseQueryString('');
      expect(filter.limit).toBe(50);
    });
  });

  describe('filterJobs', () => {
    it('filters by status', () => {
      const result = filterJobs(sampleJobs, { status: 'complete' });
      expect(result.filtered).toBe(3);
      expect(result.jobs.every(j => j.status === 'complete')).toBe(true);
    });

    it('filters by query', () => {
      const result = filterJobs(sampleJobs, { query: 'michaelis-menten' });
      expect(result.filtered).toBe(3);
      expect(result.jobs.every(j => j.query === 'michaelis-menten')).toBe(true);
    });

    it('filters by validated', () => {
      const result = filterJobs(sampleJobs, { validated: true });
      expect(result.jobs.every(j => j.result?.validated === true)).toBe(true);
    });

    it('filters by date range', () => {
      const dateFrom = new Date('2026-08-11T00:00:00Z');
      const dateTo = new Date('2026-08-12T00:00:00Z');
      const result = filterJobs(sampleJobs, { dateFrom, dateTo });
      expect(result.filtered).toBe(3);
    });

    it('filters by confidence range', () => {
      const result = filterJobs(sampleJobs, { minConfidence: 0.9 });
      expect(result.jobs.every(j => (j.result?.confidence || 0) >= 0.9)).toBe(true);
    });

    it('sorts by confidence descending', () => {
      const result = filterJobs(sampleJobs, { sortBy: 'confidence', sortOrder: 'desc' });
      expect(result.jobs[0].result?.confidence).toBeGreaterThanOrEqual(result.jobs[1].result?.confidence || 0);
    });

    it('sorts by date ascending', () => {
      const result = filterJobs(sampleJobs, { sortBy: 'date', sortOrder: 'asc' });
      for (let i = 0; i < result.jobs.length - 1; i++) {
        expect(result.jobs[i].startTime).toBeLessThanOrEqual(result.jobs[i + 1].startTime);
      }
    });

    it('paginates results', () => {
      const result = filterJobs(sampleJobs, { limit: 2, offset: 1 });
      expect(result.jobs.length).toBeLessThanOrEqual(2);
      expect(result.limit).toBe(2);
      expect(result.offset).toBe(1);
    });

    it('returns total and filtered counts', () => {
      const result = filterJobs(sampleJobs, { status: 'complete' });
      expect(result.total).toBe(4);
      expect(result.filtered).toBe(3);
    });

    // `(job.result?.confidence || 0) <= max` scored a job with no result as
    // zero confidence, so every unfinished and every errored job satisfied
    // any upper bound. job_3 (status 'error', no result) came back as the
    // whole answer to "show me the low-confidence results".
    it('excludes jobs with no result from an upper-bound confidence filter', () => {
      const result = filterJobs(sampleJobs, { maxConfidence: 0.5 });

      expect(result.filtered).toBe(0);
      expect(result.jobs.map(j => j.jobId)).not.toContain('job_3');
    });

    // Same defect on duration: a job that has not finished has no duration,
    // and scoring it as 0 ms listed it among the fastest runs.
    it('excludes jobs with no duration from an upper-bound duration filter', () => {
      const running = {
        jobId: 'job_running',
        query: 'michaelis-menten',
        status: 'running',
        startTime: new Date('2026-08-11T13:00:00Z').getTime(),
        duration: undefined,
        result: undefined
      };

      const result = filterJobs([...sampleJobs, running], { maxDuration: 1200 });
      const ids = result.jobs.map(j => j.jobId);

      // job_3 errored but DID record a 500 ms duration, so it belongs here;
      // job_running has no duration at all and must not be reported as the
      // fastest run in the set.
      expect(ids).not.toContain('job_running');
      expect(ids.sort()).toEqual(['job_1', 'job_3']);
    });

    // The fix must not throw out genuine zeros with the absent values: a
    // simulation legitimately reporting confidence 0, or completing in under
    // a millisecond, is data, not a missing field.
    it('keeps a genuine zero confidence and a genuine zero duration', () => {
      const zeroJob = {
        jobId: 'job_zero',
        query: 'michaelis-menten',
        status: 'complete',
        startTime: new Date('2026-08-11T14:00:00Z').getTime(),
        duration: 0,
        result: { finalValue: 0, confidence: 0, validated: false }
      };

      expect(filterJobs([zeroJob], { maxConfidence: 0.5 }).jobs.map(j => j.jobId))
        .toEqual(['job_zero']);
      expect(filterJobs([zeroJob], { minConfidence: 0 }).jobs.map(j => j.jobId))
        .toEqual(['job_zero']);
      expect(filterJobs([zeroJob], { maxDuration: 1200 }).jobs.map(j => j.jobId))
        .toEqual(['job_zero']);
      expect(filterJobs([zeroJob], { minDuration: 0 }).jobs.map(j => j.jobId))
        .toEqual(['job_zero']);
    });

    // `slice()` reads a negative argument as an offset from the END of the
    // array, so `?limit=-1` returned every job except the last one while
    // reporting limit=-1 back to the caller.
    it('serves an empty page for a negative limit rather than dropping the tail', () => {
      const result = filterJobs(sampleJobs, parseQueryString('limit=-1'));

      expect(result.jobs).toEqual([]);
      expect(result.limit).toBe(0);
    });

    it('serves an empty page for limit=0 instead of falling back to 50', () => {
      const result = filterJobs(sampleJobs, parseQueryString('limit=0'));

      expect(result.jobs).toEqual([]);
      expect(result.filtered).toBe(4);
    });

    it('treats a negative offset as the first page, not the last', () => {
      const negative = filterJobs(sampleJobs, parseQueryString('offset=-2'));
      const first = filterJobs(sampleJobs, parseQueryString('offset=0'));

      expect(negative.offset).toBe(0);
      expect(negative.jobs.map(j => j.jobId)).toEqual(first.jobs.map(j => j.jobId));
    });

    it('applies multiple filters', () => {
      const result = filterJobs(sampleJobs, {
        status: 'complete',
        query: 'michaelis-menten',
        minConfidence: 0.9
      });
      expect(result.jobs.every(j =>
        j.status === 'complete' &&
        j.query === 'michaelis-menten' &&
        (j.result?.confidence || 0) >= 0.9
      )).toBe(true);
    });
  });

  describe('buildQueryUrl', () => {
    it('builds URL with filters', () => {
      const filter = {
        status: 'complete' as const,
        query: 'michaelis-menten',
        limit: 100
      };
      const url = buildQueryUrl(filter);
      expect(url).toContain('status=complete');
      expect(url).toContain('query=michaelis-menten');
      expect(url).toContain('limit=100');
    });

    it('skips undefined filters', () => {
      const filter = {
        status: 'complete' as const,
        query: undefined,
        limit: 50
      };
      const url = buildQueryUrl(filter);
      expect(url).toContain('status=complete');
      expect(url).not.toContain('query=');
      expect(url).toContain('limit=50');
    });
  });

  describe('FilterPresets', () => {
    it('recentSuccessful preset', () => {
      const filter = FilterPresets.recentSuccessful();
      expect(filter.status).toBe('complete');
      expect(filter.limit).toBe(50);
    });

    it('highConfidence preset', () => {
      const filter = FilterPresets.highConfidence();
      expect(filter.minConfidence).toBe(0.9);
      expect(filter.sortBy).toBe('confidence');
    });

    it('failures preset', () => {
      const filter = FilterPresets.failures();
      expect(filter.status).toBe('error');
    });

    it('today preset', () => {
      const filter = FilterPresets.today();
      expect(filter.dateFrom).toBeDefined();
      expect(filter.dateTo).toBeDefined();
    });

    it('validated preset', () => {
      const filter = FilterPresets.validated();
      expect(filter.validated).toBe(true);
    });

    it('unvalidated preset', () => {
      const filter = FilterPresets.unvalidated();
      expect(filter.validated).toBe(false);
    });

    it('model-specific presets', () => {
      const mmFilter = FilterPresets.michaelisMenten();
      expect(mmFilter.query).toBe('michaelis-menten');

      const ciFilter = FilterPresets.competitiveInhibition();
      expect(ciFilter.query).toBe('competitive-inhibition');
    });
  });
});
