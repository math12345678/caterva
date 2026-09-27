/**
 * Jeske's conditions have to survive the whole way into the file.
 *
 * WHY THIS TEST IS AT THIS LEVEL
 * ------------------------------
 * The Python side can carry `assay_ph` perfectly and the feature still not
 * exist, because `ExportProvenance` had no field for it and nothing would
 * ever be populated. That is the shape `literatureResolver.ts` records
 * about `bufferIdentity`: "Present, correct, unreachable" — resolved for
 * months and dropped because the receiving type had no field.
 *
 * So these spawn the real export script and read the real written file.
 * A test that asserted the payload shape would pass with a Python side
 * that ignored the key.
 */

import { mkdtemp, readFile } from 'fs/promises';
import { tmpdir } from 'os';
import path from 'path';

import { exportModel, type ModelExportRequest } from '../exportArtifacts';

async function destination(name: string): Promise<string> {
  const directory = await mkdtemp(path.join(tmpdir(), 'caterva-assay-'));
  return path.join(directory, name);
}

const REQUEST: ModelExportRequest = {
  domain: 'mm',
  parameters: { km: 2.5, vmax: 0.25, s0: 10 },
  provenance: {
    km: {
      origin: 'resolved',
      citation: 'BRENDA ref 740253',
      organism: 'Homo sapiens',
      citationSource: 'BRENDA',
      referenceId: '740253',
      assayConditions: { ph: 7.4, temperatureC: 25, buffer: 'Tris-HCl' },
    },
    vmax: {
      origin: 'resolved',
      citation: 'BRENDA ref 711801',
      organism: 'Homo sapiens',
      citationSource: 'BRENDA',
      referenceId: '711801',
      // The source reported a pH and said nothing about the rest.
      assayConditions: { ph: 7.4, unreported: ['temperature', 'buffer'] },
    },
  },
};

describe('assay conditions reach the exported artifact', () => {
  it('writes the values into the Antimony comments', async () => {
    const target = await destination('model.txt');
    const outcome = await exportModel(REQUEST, target);
    expect(outcome.error ?? null).toBeNull();
    expect(outcome.ok).toBe(true);

    const text = await readFile(target, 'utf-8');
    // The numbers, not "pH and temperature both reported".
    expect(text).toContain('pH 7.4');
    expect(text).toContain('25 C');
    expect(text).toContain('Tris-HCl');
  }, 60_000);

  it('names the conditions the source did not report', async () => {
    // An omitted line reads as an oversight by whoever produced the file.
    // A line saying the source is silent is a fact about the publication.
    const target = await destination('model.txt');
    expect((await exportModel(REQUEST, target)).ok).toBe(true);

    const text = await readFile(target, 'utf-8');
    expect(text).toContain('NOT REPORTED by the source: temperature, buffer');
  }, 60_000);

  it('writes them into the SBML notes as well', async () => {
    // Both artifacts or neither. A fact present in one export and missing
    // from the other makes the omission look like a property of the
    // measurement rather than of the export path.
    const target = await destination('model.xml');
    const outcome = await exportModel(REQUEST, target);
    expect(outcome.error ?? null).toBeNull();
    expect(outcome.ok).toBe(true);

    const text = await readFile(target, 'utf-8');
    expect(text).toContain('pH 7.4');
    expect(text).toContain('Tris-HCl');
    expect(text).toContain('Not reported by the source');
  }, 60_000);

  it('says nothing about conditions for a parameter that has none', async () => {
    // A conditions line on every parameter of a model whose conditions
    // were never parsed is noise, and noise is how the lines that matter
    // stop being read (ADR 0028).
    const target = await destination('model.txt');
    const bare: ModelExportRequest = {
      ...REQUEST,
      provenance: {
        km: { origin: 'resolved', citation: 'BRENDA ref 740253' },
        vmax: { origin: 'user' },
      },
    };
    expect((await exportModel(bare, target)).ok).toBe(true);

    const text = await readFile(target, 'utf-8');
    expect(text).not.toContain('measured at');
    expect(text).not.toContain('NOT REPORTED');
  }, 60_000);
});
