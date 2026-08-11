/**
 * Batch Job Manager
 *
 * Manages simulation jobs with:
 * - Job queuing and scheduling
 * - Progress tracking
 * - Result aggregation
 * - Error recovery
 */

import { logger } from '../logger';

// Simple UUID generator
function generateId(): string {
  return Math.random().toString(36).substring(2, 10) + Date.now().toString(36).substring(6);
}

// ============================================================================
// JOB DEFINITIONS
// ============================================================================

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface JobTask {
  id: string;
  name: string;
  query: string;
  parameters: Record<string, number>;
  priority?: number;
}

export interface JobResult {
  jobId: string;
  taskId: string;
  status: JobStatus;
  result?: unknown;
  error?: string;
  startTime: number;
  endTime?: number;
  duration?: number;
}

export interface Job {
  id: string;
  name: string;
  tasks: JobTask[];
  status: JobStatus;
  createdAt: number;
  startedAt?: number;
  completedAt?: number;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  results: Map<string, JobResult>;
  progress: number;
}

// ============================================================================
// JOB MANAGER
// ============================================================================

export class JobManager {
  private jobs: Map<string, Job> = new Map();
  private queue: string[] = [];
  private maxConcurrent: number = 3;
  private activeJobs: Set<string> = new Set();

  constructor(maxConcurrent: number = 3) {
    this.maxConcurrent = maxConcurrent;
  }

  /**
   * Create a new batch job
   */
  createJob(name: string, tasks: JobTask[]): Job {
    const jobId = generateId().substring(0, 8);
    const job: Job = {
      id: jobId,
      name,
      tasks,
      status: 'pending',
      createdAt: Date.now(),
      totalTasks: tasks.length,
      completedTasks: 0,
      failedTasks: 0,
      results: new Map(),
      progress: 0
    };

    this.jobs.set(jobId, job);
    this.queue.push(jobId);

    logger.info({ jobId, taskCount: tasks.length }, 'Job created');
    return job;
  }

  /**
   * Get job status
   */
  getJob(jobId: string): Job | undefined {
    return this.jobs.get(jobId);
  }

  /**
   * Get all jobs
   */
  getAllJobs(): Job[] {
    return Array.from(this.jobs.values());
  }

  /**
   * Start job processing
   */
  async processQueue(): Promise<void> {
    while (this.queue.length > 0 || this.activeJobs.size > 0) {
      // Start new jobs if below concurrency limit
      while (this.queue.length > 0 && this.activeJobs.size < this.maxConcurrent) {
        const jobId = this.queue.shift();
        if (jobId) {
          this.activeJobs.add(jobId);
          this.processJob(jobId).catch(err => {
            logger.error({ jobId, error: err }, 'Job processing failed');
            const job = this.jobs.get(jobId);
            if (job) job.status = 'failed';
          });
        }
      }

      // Wait a bit before checking again
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }

  /**
   * Process individual job
   */
  private async processJob(jobId: string): Promise<void> {
    const job = this.jobs.get(jobId);
    if (!job) return;

    job.status = 'running';
    job.startedAt = Date.now();

    logger.info({ jobId, name: job.name }, 'Job processing started');

    for (const task of job.tasks) {
      try {
        const startTime = Date.now();

        // Simulate task execution (in real implementation, call ScientificPipeline)
        const result = await this.executeTask(task);

        const duration = Date.now() - startTime;

        job.results.set(task.id, {
          jobId,
          taskId: task.id,
          status: 'completed',
          result,
          startTime,
          endTime: Date.now(),
          duration
        });

        job.completedTasks++;
      } catch (error) {
        job.results.set(task.id, {
          jobId,
          taskId: task.id,
          status: 'failed',
          error: error instanceof Error ? error.message : String(error),
          startTime: Date.now()
        });

        job.failedTasks++;

        logger.warn({ jobId, taskId: task.id, error }, 'Task failed');
      }

      this.updateProgress(jobId);
    }

    job.status = 'completed';
    job.completedAt = Date.now();
    this.activeJobs.delete(jobId);

    logger.info(
      {
        jobId,
        completed: job.completedTasks,
        failed: job.failedTasks,
        duration: job.completedAt - job.startedAt!
      },
      'Job completed'
    );
  }

  /**
   * Execute individual task (placeholder)
   */
  private async executeTask(task: JobTask): Promise<unknown> {
    // In real implementation, this would call ScientificPipeline.execute()
    // For now, simulate with a delay
    return new Promise(resolve => {
      setTimeout(() => {
        resolve({
          taskId: task.id,
          query: task.query,
          parameters: task.parameters,
          finalValue: Math.random() * 10,
          confidence: 0.85 + Math.random() * 0.1
        });
      }, 100 + Math.random() * 200);
    });
  }

  /**
   * Update job progress
   */
  private updateProgress(jobId: string): void {
    const job = this.jobs.get(jobId);
    if (!job) return;

    job.progress = (job.completedTasks / job.totalTasks) * 100;

    logger.debug(
      { jobId, progress: job.progress.toFixed(1), completed: job.completedTasks },
      'Job progress updated'
    );
  }

  /**
   * Cancel job
   */
  cancelJob(jobId: string): boolean {
    const job = this.jobs.get(jobId);
    if (!job) return false;

    if (job.status === 'running') {
      job.status = 'cancelled';
      this.activeJobs.delete(jobId);
      logger.info({ jobId }, 'Job cancelled');
      return true;
    }

    return false;
  }

  /**
   * Get job results
   */
  getResults(jobId: string): JobResult[] {
    const job = this.jobs.get(jobId);
    return job ? Array.from(job.results.values()) : [];
  }

  /**
   * Get aggregate statistics
   */
  getStatistics(jobId: string): {
    totalTasks: number;
    completed: number;
    failed: number;
    successRate: number;
    avgDuration: number;
    totalDuration: number;
  } | null {
    const job = this.jobs.get(jobId);
    if (!job) return null;

    const completed = job.completedTasks;
    const failed = job.failedTasks;
    const total = job.totalTasks;

    const results = Array.from(job.results.values());
    const durations = results
      .filter(r => r.duration !== undefined)
      .map(r => r.duration!);

    const avgDuration = durations.length > 0
      ? durations.reduce((a, b) => a + b) / durations.length
      : 0;

    const totalDuration = job.completedAt && job.startedAt
      ? job.completedAt - job.startedAt
      : 0;

    return {
      totalTasks: total,
      completed,
      failed,
      successRate: total > 0 ? (completed / total) * 100 : 0,
      avgDuration,
      totalDuration
    };
  }

  /**
   * Export results to JSON
   */
  exportResults(jobId: string): unknown {
    const job = this.jobs.get(jobId);
    if (!job) return null;

    const stats = this.getStatistics(jobId);
    const results = this.getResults(jobId);

    return {
      job: {
        id: job.id,
        name: job.name,
        status: job.status,
        createdAt: new Date(job.createdAt).toISOString(),
        startedAt: job.startedAt ? new Date(job.startedAt).toISOString() : null,
        completedAt: job.completedAt ? new Date(job.completedAt).toISOString() : null
      },
      statistics: stats,
      results: results.map(r => ({
        ...r,
        startTime: new Date(r.startTime).toISOString(),
        endTime: r.endTime ? new Date(r.endTime).toISOString() : null
      }))
    };
  }

  /**
   * Clear completed jobs
   */
  clearCompleted(): number {
    let cleared = 0;
    for (const [jobId, job] of this.jobs) {
      if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
        this.jobs.delete(jobId);
        cleared++;
      }
    }
    logger.info({ cleared }, 'Completed jobs cleared');
    return cleared;
  }
}

// ============================================================================
// SINGLETON INSTANCE
// ============================================================================

export const jobManager = new JobManager();

// ============================================================================
// EXAMPLE USAGE
// ============================================================================

/*
// Create jobs with multiple variants
const variants = [
  { id: '1', name: 'Wild-type', query: 'ldh', parameters: { km: 5.2, vmax: 12.8, s0: 10 } },
  { id: '2', name: 'V156K', query: 'ldh', parameters: { km: 5.8, vmax: 10.5, s0: 10 } },
  { id: '3', name: 'L140F', query: 'ldh', parameters: { km: 4.9, vmax: 15.2, s0: 10 } }
];

const job = jobManager.createJob('enzyme-screening-2024', variants);

// Process queue (runs concurrently with maxConcurrent limit)
await jobManager.processQueue();

// Get results and statistics
const stats = jobManager.getStatistics(job.id);
const results = jobManager.getResults(job.id);
const exported = jobManager.exportResults(job.id);
*/
