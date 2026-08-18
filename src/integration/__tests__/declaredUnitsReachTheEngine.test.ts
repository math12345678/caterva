/**
 * The unit a user writes must change the number the engine integrates.
 *
 * WHAT THIS COMES FROM
 * --------------------
 * `simulate "michaelis menten" --km 5.2mM --vmax 12.8uM/min --s0 10mM` and
 * the same command with `--vmax 12.8mM/s` produced **identical
 * trajectories**. Those two Vmax values are a factor of 60,000 apart.
 *
 * Three separate places dropped the unit, each of which looked fixed:
 *
 * 1. `commandSimulate`/`commandValidate` read the flags with `parseFloat`,
 *    so `'12.8mM/s'` became `12.8`.
 * 2. The `simulate` dispatcher DID call `parseQuantity` — validating the
 *    unit, using it to decide whether to warn — and then stored
 *    `String(quantity.value)`, throwing it away before the command saw it.
 * 3. `runSimulation` unwrapped `{value, unit}` and kept only `.value`, so
 *    even a correctly-labelled parameter was integrated as a bare number.
 *
 * `parseQuantity` was written specifically to fix this and names the 60,000
 * in its own docstring. It fixed the *reporting*. The arithmetic went on
 * being wrong, and the pipeline told the user
 *
 *     "User supplied a bare number; unit was ASSUMED, not declared"
 *
 * about a unit they had typed — so the one visible symptom pointed away
 * from the cause.
 *
 * WHAT THIS CHECKS
 * ----------------
 * Against an exact closed form, not against the engine's own previous
 * answer. Constitution Rule 1: a trajectory is checked against something
 * that is not the solver checking itself.
 *
 * For Michaelis-Menten the integrated form is implicit,
 *
 *     Km ln(S0/S) + (S0 - S) = Vmax t
 *
 * so the test integrates the residual rather than comparing curves: for the
 * reported final S, the equation must balance for the Vmax the user
 * DECLARED, and must not balance for the one the name-based table would
 * have assumed.
 */
import ScientificPipeline from '../scientificPipeline';

jest.setTimeout(120000);

/** Km ln(S0/S) + (S0 - S) - Vmax·t, in mM. Zero when S is correct. */
function implicitResidual(
  s: number, s0: number, km: number, vmaxPerSec: number, tSec: number
): number {
  return km * Math.log(s0 / s) + (s0 - s) - vmaxPerSec * tSec;
}

async function finalSubstrate(vmax: number, vmaxUnit: string): Promise<number> {
  const pipeline = new ScientificPipeline();
  pipeline.initializeLiterature([]);
  const response = await pipeline.execute({
    query: 'michaelis menten',
    domain: 'mm',
    parameters: { km: 5.2, vmax, s0: 10 },
    providedProvenance: {
      km: { source: 'user', unit: 'mM' },
      vmax: { source: 'user', unit: vmaxUnit },
      s0: { source: 'user', unit: 'mM' }
    }
  });
  const trajectory = response.results?.trajectory ?? [];
  expect(trajectory.length).toBeGreaterThan(1);
  return trajectory[trajectory.length - 1].value;
}

describe('a declared unit reaches the engine', () => {
  test('a Vmax in mM/s is integrated as mM/s', async () => {
    const s = await finalSubstrate(12.8, 'mM/s');
    // 12.8 mM/s empties 10 mM long before the 10 s window closes.
    expect(s).toBeLessThan(0.01);
  });

  test('a Vmax in uM/min is integrated as uM/min, not as mM/s', async () => {
    const s = await finalSubstrate(12.8, 'uM/min');

    // 12.8 uM/min = 2.133e-4 mM/s. Over 10 s that consumes ~1.4e-3 mM of
    // 10 mM, so the substrate is essentially untouched. Before the fix this
    // returned ~0, because the number was integrated as 12.8 mM/s.
    expect(s).toBeGreaterThan(9.99);

    const residual = implicitResidual(s, 10, 5.2, (12.8e-3) / 60, 10);
    expect(Math.abs(residual)).toBeLessThan(1e-3);
  });

  test('the two units give different answers at all', async () => {
    // The assertion the original defect would have failed outright: the
    // two runs were byte-identical.
    const fast = await finalSubstrate(12.8, 'mM/s');
    const slow = await finalSubstrate(12.8, 'uM/min');
    expect(slow - fast).toBeGreaterThan(9);
  });

  test('a Km in uM is converted into the substrate units', async () => {
    // Km 5200 uM is Km 5.2 mM. If the unit were ignored, the engine would
    // see Km = 5200 against s0 = 10 -- first-order rather than saturated,
    // and a visibly different curve.
    const pipeline = new ScientificPipeline();
    pipeline.initializeLiterature([]);
    const response = await pipeline.execute({
      query: 'michaelis menten',
      domain: 'mm',
      parameters: { km: 5200, vmax: 12.8, s0: 10 },
      providedProvenance: {
        km: { source: 'user', unit: 'uM' },
        vmax: { source: 'user', unit: 'mM/s' },
        s0: { source: 'user', unit: 'mM' }
      }
    });
    const trajectory = response.results?.trajectory ?? [];
    const final = trajectory[trajectory.length - 1].value;
    expect(final).toBeLessThan(0.01);
  });
});

/**
 * The window must follow the kinetics through the whole pipeline, not just
 * inside the helper that computes it.
 */
describe('the integration window reaches the engine', () => {
  async function lastTime(vmaxUnit: string): Promise<number> {
    const pipeline = new ScientificPipeline();
    pipeline.initializeLiterature([]);
    const response = await pipeline.execute({
      query: 'michaelis menten',
      domain: 'mm',
      parameters: { km: 5.2, vmax: 12.8, s0: 10 },
      providedProvenance: {
        km: { source: 'user', unit: 'mM' },
        vmax: { source: 'user', unit: vmaxUnit },
        s0: { source: 'user', unit: 'mM' }
      }
    });
    const t = response.results?.trajectory ?? [];
    return t[t.length - 1].time;
  }

  test('a slow reaction is given a long window, a fast one a short window', async () => {
    // Both were 10 s. The slow run therefore showed 0.014% of its reaction
    // as a flat line at 10.000 mM.
    const slow = await lastTime('uM/min');
    const fast = await lastTime('mM/s');

    expect(slow).toBeGreaterThan(1000);
    expect(fast).toBeLessThan(10);
    expect(slow / fast).toBeCloseTo(60000, -2);
  });

  test('the slow run now shows the reaction instead of a flat line', async () => {
    const pipeline = new ScientificPipeline();
    pipeline.initializeLiterature([]);
    const response = await pipeline.execute({
      query: 'michaelis menten',
      domain: 'mm',
      parameters: { km: 5.2, vmax: 12.8, s0: 10 },
      providedProvenance: {
        km: { source: 'user', unit: 'mM' },
        vmax: { source: 'user', unit: 'uM/min' },
        s0: { source: 'user', unit: 'mM' }
      }
    });
    const trajectory = response.results?.trajectory ?? [];
    const final = trajectory[trajectory.length - 1].value;

    // 5% of 10 mM remaining at the right-hand edge, by construction.
    expect(final).toBeCloseTo(0.5, 1);
    // And the curve is a curve: before this, every point read 10.000.
    expect(trajectory[0].value - final).toBeGreaterThan(9);
  });
});
