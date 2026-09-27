/**
 * `--json` puts one parsable document on stdout, whatever else happens.
 *
 * WHY THIS FILE EXISTS SEPARATELY FROM refusalStillDelivers.test.ts
 * ----------------------------------------------------------------
 * That file already asserts "puts nothing but the document on stdout". It
 * passed while `--json` was broken in four other ways, because it ran ONE
 * scenario — a refusal with `--export-citations` — and the prose that
 * corrupts the document comes from branches that scenario never entered:
 *
 *   --ki + --i0 with model mm  -> "• Did you mean --model competitive? ..."
 *   --sensitivity              -> the whole provenance table
 *   product inhibition         -> PRODUCT_INHIBITION_CAVEAT
 *
 * Each printed a sentence ahead of the JSON:
 *
 *     $ simulate ... --resolve --ki 5mM --i0 1mM --json
 *     • Did you mean --model competitive? ...
 *     { "ok": true, ... }
 *     -> Expecting value: line 2 column 1 (char 1)
 *
 * ADR 0077 fixed this inside `writeExports` and stopped there, which fixed
 * the instance and not the class. So this file does not test a scenario; it
 * enumerates the FLAG COMBINATIONS that reach different branches and asserts
 * the same property of each. A property tested once is a property tested on
 * one path.
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
    const e = err as { stdout?: string; status?: number };
    return { stdout: e.stdout ?? '', code: e.status ?? 1 };
  }
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-json-'));
  stub = path.join(tmpDir, 'stub.py');
  // Km resolves; everything else is a clean absence. Enough to reach both
  // the successful and the refused paths depending on what the caller
  // supplies, without a network.
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

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

jest.setTimeout(600_000);

const SYSTEM = [
  'simulate', 'michaelis menten', '--resolve',
  '--substrate', 'pyruvate',
  '--organism', 'Homo sapiens',
  '--enzyme', 'lactate dehydrogenase',
];

/**
 * Each entry names the branch it exists to enter. Adding a combination here
 * is cheaper than discovering later that a new message escaped.
 */
function combinations(): Array<{ what: string; args: string[] }> {
  return [
    { what: 'a plain successful run', args: [...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s'] },
    { what: 'a refusal (no kcat to bridge Vmax)', args: [...SYSTEM, '--enzyme-conc', '0.01mM', '--s0', '10mM'] },
    {
      what: 'the model suggestion (ki + i0 under plain mm)',
      args: [...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s', '--ki', '5mM', '--i0', '1mM'],
    },
    {
      what: 'a sensitivity sweep',
      args: [...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s', '--sensitivity', '0.1'],
    },
    {
      what: 'a successful run writing both exports',
      args: [
        ...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s',
        '--export-citations', path.join(tmpDir, 'a.bib'),
        '--export-model', path.join(tmpDir, 'a.txt'),
      ],
    },
    {
      what: 'a refusal that was asked for exports',
      args: [
        ...SYSTEM, '--enzyme-conc', '0.01mM', '--s0', '10mM',
        '--export-citations', path.join(tmpDir, 'b.bib'),
        '--export-model', path.join(tmpDir, 'b.txt'),
      ],
    },
  ];
}

describe('--json emits exactly one parsable document', () => {
  it('for every flag combination that reaches a different branch', () => {
    const broken: string[] = [];
    for (const { what, args } of combinations()) {
      const { stdout } = runCli([...args, '--json']);
      try {
        JSON.parse(stdout);
      } catch (err) {
        broken.push(
          `\n  ${what}\n    ${(err as Error).message}\n` +
            `    stdout began: ${JSON.stringify(stdout.slice(0, 90))}`,
        );
      }
    }
    // All of them reported at once. Fixing one leak, re-running a suite this
    // slow, and finding the next is how the third one gets left.
    expect(broken.join('')).toBe('');
  });

  it('and the same runs without --json do print prose', () => {
    // The other half. Routing every message through a sink that is silent
    // under --json would also satisfy the test above if the sink were
    // silent ALWAYS — which would delete the human interface and pass.
    const { stdout } = runCli([
      ...SYSTEM, '--s0', '10mM', '--vmax', '1.2mM/s', '--ki', '5mM', '--i0', '1mM',
    ]);
    expect(stdout).toMatch(/Did you mean/i);
    expect(stdout).toMatch(/Parameters and where they came from/i);
  });
});
