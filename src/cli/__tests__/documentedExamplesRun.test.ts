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
import * as fs from 'fs';
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
  report:
    'resolves a real Km from BRENDA and the organism from NCBI Taxonomy, ' +
    'so it needs four services reachable at that instant. The offline ' +
    'route is --fixture (ADR 0149), which the help example deliberately ' +
    'does not use because it documents the live command.',
  ensemble:
    'samples the published values for the enzyme, which means a BRENDA ' +
    'lookup over the network.',
};

let examples: string[];

beforeAll(() => {
  const help = runCli(['help']);
  expect(help.code).toBe(0);
  // Continuation lines are JOINED. `Example:` lines that end in a
  // backslash carry the rest of the command on the next line, exactly as a
  // shell would, and two of them do -- `report` and `ensemble`.
  //
  // Matching one line and stopping produced an argv missing every flag
  // after the backslash, so the CLI refused a request that was genuinely
  // incomplete and the test blamed the documentation. `report` exits 1 with
  // "report needs an enzyme, an organism and a substrate" because the
  // extractor threw away `--substrate`, `--s0` and `--vmax`. The example in
  // help is correct and always was.
  //
  // Tenth instance in this repository of a matcher narrower than its
  // subject (ADR 0144's `^\|` anchor, ADR 0153's five front doors); this
  // one is in a test whose own header explains that a second source of
  // truth would "keep passing after someone edited the help text".
  const plain = help.stdout.replace(ANSI, '').split('\n');
  examples = [];
  for (let i = 0; i < plain.length; i += 1) {
    const first = plain[i]!.match(/Example:\s*(.+)$/)?.[1]?.trim();
    if (!first) continue;
    let command = first;
    // A trailing backslash means the command continues. Consume following
    // lines until one does not end in a backslash. Bounded by the array
    // length, so a help text ending mid-continuation cannot spin.
    while (command.endsWith('\\') && i + 1 < plain.length) {
      i += 1;
      command = `${command.slice(0, -1).trim()} ${plain[i]!.trim()}`;
    }
    examples.push(command);
  }
});

jest.setTimeout(600_000);

describe('every documented example', () => {
  it('is extracted from help, and there are some', () => {
    // If the extraction silently found nothing, every assertion below would
    // vacuously pass. This is the check that the check is looking at anything.
    expect(examples.length).toBeGreaterThanOrEqual(5);
  });

  it('joins a backslash-continued example instead of truncating it', () => {
    // The extractor fix needs its own assertion. Excluding `report` and
    // `ensemble` from the run-it list ALSO turns this file green, and it
    // would leave the truncation in place -- every continued example
    // silently reduced to its first line, which is how the bug read as
    // "the documentation is wrong" for as long as it existed.
    //
    // Asserted on the flags that live AFTER the backslash. A continued
    // example is only correctly extracted if they survived.
    const continued = examples.filter((e) => e.startsWith('report '));
    expect(continued).toHaveLength(1);
    expect(continued[0]).toContain('--substrate');
    expect(continued[0]).toContain('--vmax');
    // And no example may still carry the continuation marker itself.
    for (const example of examples) {
      expect(example).not.toContain('\\');
    }
  });

  it('names a command the CLI actually dispatches', () => {
    // READ OUT OF THE DISPATCH SWITCH, not listed here. The hardcoded
    // version of this set is the defect this file's own header warns
    // about -- "a hardcoded copy would be a second source of truth, and
    // it would keep passing after someone edited the help text" -- and it
    // was four lines below that paragraph.
    //
    // It had drifted exactly as predicted, and in the direction that
    // matters: it named ten commands, one of which (`help`) is not a case
    // label at all, and MISSED FOUR the CLI really dispatches --
    // `report`, `ensemble`, `catalog`, `domains`. `report` is the command
    // START_HERE and `make demo` both tell a new user to run. So the test
    // written to prove the documented examples are real was rejecting the
    // flagship one, and its comment said "covers all nine" while listing
    // ten.
    //
    // Same extraction as scripts/check_cli_surface_documented.py, which
    // has read the switch this way all along: four-space-indented
    // `case '...':` in the one file that parses argv.
    const source = fs.readFileSync(CLI, 'utf-8');
    const dispatched = new Set(
      [...source.matchAll(/^ {4}case '([a-z][a-z0-9-]*)':/gm)].map((m) => m[1]!),
    );

    // `help` is real and is NOT a case label -- scientificCLI.ts handles it
    // before the switch, alongside `--help`/`-h`/no-args. Added explicitly
    // rather than by loosening the pattern, because widening the regex to
    // catch it would also catch every case label in every nested switch.
    dispatched.add('help');

    // If the extraction broke, `dispatched` would be small or empty and
    // every assertion below would fail for the wrong reason -- or, worse,
    // an empty set with no examples would pass. The CLI has thirteen case
    // labels today; asserting a floor catches a regex that silently
    // stopped matching without pinning the number as it grows.
    expect(dispatched.size).toBeGreaterThanOrEqual(11);

    for (const example of examples) {
      expect([...dispatched]).toContain(toArgv(example)[0]!);
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
