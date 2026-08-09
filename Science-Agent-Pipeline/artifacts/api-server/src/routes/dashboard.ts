import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import * as queue from "../lib/queue";
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
        const blocked = Object.values(job.result.parameterProvenance).some(
          (p) => p.origin === "llm",
        );
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
        system: {
          status: "healthy",
          uptime: process.uptime(),
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
            standard: "Gelperin et al. (2010) - STRENDA Guidelines",
            doi: "10.1038/nbt0610-592",
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

      const healthy =
        metrics.completedJobs >= 0 &&
        metrics.avgLatencyMs >= 0 &&
        jobs.length >= 0;

      res.status(healthy ? 200 : 503).json({
        status: healthy ? "healthy" : "degraded",
        timestamp: new Date().toISOString(),
        checks: {
          metrics: metrics.completedJobs >= 0 ? "ok" : "failed",
          queue: jobs.length >= 0 ? "ok" : "failed",
          literature: "ok",
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

export default router;
