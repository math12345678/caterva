/**
 * The CLI chooses what the question did not name, and says so (ADR 0182).
 *
 * Measured before: `simulate "hexokinase in humans" --resolve` refused with
 * "--resolve needs --substrate, --organism, and either --enzyme or --ec",
 * while BRENDA holds 25 measured human glucose Km rows. Now the engine's
 * chooser picks the best-measured substrate, the confirmation shows it with
 * the alternatives, and the run proceeds with it.
 *
 * Spawns the real binary, offline: the literature runner is stubbed with
 * CATERVA_LITERATURE_RUNNER and the chooser with CATERVA_DEFAULTS_RUNNER,
 * each a script answering in the real one's shape. The partial reading of
 * the sentence ("hexokinase in humans" -> hexokinase, EC 2.7.1.1, Homo
 * sapiens) is the real Python reader, which is offline.
 */
import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { readPartialSystemFromQuery } from '../readSystem';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

jest.setTimeout(180_000);

let dir: string;
beforeAll(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-chooser-'));
});
afterAll(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

/** stdout and stderr together: the confirmation screen is on stderr. */
function run(args: string[], env: NodeJS.ProcessEnv): { out: string; code: number } {
  const proc = spawnSync(TS_NODE, [CLI, ...args], {
    cwd: REPO_ROOT,
    env: { ...process.env, ...env },
    encoding: 'utf-8',
    timeout: 150_000,
  });
  return { out: (proc.stdout ?? '') + (proc.stderr ?? ''), code: proc.status ?? 1 };
}

function script(name: string, lines: string[]): string {
  const file = path.join(dir, `${name}_${Math.random().toString(36).slice(2)}.py`);
  fs.writeFileSync(file, lines.join('\n') + '\n', 'utf-8');
  return file;
}

/** The chooser: D-glucose for a substrate, Homo sapiens for an organism. */
function chooser(record: string): string {
  return script('chooser', [
    'import sys, json',
    `open(${JSON.stringify(record)}, "a").write(json.dumps(sys.argv[1:]) + "\\n")`,
    'role = sys.argv[sys.argv.index("--role") + 1]',
    'choices = {',
    '  "substrate": {"role": "substrate", "chosen": "D-glucose", "why": "most Km and kcat rows in Homo sapiens",',
    '                "alternatives": [{"name": "ATP", "rows": {"km": 106}}], "considered": 12},',
    '  "organism": {"role": "organism", "chosen": "Homo sapiens", "why": "most Km rows for EC 2.7.1.1",',
    '               "alternatives": [{"name": "Rattus norvegicus", "rows": {"km": 40}}], "considered": 30},',
    '}',
    'sys.stdout.write(json.dumps({"choice": choices[role], "note": "chosen"}))',
  ]);
}

/** A chooser for which BRENDA has nothing: exit 3 with what is missing. */
function emptyChooser(): string {
  return script('empty', [
    'import sys, json',
    'sys.stdout.write(json.dumps({"choice": None, "note": "BRENDA lists no Km row for any substrate of EC 3.4.21.79 in Homo sapiens; name one with --substrate, or give --km."}))',
    'sys.exit(3)',
  ]);
}

/** The literature runner: records what it was asked, answers Km and kcat. */
function literature(record: string): string {
  return script('literature', [
    'import sys, json',
    'p = json.loads(sys.stdin.read())',
    `open(${JSON.stringify(record)}, "a").write(json.dumps(p) + "\\n")`,
    'q = p.get("quantity", "km")',
    'if q == "km":',
    '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM", "organism": "Homo sapiens",',
    '           "source": "brenda_exact", "citation": {"source": "BRENDA", "reference_id": "641068"}, "logs": []}',
    'else:',
    '    out = {"ok": True, "found": True, "kcat": 40.1, "unit": "1/s", "organism": "Homo sapiens",',
    '           "source": "brenda_exact", "citation": {"source": "BRENDA", "reference_id": "739603"},',
    '           "vmax": 0.0020050000000000003, "vmaxValidation": {"ok": True, "flagged": False}, "logs": []}',
    'sys.stdout.write(json.dumps(out))',
  ]);
}

function lines(file: string): unknown[] {
  return fs.existsSync(file)
    ? fs.readFileSync(file, 'utf-8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
    : [];
}

describe('the sentence names the enzyme and organism, not the substrate', () => {
  it('reads "hexokinase in humans" as hexokinase, EC 2.7.1.1, in Homo sapiens', () => {
    expect(readPartialSystemFromQuery('hexokinase in humans')).toEqual({
      enzyme: 'hexokinase',
      ec: '2.7.1.1',
      ecName: 'hexokinase',
      organism: 'Homo sapiens',
      organismTyped: 'humans',
    });
  });

  it('reads an enzyme alone, with no organism', () => {
    expect(readPartialSystemFromQuery('simulate hexokinase')).toEqual({
      enzyme: 'hexokinase',
      ec: '2.7.1.1',
      ecName: 'hexokinase',
    });
  });

  it('reads nothing when the name is not one enzyme', () => {
    expect(readPartialSystemFromQuery('lactate dehydrogenase')).toBeNull();
  });
});

describe('simulate --resolve chooses, shows the choice, and runs with it', () => {
  it('uses the chosen substrate for every lookup and says so', () => {
    const asked = path.join(dir, 'asked.jsonl');
    const looked = path.join(dir, 'looked.jsonl');
    const { out, code } = run(
      ['simulate', 'hexokinase in humans', '--resolve', '--yes', '--s0', '10mM', '--enzyme-conc', '0.00005mM'],
      { CATERVA_DEFAULTS_RUNNER: chooser(asked), CATERVA_LITERATURE_RUNNER: literature(looked) },
    );
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${out}`);
    expect(out).toContain('No substrate named; using D-glucose (most Km and kcat rows in Homo sapiens).');
    expect(out).toContain('Others: ATP (Km 106 rows).');
    expect(out).toMatch(/substrate\s+D-glucose\s+\(chosen: you named none\)/);
    // The organism was named, so only the substrate was asked for.
    expect(lines(asked)).toEqual([
      ['--ec', '2.7.1.1', '--role', 'substrate', '--json', '--organism', 'Homo sapiens'],
    ]);
    // Every lookup is for exactly the chosen substrate.
    const substrates = (lines(looked) as Array<{ substrate?: string }>).map((p) => p.substrate);
    expect(substrates.length).toBeGreaterThan(0);
    expect(new Set(substrates)).toEqual(new Set(['D-glucose']));
    // And the computed Vmax is printed as a number, not as float noise.
    expect(out).toContain('0.002005 mM/s');
    expect(out).not.toContain('0.0020050000000000003');
  });

  it('keeps the refusal, and says what is missing, when BRENDA has nothing to choose', () => {
    const { out, code } = run(['simulate', 'granzyme B in human', '--resolve', '--yes'], {
      CATERVA_DEFAULTS_RUNNER: emptyChooser(),
    });
    expect(code).toBe(1);
    expect(out).toContain('--resolve could not settle the system');
    expect(out).toContain('BRENDA lists no Km row for any substrate of EC 3.4.21.79 in Homo sapiens');
  });
});

describe('resolve chooses too', () => {
  it('chooses the substrate for an enzyme and organism, and prints the choice first', () => {
    const looked = path.join(dir, 'resolve-looked.jsonl');
    const { out, code } = run(['resolve', 'hexokinase', '--organism', 'human'], {
      CATERVA_DEFAULTS_RUNNER: chooser(path.join(dir, 'resolve-asked.jsonl')),
      CATERVA_LITERATURE_RUNNER: literature(looked),
    });
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${out}`);
    expect(out).toContain('No substrate named; using D-glucose');
    expect((lines(looked)[0] as { substrate?: string }).substrate).toBe('D-glucose');
  });

  it('under --json, the document itself says the substrate was chosen', () => {
    // The person-facing line is not printed under --json (stdout is one
    // document), so without `choices` in the document a script reading it
    // got a Km "of D-glucose" with nothing saying nobody typed D-glucose.
    const proc = spawnSync(TS_NODE, [CLI, 'resolve', 'hexokinase', '--organism', 'human', '--json'], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        CATERVA_DEFAULTS_RUNNER: chooser(path.join(dir, 'json-asked.jsonl')),
        CATERVA_LITERATURE_RUNNER: literature(path.join(dir, 'json-looked.jsonl')),
      },
      encoding: 'utf-8',
      timeout: 150_000,
    });
    if (proc.status !== 0) throw new Error(`expected 0, got ${proc.status}\n${proc.stdout}${proc.stderr}`);
    const doc = JSON.parse(proc.stdout) as { status: string; choices: Array<{ role: string; chosen: string }> };
    expect(doc.status).toBe('found');
    expect(doc.choices.map((c) => [c.role, c.chosen])).toEqual([['substrate', 'D-glucose']]);
  });
});
