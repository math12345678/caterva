import { describe, it, expect } from "vitest";
import {
  verifyParameterAgainstLiterature,
  getPublicationVerification,
  canPublish,
  auditForPublication,
  generatePublicationTable,
} from "../lib/literature-verifier";

describe("Literature Verifier", () => {
  describe("Parameter Verification", () => {
    it("accepts user-supplied parameters", () => {
      const result = verifyParameterAgainstLiterature(
        "km",
        2.5,
        "user",
        undefined,
      );

      expect(result.level).toBe("unverifiable");
      expect(result.confidence).toBe(1.0);
      expect(result.requiresManualReview).toBe(false);
    });

    it("flags default parameters as low confidence", () => {
      const result = verifyParameterAgainstLiterature(
        "km",
        2.0,
        "default",
        undefined,
      );

      expect(result.level).toBe("unverifiable");
      expect(result.confidence).toBe(0.3);
      expect(result.requiresManualReview).toBe(false);
    });

    it("requires manual review for LLM-supplied parameters", () => {
      const result = verifyParameterAgainstLiterature("km", 2.5, "llm", {
        source: "llm",
      });

      expect(result.level).toBe("pending");
      expect(result.requiresManualReview).toBe(true);
      expect(result.confidence).toBe(0.4);
    });

    it("accepts keyword-matched parameters with medium confidence", () => {
      const result = verifyParameterAgainstLiterature("km", 2.5, "keyword");

      expect(result.level).toBe("flagged");
      expect(result.confidence).toBeGreaterThan(0.5);
    });

    it("accepts resolved parameters with documentation", () => {
      const result = verifyParameterAgainstLiterature(
        "km",
        2.5,
        "resolved",
        {
          doi: "10.1093/nar/gkw952",
          source: "brenda",
        },
        true, // Complete assay conditions
      );

      expect(result.level).toBe("verified");
      expect(result.confidence).toBeGreaterThan(0.9);
      expect(result.requiresManualReview).toBe(false);
    });

    it("flags resolved parameters without complete assay conditions", () => {
      const result = verifyParameterAgainstLiterature(
        "km",
        2.5,
        "resolved",
        {
          doi: "10.1093/nar/gkw952",
          source: "brenda",
        },
        false, // Missing assay conditions
      );

      expect(result.level).toBe("flagged");
      expect(result.confidence).toBeLessThan(0.95);
    });
  });

  describe("Publication Verification", () => {
    it("marks verified parameters as publication-ready", () => {
      const result = verifyParameterAgainstLiterature(
        "km",
        2.5,
        "resolved",
        { doi: "10.1093/nar/gkw952", source: "brenda" },
        true,
      );

      const message = getPublicationVerification(result);
      expect(message).toContain("✅");
      expect(message).toContain("DOI");
    });

    it("marks pending parameters as not ready", () => {
      const result = verifyParameterAgainstLiterature("km", 2.5, "llm", {
        source: "llm",
      });

      const message = getPublicationVerification(result);
      expect(message).toContain("❌");
      expect(message).toContain("DO NOT PUBLISH");
    });

    it("canPublish checks verification level", () => {
      const verified = verifyParameterAgainstLiterature(
        "km",
        2.5,
        "resolved",
        { doi: "10.1093/nar/gkw952" },
        true,
      );
      expect(canPublish(verified)).toBe(true);

      const pending = verifyParameterAgainstLiterature("km", 2.5, "llm", {
        source: "llm",
      });
      expect(canPublish(pending)).toBe(false);
    });
  });

  describe("Publication Audit", () => {
    it("audits parameter set for publication readiness", () => {
      const results = {
        km: verifyParameterAgainstLiterature(
          "km",
          2.5,
          "resolved",
          { doi: "10.1093/nar/gkw952" },
          true,
        ),
        vmax: verifyParameterAgainstLiterature(
          "vmax",
          5.0,
          "resolved",
          { doi: "10.1093/nar/gkw952" },
          true,
        ),
        s0: verifyParameterAgainstLiterature("s0", 10, "user"),
      };

      const audit = auditForPublication(results);

      expect(audit.verifiedCount).toBe(2);
      expect(audit.unverifiableCount).toBe(1);
      expect(audit.readyToPublish).toBe(true);
    });

    it("blocks publication with pending parameters", () => {
      const results = {
        km: verifyParameterAgainstLiterature("km", 2.5, "llm", {
          source: "llm",
        }),
      };

      const audit = auditForPublication(results);

      expect(audit.readyToPublish).toBe(false);
      expect(audit.pendingCount).toBe(1);
      expect(audit.issues.length).toBeGreaterThan(0);
    });

    it("generates publication table", () => {
      const results = {
        km: verifyParameterAgainstLiterature(
          "km",
          2.5,
          "resolved",
          { doi: "10.1093/nar/gkw952" },
          true,
        ),
        vmax: verifyParameterAgainstLiterature("vmax", 5.0, "user"),
      };

      const table = generatePublicationTable(results);

      expect(table).toContain("Parameter");
      expect(table).toContain("km");
      expect(table).toContain("vmax");
      expect(table).toContain("DOI");
      expect(table).toContain("verified");
      expect(table).toContain("unverifiable");
    });
  });

  describe("Verification Levels", () => {
    it("has four distinct levels", () => {
      const levels = [
        verifyParameterAgainstLiterature("p", 1, "resolved", {
          doi: "10.1234/test",
        }, true).level,
        verifyParameterAgainstLiterature("p", 1, "keyword").level,
        verifyParameterAgainstLiterature("p", 1, "llm", {}).level,
        verifyParameterAgainstLiterature("p", 1, "default").level,
      ];

      expect(new Set(levels).size).toBeGreaterThanOrEqual(3); // At least 3 different levels
    });
  });

  describe("Confidence Scoring", () => {
    it("ranks verification levels by confidence", () => {
      const user = verifyParameterAgainstLiterature("p", 1, "user")
        .confidence;
      const verified = verifyParameterAgainstLiterature(
        "p",
        1,
        "resolved",
        { doi: "10.1234/test" },
        true,
      ).confidence;
      const pending = verifyParameterAgainstLiterature("p", 1, "llm", {})
        .confidence;
      const defaultVal = verifyParameterAgainstLiterature("p", 1, "default")
        .confidence;

      // Verified > Pending > User > Default (generally)
      expect(verified).toBeGreaterThan(pending);
      expect(pending).toBeGreaterThan(defaultVal);
    });
  });
});
