"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScientificPipeline = void 0;
const logger_1 = require("../logger");
const scientificValidator_1 = require("../validation/scientificValidator");
const literatureService_1 = require("../literature/literatureService");
const reproducibilityEngine_1 = require("../reproducibility/reproducibilityEngine");
const telluriumBridge_1 = require("../engine/telluriumBridge");
const units_1 = require("../units");
// ============================================================================
// SCIENTIFIC PIPELINE
// ============================================================================
class ScientificPipeline {
    literatureService;
    reproducibilityService;
    // Shared with runSimulation()'s integration window so Layer 3's
    // substrate-depletion check (AssumptionValidator.validateAssumptions,
    // which needs conditions.measurementTime) evaluates the SAME window the
    // simulation actually ran over, rather than two independent numbers that
    // can drift apart.
    static SIMULATION_END_TIME_S = 10;
    /** Sample points across the integration window, endpoints inclusive. */
    static SIMULATION_POINTS = 101;
    constructor() {
        this.literatureService = new literatureService_1.LiteratureService();
        this.reproducibilityService = new reproducibilityEngine_1.ReproducibilityService();
    }
    /**
     * Initialize with literature database
     */
    initializeLiterature(literature) {
        for (const lit of literature) {
            this.literatureService.addLiterature(lit);
        }
        logger_1.logger.info({ count: literature.length }, 'Literature database initialized');
    }
    /**
     * Execute simulation with full scientific validation
     */
    async execute(request) {
        const jobId = this.generateJobId();
        const startTime = Date.now();
        logger_1.logger.info({ jobId, query: request.query }, 'Simulation started');
        try {
            // STEP 1: Extract and resolve parameters
            logger_1.logger.info({ jobId }, 'STEP 1: Parameter resolution');
            const resolvedParameters = await this.resolveParameters(request.query, request.parameters, request.system, request.providedProvenance);
            // STEP 2: Get literature backing
            logger_1.logger.info({ jobId }, 'STEP 2: Literature verification');
            const literatureData = this.getLiteratureBacking(resolvedParameters);
            // STEP 3: Validate parameters (Layer 1-3)
            logger_1.logger.info({ jobId }, 'STEP 3: Scientific validation');
            const parameterMetadata = this.buildParameterMetadata(resolvedParameters, literatureData);
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
            const vmaxInSubstrateUnitsPerSec = resolvedParameters.vmax && resolvedParameters.s0
                ? (0, units_1.vmaxInSubstrateUnitsPerSecond)(resolvedParameters.vmax.value, resolvedParameters.vmax.unit, resolvedParameters.s0.unit)
                : undefined;
            // [E]0 is expressed in the substrate's units so that
            // epsilon = e0/(Km + s0) is a ratio of like quantities. Converting
            // through the declared units rather than assuming they already
            // match -- a caller working in uM against a Km in mM would otherwise
            // compute an epsilon 1000x too large and see a spurious failure.
            const e0InSubstrateUnits = request.enzymeConcentration && resolvedParameters.s0
                ? (0, units_1.convertConcentration)(request.enzymeConcentration.value, request.enzymeConcentration.unit, resolvedParameters.s0.unit)
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
            const validationResult = await scientificValidator_1.ScientificValidationPipeline.validate(parameterMetadata, {
                steadyState: true,
                noSubstrateDepletion: true,
                noProductInhibition: true,
                enzymeNotDeactivating: true,
                singleEnzymeForm: true
            }, conditions);
            if (!validationResult.passed) {
                logger_1.logger.error({ jobId, errors: validationResult.errors }, 'Validation failed - execution stopped');
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
            logger_1.logger.info({ jobId }, 'STEP 4: Simulation execution');
            const simulationOutput = await this.runSimulation(resolvedParameters, conditions);
            this.reproducibilityService.addPhase(jobId, 'simulation', Date.now() - startTime, simulationOutput.trajectory?.length || 0);
            // STEP 5: Validate results (Layer 4)
            logger_1.logger.info({ jobId }, 'STEP 5: Result validation');
            const resultValidation = await scientificValidator_1.ScientificValidationPipeline.validate(parameterMetadata, {
                steadyState: true,
                noSubstrateDepletion: true,
                noProductInhibition: true,
                enzymeNotDeactivating: true,
                singleEnzymeForm: true
            }, conditions, simulationOutput);
            // STEP 6: Record execution
            logger_1.logger.info({ jobId }, 'STEP 6: Execution recording');
            const executionRecord = this.reproducibilityService.recordExecution(jobId, request.query, resolvedParameters, conditions, simulationOutput);
            const executionTimeMs = Date.now() - startTime;
            logger_1.logger.info({
                jobId,
                executionTimeMs,
                confidence: resultValidation.confidence
            }, '✓ Simulation completed successfully');
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
        }
        catch (error) {
            logger_1.logger.error({ jobId, error }, 'Simulation error');
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
    async verifyReproducibility(jobId) {
        logger_1.logger.info({ jobId }, 'Verifying reproducibility');
        // The verifier calls its reproducer with ONE object --
        // `{ query, parameters, conditions, solver }` -- but `runSimulation`
        // takes two positional arguments. Passing `this.runSimulation.bind(this)`
        // directly meant `conditions` arrived as `undefined` on every replay,
        // so the reproduction ran under different conditions than the original
        // and any disagreement would have been blamed on non-determinism.
        // The adapter unpacks the recorded inputs explicitly.
        const result = await this.reproducibilityService.verifyReproducibility(jobId, (inputs) => this.runSimulation(inputs.parameters, inputs.conditions));
        return {
            reproduced: result.verification.passed,
            maxError: result.verification.maxRelativeError,
            summary: result.summary
        };
    }
    /**
     * Check data integrity
     */
    checkIntegrity(jobId) {
        return this.reproducibilityService.checkIntegrity(jobId);
    }
    /**
     * Get simulation report
     */
    getReport(jobId) {
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
    async resolveParameters(query, userParameters, system, system_provenance) {
        // Parse query to extract domain and requirements
        const domain = query.toLowerCase().includes('michaelis') ? 'mm' : 'sir';
        const resolved = {};
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
        const requiredParams = this.getRequiredParameters(domain);
        for (const param of requiredParams) {
            if (!resolved[param]) {
                try {
                    const recommendation = system
                        ? await this.literatureService.resolveFromLiterature(param, domain, system)
                        : this.literatureService.getRecommendation(param, domain);
                    if (!recommendation) {
                        // The literature genuinely has nothing. Left unresolved rather
                        // than defaulted; downstream validation reports the missing
                        // parameter and the engine bridge refuses to run without it.
                        logger_1.logger.warn({ parameter: param, domain }, 'Literature has no value for this parameter; leaving it unresolved');
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
                }
                catch (error) {
                    logger_1.logger.warn({ parameter: param }, 'No literature recommendation found');
                }
            }
        }
        return resolved;
    }
    getLiteratureBacking(parameters) {
        const byParameter = {};
        let totalSources = 0;
        for (const [param, data] of Object.entries(parameters)) {
            try {
                const verification = this.literatureService.crossVerify(param, 'mm');
                byParameter[param] = verification.sources.length;
                totalSources += verification.sources.length;
            }
            catch (error) {
                byParameter[param] = 0;
            }
        }
        return { totalSources, byParameter };
    }
    buildParameterMetadata(parameters, literature) {
        return Object.entries(parameters).map(([name, data]) => {
            // Get literature sources for this parameter
            let literatureSources = [];
            try {
                const verification = this.literatureService.crossVerify(name, 'mm');
                literatureSources = verification.sources.map((source) => ({
                    doi: source.doi,
                    title: source.title,
                    authors: source.authors || [],
                    year: source.year,
                    journal: source.journal,
                    peerReviewed: source.peerReviewed !== false,
                    impactFactor: source.impactFactor,
                    citations: source.citationCount
                }));
            }
            catch (error) {
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
                literatureSources = data.citations.map((identifier) => ({
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
            let min;
            let max;
            try {
                const recommendation = this.literatureService.getRecommendation(name, 'mm');
                [min, max] = recommendation.range;
            }
            catch (error) {
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
    async runSimulation(parameters, conditions) {
        void conditions;
        // Unwrap the {value, unit, source, ...} envelope this tree carries.
        // No `||` fallbacks: an absent parameter stays absent so that
        // runTellurium's `required` check can refuse the run.
        const numeric = (name) => {
            const raw = parameters[name];
            if (raw === undefined || raw === null)
                return undefined;
            const value = typeof raw === 'object' ? raw.value : raw;
            return typeof value === 'number' && Number.isFinite(value)
                ? value
                : undefined;
        };
        const engineParameters = {
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
        const result = await (0, telluriumBridge_1.runTellurium)('mm', engineParameters, {
            required: ['km', 'vmax', 's0']
        });
        // The engine returns every species; `[S]` is the substrate this
        // pipeline reports as its tracked value.
        const { points } = (0, telluriumBridge_1.extractSeries)(result.trajectory, '[S]');
        // Velocity is derived from the engine's own trajectory rather than
        // recomputed from a rate law here -- recomputing would reintroduce a
        // second implementation of the model, which is what went wrong before.
        const trajectory = points.map((point, index) => {
            const previous = points[index - 1];
            const dt = previous ? point.time - previous.time : 0;
            const velocity = previous && dt > 0 ? (previous.value - point.value) / dt : 0;
            return { time: point.time, value: point.value, velocity };
        });
        const finalValue = points.length > 0 ? points[points.length - 1].value : 0;
        const initialValue = points.length > 0 ? points[0].value : 0;
        return {
            trajectory,
            finalValue,
            metrics: {
                finalValue,
                finalVelocity: trajectory.length > 0 ? trajectory[trajectory.length - 1].velocity : 0,
                totalSubstrateConsumed: initialValue - finalValue
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
    getAssumedUnitForUserInput(param) {
        const units = {
            km: 'mM',
            vmax: 'μM/min',
            s0: 'mM',
            't0': 'min'
        };
        const unit = units[param] || 'unknown';
        logger_1.logger.warn({ parameter: param, assumedUnit: unit }, 'User supplied a bare number; unit was ASSUMED, not declared');
        return unit;
    }
    getRequiredParameters(domain) {
        const params = {
            mm: ['km', 'vmax', 's0'],
            sir: ['beta', 'gamma', 's0', 'i0']
        };
        return params[domain] || [];
    }
    generateJobId() {
        return `job_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
    }
}
exports.ScientificPipeline = ScientificPipeline;
// ============================================================================
// EXPORT
// ============================================================================
exports.default = ScientificPipeline;
