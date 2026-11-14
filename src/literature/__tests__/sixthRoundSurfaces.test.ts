import { mapFoundResult, withheldSentence } from '../literatureResolver';

/**
 * Sixth review round, XS5R2-03. Vibrio tyrosinaticus's tyrosinase kcat rows
 * are "isoenzyme A" (75 1/s) and "isoenzyme B" (90 1/s), ref 636408. The
 * search sets them aside without --isoform, and this CLI called them
 * "protein variant only". An isozyme is a wild-type protein in its own
 * right, and is said as one.
 */
describe('withheldSentence: isozyme rows are isozymes, not variants', () => {
  const base = {
    found: false as const, quantity: 'kcat' as const, logs: [], candidates: [],
    isoformsAvailable: [], variantCandidatesAvailable: [], crossSpeciesOrganismsAvailable: [],
    modesAvailable: [],
  };

  it('names an isozyme-only organism as such, beside the usable ones', () => {
    const s = withheldSentence({
      ...base, source: 'cross_species_withheld',
      crossSpeciesOrganismsAvailable: ['Homo sapiens', 'Vibrio tyrosinaticus'],
      crossSpeciesVariantOnly: ['Vibrio tyrosinaticus'],
      crossSpeciesIsozymeOnly: ['Vibrio tyrosinaticus'],
    });
    expect(s).toContain('only for other organisms (Homo sapiens; rows of a named isozyme only');
    expect(s).toContain('Vibrio tyrosinaticus');
    expect(s).not.toContain('protein variant');
  });

  it('says isozymes when they are all there is', () => {
    const s = withheldSentence({
      ...base, source: 'cross_species_withheld',
      crossSpeciesOrganismsAvailable: ['Vibrio tyrosinaticus'],
      crossSpeciesVariantOnly: ['Vibrio tyrosinaticus'],
      crossSpeciesIsozymeOnly: ['Vibrio tyrosinaticus'],
    });
    expect(s).toContain('each name an isozyme');
    expect(s).not.toContain('protein variant');
    expect(s).not.toContain('Pass --allow-cross-species');
  });
});

/**
 * XS5R2-04: the runner sends compose's isozyme notice with a Km ("EC 2.7.1.1
 * is 5 human proteins ... the model is of GCK"), and this CLI read only the
 * row's accession. It is read through, so the table can print it.
 */
describe('mapFoundResult: the isozyme notice is read through', () => {
  it('keeps headline, detail and remedy', () => {
    const r = mapFoundResult({
      organism: 'Homo sapiens',
      isozymeNotice: { headline: 'EC 2.7.1.1 is 5 proteins in human', detail: 'the model is of GCK', remedy: 'pass --isoform GCK' },
    }, 'km', 6.3, 'mM', []);
    expect(r.isozymeNotice).toEqual({
      headline: 'EC 2.7.1.1 is 5 proteins in human', detail: 'the model is of GCK', remedy: 'pass --isoform GCK',
    });
  });

  it('is absent when the runner sends none', () => {
    expect(mapFoundResult({ organism: 'Homo sapiens' }, 'km', 1, 'mM', []).isozymeNotice).toBeUndefined();
  });
});
