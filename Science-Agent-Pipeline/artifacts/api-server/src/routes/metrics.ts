/**
 * Metrics API Endpoint
 * Provides real-time pipeline metrics for dashboard visualization
 * GET /api/metrics — Returns current snapshot
 * GET /api/metrics/history — Returns historical data (if available)
 */

import { Router, Request, Response } from "express";
import { metricsCollector } from "../lib/metrics";
import { logger } from "../lib/logger";

const router = Router();

/**
 * GET /api/metrics
 * Returns current snapshot of all pipeline metrics
 */
router.get("/", (req: Request, res: Response) => {
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

        stages: Object.values(snapshot.stageMetrics).map((stage) => ({
          name: stage.name,
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

        domains: Object.values(snapshot.domainMetrics)
          .filter((d) => d.count > 0) // Only include domains that have been used
          .sort((a, b) => b.count - a.count)
          .map((domain) => ({
            name: domain.domain,
            count: domain.count,
            avgResolutionMs: Math.round(domain.avgResolutionMs),
            parameterSuccessRate: Math.round(domain.parameterSuccessRate),
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
router.get("/health", (req: Request, res: Response) => {
  try {
    const snapshot = metricsCollector.getSnapshot();

    // Define health thresholds
    const successRate =
      snapshot.completedJobs + snapshot.failedJobs > 0
        ? snapshot.completedJobs / (snapshot.completedJobs + snapshot.failedJobs)
        : 1;

    const isHealthy = successRate > 0.9; // 90% success rate threshold
    const status = isHealthy ? "healthy" : "degraded";

    res.status(isHealthy ? 200 : 503).json({
      status,
      successRate: (successRate * 100).toFixed(1),
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
router.post("/reset", (req: Request, res: Response) => {
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
