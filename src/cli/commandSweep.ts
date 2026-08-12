/**
 * `scientific sweep` — run the model across a range of one parameter and
 * say what the curve does.
 *
 * A sweep that prints a column of numbers is a spreadsheet. What makes it
 * worth having here is that the numbers get interpreted: `advanced-analytics`
 * (363 lines that nothing imported) provides trend detection, outlier
 * detection and summary statistics, so the output can answer the question
 * behind the sweep rather than just supplying the data for it.
 *
 * The specific question a teaching lab asks is *where does the behaviour
 * change* — where does the reaction stop being substrate-limited, where
 * does adding more inhibitor stop mattering. A monotonic trend with a
 * flattening tail says something a table of 20 rows does not.
 */

import {
  analyzeTrends,
  calculateSummaryStats,
  detectOutliers,
} from '../analysis/advanced-analytics';
import { parameterSweep, type SweepPoint } from './advanced-features';
import type { ParameterProvenance } from './commandSimulateResolved';

const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';

const useColour = process.stdout.isTTY === true;
const c = (code: string, text: string): string =>
  useColour ? `${code}${text}${RESET}` : text;

export interface SweepOptions {
  query: string;
  /** Which parameter to vary. */
  parameter: string;
  min: number;
  max: number;
  step: number;
  /** Everything the model needs that is NOT being swept. */
  baseParameters: Record<string, number>;
  provenance: ParameterProvenance[];
  request: Record<string, unknown>;
  json: boolean;
}

/** A simple sparkline, so the shape is visible without a plotting library. */
function sparkline(values: number[]): string {
  const blocks = '▁▂▃▄▅▆▇█';
  const usable = values.filter((v) => Number.isFinite(v));
  if (usable.length === 0) return '';
  const low = Math.min(...usable);
  const high = Math.max(...usable);
  const span = high - low;

  return values
    .map((v) => {
      if (!Number.isFinite(v)) return '·'; // a point that could not be computed
      if (span === 0) return blocks[0];
      const index = Math.round(((v - low) / span) * (blocks.length - 1));
      return blocks[index];
    })
    .join('');
}

export async function commandSweep(options: SweepOptions): Promise<number> {
  let points: SweepPoint[];
  try {
    points = await parameterSweep(
      options.query,
      options.parameter,
      options.min,
      options.max,
      options.step,
      options.baseParameters,
      options.request,
    );
  } catch (err) {
    process.stderr.write(
      `${c(RED, '✗')} ${err instanceof Error ? err.message : String(err)}\n`,
    );
    return 2;
  }

  const computed = points.filter((p) => !p.failed);
  const failed = points.filter((p) => p.failed);

  if (options.json) {
    process.stdout.write(
      JSON.stringify(
        { ok: computed.length > 0, parameter: options.parameter, points, provenance: options.provenance },
        null,
        2,
      ) + '\n',
    );
    return computed.length > 0 ? 0 : 2;
  }

  // Every point failing is not an empty result -- it is a broken run, and
  // the original code returned [] for both.
  if (computed.length === 0) {
    process.stderr.write(
      `${c(RED, '✗')} Every point in the sweep failed. The first reason was:\n` +
        `    ${failed[0]?.failed ?? 'unknown'}\n`,
    );
    return 2;
  }

  const values = computed.map((p) => p.finalValue);
  const stats = calculateSummaryStats(values);

  process.stdout.write(
    `\n${c(BOLD, `Sweep: ${options.parameter} from ${options.min} to ${options.max} step ${options.step}`)}\n\n`,
  );

  const width = Math.max(...points.map((p) => String(p.paramValue).length), 5);
  for (const point of points) {
    if (point.failed) {
      process.stdout.write(
        `  ${String(point.paramValue).padStart(width)}  ${c(RED, 'failed')}  ${c(DIM, point.failed.slice(0, 60))}\n`,
      );
      continue;
    }
    process.stdout.write(
      `  ${String(point.paramValue).padStart(width)}  ${point.finalValue.toFixed(4)}\n`,
    );
  }

  process.stdout.write(`\n  ${c(DIM, 'shape')}  ${sparkline(points.map((p) => p.finalValue))}\n`);

  // --- interpretation, which is the reason this is not a spreadsheet ---
  const trend = analyzeTrends(
    computed.map((p) => ({ x: p.paramValue, y: p.finalValue })),
  ).find((t) => t.variable === 'y');

  if (trend) {
    process.stdout.write(
      `  ${c(DIM, 'trend')}  ${trend.direction}${
        typeof trend.slope === 'number' ? c(DIM, `  (slope ${trend.slope.toExponential(2)})`) : ''
      }\n`,
    );
  }

  process.stdout.write(
    `  ${c(DIM, 'range')}  ${stats.min.toFixed(4)} … ${stats.max.toFixed(4)}` +
      `${c(DIM, `   mean ${stats.mean.toFixed(4)}  sd ${stats.stdDev.toFixed(4)}`)}\n`,
  );

  const outliers = detectOutliers(values);
  const flagged = outliers.filter((o) => o.isOutlier);
  if (flagged.length > 0) {
    process.stdout.write(
      `\n${c(YELLOW, '•')} ${c(BOLD, 'Points that break the pattern:')}\n`,
    );
    for (const outlier of flagged) {
      const point = computed[outliers.indexOf(outlier)];
      process.stdout.write(
        `    ${options.parameter}=${point?.paramValue}: ${outlier.value.toFixed(4)} ` +
          `${c(DIM, `(${outlier.zscore.toFixed(1)}σ from the mean)`)}\n`,
      );
    }
    process.stdout.write(
      `${c(DIM, '    Often where the model stops behaving the way the rest of the')}\n` +
        `${c(DIM, '    range does — worth looking at rather than averaging away.')}\n`,
    );
  }

  if (failed.length > 0) {
    process.stdout.write(
      `\n${c(YELLOW, '⚠')} ${failed.length} of ${points.length} points could not be computed ` +
        `${c(DIM, '(shown as · in the shape line).')}\n`,
    );
  }

  process.stdout.write('\n');
  return 0;
}
