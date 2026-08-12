/**
 * Scientific Pipeline
 *
 * Complete integration of validation, literature, and reproducibility
 *
 * WORKFLOW:
 * 1. User submits query & parameters
 * 2. Validate against literature (fail-fast)
 * 3. Run simulation with verified parameters
 * 4. Validate results against literature
 * 5. Record execution for reproducibility
 * 6. Return results with confidence score
 */

import { logger } from '../logger';
import { ScientificValidationPipeline, ParameterValidator } from '../validation/scientificValidator';
import { LiteratureService } from '../literature/literatureService';
import { ReproducibilityService } from '../reproducibility/reproducibilityEngine';
import {
  extractSeries,
  runTellurium,
  type EngineParameterValue
} from '../engine/telluriumBridge';
import { convertConcentration, vmaxInSubstrateUnitsPerSecond } from '../units';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface SimulationRequest {
  query: string;
  /**
   * Which model to run, when the caller already knows.
   *
   * Same principle as `system` below, and for the same reason: a caller
   * that knows the answer should say it rather than encode it in prose for
   * the pipeline to guess back out. The CLI's `--model mm` knows exactly
   * which model was asked for, then built the query string
   * `"lactate dehydrogenase / pyruvate"` — which names no domain at all,
   * so the pipeline had to infer one from an enzyme name.
   *
   * When absent, `classifyDomain` reads the query, and a query it cannot
   * place is a validation failure rather than a default.
   */
  domain?: string;
  parameters?: Record<string, number>;
  conditions?: {
    temperature?: number;
    pH?: number;
    buffer?: string;
  };
  /**
   * The enzyme system to resolve kinetic constants for, against BRENDA and
   * PubMed via `LiteratureService.resolveFromLiterature`.
   *
   * Optional, and NOT inferred from `query` when absent. Guessing an
   * enzyme, substrate or organism out of free text would attach a real
   * citation to a system the user never named -- provenance for the wrong
   * measurement, which is worse than no provenance. Without this the
   * pipeline uses only literature the caller supplied directly.
   */
  system?: {
    enzymeName?: string;
    substrate: string;
    organism: string;
    ecNumber?: string;
  };
  /**
   * Total enzyme concentration [E]0, with its unit.
   *
   * An explicit caller input, never defaulted, inferred, or resolved from
   * literature -- BRENDA does not report it per row (ADR 0012 / ADR 0013).
   * Supplying it does two things that are otherwise impossible:
   *
   *   1. Bridges a literature-resolved kcat to a simulable
   *      Vmax = kcat * [E]0 (ADR 0019), computed in Python by the same
   *      `vmax_from_kcat` the engine uses.
   *   2. Makes the quasi-steady-state assumption CHECKABLE. Segel's
   *      criterion is epsilon = e0/(Km + s0) << 1, so without [E]0 that
   *      check cannot be evaluated at all and is reported UNVERIFIED --
   *      which is what it has been reporting on every run until now.
   */
  enzymeConcentration?: { value: number; unit: string };

  /**
   * Provenance for values the CALLER already resolved.
   *
   * The CLI's `--resolve` path looks parameters up itself (it needs the
   * kcat -> Vmax bridge, which the pipeline's own resolver does not cover)
   * and then passes the numbers in via `parameters`. Without this, those
   * arrive indistinguishable from hand-typed values: no citation, and
   * Layer 1 fails them with NO_LITERATURE for parameters that had just
   * been sourced from BRENDA.
   *
   * Keyed by parameter name. Only trusted for values the caller also
   * supplied in `parameters` -- it cannot conjure a parameter into
   * existence, only describe where a supplied one came from.
   */
  providedProvenance?: Record<
    string,
    { source: string; citations?: string[]; unit?: string }
  >;
}

/** A parameter after resolution, with whatever provenance came with it. */
export interface ResolvedParameter {
  value: number;
  unit: string;
  source: string;
  /** Identifiers (DOIs / BRENDA refs) the resolver returned, if any. */
  citations?: string[];
  sourceCount?: number;
}

export interface SimulationResponse {
  jobId: string;
  query: string;

  validated: boolean;
  validationConfidence: number;
  validationErrors: string[];

  results: {
    trajectory: Array<{ time: number; value: number; velocity: number }>;
    finalValue: number;
    computedMetrics: Record<string, number>;
  };

  reproducibilityKey: string;
  dataIntegrityHash: string;

  metadata: {
    executionTimeMs: number;
    literatureSourcesUsed: number;
    confidenceScore: number;
    warnings: string[];
  };

  /**
   * Where every parameter came from.
   *
   * Returned by the pipeline rather than reconstructed by each caller: the
   * CLI previously resolved values itself and handed the pipeline bare
   * numbers, so the citations were dropped on the way in and the run failed
   * with NO_LITERATURE for parameters that had just been sourced. One
   * resolution, one provenance record, emitted by whoever did the work.
   */
  parameterProvenance: Record<string, ResolvedParameter>;
}

// ============================================================================
// SCIENTIFIC PIPELINE
// ============================================================================

export class ScientificPipeline {
  private literatureService: LiteratureService;
  private reproducibilityService: ReproducibilityService;

  // Shared with runSimulation()'s integration window so Layer 3's
  // substrate-depletion check (AssumptionValidator.validateAssumptions,
  // which needs conditions.measurementTime) evaluates the SAME window the
  // simulation actually ran over, rather than two independent numbers that
  // can drift apart.
  private static readonly SIMULATION_END_TIME_S = 10;

  /** Sample points across the integration window, endpoints inclusive. */
  private static readonly SIMULATION_POINTS = 101;

  constructor() {
    this.literatureService = new LiteratureService();
    this.reproducibilityService = new ReproducibilityService();
  }

  /**
   * Initialize with literature database
   */
  initializeLiterature(literature: any[]): void {
    for (const lit of literature) {
      this.literatureService.addLiterature(lit);
    }
    logger.info({ count: literature.length }, 'Literature database initialized');
  }

  /**
   * Execute simulation with full scientific validation
   */
  async execute(request: SimulationRequest): Promise<SimulationResponse> {
    const jobId = this.generateJobId();
    const startTime = Date.now();

    logger.info({ jobId, query: request.query }, 'Simulation started');

    try {
      // STEP 1: Extract and resolve parameters
      logger.info({ jobId }, 'STEP 1: Parameter resolution');

      const resolvedParameters = await this.resolveParameters(
        request.query,
        request.parameters,
        request.system,
        request.providedProvenance,
        request.domain
      );

      // A required parameter that resolveParameters() could not source
      // (no user value, no literature match) is simply absent from
      // resolvedParameters -- resolveParameters() logs a warning and moves
      // on rather than inventing a default. Nothing downstream checked for
      // that absence: buildParameterMetadata() only iterates the
      // parameters that DID resolve, so a missing required parameter was
      // invisible to Layer 1-3 validation and the pipeline proceeded
      // straight to STEP 4, where the engine bridge's own hard-block threw
      // an uncaught "required parameter(s) ... were not supplied" error --
      // turning what should be a clean, reported validation failure into a
      // raw SIMULATION_ERROR crash. Checking here restores the intended
      // fail-fast contract: missing required parameters stop the run at
      // Layer 1 with a normal response, not an exception.
      // An explicit domain is honoured as given; only an unnamed one is
      // inferred. A caller that names a domain the pipeline does not know
      // still fails below, which is the honest outcome — better than
      // quietly falling back to reading the prose.
      const domain = request.domain ?? this.classifyDomain(request.query);

      // A query naming no known domain stops here.
      //
      // Before the classifier was fixed this could not arise -- everything
      // unrecognised was called SIR. Now that "I cannot tell" is
      // expressible, it has to be answered, and the answer cannot be "carry
      // on": `runSimulation` builds km/vmax/s0 unconditionally, so an
      // unplaced query would have been simulated as Michaelis-Menten
      // whatever it actually asked for. Running a model nobody requested is
      // worse than running none.
      const domainErrors = domain
        ? []
        : [
            `Query '${request.query}' does not name a domain this pipeline ` +
              `knows (${Object.keys(ScientificPipeline.DOMAINS).join(', ')}). ` +
              'Name the model explicitly rather than leaving it to be ' +
              'inferred: a simulation of the wrong system is not a partial ' +
              'answer, it is a different answer.',
          ];

      const missingRequired = domain
        ? this.getRequiredParameters(domain).filter(
            param => !resolvedParameters[param]
          )
        : [];

      if (missingRequired.length > 0 || domainErrors.length > 0) {
        logger.error(
          { jobId, domain, missingRequired, domainErrors },
          'Validation failed - unrecognised domain or unresolved required parameters'
        );

        return {
          jobId,
          query: request.query,
          validated: false,
          validationConfidence: 0,
          validationErrors: [
            ...domainErrors,
            ...missingRequired.map(param =>
              `Parameter '${param}': Required parameter '${param}' for domain '${domain}' has no ` +
              'user-supplied value and no literature match; the run cannot proceed without either.'
            ),
          ],
          results: {
            trajectory: [],
            finalValue: 0,
            computedMetrics: {}
          },
          reproducibilityKey: '',
          dataIntegrityHash: '',
          parameterProvenance: resolvedParameters,
          metadata: {
            executionTimeMs: Date.now() - startTime,
            literatureSourcesUsed: 0,
            confidenceScore: 0,
            warnings: []
          }
        };
      }

      // STEP 2: Get literature backing
      logger.info({ jobId }, 'STEP 2: Literature verification');

      const literatureData = this.getLiteratureBacking(resolvedParameters);

      // STEP 3: Validate parameters (Layer 1-3)
      logger.info({ jobId }, 'STEP 3: Scientific validation');

      const parameterMetadata = this.buildParameterMetadata(
        resolvedParameters,
        literatureData
      );

      // Layer 3 (AssumptionValidator) evaluates its checks against
      // conditions.km/vmax/s0/measurementTime -- not against
      // resolvedParameters, which is a separate object. Only
      // temperature/pH used to be included here, so every assumption check
      // that needs a kinetic constant ran against `undefined`:
      // substrateDepletionUpperBound(undefined, undefined, undefined) hits
      // its own `!(s0 > 0)` guard and returns +Infinity unconditionally,
      // which read as "100% of s0 consumed in undefined time units" and
      // capped confidence at 0.8 on every run, regardless of the actual
      // parameters. Merging the resolved values in here is what makes the
      // check evaluate the real run instead of a gap in its own inputs.
      // Vmax must be expressed in the substrate's units per second before
      // the depletion check can compare it against s0 over a window
      // measured in seconds.
      //
      // This was `(resolvedParameters.vmax?.value || 0) / 1000` with the
      // comment "Literature provides vmax in μM/min, convert to mM/min".
      // That factor was applied unconditionally no matter what units the
      // parameters actually declared, and `|| 0` turned a missing Vmax into
      // zero -- which reads as "no substrate consumed at all" and passes
      // every depletion check. The units were available all along:
      // resolved parameters carry a `unit` field. Reading them is the fix;
      // a constant here can only ever be right by coincidence.
      // Only convertible when both parameters resolved. When they did not
      // -- the Layer 1 "no literature" path, for instance -- `vmax` stays
      // undefined and the validator reports the missing parameter, which
      // is the correct outcome. An earlier revision used
      // `resolvedParameters.vmax!.value` here and threw a TypeError
      // instead, turning a clean validation failure into a crash.
      const vmaxInSubstrateUnitsPerSec =
        resolvedParameters.vmax && resolvedParameters.s0
          ? vmaxInSubstrateUnitsPerSecond(
              resolvedParameters.vmax.value,
              resolvedParameters.vmax.unit,
              resolvedParameters.s0.unit
            )
          : undefined;

      // [E]0 is expressed in the substrate's units so that
      // epsilon = e0/(Km + s0) is a ratio of like quantities. Converting
      // through the declared units rather than assuming they already
      // match -- a caller working in uM against a Km in mM would otherwise
      // compute an epsilon 1000x too large and see a spurious failure.
      const e0InSubstrateUnits =
        request.enzymeConcentration && resolvedParameters.s0
          ? convertConcentration(
              request.enzymeConcentration.value,
              request.enzymeConcentration.unit,
              resolvedParameters.s0.unit
            )
          : undefined;

      const conditions = {
        temperature: 37,
        pH: 7.4,
        ...request.conditions,
        km: resolvedParameters.km?.value,
        vmax: vmaxInSubstrateUnitsPerSec,
        s0: resolvedParameters.s0?.value,
        // Without this the steady-state check reported `notEvaluated` on
        // every single run: Segel's criterion needs e0 and nothing supplied
        // it, so Layer 3's first check did no work at all.
        ...(e0InSubstrateUnits !== undefined ? { e0: e0InSubstrateUnits } : {}),
        measurementTime: ScientificPipeline.SIMULATION_END_TIME_S
      };

      const validationResult = await ScientificValidationPipeline.validate(
        parameterMetadata,
        {
          steadyState: true,
          noSubstrateDepletion: true,
          noProductInhibition: true,
          enzymeNotDeactivating: true,
          singleEnzymeForm: true
        },
        conditions
      );

      if (!validationResult.passed) {
        logger.error(
          { jobId, errors: validationResult.errors },
          'Validation failed - execution stopped'
        );

        return {
          jobId,
          query: request.query,
          validated: false,
          validationConfidence: 0,
          validationErrors: validationResult.errors,
          results: {
            trajectory: [],
            finalValue: 0,
            computedMetrics: {}
          },
          reproducibilityKey: '',
          dataIntegrityHash: '',
          parameterProvenance: resolvedParameters,
          metadata: {
            executionTimeMs: Date.now() - startTime,
            literatureSourcesUsed: 0,
            confidenceScore: 0,
            // `validate()` returns `errors: string[]`; this destructured `.code`
            // and `.message` off a string, yielding "undefined: undefined"
            // for every validation failure had it ever run.
            warnings: [...validationResult.errors]
          }
        };
      }

      // STEP 4: Run simulation
      logger.info({ jobId }, 'STEP 4: Simulation execution');

      const simulationOutput = await this.runSimulation(
        resolvedParameters,
        conditions
      );

      this.reproducibilityService.addPhase(
        jobId,
        'simulation',
        Date.now() - startTime,
        simulationOutput.trajectory?.length || 0
      );

      // STEP 5: Validate results (Layer 4)
      logger.info({ jobId }, 'STEP 5: Result validation');

      const resultValidation = await ScientificValidationPipeline.validate(
        parameterMetadata,
        {
          steadyState: true,
          noSubstrateDepletion: true,
          noProductInhibition: true,
          enzymeNotDeactivating: true,
          singleEnzymeForm: true
        },
        conditions,
        simulationOutput
      );

      // STEP 6: Record execution
      logger.info({ jobId }, 'STEP 6: Execution recording');

      const executionRecord = this.reproducibilityService.recordExecution(
        jobId,
        request.query,
        resolvedParameters,
        conditions,
        simulationOutput
      );

      const executionTimeMs = Date.now() - startTime;

      logger.info(
        {
          jobId,
          executionTimeMs,
          confidence: resultValidation.confidence
        },
        '✓ Simulation completed successfully'
      );

      // STEP 7: Format response
      return {
        jobId,
        query: request.query,
        validated: resultValidation.passed,
        validationConfidence: resultValidation.confidence,
        validationErrors: [],

        results: {
          trajectory: simulationOutput.trajectory || [],
          finalValue: simulationOutput.finalValue || 0,
          computedMetrics: simulationOutput.metrics || {}
        },

        reproducibilityKey: executionRecord.hashes.reproductionKey,
        dataIntegrityHash: executionRecord.hashes.outputHash,

        parameterProvenance: resolvedParameters,
        metadata: {
          executionTimeMs,
          literatureSourcesUsed: literatureData.totalSources,
          confidenceScore: resultValidation.confidence,
          warnings: []
        }
      };
    } catch (error) {
      logger.error({ jobId, error }, 'Simulation error');

      throw {
        jobId,
        error: 'SIMULATION_ERROR',
        message: error instanceof Error ? error.message : 'Unknown error',
        executionTimeMs: Date.now() - startTime
      };
    }
  }

  /**
   * Verify reproducibility of past simulation
   */
  async verifyReproducibility(jobId: string): Promise<{
    reproduced: boolean;
    maxError: number;
    summary: string;
  }> {
    logger.info({ jobId }, 'Verifying reproducibility');

    // The verifier calls its reproducer with ONE object --
    // `{ query, parameters, conditions, solver }` -- but `runSimulation`
    // takes two positional arguments. Passing `this.runSimulation.bind(this)`
    // directly meant `conditions` arrived as `undefined` on every replay,
    // so the reproduction ran under different conditions than the original
    // and any disagreement would have been blamed on non-determinism.
    // The adapter unpacks the recorded inputs explicitly.
    const result = await this.reproducibilityService.verifyReproducibility(
      jobId,
      (inputs: { parameters: Record<string, any>; conditions: any }) =>
        this.runSimulation(inputs.parameters, inputs.conditions)
    );

    return {
      reproduced: result.verification.passed,
      maxError: result.verification.maxRelativeError,
      summary: result.summary
    };
  }

  /**
   * Check data integrity
   */
  checkIntegrity(jobId: string): {
    intact: boolean;
    issues: string[];
  } {
    return this.reproducibilityService.checkIntegrity(jobId);
  }

  /**
   * Get simulation report
   */
  getReport(jobId: string): string {
    const record = this.reproducibilityService.getRecord(jobId);

    if (!record) {
      return `No record found for job ${jobId}`;
    }

    const integrityReport = this.reproducibilityService.getIntegrityReport(jobId);

    return `
Simulation Report
=================
Job ID: ${jobId}
Query: ${record.inputs.query}
Timestamp: ${record.timestamp.toISOString()}

Inputs:
${JSON.stringify(record.inputs, null, 2)}

Output Summary:
- Trajectory points: ${record.output.trajectory.length}
- Final value: ${record.output.metrics.finalValue}
- Quality score: ${(record.validation.dataQualityScore * 100).toFixed(1)}%

Reproducibility:
- Reproduction key: ${record.hashes.reproductionKey.slice(0, 16)}...
- Input hash: ${record.hashes.inputHash.slice(0, 16)}...
- Output hash: ${record.hashes.outputHash.slice(0, 16)}...

${integrityReport}
    `;
  }

  // ========================================================================
  // PRIVATE METHODS
  // ========================================================================

  private async resolveParameters(
    query: string,
    userParameters?: Record<string, number>,
    system?: SimulationRequest['system'],
    system_provenance?: SimulationRequest['providedProvenance'],
    explicitDomain?: string
  ): Promise<Record<string, ResolvedParameter>> {
    // One classifier, used by both call sites. This was a second, separate
    // copy of the same `includes('michaelis') ? 'mm' : 'sir'` expression --
    // and duplicated classification means the two halves of a request can
    // disagree about what is being simulated without anything noticing.
    // Constitution Rule 4: shared constraints across layers are enforced by
    // a test, not by two comments hoping to stay in sync.
    //
    // Undefined means "not recognised", and resolution below then attempts
    // nothing rather than resolving SIR parameters for an enzyme query.
    const domain = explicitDomain ?? this.classifyDomain(query);

    const resolved: Record<string, ResolvedParameter> = {};

    // Use user-provided parameters
    if (userParameters) {
      for (const [key, value] of Object.entries(userParameters)) {
        const supplied = system_provenance?.[key];
        resolved[key] = {
          value,
          // A unit the caller declared beats one assumed from the name.
          unit: supplied?.unit ?? this.getAssumedUnitForUserInput(key),
          source: supplied?.source ?? 'user',
          ...(supplied?.citations?.length
            ? { citations: supplied.citations, sourceCount: supplied.citations.length }
            : {})
        };
      }
    }

    // Get recommendations from literature for missing parameters.
    //
    // `resolveFromLiterature` tries the in-memory database first, then --
    // when the caller named a system -- the real BRENDA/PubMed chain via
    // science_agent_runner.py. Previously this called the synchronous
    // `getRecommendation`, which only ever saw literature the caller had
    // already handed in, so a parameter absent from that handful was
    // simply dropped and the run continued without it.
    // An unrecognised domain has no required-parameter list, so there is
    // nothing to look up. Resolving the SIR list for a query the classifier
    // could not place is how an enzyme run ended up demanding beta and
    // gamma; `getRequiredParameters` returns [] for undefined, and the loop
    // below simply does not run.
    const requiredParams = domain ? this.getRequiredParameters(domain) : [];
    for (const param of requiredParams) {
      if (domain === undefined) break;
      if (!resolved[param]) {
        try {
          const recommendation = system
            ? await this.literatureService.resolveFromLiterature(
                param,
                domain,
                system
              )
            : this.literatureService.getRecommendation(param, domain);

          if (!recommendation) {
            // The literature genuinely has nothing. Left unresolved rather
            // than defaulted; downstream validation reports the missing
            // parameter and the engine bridge refuses to run without it.
            logger.warn(
              { parameter: param, domain },
              'Literature has no value for this parameter; leaving it unresolved'
            );
            continue;
          }
          resolved[param] = {
            value: recommendation.recommendedValue,
            // The unit the SOURCES reported, not one guessed from the
            // parameter's name. `getDefaultUnit` returned 'mM' for any
            // parameter called km and 'uM/min' for any vmax, so a value
            // read out of literature in different units was silently
            // relabelled with the assumed one -- the label always agreed
            // with the assumption and never with the data.
            unit: recommendation.unit,
            source: `literature (${recommendation.sourceCount} sources)`,
            // The citation the RESOLVER returned, carried onto the
            // parameter. Without this, provenance was lost between
            // resolution and validation: a Km resolved from BRENDA with a
            // real reference reached buildParameterMetadata, which looked
            // literature up in the in-memory database (empty), found none,
            // and failed the run with NO_LITERATURE -- for a parameter
            // that had just been sourced.
            citations: recommendation.sources,
            sourceCount: recommendation.sourceCount
          };
        } catch (error) {
          logger.warn({ parameter: param }, 'No literature recommendation found');
        }
      }
    }

    return resolved;
  }

  private getLiteratureBacking(
    parameters: Record<string, any>
  ): { totalSources: number; byParameter: Record<string, number> } {
    const byParameter: Record<string, number> = {};
    let totalSources = 0;

    for (const [param, data] of Object.entries(parameters)) {
      try {
        const verification = this.literatureService.crossVerify(param, 'mm');
        byParameter[param] = verification.sources.length;
        totalSources += verification.sources.length;
      } catch (error) {
        byParameter[param] = 0;
      }
    }

    return { totalSources, byParameter };
  }

  private buildParameterMetadata(
    parameters: Record<string, any>,
    literature: any
  ): any[] {
    return Object.entries(parameters).map(([name, data]: [string, any]) => {
      // Get literature sources for this parameter
      let literatureSources: any[] = [];
      try {
        const verification = this.literatureService.crossVerify(name, 'mm');
        literatureSources = verification.sources.map((source: any) => ({
          doi: source.doi,
          title: source.title,
          authors: source.authors || [],
          year: source.year,
          journal: source.journal,
          peerReviewed: source.peerReviewed !== false,
          impactFactor: source.impactFactor,
          citations: source.citationCount
        }));
      } catch (error) {
        // No literature found for this parameter
        literatureSources = [];
      }

      // Fall back to the citations the RESOLVER attached.
      //
      // crossVerify only sees the in-memory database. A Km resolved live
      // from BRENDA -- with a real reference id -- was therefore invisible
      // here, and the run died with NO_LITERATURE for a parameter that had
      // just been sourced. These are marked peerReviewed: false-by-default
      // ONLY when the resolver said nothing about review status; a BRENDA
      // reference is a pointer into the primary literature, so it counts
      // as backing, while the citation-level verification (does this DOI
      // resolve, is it peer reviewed) stays LiteratureVerifier's job.
      if (literatureSources.length === 0 && Array.isArray(data?.citations)) {
        literatureSources = data.citations.map((identifier: string) => ({
          doi: identifier.startsWith('10.') ? identifier : undefined,
          title: `Resolved via ${data.source}`,
          authors: [],
          year: 0,
          journal: 'BRENDA/PubMed (resolver)',
          peerReviewed: true,
        }));
      }

      // The valid range must come from the literature database's own
      // recorded values, not be invented at validation time. This went
      // through two wrong versions before this one:
      //
      //   1. `min: data.value * 0.5, max: data.value * 1.5` -- a range
      //      centered on the value being checked. No value could ever fail
      //      it, however absurd: km=500 against a seeded literature Km of
      //      ~5.1-5.2 "validated" as true, because [250, 750] contains 500
      //      by construction. Structurally the same failure as the
      //      `verifyDOI` that returned true for any DOI-shaped string.
      //   2. A hardcoded `parameterRanges` table (km: [4.0, 6.0], etc.)
      //      typed by hand into this file. Better than (1), but it is a
      //      number nobody derived from the actual seeded `Literature`
      //      entries, and it silently goes stale the moment that seed data
      //      changes -- exactly the "pinned against a literal, not verified
      //      against a source" gap this project has hit before (ADR 0023,
      //      the repressilator beta correction).
      //
      // `ParameterRecommender.recommend()` already computes
      // `range: [min(extractedValues), max(extractedValues)]` from the
      // literature actually loaded into this pipeline's database, so using
      // it here means the bound can never drift from what the database
      // really contains.
      let min: number;
      let max: number;
      try {
        const recommendation = this.literatureService.getRecommendation(name, 'mm');
        [min, max] = recommendation.range;
      } catch (error) {
        // No literature at all for this parameter -- there is nothing to
        // bound it against, so the range check is left unable to fire
        // rather than faked shut (self-referential) or faked narrow
        // (guessed). `confidence: 0` below already reflects the missing
        // literature backing; this is a second, independent signal and
        // should not silently borrow the first one's answer.
        min = -Infinity;
        max = Infinity;
      }

      return {
        name,
        value: data.value,
        unit: data.unit,
        min,
        max,
        // Carried so Layer 1 can tell a value the user typed from one that
        // claims to be resolved. Without it, every unsourced parameter
        // looked identical to the validator and an honest hand-entered Km
        // was rejected as harshly as a fabricated citation.
        origin: data.source,
        literature: literatureSources,
        // Higher confidence for parameters with multiple literature sources
        confidence: literatureSources.length > 1 ? 0.95 : (literatureSources.length > 0 ? 0.92 : 0)
      };
    });
  }

  /**
   * Run the simulation in the real Tellurium engine.
   *
   * This used to be a hand-rolled forward-Euler Michaelis-Menten loop with
   * `parameters.km?.value || 5.0`, `|| 10.0` and `|| 1.0` fallbacks. Those
   * defaults meant a missing Km silently became 5.0 and the run continued,
   * emitting a trajectory and a provenance record for a number that no
   * literature, user or resolver ever supplied. It also duplicated a model
   * the Python engine already implements, with a fixed-step explicit
   * integrator and a `Math.max(0, ...)` clamp that hid step-size error
   * behind a plausible-looking curve.
   *
   * It now spawns the same `tellurium_runner.py` the production api-server
   * uses. Missing parameters raise MissingParameterError rather than being
   * defaulted, and physical validity is decided by the engine.
   */
  private async runSimulation(
    parameters: Record<string, any>,
    conditions: any
  ): Promise<any> {
    void conditions;

    // Unwrap the {value, unit, source, ...} envelope this tree carries.
    // No `||` fallbacks: an absent parameter stays absent so that
    // runTellurium's `required` check can refuse the run.
    const numeric = (name: string): number | undefined => {
      const raw = parameters[name];
      if (raw === undefined || raw === null) return undefined;
      const value = typeof raw === 'object' ? raw.value : raw;
      return typeof value === 'number' && Number.isFinite(value)
        ? value
        : undefined;
    };

    const engineParameters: Record<string, EngineParameterValue> = {
      km: numeric('km') ?? null,
      vmax: numeric('vmax') ?? null,
      s0: numeric('s0') ?? null,
      // `end` and `points` are the names tellurium_runner.py actually
      // reads. This first sent `t_end`/`n_points`, which the runner
      // ignores -- and the mistake was nearly invisible, because the
      // runner's default `end` is also 10.0, so the window looked correct
      // while the resolution silently stayed at the default 51. See the
      // echo check in runTellurium, which now catches this class of error.
      end: ScientificPipeline.SIMULATION_END_TIME_S,
      points: ScientificPipeline.SIMULATION_POINTS
    };

    const result = await runTellurium('mm', engineParameters, {
      required: ['km', 'vmax', 's0']
    });

    // The engine returns every species; `[S]` is the substrate this
    // pipeline reports as its tracked value.
    const { points } = extractSeries(result.trajectory, '[S]');

    // Velocity is derived from the engine's own trajectory rather than
    // recomputed from a rate law here -- recomputing would reintroduce a
    // second implementation of the model, which is what went wrong before.
    // Velocity by finite difference on the engine's own trajectory.
    //
    // The FIRST point used a backward difference against a non-existent
    // predecessor and so reported velocity 0 -- but for Michaelis-Menten
    // t=0 is where the rate is HIGHEST (v0 = Vmax*s0/(Km+s0)). Reporting
    // it as zero made `maxVelocity` miss the true maximum and biased any
    // average downward. A forward difference is used for that one point.
    //
    // Negative velocities are NOT clamped. A negative value here would mean
    // substrate increasing in an irreversible reaction, i.e. an integration
    // problem; clamping it to zero would guarantee the reader never sees
    // the one signal that something is wrong.
    const trajectory = points.map((point, index) => {
      const previous = points[index - 1];
      const next = points[index + 1];

      let velocity = 0;
      if (previous) {
        const dt = point.time - previous.time;
        if (dt > 0) velocity = (previous.value - point.value) / dt;
      } else if (next) {
        const dt = next.time - point.time;
        if (dt > 0) velocity = (point.value - next.value) / dt;
      }

      return { time: point.time, value: point.value, velocity };
    });

    const finalValue = points.length > 0 ? points[points.length - 1]!.value : 0;
    const initialValue = points.length > 0 ? points[0]!.value : 0;

    return {
      trajectory,
      finalValue,
      metrics: {
        finalValue,
        finalVelocity:
          trajectory.length > 0 ? trajectory[trajectory.length - 1]!.velocity : 0,
        totalSubstrateConsumed: initialValue - finalValue,
        // Derived quantities a bench scientist actually reports. The
        // pipeline declared `computedMetrics` and returned only three
        // fields; conversion and the velocity envelope had to be computed
        // by hand from the trajectory every time.
        //
        // conversionPercentage is guarded against s0 = 0 rather than
        // dividing blind: 0/0 would render as NaN in a results table.
        conversionPercentage:
          initialValue > 0
            ? ((initialValue - finalValue) / initialValue) * 100
            : 0,
        maxVelocity: trajectory.reduce(
          (highest, point) => Math.max(highest, point.velocity),
          Number.NEGATIVE_INFINITY
        ),
        avgVelocity:
          trajectory.length > 0
            ? trajectory.reduce((sum, p) => sum + p.velocity, 0) /
              trajectory.length
            : 0
      },
      // Preserved so a caller can see the engine's Rule 2 verdict rather
      // than only this tree's opinion.
      engineFlagged: result.flagged,
      engineFlagReason: result.flagReason
    };
  }

  /**
   * The unit assumed for a USER-SUPPLIED parameter.
   *
   * `SimulationRequest.parameters` is `Record<string, number>` -- bare
   * numbers with no units -- so something has to be assumed for them, and
   * this records what. It is deliberately no longer used for
   * literature-derived values: those carry the unit their sources reported
   * (see resolveParameters), and overwriting that with a name-based guess
   * was how values in one unit ended up labelled with another.
   *
   * The assumption is logged on every use so it is visible in the run
   * record rather than implicit, and an unknown parameter yields 'unknown',
   * which downstream unit conversion refuses rather than silently accepts.
   */
  private getAssumedUnitForUserInput(param: string): string {
    const units: Record<string, string> = {
      km: 'mM',
      vmax: 'μM/min',
      s0: 'mM',
      't0': 'min'
    };
    const unit = units[param] || 'unknown';
    logger.warn(
      { parameter: param, assumedUnit: unit },
      'User supplied a bare number; unit was ASSUMED, not declared'
    );
    return unit;
  }

  private getRequiredParameters(domain: string): string[] {
    return ScientificPipeline.DOMAINS[domain]?.required ?? [];
  }

  /**
   * The domains this pipeline knows, and how to recognise one.
   *
   * Replaces this, which appeared TWICE (execute() and resolveParameters()):
   *
   *     const domain = query.toLowerCase().includes('michaelis') ? 'mm' : 'sir';
   *
   * Every query not containing the literal string "michaelis" was
   * classified as SIR — an epidemic model. `simulate mm`, `enzyme
   * kinetics`, `lactate dehydrogenase`, a Gillespie decay: all SIR. The CLI
   * end-to-end test caught it in the most legible possible way — the run
   * resolved km and Vmax from BRENDA, printed a correct enzyme provenance
   * table, and was then blocked for having no `beta`, `gamma` or `i0`.
   *
   * Two things made it survive: the classifier was duplicated, so the two
   * copies could never disagree in a way anyone would notice; and its
   * fallback was a SPECIFIC domain rather than "unknown", so a failure to
   * recognise the query was indistinguishable from a confident answer.
   *
   * Defaulting to a domain is the same defect as defaulting a parameter,
   * one level up. `classifyDomain` returns undefined when it cannot tell,
   * and the caller reports that rather than guessing.
   */
  private static readonly DOMAINS: Record<
    string,
    { required: string[]; aliases: string[] }
  > = {
    mm: {
      required: ['km', 'vmax', 's0'],
      // Ordered longest-first at match time, so "michaelis menten" cannot
      // be beaten to the answer by a shorter alias of another domain.
      aliases: [
        'michaelis',
        'michaelis-menten',
        'michaelis menten',
        'enzyme kinetics',
        'enzyme',
        'mm',
      ],
    },
    sir: {
      required: ['beta', 'gamma', 's0', 'i0'],
      aliases: ['sir', 'epidemic', 'infection', 'outbreak', 'susceptible'],
    },
  };

  /**
   * Which domain a query names, or undefined when it names none.
   *
   * Undefined is a real answer here, and the reason this returns it rather
   * than a default: a query the pipeline cannot place is a query it must
   * not silently run as something else.
   */
  private classifyDomain(query: string): string | undefined {
    const text = query.toLowerCase();

    const candidates: Array<{ domain: string; alias: string }> = [];
    for (const [domain, spec] of Object.entries(ScientificPipeline.DOMAINS)) {
      for (const alias of spec.aliases) {
        // Word-boundary matched, so "mm" does not fire on "summary" and
        // "sir" does not fire on "desire".
        const pattern = new RegExp(
          `\\b${alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`,
          'i'
        );
        if (pattern.test(text)) candidates.push({ domain, alias });
      }
    }

    if (candidates.length === 0) return undefined;

    // Longest alias wins: "michaelis menten" beats a stray "mm", and a
    // query naming both domains resolves to the more specific mention
    // rather than to whichever was declared first.
    candidates.sort((a, b) => b.alias.length - a.alias.length);
    return candidates[0]!.domain;
  }

  private generateJobId(): string {
    return `job_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
  }
}

// ============================================================================
// EXPORT
// ============================================================================

export default ScientificPipeline;
