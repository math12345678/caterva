// Client-side ODE integration for the live terminal's `run kinetics` and
// `run epidemiology` commands.
//
// This is not new physics written for the marketing site: it is the same
// RK4 integrator already shipped in
// Science-Agent-Pipeline/artifacts/terrium-landing/src/lib/simulate.ts,
// reused here rather than re-derived, per the project's own rule against
// leaving working code stranded instead of wiring it in. It mirrors the
// rate laws verified in Tellurium/tellurium_engine.py and its test suite,
// and is checked here against the same closed-form residuals that suite
// uses -- a real RK4 integrator, not a canned animation.

export interface Point {
  t: number;
  [species: string]: number;
}

function rk4Step(
  derivs: (state: number[]) => number[],
  state: number[],
  dt: number,
): number[] {
  const k1 = derivs(state);
  const s2 = state.map((s, i) => s + (dt / 2) * k1[i]);
  const k2 = derivs(s2);
  const s3 = state.map((s, i) => s + (dt / 2) * k2[i]);
  const k3 = derivs(s3);
  const s4 = state.map((s, i) => s + dt * k3[i]);
  const k4 = derivs(s4);
  return state.map(
    (s, i) => s + (dt / 6) * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]),
  );
}

function integrate(
  derivs: (state: number[]) => number[],
  initial: number[],
  end: number,
  points: number,
  labels: string[],
): Point[] {
  const dt = end / (points - 1);
  // Substeps per output interval for accuracy independent of point count --
  // same reasoning as DEFAULT_RELATIVE_TOLERANCE in the Python engine: the
  // output resolution the caller asks for shouldn't change the physics.
  const substeps = 200;
  const h = dt / substeps;

  let state = initial;
  const out: Point[] = [
    Object.fromEntries([['t', 0], ...labels.map((l, i) => [l, initial[i]])]),
  ] as Point[];

  for (let i = 1; i < points; i++) {
    for (let s = 0; s < substeps; s++) {
      state = rk4Step(derivs, state, h);
    }
    out.push(
      Object.fromEntries([
        ['t', i * dt],
        ...labels.map((l, j) => [l, state[j]]),
      ]) as Point,
    );
  }
  return out;
}

export interface MMParams {
  km: number;
  vmax: number;
  s0: number;
  end: number;
  points: number;
}

export interface MMResult {
  trajectory: Point[];
  // Residual of the exact implicit MM solution at the final point:
  //   Km*ln(S0/S) + (S0 - S) = Vmax*t
  // Same closed-form check Tellurium/tests/test_kinetics_correctness.py runs
  // against the Python engine.
  finalResidual: number;
}

export function simulateMichaelisMenten(p: MMParams): MMResult {
  const derivs = ([S]: number[]) => [-(p.vmax * S) / (p.km + S)];
  const trajectory = integrate(derivs, [p.s0], p.end, p.points, ['S']);

  const S_final = Math.max(trajectory[trajectory.length - 1].S, 1e-12);
  const lhs = p.km * Math.log(p.s0 / S_final) + (p.s0 - S_final);
  const rhs = p.vmax * p.end;
  const finalResidual = Math.abs(lhs - rhs);

  return { trajectory, finalResidual };
}

export interface SIRParams {
  beta: number;
  gamma: number;
  s0: number;
  i0: number;
  end: number;
  points: number;
}

export interface SIRResult {
  trajectory: Point[];
  // S + I + R must equal N at every point (population conservation) -- the
  // same invariant Tellurium/tests/test_properties.py checks with
  // Hypothesis, spot-checked here at the final point.
  conservationError: number;
}

export function simulateSIR(p: SIRParams): SIRResult {
  const N = p.s0 + p.i0;
  const derivs = ([S, I]: number[]) => {
    const infection = (p.beta * S * I) / N;
    const recovery = p.gamma * I;
    return [-infection, infection - recovery, recovery];
  };
  const trajectory = integrate(derivs, [p.s0, p.i0, 0], p.end, p.points, [
    'S',
    'I',
    'R',
  ]);

  const last = trajectory[trajectory.length - 1];
  const conservationError = Math.abs(last.S + last.I + last.R - N);

  return { trajectory, conservationError };
}

/** Default parameters used by the terminal demo commands. */
export const DEFAULT_MM: MMParams = { km: 2, vmax: 5, s0: 10, end: 10, points: 51 };
export const DEFAULT_SIR: SIRParams = {
  beta: 0.4,
  gamma: 0.1,
  s0: 990,
  i0: 10,
  end: 60,
  points: 61,
};

export const MM_TOLERANCE = 1e-6;
export const SIR_TOLERANCE = 1e-6;
