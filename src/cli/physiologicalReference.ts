/**
 * Parse `--physiological` into the reference Bakker's proximity axis needs.
 *
 * WHY IT IS A FLAG AND NOT A DEFAULT
 * ----------------------------------
 * "Physiological pH and temperature" has no organism-independent value.
 * 7.4 and 37 °C describe a mammal and misdescribe Thermus thermophilus,
 * whose enzymes are measured near 70 °C — the very comparison Lisa Jeske
 * raised when she warned that mixing conditions across sources produces
 * "fantasy numbers".
 *
 * So the reference is an EXPERIMENTAL CONDITION the person building the
 * model states, exactly as `s0` and `end` are (ADR 0012/0013). Without it
 * the axis reports `not_assessed` and says why — which is true, where a
 * built-in 7.4/37 would report a confident "far" for a thermophile assay
 * that was in fact ideal.
 *
 * WHY `basis` IS REQUIRED
 * -----------------------
 * A reference with no stated basis is a number someone typed. Requiring the
 * caller to say where it came from is the same rule the rest of the system
 * applies to every other value, applied to the yardstick itself — otherwise
 * the thing measuring provenance would be the one thing without any.
 */

export interface PhysiologicalReference {
  ph: number;
  temperatureC: number;
  basis: string;
  phTolerance: number;
  temperatureToleranceC: number;
}

export interface ParseResult {
  reference?: PhysiologicalReference;
  error?: string;
}

/** Tolerances used when `--physiological-tolerance` is omitted. */
export const DEFAULT_PH_TOLERANCE = 0.5;
export const DEFAULT_TEMPERATURE_TOLERANCE_C = 5;

function parsePair(raw: string): [number, number] | null {
  const parts = raw.split(',').map((part) => part.trim());
  if (parts.length !== 2) return null;
  const [first, second] = parts.map(Number);
  if (!Number.isFinite(first) || !Number.isFinite(second)) return null;
  return [first!, second!];
}

/**
 * `--physiological "7.4,37" --physiological-basis "human blood plasma"`
 *
 * Returns `{}` when the flag is absent — not an error. Omitting it is the
 * normal case and leaves the axis honestly unassessed.
 */
export function parsePhysiological(
  value: string | undefined,
  tolerance: string | undefined,
  basis: string | undefined,
): ParseResult {
  if (value === undefined) {
    if (tolerance !== undefined || basis !== undefined) {
      // A tolerance with nothing to be a tolerance OF is almost certainly a
      // typo'd invocation, and silently ignoring it would leave the user
      // believing they set something.
      return {
        error:
          '--physiological-tolerance and --physiological-basis mean nothing ' +
          'without --physiological. Give the conditions your model represents, ' +
          'e.g. --physiological "7.4,37".',
      };
    }
    return {};
  }

  const parsed = parsePair(value);
  if (parsed === null) {
    return {
      error:
        `--physiological expects "pH,temperatureC" (got '${value}'). ` +
        'Example: --physiological "7.4,37" for a human-like model, or ' +
        '"7.0,70" for a thermophile. There is no default, because ' +
        '"physiological" means something different for each.',
    };
  }
  const [ph, temperatureC] = parsed;

  if (ph < 0 || ph > 14) {
    // Not a plausibility opinion about the model — a value outside 0–14 is
    // not a pH at all, and is far more likely to be the arguments given in
    // the wrong order (`--physiological "37,7.4"`).
    return {
      error:
        `A pH of ${ph} is outside 0–14. The order is "pH,temperatureC" — ` +
        `did you mean --physiological "${temperatureC},${ph}"?`,
    };
  }

  if (basis === undefined || basis.trim().length === 0) {
    return {
      error:
        '--physiological also needs --physiological-basis: say where these ' +
        'conditions come from (a species, a citation, or "chosen by me"). ' +
        'A reference with no stated basis is a number someone typed, and ' +
        'this is the yardstick every other value gets measured against.',
    };
  }

  let phTolerance = DEFAULT_PH_TOLERANCE;
  let temperatureToleranceC = DEFAULT_TEMPERATURE_TOLERANCE_C;
  if (tolerance !== undefined) {
    const parsedTolerance = parsePair(tolerance);
    if (parsedTolerance === null) {
      return {
        error:
          `--physiological-tolerance expects "pH,temperatureC" (got '${tolerance}'). ` +
          'Example: --physiological-tolerance "0.4,5".',
      };
    }
    const [phTol, tempTol] = parsedTolerance;
    if (phTol < 0 || tempTol < 0) {
      return { error: 'Tolerances cannot be negative.' };
    }
    phTolerance = phTol!;
    temperatureToleranceC = tempTol!;
  }

  return {
    reference: { ph, temperatureC, basis: basis.trim(), phTolerance, temperatureToleranceC },
  };
}
