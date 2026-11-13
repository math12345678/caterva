import { withheldSentence } from '../literatureResolver';

/**
 * The fifth adversarial round (2026-11-12, V7-04): "BRENDA holds this kcat
 * only for other organisms (Mus musculus). Pass --allow-cross-species" was
 * printed for human COX-2, whose only Mus musculus row is the N580A
 * mutant's; the re-run was refused again. An organism whose every row
 * measured a variant is said to be one, and the opt-in is not offered for it.
 */
describe('withheldSentence: an organism holding only a variant is not a way out', () => {
  const base = {
    found: false as const, quantity: 'kcat' as const, logs: [], candidates: [],
    isoformsAvailable: [], variantCandidatesAvailable: [], crossSpeciesOrganismsAvailable: [],
    modesAvailable: [],
  };

  it('says the only rows elsewhere are a variant\'s and offers no opt-in', () => {
    const s = withheldSentence({
      ...base, source: 'cross_species_withheld',
      crossSpeciesOrganismsAvailable: ['Mus musculus'], crossSpeciesVariantOnly: ['Mus musculus'],
    });
    expect(s).toContain('(Mus musculus) measured a protein variant');
    expect(s).toContain('would not fill it either');
    expect(s).not.toContain('Pass --allow-cross-species');
  });

  it('offers only the organisms with usable rows', () => {
    const s = withheldSentence({
      ...base, source: 'cross_species_withheld',
      crossSpeciesOrganismsAvailable: ['Mus musculus', 'Ovis aries'], crossSpeciesVariantOnly: ['Mus musculus'],
    });
    expect(s).toContain('only for other organisms (Ovis aries; rows of a protein variant only, withheld: Mus musculus)');
    expect(s).toContain('--allow-cross-species');
  });

  it('reads as before for a runner that sends no variant list', () => {
    const s = withheldSentence({ ...base, source: 'cross_species_withheld', crossSpeciesOrganismsAvailable: ['Sus scrofa'] });
    expect(s).toContain('only for other organisms (Sus scrofa)');
  });
});
