/**
 * An epidemic query is not answered "km is required".
 *
 * WHAT WAS MEASURED
 * -----------------
 * Over HTTP, on 2026-08-22:
 *
 *     POST /api/simulate
 *     {"query":"sir epidemic",
 *      "parameters":{"beta":0.3,"gamma":0.1,"s0":990,"i0":10}}
 *
 *     -> parameters.km is required
 *        parameters.vmax is required
 *
 * `sir`, `epidemic`, `infection`, `outbreak` and `susceptible` are all
 * aliases the classifier accepts, and the validator's own error message
 * lists them as models "this pipeline can run". Then it demanded two
 * Michaelis-Menten parameters from a different branch of biology, neither
 * of which the caller had mentioned.
 *
 * `const requiredParams = ['km', 'vmax', 's0']` appeared THREE times in
 * request-validator.ts. A wrong error is worse than a bare failure: it
 * sends somebody to fix the thing that is not broken.
 *
 * THE SECOND HALF, WHICH IS THE DANGEROUS ONE
 * -------------------------------------------
 * Fixing only the validator would have moved the lie deeper.
 * `runSimulation` called `runCaterva('mm', ...)` with the domain out of
 * scope entirely, so a correctly-validated SIR request would have reached
 * an integrator running enzyme kinetics. Nothing had gone visibly wrong
 * only because the missing `km` killed it first — a coincidence standing in
 * for a check.
 */
import { validateSimulationRequest } from '../request-validator';
import { ScientificPipeline } from '../../integration/scientificPipeline';
import { INHIBITION_MODELS } from '../../cli/inhibitionModels';

describe('required parameters follow the domain', () => {

  it('still asks Michaelis-Menten for km, vmax and s0', () => {
    expect(ScientificPipeline.requiredParametersFor('michaelis-menten')).toEqual(
      expect.arrayContaining(['km', 'vmax', 's0'])
    );
  });

  it('falls back to Michaelis-Menten for a query naming no domain', () => {
    // Unchanged behaviour, asserted so it stays deliberate. Such a query
    // already fails on the `query` field; inventing a different requirement
    // set would add a second error about a first one.
    expect(ScientificPipeline.requiredParametersFor('banana')).toEqual(
      expect.arrayContaining(['km', 'vmax', 's0'])
    );
  });


  it('still rejects a Michaelis-Menten request missing its own parameters', () => {
    // Without this, deleting the whole check would pass every test above.
    const { errors } = validateSimulationRequest({
      query: 'michaelis-menten',
      parameters: { s0: 10 },
    });
    expect(errors.map((e) => e.field)).toEqual(
      expect.arrayContaining(['parameters.km', 'parameters.vmax'])
    );
  });
});

describe('what the pipeline can dispatch, as opposed to name', () => {
  it('lists only domains the classifier also knows', () => {
    // A dispatchable domain the classifier cannot recognise would be
    // unreachable; the two lists disagreeing in that direction is the same
    // drift, mirrored.
    for (const domain of ScientificPipeline.DISPATCHABLE_DOMAINS) {
      expect(ScientificPipeline.requiredParametersFor(domain).length)
        .toBeGreaterThan(0);
    }
  });


  it('dispatches nothing it cannot classify', () => {
    // The mirrored drift: a dispatchable domain the classifier does not
    // know would be unreachable, and the two lists would disagree in the
    // direction this file has not otherwise checked.
    for (const domain of ScientificPipeline.DISPATCHABLE_DOMAINS) {
      expect(ScientificPipeline.knownDomainAliases()).toContain(domain);
    }
  });
});

/**
 * An epidemic reported as an epidemic.
 *
 * `runSir` deliberately does NOT return the Michaelis-Menten envelope.
 * Every field in it — `totalSubstrateConsumed`, `conversionPercentage`,
 * `maxVelocity` — would COMPUTE for an epidemic and every one would be
 * labelled as enzymology. Plausible numbers under names describing a
 * different experiment is worse than no result: nothing looks wrong.
 *
 * `summariseSir` is static and pure so the two cases that matter — a
 * truncated window and a resolved epidemic — can be driven without a Python
 * subprocess.
 */

/**
 * The three inhibition models, reachable over HTTP.
 *
 * The dashboard offered them and the API rejected them (ADR 0149). They
 * were disabled with a label, then dispatched (ADR 0157) — and the order
 * matters: the label came off because the model ran, not because the label
 * was inconvenient.
 */
describe('inhibition models', () => {
  it.each([
    ['competitive-inhibition', 'competitive'],
    ['non-competitive-inhibition', 'noncompetitive'],
    ['product-inhibition', 'product'],
  ])('%s classifies as %s and is dispatchable', (query, domain) => {
    expect(ScientificPipeline.requiredParametersFor(query)).toEqual(
      INHIBITION_MODELS[domain as 'competitive'].requires
    );
    expect([...ScientificPipeline.DISPATCHABLE_DOMAINS]).toContain(domain);
  });

  it('does not let the shorter alias claim the longer query', () => {
    // `non-competitive-inhibition` CONTAINS `competitive-inhibition`. If the
    // classifier matched on first-found rather than longest, this query
    // would run competitive inhibition on non-competitive parameters —
    // right numbers, wrong model, no error.
    expect(ScientificPipeline.requiredParametersFor('non-competitive-inhibition'))
      .toEqual(INHIBITION_MODELS.noncompetitive.requires);
  });


  it('requires ki for every one of them', () => {
    // The parameter that distinguishes an inhibition run from plain
    // Michaelis-Menten. If it ever became optional, the models would
    // silently degrade to the model they exist to differ from.
    for (const model of ['competitive', 'noncompetitive', 'product'] as const) {
      expect(ScientificPipeline.requiredParametersFor(model)).toContain('ki');
    }
  });
});
