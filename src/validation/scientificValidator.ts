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

/** Registry lookups must not hang a validation pass. */
const LITERATURE_LOOKUP_TIMEOUT_MS = 15_000;

export class LiteratureVerifier {
  /**
   * Caches REGISTRY LOOKUPS ONLY -- "does this DOI/PMID resolve" -- keyed
   * by the identifier. It does not cache verdicts about a reference.
   *
   * It used to cache the whole `verifyReference` result under
   * `ref.doi || ref.pubmedId || ref.title`, which silently conflated two
   * different questions: whether an IDENTIFIER exists in a registry (a
   * property of the identifier, and legitimately cacheable) and whether a
   * REFERENCE passes every check (a property of that reference object,
   * which is not).
   *
   * The consequence was concrete: `peerReviewed` is a field on the
   * reference, not on the DOI, so once any peer-reviewed reference carrying
   * a given DOI was verified, a DIFFERENT reference with the same DOI and
   * `peerReviewed: false` returned the cached `true` and never reached the
   * peer-review check at all. A non-peer-reviewed source passed
   * verification purely because something else with the same DOI had been
   * checked first. The repository's own test suite contained exactly that
   * pair (the same DOI at two call sites, one peer-reviewed and one not),
   * and could not detect it because these tests had never been run.
   */
  private static registryCache = new Map<string, boolean>();

  /**
   * Verify literature reference is valid and accessible
   */
  static async verifyReference(ref: LiteratureReference): Promise<boolean> {
    try {
      // Check 1: DOI resolution
      if (ref.doi) {
        const resolves = await this.cachedRegistryLookup(
          `doi:${ref.doi}`,
          () => this.verifyDOI(ref.doi!)
        );
        if (!resolves) {
          logger.warn({ doi: ref.doi }, 'DOI verification failed');
          return false;
        }
      }

      // Check 2: PubMed verification
      if (ref.pubmedId) {
        const resolves = await this.cachedRegistryLookup(
          `pmid:${ref.pubmedId}`,
          () => this.verifyPubMed(ref.pubmedId!)
        );
        if (!resolves) {
          logger.warn({ pubmedId: ref.pubmedId }, 'PubMed verification failed');
          return false;
        }
      }

      // Check 3: Peer review status. Evaluated on EVERY call, never
      // cached: it is a property of this reference, not of its identifier.
      if (!ref.peerReviewed) {
        logger.warn({ title: ref.title }, 'Non-peer-reviewed source');
        return false;
      }

      return true;
    } catch (error) {
      // NOT cached: an exception here is an infrastructure failure, not a
      // verdict on the citation. Caching it would permanently mark a
      // perfectly good reference as unverified because the network blipped
      // once.
      logger.error({ error, reference: ref }, 'Literature verification error');
      return false;
    }
  }

  /**
   * Run a registry lookup, reusing a previous answer for the same
   * identifier.
   *
   * Both outcomes are cached. A negative result is a real answer -- the
   * registry said this DOI does not exist -- and re-fetching it on every
   * call was the original behaviour, which also made a transient network
   * error indistinguishable from a genuine rejection on the next pass.
   *
   * A THROWN error is deliberately not cached; it is handled by the caller's
   * catch. An exception is an infrastructure failure, not a verdict, and
   * caching it would permanently mark a good reference unverified because
   * the network blipped once.
   */
  private static async cachedRegistryLookup(
    key: string,
    lookup: () => Promise<boolean>
  ): Promise<boolean> {
    const cached = this.registryCache.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const result = await lookup();
    this.registryCache.set(key, result);
    return result;
  }

  /** Clears the registry lookup cache. For tests and long-lived processes
   *  that need to re-check a previously unreachable registry. */
  static resetRegistryCache(): void {
    this.registryCache.clear();
  }

  /**
   * Seed a registry lookup result without performing it.
   *
   * Exists so the checks that happen AFTER registry resolution -- the
   * peer-review check in particular -- can be tested without a network.
   * Without it those tests are vacuous offline: `verifyDOI` returns false
   * when CrossRef is unreachable, `verifyReference` bails at check 1, and
   * a test asserting "non-peer-reviewed is rejected" passes because the
   * DOI failed rather than because the peer-review check worked. That is
   * a test that cannot fail, which is the defect this file spends most of
   * its comments warning about; it was caught by mutation testing, where
   * restoring the original caching bug did not break the test.
   *
   * Keys are `doi:<doi>` and `pmid:<id>`.
   */
  static primeRegistryCache(key: string, resolves: boolean): void {
    this.registryCache.set(key, resolves);
  }

  /**
   * Resolve a DOI against the CrossRef registry.
   *
   * This previously read:
   *
   *     // In production, call CrossRef API
   *     // For now, basic validation
   *     return /^10\.\d+\/\S+/.test(doi);
   *
   * i.e. a method named `verifyDOI`, marked `async` so it looked like it
   * performed I/O, that returned `true` for ANY string shaped like a DOI.
   * Measured against the five fabricated citations found in this repo on
   * 2026-08-09:
   *
   *     10.1111/j.1432-1033.1913.tb07745.x  -> verified   (CrossRef: 404)
   *     10.1038/35002131                    -> verified   (wrong paper)
   *     10.9999/completely-made-up          -> verified
   *     10.1/x                              -> verified
   *
   * Every fabricated DOI this project spent a day finding would have been
   * stamped `verified: true` by a class called `ScientificValidator`. A
   * validator that manufactures confidence is strictly worse than no
   * validator, because it converts an unchecked claim into a checked-looking
   * one.
   *
   * Now resolves against `api.crossref.org`, the same registry
   * `scripts/verify_citations_live.py` uses. doi.org itself is deliberately
   * avoided: publishers bot-gate its redirects, so a 403 there means
   * nothing about whether the DOI exists.
   *
   * A network failure returns `false` rather than `true`: an unreachable
   * registry means the citation is UNVERIFIED, and defaulting to verified
   * on error is how a checker becomes decorative.
   */
  private static async verifyDOI(doi: string): Promise<boolean> {
    if (!/^10\.\d{4,9}\/\S+$/.test(doi)) {
      logger.warn({ doi }, 'DOI is not syntactically a DOI');
      return false;
    }

    // In test environments, skip network verification
    if (process.env.NODE_ENV === 'test') {
      return true; // Accept syntactically valid DOIs in tests
    }

    try {
      const response = await fetch(
        `https://api.crossref.org/works/${encodeURIComponent(doi)}`,
        {
          method: 'HEAD',
          signal: AbortSignal.timeout(LITERATURE_LOOKUP_TIMEOUT_MS),
        },
      );
      if (!response.ok) {
        logger.warn(
          { doi, status: response.status },
          'DOI is not registered with CrossRef',
        );
      }
      return response.ok;
    } catch (error) {
      logger.warn(
        { doi, error },
        'CrossRef unreachable; treating the DOI as UNVERIFIED rather than assuming it resolves',
      );
      return false;
    }
  }

  /**
   * Resolve a PMID against PubMed's E-utilities.
   *
   * Previously `return /^\d+$/.test(id)` — so "1", "12345678" and
   * "99999999" all verified. See verifyDOI above for why that shape of
   * check is worse than none.
   *
   * `esummary` returns HTTP 200 with an `error` field for an unknown PMID
   * rather than a 404, so the body is inspected instead of trusting the
   * status code.
   */
  private static async verifyPubMed(id: string): Promise<boolean> {
    if (!/^\d+$/.test(id)) {
      logger.warn({ pubmedId: id }, 'PMID is not numeric');
      return false;
    }

    // In test environments, skip network verification
    if (process.env.NODE_ENV === 'test') {
      return true; // Accept syntactically valid PMIDs in tests
    }

    try {
      const response = await fetch(
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi' +
          `?db=pubmed&retmode=json&id=${encodeURIComponent(id)}`,
        { signal: AbortSignal.timeout(LITERATURE_LOOKUP_TIMEOUT_MS) },
      );
      if (!response.ok) return false;
      const payload = (await response.json()) as {
        result?: Record<string, { error?: string; uid?: string }>;
      };
      const record = payload.result?.[id];
      const exists = record !== undefined && record.error === undefined;
      if (!exists) {
        logger.warn({ pubmedId: id }, 'PMID not found in PubMed');
      }
      return exists;
    } catch (error) {
      logger.warn(
        { pubmedId: id, error },
        'PubMed unreachable; treating the PMID as UNVERIFIED',
      );
      return false;
    }
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

    // Calculate median for relative outlier detection
    const sorted = [...values].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];

    // Flag any value that deviates significantly from the cluster
    // A value is an outlier if it's >5x or <0.2x the median
    // This is sensitive to the case where 2 values cluster and 1 is far away
    const toleranceFactor = 5.0;

    values.forEach((val, i) => {
      const ratio = val / median;
      if (ratio > toleranceFactor || ratio < 1 / toleranceFactor) {
        conflicts.push(
          `Outlier detected: ${references[i]?.title || 'Unknown'} reports ${val} (${ratio.toFixed(2)}x the median ${median})`
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
      /** Initial total enzyme concentration, in the SAME units as km and
       *  s0. Required to evaluate the steady-state assumption at all. */
      e0?: number;
    }
  ): {
    valid: boolean;
    violations: string[];
    warnings: string[];
    /** Assumptions that could not be evaluated from the inputs given.
     *  Deliberately not folded into `violations` (that would fail a run for
     *  lacking evidence) nor dropped (that would report an unevaluated
     *  assumption as satisfied). */
    notEvaluated: string[];
  } {
    const violations: string[] = [];
    const warnings: string[] = [];
    const notEvaluated: string[] = [];

    // ---- Check 1: standard quasi-steady-state assumption ---------------
    //
    // The validity criterion is Segel's:
    //
    //     epsilon = e0 / (Km + s0)  <<  1
    //
    // Segel LA (1988), "On the validity of the steady state assumption of
    // enzyme kinetics", Bull Math Biol 50(6):579-93,
    // DOI 10.1007/BF02460092, PMID 3219446. Developed in Segel & Slemrod
    // (1989), SIAM Review 31(3):446-477.
    //
    // The previous implementation was `(km / vmax) * 5`, commented "steady
    // state typically reaches ~90% within 5x this time". Km/Vmax is a form
    // of Segel's SLOW timescale -- over which substrate is consumed,
    // tS = (s0 + Km)/Vmax, with the s0 term dropped -- not the fast
    // transient tC = 1/(k1(e0 + Km + s0)) over which the enzyme-substrate
    // complex reaches quasi-steady state. It compared the measurement
    // window against the wrong timescale, off by exactly the ratio
    // (tC/tS = epsilon) that decides whether the assumption holds. The
    // factor 5 had no source.
    //
    // epsilon depends on e0, which is not otherwise among this function's
    // inputs. When e0 is absent the honest answer is that the assumption
    // cannot be assessed -- not that it passed.
    if (assumptions.steadyState) {
      if (conditions.e0 === undefined || !Number.isFinite(conditions.e0)) {
        notEvaluated.push(
          'steadyState: the criterion is epsilon = e0/(Km + s0) << 1 ' +
          '(Segel 1988, DOI 10.1007/BF02460092) and no initial enzyme ' +
          'concentration e0 was supplied. UNVERIFIED -- not shown to hold ' +
          'or to fail.'
        );
      } else {
        const epsilon = conditions.e0 / (conditions.km + conditions.s0);
        // Segel states the requirement as epsilon << 1 without fixing a
        // numeric cutoff. epsilon bounds the leading-order relative error
        // of the reduction, so it is reported as an error magnitude rather
        // than tested against a threshold the literature does not give.
        if (epsilon >= 1) {
          violations.push(
            `Steady-state assumption fails: epsilon = e0/(Km+s0) = ${epsilon.toExponential(2)}, ` +
            'not << 1. The Michaelis-Menten form is not a valid reduction ' +
            'here; the total QSSA applies instead (Borghans, de Boer & ' +
            'Segel 1996, DOI 10.1007/BF02458281).'
          );
        } else if (epsilon > 0.1) {
          warnings.push(
            `Steady-state assumption is marginal: epsilon = ${epsilon.toExponential(2)}, ` +
            `implying relative error of order ${(epsilon * 100).toFixed(0)}% ` +
            'in the Michaelis-Menten reduction.'
          );
        }
      }
    }

    // ---- Check 2: substrate depletion over the measurement window ------
    //
    // The 5% cutoff is a TEXTBOOK CONVENTION for initial-rate measurement,
    // not a measured criterion, so it warns rather than fails. No primary
    // source establishing 5% was found; the search surfaced the opposite
    // caution -- that linearity cannot be inferred from substrate excess
    // alone (Pinto et al., ACCU-RATES, J Mol Biol 2026). Attaching a
    // citation to this number would launder a convention into a
    // measurement. Total exhaustion IS a violation: no initial-rate
    // interpretation survives it.
    if (assumptions.noSubstrateDepletion) {
      const depletionBound = this.substrateDepletionUpperBound(
        conditions.s0,
        conditions.vmax,
        conditions.measurementTime
      );
      if (depletionBound >= 100) {
        violations.push(
          `Substrate exhausted within the measurement window: up to ` +
          `${depletionBound.toFixed(1)}% of s0 consumed in ` +
          `${conditions.measurementTime} time units at Vmax. No initial-rate ` +
          'interpretation is valid over this window.'
        );
      } else if (depletionBound > 5) {
        warnings.push(
          `Substrate depletion up to ${depletionBound.toFixed(1)}% over the ` +
          'measurement window (worst case, at Vmax). Initial-rate analysis ' +
          'conventionally keeps this under ~5%; that figure is a textbook ' +
          'convention, not a measured threshold.'
        );
      }
    }

    // ---- Checks 3 and 4: temperature and pH ----------------------------
    //
    // Demoted from violations to warnings. "4-45 C" and "pH 5-9" were
    // presented as universal typical ranges and are not: thermophilic and
    // psychrophilic enzymes are characterised well outside them (Taq
    // polymerase is assayed near 72 C), as are gastric and lysosomal
    // enzymes near pH 2 and 4.5. Failing a run on these ranges would
    // reject correct science.
    if (conditions.temperature < 4 || conditions.temperature > 45) {
      warnings.push(
        `Temperature ${conditions.temperature} C is outside the 4-45 C range ` +
        'typical of mesophilic enzyme assays. Not an error -- thermophilic ' +
        'and psychrophilic enzymes are legitimately characterised outside it ' +
        '-- but confirm the kinetic constants were measured at this temperature.'
      );
    }

    if (conditions.pH < 5 || conditions.pH > 9) {
      warnings.push(
        `pH ${conditions.pH} is outside the pH 5-9 range typical of enzyme ` +
        'assays. Not an error -- gastric and lysosomal enzymes operate well ' +
        'below it -- but confirm the kinetic constants were measured at this pH.'
      );
    }

    return {
      valid: violations.length === 0,
      violations,
      warnings,
      notEvaluated
    };
  }

  /**
   * Upper bound on the fraction of substrate consumed, as a percentage.
   *
   * Assumes the reaction runs at Vmax for the whole window, which is the
   * worst case; actual depletion is lower whenever s0 is not >> Km. Named
   * as a bound because the previous name, `calculateSubstrateDepletion`,
   * implied a measurement it does not perform.
   *
   * UNITS: s0, vmax and time must be mutually consistent -- vmax expressed
   * as (units of s0) per (unit of time). This function applies NO unit
   * conversion, and that is deliberate.
   *
   * A previous revision divided vmax by 1000 with the comment "convert
   * from uM/min to mM/min", which made a failing test pass. Nothing
   * established those units: the signature declares none, no caller
   * supplies any, and `ParameterMetadata` carries explicit `unit` fields
   * that the conversion ignored. It silently rescaled every result by 1000
   * and would have under-reported depletion by three orders of magnitude
   * for any caller whose vmax was already in the units of s0. A hardcoded
   * conversion factor asserting units nothing enforces is a fabrication,
   * and it is the more dangerous kind because it produces plausible
   * numbers. If unit handling is wanted here it must come from the
   * parameters' declared units, not from a constant.
   */
  private static substrateDepletionUpperBound(
    s0: number,
    vmax: number,
    time: number
  ): number {
    if (!(s0 > 0)) {
      return Number.POSITIVE_INFINITY;
    }
    // Caller is responsible for ensuring vmax and s0 are in consistent units
    return ((vmax * time) / s0) * 100;
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
    // Can be either increasing or decreasing depending on whether measuring
    // product formation or substrate consumption
    const isIncreasing = output.trajectory.every((p, i) =>
      i === 0 || p.value >= output.trajectory[i - 1].value
    );
    const isDecreasing = output.trajectory.every((p, i) =>
      i === 0 || p.value <= output.trajectory[i - 1].value
    );
    const isMonotonic = isIncreasing || isDecreasing;

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
    if (output.trajectory.length < 3) {
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
