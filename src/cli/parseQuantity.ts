/**
 * Parsing `--km 5.2mM` — a number with the unit attached.
 *
 * WHY
 *
 * The CLI took bare numbers (`--km 5.2 --vmax 12.8`) and assigned units
 * from a table keyed on the parameter's NAME: km→mM, vmax→μM/min. The
 * label therefore always agreed with the assumption and never with what
 * the user meant. Someone with a Vmax in mM/s got their number silently
 * reinterpreted as μM/min — a factor of 60,000 — and the run continued,
 * producing a trajectory and a provenance record for a quantity nobody
 * supplied.
 *
 * That is the same defect as the hardcoded `vmax / 1000` this codebase has
 * removed twice, and as `getDefaultUnit`. The fix is the same: take the
 * unit from the data instead of inventing one.
 *
 * A bare number is still accepted, because requiring units on every flag
 * would make the tool tedious for the common case. But it is recorded as
 * ASSUMED, travels through the pipeline marked that way, and is reported
 * in the output — so the user can see which of their numbers the tool
 * interpreted rather than read.
 */

import { UnitError, concentrationFactor, parseRateUnit } from '../units';

export interface ParsedQuantity {
  value: number;
  unit: string;
  /** true when the unit came from the user, false when this module chose
   *  it. Anything derived from an assumed unit must be labelled. */
  unitDeclared: boolean;
}

/**
 * Units assumed for a bare number, by parameter name.
 *
 * These are conventions, not measurements, and they exist only so that
 * `--km 5.2` works at all. Every use is flagged `unitDeclared: false`.
 */
const ASSUMED_UNITS: Readonly<Record<string, string>> = {
  km: 'mM',
  ki: 'mM',
  s0: 'mM',
  e0: 'mM',
  enzyme_conc: 'mM',
  vmax: 'uM/min',
  kcat: '1/s',
};

/** Splits "5.2mM" into "5.2" and "mM"; "5.2" into "5.2" and "". */
const NUMBER_THEN_UNIT = /^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*)$/;

/**
 * Flags that mean a chemical NAME under `--resolve` and a QUANTITY without it.
 *
 * This is the trap. `resolve` is documented as
 *
 *     scientific resolve "lactate dehydrogenase" --substrate pyruvate ...
 *
 * so `--substrate pyruvate` is the first thing anyone learns. Carrying that
 * straight over to `simulate` -- the obvious next step, and the one the README
 * teaches next -- fails, because without `--resolve` the same flag is an
 * initial concentration. The old message was "could not read a number",
 * which is true, names the symptom, and hides the cause completely.
 */
const NAME_UNDER_RESOLVE = new Set(['substrate', 'enzyme']);

/** Anything with no digit at all is a word, not a malformed number. */
const HAS_DIGIT = /\d/;

/**
 * Say what is actually wrong, and when the cause is knowable, say that too.
 *
 * A parse error should distinguish "you typed 5,2 instead of 5.2" from "you
 * passed a name where a quantity goes", because those need different fixes and
 * only the second is a wrong mental model of the command.
 */
function explainUnreadable(name: string, raw: string): string {
  if (HAS_DIGIT.test(raw)) {
    return (
      `--${name} ${raw}: could not read a number. Expected something like ` +
      `'5.2' or '5.2mM'.`
    );
  }

  const flag = name.replace(/_/g, '-');
  if (!NAME_UNDER_RESOLVE.has(name.replace(/-/g, '_'))) {
    return (
      `--${flag} ${raw}: '${raw}' is a name, not a quantity. This flag takes ` +
      `a number, like '5.2' or '5.2mM'.`
    );
  }

  return (
    `--${flag} ${raw}: '${raw}' is a name, not a quantity.\n\n` +
    `  In 'simulate', --${flag} is a concentration. It only means a name to ` +
    `look up\n` +
    `  when you also pass --resolve, which is what turns the run into a ` +
    `literature\n  lookup. You probably want:\n\n` +
    `    simulate mm --resolve --enzyme "<enzyme>" \\\n` +
    `      --${flag} ${raw} --organism "<organism>" \\\n` +
    `      --s0 10mM --enzyme-conc 0.001mM\n\n` +
    `  Or, to look the value up without simulating:\n\n` +
    `    resolve "<enzyme>" --${flag} ${raw} --organism "<organism>"`
  );
}

/**
 * Parse a CLI quantity for `name`.
 *
 * Throws on anything it cannot interpret rather than falling back to a
 * default — a silently reinterpreted number is worse than a rejected one,
 * because it looks like an answer.
 */
export function parseQuantity(name: string, raw: string): ParsedQuantity {
  const match = NUMBER_THEN_UNIT.exec(raw);
  if (!match) {
    throw new UnitError(explainUnreadable(name, raw));
  }

  const value = Number(match[1]);
  if (!Number.isFinite(value)) {
    throw new UnitError(`--${name} ${raw}: '${match[1]}' is not a finite number.`);
  }

  const declared = (match[2] ?? '').trim();

  if (declared.length > 0) {
    // Validate it NOW, against the same tables the rest of the system
    // uses, so a typo fails at the command line rather than three layers
    // in with a misleading message.
    if (declared.includes('/')) {
      parseRateUnit(declared);
    } else {
      concentrationFactor(declared);
    }
    return { value, unit: declared, unitDeclared: true };
  }

  const assumed = ASSUMED_UNITS[name.toLowerCase()];
  if (!assumed) {
    throw new UnitError(
      `--${name} ${raw}: no unit given and none is conventional for ` +
      `'${name}'. Write the unit explicitly, e.g. --${name} ${match[1]}mM.`
    );
  }

  return { value, unit: assumed, unitDeclared: false };
}

/**
 * Parse `--flag value` pairs into quantities, keeping non-quantity flags
 * (`--json`, `--verbose`, `--organism`) as plain strings.
 */
export function parseArgs(argv: string[]): {
  flags: Record<string, string>;
  booleans: Set<string>;
} {
  const flags: Record<string, string> = {};
  const booleans = new Set<string>();

  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (!token || !token.startsWith('--')) continue;

    const key = token.slice(2);
    const next = argv[i + 1];

    // A flag followed by another flag, or by nothing, is a boolean. The
    // previous parser advanced by 2 unconditionally, so `--verbose` ate
    // the following argument and `simulate q --verbose --km 5` silently
    // dropped the km.
    if (next === undefined || next.startsWith('--')) {
      booleans.add(key);
    } else {
      flags[key] = next;
      i++;
    }
  }

  return { flags, booleans };
}
