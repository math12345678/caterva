/**
 * A refusal must hand you the command that works.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Used the way a student uses it, Caterva took three attempts and six flags
 * before producing a single number:
 *
 *   simulate "lactate dehydrogenase"
 *     -> does not name a domain this pipeline knows
 *   simulate "michaelis menten" --resolve --substrate ... --organism ... --enzyme ...
 *     -> Cannot run: vmax, s0
 *   ...and the refusal never said what to type.
 *
 * That is Sauro's objection in ADR 0024, still open: a tool that refuses
 * pushes people to "hardcode a number with no warning at all". A student
 * stuck on `[E]0` searches for a plausible enzyme concentration, pastes it,
 * and now holds an unsourced parameter with no record of where it came from
 * — worse than anything the refusal was protecting them from.
 *
 * The refusal is unchanged. Nothing is defaulted. What changed is that the
 * next step is on screen.
 *
 * THE ASSERTION THAT MATTERS
 * --------------------------
 * Not that a "What to do next" section is printed — a section full of
 * plausible-looking flags that do not work would satisfy that and be worse
 * than silence. ADR 0070 is the precedent: the CLI's own `help` examples
 * could not run for months.
 *
 * So the test EXTRACTS the suggested flags and RUNS them, and requires that
 * the run gets further than it did before. A suggestion that reproduces the
 * same blocker is a suggestion that did nothing.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

let tmpDir: string;
let stub: string;

function runCli(args: string[]): { stdout: string; code: number } {
  try {
    const stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, CATERVA_LITERATURE_RUNNER: stub },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120_000,
    });
    return { stdout, code: 0 };
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string; status?: number; signal?: string };
    if (e.status === undefined || e.status === null) {
      // A process killed by a signal has NO exit status. Coercing that to 1
      // — `e.status ?? 1` — reports it as the CLI's "could not perform the
      // lookup" code, and the first run of this file failed exactly that
      // way under load: a ts-node spawn was killed, surfaced as `code 1`,
      // and looked like a product bug in the refusal path.
      //
      // An environment failure must not be able to impersonate a result.
      // That is the same rule this project applies to its own exit codes.
      throw new Error(
        `CLI did not exit cleanly (killed, not a real exit code): ` +
          `signal=${e.signal} stderr=${(e.stderr ?? '').slice(0, 400)}`,
      );
    }
    return { stdout: e.stdout ?? '', code: e.status };
  }
}

const ANSI = /\x1b\[[0-9;]*m/g;

/** Km resolves; nothing else does. The ordinary shape of a first run. */
beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-next-'));
  stub = path.join(tmpDir, 'stub.py');
  fs.writeFileSync(
    stub,
    [
      'import json, sys',
      'p = json.loads(sys.stdin.read() or "{}")',
      'if p.get("quantity") == "km":',
      '    out = {"ok": True, "found": True, "km": 10.73, "unit": "mM",',
      '           "organism": "Homo sapiens", "source": "brenda_exact",',
      '           "citation": {"source": "BRENDA", "reference_id": "740253"},',
      '           "logs": []}',
      'else:',
      '    out = {"ok": True, "found": False, "logs": []}',
      'sys.stdout.write(json.dumps(out))',
    ].join('\n'),
    'utf-8',
  );
});

afterAll(() => fs.rmSync(tmpDir, { recursive: true, force: true }));

jest.setTimeout(600_000);

const SYSTEM = [
  'simulate', 'michaelis menten', '--resolve',
  '--substrate', 'pyruvate',
  '--organism', 'Homo sapiens',
  '--enzyme', 'lactate dehydrogenase',
];

/** Flags the guidance suggested, as argv. */
function suggestedFlags(stdout: string): string[] {
  const clean = stdout.replace(ANSI, '');
  const section = clean.split('What to do next')[1] ?? '';
  const argv: string[] = [];
  // `--flag value` lines, one per suggestion. `--cite x="..."` and bare
  // switches are excluded here: this extracts the minimal set that makes
  // the run progress, not every option offered.
  //
  // `[a-z0-9-]` and not `[a-z-]`. The first version omitted digits, so it
  // matched `--enzyme-conc` and silently skipped `--s0` and `--i0` — the
  // extraction looked like it worked, returned one flag instead of two, and
  // the failure surfaced later as "the suggestion did not fix s0". A pattern
  // that matches a subset while looking complete is the same defect this
  // project keeps finding in guards.
  for (const m of section.matchAll(/^\s{4}(--[a-z0-9-]+) (\S+)$/gm)) {
    argv.push(m[1]!, m[2]!);
  }
  return argv;
}

describe('a refusal explains the next step', () => {
  it('prints a what-to-do-next section naming both kinds of blocker', () => {
    const { stdout, code } = runCli(SYSTEM);
    expect(code).toBe(2);
    const clean = stdout.replace(ANSI, '');

    expect(clean).toContain('What to do next');
    // The distinction is the substance: a value you choose is not a gap in
    // Caterva's coverage, and saying so is what stops a student treating it
    // as one.
    expect(clean).toMatch(/describe YOUR experiment/i);
    expect(clean).toMatch(/--enzyme-conc/);
    expect(clean).toMatch(/--s0/);
  });

  it('suggests flags that actually advance the run', () => {
    // The assertion ADR 0070 exists for. Extract, run, require progress.
    const first = runCli(SYSTEM);
    expect(first.code).toBe(2);

    const extra = suggestedFlags(first.stdout);
    expect(extra.length).toBeGreaterThan(0);

    const second = runCli([...SYSTEM, ...extra]);
    const secondClean = second.stdout.replace(ANSI, '');

    // It must not stop on the SAME blockers. Advancing to a different
    // blocker is progress; repeating one means the suggestion was noise.
    expect(secondClean).not.toMatch(/s0 \(an experimental condition/);
    expect(secondClean).not.toMatch(/needs --enzyme-conc/);
  });

  it('reaches a real simulation once the remaining gap is supplied', () => {
    // The chain has to terminate. With the conditions chosen and the one
    // literature gap supplied, the run completes and the Km is still the
    // cited one — the guidance must not have quietly replaced a resolved
    // value with a user-typed one.
    const { stdout, code } = runCli([...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s']);
    expect(code).toBe(0);
    const clean = stdout.replace(ANSI, '');
    expect(clean).toMatch(/km\s+10\.73 mM\s+brenda_exact/);
    expect(clean).toContain('740253');
  });

  it('offers citing a source, not just typing a number', () => {
    // For a literature gap the useful advice is different: record where the
    // number came from. `--cite` already existed and nothing pointed at it
    // from the one screen where a student needs it.
    const { stdout } = runCli([...SYSTEM, '--enzyme-conc', '0.01mM', '--s0', '10mM']);
    const clean = stdout.replace(ANSI, '');
    expect(clean).toMatch(/did not yield/i);
    expect(clean).toMatch(/--cite vmax=/);
    expect(clean).toMatch(/--allow-cross-species/);
  });

  it('says nothing extra under --json', () => {
    // The guidance is prose for a person. Under --json stdout carries one
    // document (ADR 0077), and this must not have reopened that.
    const { stdout } = runCli([...SYSTEM, '--json']);
    expect(() => JSON.parse(stdout)).not.toThrow();
    expect(stdout).not.toContain('What to do next');
  });
});
