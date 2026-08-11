/**
 * [E]0 as a caller input, and the check it unblocks.
 *
 * `AssumptionValidator`'s steady-state check implements Segel's criterion,
 *
 *     epsilon = e0 / (Km + s0)  <<  1
 *
 * (Segel 1988, Bull Math Biol 50(6):579-93, DOI 10.1007/BF02460092), and
 * epsilon needs the total enzyme concentration. Nothing in this tree
 * supplied one, so the check reported `notEvaluated` on EVERY run -- Layer
 * 3's first assumption did no work at all. Honest, but inert.
 *
 * [E]0 cannot come from literature: BRENDA does not report it per row, and
 * ADR 0013 rules that it is an explicit caller input, never defaulted and
 * never inferred. So it arrives on the request, with its unit, and these
 * tests pin what it then enables.
 */
import { AssumptionValidator, type ModelAssumptions } from '../validation/scientificValidator';
import { convertConcentration } from '../units';

const ASSUMPTIONS: ModelAssumptions = {
  steadyState: true,
  noSubstrateDepletion: true,
  noProductInhibition: true,
  enzymeNotDeactivating: true,
  singleEnzymeForm: true
};

/** Km + s0 = 105, and a window short enough not to consume the substrate. */
const BASE = {
  km: 5.0,
  vmax: 10.0,
  s0: 100.0,
  measurementTime: 0.1,
  temperature: 37,
  pH: 7.4
};

describe('the steady-state check is inert without [E]0', () => {
  it('reports notEvaluated, and does NOT report a pass', () => {
    const result = AssumptionValidator.validateAssumptions(ASSUMPTIONS, BASE);

    expect(result.notEvaluated).toHaveLength(1);
    expect(result.notEvaluated[0]).toContain('UNVERIFIED');
    // The distinction that matters: not evaluated is not the same as
    // satisfied. Reporting an unevaluated assumption as met is how a
    // validator manufactures confidence.
    expect(result.violations.some(v => v.includes('epsilon'))).toBe(false);
  });
});

describe('supplying [E]0 makes the criterion evaluable', () => {
  it('evaluates rather than deferring when e0 is present', () => {
    const result = AssumptionValidator.validateAssumptions(ASSUMPTIONS, {
      ...BASE,
      e0: 0.01 // epsilon = 0.01/105 ~ 9.5e-5
    });

    expect(result.notEvaluated).toEqual([]);
    expect(result.valid).toBe(true);
  });

  it('fails when epsilon is not << 1', () => {
    // epsilon = 200/105 = 1.9. The Michaelis-Menten reduction is simply not
    // valid here, and the run must not proceed as though it were.
    const result = AssumptionValidator.validateAssumptions(ASSUMPTIONS, {
      ...BASE,
      e0: 200
    });

    expect(result.valid).toBe(false);
    expect(result.violations.some(v => v.includes('epsilon'))).toBe(true);
    // Points at the reduction that DOES apply rather than only refusing.
    expect(result.violations.join(' ')).toContain('10.1007/BF02458281');
  });

  it('warns at a marginal epsilon without failing', () => {
    // epsilon = 21/105 = 0.2 -> ~20% error in the reduction. Valid, but the
    // student should be told the approximation is being stretched.
    const result = AssumptionValidator.validateAssumptions(ASSUMPTIONS, {
      ...BASE,
      e0: 21
    });

    expect(result.valid).toBe(true);
    expect(result.warnings.some(w => w.includes('marginal'))).toBe(true);
  });

  it('scales with Km + s0, not with e0 alone', () => {
    // epsilon is a RATIO. The same [E]0 is fine against a large (Km + s0)
    // and not against a small one -- which is exactly why a fixed
    // "enzyme concentration limit" constant would have been wrong.
    const againstLargePool = AssumptionValidator.validateAssumptions(
      ASSUMPTIONS,
      { ...BASE, s0: 100_000, e0: 50 }
    );
    const againstSmallPool = AssumptionValidator.validateAssumptions(
      ASSUMPTIONS,
      { ...BASE, s0: 1, km: 0.1, e0: 50 }
    );

    expect(againstLargePool.valid).toBe(true);
    expect(againstSmallPool.valid).toBe(false);
  });
});

describe('[E]0 units are converted, not assumed', () => {
  it('a micromolar [E]0 against a millimolar substrate is not 1000x too big', () => {
    // The conversion the pipeline performs before handing e0 to the
    // validator. A caller working in uM against a Km in mM would otherwise
    // compute an epsilon 1000x too large and see a spurious failure --
    // the same class of error as the hardcoded `vmax / 1000` this codebase
    // has now removed twice.
    const e0Micromolar = 10_000; // 10,000 uM, i.e. 10 mM
    const converted = convertConcentration(e0Micromolar, 'uM', 'mM');
    expect(converted).toBeCloseTo(10, 9);

    const naive = AssumptionValidator.validateAssumptions(ASSUMPTIONS, {
      ...BASE,
      e0: e0Micromolar // wrong: uM value against mM Km/s0
    });
    const correct = AssumptionValidator.validateAssumptions(ASSUMPTIONS, {
      ...BASE,
      e0: converted
    });

    expect(naive.valid).toBe(false); // epsilon = 10000/105 = 95
    expect(correct.valid).toBe(true); // epsilon = 10/105 = 0.095
  });
});
