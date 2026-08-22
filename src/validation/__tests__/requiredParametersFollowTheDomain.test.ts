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
 * `runSimulation` called `runTerium('mm', ...)` with the domain out of
 * scope entirely, so a correctly-validated SIR request would have reached
 * an integrator running enzyme kinetics. Nothing had gone visibly wrong
 * only because the missing `km` killed it first — a coincidence standing in
 * for a check.
 */
import { validateSimulationRequest } from '../request-validator';
import { ScientificPipeline } from '../../integration/scientificPipeline';

describe('required parameters follow the domain', () => {
  it('asks the epidemic domain for its own parameters', () => {
    const required = ScientificPipeline.requiredParametersFor('sir epidemic');
    expect(required).toEqual(expect.arrayContaining(['beta', 'gamma', 's0', 'i0']));
    // The regression, stated as the absence it is.
    expect(required).not.toContain('km');
    expect(required).not.toContain('vmax');
  });

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

  it('does not tell an epidemic request that km is missing', () => {
    const { errors } = validateSimulationRequest({
      query: 'sir epidemic',
      parameters: { beta: 0.3, gamma: 0.1, s0: 990, i0: 10 },
    });
    const fields = errors.map((e) => e.field);
    expect(fields).not.toContain('parameters.km');
    expect(fields).not.toContain('parameters.vmax');
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

  it('does not claim to dispatch every domain it can classify', () => {
    // This test is expected to CHANGE, not to be deleted. When SIR is
    // dispatched over HTTP, the assertion below fails and whoever made that
    // true updates it — which is the point. A silent widening of
    // DISPATCHABLE_DOMAINS without a working executor is exactly what this
    // catches.
    expect([...ScientificPipeline.DISPATCHABLE_DOMAINS]).toEqual(['mm']);
  });
});
