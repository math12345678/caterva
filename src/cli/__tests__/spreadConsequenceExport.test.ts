/**
 * What the tie does to the model, written to a file a student can keep.
 *
 * The assertion that matters is the one about NOT defaulting. The CLI
 * usually does have a plausible `s0` and `vmax` lying around — they are the
 * settings of the run in progress — which makes filling one in here the
 * easy, helpful-looking mistake. It would silently undo the refusal the
 * Python module exists to make.
 *
 * These spawn the real script. A mocked subprocess would test that this
 * file builds a payload, not that the two sides agree about it, and ADR
 * 0107 records what that costs: `export_citations.py` sat dead on its
 * import line in HEAD while every test passed.
 */

import { mkdtemp, readFile } from 'fs/promises';
import { tmpdir } from 'os';
import path from 'path';

import { exportSpreadConsequence } from '../exportArtifacts';

const TWO_KM = [
  { value: 0.5, selected: true, unit: 'mM', conditions: 'pH 7.4, 25°C', referenceId: '740253' },
  { value: 2.5, unit: 'mM', conditions: 'pH 7.0, 37°C', referenceId: '740999' },
];

async function destination(): Promise<string> {
  const directory = await mkdtemp(path.join(tmpdir(), 'terrium-spread-'));
  return path.join(directory, 'spread.json');
}

describe('exportSpreadConsequence', () => {
  it('writes the model run at each literature value', async () => {
    const target = await destination();
    const outcome = await exportSpreadConsequence(
      { parameter: 'km', candidates: TWO_KM, vmax: 0.25, s0: 10 },
      target,
    );

    expect(outcome.error ?? null).toBeNull();
    expect(outcome.ok).toBe(true);
    const written = JSON.parse(await readFile(target, 'utf-8'));

    expect(written.status).toBe('assessed');
    expect(written.outcomes).toHaveLength(2);
    // The values simulated are the values handed in, and no others.
    expect(written.outcomes.map((o: { value: number }) => o.value).sort()).toEqual([0.5, 2.5]);
    expect(written.reason).toContain('NOT an uncertainty estimate');
  }, 30_000);

  it('does not fill in a missing experimental setting', async () => {
    // No `s0`. The refusal has to survive the trip through the boundary:
    // a caller that supplied a plausible one to avoid an unhelpful-looking
    // result would be the whole point of the module, undone at the last
    // step.
    const target = await destination();
    const outcome = await exportSpreadConsequence(
      { parameter: 'km', candidates: TWO_KM, vmax: 0.25 },
      target,
    );

    expect(outcome.error ?? null).toBeNull();
    expect(outcome.ok).toBe(true);
    const written = JSON.parse(await readFile(target, 'utf-8'));

    expect(written.status).toBe('not_assessed');
    expect(written.reason).toContain('s0 not supplied');
    expect(written.outcomes).toEqual([]);
  }, 30_000);

  it('refuses a request carrying no disagreement', async () => {
    const outcome = await exportSpreadConsequence(
      { parameter: 'km', candidates: [TWO_KM[0]], vmax: 0.25, s0: 10 },
      await destination(),
    );
    expect(outcome.ok).toBe(false);
    expect(outcome.error).toContain('no disagreement');
  }, 30_000);
});
