import { spawnSync } from 'child_process';
import * as path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';

/**
 * `scientific ensemble` — what the literature actually supports, as a band.
 *
 * THE COMMAND THIS PRODUCT IS FOR
 * -------------------------------
 * Asked whether "flag it, don't use it" is right for a value with missing
 * assay conditions, Prof. Barbara Bakker answered:
 *
 *   "In practice, we chose the best option, but do not exclude anything a
 *    priori [...] These scores were then used to give the parameter a weight
 *    in the sampling."
 *
 * and Prof. Herbert Sauro, told about both options:
 *
 *   "With Jessie's approach you don't get any simulation, with Barbara's you
 *    can sample and get an ensemble distribution. That is the right way to
 *    do it."
 *
 * Everywhere else in Caterva, a Km the literature disagrees about becomes
 * one number chosen by `min()` — or stops the run. This command runs the
 * model once per published value, weighted by how well evidenced each is,
 * and shows the envelope.
 *
 * WHY IT SHELLS OUT RATHER THAN REIMPLEMENTING
 * --------------------------------------------
 * The weighting needs per-candidate reliability scores, which live in the
 * Python literature layer beside `score_reliability` — the same function the
 * single-value path grades its winner with. A TypeScript reimplementation
 * would be a second implementation of the sampling, which is ADR 0027's
 * defect and the reason `reliabilityScore.ts` was deleted rather than kept
 * "just in case".
 *
 * Same shape as `commandDomains`: ask the side that knows, render here.
 */

const ENSEMBLE = path.join(REPO_ROOT, 'Tests', 'ensemble.py');

const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';
const YELLOW = '\x1b[33m';

export interface EnsembleOptions {
  /** A saved BRENDA table. Omit to resolve live — see commandEnsemble. */
  fixture?: string;
  /** Enzyme name for a live lookup, when no fixture is given. */
  enzyme?: string;
  substrate: string;
  organism?: string;
  ec?: string;
  seed: number;
  draws?: number;
  simulate?: string;
  points?: number;
  json?: boolean;
}

interface Candidate {
  value: number;
  unit: string | null;
  probability: number;
  referenceId: string | null;
  conditions: string | null;
  grades: string[];
}

interface Envelope {
  column: string;
  times: number[];
  low: number[];
  median: number[];
  high: number[];
}

interface EnsemblePayload {
  ok: boolean;
  error?: string;
  substrate: string;
  organism: string;
  rows: number;
  frontier: number;
  seed: number;
  disclaimer: string;
  candidates: Candidate[];
  summary: Record<string, number | null>;
  band?: {
    swept: string[];
    succeeded: number;
    attempted: number;
    supportNote: string;
    envelopes: Envelope[];
  };
}

export function runEnsemble(options: EnsembleOptions): EnsemblePayload | null {
  const args = [
    ENSEMBLE,
    '--substrate', options.substrate,
    '--seed', String(options.seed),
    '--json',
  ];
  if (options.fixture) args.push('--fixture', options.fixture);
  if (options.enzyme) args.push('--enzyme', options.enzyme);
  if (options.organism) args.push('--organism', options.organism);
  if (options.ec) args.push('--ec', options.ec);
  if (options.draws) args.push('--draws', String(options.draws));
  if (options.simulate) args.push('--simulate', options.simulate);
  if (options.points) args.push('--points', String(options.points));

  const result = spawnSync(resolvePythonExecutable(REPO_ROOT), args, {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: REPO_ROOT },
    timeout: 300_000,
  });
  if (!result.stdout) return null;
  try {
    return JSON.parse(result.stdout.trim()) as EnsemblePayload;
  } catch {
    return null;
  }
}

/**
 * `run` is injectable, and that is not a test convenience.
 *
 * `commandEnsemble` called `runEnsemble` directly, and a module mock could
 * not intercept it -- an internal call does not go through the module
 * object. The choice was to test the rendering through a real subprocess on
 * every case (slow, and it would conflate a rendering regression with a
 * resolver one) or to make the seam explicit. The seam is explicit.
 *
 * The Python side is exercised for real elsewhere: `test_ensemble_boundary`
 * spawns the runner, `test_ensemble` pins the weighting. What is injected
 * here is only the transport.
 */
export function commandEnsemble(
  options: EnsembleOptions,
  run: (o: EnsembleOptions) => EnsemblePayload | null = runEnsemble,
): number {
  const payload = run(options);

  if (payload === null) {
    // "Could not ask" is not "there is no ensemble". Printing an empty band
    // here would be the defect this whole command exists to remove, one
    // level up.
    process.stderr.write(
      `${YELLOW}✗${RESET} Could not run the ensemble.\n` +
        `${DIM}  The weighting lives in the Python literature layer, so without it\n` +
        `  there is nothing honest to print. Run \`make doctor\`.${RESET}\n`,
    );
    return 1;
  }
  if (payload.ok !== true) {
    process.stderr.write(`${YELLOW}✗${RESET} ${payload.error ?? 'the ensemble failed'}\n`);
    return 2;
  }

  if (options.json === true) {
    process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
    return 0;
  }

  const { candidates, summary, band } = payload;

  process.stdout.write(
    `\n${BOLD}The literature does not agree on this value.${RESET}\n` +
      `${DIM}${payload.rows} published row(s); ${payload.frontier} survive the ` +
      `evidence ranking.${RESET}\n\n`,
  );

  for (const c of candidates) {
    const unit = c.unit ? ` ${c.unit}` : '';
    const ref = c.referenceId ? `  ${DIM}[ref ${c.referenceId}]${RESET}` : '';
    process.stdout.write(
      `  ${BOLD}${c.value}${unit}${RESET}   drawn ${(c.probability * 100).toFixed(1)}% ` +
        `of the time${ref}\n` +
        `${DIM}      ${c.grades.join(' / ')}${RESET}\n`,
    );
    if (c.conditions) {
      process.stdout.write(`${DIM}      ${c.conditions.slice(0, 64)}${RESET}\n`);
    }
  }

  const fold = summary['fold_range'];
  process.stdout.write(
    `\n  ${BOLD}Spread${RESET} ${summary['low']} to ${summary['high']}` +
      (typeof fold === 'number' ? `, a ${fold.toPrecision(3)}-fold range` : '') +
      `   ${DIM}(median ${summary['median']})${RESET}\n`,
  );

  if (band) {
    // The parameter spread says the literature disagrees. The band says how
    // much that disagreement matters to the answer, which is the only one of
    // the two a student can act on.
    process.stdout.write(
      `\n${BOLD}What that does to the simulation${RESET}\n` +
        `${DIM}  ${band.supportNote}${RESET}\n`,
    );
    for (const envelope of band.envelopes) {
      const widths = envelope.low.map((lo, i) => (envelope.high[i] ?? lo) - lo);
      const widest = widths.indexOf(Math.max(...widths));
      if ((widths[widest] ?? 0) <= 0) {
        process.stdout.write(`${DIM}  ${envelope.column}: identical across every run.${RESET}\n`);
        continue;
      }
      // The widest point, not the whole table. A student wants to know where
      // the choice of paper matters most; a column of near-identical rows
      // buries that under arithmetic.
      process.stdout.write(
        `  ${BOLD}${envelope.column}${RESET} differs most at t=${envelope.times[widest]}: ` +
          `${envelope.low[widest]?.toPrecision(4)} to ${envelope.high[widest]?.toPrecision(4)}\n`,
      );
    }
  }

  // Never optional. ADR 0024 declined sampling because a spread with no
  // validation step reads as an uncertainty estimate; the answer is to make
  // the sentence inseparable from the numbers, not to drop the numbers.
  process.stdout.write(`\n${DIM}${payload.disclaimer}${RESET}\n`);
  process.stdout.write(
    `${DIM}Reproduce with --seed ${payload.seed}.${RESET}\n\n`,
  );
  return 0;
}
