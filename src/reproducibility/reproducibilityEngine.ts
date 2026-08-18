/**
 * Reproducibility Engine
 *
 * Ensures every simulation is independently reproducible:
 * - Record complete execution state
 * - Verify outputs are deterministic
 * - Track data integrity
 * - Enable re-execution with identical results
 *
 * PRINCIPLE: EVERY RESULT MUST BE INDEPENDENTLY REPRODUCIBLE
 */

import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { logger } from '../logger';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface ExecutionRecord {
  jobId: string;
  timestamp: Date;

  // Environment
  environment: {
    nodeVersion: string;
    platform: string;
    arch: string;
    memoryAvailable: number;
  };

  gitState: {
    commitHash: string;
    branch: string;
    isDirty: boolean;
  };

  // Input snapshot (complete)
  inputs: {
    query: string;
    parameters: Record<string, {
      value: number;
      unit: string;
      source: string;
      confidence: number;
    }>;
    conditions: Record<string, any>;
  };

  // Solver configuration
  solver: {
    algorithm: string;
    /** Undefined when the run did not record how it was integrated.
     *  `verifyReproducibility` refuses rather than picking a tolerance,
     *  because a comparison calibrated by this file certifies at a
     *  standard nobody chose. */
    absoluteTolerance: number | undefined;
    relativeTolerance: number | undefined;
    randomSeed?: number;
  };

  // Execution trace
  executionTrace: {
    phase: string;
    durationMs: number;
    stepCount?: number;
    warnings?: string[];
  }[];

  // Output
  output: {
    trajectory: Array<{ time: number; value: number }>;
    metrics: Record<string, number>;
  };

  // Reproducibility
  hashes: {
    inputHash: string;
    outputHash: string;
    reproductionKey: string;
  };

  // Validation
  validation: {
    dataQualityScore: number | undefined;
    biologicalPlausibility: string;
    comparisonToLiterature: string;
  };
}

export interface ReproductionAttempt {
  originalJobId: string;
  attemptJobId: string;

  verification: {
    inputHashMatch: boolean;
    outputHashMatch: boolean;
    outputsIdentical: boolean;
    maxRelativeError: number;
    meanRelativeError: number;
    passed: boolean;
  };

  differences?: {
    possibleCauses: string[];
    conclusion: string;
  };

  summary: string;
}

// ============================================================================
// EXECUTION RECORDER
// ============================================================================

export class ExecutionRecorder {
  /**
   * Create execution record with complete snapshot
   */
  static createRecord(
    jobId: string,
    query: string,
    parameters: Record<string, any>,
    conditions: Record<string, any>,
    output: any,
    /** How the run was actually integrated. Omitted -> recorded as
     *  unrecorded, never guessed. */
    solver?: ExecutionRecord['solver']
  ): ExecutionRecord {
    // Hash the representation that is actually STORED on the record, not
    // the raw arguments.
    //
    // This hashed `{ query, parameters, conditions }` with the raw
    // `parameters`, while `inputs.parameters` below stores
    // `serializeParameters(parameters)` -- a different object. Verification
    // recomputes `sha256(JSON.stringify(record.inputs))`, so the two could
    // only agree when serialization happened to be an identity, i.e. when
    // `parameters` was empty. Every record carrying real parameters had a
    // permanently unmatchable input hash, which made `inputHashMatch`
    // false and therefore `passed` false no matter how perfectly the
    // simulation reproduced.
    //
    // Nobody saw it because the numerical half of the check was also
    // broken in the opposite direction (always 0 error, see
    // ReproducibilityVerifier.verify), and no test in this tree had ever
    // been executed -- `npm run verify-all` died at `type-check` before
    // reaching `npm test`.
    const storedInputs = {
      query,
      parameters: this.serializeParameters(parameters),
      conditions
    };
    // Identical hazard on the output side: this hashed the raw `output`
    // argument while `record.output` below stored a rebuilt
    // `{ trajectory, metrics }`. Any extra field on the caller's output --
    // `finalValue`, say, which the pipeline's runSimulation returns --
    // was hashed but not stored, so DataIntegrityChecker.verify()
    // recomputed a different hash and reported "Output data corrupted"
    // for data that was perfectly intact. An integrity checker that cries
    // corruption on every healthy record trains its reader to ignore it.
    const storedOutput = {
      trajectory: output?.trajectory ?? [],
      metrics: output?.metrics ?? {}
    };
    const inputHash = this.sha256(JSON.stringify(storedInputs));
    const outputHash = this.sha256(JSON.stringify(storedOutput));
    // `Date.now()` alone has millisecond resolution, so two records with
    // identical inputs and outputs created inside the same millisecond
    // produced the SAME "unique" reproduction key. That is not theoretical
    // -- the repository's own test creates records in a tight loop and was
    // intermittently failing on it, visibly under `jest --runInBand`.
    //
    // A colliding key silently merges two distinct executions in any store
    // that treats it as an identifier.
    //
    // A process-local counter was tried first and is NOT sufficient: each
    // process starts it at 0, so two workers (jest runs suites in parallel
    // processes; so would any multi-process server) can emit the same
    // counter value in the same millisecond for the same inputs.
    // `crypto.randomUUID` is unique across processes. The timestamp is
    // retained so keys remain roughly ordered by creation.
    const reproductionKey = this.sha256(
      `${inputHash}:${outputHash}:${Date.now()}:${crypto.randomUUID()}`
    );

    return {
      jobId,
      timestamp: new Date(),

      environment: {
        nodeVersion: process.version,
        platform: process.platform,
        arch: process.arch,
        memoryAvailable: process.memoryUsage().heapTotal
      },

      gitState: {
        commitHash: process.env.GIT_COMMIT || 'unknown',
        branch: process.env.GIT_BRANCH || 'unknown',
        isDirty: process.env.GIT_DIRTY === 'true'
      },

      // The very same object that was hashed above. Rebuilding an
      // equivalent-looking literal here is what let the hash and the
      // stored inputs drift apart in the first place.
      inputs: storedInputs,

      // The solver configuration of the run being recorded.
      //
      // This said `RK45` at rtol 1e-6 / atol 1e-8. Terrium integrates with
      // **CVODE** at 1e-10 / 1e-12 (DEFAULT_RELATIVE_TOLERANCE and
      // DEFAULT_ABSOLUTE_TOLERANCE). Every field was wrong, in the record
      // whose entire job is describing how a result was produced.
      //
      // Not merely cosmetic: `verifyReproducibility` reads these tolerances
      // to calibrate its comparison, so a reproduction differing by 1e-7 --
      // ten thousand times looser than the integrator's own accuracy -- was
      // certified FULLY REPRODUCIBLE. The comment there claimed "nothing
      // here is a constant chosen by this file", which was true of that
      // file and false of the system: the constant was chosen here.
      //
      // Unknown rather than invented when the caller does not supply it. A
      // record saying "unrecorded" is useless in a visible way; one saying
      // RK45 is useless in a way that looks like information.
      solver: solver ?? {
        algorithm: 'unrecorded',
        absoluteTolerance: undefined,
        relativeTolerance: undefined,
        randomSeed: undefined
      },

      executionTrace: [],

      // The same object that was hashed above, for the same reason.
      output: storedOutput,

      hashes: {
        inputHash,
        outputHash,
        reproductionKey
      },

      validation: {
        // These were 0.9, 'high' and 'within range' -- constants, rendered
        // by the report as "Quality score: 90.0%".
        //
        // A fabricated assessment presented as a measurement is the worst
        // thing this project can emit, and it contradicted a written
        // decision: ADR 0024 Decision 3 refuses an aggregate quality score
        // because combining Bakker's axes needs a trade-off nobody has
        // measured. One layer refused to produce a number while another
        // invented one.
        //
        // Nothing is assessed here now. The real, per-parameter assessment
        // is the reliability axes, and it travels with the run.
        dataQualityScore: undefined,
        biologicalPlausibility: 'not assessed',
        comparisonToLiterature: 'not assessed'
      }
    };
  }

  /**
   * Add execution phase to trace
   */
  static addPhase(
    record: ExecutionRecord,
    phase: string,
    durationMs: number,
    stepCount?: number,
    warnings?: string[]
  ): void {
    record.executionTrace.push({
      phase,
      durationMs,
      stepCount,
      warnings
    });
  }

  private static serializeParameters(params: Record<string, any>): Record<string, any> {
    return Object.entries(params).reduce((acc, [key, param]) => {
      acc[key] = {
        value: param.value,
        unit: param.unit,
        source: param.source || 'unknown',
        confidence: param.confidence || 1.0
      };
      return acc;
    }, {} as Record<string, any>);
  }

  private static sha256(data: string): string {
    return crypto.createHash('sha256').update(data).digest('hex');
  }
}

// ============================================================================
// REPRODUCIBILITY VERIFIER
// ============================================================================

export class ReproducibilityVerifier {
  /**
   * Verify simulation is reproducible
   */
  static async verify(
    originalRecord: ExecutionRecord,
    reproducer: (inputs: any) => Promise<any>
  ): Promise<ReproductionAttempt> {
    logger.info({ jobId: originalRecord.jobId }, 'Starting reproducibility verification');

    // Re-run with identical inputs
    const reproduced = await reproducer({
      query: originalRecord.inputs.query,
      parameters: originalRecord.inputs.parameters,
      conditions: originalRecord.inputs.conditions,
      solver: originalRecord.solver
    });

    // Compare outputs.
    //
    // This passed `reproducer` -- the FUNCTION -- where the reproduced
    // OUTPUT belongs. Combined with the `|| orig` fallback that used to sit
    // in compareOutputs (see there), every trajectory point compared
    // `orig` against itself, so `maxRelativeError` was always exactly 0.
    // `passed` then reduced to `inputHashMatch`, and the summary always
    // read "✓ FULLY REPRODUCIBLE (max error: 0.00e+0)".
    //
    // A reproducibility verifier that cannot fail is not a weak check, it
    // is an inverted one: it certifies every irreproducible simulation as
    // reproducible. Same defect class as the `verifyDOI` that returned
    // true for any DOI-shaped string.
    // Both tolerances come from the record's own solver configuration, so
    // a run integrated to a tighter tolerance is held to a tighter
    // reproducibility standard automatically. Nothing here is a constant
    // chosen by this file.
    // No fallback. The old `: 1e-6` / `: 1e-8` looked like defensive
    // defaults and were the thing that made this verifier meaningless: a
    // run integrated at 1e-10 was compared at 1e-6, so a reproduction four
    // orders of magnitude off passed.
    //
    // If the record does not say how it was integrated, this cannot say
    // whether it was reproduced. Refusing is the honest third outcome;
    // substituting a tolerance nobody used certifies at a standard nobody
    // chose.
    const relativeTolerance = originalRecord.solver.relativeTolerance;
    const absoluteTolerance = originalRecord.solver.absoluteTolerance;
    const calibrated =
      Number.isFinite(relativeTolerance) && (relativeTolerance as number) > 0
      && Number.isFinite(absoluteTolerance) && (absoluteTolerance as number) > 0;

    if (!calibrated) {
      throw new Error(
        `Cannot verify reproducibility of ${originalRecord.jobId}: the record ` +
        `does not state the solver tolerances it ran at ` +
        `(algorithm=${originalRecord.solver.algorithm}). Comparing against a ` +
        `tolerance this function invented would certify the run at a standard ` +
        `nobody chose.`
      );
    }

    // Past the guard above these are numbers. Bound once so every message
    // below reads the same narrowed values rather than re-asserting.
    const atol = absoluteTolerance as number;
    const rtol = relativeTolerance as number;

    const comparison = this.compareOutputs(
      originalRecord.output,
      reproduced,
      atol,
      rtol
    );

    // Verify hashes
    const inputHashMatch =
      originalRecord.hashes.inputHash ===
      this.sha256(JSON.stringify(originalRecord.inputs));

    // Was `JSON.stringify(reproducer)`, which returns `undefined` for a
    // function, so this hashed the literal string "undefined" and could
    // never match a real output hash.
    const outputHashMatch =
      originalRecord.hashes.outputHash ===
      this.sha256(JSON.stringify(reproduced));

    // `outputHashMatch` was computed and then left out of `passed`, so a
    // byte-level output mismatch could not fail the verification. It is
    // deliberately NOT required for `passed`: bit-identical output is a
    // stronger condition than reproducibility, and legitimate FP
    // reassociation across platforms breaks it while leaving results
    // scientifically identical. It is reported separately so a caller can
    // tell bit-identical from numerically-equivalent.
    // The agreement threshold is the solver's OWN declared relative
    // tolerance, read from the record, not a constant written here. A
    // solver integrating to rtol=1e-6 may legitimately land 1e-6 away on a
    // re-run; demanding tighter agreement than the solver ever promised
    // would report correct reproductions as failures. Equally, hardcoding
    // 1e-6 would silently over-accept a run configured to rtol=1e-10.
    // `<=` because a solver guaranteeing rtol is allowed to reach exactly
    // rtol.
    // <= 1 means every point sat inside `atol + rtol*|original|`.
    const numericallyReproduced = comparison.maxToleranceRatio <= 1;
    const passed = inputHashMatch && numericallyReproduced;

    const summary = passed
      ? `✓ REPRODUCIBLE (max relative error: ${comparison.maxRelativeError.toExponential(2)}${outputHashMatch ? ", output bit-identical" : ""})`
      : !inputHashMatch
        ? "✗ NOT VERIFIABLE: recorded input hash does not match the inputs replayed, so this comparison says nothing about reproducibility"
        : `✗ NOT REPRODUCIBLE (max relative error: ${comparison.maxRelativeError.toExponential(2)} exceeds the solver's declared tolerance (atol ${atol.toExponential(2)}, rtol ${rtol.toExponential(2)}))`;

    logger.info(
      {
        jobId: originalRecord.jobId,
        inputHashMatch,
        outputHashMatch,
        maxError: comparison.maxRelativeError
      },
      summary
    );

    return {
      originalJobId: originalRecord.jobId,
      attemptJobId: `${originalRecord.jobId}-repro-${Date.now()}`,

      verification: {
        inputHashMatch,
        outputHashMatch,
        outputsIdentical: comparison.maxRelativeError === 0,
        maxRelativeError: comparison.maxRelativeError,
        meanRelativeError: comparison.meanRelativeError,
        passed
      },

      // The conclusion here used to be the constant string "Results
      // numerically equivalent within expected precision", emitted for ANY
      // non-zero error -- so a reproduction that disagreed by 400% was
      // reported as equivalent. The conclusion now follows the measurement
      // instead of overriding it.
      differences:
        comparison.maxRelativeError > 0
          ? {
            possibleCauses: numericallyReproduced
              ? [
                'Different floating-point implementations',
                'Compiler optimization differences',
                'Numerical solver variations'
              ]
              : [
                'Unseeded randomness in the model or solver',
                'Adaptive step sizing not pinned by the recorded solver settings',
                'A parameter read from live state rather than the recorded inputs',
                'Genuine non-determinism in the simulation code'
              ],
            conclusion: numericallyReproduced
              ? `Results numerically equivalent within the solver's declared precision (max relative error ${comparison.maxRelativeError.toExponential(2)} within atol ${atol.toExponential(2)} + rtol ${rtol.toExponential(2)})`
              : `Results DIFFER: max relative error ${comparison.maxRelativeError.toExponential(2)} exceeds the solver's declared tolerance (atol ${atol.toExponential(2)}, rtol ${rtol.toExponential(2)}) by ${comparison.maxToleranceRatio.toExponential(2)}x. This is not floating-point noise.`
          }
          : undefined,

      summary
    };
  }

  /**
   * Compare a reproduction against the original trajectory.
   *
   * The pass/fail decision uses the standard mixed absolute-relative
   * tolerance test
   *
   *     |original - reproduced|  <=  atol + rtol * |original|
   *
   * rather than a bare relative comparison. This is the criterion used by
   * SUNDIALS/CVODE's weighted error norm, `scipy.integrate.solve_ivp` and
   * `numpy.allclose`, and it is the one that matches what an ODE solver
   * actually guarantees. Two reasons it matters here:
   *
   *   1. A bare relative test is undefined at 0 and explodes near it, so
   *      trajectories that legitimately decay to zero -- most of them --
   *      fail for values the solver never claimed to resolve. `atol` is
   *      precisely the floor for "smaller than we promised to track".
   *   2. The record stores BOTH `absoluteTolerance` and
   *      `relativeTolerance`; using only the relative one silently
   *      discarded half the solver's declared accuracy contract.
   *
   * `maxToleranceRatio` is that inequality's left side over its right
   * side, so <= 1 means "agrees to within what the solver promised",
   * independent of the trajectory's scale. The raw relative errors are
   * still returned for reporting.
   */
  private static compareOutputs(
    original: { trajectory: Array<{ time: number; value: number }>; metrics?: Record<string, number> },
    reproduced: any,
    absoluteTolerance: number,
    relativeTolerance: number
  ): {
    maxRelativeError: number;
    meanRelativeError: number;
    maxToleranceRatio: number;
  } {
    // An empty original returns Infinity, not 0. There is nothing to
    // compare against, so the honest answer is "cannot be shown
    // reproducible" -- returning 0 declared a perfect match on no evidence
    // and would sail past the `< 1e-6` test in verify().
    if (!original.trajectory || original.trajectory.length === 0) {
      return {
        maxRelativeError: Number.POSITIVE_INFINITY,
        meanRelativeError: Number.POSITIVE_INFINITY,
        maxToleranceRatio: Number.POSITIVE_INFINITY
      };
    }

    const reproducedTrajectory: Array<{ time: number; value: number }> =
      reproduced?.trajectory ?? [];

    // A reproduction of the wrong length is not reproducible, whatever the
    // overlapping points say.
    if (reproducedTrajectory.length !== original.trajectory.length) {
      return {
        maxRelativeError: Number.POSITIVE_INFINITY,
        meanRelativeError: Number.POSITIVE_INFINITY,
        maxToleranceRatio: Number.POSITIVE_INFINITY
      };
    }

    let maxError = 0;
    let sumError = 0;
    let comparedPoints = 0;
    let maxToleranceRatio = 0;

    for (let i = 0; i < original.trajectory.length; i++) {
      const orig = original.trajectory[i]!.value;
      // Was `reproduced?.trajectory?.[i]?.value || orig` -- a missing
      // reproduction point substituted the ORIGINAL value, scoring a
      // perfect match for data that was never produced. `|| ` also
      // swallowed a legitimate reproduced 0. A missing point is now a
      // failure, which is what "not reproducible" means.
      const repro = reproducedTrajectory[i]?.value;

      if (repro === undefined || !Number.isFinite(repro)) {
        return {
          maxRelativeError: Number.POSITIVE_INFINITY,
          meanRelativeError: Number.POSITIVE_INFINITY,
          maxToleranceRatio: Number.POSITIVE_INFINITY
        };
      }

      // The tolerance test itself, applied at every point including
      // orig === 0 -- where a bare relative error is undefined and the
      // original code simply `continue`d, letting a reproduction that
      // returned a large value where the original was exactly 0 pass
      // completely unnoticed. `atol` handles that point correctly.
      const absoluteDifference = Math.abs(orig - repro);
      const allowed = absoluteTolerance + relativeTolerance * Math.abs(orig);
      maxToleranceRatio = Math.max(
        maxToleranceRatio,
        allowed > 0
          ? absoluteDifference / allowed
          : (absoluteDifference === 0 ? 0 : Number.POSITIVE_INFINITY)
      );

      // Reported separately, purely for human-readable output. Relative
      // error is still undefined at zero, so those points contribute their
      // absolute difference instead and are excluded from the relative
      // mean rather than diluting it.
      if (orig === 0) {
        if (repro !== 0) {
          maxError = Math.max(maxError, Math.abs(repro));
          sumError += Math.abs(repro);
          comparedPoints++;
        }
        continue;
      }

      const relError = absoluteDifference / Math.abs(orig);
      maxError = Math.max(maxError, relError);
      sumError += relError;
      comparedPoints++;
    }

    return {
      maxRelativeError: maxError,
      // Divided by the full trajectory length even though zero-valued
      // points were skipped, which diluted the mean toward 0 in proportion
      // to how many points were skipped. Divide by what was compared.
      meanRelativeError: comparedPoints > 0 ? sumError / comparedPoints : 0,
      maxToleranceRatio
    };
  }

  private static sha256(data: string): string {
    return crypto.createHash('sha256').update(data).digest('hex');
  }
}

// ============================================================================
// DATA INTEGRITY CHECKER
// ============================================================================

export class DataIntegrityChecker {
  /**
   * Verify data hasn't been corrupted
   */
  static verify(record: ExecutionRecord): {
    intact: boolean;
    issues: string[];
    warnings: string[];
  } {
    const issues: string[] = [];
    // Findings that are NOT corruption. `createRecord` always initialises
    // `executionTrace: []` and phases are appended later, so treating an
    // empty trace as an integrity violation marked EVERY freshly created
    // record "✗ CORRUPTED" -- and `src/cli/scientificCLI.ts` does
    // `process.exit(result.intact ? 0 : 1)`, so the CLI failed on
    // completely healthy data. An alarm that fires on every record is an
    // alarm its reader learns to ignore, which is worse than no alarm.
    const warnings: string[] = [];

    // Check 1: Input hash
    const computedInputHash = crypto
      .createHash('sha256')
      .update(JSON.stringify(record.inputs))
      .digest('hex');

    if (computedInputHash !== record.hashes.inputHash) {
      issues.push('Input data corrupted - hash mismatch');
    }

    // Check 2: Output hash
    const computedOutputHash = crypto
      .createHash('sha256')
      .update(JSON.stringify(record.output))
      .digest('hex');

    if (computedOutputHash !== record.hashes.outputHash) {
      issues.push('Output data corrupted - hash mismatch');
    }

    // Check 3: Output data quality
    if (record.output.trajectory.some(p => !isFinite(p.value))) {
      issues.push('Output contains invalid values (NaN or Infinity)');
    }

    // Check 4: Execution trace -- completeness, not corruption. See the
    // `warnings` declaration above.
    if (!record.executionTrace || record.executionTrace.length === 0) {
      warnings.push(
        'No execution trace recorded: the run\'s phases were never added, ' +
        'so timing and step counts cannot be audited. This is not data ' +
        'corruption.'
      );
    }

    return {
      // `intact` now answers exactly one question -- was this data
      // corrupted -- so a caller like the CLI can act on it. Completeness
      // findings travel separately in `warnings`.
      intact: issues.length === 0,
      issues,
      warnings
    };
  }

  /**
   * Generate integrity report
   */
  static generateReport(record: ExecutionRecord): string {
    const { intact, issues, warnings } = this.verify(record);

    const status = intact ? '✓ INTACT' : '✗ CORRUPTED';

    return `
Data Integrity Report
=====================
Job: ${record.jobId}
Status: ${status}

Details:
- Input hash: ${record.hashes.inputHash.slice(0, 8)}...
- Output hash: ${record.hashes.outputHash.slice(0, 8)}...
- Reproduction key: ${record.hashes.reproductionKey.slice(0, 8)}...

${issues.length > 0 ? `Issues:\n${issues.map(i => `- ${i}`).join('\n')}` : 'No issues detected'}
${warnings.length > 0 ? `Warnings (not corruption):\n${warnings.map(w => `- ${w}`).join('\n')}` : ''}

Data Quality Score: ${record.validation.dataQualityScore === undefined ? 'not assessed (see the reliability axes, which are per-parameter)' : (record.validation.dataQualityScore * 100).toFixed(1) + '%'}
Biological Plausibility: ${record.validation.biologicalPlausibility}
    `;
  }
}

// ============================================================================
// REPRODUCIBILITY SERVICE (MAIN API)
// ============================================================================

/**
 * Where execution records live between processes.
 *
 * WHY THIS EXISTS
 * ---------------
 * `records` below was a bare in-memory Map, and the CLI is a fresh process
 * per invocation. So `scientific verify <jobId>` and
 * `scientific check-integrity <jobId>` looked up a job in a Map that had just
 * been constructed empty, and threw `Record not found for job <jobId>` — for
 * every job id, always, since the commands existed.
 *
 * `history` meanwhile persists to `~/.terrium/history.json` and lists those
 * same ids happily. Its help text reads: "The run id printed at the end of a
 * simulation is only useful if something can resolve it later; this is that
 * something." So the tool printed an id, listed it, and then denied it
 * existed — the two stores never agreed because only one of them was a store.
 *
 * Neither command could have been caught by a unit test of this class: a test
 * that calls `recordExecution` and then `checkIntegrity` in one process
 * passes, because the Map is populated. The defect only exists ACROSS
 * processes, which is the only way a user ever meets it.
 */
export function recordsDir(): string {
  return path.join(os.homedir(), '.terrium', 'records');
}

export class ReproducibilityService {
  private records: Map<string, ExecutionRecord> = new Map();

  /**
   * Record execution
   */
  recordExecution(
    jobId: string,
    query: string,
    parameters: Record<string, any>,
    conditions: Record<string, any>,
    output: any,
    /** How the run was integrated. Passed straight through: a service that
     *  dropped it would put the record back to "unrecorded" and make
     *  verification impossible, which is exactly the failure this
     *  parameter exists to prevent. */
    solver?: ExecutionRecord['solver']
  ): ExecutionRecord {
    const record = ExecutionRecorder.createRecord(
      jobId,
      query,
      parameters,
      conditions,
      output,
      solver
    );

    this.records.set(jobId, record);
    this.persist(record);
    logger.info({ jobId }, 'Execution recorded');

    return record;
  }

  /**
   * Write the record where a later process can find it.
   *
   * Failure to persist NEVER throws. A simulation that produced a correct
   * result did produce it, and turning an unwritable home directory into a
   * failed run would make the exit code mean two different things. The
   * consequence — that `verify` will not find this job — is logged where an
   * operator can see it, which is the same trade `writeExports` makes.
   */
  private persist(record: ExecutionRecord): void {
    try {
      const dir = recordsDir();
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(
        path.join(dir, `${record.jobId}.json`),
        JSON.stringify(record, null, 2),
        'utf-8'
      );
    } catch (err) {
      logger.warn(
        { jobId: record.jobId, error: err instanceof Error ? err.message : String(err) },
        'Execution record could not be persisted; verify/check-integrity will not find this job'
      );
    }
  }

  /**
   * In-memory first, then disk.
   *
   * The Map is still the fast path within a process, and it is also the only
   * path that sees phases added by `addPhase` after the record was written.
   * Disk is what makes a job id mean something tomorrow.
   *
   * `timestamp` is revived to a Date: JSON.stringify writes it as a string,
   * and every consumer of `ExecutionRecord.timestamp` expects the object.
   * Leaving it a string would give a record that looks loaded and throws on
   * first use, which is worse than not loading it.
   */
  private load(jobId: string): ExecutionRecord | undefined {
    const cached = this.records.get(jobId);
    if (cached) return cached;

    try {
      const file = path.join(recordsDir(), `${jobId}.json`);
      if (!fs.existsSync(file)) return undefined;
      const parsed = JSON.parse(fs.readFileSync(file, 'utf-8')) as ExecutionRecord;
      parsed.timestamp = new Date(parsed.timestamp);
      this.records.set(jobId, parsed);
      return parsed;
    } catch (err) {
      // A corrupt record is NOT a missing one, and must not be reported as
      // "no such job" -- that would send someone looking for a job they ran.
      logger.error(
        { jobId, error: err instanceof Error ? err.message : String(err) },
        'Execution record exists but could not be read'
      );
      throw new Error(
        `The execution record for ${jobId} exists but could not be read: ` +
          `${err instanceof Error ? err.message : String(err)}. ` +
          'This is a damaged record, not a missing one.'
      );
    }
  }

  /**
   * Add phase to execution trace
   */
  addPhase(
    jobId: string,
    phase: string,
    durationMs: number,
    stepCount?: number,
    warnings?: string[]
  ): void {
    // Deliberately the Map only, NOT `load()`. A phase is added while a run
    // is in flight, to the record that run is building. Reviving a finished
    // record from disk to append a phase would mutate a copy that is never
    // written back — the caller would see a successful call and the phase
    // would vanish, which is the silent-discard pattern this repository has
    // spent several passes removing.
    const record = this.records.get(jobId);
    if (!record) {
      logger.warn({ jobId }, 'Record not found for phase tracking');
      return;
    }

    ExecutionRecorder.addPhase(record, phase, durationMs, stepCount, warnings);
  }

  /**
   * Verify reproducibility
   */
  async verifyReproducibility(
    jobId: string,
    reproducer: (inputs: any) => Promise<any>
  ): Promise<ReproductionAttempt> {
    const record = this.load(jobId);
    if (!record) {
      throw new Error(
        `No execution record for job ${jobId}. Records are written when a ` +
          `simulation runs; \`history\` lists the jobs that have them.`
      );
    }

    return ReproducibilityVerifier.verify(record, reproducer);
  }

  /**
   * Check data integrity
   */
  checkIntegrity(jobId: string): {
    intact: boolean;
    issues: string[];
  } {
    const record = this.load(jobId);
    if (!record) {
      throw new Error(
        `No execution record for job ${jobId}. Records are written when a ` +
          `simulation runs; \`history\` lists the jobs that have them.`
      );
    }

    return DataIntegrityChecker.verify(record);
  }

  /**
   * Get integrity report
   */
  getIntegrityReport(jobId: string): string {
    const record = this.load(jobId);
    if (!record) {
      throw new Error(
        `No execution record for job ${jobId}. Records are written when a ` +
          `simulation runs; \`history\` lists the jobs that have them.`
      );
    }

    return DataIntegrityChecker.generateReport(record);
  }

  /**
   * Get execution record
   */
  getRecord(jobId: string): ExecutionRecord | undefined {
    return this.load(jobId);
  }

  /**
   * Get all records
   */
  getAllRecords(): ExecutionRecord[] {
    return Array.from(this.records.values());
  }

  /**
   * Nightly verification (check recent simulations)
   */
  async nightly_verification(reproducer: (inputs: any) => Promise<any>): Promise<{
    totalChecked: number;
    passed: number;
    failed: number;
    successRate: number;
  }> {
    const records = this.getAllRecords();
    const recent = records.filter(r => {
      const hoursOld = (Date.now() - r.timestamp.getTime()) / (1000 * 60 * 60);
      return hoursOld < 24;
    });

    logger.info({ count: recent.length }, 'Starting nightly reproducibility verification');

    let passed = 0;
    let failed = 0;

    for (const record of recent) {
      try {
        const result = await this.verifyReproducibility(record.jobId, reproducer);
        if (result.verification.passed) {
          passed++;
        } else {
          failed++;
          logger.warn({ jobId: record.jobId }, 'Reproducibility check failed');
        }
      } catch (error) {
        failed++;
        logger.error({ jobId: record.jobId, error }, 'Reproducibility check error');
      }
    }

    const successRate = recent.length > 0 ? passed / recent.length : 0;

    logger.info(
      { passed, failed, total: recent.length, successRate: (successRate * 100).toFixed(1) },
      'Nightly verification complete'
    );

    return {
      totalChecked: recent.length,
      passed,
      failed,
      successRate
    };
  }
}

// ============================================================================
// EXPORT
// ============================================================================

export default {
  ExecutionRecorder,
  ReproducibilityVerifier,
  DataIntegrityChecker,
  ReproducibilityService
};
