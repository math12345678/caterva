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

/**
 * The candidate papers cross the subprocess boundary.
 *
 * WHY THIS IS HERE AND NOT IN THE CLI TEST
 * ----------------------------------------
 * `src/cli/__tests__/candidatePapersShown.test.ts` asserts that the command
 * RENDERS papers it is handed. It mocks `resolveKinetic`, so the parsing
 * this fix actually changed never runs — and the mutation harness said so
 * immediately: reverting `literatureResolver.ts` to ignore
 * `literatureCandidates` left all 21 of those tests passing.
 *
 * That is ADR 0027's finding verbatim — **a test that pins a component
 * tells you nothing about the wiring** — and it is the second half of the
 * pipe being tested while the bug lived in the first.
 *
 * So this drives the real subprocess through the stub, which is the seam
 * this file exists for.
 */
describe('candidate papers survive the subprocess boundary', () => {
  it('reaches the caller as structured papers, not just a log line', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'ki' });
    expect(result.found).toBe(false);
    if (result.found) throw new Error('fixture should not resolve');

    expect(result.candidates.map((p) => p.title)).toEqual([
      'Kinetics of human muscle lactate dehydrogenase',
      'Substrate affinity of LDH isoenzymes',
    ]);
    expect(result.candidates[0]?.pmid).toBe('1234567');
    expect(result.candidates[1]?.doi).toBe('10.1000/example');
  });

  /**
   * The fixture carries four entries; two are unusable. A title-less row
   * cannot be shown and a locator-less row cannot be checked, so both are
   * dropped — and the count the student is given comes from the filtered
   * list, so it can never promise more papers than it names.
   */
  it('drops the entries that cannot be shown or cannot be checked', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'ki' });
    if (result.found) throw new Error('fixture should not resolve');

    expect(result.candidates).toHaveLength(2);
    expect(result.candidates.map((p) => p.title)).not.toContain('');
    expect(result.candidates.map((p) => p.title)).not.toContain(
      'A paper nobody can look up',
    );
  });

  /**
   * The genuinely-empty case must stay empty. If filtering or parsing ever
   * invents a candidate, the CLI would print "the search did find papers"
   * over a search that found none — the original defect, mirrored.
   */
  it('stays empty when the search really found nothing', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'kcat' });
    if (result.found) throw new Error('fixture should not resolve');
    expect(result.candidates).toEqual([]);
  });
});

/**
 * The tie the evidence could not break crosses the subprocess boundary.
 *
 * `check_both_front_ends_read_it.py` (ADR 0110/0112) counted 24 keys the
 * runner emits that only one front end reads. `selectionTie` was the
 * highest-value one: the API path has rendered it since ADR 0051, and the
 * CLI never mentioned it, so a CLI user was handed 21.1 — the lowest of six
 * equally well-evidenced rows spanning to 6467 — with nothing saying the
 * evidence found 6467 equally credible.
 *
 * Asserted at the BOUNDARY and not through a mock, because that is where
 * the last two defects in this path lived and where a mocked test would
 * have proved nothing (ADR 0109).
 */
describe('the selection tie survives the subprocess boundary', () => {
  it('arrives as structured candidates with their references', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'kcat_tied' as never });
    expect(result.found).toBe(true);
    if (!result.found) throw new Error('fixture should resolve');

    const tie = result.selectionTie;
    expect(tie).not.toBeNull();
    expect(tie!.candidates.map((c) => c.value)).toEqual([21.1, 6467]);
    expect(tie!.candidates[1]?.reference_id).toBe('761568');
    expect(tie!.candidates[0]?.selected).toBe(true);
  });

  it('carries the spread as numbers, not only inside the sentence', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'kcat_tied' as never });
    if (!result.found) throw new Error('fixture should resolve');
    expect(result.selectionTie!.low).toBe(21.1);
    expect(result.selectionTie!.high).toBe(6467);
    expect(result.selectionTie!.fold_range).toBeCloseTo(306.5);
  });

  /**
   * A candidate with no value cannot be compared or shown, and a tie whose
   * alternatives are blank is worse than no tie line at all. The fixture
   * carries three rows; one has no value.
   */
  it('drops a candidate that carries no value', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'kcat_tied' as never });
    if (!result.found) throw new Error('fixture should resolve');
    expect(result.selectionTie!.candidates).toHaveLength(2);
  });

  /**
   * Fewer than two candidates is NOT a tie. `SelectionTie()` with an empty
   * list is also what an unpopulated field looks like, which is why
   * `selection_tie.py` makes `is_tied` a positive test — a check on mere
   * presence would inherit the ambiguity it exists to remove.
   */
  it('reports no tie when the resolver reported none', async () => {
    const result = await resolveKinetic({ ...QUERY, quantity: 'km' });
    if (!result.found) throw new Error('fixture should resolve');
    expect(result.selectionTie ?? null).toBeNull();
  });
});
