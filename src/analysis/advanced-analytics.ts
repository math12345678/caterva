/**
 * Advanced Analytics Module
 *
 * Statistical analysis and insights generation for simulation results
 * - Correlation detection
 * - Trend analysis
 * - Outlier detection
 * - Statistical comparisons
 */

import { logger } from '../logger';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface DataPoint {
  [key: string]: number | string;
}

export interface CorrelationResult {
  var1: string;
  var2: string;
  pearson: number;
  spearman: number;
  significance: 'strong' | 'moderate' | 'weak' | 'none';
}

export interface TrendAnalysis {
  variable: string;
  /**
   * `indeterminate` when there is not enough data to fit a line at all --
   * see `getTrendDirection`. It is a distinct outcome from `stable`, which
   * is a measured slope of approximately zero.
   */
  direction: 'increasing' | 'decreasing' | 'stable' | 'indeterminate';
  slope: number;
  r_squared: number;
  predictedValue: number;
}

export interface OutlierResult {
  index: number;
  value: number;
  zscore: number;
  isOutlier: boolean;
  severity: 'extreme' | 'moderate' | 'none';
}

// ============================================================================
// CORRELATION ANALYSIS
// ============================================================================

export function calculatePearsonCorrelation(x: number[], y: number[]): number {
  if (x.length !== y.length || x.length < 2) return 0;

  const meanX = x.reduce((a, b) => a + b) / x.length;
  const meanY = y.reduce((a, b) => a + b) / y.length;

  const numerator = x.reduce((sum, xi, i) => sum + (xi - meanX) * (y[i] - meanY), 0);
  const denomX = Math.sqrt(x.reduce((sum, xi) => sum + Math.pow(xi - meanX, 2), 0));
  const denomY = Math.sqrt(y.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0));

  return denomX === 0 || denomY === 0 ? 0 : numerator / (denomX * denomY);
}

export function correlationMatrix(data: DataPoint[]): CorrelationResult[] {
  const results: CorrelationResult[] = [];
  const keys = Object.keys(data[0]).filter(k => typeof data[0][k] === 'number');

  for (let i = 0; i < keys.length; i++) {
    for (let j = i + 1; j < keys.length; j++) {
      const x = data.map(d => Number(d[keys[i]]));
      const y = data.map(d => Number(d[keys[j]]));

      const pearson = calculatePearsonCorrelation(x, y);
      const spearman = calculateSpearmanCorrelation(x, y);
      const significance = getCorrelationSignificance(Math.abs(pearson));

      results.push({
        var1: keys[i],
        var2: keys[j],
        pearson: Number(pearson.toFixed(4)),
        spearman: Number(spearman.toFixed(4)),
        significance
      });
    }
  }

  return results.sort((a, b) => Math.abs(b.pearson) - Math.abs(a.pearson));
}

function calculateSpearmanCorrelation(x: number[], y: number[]): number {
  const rankX = getRanks(x);
  const rankY = getRanks(y);
  return calculatePearsonCorrelation(rankX, rankY);
}

function getRanks(data: number[]): number[] {
  const indexed = data.map((val, idx) => ({ val, idx }));
  indexed.sort((a, b) => a.val - b.val);

  const ranks = new Array(data.length);
  for (let i = 0; i < indexed.length; i++) {
    ranks[indexed[i].idx] = i + 1;
  }
  return ranks;
}

function getCorrelationSignificance(r: number): 'strong' | 'moderate' | 'weak' | 'none' {
  const abs = Math.abs(r);
  if (abs >= 0.7) return 'strong';
  if (abs >= 0.4) return 'moderate';
  if (abs >= 0.2) return 'weak';
  return 'none';
}

// ============================================================================
// TREND ANALYSIS
// ============================================================================

export function analyzeTrends(data: DataPoint[]): TrendAnalysis[] {
  const results: TrendAnalysis[] = [];
  const numericKeys = Object.keys(data[0]).filter(k => typeof data[0][k] === 'number');

  for (const key of numericKeys) {
    const values = data.map(d => Number(d[key]));
    const trend = linearRegression(values);

    results.push({
      variable: key,
      direction: getTrendDirection(trend.slope),
      slope: Number(trend.slope.toFixed(6)),
      r_squared: Number(trend.r_squared.toFixed(4)),
      predictedValue: Number((trend.slope * values.length + trend.intercept).toFixed(3))
    });
  }

  return results.sort((a, b) => Math.abs(b.slope) - Math.abs(a.slope));
}

function linearRegression(y: number[]): { slope: number; intercept: number; r_squared: number } {
  const n = y.length;
  const x = Array.from({ length: n }, (_, i) => i + 1);

  const meanX = x.reduce((a, b) => a + b) / n;
  const meanY = y.reduce((a, b) => a + b) / n;

  const slope = x.reduce((sum, xi, i) => sum + (xi - meanX) * (y[i] - meanY), 0) /
                x.reduce((sum, xi) => sum + Math.pow(xi - meanX, 2), 0);

  const intercept = meanY - slope * meanX;

  const ss_res = y.reduce((sum, yi, i) => sum + Math.pow(yi - (slope * x[i] + intercept), 2), 0);
  const ss_tot = y.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0);
  const r_squared = 1 - (ss_res / ss_tot);

  return { slope, intercept, r_squared };
}

function getTrendDirection(
  slope: number
): 'increasing' | 'decreasing' | 'stable' | 'indeterminate' {
  // A single data point gives `linearRegression` a zero denominator, so the
  // slope is NaN. Every comparison against NaN is false, which used to fall
  // through both branches to `slope > 0 ? ... : 'decreasing'` -- so one
  // point produced the confident claim "direction: decreasing". `scientific
  // sweep` printed "trend  decreasing  (slope NaN)" whenever exactly one
  // point in the sweep was computable, which is the ordinary outcome when
  // validation rejects the rest of the range. Stating a direction from one
  // observation is not a weaker answer than the truth, it is a different
  // one, and it pointed downward every time by accident of operator
  // precedence.
  if (!Number.isFinite(slope)) return 'indeterminate';
  if (Math.abs(slope) < 0.001) return 'stable';
  return slope > 0 ? 'increasing' : 'decreasing';
}

// ============================================================================
// OUTLIER DETECTION
// ============================================================================

export function detectOutliers(values: number[], threshold: number = 2.5): OutlierResult[] {
  const mean = values.reduce((a, b) => a + b) / values.length;
  const stdDev = Math.sqrt(
    values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length
  );

  return values.map((value, index) => {
    const zscore = (value - mean) / stdDev;
    const absZ = Math.abs(zscore);

    const severity: 'extreme' | 'moderate' | 'none' = absZ > 3 ? 'extreme' : absZ > 2 ? 'moderate' : 'none';

    return {
      index,
      value,
      zscore: Number(zscore.toFixed(3)),
      isOutlier: absZ > threshold,
      severity
    };
  }).filter(r => r.isOutlier);
}

// ============================================================================
// STATISTICAL COMPARISONS
// ============================================================================

export interface ComparisonResult {
  group1Mean: number;
  group2Mean: number;
  difference: number;
  percentChange: number;
  tStatistic: number;
  pValue: number;
  significant: boolean;
}

export function compareGroups(group1: number[], group2: number[]): ComparisonResult {
  const mean1 = group1.reduce((a, b) => a + b) / group1.length;
  const mean2 = group2.reduce((a, b) => a + b) / group2.length;

  const var1 = group1.reduce((sum, val) => sum + Math.pow(val - mean1, 2), 0) / (group1.length - 1);
  const var2 = group2.reduce((sum, val) => sum + Math.pow(val - mean2, 2), 0) / (group2.length - 1);

  const pooledStdErr = Math.sqrt((var1 / group1.length) + (var2 / group2.length));
  const tStatistic = (mean1 - mean2) / pooledStdErr;

  // Approximate p-value using normal distribution
  const pValue = 2 * (1 - normalCDF(Math.abs(tStatistic)));

  const difference = mean1 - mean2;
  const percentChange = (difference / mean2) * 100;

  return {
    group1Mean: Number(mean1.toFixed(4)),
    group2Mean: Number(mean2.toFixed(4)),
    difference: Number(difference.toFixed(4)),
    percentChange: Number(percentChange.toFixed(2)),
    tStatistic: Number(tStatistic.toFixed(4)),
    pValue: Number(pValue.toFixed(4)),
    significant: pValue < 0.05
  };
}

/**
 * Standard normal CDF, via the Abramowitz & Stegun 7.1.26 rational
 * approximation to erf (|error| < 1.5e-7).
 *
 * The `/ Math.sqrt(2)` on the next line was missing. The identity is
 *
 *     Phi(z) = 0.5 * (1 + erf(z / sqrt(2)))
 *
 * and the old code fed `z` straight into erf, so it returned Phi(z*sqrt(2))
 * -- a distribution far too narrow. `compareGroups` uses this for its
 * two-sided p-value, so the effect was that p came out several times too
 * small and `significant` flipped true well below the threshold it claims:
 *
 *     |t| = 1.96  ->  reported p = 0.0056   (correct: 0.0500)
 *     |t| = 1.91  ->  reported p = 0.0069, "significant"  (correct: 0.0562,
 *                     NOT significant at 0.05)
 *
 * The real 0.05 cutoff is |t| = 1.96; the broken one was |t| = 1.386. Every
 * difference between those two was announced as statistically significant
 * when it was not. Checked against the closed-form values (Phi(1.96) =
 * 0.975002, Phi(2.5758) = 0.995) in the tests, not against itself.
 */
function normalCDF(z: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;

  const sign = z < 0 ? -1 : 1;
  const x = Math.abs(z) / Math.SQRT2;

  const t = 1 / (1 + p * x);
  const t2 = t * t;
  const t3 = t2 * t;
  const t4 = t3 * t;
  const t5 = t4 * t;

  // erf(x)
  const y = 1 - (((((a5 * t5) + (a4 * t4)) + (a3 * t3)) + (a2 * t2)) + (a1 * t)) *
    Math.exp(-x * x);

  return 0.5 * (1 + sign * y);
}

// ============================================================================
// SUMMARY STATISTICS
// ============================================================================

export interface SummaryStats {
  mean: number;
  median: number;
  stdDev: number;
  min: number;
  max: number;
  q1: number;
  q3: number;
  iqr: number;
  skewness: number;
  kurtosis: number;
}

export function calculateSummaryStats(values: number[]): SummaryStats {
  const sorted = [...values].sort((a, b) => a - b);
  const n = values.length;

  const mean = values.reduce((a, b) => a + b) / n;
  const median = n % 2 === 0
    ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    : sorted[Math.floor(n / 2)];

  const stdDev = Math.sqrt(values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / n);

  const min = sorted[0];
  const max = sorted[n - 1];

  const q1 = sorted[Math.floor(n / 4)];
  const q3 = sorted[Math.floor((3 * n) / 4)];
  const iqr = q3 - q1;

  const skewness = values.reduce((sum, val) => sum + Math.pow((val - mean) / stdDev, 3), 0) / n;
  const kurtosis = values.reduce((sum, val) => sum + Math.pow((val - mean) / stdDev, 4), 0) / n - 3;

  return {
    mean: Number(mean.toFixed(4)),
    median: Number(median.toFixed(4)),
    stdDev: Number(stdDev.toFixed(4)),
    min: Number(min.toFixed(4)),
    max: Number(max.toFixed(4)),
    q1: Number(q1.toFixed(4)),
    q3: Number(q3.toFixed(4)),
    iqr: Number(iqr.toFixed(4)),
    skewness: Number(skewness.toFixed(4)),
    kurtosis: Number(kurtosis.toFixed(4))
  };
}

// ============================================================================
// ANALYSIS REPORT GENERATION
// ============================================================================

export interface AnalysisReport {
  timestamp: string;
  dataPoints: number;
  correlations: CorrelationResult[];
  trends: TrendAnalysis[];
  outliers: OutlierResult[];
  summaryStats: Record<string, SummaryStats>;
  insights: string[];
}

export function generateAnalysisReport(data: DataPoint[]): AnalysisReport {
  const correlations = correlationMatrix(data);
  const trends = analyzeTrends(data);
  const summaryStats: Record<string, SummaryStats> = {};
  const insights: string[] = [];

  // Generate summary statistics and insights
  const numericKeys = Object.keys(data[0]).filter(k => typeof data[0][k] === 'number');

  for (const key of numericKeys) {
    const values = data.map(d => Number(d[key]));
    summaryStats[key] = calculateSummaryStats(values);

    const outliers = detectOutliers(values);
    if (outliers.length > 0) {
      insights.push(
        `⚠️ ${outliers.length} outlier(s) detected in ${key} (${(outliers.length / data.length * 100).toFixed(1)}%)`
      );
    }

    const trend = trends.find(t => t.variable === key);
    if (trend && trend.r_squared > 0.7) {
      insights.push(`📈 ${key} shows ${trend.direction} trend (R² = ${trend.r_squared})`);
    }
  }

  const strongCorr = correlations.filter(c => c.significance === 'strong');
  if (strongCorr.length > 0) {
    insights.push(
      `🔗 Strong correlations found: ${strongCorr.slice(0, 2).map(c => `${c.var1}↔${c.var2}`).join(', ')}`
    );
  }

  return {
    timestamp: new Date().toISOString(),
    dataPoints: data.length,
    correlations,
    trends,
    outliers: numericKeys.flatMap(k =>
      detectOutliers(data.map(d => Number(d[k]))).map(o => ({ ...o, variable: k }))
    ),
    summaryStats,
    insights
  };
}
