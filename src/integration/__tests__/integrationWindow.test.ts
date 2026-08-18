/**
 * The integration window must come from the kinetics, not from a constant.
 *
 * WHAT THIS COMES FROM
 * --------------------
 * `SIMULATION_END_TIME_S = 10` was the window for every Michaelis-Menten
 * run, whatever the parameters. For the CLI's own documented example
 * (Km 5.2 mM, Vmax 12.8 μM/min, S0 10 mM) the reaction needs **32 hours**
 * to reach 95% conversion, so ten seconds showed 0.014% of it — a flat line
 * at 10.000 mM, printed ten times.
 *
 * It was invisible until ADR 0117 made units count, because until then
 * every Vmax was integrated as though it were in mM/s, which is the one
 * regime where ten seconds is roughly right.
 *
 * WHAT THIS CHECKS
 * ----------------
 * The window against the closed form it is derived from, and the guards
 * that stop it inventing a timescale it cannot compute.
 */
import {
  DEFAULT_FRACTION_REMAINING,
  INITIAL_RATE_DEPLETION,
  initialRateWindowSeconds,
  substrateDepletionWindowSeconds
} from '../integrationWindow';

/** Substrate at time t, by bisection on Km ln(S0/S) + (S0 - S) = Vmax t. */
function substrateAt(
  t: number, s0: number, km: number, vmaxPerSecond: number
): number {
  let lo = 1e-12;
  let hi = s0;
  for (let i = 0; i < 300; i++) {
    const mid = (lo + hi) / 2;
    if (km * Math.log(s0 / mid) + (s0 - mid) > vmaxPerSecond * t) lo = mid;
    else hi = mid;
  }
  return lo;
}

describe('substrateDepletionWindowSeconds', () => {
  test('the window really does leave the requested fraction', () => {
    // The property, checked against the equation rather than against a
    // remembered number: integrate to the returned t and the substrate
    // must be at f·S0.
    const km = 5.2;
    const s0 = 10;
    const vmax = 12.8e-3 / 60; // 12.8 uM/min in mM/s

    const t = substrateDepletionWindowSeconds({ km, vmaxPerSecond: vmax, s0 });
    expect(t).toBeDefined();

    const remaining = substrateAt(t!, s0, km, vmax);
    expect(remaining / s0).toBeCloseTo(DEFAULT_FRACTION_REMAINING, 6);
  });

  test('it holds across four orders of magnitude of Vmax', () => {
    // A window correct only near the value it was tuned on is the constant
    // it replaced, wearing a formula.
    for (const vmax of [1e-4, 1e-2, 1, 12.8]) {
      const t = substrateDepletionWindowSeconds({
        km: 5.2, vmaxPerSecond: vmax, s0: 10
      });
      expect(t).toBeDefined();
      expect(substrateAt(t!, 10, 5.2, vmax) / 10).toBeCloseTo(0.05, 6);
    }
  });

  test('the window scales inversely with Vmax', () => {
    // 60,000x the rate, 1/60,000th the time. This is the relationship the
    // fixed constant destroyed.
    const slow = substrateDepletionWindowSeconds({
      km: 5.2, vmaxPerSecond: 12.8e-3 / 60, s0: 10
    })!;
    const fast = substrateDepletionWindowSeconds({
      km: 5.2, vmaxPerSecond: 12.8, s0: 10
    })!;
    expect(slow / fast).toBeCloseTo(60000, 0);
  });

  test('a smaller remaining fraction gives a longer window', () => {
    const to5 = substrateDepletionWindowSeconds({
      km: 5.2, vmaxPerSecond: 1, s0: 10, fractionRemaining: 0.05
    })!;
    const to1 = substrateDepletionWindowSeconds({
      km: 5.2, vmaxPerSecond: 1, s0: 10, fractionRemaining: 0.01
    })!;
    expect(to1).toBeGreaterThan(to5);
  });

  test('zero-order limit: with Km = 0 the window is S0(1-f)/Vmax', () => {
    // Km -> 0 removes the logarithmic term, and the closed form collapses
    // to constant-rate depletion. A useful independent check because the
    // answer is arithmetic rather than another bisection.
    const t = substrateDepletionWindowSeconds({
      km: 0, vmaxPerSecond: 2, s0: 10, fractionRemaining: 0.05
    });
    expect(t).toBeCloseTo((10 * 0.95) / 2, 10);
  });

  describe('refuses rather than inventing a timescale', () => {
    const base = { km: 5.2, vmaxPerSecond: 1, s0: 10 };

    test.each([
      ['a zero Vmax', { ...base, vmaxPerSecond: 0 }],
      ['a negative Vmax', { ...base, vmaxPerSecond: -1 }],
      ['a zero S0', { ...base, s0: 0 }],
      ['a negative Km', { ...base, km: -1 }],
      ['a NaN', { ...base, km: NaN }],
      ['an infinite Vmax', { ...base, vmaxPerSecond: Infinity }],
      ['a fraction of 0', { ...base, fractionRemaining: 0 }],
      ['a fraction of 1', { ...base, fractionRemaining: 1 }]
    ])('%s yields undefined', (_label, inputs) => {
      expect(substrateDepletionWindowSeconds(inputs)).toBeUndefined();
    });

    test('undefined is distinguishable from a computed window', () => {
      // The caller falls back to its documented constant on undefined. If
      // this ever returned a number for a broken input, that fallback would
      // never fire and a made-up timescale would be presented as derived.
      expect(substrateDepletionWindowSeconds(base)).toBeGreaterThan(0);
    });
  });
});

/**
 * The two windows answer different questions and must not be the same
 * number.
 *
 * Coupling them made the validator's initial-rate check report "substrate
 * exhausted" on every run — true of the plot window, and a warning about a
 * window nobody had claimed. It dropped confidence on every full-reaction
 * simulation.
 */
describe('the plot window and the initial-rate window are different', () => {
  const km = 5.2;
  const s0 = 10;
  const vmax = 12.8e-3 / 60;

  test('the initial-rate window is far shorter', () => {
    const plot = substrateDepletionWindowSeconds({ km, vmaxPerSecond: vmax, s0 })!;
    const rate = initialRateWindowSeconds({ vmaxPerSecond: vmax, s0 })!;
    expect(rate).toBeLessThan(plot);
    expect(plot / rate).toBeGreaterThan(10);
  });

  test('actual depletion over the initial-rate window is under 5%', () => {
    // The validator bounds depletion by the zero-order worst case, so the
    // window where that bound reaches 5% leaves TRUE depletion below it.
    // Conservative in the right direction, which is the point.
    const rate = initialRateWindowSeconds({ vmaxPerSecond: vmax, s0 })!;
    const remaining = substrateAt(rate, s0, km, vmax);
    const depleted = (s0 - remaining) / s0;
    expect(depleted).toBeLessThan(INITIAL_RATE_DEPLETION);
    // ...and not absurdly conservative either; it should be close to it.
    expect(depleted).toBeGreaterThan(INITIAL_RATE_DEPLETION / 2);
  });

  test('the zero-order bound over that window is exactly the convention', () => {
    const rate = initialRateWindowSeconds({ vmaxPerSecond: vmax, s0 })!;
    expect((vmax * rate) / s0).toBeCloseTo(INITIAL_RATE_DEPLETION, 12);
  });

  test('it refuses the same broken inputs rather than inventing one', () => {
    expect(initialRateWindowSeconds({ vmaxPerSecond: 0, s0: 10 })).toBeUndefined();
    expect(initialRateWindowSeconds({ vmaxPerSecond: 1, s0: 0 })).toBeUndefined();
    expect(initialRateWindowSeconds({ vmaxPerSecond: NaN, s0: 10 })).toBeUndefined();
  });
});
