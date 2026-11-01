/**
 * A write that failed has to reach the document, not just the terminal.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `simulate --resolve --export-model out.omex` printed a red
 * `✗ Model not written` line, wrote nothing, and emitted a `--json`
 * document whose `exports` block was byte-identical to a successful run:
 *
 *     "exports": { "model": "out.omex", "citations": null }
 *
 * Under `--json` the red line is suppressed on purpose -- one
 * machine-readable document on stdout and nothing else -- so for the
 * caller that reads the document, the failure did not exist.
 *
 * The verdict was never missing. `exportModel` returns
 * `{ ok: false, error }`; `writeExports` read it, printed it, and returned
 * `void`. Computed and not delivered, to the one consumer with no other
 * way to learn it.
 *
 * The comment that stood over that block argued a caller could `stat()`
 * the path instead. It cannot answer the question: a stale file left by an
 * earlier run at the same path exists and is wrong, so "a file is there"
 * and "this run wrote it" are different facts, and only the writer knows
 * which.
 *
 * HOW THE FAILURE IS FORCED
 * -------------------------
 * The destination is inside a directory that does not exist, so the write
 * fails in `exportArtifacts.writeFile` on every platform, with no
 * dependency on which optional Python modules happen to be installed. The
 * defect was FOUND with `libsedml` missing, but a test that reproduced it
 * that way would go quiet the moment someone ran `make setup`.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

jest.setTimeout(300_000);

let tmp: string;

beforeAll(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-export-outcome-'));
});

afterAll(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

/** A literature runner that resolves km and kcat without touching a network. */
function stub(): string {
  const file = path.join(tmp, 'stub.py');
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

function runJson(extra: string[]): { doc: Record<string, any>; code: number } {
  const args = [
    'simulate', 'mm', '--resolve',
    '--enzyme', 'lactate dehydrogenase',
    '--substrate', 'pyruvate',
    '--organism', 'Homo sapiens',
    '--s0', '10mM', '--enzyme-conc', '0.001mM',
    '--json', ...extra,
  ];
  let stdout = '';
  let code = 0;
  try {
    stdout = execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      env: { ...process.env, CATERVA_LITERATURE_RUNNER: stub() },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 240_000,
    });
  } catch (err) {
    const e = err as { stdout?: string; status?: number };
    stdout = e.stdout ?? '';
    code = e.status ?? 1;
  }
  // Under --json the document is the only thing on stdout. If prose has
  // leaked in front of it this throws, which is the correct outcome: that
  // is ADR 0077's defect and it would be hidden by a tolerant parser.
  return { doc: JSON.parse(stdout), code };
}

describe('the exports block reports what happened, not what was asked for', () => {
  it('says written.model === false when the file could not be written', () => {
    const unwritable = path.join(tmp, 'no-such-directory', 'out.xml');
    const { doc } = runJson(['--export-model', unwritable]);

    // The run itself succeeded -- this is specifically about the export.
    expect(doc.ok).toBe(true);
    expect(doc.status).toBe('ran');

    // The requested path is still reported, as it always was.
    expect(doc.exports.model).toBe(unwritable);

    // ...and now so is the outcome. This is the assertion the old code
    // failed: `written` did not exist, and `exports.model` alone was
    // identical to a successful run.
    expect(doc.exports.written.model).toBe(false);

    // Proof the file really is absent, so the assertion above is about a
    // real failed write rather than a field that always says false.
    expect(fs.existsSync(unwritable)).toBe(false);
  });

  it('says written.model === true when the file was written', () => {
    // The other direction, and it is not optional: a `written` field
    // hardcoded to false would pass the test above and be worthless.
    const good = path.join(tmp, 'written.xml');
    const { doc } = runJson(['--export-model', good]);

    expect(doc.exports.written.model).toBe(true);
    expect(fs.existsSync(good)).toBe(true);
  });

  it('distinguishes "not requested" from "requested and failed"', () => {
    // null, not false. A caller that cannot tell these apart reads a run
    // nobody asked anything of as a run that failed to deliver.
    const { doc } = runJson([]);
    expect(doc.exports.written.model).toBeNull();
    expect(doc.exports.written.citations).toBeNull();
  });
});
