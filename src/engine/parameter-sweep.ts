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
  finalValue: number;
  confidence: number;
  validated: boolean;
  executionTimeMs: number;
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
          parameters: currentParams,
          conditions: { temperature: 37, pH: 7.4 }
        });

        completedSimulations++;
        if (onProgress) onProgress(completedSimulations, totalSimulations);

        results.push({
          parameters: { ...currentParams },
          finalValue: response.results?.finalValue || 0,
          confidence: response.validationConfidence,
          validated: response.validated,
          executionTimeMs: response.metadata.executionTimeMs
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
        results.push({
          parameters: { ...currentParams },
          finalValue: 0,
          confidence: 0,
          validated: false,
          executionTimeMs: 0
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
  meanFinalValue: number;
  minFinalValue: number;
  maxFinalValue: number;
  stdDevFinalValue: number;
  optimalParams: Record<string, number>;
  optimalValue: number;
  parameterSensitivity: Record<string, number>;
} {
  const { results, sweptParameters } = sweepResults;

  if (results.length === 0) {
    return {
      meanFinalValue: 0,
      minFinalValue: 0,
      maxFinalValue: 0,
      stdDevFinalValue: 0,
      optimalParams: {},
      optimalValue: 0,
      parameterSensitivity: {}
    };
  }

  // Calculate statistics
  const values = results.map(r => r.finalValue);
  const meanFinalValue = values.reduce((a, b) => a + b, 0) / values.length;
  const minFinalValue = Math.min(...values);
  const maxFinalValue = Math.max(...values);
  const variance =
    values.reduce((sum, v) => sum + Math.pow(v - meanFinalValue, 2), 0) / values.length;
  const stdDevFinalValue = Math.sqrt(variance);

  // Find optimal (minimum substrate remaining = maximum conversion)
  const optimalResult = results.reduce((best, current) =>
    current.finalValue < best.finalValue ? current : best
  );

  // Calculate parameter sensitivity
  const parameterSensitivity: Record<string, number> = {};
  for (const param of sweptParameters) {
    const paramResults = results.filter(r => r.parameters[param.name] !== undefined);
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
    parameterSensitivity
  };
}
