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
    // UPDATED 2026-08-22, and the update is the point.
    //
    // Written one day earlier as `['mm']`, with the note: "expected to
    // CHANGE, not to be deleted. When SIR is dispatched over HTTP, the
    // assertion fails and whoever made that true updates it."
    //
    // It fired on exactly that, and `runSir` is why. The list widened
    // BECAUSE an executor arrived — which is the distinction this test
    // exists to enforce, and the reason it is a literal rather than
    // something derived from DOMAINS: derived, it could never disagree.
    expect([...ScientificPipeline.DISPATCHABLE_DOMAINS]).toEqual(['mm', 'sir']);
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
describe('an SIR summary', () => {
  // beta 0.3, gamma 0.1, s0 990, i0 10, cut off at t=10: infections are
  // still climbing steeply. Shape taken from the real engine output.
  const truncated = [
    { time: 0, susceptible: 990, infected: 10, recovered: 0 },
    { time: 5, susceptible: 960, infected: 28, recovered: 12 },
    { time: 10, susceptible: 904, infected: 65, recovered: 30 },
  ];

  // The same run allowed to finish.
  const resolved = [
    { time: 0, susceptible: 990, infected: 10, recovered: 0 },
    { time: 26, susceptible: 400, infected: 303, recovered: 297 },
    { time: 120, susceptible: 59, infected: 0.3, recovered: 941 },
  ];

  it('refuses to call the edge of the window a peak', () => {
    const m = ScientificPipeline.summariseSir(truncated, 0.1, 10);
    // null, not 65. "I did not see the peak" must never read as "the peak
    // was here", and a number is not improved by being the largest seen.
    expect(m.peakInfected).toBeNull();
    expect(m.peakTime).toBeNull();
    expect(m.peakReachedWithinWindow).toBe(false);
    // The number is still reported, under a name that says what it is.
    expect(m.highestInfectedSeen).toBe(65);
  });

  it('says how to get the peak, in terms of the run that was asked for', () => {
    const note = String(ScientificPipeline.summariseSir(truncated, 0.1, 10).note);
    expect(note).toContain("Pass a larger 'end'");
    // Actionable rather than regretful: 1/gamma = 10, and a window of 10
    // covers 1.0 infectious periods. Both derived, neither invented.
    expect(note).toContain('mean infectious period is 10');
    expect(note).toContain('1.0');
  });

  it('reports a real peak when the epidemic resolved', () => {
    const m = ScientificPipeline.summariseSir(resolved, 0.1, 120);
    expect(m.peakInfected).toBe(303);
    expect(m.peakTime).toBe(26);
    expect(m.peakReachedWithinWindow).toBe(true);
    // No apology attached to a complete answer (ADR 0028: a note that fires
    // on the ordinary case is a note nobody reads on the one that matters).
    expect(m.note).toBeUndefined();
  });

  it('reports an attack rate, not a conversion percentage', () => {
    const m = ScientificPipeline.summariseSir(resolved, 0.1, 120);
    // (990 - 59) / 990 -> 94%. The standard final-size reading for R0 = 3,
    // which is what beta/gamma is here.
    expect(m.attackRate as number).toBeCloseTo(94.04, 1);
    expect(Object.keys(m)).not.toContain('conversionPercentage');
    expect(Object.keys(m)).not.toContain('totalSubstrateConsumed');
    expect(Object.keys(m)).not.toContain('maxVelocity');
  });
});
