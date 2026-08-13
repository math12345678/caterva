/**
 * Result Comparison Engine
 *
 * Compare two or more job results to identify differences
 * Useful for comparing: different models, different conditions, experimental vs predicted
 */

export interface ComparisonMetrics {
  difference: number;
  percentDifference: number;
  ratio: number;
  isDifferenceSignificant: boolean;
}

export interface JobComparison {
  job1Id: string;
  job2Id: string;
  job1Query: string;
  job2Query: string;
  job1FinalValue: number;
  job2FinalValue: number;
  metrics: ComparisonMetrics;
  similarity: 'identical' | 'very_similar' | 'different' | 'significantly_different';
  insights: string[];
}

export interface MultiJobComparison {
  jobIds: string[];
  queries: string[];
  finalValues: number[];
  mean: number;
  median: number;
  stdDev: number;
  min: { jobId: string; value: number };
  max: { jobId: string; value: number };
  range: number;
  coefficientOfVariation: number;
  ranking: Array<{ jobId: string; query: string; value: number; rank: number }>;
  insights: string[];
}

/**
 * Compare two job results
 */
export function compareJobs(job1: any, job2: any): JobComparison {
  const val1 = job1.result?.finalValue || 0;
  const val2 = job2.result?.finalValue || 0;

  const difference = Math.abs(val1 - val2);
  const avgValue = (Math.abs(val1) + Math.abs(val2)) / 2;
  const percentDifference = avgValue > 0 ? (difference / avgValue) * 100 : 0;
  const ratio = val2 !== 0 ? val1 / val2 : val1 === 0 ? 1 : Infinity;

  // Determine significance (>10% difference or >1.5x ratio)
  const isDifferenceSignificant = percentDifference > 10 || ratio > 1.5 || ratio < 0.67;

  // Classify similarity
  let similarity: 'identical' | 'very_similar' | 'different' | 'significantly_different';
  if (percentDifference < 0.1) similarity = 'identical';
  else if (percentDifference < 5) similarity = 'very_similar';
  else if (percentDifference < 10) similarity = 'different';
  else similarity = 'significantly_different';

  // Generate insights
  const insights: string[] = [];

  // `query` lives on the JOB, not on `job.result`. This read
  // `job1.result?.query`, which is always undefined -- so the comparison
  // was `undefined === undefined`, always true, and every comparison of
  // any two jobs reported:
  //
  //     "Both jobs used the undefined model"
  //
  // A model-comparison tool that cannot distinguish two models is not a
  // degraded tool, it is a tool that answers the opposite question. And it
  // said so in every output, which is the part worth noticing: the word
  // "undefined" was printed to the user on every single run.
  //
  // `compareMultipleJobs` in this same file reads `job.query` correctly,
  // so the two halves disagreed about where the field lives -- the
  // duplicate-source-of-truth shape, inside one module.
  const model1 = job1.query;
  const model2 = job2.query;

  if (model1 === undefined || model2 === undefined) {
    insights.push(
      'At least one job records no query, so the models could not be compared'
    );
  } else if (model1 === model2) {
    insights.push(`Both jobs used the ${model1} model`);
  } else {
    insights.push(`Models differ: ${model1} vs ${model2}`);
  }

  if (percentDifference > 0) {
    insights.push(`${percentDifference.toFixed(2)}% difference in final values`);
  }

  if (job1.result?.validated && !job2.result?.validated) {
    insights.push('Job 1 has literature validation, Job 2 does not');
  } else if (!job1.result?.validated && job2.result?.validated) {
    insights.push('Job 2 has literature validation, Job 1 does not');
  }

  // The closing paren of Math.abs() used to sit after the FIRST term:
  //
  //     Math.abs(job1.confidence || 0) - (job2.confidence || 0) > 0.1
  //
  // so this tested `c1 - c2 > 0.1`, not `|c1 - c2| > 0.1`. Confidences are
  // already non-negative, which is why it looked right. The consequence is
  // that the insight only ever fired when job 1 was the more confident of
  // the two: comparing a 0.20 job against a 0.90 job reported NO confidence
  // difference, and swapping the two arguments changed the answer for the
  // same pair of jobs. A comparison tool whose output depends on argument
  // order is telling two users different things about identical data --
  // and the direction it stayed silent in is the one that matters, because
  // "the job I am asking about is the less trustworthy one" is the fact a
  // reader most needs.
  //
  // The `|| 0` went with it: a job that has no result yet has no confidence,
  // not a confidence of zero, and printing "0.950 vs 0.000" for a job that
  // has not finished asserts a measurement nobody made.
  const conf1 = job1.result?.confidence;
  const conf2 = job2.result?.confidence;
  if (
    typeof conf1 === 'number' &&
    typeof conf2 === 'number' &&
    Math.abs(conf1 - conf2) > 0.1
  ) {
    insights.push(
      `Confidence difference: ${conf1.toFixed(3)} vs ${conf2.toFixed(3)}`
    );
  }

  return {
    job1Id: job1.jobId,
    job2Id: job2.jobId,
    job1Query: job1.result?.query || job1.query,
    job2Query: job2.result?.query || job2.query,
    job1FinalValue: val1,
    job2FinalValue: val2,
    metrics: {
      difference,
      percentDifference,
      ratio,
      isDifferenceSignificant
    },
    similarity,
    insights
  };
}

/**
 * Compare multiple job results
 */
export function compareMultipleJobs(jobs: any[]): MultiJobComparison {
  if (jobs.length === 0) {
    throw new Error('At least one job required');
  }

  const values = jobs.map(j => j.result?.finalValue || 0);
  const queries = jobs.map(j => j.result?.query || j.query || 'unknown');
  const jobIds = jobs.map(j => j.jobId);

  // Calculate statistics
  const sorted = [...values].sort((a, b) => a - b);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const median = values.length % 2 === 0 ? (sorted[values.length / 2 - 1] + sorted[values.length / 2]) / 2 : sorted[Math.floor(values.length / 2)];

  const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
  const stdDev = Math.sqrt(variance);

  const min = { jobId: jobIds[values.indexOf(Math.min(...values))], value: Math.min(...values) };
  const max = { jobId: jobIds[values.indexOf(Math.max(...values))], value: Math.max(...values) };
  const range = max.value - min.value;

  const coefficientOfVariation = mean !== 0 ? (stdDev / Math.abs(mean)) * 100 : 0;

  // Rank jobs
  const ranking = jobs
    .map((job, idx) => ({
      jobId: jobIds[idx],
      query: queries[idx],
      value: values[idx],
      rank: 0
    }))
    .sort((a, b) => b.value - a.value)
    .map((item, idx) => ({ ...item, rank: idx + 1 }));

  // Generate insights
  const insights: string[] = [];

  insights.push(`${jobs.length} jobs compared`);

  if (stdDev > 0) {
    insights.push(`Results vary by ±${stdDev.toFixed(3)} (CV: ${coefficientOfVariation.toFixed(1)}%)`);
  }

  const uniqueQueries = new Set(queries);
  if (uniqueQueries.size > 1) {
    insights.push(`${uniqueQueries.size} different kinetic models used`);
  }

  const validatedCount = jobs.filter(j => j.result?.validated).length;
  if (validatedCount > 0) {
    insights.push(`${validatedCount}/${jobs.length} jobs validated against literature`);
  }

  if (range > 0) {
    insights.push(`Range: ${min.value.toFixed(3)} to ${max.value.toFixed(3)}`);
  }

  return {
    jobIds,
    queries,
    finalValues: values,
    mean,
    median,
    stdDev,
    min,
    max,
    range,
    coefficientOfVariation,
    ranking,
    insights
  };
}

/**
 * Analyze parameter sensitivity from sweep results
 */
export function analyzeSensitivity(sweepResult: any): any {
  if (!sweepResult || !sweepResult.results || sweepResult.results.length < 2) {
    return null;
  }

  const results = sweepResult.results;
  const values = results.map((r: any) => r.finalValue || 0);

  // Calculate sensitivity metrics
  const mean = values.reduce((a: number, b: number) => a + b, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;

  const variance = values.reduce((sum: number, val: number) => sum + Math.pow(val - mean, 2), 0) / values.length;
  const stdDev = Math.sqrt(variance);

  // Sensitivity index (higher = more sensitive)
  const sensitivity = mean !== 0 ? Math.abs(range / mean) * 100 : 0;

  // Identify inflection points where response changes significantly
  const inflectionPoints: number[] = [];
  for (let i = 1; i < values.length - 1; i++) {
    const delta1 = Math.abs(values[i] - values[i - 1]);
    const delta2 = Math.abs(values[i + 1] - values[i]);
    if (delta1 > stdDev || delta2 > stdDev) {
      inflectionPoints.push(i);
    }
  }

  return {
    sensitivity,
    inflectionPoints,
    mean,
    min,
    max,
    range,
    stdDev,
    totalPoints: results.length,
    optimalParameterIndex: values.indexOf(Math.max(...values))
  };
}
