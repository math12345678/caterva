/**
 * The numbers a student typed at `report`, read the way every other command
 * reads them.
 *
 * WHAT WAS MEASURED
 * -----------------
 * `report` built its payload with `Number(flagValue(rest, '--s0'))`. The
 * CLI's own help teaches `--s0 10mM` for `simulate`, so that is what a
 * student types. `Number('10mM')` is `NaN`, and `JSON.stringify` turns NaN
 * into `null`:
 *
 *     {"supplied":[{"name":"s0","value":null,"unit":"mM"}],"s0":null}
 *
 * `report_lab.py` skips supplied entries whose value is None, so the number
 * vanished entirely and the document came back saying:
 *
 *     the simulation was not run: s0 is missing — yours to choose — how
 *     much substrate you put in, not a property of the enzyme
 *
 * **They did choose it.** The tool dropped it and then lectured them for not
 * providing it. A refusal that blames the user for the tool's own data loss
 * is worse than a crash, because it is actionable-looking and wrong.
 *
 * THE SECOND DEFECT, WHICH IS QUIETER AND WORSE
 * ---------------------------------------------
 * `--vmax 0.25` with no unit was passed straight through and used as mM/s,
 * because that is what the engine's other inputs are in. `parseQuantity`,
 * which every other command uses, assumes **uM/min** for a bare vmax.
 *
 * So the same three characters meant two things 60,000x apart depending on
 * which command read them — and `report`'s own help text contains the
 * sentence "assumed unit is reported -- vmax in mM/s read as uM/min is off
 * by 60,000x", warning about precisely the bug in the command printing it.
 *
 * A wrong Vmax does not fail. It produces a plausible trajectory, in a
 * document whose entire purpose is being handed to a teacher.
 *
 * WHY THIS IS A MODULE AND NOT FOUR LINES IN THE SWITCH
 * ----------------------------------------------------
 * Because the switch statement is where the first version lived, and it
 * drifted from `simulate` without anyone seeing it. Parsing a quantity is
 * already solved twice over — `parseQuantity` for the syntax,
 * `src/units.ts` for the conversion — and the defect was `report` doing
 * neither. This function does no arithmetic of its own; it routes.
 *
 * ASSUMED UNITS ARE REPORTED, NOT SILENT
 * --------------------------------------
 * `parseQuantity` already distinguishes a unit the user declared from one it
 * chose. That distinction is the whole provenance argument applied to units,
 * so it survives into the document: a value whose unit was assumed says so
 * in the Parameters table, beside the number.
 */
import { parseQuantity } from './parseQuantity';
import { convertConcentration, vmaxInSubstrateUnitsPerSecond } from '../units';

/** One number the student supplied, ready for the report payload. */
export interface SuppliedQuantity {
  name: string;
  /** In the engine's units: mM for concentrations, mM/s for Vmax. */
  value: number;
  unit: string;
  /** Why this number. `undefined` rather than invented when not given. */
  basis?: string;
  /** Set only when the unit was ASSUMED. Rendered in the document. */
  assumedUnit?: string;
}

export interface ReportQuantities {
  supplied: SuppliedQuantity[];
  /** Empty when everything parsed. Each entry is shown and the run stops. */
  problems: string[];
}

/** The engine's units. Every value is converted to these, or refused. */
const ENGINE_CONCENTRATION = 'mM';
const ENGINE_VMAX = 'mM/s';

/**
 * @param raw  flag name -> the string the user typed, e.g. `{ s0: '10mM' }`.
 *             A flag the user did not pass must be absent or undefined —
 *             NOT the empty string, which is a value they did type.
 */
export function parseReportQuantities(
  raw: Readonly<Record<string, string | undefined>>,
): ReportQuantities {
  const supplied: SuppliedQuantity[] = [];
  const problems: string[] = [];

  const s0Raw = raw['s0'];
  const vmaxRaw = raw['vmax'];

  if (s0Raw !== undefined) {
    try {
      const parsed = parseQuantity('s0', s0Raw);
      supplied.push({
        name: 's0',
        value: convertConcentration(parsed.value, parsed.unit, ENGINE_CONCENTRATION),
        unit: ENGINE_CONCENTRATION,
        basis: raw['s0-basis'],
        assumedUnit: parsed.unitDeclared ? undefined : parsed.unit,
      });
    } catch (err) {
      problems.push(err instanceof Error ? err.message : String(err));
    }
  }

  if (vmaxRaw !== undefined) {
    try {
      const parsed = parseQuantity('vmax', vmaxRaw);
      // Converted RELATIVE to the substrate unit, which is what makes a rate
      // meaningful — `vmaxInSubstrateUnitsPerSecond` refuses to assume
      // either side. s0 is always mM by the time it reaches here, and when
      // no s0 was supplied the engine's own unit is still mM, so the
      // conversion is well defined either way.
      supplied.push({
        name: 'vmax',
        value: vmaxInSubstrateUnitsPerSecond(
          parsed.value,
          parsed.unit,
          ENGINE_CONCENTRATION,
        ),
        unit: ENGINE_VMAX,
        basis: raw['vmax-basis'],
        assumedUnit: parsed.unitDeclared ? undefined : parsed.unit,
      });
    } catch (err) {
      problems.push(err instanceof Error ? err.message : String(err));
    }
  }

  const kmRaw = raw['km'];
  const kmBasis = raw['km-basis'];

  // A MEASUREMENT MAY BE SUPPLIED, BUT NEVER BARE.
  //
  // Herbert Sauro asked the question this answers: "If you refuse to run
  // what does the user do?" When the literature genuinely holds no value —
  // not a mistyped substrate label, not an outage, actually nothing — there
  // is nothing to sample, so there is no ensemble, and refusing leaves a
  // student with nowhere to go. He is right about that.
  //
  // His own suggestion was a default of 0.5 with a warning in the Antimony.
  // The objection to it is not that 0.5 is a bad guess; it is that nobody
  // chose it, so there is no one to ask about it and nothing in the document
  // a teacher can challenge.
  //
  // The third option is the student's own number, ATTRIBUTED. They measured
  // it in the lab, or it is on the handout. That is a human source, it is
  // defensible, and the model runs.
  //
  // WHY THE BASIS IS REQUIRED HERE AND NOT FOR s0
  // ---------------------------------------------
  // `s0` is an experimental CONDITION — the student chose how much substrate
  // to put in, and asking them to cite that is the category error START_HERE
  // says has broken this codebase twice. `km` is a MEASUREMENT: somebody
  // stood at a bench and measured it. Accepting one bare would erase exactly
  // the distinction this whole project is built on, and `--km 5.2` with no
  // source is a default with extra steps.
  if (kmRaw !== undefined && (kmBasis === undefined || kmBasis.trim() === '')) {
    problems.push(
      'km is a measured property of the enzyme, so Terrium will not take it ' +
      'as a bare number. Say where it came from:\n' +
      '  --km 5.2mM --km-basis "measured in our lab, 14 Mar 2026"\n\n' +
      'The report prints that basis beside the value, so whoever reads it ' +
      'knows the number is yours rather than the literature\'s. A km with ' +
      'no stated source is a default with extra steps — and a default is ' +
      'a number nobody can be asked about.',
    );
  } else if (kmRaw !== undefined) {
    try {
      const parsed = parseQuantity('km', kmRaw);
      supplied.push({
        name: 'km',
        value: convertConcentration(parsed.value, parsed.unit, ENGINE_CONCENTRATION),
        unit: ENGINE_CONCENTRATION,
        basis: kmBasis,
        assumedUnit: parsed.unitDeclared ? undefined : parsed.unit,
      });
    } catch (err) {
      problems.push(err instanceof Error ? err.message : String(err));
    }
  }

  return { supplied, problems };
}
