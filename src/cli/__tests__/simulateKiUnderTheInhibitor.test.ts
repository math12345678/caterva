/**
 * `simulate --resolve` looks each constant up the way BRENDA files it.
 *
 * WHAT WAS WRONG
 * --------------
 * An inhibition model's Ki was looked up under the SUBSTRATE's name, with no
 * inhibitor and no mode:
 *
 *     resolveKinetic({ ..., substrate: options.substrate, quantity: 'ki' })
 *
 * BRENDA files a Ki under its inhibitor, so the lookup asked for a Ki "of"
 * pyruvate and came back with one, or with nothing. `caterva compose` stopped
 * doing this on 2026-09-29 (each constant under its own compound) and the API
 * the same day (queryResolver: a Ki under the inhibitor the query names, none
 * looked up when it names none); since 2026-09-30 the API also sends its
 * model's inhibition mode. This was the third front door, still asking the
 * old way.
 *
 * And `--allow-cross-species`, documented for this command and suggested by
 * every one of its literature refusals, never reached a lookup at all.
 *
 * HOW IT IS TESTED
 * ----------------
 * The resolver is mocked at the module boundary and the tests assert what
 * each lookup SENDS: the payload is where both defects lived, and a fake
 * answer cannot hide a wrong question. The runs are made to stop at the
 * refusal (no `--s0`), so nothing reaches the engine; what the refusal says
 * is asserted from the `--json` document, which is the one output a script
 * reads. The Ki the runner actually chooses for a mode is tested on the
 * committed BRENDA pages in Tests/test_ki_mode_resolution.py, not here.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

import type { ResolverQuery, ResolverResult } from '../../literature/literatureResolver';
import {
  buildNonCompetitiveInhibition,
  buildProductInhibition,
} from '../../engine/sbml-builder';

// This package runs under jest (package.json), so describe/it/expect/jest are
// globals and each jest.mock below is hoisted above the imports, as vi.mock
// is under vitest. jest.requireActual is synchronous where vitest's
// importOriginal is not; the module each factory returns is the same.
jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

// For the runs that get past the refusal: the pipeline's validation gate, the
// engine and the exporters are replaced at their module boundaries, so these
// tests need no Python and assert what the command SENDS and PRINTS. The
// engine's answer used below is a real one (see ENGINE_NONCOMPETITIVE).
jest.mock('../../integration/scientificPipeline', () => ({
  ScientificPipeline: class {
    async execute() {
      return { validated: true, validationErrors: [] };
    }
  },
}));
jest.mock('../inhibitionModels', () => ({
  ...jest.requireActual('../inhibitionModels'),
  runInhibitionModel: jest.fn(),
}));
jest.mock('../exportArtifacts', () => ({
  ...jest.requireActual('../exportArtifacts'),
  exportCitations: jest.fn(),
  exportModel: jest.fn(),
}));

import { resolveKinetic } from '../../literature/literatureResolver';
import { commandSimulateResolved, type SimulateResolvedOptions } from '../commandSimulateResolved';
import { exportCitations, exportModel } from '../exportArtifacts';
import { KI_MODE_OF_MODEL, runInhibitionModel } from '../inhibitionModels';

/** BRENDA 739793's inhibitor of human LDH (docs/USING_CATERVA.md). */
const QUINOLINE =
  '3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid';

const NOTHING = (quantity: 'km' | 'ki' | 'kcat'): ResolverResult => ({
  found: false,
  quantity,
  logs: [],
  candidates: [],
  source: 'not_found',
  isoformsAvailable: [],
  variantCandidatesAvailable: [],
  crossSpeciesOrganismsAvailable: [],
  modesAvailable: [],
});

const LDH: SimulateResolvedOptions = {
  ec: '1.1.1.27',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  // Km and Vmax supplied, so the only lookup a model makes is its Ki.
  overrides: { km: '0.1mM', vmax: '0.01mM/s' },
  json: true,
};

let out: string[];

beforeEach(() => {
  out = [];
  jest.mocked(resolveKinetic).mockReset();
  jest.mocked(runInhibitionModel).mockReset();
  jest.mocked(exportCitations).mockReset();
  jest.mocked(exportModel).mockReset();
  jest.spyOn(process.stdout, 'write').mockImplementation(((chunk: string) => {
    out.push(String(chunk));
    return true;
  }) as typeof process.stdout.write);
  jest.spyOn(process.stderr, 'write').mockImplementation(((chunk: string) => {
    out.push(String(chunk));
    return true;
  }) as typeof process.stderr.write);
});

afterEach(() => {
  jest.restoreAllMocks();
});

/** Every query the command sent the resolver, in order. */
const sent = (): ResolverQuery[] =>
  jest.mocked(resolveKinetic).mock.calls.map((call) => call[0]);

/** The one `--json` document the run wrote. */
const document = (): {
  ok: boolean;
  status: string;
  unresolved: string[];
  provenance: Array<Record<string, unknown>>;
} => JSON.parse(out.join(''));

/** The Ki queries only. */
const kiQueries = (): ResolverQuery[] => sent().filter((q) => q.quantity === 'ki');

describe('--allow-cross-species reaches every lookup', () => {
  it('is sent with the Km and the kcat lookup when given', async () => {
    jest.mocked(resolveKinetic).mockImplementation(async (q) => NOTHING(q.quantity ?? 'km'));
    await commandSimulateResolved({
      ...LDH,
      overrides: {},
      enzymeConc: '0.001mM',
      allowCrossSpecies: true,
    });
    const queries = sent();
    expect(queries.map((q) => q.quantity)).toEqual(['km', 'kcat']);
    for (const q of queries) expect(q.allowCrossSpecies).toBe(true);
  });

  it('is sent as false when not given, never left to a default', async () => {
    jest.mocked(resolveKinetic).mockImplementation(async (q) => NOTHING(q.quantity ?? 'km'));
    await commandSimulateResolved({ ...LDH, overrides: {}, enzymeConc: '0.001mM' });
    for (const q of sent()) expect(q.allowCrossSpecies).toBe(false);
  });
});

describe('a Ki is looked up under the inhibitor, by the model mode', () => {
  it('refuses without --inhibitor, and looks nothing up under the substrate', async () => {
    // The defect: this run used to send { substrate: 'pyruvate', quantity:
    // 'ki' } -- a Ki "of" the model's substrate.
    const code = await commandSimulateResolved({ ...LDH, model: 'noncompetitive' });

    expect(code).toBe(2);
    expect(kiQueries()).toEqual([]);
    const doc = document();
    expect(doc.status).toBe('unresolved');
    expect(doc.unresolved).toContain(
      'ki (not looked up: BRENDA files a Ki under its inhibitor, and no --inhibitor was given)',
    );
  });

  it('sends the inhibitor as the compound, with the mode and the model substrate', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(NOTHING('ki'));
    await commandSimulateResolved({ ...LDH, model: 'noncompetitive', inhibitor: QUINOLINE });

    const [ki, ...others] = kiQueries();
    expect(others).toEqual([]);
    expect(ki).toMatchObject({
      ecNumber: '1.1.1.27',
      organism: 'Homo sapiens',
      quantity: 'ki',
      substrate: QUINOLINE,
      inhibitionMode: 'noncompetitive',
      modelSubstrate: 'pyruvate',
    });
    // No isoform was asked for, so none is sent: an absent key and an empty
    // one mean different things at the runner.
    expect(ki).not.toHaveProperty('isoform');
  });

  it.each([
    ['competitive', 'competitive'],
    ['noncompetitive', 'noncompetitive'],
    // Not competitive, although row_scope.MODE_OF_MOTIF says so for compose's
    // product motif: this command's product rate law is a different
    // equation. See the rate-law test below and KI_MODE_OF_MODEL.
    ['product', 'noncompetitive'],
  ] as const)('--model %s asks for a %s row', async (model, mode) => {
    jest.mocked(resolveKinetic).mockResolvedValue(NOTHING('ki'));
    await commandSimulateResolved({ ...LDH, model, inhibitor: 'oxamate' });
    expect(kiQueries().map((q) => q.inhibitionMode)).toEqual([mode]);
  });

  it('looks up no Ki, and needs no inhibitor, when the Ki is supplied', async () => {
    const code = await commandSimulateResolved({
      ...LDH,
      model: 'competitive',
      overrides: { ...LDH.overrides, ki: '5mM' },
    });
    expect(code).toBe(2); // s0 and i0 are still the student's to give
    expect(sent()).toEqual([]);
    expect(document().unresolved.join(' ')).not.toContain('--inhibitor');
  });

  it('sends --isoform with every lookup, the Ki included', async () => {
    jest.mocked(resolveKinetic).mockImplementation(async (q) => NOTHING(q.quantity ?? 'km'));
    await commandSimulateResolved({
      ...LDH,
      overrides: {},
      enzymeConc: '0.001mM',
      model: 'competitive',
      inhibitor: 'gossypol',
      isoform: 'LDH-A',
    });
    const queries = sent();
    expect(queries.map((q) => q.quantity)).toEqual(['km', 'kcat', 'ki']);
    for (const q of queries) expect(q.isoform).toBe('LDH-A');
  });

  it('carries the Ki under its inhibitor, with what its row measured', async () => {
    // BRENDA 739793's noncompetitive row for human LDH: 0.00252 mM,
    // "noncompetitive versus pyruvate" (Tests/fixtures/ki_mode/README.md).
    // The runner's rowScope for it, as caterva.bind.core reads the row.
    jest.mocked(resolveKinetic).mockResolvedValue({
      found: true,
      quantity: 'ki',
      value: 0.00252,
      unit: 'mM',
      source: 'brenda_exact',
      organism: 'Homo sapiens',
      citation: { source: 'BRENDA', reference_id: '739793' },
      rowScope: { isoform: null, inhibitionMode: 'noncompetitive', versus: 'pyruvate' },
      logs: [],
    } as unknown as ResolverResult);
    await commandSimulateResolved({ ...LDH, model: 'noncompetitive', inhibitor: QUINOLINE });

    const ki = document().provenance.find((row) => row['name'] === 'ki')!;
    expect(ki).toMatchObject({
      value: 0.00252,
      citation: 'BRENDA ref 739793',
      inhibitor: QUINOLINE,
      askedMode: 'noncompetitive',
    });
    expect(ki['rowScope']).toEqual([
      'The row measured noncompetitive inhibition versus pyruvate. A Ki belongs to that mode and that assay.',
    ]);
  });
});

describe('a Ki withheld by mode or isoform says so, in this command\'s flags', () => {
  const withheld = (overrides: Partial<ResolverResult>): ResolverResult =>
    ({ ...NOTHING('ki'), ...overrides }) as ResolverResult;

  it('names the modes BRENDA holds and the --model that takes one', async () => {
    // What the runner answers for rabbit hexokinase and MgADP- asked for a
    // competitive Ki: both rows (BRENDA ref 640206) state mixed inhibition
    // (Tests/test_ki_mode_resolution.py, TestMixed, on the recorded page).
    jest.mocked(resolveKinetic).mockResolvedValue(
      withheld({
        source: 'mode_withheld',
        modesAvailable: ['mixed inhibition versus MgATP2-', 'mixed inhibition versus glucose'],
      }),
    );
    const code = await commandSimulateResolved({
      ...LDH,
      ec: '2.7.1.1',
      substrate: 'glucose',
      organism: 'Oryctolagus cuniculus',
      model: 'competitive',
      inhibitor: 'MgADP-',
    });

    expect(code).toBe(2);
    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toBe(
      'ki (Every row BRENDA holds for this Ki states an inhibition mode other than the one ' +
        '--model asked for (mixed inhibition versus MgATP2-; mixed inhibition versus glucose). ' +
        'A Ki belongs to the mechanism it was measured under. To use one, run with ' +
        "--model noncompetitive; or supply --ki with a constant of this model's mechanism, " +
        'and --cite ki="..." with its source.)',
    );
    // resolve's flag, which this command does not have, is not offered.
    // (A word boundary, since "--model" begins with "--mode".)
    expect(ki).not.toMatch(/--mode\b/);
  });

  it('offers no --model for a mode no model here is of', async () => {
    // A clause the runner would write for a row stating uncompetitive
    // inhibition. Constructed to reach this branch, not read from BRENDA:
    // there is no uncompetitive model in `simulate`, so the row is named and
    // no flag is offered for it.
    jest.mocked(resolveKinetic).mockResolvedValue(
      withheld({ source: 'mode_withheld', modesAvailable: ['uncompetitive inhibition versus NADH'] }),
    );
    await commandSimulateResolved({ ...LDH, model: 'noncompetitive', inhibitor: 'oxamate' });

    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toContain('(uncompetitive inhibition versus NADH)');
    expect(ki).toContain('No --model takes any of them');
    expect(ki).toContain('Supply --ki with a constant');
    expect(ki).not.toContain('run with --model');
  });

  it('names the isoforms BRENDA holds, and --isoform', async () => {
    // Gossypol's three human LDH isoforms in BRENDA 711801. The runner
    // answers isoform_withheld when the one asked for is none of them.
    jest.mocked(resolveKinetic).mockResolvedValue(
      withheld({ source: 'isoform_withheld', isoformsAvailable: ['LDH-A', 'LDH-B', 'LDH-C'] }),
    );
    await commandSimulateResolved({
      ...LDH,
      model: 'competitive',
      inhibitor: 'gossypol',
      isoform: 'LDHAL6A',
    });

    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toContain('only for other isoforms (LDH-A, LDH-B, LDH-C)');
    expect(ki).toContain('pass --isoform with one of those');
  });

  it('keeps the plain miss as a miss, naming the inhibitor', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(NOTHING('ki'));
    await commandSimulateResolved({ ...LDH, model: 'competitive', inhibitor: 'oxamate' });
    expect(document().unresolved).toContain(
      'ki (no inhibition constant for oxamate in the literature for this system)',
    );
  });
});

describe('the refusal hands back a command for the same model', () => {
  it('carries --model and asks for --inhibitor', async () => {
    const code = await commandSimulateResolved({ ...LDH, json: false, model: 'noncompetitive' });
    expect(code).toBe(2);
    const text = out.join('').replace(/\x1b\[[0-9;]*m/g, '');
    const full = text.split('In full')[1] ?? '';
    // Without --model the printed command re-ran plain Michaelis-Menten,
    // which refuses --inhibitor.
    expect(full).toContain('--model noncompetitive');
    expect(full).toContain('--inhibitor "<inhibitor>"');
  });
});

describe('the mode a product model asks for is its rate law\'s', () => {
  it('builds the same rate law as the noncompetitive model, P for I and Kp for Ki', () => {
    // KI_MODE_OF_MODEL.product is 'noncompetitive' BECAUSE of this equality.
    // If the product model is ever rewritten as competitive product
    // inhibition (Km(1 + P/Kp) + S, as compose's motif is), this fails, and
    // the mode it asks for has to change with it.
    const law = (xml: string) =>
      (xml.match(/<kineticLaw>([\s\S]*?)<\/kineticLaw>/)?.[1] ?? '').replace(/\s+/g, ' ').trim();
    const product = law(
      buildProductInhibition({ km: 1, vmax: 1, kp: 1, s0: 1 }).xml,
    );
    const noncompetitive = law(
      buildNonCompetitiveInhibition({ km: 1, vmax: 1, ki: 1, s0: 1, i0: 1 }).xml,
    )
      .replace(/<ci>\s*I\s*<\/ci>/g, '<ci>P</ci>')
      .replace(/<ci>\s*ki\s*<\/ci>/g, '<ci>kp</ci>');

    expect(product.length).toBeGreaterThan(0);
    expect(product).toBe(noncompetitive);
    expect(KI_MODE_OF_MODEL.product).toBe(KI_MODE_OF_MODEL.noncompetitive);
  });
});

describe('the argv parser', () => {
  // Spawned, because these refusals are process exits in scientificCLI.ts.
  // Both exit before any lookup, so they need no network and no runner.
  //
  // Launched the way the other CLI tests launch it (node_modules' ts-node)
  // where that is installed, else with bun, which runs the TypeScript
  // directly. Neither present is an environment failure, and it is thrown as
  // one below rather than read as an exit code.
  const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
  const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');
  const LAUNCHER = fs.existsSync(TS_NODE) ? TS_NODE : 'bun';
  const run = (args: string[]): { code: number; stderr: string } => {
    try {
      execFileSync(LAUNCHER, [path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts'), ...args], {
        cwd: REPO_ROOT,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 120_000,
      });
      return { code: 0, stderr: '' };
    } catch (err) {
      const e = err as { status?: number | null; stderr?: string; signal?: string };
      if (e.status === undefined || e.status === null) {
        // Killed, or the launcher is missing (ENOENT): not an exit code of
        // the CLI's, and must not be able to pass for one.
        throw new Error(
          `CLI did not exit (${LAUNCHER}, signal ${e.signal}): ${String(err).slice(0, 300)}`,
        );
      }
      return { code: e.status, stderr: e.stderr ?? '' };
    }
  };
  const SYSTEM = [
    'simulate', 'mm', '--resolve', '--ec', '1.1.1.27',
    '--substrate', 'pyruvate', '--organism', 'Homo sapiens',
  ];

  it('refuses --inhibitor on plain Michaelis-Menten, which has no Ki', () => {
    const { code, stderr } = run([...SYSTEM, '--inhibitor', 'oxamate', '--s0', '10mM']);
    expect(code).toBe(1);
    expect(stderr).toContain('plain Michaelis-Menten has no Ki');
  }, 150_000);

  it('refuses --inhibitor with no value rather than reading it as absent', () => {
    const { code, stderr } = run([...SYSTEM, '--model', 'competitive', '--inhibitor', '--s0', '10mM']);
    expect(code).toBe(1);
    expect(stderr).toContain('--inhibitor needs a value');
  }, 150_000);

  it('refuses --isoform with no value rather than reading it as absent', () => {
    // Read as absent, every constant would be looked up with no isoform
    // while the user believes one was asked for.
    const { code, stderr } = run([...SYSTEM, '--model', 'competitive', '--inhibitor', 'gossypol', '--isoform', '--s0', '10mM']);
    expect(code).toBe(1);
    expect(stderr).toContain('--isoform needs a value');
  }, 150_000);
});

/**
 * Rabbit hexokinase and MgADP-, asked for a noncompetitive Ki: what the real
 * runner answers on the committed page (Tests/fixtures/recorded/
 * brenda_2.7.1.1.html.gz, 2026-09-30), mapped as literatureResolver maps it:
 * 7.8 mM, BRENDA ref 640206, a row stating mixed inhibition versus glucose.
 */
const MGADP_NONCOMPETITIVE = {
  found: true,
  quantity: 'ki',
  value: 7.8,
  unit: 'mM',
  source: 'brenda_exact',
  organism: 'Oryctolagus cuniculus',
  citation: { source: 'BRENDA', reference_id: '640206' },
  rowScope: { isoform: null, inhibitionMode: 'mixed', versus: 'glucose', kitzWilson: false },
  logs: [],
} as unknown as ResolverResult;

/**
 * The engine's answer for exactly the run below (noncompetitive; Km 0.1 mM,
 * Vmax 0.01 mM/s, [S]0 10 mM, Ki 7.8 mM, [I]0 1 mM, t = 0..10, 101 points),
 * computed by the real `runInhibitionModel` on 2026-09-30. Its first and last
 * points only: the document reports what it is handed, and the test says so
 * by counting what it handed.
 */
const ENGINE_NONCOMPETITIVE = {
  domain: 'sbml',
  viaSbml: true,
  trajectory: [
    { time: 0, '[S]': 10, '[I]': 1, '[P]': 0, '[E]': 1 },
    { time: 10, '[S]': 9.912245058919646, '[I]': 1, '[P]': 0.08775494108035671, '[E]': 1 },
  ],
};

const HEXOKINASE_RUN: SimulateResolvedOptions = {
  ec: '2.7.1.1',
  substrate: 'glucose',
  organism: 'Oryctolagus cuniculus',
  overrides: { km: '0.1mM', vmax: '0.01mM/s', i0: '1mM', s0: '10mM' },
  model: 'noncompetitive',
  inhibitor: 'MgADP-',
  json: true,
  exportModel: 'hexokinase.xml',
  exportCitations: 'hexokinase.bib',
};

describe('a successful inhibition run reports through --json and the exports', () => {
  // The defect: this path printed the human table and returned 0 before the
  // JSON document or writeExports was reached. Reproduced on the committed
  // page: `--json` gave text no parser reads, and neither file was written.

  it('writes one document carrying the Ki under its inhibitor, and the result', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(MGADP_NONCOMPETITIVE);
    jest.mocked(runInhibitionModel).mockResolvedValue(ENGINE_NONCOMPETITIVE);
    jest.mocked(exportCitations).mockResolvedValue({ ok: true, path: 'hexokinase.bib' });

    const code = await commandSimulateResolved(HEXOKINASE_RUN);

    expect(code).toBe(0);
    const doc = JSON.parse(out.join('')) as Record<string, any>;
    expect(doc).toMatchObject({ ok: true, status: 'ran', model: 'noncompetitive' });
    const ki = (doc.provenance as Array<Record<string, unknown>>).find((row) => row['name'] === 'ki')!;
    expect(ki).toMatchObject({
      value: 7.8,
      citation: 'BRENDA ref 640206',
      inhibitor: 'MgADP-',
      askedMode: 'noncompetitive',
    });
    expect((ki['rowScope'] as string[]).join(' ')).toContain('mixed inhibition versus glucose');
    expect(doc.result).toMatchObject({
      engine: 'sbml',
      viaSbml: true,
      species: '[S]',
      initial: 10,
      final: 9.912245058919646,
      points: ENGINE_NONCOMPETITIVE.trajectory.length,
    });
    expect(doc.result.trajectory).toEqual(ENGINE_NONCOMPETITIVE.trajectory);
    // The run the engine was given is the one the table describes.
    expect(jest.mocked(runInhibitionModel).mock.calls[0]).toEqual([
      'noncompetitive',
      { km: 0.1, vmax: 0.01, s0: 10, ki: 7.8, i0: 1, end: 10, points: 101 },
    ]);
  });

  it('writes the citations with the inhibitor, and withholds the model with its reason', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(MGADP_NONCOMPETITIVE);
    jest.mocked(runInhibitionModel).mockResolvedValue(ENGINE_NONCOMPETITIVE);
    jest.mocked(exportCitations).mockResolvedValue({ ok: true, path: 'hexokinase.bib' });

    await commandSimulateResolved(HEXOKINASE_RUN);

    const [cited, destination] = jest.mocked(exportCitations).mock.calls[0]!;
    expect(destination).toBe('hexokinase.bib');
    expect(cited).toEqual([
      expect.objectContaining({
        parameter: 'ki',
        citationSource: 'BRENDA',
        referenceId: '640206',
        inhibitor: 'MgADP-',
      }),
    ]);
    // No exporter here writes a noncompetitive model; writing it as plain
    // Michaelis-Menten would be a file without the inhibitor in it.
    expect(exportModel).not.toHaveBeenCalled();
    const doc = JSON.parse(out.join('')) as Record<string, any>;
    expect(doc.exports).toMatchObject({
      model: null,
      citations: 'hexokinase.bib',
      written: { model: null, citations: true },
    });
    expect(doc.exports.modelWithheld).toMatch(/^No model file is written for an inhibition model yet/);
  });

  it('says the same to a person, after the result', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(MGADP_NONCOMPETITIVE);
    jest.mocked(runInhibitionModel).mockResolvedValue(ENGINE_NONCOMPETITIVE);
    jest.mocked(exportCitations).mockResolvedValue({ ok: true, path: 'hexokinase.bib' });

    const code = await commandSimulateResolved({ ...HEXOKINASE_RUN, json: false });

    expect(code).toBe(0);
    const text = out.join('').replace(/\x1b\[[0-9;]*m/g, '');
    expect(text).toContain('Ki of MgADP-');
    expect(text.indexOf('Result')).toBeLessThan(text.indexOf('Model not written'));
    expect(text).toContain('No model file is written for an inhibition model yet.');
    expect(text).toContain('Citations written hexokinase.bib');
  });

  it('leaves a document when the engine fails', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(MGADP_NONCOMPETITIVE);
    jest.mocked(runInhibitionModel).mockRejectedValue(new Error('engine exited 1'));
    const stdout: string[] = [];
    jest.mocked(process.stdout.write).mockImplementation(((chunk: string) => {
      stdout.push(String(chunk));
      return true;
    }) as typeof process.stdout.write);

    const code = await commandSimulateResolved(HEXOKINASE_RUN);

    expect(code).toBe(2);
    expect(JSON.parse(stdout.join(''))).toMatchObject({
      ok: false,
      status: 'engine_failed',
      error: 'engine exited 1',
    });
  });
});

describe('a Ki you type, with --inhibitor, says whose it is', () => {
  it('puts the inhibitor on the typed Ki row, and looks nothing up', async () => {
    // --inhibitor beside --ki was accepted and read by nothing.
    const code = await commandSimulateResolved({
      ...LDH,
      model: 'competitive',
      overrides: { ...LDH.overrides, ki: '0.0019mM' },
      inhibitor: 'gossypol',
    });
    expect(code).toBe(2); // s0 and i0 are still the student's to give
    expect(sent()).toEqual([]);
    const ki = document().provenance.find((row) => row['name'] === 'ki')!;
    expect(ki).toMatchObject({ value: 0.0019, origin: 'user', inhibitor: 'gossypol' });
    // No mode chose a typed value, and the row does not say one did.
    expect(ki).not.toHaveProperty('askedMode');
  });
});

describe('the command printed "in full" is the run that was asked for', () => {
  const fullCommand = (): { heading: string; command: string } => {
    const text = out.join('').replace(/\x1b\[[0-9;]*m/g, '');
    const after = text.split('What to do next')[1] ?? '';
    const heading = after.split('\n').find((line) => line.includes('In full')) ?? '';
    return { heading: heading.trim(), command: after.split(heading)[1] ?? '' };
  };

  it('carries --ec, --allow-cross-species, --isoform and the values typed', async () => {
    await commandSimulateResolved({
      ...LDH,
      json: false,
      model: 'noncompetitive',
      isoform: 'LDH-A',
      allowCrossSpecies: true,
      userCitations: new Map([['km', 'Smith 2019, PMID 12345']]),
    });
    const { command } = fullCommand();
    expect(command).toContain('--ec "1.1.1.27"');
    // A placeholder where a working identifier was, before.
    expect(command).not.toContain('--enzyme');
    expect(command).toContain('--allow-cross-species');
    expect(command).toContain('--isoform "LDH-A"');
    expect(command).toContain('--km 0.1mM');
    expect(command).toContain('--vmax 0.01mM/s');
    expect(command).toContain('--cite km="Smith 2019, PMID 12345"');
  });

  it('names the placeholder it prints, rather than calling it an example value', async () => {
    await commandSimulateResolved({ ...LDH, json: false, model: 'noncompetitive' });
    const { heading, command } = fullCommand();
    expect(command).toContain('--inhibitor "<inhibitor>"');
    expect(heading).toBe(
      'In full, with the example values above; replace <inhibitor> with your own before running it:',
    );
  });

  it('keeps the plain heading when every value in it is one', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(NOTHING('ki'));
    await commandSimulateResolved({ ...LDH, json: false, model: 'competitive', inhibitor: 'oxamate' });
    expect(fullCommand().heading).toBe('In full, with the example values above:');
  });
});

describe('a refused product model is not switched to another model', () => {
  // Rabbit hexokinase and N-acetyl-D-glucosamine, asked for a noncompetitive
  // Ki: the real runner's answer on the committed page (2026-09-30). BRENDA's
  // one rabbit row (ref 640206, 0.7 mM) says "competitive to glucose".
  const COMPETITIVE_ONLY = {
    ...NOTHING('ki'),
    source: 'mode_withheld',
    modesAvailable: ['competitive inhibition'],
  } as ResolverResult;
  const run = (model: 'product' | 'noncompetitive') =>
    commandSimulateResolved({
      ...LDH,
      ec: '2.7.1.1',
      substrate: 'glucose',
      organism: 'Oryctolagus cuniculus',
      model,
      inhibitor: 'N-acetyl-D-glucosamine',
    });

  it('offers a noncompetitive model the competitive one', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(COMPETITIVE_ONLY);
    await run('noncompetitive');
    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toContain('To use one, run with --model competitive');
  });

  it('offers a product model none, and says why', async () => {
    jest.mocked(resolveKinetic).mockResolvedValue(COMPETITIVE_ONLY);
    await run('product');
    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toContain('(competitive inhibition)');
    expect(ki).not.toContain('run with --model');
    expect(ki).toContain('no other --model is offered');
    // Not the default, which would deny that a competitive model exists.
    expect(ki).not.toContain('none states a mechanism a model here is of');
    expect(ki).toContain('Supply --ki with a constant');
  });
});

describe('an enzyme that was never identified is not "no Ki in the literature"', () => {
  it('prints the runner\'s own sentence, and names --ec', async () => {
    // The runner's live answer for "lactate dehydrogenase" (2026-09-30):
    // it names two enzymes, so no EC number was chosen and nothing searched.
    jest.mocked(resolveKinetic).mockResolvedValue({
      ...NOTHING('ki'),
      source: 'ec_ambiguous',
      logs: [
        "'lactate dehydrogenase' names more than one enzyme: 1.1.98.-, 1.1.1.27. These are " +
          'different proteins, so no EC number was chosen — a wrong one is a citation for ' +
          'the wrong enzyme, not merely a wrong value. Re-run with the EC number you meant.',
      ],
    } as ResolverResult);
    await commandSimulateResolved({
      ...LDH,
      ec: undefined,
      enzyme: 'lactate dehydrogenase',
      model: 'competitive',
      inhibitor: 'gossypol',
    });
    const ki = document().unresolved.find((u) => u.startsWith('ki '))!;
    expect(ki).toContain("'lactate dehydrogenase' names more than one enzyme: 1.1.98.-, 1.1.1.27.");
    // BRENDA's human LDH page files three gossypol Ki rows (ref 711801); the
    // search this sentence reported on never ran.
    expect(ki).not.toContain('no inhibition constant for gossypol');

    // And the next step, printed for a person, is the EC number.
    out = [];
    await commandSimulateResolved({
      ...LDH,
      json: false,
      ec: undefined,
      enzyme: 'lactate dehydrogenase',
      model: 'competitive',
      inhibitor: 'gossypol',
    });
    const next = out.join('').replace(/\x1b\[[0-9;]*m/g, '').split('What to do next')[1] ?? '';
    expect(next).toContain('Name it by EC number with --ec and the lookup runs.');
  });
});
