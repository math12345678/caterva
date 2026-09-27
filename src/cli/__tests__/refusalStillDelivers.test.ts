/**
 * What a refused run still owes the user.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `simulate --resolve` refuses when a parameter cannot be resolved, which is
 * the behaviour the whole tool is built around. But the refusal path
 * `return`ed two screens before `writeExports`, so a user who typed
 * `--export-model` and `--export-citations` got **no files and no message**.
 *
 * Nothing failed. The exit code was 2, which is correct and which the user
 * was expecting. The missing artifacts were invisible against a backdrop of
 * "the tool told me it could not run" — the natural reading is that nothing
 * was written because nothing ran, and there was no way to tell that from
 * "written somewhere I am not looking".
 *
 * This was found by running the command as a student would rather than by
 * reading the code: the flags are parsed, validated and threaded all the way
 * to a function that the refusal path never reaches. Every unit test of
 * `writeExports` passed, because they all call it directly.
 *
 * THE TWO EXPORTS ARE NOT THE SAME AND ARE NOT TESTED THE SAME
 * ------------------------------------------------------------
 * A bibliography of the parameters that WERE resolved is a real finding that
 * does not stop being real because a different parameter is missing — and
 * the refusal message is precisely the moment a student is being told to go
 * read the literature.
 *
 * A model file is different. Antimony with a hole where `vmax` should be is
 * not a model; it is a file shaped like one, and it fails inside whatever
 * opens it rather than here, where the reason is. So it is withheld — and
 * saying so is the part that was missing.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

let tmpDir: string;

interface RunResult {
  stdout: string;
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
    return { stdout, code: 0 };
  } catch (err) {
    const e = err as { stdout?: string; status?: number };
    return { stdout: e.stdout ?? '', code: e.status ?? 1 };
  }
}

/**
 * A runner that resolves Km and finds no kcat, so `vmax` cannot be bridged.
 *
 * This is a REAL refusal, not a contrived one: BRENDA genuinely does not
 * report [E]0 per row (ADR 0012/0013), so "Km found, Vmax unreachable" is
 * the single most common way a student's first run stops. The artifacts
 * withheld here are withheld on the ordinary path, not an edge case.
 */
function writeStub(): string {
  const file = path.join(tmpDir, 'stub_km_only.py');
  fs.writeFileSync(
    file,
    [
      'import json, sys',
      'payload = json.loads(sys.stdin.read() or "{}")',
      // Km resolves with a citation; every other quantity reports a clean
      // absence. `ok: true` throughout — this is "the literature has
      // nothing", not "the lookup failed", and the two must not be blurred.
      'if payload.get("quantity") == "km":',
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
  return file;
}

const BASE_ARGS = [
  'simulate',
  'michaelis menten',
  '--resolve',
  '--substrate',
  'pyruvate',
  '--organism',
  'Homo sapiens',
  '--enzyme',
  'lactate dehydrogenase',
  '--enzyme-conc',
  '0.01mM',
  '--s0',
  '10mM',
];

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-refusal-'));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

jest.setTimeout(180_000);

describe('a refused run still delivers what it can', () => {
  it('writes the bibliography of what WAS resolved', () => {
    const bib = path.join(tmpDir, 'refs.bib');
    const { stdout, code } = runCli([...BASE_ARGS, '--export-citations', bib], {
      CATERVA_LITERATURE_RUNNER: writeStub(),
    });

    // Still a refusal. Delivering the bibliography must not be mistaken for
    // the run having succeeded.
    expect(code).toBe(2);
    expect(stdout).toContain('Cannot run.');

    expect(fs.existsSync(bib)).toBe(true);
    const contents = fs.readFileSync(bib, 'utf-8');
    // The Km that WAS resolved, with the reference a student would go read.
    expect(contents).toContain('740253');
    expect(contents).toContain('BRENDA');
    // And it says what it does not know, rather than inventing it.
    expect(contents).toMatch(/author.*(NOT known|omitted)/is);
  });

  it('does not write a model with a hole in it, and says why', () => {
    const model = path.join(tmpDir, 'model.txt');
    const { stdout, code } = runCli([...BASE_ARGS, '--export-model', model], {
      CATERVA_LITERATURE_RUNNER: writeStub(),
    });

    expect(code).toBe(2);
    // The file is genuinely absent...
    expect(fs.existsSync(model)).toBe(false);
    // ...and the user is told so, by path, with a reason and a next step.
    // Asserting only `existsSync === false` would have PASSED against the
    // original defect, which also wrote nothing — silently. The message is
    // the entire fix, so the message is what this asserts.
    expect(stdout).toContain('Model not written');
    expect(stdout).toContain(model);
    expect(stdout).toMatch(/not a model|hole/i);
  });

  it('still writes the model when the run succeeds', () => {
    // The guard against overcorrecting: a change that suppressed the model
    // export would satisfy the test above and break the feature. This is the
    // case that says the withholding is conditional.
    const model = path.join(tmpDir, 'ok_model.txt');
    const { stdout, code } = runCli(
      [
        'simulate',
        'michaelis menten',
        '--resolve',
        '--substrate',
        'pyruvate',
        '--organism',
        'Homo sapiens',
        '--enzyme',
        'lactate dehydrogenase',
        '--s0',
        '10mM',
        '--vmax',
        '1.2mM/s',
        '--export-model',
        model,
      ],
      { CATERVA_LITERATURE_RUNNER: writeStub() },
    );

    expect(code).toBe(0);
    expect(stdout).toContain('Model written');
    expect(fs.existsSync(model)).toBe(true);
    const antimony = fs.readFileSync(model, 'utf-8');
    // Sauro's mechanism: the provenance travels with the file.
    expect(antimony).toContain('740253');
  });
});

describe('--json is one document, and the exports still happen', () => {
  /**
   * These were missing, and their absence let two defects through.
   *
   * `--json` promises machine-readable output. The human-readable export
   * messages were being appended AFTER the JSON document, so
   * `--json --export-citations X` produced
   * `JSONDecodeError: Extra data: line 39 column 1` — and the tests above
   * all pass, because none of them passes `--json`.
   *
   * Worse on the success path: `if (options.json) { ...; return 0 }` sat
   * ABOVE the `writeExports` call, so a scripted run wrote no files at all.
   * That is ADR 0049's silent non-delivery, surviving in the path where it
   * is quietest — a script does not notice a missing file the way a person
   * reading a terminal does.
   */
  const parse = (stdout: string): Record<string, unknown> => JSON.parse(stdout);

  it('emits parseable JSON when the run is refused and exports were asked for', () => {
    const bib = path.join(tmpDir, 'json_refused.bib');
    const model = path.join(tmpDir, 'json_refused.txt');
    const { stdout, code } = runCli([...BASE_ARGS, '--json', '--export-citations', bib, '--export-model', model], {
      CATERVA_LITERATURE_RUNNER: writeStub(),
    });

    expect(code).toBe(2);
    const doc = parse(stdout) as { status: string; exports: Record<string, unknown> };
    expect(doc.status).toBe('unresolved');

    // The bibliography is still written — a resolved Km stays a finding.
    expect(fs.existsSync(bib)).toBe(true);
    expect(doc.exports['citations']).toBe(bib);

    // The model is not, and the document says so rather than reporting a
    // path that would imply a file on disk.
    expect(fs.existsSync(model)).toBe(false);
    expect(doc.exports['model']).toBeNull();
    expect(String(doc.exports['modelWithheld'])).toMatch(/refused/i);
  });

  it('writes the exports on the successful --json path', () => {
    const bib = path.join(tmpDir, 'json_ok.bib');
    const model = path.join(tmpDir, 'json_ok.txt');
    const { stdout, code } = runCli(
      [
        'simulate', 'michaelis menten', '--resolve',
        '--substrate', 'pyruvate', '--organism', 'Homo sapiens',
        '--enzyme', 'lactate dehydrogenase',
        '--s0', '10mM', '--vmax', '1.2mM/s',
        '--json', '--export-citations', bib, '--export-model', model,
      ],
      { CATERVA_LITERATURE_RUNNER: writeStub() },
    );

    expect(code).toBe(0);
    const doc = parse(stdout) as { status: string; exports: Record<string, unknown> };
    expect(doc.status).toBe('ran');
    expect(fs.existsSync(bib)).toBe(true);
    expect(fs.existsSync(model)).toBe(true);
    expect(doc.exports['model']).toBe(model);
  });

  it('puts nothing but the document on stdout', () => {
    // Stated as a property of the whole stream rather than by checking for
    // particular stray sentences: the next message added to writeExports
    // would slip past a substring check.
    const { stdout } = runCli(
      [...BASE_ARGS, '--json', '--export-citations', path.join(tmpDir, 'only.bib')],
      { CATERVA_LITERATURE_RUNNER: writeStub() },
    );
    expect(() => JSON.parse(stdout)).not.toThrow();
  });
});

describe('the unresolved list names each thing once', () => {
  it('lists s0 exactly once', () => {
    // s0 is in every model's `requires`, so the generic loop reports it —
    // and a leftover hardcoded block reported it again with a byte-identical
    // sentence. Every refusal missing s0 printed the same line twice, and
    // the obvious reading of two identical lines is that there are two
    // different s0s.
    const { stdout, code } = runCli(
      [
        'simulate',
        'michaelis menten',
        '--resolve',
        '--substrate',
        'pyruvate',
        '--organism',
        'Homo sapiens',
        '--enzyme',
        'lactate dehydrogenase',
      ],
      { CATERVA_LITERATURE_RUNNER: writeStub() },
    );

    expect(code).toBe(2);
    const s0Lines = stdout
      .split('\n')
      .filter((line) => /^\s+s0 \(/.test(line));
    expect(s0Lines).toHaveLength(1);
  });

  it('reports no duplicate lines in the unresolved block at all', () => {
    // Stated as a property rather than about s0 specifically. The next
    // parameter to acquire a second check would otherwise reintroduce this
    // with a different name and pass the test above.
    const { stdout } = runCli(
      [
        'simulate',
        'michaelis menten',
        '--resolve',
        '--substrate',
        'pyruvate',
        '--organism',
        'Homo sapiens',
        '--enzyme',
        'lactate dehydrogenase',
      ],
      { CATERVA_LITERATURE_RUNNER: writeStub() },
    );

    const block = stdout.split('Cannot run.')[1]?.split('No value has been')[0] ?? '';
    const items = block
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    expect(items.length).toBeGreaterThan(0);
    expect(new Set(items).size).toBe(items.length);
  });
});
