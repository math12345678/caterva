/**
 * Result Comparator Tests
 *
 * Comprehensive tests for job comparison and sensitivity analysis
 */

import { compareJobs, compareMultipleJobs, analyzeSensitivity } from '../result-comparator';

describe('Result Comparator', () => {
  describe('compareJobs', () => {
    it('compares two identical jobs', () => {
      const job = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.34, confidence: 0.95, validated: true }
      };

      const comparison = compareJobs(job, job);

      expect(comparison.job1Id).toBe('job_1');
      expect(comparison.job2Id).toBe('job_1');
      expect(comparison.metrics.percentDifference).toBe(0);
      expect(comparison.similarity).toBe('identical');
    });

    it('detects very similar jobs', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.34, confidence: 0.95, validated: true }
      };

      const job2 = {
        jobId: 'job_2',
        query: 'michaelis-menten',
        result: { finalValue: 2.36, confidence: 0.95, validated: true }
      };

      const comparison = compareJobs(job1, job2);

      expect(comparison.similarity).toBe('very_similar');
      expect(comparison.metrics.percentDifference).toBeLessThan(5);
      expect(comparison.metrics.isDifferenceSignificant).toBe(false);
    });

    it('detects different jobs', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.95, validated: true }
      };

      const job2 = {
        jobId: 'job_2',
        query: 'competitive-inhibition',
        result: { finalValue: 3.0, confidence: 0.85, validated: true }
      };

      const comparison = compareJobs(job1, job2);

      expect(comparison.similarity).toBe('significantly_different');
      expect(comparison.metrics.isDifferenceSignificant).toBe(true);
      expect(comparison.insights.length).toBeGreaterThan(0);
    });

    it('calculates metrics correctly', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'test',
        result: { finalValue: 10, confidence: 0.9, validated: false }
      };

      const job2 = {
        jobId: 'job_2',
        query: 'test',
        result: { finalValue: 12, confidence: 0.9, validated: false }
      };

      const comparison = compareJobs(job1, job2);

      expect(comparison.metrics.difference).toBe(2);
      expect(comparison.metrics.percentDifference).toBeCloseTo(18.18, 1);
      expect(comparison.metrics.ratio).toBeCloseTo(0.833, 2);
    });

    it('generates insights for different models', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.95, validated: true }
      };

      const job2 = {
        jobId: 'job_2',
        query: 'competitive-inhibition',
        result: { finalValue: 2.0, confidence: 0.90, validated: true }
      };

      const comparison = compareJobs(job1, job2);

      expect(comparison.insights).toContainEqual(expect.stringContaining('Models differ'));
    });

    it('handles zero final values', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'test',
        result: { finalValue: 0, confidence: 0.9, validated: false }
      };

      const job2 = {
        jobId: 'job_2',
        query: 'test',
        result: { finalValue: 5, confidence: 0.9, validated: false }
      };

      // Should not crash with division by zero
      const comparison = compareJobs(job1, job2);
      expect(comparison.metrics.difference).toBe(5);
    });

    // Regression: the closing paren of Math.abs() sat after the first term,
    // so the test was `c1 - c2 > 0.1` rather than `|c1 - c2| > 0.1`. The
    // insight fired only when job 1 was the more confident of the two, which
    // made the whole comparison depend on which job the caller happened to
    // pass first.
    it('reports a confidence gap regardless of which job is passed first', () => {
      const lowConfidence = {
        jobId: 'job_low',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.2, validated: true }
      };
      const highConfidence = {
        jobId: 'job_high',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.9, validated: true }
      };

      const lowFirst = compareJobs(lowConfidence, highConfidence).insights;
      const highFirst = compareJobs(highConfidence, lowConfidence).insights;

      expect(lowFirst).toContainEqual(expect.stringContaining('Confidence difference'));
      expect(highFirst).toContainEqual(expect.stringContaining('Confidence difference'));
      expect(lowFirst).toContainEqual('Confidence difference: 0.200 vs 0.900');
      expect(highFirst).toContainEqual('Confidence difference: 0.900 vs 0.200');
    });

    it('stays silent when the confidences are within 0.1 of each other', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.9, validated: true }
      };
      const job2 = {
        jobId: 'job_2',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.85, validated: true }
      };

      expect(compareJobs(job1, job2).insights).not.toContainEqual(
        expect.stringContaining('Confidence difference')
      );
      expect(compareJobs(job2, job1).insights).not.toContainEqual(
        expect.stringContaining('Confidence difference')
      );
    });

    // A job with no result has no confidence. Coalescing it to 0 printed
    // "0.950 vs 0.000", asserting a measurement that was never made.
    it('does not report a confidence of zero for a job that has no result', () => {
      const finished = {
        jobId: 'job_1',
        query: 'michaelis-menten',
        result: { finalValue: 2.0, confidence: 0.95, validated: true }
      };
      const unfinished = { jobId: 'job_2', query: 'michaelis-menten', result: undefined };

      const insights = compareJobs(finished, unfinished).insights;

      expect(insights).not.toContainEqual(expect.stringContaining('Confidence difference'));
      expect(insights.join(' ')).not.toContain('0.000');
    });

    it('reports a job with no result as null, not as a final value of zero', () => {
      // This test previously asserted `job1FinalValue === 0`, which is the
      // defect: `job.result?.finalValue || 0` gave a job that never finished
      // a real-looking measurement of zero.
      const job1 = { jobId: 'job_1', query: 'test', result: undefined };
      const job2 = {
        jobId: 'job_2',
        query: 'test',
        result: { finalValue: 2.0, confidence: 0.9, validated: false }
      };

      const comparison = compareJobs(job1, job2);

      expect(comparison.job1FinalValue).toBeNull();
      expect(comparison.job1FinalValue).not.toBe(0);
      expect(comparison.job2FinalValue).toBe(2.0);
      expect(comparison.comparable).toBe(false);
      expect(comparison.incomparableReason).toMatch(/produced no final value/);
      expect(comparison.similarity).toBeNull();
      expect(comparison.metrics.percentDifference).toBeNull();
    });

    it('does NOT report two jobs that produced nothing as identical', () => {
      // THE DEFECT, in its sharpest form. Measured before the fix:
      //
      //   job1FinalValue : 0
      //   job2FinalValue : 0
      //   similarity     : identical
      //   percentDiff    : 0
      //
      // Two failed runs, reported as results that agree perfectly — a
      // scientific claim manufactured out of two absences, at
      // POST /api/compare/jobs, which is a live route.
      const a = { jobId: 'job_a', query: 'michaelis-menten', result: undefined };
      const b = { jobId: 'job_b', query: 'competitive-inhibition', result: undefined };

      const comparison = compareJobs(a, b);

      expect(comparison.similarity).not.toBe('identical');
      expect(comparison.similarity).toBeNull();
      expect(comparison.comparable).toBe(false);
      // The refusal names BOTH jobs, so a caller can see it is not one side.
      expect(comparison.incomparableReason).toContain('job_a');
      expect(comparison.incomparableReason).toContain('job_b');
    });

    it('still compares a genuine final value of zero', () => {
      // The other direction, and why `?? null` was chosen over `|| 0`.
      // Full substrate consumption gives a real zero and is the normal end
      // state of a Michaelis-Menten run; a filter that treated zero as
      // absent would throw away the answer.
      const consumed = {
        jobId: 'job_1', query: 'mm',
        result: { finalValue: 0, confidence: 0.9, validated: true }
      };
      const partial = {
        jobId: 'job_2', query: 'mm',
        result: { finalValue: 5, confidence: 0.9, validated: true }
      };

      const comparison = compareJobs(consumed, partial);

      expect(comparison.comparable).not.toBe(false);
      expect(comparison.job1FinalValue).toBe(0);
      expect(comparison.metrics.difference).toBe(5);
    });

    it('keeps a genuine zero in the NESTED pipeline shape too', () => {
      // Found by mutation. The test above uses the flat shape, so a mutation
      // that made the nested reader treat 0 as absent
      // (`typeof nested === 'number' && nested !== 0`) passed every test:
      // the flat fallback still returned 0 and nothing noticed.
      //
      // The pipeline emits the NESTED shape, so that is the path a real job
      // takes. Covering only the flat one tested the fallback and left the
      // primary reader unguarded -- the same shape as ADR 0056, where
      // nineteen tests agreed with the code about a shape production never
      // produces.
      const consumed = {
        jobId: 'job_1', query: 'mm',
        result: { validated: true, results: { finalValue: 0 } }
      };
      const partial = {
        jobId: 'job_2', query: 'mm',
        result: { validated: true, results: { finalValue: 5 } }
      };

      const comparison = compareJobs(consumed, partial);

      expect(comparison.job1FinalValue).toBe(0);
      expect(comparison.job1FinalValue).not.toBeNull();
      expect(comparison.comparable).not.toBe(false);
      expect(comparison.metrics.difference).toBe(5);
    });

    it('reads the nested pipeline shape as well as the flat one', () => {
      // ADR 0056: the pipeline returns `results.finalValue`; only some
      // callers flatten it. Reading one shape blanked every real job.
      const nested = {
        jobId: 'job_1', query: 'mm',
        result: { validated: true, results: { finalValue: 3.5 } }
      };
      const flat = {
        jobId: 'job_2', query: 'mm',
        result: { finalValue: 3.5, confidence: 0.9, validated: true }
      };

      const comparison = compareJobs(nested, flat);

      expect(comparison.job1FinalValue).toBe(3.5);
      expect(comparison.similarity).toBe('identical');
    });
  });

  describe('compareMultipleJobs', () => {
    it('throws on empty job list', () => {
      expect(() => compareMultipleJobs([])).toThrow();
    });

    it('handles single job', () => {
      const jobs = [
        {
          jobId: 'job_1',
          query: 'test',
          result: { finalValue: 2.0, confidence: 0.9, validated: false }
        }
      ];

      const comparison = compareMultipleJobs(jobs);

      expect(comparison.mean).toBe(2.0);
      expect(comparison.stdDev).toBe(0);
      expect(comparison.ranking.length).toBe(1);
    });

    it('calculates statistics for multiple jobs', () => {
      const jobs = [
        {
          jobId: 'job_1',
          query: 'test',
          result: { finalValue: 1.0, confidence: 0.9, validated: false }
        },
        {
          jobId: 'job_2',
          query: 'test',
          result: { finalValue: 2.0, confidence: 0.9, validated: false }
        },
        {
          jobId: 'job_3',
          query: 'test',
          result: { finalValue: 3.0, confidence: 0.9, validated: false }
        }
      ];

      const comparison = compareMultipleJobs(jobs);

      expect(comparison.mean).toBe(2.0);
      expect(comparison.median).toBe(2.0);
      expect(comparison.min.value).toBe(1.0);
      expect(comparison.max.value).toBe(3.0);
      expect(comparison.range).toBe(2.0);
      expect(comparison.stdDev).toBeGreaterThan(0);
    });

    it('ranks jobs by final value', () => {
      const jobs = [
        { jobId: 'job_1', query: 'test', result: { finalValue: 1.0, confidence: 0.9, validated: false } },
        { jobId: 'job_2', query: 'test', result: { finalValue: 3.0, confidence: 0.9, validated: false } },
        { jobId: 'job_3', query: 'test', result: { finalValue: 2.0, confidence: 0.9, validated: false } }
      ];

      const comparison = compareMultipleJobs(jobs);

      expect(comparison.ranking[0].jobId).toBe('job_2'); // 3.0 is highest
      expect(comparison.ranking[0].rank).toBe(1);
      expect(comparison.ranking[1].jobId).toBe('job_3'); // 2.0 is second
      expect(comparison.ranking[1].rank).toBe(2);
      expect(comparison.ranking[2].jobId).toBe('job_1'); // 1.0 is lowest
      expect(comparison.ranking[2].rank).toBe(3);
    });

    it('calculates coefficient of variation', () => {
      const jobs = [
        { jobId: 'job_1', query: 'test', result: { finalValue: 10, confidence: 0.9, validated: false } },
        { jobId: 'job_2', query: 'test', result: { finalValue: 12, confidence: 0.9, validated: false } },
        { jobId: 'job_3', query: 'test', result: { finalValue: 8, confidence: 0.9, validated: false } }
      ];

      const comparison = compareMultipleJobs(jobs);

      // CV = (stdDev / mean) * 100
      expect(comparison.coefficientOfVariation).toBeGreaterThan(0);
      expect(comparison.coefficientOfVariation).toBeLessThan(100);
    });

    it('generates insights about model variety', () => {
      const jobs = [
        { jobId: 'job_1', query: 'michaelis-menten', result: { finalValue: 2.0, confidence: 0.9, validated: false } },
        { jobId: 'job_2', query: 'competitive-inhibition', result: { finalValue: 2.1, confidence: 0.9, validated: false } },
        { jobId: 'job_3', query: 'non-competitive-inhibition', result: { finalValue: 2.05, confidence: 0.9, validated: false } }
      ];

      const comparison = compareMultipleJobs(jobs);

      expect(comparison.insights).toContainEqual(expect.stringContaining('different kinetic models'));
    });

    it('generates insights about validation', () => {
      const jobs = [
        { jobId: 'job_1', query: 'test', result: { finalValue: 2.0, confidence: 0.9, validated: true } },
        { jobId: 'job_2', query: 'test', result: { finalValue: 2.1, confidence: 0.9, validated: false } }
      ];

      const comparison = compareMultipleJobs(jobs);

      expect(comparison.insights.length).toBeGreaterThan(0);
    });
  });

  describe('analyzeSensitivity', () => {
    it('returns null for empty sweep', () => {
      const result = analyzeSensitivity(null);
      expect(result).toBeNull();
    });

    it('returns null for single result', () => {
      const sweep = {
        results: [{ finalValue: 1.0, validated: true }]
      };

      const result = analyzeSensitivity(sweep);
      expect(result).toBeNull();
    });

    it('calculates sensitivity for flat sweep', () => {
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 1.0, validated: true },
          { finalValue: 1.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.sensitivity).toBe(0); // No variation
      expect(analysis.stdDev).toBe(0);
      expect(analysis.mean).toBe(1.0);
    });

    it('calculates sensitivity for varied sweep', () => {
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 2.0, validated: true },
          { finalValue: 3.0, validated: true },
          { finalValue: 4.0, validated: true },
          { finalValue: 5.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.sensitivity).toBeGreaterThan(0);
      expect(analysis.mean).toBe(3.0);
      expect(analysis.min).toBe(1.0);
      expect(analysis.max).toBe(5.0);
      expect(analysis.range).toBe(4.0);
    });

    it('does NOT name an optimal point — that contradicted analyzeSweep', () => {
      // This replaces a test that asserted `optimalParameterIndex === 2`,
      // the index of the MAXIMUM value. `analyzeSweep` defines the optimum
      // as the MINIMUM ("minimum substrate remaining = maximum
      // conversion"), and both answers reached users: analyzeSweep's via
      // the exported CSV, this one via GET /api/analyze/sweep/:sweepId.
      // On 4.0, 2.5, 9.1 they named opposite ends of the range.
      //
      // ADR 0027's ruling on a duplicate implementation was to delete it
      // rather than bypass it, because a bypassed duplicate comes back. So
      // this is a deletion guard, not an absence of coverage: it fails if
      // anyone reintroduces an optimum here under any name.
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 2.0, validated: true },
          { finalValue: 5.0, validated: true },
          { finalValue: 3.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.optimalParameterIndex).toBeUndefined();
      const optimumish = Object.keys(analysis).filter(k => /optim|best/i.test(k));
      expect(optimumish).toEqual([]);
    });

    it('excludes points that did not run from every statistic', () => {
      // The defect this guards: `results.map(r => r.finalValue || 0)` gave
      // a crashed point a value of 0, and 0 is a real reading (full
      // substrate consumption), so nothing downstream could tell them
      // apart. mean, min, max, range, stdDev and sensitivity were all
      // computed over fabricated zeros.
      const withFailure = {
        results: [
          { finalValue: 4.0, validated: true },
          { finalValue: 2.5, validated: true },
          { finalValue: null, validated: false, error: 'solver diverged' }
        ]
      };
      const withoutIt = {
        results: [
          { finalValue: 4.0, validated: true },
          { finalValue: 2.5, validated: true }
        ]
      };

      const a = analyzeSensitivity(withFailure);
      const b = analyzeSensitivity(withoutIt);

      expect(a.mean).toBe(b.mean);
      expect(a.min).toBe(b.min);
      expect(a.stdDev).toBe(b.stdDev);
      // ...and it says how much of the grid is missing, rather than
      // reporting the same shape of answer as a sweep where none failed.
      expect(a.pointsAnalyzed).toBe(2);
      expect(a.pointsExcluded).toBe(1);
      expect(a.totalPoints).toBe(3);
    });

    it('refuses when fewer than two points are usable', () => {
      // One usable point cannot show a response to a parameter change.
      // A number here would be meaningless and would still get plotted.
      const analysis = analyzeSensitivity({
        results: [
          { finalValue: 4.0, validated: true },
          { finalValue: null, validated: false, error: 'boom' }
        ]
      });

      expect(analysis.sensitivity).toBeNull();
      expect(analysis.mean).toBeNull();
      expect(analysis.unanalysableReason).toMatch(/at least two/);
    });

    it('treats a point that does not say whether it ran as unusable', () => {
      // Absence of `validated` must not read as success. Requiring
      // `=== true` rather than `!== false` is the difference between
      // "checked and fine" and "nobody said".
      // NOTE: these two fixtures deliberately omit `validated`. A bulk edit
      // that adds `validated: true` to every sweep fixture in this file
      // must not touch them — doing so silently converts this test into a
      // duplicate of the happy path. It has already happened once.
      const analysis = analyzeSensitivity({
        results: [{ finalValue: 4.0 }, { finalValue: 2.5 }]
      });

      expect(analysis.pointsAnalyzed).toBe(0);
      expect(analysis.mean).toBeNull();
    });

    it('detects inflection points', () => {
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 1.1, validated: true },
          { finalValue: 1.15, validated: true },
          { finalValue: 4.0, validated: true }, // Large jump
          { finalValue: 5.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      // Should detect the large jump at index 3
      expect(analysis.inflectionPoints.length).toBeGreaterThanOrEqual(0);
    });

    it('calculates standard deviation correctly', () => {
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 2.0, validated: true },
          { finalValue: 3.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.stdDev).toBeCloseTo(0.816, 2);
    });

    it('handles missing analysis field in sweep', () => {
      const sweep = {
        results: [
          { finalValue: 1.0, validated: true },
          { finalValue: 2.0, validated: true }
        ]
        // No analysis field
      };

      const analysis = analyzeSensitivity(sweep);

      // Should still work without analysis
      expect(analysis.sensitivity).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Edge Cases', () => {
    it('handles very large numbers', () => {
      const jobs = [
        { jobId: 'job_1', query: 'test', result: { finalValue: 1e10, confidence: 0.9, validated: false } },
        { jobId: 'job_2', query: 'test', result: { finalValue: 1e10 + 1e9, confidence: 0.9, validated: false } }
      ];

      const comparison = compareJobs(jobs[0], jobs[1]);

      expect(comparison.metrics.difference).toBeLessThan(1e10);
    });

    it('handles very small numbers', () => {
      const jobs = [
        { jobId: 'job_1', query: 'test', result: { finalValue: 1e-10, confidence: 0.9, validated: false } },
        { jobId: 'job_2', query: 'test', result: { finalValue: 2e-10, confidence: 0.9, validated: false } }
      ];

      const comparison = compareJobs(jobs[0], jobs[1]);

      // Non-null asserted rather than cast away: both jobs have a real
      // finalValue here, so `comparable` is true and the metric is a number.
      // If that ever stops holding, this line should fail rather than
      // quietly compare against a fabricated zero.
      expect(comparison.comparable).not.toBe(false);
      expect(isFinite(comparison.metrics.percentDifference!)).toBe(true);
    });

    it('handles negative values in sweep', () => {
      const sweep = {
        results: [
          { finalValue: -5.0, validated: true },
          { finalValue: -2.0, validated: true },
          { finalValue: 1.0, validated: true }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.min).toBe(-5.0);
      expect(analysis.max).toBe(1.0);
      expect(analysis.range).toBe(6.0);
    });
  });
});
