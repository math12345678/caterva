/**
 * Metrics Collection Tests
 * Validates that pipeline metrics are correctly tracked and aggregated
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  metricsCollector,
  recordJobExecution,
  StageMetrics,
  DomainMetrics,
} from "../lib/metrics";

describe("Metrics Collector", () => {
  beforeEach(() => {
    metricsCollector.reset();
  });

  describe("Job Tracking", () => {
    it("tracks active jobs correctly", () => {
      metricsCollector.recordJobStart("job-1");
      expect(metricsCollector.getSnapshot().activeJobs).toBe(1);

      metricsCollector.recordJobStart("job-2");
      expect(metricsCollector.getSnapshot().activeJobs).toBe(2);

      metricsCollector.recordJobCompletion("job-1", 100);
      expect(metricsCollector.getSnapshot().activeJobs).toBe(1);
    });

    it("counts completed jobs", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobCompletion("job-1", 150);

      const snapshot = metricsCollector.getSnapshot();
      expect(snapshot.completedJobs).toBe(1);
      expect(snapshot.failedJobs).toBe(0);
    });

    it("counts failed jobs", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobFailure("job-1");

      const snapshot = metricsCollector.getSnapshot();
      expect(snapshot.completedJobs).toBe(0);
      expect(snapshot.failedJobs).toBe(1);
    });

    it("calculates average latency", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobCompletion("job-1", 100);

      metricsCollector.recordJobStart("job-2");
      metricsCollector.recordJobCompletion("job-2", 200);

      const snapshot = metricsCollector.getSnapshot();
      expect(snapshot.avgLatencyMs).toBe(150);
    });

    it("maintains rolling window of latency samples", () => {
      // Record 150 jobs to exceed default window of 100
      for (let i = 0; i < 150; i++) {
        metricsCollector.recordJobStart(`job-${i}`);
        metricsCollector.recordJobCompletion(`job-${i}`, 100);
      }

      const snapshot = metricsCollector.getSnapshot();
      // Should only keep last 100 samples
      expect(snapshot.avgLatencyMs).toBe(100);
      expect(snapshot.completedJobs).toBe(150); // Total count still tracked
    });
  });

  describe("Stage Metrics", () => {
    it("tracks stage execution success", () => {
      metricsCollector.recordStageExecution("Entity Extraction", 50, true);
      metricsCollector.recordStageExecution("Entity Extraction", 60, true);
      metricsCollector.recordStageExecution("Entity Extraction", 55, false);

      const snapshot = metricsCollector.getSnapshot();
      const stage = snapshot.stageMetrics["Entity Extraction"];

      expect(stage.successCount).toBe(2);
      expect(stage.failureCount).toBe(1);
    });

    it("calculates average stage duration", () => {
      metricsCollector.recordStageExecution("Parameter Resolution", 100, true);
      metricsCollector.recordStageExecution("Parameter Resolution", 200, true);

      const snapshot = metricsCollector.getSnapshot();
      const stage = snapshot.stageMetrics["Parameter Resolution"];

      expect(stage.avgDurationMs).toBe(150);
    });

    it("tracks all 5 pipeline stages", () => {
      const stages = [
        "Entity Extraction",
        "Parameter Resolution",
        "Domain Classification",
        "Validation",
        "Simulation Output",
      ];

      const snapshot = metricsCollector.getSnapshot();

      for (const stage of stages) {
        expect(snapshot.stageMetrics[stage]).toBeDefined();
        expect(snapshot.stageMetrics[stage].name).toBe(stage);
      }
    });
  });

  describe("Domain Metrics", () => {
    it("tracks domain usage counts", () => {
      metricsCollector.recordDomainUsage("mm", 150, true);
      metricsCollector.recordDomainUsage("mm", 200, true);
      metricsCollector.recordDomainUsage("sir", 100, true);

      const snapshot = metricsCollector.getSnapshot();

      expect(snapshot.domainMetrics["mm"].count).toBe(2);
      expect(snapshot.domainMetrics["sir"].count).toBe(1);
    });

    it("calculates average resolution time per domain", () => {
      metricsCollector.recordDomainUsage("mm_competitive_inhibition", 100, true);
      metricsCollector.recordDomainUsage("mm_competitive_inhibition", 200, true);

      const snapshot = metricsCollector.getSnapshot();
      const domain = snapshot.domainMetrics["mm_competitive_inhibition"];

      expect(domain.avgResolutionMs).toBe(150);
    });

    it("calculates parameter success rate per domain", () => {
      metricsCollector.recordDomainUsage("seir", 100, true);
      metricsCollector.recordDomainUsage("seir", 110, true);
      metricsCollector.recordDomainUsage("seir", 120, false);

      const snapshot = metricsCollector.getSnapshot();
      const domain = snapshot.domainMetrics["seir"];

      // Success rate should be 2/3 ≈ 66.67%
      expect(domain.parameterSuccessRate).toBeGreaterThan(60);
      expect(domain.parameterSuccessRate).toBeLessThan(70);
    });

    it("tracks all 13 domains", () => {
      const expectedDomains = [
        "mm",
        "mm_competitive_inhibition",
        "sir",
        "seir",
        "pcr",
        "monte_carlo_pi",
        "wright_fisher",
        "two_locus_wright_fisher",
        "molecular_dynamics",
        "gillespie_ssa",
        "gillespie_ssa_bimolecular",
        "gillespie_ssa_replicates",
      ];

      const snapshot = metricsCollector.getSnapshot();

      for (const domain of expectedDomains) {
        expect(snapshot.domainMetrics[domain]).toBeDefined();
        expect(snapshot.domainMetrics[domain].domain).toBe(domain);
      }
    });
  });

  describe("Resolution Metrics", () => {
    it("tracks LLM classification results", () => {
      metricsCollector.recordLLMClassification(true);
      metricsCollector.recordLLMClassification(true);
      metricsCollector.recordLLMClassification(false);

      const snapshot = metricsCollector.getSnapshot();

      expect(snapshot.resolutionMetrics.llmClassificationSuccesses).toBe(2);
      expect(snapshot.resolutionMetrics.llmClassificationFailures).toBe(1);
      expect(snapshot.llmSuccessRate).toBeCloseTo(66.67, 1);
    });

    it("tracks keyword fallback usage", () => {
      metricsCollector.recordKeywordFallback();
      metricsCollector.recordKeywordFallback();

      const snapshot = metricsCollector.getSnapshot();
      expect(snapshot.resolutionMetrics.keywordFallbackUsed).toBe(2);
    });

    it("tracks literature resolution results", () => {
      metricsCollector.recordLiteratureResolution(true);
      metricsCollector.recordLiteratureResolution(true);
      metricsCollector.recordLiteratureResolution(false);

      const snapshot = metricsCollector.getSnapshot();

      expect(snapshot.resolutionMetrics.literatureHitCount).toBe(2);
      expect(snapshot.resolutionMetrics.literatureMissCount).toBe(1);
      expect(snapshot.literatureHitRate).toBeCloseTo(66.67, 1);
    });
  });

  describe("Helper Function: recordJobExecution", () => {
    it("records complete job execution with all metrics", () => {
      recordJobExecution(
        "job-123",
        "mm_competitive_inhibition",
        250,
        true,
        {
          "Entity Extraction": { duration: 50, success: true },
          "Parameter Resolution": { duration: 100, success: true },
          "Domain Classification": { duration: 30, success: true },
          Validation: { duration: 40, success: true },
          "Simulation Output": { duration: 30, success: true },
        },
        true, // LLM used
        true, // LLM success
        true, // Literature hit
      );

      const snapshot = metricsCollector.getSnapshot();

      // Check job metrics
      expect(snapshot.completedJobs).toBe(1);
      expect(snapshot.failedJobs).toBe(0);
      expect(snapshot.avgLatencyMs).toBe(250);

      // Check domain metrics
      expect(snapshot.domainMetrics["mm_competitive_inhibition"].count).toBe(1);

      // Check stage metrics
      expect(
        snapshot.stageMetrics["Entity Extraction"].successCount,
      ).toBeGreaterThan(0);

      // Check resolution metrics
      expect(
        snapshot.resolutionMetrics.llmClassificationSuccesses,
      ).toBeGreaterThan(0);
      expect(snapshot.resolutionMetrics.literatureHitCount).toBeGreaterThan(0);
    });

    it("handles failed job execution", () => {
      recordJobExecution(
        "job-456",
        "sir",
        100,
        false,
        {
          "Entity Extraction": { duration: 50, success: false },
        },
        false, // LLM not used
        false, // LLM failure
        false, // No literature hit
      );

      const snapshot = metricsCollector.getSnapshot();

      expect(snapshot.completedJobs).toBe(0);
      expect(snapshot.failedJobs).toBe(1);
      expect(snapshot.resolutionMetrics.keywordFallbackUsed).toBe(1);
    });
  });

  describe("Reset Functionality", () => {
    it("resets all metrics to initial state", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobCompletion("job-1", 100);
      metricsCollector.recordDomainUsage("mm", 100, true);
      metricsCollector.recordLLMClassification(true);

      let snapshot = metricsCollector.getSnapshot();
      expect(snapshot.completedJobs).toBeGreaterThan(0);
      expect(snapshot.domainMetrics["mm"].count).toBeGreaterThan(0);

      metricsCollector.reset();

      snapshot = metricsCollector.getSnapshot();
      expect(snapshot.activeJobs).toBe(0);
      expect(snapshot.completedJobs).toBe(0);
      expect(snapshot.failedJobs).toBe(0);
      expect(snapshot.avgLatencyMs).toBe(0);
      expect(snapshot.domainMetrics["mm"].count).toBe(0);
      expect(snapshot.resolutionMetrics.llmClassificationSuccesses).toBe(0);
    });
  });

  describe("Snapshot Export", () => {
    it("exports complete metrics snapshot", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobCompletion("job-1", 100);

      const snapshot = metricsCollector.getSnapshot();

      expect(snapshot).toHaveProperty("timestamp");
      expect(snapshot).toHaveProperty("activeJobs");
      expect(snapshot).toHaveProperty("completedJobs");
      expect(snapshot).toHaveProperty("failedJobs");
      expect(snapshot).toHaveProperty("avgLatencyMs");
      expect(snapshot).toHaveProperty("stageMetrics");
      expect(snapshot).toHaveProperty("domainMetrics");
      expect(snapshot).toHaveProperty("resolutionMetrics");
      expect(snapshot).toHaveProperty("llmSuccessRate");
      expect(snapshot).toHaveProperty("literatureHitRate");
    });

    it("exports JSON representation", () => {
      metricsCollector.recordJobStart("job-1");
      metricsCollector.recordJobCompletion("job-1", 100);

      const json = metricsCollector.toJSON();

      expect(json).toHaveProperty("timestamp");
      expect(json).toHaveProperty("completedJobs");
      expect(json.completedJobs).toBe(1);
    });
  });
});
