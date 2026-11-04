/**
 * A refusal states what actually happened, in the flags this CLI has.
 *
 * Three sentences that were each true of a different situation:
 *
 *   - An LDH ambiguity said "re-run with ecNumber 1.1.1.27". ecNumber is the
 *     API's request field; the CLI's flag is --ec, and no command line
 *     accepts the other. The runner now spells the re-run the way the
 *     caller asks (payload `ecFlag`), and the CLI asks for `--ec`.
 *   - `simulate "michaelis menten"` reported km, vmax and s0 as having "no
 *     literature match". No literature was searched: the CLI hands the
 *     pipeline an empty source list and the question names no system.
 *   - The advice under an unparsed question said Caterva "does not read"
 *     the system out of a question -- false since --resolve does -- and
 *     offered `--km 5.2 --vmax 12.8` as values to type.
 *
 * The literature runner is a stub (CATERVA_LITERATURE_RUNNER) that echoes
 * the ecFlag it was sent, so the first check is of what crosses the wire,
 * not of a string this file wrote itself.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');
const ANSI = /\x1b\[[0-9;]*m/g;

let tmpDir: string;
let stub: string;

jest.setTimeout(300_000);

function runCli(args: string[]): { out: string; code: number } {
  try {
    const stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, CATERVA_LITERATURE_RUNNER: stub },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120_000,
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
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-said-'));
  stub = path.join(tmpDir, 'stub.py');
  fs.writeFileSync(
    stub,
    [
      'import json, sys',
      'p = json.loads(sys.stdin.read() or "{}")',
      'msg = ("\'lactate dehydrogenase\' could be 2 enzymes. To accept the "',
      '       "recommendation, re-run with " + str(p.get("ecFlag", "ecNumber")) + " 1.1.1.27")',
      'sys.stdout.write(json.dumps({"ok": True, "found": False, "source": "ec_ambiguous",',
      '    "ecCandidates": ["1.1.1.27", "1.1.1.28"], "ecCandidateNames": [],',
      '    "ecRefusal": msg, "literatureCandidates": [], "logs": [msg]}))',
    ].join('\n'),
    'utf-8',
  );
});

afterAll(() => fs.rmSync(tmpDir, { recursive: true, force: true }));

describe('a refusal names the flag this CLI actually has', () => {
  it('an ambiguous enzyme name is re-run with --ec, not ecNumber', () => {
    const { out, code } = runCli([
      'simulate', 'michaelis menten', '--resolve',
      '--enzyme', 'lactate dehydrogenase', '--substrate', 'pyruvate',
      '--organism', 'Homo sapiens', '--s0', '10mM', '--enzyme-conc', '50nM',
    ]);
    expect(code).toBe(2);
    expect(out).toContain('re-run with --ec 1.1.1.27');
    expect(out).not.toContain('ecNumber');
  });
});

describe('a refusal with no lookup behind it does not claim one', () => {
  it('says no literature was searched, rather than "no literature match"', () => {
    const { out } = runCli(['simulate', 'michaelis menten']);
    expect(out).toMatch(/Parameter 'km':.*no literature was searched/);
    expect(out).not.toContain('no literature match');
  });

  it('does not say the question is never read, and offers no constants to type', () => {
    const { out } = runCli(['simulate', 'michaelis menten']);
    expect(out).not.toContain('does not read');
    expect(out).not.toMatch(/--km \d|--vmax \d/);
    expect(out).toContain('--resolve reads them out');
  });
});
