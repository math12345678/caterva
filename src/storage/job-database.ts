/**
 * Job Database — Persistent Storage
 *
 * Stores simulation jobs to SQLite so they survive server restarts.
 * Provides query/retrieval interface for CLI and API.
 */

import * as fs from 'fs';
import * as path from 'path';
import { logger } from '../logger';

export interface StoredJob {
  jobId: string;
  query: string;
  parameters: Record<string, number>;
  status: 'running' | 'complete' | 'error';
  result?: any;
  error?: string;
  startTime: number;
  endTime?: number;
  duration?: number;
}

/**
 * Simple file-based storage (no external dependencies)
 *
 * Uses JSON lines format for easy querying:
 * - One job per line
 * - Each line is valid JSON
 * - No parsing of whole file needed
 */
export class JobDatabase {
  private dbPath: string;

  constructor(dbPath: string = './terrium-jobs.jsonl') {
    this.dbPath = dbPath;

    // Create file if doesn't exist
    if (!fs.existsSync(dbPath)) {
      fs.writeFileSync(dbPath, '', 'utf-8');
      logger.info({ path: dbPath }, 'Created job database');
    }
  }

  /**
   * Save job to database
   */
  saveJob(job: StoredJob): void {
    try {
      const line = JSON.stringify(job) + '\n';
      fs.appendFileSync(this.dbPath, line, 'utf-8');
      logger.debug({ jobId: job.jobId }, 'Job saved to database');
    } catch (error) {
      logger.error({ jobId: job.jobId, error }, 'Failed to save job');
    }
  }

  /**
   * Update existing job
   */
  updateJob(jobId: string, updates: Partial<StoredJob>): void {
    try {
      const jobs = this.getAllJobs();
      const index = jobs.findIndex(j => j.jobId === jobId);

      if (index === -1) {
        logger.warn({ jobId }, 'Job not found for update');
        return;
      }

      jobs[index] = { ...jobs[index], ...updates };
      this.writeAllJobs(jobs);
      logger.debug({ jobId }, 'Job updated in database');
    } catch (error) {
      logger.error({ jobId, error }, 'Failed to update job');
    }
  }

  /**
   * Get single job by ID
   */
  getJob(jobId: string): StoredJob | null {
    try {
      const jobs = this.getAllJobs();
      return jobs.find(j => j.jobId === jobId) || null;
    } catch (error) {
      logger.error({ jobId, error }, 'Failed to get job');
      return null;
    }
  }

  /**
   * Get all jobs
   */
  getAllJobs(): StoredJob[] {
    try {
      const content = fs.readFileSync(this.dbPath, 'utf-8');
      if (!content.trim()) return [];

      return content
        .trim()
        .split('\n')
        .filter(line => line.trim())
        .map(line => JSON.parse(line));
    } catch (error) {
      logger.error({ error }, 'Failed to read jobs');
      return [];
    }
  }

  /**
   * Get recent jobs (last N)
   */
  getRecentJobs(limit: number = 20): StoredJob[] {
    const jobs = this.getAllJobs();
    return jobs.slice(-limit);
  }

  /**
   * Get jobs by status
   */
  getJobsByStatus(status: string): StoredJob[] {
    return this.getAllJobs().filter(j => j.status === status);
  }

  /**
   * Get jobs by query type
   */
  getJobsByQuery(query: string): StoredJob[] {
    return this.getAllJobs().filter(j => j.query === query);
  }

  /**
   * Get statistics
   */
  getStatistics(): {
    totalJobs: number;
    successful: number;
    failed: number;
    running: number;
    averageExecutionTimeMs: number;
    queryCounts: Record<string, number>;
  } {
    const jobs = this.getAllJobs();
    const completed = jobs.filter(j => j.status === 'complete');
    const successful = completed.filter(j => !j.error).length;
    const failed = jobs.filter(j => j.status === 'error').length;
    const running = jobs.filter(j => j.status === 'running').length;

    const executionTimes = completed
      .filter(j => j.duration)
      .map(j => j.duration!);
    const averageExecutionTimeMs =
      executionTimes.length > 0
        ? executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length
        : 0;

    const queryCounts: Record<string, number> = {};
    jobs.forEach(j => {
      queryCounts[j.query] = (queryCounts[j.query] || 0) + 1;
    });

    return {
      totalJobs: jobs.length,
      successful,
      failed,
      running,
      averageExecutionTimeMs,
      queryCounts
    };
  }

  /**
   * Clear old jobs (older than X days)
   */
  clearOldJobs(daysOld: number): number {
    try {
      const cutoffTime = Date.now() - daysOld * 24 * 60 * 60 * 1000;
      const jobs = this.getAllJobs().filter(j => (j.endTime || j.startTime) > cutoffTime);

      const removed = this.getAllJobs().length - jobs.length;
      this.writeAllJobs(jobs);

      logger.info({ removed, daysOld }, `Cleaned up old jobs`);
      return removed;
    } catch (error) {
      logger.error({ error }, 'Failed to clean old jobs');
      return 0;
    }
  }

  /**
   * Export jobs to CSV
   */
  exportToCSV(filePath: string): void {
    try {
      const jobs = this.getAllJobs();
      const headers = ['jobId', 'query', 'status', 'startTime', 'endTime', 'duration', 'error'];
      const lines = [headers.join(',')];

      for (const job of jobs) {
        const row = [
          job.jobId,
          job.query,
          job.status,
          new Date(job.startTime).toISOString(),
          job.endTime ? new Date(job.endTime).toISOString() : '',
          job.duration || '',
          job.error || ''
        ];
        lines.push(row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
      }

      fs.writeFileSync(filePath, lines.join('\n'), 'utf-8');
      logger.info({ filePath, count: jobs.length }, 'Exported jobs to CSV');
    } catch (error) {
      logger.error({ error }, 'Failed to export to CSV');
    }
  }

  /**
   * Internal: Write all jobs
   */
  private writeAllJobs(jobs: StoredJob[]): void {
    const lines = jobs.map(j => JSON.stringify(j) + '\n').join('');
    fs.writeFileSync(this.dbPath, lines, 'utf-8');
  }
}

// Default instance
let defaultDb: JobDatabase | null = null;

export function getDefaultDatabase(): JobDatabase {
  if (!defaultDb) {
    defaultDb = new JobDatabase('./terrium-jobs.jsonl');
  }
  return defaultDb;
}
