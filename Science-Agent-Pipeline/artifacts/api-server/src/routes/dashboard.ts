import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import * as queue from "../lib/queue";
import { unverifiedOriginKeys } from "../lib/provenance";
import { verifiableMetricsCollector } from "../lib/verifiable-metrics";
import { getDomainCitation } from "../lib/domain-literature";

const router: IRouter = Router();

/**
 * GET /api/dashboard/overview
 *
 * Complete system state overview with literature backing.
 * Shows:
 * - Active jobs and queue status
 * - Pipeline metrics (Little's Law, Wilson CI, Harter percentiles)
 * - Domain coverage with literature citations
 * - STRENDA compliance status
 * - Publication readiness across all jobs
 */
router.get(
  "/dashboard/overview",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const jobs = queue.listJobs();
      const metrics = verifiableMetricsCollector.getSnapshot();
      const successRate = verifiableMetricsCollector.getSuccessRateWithConfidence();
      const latencyPercentiles = verifiableMetricsCollector.getLatencyPercentiles();

      // Analyze jobs
      const jobsByStatus = jobs.reduce(
        (acc, job) => {
          acc[job.status] = (acc[job.status] ?? 0) + 1;
          return acc;
        },
        {} as Record<string, number>,
      );

      // Count publication-ready jobs
      let publicationReady = 0;
      let publicationBlocked = 0;
      for (const job of jobs) {
        if (!job.result?.parameterProvenance) continue;
        // `unverifiedOriginKeys` is the same predicate the hard rule uses
        // (provenance.ts), so the dashboard and the engine cannot disagree
        // about what "publication-ready" means. This previously tested
        // `origin === "llm"` alone, ignoring `default` -- which the hard
        // rule blocks identically -- so a job carrying an unverified
        // default counted as ready to publish.
        const blocked =
          unverifiedOriginKeys(job.result.parameterProvenance).length > 0;
        if (blocked) {
          publicationBlocked++;
        } else {
          publicationReady++;
        }
      }

      const domains = [
        "mm",
        "mm_competitive_inhibition",
        "sir",
        "seir",
        "wright_fisher",
        "gillespie_ssa",
        "pcr",
        "molecular_dynamics",
        "gillespie_ssa_bimolecular",
        "two_locus_wright_fisher",
        "lotka_volterra",
        "cell_cycle_oscillator",
        "repressilator",
      ];

      res.json({
        timestamp: new Date().toISOString(),
        // THIRD occurrence of the same defect in this codebase, and the
        // second in this file.
        //
        // `status` was the literal "healthy", with no probe behind it and
        // no code path able to produce any other value -- so this endpoint
        // reported the system healthy while Python was missing, the
        // database was down and every job was failing. A monitoring signal
        // that cannot fail is worse than none: it actively suppresses the
        // alarm it exists to raise. That sentence is already written, 100
        // lines below, about /api/dashboard/health, which was fixed; and
        // again in routes/metrics.ts, which was fixed before it. Only this
        // copy was missed, twice.
        //
        // Same three-tier shape as the other two. "no_data" is neither
        // healthy nor degraded: the process IS up and answering, and the
        // distinction being drawn is between "up with no evidence" and "up
        // and demonstrably fine".
        //
        // `uptime` stays process.uptime() but is NAMED as such. It was
        // sitting under a hardcoded "healthy" where a reader would take it
        // for service availability; it is how long this process has been
        // running, which is a different claim and only ever an upper bound
        // on the other.
        system: {
          status:
            metrics.sampleCount === 0
              ? "no_data"
              : metrics.completedJobs / metrics.sampleCount > 0.9
                ? "healthy"
                : "degraded",
          // Published alongside the status so a caller can tell
          // 100%-of-zero from 100%-of-500.
          sampleCount: metrics.sampleCount,
          processUptimeSeconds: process.uptime(),
          version: "literature-backed-v1",
        },
        queue: {
          total: jobs.length,
          byStatus: jobsByStatus,
          publicationReady,
          publicationBlocked,
          averageWaitTimeMs: metrics.avgLatencyMs,
        },
        metrics: {
          literature: {
            queueTheory: "Little (1961) - L = λW",
            confidenceIntervals: "Wilson (1927) - Binomial proportion CI",
            percentiles: "Harter (1974) - P95 and P99 analysis",
            responseTime: "Nielsen (1993) - User perception",
          },
          completedJobs: metrics.completedJobs,
          successRate: {
            rate: successRate.rate,
            ci95Lower: successRate.confidence95.lower,
            ci95Upper: successRate.confidence95.upper,
          },
          latency: {
            avgMs: metrics.avgLatencyMs,
            p95Ms: latencyPercentiles.p95,
            p99Ms: latencyPercentiles.p99,
          },
        },
        domains: {
          total: domains.length,
          covered: domains,
          citations: domains.map((domain) => ({
            domain,
            citation: getDomainCitation(domain),
          })),
        },
        compliance: {
          strenda: {
            standard: "Tipton et al. (2014) - STRENDA Guidelines",
            doi: "10.1016/j.pisc.2014.02.012",
            requirements: 7,
            applicableDomains: [
              "mm",
              "mm_competitive_inhibition",
            ],
          },
          publications: {
            readyCount: publicationReady,
            blockedCount: publicationBlocked,
            readinessPercentage:
              jobs.length > 0
                ? Math.round((publicationReady / jobs.length) * 100)
                : 0,
          },
        },
        api: {
          endpoints: {
            jobs: [
              "POST /api/simulate - Start new simulation",
              "GET /api/simulate - List all jobs",
              "GET /api/simulate/:jobId - Get job status",
              "GET /api/simulate/:jobId/stream - Real-time updates (SSE)",
              "POST /api/simulate/:jobId/cancel - Cancel job",
              "GET /api/simulate/:jobId/export - Export as CSV",
            ],
            literature: [
              "GET /api/simulate/:jobId/confidence - Parameter confidence scores",
              "GET /api/simulate/:jobId/audit - Publication audit trail",
              "GET /api/simulate/metrics/pipeline - Pipeline metrics",
              "GET /api/pipeline/literature - Domain literature backing",
            ],
            dashboard: [
              "GET /api/dashboard/overview - This endpoint",
              "GET /api/dashboard/health - Health check",
            ],
          },
          // No testCoverage block: a test count baked into a runtime API
          // response goes stale the moment a test is added or removed
          // (it already had -- 395/27 here vs. the actual 399/28 at time
          // of writing). Run `npx vitest run` or `make test` for the real,
          // current number instead of trusting one frozen into a response.
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/dashboard/health
 *
 * Lightweight health check with literature validation.
 */
router.get(
  "/dashboard/health",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const metrics = verifiableMetricsCollector.getSnapshot();
      const jobs = queue.listJobs();

      // This endpoint could not report anything but "healthy". It was:
      //
      //   const healthy =
      //     metrics.completedJobs >= 0 &&
      //     metrics.avgLatencyMs >= 0 &&
      //     jobs.length >= 0;
      //
      // `completedJobs` is a counter initialised to 0 and only ever
      // incremented; `avgLatencyMs` is a mean of elapsed times or 0; and
      // `Array.prototype.length` is a uint32. All three comparisons are
      // tautologies on quantities that are non-negative by construction,
      // so `healthy` was a compile-time `true` and the 503 branch was
      // unreachable. `checks.literature` was the string literal "ok" --
      // no literature was consulted at all.
      //
      // A monitoring signal that cannot fail is worse than none: it
      // actively suppresses the alarm it exists to raise. This is the same
      // defect `/api/metrics/health` had and had fixed (see routes/
      // metrics.ts); only this copy was missed. It now follows that same
      // three-tier shape.
      const observed = metrics.sampleCount;
      const successRate =
        observed > 0 ? metrics.completedJobs / observed : null;

      // "no_data" is neither healthy nor degraded, and returns 200: the
      // process IS up and answering. The distinction being drawn is
      // between "up with no evidence" and "up and demonstrably fine".
      const status =
        successRate === null
          ? "no_data"
          : successRate > 0.9
            ? "healthy"
            : "degraded";

      res.status(status === "degraded" ? 503 : 200).json({
        status,
        timestamp: new Date().toISOString(),
        // Published alongside every rate so a caller can tell 100%-of-zero
        // from 100%-of-500.
        sampleCount: observed,
        successRate: successRate === null ? null : Number(successRate.toFixed(4)),
        checks: {
          metrics: observed > 0 ? "ok" : "no_data",
          queue: `${jobs.length} job(s) known`,
          // Was hardcoded "ok". This endpoint performs no literature
          // check, so it does not get to report on one; saying so is the
          // honest answer. /api/simulate/metrics/pipeline is where
          // literature resolution is actually measured.
          literature: "not_checked_here",
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

export default router;
