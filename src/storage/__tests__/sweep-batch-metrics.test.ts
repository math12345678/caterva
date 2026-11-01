/**
 * Sweep and Batch Metrics Tests
 */

import {
  recordSweepMetrics,
  recordBatchMetrics,
  getSweepMetrics,
  getAllSweepMetrics,
  getBatchMetrics,
  getAllBatchMetrics,
  getSweepMetricsByQuery,
  getBatchMetricsByQuery,
  clearSweepBatchMetrics
} from '../sweep-batch-metrics';

describe('Sweep/Batch Metrics', () => {
  beforeEach(() => {
    clearSweepBatchMetrics();
  });

  describe('sweep metrics', () => {
    it('records sweep metrics correctly', () => {
      const results = [
        { executionTimeMs: 100, validated: true },
        { executionTimeMs: 150, validated: true },
        { executionTimeMs: 200, validated: false }
      ];

      const sweepId = 'sweep_test_001';
      const query = 'michaelis-menten';
      const metrics = recordSweepMetrics(sweepId, query, results);

      expect(metrics.sweepId).toBe(sweepId);
      expect(metrics.query).toBe(query);
      expect(metrics.totalSimulations).toBe(3);
      expect(metrics.successfulSimulations).toBe(2);
      expect(metrics.failedSimulations).toBe(1);
      expect(metrics.averageTimeMs).toBe(150); // (100 + 150 + 200) / 3
      expect(metrics.minTimeMs).toBe(100);
      expect(metrics.maxTimeMs).toBe(200);
      expect(metrics.successRate).toBe((2 / 3) * 100);
    });

    it('retrieves recorded sweep metrics', () => {
      const sweepId = 'sweep_test_002';
      const results = [
        { executionTimeMs: 100, validated: true }
      ];

      recordSweepMetrics(sweepId, 'query1', results);
      const retrieved = getSweepMetrics(sweepId);

      expect(retrieved).toBeDefined();
      expect(retrieved!.sweepId).toBe(sweepId);
    });

    it('returns undefined for nonexistent sweep', () => {
      const retrieved = getSweepMetrics('nonexistent');
      expect(retrieved).toBeUndefined();
    });

    it('retrieves all sweep metrics', () => {
      recordSweepMetrics('sweep_1', 'query1', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordSweepMetrics('sweep_2', 'query2', [
        { executionTimeMs: 200, validated: true }
      ]);

      const all = getAllSweepMetrics();
      expect(all).toHaveLength(2);
      expect(all.map(m => m.sweepId)).toContain('sweep_1');
      expect(all.map(m => m.sweepId)).toContain('sweep_2');
    });

    it('groups sweep metrics by query', () => {
      recordSweepMetrics('sweep_1', 'michaelis-menten', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordSweepMetrics('sweep_2', 'michaelis-menten', [
        { executionTimeMs: 150, validated: true }
      ]);
      recordSweepMetrics('sweep_3', 'competitive-inhibition', [
        { executionTimeMs: 200, validated: true }
      ]);

      const byQuery = getSweepMetricsByQuery();

      expect(byQuery.size).toBe(2);
      expect(byQuery.get('michaelis-menten')).toHaveLength(2);
      expect(byQuery.get('competitive-inhibition')).toHaveLength(1);
    });

    it('calculates median correctly for sweep metrics', () => {
      const results = [
        { executionTimeMs: 50, validated: true },
        { executionTimeMs: 100, validated: true },
        { executionTimeMs: 150, validated: true },
        { executionTimeMs: 200, validated: true },
        { executionTimeMs: 250, validated: true }
      ];

      const metrics = recordSweepMetrics('sweep_median', 'query1', results);
      expect(metrics.minTimeMs).toBe(50);
      expect(metrics.maxTimeMs).toBe(250);
    });

    it('handles all-failed sweep', () => {
      const results = [
        { executionTimeMs: 100, validated: false },
        { executionTimeMs: 150, validated: false },
        { executionTimeMs: 200, validated: false }
      ];

      const metrics = recordSweepMetrics('sweep_failed', 'query1', results);

      expect(metrics.totalSimulations).toBe(3);
      expect(metrics.successfulSimulations).toBe(0);
      expect(metrics.failedSimulations).toBe(3);
      expect(metrics.successRate).toBe(0);
      expect(metrics.totalTimeMs).toBe(450);
    });

    it('handles empty sweep results with null rate/timing, not fabricated zeros', () => {
      // Zero simulations recorded is a different fact from "ran and got
      // 0% success" / "ran and took 0ms" -- those are real measurements,
      // this is the absence of any. null says "nothing to measure" the
      // same way metrics-collector.ts's getAggregatedMetrics() does for
      // totalJobs === 0.
      const metrics = recordSweepMetrics('sweep_empty', 'query1', []);

      expect(metrics.totalSimulations).toBe(0);
      expect(metrics.successfulSimulations).toBe(0);
      expect(metrics.failedSimulations).toBe(0);
      expect(metrics.successRate).toBeNull();
      expect(metrics.averageTimeMs).toBeNull();
      expect(metrics.minTimeMs).toBeNull();
      expect(metrics.maxTimeMs).toBeNull();
      expect(metrics.totalTimeMs).toBe(0); // sum of nothing is a real 0, unlike the fields above
    });
  });

  describe('batch metrics', () => {
    it('records batch metrics correctly', () => {
      const results = [
        { executionTimeMs: 200, validated: true },
        { executionTimeMs: 250, validated: true },
        { executionTimeMs: 300, validated: false }
      ];

      const batchId = 'batch_test_001';
      const query = 'competitive-inhibition';
      const metrics = recordBatchMetrics(batchId, query, results);

      expect(metrics.batchId).toBe(batchId);
      expect(metrics.query).toBe(query);
      expect(metrics.totalJobs).toBe(3);
      expect(metrics.successfulJobs).toBe(2);
      expect(metrics.failedJobs).toBe(1);
      expect(metrics.averageTimeMs).toBe((200 + 250 + 300) / 3);
      expect(metrics.minTimeMs).toBe(200);
      expect(metrics.maxTimeMs).toBe(300);
    });

    it('retrieves recorded batch metrics', () => {
      const batchId = 'batch_test_002';
      const results = [
        { executionTimeMs: 100, validated: true }
      ];

      recordBatchMetrics(batchId, 'query1', results);
      const retrieved = getBatchMetrics(batchId);

      expect(retrieved).toBeDefined();
      expect(retrieved!.batchId).toBe(batchId);
    });

    it('returns undefined for nonexistent batch', () => {
      const retrieved = getBatchMetrics('nonexistent');
      expect(retrieved).toBeUndefined();
    });

    it('retrieves all batch metrics', () => {
      recordBatchMetrics('batch_1', 'query1', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordBatchMetrics('batch_2', 'query2', [
        { executionTimeMs: 200, validated: true }
      ]);

      const all = getAllBatchMetrics();
      expect(all).toHaveLength(2);
      expect(all.map(m => m.batchId)).toContain('batch_1');
      expect(all.map(m => m.batchId)).toContain('batch_2');
    });

    it('groups batch metrics by query', () => {
      recordBatchMetrics('batch_1', 'michaelis-menten', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordBatchMetrics('batch_2', 'michaelis-menten', [
        { executionTimeMs: 150, validated: true }
      ]);
      recordBatchMetrics('batch_3', 'competitive-inhibition', [
        { executionTimeMs: 200, validated: true }
      ]);

      const byQuery = getBatchMetricsByQuery();

      expect(byQuery.size).toBe(2);
      expect(byQuery.get('michaelis-menten')).toHaveLength(2);
      expect(byQuery.get('competitive-inhibition')).toHaveLength(1);
    });

    it('handles all-failed batch', () => {
      const results = [
        { executionTimeMs: 100, validated: false },
        { executionTimeMs: 150, validated: false }
      ];

      const metrics = recordBatchMetrics('batch_failed', 'query1', results);

      expect(metrics.totalJobs).toBe(2);
      expect(metrics.successfulJobs).toBe(0);
      expect(metrics.failedJobs).toBe(2);
      expect(metrics.successRate).toBe(0);
    });

    it('handles empty batch results with null rate/timing, not fabricated zeros', () => {
      const metrics = recordBatchMetrics('batch_empty', 'query1', []);

      expect(metrics.totalJobs).toBe(0);
      expect(metrics.successfulJobs).toBe(0);
      expect(metrics.failedJobs).toBe(0);
      expect(metrics.successRate).toBeNull();
      expect(metrics.averageTimeMs).toBeNull();
      expect(metrics.minTimeMs).toBeNull();
      expect(metrics.maxTimeMs).toBeNull();
      expect(metrics.totalTimeMs).toBe(0);
    });
  });

  describe('isolation between sweep and batch', () => {
    it('keeps sweep and batch metrics separate', () => {
      recordSweepMetrics('sweep_1', 'query1', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordBatchMetrics('batch_1', 'query1', [
        { executionTimeMs: 200, validated: true }
      ]);

      const sweeps = getAllSweepMetrics();
      const batches = getAllBatchMetrics();

      expect(sweeps).toHaveLength(1);
      expect(batches).toHaveLength(1);
      expect(sweeps[0].sweepId).toBe('sweep_1');
      expect(batches[0].batchId).toBe('batch_1');
    });
  });

  describe('clear functionality', () => {
    it('clears all metrics', () => {
      recordSweepMetrics('sweep_1', 'query1', [
        { executionTimeMs: 100, validated: true }
      ]);
      recordBatchMetrics('batch_1', 'query1', [
        { executionTimeMs: 200, validated: true }
      ]);

      expect(getAllSweepMetrics()).toHaveLength(1);
      expect(getAllBatchMetrics()).toHaveLength(1);

      clearSweepBatchMetrics();

      expect(getAllSweepMetrics()).toHaveLength(0);
      expect(getAllBatchMetrics()).toHaveLength(0);
    });
  });

  describe('success rate accuracy', () => {
    it('calculates correct success rate for sweeps', () => {
      const results = [
        { executionTimeMs: 100, validated: true },
        { executionTimeMs: 100, validated: true },
        { executionTimeMs: 100, validated: false }
      ];

      const metrics = recordSweepMetrics('sweep_sr', 'query1', results);
      expect(metrics.successRate).toBeCloseTo(66.67, 1);
    });

    it('calculates correct success rate for batches', () => {
      const results = [
        { executionTimeMs: 100, validated: true },
        { executionTimeMs: 100, validated: false },
        { executionTimeMs: 100, validated: false }
      ];

      const metrics = recordBatchMetrics('batch_sr', 'query1', results);
      expect(metrics.successRate).toBeCloseTo(33.33, 1);
    });
  });
});
