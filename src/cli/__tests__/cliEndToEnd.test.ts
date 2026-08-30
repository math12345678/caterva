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
import { resolvePythonExecutable } from '../../engine/teriumBridge';

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

/**
 * Bakker's reliability axes in the PRIMARY command.
 *
 * The axes were computed by the runner, parsed by the resolver, typed on
 * `ParameterProvenance`, and read when writing the annotated model — and
 * never written by any of the five `provenance.push` calls in
 * `simulate --resolve`. So every exported model carried an empty
 * reliability block while every layer above it worked. `grep -A12
 * "provenance.push({" | grep -c "reliability:"` returned 0.
 *
 * Separately, `--physiological` was parsed only in the `resolve` branch, so
 * `conditionProximity` came back `not_assessed` on every run of the command
 * that actually simulates something.
 *
 * These two tests pin both. The second one asserts on what the RUNNER
 * RECEIVED rather than on printed text: a stub that ignores its stdin and
 * returns a `near` grade would satisfy an output assertion while the flag
 * never left the CLI. That is the same defect one level up — a check that
 * agrees with itself.
 */
describe('simulate --resolve: reliability reaches the user and the runner', () => {
  const SYSTEM_2 = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  /** Returns axes, and records the request it was handed. */
  function reflectingStub(recordTo: string): string {
    const file = path.join(stubDir, `reflect_${Math.random().toString(36).slice(2)}.py`);
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'with open(%s, "a") as fh:'.replace('%s', JSON.stringify(recordTo)),
        '    fh.write(json.dumps(p) + "\\n")',
        'q = p.get("quantity", "km")',
        'axes = {"assayCompleteness": {"grade": "complete", "reason": "pH and T reported."},',
        '        "conditionProximity": {"grade": "near", "reason": "Within tolerance."},',
        '        "organismMatch": {"grade": "exact", "reason": "Same organism."},',
        '        "noAggregateReason": "The axes are not commensurable."}',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "organism": "Homo sapiens", "source": "brenda_exact",',
        '           "citation": {"source": "BRENDA", "reference_id": "12345"},',
        '           "reliability": axes, "logs": []}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "organism": "Homo sapiens", "source": "brenda_exact",',
        '           "citation": {"source": "BRENDA", "reference_id": "649716"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False},',
        '           "reliability": axes, "logs": []}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  it('prints every axis beside the parameter it grades', () => {
    const record = path.join(stubDir, `req_${Math.random().toString(36).slice(2)}.jsonl`);
    const { stdout, stderr, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM_2, '--s0', '10mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: reflectingStub(record) },
    );

    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);

    expect(stdout).toMatch(/reliability:/);
    // All three, named. A single summary grade would hide which axis is
    // weak, which is the whole reason there are three (ADR 0027).
    expect(stdout).toMatch(/assay completeness complete/);
    expect(stdout).toMatch(/conditions vs model near/);
    expect(stdout).toMatch(/organism match exact/);
  });

  it('sends the physiological reference the user gave to the runner', () => {
    const record = path.join(stubDir, `req_${Math.random().toString(36).slice(2)}.jsonl`);
    const { stdout, stderr, code } = runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_2,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--physiological', '7.4,37',
        '--physiological-basis', 'human cytosol, Alberts 6e',
      ],
      { TERRIUM_LITERATURE_RUNNER: reflectingStub(record) },
    );

    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);

    const requests = fs
      .readFileSync(record, 'utf-8')
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line) as Record<string, any>);

    // Both lookups, not just the first. km and vmax are resolved by two
    // separate calls and threading the reference into one of them is a
    // silent half-fix that an output assertion could not see.
    expect(requests.length).toBeGreaterThanOrEqual(2);
    for (const request of requests) {
      expect(request.physiologicalReference).toBeTruthy();
      expect(request.physiologicalReference.ph).toBe(7.4);
      expect(request.physiologicalReference.temperatureC).toBe(37);
      // The yardstick needs provenance too: an unattributed reference is
      // a number from nowhere being used to judge numbers from somewhere.
      expect(request.physiologicalReference.basis).toBe('human cytosol, Alberts 6e');
    }
  });

  it('refuses a physiological reference with no stated basis', () => {
    const record = path.join(stubDir, `req_${Math.random().toString(36).slice(2)}.jsonl`);
    const { stdout, stderr, code } = runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_2,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--physiological', '7.4,37',
      ],
      { TERRIUM_LITERATURE_RUNNER: reflectingStub(record) },
    );

    expect(code).toBe(1);
    expect(stdout + stderr).toMatch(/basis/i);
    // Same parser as `resolve`, so the two commands cannot disagree about
    // what a valid reference is.
    expect(fs.existsSync(record)).toBe(false);
  });
});

/**
 * The cross-species warning, as data rather than prose.
 *
 * The SBML annotator could write `bqbiol:hasTaxon` from the day it was
 * built, and nothing fed it: the runner resolved a taxon id for its own EC
 * lookup and discarded it, so every real export carried zero taxon
 * annotations. The capability existed and could not fire — which is the
 * same as not existing, and is why this test drives the whole chain
 * (runner → resolver → CLI → file) instead of the annotator alone.
 *
 * The assertion is made by re-reading the written file with a plain SBML
 * reader. Asserting on the CLI's own summary line would only prove the CLI
 * agrees with itself.
 */
describe('simulate --resolve: cross-species is machine-detectable in the export', () => {
  const SYSTEM_3 = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  function taxonStub(measuredTaxon: string | null): string {
    const file = path.join(stubDir, `taxon_${Math.random().toString(36).slice(2)}.py`);
    const measured = measuredTaxon === null ? 'None' : JSON.stringify(measuredTaxon);
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'q = p.get("quantity", "km")',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "organism": "Homo sapiens", "taxonId": "9606",',
        '           "requestedTaxonId": "9606", "source": "brenda_exact",',
        '           "citation": {"source": "PubMed", "reference_id": "12345678"},',
        '           "logs": []}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "organism": "Oryctolagus cuniculus",',
        `           "taxonId": ${measured},`,
        '           "requestedTaxonId": "9606", "crossSpecies": True,',
        '           "source": "brenda_cross_species",',
        '           "citation": {"source": "PubMed", "reference_id": "999111"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False},',
        '           "logs": []}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  /** Ask a plain SBML reader what is in the file, via the Python side. */
  function annotationsIn(file: string): Record<string, string[]> {
    const out = execFileSync(
      'python3',
      [
        '-c',
        'import sys,json;sys.path.insert(0,".");' +
          'from Terium.core.sbml_provenance import read_back;' +
          'print(json.dumps(read_back(open(sys.argv[1]).read())))',
        file,
      ],
      { cwd: REPO_ROOT, encoding: 'utf-8' },
    );
    return JSON.parse(out) as Record<string, string[]>;
  }

  function mismatchesIn(file: string): Array<[string, string, string]> {
    const out = execFileSync(
      'python3',
      [
        '-c',
        'import sys,json;sys.path.insert(0,".");' +
          'from Terium.core.sbml_provenance import cross_species_parameters;' +
          'print(json.dumps(cross_species_parameters(open(sys.argv[1]).read())))',
        file,
      ],
      { cwd: REPO_ROOT, encoding: 'utf-8' },
    );
    return JSON.parse(out) as Array<[string, string, string]>;
  }

  it('writes the measured taxon on each parameter and the asked-for taxon on the model', () => {
    const out = path.join(stubDir, `cross_${Math.random().toString(36).slice(2)}.xml`);
    const { stdout, stderr, code } = runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_3,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--allow-cross-species', '--export-model', out,
      ],
      { TERRIUM_LITERATURE_RUNNER: taxonStub('9986') },
    );
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);

    const annotations = annotationsIn(out);
    expect(annotations['Km']).toContain('https://identifiers.org/taxonomy:9606');
    expect(annotations['Vmax']).toContain('https://identifiers.org/taxonomy:9986');
  });

  it('lets a plain SBML reader find the substitution with no Terrium knowledge', () => {
    const out = path.join(stubDir, `cross_${Math.random().toString(36).slice(2)}.xml`);
    runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_3,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--allow-cross-species', '--export-model', out,
      ],
      { TERRIUM_LITERATURE_RUNNER: taxonStub('9986') },
    );

    const mismatches = mismatchesIn(out);
    expect(mismatches.map(([name]) => name)).toEqual(['Vmax']);
    // Km was measured in the organism asked about, so it is not flagged.
    expect(mismatches.map(([name]) => name)).not.toContain('Km');
  });

  it('omits the taxon rather than inventing one when the lookup failed', () => {
    // A null taxonId is "not resolved", which is what a network failure
    // looks like. The annotation must be absent, and the prose warning must
    // still be present — the fact is not lost, only its machine-readable
    // form.
    const out = path.join(stubDir, `cross_${Math.random().toString(36).slice(2)}.xml`);
    runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_3,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--allow-cross-species', '--export-model', out,
      ],
      { TERRIUM_LITERATURE_RUNNER: taxonStub(null) },
    );

    const annotations = annotationsIn(out);
    expect(annotations['Vmax'].join(' ')).not.toContain('taxonomy:');
    // No taxon on the parameter means no detectable mismatch...
    expect(mismatchesIn(out)).toEqual([]);
    // ...but the reader is still told, in the notes.
    expect(fs.readFileSync(out, 'utf-8')).toContain('CROSS-SPECIES');
  });
});

/**
 * A run somebody else can actually re-run.
 *
 * Terrium could export a model, a bibliography, a job id and a
 * reproducibility key — and none of that let another person repeat the
 * experiment. The model says what the system is; it does not say this run
 * integrated to t=10 with 101 points, which is what decides the figure.
 *
 * The assertion is made by RE-EXECUTING the archive, not by inspecting it.
 * A well-formed archive that reproduces a different curve is still broken,
 * and no amount of schema validation distinguishes the two.
 */
describe('simulate --resolve: the COMBINE archive re-runs', () => {
  const SYSTEM_4 = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  function python(script: string, ...args: string[]): string {
    // The SAME interpreter the CLI under test uses, not a bare `python3`.
    //
    // These three tests read the archive back with libsedml and
    // roadrunner. `make setup` installs both into `.venv`, and
    // `resolvePythonExecutable` is how every product path finds it -- so
    // hardcoding `python3` here pointed the verification at whatever
    // interpreter happened to be first on PATH, which on a machine that
    // followed CONTRIBUTING is the one WITHOUT the dependencies.
    //
    // The result was a suite that could not pass on a correctly set-up
    // machine: `ModuleNotFoundError: No module named 'libsedml'`, raised by
    // the test's own helper, about a module the project installs. Reusing
    // the resolver rather than repeating its logic keeps one answer to
    // "which Python is this project's Python" (TERRIUM_PYTHON, then
    // .venv, then venv, then PATH).
    return execFileSync(resolvePythonExecutable(REPO_ROOT), ['-c', script, ...args], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
    });
  }

  /** km and kcat answered separately, as the real runner does. */
  function archiveStub(): string {
    const file = path.join(stubDir, `arch_${Math.random().toString(36).slice(2)}.py`);
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'q = p.get("quantity", "km")',
        'base = {"organism": "Homo sapiens", "taxonId": "9606",',
        '        "requestedTaxonId": "9606", "source": "brenda_exact", "logs": []}',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "citation": {"source": "PubMed", "reference_id": "12345678"}, **base}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "citation": {"source": "PubMed", "reference_id": "999111"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False}, **base}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  function writeArchive(): { file: string; stdout: string; code: number } {
    const file = path.join(stubDir, `run_${Math.random().toString(36).slice(2)}.omex`);
    const { stdout, stderr, code } = runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_4,
        '--s0', '10mM', '--enzyme-conc', '0.001mM',
        '--export-model', file,
      ],
      { TERRIUM_LITERATURE_RUNNER: archiveStub() },
    );
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);
    return { file, stdout, code };
  }

  it('writes an archive whose manifest matches its contents', () => {
    const { file } = writeArchive();
    const out = python(
      'import sys,json;sys.path.insert(0,".");' +
        'from Terium.core.combine_archive import verify_archive;' +
        'v=verify_archive(sys.argv[1]);' +
        'print(json.dumps({"ok":v.ok,"problems":v.problems,"present":v.present}))',
      file,
    );
    const result = JSON.parse(out) as { ok: boolean; problems: string[]; present: string[] };
    expect(result.problems).toEqual([]);
    expect(result.ok).toBe(true);
    // CITATION.cff is IN the archive on purpose: a result that cites every
    // measurement it used and not the tool that produced them is the
    // converse of Katz's objection, and Terium/tests/test_citation_metadata.py
    // pins the same bundling from the Python side. This list did not have it
    // and had been stale since the file started being bundled -- unnoticed
    // because the Python test that asserts it skips when `libsedml` is
    // absent, and this one failed for that same missing module before it
    // could ever reach this line.
    expect(result.present.sort()).toEqual([
      'CITATION.cff',
      'manifest.xml',
      'model.xml',
      'simulation.sedml',
    ]);
  });

  it('records the time course that actually ran, not a default', () => {
    const { file, stdout } = writeArchive();
    // The CLI prints how many points it produced; the SED-ML must describe
    // that same run. A constant in the exporter would keep describing the
    // old time course the moment the engine's defaults changed.
    const reported = /points\s+(\d+)/.exec(stdout);
    expect(reported).not.toBeNull();

    const out = python(
      'import sys,json,zipfile;sys.path.insert(0,".");import libsedml;' +
        'z=zipfile.ZipFile(sys.argv[1]);' +
        'd=libsedml.readSedMLFromString(z.read("simulation.sedml").decode());' +
        's=d.getSimulation(0);' +
        'print(json.dumps({"rows":s.getNumberOfPoints()+1,"end":s.getOutputEndTime()}))',
      file,
    );
    const experiment = JSON.parse(out) as { rows: number; end: number };
    expect(experiment.rows).toBe(Number(reported![1]));
    expect(experiment.end).toBeGreaterThan(0);
  });

  it('reproduces the reported final value from the archive alone', () => {
    const { file, stdout } = writeArchive();
    const reported = /final\s+([\d.]+)/.exec(stdout);
    expect(reported).not.toBeNull();

    // Nothing from the CLI is used below except the number being checked:
    // the model, the time course and the solver all come out of the file.
    const out = python(
      'import sys,zipfile;sys.path.insert(0,".");import libsedml,roadrunner;' +
        'z=zipfile.ZipFile(sys.argv[1]);' +
        'd=libsedml.readSedMLFromString(z.read("simulation.sedml").decode());' +
        's=d.getSimulation(0);' +
        'r=roadrunner.RoadRunner(z.read("model.xml").decode());' +
        'res=r.simulate(s.getOutputStartTime(),s.getOutputEndTime(),s.getNumberOfPoints()+1);' +
        'print(float(res[-1][1]))',
      file,
    );
    expect(Number(out.trim())).toBeCloseTo(Number(reported![1]), 3);
  });
});

/**
 * The reason behind a grade, where a student can read it.
 *
 * `scientific resolve` printed these from the day the axes existed.
 * `simulate --resolve` — the command a teaching lab actually runs — printed
 * `assay completeness partial` and stopped. The grade is a token; the
 * reason is the sentence somebody learns from, and it was being computed,
 * serialised across a process boundary, typed, and then dropped one step
 * before anyone saw it.
 */
describe('simulate --resolve: a grade explains itself', () => {
  const SYSTEM_5 = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  const PARTIAL_REASON =
    'Assay reports pH 7.4 but no temperature. Weak evidence rather than none.';
  const EXACT_REASON = 'Measured in the organism asked about.';

  function gradedStub(assayGrade: string): string {
    const file = path.join(stubDir, `graded_${Math.random().toString(36).slice(2)}.py`);
    const axes = JSON.stringify({
      assayCompleteness: { grade: assayGrade, reason: PARTIAL_REASON },
      conditionProximity: { grade: 'near', reason: 'Within tolerance.' },
      organismMatch: { grade: 'exact', reason: EXACT_REASON },
      noAggregateReason: 'The axes are not commensurable.',
    });
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'q = p.get("quantity", "km")',
        `axes = json.loads(${JSON.stringify(axes)})`,
        'base = {"organism": "Homo sapiens", "source": "brenda_exact",',
        '        "reliability": axes, "logs": []}',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "citation": {"source": "PubMed", "reference_id": "12345678"}, **base}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "citation": {"source": "PubMed", "reference_id": "999111"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False}, **base}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  function run(assayGrade: string, extra: string[] = []) {
    return runCli(
      [
        'simulate', 'mm', '--resolve', ...SYSTEM_5,
        '--s0', '10mM', '--enzyme-conc', '0.001mM', ...extra,
      ],
      { TERRIUM_LITERATURE_RUNNER: gradedStub(assayGrade) },
    );
  }

  it('prints the reason for an axis reporting a limitation', () => {
    const { stdout, stderr, code } = run('partial');
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);

    expect(stdout).toMatch(/assay completeness partial/);
    // The sentence, not just the token.
    //
    // Matched on a SHORT fragment because the reason is word-wrapped: the
    // first version of this test looked for "Weak evidence rather than
    // none" and failed, because the wrap falls between "than" and "none".
    // The code was right and the assertion spanned a line break.
    expect(stdout).toMatch(/Weak evidence/);
    expect(stdout).toMatch(/no temperature/);
  });

  it('does not bury the answer under reasons for axes that are fine', () => {
    // All three grades are on the line above whatever they say, so an
    // absent reason never reads as "not assessed". Printing three
    // paragraphs per parameter would push the result off the screen — the
    // output-hygiene tests above exist for that failure.
    const { stdout } = run('complete');
    expect(stdout).toMatch(/assay completeness complete/);
    expect(stdout).not.toMatch(/Weak evidence/);
    expect(stdout).not.toMatch(/Measured in the organism asked about/);
  });

  it('writes every reason into the exported model, including the good ones', () => {
    // Nothing is lost by the terminal being brief: the file carries the
    // full set, and it is the file that travels.
    const out = path.join(stubDir, `reasons_${Math.random().toString(36).slice(2)}.xml`);
    const { code, stdout, stderr } = run('complete', ['--export-model', out]);
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);

    const model = fs.readFileSync(out, 'utf-8');
    expect(model).toContain('assay completeness: complete');
    expect(model).toContain('Measured in the organism asked about.');
  });
});

/**
 * The identifier labelled reproducible has to reproduce.
 *
 * Every run printed `repro key`: a sha256 of the inputs, the outputs,
 * `Date.now()` and a random UUID. The randomness is correct — it is a
 * unique execution identifier and the comment beside it explains why
 * collisions had to be ruled out. What was wrong is the *name*. Two
 * identical runs produce different keys by construction, so a student
 * comparing them would conclude the tool is non-deterministic.
 *
 * `inputHash` — sha256 of `{query, parameters, conditions}` — was computed
 * and stored from the beginning and shown to nobody.
 */
describe('simulate --resolve: the reproducible identifier reproduces', () => {
  const SYSTEM_6 = [
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
  ];

  function stub(): string {
    const file = path.join(stubDir, `ident_${Math.random().toString(36).slice(2)}.py`);
    fs.writeFileSync(
      file,
      [
        'import sys, json',
        'p = json.loads(sys.stdin.read())',
        'q = p.get("quantity", "km")',
        'base = {"organism": "Homo sapiens", "source": "brenda_exact", "logs": []}',
        'if q == "km":',
        '    out = {"ok": True, "found": True, "km": 0.14, "unit": "mM",',
        '           "citation": {"source": "PubMed", "reference_id": "1"}, **base}',
        'elif q == "kcat":',
        '    out = {"ok": True, "found": True, "kcat": 250.0, "unit": "1/s",',
        '           "citation": {"source": "PubMed", "reference_id": "2"},',
        '           "vmax": 0.25, "vmaxValidation": {"ok": True, "flagged": False}, **base}',
        'else:',
        '    out = {"ok": True, "found": False, "logs": []}',
        'sys.stdout.write(json.dumps(out))',
        '',
      ].join('\n'),
      'utf-8',
    );
    return file;
  }

  function identifiers(stdout: string) {
    return {
      inputs: /^ {2}inputs {4}\s+(\S+)/m.exec(stdout)?.[1],
      runId: /^ {2}run id {4}\s+(\S+)/m.exec(stdout)?.[1],
    };
  }

  function run() {
    const { stdout, stderr, code } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM_6, '--s0', '10mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: stub() },
    );
    if (code !== 0) throw new Error(`expected 0, got ${code}\n${stdout}\n${stderr}`);
    return identifiers(stdout);
  }

  it('gives two identical runs the same inputs hash and different run ids', () => {
    const first = run();
    const second = run();

    expect(first.inputs).toBeTruthy();
    expect(second.inputs).toBe(first.inputs);

    // And the other one must NOT match, or it is not a unique run id.
    expect(first.runId).toBeTruthy();
    expect(second.runId).not.toBe(first.runId);
  });

  it('says which is which, rather than leaving the reader to find out', () => {
    const { stdout } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM_6, '--s0', '10mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: stub() },
    );
    expect(stdout).toMatch(/same inputs give the same value/);
    expect(stdout).toMatch(/unique per run, never repeats/);
    // The old label claimed a property the value does not have.
    expect(stdout).not.toMatch(/repro key/);
  });

  it('changes the inputs hash when an input changes', () => {
    // A hash that ignored a parameter would look stable for the wrong
    // reason, and this test would be the only thing to notice.
    const base = run();
    const { stdout } = runCli(
      ['simulate', 'mm', '--resolve', ...SYSTEM_6, '--s0', '20mM', '--enzyme-conc', '0.001mM'],
      { TERRIUM_LITERATURE_RUNNER: stub() },
    );
    expect(identifiers(stdout).inputs).not.toBe(base.inputs);
  });
});
