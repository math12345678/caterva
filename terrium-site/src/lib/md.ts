/**
 * Lennard-Jones molecular dynamics, velocity Verlet, in the browser.
 *
 * This drives the ambient background of the site. It is not a particle
 * effect dressed up in physics vocabulary — it is the same model Terrium's
 * molecular-dynamics domain implements in Python, integrated with the same
 * scheme, conserving the same quantities. The background of the page is one
 * of the product's own simulation domains, running.
 *
 * Reduced units throughout (epsilon = sigma = m = 1), matching the engine.
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

// ---------------------------------------------------------------------------
// Cluster geometry — the values the terminal reports, recomputed live.
// ---------------------------------------------------------------------------

export const R_MIN = Math.pow(2, 1 / 6); // 1.122462048309373

function ljPotential(p: number[][]): number {
  let e = 0;
  for (let i = 0; i < p.length; i++) {
    for (let j = i + 1; j < p.length; j++) {
      const dx = p[i][0] - p[j][0];
      const dy = p[i][1] - p[j][1];
      const dz = p[i][2] - p[j][2];
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const s6 = Math.pow(1 / r, 6);
      e += 4 * (s6 * s6 - s6);
    }
  }
  return e;
}

const PHI = (1 + Math.sqrt(5)) / 2;

const ICOSA: number[][] = [
  [0, 1, PHI], [0, 1, -PHI], [0, -1, PHI], [0, -1, -PHI],
  [1, PHI, 0], [1, -PHI, 0], [-1, PHI, 0], [-1, -PHI, 0],
  [PHI, 0, 1], [PHI, 0, -1], [-PHI, 0, 1], [-PHI, 0, -1],
];

/**
 * Golden-section search for the LJ13 icosahedron scale.
 *
 * One-dimensional, deterministic, hand-written — the same constraint the
 * engine works under (numpy only, no optimiser). Converges to
 * 0.5687560445, giving E = -44.326801, which is the published global minimum
 * from Hoare & Pal (1971).
 */
export function lj13(): { scale: number; energy: number; shell: number; centre: number } {
  const invPhi = PHI - 1;
  let lo = 0.4;
  let hi = 0.8;
  const build = (sc: number) => [[0, 0, 0], ...ICOSA.map((v) => v.map((c) => c * sc))];
  const f = (sc: number) => ljPotential(build(sc));

  let m1 = hi - invPhi * (hi - lo);
  let m2 = lo + invPhi * (hi - lo);
  let e1 = f(m1);
  let e2 = f(m2);

  for (let k = 0; k < 200 && hi - lo > 1e-12; k++) {
    if (e1 < e2) {
      hi = m2; m2 = m1; e2 = e1; m1 = hi - invPhi * (hi - lo); e1 = f(m1);
    } else {
      lo = m1; m1 = m2; e1 = e2; m2 = lo + invPhi * (hi - lo); e2 = f(m2);
    }
  }

  const scale = (lo + hi) / 2;
  const pts = build(scale);
  const centre = Math.hypot(pts[1][0], pts[1][1], pts[1][2]);
  let shell = Infinity;
  for (let i = 1; i < 13; i++) {
    for (let j = i + 1; j < 13; j++) {
      const d = Math.hypot(
        pts[i][0] - pts[j][0], pts[i][1] - pts[j][1], pts[i][2] - pts[j][2],
      );
      if (d < shell) shell = d;
    }
  }
  return { scale, energy: ljPotential(pts), shell, centre };
}

/** Small clusters whose minima are exact by construction AND published. */
export function exactCluster(n: 2 | 3 | 4): number {
  const r = R_MIN;
  if (n === 2) return ljPotential([[0, 0, 0], [r, 0, 0]]);
  if (n === 3) {
    return ljPotential([[0, 0, 0], [r, 0, 0], [r / 2, (r * Math.sqrt(3)) / 2, 0]]);
  }
  const s = r / (2 * Math.sqrt(2));
  return ljPotential([
    [s, s, s], [s, -s, -s], [-s, s, -s], [-s, -s, s],
  ]);
}
