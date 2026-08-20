import { commandEnsemble } from '../commandEnsemble';

/**
 * `scientific ensemble` — the command the mission is about.
 *
 * Everywhere else, a Km the literature disagrees about becomes one number
 * chosen by `min()`. This command shows the disagreement and what it does to
 * the answer, which is what Bakker described and Sauro called "the right way
 * to do it".
 *
 * These assert on RENDERED OUTPUT, because a payload plumbed through and
 * never printed satisfies a shape assertion and fails the only thing that
 * matters — the standing rule in `resolveOutput.test.ts`, and the reason
 * `blockers` sat unread at five sites for as long as it did.
 *
 * The Python side is exercised for real: `Tests/test_ensemble_boundary.py`
 * spawns the runner, and `test_ensemble.py` pins the weighting. What is
 * mocked here is only the transport, so that a rendering regression is
 * distinguishable from a resolver one.
 */


function captureStdout(): { output: () => string; restore: () => void } {
  const chunks: string[] = [];
  const original = process.stdout.write.bind(process.stdout);
  (process.stdout as unknown as { write: unknown }).write = (chunk: unknown) => {
    chunks.push(String(chunk));
    return true;
  };
  return {
    output: () => chunks.join(''),
    restore: () => {
      (process.stdout as unknown as { write: unknown }).write = original;
    },
  };
}

/** The real human-LDH disagreement: 0.03 and 0.398 mM, thirteen-fold apart. */
const PAYLOAD = {
  ok: true,
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  rows: 2,
  frontier: 2,
  seed: 1,
  disclaimer:
    'This is the spread of published measurements, weighted by how well ' +
    'evidenced each one is. It is NOT an uncertainty estimate: there is no ' +
    'validation step rejecting models that disagree with data.',
  candidates: [
    {
      value: 0.03,
      unit: 'mM',
      probability: 0.5,
      referenceId: '286469',
      conditions: null,
      grades: ['absent', 'not_assessed', 'exact'],
    },
    {
      value: 0.398,
      unit: 'mM',
      probability: 0.5,
      referenceId: '286442',
      conditions: null,
      grades: ['absent', 'not_assessed', 'exact'],
    },
  ],
  summary: { low: 0.03, median: 0.03, high: 0.398, fold_range: 13.2666 },
  band: {
    swept: ['km'],
    succeeded: 200,
    attempted: 200,
    supportNote: 'The band covers all 200 runs; none failed to integrate.',
    envelopes: [
      {
        column: '[S]',
        times: [0, 2, 4],
        low: [10, 0.1302, 0],
        median: [10, 0.1302, 0],
        high: [10, 0.9407, 0],
      },
    ],
  },
};

const OPTIONS = { fixture: 'f.html', substrate: 'pyruvate', seed: 1 };

function render(payload: unknown): string {
  const cap = captureStdout();
  try {
    commandEnsemble(OPTIONS, () => payload as never);
    return cap.output();
  } finally {
    cap.restore();
  }
}

describe('what a student is shown', () => {
  it('names every published value, not just the one that won', () => {
    const out = render(PAYLOAD);
    expect(out).toContain('0.03');
    expect(out).toContain('0.398');
  });

  it('shows how often each was drawn, so the weighting is visible', () => {
    expect(render(PAYLOAD)).toContain('50.0%');
  });

  it('carries the reference for each, so an alternative is checkable', () => {
    const out = render(PAYLOAD);
    expect(out).toContain('286469');
    expect(out).toContain('286442');
  });

  it('shows the grades that produced the weights', () => {
    expect(render(PAYLOAD)).toContain('absent / not_assessed / exact');
  });

  it('states the spread with its fold-range', () => {
    const out = render(PAYLOAD);
    expect(out).toMatch(/13\.3/);
  });
});

describe('the band — what the disagreement does to the answer', () => {
  /**
   * THE LOAD-BEARING ONE. The parameter spread says the literature
   * disagrees; the band says whether that matters. Without it this command
   * is a more decorative version of the tie flag.
   */
  it('reports where the choice of paper matters most', () => {
    const out = render(PAYLOAD);
    expect(out).toContain('differs most at t=2');
    expect(out).toContain('0.1302');
    expect(out).toContain('0.9407');
  });

  it('states how many runs the band is drawn over', () => {
    expect(render(PAYLOAD)).toContain('all 200 runs');
  });

  /**
   * A column identical across every run is not interesting and crowds out
   * the one that is. Said in a line rather than a table of equal numbers.
   */
  it('collapses a column that does not vary', () => {
    const flat = {
      ...PAYLOAD,
      band: {
        ...PAYLOAD.band,
        envelopes: [
          { column: '[X]', times: [0, 1], low: [1, 1], median: [1, 1], high: [1, 1] },
        ],
      },
    };
    expect(render(flat)).toContain('identical across every run');
  });

  it('works without a band, when no simulation was requested', () => {
    const { band, ...noBand } = PAYLOAD;
    const out = render(noBand);
    expect(out).toContain('0.398');
    expect(out).not.toContain('differs most');
  });
});

describe('what it refuses to imply', () => {
  /**
   * ADR 0024 declined sampling because a spread with no validation step
   * reads as an uncertainty estimate. The answer is to make the sentence
   * inseparable from the numbers.
   */
  it('always prints the disclaimer', () => {
    expect(render(PAYLOAD)).toContain('NOT an uncertainty estimate');
  });

  it('always prints the seed, so the run can be re-derived', () => {
    expect(render(PAYLOAD)).toContain('--seed 1');
  });

  it('reports a failure rather than an empty band', () => {
    expect(commandEnsemble(OPTIONS, () => null)).toBe(1);
  });

  it('distinguishes "could not run" from "the ensemble failed"', () => {
    expect(
      commandEnsemble(OPTIONS, () => ({ ok: false, error: 'no rows' }) as never),
    ).toBe(2);
  });
});
