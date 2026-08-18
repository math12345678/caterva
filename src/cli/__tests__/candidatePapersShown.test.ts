import { commandResolve } from '../commandResolve';
import { resolveKinetic } from '../../literature/literatureResolver';

jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

/**
 * The CLI's most reassuring sentence was false exactly when it mattered.
 *
 * When BRENDA holds no value, the Python resolver searches PubMed and CORE
 * and returns `source: "literature_candidates"` with the papers it found.
 * `literatureResolver.ts` parsed that response into
 * `{ found: false, quantity, logs }` — dropping the list at the boundary
 * without ever reading it — and this command then printed:
 *
 *     "BRENDA and PubMed were searched and returned nothing.
 *      This is an answer, not a failure."
 *
 * PubMed had not returned nothing. It had returned papers. **The line is
 * untrue in precisely the case where the student most needs somewhere to go
 * next**, and it is the line written to sound trustworthy.
 *
 * The same defect was fixed on the API path one pass earlier (ADR 0106).
 * Finding it again here is the standing lesson: a lesson applied only where
 * it was first learned is a lesson half-taken.
 *
 * These assert on RENDERED OUTPUT for the reason this file already gives —
 * a field plumbed through and never printed satisfies a shape assertion and
 * fails the only thing that matters.
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

const OPTIONS = {
  enzyme: 'lactate dehydrogenase',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  quantity: 'km' as const,
  json: false,
};

const PAPERS = [
  {
    title: 'Kinetics of human muscle lactate dehydrogenase',
    url: 'https://pubmed.ncbi.nlm.nih.gov/1234567/',
    source: 'pubmed',
    pmid: '1234567',
    doi: null,
  },
  {
    title: 'Substrate affinity of LDH isoenzymes',
    url: 'https://core.ac.uk/download/98765.pdf',
    source: 'core',
    pmid: null,
    doi: '10.1000/example',
  },
];

async function render(
  candidates: unknown[],
  json = false,
): Promise<string> {
  mockedResolve.mockResolvedValueOnce({
    found: false,
    quantity: 'km',
    logs: ['BRENDA exact: nothing', 'PubMed: 2 candidates'],
    candidates,
  } as never);
  const cap = captureStdout();
  try {
    await commandResolve({ ...OPTIONS, json });
    return cap.output();
  } finally {
    cap.restore();
  }
}

describe('candidate papers are shown, not discarded', () => {
  it('names each paper the search found', async () => {
    const out = await render(PAPERS);
    expect(out).toContain('Kinetics of human muscle lactate dehydrogenase');
    expect(out).toContain('Substrate affinity of LDH isoenzymes');
  });

  /**
   * A title with no locator is a claim. PubMed's esummary never supplies a
   * DOI and CORE has no PMID, so covering one source's locator silently
   * strips the provenance from every paper that came from the other.
   */
  it('gives each one a locator, from whichever source it came', async () => {
    const out = await render(PAPERS);
    expect(out).toContain('PMID 1234567');
    expect(out).toContain('doi 10.1000/example');
  });

  /**
   * THE LOAD-BEARING ASSERTION. The old sentence must not appear when the
   * search did find something — it is the false claim this change exists to
   * remove, and a fix that printed the papers while leaving the sentence
   * above them would be worse than before: contradicting itself on screen.
   */
  it('does not claim PubMed returned nothing when it returned papers', async () => {
    const out = await render(PAPERS);
    expect(out).not.toContain('returned nothing');
  });

  it('says Terrium did not read a number out of them', async () => {
    const out = await render(PAPERS);
    expect(out).toMatch(/does not read numbers out of full text/i);
  });

  it('tells the student how to supply a value they find', async () => {
    const out = await render(PAPERS);
    expect(out).toContain('--km');
    expect(out).toContain('--cite km=');
  });

  /**
   * The genuinely-empty case keeps the original wording, because there it
   * is TRUE. "Nothing was found" and "something was found that nobody used"
   * are two facts, and ADR 0065's rule is that they must not share a
   * rendering.
   */
  it('keeps the honest original message when the search really was empty', async () => {
    const out = await render([]);
    expect(out).toContain('returned nothing');
    expect(out).not.toMatch(/paper\(s\) that may report/i);
  });

  it('carries the papers in --json too, not only in the prose', async () => {
    const out = await render(PAPERS, true);
    const parsed = JSON.parse(out);
    expect(parsed.status).toBe('not_found');
    expect(parsed.candidates).toHaveLength(2);
    expect(parsed.candidates[0].pmid).toBe('1234567');
  });
});
