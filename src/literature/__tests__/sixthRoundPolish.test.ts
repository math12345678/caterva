/**
 * Polish pass after the sixth review round, the CLI's side.
 *
 * XS6V1-04: the CLI printed "The row names no isoform, so whether it measured
 * DPP4, the one asked for, is unknown." above "the row: the row's UniProt
 * accession (P27487) is DPP4".
 */
import { accessionNamesIsoform, rowScopeLines } from '../literatureResolver';

describe('a row whose UniProt cell names the isoform asked for', () => {
  const notes = ["the row's UniProt accession (P27487) is DPP4"];

  it('is said to name it', () => {
    const lines = rowScopeLines('km', null, 'DPP4', notes);
    expect(lines).toEqual(["The row's UniProt cell names DPP4, the one asked for."]);
  });

  it('matches whatever the spelling of the request', () => {
    expect(accessionNamesIsoform(notes, 'DPP-4')).toBe(true);
    expect(accessionNamesIsoform(notes, 'DPP8')).toBe(false);
  });

  it('is still called unknown when no note names it', () => {
    const lines = rowScopeLines('km', null, 'DPP4', []);
    expect(lines.join(' ')).toContain('names no isoform');
  });
});
