/**
 * `scientific resolve --mode ... --model-substrate ...` says when a row is
 * evidence against the model's mechanism, as `caterva compose` does.
 *
 * BRENDA ref 739793 gives human LDH and one quinoline sulfonamide 0.00059 mM
 * "competitive versus NADH" and 0.00252 mM "noncompetitive versus pyruvate".
 * `--mode competitive --model-substrate pyruvate` takes the first, which is
 * right: it is the only row stating that mode. The second says that against
 * pyruvate the inhibitor is not competitive. The runner's mode step sets it
 * aside, so this command printed only what the row taken measured ("versus
 * NADH") and never the row that contradicts the model. The runner now sends
 * it as `mechanismEvidence`, found in Python by the function compose uses,
 * and this side reads it and prints it.
 *
 * Asserts on RENDERED OUTPUT for the reason resolveOutput.test.ts gives: a
 * field parsed and never printed passes a shape test and reaches no one, and
 * mocks the resolver the way that file does. This package runs under jest
 * (package.json), so describe/it/expect/jest are its globals.
 */
import { commandResolve } from '../commandResolve';
import {
  mapFoundResult,
  mechanismEvidenceLines,
  resolveKinetic,
  type ResolvedKinetic,
} from '../../literature/literatureResolver';

jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

const QUINOLINE =
  '3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid';
const COMPETITIVE_VS_NADH =
  'pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, competitive versus NADH';
const NONCOMPETITIVE_VS_PYRUVATE =
  'pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, noncompetitive versus pyruvate';

/**
 * These fields as science_agent_runner.py emitted them on 2026-09-30 for
 * `quantity: "ki"`, the quinoline sulfonamide, `inhibitionMode:
 * "competitive"`, `modelSubstrate: "pyruvate"`, reading the committed BRENDA
 * page Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz and reading BRENDA
 * live (Tests/test_runner_contract.py asserts the same `mechanismEvidence`).
 */
const RUNNER_OUTPUT: Record<string, unknown> = {
  source: 'brenda_exact',
  organism: 'Homo sapiens',
  citation: {
    source: 'BRENDA',
    referenceId: '739793',
    url: 'https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27',
  },
  commentary: COMPETITIVE_VS_NADH,
  rowScope: { isoform: null, inhibitionMode: 'competitive', versus: 'NADH', kitzWilson: false },
  mechanismEvidence: {
    value: 0.00252,
    unit: 'mM',
    organism: 'Homo sapiens',
    referenceId: '739793',
    inhibitionMode: 'noncompetitive',
    versus: 'pyruvate',
    conditions: NONCOMPETITIVE_VS_PYRUVATE,
    modelMode: 'competitive',
    modelSubstrate: 'pyruvate',
  },
};

const THE_LINES = [
  'Another row for this inhibitor, 0.00252 mM (Homo sapiens, BRENDA ref 739793), states ' +
    "noncompetitive inhibition versus pyruvate, and pyruvate is this model's substrate.",
  'Measured against it, the inhibitor is not competitive, and a competitive model says it is. ' +
    "That is evidence against this model's mechanism for this inhibitor, and no choice of row " +
    'fixes it.',
  `Other row: ${NONCOMPETITIVE_VS_PYRUVATE}`,
];

describe('mapFoundResult reads mechanismEvidence', () => {
  it('carries the row and the model it contradicts', () => {
    const r = mapFoundResult(RUNNER_OUTPUT, 'ki', 0.00059, 'mM', []);
    expect(r.mechanismEvidence).toEqual(RUNNER_OUTPUT['mechanismEvidence']);
  });

  it('reads null, absence, or a row missing what its sentence needs as none', () => {
    for (const raw of [null, undefined, {}, { ...(RUNNER_OUTPUT['mechanismEvidence'] as object), versus: null }]) {
      const r = mapFoundResult({ ...RUNNER_OUTPUT, mechanismEvidence: raw }, 'ki', 0.00059, 'mM', []);
      expect(r.mechanismEvidence).toBeNull();
    }
  });
});

describe('mechanismEvidenceLines', () => {
  const evidence = mapFoundResult(RUNNER_OUTPUT, 'ki', 0.00059, 'mM', []).mechanismEvidence;

  it('puts the runner\'s fields into words', () => {
    expect(mechanismEvidenceLines('ki', evidence)).toEqual(THE_LINES);
  });

  it('is only about a Ki, and only when there is one', () => {
    expect(mechanismEvidenceLines('km', evidence)).toEqual([]);
    expect(mechanismEvidenceLines('ki', null)).toEqual([]);
  });
});

describe('scientific resolve prints it', () => {
  const mocked = jest.mocked(resolveKinetic);
  const chunks: string[] = [];
  const original = process.stdout.write.bind(process.stdout);

  afterEach(() => {
    (process.stdout as unknown as { write: unknown }).write = original;
    chunks.length = 0;
  });

  async function printed(result: ResolvedKinetic): Promise<string> {
    mocked.mockResolvedValue(result);
    (process.stdout as unknown as { write: unknown }).write = (chunk: unknown) => {
      chunks.push(String(chunk));
      return true;
    };
    const code = await commandResolve({
      ec: '1.1.1.27',
      substrate: QUINOLINE,
      organism: 'Homo sapiens',
      quantity: 'ki',
      inhibitionMode: 'competitive',
      modelSubstrate: 'pyruvate',
      json: false,
    });
    (process.stdout as unknown as { write: unknown }).write = original;
    expect(code).toBe(0);
    return chunks.join('');
  }

  it('under its own heading, after what the row taken measured', async () => {
    const out = await printed(mapFoundResult(RUNNER_OUTPUT, 'ki', 0.00059, 'mM', []));
    expect(out).toContain('KI = 0.00059 mM');
    const measured = out.indexOf('The row measured competitive inhibition versus NADH.');
    const heading = out.indexOf("Evidence against this model's mechanism");
    expect(measured).toBeGreaterThanOrEqual(0);
    expect(heading).toBeGreaterThan(measured);
    for (const line of THE_LINES) expect(out).toContain(`  ${line}`);
  });

  it('prints nothing of it when the runner found no such row', async () => {
    const out = await printed(
      mapFoundResult({ ...RUNNER_OUTPUT, mechanismEvidence: null }, 'ki', 0.00059, 'mM', []),
    );
    expect(out).toContain('KI = 0.00059 mM');
    expect(out).not.toContain('Evidence against');
  });

  it('carries it in --json as the runner sent it', async () => {
    mocked.mockResolvedValue(mapFoundResult(RUNNER_OUTPUT, 'ki', 0.00059, 'mM', []));
    (process.stdout as unknown as { write: unknown }).write = (chunk: unknown) => {
      chunks.push(String(chunk));
      return true;
    };
    await commandResolve({
      ec: '1.1.1.27', substrate: QUINOLINE, organism: 'Homo sapiens', quantity: 'ki',
      inhibitionMode: 'competitive', modelSubstrate: 'pyruvate', json: true,
    });
    (process.stdout as unknown as { write: unknown }).write = original;
    expect(JSON.parse(chunks.join('')).mechanismEvidence).toEqual(RUNNER_OUTPUT['mechanismEvidence']);
  });
});
