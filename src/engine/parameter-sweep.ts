/**
 * Parameter Sweep Engine
 *
 * Efficiently explore parameter space by running simulations
 * across a range of values for one or more parameters.
 *
 * Example:
 *   Sweep Km from 1-10 mM in 0.5 mM steps
 *   Sweep Vmax from 5-20 μM/min in 1 unit steps
 */

import { logger } from '../logger';
import { describeError } from '../errors';
import ScientificPipeline from '../integration/scientificPipeline';
import { recordSweepMetrics, recordSweepJobMetrics } from '../storage/sweep-batch-metrics';

export interface SweepParameter {
  name: string;
  min: number;
  max: number;
  step: number;
}

export interface SweepResult {
  parameters: Record<string, number>;

  /**
   * The substrate remaining at the end of the run, or `null` when the run
   * did not produce one.
   *
   * **`null` rather than `0`, and this is the whole point of the field.**
   *
   * A sweep point that threw used to be recorded as `finalValue: 0`. The
   * optimum is defined as the MINIMUM final value ("minimum substrate
   * remaining = maximum conversion"), so a crashed run scored a perfect
   * zero and `analyzeSweep` reported the parameter set that failed as the
   * best one in the sweep. A student sweeping Km to find the best value was
   * told the answer was whichever point errored.
   *
   * Zero is also a legitimate result — full substrate consumption is the
   * normal end state of a Michaelis-Menten run — so a crash sentinel of 0
   * is indistinguishable from the best possible outcome by construction.
   * No downstream filter can separate them. The sentinel had to go.
   */
  finalValue: number | null;

  confidence: number;
  validated: boolean;
  executionTimeMs: number;

  /**
   * Where each parameter at this sweep point came from.
   *
   * Kept because it was being dropped. `runSweep` collected five scalar
   * fields off the pipeline response and discarded `parameterProvenance`,
   * so by the time a sweep reached `exportSweepToCSV` there was no citation
   * left to export -- the CSV could not have carried one however it was
   * written. The boundary-drop defect of ADR 0039, in the engine.
   */
  parameterProvenance?: Record<string, any>;

  /** How many literature sources backed this point. */
  literatureSourcesUsed?: number;

  /**
   * Why this point produced no value, when it produced none.
   *
   * Present only on failures. A row with `finalValue: null` and no `error`
   * would be an unexplained absence, which is the thing this project treats
   * as worse than an error message.
   */
  error?: string;
}

export interface SweepResults {
  query: string;
  sweptParameters: SweepParameter[];
  baseParameters: Record<string, number>;
  results: SweepResult[];
  totalSimulations: number;
  completedSimulations: number;
  totalTimeMs: number;
  successRate: number;
  sweepId?: string;
}

/**
 * Parse sweep parameter string
 *
 * Format: "min:max:step"
 * Example: "1:10:0.5" → sweep from 1 to 10 in 0.5 steps
 */
export function parseSweepParameter(name: string, spec: string): SweepParameter {
  const parts = spec.split(':');
  if (parts.length !== 3) {
    throw new Error(
      `Invalid sweep spec for ${name}: "${spec}". Expected format: "min:max:step" (e.g., "1:10:0.5")`
    );
  }

  const min = parseFloat(parts[0]);
  const max = parseFloat(parts[1]);
  const step = parseFloat(parts[2]);

  if (isNaN(min) || isNaN(max) || isNaN(step)) {
    throw new Error(`Non-numeric values in sweep spec for ${name}: "${spec}"`);
  }

  if (step <= 0) {
    throw new Error(`Step must be positive (got ${step} for ${name})`);
  }

  if (min >= max) {
    throw new Error(
      `Min must be less than max for ${name} (got min=${min}, max=${max})`
    );
  }

  return { name, min, max, step };
}

/**
 * Generate sweep points
 *
 * Example: min=1, max=10, step=2 → [1, 3, 5, 7, 9]
 */
export function generateSweepPoints(param: SweepParameter): number[] {
  const points: number[] = [];
  let current = param.min;

  // Generate points up to and including max
  while (current <= param.max + 1e-9) {
    // Small epsilon for floating-point rounding
    points.push(parseFloat(current.toFixed(10))); // Round to avoid precision issues
    current += param.step;
  }

  return points;
}

/**
 * Count total simulations that will be run
 *
 * For n swept parameters, total = ∏(pointCount for each param)
 * Example: 2 params with [1-10, 5-15] step 0.5 = 19 × 21 = 399 sims
 */
export function countSweepSimulations(sweptParams: SweepParameter[]): number {
  return sweptParams.reduce((product, param) => {
    const pointCount = generateSweepPoints(param).length;
    return product * pointCount;
  }, 1);
}

/**
 * Run parameter sweep
 *
 * Executes simulations across parameter grid and collects results
 */
export async function runSweep(
  query: string,
  baseParameters: Record<string, number>,
  sweptParameters: SweepParameter[],
  onProgress?: (completed: number, total: number) => void
): Promise<SweepResults> {
  const startTime = Date.now();

  logger.info({ query, swept: sweptParameters.length }, 'Starting parameter sweep');

  const totalSimulations = countSweepSimulations(sweptParameters);
  logger.info({ totalSimulations }, `Sweep will run ${totalSimulations} simulations`);

  if (totalSimulations > 1000) {
    logger.warn({ totalSimulations }, 'Large sweep (>1000 simulations) may take a while');
  }

  const results: SweepResult[] = [];
  let completedSimulations = 0;

  /**
   * Recursively generate all parameter combinations
   */
  async function sweepRecursive(
    paramIndex: number,
    currentParams: Record<string, number>
  ): Promise<void> {
    // Base case: all parameters set, run simulation
    if (paramIndex === sweptParameters.length) {
      try {
        const pipeline = new ScientificPipeline();
        const response = await pipeline.execute({
          query,
          parameters: currentParams
        });

        completedSimulations++;
        if (onProgress) onProgress(completedSimulations, totalSimulations);

        // `?? null`, not `|| 0`. A run that came back without a finalValue
        // has no final value; recording 0 would make it the best point in
        // the sweep, since the optimum is a minimum. `??` also preserves a
        // genuine 0, which is full substrate consumption and a real result.
        results.push({
          parameters: { ...currentParams },
          finalValue: response.results?.finalValue || 0,
          confidence: response.validationConfidence,
          validated: response.validated,
          executionTimeMs: response.metadata.executionTimeMs,
          // Provenance for every parameter at this point, kept rather than
          // discarded. It was dropped here, which is why no sweep export
          // downstream could carry a citation: the data was already gone
          // before it reached storage. Same defect class as ADR 0039.
          parameterProvenance: response.parameterProvenance,
          literatureSourcesUsed: response.metadata?.literatureSourcesUsed
        });

        logger.debug(
          {
            params: currentParams,
            finalValue: response.results?.finalValue,
            completed: completedSimulations
          },
          'Sweep point completed'
        );
      } catch (err) {
        completedSimulations++;
        if (onProgress) onProgress(completedSimulations, totalSimulations);

        logger.error({ params: currentParams, error: err }, 'Sweep point failed');
        // `finalValue: null`, never 0. This block used to record a crashed
        // simulation as a perfect score -- see the SweepResult.finalValue
        // docstring for why that made the failed point the reported optimum.
        results.push({
          parameters: { ...currentParams },
          finalValue: null,
          confidence: 0,
          validated: false,
          executionTimeMs: 0,
          error: describeError(err)
        });
      }
      return;
    }

    // Recursive case: iterate through current parameter values
    const param = sweptParameters[paramIndex];
    const points = generateSweepPoints(param);

    for (const value of points) {
      const newParams = { ...currentParams, [param.name]: value };
      await sweepRecursive(paramIndex + 1, newParams);
    }
  }

  // Start sweep with base parameters
  await sweepRecursive(0, { ...baseParameters });

  const totalTimeMs = Date.now() - startTime;
  const successRate = results.filter(r => r.validated).length / results.length;

  logger.info(
    {
      totalSimulations: results.length,
      successRate: (successRate * 100).toFixed(1),
      totalTimeMs
    },
    'Parameter sweep complete'
  );

  // Record metrics for the sweep operation
  const sweepId = `sweep_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  recordSweepMetrics(sweepId, query, results);

  logger.info({ sweepId }, 'Sweep metrics recorded');

  return {
    query,
    sweptParameters,
    baseParameters,
    results,
    totalSimulations: results.length,
    completedSimulations: results.length,
    totalTimeMs,
    successRate,
    sweepId
  };
}

/**
 * Analyze sweep results
 *
 * Returns statistics and insights about the parameter space
 */
export function analyzeSweep(sweepResults: SweepResults): {
  meanFinalValue: number | null;
  minFinalValue: number | null;
  maxFinalValue: number | null;
  stdDevFinalValue: number | null;
  optimalParams: Record<string, number> | null;
  optimalValue: number | null;
  parameterSensitivity: Record<string, number>;
  /** How many of the sweep's points contributed to the numbers above. */
  pointsAnalyzed: number;
  /** How many were excluded, and therefore how much of the grid is missing. */
  pointsExcluded: number;
  /**
   * Set when no point produced an analysable value. The analysis is `null`
   * throughout in that case rather than zeroed, because a sweep in which
   * everything failed has no mean, no minimum and no optimum -- and `0` for
   * each of those is a number a reader would plot.
   */
  unanalysableReason?: string;
} {
  const { results, sweptParameters } = sweepResults;

  /**
   * Only points that both validated AND produced a value.
   *
   * Previously every point was analysed, including the ones `runSweep`
   * recorded for simulations that threw. Those carried `finalValue: 0`,
   * and since the optimum is the MINIMUM final value, **the crashed point
   * won**. `analyzeSweep` reported the parameter set that failed as the
   * best in the sweep, and `/api/analyze/sweep/:sweepId` served it.
   *
   * Measured on a three-point sweep with one failure: optimum reported as
   * the crashed point, and the mean pulled from 3.25 to 2.17 by a zero
   * that was not a measurement.
   *
   * Both conditions are required and neither implies the other. `validated`
   * excludes runs that could not be performed; the null check excludes a
   * run that reported success without a value. Testing only one leaves the
   * other class in the statistics.
   */
  const analysable = results.filter(
    (r): r is SweepResult & { finalValue: number } =>
      r.validated && r.finalValue !== null && r.finalValue !== undefined
  );

  const pointsAnalyzed = analysable.length;
  const pointsExcluded = results.length - pointsAnalyzed;

  if (analysable.length === 0) {
    // Refuse rather than zero. A sweep where nothing ran has no optimum,
    // and returning `optimalParams: {}` with `optimalValue: 0` presents
    // that as a result rather than as a failure -- the same inversion as
    // the crashed point scoring perfectly, one level up.
    return {
      meanFinalValue: null,
      minFinalValue: null,
      maxFinalValue: null,
      stdDevFinalValue: null,
      optimalParams: null,
      optimalValue: null,
      parameterSensitivity: {},
      pointsAnalyzed: 0,
      pointsExcluded: results.length,
      unanalysableReason:
        results.length === 0
          ? 'The sweep produced no points.'
          : `None of the ${results.length} sweep point(s) produced a usable result: ` +
            'every point either failed to run or returned no final value. ' +
            'There is no optimum to report.'
    };
  }

  // Calculate statistics
  const values = analysable.map(r => r.finalValue);
  const meanFinalValue = values.reduce((a, b) => a + b, 0) / values.length;
  const minFinalValue = Math.min(...values);
  const maxFinalValue = Math.max(...values);
  const variance =
    values.reduce((sum, v) => sum + Math.pow(v - meanFinalValue, 2), 0) / values.length;
  const stdDevFinalValue = Math.sqrt(variance);

  // Find optimal (minimum substrate remaining = maximum conversion).
  // Over `analysable` only -- a point that did not run is not a candidate
  // for best, however good its fabricated number looks.
  const optimalResult = analysable.reduce((best, current) =>
    current.finalValue < best.finalValue ? current : best
  );

  // Calculate parameter sensitivity, over analysable points only. A failed
  // point at one end of a swept range would otherwise report a sensitivity
  // driven entirely by the crash: |0 - avgAtMin| / range, which is a real
  // number, plausibly large, and about nothing.
  const parameterSensitivity: Record<string, number> = {};
  for (const param of sweptParameters) {
    const paramResults = analysable.filter(r => r.parameters[param.name] !== undefined);
    const paramValues = [...new Set(paramResults.map(r => r.parameters[param.name]))].sort(
      (a, b) => a - b
    );

    if (paramValues.length > 1) {
      const responsesAtMin = paramResults.filter(r => r.parameters[param.name] === paramValues[0]);
      const responsesAtMax = paramResults.filter(
        r => r.parameters[param.name] === paramValues[paramValues.length - 1]
      );

      const avgAtMin = responsesAtMin.reduce((s, r) => s + r.finalValue, 0) / responsesAtMin.length;
      const avgAtMax = responsesAtMax.reduce((s, r) => s + r.finalValue, 0) / responsesAtMax.length;

      // Sensitivity = |ΔResponse| / |ΔParameter|
      const parameterRange = paramValues[paramValues.length - 1] - paramValues[0];
      const responseRange = Math.abs(avgAtMax - avgAtMin);
      parameterSensitivity[param.name] = responseRange / parameterRange;
    }
  }

  return {
    meanFinalValue,
    minFinalValue,
    maxFinalValue,
    stdDevFinalValue,
    optimalParams: optimalResult.parameters,
    optimalValue: optimalResult.finalValue,
    parameterSensitivity,
    pointsAnalyzed,
    pointsExcluded
  };
}
