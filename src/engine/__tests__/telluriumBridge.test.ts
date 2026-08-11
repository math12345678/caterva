/**
 * The bridge to the real engine.
 *
 * `ScientificPipeline.runSimulation` used to be a hand-rolled
 * forward-Euler Michaelis-Menten loop with `parameters.km?.value || 5.0`,
 * `|| 10.0` and `|| 1.0` fallbacks. A missing Km silently became 5.0 and
 * the run continued, producing a trajectory and a provenance record for a
 * number nothing supplied.
 *
 * These tests run the ACTUAL Python engine -- the same
 * tellurium_runner.py the production api-server spawns -- so they verify
 * the wiring rather than a mock of it. They are skipped, loudly, if the
 * engine cannot be started, because a green tick from a suite that
 * silently skipped its only real assertion is worse than a red one.
 */
import { execFileSync } from 'child_process';

import {
  MissingParameterError,
  REPO_ROOT,
  extractSeries,
  resolvePythonExecutable,
  runTellurium
} from '../telluriumBridge';

/** Whether the Python engine can actually be run in this environment. */
function engineIsAvailable(): boolean {
  try {
    execFileSync(
      resolvePythonExecutable(REPO_ROOT),
      ['-c', 'import Tellurium.tellurium_engine'],
      { cwd: REPO_ROOT, env: { ...process.env, PYTHONPATH: REPO_ROOT }, stdio: 'pipe' }
    );
    return true;
  } catch {
    return false;
  }
}

const ENGINE_AVAILABLE = engineIsAvailable();
const describeEngine = ENGINE_AVAILABLE ? describe : describe.skip;

if (!ENGINE_AVAILABLE) {
  // Printed rather than swallowed: a reader must be able to tell "passed"
  // from "did not run".
  console.warn(
    '\n[telluriumBridge.test] The Python engine could not be imported, so ' +
    'the tests that exercise the real simulation are SKIPPED, not passing.\n'
  );
}

describe('refusing to invent parameters', () => {
  // These need no engine: the check runs before the process is spawned,
  // which is the point -- a missing parameter must not reach a simulator
  // that might default it.
  it('throws MissingParameterError instead of defaulting a missing Km', async () => {
    await expect(
      runTellurium('mm', { vmax: 10, s0: 100 }, { required: ['km', 'vmax', 's0'] })
    ).rejects.toThrow(MissingParameterError);
  });

  it('names every missing parameter, not just the first', async () => {
    try {
      await runTellurium('mm', {}, { required: ['km', 'vmax', 's0'] });
      throw new Error('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(MissingParameterError);
      expect((error as MissingParameterError).missing).toEqual([
        'km',
        'vmax',
        's0'
      ]);
    }
  });

  it('treats an explicit null as missing', async () => {
    // The pipeline maps absent values to null when building the engine
    // payload, so null must be refused exactly like undefined.
    await expect(
      runTellurium('mm', { km: null, vmax: 10, s0: 100 }, { required: ['km'] })
    ).rejects.toThrow(MissingParameterError);
  });
});

describeEngine('running the real Tellurium engine', () => {
  jest.setTimeout(120_000);

  it('returns a trajectory from the Python engine', async () => {
    const result = await runTellurium(
      'mm',
      { km: 5.0, vmax: 10.0, s0: 100.0, end: 10.0 },
      { required: ['km', 'vmax', 's0'] }
    );

    expect(result.ok).toBe(true);
    expect(result.domain).toBe('mm');
    expect(result.trajectory.length).toBeGreaterThan(1);

    const { key, points } = extractSeries(result.trajectory, '[S]');
    expect(key).toBe('[S]');
    expect(points[0]!.value).toBeCloseTo(100.0, 6);
  });

  it('produces a monotonically decreasing substrate curve', async () => {
    // Michaelis-Menten with no product back-reaction: [S] must not rise.
    // The old hand-rolled loop clamped with Math.max(0, ...), which could
    // hide a step size large enough to overshoot into negative substrate.
    const result = await runTellurium(
      'mm',
      { km: 5.0, vmax: 10.0, s0: 100.0, end: 10.0 },
      { required: ['km', 'vmax', 's0'] }
    );
    const { points } = extractSeries(result.trajectory, '[S]');

    for (let i = 1; i < points.length; i++) {
      expect(points[i]!.value).toBeLessThanOrEqual(points[i - 1]!.value + 1e-9);
      expect(points[i]!.value).toBeGreaterThanOrEqual(0);
    }
  });

  it('conserves mass: [S] + [P] stays at s0', async () => {
    // A property of the model that no amount of solver tuning should
    // break, and one the Euler loop did break whenever its clamp fired.
    const result = await runTellurium(
      'mm',
      { km: 5.0, vmax: 10.0, s0: 100.0, end: 10.0 },
      { required: ['km', 'vmax', 's0'] }
    );

    for (const point of result.trajectory) {
      const s = point['[S]'];
      const p = point['[P]'];
      if (s === undefined || p === undefined) continue;
      expect(s + p).toBeCloseTo(100.0, 6);
    }
  });

  it('is deterministic across runs for a deterministic domain', async () => {
    const parameters = { km: 5.0, vmax: 10.0, s0: 100.0, end: 10.0 };
    const first = await runTellurium('mm', parameters, {});
    const second = await runTellurium('mm', parameters, {});
    expect(second.trajectory).toEqual(first.trajectory);
  });

  it('rejects a parameter the engine silently ignores', async () => {
    // `t_end` and `n_points` are NOT what tellurium_runner.py reads -- it
    // reads `end` and `points`. Sending the wrong names was nearly
    // undetectable, because the runner's default `end` is also 10.0: the
    // window looked right while the resolution silently stayed at the
    // default 51 instead of the 101 requested. The engine echoes the
    // parameters it used, so anything absent from the echo was dropped.
    await expect(
      runTellurium('mm', { km: 5, vmax: 10, s0: 100, t_end: 10, n_points: 101 }, {})
    ).rejects.toThrow(/ignored parameter/i);
  });

  it('honours the sampling resolution it is given', async () => {
    const result = await runTellurium(
      'mm',
      { km: 5.0, vmax: 10.0, s0: 100.0, end: 10.0, points: 101 },
      {}
    );
    expect(result.trajectory).toHaveLength(101);
    expect(result.parameters['points']).toBe(101);
  });

  it('surfaces the engine rejection for physically impossible input', async () => {
    // Rule 1 lives in the Python engine and stays authoritative; the
    // bridge must not soften or reinterpret it. A negative Km is not a
    // number the engine should accept.
    await expect(
      runTellurium('mm', { km: -5.0, vmax: 10.0, s0: 100.0 }, {})
    ).rejects.toThrow();
  });
});
