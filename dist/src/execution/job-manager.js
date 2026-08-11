"use strict";
/**
 * Batch Job Manager
 *
 * Manages simulation jobs with:
 * - Job queuing and scheduling
 * - Progress tracking
 * - Result aggregation
 * - Error recovery
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.jobManager = exports.JobManager = void 0;
exports.historyPath = historyPath;
const logger_1 = require("../logger");
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
// Simple UUID generator
function generateId() {
    return Math.random().toString(36).substring(2, 10) + Date.now().toString(36).substring(6);
}
// ============================================================================
// JOB MANAGER
// ============================================================================
/**
 * Where run history is kept between invocations.
 *
 * A CLI process exits after every command, so an in-memory job store is
 * empty on the next run. That is why `scientific verify <jobId>` and
 * `check-integrity <jobId>` could never work: they print a job id at the
 * end of a simulation and then, in a new process, have no record of it.
 *
 * Overridable so tests do not write into a developer's real history.
 */
function historyPath() {
    const override = process.env['TERRIUM_HISTORY_FILE'];
    if (override)
        return override;
    return path.join(os.homedir(), '.terrium', 'history.json');
}
class JobManager {
    jobs = new Map();
    queue = [];
    maxConcurrent = 3;
    activeJobs = new Set();
    constructor(maxConcurrent = 3) {
        this.maxConcurrent = maxConcurrent;
    }
    /**
     * Append a completed run to the on-disk history.
     *
     * Best-effort by design: a CLI must not fail a successful simulation
     * because it could not write a history file. But the failure is
     * REPORTED, not swallowed -- silently losing history would make
     * `verify` mysteriously not find a job the user just watched complete.
     */
    static recordRun(record) {
        try {
            const file = historyPath();
            fs.mkdirSync(path.dirname(file), { recursive: true });
            const existing = JobManager.readHistory();
            existing.push(record);
            // Bounded: history is a convenience, not an archive, and an
            // unbounded JSON file read on every invocation gets slow.
            const trimmed = existing.slice(-200);
            fs.writeFileSync(file, JSON.stringify(trimmed, null, 2), 'utf-8');
            return { ok: true };
        }
        catch (error) {
            const reason = error instanceof Error ? error.message : String(error);
            logger_1.logger.warn({ error: reason }, 'Could not write run history');
            return { ok: false, reason };
        }
    }
    /** Every recorded run, newest last. Returns [] when there is no history
     *  file -- but throws nothing, so a corrupt file cannot break the CLI. */
    static readHistory() {
        const file = historyPath();
        if (!fs.existsSync(file))
            return [];
        try {
            const parsed = JSON.parse(fs.readFileSync(file, 'utf-8'));
            return Array.isArray(parsed) ? parsed : [];
        }
        catch (error) {
            logger_1.logger.warn({ error: error instanceof Error ? error.message : String(error) }, 'Run history file is unreadable; treating as empty');
            return [];
        }
    }
    /** One run by id, or undefined. */
    static findRun(jobId) {
        return JobManager.readHistory().find((r) => r.jobId === jobId);
    }
    /**
     * Create a new batch job
     */
    createJob(name, tasks) {
        const jobId = generateId().substring(0, 8);
        const job = {
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
        logger_1.logger.info({ jobId, taskCount: tasks.length }, 'Job created');
        return job;
    }
    /**
     * Get job status
     */
    getJob(jobId) {
        return this.jobs.get(jobId);
    }
    /**
     * Get all jobs
     */
    getAllJobs() {
        return Array.from(this.jobs.values());
    }
    /**
     * Start job processing
     */
    async processQueue() {
        while (this.queue.length > 0 || this.activeJobs.size > 0) {
            // Start new jobs if below concurrency limit
            while (this.queue.length > 0 && this.activeJobs.size < this.maxConcurrent) {
                const jobId = this.queue.shift();
                if (jobId) {
                    this.activeJobs.add(jobId);
                    this.processJob(jobId).catch(err => {
                        logger_1.logger.error({ jobId, error: err }, 'Job processing failed');
                        const job = this.jobs.get(jobId);
                        if (job)
                            job.status = 'failed';
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
    async processJob(jobId) {
        const job = this.jobs.get(jobId);
        if (!job)
            return;
        job.status = 'running';
        job.startedAt = Date.now();
        logger_1.logger.info({ jobId, name: job.name }, 'Job processing started');
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
            }
            catch (error) {
                job.results.set(task.id, {
                    jobId,
                    taskId: task.id,
                    status: 'failed',
                    error: error instanceof Error ? error.message : String(error),
                    startTime: Date.now()
                });
                job.failedTasks++;
                logger_1.logger.warn({ jobId, taskId: task.id, error }, 'Task failed');
            }
            this.updateProgress(jobId);
        }
        job.status = 'completed';
        job.completedAt = Date.now();
        this.activeJobs.delete(jobId);
        logger_1.logger.info({
            jobId,
            completed: job.completedTasks,
            failed: job.failedTasks,
            duration: job.completedAt - job.startedAt
        }, 'Job completed');
    }
    /**
     * Execute individual task (placeholder)
     */
    async executeTask(task) {
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
    updateProgress(jobId) {
        const job = this.jobs.get(jobId);
        if (!job)
            return;
        job.progress = (job.completedTasks / job.totalTasks) * 100;
        logger_1.logger.debug({ jobId, progress: job.progress.toFixed(1), completed: job.completedTasks }, 'Job progress updated');
    }
    /**
     * Cancel job
     */
    cancelJob(jobId) {
        const job = this.jobs.get(jobId);
        if (!job)
            return false;
        if (job.status === 'running') {
            job.status = 'cancelled';
            this.activeJobs.delete(jobId);
            logger_1.logger.info({ jobId }, 'Job cancelled');
            return true;
        }
        return false;
    }
    /**
     * Get job results
     */
    getResults(jobId) {
        const job = this.jobs.get(jobId);
        return job ? Array.from(job.results.values()) : [];
    }
    /**
     * Get aggregate statistics
     */
    getStatistics(jobId) {
        const job = this.jobs.get(jobId);
        if (!job)
            return null;
        const completed = job.completedTasks;
        const failed = job.failedTasks;
        const total = job.totalTasks;
        const results = Array.from(job.results.values());
        const durations = results
            .filter(r => r.duration !== undefined)
            .map(r => r.duration);
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
    exportResults(jobId) {
        const job = this.jobs.get(jobId);
        if (!job)
            return null;
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
    clearCompleted() {
        let cleared = 0;
        for (const [jobId, job] of this.jobs) {
            if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
                this.jobs.delete(jobId);
                cleared++;
            }
        }
        logger_1.logger.info({ cleared }, 'Completed jobs cleared');
        return cleared;
    }
}
exports.JobManager = JobManager;
// ============================================================================
// SINGLETON INSTANCE
// ============================================================================
exports.jobManager = new JobManager();
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
