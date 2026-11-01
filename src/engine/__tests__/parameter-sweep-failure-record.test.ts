/**
 * What `runSweep` writes down when a sweep point throws.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * A mutation reverted `runSweep`'s catch block to `finalValue: 0` — the
 * original defect, where a crashed simulation scored a perfect zero and won
 * the sweep — and **every one of the 23 existing tests still passed**.
 *
 * They all construct the `results` array by hand and hand it to
 * `analyzeSweep`. None of them runs `runSweep`, so the line that produces
 * the record was never exercised. The sentinel is the root-cause fix and it
 * had no test; `analyzeSweep`'s filter was catching the consequence, which
 * is defence in depth working, and is not the same as the fix being tested.
 *
 * This is the "a check that cannot fail" pattern with the roles reversed: a
 * check that CAN fail, in a place no test looks.
 */
import { runSweep } from '../parameter-sweep';

// The pipeline is mocked so a sweep point can be made to throw on demand,
// and so this suite needs no network and no solver.
jest.mock('../../integration/scientificPipeline', () => {
  return {
    __esModule: true,
    default: jest.fn().mockImplementation(() => ({
      execute: jest.fn(async ({ parameters }: any) => {
        if (parameters.km === 3) {
          throw new Error('solver diverged');
        }
        return {
          validated: true,
          validationConfidence: 0.9,
          results: { trajectory: [], finalValue: parameters.km * 2, computedMetrics: {} },
          parameterProvenance: {
            vmax: { value: 10, origin: 'resolved', citation: 'BRENDA ref 740253' },
          },
          metadata: { executionTimeMs: 1, literatureSourcesUsed: 2, confidenceScore: 0.9, warnings: [] },
        };
      }),
    })),
  };
});

jest.mock('../../storage/sweep-batch-metrics', () => ({
  recordSweepMetrics: jest.fn(),
  recordSweepJobMetrics: jest.fn(),
}));

describe('runSweep records a failed point as absent, not as zero', () => {
  it('writes finalValue: null when the simulation throws', async () => {
    // THE DEFECT. `finalValue: 0` here made the crashed point the minimum,
    // and the optimum is the minimum, so the sweep recommended whichever
    // parameter set had errored.
    const sweep = await runSweep('michaelis-menten', { vmax: 10, s0: 5 }, [
      { name: 'km', min: 1, max: 3, step: 1 },
    ]);

    const failed = sweep.results.find(r => r.parameters.km === 3)!;

    expect(failed.finalValue).toBeNull();
    expect(failed.finalValue).not.toBe(0);
    expect(failed.validated).toBe(false);
  });

  it('says why the point failed', () => {
    // An absent value with no explanation is an unexplained absence, which
    // reads as missing data rather than as a run that failed for a reason.
    return runSweep('michaelis-menten', { vmax: 10, s0: 5 }, [
      { name: 'km', min: 3, max: 3, step: 1 },
    ]).then(sweep => {
      expect(sweep.results[0]!.error).toBe('solver diverged');
    });
  });

  it('keeps the successful points intact', async () => {
    const sweep = await runSweep('michaelis-menten', { vmax: 10, s0: 5 }, [
      { name: 'km', min: 1, max: 3, step: 1 },
    ]);

    const ok = sweep.results.filter(r => r.validated);
    expect(ok.map(r => r.finalValue)).toEqual([2, 4]);
    expect(ok.every(r => r.error === undefined)).toBe(true);
  });

  it('keeps each point provenance instead of discarding it', async () => {
    // `runSweep` collected five scalar fields off the pipeline response and
    // dropped `parameterProvenance`, so by the time a sweep reached
    // `exportSweepToCSV` there was no citation left to export — the CSV
    // could not have carried one however it was written. ADR 0039's
    // boundary drop, in the engine.
    const sweep = await runSweep('michaelis-menten', { vmax: 10, s0: 5 }, [
      { name: 'km', min: 1, max: 1, step: 1 },
    ]);

    expect(sweep.results[0]!.parameterProvenance).toBeDefined();
    expect(sweep.results[0]!.parameterProvenance!.vmax.citation).toBe('BRENDA ref 740253');
    expect(sweep.results[0]!.literatureSourcesUsed).toBe(2);
  });

  it('does not turn a genuine finalValue of zero into an absence', () => {
    // The other direction. `?? null` was chosen over `|| 0` precisely so a
    // real zero — full substrate consumption, the best possible outcome —
    // survives. `||` would have erased it.
    return runSweep('michaelis-menten', { vmax: 10, s0: 5 }, [
      { name: 'km', min: 0, max: 0, step: 1 },
    ]).then(sweep => {
      expect(sweep.results[0]!.finalValue).toBe(0);
      expect(sweep.results[0]!.finalValue).not.toBeNull();
    });
  });
});
