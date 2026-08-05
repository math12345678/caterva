import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import { desc, sql } from "drizzle-orm";
import {
  RunSimulationBody,
  GetSimulationJobParams,
  StreamSimulationJobParams,
} from "@workspace/api-zod";
import { getDb, isDbAvailable, simulationsTable } from "@workspace/db";
import { logger } from "../lib/logger";
import { resolveQuery } from "../lib/queryResolver";
import { runTellurium, type SimulationDomain } from "../lib/telluriumRunner";
import { SimulationParameterSchemas } from "../lib/schemas";
import * as queue from "../lib/queue";
import { findCachedResultByQuery, persistJob } from "../lib/cache";
import { simulateLimiter } from "../lib/rateLimit";
import {
  RequiredParametersMissingError,
  validateParameterProvenance,
  type ParameterProvenance,
} from "../lib/provenance";

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
router.get(
  "/simulate",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const jobs = queue.listJobs();
      res.json(jobs);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * POST /api/simulate
 *
 * Enqueues a new science-agent simulation job and immediately returns a
 * 202 Accepted job object. The actual pipeline runs asynchronously; clients
 * can poll `GET /simulate/:jobId` or subscribe to `GET /simulate/:jobId/stream`
 * for real-time progress updates.
 */
router.post(
  "/simulate",
  simulateLimiter,
  async (req: Request, res: Response, next: NextFunction) => {
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

      const cached = isDbAvailable()
        ? await findCachedSimulation(normalizedQuery)
        : findCachedResultByQuery(normalizedQuery);
      if (cached) {
        logger.info({ query }, "Returning cached simulation result");
        const job = queue.createJob(query);
        queue.setJobResult(job.jobId, cached);
        guardSerializationProvenance(cached);
        res.status(202).json(job);
        return;
      }

      const job = queue.createJob(query);

      // Run the pipeline asynchronously. Errors are captured in the job state.
      runPipeline(job.jobId, query).catch((err) => {
        logger.error(
          { err, jobId: job.jobId },
          "Pipeline runner threw unexpectedly",
        );
        queue.setJobError(job.jobId, {
          error: "INTERNAL_SERVER_ERROR",
          message:
            err instanceof Error ? err.message : "Unexpected pipeline failure",
        });
      });

      res.status(202).json(job);
    } catch (err) {
      next(err);
    }
  },
);

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
router.get(
  "/simulate/:jobId",
  async (req: Request, res: Response, next: NextFunction) => {
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
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      if (job.result) guardSerializationProvenance(job.result);

      res.json(job);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/stream
 *
 * Server-Sent Events endpoint that pushes the job state every time it changes.
 * The stream closes automatically once the job reaches a terminal state
 * (completed or failed).
 */
router.get(
  "/simulate/:jobId/stream",
  async (req: Request, res: Response, next: NextFunction) => {
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
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.flushHeaders();

      const send = (data: queue.Job) => {
        if (data.result) guardSerializationProvenance(data.result);
        res.write(`data: ${JSON.stringify(data)}\n\n`);
      };

      send(job);

      const unsubscribe = queue.subscribe(jobId, (updated) => {
        send(updated);
        if (
          updated.status === "completed" ||
          updated.status === "failed" ||
          updated.status === "cancelled"
        ) {
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
  },
);

/**
 * POST /api/simulate/:jobId/cancel
 *
 * Cancels a running simulation job. Jobs in terminal states are no-ops.
 * The pipeline runner checks for cancellation between stages and the
 * Python process receives SIGTERM.
 */
router.post(
  "/simulate/:jobId/cancel",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }
      if (TERMINAL.has(job.status)) {
        res.status(409).json({
          error: "ALREADY_TERMINAL",
          message: `Job is already ${job.status}`,
        });
        return;
      }
      const updated = queue.cancelJob(jobId);
      logger.info({ jobId, status: updated?.status }, "Job cancelled");
      res.json(updated);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/export
 *
 * Export the simulation trajectory as a CSV file. Great for researchers
 * who want to import results into R, Python, or Excel.
 */
router.get(
  "/simulate/:jobId/export",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }
      if (
        !job.result ||
        !job.result.trajectory ||
        job.result.trajectory.length === 0
      ) {
        res.status(409).json({
          error: "NO_DATA",
          message: "Job has no trajectory data to export",
        });
        return;
      }

      const trajectory = job.result.trajectory;
      const headers = Object.keys(trajectory[0]!);
      const rows = trajectory.map((point) =>
        headers.map((h) => String(point[h] ?? "")).join(","),
      );

      res.setHeader("Content-Type", "text/csv");
      res.setHeader(
        "Content-Disposition",
        `attachment; filename="simulation-${jobId.slice(0, 8)}.csv"`,
      );
      res.send([headers.join(","), ...rows].join("\n"));
    } catch (err) {
      next(err);
    }
  },
);

/**
 * Look up a previously-completed simulation with the same query. This is a
 * naive but effective cache: identical natural-language queries produce the
 * same resolved parameters, so we can short-circuit the engine entirely.
 */
async function findCachedSimulation(
  query: string,
): Promise<queue.SimulationResponse | undefined> {
  try {
    const db = getDb();
    if (!db) return undefined;

    const rows = await db
      .select()
      .from(simulationsTable)
      .where(
        sql`lower(trim(regexp_replace(${simulationsTable.query}, '\\s+', ' ', 'g'))) = ${query}`,
      )
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
      provenance: (row.provenance as {
        reasoning: string;
        modelCitations: string[];
        flags: string[];
      }) || {
        reasoning: "",
        modelCitations: [],
        flags: [],
      },
      parameterProvenance:
        (row.parameterProvenance as Record<string, ParameterProvenance>) || {},
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
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.releaseRunnerSlot();
      return;
    }

    let engineResult;
    try {
      engineResult = await runTellurium(
        resolved.domain,
        resolved.parameters,
        abort.signal,
      );
    } finally {
      queue.releaseRunnerSlot();
    }

    if (queue.isCancelled(jobId)) return;

    // The engine can return parameters resolveQuery() never saw -- most
    // notably an auto-generated `seed` for stochastic domains (ADR 0005:
    // numpy.random.default_rng(seed)) when the query didn't supply one.
    // That seed is real and belongs in the response (it's what a student
    // needs to reproduce this exact run), but it isn't a "default" in the
    // fallback-constant sense and it isn't literature-backed -- it's an
    // engine-generated reproducibility nonce. Give it its own honest
    // provenance entry rather than leaving it un-tagged, which previously
    // reached guardSerializationProvenance() as a silent violation.
    const parameterProvenance = { ...resolved.parameterProvenance };
    for (const key of Object.keys(engineResult.parameters)) {
      if (!(key in parameterProvenance)) {
        parameterProvenance[key] = {
          origin: "default",
          note:
            key === "seed"
              ? "Auto-generated by the engine for reproducibility (ADR 0005); " +
                "not a scientific claim. Re-run with seed=<this value> to reproduce " +
                "this exact trajectory."
              : "Added by the engine after literature/user resolution; not " +
                "traceable to a literature lookup or explicit user input.",
        };
      }
    }

    const provenance = {
      reasoning: resolved.provenance.reasoning,
      modelCitations: resolved.provenance.modelCitations,
      flags: [
        ...resolved.provenance.flags,
        ...(engineResult.flagged && engineResult.flagReason
          ? [engineResult.flagReason]
          : []),
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
        parameterProvenance,
      });
    } else {
      logger.debug(
        { jobId },
        "Database unavailable; skipping persistence for this run",
      );
    }

    const result: queue.SimulationResponse = {
      runId: resolved.runId,
      domain: engineResult.domain,
      parameters: engineResult.parameters,
      trajectory: engineResult.trajectory,
      provenance,
      parameterProvenance,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
    persistJob(queue.getJob(jobId)!).catch(() => {});
  } catch (err) {
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
    } else if (err instanceof RequiredParametersMissingError) {
      // Not a pipeline failure -- the query itself was underspecified.
      // Distinguishing this from PIPELINE_ERROR matters to callers: this
      // one is fixable by editing the query, a real PIPELINE_ERROR isn't.
      queue.setJobError(jobId, {
        error: "MISSING_REQUIRED_INPUT",
        message: err.message,
      });
    } else {
      queue.setJobError(jobId, {
        error: "PIPELINE_ERROR",
        message:
          err instanceof Error ? err.message : "Unexpected pipeline failure",
      });
    }
    persistJob(queue.getJob(jobId)!).catch(() => {});
  }
}

/**
 * Structural validation of resolved parameters before invoking the engine.
 *
 * Shape validation (presence, numeric types, integer counts, the four-entry
 * haplotype array) happens here against the Zod schemas in `lib/schemas.ts`.
 * Scientific plausibility bounds remain in the engine only, so the two
 * layers cannot drift on physical constraints (ADR 0003). A malformed
 * request is rejected here with a structured message instead of reaching
 * Python and surfacing as a ValueError string.
 */
function validateParameters(
  domain: string,
  parameters: Record<string, unknown>,
): void {
  const schema = SimulationParameterSchemas[domain as SimulationDomain];
  if (!schema) {
    throw new Error(`Unknown simulation domain: ${domain}`);
  }

  const parse = schema.safeParse(parameters);
  if (!parse.success) {
    const messages = parse.error.errors.map(
      (e) => `parameter ${e.path.join(".")}: ${e.message}`,
    );
    throw new Error(`Invalid simulation parameters: ${messages.join("; ")}`);
  }
}

/**
 * Serialization-boundary provenance guard (ADR 0016 step 4 — the
 * generalizable fix).
 *
 * `validateParameterProvenance` is already enforced at computation time
 * (`queryResolver` throws on violation: ADR 0008 decision #3), but nothing
 * enforced it at the point a `SimulationResponse` is serialized back to the
 * client. The DB cache path builds its response by hand and shipped empty
 * per-parameter provenance (ADR 0016). Steps 1–3 of that ADR (schema column,
 * write at insert, read on cache path) fix *that instance*; this call is what
 * prevents the whole class from recurring through any future producer of
 * `SimulationResponse` — the same failure shape as the STRENDA gap: an
 * enforcement existed, and one path routed around it.
 *
 * Failure handling is log-and-flag, deliberately NOT throw-500. Rule 2 of
 * docs/CONSTITUTION.md draws the line between the *impossible* and the
 * *implausible-but-real*: reject the first, flag the second. A response with
 * missing per-parameter provenance is not structurally impossible — it still
 * satisfies the response schema, still carries correct numbers, and still
 * carries model-level provenance (reasoning/citations/flags). It is
 * degraded-but-real (the implausible tier), so we serve it but surface a flag
 * and log the violations. ADR 0008's hard rejection is the right behavior
 * where provenance is *guaranteed by construction* (fresh computation); it is
 * the wrong behavior at this boundary, which legitimately sees pre-migration
 * rows and would otherwise turn a working-but-degraded cache hit into an
 * availability regression (a 500 on every cache read).
 */
function guardSerializationProvenance(result: queue.SimulationResponse): void {
  const violations = validateParameterProvenance(
    result.parameters,
    result.parameterProvenance,
  );
  if (violations.length === 0) return;

  logger.warn(
    { violations, runId: result.runId, domain: result.domain },
    "SimulationResponse serialized with unsound parameter provenance",
  );

  const flag =
    "parameter provenance is incomplete for one or more parameters " +
    "(see server log for details)";
  if (!result.provenance.flags.includes(flag)) {
    result.provenance.flags.push(flag);
  }
}

export default router;
