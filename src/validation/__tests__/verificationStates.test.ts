/**
 * Three-state citation verification.
 *
 * This exists because the two-state version regressed twice, in the same
 * direction, for the same reason: `verifyReference` returned `boolean`,
 * which cannot express "I could not check". Faced with an unreachable
 * registry, the only options were `false` (fails every run) and `true`
 * (passes everything), and both times someone chose `true`.
 *
 * The second regression went further than network handling and accepted a
 * DOI that CrossRef AFFIRMATIVELY reported does not exist:
 *
 *     if (!resolves) {
 *       logger.warn('DOI not found in registry; accepting peer-reviewed source');
 *     }
 *     // ...falls through, returns true
 *
 * With a format check in front, that is "true for any DOI-shaped string on
 * an object whose own `peerReviewed` field says true" -- and `peerReviewed`
 * is self-declared, not verified. Every fabricated DOI this repository has
 * ever contained passes it.
 *
 * The invariant these tests defend: **"the registry says this does not
 * exist" and "the registry could not be reached" must never collapse into
 * each other**, and no configuration may turn the former into a pass.
 */
import {
  LiteratureVerifier,
  type LiteratureReference
} from '../scientificValidator';

const BASE: LiteratureReference = {
  title: 'A paper',
  authors: ['Author'],
  year: 2020,
  journal: 'Journal',
  peerReviewed: true
};

const REAL_DOI = '10.1073/pnas.88.16.7328';
const FABRICATED_DOI = '10.9999/completely-made-up';

const originalOptIn = process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'];

beforeEach(() => {
  LiteratureVerifier.resetRegistryCache();
  delete process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'];
});

afterAll(() => {
  if (originalOptIn === undefined) {
    delete process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'];
  } else {
    process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'] = originalOptIn;
  }
});

describe('a registry that answers "no" is a rejection, not a network problem', () => {
  it('rejects a DOI the registry reports does not exist', () => {
    // Primed false = CrossRef was reached and said no such DOI.
    LiteratureVerifier.primeRegistryCache(`doi:${FABRICATED_DOI}`, false);

    return LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: FABRICATED_DOI
    }).then(outcome => {
      expect(outcome.status).toBe('rejected');
      expect(outcome.reason).toMatch(/does not exist|does not resolve/i);
    });
  });

  it('NO configuration can turn a rejected citation into a pass', () => {
    // The load-bearing test. The opt-in below exists so that working
    // offline does not require editing the source -- the pressure that
    // caused both regressions. It must not rescue a fabricated citation.
    LiteratureVerifier.primeRegistryCache(`doi:${FABRICATED_DOI}`, false);
    process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'] = '1';

    return LiteratureVerifier.verifyReference({
      ...BASE,
      doi: FABRICATED_DOI
    }).then(verified => {
      expect(verified).toBe(false);
    });
  });

  it('rejects a malformed DOI without needing a registry at all', async () => {
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: '10.1/x'
    });
    expect(outcome.status).toBe('rejected');
  });

  it('rejects a non-peer-reviewed source even when its DOI resolves', async () => {
    LiteratureVerifier.primeRegistryCache(`doi:${REAL_DOI}`, true);

    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: REAL_DOI,
      peerReviewed: false
    });
    expect(outcome.status).toBe('rejected');
  });
});

describe('a registry that confirms is a verification', () => {
  it('verifies a DOI that resolves', async () => {
    LiteratureVerifier.primeRegistryCache(`doi:${REAL_DOI}`, true);

    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: REAL_DOI
    });
    expect(outcome.status).toBe('verified');
    expect(await LiteratureVerifier.verifyReference({ ...BASE, doi: REAL_DOI })).toBe(
      true
    );
  });
});

describe('a reference with no identifier is unverified, not verified', () => {
  it('does not treat "peer-reviewed" as a substitute for an identifier', async () => {
    // `peerReviewed` is a self-declared field on a plain object. Accepting
    // it as verification is accepting the claim as its own evidence.
    const outcome = await LiteratureVerifier.verifyReferenceDetailed(BASE);
    expect(outcome.status).toBe('unverified');
  });

  it('is not verified by default', async () => {
    expect(await LiteratureVerifier.verifyReference(BASE)).toBe(false);
  });

  it('is accepted only under the explicit opt-in', async () => {
    process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'] = '1';
    expect(await LiteratureVerifier.verifyReference(BASE)).toBe(true);
  });
});

describe('offline mode: CATERVA_SKIP_DOI_VERIFICATION', () => {
  // Skipping the registry lookup is a legitimate need -- an offline
  // laptop, CI without egress, a sandbox that 403s CrossRef. What it must
  // never do is call the result VERIFIED.
  //
  // The first version of this flag returned `{ status: 'verified' }` with
  // the comment "Trust peer-reviewed assertion for identifiers that are
  // well-formed", and shipped with a test asserting that a completely
  // fabricated DOI came back verified. That is the same defect as Parts 6
  // and 11, arriving a third time by a different route: a citation is
  // stamped verified on nothing but its SHAPE and a self-declared
  // `peerReviewed: true`.
  //
  // Skipping a check yields UNVERIFIED. That is the entire reason the
  // third state exists.
  const originalSkipDoi = process.env['CATERVA_SKIP_DOI_VERIFICATION'];

  beforeEach(() => {
    process.env['CATERVA_SKIP_DOI_VERIFICATION'] = '1';
    LiteratureVerifier.resetRegistryCache();
  });

  afterEach(() => {
    if (originalSkipDoi === undefined) {
      delete process.env['CATERVA_SKIP_DOI_VERIFICATION'];
    } else {
      process.env['CATERVA_SKIP_DOI_VERIFICATION'] = originalSkipDoi;
    }
  });

  it('reports UNVERIFIED, never verified, when the lookup is skipped', async () => {
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: FABRICATED_DOI
    });

    expect(outcome.status).toBe('unverified');
    expect(outcome.status).not.toBe('verified');
    expect(outcome.reason).toMatch(/skipped/i);
  });

  it('says so for a well-formed PMID too', async () => {
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      pubmedId: '12345678'
    });
    expect(outcome.status).toBe('unverified');
  });

  it('still rejects a malformed DOI', async () => {
    // Malformedness needs no network, so skipping the lookup cannot
    // excuse it.
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: 'not-a-real-doi'
    });
    expect(outcome.status).toBe('rejected');
  });

  it('still rejects a malformed PMID', async () => {
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      pubmedId: 'not-a-number'
    });
    expect(outcome.status).toBe('rejected');
  });

  it('still rejects a non-peer-reviewed source', async () => {
    const outcome = await LiteratureVerifier.verifyReferenceDetailed({
      ...BASE,
      doi: FABRICATED_DOI,
      peerReviewed: false
    });
    expect(outcome.status).toBe('rejected');
  });

  it('is not accepted by the boolean form without the separate opt-in', async () => {
    // The two variables compose: skip the lookup, then decide separately
    // what an unlooked-up citation is worth. Skipping alone does not make
    // it acceptable.
    delete process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'];
    expect(
      await LiteratureVerifier.verifyReference({ ...BASE, doi: FABRICATED_DOI })
    ).toBe(false);
  });

  it('is accepted only when the caller also opts in to unverified citations', async () => {
    process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'] = '1';
    expect(
      await LiteratureVerifier.verifyReference({ ...BASE, doi: FABRICATED_DOI })
    ).toBe(true);
    delete process.env['CATERVA_ALLOW_UNVERIFIED_CITATIONS'];
  });
});
