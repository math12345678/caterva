/**
 * Model selection, and the model that never ran.
 *
 * `rankModelsByFit` answers the most consequential question this codebase
 * asks: *which model best explains my experimental data*. It filtered with
 * `results.filter(r => !r.error)`, which excludes models that **threw** and
 * admits models that **ran and failed validation**.
 *
 * `scientificPipeline` returns `finalValue: simulationOutput.finalValue || 0`
 * with an empty trajectory in exactly that case. So a model that did not
 * validate arrived carrying a fabricated `0`, with no `error` string to
 * catch it on — and fit is scored by `|finalValue - experimental|`.
 *
 * The closer the experiment's own value is to zero, the better a failed
 * model scores. Measured against an experimental value of 0.4 — ordinary
 * near-complete conversion in enzyme kinetics — the model that did not
 * validate ranked FIRST at distance 0.4, ahead of two models that ran, at
 * 3.5 and 3.8.
 *
 * This is ADR 0058's defect at the point where it does the most damage: not
 * a skewed statistic, a recommendation.
 */
import { compareModels, rankModelsByFit } from '../model-comparison';
import type { ModelResult } from '../model-comparison';

const executeMock = jest.fn();

jest.mock('../../integration/scientificPipeline', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({
    execute: (...args: any[]) => executeMock(...args),
  })),
}));

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

describe('rankModelsByFit only ranks models that produced a result', () => {
  const RAN_AND_VALIDATED = [
    model({ model: 'michaelis-menten', finalValue: 4.2 }),
    model({ model: 'competitive-inhibition', finalValue: 3.9 }),
  ];

  it('does not rank a model that ran and failed validation', () => {
    // The exact fixture that produced the original finding. Note the
    // absence of an `error` field: that is what `!r.error` could not see.
    const results = [
      ...RAN_AND_VALIDATED,
      model({
        model: 'uncompetitive' as any,
        finalValue: 0,
        confidence: 0,
        validated: false,
        trajectoryPoints: 0,
      }),
    ];

    const { ranked, excluded } = rankModelsByFit(results, 0.4);

    expect(ranked.map(r => r.model)).toEqual([
      'competitive-inhibition',
      'michaelis-menten',
    ]);
    expect(ranked.find(r => (r.model as string) === 'uncompetitive')).toBeUndefined();
    expect(excluded).toEqual([
      { model: 'uncompetitive', reason: 'ran but did not validate' },
    ]);
  });

  it('does not rank a model that threw', () => {
    const results = [
      ...RAN_AND_VALIDATED,
      model({
        model: 'product-inhibition',
        finalValue: null,
        validated: false,
        error: 'solver diverged',
      }),
    ];

    const { ranked, excluded } = rankModelsByFit(results, 0.4);

    expect(ranked).toHaveLength(2);
    expect(excluded[0]!.reason).toMatch(/failed to run: solver diverged/);
  });

  it('reports what it left out rather than dropping it silently', () => {
    // A clean three-way ranking with no sign a fourth model was attempted
    // would let a reader conclude the comparison was complete.
    const results = [
      ...RAN_AND_VALIDATED,
      model({ model: 'product-inhibition', finalValue: null, validated: false, error: 'boom' }),
      model({ model: 'non-competitive-inhibition', finalValue: 0, validated: false }),
    ];

    const { ranked, excluded } = rankModelsByFit(results, 0.4);

    expect(ranked).toHaveLength(2);
    expect(excluded).toHaveLength(2);
    expect(excluded.map(e => e.model).sort()).toEqual([
      'non-competitive-inhibition',
      'product-inhibition',
    ]);
  });

  it('still ranks a model whose genuine result is zero', () => {
    // The other direction, and why the sentinel had to become null rather
    // than the filter becoming "drop zeros". Full conversion gives a real
    // zero and is a perfectly good fit to an experiment that measured zero.
    const results = [
      model({ model: 'michaelis-menten', finalValue: 4.2 }),
      model({ model: 'competitive-inhibition', finalValue: 0, validated: true, trajectoryPoints: 50 }),
    ];

    const { ranked, excluded } = rankModelsByFit(results, 0.1);

    expect(ranked[0]!.model).toBe('competitive-inhibition');
    expect(excluded).toEqual([]);
  });

  it('ranks nothing, rather than something wrong, when no model is usable', () => {
    const { ranked, excluded } = rankModelsByFit(
      [
        model({ model: 'michaelis-menten', finalValue: null, validated: false, error: 'a' }),
        model({ model: 'competitive-inhibition', finalValue: 0, validated: false }),
      ],
      0.4,
    );

    expect(ranked).toEqual([]);
    expect(excluded).toHaveLength(2);
  });
});

describe('compareModels refuses rather than naming a loser as the winner', () => {
  beforeEach(() => executeMock.mockReset());

  it('returns bestModel: null when no model produced a usable result', async () => {
    // THE DEFECT. This branch was `: results[0]` — the first model in the
    // list, which in this situation had just failed — returned as
    // `bestModel` with nothing marking it. A comparison in which nothing
    // ran has no winner.
    executeMock.mockImplementation(async () => {
      throw new Error('solver diverged');
    });

    const result = await compareModels({ km: 1, vmax: 10, s0: 5 });

    expect(result.bestModel).toBeNull();
    expect(result.bestFinalValue).toBeNull();
    expect(result.variability).toBeNull();
    expect(result.modelsAnalyzed).toBe(0);
    expect(result.modelsExcluded).toBe(4);
    expect(result.unanalysableReason).toMatch(/no best model to report/i);
  });

  it('does not name a model that ran and failed validation as best', async () => {
    // The same door ADR 0058 found in the sweep: no `error` string, a
    // fabricated finalValue of 0, and best = minimum.
    executeMock.mockImplementation(async ({ query }: any) => {
      if (query === 'michaelis-menten') {
        return {
          validated: true,
          validationConfidence: 0.9,
          results: { trajectory: [{ time: 0 }], finalValue: 3.2, computedMetrics: {} },
          metadata: { executionTimeMs: 1, literatureSourcesUsed: 1, confidenceScore: 0.9, warnings: [] },
        };
      }
      return {
        validated: false,
        validationConfidence: 0,
        results: { trajectory: [], finalValue: 0, computedMetrics: {} },
        metadata: { executionTimeMs: 1, literatureSourcesUsed: 0, confidenceScore: 0, warnings: [] },
      };
    });

    const result = await compareModels({ km: 1, vmax: 10, s0: 5 });

    expect(result.bestModel).toBe('michaelis-menten');
    expect(result.bestFinalValue).toBe(3.2);
    expect(result.modelsAnalyzed).toBe(1);
    expect(result.modelsExcluded).toBe(3);
  });

  it('computes variability over usable models only', async () => {
    // A fabricated zero in the set inflates the standard deviation, which
    // is reported to the user as "how much the models disagree".
    executeMock.mockImplementation(async ({ query }: any) => {
      const ok = query === 'michaelis-menten' || query === 'competitive-inhibition';
      return {
        validated: ok,
        validationConfidence: ok ? 0.9 : 0,
        results: {
          trajectory: ok ? [{ time: 0 }] : [],
          finalValue: query === 'michaelis-menten' ? 4 : query === 'competitive-inhibition' ? 4 : 0,
          computedMetrics: {},
        },
        metadata: { executionTimeMs: 1, literatureSourcesUsed: 1, confidenceScore: 0.9, warnings: [] },
      };
    });

    const result = await compareModels({ km: 1, vmax: 10, s0: 5 });

    // Two usable models, both 4.0 — they agree exactly.
    expect(result.modelsAnalyzed).toBe(2);
    expect(result.variability).toBe(0);
  });
});

describe('a failed model says why it failed', () => {
  beforeEach(() => executeMock.mockReset());

  it('keeps the real message when the pipeline throws a non-Error', async () => {
    // See batch-success-accounting.test.ts for the full reasoning. The
    // short version: the pipeline threw a plain object, `String(obj)` ran
    // instead of `.message`, and every model that failed recorded
    // "[object Object]" — including in the `insights` array this comparison
    // returns to explain itself when nothing ran.
    executeMock.mockImplementation(async () => {
      throw {
        jobId: 'job_1',
        error: 'SIMULATION_ERROR',
        message: 'Cannot simulate: ki could not be resolved from literature',
        executionTimeMs: 42,
      };
    });

    const result = await compareModels({ km: 1, vmax: 10, s0: 5 });

    expect(result.models[0]!.error).toBe(
      'Cannot simulate: ki could not be resolved from literature',
    );
    expect(result.models.some(m => m.error === '[object Object]')).toBe(false);
    // The refusal explains itself with the real cause, not with a
    // placeholder repeated four times.
    expect(result.insights[0]).toMatch(/ki could not be resolved/);
  });
});
