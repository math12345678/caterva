import { randomUUID } from "node:crypto";
import type { SimulationDomain } from "./telluriumRunner";
import type { ParameterProvenance } from "./provenance";
import { logger } from "./logger";

export type JobStatus =
  | "pending"
  | "resolving"
  | "validating"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface SimulationResponse {
  runId: string;
  domain: SimulationDomain;
  parameters: Record<string, unknown>;
  trajectory: Record<string, unknown>[];
  provenance: {
    reasoning: string;
    modelCitations: string[];
    flags: string[];
  };
  parameterProvenance: Record<string, ParameterProvenance>;
  completedAt: string;
}

export interface Job {
  jobId: string;
  query: string;
  status: JobStatus;
  progress: number;
  result?: SimulationResponse;
  error?: { error: string; message: string };
  createdAt: string;
  updatedAt: string;
}

type Listener = (job: Job) => void;
type JobUpdate = Partial<Omit<Job, "jobId" | "createdAt" | "progress">>;

const jobs = new Map<string, Job>();
const listeners = new Map<string, Set<Listener>>();
const abortControllers = new Map<string, AbortController>();

// Semaphore for the Python bridge concurrency limit.
const MAX_CONCURRENT = 2;
let activeRunners = 0;
const pendingQueue: Array<{
  resolve: () => void;
  reject: (reason?: unknown) => void;
}> = [];

/**
 * Acquire a slot in the Python bridge semaphore. Resolves when concurrency
 * drops below MAX_CONCURRENT. Caller must release after finishing.
 */
export function acquireRunnerSlot(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (activeRunners < MAX_CONCURRENT) {
      activeRunners++;
      resolve();
    } else {
      pendingQueue.push({ resolve, reject });
    }
  });
}

/**
 * Release a slot in the Python bridge semaphore. If jobs are queued, the
 * next one acquires the slot immediately.
 */
export function releaseRunnerSlot(): void {
  const next = pendingQueue.shift();
  if (next) {
    next.resolve();
  } else {
    activeRunners = Math.max(0, activeRunners - 1);
  }
}

// Keep the in-memory job store from growing without bound. This is a simple
// demo guard; a production deployment would use Redis or a database.
const MAX_JOBS = 1000;

const progressForStatus: Record<JobStatus, number> = {
  pending: 0,
  resolving: 15,
  validating: 35,
  running: 60,
  completed: 100,
  failed: 100,
  cancelled: 100,
};

function now(): string {
  return new Date().toISOString();
}

export function createJob(query: string): Job {
  const jobId = randomUUID();
  const createdAt = now();
  const job: Job = {
    jobId,
    query,
    status: "pending",
    progress: progressForStatus.pending,
    createdAt,
    updatedAt: createdAt,
  };
  jobs.set(jobId, job);

  // Prune oldest completed/failed jobs if we exceed the in-memory limit.
  if (jobs.size > MAX_JOBS) {
    const oldest = Array.from(jobs.values())
      .filter((j) => j.status === "completed" || j.status === "failed")
      .sort(
        (a, b) =>
          new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime(),
      )[0];
    if (oldest) {
      jobs.delete(oldest.jobId);
      listeners.delete(oldest.jobId);
    }
  }

  return job;
}

export function getJob(jobId: string): Job | undefined {
  return jobs.get(jobId);
}

export function updateJob(jobId: string, update: JobUpdate): Job | undefined {
  const job = jobs.get(jobId);
  if (!job) return undefined;

  const next: Job = {
    ...job,
    ...update,
    updatedAt: now(),
  };

  if (update.status) {
    next.progress = progressForStatus[update.status];
  }

  jobs.set(jobId, next);

  const subs = listeners.get(jobId);
  if (subs) {
    for (const listener of subs) {
      try {
        listener(next);
      } catch (err) {
        // Listeners must not throw into the publisher - log and continue.
        logger.error(
          { err, jobId, status: next.status },
          "Job listener threw error; continuing",
        );
      }
    }
  }

  return next;
}

export function setJobResult(
  jobId: string,
  result: SimulationResponse,
): Job | undefined {
  return updateJob(jobId, { status: "completed", result });
}

export function setJobError(
  jobId: string,
  error: { error: string; message: string },
): Job | undefined {
  return updateJob(jobId, { status: "failed", error });
}

export function setJobCancelled(jobId: string): Job | undefined {
  const ctrl = abortControllers.get(jobId);
  if (ctrl && !ctrl.signal.aborted) {
    ctrl.abort();
  }
  return updateJob(jobId, { status: "cancelled" });
}

/**
 * Register an AbortController for a job. Used by the pipeline runner so that
 * cancelJob can signal the running Python process to stop.
 */
export function registerAbortController(
  jobId: string,
  ctrl: AbortController,
): void {
  abortControllers.set(jobId, ctrl);
}

/**
 * Returns true if the job has been requested to cancel. Pipeline stages
 * should check this between expensive operations.
 */
export function isCancelled(jobId: string): boolean {
  const job = jobs.get(jobId);
  return job?.status === "cancelled";
}

export function cancelJob(jobId: string): Job | undefined {
  const job = jobs.get(jobId);
  if (!job) return undefined;
  if (
    job.status === "completed" ||
    job.status === "failed" ||
    job.status === "cancelled"
  ) {
    return job;
  }
  return setJobCancelled(jobId);
}

export function subscribe(jobId: string, listener: Listener): () => void {
  let subs = listeners.get(jobId);
  if (!subs) {
    subs = new Set();
    listeners.set(jobId, subs);
  }
  subs.add(listener);

  return () => {
    const current = listeners.get(jobId);
    if (current) {
      current.delete(listener);
      if (current.size === 0) {
        listeners.delete(jobId);
      }
    }
  };
}

/**
 * Clean up internal state for a job. Called once the job has finished and
 * listeners have been notified. Completed jobs remain queryable via getJob
 * until the process restarts; this just removes the listener set to avoid
 * leaking memory.
 */
export function cleanupJob(jobId: string): void {
  listeners.delete(jobId);
}

export function listJobs(): Job[] {
  return Array.from(jobs.values()).sort((a, b) => {
    const timeDiff =
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
    if (timeDiff !== 0) return timeDiff;
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });
}

/**
 * Reset all internal state. Intended for test use only.
 */
export function reset(): void {
  for (const controller of abortControllers.values()) {
    if (!controller.signal.aborted) controller.abort();
  }
  jobs.clear();
  listeners.clear();
  abortControllers.clear();
  // Cancel waiters rather than resolving them as if they acquired a slot.
  // Resolving would make their later release decrement activeRunners even
  // though no slot was transferred, corrupting the semaphore accounting.
  const pending = pendingQueue.splice(0);
  for (const waiter of pending) {
    waiter.reject(new Error("Runner queue reset"));
  }
  // Do not reset activeRunners here. Aborted pipelines may still be
  // unwinding and will release their slots; clearing the count would allow
  // new work to exceed MAX_CONCURRENT when those releases arrive.
}
