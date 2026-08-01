/**
 * Wright-Fisher neutral drift, in the browser.
 *
 * This is the same model Terrium's population-genetics domain implements in
 * Python, reimplemented here so the landing page runs the real simulation
 * rather than replaying a recording.
 *
 * Everything is seeded and deterministic: the page renders byte-identically
 * on every load. That is not incidental polish — reproducibility under a
 * fixed seed is one of the product's actual claims, so the page that makes
 * the claim should honour it.
 */

/** Deterministic 32-bit PRNG. Small, fast, and stable across browsers. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Binomial(n, p) as an explicit sum of Bernoulli trials.
 *
 * Deliberately not a normal approximation. At n = 100 the exact sum costs
 * nothing, and the discreteness matters: allele counts are integers, and
 * fixation (p hitting exactly 0 or 1 and staying there) is the phenomenon
 * being shown. A continuous approximation never truly fixes.
 */
function binomial(n: number, p: number, rand: () => number): number {
  if (p <= 0) return 0;
  if (p >= 1) return n;
  let k = 0;
  for (let i = 0; i < n; i++) if (rand() < p) k++;
  return k;
}

export interface DriftResult {
  /**
   * Allele frequency paths, but only for the replicates actually drawn on
   * screen. Retaining all 2000 would cost ~3MB per model for data nothing
   * reads; the mean is accumulated on the fly instead.
   */
  trajectories: Float64Array[];
  /** [generation] -> mean heterozygosity across ALL replicates */
  meanHeterozygosity: Float64Array;
}

export interface DriftOptions {
  /** Number of allele copies per population. Correct diploid value is 2N. */
  alleleCopies: number;
  startingFrequency: number;
  generations: number;
  replicates: number;
  seed: number;
  /** How many individual paths to retain for rendering. */
  keepTrajectories: number;
}

/**
 * Simulate `replicates` independent populations for `generations` generations.
 *
 * Each generation the next allele count is drawn Binomial(alleleCopies, p),
 * then p = count / alleleCopies.
 *
 * `alleleCopies` is a parameter rather than being derived from N inside this
 * function specifically so the page can run the correct model (2N) and the
 * bugged model (N) through identical code. The bug being demonstrated is a
 * real one: dropping the diploid factor of two.
 */
export function simulateDrift(opts: DriftOptions): DriftResult {
  const {
    alleleCopies,
    startingFrequency,
    generations,
    replicates,
    seed,
    keepTrajectories,
  } = opts;

  const rand = mulberry32(seed);
  const trajectories: Float64Array[] = [];
  const hetSum = new Float64Array(generations + 1);

  for (let r = 0; r < replicates; r++) {
    const path = r < keepTrajectories ? new Float64Array(generations + 1) : null;
    let p = startingFrequency;
    if (path) path[0] = p;
    hetSum[0] += 2 * p * (1 - p);

    for (let g = 1; g <= generations; g++) {
      // Once an allele is fixed or lost it stays there forever — there is no
      // mutation in this model. Skipping the draw is not an approximation,
      // it is the same result for less work.
      if (p > 0 && p < 1) p = binomial(alleleCopies, p, rand) / alleleCopies;
      if (path) path[g] = p;
      hetSum[g] += 2 * p * (1 - p);
    }
    if (path) trajectories.push(path);
  }

  for (let g = 0; g <= generations; g++) hetSum[g] /= replicates;

  return { trajectories, meanHeterozygosity: hetSum };
}

/**
 * Closed form: E[H_t] = H_0 * (1 - 1/(2N))^t
 *
 * This is the ground truth the simulation is checked against — an exact
 * analytical result, not a reference implementation. It is the entire reason
 * a wrong simulation is detectable at all.
 */
export function theoreticalHeterozygosity(
  startingFrequency: number,
  alleleCopies: number,
  generations: number,
): Float64Array {
  const h0 = 2 * startingFrequency * (1 - startingFrequency);
  const rate = 1 - 1 / alleleCopies;
  const out = new Float64Array(generations + 1);
  for (let g = 0; g <= generations; g++) out[g] = h0 * Math.pow(rate, g);
  return out;
}

/** Largest absolute gap between two curves. The test's actual assertion. */
export function maxDeviation(a: Float64Array, b: Float64Array): number {
  let m = 0;
  for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i] - b[i]));
  return m;
}

// ---------------------------------------------------------------------------
// Fixed configuration for the page. Exported so the UI can display the exact
// parameters it ran — a simulation whose parameters aren't visible isn't
// evidence of anything.
// ---------------------------------------------------------------------------

export const CONFIG = {
  populationSize: 50,
  correctAlleleCopies: 100, // 2N — correct diploid
  buggedAlleleCopies: 50, //  N — the injected bug
  startingFrequency: 0.5,
  generations: 200,
  /**
   * 2000, not a rounder 200, and the reason matters. At 200 replicates the
   * sampling noise on mean heterozygosity is ~0.029 — which EXCEEDS the 0.02
   * tolerance, so the correct implementation would display FAIL. Measured
   * deviations: 200 reps -> 0.0294, 500 -> 0.0234, 1000 -> 0.0140,
   * 2000 -> 0.0054. At 2000 the correct model clears tolerance by ~3.7x and
   * the bugged model misses it by ~6x, which is the separation the demo needs.
   */
  replicates: 2000,
  displayedTrajectories: 40,
  seed: 42,
  /**
   * Matches the tolerance in Terrium's own Python test. Note this is actually
   * STRICTER here than there: that test uses 5000 replicates, and sampling
   * error scales as 1/sqrt(R).
   */
  tolerance: 0.02,
} as const;

export interface PreparedData {
  theory: Float64Array;
  theoryBugged: Float64Array;
  correct: DriftResult;
  bugged: DriftResult;
  deviationCorrect: number;
  deviationBugged: number;
}

/** Run both models once. Called a single time on mount, never per-frame. */
export function prepare(): PreparedData {
  const {
    correctAlleleCopies,
    buggedAlleleCopies,
    startingFrequency,
    generations,
    replicates,
    seed,
  } = CONFIG;

  const theory = theoreticalHeterozygosity(
    startingFrequency,
    correctAlleleCopies,
    generations,
  );
  const theoryBugged = theoreticalHeterozygosity(
    startingFrequency,
    buggedAlleleCopies,
    generations,
  );

  const keepTrajectories = CONFIG.displayedTrajectories;

  const correct = simulateDrift({
    alleleCopies: correctAlleleCopies,
    startingFrequency,
    generations,
    replicates,
    seed,
    keepTrajectories,
  });
  const bugged = simulateDrift({
    alleleCopies: buggedAlleleCopies,
    startingFrequency,
    generations,
    replicates,
    seed,
    keepTrajectories,
  });

  return {
    theory,
    theoryBugged,
    correct,
    bugged,
    deviationCorrect: maxDeviation(correct.meanHeterozygosity, theory),
    deviationBugged: maxDeviation(bugged.meanHeterozygosity, theory),
  };
}
