/**
 * Literature Database Service
 *
 * Manages curated scientific literature with:
 * - Parameter extraction
 * - Cross-verification
 * - Conflict detection
 * - Citation tracking
 *
 * PRINCIPLE: Every parameter is traceable to primary literature
 */

import { logger } from '../logger';
import { convertConcentration, convertRate, parseRateUnit } from '../units';

/**
 * Convert a value between units of the same kind, choosing concentration or
 * rate handling by the shape of the unit string. Raises for anything it
 * cannot interpret -- see src/units.ts for why guessing is forbidden here.
 */
function convertToUnit(value: number, from: string, to: string): number {
  const fromIsRate = from.includes('/');
  const toIsRate = to.includes('/');
  if (fromIsRate !== toIsRate) {
    throw new Error(
      `'${from}' and '${to}' are different kinds of quantity (one is a rate, ` +
      'one is not) and cannot be converted into each other.'
    );
  }
  if (fromIsRate) {
    parseRateUnit(from);
    parseRateUnit(to);
    return convertRate(value, from, to);
  }
  return convertConcentration(value, from, to);
}

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface Literature {
  id: string;
  doi?: string;
  pubmedId?: string;
  arxivId?: string;

  title: string;
  authors: string[];
  year: number;
  journal: string;
  volume?: string;
  issue?: string;
  pages?: string;

  peerReviewed: boolean;
  impactFactor?: number;
  citationCount?: number;

  abstract: string;
  domain: string; // 'mm' | 'sir' | etc

  extractedParameters: Array<{
    name: string;
    value: number;
    unit: string;
    table?: string;
    page?: number;
    conditions?: {
      temperature?: number;
      pH?: number;
      substrate?: string;
      species?: string;
    };
  }>;
}

export interface ParameterRecommendation {
  parameterName: string;
  recommendedValue: number;
  /** The unit `recommendedValue` and `range` are expressed in, taken from
   *  the sources rather than assumed from the parameter's name. */
  unit: string;
  range: [number, number];
  sources: string[]; // DOIs
  sourceCount: number;
  confidence: number;
  warnings: string[];
}

export interface CrossVerificationResult {
  parameterName: string;
  values: number[];
  sources: Literature[];
  mean: number;
  stdDev: number;
  min: number;
  max: number;
  relativeDeviation: number;
  consensus: 'strong' | 'moderate' | 'weak' | 'conflicting';
  recommendation: string;
}

// ============================================================================
// LITERATURE DATABASE
// ============================================================================

export class LiteratureDatabase {
  private db: Map<string, Literature> = new Map();
  private parameterIndex: Map<string, Set<string>> = new Map(); // parameter -> literature IDs

  /**
   * Add literature to database
   */
  add(literature: Literature): void {
    if (this.db.has(literature.id)) {
      logger.warn({ id: literature.id }, 'Literature already exists, updating');
    }

    this.db.set(literature.id, literature);

    // Index parameters
    for (const param of literature.extractedParameters) {
      const key = `${param.name}:${literature.domain}`;
      if (!this.parameterIndex.has(key)) {
        this.parameterIndex.set(key, new Set());
      }
      this.parameterIndex.get(key)!.add(literature.id);
    }

    logger.info(
      {
        id: literature.id,
        doi: literature.doi,
        parameters: literature.extractedParameters.length
      },
      'Literature added to database'
    );
  }

  /**
   * Find all literature supporting a parameter
   */
  findByParameter(
    parameterName: string,
    domain: string
  ): Literature[] {
    const key = `${parameterName}:${domain}`;
    const ids = this.parameterIndex.get(key);

    if (!ids || ids.size === 0) {
      return [];
    }

    return Array.from(ids).map(id => this.db.get(id)!).filter(Boolean);
  }

  /**
   * Find literature by DOI
   */
  findByDOI(doi: string): Literature | undefined {
    for (const lit of this.db.values()) {
      if (lit.doi === doi) return lit;
    }
    return undefined;
  }

  /**
   * Get statistics on literature database
   */
  getStats(): {
    totalEntries: number;
    byDomain: Record<string, number>;
    peerReviewedCount: number;
    averageImpactFactor: number;
    averageCitations: number;
  } {
    const entries = Array.from(this.db.values());

    const byDomain: Record<string, number> = {};
    let totalImpactFactor = 0;
    let totalCitations = 0;
    let impactFactorCount = 0;
    let citationCount = 0;

    for (const lit of entries) {
      byDomain[lit.domain] = (byDomain[lit.domain] || 0) + 1;

      if (lit.impactFactor) {
        totalImpactFactor += lit.impactFactor;
        impactFactorCount++;
      }

      if (lit.citationCount) {
        totalCitations += lit.citationCount;
        citationCount++;
      }
    }

    return {
      totalEntries: entries.length,
      byDomain,
      peerReviewedCount: entries.filter(e => e.peerReviewed).length,
      averageImpactFactor: impactFactorCount > 0 ? totalImpactFactor / impactFactorCount : 0,
      averageCitations: citationCount > 0 ? totalCitations / citationCount : 0
    };
  }
}

// ============================================================================
// PARAMETER RECOMMENDATION
// ============================================================================

export class ParameterRecommender {
  constructor(private db: LiteratureDatabase) {}

  /**
   * Get recommended value for a parameter based on literature
   */
  recommend(
    parameterName: string,
    domain: string
  ): ParameterRecommendation {
    const literature = this.db.findByParameter(parameterName, domain);

    if (literature.length === 0) {
      throw new Error(`No literature found for parameter '${parameterName}' in domain '${domain}'`);
    }

    // Extract all values WITH their declared units.
    //
    // This previously mapped `p => ({ value: p.value, literature: lit })`,
    // dropping `p.unit` entirely, and then took a weighted mean across the
    // raw numbers. If one source reported Km in mM and another in uM -- a
    // completely routine occurrence, BRENDA carries both -- the "recommended
    // value" was the average of quantities in different units, which is not
    // a quantity at all. Nothing downstream could detect it, because the
    // result was then labelled with a unit guessed from the parameter's
    // NAME by `getDefaultUnit`, so it always looked self-consistent.
    const rawValues = literature.flatMap(lit =>
      lit.extractedParameters
        .filter(p => p.name === parameterName)
        .map(p => ({ value: p.value, unit: p.unit, literature: lit }))
    );

    if (rawValues.length === 0) {
      throw new Error(`No values extracted for parameter '${parameterName}'`);
    }

    // Everything is converted onto the first source's unit. Conversion is
    // driven by the declared strings, and an unrecognised or incompatible
    // unit raises rather than being averaged in as a bare number.
    const targetUnit = rawValues[0]!.unit;
    const values = rawValues.map(entry => {
      if (entry.unit === targetUnit) {
        return { value: entry.value, literature: entry.literature };
      }
      try {
        return {
          value: convertToUnit(entry.value, entry.unit, targetUnit),
          literature: entry.literature
        };
      } catch (error) {
        throw new Error(
          `Cannot combine literature values for '${parameterName}': source ` +
          `${entry.literature.doi || entry.literature.id} reports ` +
          `${entry.value} ${entry.unit} but ${rawValues[0]!.literature.doi || rawValues[0]!.literature.id} ` +
          `reports ${targetUnit}. ` +
          (error instanceof Error ? error.message : String(error))
        );
      }
    });

    // Calculate statistics
    const valueNumbers = values.map(v => v.value);
    const mean = valueNumbers.reduce((a, b) => a + b, 0) / valueNumbers.length;
    const stdDev = Math.sqrt(
      valueNumbers.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / valueNumbers.length
    );

    // Detect outliers
    const outliers = valueNumbers.filter(v => Math.abs(v - mean) > 2 * stdDev);
    const warnings: string[] = [];

    if (outliers.length > 0) {
      warnings.push(`${outliers.length} outliers detected (>2σ from mean)`);
    }

    // Weighted mean by journal quality
    let weightedMean = 0;
    let totalWeight = 0;

    for (const { value, literature: lit } of values) {
      const weight = this.calculateSourceWeight(lit);
      weightedMean += value * weight;
      totalWeight += weight;
    }

    weightedMean /= totalWeight;

    // Calculate confidence
    const variance = stdDev / mean; // Coefficient of variation
    let confidence = 1.0;
    if (variance > 0.2) confidence -= 0.2; // High variance reduces confidence
    if (literature.length < 2) confidence -= 0.2; // Single source reduces confidence
    if (outliers.length > 0) confidence -= 0.1; // Outliers reduce confidence

    confidence = Math.max(0, Math.min(1, confidence));

    return {
      parameterName,
      recommendedValue: weightedMean,
      unit: targetUnit,
      range: [Math.min(...valueNumbers), Math.max(...valueNumbers)],
      sources: literature.map(l => l.doi || l.pubmedId || l.id),
      sourceCount: literature.length,
      confidence,
      warnings
    };
  }

  /**
   * Calculate source weight (higher for high-quality journals)
   */
  private calculateSourceWeight(lit: Literature): number {
    let weight = 1.0;

    // Boost for peer review
    if (lit.peerReviewed) weight *= 1.5;

    // Boost for high-impact journals
    if (lit.impactFactor) {
      if (lit.impactFactor > 5) weight *= 1.3;
      else if (lit.impactFactor > 2) weight *= 1.1;
    }

    // Boost for highly cited papers
    if (lit.citationCount) {
      if (lit.citationCount > 500) weight *= 1.2;
      else if (lit.citationCount > 100) weight *= 1.1;
    }

    return weight;
  }
}

// ============================================================================
// CROSS-VERIFICATION
// ============================================================================

export class CrossVerifier {
  constructor(private db: LiteratureDatabase) {}

  /**
   * Verify parameter consistency across multiple literature sources
   */
  verify(parameterName: string, domain: string): CrossVerificationResult {
    const literature = this.db.findByParameter(parameterName, domain);

    if (literature.length < 2) {
      logger.warn(
        { parameterName, domain },
        'Cross-verification requires at least 2 sources'
      );
    }

    const values = literature
      .flatMap(lit =>
        lit.extractedParameters
          .filter(p => p.name === parameterName)
          .map(p => p.value)
      );

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);
    const relativeDeviation = (stdDev / mean) * 100;

    // Determine consensus
    let consensus: 'strong' | 'moderate' | 'weak' | 'conflicting' = 'strong';
    if (relativeDeviation > 20) consensus = 'moderate';
    if (relativeDeviation > 50) consensus = 'weak';
    if (relativeDeviation > 100) consensus = 'conflicting';

    const recommendation = this.generateRecommendation(
      parameterName,
      values,
      mean,
      consensus
    );

    return {
      parameterName,
      values,
      sources: literature,
      mean,
      stdDev,
      min: Math.min(...values),
      max: Math.max(...values),
      relativeDeviation,
      consensus,
      recommendation
    };
  }

  private generateRecommendation(
    parameterName: string,
    values: number[],
    mean: number,
    consensus: string
  ): string {
    const consensusMap = {
      strong: 'HIGH - Use weighted mean with confidence',
      moderate: 'MEDIUM - Consider range, recommend additional validation',
      weak: 'LOW - Conflicting literature, manual review required',
      conflicting: 'VERY LOW - Significant conflicts detected, do not use'
    };

    return `${parameterName} consensus level: ${consensusMap[consensus as keyof typeof consensusMap]}. Mean: ${mean.toFixed(3)}`;
  }

  /**
   * Find conflicting values (outliers)
   */
  findConflicts(parameterName: string, domain: string): {
    hasConflicts: boolean;
    outliers: Array<{ value: number; source: string; deviation: number }>;
  } {
    const result = this.verify(parameterName, domain);

    const outliers = result.sources
      .flatMap(lit =>
        lit.extractedParameters
          .filter(p => p.name === parameterName)
          .map(p => {
            const deviation = Math.abs(p.value - result.mean) / result.stdDev;
            return deviation > 2 ? {
              value: p.value,
              source: lit.doi || lit.id,
              deviation
            } : null;
          })
          .filter(Boolean)
      )
      .filter(Boolean) as Array<{ value: number; source: string; deviation: number }>;

    return {
      hasConflicts: outliers.length > 0,
      outliers
    };
  }
}

// ============================================================================
// LITERATURE SERVICE (MAIN API)
// ============================================================================

export class LiteratureService {
  private db: LiteratureDatabase;
  private recommender: ParameterRecommender;
  private verifier: CrossVerifier;

  constructor() {
    this.db = new LiteratureDatabase();
    this.recommender = new ParameterRecommender(this.db);
    this.verifier = new CrossVerifier(this.db);
  }

  /**
   * Add literature to database
   */
  addLiterature(lit: Literature): void {
    this.db.add(lit);
  }

  /**
   * Get parameter recommendation
   */
  getRecommendation(parameterName: string, domain: string): ParameterRecommendation {
    return this.recommender.recommend(parameterName, domain);
  }

  /**
   * Cross-verify parameter across sources
   */
  crossVerify(parameterName: string, domain: string): CrossVerificationResult {
    return this.verifier.verify(parameterName, domain);
  }

  /**
   * Find conflicts in literature
   */
  findConflicts(parameterName: string, domain: string): {
    hasConflicts: boolean;
    outliers: Array<{ value: number; source: string; deviation: number }>;
  } {
    return this.verifier.findConflicts(parameterName, domain);
  }

  /**
   * Get database statistics
   */
  getStats() {
    return this.db.getStats();
  }

  /**
   * Get literature by DOI
   */
  getByDOI(doi: string): Literature | undefined {
    return this.db.findByDOI(doi);
  }
}

// ============================================================================
// EXPORT
// ============================================================================

export default {
  LiteratureDatabase,
  ParameterRecommender,
  CrossVerifier,
  LiteratureService
};
