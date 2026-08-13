/**
 * `scientific sweep` -- what it says about WHERE the model misbehaves.
 *
 * The point of the "Points that break the pattern" block is to name the
 * parameter value at which the behaviour changes. It looked the anomaly up
 * with `computed[outliers.indexOf(outlier)]` -- a position in the already
 * filtered outlier list used as an index into the full sweep -- so with a
 * single outlier it always printed the FIRST point's parameter value. The
 * anomalous number was correct and the parameter it was attributed to was
 * not, which is the failure mode this test exists to prevent: an answer
 * that is confidently pointed at the wrong end of the range.
 *
 * The engine is not involved. `parameterSweep` is mocked so the sweep shape
 * is fixed by hand and the assertion is about the reporting, not about
 * anyone's kinetics.
 */

import type { SweepPoint } from '../advanced-features';

const parameterSweep = jest.fn<Promise<SweepPoint[]>, unknown[]>();

jest.mock('../advanced-features', () => ({
  parameterSweep: (...args: unknown[]) => parameterSweep(...args),
}));

// Imported after the mock is registered so commandSweep binds to it.
// eslint-disable-next-line @typescript-eslint/no-var-requires
import { commandSweep, type SweepOptions } from '../commandSweep';

function optionsFor(points: SweepPoint[]): SweepOptions {
  parameterSweep.mockResolvedValue(points);
  return {
    query: 'hexokinase / glucose',
    parameter: 'km',
    min: 0.1,
    max: 1.0,
    step: 0.1,
    baseParameters: { km: 0.1, vmax: 10, s0: 5 },
    provenance: [],
    request: {},
    json: false,
  };
}

/** Run the command and return everything it wrote to stdout. */
async function runSweep(options: SweepOptions): Promise<{ out: string; code: number }> {
  let out = '';
  const write = jest
    .spyOn(process.stdout, 'write')
    .mockImplementation((chunk: string | Uint8Array) => {
      out += typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString();
      return true;
    });
  try {
    const code = await commandSweep(options);
    return { out, code };
  } finally {
    write.mockRestore();
  }
}

/** A flat sweep with one point that jumps, at a chosen position. */
function sweepWithAnomalyAt(position: number): SweepPoint[] {
  return Array.from({ length: 10 }, (_, i) => ({
    paramValue: Number((0.1 * (i + 1)).toFixed(1)),
    finalValue: i === position ? 50 : 1 + i * 0.01,
    confidence: 0.9,
  }));
}

describe('commandSweep', () => {
  beforeEach(() => {
    parameterSweep.mockReset();
  });

  it('attributes an anomaly at the end of the range to the last parameter value', async () => {
    const { out, code } = await runSweep(optionsFor(sweepWithAnomalyAt(9)));

    expect(code).toBe(0);
    expect(out).toContain('Points that break the pattern');
    expect(out).toContain('km=1: 50.0000');
    expect(out).not.toContain('km=0.1: 50.0000');
  });

  it('attributes an anomaly in the middle of the range to that parameter value', async () => {
    const { out } = await runSweep(optionsFor(sweepWithAnomalyAt(5)));

    expect(out).toContain('km=0.6: 50.0000');
    expect(out).not.toContain('km=0.1: 50.0000');
  });

  it('still names the first point when the anomaly really is the first point', async () => {
    const { out } = await runSweep(optionsFor(sweepWithAnomalyAt(0)));

    expect(out).toContain('km=0.1: 50.0000');
  });

  // When validation rejects most of the range -- the ordinary outcome at
  // the extremes of a sweep -- only one point is computable. The trend line
  // then has a zero denominator and used to print
  // "trend  decreasing  (slope NaN)": a direction claim from one
  // observation, always pointing down, next to a number that is not one.
  it('does not claim a trend direction when only one point could be computed', async () => {
    const mostlyFailed: SweepPoint[] = Array.from({ length: 5 }, (_, i) => ({
      paramValue: Number((0.1 * (i + 1)).toFixed(1)),
      finalValue: i === 2 ? 2.5 : Number.NaN,
      confidence: i === 2 ? 0.9 : 0,
      ...(i === 2 ? {} : { failed: 'km must be positive' }),
    }));

    const { out, code } = await runSweep(optionsFor(mostlyFailed));

    expect(code).toBe(0);
    expect(out).toContain('indeterminate');
    expect(out).toContain('needs at least 2 computed points; 1 available');
    expect(out).not.toContain('NaN');
    expect(out).not.toMatch(/trend\s+decreasing/);
  });

  it('still reports a direction once two points survive', async () => {
    const twoGood: SweepPoint[] = [
      { paramValue: 0.1, finalValue: Number.NaN, confidence: 0, failed: 'km must be positive' },
      { paramValue: 0.2, finalValue: 1.0, confidence: 0.9 },
      { paramValue: 0.3, finalValue: 5.0, confidence: 0.9 },
    ];

    const { out } = await runSweep(optionsFor(twoGood));

    expect(out).toMatch(/trend\s+increasing/);
    expect(out).not.toContain('indeterminate');
  });

  it('says nothing about broken patterns when the sweep is smooth', async () => {
    const smooth: SweepPoint[] = Array.from({ length: 10 }, (_, i) => ({
      paramValue: Number((0.1 * (i + 1)).toFixed(1)),
      finalValue: 1 + i * 0.1,
      confidence: 0.9,
    }));

    const { out, code } = await runSweep(optionsFor(smooth));

    expect(code).toBe(0);
    expect(out).not.toContain('Points that break the pattern');
  });
});
