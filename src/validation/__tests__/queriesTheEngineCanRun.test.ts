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

  it('accepts `sir`, which the old list made unreachable over HTTP', () => {
    // ADR 0020 wired epidemiology end to end. The API refused it for as
    // long as both existed, because the list predated the domain.
    expect(accepts('sir')).toBe(true);
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
    for (const query of [
      'competitive-inhibition',
      'non-competitive-inhibition',
      'product-inhibition',
      'allosteric',
      'nonsense',
    ]) {
      expect(accepts(query)).toBe(false);
      expect(ScientificPipeline.namesAKnownDomain(query)).toBe(false);
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
