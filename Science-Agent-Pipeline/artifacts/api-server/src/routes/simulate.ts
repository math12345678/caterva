import { Router, type IRouter, type Request, type Response, type NextFunction } from "express";
import { desc, eq } from "drizzle-orm";
import { RunSimulationBody, GetSimulationJobParams, StreamSimulationJobParams } from "@workspace/api-zod";
import { getDb, isDbAvailable, simulationsTable } from "@workspace/db";
import { logger } from "../lib/logger";
import { resolveQuery } from "../lib/queryResolver";
import { runTellurium } from "../lib/telluriumRunner";
import * as queue from "../lib/queue";
import { findCachedResultByQuery, persistJob } from "../lib/cache";
import { simulateLimiter } from "../lib/rateLimit";

const router: IRouter = Router();

/** Terminal states that cannot transition further. */
const TERMINAL = new Set<queue.JobStatus>(["completed", "failed", "cancelled"]);

/**
 * GET /api/simulate
 *
 * Returns the most recent simulation jobs from the in-memory queue, ordered
 * by updatedAt descending. This is a lightweight "runs dashboard" endpoint
 * that lets clients show a history of pipeline runs.
 */
router.get("/simulate", async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const jobs = queue.listJobs();
    res.json(jobs);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/simulate
 *
 * Enqueues a new science-agent simulation job and immediately returns a
 * 202 Accepted job object. The actual pipeline runs asynchronously; clients
 * can poll `GET /simulate/:jobId` or subscribe to `GET /simulate/:jobId/stream`
 * for real-time progress updates.
 */
router.post("/simulate", simulateLimiter, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const parse = RunSimulationBody.safeParse(req.body);
    if (!parse.success) {
      res.status(400).json({
        error: "BAD_REQUEST",
        message: parse.error.errors.map((e) => e.message).join("; "),
      });
      return;
    }

    const { query } = parse.data;
    const normalizedQuery = normalizeQuery(query);
    logger.info({ query, normalizedQuery }, "Enqueuing simulation job");

    const cached = isDbAvailable() ? await findCachedSimulation(normalizedQuery) : findCachedResultByQuery(normalizedQuery);
    if (cached) {
      logger.info({ query }, "Returning cached simulation result");
      const job = queue.createJob(query);
      queue.setJobResult(job.jobId, cached);
      res.status(202).json(job);
      return;
    }

    const job = queue.createJob(query);

    // Run the pipeline asynchronously. Errors are captured in the job state.
    runPipeline(job.jobId, query).catch((err) => {
      logger.error({ err, jobId: job.jobId }, "Pipeline runner threw unexpectedly");
      queue.setJobError(job.jobId, {
        error: "INTERNAL_SERVER_ERROR",
        message: err instanceof Error ? err.message : "Unexpected pipeline failure",
      });
    });

    res.status(202).json(job);
  } catch (err) {
    next(err);
  }
});

/**
 * Normalize a query so that tiny whitespace/casing differences hit the cache.
 */
function normalizeQuery(query: string): string {
  return query.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * GET /api/simulate/:jobId
 *
 * Returns the current state of a simulation job, including its result if it
 * has completed.
 */
router.get("/simulate/:jobId", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const params = GetSimulationJobParams.safeParse(req.params);
    if (!params.success) {
      res.status(400).json({
        error: "BAD_REQUEST",
        message: params.error.errors.map((e) => e.message).join("; "),
      });
      return;
    }

    const job = queue.getJob(params.data.jobId);
    if (!job) {
      res.status(404).json({ error: "NOT_FOUND", message: "Simulation job not found" });
      return;
    }

    res.json(job);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/simulate/:jobId/stream
 *
 * Server-Sent Events endpoint that pushes the job state every time it changes.
 * The stream closes automatically once the job reaches a terminal state
 * (completed or failed).
 */
router.get("/simulate/:jobId/stream", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const params = StreamSimulationJobParams.safeParse(req.params);
    if (!params.success) {
      res.status(400).json({
        error: "BAD_REQUEST",
        message: params.error.errors.map((e) => e.message).join("; "),
      });
      return;
    }

    const { jobId } = params.data;
    const job = queue.getJob(jobId);
    if (!job) {
      res.status(404).json({ error: "NOT_FOUND", message: "Simulation job not found" });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    const send = (data: queue.Job) => {
      res.write(`data: ${JSON.stringify(data)}\n\n`);
    };

    send(job);

    const unsubscribe = queue.subscribe(jobId, (updated) => {
      send(updated);
      if (updated.status === "completed" || updated.status === "failed" || updated.status === "cancelled") {
        unsubscribe();
        queue.cleanupJob(jobId);
        res.end();
      }
    });

    req.on("close", () => {
      unsubscribe();
    });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/simulate/:jobId/cancel
 *
 * Cancels a running simulation job. Jobs in terminal states are no-ops.
 * The pipeline runner checks for cancellation between stages and the
 * Python process receives SIGTERM.
 */
router.post("/simulate/:jobId/cancel", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const jobId = req.params.jobId as string;
    const job = queue.getJob(jobId);
    if (!job) {
      res.status(404).json({ error: "NOT_FOUND", message: "Simulation job not found" });
      return;
    }
    if (TERMINAL.has(job.status)) {
      res.status(409).json({ error: "ALREADY_TERMINAL", message: `Job is already ${job.status}` });
      return;
    }
    const updated = queue.cancelJob(jobId);
    logger.info({ jobId, status: updated?.status }, "Job cancelled");
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/simulate/:jobId/export
 *
 * Export the simulation trajectory as a CSV file. Great for researchers
 * who want to import results into R, Python, or Excel.
 */
router.get("/simulate/:jobId/export", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const jobId = req.params.jobId as string;
    const job = queue.getJob(jobId);
    if (!job) {
      res.status(404).json({ error: "NOT_FOUND", message: "Simulation job not found" });
      return;
    }
    if (!job.result || !job.result.trajectory || job.result.trajectory.length === 0) {
      res.status(409).json({ error: "NO_DATA", message: "Job has no trajectory data to export" });
      return;
    }

    const trajectory = job.result.trajectory;
    const headers = Object.keys(trajectory[0]!);
    const rows = trajectory.map((point) => headers.map((h) => String(point[h] ?? "")).join(","));

    res.setHeader("Content-Type", "text/csv");
    res.setHeader("Content-Disposition", `attachment; filename="simulation-${jobId.slice(0, 8)}.csv"`);
    res.send([headers.join(","), ...rows].join("\n"));
  } catch (err) {
    next(err);
  }
});

/**
 * Look up a previously-completed simulation with the same query. This is a
 * naive but effective cache: identical natural-language queries produce the
 * same resolved parameters, so we can short-circuit the engine entirely.
 */
async function findCachedSimulation(query: string): Promise<queue.SimulationResponse | undefined> {
  try {
    const db = getDb();
    if (!db) return undefined;

    const rows = await db
      .select()
      .from(simulationsTable)
      .where(eq(simulationsTable.query, query))
      .orderBy(desc(simulationsTable.createdAt))
      .limit(1);

    if (rows.length === 0) return undefined;

    const row = rows[0];
    if (!row) return undefined;

    return {
      runId: String(row.id),
      domain: row.domain,
      parameters: (row.parameters as Record<string, unknown>) || {},
      trajectory: (row.trajectory as Record<string, unknown>[]) || [],
      provenance: (row.provenance as { reasoning: string; citations: string[]; flags: string[] }) || {
        reasoning: "",
        citations: [],
        flags: [],
      },
      completedAt: row.createdAt.toISOString(),
    };
  } catch (err) {
    logger.warn({ err }, "Cache lookup failed; continuing without cache");
    return undefined;
  }
}

/**
 * The core science-agent pipeline. Each stage updates the job state so that
 * SSE and polling clients can observe progress.
 *
 * Stages:
 *   1. Resolve domain and parameters (keyword/regex or LLM fallback).
 *   2. Validate parameters.
 *   3. Run the Tellurium engine (with concurrency limit).
 *   4. Persist to PostgreSQL for provenance.
 *   5. Mark job completed (or failed).
 *
 * Between each stage we check for cancellation. Jobs that are cancelled
 * mid-flight are marked as cancelled rather than failed.
 */
async function runPipeline(jobId: string, query: string): Promise<void> {
  const abort = new AbortController();
  queue.registerAbortController(jobId, abort);

  try {
    if (queue.isCancelled(jobId)) return;

    queue.updateJob(jobId, { status: "resolving" });
    const resolved = await resolveQuery(query);

    if (queue.isCancelled(jobId)) return;
    queue.updateJob(jobId, { status: "validating" });
    validateParameters(resolved.domain, resolved.parameters);

    if (queue.isCancelled(jobId)) return;
    queue.updateJob(jobId, { status: "running" });

    await queue.acquireRunnerSlot();
    let engineResult;
    try {
      engineResult = await runTellurium(resolved.domain, resolved.parameters, abort.signal);
    } finally {
      queue.releaseRunnerSlot();
    }

    if (queue.isCancelled(jobId)) return;

    const provenance = {
      reasoning: resolved.provenance.reasoning,
      citations: resolved.provenance.citations,
      flags: [
        ...resolved.provenance.flags,
        ...(engineResult.flagged && engineResult.flagReason ? [engineResult.flagReason] : []),
      ],
    };
    const db = getDb();
    if (db) {
      await db.insert(simulationsTable).values({
        query,
        domain: engineResult.domain,
        parameters: engineResult.parameters,
        trajectory: engineResult.trajectory,
        provenance,
      });
    } else {
      logger.debug({ jobId }, "Database unavailable; skipping persistence for this run");
    }

    const result: queue.SimulationResponse = {
      runId: resolved.runId,
      domain: engineResult.domain,
      parameters: engineResult.parameters,
      trajectory: engineResult.trajectory,
      provenance,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
    persistJob(queue.getJob(jobId)!).catch(() => {});
  } catch (err) {
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
    } else {
      queue.setJobError(jobId, {
        error: "PIPELINE_ERROR",
        message: err instanceof Error ? err.message : "Unexpected pipeline failure",
      });
    }
    persistJob(queue.getJob(jobId)!).catch(() => {});
  }
}

/**
 * Basic validation of resolved parameters before invoking the engine. This is
 * intentionally lightweight; the engine itself performs more thorough checks.
 */
function validateParameters(domain: string, parameters: Record<string, number>): void {
  const required: Record<string, string[]> = {
    mm: ["km", "vmax", "s0"],
    sir: ["beta", "gamma", "s0", "i0"],
    seir: ["beta", "sigma", "gamma", "s0", "e0", "i0"],
  };

  const fields = required[domain];
  if (!fields) {
    throw new Error(`Unknown simulation domain: ${domain}`);
  }

  for (const field of fields) {
    const value = parameters[field];
    if (value === undefined || Number.isNaN(value)) {
      throw new Error(`Missing or invalid required parameter: ${field}`);
    }
  }
}

export default router;
