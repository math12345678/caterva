// Client-side ODE integration for the live "terrium simulate" terminal demo.
//
// This mirrors the physics actually verified in Tellurium/tellurium_engine.py
// and its test suite -- same rate laws, same conserved quantities used to
// check correctness. It is a real RK4 integrator, not a canned animation:
// change the parameters and the trajectory actually changes, and the panel
// shows its own error against the closed-form check the Python suite uses.

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
    Object.fromEntries([["t", 0], ...labels.map((l, i) => [l, initial[i]])]),
  ] as Point[];

  for (let i = 1; i < points; i++) {
    for (let s = 0; s < substeps; s++) {
      state = rk4Step(derivs, state, h);
    }
    out.push(
      Object.fromEntries([
        ["t", i * dt],
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
  // This is the same closed-form check
  // Tellurium/tests/test_kinetics_correctness.py runs against the Python
  // engine. A small residual here is direct evidence the RK4 integration
  // above is actually solving the stated rate law, not just drawing a curve.
  finalResidual: number;
}

export function simulateMichaelisMenten(p: MMParams): MMResult {
  const derivs = ([S]: number[]) => [-(p.vmax * S) / (p.km + S)];
  const trajectory = integrate(derivs, [p.s0], p.end, p.points, ["S"]);

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
  // same invariant Tellurium/tests/test_properties.py checks with Hypothesis
  // across the whole input space, spot-checked here at the final point.
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
    "S",
    "I",
    "R",
  ]);

  const last = trajectory[trajectory.length - 1];
  const conservationError = Math.abs(last.S + last.I + last.R - N);

  return { trajectory, conservationError };
}
