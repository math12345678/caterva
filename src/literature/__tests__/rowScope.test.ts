/**
 * What the winning row says it measured reaches the CLI, not only the API.
 *
 * The runner parses the row's commentary with caterva.bind.core and emits
 * `rowScope`. The API turned it into flags; the CLI dropped it, which
 * `check_both_front_ends_read_it.py` caught on 2026-09-29.
 */
import { describe, expect, it } from 'vitest';

import { mapFoundResult, rowScopeLines, withheldSentence } from '../literatureResolver';

const GOSSYPOL_ROW =
  'LDH-B, pH not specified in the publication, temperature not specified in the publication';

describe('mapFoundResult reads the row scope', () => {
  it('carries the commentary and the parsed scope', () => {
    const r = mapFoundResult(
      {
        source: 'brenda_exact',
        commentary: GOSSYPOL_ROW,
        rowScope: { isoform: 'LDH-B', inhibitionMode: 'unstated', versus: null },
      },
      'ki',
      0.0014,
      'mM',
      [],
    );
    expect(r.commentary).toBe(GOSSYPOL_ROW);
    expect(r.rowScope).toEqual({ isoform: 'LDH-B', inhibitionMode: 'unstated', versus: null });
  });

  it('an all-null or missing scope is no scope', () => {
    const empty = mapFoundResult(
      { rowScope: { isoform: null, inhibitionMode: null, versus: null } }, 'km', 1, 'mM', []);
    expect(empty.rowScope).toBeNull();
    expect(mapFoundResult({}, 'km', 1, 'mM', []).rowScope).toBeNull();
  });
});

describe('rowScopeLines', () => {
  it('names the isoform and a missing mode for a Ki', () => {
    const lines = rowScopeLines('ki', { isoform: 'LDH-B', inhibitionMode: 'unstated', versus: null });
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('isoform LDH-B');
    expect(lines[1]).toContain('states no inhibition mode');
  });

  it('names the mode and what it was measured against', () => {
    expect(rowScopeLines('ki', { isoform: null, inhibitionMode: 'competitive', versus: 'NADH' })).toEqual([
      'The row measured competitive inhibition versus NADH. A Ki belongs to that mode and that assay.',
    ]);
  });

  it('never tells a Km row about inhibition modes', () => {
    expect(rowScopeLines('km', { isoform: null, inhibitionMode: 'unstated', versus: null })).toEqual([]);
    expect(rowScopeLines('km', null)).toEqual([]);
  });
});

describe('withheldSentence: rows found and withheld are not "nothing"', () => {
  const base = {
    found: false as const, quantity: 'ki' as const, logs: [], candidates: [],
    isoformsAvailable: [], variantCandidatesAvailable: [], crossSpeciesOrganismsAvailable: [],
  };

  it('names the isoforms and the flag that reaches them', () => {
    const s = withheldSentence({ ...base, source: 'isoform_withheld', isoformsAvailable: ['LDH-A', 'LDH-B'] });
    expect(s).toContain('only for other isoforms (LDH-A, LDH-B)');
    expect(s).toContain('--isoform');
  });

  it('names the organisms and the opt-in', () => {
    const s = withheldSentence({ ...base, source: 'cross_species_withheld', crossSpeciesOrganismsAvailable: ['Sus scrofa'] });
    expect(s).toContain('(Sus scrofa)');
    expect(s).toContain('--allow-cross-species');
  });

  it('says nothing when nothing was withheld', () => {
    expect(withheldSentence({ ...base, source: 'not_found' })).toBeNull();
    expect(withheldSentence({ ...base, source: null })).toBeNull();
  });
});
