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
 * from the cause. See ADR 0117.
 *
 * WHAT THIS CHECKS, AND WHY IT CHANGED
 * ------------------------------------
 * The first version of this file asserted on the FINAL SUBSTRATE: "a Vmax
 * in mM/s empties 10 mM before the 10 s window closes", "a Vmax in uM/min
 * leaves the substrate untouched". Both were true, and both silently
 * depended on `SIMULATION_END_TIME_S = 10` — the hardcoded window that
 * ADR 0118 then replaced with one derived from the kinetics. Every run now
 * ends at 5% remaining whatever the rate, so those assertions failed on a
 * change that was an improvement.
 *
 * **A test pinned to an incidental constant fails when the constant is
 * fixed.** What is actually invariant is the closed form: for
 * Michaelis-Menten,
 *
 *     Km·ln(S0/S) + (S0 - S) = Vmax·t
 *
 * so the trajectory's own (t, S) pairs are checked against the Vmax the
 * user DECLARED, at the times the engine reports rather than times this
 * test assumes. That holds under any window.
 */
import ScientificPipeline from '../scientificPipeline';

jest.setTimeout(180000);

const KM_MM = 5.2;
const S0_MM = 10;

/** Km ln(S0/S) + (S0 - S) - Vmax·t, in mM. Zero when S is right for t. */
function implicitResidual(
  s: number, s0: number, km: number, vmaxPerSec: number, tSec: number
): number {
  return km * Math.log(s0 / s) + (s0 - s) - vmaxPerSec * tSec;
}

async function run(vmaxUnit: string, km = KM_MM, kmUnit = 'mM') {
  const pipeline = new ScientificPipeline();
  pipeline.initializeLiterature([]);
  const response = await pipeline.execute({
    query: 'michaelis menten',
    domain: 'mm',
    parameters: { km, vmax: 12.8, s0: S0_MM },
    providedProvenance: {
      km: { source: 'user', unit: kmUnit },
      vmax: { source: 'user', unit: vmaxUnit },
      s0: { source: 'user', unit: 'mM' }
    }
  });
  const trajectory = response.results?.trajectory ?? [];
  expect(trajectory.length).toBeGreaterThan(10);
  return trajectory;
}

/** The largest closed-form residual over the trajectory, in mM. */
function worstResidual(
  trajectory: Array<{ time: number; value: number }>,
  vmaxPerSec: number,
  km = KM_MM
): number {
  return Math.max(
    ...trajectory
      .filter(p => p.value > 1e-6)
      .map(p => Math.abs(implicitResidual(p.value, S0_MM, km, vmaxPerSec, p.time)))
  );
}

describe('a declared unit reaches the engine', () => {
  test('a Vmax in uM/min is integrated as uM/min', async () => {
    const trajectory = await run('uM/min');
    // 12.8 uM/min expressed in mM/s.
    expect(worstResidual(trajectory, 12.8e-3 / 60)).toBeLessThan(1e-2);
  });

  test('a Vmax in mM/s is integrated as mM/s', async () => {
    const trajectory = await run('mM/s');
    expect(worstResidual(trajectory, 12.8)).toBeLessThan(1e-2);
  });

  test('neither is integrated as the other', async () => {
    // The assertion the original defect fails outright: before the fix both
    // runs were byte-identical, so one of these two had to be wrong.
    const slow = await run('uM/min');
    expect(worstResidual(slow, 12.8)).toBeGreaterThan(1);

    const fast = await run('mM/s');
    expect(worstResidual(fast, 12.8e-3 / 60)).toBeGreaterThan(1);
  });

  test('a Km in uM is converted into the substrate units', async () => {
    // 5200 uM is 5.2 mM. If the unit were ignored the engine would see
    // Km = 5200 against s0 = 10 -- first-order rather than saturated.
    const trajectory = await run('mM/s', 5200, 'uM');
    expect(worstResidual(trajectory, 12.8, 5.2)).toBeLessThan(1e-2);
    expect(worstResidual(trajectory, 12.8, 5200)).toBeGreaterThan(1);
  });
});

describe('the integration window follows the kinetics', () => {
  test('a slow reaction gets a long window and a fast one a short window', async () => {
    // Both were 10 s. The slow run therefore showed 0.014% of its reaction
    // as a flat line at 10.000 mM, printed ten times.
    const slow = await run('uM/min');
    const fast = await run('mM/s');

    const slowEnd = slow[slow.length - 1].time;
    const fastEnd = fast[fast.length - 1].time;

    expect(slowEnd).toBeGreaterThan(1000);
    expect(fastEnd).toBeLessThan(10);
    expect(slowEnd / fastEnd).toBeCloseTo(60000, -2);
  });

  test('the slow run shows a reaction rather than a flat line', async () => {
    const trajectory = await run('uM/min');
    const first = trajectory[0].value;
    const last = trajectory[trajectory.length - 1].value;

    // 5% of S0 remaining at the right-hand edge, by construction.
    expect(last).toBeCloseTo(0.05 * S0_MM, 1);
    // Before this, every printed point read 10.000.
    expect(first - last).toBeGreaterThan(9);
  });

  test('both rates produce the same curve, only the time axis differs', async () => {
    // The strongest statement that units and window are both right: the
    // dimensionless solution does not depend on Vmax, so the two
    // trajectories must agree point-for-point in substrate.
    const slow = await run('uM/min');
    const fast = await run('mM/s');
    expect(slow.length).toBe(fast.length);

    for (let i = 0; i < slow.length; i++) {
      expect(slow[i].value).toBeCloseTo(fast[i].value, 3);
    }
  });
});
