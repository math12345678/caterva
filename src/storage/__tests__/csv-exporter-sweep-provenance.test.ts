/**
 * The sweep CSV, and the two things it could not say.
 *
 * 1. **No citations.** Not because the exporter omitted them — because
 *    `runSweep` collected five scalar fields off each pipeline response and
 *    discarded `parameterProvenance`. The data was gone before it reached
 *    storage, so no exporter downstream could have carried a source however
 *    it was written. ADR 0039's boundary drop, in the engine.
 *
 * 2. **Failures rendered as zero.** `runSweep`'s catch block recorded a
 *    crashed point as `finalValue: 0`, and the optimum is the minimum
 *    ("minimum substrate remaining = maximum conversion"), so the point
 *    that failed was reported as the best in the sweep.
 *
 * These tests are on the export because the export is the artifact that
 * leaves the building (ADR 0050) — a reader plotting this file has no other
 * route to either fact.
 */
import { exportSweepToCSV } from '../csv-exporter';
import { columnValue, dataLines, splitCsvLine } from './csvTestHelpers';

/** A sweep result shaped as `runSweep` now returns it. */
const SWEEP = {
  query: 'simulate michaelis menten km=? vmax=10 s0=5',
  sweepId: 'sweep_123',
  sweptParameters: [{ name: 'km', min: 1, max: 3, step: 1 }],
  baseParameters: { vmax: 10, s0: 5 },
  results: [
    {
      parameters: { km: 1, vmax: 10, s0: 5 },
      finalValue: 4.0,
      confidence: 0.9,
      validated: true,
      executionTimeMs: 10,
      parameterProvenance: {
        km: { value: 1, origin: 'user' },
        vmax: {
          value: 10,
          origin: 'resolved',
          citation: 'BRENDA ref 740253',
          organism: 'Homo sapiens',
        },
        s0: {
          value: 5,
          origin: 'default',
          note: 'Could not resolve a real S0; experimental condition supplied by caller.',
        },
      },
      literatureSourcesUsed: 2,
    },
    {
      parameters: { km: 2, vmax: 10, s0: 5 },
      finalValue: 2.5,
      confidence: 0.9,
      validated: true,
      executionTimeMs: 10,
    },
    {
      parameters: { km: 3, vmax: 10, s0: 5 },
      finalValue: null,
      confidence: 0,
      validated: false,
      executionTimeMs: 0,
      error: 'solver diverged',
    },
  ],
  analysis: {
    optimalParameters: { km: 2 },
    meanFinalValue: 3.25,
    minFinalValue: 2.5,
    maxFinalValue: 4.0,
    stdDeviation: 0.75,
    pointsAnalyzed: 2,
    pointsExcluded: 1,
  },
};

describe('the sweep export carries its provenance', () => {
  it('names the citation for a parameter held constant', () => {
    // The thing the sweep export could never do, because the engine threw
    // the provenance away before storage ever saw it.
    expect(exportSweepToCSV(SWEEP)).toContain('BRENDA ref 740253');
  });

  it('says which parameter was swept, and that nobody cited it', () => {
    // A swept parameter is an experimental condition — the experimenter
    // chose to vary it — so it needs no citation, and saying so is more
    // useful than a blank cell (ADR 0012/0013).
    const csv = exportSweepToCSV(SWEEP);
    expect(csv).toContain('SWEPT');
    expect(csv).toMatch(/km: 1 to 3 step 1/);
    expect(csv).toContain('not resolved from literature');
  });

  it('does not list the swept parameter among the ones held constant', () => {
    // A mutation that removed the exclusion passed every other test here.
    //
    // It matters because the two blocks make different claims. HELD
    // CONSTANT says "this value did not move, and here is its source".
    // `km` moved across the whole sweep by design. Printing
    // `km = 1 [user]` under HELD CONSTANT states something false about the
    // experiment, and does it in the provenance block — the part of the
    // file a reader consults precisely because they want to know what was
    // varied and what was cited (ADR 0012/0013).
    const csv = exportSweepToCSV(SWEEP);
    const held = csv
      .split('\n')
      .slice(csv.split('\n').findIndex(l => l.includes('HELD CONSTANT')))
      .filter(l => l.startsWith('#   ') || l.startsWith('#       '));

    expect(held.length).toBeGreaterThan(0);
    expect(held.some(l => /vmax/.test(l))).toBe(true);
    expect(held.some(l => /\bkm\b/.test(l))).toBe(false);
  });

  it('carries the note explaining a defaulted parameter', () => {
    expect(exportSweepToCSV(SWEEP)).toMatch(/Could not resolve a real S0/);
  });

  it('marks a parameter with no provenance entry as unknown, not resolved', () => {
    const csv = exportSweepToCSV({
      ...SWEEP,
      results: [
        {
          ...SWEEP.results[0],
          parameterProvenance: { vmax: { value: 10 } },
        },
      ],
    });
    expect(csv).toContain('[unknown]');
  });

  it('spells out that provenance is missing rather than omitting the block', () => {
    // A reader who saw no provenance block would reasonably assume the
    // sweep did not need one. Absence has to be stated.
    const csv = exportSweepToCSV({
      ...SWEEP,
      results: SWEEP.results.map(({ parameterProvenance, ...rest }) => rest),
    });
    expect(csv).toMatch(/No parameter provenance was recorded/);
    expect(csv).not.toContain('HELD CONSTANT');
  });
});

describe('a point that failed does not look like a point that scored zero', () => {
  it('leaves the finalValue cell empty, never 0', () => {
    // The defect: `finalValue: 0` on a crash, and the optimum is the
    // minimum, so the crashed point won the sweep.
    //
    // Asserted on the finalValue COLUMN specifically. An earlier version
    // checked that the whole row contained no "0" anywhere, which is a
    // different and wrong claim — the failed point legitimately has
    // `confidence: 0`, and that zero is a real reading.
    const csv = exportSweepToCSV(SWEEP);
    const failedIndex = dataLines(csv).findIndex(l => l.includes('solver diverged'));
    expect(failedIndex).toBeGreaterThan(0);

    expect(columnValue(csv, 'finalValue', failedIndex)).toBe('');
    expect(columnValue(csv, 'error', failedIndex)).toBe('solver diverged');
    // ...while a point that DID run still shows its number.
    expect(columnValue(csv, 'finalValue', 1)).toBe('4');
  });

  it('says why the point produced nothing', () => {
    // An empty cell with no explanation reads as missing data rather than
    // as a run that failed for a stateable reason.
    expect(exportSweepToCSV(SWEEP)).toContain('solver diverged');
  });

  it('reports how much of the grid the analysis rests on', () => {
    const csv = exportSweepToCSV(SWEEP);
    expect(csv).toContain('pointsAnalyzed,2');
    expect(csv).toContain('pointsExcluded,1');
    expect(csv).toMatch(/1 of 3 point\(s\) produced no usable value/);
  });

  it('renders a refused analysis as empty, not as zero or "null"', () => {
    // When every point failed, analyzeSweep returns null throughout. Those
    // must not surface as 0 (a plottable number) or as the string "null".
    const csv = exportSweepToCSV({
      ...SWEEP,
      analysis: {
        optimalParameters: null,
        meanFinalValue: null,
        minFinalValue: null,
        maxFinalValue: null,
        stdDeviation: null,
        pointsAnalyzed: 0,
        pointsExcluded: 3,
        unanalysableReason: 'None of the 3 sweep point(s) produced a usable result.',
      },
    });
    expect(csv).toContain('optimalParameters,\n');
    expect(csv).toContain('meanFinalValue,\n');
    expect(csv).not.toMatch(/meanFinalValue,(0|null)/);
    expect(csv).toMatch(/None of the 3 sweep point\(s\)/);
  });
});

describe('the data is still readable by anything that skips comments', () => {
  it('puts every provenance line behind a #', () => {
    const csv = exportSweepToCSV(SWEEP);
    const headerRow = csv.split('\n').findIndex(l => l.startsWith('parameterSet'));
    const before = csv.split('\n').slice(0, headerRow);
    expect(before.every(l => l.startsWith('#'))).toBe(true);
  });

  it('emits one data row per sweep point', () => {
    // The `# Analysis` block below the data is comment-prefixed, so a
    // consumer reading with comment="#" sees exactly the grid.
    expect(dataLines(exportSweepToCSV(SWEEP)).length).toBe(1 + SWEEP.results.length);
  });
});
