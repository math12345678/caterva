/**
 * Does anything ever POPULATE the conditions on the way to the file?
 *
 * WHY THIS EXISTS SEPARATELY FROM `assayConditionsInExport.test.ts`
 * ----------------------------------------------------------------
 * That file builds its own `ModelExportRequest` and asserts the written
 * artifact carries the conditions. It proves the export path works. It
 * cannot prove anything fills it in — measured by mutation: deleting
 *
 *     assayConditions: row.assayConditions,
 *
 * from the CLI's provenance builder left all four of its tests passing.
 *
 * That is the exact defect `literatureResolver.ts` records about
 * `bufferIdentity`: resolved for months, dropped because the receiving type
 * had no field, and invisible because "the rendering tests mock
 * `resolveKinetic`, so they assert what the CLI does with an object rather
 * than whether the object is ever populated. Deleting the plumbing left all
 * fourteen of them passing."
 *
 * So this one starts at the resolver and finishes at the bytes on disk.
 */

import { mkdtemp, readFile } from 'fs/promises';
import { tmpdir } from 'os';
import path from 'path';

import { commandSimulateResolved } from '../commandSimulateResolved';
import { resolveKinetic } from '../../literature/literatureResolver';

jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

const mockedResolve = resolveKinetic as jest.MockedFunction<typeof resolveKinetic>;

/** A resolved KM whose source stated pH and temperature and no buffer. */
const RESOLVED = {
  found: true,
  value: 2.5,
  unit: 'mM',
  organism: 'Homo sapiens',
  source: 'brenda_exact',
  crossSpecies: false,
  citation: { source: 'BRENDA', reference_id: '740253' },
  assayConditions: {
    ph: 7.4,
    temperatureC: 25,
    buffer: null,
    unreported: ['buffer'],
  },
  logs: [],
  literatureCandidates: [],
};

function silenceStdout(): () => void {
  const original = process.stdout.write.bind(process.stdout);
  (process.stdout as unknown as { write: unknown }).write = () => true;
  return () => {
    (process.stdout as unknown as { write: unknown }).write = original;
  };
}

describe('the conditions travel from the resolver into the written model', () => {
  it('carries what the resolver reported all the way to the file', async () => {
    mockedResolve.mockResolvedValue(RESOLVED as unknown as Awaited<
      ReturnType<typeof resolveKinetic>
    >);

    const directory = await mkdtemp(path.join(tmpdir(), 'terrium-reach-'));
    const target = path.join(directory, 'model.txt');
    const restore = silenceStdout();
    try {
      await commandSimulateResolved({
        ec: '1.1.1.27',
        substrate: 'pyruvate',
        organism: 'Homo sapiens',
        overrides: { s0: '10', vmax: '0.25' },
        json: false,
        exportModel: target,
      });
    } finally {
      restore();
    }

    const text = await readFile(target, 'utf-8');

    // The values the RESOLVER reported — nothing in this test handed them
    // to the exporter.
    expect(text).toContain('pH 7.4');
    expect(text).toContain('25 C');
    // And the condition the source was silent about, named rather than
    // omitted.
    expect(text).toContain('NOT REPORTED by the source: buffer');
  }, 60_000);
});
