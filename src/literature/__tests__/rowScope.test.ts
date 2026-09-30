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

describe('a Kitz-Wilson row is named for what it is', () => {
  // BRENDA ref 702238's MAO-B phenylhydrazine row: "determined from
  // Kitz-Wilson plots", the K_I of an irreversible inactivation.
  const KITZ_WILSON = { isoform: 'MAO-B', inhibitionMode: 'unstated', versus: null, kitzWilson: true };

  it('is read from the runner only when it says so', () => {
    const r = mapFoundResult({ rowScope: KITZ_WILSON }, 'ki', 0.791, 'mM', []);
    expect(r.rowScope).toEqual(KITZ_WILSON);
    const plain = mapFoundResult(
      { rowScope: { ...KITZ_WILSON, kitzWilson: false } }, 'ki', 0.791, 'mM', []);
    expect(plain.rowScope).toEqual({ isoform: 'MAO-B', inhibitionMode: 'unstated', versus: null });
  });

  it('is said instead of "states no inhibition mode"', () => {
    const lines = rowScopeLines('ki', KITZ_WILSON);
    expect(lines).toContain(
      'The row was determined from Kitz-Wilson plots, which give the K_I of an irreversible ' +
        'inactivation, not a reversible Ki. It states no inhibition mode.',
    );
    expect(lines.join(' ')).not.toContain('which mechanism this Ki belongs to is unknown');
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
    modesAvailable: [],
  };

  it('names the modes BRENDA holds, and how to reach them', () => {
    // What the runner returns for `resolve --quantity ki --mode uncompetitive`
    // on human LDH and the quinoline sulfonamide of BRENDA ref 739793
    // (Tests/test_ki_mode_resolution.py, on the committed page).
    const s = withheldSentence({
      ...base,
      source: 'mode_withheld',
      modesAvailable: ['competitive inhibition versus NADH', 'noncompetitive inhibition versus pyruvate'],
    });
    expect(s).toBe(
      'Every row BRENDA holds for this Ki states an inhibition mode other than the one --mode ' +
        'asked for (competitive inhibition versus NADH; noncompetitive inhibition versus pyruvate). ' +
        'A Ki belongs to the mechanism it was measured under. To use one, run with --mode ' +
        'competitive or --mode noncompetitive; or run without --mode to take the resolver\'s pick ' +
        'with its stated mode printed beside it.',
    );
  });

  it('sends a mixed row to --mode noncompetitive, once', () => {
    // What the runner returns for rabbit hexokinase and MgADP- (BRENDA ref
    // 640206) asked for a competitive model, on the recorded page
    // (Tests/test_ki_mode_resolution.py, TestMixed).
    const s = withheldSentence({
      ...base,
      source: 'mode_withheld',
      modesAvailable: ['mixed inhibition versus MgATP2-', 'mixed inhibition versus glucose'],
    });
    expect(s).toContain('To use one, run with --mode noncompetitive; or run without --mode');
  });

  it('names no --mode when no --mode would take any of the rows', () => {
    // caterva.bind.core reads "partially competitive" as mode "partial",
    // which fits no model, so a row stating it is refused for every --mode.
    // No Ki row read so far states it (none of the Ki rows on the three
    // committed BRENDA pages), so this clause is the one the runner would
    // write for such a row, not one taken from BRENDA.
    const s = withheldSentence({ ...base, source: 'mode_withheld', modesAvailable: ['partial inhibition'] });
    expect(s).toContain('(partial inhibition)');
    expect(s).toContain('No --mode takes any of them');
    expect(s).not.toContain('run with --mode');
  });

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
