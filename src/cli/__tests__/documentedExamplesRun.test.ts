/**
 * The examples in `help` are run, not just read.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Three of the nine `Example:` lines the CLI prints could not work:
 *
 *   sweep --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s
 *     -> "Every point in the sweep failed. Query 'sweep' does not name a
 *        domain this pipeline knows" — the example omitted the model, and
 *        the code defaulted the model name to the literal string 'sweep'.
 *
 *   validate "lactate dehydrogenase km=5.2"
 *     -> "does not name a domain this pipeline knows", and separately the
 *        `validate` case never passed its flags through, so every required
 *        parameter was reported missing no matter what the user typed.
 *
 * Someone following the tool's own documentation got a total failure and
 * reasonably concluded the feature was broken. That is a fair reading: from
 * outside, an example that cannot work and a feature that does not work are
 * the same thing.
 *
 * WHY THE EXAMPLES ARE READ OUT OF `help` RATHER THAN LISTED HERE
 * --------------------------------------------------------------
 * A hardcoded copy of the examples would be a second source of truth, and it
 * would keep passing after someone edited the help text — verifying the copy,
 * which is the failure mode this repository keeps finding (ADR 0034, 0036).
 * The examples are extracted from the CLI's real `help` output, so editing
 * help is what this test checks.
 *
 * WHAT IT DELIBERATELY DOES NOT COVER
 * ----------------------------------
 * Only the examples that can succeed with no network and no prior state are
 * asserted to exit 0. The rest are listed below with the reason each is
 * excluded, because a guard that silently skips most of its subject is worse
 * than one that says how much of the world it looked at.
 */
import { execFileSync } from 'child_process';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

interface Run {
  stdout: string;
  code: number;
}

function runCli(args: string[]): Run {
  try {
    const stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120_000,
    });
    return { stdout, code: 0 };
  } catch (err) {
    const e = err as { stdout?: string; status?: number };
    return { stdout: e.stdout ?? '', code: e.status ?? 1 };
  }
}

const ANSI = /\x1b\[[0-9;]*m/g;

/** Split a shell-ish example into argv, honouring double quotes. */
function toArgv(example: string): string[] {
  return (example.match(/"[^"]*"|\S+/g) ?? []).map((t) =>
    t.startsWith('"') && t.endsWith('"') ? t.slice(1, -1) : t,
  );
}

/**
 * Examples that need something this test cannot supply. Each says WHY, so
 * that "excluded" never quietly becomes "forgotten".
 */
const NEEDS_MORE_THAN_A_CLEAN_CHECKOUT: Record<string, string> = {
  resolve: 'reaches BRENDA/PubMed over the network',
  literature: 'reaches PubMed and CrossRef over the network',
  corpus: 'needs a BRENDA bulk download the user fetched themselves',
  verify: 'the example job id job_001 is illustrative and has no record',
  'check-integrity': 'same illustrative job id',
};

let examples: string[];

beforeAll(() => {
  const help = runCli(['help']);
  expect(help.code).toBe(0);
  examples = help.stdout
    .replace(ANSI, '')
    .split('\n')
    .map((line) => line.match(/Example:\s*(.+)$/)?.[1]?.trim())
    .filter((x): x is string => Boolean(x));
});

jest.setTimeout(600_000);

describe('every documented example', () => {
  it('is extracted from help, and there are some', () => {
    // If the extraction silently found nothing, every assertion below would
    // vacuously pass. This is the check that the check is looking at anything.
    expect(examples.length).toBeGreaterThanOrEqual(5);
  });

  it('names a command the CLI actually dispatches', () => {
    // Cheap, covers all nine, and catches a renamed or deleted command.
    const known = new Set([
      'validate', 'simulate', 'verify', 'check-integrity',
      'resolve', 'corpus', 'sweep', 'history', 'literature', 'help',
    ]);
    for (const example of examples) {
      expect(known).toContain(toArgv(example)[0]!);
    }
  });
});

describe('the examples that need nothing but a checkout, succeed', () => {
  // Built at describe time from the extracted list rather than written out,
  // so a new offline example is covered the day it is added.
  const offline = () =>
    examples.filter((e) => !(toArgv(e)[0]! in NEEDS_MORE_THAN_A_CLEAN_CHECKOUT));

  it('runs each one and exits 0', () => {
    const failures: string[] = [];
    for (const example of offline()) {
      const argv = toArgv(example);
      const { code, stdout } = runCli(argv);
      if (code !== 0) {
        failures.push(
          `\n  $ scientific ${example}\n    exit ${code}\n` +
            `    ${stdout.replace(ANSI, '').trim().split('\n').slice(-3).join('\n    ')}`,
        );
      }
    }
    // Reported together: fixing one broken example at a time, re-running a
    // two-minute suite between each, is how the second one gets left.
    expect(failures.join('')).toBe('');
  });

  it('covers more than one command', () => {
    // Guards the exclusion list. If someone adds every command to
    // NEEDS_MORE_THAN_A_CLEAN_CHECKOUT to make this file green, the suite
    // above would pass over an empty set and prove nothing.
    const commands = new Set(offline().map((e) => toArgv(e)[0]!));
    expect(commands.size).toBeGreaterThanOrEqual(3);
  });
});
