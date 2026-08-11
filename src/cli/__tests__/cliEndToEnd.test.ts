/**
 * The CLI as a user actually invokes it.
 *
 * This is the surface the tool is used through, and nothing tested it. The
 * tests below spawn the real binary and read its real stdout/stderr and
 * exit code, because the things that break a CLI — argument parsing, exit
 * codes, what lands on which stream — are invisible to a unit test of the
 * functions underneath.
 *
 * The literature runner is stubbed via TERRIUM_LITERATURE_RUNNER so these
 * are offline and deterministic. The stub returns the shape
 * `science_agent_runner.py` really returns; the contract between them is
 * covered separately in literatureResolver.test.ts.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

let stubDir: string;

interface RunResult {
  stdout: string;
  stderr: string;
  code: number;
}

function runCli(args: string[], env: NodeJS.ProcessEnv = {}): RunResult {
  try {
    const stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, ...env },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120_000,
    });
    return { stdout, stderr: '', code: 0 };
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string; status?: number };
    return {
      stdout: e.stdout ?? '',
      stderr: e.stderr ?? '',
      code: e.status ?? 1,
    };
  }
}

function writeStub(name: string, payload: unknown): string {
  const file = path.join(stubDir, `${name}_${Math.random().toString(36).slice(2)}.py`);
  // Writes the payload verbatim on stdout, exactly as
  // science_agent_runner.py does. `json` is imported but unused by design:
  // the payload is already serialised here, so the stub cannot reformat or
  // reorder it and mask a parsing bug on the reading side.
  fs.writeFileSync(
    file,
    'import sys\nsys.stdin.read()\n' +
      `sys.stdout.write(${JSON.stringify(JSON.stringify(payload))})\n`,
    'utf-8',
  );
  return file;
}

beforeAll(() => {
  stubDir = fs.mkdtempSync(path.join(os.tmpdir(), 'terrium-cli-'));
});

afterAll(() => {
  fs.rmSync(stubDir, { recursive: true, force: true });
});

jest.setTimeout(180_000);

describe('help', () => {
  it('documents resolve, and exits 0', () => {
    const { stdout, code } = runCli(['help']);
    expect(code).toBe(0);
    expect(stdout).toContain('resolve');
    expect(stdout).toContain('--substrate');
  });
});

describe('resolve: three outcomes, three exit codes', () => {
  it('exits 0 and prints the value, unit and citation when found', () => {
    const stub = writeStub('found', {
      ok: true,
      found: true,
      km: 2.5,
      unit: 'mM',
      organism: 'Homo sapiens',
      source: 'brenda_exact',
      citation: { source: 'BRENDA', reference_id: '649716' },
      logs: [],
    });

    const { stdout, code } = runCli(
      ['resolve', 'ldh', '--substrate', 'pyruvate', '--organism', 'Homo sapiens'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );

    expect(code).toBe(0);
    expect(stdout).toContain('2.5 mM');
    // The unit must be shown next to the value. A kinetic constant without
    // its unit is not a measurement.
    expect(stdout).toContain('BRENDA');
    expect(stdout).toContain('649716');
  });

  it('exits 2 when the literature genuinely has nothing', () => {
    const stub = writeStub('none', {
      ok: true,
      found: false,
      logs: ['BRENDA exact: no rows'],
    });

    const { stdout, code } = runCli(
      ['resolve', 'nothing', '--substrate', 'x', '--organism', 'y'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );

    // Distinct from 1: a script needs to tell "no data" from "no network".
    expect(code).toBe(2);
    expect(stdout).toMatch(/no km found/i);
    // And it must not read as a malfunction.
    expect(stdout).toMatch(/answer, not a failure/i);
  });

  it('exits 1 when the lookup could not be performed at all', () => {
    const stub = writeStub('broken', { ok: false, error: '403 Forbidden' });

    const { stderr, code } = runCli(
      ['resolve', 'ldh', '--substrate', 'pyruvate', '--organism', 'Homo sapiens'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );

    expect(code).toBe(1);
    expect(stderr).toContain('403 Forbidden');
    // The distinction that matters most in this whole command.
    expect(stderr).toMatch(/NOT the same as "no value exists"/i);
  });
});

describe('resolve: provenance is never buried', () => {
  it('warns loudly that a cross-species value is not the organism asked for', () => {
    const stub = writeStub('cross', {
      ok: true,
      found: true,
      km: 1.1,
      unit: 'mM',
      organism: 'Oryctolagus cuniculus',
      source: 'brenda_cross_species',
      citation: { source: 'BRENDA', reference_id: '999' },
      logs: [],
    });

    const { stdout } = runCli(
      ['resolve', 'ldh', '--substrate', 'pyruvate', '--organism', 'Homo sapiens'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );

    expect(stdout).toMatch(/cross-species/i);
    expect(stdout).toContain('Oryctolagus cuniculus');
    expect(stdout).toMatch(/do not report it as a Homo sapiens measurement/i);
  });

  it('refuses to guess the system from the query text', () => {
    // Inferring an enzyme/substrate/organism from prose would attach a real
    // citation to a system the user never named.
    const { code, stdout, stderr } = runCli(['resolve', 'lactate dehydrogenase']);
    expect(code).toBe(1);
    expect(stdout + stderr).toMatch(/needs a substrate, an organism/i);
  });
});

describe('resolve: --json is machine readable', () => {
  it('emits parseable JSON on stdout and nothing else', () => {
    const stub = writeStub('json', {
      ok: true,
      found: true,
      km: 2.5,
      unit: 'mM',
      organism: 'Homo sapiens',
      source: 'brenda_exact',
      citation: null,
      logs: [],
    });

    const { stdout, stderr, code } = runCli(
      ['resolve', 'ldh', '--substrate', 'pyruvate', '--organism', 'Homo sapiens', '--json'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );

    // Surface both streams on failure: a CLI test that reports only an exit
    // code makes you re-run it by hand to learn anything.
    if (code !== 0) {
      throw new Error(
        `expected exit 0, got ${code}\n--- stdout ---\n${stdout}\n--- stderr ---\n${stderr}`,
      );
    }
    const parsed = JSON.parse(stdout);
    expect(parsed.status).toBe('found');
    expect(parsed.value).toBe(2.5);
    expect(parsed.unit).toBe('mM');
  });
});

describe('simulate --resolve: the tool doing its actual job', () => {
  /** Answers km and kcat differently, like the real runner does. */
  function multiStub(): string {
    // Unique per call. A fixed filename was rewritten by every test that
    // used it, and with several ts-node processes reading it across a run
    // one of them saw a stale or partially-written file and answered a
    // kcat query with the km branch.
    const file = path.join(stubDir, `multi_${Math.random().toString(36).slice(2)}.py`);
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'q = p.get("quantity", "km")',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "organism": "Homo sapiens", "source": "brenda_exact",',
        '           "citation": {"source": "BRENDA", "reference_id": "12345"}, "logs": []}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "organism": "Oryctolagus cuniculus", "source": "brenda_cross_species",',
        '           "citation": {"source": "BRENDA", "reference_id": "649716"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False}, "logs": []}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  const SYSTEM = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  it('resolves, runs the real engine, and shows where each number came from', () => {
    const { stdout, stderr, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM, '--s0', '10mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: multiStub() },
    );

    if (code !== 0) {
      throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);
    }

    // The provenance table is the point of the command.
    expect(stdout).toMatch(/where they came from/i);
    expect(stdout).toMatch(/km\s+0\.14 mM\s+brenda_exact/);
    expect(stdout).toContain('BRENDA ref 12345');
    // Vmax is not a BRENDA table: it is kcat x [E]0.
    expect(stdout).toMatch(/vmax.*kcat/);

    // And it actually simulated -- the engine's sampling resolution.
    expect(stdout).toMatch(/points\s+101/);
    expect(stdout).toMatch(/consumed/);
  });

  it('never buries a cross-species substitution', () => {
    const { stdout } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM, '--s0', '10mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: multiStub() },
    );
    expect(stdout).toContain('Oryctolagus cuniculus');
    expect(stdout).toMatch(/not the organism requested/i);
  });

  it('refuses to run, rather than defaulting, when a parameter is unresolved', () => {
    // No --enzyme-conc, so Vmax = kcat x [E]0 cannot be formed. The old
    // pipeline would have used `|| 10.0`.
    const { stdout, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM, '--s0', '10mM'],
      { TERRIUM_LITERATURE_RUNNER: multiStub() },
    );

    expect(code).toBe(2);
    expect(stdout).toMatch(/cannot run/i);
    expect(stdout).toMatch(/enzyme-conc/);
    expect(stdout).toMatch(/no value has been invented/i);
  });

  it('requires s0, which is a condition nobody can look up', () => {
    const { stdout, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM, '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: multiStub() },
    );
    expect(code).toBe(2);
    expect(stdout).toMatch(/s0.*experimental condition/i);
  });

  it('will not guess the system from the query text', () => {
    const { stdout, stderr, code } = runCli(['simulate', 'lactate dehydrogenase', '--resolve']);
    expect(code).toBe(1);
    expect(stdout + stderr).toMatch(/--substrate/);
    expect(stdout + stderr).toMatch(/never inferred from the query/i);
  });

  it('reports an unreachable registry as unavailable, not as "no data"', () => {
    const stub = writeStub('down', { ok: false, error: '403 Forbidden' });
    const { stderr, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM, '--s0', '10mM'],
      { TERRIUM_LITERATURE_RUNNER: stub },
    );
    expect(code).toBe(1);
    expect(stderr).toContain('403 Forbidden');
  });
});

describe('units on the command line', () => {
  it('rejects an unknown unit instead of silently reinterpreting it', () => {
    const { stdout, stderr, code } = runCli(['simulate', 'mm', '--km', '5.2mMM']);
    expect(code).toBe(1);
    expect(stdout + stderr).toMatch(/unrecognised concentration unit/i);
  });

  it('reports which units it had to assume', () => {
    const { stdout, stderr } = runCli(['simulate', 'michaelis menten', '--km', '5.2']);
    expect(stdout + stderr).toMatch(/units not given/i);
    expect(stdout + stderr).toMatch(/assumed mM/i);
  });

  it('says nothing about assumptions when every unit is declared', () => {
    const { stdout, stderr } = runCli([
      'simulate', 'michaelis menten',
      '--km', '5.2mM', '--vmax', '12.8uM/min', '--s0', '10mM',
    ]);
    expect(stdout + stderr).not.toMatch(/units not given/i);
  });
});

describe('output hygiene', () => {
  it('does not flood stdout with structured logs by default', () => {
    // The pipeline logs a dozen JSON lines per run. On a terminal they
    // buried the actual answer, which is the one thing a CLI exists to
    // show. They go to stderr and are silenced unless --verbose.
    const { stdout } = runCli(['simulate', 'michaelis menten', '--km', '5.2mM']);
    const jsonLogLines = stdout
      .split('\n')
      .filter((line) => line.trim().startsWith('{"level"'));
    expect(jsonLogLines).toHaveLength(0);
  });
});
