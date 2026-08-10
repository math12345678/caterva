/**
 * Metrics API Endpoint
 * Provides real-time pipeline metrics for dashboard visualization
 * GET /api/metrics — Returns current snapshot
 * GET /api/metrics/history — Returns historical data (if available)
 */

import { Router, Request, Response } from "express";
// The pipeline records into `verifiableMetricsCollector`, not
// `metricsCollector`. These routes read the latter, which has ZERO
// production writers -- `recordJobExecution` is called only by its own
// test. So /snapshot and /metrics/health reported permanent zeros for the
// life of the process, with llmSuccessRate and literatureHitRate showing
// 100% fabricated from an empty sample. An endpoint that always says
// "healthy, 100%" is worse than no endpoint: it is a monitoring signal
// that cannot fail.
import { verifiableMetricsCollector as metricsCollector } from "../lib/verifiable-metrics";
import { logger } from "../lib/logger";

const router = Router();

/**
 * GET /api/metrics/snapshot
 * Returns current snapshot of all pipeline metrics
 */
router.get("/snapshot", (req: Request, res: Response) => {
  try {
    const snapshot = metricsCollector.getSnapshot();

    res.status(200).json({
      status: "ok",
      timestamp: snapshot.timestamp,
      data: {
        activeJobs: snapshot.activeJobs,
        completedJobs: snapshot.completedJobs,
        failedJobs: snapshot.failedJobs,
        avgLatencyMs: Math.round(snapshot.avgLatencyMs),
        successRate:
          snapshot.completedJobs + snapshot.failedJobs > 0
            ? (
                (snapshot.completedJobs /
                  (snapshot.completedJobs + snapshot.failedJobs)) *
                100
              ).toFixed(1)
            : "N/A",
        llmSuccessRate: Math.round(snapshot.llmSuccessRate),
        literatureHitRate: Math.round(snapshot.literatureHitRate),

        stages: Object.entries(snapshot.stageMetrics).map(([name, stage]) => ({
          name,
          successCount: stage.successCount,
          failureCount: stage.failureCount,
          avgDurationMs: Math.round(stage.avgDurationMs),
          successRate:
            stage.successCount + stage.failureCount > 0
              ? (
                  (stage.successCount /
                    (stage.successCount + stage.failureCount)) *
                  100
                ).toFixed(1)
              : "N/A",
        })),

        domains: Object.entries(snapshot.domainMetrics)
          .filter(([, d]) => d.count > 0) // only domains actually used
          .sort(([, a], [, b]) => b.count - a.count)
          .map(([name, domain]) => ({
            name,
            count: domain.count,
            avgResolutionMs: Math.round(domain.avgLatencyMs),
            parameterSuccessRate: Math.round(domain.successRate),
          })),

        resolution: {
          llmSuccesses: snapshot.resolutionMetrics.llmClassificationSuccesses,
          llmFailures: snapshot.resolutionMetrics.llmClassificationFailures,
          keywordFallbacks: snapshot.resolutionMetrics.keywordFallbackUsed,
          literatureHits: snapshot.resolutionMetrics.literatureHitCount,
          literatureMisses: snapshot.resolutionMetrics.literatureMissCount,
        },
      },
    });
  } catch (error) {
    logger.error({ error }, "Failed to get metrics snapshot");
    res.status(500).json({
      status: "error",
      error: "Failed to retrieve metrics",
    });
  }
});

/**
 * GET /api/metrics/health
 * Minimal health check for monitoring systems
 * Returns 200 if pipeline is operational
 */
router.get("/metrics/health", (req: Request, res: Response) => {
  try {
    const snapshot = metricsCollector.getSnapshot();

    // Define health thresholds
    // With no jobs yet there is no success rate -- not a success rate of
    // 1. Defaulting to 1 made this endpoint structurally incapable of
    // reporting `degraded` on a fresh process, and reported "100.0" from
    // zero observations. A rate computed from an empty sample is a
    // fabricated measurement, which is the same failure this codebase
    // corrects everywhere else.
    const observed = snapshot.sampleCount;
    const successRate =
      observed > 0 ? snapshot.completedJobs / observed : null;

    // "no_data" is neither healthy nor degraded. It reports 200 because
    // the process IS up and answering -- the distinction being drawn is
    // between "up with no evidence" and "up and demonstrably fine".
    const status =
      successRate === null
        ? "no_data"
        : successRate > 0.9
          ? "healthy"
          : "degraded";

    res.status(status === "degraded" ? 503 : 200).json({
      status,
      successRate: successRate === null ? null : (successRate * 100).toFixed(1),
      sampleCount: observed,
      activeJobs: snapshot.activeJobs,
      avgLatencyMs: Math.round(snapshot.avgLatencyMs),
      uptime: process.uptime(),
    });
  } catch (error) {
    logger.error({ error }, "Health check failed");
    res.status(500).json({
      status: "error",
      message: "Health check failed",
    });
  }
});

/**
 * POST /api/metrics/reset
 * Reset all metrics (admin endpoint - requires authorization token)
 * Authorization: Bearer <METRICS_ADMIN_TOKEN>
 */
router.post("/metrics/reset", (req: Request, res: Response) => {
  try {
    // Require authorization token for metrics reset (prevents accidental/malicious resets)
    const adminToken = process.env.METRICS_ADMIN_TOKEN;
    if (!adminToken) {
      logger.warn("METRICS_ADMIN_TOKEN not configured; metrics reset disabled");
      res.status(501).json({
        status: "error",
        error: "Metrics reset not configured",
      });
      return;
    }

    const authHeader = req.headers.authorization || "";
    const [scheme, token] = authHeader.split(" ");

    if (scheme !== "Bearer" || token !== adminToken) {
      logger.warn({ authHeader: authHeader.split(" ")[0] }, "Metrics reset authorization failed");
      res.status(403).json({
        status: "error",
        error: "Unauthorized",
      });
      return;
    }

    metricsCollector.reset();
    logger.info("Metrics reset via API by authorized request");

    res.status(200).json({
      status: "ok",
      message: "Metrics reset successfully",
    });
  } catch (error) {
    logger.error({ error }, "Failed to reset metrics");
    res.status(500).json({
      status: "error",
      error: "Failed to reset metrics",
    });
  }
});

export default router;
