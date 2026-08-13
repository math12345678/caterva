/**
 * Advanced analytics: the numbers, checked against closed forms.
 *
 * This module had no test file at all, and the two things it is actually
 * used for -- deciding whether a difference is statistically significant,
 * and saying WHICH sweep point is anomalous -- were both wrong.
 *
 * The p-value tests below compare against the standard normal distribution
 * evaluated exactly, not against the module's own output. That is the only
 * kind of check that could have caught the missing `/ sqrt(2)` in
 * `normalCDF`: every internal consistency property (symmetry, monotonicity,
 * CDF(0) = 0.5, p in [0, 1]) held perfectly while the distribution was the
 * wrong width.
 */

import {
  compareGroups,
  detectOutliers,
  calculateSummaryStats,
  calculatePearsonCorrelation,
  analyzeTrends,
} from '../advanced-analytics';

/**
 * A pair of groups whose Welch t-statistic is exactly `t`.
 *
 * group1 is [-1, +1] repeated (mean 0, sample variance 10/9), group2 is the
 * same series shifted, so pooledStdErr = sqrt(2 * (10/9) / 10) = sqrt(2/9)
 * and t = -shift / sqrt(2/9). Constructing the input from the target
 * statistic keeps the test honest about what it is probing: the assertion
 * on `tStatistic` below fails first if this construction is wrong, so a
 * p-value assertion can never pass for the wrong reason.
 */
function groupsWithTStatistic(t: number): { a: number[]; b: number[] } {
  const a = Array.from({ length: 10 }, (_, i) => (i % 2 === 0 ? -1 : 1));
  const shift = t * Math.sqrt(2 / 9);
  return { a, b: a.map((v) => v + shift) };
}

describe('advanced analytics', () => {
  describe('compareGroups p-values', () => {
    // Exact two-sided normal tail probabilities, 2 * (1 - Phi(z)).
    // Independent of this codebase: Phi(1.959964) = 0.975 and
    // Phi(2.575829) = 0.995 are the textbook 95% and 99% critical values.
    const CASES: Array<{ t: number; p: number; label: string }> = [
      { t: 1.0, p: 0.3173105, label: 'one standard error' },
      { t: 1.5, p: 0.1336144, label: 'one and a half standard errors' },
      { t: 1.959964, p: 0.05, label: 'the 95% critical value' },
      { t: 2.575829, p: 0.01, label: 'the 99% critical value' },
    ];

    for (const { t, p, label } of CASES) {
      it(`matches the normal tail probability at ${label} (t = ${t})`, () => {
        const { a, b } = groupsWithTStatistic(t);
        const result = compareGroups(a, b);

        expect(Math.abs(result.tStatistic)).toBeCloseTo(t, 3);
        expect(result.pValue).toBeCloseTo(p, 4);
      });
    }

    it('reports a symmetric p-value at t = 0', () => {
      const { a, b } = groupsWithTStatistic(0);
      const result = compareGroups(a, b);

      expect(result.tStatistic).toBeCloseTo(0, 6);
      expect(result.pValue).toBeCloseTo(1, 4);
      expect(result.significant).toBe(false);
    });

    // The concrete consequence of the missing / sqrt(2): the real 0.05
    // cutoff is |t| = 1.96, the broken one was |t| = 1.386. Everything in
    // between was announced as significant when it is not.
    it('does not call a 1.5-sigma difference significant', () => {
      const { a, b } = groupsWithTStatistic(1.5);
      const result = compareGroups(a, b);

      expect(result.significant).toBe(false);
      expect(result.pValue).toBeGreaterThan(0.05);
    });

    it('still calls a 3-sigma difference significant', () => {
      const { a, b } = groupsWithTStatistic(3);
      const result = compareGroups(a, b);

      expect(result.significant).toBe(true);
      expect(result.pValue).toBeCloseTo(0.0026998, 5);
    });
  });

  describe('detectOutliers', () => {
    // `index` is the index into the array that was passed in. commandSweep
    // relies on exactly this to say which parameter value the anomaly
    // belongs to; it previously used the position within the returned
    // (already filtered) list and attributed the anomaly to the wrong point.
    it('reports the index into the input array, not into the returned list', () => {
      const values = [1.0, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08, 50];

      const outliers = detectOutliers(values);

      expect(outliers).toHaveLength(1);
      expect(outliers[0].index).toBe(9);
      expect(outliers[0].value).toBe(50);
      expect(values[outliers[0].index]).toBe(outliers[0].value);
    });

    it('returns only points past the threshold, each with a matching value', () => {
      const values = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 200, 10, 10];

      const outliers = detectOutliers(values);

      expect(outliers.length).toBeGreaterThan(0);
      for (const outlier of outliers) {
        expect(outlier.isOutlier).toBe(true);
        expect(values[outlier.index]).toBe(outlier.value);
      }
    });

    it('finds nothing in a perfectly flat series', () => {
      expect(detectOutliers([5, 5, 5, 5, 5])).toEqual([]);
    });
  });

  describe('analyzeTrends', () => {
    // One point gives a zero denominator, so slope is NaN; every comparison
    // against NaN is false and the ternary fell through to 'decreasing'.
    // A direction is a claim, and one observation cannot support one.
    it('refuses to name a direction from a single data point', () => {
      const trends = analyzeTrends([{ y: 2.5 }]);

      expect(trends).toHaveLength(1);
      expect(trends[0].direction).toBe('indeterminate');
      expect(trends[0].direction).not.toBe('decreasing');
    });

    it('calls a genuinely flat series stable, not indeterminate', () => {
      const trends = analyzeTrends([{ y: 2.5 }, { y: 2.5 }, { y: 2.5 }]);

      expect(trends[0].direction).toBe('stable');
      expect(trends[0].slope).toBe(0);
    });

    it('recovers the slope of an exact line', () => {
      // y = 2x + 1 sampled at x = 1..5, and linearRegression indexes x from 1.
      const trends = analyzeTrends([{ y: 3 }, { y: 5 }, { y: 7 }, { y: 9 }, { y: 11 }]);

      expect(trends[0].direction).toBe('increasing');
      expect(trends[0].slope).toBeCloseTo(2, 6);
      expect(trends[0].r_squared).toBeCloseTo(1, 6);
    });

    it('detects a decreasing series', () => {
      const trends = analyzeTrends([{ y: 11 }, { y: 9 }, { y: 7 }, { y: 5 }, { y: 3 }]);

      expect(trends[0].direction).toBe('decreasing');
      expect(trends[0].slope).toBeCloseTo(-2, 6);
    });
  });

  describe('summary statistics', () => {
    it('matches hand-computed values for 1..9', () => {
      const stats = calculateSummaryStats([1, 2, 3, 4, 5, 6, 7, 8, 9]);

      expect(stats.mean).toBe(5);
      expect(stats.median).toBe(5);
      expect(stats.min).toBe(1);
      expect(stats.max).toBe(9);
      // Population standard deviation of 1..9 is sqrt(60/9) = 2.581989.
      expect(stats.stdDev).toBeCloseTo(2.582, 3);
      // A symmetric series has zero skew.
      expect(stats.skewness).toBeCloseTo(0, 6);
    });

    it('averages the middle pair for an even-length series', () => {
      expect(calculateSummaryStats([1, 2, 3, 4]).median).toBe(2.5);
    });
  });

  describe('Pearson correlation', () => {
    it('is exactly 1 for a perfect positive linear relation', () => {
      expect(calculatePearsonCorrelation([1, 2, 3, 4], [2, 4, 6, 8])).toBeCloseTo(1, 10);
    });

    it('is exactly -1 for a perfect negative linear relation', () => {
      expect(calculatePearsonCorrelation([1, 2, 3, 4], [8, 6, 4, 2])).toBeCloseTo(-1, 10);
    });

    it('is 0 when one series is constant', () => {
      expect(calculatePearsonCorrelation([1, 2, 3, 4], [7, 7, 7, 7])).toBe(0);
    });
  });
});
