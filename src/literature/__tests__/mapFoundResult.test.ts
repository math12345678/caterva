import { mapFoundResult } from '../literatureResolver';

/**
 * The payload -> result mapping, tested directly.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `science_agent_runner.py` emitted `variant`, `effectors` and
 * `assayConditions.bufferIdentity` for as long as those features have
 * existed. This mapping dropped every one of them, because `ResolvedKinetic`
 * had no field to receive them. Four ADRs' worth of findings — cross-species
 * relatedness, buffer chemistry, protein variants, cofactors — were computed,
 * serialised, and discarded one function short of the screen.
 *
 * Nothing could see it. The producer saw a successful write; the consumer saw
 * a complete object; no error was raised on either side.
 *
 * `src/cli/__tests__/resolveOutput.test.ts` was written to cover this and
 * **could not**: it mocks `resolveKinetic`, so it asserts what the CLI does
 * with an object rather than whether the object is ever populated. Deleting
 * the plumbing left all fourteen of those tests passing. This file is the
 * one that fails.
 *
 * The mapping was inline inside `resolveKinetic`, which spawns Python, so it
 * was unreachable from any unit test. It was extracted for this reason: a
 * mapping only reachable through a subprocess is a mapping nothing tests.
 */

const MINIMAL = {
  organism: 'Homo sapiens',
  source: 'brenda_exact',
  citation: { source: 'BRENDA', reference_id: '649716' },
};

function map(extra: Record<string, unknown>) {
  return mapFoundResult({ ...MINIMAL, ...extra }, 'km', 2.5, 'mM', []);
}

describe('fields the runner emits survive the mapping', () => {
  it('carries the variant verdict', () => {
    const result = map({
      variant: {
        status: 'variant',
        kind: 'mutant',
        evidence: 'Y337A',
        reason: 'A substitution changes the kinetics.',
      },
    });
    expect(result.variant?.status).toBe('variant');
    expect(result.variant?.evidence).toBe('Y337A');
  });

  it('carries an `unstated` verdict, which is not the same as absent', () => {
    // The distinction the whole mechanism rests on. If `unstated` were
    // dropped as uninteresting, the CLI would print nothing and a reader
    // would infer the enzyme as found.
    const result = map({
      variant: { status: 'unstated', reason: 'The commentary does not say.' },
    });
    expect(result.variant).toBeDefined();
    expect(result.variant?.status).toBe('unstated');
  });

  it('carries effectors, including absences', () => {
    const result = map({
      effectors: [
        { raw: 'with 0.2 mM NADH', compound_text: 'NADH', presence: 'present' },
        { raw: 'without FBP', compound_text: 'FBP', presence: 'absent' },
      ],
    });
    expect(result.effectors).toHaveLength(2);
    expect(result.effectors?.map((e) => e.presence)).toEqual(['present', 'absent']);
  });

  it('distinguishes "named none" from "nothing looked"', () => {
    // An empty array is a finding: the commentary named no effectors.
    // `undefined` means the field never arrived. Collapsing them would make
    // a silent pipeline break indistinguishable from a clean assay.
    expect(map({ effectors: [] }).effectors).toEqual([]);
    expect(map({}).effectors).toBeUndefined();
  });

  it('carries bufferIdentity inside assayConditions', () => {
    // The subtlest of the four. `assayConditions` WAS copied through — but
    // cast to a type with no `bufferIdentity`, so the resolution arrived at
    // runtime and was invisible to every typed consumer.
    const result = map({
      assayConditions: {
        ph: 7.4,
        temperatureC: 25,
        buffer: '0.5 M Tris-HCl buffer',
        bufferIdentity: {
          raw: '0.5 M Tris-HCl buffer',
          species: 'Tris-HCl',
          cid: 93573,
          parent_cid: 6503,
          status: 'resolved',
        },
      },
    });
    expect(result.assayConditions?.bufferIdentity?.parent_cid).toBe(6503);
  });

  it('carries the reliability axes', () => {
    const result = map({
      reliability: {
        assayCompleteness: { grade: 'complete', reason: 'r' },
        conditionProximity: { grade: 'near', reason: 'r' },
        organismMatch: { grade: 'exact', reason: 'r' },
        noAggregateReason: 'no total on purpose',
      },
    });
    expect(result.reliability?.conditionProximity.grade).toBe('near');
  });
});

describe('the mapping does not invent anything', () => {
  it('leaves absent fields absent rather than defaulting them', () => {
    // A defaulted `variant: { status: 'wild_type' }` would be a fabricated
    // claim about the literature — the exact thing ADR 0012/0013 forbid for
    // parameters, applied to a description of one.
    const result = map({});
    expect(result.variant).toBeUndefined();
    expect(result.effectors).toBeUndefined();
    expect(result.assayConditions).toBeUndefined();
    expect(result.reliability).toBeUndefined();
  });

  it('still maps the value, unit and citation', () => {
    const result = map({});
    expect(result.value).toBe(2.5);
    expect(result.unit).toBe('mM');
    expect(result.citation?.reference_id).toBe('649716');
    expect(result.organism).toBe('Homo sapiens');
  });

  it('derives crossSpecies from the source rather than trusting a flag', () => {
    expect(map({ source: 'brenda_cross_species' }).crossSpecies).toBe(true);
    expect(map({ source: 'brenda_exact' }).crossSpecies).toBe(false);
  });
});
