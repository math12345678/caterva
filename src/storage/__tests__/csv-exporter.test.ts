/**
 * CSV Exporter Tests
 *
 * Comprehensive tests for CSV export functionality
 */

import {
  exportJobHistoryToCSV,
  exportSweepToCSV,
  exportBatchToCSV,
  exportComparisonToCSV,
  exportStatisticsToCSV
} from '../csv-exporter';

describe('CSV Exporter', () => {
  describe('exportJobHistoryToCSV', () => {
    it('exports empty job list gracefully', () => {
      const csv = exportJobHistoryToCSV([]);
      expect(csv).toContain('No jobs to export');
    });

    it('exports single job with all fields', () => {
      const jobs = [
        {
          jobId: 'job_123',
          query: 'michaelis-menten',
          status: 'complete',
          startTime: new Date('2026-08-11T15:00:00Z').getTime(),
          endTime: new Date('2026-08-11T15:00:01Z').getTime(),
          duration: 1000,
          result: {
            finalValue: 2.34,
            confidence: 0.95,
            validated: true
          },
          parameters: { km: 5.2, vmax: 12.8, s0: 10 }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      expect(csv).toContain('job_123');
      expect(csv).toContain('michaelis-menten');
      expect(csv).toContain('2.34');
      expect(csv).toContain('0.95');
    });

    it('handles special characters in parameters', () => {
      const jobs = [
        {
          jobId: 'job_456',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: Date.now(),
          duration: 100,
          result: { finalValue: 1.0, confidence: 0.9, validated: false },
          parameters: { enzyme: 'test, "enzyme"', substrate: 'sub"strate' }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      // Parameters should be properly quoted
      expect(csv).toContain('"');
    });

    it('includes parameters when requested', () => {
      const jobs = [
        {
          jobId: 'job_789',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: Date.now(),
          duration: 100,
          result: { finalValue: 1.0, confidence: 0.9, validated: false },
          parameters: { km: 5.0 }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs, { includeParameters: true });
      expect(csv).toContain('parameters');
      // The parameter JSON contains double quotes, so RFC 4180 requires the
      // field to be quoted and every inner quote doubled. This asserted the
      // RAW JSON `{"km":5}`, which never appears in valid CSV output -- so
      // the test was demanding malformed output and failing when it got
      // correct output.
      expect(csv).toContain('"{""km"":5}"');
    });

    it('handles missing fields gracefully', () => {
      const jobs = [
        {
          jobId: 'job_incomplete',
          query: 'test',
          status: 'running',
          startTime: Date.now()
          // Missing endTime, duration, result
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      expect(csv).toContain('job_incomplete');
      // Should not crash, empty fields are OK
      expect(csv.length).toBeGreaterThan(0);
    });

    it('exports multiple jobs with correct row count', () => {
      const jobs = Array(5).fill(null).map((_, i) => ({
        jobId: `job_${i}`,
        query: 'test',
        status: 'complete',
        startTime: Date.now(),
        endTime: Date.now(),
        duration: 100,
        result: { finalValue: 1.0, confidence: 0.9, validated: false },
        parameters: {}
      }));

      const csv = exportJobHistoryToCSV(jobs);
      const lines = csv.split('\n');
      // Header + 5 jobs
      expect(lines.length).toBeGreaterThanOrEqual(6);
    });
  });

  describe('exportSweepToCSV', () => {
    it('handles empty sweep results', () => {
      const csv = exportSweepToCSV(null);
      expect(csv).toContain('No sweep results');
    });

    it('exports sweep with analysis summary', () => {
      const sweep = {
        results: [
          { parameters: { km: 1 }, finalValue: 0.5, confidence: 0.9, validated: true },
          { parameters: { km: 2 }, finalValue: 1.0, confidence: 0.92, validated: true },
          { parameters: { km: 3 }, finalValue: 1.5, confidence: 0.94, validated: true }
        ],
        analysis: {
          optimalParameters: { km: 3 },
          meanFinalValue: 1.0,
          minFinalValue: 0.5,
          maxFinalValue: 1.5,
          stdDeviation: 0.41
        }
      };

      const csv = exportSweepToCSV(sweep);
      expect(csv).toContain('0.5');
      // `finalValue: 1.0` is the NUMBER 1 by the time it reaches the
      // exporter -- JavaScript has one numeric type and `String(1.0)` is
      // "1". The trailing zero was lost at parse time and cannot be
      // recovered, so asserting "1.0" demanded a precision the data no
      // longer carries. Asserting the row instead of a loose substring also
      // pins WHERE the value appears, which `toContain('0.5')` never did.
      expect(csv).toContain('1,0.92,true');
      expect(csv).toContain('1.5');
      expect(csv).toContain('# Analysis');
      expect(csv).toContain('optimalParameters');
    });

    it('properly quotes parameter JSON', () => {
      const sweep = {
        results: [
          {
            parameters: { km: 1.5, vmax: 10.2, s0: 5 },
            finalValue: 1.0,
            confidence: 0.9,
            validated: true
          }
        ]
      };

      const csv = exportSweepToCSV(sweep);
      // Quoted field, inner quotes doubled -- see the note above. This is
      // what "properly quotes parameter JSON" means, and the test now
      // asserts it rather than its opposite.
      expect(csv).toContain('"{""km"":1.5,""vmax"":10.2,""s0"":5}"');
    });
  });

  describe('exportBatchToCSV', () => {
    it('handles empty batch', () => {
      const csv = exportBatchToCSV(null);
      expect(csv).toContain('No batch results');
    });

    it('exports batch with summary statistics', () => {
      const batch = {
        results: [
          { finalValue: 1.0, confidence: 0.9, validated: true, executionTimeMs: 75, parameters: { km: 1 } },
          { finalValue: 1.1, confidence: 0.91, validated: true, executionTimeMs: 78, parameters: { km: 2 } },
          { finalValue: 1.2, confidence: 0.92, validated: true, executionTimeMs: 80, parameters: { km: 3 } }
        ],
        summary: {
          totalJobs: 3,
          successfulJobs: 3,
          failedJobs: 0,
          averageExecutionTimeMs: 77.67
        }
      };

      const csv = exportBatchToCSV(batch);
      // Same as the sweep case: `1.0` is the number 1. Asserted as a whole
      // row so this pins the first job's cells rather than matching "1.0"
      // anywhere in the file.
      expect(csv).toContain('1,1,0.9,true,75');
      expect(csv).toContain('# Summary');
      expect(csv).toContain('totalJobs');
      expect(csv).toContain('3');
    });

    it('indexes jobs starting from 1', () => {
      const batch = {
        results: Array(3).fill(null).map(() => ({
          finalValue: 1.0,
          confidence: 0.9,
          validated: true,
          executionTimeMs: 75,
          parameters: {}
        }))
      };

      const csv = exportBatchToCSV(batch);
      expect(csv).toContain('1,');
      expect(csv).toContain('2,');
      expect(csv).toContain('3,');
    });
  });

  describe('exportComparisonToCSV', () => {
    it('handles empty comparison', () => {
      const csv = exportComparisonToCSV(null);
      expect(csv).toContain('No comparison results');
    });

    it('exports all 4 models with ranking', () => {
      const comparison = {
        models: [
          { model: 'michaelis-menten', finalValue: 2.34, confidence: 0.95, validated: true, executionTimeMs: 75 },
          { model: 'competitive-inhibition', finalValue: 2.12, confidence: 0.88, validated: false, executionTimeMs: 82 },
          { model: 'non-competitive-inhibition', finalValue: 2.45, confidence: 0.91, validated: false, executionTimeMs: 78 },
          { model: 'product-inhibition', finalValue: 2.01, confidence: 0.85, validated: false, executionTimeMs: 79 }
        ],
        ranking: [
          'michaelis-menten',
          'non-competitive-inhibition',
          'competitive-inhibition',
          'product-inhibition'
        ],
        bestModel: 'michaelis-menten',
        analysis: {
          meanFinalValue: 2.23,
          modelVariability: 0.18
        }
      };

      const csv = exportComparisonToCSV(comparison);
      expect(csv).toContain('michaelis-menten');
      expect(csv).toContain('competitive-inhibition');
      expect(csv).toContain('non-competitive-inhibition');
      expect(csv).toContain('product-inhibition');
      expect(csv).toContain('# Analysis');
    });
  });

  describe('exportStatisticsToCSV', () => {
    it('exports system statistics', () => {
      const stats = {
        totalJobs: 100,
        successful: 95,
        failed: 5,
        averageExecutionTimeMs: 85,
        queryCounts: {
          'michaelis-menten': 60,
          'competitive-inhibition': 25,
          'non-competitive-inhibition': 10,
          'product-inhibition': 5
        }
      };

      const csv = exportStatisticsToCSV(stats);
      expect(csv).toContain('totalJobs,100');
      // The exporter's row labels are totalJobs / successfulJobs /
      // failedJobs -- one consistent naming scheme. The input field is
      // `stats.successful`; the OUTPUT label is `successfulJobs`, and the
      // output is what a CSV reader sees. The test asserted the input name.
      expect(csv).toContain('successfulJobs,95');
      expect(csv).toContain('failedJobs,5');
      expect(csv).toContain('# Query Distribution');
      expect(csv).toContain('michaelis-menten,60');
    });
  });

  describe('CSV Escaping Edge Cases', () => {
    it('handles quotes in field values', () => {
      const jobs = [
        {
          jobId: 'job_quotes',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: Date.now(),
          duration: 100,
          result: { finalValue: 1.0, confidence: 0.9, validated: false },
          parameters: { enzyme: 'test "enzyme" name' }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      // Should properly escape quotes
      expect(csv).toContain('""');
    });

    it('handles newlines in field values', () => {
      const jobs = [
        {
          jobId: 'job_newlines',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: Date.now(),
          duration: 100,
          result: { finalValue: 1.0, confidence: 0.9, validated: false },
          parameters: { note: 'line1\nline2' }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      // Should be quoted for newline handling
      expect(csv).toContain('"');
    });

    it('handles commas in field values', () => {
      const jobs = [
        {
          jobId: 'job_commas',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: Date.now(),
          duration: 100,
          result: { finalValue: 1.0, confidence: 0.9, validated: false },
          parameters: { enzyme: 'lactate, dehydrogenase' }
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      // Should be quoted for comma handling
      expect(csv).toContain('"');
    });

    it('handles null and undefined values', () => {
      const jobs = [
        {
          jobId: 'job_nulls',
          query: 'test',
          status: 'complete',
          startTime: Date.now(),
          endTime: null,
          duration: undefined,
          result: undefined,
          parameters: null
        }
      ];

      const csv = exportJobHistoryToCSV(jobs);
      // Should not crash, empty fields are OK
      expect(csv.length).toBeGreaterThan(0);
    });
  });
});
