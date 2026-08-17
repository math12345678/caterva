import path from 'path';

import { resolveKinetic, ResolverUnavailableError } from '../literatureResolver';

/**
 * The subprocess path, exercised for real, without a network.
 *
 * WHY THIS EXISTS
 * ---------------
 * `src/cli/__tests__/cliEndToEnd.test.ts` spawns the real runner, which
 * calls BRENDA and PubMed. Without network access to those hosts it does
 * not fail — it HANGS, on a 120-second per-invocation timeout, so the suite
 * is simply never run. Three consecutive verification passes reported it as
 * "not verified", which was honest and was not a substitute for verifying
 * it.
 *
 * `TERRIUM_LITERATURE_RUNNER` is a seam that already existed for exactly
 * this. These tests point it at a stub and exercise spawn, stdin, exit
 * code and stdout parsing — the boundary where every bug in this path has
 * actually been.
 *
 * Deliberately NOT a module mock. The first version of this resolver
 * discarded a structured `{"ok": false, "error": "403 Forbidden"}` because
 * the process also exited 1, replacing a precise cause with "exited with
 * code 1". A mock of the module cannot catch that; a real subprocess can.
 */

const STUB = path.resolve(
  __dirname,
  '../../../Tests/fixtures/offline_runner/stub_literature_runner.py',
);

const original = process.env['TERRIUM_LITERATURE_RUNNER'];

beforeAll(() => {
  process.env['TERRIUM_LITERATURE_RUNNER'] = STUB;
});

afterAll(() => {
  if (original === undefined) delete process.env['TERRIUM_LITERATURE_RUNNER'];
  else process.env['TERRIUM_LITERATURE_RUNNER'] = original;
});

jest.setTimeout(120_000);

const QUERY = {
  enzymeName: 'lactate dehydrogenase',
  substrate: 'lactate',
  organism: 'Homo sapiens',
  ecNumber: '1.1.1.27',
};

describe('the real subprocess path, offline', () => {
  it('resolves a value with its unit, organism and citation', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'km' });
    expect(result.found).toBe(true);
    if (!result.found) return;

    expect(result.value).toBe(10.73);
    // A number without its unit is not a measurement.
    expect(result.unit).toBe('mM');
    expect(result.organism).toBe('Homo sapiens');
    expect(result.citation?.reference_id).toBe('740253');
  });

  it('carries the runner-computed reliability score across the boundary', async () => {
    // The CLI displays this. If the resolver dropped it, the axes would
    // silently vanish from every `scientific resolve` output and nothing
    // else would fail.
    const result = await resolveKinetic({ ...QUERY, quantity: 'km' });
    if (!result.found) throw new Error('expected a value');

    expect(result.reliability?.assayCompleteness.grade).toBe('complete');
    expect(result.reliability?.organismMatch.grade).toBe('exact');
    expect(result.reliability?.noAggregateReason).toContain('ADR 0024');
  });

  it('carries the assay conditions across the boundary', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'km' });
    if (!result.found) throw new Error('expected a value');

    expect(result.assayConditions?.ph).toBe(7.4);
    expect(result.assayConditions?.temperatureC).toBe(25);
  });

  it('reports a genuine miss as found:false rather than as an error', async () => {
    // "The literature has nothing" and "we could not look" are different
    // facts with different exit codes. This is the first.
    const result = await resolveKinetic({ ...QUERY, quantity: 'kcat' });
    expect(result.found).toBe(false);
  });

  it('delivers allowCrossSpecies to the runner', async () => {
    // The opt-in has to survive the payload → subprocess hop. A flag
    // accepted by the CLI, logged as accepted, and never applied is worse
    // than no flag, because the user believes they made a choice.
    const withOptIn = await resolveKinetic({
      ...QUERY,
      quantity: 'km',
      allowCrossSpecies: true,
    });
    expect(withOptIn.logs.join(' ')).toContain('allowCrossSpecies=True');

    const withoutOptIn = await resolveKinetic({ ...QUERY, quantity: 'km' });
    expect(withoutOptIn.logs.join(' ')).toContain('allowCrossSpecies=False');
  });

  it('delivers the physiological reference to the runner', async () => {
    const withReference = await resolveKinetic({
      ...QUERY,
      quantity: 'km',
      physiologicalReference: {
        ph: 7.4,
        temperatureC: 37,
        basis: 'human blood plasma',
        phTolerance: 0.4,
        temperatureToleranceC: 5,
      },
    });
    expect(withReference.logs.join(' ')).toContain('physiologicalReference=yes');

    const without = await resolveKinetic({ ...QUERY, quantity: 'km' });
    expect(without.logs.join(' ')).toContain('physiologicalReference=no');
  });
});

describe('the failure the boundary actually has', () => {
  it('surfaces a runner error rather than an exit code', async () => {
    // The bug this whole approach exists to catch: a structured error on
    // stdout, discarded because the process also exited non-zero, and
    // replaced with "exited with code 1".
    process.env['TERRIUM_LITERATURE_RUNNER'] = path.resolve(
      __dirname,
      '../../../Tests/fixtures/offline_runner/stub_failing_runner.py',
    );

    await expect(
      resolveKinetic({ ...QUERY, quantity: 'km' }),
    ).rejects.toThrow(ResolverUnavailableError);

    try {
      await resolveKinetic({ ...QUERY, quantity: 'km' });
    } catch (err) {
      // The REASON must survive, not just the failure.
      expect((err as Error).message).toContain('403');
    } finally {
      process.env['TERRIUM_LITERATURE_RUNNER'] = STUB;
    }
  });

  it('treats a missing runner as unavailable, not as an empty result', async () => {
    process.env['TERRIUM_LITERATURE_RUNNER'] = path.resolve(
      __dirname,
      '../../../Tests/fixtures/offline_runner/does_not_exist.py',
    );
    try {
      await expect(
        resolveKinetic({ ...QUERY, quantity: 'km' }),
      ).rejects.toThrow();
    } finally {
      process.env['TERRIUM_LITERATURE_RUNNER'] = STUB;
    }
  });
});
