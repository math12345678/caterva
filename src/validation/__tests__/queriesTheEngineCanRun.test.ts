/**
 * The API accepts exactly what the pipeline can run — no more, no less.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `validateSimulationRequest` held a hardcoded list of four "valid"
 * queries, and it had drifted from the pipeline in BOTH directions:
 *
 *   accepted, but unrunnable   competitive-inhibition
 *                              non-competitive-inhibition
 *                              product-inhibition
 *   runnable, but rejected     sir  (the whole epidemiology domain)
 *                              mm   (the CLI's own documented spelling)
 *
 * Measured against the running server before the fix: `competitive-inhibition`
 * passed validation, was queued, returned a job id, and the job then reported
 *
 *     "status": "complete"
 *
 * while carrying `validated: false` and "Query 'competitive-inhibition' does
 * not name a domain this pipeline knows (mm, sir)". The refusal arrived
 * buried inside a result labelled complete, twelve seconds after a 200.
 *
 * And `sir` — wired end to end by ADR 0020 — was unreachable over HTTP
 * entirely, because a list written before it existed never learned about it.
 *
 * The validator now asks `ScientificPipeline.namesAKnownDomain`. These tests
 * pin the property that matters: acceptance and runnability are the same
 * predicate, not two lists that happen to agree today.
 */
import { ScientificPipeline } from '../../integration/scientificPipeline';
import { validateSimulationRequest } from '../request-validator';

const PARAMS = { km: 5.2, vmax: 12.8, s0: 10 };

const accepts = (query: string): boolean =>
  validateSimulationRequest({ query, parameters: PARAMS }).errors.every(
    (e) => e.field !== 'query',
  );

describe('acceptance follows the pipeline, not a copy of it', () => {
  it('accepts every alias the pipeline advertises', () => {
    // The error message lists these, so a caller who reads it and retries
    // must succeed. A message naming a query the validator then rejects is
    // worse than no message.
    const aliases = ScientificPipeline.knownDomainAliases();
    expect(aliases.length).toBeGreaterThan(0);
    for (const alias of aliases) {
      expect(accepts(alias)).toBe(true);
    }
  });


  it('accepts `mm`, so the CLI and the API share a vocabulary', () => {
    // `sweep mm --parameter ...` is the CLI's own documented example. A
    // student who learns it at the terminal and then scripts the API used
    // to get a 400 for the same word.
    expect(accepts('mm')).toBe(true);
  });

  it('rejects queries the pipeline cannot place, at request time', () => {
    // These were accepted and queued. Refusing them here is the difference
    // between a 400 and a job that reports "complete" having validated
    // nothing.
    //
    // THE THREE INHIBITION QUERIES ARE NO LONGER IN THIS LIST, and their
    // removal is a correction to this test rather than a loosening of it.
    // `competitive-inhibition`, `non-competitive-inhibition` and
    // `product-inhibition` were genuinely unplaceable when this was
    // written; ADR 0157 taught the pipeline to dispatch all three, and
    // `dashboard.html` re-enabled the controls at the same time. They now
    // classify to `competitive`, `noncompetitive` and `product`.
    //
    // Leaving them here did not make the suite stricter, it made it
    // self-contradictory: the first test in this file asserts that every
    // alias `knownDomainAliases()` advertises is accepted, and all three
    // are advertised. One test required accepting exactly what another
    // required rejecting, so the file could not go green whatever the code
    // did -- and the failure read as "the validator accepts junk".
    //
    // `allosteric` stays, and for a stated reason rather than by
    // inheritance: `kinematicModels` implements Allosteric (Hill), but the
    // pipeline has no domain for it, so a request naming it cannot be run.
    // Rejecting it at request time is correct; `dashboard.html` keeps that
    // option disabled for the same reason and says so.
    for (const query of ['allosteric', 'nonsense']) {
      expect(accepts(query)).toBe(false);
      expect(ScientificPipeline.namesAKnownDomain(query)).toBe(false);
    }
  });

  it('places the three inhibition queries ADR 0157 added', () => {
    // The other half of the correction above. Without this, deleting those
    // three domains would take the suite from red to green -- the list
    // they were removed from is the only place they appeared, and a
    // removal that makes tests pass is how a capability disappears
    // unnoticed.
    for (const [query, domain] of [
      ['competitive-inhibition', 'competitive'],
      ['non-competitive-inhibition', 'noncompetitive'],
      ['product-inhibition', 'product'],
    ] as const) {
      expect(accepts(query)).toBe(true);
      expect(ScientificPipeline.namesAKnownDomain(query)).toBe(true);
      // Asserted on the domain, not just on acceptance: accepting the word
      // and placing it on the wrong model is the failure this file exists
      // to catch, and `accepts()` alone cannot see it.
      expect(
        (ScientificPipeline as unknown as {
          classifyDomainOf(q: string): string | undefined;
        }).classifyDomainOf(query),
      ).toBe(domain);
    }
  });

  it('agrees with the pipeline on every case tested', () => {
    // The property, stated once rather than implied by the cases above:
    // there is no query the validator accepts and the pipeline cannot
    // place, and none it rejects that the pipeline could have run.
    const probes = [
      ...ScientificPipeline.knownDomainAliases(),
      'competitive-inhibition',
      'allosteric',
      'nonsense',
      'summary',   // must NOT match `mm` — word-boundary check
      'desire',    // must NOT match `sir`
    ];
    for (const query of probes) {
      expect(accepts(query)).toBe(ScientificPipeline.namesAKnownDomain(query));
    }
  });

  it('still rejects a missing or non-string query', () => {
    // The other validation rule must survive: asking the pipeline about
    // `undefined` should not throw, and should not accidentally accept.
    expect(validateSimulationRequest({ parameters: PARAMS }).valid).toBe(false);
    expect(validateSimulationRequest({ query: 42, parameters: PARAMS }).valid).toBe(false);
  });
});
