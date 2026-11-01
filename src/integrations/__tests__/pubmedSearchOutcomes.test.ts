/**
 * "PubMed has nothing" and "PubMed was not reached" are different facts.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `searchPubMedForEnzymeKinetics` tried three query strategies and, when all
 * three fell through, threw ONE error for every reason they might have:
 *
 *     No real literature found on PubMed for "X" and "Y". The system requires
 *     verified papers from scientific databases. Check your network access
 *     and verify this enzyme/substrate pair has published kinetics data.
 *
 * The sentence hedges — "check your network access AND verify this pair has
 * published kinetics data" — because the code genuinely did not know which
 * had happened. Every branch was a bare `continue`.
 *
 * So a dead network was reported to the user as "this enzyme has no papers",
 * which is an absence of evidence presented as evidence of absence. The rest
 * of this tool is built around not doing that: `resolve` exits 0 / 2 / 1 for
 * found / nothing / could-not-look, and says in its own help text that
 * collapsing the last two "teaches you to read an absence of evidence as
 * evidence of absence".
 *
 * The integration is exercised through a stubbed `fetch` rather than the real
 * endpoint: these assertions are about which outcome is reported for a given
 * server behaviour, and pinning that to NCBI's live availability would make
 * the test flaky in exactly the situation it exists to describe.
 */
import {
  PubMedUnavailableError,
  searchPubMedForEnzymeKinetics,
} from '../crossref-pubmed-real';

const realFetch = global.fetch;

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

/** PubMed answering normally, with no hits. */
const EMPTY_RESULT = jsonResponse({ esearchresult: { idlist: [] } });

afterEach(() => {
  global.fetch = realFetch;
  jest.restoreAllMocks();
});

describe('a search that ran and found nothing', () => {
  it('returns an empty list rather than throwing', async () => {
    // Every strategy reaches PubMed and PubMed says there is nothing. That
    // is an ANSWER about the literature, and the caller is entitled to treat
    // it as one.
    global.fetch = jest.fn(async () => EMPTY_RESULT) as unknown as typeof fetch;

    const papers = await searchPubMedForEnzymeKinetics('nonesuchase', 'unobtainium', 5);
    expect(papers).toEqual([]);
  });

  it('counts a completed search even when a later strategy cannot run', async () => {
    // First strategy completes with zero hits; the network then dies. One
    // strategy DID reach the registry and reported nothing, so the honest
    // answer is still "nothing found" rather than "could not look".
    let call = 0;
    global.fetch = jest.fn(async () => {
      call += 1;
      if (call === 1) return EMPTY_RESULT;
      throw new TypeError('fetch failed');
    }) as unknown as typeof fetch;

    await expect(
      searchPubMedForEnzymeKinetics('nonesuchase', 'unobtainium', 5),
    ).resolves.toEqual([]);
  });
});

describe('a search that could not be performed', () => {
  it('throws PubMedUnavailableError when no strategy reaches the registry', async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError('fetch failed');
    }) as unknown as typeof fetch;

    await expect(
      searchPubMedForEnzymeKinetics('lactate dehydrogenase', 'pyruvate', 5),
    ).rejects.toBeInstanceOf(PubMedUnavailableError);
  });

  it('says the result is not a claim about what exists', async () => {
    // The message is the part a user reads. If it hedged again — "check your
    // network and verify this pair has published data" — the type would be
    // right and the user would still be misled.
    global.fetch = jest.fn(async () => {
      throw new TypeError('fetch failed');
    }) as unknown as typeof fetch;

    await expect(
      searchPubMedForEnzymeKinetics('lactate dehydrogenase', 'pyruvate', 5),
    ).rejects.toThrow(/says nothing about whether such papers exist/i);
  });

  it('treats an HTTP error from PubMed as not-reached, not as empty', async () => {
    // A 500 means the registry did not answer the question. Counting it as
    // "no results" would let an NCBI outage read as an empty literature.
    global.fetch = jest.fn(async () => ({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: { get: () => 'application/json' },
      text: async () => '',
    })) as unknown as typeof fetch;

    await expect(
      searchPubMedForEnzymeKinetics('lactate dehydrogenase', 'pyruvate', 5),
    ).rejects.toBeInstanceOf(PubMedUnavailableError);
  });

  it('treats a non-JSON body as not-reached', async () => {
    // A captive-portal or proxy HTML page is a 200 that is not an answer.
    // Parsing it as "no idlist, therefore no papers" is how a coffee-shop
    // wifi login screen becomes a scientific finding.
    global.fetch = jest.fn(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => 'text/html' },
      text: async () => '<html>Sign in to continue</html>',
    })) as unknown as typeof fetch;

    await expect(
      searchPubMedForEnzymeKinetics('lactate dehydrogenase', 'pyruvate', 5),
    ).rejects.toBeInstanceOf(PubMedUnavailableError);
  });
});

describe('the query is built from the arguments', () => {
  it('searches for the enzyme it was given', async () => {
    // The defect that started this: `literature`, `validate` and `simulate`
    // all called the layer above with the string 'lactate dehydrogenase'
    // hardcoded, so every search was for the same enzyme. This asserts the
    // argument reaches the URL, which is the property those call sites
    // violated.
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: unknown) => {
      seen.push(String(url));
      return EMPTY_RESULT;
    }) as unknown as typeof fetch;

    await searchPubMedForEnzymeKinetics('acetylcholinesterase', 'acetylcholine', 5);

    expect(seen.length).toBeGreaterThan(0);
    expect(seen.join(' ')).toContain('acetylcholinesterase');
    expect(seen.join(' ')).not.toContain('lactate');
  });
});
