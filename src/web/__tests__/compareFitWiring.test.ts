/**
 * `rankModelsByFit` reaching a route.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The function that answers *"which mechanism does my bench data support"*
 * had **no production caller**. It was written, tested, and invoked by
 * nothing — so the answer was computed by nobody and reached no one.
 *
 * That is ADR 0039's defect class at the scale of a whole capability: not a
 * field dropped at a boundary, but an entire analysis never wired. It is
 * also why ADR 0060's defect could sit inside it unnoticed — a model that
 * never ran ranking FIRST, because its fabricated `0` sat closest to a small
 * experimental value.
 *
 * ADR 0045's boundary guard walks `KineticResult` fields to a rendering
 * surface. It has nothing to say about an exported function nobody calls,
 * which is the same question one level up.
 *
 * These tests assert the wiring's CONTRACT rather than the HTTP plumbing:
 * given a comparison result and a caller-supplied measurement, what does the
 * route hand back, and what does it refuse to invent.
 */
import { fitRankingFor } from '../../engine/model-comparison';
import type { ModelResult } from '../../engine/model-comparison';

function model(over: Partial<ModelResult>): ModelResult {
  return {
    model: 'michaelis-menten',
    finalValue: 1,
    confidence: 0.9,
    validated: true,
    executionTimeMs: 10,
    trajectoryPoints: 50,
    ...over,
  } as ModelResult;
}

/**
 * The route's decision, IMPORTED rather than re-implemented.
 *
 * The first version of this file defined its own copy of the condition. A
 * mutation to the route then changed nothing these tests could see, and the
 * harness reported NOT CAUGHT — a test written to prove the wiring, which
 * proved only that a local copy agreed with itself.
 *
 * That is ADR 0027's duplicate-source-of-truth defect, committed inside a
 * test demonstrating delivery. The parity test deleted in ADR 0027 failed
 * the same way: two implementations agreeing perfectly, on a question
 * neither was being asked.
 */
const fitFor = fitRankingFor;

const RAN = [
  model({ model: 'michaelis-menten', finalValue: 4.2 }),
  model({ model: 'competitive-inhibition', finalValue: 3.9 }),
];

describe('the comparison route ranks models against the caller measurement', () => {
  it('ranks by distance from the experimental value', () => {
    const fit = fitFor(RAN, 4.0)!;
    expect(fit.ranked[0]!.model).toBe('competitive-inhibition');
    expect(fit.ranked.map(r => r.ranking)).toEqual([1, 2]);
  });

  it('omits the ranking entirely when no measurement was supplied', () => {
    // `experimentalFinalValue` is a number the experimenter measured.
    // Caterva cannot resolve it from literature and must not invent one, so
    // its absence means "no fit ranking" -- never a default. This is the
    // experimental-condition rule of ADR 0012/0013 applied to an input.
    expect(fitFor(RAN, undefined)).toBeUndefined();
    expect(fitFor(RAN, null)).toBeUndefined();
    expect(fitFor(RAN, '4.0')).toBeUndefined();
  });

  it('refuses a non-finite measurement rather than ranking against it', () => {
    // `Math.abs(x - NaN)` is NaN, and `.sort()` on NaN comparisons leaves
    // the array in input order -- which would look like a ranking and be an
    // artefact of argument order.
    expect(fitFor(RAN, NaN)).toBeUndefined();
    expect(fitFor(RAN, Infinity)).toBeUndefined();
  });

  it('does not rank a model that never ran (ADR 0060, at the route)', () => {
    // The defect that could sit here unnoticed while nothing called this.
    // Against an experimental value of 0.4 -- ordinary near-complete
    // conversion -- a model carrying a fabricated 0 outranked both models
    // that ran, at 3.5 and 3.8 away.
    const withFailure = [
      ...RAN,
      model({ model: 'product-inhibition', finalValue: 0, validated: false, trajectoryPoints: 0 }),
    ];

    const fit = fitFor(withFailure, 0.4)!;

    expect(fit.ranked.map(r => r.model)).not.toContain('product-inhibition');
    expect(fit.excluded).toEqual([
      { model: 'product-inhibition', reason: 'ran but did not validate' },
    ]);
  });

  it('reports what it excluded, so a partial comparison cannot read as complete', () => {
    const fit = fitFor(
      [...RAN, model({ model: 'product-inhibition', finalValue: null, validated: false, error: 'solver diverged' })],
      0.4,
    )!;

    expect(fit.ranked).toHaveLength(2);
    expect(fit.excluded[0]!.reason).toMatch(/failed to run: solver diverged/);
  });

  it('ranks nothing when no model is usable, rather than something wrong', () => {
    const fit = fitFor(
      [
        model({ model: 'michaelis-menten', finalValue: null, validated: false, error: 'a' }),
        model({ model: 'competitive-inhibition', finalValue: 0, validated: false }),
      ],
      0.4,
    )!;

    expect(fit.ranked).toEqual([]);
    expect(fit.excluded).toHaveLength(2);
  });
});
