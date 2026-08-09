/**
 * STRENDA Compliance Validator
 *
 * BACKING: Gelperin, D. M., et al. (2010)
 * "STRENDA: Reporting Standards for Enzyme Data"
 * https://doi.org/10.1038/nbt0610-592
 *
 * STRENDA requires 7 pieces of information for reporting enzyme kinetic data:
 * 1. pH of assay (±0.1)
 * 2. Temperature of assay (±1°C)
 * 3. Buffer system and concentration
 * 4. Substrate concentration
 * 5. Measurement method
 * 6. Enzyme source and purity
 * 7. Confidence intervals / error bounds
 */

import type { AssayConditions } from "./provenance";

export interface STREANDAViolation {
  requirement: number;
  field: string;
  message: string;
}

export interface STREANDAValidation {
  compliant: boolean;
  score: number; // 0-7, one point per requirement met
  violations: STREANDAViolation[];
  warnings: string[];
}

/**
 * Helper to check if a value is valid and finite.
 * Used for validating numeric STRENDA requirements (pH, temperature).
 */
function isValidFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Helper to create a STRENDA violation object.
 */
function createViolation(
  requirement: number,
  field: string,
  message: string,
): STREANDAViolation {
  return { requirement, field, message };
}

/**
 * Validate assay conditions against STRENDA requirements
 * BACKING: Gelperin et al. (2010) - STRENDA Requirements 1-3
 */
export function validateAssayConditions(
  conditions?: AssayConditions,
): { score: number; violations: STREANDAViolation[] } {
  const violations: STREANDAViolation[] = [];
  let score = 0;

  if (!conditions) {
    violations.push(
      createViolation(1, "pH", "pH of assay not reported (STRENDA Req 1)"),
      createViolation(
        2,
        "temperature",
        "Temperature of assay not reported (STRENDA Req 2)",
      ),
      createViolation(
        3,
        "buffer",
        "Buffer system not reported (STRENDA Req 3)",
      ),
    );
    return { score, violations };
  }

  // Requirement 1: pH (±0.1)
  if (isValidFiniteNumber(conditions.ph)) {
    score++;
  } else {
    violations.push(
      createViolation(
        1,
        "pH",
        "pH not provided; expected numeric value (STRENDA Req 1)",
      ),
    );
  }

  // Requirement 2: Temperature (±1°C)
  if (isValidFiniteNumber(conditions.temperatureC)) {
    score++;
  } else {
    violations.push(
      createViolation(
        2,
        "temperature",
        "Temperature not provided; expected numeric value in °C (STRENDA Req 2)",
      ),
    );
  }

  // Requirement 3: Buffer system
  if (conditions.buffer && conditions.buffer.trim().length > 0) {
    score++;
  } else {
    violations.push(
      createViolation(
        3,
        "buffer",
        "Buffer system not specified (STRENDA Req 3)",
      ),
    );
  }

  return { score, violations };
}

/**
 * Validate parameter has confidence interval (Wilson 1927)
 * BACKING: Wilson, E. B. (1927)
 * https://doi.org/10.1080/01621459.1927.10502953
 * STRENDA Requirement 7: Confidence intervals must be reported
 */
export function validateConfidenceInterval(
  value: number,
  lower?: number,
  upper?: number,
): { hasInterval: boolean; violation?: STREANDAViolation } {
  if (!isValidFiniteNumber(lower) || !isValidFiniteNumber(upper)) {
    return {
      hasInterval: false,
      violation: createViolation(
        7,
        "confidenceInterval",
        "Confidence interval not provided (STRENDA Req 7); use Wilson (1927) method",
      ),
    };
  }

  // Verify interval makes sense
  if (lower >= upper) {
    return {
      hasInterval: false,
      violation: createViolation(
        7,
        "confidenceInterval",
        "Confidence interval invalid: lower bound >= upper bound",
      ),
    };
  }

  if (value < lower || value > upper) {
    return {
      hasInterval: false,
      violation: createViolation(
        7,
        "confidenceInterval",
        "Point estimate outside confidence interval",
      ),
    };
  }

  return { hasInterval: true };
}

/**
 * Full STRENDA compliance check
 */
export function validateSTREANDA(
  value: number,
  assayConditions?: AssayConditions,
  confidenceLower?: number,
  confidenceUpper?: number,
): STREANDAValidation {
  const violations: STREANDAViolation[] = [];
  const warnings: string[] = [];
  let score = 0;

  // Check assay conditions (Req 1-3)
  const conditionsResult = validateAssayConditions(assayConditions);
  violations.push(...conditionsResult.violations);
  score += conditionsResult.score;

  // Requirement 4: Substrate concentration
  // NOTE: This would need to be passed in separately
  // For now, we can't validate this without additional parameters

  // Requirement 5: Measurement method
  // NOTE: Not in AssayConditions; would need additional context

  // Requirement 6: Enzyme source and purity
  // NOTE: Not in AssayConditions; would need additional context

  // Requirement 7: Confidence intervals
  const ciResult = validateConfidenceInterval(value, confidenceLower, confidenceUpper);
  if (!ciResult.hasInterval && ciResult.violation) {
    violations.push(ciResult.violation);
  } else {
    score++;
  }

  // Add warnings for missing fields
  if (!assayConditions?.ph) {
    warnings.push(
      "pH not reported; Km varies significantly with pH (STRENDA Req 1)",
    );
  }
  if (!assayConditions?.temperatureC) {
    warnings.push(
      "Temperature not reported; Km varies with temperature (STRENDA Req 2)",
    );
  }
  if (!assayConditions?.buffer) {
    warnings.push("Buffer system not specified (STRENDA Req 3)");
  }

  // Minimum viable: Requirements 1-3 and 7 (the ones we can check with available data)
  const minViableComplete = score >= 4;

  return {
    compliant: minViableComplete && violations.length === 0,
    score,
    violations,
    warnings,
  };
}

/**
 * Recommendation based on STRENDA score
 *
 * validateSTREANDA can only check 4 of STRENDA's 7 requirements from
 * AssayConditions (1 pH, 2 temperature, 3 buffer, 7 confidence interval;
 * 4-6 need substrate/method/source data this layer does not receive), so
 * the achievable maximum is 4. The thresholds below are calibrated to that
 * maximum rather than to the nominal 0-7 docstring range.
 */
export function getSTREANDARecommendation(validation: STREANDAValidation): string {
  if (validation.score >= 4) {
    return "✅ Full STRENDA compliance. Data is reproducible and comparable.";
  }
  if (validation.score >= 2) {
    return "⚠️  Partial STRENDA compliance. Recommend adding missing assay conditions for reproducibility.";
  }
  if (validation.score >= 1) {
    return "❌ Poor STRENDA compliance. Several assay conditions missing. Data reproducibility at risk.";
  }
  return "❌ Minimal STRENDA compliance. Recommend obtaining complete assay conditions.";
}

/**
 * Compare two STRENDA validations
 * Used when deciding between multiple literature values
 */
export function compareSTREANDA(
  v1: STREANDAValidation,
  v2: STREANDAValidation,
): -1 | 0 | 1 {
  // Prefer higher score
  if (v1.score > v2.score) return -1;
  if (v1.score < v2.score) return 1;

  // Equal score: prefer fewer violations
  if (v1.violations.length < v2.violations.length) return -1;
  if (v1.violations.length > v2.violations.length) return 1;

  // Equal: prefer fewer warnings
  if (v1.warnings.length < v2.warnings.length) return -1;
  if (v1.warnings.length > v2.warnings.length) return 1;

  return 0;
}
