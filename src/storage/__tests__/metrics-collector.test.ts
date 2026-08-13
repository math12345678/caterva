/**
 * Metrics Collector Tests
 */

import { MetricsCollector, ExecutionMetrics } from '../metrics-collector';

describe('MetricsCollector', () => {
  let collector: MetricsCollector;

  beforeEach(() => {
    collector = new MetricsCollector();
  });

  // A sibling metrics system in this repo (Science-Agent-Pipeline's
  // metrics.ts, since deleted) had no production writers and reported a
  // fabricated 100% success rate from an empty sample -- a health check
  // that could never fail. This collector had the same shape of bug
  // (numeric defaults for zero/all-failed samples that read as real
  // measurements) until it was fixed. These tests exercise exactly the
  // zero-sample and all-failed cases that let that bug through
  // unnoticed the first time, so a regression here goes red immediately
  // instead of silently shipping a fabricated number again.
  describe('zero-sample and all-failed honesty (regression coverage)', () => {
    it('reports successRate null, not 0, when no jobs have run at all', () => {
      const agg = collector.getAggregatedMetrics();

      expect(agg.totalJobs).toBe(0);
      expect(agg.successRate).toBeNull();
      expect(agg.averageExecutionTimeMs).toBeNull();
      expect(agg.medianExecutionTimeMs).toBeNull();
      expect(agg.minExecutionTimeMs).toBeNull();
      expect(agg.maxExecutionTimeMs).toBeNull();
      expect(agg.stdDevExecutionTimeMs).toBeNull();
      expect(agg.averageConvergenceSteps).toBeNull();
    });

    it('reports successRate 0 (a real measurement), not null, when jobs ran and all failed', () => {
      collector.recordExecution({
        jobId: 'job_fail_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 1500,
        executionTimeMs: 500,
        convergenceSteps: 0,
        success: false,
        errorMessage: 'engine error'
      });

      const agg = collector.getAggregatedMetrics();

      expect(agg.totalJobs).toBe(1);
      // 0 successes out of 1 real recorded job IS a genuine 0% -- this
      // must stay a number, not collapse into the same null used for
      // "nothing has run yet".
      expect(agg.successRate).toBe(0);
      // But there is no successful execution to time, so timing stays null.
      expect(agg.averageExecutionTimeMs).toBeNull();
    });

    it('includes an all-failed query in getMetricsByModel() instead of silently dropping it', () => {
      collector.recordExecution({
        jobId: 'job_fail_1',
        query: 'always-fails-query',
        startTime: 1000,
        endTime: 1500,
        executionTimeMs: 500,
        convergenceSteps: 0,
        success: false
      });

      const byModel = collector.getMetricsByModel();
      const entry = byModel.find(m => m.query === 'always-fails-query');

      // Previously this query vanished from the report entirely
      // (`if (executionTimes.length === 0) continue`), which is worse
      // than reporting a fabricated number: a query failing 100% of the
      // time simply disappeared instead of being the thing an operator
      // most needs to see.
      expect(entry).toBeDefined();
      expect(entry!.jobCount).toBe(1);
      expect(entry!.successRate).toBe(0);
      expect(entry!.averageExecutionTimeMs).toBeNull();
    });

    it('returns null, not 0ms, from getPercentile() when there is no successful execution', () => {
      expect(collector.getPercentile(50)).toBeNull();

      collector.recordExecution({
        jobId: 'job_fail_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 1500,
        executionTimeMs: 500,
        convergenceSteps: 0,
        success: false
      });

      // Still no SUCCESSFUL execution, even though a job was recorded.
      expect(collector.getPercentile(50)).toBeNull();
    });

    it('reports isReproducible null, not true, for a value observed exactly once', () => {
      const metrics = collector.trackReproducibility('michaelis-menten', 'hash_new', 42.0);

      // One observation cannot confirm OR deny agreement across runs.
      // Defaulting a freshly-created record to `true` reported
      // "reproducible" for a result nothing had yet reproduced.
      expect(metrics.runCount).toBe(1);
      expect(metrics.isReproducible).toBeNull();
    });

    it('reports correlationWithExecutionTime null, not 0, since it is never actually computed', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 1500,
        executionTimeMs: 500,
        convergenceSteps: 25,
        success: true
      });
      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2800,
        executionTimeMs: 800,
        convergenceSteps: 40,
        success: true
      });

      const result = collector.analyzeParameterSensitivity('km');

      // ExecutionMetrics carries no parameter VALUES, so there is
      // nothing here to correlate -- a hardcoded 0 read as "measured, no
      // correlation" rather than "not measured at all".
      expect(result!.correlationWithExecutionTime).toBeNull();
    });
  });

  describe('recording metrics', () => {
    it('records execution metrics for a job', () => {
      const metrics: ExecutionMetrics = {
        jobId: 'job_123',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      };

      collector.recordExecution(metrics);
      const retrieved = collector.getJobMetrics('job_123');

      expect(retrieved).toEqual(metrics);
    });

    it('handles multiple job metrics', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2500,
        executionTimeMs: 500,
        convergenceSteps: 25,
        success: true
      });

      const all = collector.getAllMetrics();
      expect(all).toHaveLength(2);
    });
  });

  describe('aggregated metrics', () => {
    it('calculates aggregated metrics', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2200,
        executionTimeMs: 200,
        convergenceSteps: 25,
        success: true
      });

      const agg = collector.getAggregatedMetrics();

      expect(agg.totalJobs).toBe(2);
      expect(agg.successfulJobs).toBe(2);
      expect(agg.failedJobs).toBe(0);
      expect(agg.averageExecutionTimeMs).toBe(600);
      expect(agg.medianExecutionTimeMs).toBe(600);
      expect(agg.minExecutionTimeMs).toBe(200);
      expect(agg.maxExecutionTimeMs).toBe(1000);
      expect(agg.successRate).toBe(100);
    });

    it('handles failed jobs in aggregation', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2100,
        executionTimeMs: 100,
        convergenceSteps: 0,
        success: false,
        errorMessage: 'Convergence failed'
      });

      const agg = collector.getAggregatedMetrics();

      expect(agg.totalJobs).toBe(2);
      expect(agg.successfulJobs).toBe(1);
      expect(agg.failedJobs).toBe(1);
      expect(agg.successRate).toBe(50);
    });

    it('calculates standard deviation correctly', () => {
      // Times: 100, 200, 300
      // Mean: 200
      // Variance: ((100-200)^2 + (200-200)^2 + (300-200)^2) / 3 = 6666.67
      // StdDev: 81.65

      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 1100,
        executionTimeMs: 100,
        convergenceSteps: 25,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2200,
        executionTimeMs: 200,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_3',
        query: 'michaelis-menten',
        startTime: 3000,
        endTime: 3300,
        executionTimeMs: 300,
        convergenceSteps: 75,
        success: true
      });

      const agg = collector.getAggregatedMetrics();

      expect(agg.stdDevExecutionTimeMs).toBeCloseTo(81.65, 1);
    });
  });

  describe('model metrics', () => {
    it('groups metrics by model', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'competitive-inhibition',
        startTime: 2000,
        endTime: 2300,
        executionTimeMs: 300,
        convergenceSteps: 30,
        success: true
      });

      const modelMetrics = collector.getMetricsByModel();

      expect(modelMetrics).toHaveLength(2);
      expect(modelMetrics[0].query).toBe('michaelis-menten');
      expect(modelMetrics[0].jobCount).toBe(1);
    });

    it('calculates success rate per model', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2100,
        executionTimeMs: 100,
        convergenceSteps: 0,
        success: false,
        errorMessage: 'Failed'
      });

      const modelMetrics = collector.getMetricsByModel();

      expect(modelMetrics[0].successRate).toBe(50);
    });
  });

  describe('reproducibility tracking', () => {
    it('tracks reproducibility across multiple runs', () => {
      // Same parameter set (same hash), same model, different runs
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 45.2);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 45.1);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 45.3);

      const metrics = collector.getReproducibilityMetrics('michaelis-menten', 'param_hash_abc');

      expect(metrics).toBeDefined();
      expect(metrics!.runCount).toBe(3);
      expect(metrics!.results).toEqual([45.2, 45.1, 45.3]);
    });

    it('marks reproducible when variance is low', () => {
      // All results identical = perfect reproducibility
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 100);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 100);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 100);

      const metrics = collector.getReproducibilityMetrics('michaelis-menten', 'param_hash_abc');

      expect(metrics!.isReproducible).toBe(true);
      expect(metrics!.stdDev).toBe(0);
    });

    it('marks non-reproducible when variance is high', () => {
      // High variance across runs
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 100);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 50);
      collector.trackReproducibility('michaelis-menten', 'param_hash_abc', 150);

      const metrics = collector.getReproducibilityMetrics('michaelis-menten', 'param_hash_abc');

      expect(metrics!.isReproducible).toBe(false);
      expect(metrics!.stdDev).toBeGreaterThan(30);
    });

    it('returns all reproducibility metrics', () => {
      collector.trackReproducibility('michaelis-menten', 'hash_1', 100);
      collector.trackReproducibility('competitive-inhibition', 'hash_2', 50);

      const all = collector.getAllReproducibilityMetrics();

      expect(all).toHaveLength(2);
    });
  });

  describe('percentile analysis', () => {
    it('calculates percentile execution time', () => {
      // Times: 100, 200, 300, 400, 500
      for (let i = 1; i <= 5; i++) {
        collector.recordExecution({
          jobId: `job_${i}`,
          query: 'michaelis-menten',
          startTime: 1000,
          endTime: 1000 + i * 100,
          executionTimeMs: i * 100,
          convergenceSteps: 25,
          success: true
        });
      }

      expect(collector.getPercentile(50)).toBe(300); // median
      expect(collector.getPercentile(90)).toBe(500); // 90th percentile
    });
  });

  describe('slow queries', () => {
    it('identifies queries slower than threshold', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2100,
        executionTimeMs: 100,
        convergenceSteps: 25,
        success: true
      });

      const slow = collector.getSlowQueries(500);

      expect(slow).toHaveLength(1);
      expect(slow[0].jobId).toBe('job_1');
    });
  });

  describe('failed queries', () => {
    it('retrieves failed queries for debugging', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      collector.recordExecution({
        jobId: 'job_2',
        query: 'michaelis-menten',
        startTime: 2000,
        endTime: 2100,
        executionTimeMs: 100,
        convergenceSteps: 0,
        success: false,
        errorMessage: 'Convergence failed'
      });

      const failed = collector.getFailedQueries();

      expect(failed).toHaveLength(1);
      expect(failed[0].jobId).toBe('job_2');
      expect(failed[0].errorMessage).toBe('Convergence failed');
    });
  });

  describe('clear', () => {
    it('clears all metrics', () => {
      collector.recordExecution({
        jobId: 'job_1',
        query: 'michaelis-menten',
        startTime: 1000,
        endTime: 2000,
        executionTimeMs: 1000,
        convergenceSteps: 50,
        success: true
      });

      expect(collector.getAllMetrics()).toHaveLength(1);

      collector.clear();

      expect(collector.getAllMetrics()).toHaveLength(0);
    });
  });
});
