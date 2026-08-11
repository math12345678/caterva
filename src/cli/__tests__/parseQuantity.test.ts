import { parseQuantity, parseArgs } from '../parseQuantity';
import { UnitError } from '../../units';

describe('units come from the user, not a table keyed on the name', () => {
  it('reads the unit attached to the number', () => {
    const q = parseQuantity('vmax', '12.8mM/s');
    expect(q).toEqual({ value: 12.8, unit: 'mM/s', unitDeclared: true });
  });

  it('marks an omitted unit as ASSUMED rather than pretending it was given', () => {
    // The old CLI assigned vmax -> uM/min from a name table with no signal
    // to the user. Someone working in mM/s had their number reinterpreted
    // by a factor of 60,000 and the run continued.
    const q = parseQuantity('vmax', '12.8');
    expect(q.unitDeclared).toBe(false);
    expect(q.unit).toBe('uM/min');
  });

  it('accepts both micro signs and ASCII u', () => {
    for (const u of ['µM', 'μM', 'uM']) {
      expect(parseQuantity('km', `5.2${u}`).value).toBe(5.2);
    }
  });

  it('rejects a typo at the command line instead of three layers in', () => {
    expect(() => parseQuantity('km', '5.2mMM')).toThrow(UnitError);
    expect(() => parseQuantity('vmax', '12.8uM/fortnight')).toThrow(UnitError);
  });

  it('rejects a specific activity, which is not a concentration rate', () => {
    expect(() => parseQuantity('vmax', '12.4umol/min/mg')).toThrow(/specific activity/i);
  });

  it('refuses a bare number for a parameter with no convention', () => {
    expect(() => parseQuantity('mystery', '5')).toThrow(/no unit given/i);
  });

  it('handles scientific notation and negatives', () => {
    expect(parseQuantity('km', '1e-3mM').value).toBeCloseTo(0.001, 12);
    expect(parseQuantity('km', '-5mM').value).toBe(-5);
  });
});

describe('argument parsing', () => {
  it('does not let a boolean flag swallow the next argument', () => {
    // The old parser stepped i += 2 unconditionally, so `--verbose --km 5`
    // consumed "--km" as --verbose's value and dropped km entirely.
    const { flags, booleans } = parseArgs(['--verbose', '--km', '5.2mM']);
    expect(booleans.has('verbose')).toBe(true);
    expect(flags['km']).toBe('5.2mM');
  });

  it('treats a trailing flag as a boolean', () => {
    const { booleans } = parseArgs(['--km', '5', '--json']);
    expect(booleans.has('json')).toBe(true);
  });
});
