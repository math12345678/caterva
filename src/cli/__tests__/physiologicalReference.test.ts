import {
  DEFAULT_PH_TOLERANCE,
  DEFAULT_TEMPERATURE_TOLERANCE_C,
  parsePhysiological,
} from '../physiologicalReference';

/**
 * `--physiological` exists so Bakker's condition-proximity axis can fire at
 * all. Before it, the axis reported `not_assessed` on every single run —
 * honest, and therefore decoration.
 *
 * The tests that matter are the refusals: no default reference, and no
 * reference without a stated basis.
 */

describe('there is no default reference, and that is the point', () => {
  it('returns no reference when the flag is absent, and no error', () => {
    // Omitting it is the normal case. The axis stays honestly unassessed.
    const result = parsePhysiological(undefined, undefined, undefined);
    expect(result.reference).toBeUndefined();
    expect(result.error).toBeUndefined();
  });

  it('never invents 7.4 / 37', () => {
    // A built-in mammalian default would report a confident "far" for a
    // thermophile assay that was in fact ideal.
    const result = parsePhysiological(undefined, undefined, undefined);
    expect(result.reference?.ph).toBeUndefined();
    expect(result.reference?.temperatureC).toBeUndefined();
  });

  it('rejects a tolerance given without a reference to be a tolerance of', () => {
    // Silently ignoring it would leave the user believing they set something.
    const result = parsePhysiological(undefined, '0.4,5', undefined);
    expect(result.error).toContain('mean nothing without --physiological');
  });
});

describe('a reference must say where it came from', () => {
  it('refuses a reference with no basis', () => {
    const result = parsePhysiological('7.4,37', undefined, undefined);
    expect(result.reference).toBeUndefined();
    expect(result.error).toContain('--physiological-basis');
    // The reasoning, not just the requirement.
    expect(result.error).toContain('a number someone typed');
  });

  it('refuses a blank basis', () => {
    const result = parsePhysiological('7.4,37', undefined, '   ');
    expect(result.error).toBeDefined();
  });

  it('accepts a stated basis and trims it', () => {
    const result = parsePhysiological('7.4,37', undefined, '  human blood plasma  ');
    expect(result.reference?.basis).toBe('human blood plasma');
  });
});

describe('parsing', () => {
  it('reads pH and temperature in that order', () => {
    const { reference } = parsePhysiological('7.4,37', undefined, 'human');
    expect(reference?.ph).toBe(7.4);
    expect(reference?.temperatureC).toBe(37);
  });

  it('accepts a thermophile reference, because that is the whole argument', () => {
    const { reference } = parsePhysiological('7.0,70', undefined, 'T. thermophilus optimum');
    expect(reference?.ph).toBe(7);
    expect(reference?.temperatureC).toBe(70);
  });

  it('catches transposed arguments rather than accepting a pH of 37', () => {
    // Far more likely a typo than a real intent, and the suggested fix is
    // the transposition rather than a generic complaint.
    const result = parsePhysiological('37,7.4', undefined, 'human');
    expect(result.reference).toBeUndefined();
    expect(result.error).toContain('outside 0–14');
    expect(result.error).toContain('did you mean --physiological "7.4,37"');
  });

  it('rejects a malformed pair with an example', () => {
    for (const bad of ['7.4', '7.4,37,20', 'abc,37', '']) {
      const result = parsePhysiological(bad, undefined, 'human');
      expect(result.reference).toBeUndefined();
      expect(result.error).toContain('pH,temperatureC');
    }
  });

  it('uses stated tolerances over the defaults', () => {
    const { reference } = parsePhysiological('7.4,37', '0.1,2', 'human');
    expect(reference?.phTolerance).toBe(0.1);
    expect(reference?.temperatureToleranceC).toBe(2);
  });

  it('falls back to documented tolerance defaults', () => {
    const { reference } = parsePhysiological('7.4,37', undefined, 'human');
    expect(reference?.phTolerance).toBe(DEFAULT_PH_TOLERANCE);
    expect(reference?.temperatureToleranceC).toBe(DEFAULT_TEMPERATURE_TOLERANCE_C);
  });

  it('rejects a negative tolerance', () => {
    const result = parsePhysiological('7.4,37', '-1,5', 'human');
    expect(result.error).toContain('cannot be negative');
  });

  it('accepts pH 0 and 0 °C as real values', () => {
    // Extreme but real. A truthiness check would reject them.
    const { reference } = parsePhysiological('0,0', undefined, 'extreme control');
    expect(reference?.ph).toBe(0);
    expect(reference?.temperatureC).toBe(0);
  });
});
