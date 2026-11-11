/**
 * A computed Vmax printed as 0.0020050000000000003 mM/s: 40.1 x 0.00005 in
 * floating point, shown to its last noisy digit. Display only -- --json and
 * exported files keep the full value.
 */
import { formatDerived, formatValue } from '../formatNumber';

describe('formatDerived', () => {
  it('prints a bridged Vmax to four significant figures', () => {
    expect(formatDerived(40.1 * 0.00005)).toBe('0.002005');
    expect(formatDerived(0.0020050000000000003)).toBe('0.002005');
    expect(formatDerived(123456)).toBe('123500');
  });

  it('leaves non-finite values as they are', () => {
    expect(formatDerived(Number.NaN)).toBe('NaN');
  });
});

describe('formatValue', () => {
  it('drops the float noise and keeps every digit a person typed', () => {
    expect(formatValue(0.1 + 0.2)).toBe('0.3');
    expect(formatValue(10.73)).toBe('10.73');
    expect(formatValue(12.3456789)).toBe('12.3456789');
  });

  it('passes a string through', () => {
    expect(formatValue('n/a')).toBe('n/a');
  });
});
