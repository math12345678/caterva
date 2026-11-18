/**
 * A flag and the question it was typed with must name the same system.
 *
 * Found 2026-11-03 by review: `simulate "hexokinase glucose mouse"
 * --organism human --resolve --yes` read the sentence, overwrote enzyme,
 * substrate AND organism with it, dropped `--organism human` without a
 * word, and cited BRENDA refs 758915 and 674800 -- measurements in mouse --
 * for a run whose command line said human. origin/main refused the same
 * command only because it could not read a sentence without prepositions;
 * the overwrite itself was older ("hexokinase on glucose in Homo sapiens"
 * --enzyme catalase cited hexokinase).
 *
 * The literature runner here is a stub that writes a marker file when it is
 * called, so "nothing was resolved" is checked as a fact about the process,
 * not as the absence of a string this file expects.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { flagsContradicting, readSystemFromQuery } from '../readSystem';
import type { ParsedSystem } from '../suggestResolveCommand';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');
const ANSI = /\x1b\[[0-9;]*m/g;

let tmpDir: string;
let stub: string;
let marker: string;

jest.setTimeout(300_000);

function runCli(args: string[]): { out: string; code: number } {
  try {
    const stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, CATERVA_LITERATURE_RUNNER: stub },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 180_000,
    });
    return { out: stdout.replace(ANSI, ''), code: 0 };
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string; status?: number | null; signal?: string };
    if (e.status === undefined || e.status === null) {
      throw new Error(`CLI did not exit cleanly: signal=${e.signal} stderr=${(e.stderr ?? '').slice(0, 400)}`);
    }
    return { out: `${e.stdout ?? ''}${e.stderr ?? ''}`.replace(ANSI, ''), code: e.status };
  }
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-agree-'));
  stub = path.join(tmpDir, 'stub.py');
  marker = path.join(tmpDir, 'called');
  fs.writeFileSync(
    stub,
    [
      'import json, sys',
      `open(${JSON.stringify(marker)}, "a").write(sys.stdin.read() + "\\n")`,
      'sys.stdout.write(json.dumps({"ok": True, "found": False, "logs": []}))',
    ].join('\n'),
    'utf-8',
  );
});

afterAll(() => fs.rmSync(tmpDir, { recursive: true, force: true }));

const CONDITIONS = ['--resolve', '--yes', '--s0', '10mM', '--enzyme-conc', '50nM'];

describe('a flag the question contradicts stops the run before anything is resolved', () => {
  it.each([
    ['--organism', ['hexokinase glucose mouse', '--organism', 'human'], /--organism "human", but the question says "mouse" \(Mus musculus\)/],
    ['--enzyme', ['hexokinase on glucose in Homo sapiens', '--enzyme', 'catalase'], /--enzyme "catalase", but the question says "hexokinase"/],
  ])('%s', (_flag, args, said) => {
    fs.rmSync(marker, { force: true });
    const { out, code } = runCli(['simulate', ...args, ...CONDITIONS]);
    expect(code).toBe(1);
    expect(out).toMatch(/flags and your question name different systems/);
    expect(out).toMatch(said);
    // The decisive check: the literature runner never ran, so no citation
    // for either system could have been attached.
    expect(fs.existsSync(marker)).toBe(false);
    expect(out).not.toMatch(/BRENDA ref|Simulation complete/);
  });

  it('a flag that agrees with the question, in other words, is not a conflict', () => {
    // "human" and "Homo sapiens" are one organism by the shared normaliser;
    // refusing that would make the check a nuisance people learn to strip.
    fs.rmSync(marker, { force: true });
    const { out } = runCli(['simulate', 'hexokinase glucose human', '--organism', 'human', ...CONDITIONS]);
    expect(out).not.toMatch(/name different systems/);
    expect(fs.existsSync(marker)).toBe(true);
  });
});

describe('flagsContradicting', () => {
  const parsed: ParsedSystem = {
    enzyme: 'hexokinase', substrate: 'glucose', organism: 'Mus musculus', organismTyped: 'mouse',
    ec: '2.7.1.1', ecName: 'hexokinase',
  };
  const canon = (typed: string): string =>
    ({ human: 'Homo sapiens', mouse: 'Mus musculus' } as Record<string, string>)[typed] ?? typed;

  it('names each flag the reading contradicts', () => {
    expect(flagsContradicting(parsed, { organism: 'human', substrate: 'fructose', ec: '1.11.1.6' }, canon))
      .toEqual([
        '--substrate "fructose", but the question says "glucose"',
        '--organism "human", but the question says "mouse" (Mus musculus)',
        '--ec 1.11.1.6, but "hexokinase" in the question is EC 2.7.1.1 (hexokinase)',
      ]);
  });

  it('is empty when the flags agree, compared as the organism BRENDA is searched under', () => {
    expect(flagsContradicting(parsed, { organism: 'mouse', enzyme: 'Hexokinase', ec: '2.7.1.1' }, canon)).toEqual([]);
    expect(flagsContradicting(parsed, {}, canon)).toEqual([]);
  });
});

describe('the confirmation names the enzyme the citation will be about', () => {
  it('carries the EC the nomenclature resolves the name to', () => {
    expect(readSystemFromQuery('hexokinase glucose human')).toMatchObject({ ec: '2.7.1.1', ecName: 'hexokinase' });
    expect(readSystemFromQuery('hexokinase on glucose in humans')).toMatchObject({ ec: '2.7.1.1' });
  });

  it('a class word is not read as an enzyme at all', () => {
    // "enzyme" is "D-enzyme" (EC 2.4.1.25) with the D- set aside; the run
    // that followed cited 4-alpha-glucanotransferase under "enzyme enzyme".
    expect(readSystemFromQuery('enzyme glucose human')).toBeNull();
    expect(readSystemFromQuery('enzyme maltotriose arabidopsis')).toBeNull();
  });
});
