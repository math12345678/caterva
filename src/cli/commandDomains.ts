import { spawnSync } from 'child_process';
import * as path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';
import { reconcileCatalogue, type CatalogueReport } from './domainCatalogue';

/**
 * `scientific domains` — what Caterva can simulate, and how to run each one.
 *
 * The list is asked of the ENGINE, not read from a file in this package.
 * `caterva_runner.py --list-domains` emits `DISPATCH`, the table the engine
 * actually dispatches on, so a domain cannot appear here unless it really
 * runs — and cannot be missing here just because nobody updated a doc.
 *
 * That distinction has a history in this repository: the runner's own
 * membership test and its call site once indexed two different tables "kept
 * equal by hand", and they diverged.
 */

const RUNNER = path.join(
  REPO_ROOT,
  'Science-Agent-Pipeline',
  'artifacts',
  'api-server',
  'src',
  'lib',
  'caterva_runner.py',
);

export interface DomainsOptions {
  json?: boolean;
}

const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';
const YELLOW = '\x1b[33m';

/** Ask the engine. Returns null when it could not be asked at all. */
export function dispatchIdsFromEngine(): string[] | null {
  const result = spawnSync(
    resolvePythonExecutable(REPO_ROOT),
    [RUNNER, '--list-domains'],
    {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      // The runner imports `caterva`, which lives at the repository root.
      env: { ...process.env, PYTHONPATH: REPO_ROOT },
      timeout: 60_000,
    },
  );
  if (result.status !== 0 || !result.stdout) return null;
  try {
    const parsed = JSON.parse(result.stdout.trim().split('\n').pop() ?? '');
    if (parsed?.ok !== true || !Array.isArray(parsed.domains)) return null;
    return parsed.domains as string[];
  } catch {
    return null;
  }
}

export function commandDomains(options: DomainsOptions = {}): number {
  const ids = dispatchIdsFromEngine();

  if (ids === null) {
    // "Could not ask" is not "there are none". Printing an empty or
    // hardcoded list here would be the exact failure this command exists to
    // correct, one level up: a catalogue that looks authoritative and was
    // never checked against anything.
    process.stderr.write(
      `${YELLOW}✗${RESET} Could not ask the engine which domains it has.\n` +
        `${DIM}  The list is read from the engine rather than written down here,\n` +
        `  so without it there is nothing honest to print. Run \`make doctor\`\n` +
        `  to check the Python environment.${RESET}\n`,
    );
    return 1;
  }

  const report: CatalogueReport = reconcileCatalogue(ids);

  if (options.json === true) {
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
    return report.undescribed.length > 0 || report.phantom.length > 0 ? 1 : 0;
  }

  process.stdout.write(
    `\n${BOLD}Caterva can simulate ${report.entries.length} things.${RESET}\n` +
      `${DIM}Each line below is a command that runs. Values are examples, not defaults —\n` +
      `Caterva has no defaults for measured quantities.${RESET}\n\n`,
  );

  for (const entry of report.entries) {
    const backed = entry.literatureBacked
      ? `${DIM} · parameters resolvable from literature${RESET}`
      : '';
    process.stdout.write(`${BOLD}${entry.title}${RESET}${backed}\n`);
    process.stdout.write(`${DIM}  ${entry.summary}${RESET}\n`);
    process.stdout.write(`    ${entry.example}\n\n`);
  }

  // Reported, never hidden. A domain the engine runs and this file does not
  // describe is a domain no student can find, which is the whole defect.
  if (report.undescribed.length > 0) {
    process.stderr.write(
      `${YELLOW}⚠${RESET} The engine also dispatches ${report.undescribed.length} domain(s) ` +
        `nothing here describes:\n    ${report.undescribed.join(', ')}\n` +
        `${DIM}  They run, and no student can discover them. Add them to\n` +
        `  src/cli/domainCatalogue.ts.${RESET}\n`,
    );
  }
  if (report.phantom.length > 0) {
    process.stderr.write(
      `${YELLOW}⚠${RESET} ${report.phantom.length} entr(y/ies) here name a domain the engine ` +
        `does not have:\n    ${report.phantom.join(', ')}\n` +
        `${DIM}  Their example commands cannot run. A catalogue that lists what the\n` +
        `  tool cannot do teaches a reader to distrust the rest of it.${RESET}\n`,
    );
  }

  return report.undescribed.length > 0 || report.phantom.length > 0 ? 1 : 0;
}
