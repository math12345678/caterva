import { describe, it, expect } from "vitest";
import {
  validateAssayConditions,
  validateConfidenceInterval,
  validateSTREANDA,
  getSTREANDARecommendation,
  compareSTREANDA,
} from "../lib/strenda-validator";

describe("STRENDA Validator", () => {
  describe("Assay Conditions Validation", () => {
    it("validates complete assay conditions", () => {
      const result = validateAssayConditions({
        ph: 7.4,
        temperatureC: 37,
        buffer: "Phosphate buffered saline",
      });

      expect(result.score).toBe(3);
      expect(result.violations).toHaveLength(0);
    });

    it("rejects incomplete conditions", () => {
      const result = validateAssayConditions({
        ph: 7.4,
        temperatureC: undefined,
        buffer: "PBS",
      });

      expect(result.score).toBe(2);
      expect(result.violations).toHaveLength(1);
      expect(result.violations[0].requirement).toBe(2);
    });

    it("handles missing conditions object", () => {
      const result = validateAssayConditions(undefined);

      expect(result.score).toBe(0);
      expect(result.violations).toHaveLength(3);
    });
  });

  describe("Confidence Interval Validation", () => {
    it("validates correct confidence interval", () => {
      const result = validateConfidenceInterval(10, 9, 11);

      expect(result.hasInterval).toBe(true);
      expect(result.violation).toBeUndefined();
    });

    it("rejects missing interval", () => {
      const result = validateConfidenceInterval(10, undefined, undefined);

      expect(result.hasInterval).toBe(false);
      expect(result.violation).toBeDefined();
      expect(result.violation?.requirement).toBe(7);
    });

    it("rejects invalid interval (value outside bounds)", () => {
      const result = validateConfidenceInterval(10, 11, 12);

      expect(result.hasInterval).toBe(false);
      expect(result.violation?.message).toContain("outside");
    });

    it("rejects reversed interval", () => {
      const result = validateConfidenceInterval(10, 12, 11);

      expect(result.hasInterval).toBe(false);
      expect(result.violation?.message).toContain("invalid");
    });
  });

  describe("Full STRENDA Validation", () => {
    it("validates fully compliant parameter", () => {
      const result = validateSTREANDA(
        2.5, // Km value
        {
          ph: 7.4,
          temperatureC: 37,
          buffer: "Tris",
        },
        2.3, // CI lower
        2.7, // CI upper
      );

      expect(result.compliant).toBe(true);
      expect(result.score).toBeGreaterThanOrEqual(4);
      expect(result.violations).toHaveLength(0);
    });

    it("handles partial compliance with warnings", () => {
      const result = validateSTREANDA(
        2.5,
        {
          ph: 7.4,
          temperatureC: undefined, // Missing
          buffer: "Tris",
        },
        2.3,
        2.7,
      );

      expect(result.compliant).toBe(false);
      expect(result.violations.length).toBeGreaterThan(0);
      expect(result.warnings.length).toBeGreaterThan(0);
    });

    it("generates appropriate recommendations", () => {
      const full = validateSTREANDA(
        2.5,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        2.3,
        2.7,
      );

      expect(getSTREANDARecommendation(full)).toContain("✅");

      const partial = validateSTREANDA(2.5, { ph: 7.4 }, 2.3, 2.7);
      expect(getSTREANDARecommendation(partial)).toContain("⚠️");
    });
  });

  describe("STRENDA Comparison", () => {
    it("prefers higher score", () => {
      const v1 = validateSTREANDA(
        2.5,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        2.3,
        2.7,
      );
      const v2 = validateSTREANDA(2.5, { ph: 7.4 }, 2.3, 2.7);

      const comparison = compareSTREANDA(v1, v2);
      expect(comparison).toBe(-1); // v1 is better
    });

    it("handles equal scores", () => {
      const v1 = validateSTREANDA(2.5, { ph: 7.4 }, 2.3, 2.7);
      const v2 = validateSTREANDA(2.5, { ph: 7.4 }, 2.3, 2.7);

      const comparison = compareSTREANDA(v1, v2);
      expect(comparison).toBe(0);
    });
  });

  describe("Requirement-Specific Tests", () => {
    it("enforces pH requirement (Req 1)", () => {
      const result = validateSTREANDA(
        2.5,
        { temperatureC: 37, buffer: "Tris" }, // Missing pH
        2.3,
        2.7,
      );

      const phViolation = result.violations.find((v) => v.requirement === 1);
      expect(phViolation).toBeDefined();
    });

    it("enforces temperature requirement (Req 2)", () => {
      const result = validateSTREANDA(
        2.5,
        { ph: 7.4, buffer: "Tris" }, // Missing temperature
        2.3,
        2.7,
      );

      const tempViolation = result.violations.find((v) => v.requirement === 2);
      expect(tempViolation).toBeDefined();
    });

    it("enforces buffer requirement (Req 3)", () => {
      const result = validateSTREANDA(
        2.5,
        { ph: 7.4, temperatureC: 37 }, // Missing buffer
        2.3,
        2.7,
      );

      const bufferViolation = result.violations.find((v) => v.requirement === 3);
      expect(bufferViolation).toBeDefined();
    });

    it("enforces confidence interval requirement (Req 7)", () => {
      const result = validateSTREANDA(
        2.5,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        undefined, // No CI
        undefined,
      );

      const ciViolation = result.violations.find((v) => v.requirement === 7);
      expect(ciViolation).toBeDefined();
    });
  });

  describe("Edge Cases", () => {
    it("handles zero value", () => {
      const result = validateSTREANDA(
        0,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        -0.1,
        0.1,
      );

      expect(result.violations).toHaveLength(0);
    });

    it("handles very small value", () => {
      const result = validateSTREANDA(
        0.001,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        0.0009,
        0.0011,
      );

      expect(result.violations).toHaveLength(0);
    });

    it("handles large value", () => {
      const result = validateSTREANDA(
        1000,
        { ph: 7.4, temperatureC: 37, buffer: "Tris" },
        900,
        1100,
      );

      expect(result.violations).toHaveLength(0);
    });
  });
});
