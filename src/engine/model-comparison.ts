/**
 * Model Comparison Engine
 *
 * Run all 4 kinetic models with same parameters and compare results.
 * Identify which model provides best fit and how results differ.
 *
 * Models:
 * 1. Michaelis-Menten (baseline)
 * 2. Competitive Inhibition
 * 3. Non-Competitive Inhibition
 * 4. Product Inhibition
 */

import { logger } from '../logger';
import ScientificPipeline from '../integration/scientificPipeline';

export type KineticModel =
  | 'michaelis-menten'
  | 'competitive-inhibition'
  | 'non-competitive-inhibition'
  | 'product-inhibition';

export interface ModelResult {
  model: KineticModel;
  finalValue: number;
  confidence: number;
  validated: boolean;
  executionTimeMs: number;
  trajectoryPoints: number;
  error?: string;
}

export interface ComparisonResult {
  baseParameters: Record<string, number>;
  models: ModelResult[];
  bestModel: KineticModel;
  bestFinalValue: number;
  variability: number; // Standard deviation across models
  totalTimeMs: number;
  insights: string[];
}

/**
 * Compare all kinetic models
 */
export async function compareModels(
  parameters: Record<string, number>,
  onProgress?: (completed: number, total: number) => void
): Promise<ComparisonResult> {
  const startTime = Date.now();
  const models: KineticModel[] = [
    'michaelis-menten',
    'competitive-inhibition',
    'non-competitive-inhibition',
    'product-inhibition'
  ];

  logger.info({ models: models.length }, 'Starting model comparison');

  const results: ModelResult[] = [];
  let completed = 0;

  // Run each model
  for (const model of models) {
    try {
      const modelStartTime = Date.now();
      const pipeline = new ScientificPipeline();

      const response = await pipeline.execute({
        query: model,
        parameters,
        conditions: { temperature: 37, pH: 7.4 }
      });

      const executionTimeMs = Date.now() - modelStartTime;

      results.push({
        model,
        finalValue: response.results?.finalValue || 0,
        confidence: response.validationConfidence,
        validated: response.validated,
        executionTimeMs,
        trajectoryPoints: response.results?.trajectory?.length || 0
      });

      logger.info({ model, finalValue: response.results?.finalValue }, `${model} complete`);
    } catch (error) {
      logger.error({ model, error }, `${model} failed`);
      results.push({
        model,
        finalValue: 0,
        confidence: 0,
        validated: false,
        executionTimeMs: 0,
        trajectoryPoints: 0,
        error: error instanceof Error ? error.message : String(error)
      });
    }

    completed++;
    if (onProgress) onProgress(completed, models.length);
  }

  // Analyze results
  const validResults = results.filter(r => !r.error);
  const finalValues = validResults.map(r => r.finalValue);

  // Best model = minimum remaining substrate
  const bestResult = validResults.length > 0 ? validResults.reduce((best, current) =>
    current.finalValue < best.finalValue ? current : best
  ) : results[0];

  // Calculate variability (standard deviation)
  const mean = finalValues.length > 0 ? finalValues.reduce((a, b) => a + b, 0) / finalValues.length : 0;
  const variance =
    finalValues.length > 0
      ? finalValues.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / finalValues.length
      : 0;
  const variability = Math.sqrt(variance);

  // Generate insights
  const insights = generateInsights(results, mean, variability);

  const totalTimeMs = Date.now() - startTime;

  logger.info(
    {
      bestModel: bestResult.model,
      variability: variability.toFixed(3),
      totalTimeMs
    },
    'Model comparison complete'
  );

  return {
    baseParameters: parameters,
    models: results,
    bestModel: bestResult.model,
    bestFinalValue: bestResult.finalValue,
    variability,
    totalTimeMs,
    insights
  };
}

/**
 * Generate scientific insights from comparison
 */
function generateInsights(results: ModelResult[], mean: number, variability: number): string[] {
  const insights: string[] = [];

  // Model agreement
  if (variability < 0.1) {
    insights.push('✓ All models show high agreement (low variability)');
    insights.push('→ Results are robust to model choice');
  } else if (variability < 0.5) {
    insights.push('⚠ Moderate variability between models');
    insights.push('→ Model selection may affect results');
  } else {
    insights.push('⚠ High variability between models');
    insights.push('→ Use experimental data to disambiguate which model fits');
  }

  // Model performance
  const validated = results.filter(r => r.validated);
  if (validated.length === results.length) {
    insights.push('✓ All models validated against literature');
  } else if (validated.length > 0) {
    insights.push(`⚠ ${validated.length}/${results.length} models have literature backing`);
  }

  // Execution time
  const avgTime = results.reduce((sum, r) => sum + r.executionTimeMs, 0) / results.length;
  insights.push(`✓ Average execution time: ${avgTime.toFixed(0)}ms per model`);

  // Trajectory consistency
  const trajectoryLengths = results.map(r => r.trajectoryPoints);
  if (new Set(trajectoryLengths).size === 1) {
    insights.push(`✓ All models generated ${trajectoryLengths[0]} trajectory points`);
  }

  return insights;
}

/**
 * Compare two specific models
 */
export async function compareModelPair(
  model1: KineticModel,
  model2: KineticModel,
  parameters: Record<string, number>
): Promise<{
  model1Result: ModelResult;
  model2Result: ModelResult;
  difference: number;
  percentDifference: number;
}> {
  const pipeline = new ScientificPipeline();

  // Run both models
  const [response1, response2] = await Promise.all([
    pipeline.execute({ query: model1, parameters, conditions: { temperature: 37, pH: 7.4 } }),
    pipeline.execute({ query: model2, parameters, conditions: { temperature: 37, pH: 7.4 } })
  ]);

  const result1: ModelResult = {
    model: model1,
    finalValue: response1.results?.finalValue || 0,
    confidence: response1.validationConfidence,
    validated: response1.validated,
    executionTimeMs: response1.metadata.executionTimeMs,
    trajectoryPoints: response1.results?.trajectory?.length || 0
  };

  const result2: ModelResult = {
    model: model2,
    finalValue: response2.results?.finalValue || 0,
    confidence: response2.validationConfidence,
    validated: response2.validated,
    executionTimeMs: response2.metadata.executionTimeMs,
    trajectoryPoints: response2.results?.trajectory?.length || 0
  };

  const difference = Math.abs(result1.finalValue - result2.finalValue);
  const avg = (result1.finalValue + result2.finalValue) / 2;
  const percentDifference = avg > 0 ? (difference / avg) * 100 : 0;

  return {
    model1Result: result1,
    model2Result: result2,
    difference,
    percentDifference
  };
}

/**
 * Rank models by fit quality (if experimental data provided)
 */
export function rankModelsByFit(
  results: ModelResult[],
  experimentalFinalValue: number
): Array<{ model: KineticModel; error: number; ranking: number }> {
  // Calculate error (distance from experimental value)
  const ranked = results
    .filter(r => !r.error)
    .map(r => ({
      model: r.model,
      error: Math.abs(r.finalValue - experimentalFinalValue),
      ranking: 0
    }))
    .sort((a, b) => a.error - b.error)
    .map((r, i) => ({ ...r, ranking: i + 1 }));

  return ranked;
}
