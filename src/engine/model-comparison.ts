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
import { describeError } from '../errors';
import ScientificPipeline from '../integration/scientificPipeline';

export type KineticModel =
  | 'michaelis-menten'
  | 'competitive-inhibition'
  | 'non-competitive-inhibition'
  | 'product-inhibition';

export interface ModelResult {
  model: KineticModel;

  /**
   * Substrate remaining at the end of the run, or `null` when the model did
   * not produce one. See ADR 0058 for why this is `null` and never `0`:
   * best-fit and best-model are both chosen by proximity to a small number,
   * so a placeholder zero does not merely pollute the statistics, it wins.
   */
  finalValue: number | null;

  confidence: number;
  validated: boolean;
  executionTimeMs: number;
  trajectoryPoints: number;
  error?: string;
}

export interface ComparisonResult {
  baseParameters: Record<string, number>;
  models: ModelResult[];

  /**
   * The model with the lowest remaining substrate, or `null` when no model
   * produced a usable result.
   *
   * Was `results[0]` in that case — the first model in the list, usually one
   * that had just failed, returned as "best" with nothing marking it. A
   * comparison in which nothing ran has no winner, and naming one anyway is
   * the failure-presented-as-a-result inversion of ADR 0058.
   */
  bestModel: KineticModel | null;
  bestFinalValue: number | null;
  variability: number | null; // Standard deviation across models

  /** How many models the numbers above rest on, and how many were left out. */
  modelsAnalyzed: number;
  modelsExcluded: number;

  /** Set when no model produced a usable result. */
  unanalysableReason?: string;

  totalTimeMs: number;
  insights: string[];
}

/**
 * The models whose numbers can be compared.
 *
 * Requires BOTH `validated === true` and a non-null `finalValue`, and
 * neither implies the other — the distinction ADR 0058 found by mutation
 * and which this file got wrong in a way that ADR did not cover.
 *
 * The filter here was `results.filter(r => !r.error)`. That excludes models
 * that **threw**, and lets through models that **ran and failed
 * validation** — and `scientificPipeline` returns
 * `finalValue: simulationOutput.finalValue || 0` with an empty trajectory
 * in exactly that case. So a model that did not validate arrived carrying a
 * fabricated `0`, with no `error` string to catch it on.
 *
 * Both consumers pick by smallness. `bestModel` takes the minimum;
 * `rankModelsByFit` takes the smallest distance from the experimental
 * value. Measured on three models against an experimental value of 0.4 —
 * near-complete conversion, an ordinary result in enzyme kinetics — the
 * model that failed validation ranked **first**, ahead of both models that
 * ran, because its placeholder zero sat 0.4 from the measurement while the
 * real models sat 3.5 and 3.8 away.
 *
 * That is model selection against experimental data recommending a model
 * that did not run.
 */
function usableResults(results: ModelResult[]): Array<ModelResult & { finalValue: number }> {
  return results.filter(
    (r): r is ModelResult & { finalValue: number } =>
      r.validated === true && r.finalValue !== null && r.finalValue !== undefined
  );
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
        parameters
      });

      const executionTimeMs = Date.now() - modelStartTime;

      // `?? null`, not `|| 0`. `??` also preserves a genuine zero, which is
      // full substrate consumption and the best possible outcome.
      results.push({
        model,
        finalValue: response.results?.finalValue ?? null,
        confidence: response.validationConfidence,
        validated: response.validated,
        executionTimeMs,
        trajectoryPoints: response.results?.trajectory?.length || 0
      });

      logger.info({ model, finalValue: response.results?.finalValue }, `${model} complete`);
    } catch (error) {
      logger.error({ model, error }, `${model} failed`);
      // `null`, never 0 — a model that threw has no final value, and both
      // "best model" and "best fit" are chosen by proximity to a small
      // number, so a zero here does not merely skew the result, it wins it.
      results.push({
        model,
        finalValue: null,
        confidence: 0,
        validated: false,
        executionTimeMs: 0,
        trajectoryPoints: 0,
        error: describeError(error)
      });
    }

    completed++;
    if (onProgress) onProgress(completed, models.length);
  }

  // Analyze results. See usableResults() for why `!r.error` was not enough.
  const validResults = usableResults(results);
  const finalValues = validResults.map(r => r.finalValue);
  const totalTimeMs = Date.now() - startTime;

  if (validResults.length === 0) {
    // Refuse. This branch used to fall back to `results[0]` — the first
    // model in the list, which in this situation had just failed — and
    // return it as `bestModel` with nothing marking it as a failure.
    logger.warn({ models: results.length }, 'Model comparison: no model produced a usable result');
    return {
      baseParameters: parameters,
      models: results,
      bestModel: null,
      bestFinalValue: null,
      variability: null,
      modelsAnalyzed: 0,
      modelsExcluded: results.length,
      unanalysableReason:
        `None of the ${results.length} model(s) produced a usable result: each either ` +
        'failed to run or did not validate. There is no best model to report.',
      totalTimeMs,
      insights: results
        .filter(r => r.error)
        .map(r => `${r.model} failed: ${r.error}`)
    };
  }

  // Best model = minimum remaining substrate
  const bestResult = validResults.reduce((best, current) =>
    current.finalValue < best.finalValue ? current : best
  );

  // Calculate variability (standard deviation), over usable models only
  const mean = finalValues.reduce((a, b) => a + b, 0) / finalValues.length;
  const variance =
    finalValues.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / finalValues.length;
  const variability = Math.sqrt(variance);

  // Generate insights
  const insights = generateInsights(results, mean, variability);

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
    modelsAnalyzed: validResults.length,
    modelsExcluded: results.length - validResults.length,
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
  /**
   * `null` when either model produced no final value.
   *
   * The difference between a number and an absence is not zero and is not
   * that number — it is not defined. Coalescing the missing side to 0 (as
   * `|| 0` did) reported a difference equal to the surviving model's entire
   * value, i.e. "these two models disagree completely", which is a strong
   * and fabricated scientific claim.
   */
  difference: number | null;
  percentDifference: number | null;
  /** Why the comparison could not be made, when it could not. */
  incomparableReason?: string;
}> {
  const pipeline = new ScientificPipeline();

  // Run both models
  const [response1, response2] = await Promise.all([
    pipeline.execute({ query: model1, parameters }),
    pipeline.execute({ query: model2, parameters })
  ]);

  const result1: ModelResult = {
    model: model1,
    finalValue: response1.results?.finalValue ?? null,
    confidence: response1.validationConfidence,
    validated: response1.validated,
    executionTimeMs: response1.metadata.executionTimeMs,
    trajectoryPoints: response1.results?.trajectory?.length || 0
  };

  const result2: ModelResult = {
    model: model2,
    finalValue: response2.results?.finalValue ?? null,
    confidence: response2.validationConfidence,
    validated: response2.validated,
    executionTimeMs: response2.metadata.executionTimeMs,
    trajectoryPoints: response2.results?.trajectory?.length || 0
  };

  const missing = [result1, result2].filter(
    r => r.finalValue === null || r.finalValue === undefined
  );

  if (missing.length > 0) {
    return {
      model1Result: result1,
      model2Result: result2,
      difference: null,
      percentDifference: null,
      incomparableReason:
        `${missing.map(r => r.model).join(' and ')} produced no final value, ` +
        'so there is no difference to report. Both results are returned ' +
        'unchanged so the caller can see which side is missing.'
    };
  }

  const v1 = result1.finalValue as number;
  const v2 = result2.finalValue as number;
  const difference = Math.abs(v1 - v2);
  const avg = (v1 + v2) / 2;
  const percentDifference = avg > 0 ? (difference / avg) * 100 : 0;

  return {
    model1Result: result1,
    model2Result: result2,
    difference,
    percentDifference
  };
}

/**
 * Rank models by fit quality (if experimental data provided).
 *
 * THE DEFECT THIS WAS FIXED FOR
 * -----------------------------
 * The filter was `results.filter(r => !r.error)`, which excludes models
 * that threw and admits models that ran and failed validation. Those arrive
 * carrying `finalValue: 0` from `scientificPipeline`, and fit is scored by
 * `|finalValue - experimental|`.
 *
 * So the closer the experiment's own value is to zero, the better a failed
 * model scores. Measured against an experimental value of 0.4 — an
 * ordinary near-complete conversion — the model that did not validate
 * ranked **first**, at distance 0.4, ahead of two models that ran at 3.5
 * and 3.8.
 *
 * This function answers "which model best explains my data". It was capable
 * of answering with a model that never produced any.
 *
 * WHAT IT RETURNS NOW
 * -------------------
 * Only models that ran and validated are ranked. The rest are returned in
 * `excluded`, with the reason, so a caller can see that the comparison was
 * partial. Dropping them silently would leave a reader with a clean
 * three-way ranking and no sign that a fourth model was ever attempted.
 */
/**
 * The route's decision about whether to rank at all, in one place.
 *
 * WHY THIS IS NOT INLINE IN THE ROUTE
 * -----------------------------------
 * It was, and the test written to prove the wiring defined its own copy of
 * the condition rather than importing it. A mutation to the route then
 * changed nothing the test could see, and the harness reported NOT CAUGHT.
 *
 * That is ADR 0027's duplicate-source-of-truth defect committed inside a
 * test written to demonstrate delivery: the test asserted a
 * re-implementation and agreed with it perfectly, which is exactly what the
 * reliability parity test did before it was deleted.
 *
 * Exported separately from the route for the same reason `buildTrajectoryCsv`
 * is (ADR 0050): a decision reachable only through an HTTP server is a
 * decision nobody tests.
 *
 * `experimentalFinalValue` is a number the EXPERIMENTER measured. Caterva
 * cannot resolve it from literature and must not invent one, so absence
 * means no ranking -- never a default. Non-finite is refused for a sharper
 * reason: `Math.abs(x - NaN)` is NaN, `.sort()` on NaN comparisons leaves
 * the array in input order, and the result would look like a ranking while
 * being an artefact of argument order.
 */
export function fitRankingFor(
  models: ModelResult[],
  experimental: unknown,
):
  | {
      ranked: Array<{ model: KineticModel; error: number; ranking: number }>;
      excluded: Array<{ model: KineticModel; reason: string }>;
    }
  | undefined {
  if (typeof experimental !== "number" || !Number.isFinite(experimental)) {
    return undefined;
  }
  return rankModelsByFit(models, experimental);
}

export function rankModelsByFit(
  results: ModelResult[],
  experimentalFinalValue: number
): {
  ranked: Array<{ model: KineticModel; error: number; ranking: number }>;
  excluded: Array<{ model: KineticModel; reason: string }>;
} {
  const usable = usableResults(results);

  const ranked = usable
    .map(r => ({
      model: r.model,
      error: Math.abs(r.finalValue - experimentalFinalValue),
      ranking: 0
    }))
    .sort((a, b) => a.error - b.error)
    .map((r, i) => ({ ...r, ranking: i + 1 }));

  const usableModels = new Set(usable.map(r => r.model));
  const excluded = results
    .filter(r => !usableModels.has(r.model))
    .map(r => ({
      model: r.model,
      reason: r.error
        ? `failed to run: ${r.error}`
        : r.finalValue === null || r.finalValue === undefined
          ? 'produced no final value'
          : 'ran but did not validate'
    }));

  return { ranked, excluded };
}
