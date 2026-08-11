/**
 * Inhibition models: one simulator, more models.
 *
 * `sbml-builder.ts` shipped with 424 lines and a full test file, and
 * nothing in the product called it — an orphan that looked covered because
 * it had tests. `kinetic-models.ts` shipped rate equations for the same
 * models, which would have been a FIFTH implementation of enzyme kinetics
 * had anyone wired them.
 *
 * The route taken instead: SBML from the builder, executed by the Python
 * engine's `sbml` escape-hatch domain — the same solver as every
 * first-class domain. The model definition is TypeScript; the integration
 * stays where it has always been.
 *
 * These tests run the REAL engine, and are skipped loudly if it is
 * unavailable, because a green tick from a suite that silently skipped its
 * only real assertion is worse than a red one.
 */
import { execFileSync } from 'child_process';

import {
  INHIBITION_MODELS,
  runInhibitionModel,
  suggestModel,
} from '../inhibitionModels';
import { REPO_ROOT, resolvePythonExecutable } from '../../engine/telluriumBridge';

function engineIsAvailable(): boolean {
  try {
    execFileSync(
      resolvePythonExecutable(REPO_ROOT),
      ['-c', 'import Tellurium.tellurium_engine'],
      { cwd: REPO_ROOT, env: { ...process.env, PYTHONPATH: REPO_ROOT }, stdio: 'pipe' },
    );
    return true;
  } catch {
    return false;
  }
}

const ENGINE_AVAILABLE = engineIsAvailable();
if (!ENGINE_AVAILABLE) {
  console.warn(
    '\n[inhibitionModels.test] Python engine unavailable; the simulation ' +
      'tests are SKIPPED, not passing.\n',
  );
}
const describeEngine = ENGINE_AVAILABLE ? describe : describe.skip;

const BASE = { km: 0.5, vmax: 0.1, s0: 10, end: 10, points: 51 };

describe('refusing to run on a missing parameter', () => {
  // No engine needed: the check happens before dispatch, which is the
  // point — a missing parameter must not reach a simulator that might
  // default it.
  it('names what is missing rather than defaulting it', async () => {
    await expect(
      runInhibitionModel('noncompetitive', { ...BASE, ki: undefined, i0: 0.1 }),
    ).rejects.toThrow(/needs ki/i);
  });

  it('requires an inhibitor concentration for non-competitive inhibition', async () => {
    await expect(
      runInhibitionModel('noncompetitive', { ...BASE, ki: 0.02, i0: undefined }),
    ).rejects.toThrow(/needs i0/i);
  });
});

describe('the model advisor', () => {
  it('catches a Ki supplied to a model that would ignore it', () => {
    // Running plain `mm` with a Ki silently discards the inhibitor: the
    // run succeeds, the numbers look fine, and the inhibition being
    // studied is simply absent from the result.
    const suggestion = suggestModel({ ki: 0.02, i0: 0.1 });
    expect(suggestion?.model).toBe('competitive');
    expect(suggestion?.why).toMatch(/ignore the inhibitor/i);
  });

  it('reads a Ki with no inhibitor concentration as product inhibition', () => {
    expect(suggestModel({ ki: 0.02 })?.model).toBe('product');
  });

  it('says nothing when there is no inhibitor', () => {
    expect(suggestModel({})).toBeNull();
  });
});

describeEngine('running through the real engine', () => {
  jest.setTimeout(180_000);

  it('runs non-competitive inhibition via the SBML escape hatch', async () => {
    // The engine has no first-class domain for this model, so before this
    // wiring there was no way to simulate it here at all.
    const run = await runInhibitionModel('noncompetitive', {
      ...BASE,
      ki: 0.02,
      i0: 0.1,
    });

    expect(run.viaSbml).toBe(true);
    expect(run.domain).toBe('sbml');
    expect(run.trajectory).toHaveLength(51);
  });

  it('uses the first-class domain for competitive inhibition, not SBML', async () => {
    // Where the engine already has a domain, use it: the well-trodden path
    // stays the default and SBML is only for what it cannot do.
    const run = await runInhibitionModel('competitive', {
      ...BASE,
      ki: 0.02,
      i0: 0.1,
    });

    expect(run.viaSbml).toBe(false);
    expect(run.domain).toBe('mm_competitive_inhibition');
  });

  it('conserves mass in the SBML models', async () => {
    // A property no solver choice should break, and the sharpest check
    // that the generated SBML is actually well-formed chemistry rather
    // than merely valid XML.
    const run = await runInhibitionModel('noncompetitive', {
      ...BASE,
      ki: 0.02,
      i0: 0.1,
    });

    for (const point of run.trajectory) {
      const s = point['[S]'];
      const p = point['[P]'];
      if (s === undefined || p === undefined) continue;
      expect(s + p).toBeCloseTo(BASE.s0, 6);
    }
  });

  it('inhibition slows the reaction relative to no inhibitor', async () => {
    // The whole scientific point of the model. If adding an inhibitor did
    // not slow it down, the SBML would be wrong in a way mass conservation
    // could not detect.
    const uninhibited = await runInhibitionModel('mm', BASE);
    const inhibited = await runInhibitionModel('noncompetitive', {
      ...BASE,
      ki: 0.02,
      i0: 1.0,
    });

    const finalOf = (traj: Array<Record<string, number>>): number => {
      const last = traj[traj.length - 1] ?? {};
      const key = Object.keys(last).find((k) => k.includes('S'));
      return key ? Number(last[key]) : Number.NaN;
    };

    // More substrate LEFT means the reaction ran slower.
    expect(finalOf(inhibited.trajectory)).toBeGreaterThan(
      finalOf(uninhibited.trajectory),
    );
  });

  it('a stronger inhibitor slows it further', async () => {
    const weak = await runInhibitionModel('noncompetitive', { ...BASE, ki: 0.02, i0: 0.1 });
    const strong = await runInhibitionModel('noncompetitive', { ...BASE, ki: 0.02, i0: 2.0 });

    const finalOf = (traj: Array<Record<string, number>>): number => {
      const last = traj[traj.length - 1] ?? {};
      const key = Object.keys(last).find((k) => k.includes('S'));
      return key ? Number(last[key]) : Number.NaN;
    };

    expect(finalOf(strong.trajectory)).toBeGreaterThan(finalOf(weak.trajectory));
  });
});

describe('the model catalogue is honest about what it needs', () => {
  it('lists a requirement set for every model', () => {
    for (const [name, spec] of Object.entries(INHIBITION_MODELS)) {
      expect(spec.requires.length).toBeGreaterThan(0);
      expect(spec.description).toBeTruthy();
      // Every inhibition model needs an inhibition constant; plain MM
      // must not.
      if (name === 'mm') {
        expect(spec.requires).not.toContain('ki');
      } else {
        expect(spec.requires).toContain('ki');
      }
    }
  });
});
