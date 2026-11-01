/**
 * Unit parsing and conversion for kinetic parameters.
 *
 * WHY THIS EXISTS
 *
 * Twice now, a hardcoded `vmax / 1000` appeared in this tree with the
 * comment "convert uM/min to mM/min" -- first inside
 * `calculateSubstrateDepletion`, then, after that was removed, at the call
 * site in `ScientificPipeline.execute`. Both times it made a failing test
 * pass. Both times it was a fabrication: nothing in the code established
 * those units, the factor applied unconditionally regardless of what the
 * parameters actually carried, and one version paired it with `|| 0`, so a
 * missing Vmax silently became zero.
 *
 * The information needed to do this correctly was already present the whole
 * time. Parameters in this tree carry a declared `unit` string -- 'mM',
 * 'μM/min', 'umol/min/mg' -- and `ParameterMetadata.unit` is part of the
 * public shape. So the conversion is read off the data rather than assumed.
 *
 * The governing rule: an unrecognised or incompatible unit raises. It is
 * never passed through unconverted and never assigned a default. A silent
 * unit error produces a number that is wrong by orders of magnitude while
 * looking entirely reasonable, which is the most dangerous failure mode
 * this codebase has.
 */

/** Raised when a unit string cannot be parsed, or cannot be converted. */
export class UnitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UnitError';
  }
}

/**
 * Concentration units, as multiples of molar (M).
 *
 * Both 'μ' (U+03BC GREEK SMALL LETTER MU) and 'µ' (U+00B5 MICRO SIGN) are
 * accepted, along with the ASCII 'u'. They are visually identical and
 * different sources emit different ones; treating them as distinct would
 * make a unit fail to parse for reasons invisible in a diff. This tree's
 * own fixtures use U+03BC.
 */
const CONCENTRATION_TO_MOLAR: ReadonlyMap<string, number> = new Map([
  ['m', 1],
  ['mm', 1e-3],
  ['um', 1e-6],
  ['nm', 1e-9],
  ['pm', 1e-12],
  ['mol/l', 1],
  ['mmol/l', 1e-3],
  ['umol/l', 1e-6],
  ['nmol/l', 1e-9]
]);

/** Time units, as multiples of a second. */
const TIME_TO_SECONDS: ReadonlyMap<string, number> = new Map([
  ['s', 1],
  ['sec', 1],
  ['secs', 1],
  ['second', 1],
  ['seconds', 1],
  ['min', 60],
  ['mins', 60],
  ['minute', 60],
  ['minutes', 60],
  ['h', 3600],
  ['hr', 3600],
  ['hour', 3600],
  ['hours', 3600]
]);

/**
 * Normalise a unit token: lowercase, trimmed, with both micro signs mapped
 * to ASCII 'u'.
 */
function normalise(token: string): string {
  return token
    .trim()
    .replace(/µ/g, 'u') // MICRO SIGN
    .replace(/μ/g, 'u') // GREEK SMALL LETTER MU
    .toLowerCase();
}

/** Factor converting `unit` to molar. Throws if unrecognised. */
export function concentrationFactor(unit: string): number {
  const key = normalise(unit);
  const factor = CONCENTRATION_TO_MOLAR.get(key);
  if (factor === undefined) {
    throw new UnitError(
      `Unrecognised concentration unit '${unit}'. Known units: ` +
      `${[...CONCENTRATION_TO_MOLAR.keys()].join(', ')}. Refusing to guess -- ` +
      'an assumed unit is wrong by orders of magnitude while looking plausible.'
    );
  }
  return factor;
}

/** Factor converting `unit` to seconds. Throws if unrecognised. */
export function timeFactor(unit: string): number {
  const key = normalise(unit);
  const factor = TIME_TO_SECONDS.get(key);
  if (factor === undefined) {
    throw new UnitError(
      `Unrecognised time unit '${unit}'. Known units: ` +
      `${[...TIME_TO_SECONDS.keys()].join(', ')}.`
    );
  }
  return factor;
}

/** Convert a concentration between declared units. */
export function convertConcentration(
  value: number,
  from: string,
  to: string
): number {
  return (value * concentrationFactor(from)) / concentrationFactor(to);
}

interface ParsedRate {
  concentration: string;
  time: string;
}

/**
 * Parse a rate unit of the form `<concentration>/<time>`, e.g. 'μM/min'.
 *
 * Specific activities such as 'umol/min/mg' are REJECTED, deliberately and
 * with an explanation. They are amount per time per mass of protein, not
 * concentration per time, and converting one to the other requires the
 * enzyme concentration and molecular weight -- neither of which this
 * function receives. BRENDA reports turnover in exactly this form, so the
 * case is real rather than hypothetical, and quietly treating 'umol/min/mg'
 * as 'umol/min' would produce a number with no physical meaning.
 */
export function parseRateUnit(unit: string): ParsedRate {
  const parts = normalise(unit).split('/');

  if (parts.length === 3) {
    throw new UnitError(
      `'${unit}' is a specific activity (amount per time per mass), not a ` +
      'concentration rate. Converting it to a concentration per time needs ' +
      'the enzyme concentration and molecular weight, which are not ' +
      'available here. Supply Vmax as a concentration rate (e.g. mM/s), or ' +
      'provide [E] and MW so it can be converted explicitly.'
    );
  }

  if (parts.length !== 2) {
    throw new UnitError(
      `Cannot parse '${unit}' as a rate. Expected <concentration>/<time>, ` +
      "e.g. 'mM/s' or 'uM/min'."
    );
  }

  const [concentration, time] = parts as [string, string];
  // Validate both halves now so the error names the unit, not a later
  // NaN with no provenance.
  concentrationFactor(concentration);
  timeFactor(time);
  return { concentration, time };
}

/**
 * Convert a rate (concentration per time) between declared units.
 *
 * Example: convertRate(1000, 'uM/min', 'mM/min') === 1
 */
export function convertRate(value: number, from: string, to: string): number {
  const source = parseRateUnit(from);
  const target = parseRateUnit(to);

  const concentrationRatio =
    concentrationFactor(source.concentration) /
    concentrationFactor(target.concentration);
  const timeRatio = timeFactor(target.time) / timeFactor(source.time);

  return value * concentrationRatio * timeRatio;
}

/**
 * Express a Vmax in "units of s0 per second", which is what the depletion
 * check and the engine both want.
 *
 * This is the operation the hardcoded `/1000` was standing in for. It is
 * driven entirely by the declared units of the two parameters, so it is
 * correct when Vmax arrives in mM/s, μM/min or M/hour, and it raises rather
 * than guessing when the unit is missing or is a specific activity.
 */
export function vmaxInSubstrateUnitsPerSecond(
  vmaxValue: number,
  vmaxUnit: string | undefined,
  s0Unit: string | undefined
): number {
  if (!vmaxUnit) {
    throw new UnitError(
      'Vmax has no declared unit, so it cannot be converted to the ' +
      'substrate units. Refusing to assume one.'
    );
  }
  if (!s0Unit) {
    throw new UnitError(
      'The substrate concentration has no declared unit, so Vmax cannot be ' +
      'expressed relative to it. Refusing to assume one.'
    );
  }
  return convertRate(vmaxValue, vmaxUnit, `${s0Unit}/s`);
}
