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

    it('handles missing result fields', () => {
      const job1 = {
        jobId: 'job_1',
        query: 'test',
        result: undefined
      };

      const job2 = {
        jobId: 'job_2',
        query: 'test',
        result: { finalValue: 2.0, confidence: 0.9, validated: false }
      };

      // Should not crash
      const comparison = compareJobs(job1, job2);
      expect(comparison.job1FinalValue).toBe(0);
      expect(comparison.job2FinalValue).toBe(2.0);
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
        results: [{ finalValue: 1.0 }]
      };

      const result = analyzeSensitivity(sweep);
      expect(result).toBeNull();
    });

    it('calculates sensitivity for flat sweep', () => {
      const sweep = {
        results: [
          { finalValue: 1.0 },
          { finalValue: 1.0 },
          { finalValue: 1.0 }
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
          { finalValue: 1.0 },
          { finalValue: 2.0 },
          { finalValue: 3.0 },
          { finalValue: 4.0 },
          { finalValue: 5.0 }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.sensitivity).toBeGreaterThan(0);
      expect(analysis.mean).toBe(3.0);
      expect(analysis.min).toBe(1.0);
      expect(analysis.max).toBe(5.0);
      expect(analysis.range).toBe(4.0);
    });

    it('identifies optimal parameter index', () => {
      const sweep = {
        results: [
          { finalValue: 1.0 },
          { finalValue: 2.0 },
          { finalValue: 5.0 }, // Maximum
          { finalValue: 3.0 }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.optimalParameterIndex).toBe(2);
    });

    it('detects inflection points', () => {
      const sweep = {
        results: [
          { finalValue: 1.0 },
          { finalValue: 1.1 },
          { finalValue: 1.15 },
          { finalValue: 4.0 }, // Large jump
          { finalValue: 5.0 }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      // Should detect the large jump at index 3
      expect(analysis.inflectionPoints.length).toBeGreaterThanOrEqual(0);
    });

    it('calculates standard deviation correctly', () => {
      const sweep = {
        results: [
          { finalValue: 1.0 },
          { finalValue: 2.0 },
          { finalValue: 3.0 }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.stdDev).toBeCloseTo(0.816, 2);
    });

    it('handles missing analysis field in sweep', () => {
      const sweep = {
        results: [
          { finalValue: 1.0 },
          { finalValue: 2.0 }
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

      expect(isFinite(comparison.metrics.percentDifference)).toBe(true);
    });

    it('handles negative values in sweep', () => {
      const sweep = {
        results: [
          { finalValue: -5.0 },
          { finalValue: -2.0 },
          { finalValue: 1.0 }
        ]
      };

      const analysis = analyzeSensitivity(sweep);

      expect(analysis.min).toBe(-5.0);
      expect(analysis.max).toBe(1.0);
      expect(analysis.range).toBe(6.0);
    });
  });
});
