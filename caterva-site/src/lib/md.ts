/**
 * The page background: particles under a Lennard-Jones-shaped pair force,
 * stepped with velocity Verlet.
 *
 * This is decoration. The core is softened, the force is clamped, the
 * velocities are damped every step and the walls reflect, so it conserves
 * nothing and simulates no system; it is not molecular dynamics and the
 * site does not call it that. Caterva's molecular dynamics is `caterva md`,
 * which sets up GROMACS runs of enzymes. The toy Lennard-Jones domain this
 * background was once described as running was archived on 2026-09-27
 * (archive/legacy_domains/README.md); v0.4.0 is the last release with it.
 */

export interface MDState {
  n: number;
  pos: Float64Array; // 2n — this is a 2D projection for display
  vel: Float64Array; // 2n
  acc: Float64Array; // 2n
  boxW: number;
  boxH: number;
}

/** Deterministic PRNG so the opening frame is identical on every load. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createMD(
  n: number,
  boxW: number,
  boxH: number,
  seed = 42,
  temperature = 0.22,
): MDState {
  const rand = mulberry32(seed);
  const pos = new Float64Array(n * 2);
  const vel = new Float64Array(n * 2);
  const acc = new Float64Array(n * 2);

  // Jittered grid rather than uniform random placement: two particles landing
  // on top of each other sit on the r^-12 wall and the first integration step
  // launches them across the screen. The engine's own spec flags exactly this
  // failure mode for random initialisation.
  const cols = Math.ceil(Math.sqrt((n * boxW) / boxH));
  const rows = Math.ceil(n / cols);
  const dx = boxW / cols;
  const dy = boxH / rows;

  for (let i = 0; i < n; i++) {
    const c = i % cols;
    const r = Math.floor(i / cols);
    pos[i * 2] = (c + 0.5 + (rand() - 0.5) * 0.45) * dx;
    pos[i * 2 + 1] = (r + 0.5 + (rand() - 0.5) * 0.45) * dy;
    vel[i * 2] = (rand() - 0.5) * Math.sqrt(temperature) * 2;
    vel[i * 2 + 1] = (rand() - 0.5) * Math.sqrt(temperature) * 2;
  }

  // Remove centre-of-mass drift, or the whole lattice slowly translates off
  // screen. Same reason the engine subtracts it: total momentum should be zero.
  let cvx = 0;
  let cvy = 0;
  for (let i = 0; i < n; i++) {
    cvx += vel[i * 2];
    cvy += vel[i * 2 + 1];
  }
  cvx /= n;
  cvy /= n;
  for (let i = 0; i < n; i++) {
    vel[i * 2] -= cvx;
    vel[i * 2 + 1] -= cvy;
  }

  return { n, pos, vel, acc, boxW, boxH };
}

/** Interaction range in display pixels. Beyond this the force is negligible. */
export const CUTOFF = 132;

/**
 * Pairwise LJ forces, softened and truncated.
 *
 * The r^-12 core is clamped: an unclamped Lennard-Jones core in a display
 * loop will, on the one frame two particles get close, produce an
 * acceleration large enough to throw a particle off screen and never
 * recover. The clamp is a rendering decision and is deliberately NOT
 * presented anywhere on the site as physics.
 */
export function computeForces(s: MDState): void {
  const { n, pos, acc } = s;
  acc.fill(0);
  const sigma = 46;
  const eps = 26;
  const cutSq = CUTOFF * CUTOFF;

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = pos[i * 2] - pos[j * 2];
      const dy = pos[i * 2 + 1] - pos[j * 2 + 1];
      let r2 = dx * dx + dy * dy;
      if (r2 > cutSq || r2 === 0) continue;
      if (r2 < 90) r2 = 90; // soften the core

      const s2 = (sigma * sigma) / r2;
      const s6 = s2 * s2 * s2;
      let f = ((24 * eps) / r2) * (2 * s6 * s6 - s6);
      if (f > 0.55) f = 0.55;
      if (f < -0.55) f = -0.55;

      acc[i * 2] += f * dx;
      acc[i * 2 + 1] += f * dy;
      acc[j * 2] -= f * dx;
      acc[j * 2 + 1] -= f * dy;
    }
  }
}

/** One velocity Verlet step, with reflecting walls and mild damping. */
export function step(s: MDState, dt: number): void {
  const { n, pos, vel, acc, boxW, boxH } = s;

  for (let i = 0; i < n * 2; i++) {
    pos[i] += vel[i] * dt + 0.5 * acc[i] * dt * dt;
    vel[i] += 0.5 * acc[i] * dt;
  }

  computeForces(s);

  for (let i = 0; i < n * 2; i++) {
    vel[i] += 0.5 * acc[i] * dt;
    vel[i] *= 0.9985; // bleed the energy the force clamp injects
  }

  for (let i = 0; i < n; i++) {
    const x = i * 2;
    const y = i * 2 + 1;
    if (pos[x] < 0) {
      pos[x] = 0;
      vel[x] = Math.abs(vel[x]);
    } else if (pos[x] > boxW) {
      pos[x] = boxW;
      vel[x] = -Math.abs(vel[x]);
    }
    if (pos[y] < 0) {
      pos[y] = 0;
      vel[y] = Math.abs(vel[y]);
    } else if (pos[y] > boxH) {
      pos[y] = boxH;
      vel[y] = -Math.abs(vel[y]);
    }
  }
}
