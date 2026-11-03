/**
 * The system read out of a question, with the shared Python tables.
 *
 * Two defects, one reader (readSystem.ts):
 *
 *   - "hexokinase on glucose in humans" reached BRENDA as "humans", which
 *     BRENDA indexes nowhere, and was refused as "BRENDA holds this km only
 *     for other organisms (... Homo sapiens ...)" while BRENDA ref 641068
 *     holds 6 mM for exactly that system.
 *   - "hexokinase glucose human" and "human hexokinase on glucose" read as
 *     naming no system at all, because the TypeScript parser needs
 *     prepositions.
 *
 * These run the real Python reader (caterva.enzymes.question), offline. If
 * it cannot be imported they FAIL: a reader that silently returned null
 * would look exactly like the old behaviour.
 */
import { execFileSync } from 'child_process';

import { REPO_ROOT, resolvePythonExecutable } from '../../engine/catervaBridge';
import { canonicalOrganism, readSystemFromQuery } from '../readSystem';

jest.setTimeout(120_000);

beforeAll(() => {
  execFileSync(
    resolvePythonExecutable(REPO_ROOT),
    ['-c', 'import caterva.enzymes.question'],
    { cwd: REPO_ROOT, env: { ...process.env, PYTHONPATH: REPO_ROOT }, stdio: 'pipe' },
  );
});

describe('the organism is searched as the binomial BRENDA files it under', () => {
  it('reads "humans" in a prepositional question as Homo sapiens, keeping what was typed', () => {
    expect(readSystemFromQuery('hexokinase on glucose in humans')).toEqual({
      enzyme: 'hexokinase',
      substrate: 'glucose',
      organism: 'Homo sapiens',
      organismTyped: 'humans',
    });
  });

  it('leaves a binomial alone, with nothing to show', () => {
    expect(readSystemFromQuery('hexokinase on glucose in Homo sapiens')).toEqual({
      enzyme: 'hexokinase',
      substrate: 'glucose',
      organism: 'Homo sapiens',
    });
  });

  it('canonicalises a typed --organism, and keeps a strain as typed', () => {
    expect(canonicalOrganism('human')).toEqual({ organism: 'Homo sapiens', typed: 'human' });
    expect(canonicalOrganism('E. coli K-12')).toEqual({ organism: 'E. coli K-12' });
    expect(canonicalOrganism('Thermus aquaticus')).toEqual({ organism: 'Thermus aquaticus' });
  });
});

describe('orderings without the full preposition pattern', () => {
  it.each([
    ['hexokinase glucose human', 'human'],
    ['hexokinase with glucose in humans', 'humans'],
    ['human hexokinase on glucose', 'human'],
  ])('reads %s', (query, typed) => {
    expect(readSystemFromQuery(query)).toEqual({
      enzyme: 'hexokinase',
      substrate: 'glucose',
      organism: 'Homo sapiens',
      organismTyped: typed,
    });
  });

  it.each([
    ['no organism', 'hexokinase glucose'],
    ['no enzyme name first', 'glucose hexokinase human'],
    ['no system', 'michaelis menten'],
  ])('refuses %s rather than guessing', (_label, query) => {
    expect(readSystemFromQuery(query)).toBeNull();
  });
});
