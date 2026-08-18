import { commandResolve } from '../commandResolve';
import { resolveKinetic } from '../../literature/literatureResolver';

jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

/**
 * Bakker's finding, on the front end that never said it.
 *
 * `evidence_rank.py` narrows candidates to the non-dominated frontier — a
 * row is dropped only when another beats it on EVERY axis, which needs no
 * weights and so could be built without inventing any. Among the survivors
 * nothing is beaten outright, and `min()` chooses. That choice is arbitrary,
 * and `selection_tie.py` exists to say so out loud:
 *
 *     "Reporting the minimum silently presents literature disagreement as a
 *      measurement."
 *
 * The API path has printed it since ADR 0051. **The CLI never mentioned
 * it** — so a CLI user was handed 21.1, the lowest of six equally
 * well-evidenced LDH turnover rows spanning to 6467, with nothing saying the
 * evidence found 6467 equally credible.
 *
 * Found by `check_both_front_ends_read_it.py` (ADR 0110/0112), which counted
 * 24 keys read by one front end and not the other. This is the first paid
 * off.
 *
 * These assert on RENDERED OUTPUT, for the reason `resolveOutput.test.ts`
 * gives: a field plumbed through and never printed satisfies a shape
 * assertion and fails the only thing that matters.
 */

const mockedResolve = resolveKinetic as jest.MockedFunction<typeof resolveKinetic>;

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

const TIE = {
  candidates: [
    {
      value: 21.1,
      unit: '1/s',
      organism: 'Homo sapiens',
      reference_id: '684519',
      conditions: 'pH 6.0, 25C, recombinant wild-type enzyme, with FBP',
      selected: true,
    },
    {
      value: 6467,
      unit: '1/s',
      organism: 'Homo sapiens',
      reference_id: '761568',
      conditions: 'wild-type, presence of D-fructose-1,6-diphosphate',
      selected: false,
    },
  ],
  low: 21.1,
  high: 6467,
  fold_range: 306.5,
  reason:
    '2 rows were equally well evidenced and their values span 21.1 to 6467, ' +
    'a 306-fold range. The value returned was chosen by taking the lowest, ' +
    'which the evidence does not justify.',
};

const BASE = {
  found: true as const,
  quantity: 'kcat' as const,
  value: 21.1,
  unit: '1/s',
  organism: 'Homo sapiens',
  source: 'brenda_exact',
  citation: { source: 'BRENDA', reference_id: '684519' },
  crossSpecies: false,
  logs: [],
};

const OPTIONS = {
  enzyme: 'lactate dehydrogenase',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  quantity: 'kcat' as const,
  json: false,
};

async function render(extra: Record<string, unknown>): Promise<string> {
  mockedResolve.mockResolvedValueOnce({ ...BASE, ...extra } as never);
  const cap = captureStdout();
  try {
    await commandResolve(OPTIONS);
    return cap.output();
  } finally {
    cap.restore();
  }
}

describe('the CLI says when the evidence did not choose', () => {
  it('says so at all', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toMatch(/evidence did not choose/i);
  });

  /**
   * A bare "there was a tie" is unactionable. The reader has to be able to
   * go and look at the row that was NOT returned — which is why the
   * alternative and its reference id both have to appear.
   */
  it('names the alternative and its reference', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toContain('6467');
    expect(out).toContain('761568');
  });

  it('marks which row was actually returned', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toContain('(returned)');
  });

  it('shows the spread, so the disagreement has a size', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toMatch(/306/);
  });

  /**
   * The resolver's sentence, verbatim. Rewording it in the client would
   * make this a second place the finding's wording can drift, and the
   * Python module is where it was argued over.
   */
  it('carries the reason, including that the tie-break is unjustified', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toMatch(/which the evidence does not justify/);
  });

  it('carries each row conditions, so the reader can judge for themselves', async () => {
    const out = await render({ selectionTie: TIE });
    expect(out).toContain('D-fructose-1,6-diphosphate');
  });

  /**
   * Fewer than two candidates is not a tie, and a one-row "tie" line would
   * be a warning about nothing — which trains readers to skip warnings.
   */
  it('says nothing when there is no tie', async () => {
    const out = await render({ selectionTie: null });
    expect(out).not.toMatch(/evidence did not choose/i);
  });

  it('says nothing when only one candidate survived', async () => {
    const out = await render({
      selectionTie: { ...TIE, candidates: [TIE.candidates[0]] },
    });
    expect(out).not.toMatch(/evidence did not choose/i);
  });
});
