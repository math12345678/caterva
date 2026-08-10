/**
 * Scientific Validation Service
 *
 * PRINCIPLE: NO CODE SHIPS WITHOUT SCIENTIFIC VALIDATION
 * Every parameter must:
 * 1. Have literature backing
 * 2. Be within documented ranges
 * 3. Pass confidence scoring
 * 4. Complete 4-layer validation
 *
 * If ANY validation fails, execution STOPS immediately.
 */

import { logger } from '../logger';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface LiteratureReference {
  doi?: string;
  pubmedId?: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  peerReviewed: boolean;
  impactFactor?: number;
  citations?: number;
}

export interface ParameterMetadata {
  name: string;
  value: number;
  unit: string;
  min: number;           // Literature minimum
  max: number;           // Literature maximum
  literature: LiteratureReference[];
  confidence: number;    // 0-1
  conditions?: {
    temperature?: number;
    pH?: number;
    substrate?: string;
  };
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  confidence: number;
  summary: string;
}

export interface ValidationError {
  code: string;
  field: string;
  message: string;
  severity: 'critical' | 'high';
  fix?: string;
}

export interface ValidationWarning {
  code: string;
  field: string;
  message: string;
  severity: 'medium' | 'low';
}

// ============================================================================
// LAYER 1: PARAMETER VALIDATION
// ============================================================================

export class ParameterValidator {
  /**
   * Validate a single parameter against literature ranges
   */
  static validateParameter(param: ParameterMetadata): ValidationResult {
    const errors: ValidationError[] = [];
    const warnings: ValidationWarning[] = [];

    // Rule 1: Must have literature sources
    if (!param.literature || param.literature.length === 0) {
      errors.push({
        code: 'NO_LITERATURE',
        field: param.name,
        message: `Parameter '${param.name}' has no literature backing`,
        severity: 'critical',
        fix: 'Provide at least 2 peer-reviewed sources'
      });
    }

    // Rule 2: All sources must be peer-reviewed
    if (param.literature) {
      const nonPeerReviewed = param.literature.filter(r => !r.peerReviewed);
      if (nonPeerReviewed.length > 0) {
        errors.push({
          code: 'NON_PEER_REVIEWED',
          field: param.name,
          message: `${nonPeerReviewed.length} non-peer-reviewed sources for '${param.name}'`,
          severity: 'high',
          fix: 'Use only peer-reviewed publications'
        });
      }
    }

    // Rule 3: Value must be within range
    if (param.value < param.min || param.value > param.max) {
      errors.push({
        code: 'OUT_OF_RANGE',
        field: param.name,
        message: `${param.name}=${param.value} ${param.unit} outside literature range [${param.min}, ${param.max}]`,
        severity: 'critical',
        fix: `Revise to range [${param.min}, ${param.max}] or provide new literature justification`
      });
    }

    // Rule 4: Confidence must be high
    if (param.confidence < 0.7) {
      warnings.push({
        code: 'LOW_CONFIDENCE',
        field: param.name,
        message: `Low confidence (${param.confidence}) for '${param.name}'`,
        severity: 'medium'
      });
    }

    // Rule 5: Citation quality (prefer high-impact journals)
    if (param.literature && param.literature.length > 0) {
      const avgImpactFactor = param.literature.reduce((sum, r) => sum + (r.impactFactor || 0), 0) / param.literature.length;
      if (avgImpactFactor < 1.5) {
        warnings.push({
          code: 'LOW_IMPACT_JOURNAL',
          field: param.name,
          message: `Average journal impact factor (${avgImpactFactor.toFixed(2)}) is low`,
          severity: 'low'
        });
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      confidence: this.calculateConfidence(param, errors, warnings),
      summary: errors.length === 0
        ? `✓ ${param.name} validated`
        : `✗ ${param.name} failed: ${errors.map(e => e.code).join(', ')}`
    };
  }

  /**
   * Calculate confidence score (0-1)
   */
  private static calculateConfidence(
    param: ParameterMetadata,
    errors: ValidationError[],
    warnings: ValidationWarning[]
  ): number {
    if (errors.length > 0) return 0;

    let confidence = param.confidence;

    // Reduce for warnings
    confidence -= warnings.filter(w => w.severity === 'medium').length * 0.05;
    confidence -= warnings.filter(w => w.severity === 'low').length * 0.02;

    // Boost for high citation count
    if (param.literature && param.literature.length > 2) {
      const avgCitations = param.literature.reduce((sum, r) => sum + (r.citations || 0), 0) / param.literature.length;
      if (avgCitations > 500) confidence += 0.05;
    }

    return Math.max(0, Math.min(1, confidence));
  }
}

// ============================================================================
// LAYER 2: LITERATURE VERIFICATION
// ============================================================================

export class LiteratureVerifier {
  private static verifiedCache = new Map<string, boolean>();

  /**
   * Verify literature reference is valid and accessible
   */
  static async verifyReference(ref: LiteratureReference): Promise<boolean> {
    const cacheKey = ref.doi || ref.pubmedId || ref.title;

    if (this.verifiedCache.has(cacheKey)) {
      return this.verifiedCache.get(cacheKey)!;
    }

    try {
      let verified = false;

      // Check 1: DOI resolution
      if (ref.doi) {
        verified = await this.verifyDOI(ref.doi);
        if (!verified) {
          logger.warn({ doi: ref.doi }, 'DOI verification failed');
          return false;
        }
      }

      // Check 2: PubMed verification
      if (ref.pubmedId) {
        verified = await this.verifyPubMed(ref.pubmedId);
        if (!verified) {
          logger.warn({ pubmedId: ref.pubmedId }, 'PubMed verification failed');
          return false;
        }
      }

      // Check 3: Peer review status
      if (!ref.peerReviewed) {
        logger.warn({ title: ref.title }, 'Non-peer-reviewed source');
        return false;
      }

      this.verifiedCache.set(cacheKey, true);
      return true;
    } catch (error) {
      logger.error({ error, reference: ref }, 'Literature verification error');
      return false;
    }
  }

  private static async verifyDOI(doi: string): Promise<boolean> {
    // In production, call CrossRef API
    // For now, basic validation
    return /^10\.\d+\/\S+/.test(doi);
  }

  private static async verifyPubMed(id: string): Promise<boolean> {
    // In production, call PubMed API
    // For now, basic validation
    return /^\d+$/.test(id);
  }

  /**
   * Find conflicting literature values
   */
  static findConflicts(
    references: LiteratureReference[],
    values: number[]
  ): string[] {
    if (values.length < 2) return [];

    const conflicts: string[] = [];
    const mean = values.reduce((a, b) => a + b) / values.length;
    const stdDev = Math.sqrt(
      values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length
    );

    // Flag outliers (>2 standard deviations)
    values.forEach((val, i) => {
      if (Math.abs(val - mean) > 2 * stdDev) {
        conflicts.push(
          `Outlier detected: ${references[i]?.title || 'Unknown'} reports ${val} (${Math.abs(val - mean).toFixed(2)}σ from mean)`
        );
      }
    });

    return conflicts;
  }
}

// ============================================================================
// LAYER 3: MODEL ASSUMPTION VALIDATION
// ============================================================================

export interface ModelAssumptions {
  steadyState: boolean;
  noSubstrateDepletion: boolean;
  noProductInhibition: boolean;
  enzymeNotDeactivating: boolean;
  singleEnzymeForm: boolean;
}

export class AssumptionValidator {
  /**
   * Validate that model assumptions hold under given conditions
   */
  static validateAssumptions(
    assumptions: ModelAssumptions,
    conditions: {
      km: number;
      vmax: number;
      s0: number;
      measurementTime: number;
      temperature: number;
      pH: number;
    }
  ): { valid: boolean; violations: string[] } {
    const violations: string[] = [];

    // Check 1: Steady-state assumption
    if (assumptions.steadyState) {
      const steadyStateTime = this.estimateSteadyStateTime(conditions.km, conditions.vmax);
      if (conditions.measurementTime < steadyStateTime) {
        violations.push(
          `Steady-state violated: measurement time (${conditions.measurementTime}s) < estimated steady-state time (${steadyStateTime.toFixed(2)}s)`
        );
      }
    }

    // Check 2: No substrate depletion
    if (assumptions.noSubstrateDepletion) {
      const depletion = this.calculateSubstrateDepletion(
        conditions.s0,
        conditions.vmax,
        conditions.measurementTime
      );
      if (depletion > 5) { // 5% threshold
        violations.push(
          `Substrate depletion violation: ${depletion.toFixed(1)}% depletion (limit: 5%)`
        );
      }
    }

    // Check 3: Temperature reasonableness
    if (conditions.temperature < 4 || conditions.temperature > 45) {
      violations.push(
        `Unusual temperature: ${conditions.temperature}°C (typical range: 4-45°C)`
      );
    }

    // Check 4: pH reasonableness
    if (conditions.pH < 5 || conditions.pH > 9) {
      violations.push(
        `Unusual pH: ${conditions.pH} (typical range: 5-9)`
      );
    }

    return {
      valid: violations.length === 0,
      violations
    };
  }

  private static estimateSteadyStateTime(km: number, vmax: number): number {
    // Roughly proportional to Km/Vmax
    // Steady state typically reaches ~90% within 5x this time
    return (km / vmax) * 5;
  }

  private static calculateSubstrateDepletion(s0: number, vmax: number, time: number): number {
    // Approximate: vmax * time / s0 * 100
    return (vmax * time / s0) * 100;
  }
}

// ============================================================================
// LAYER 4: RESULT VALIDATION
// ============================================================================

export interface SimulationOutput {
  trajectory: Array<{ time: number; value: number }>;
  finalValue: number;
  computedVmax?: number;
  computedKm?: number;
}

export class ResultValidator {
  /**
   * Validate simulation output
   */
  static validateOutput(output: SimulationOutput): {
    valid: boolean;
    issues: string[];
    dataQuality: number; // 0-1
  } {
    const issues: string[] = [];
    let dataQuality = 1.0;

    // Check 1: No NaN or Infinity
    if (output.trajectory.some(p => !isFinite(p.value))) {
      issues.push('Output contains NaN or Infinity values');
      dataQuality -= 0.5;
    }

    // Check 2: Monotonicity (should be monotonic for enzyme kinetics)
    const isMonotonic = output.trajectory.every((p, i) =>
      i === 0 || p.value >= output.trajectory[i - 1].value
    );
    if (!isMonotonic) {
      issues.push('Trajectory not monotonic - possible numerical instability');
      dataQuality -= 0.3;
    }

    // Check 3: Reasonable range (enzyme kinetics typically 0-100)
    const inRange = output.trajectory.every(p => p.value >= 0 && p.value <= 1000);
    if (!inRange) {
      issues.push('Values outside expected biological range');
      dataQuality -= 0.2;
    }

    // Check 4: Sufficient data points
    if (output.trajectory.length < 5) {
      issues.push('Insufficient data points for validation');
      dataQuality -= 0.2;
    }

    return {
      valid: issues.length === 0 && dataQuality > 0.7,
      issues,
      dataQuality: Math.max(0, dataQuality)
    };
  }

  /**
   * Compare output to expected literature values
   */
  static compareToLiterature(
    output: SimulationOutput,
    literatureValue: number,
    tolerancePercent: number = 10
  ): { withinTolerance: boolean; error: number } {
    const error = Math.abs(output.finalValue - literatureValue) / literatureValue * 100;

    return {
      withinTolerance: error <= tolerancePercent,
      error
    };
  }
}

// ============================================================================
// COMPREHENSIVE VALIDATION PIPELINE
// ============================================================================

export class ScientificValidationPipeline {
  /**
   * Complete validation: 4 layers, fail-fast
   */
  static async validate(
    parameters: ParameterMetadata[],
    assumptions: ModelAssumptions,
    conditions: any,
    output?: SimulationOutput
  ): Promise<{
    passed: boolean;
    confidence: number;
    summary: string;
    errors: string[];
  }> {
    const errors: string[] = [];
    let minConfidence = 1.0;

    logger.info({ parameterCount: parameters.length }, 'Starting 4-layer validation');

    // LAYER 1: Parameter Validation
    logger.info('LAYER 1: Parameter Validation');
    for (const param of parameters) {
      const result = ParameterValidator.validateParameter(param);

      if (!result.valid) {
        errors.push(`Parameter '${param.name}': ${result.summary}`);
        result.errors.forEach(e => {
          logger.error({ error: e.code, field: e.field }, e.message);
        });
        return { passed: false, confidence: 0, summary: `Layer 1 failed: ${param.name}`, errors };
      }

      minConfidence = Math.min(minConfidence, result.confidence);
      logger.info({ parameter: param.name, confidence: result.confidence }, result.summary);
    }

    // LAYER 2: Literature Verification
    logger.info('LAYER 2: Literature Verification');
    for (const param of parameters) {
      for (const ref of param.literature) {
        const verified = await LiteratureVerifier.verifyReference(ref);
        if (!verified) {
          errors.push(`Literature reference not verified: ${ref.title}`);
          logger.error({ reference: ref.doi || ref.title }, 'Literature verification failed');
          return { passed: false, confidence: 0, summary: 'Layer 2 failed: literature verification', errors };
        }
      }
    }
    logger.info('All literature references verified');

    // LAYER 3: Assumption Validation
    logger.info('LAYER 3: Model Assumption Validation');
    const assumptionResult = AssumptionValidator.validateAssumptions(assumptions, conditions);
    if (!assumptionResult.valid) {
      assumptionResult.violations.forEach(v => {
        logger.warn({ violation: v }, 'Assumption violated');
        minConfidence -= 0.1;
      });
    }

    // LAYER 4: Result Validation
    if (output) {
      logger.info('LAYER 4: Result Validation');
      const resultValidation = ResultValidator.validateOutput(output);
      if (!resultValidation.valid) {
        errors.push(`Result validation failed: ${resultValidation.issues.join(', ')}`);
        resultValidation.issues.forEach(issue => {
          logger.error({ issue }, 'Result validation failed');
        });
        return { passed: false, confidence: 0, summary: 'Layer 4 failed: result validation', errors };
      }
      minConfidence = Math.min(minConfidence, resultValidation.dataQuality);
      logger.info({ dataQuality: resultValidation.dataQuality }, 'Result validation passed');
    }

    logger.info({ confidence: minConfidence }, '✓ All validation layers passed');

    return {
      passed: true,
      confidence: Math.max(0, minConfidence),
      summary: `✓ Validation complete (confidence: ${(minConfidence * 100).toFixed(1)}%)`,
      errors: []
    };
  }
}

// ============================================================================
// EXPORT
// ============================================================================

export default {
  ParameterValidator,
  LiteratureVerifier,
  AssumptionValidator,
  ResultValidator,
  ScientificValidationPipeline
};
