/**
 * ADR 0055.
 *
 * These tests exist because the thing they cover shipped for months in a
 * state where it could not be wrong: every entry point passed a literal
 * `{ temperature: 37, pH: 7.4 }`, so the validator's range checks sat at the
 * centre of their own ranges and never fired.
 *
 * The validator's own unit tests passed throughout. They called
 * `validateAssumptions` directly with temperatures the product never sent.
 * **Testing a function is not testing the call site**, which is the same
 * lesson as ADR 0027's parity test — that one pinned two implementations
 * against a shared fixture and could not see that the two callers passed
 * different arguments.
 */

import {
  deriveRunConditions,
  describeConflicts,
  type ParameterWithProvenance,
} from '../runConditions';
import { AssumptionValidator } from '../scientificValidator';

const at = (
  temperatureC: number | null | undefined,
  ph: number | null | undefined,
): ParameterWithProvenance => ({ assayConditions: { temperatureC, ph } });

describe('deriveRunConditions', () => {
  it('reports one temperature when every parameter reports the same one', () => {
    const verdict = deriveRunConditions({ km: at(25, 7.0), vmax: at(25, 7.0) });

    expect(verdict.temperatureC.status).toBe('agreed');
    expect(verdict.temperatureC.value).toBe(25);
    expect(verdict.ph.status).toBe('agreed');
    expect(verdict.ph.value).toBe(7.0);
  });

  it('reports a conflict when parameters were measured at different temperatures', () => {
    const verdict = deriveRunConditions({ km: at(25, 7.0), vmax: at(37, 7.0) });

    expect(verdict.temperatureC.status).toBe('conflicting');
    // The pH agreed even though the temperature did not. Assessed per
    // condition, not per parameter set -- collapsing to a single "coherent"
    // boolean would discard the fact that half the picture is fine.
    expect(verdict.ph.status).toBe('agreed');
  });

  it('does NOT carry a value on a conflict', () => {
    const verdict = deriveRunConditions({ km: at(25, 7.0), vmax: at(37, 7.0) });

    // The whole design turns on this. If a conflict carried the first value
    // plus a flag, every consumer that forgot the flag would simulate at a
    // temperature one of its own parameters contradicts -- and it would look
    // identical to the agreed case at the call site.
    expect(verdict.temperatureC.value).toBeUndefined();
  });

  it('names what conflicted, so a refusal is checkable', () => {
    const verdict = deriveRunConditions({ km: at(25, 7.0), vmax: at(37, 7.0) });

    expect(verdict.temperatureC.reported).toEqual([
      { parameter: 'km', value: 25 },
      { parameter: 'vmax', value: 37 },
    ]);
  });

  it('distinguishes not_reported from conflicting', () => {
    const silent = deriveRunConditions({ km: at(null, null), vmax: at(null, null) });

    expect(silent.temperatureC.status).toBe('not_reported');
    // Not 'conflicting'. BRENDA not recording a temperature is a gap in the
    // record; two papers disagreeing is a defect in the model. Same absence
    // of a usable number, entirely different fact.
    expect(silent.temperatureC.status).not.toBe('conflicting');
    expect(silent.temperatureC.silent).toEqual(['km', 'vmax']);
  });

  it('treats a parameter with no provenance at all as silent, not as zero', () => {
    const verdict = deriveRunConditions({ km: at(25, 7.0), s0: {} });

    expect(verdict.temperatureC.status).toBe('agreed');
    expect(verdict.temperatureC.value).toBe(25);
    expect(verdict.temperatureC.silent).toEqual(['s0']);
  });

  it('does not swallow a genuine 0 C', () => {
    // `if (!value)` would have made an ice-bath assay indistinguishable from
    // an unrecorded one. Psychrophilic enzymes are assayed near 0.
    const verdict = deriveRunConditions({ km: at(0, 7.0), vmax: at(0, 7.0) });

    expect(verdict.temperatureC.status).toBe('agreed');
    expect(verdict.temperatureC.value).toBe(0);
    expect(verdict.temperatureC.silent).toEqual([]);
  });

  it('agrees when only one parameter reports, and says which stayed silent', () => {
    const verdict = deriveRunConditions({ km: at(30, null), vmax: at(null, null) });

    // One report is not a conflict. It is also not a consensus, which is why
    // `silent` is carried rather than dropped.
    expect(verdict.temperatureC.status).toBe('agreed');
    expect(verdict.temperatureC.value).toBe(30);
    expect(verdict.temperatureC.silent).toEqual(['vmax']);
  });

  it('takes no fallback argument', () => {
    // A `fallback` parameter is the hardcoded 37 with an extra step. Pinned
    // as an arity check because the tempting fix for `not_reported` is to
    // add one, and it would pass every other test in this file.
    expect(deriveRunConditions).toHaveLength(1);
  });
});

describe('describeConflicts', () => {
  it('names both values and refuses to average them', () => {
    const [message] = describeConflicts(
      deriveRunConditions({ km: at(25, 7.0), vmax: at(37, 7.0) }),
    );

    expect(message).toContain('km at 25 C');
    expect(message).toContain('vmax at 37 C');
    // 31 is the mean. Naming it here would be stating an assay temperature
    // no assay used.
    expect(message).not.toContain('31');
  });

  it('says nothing when the conditions agree', () => {
    expect(describeConflicts(deriveRunConditions({ km: at(25, 7), vmax: at(25, 7) })))
      .toEqual([]);
  });

  it('says nothing when nothing was reported', () => {
    // The validator already reports this as notEvaluated. Two voices saying
    // the same thing trains a reader to skim both.
    expect(describeConflicts(deriveRunConditions({ km: at(null, null) })))
      .toEqual([]);
  });
});

describe('AssumptionValidator, on conditions it was never given before', () => {
  const base = { km: 1, vmax: 1, s0: 10, measurementTime: 1, e0: 0.01 };
  const assumptions = {
    steadyState: false,
    noSubstrateDepletion: false,
    noProductInhibition: false,
    enzymeNotDeactivating: false,
    singleEnzymeForm: false,
  };

  it('reports an unknown temperature as notEvaluated, not as passing', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, base);

    expect(result.notEvaluated.some(n => n.includes('Assay temperature'))).toBe(true);
    expect(result.notEvaluated.some(n => n.includes('Assay pH'))).toBe(true);
    // An unknown condition is not a warning -- nothing is wrong, we just do
    // not know. Folding it into warnings would cry wolf on the common case.
    expect(result.warnings).toEqual([]);
  });

  it('the notEvaluated text refuses to be read as approval', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, base);
    const temperature = result.notEvaluated.find(n => n.includes('Assay temperature'))!;

    expect(temperature).toContain('it is unknown');
  });

  it('warns on a thermophile temperature -- reachable for the first time', () => {
    // 72 C, Taq polymerase. Under the old hardcoded 37 this branch could not
    // be reached from any entry point in the product.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...base,
      temperature: 72,
      pH: 7.0,
    });

    expect(result.warnings.some(w => w.includes('72 C is outside'))).toBe(true);
    expect(result.notEvaluated.some(n => n.includes('Assay temperature'))).toBe(false);
  });

  it('warns on a gastric pH -- likewise', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...base,
      temperature: 37,
      pH: 2.0,
    });

    expect(result.warnings.some(w => w.includes('pH 2 is outside'))).toBe(true);
  });

  it('is silent about conditions well inside both ranges', () => {
    // Without this the two tests above are satisfied by a validator that
    // warns unconditionally.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...base,
      temperature: 25,
      pH: 7.4,
    });

    expect(result.warnings).toEqual([]);
    expect(result.notEvaluated).toEqual([]);
  });
});
