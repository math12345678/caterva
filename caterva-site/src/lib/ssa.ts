/**
 * Exact Gillespie SSA (direct method), in the browser, for the shell's
 * `gillespie_ssa*` commands.
 *
 * Two of Caterva's live domains: first-order decay A -> B (propensity k·a)
 * and bimolecular association A + B -> C (propensity k·a·b). Each has one
 * reaction channel, so the direct method reduces to: wait an exponential
 * time with rate equal to the propensity, fire, repeat.
 *
 * The seeds are mulberry32 seeds, not numpy's. A path here is not the path
 * `python -m caterva.cli ssa --seed 1` prints; the distribution it is drawn
 * from is the same, and that is what the checks below test.
 */

import { mulberry32 } from './md.ts';

export interface SSAResult {
  /** A at each requested sample time. */
  a: number[];
  events: number;
  /** a + b = a0 (decay) or a + c = a0 and b + c = b0 (association) after every event. */
  conserved: boolean;
}

export interface DecayOptions {
  /**
   * A deliberate bug for `mutate gillespie_ssa`: the waiting time written
   * without its parentheses, `-ln(u) / k * a`, which multiplies by the count
   * the propensity should divide by.
   */
  precedenceBug?: boolean;
  /**
   * A biased sampler, for tests/terminal.test.mjs: the chain decays at
   * k·rateScale while the check still expects k. A bias small enough to
   * move the ensemble mean by a few standard errors is what pins the
   * check's tolerance; the precedence bug is too gross to.
   */
  rateScale?: number;
}

/** The value of a step function, sampled at `at`, from its jump times. */
function sampler(at: number[]) {
  const out: number[] = new Array(at.length);
  let next = 0;
  return {
    /** Record `value` for every sample time before `t`. */
    until(t: number, value: number) {
      while (next < at.length && at[next] < t) out[next++] = value;
    },
    out,
  };
}

/** A -> B with propensity k·a, from a(0) = a0, up to time `end`. */
export function ssaDecay(
  a0: number,
  k: number,
  end: number,
  seed: number,
  at: number[],
  opts: DecayOptions = {},
): SSAResult {
  const rand = mulberry32(seed);
  const s = sampler(at);
  let a = a0;
  let b = 0;
  let t = 0;
  let events = 0;
  let conserved = true;
  const rate = k * (opts.rateScale ?? 1);
  while (a > 0 && rate > 0) {
    const u = 1 - rand(); // (0, 1]: ln(0) never happens
    const tau = opts.precedenceBug ? (-Math.log(u) / rate) * a : -Math.log(u) / (rate * a);
    if (t + tau > end) break;
    t += tau;
    s.until(t, a);
    a -= 1;
    b += 1;
    events += 1;
    if (a + b !== a0) conserved = false;
  }
  s.until(Infinity, a);
  return { a: s.out, events, conserved };
}

/** A + B -> C with propensity k·a·b. */
export function ssaAssociation(
  a0: number,
  b0: number,
  k: number,
  end: number,
  seed: number,
  at: number[],
): SSAResult {
  const rand = mulberry32(seed);
  const s = sampler(at);
  let a = a0;
  let b = b0;
  let c = 0;
  let t = 0;
  let events = 0;
  let conserved = true;
  while (a > 0 && b > 0 && k > 0) {
    const u = 1 - rand();
    const tau = -Math.log(u) / (k * a * b);
    if (t + tau > end) break;
    t += tau;
    s.until(t, a);
    a -= 1;
    b -= 1;
    c += 1;
    events += 1;
    if (a + c !== a0 || b + c !== b0) conserved = false;
  }
  s.until(Infinity, a);
  return { a: s.out, events, conserved };
}

/** Deterministic A(t) for A + B -> C (the ODE the SSA mean tracks at large counts). */
export function odeAssociation(t: number, a0: number, b0: number, k: number): number {
  if (a0 === b0) return a0 / (1 + k * a0 * t);
  return (a0 - b0) / (1 - (b0 / a0) * Math.exp(-k * (a0 - b0) * t));
}

export interface EnsembleCheck {
  expected: number;
  mean: number;
  /** The allowed |mean - expected|. */
  tolerance: number;
  pass: boolean;
  conserved: boolean;
  runs: number;
}

/**
 * Mean final A over seeds 0..runs-1 against a0·e^(-k·end).
 *
 * A(t) for a first-order death chain is exactly Binomial(a0, e^(-kt)), so
 * the standard error of the mean is sqrt(a0·p·(1-p)/runs); the tolerance is
 * 3 of them. Parameters and rule are those of
 * caterva/tests/test_gillespie_ssa_correctness.py::test_mean_a_tracks_exp_decay
 * (a0 4000, k 0.5, end 10, 50 seeds).
 */
export function checkDecayMean(
  a0 = 4000,
  k = 0.5,
  end = 10,
  runs = 50,
  opts: DecayOptions = {},
): EnsembleCheck {
  const p = Math.exp(-k * end);
  const expected = a0 * p;
  let sum = 0;
  let conserved = true;
  for (let seed = 0; seed < runs; seed++) {
    const r = ssaDecay(a0, k, end, seed, [end], opts);
    sum += r.a[0];
    conserved &&= r.conserved;
  }
  const mean = sum / runs;
  const tolerance = 3 * Math.sqrt((a0 * p * (1 - p)) / runs);
  return { expected, mean, tolerance, pass: Math.abs(mean - expected) < tolerance, conserved, runs };
}

/**
 * Mean final A over seeds 0..runs-1 against the ODE, within 3% of it: the
 * rule of caterva/tests/test_gillespie_ssa_bimolecular_correctness.py
 * (TestOdeReference, 40 seeds).
 */
export function checkAssociationMean(
  a0: number,
  b0: number,
  k: number,
  end = 10,
  runs = 40,
): EnsembleCheck {
  const expected = odeAssociation(end, a0, b0, k);
  let sum = 0;
  let conserved = true;
  for (let seed = 0; seed < runs; seed++) {
    const r = ssaAssociation(a0, b0, k, end, seed, [end]);
    sum += r.a[0];
    conserved &&= r.conserved;
  }
  const mean = sum / runs;
  const tolerance = 0.03 * expected;
  return { expected, mean, tolerance, pass: Math.abs(mean - expected) < tolerance, conserved, runs };
}
