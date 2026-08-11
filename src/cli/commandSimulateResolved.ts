/**
 * `scientific simulate --resolve` — look up what the simulation needs, run
 * it, and show where every number came from.
 *
 * This is the command that makes Terrium a tool rather than a validator.
 * The old `simulate` path could not succeed through literature at all:
 *
 *   - `fetchRealLiterature('lactate dehydrogenase', 'lactate')` was called
 *     with those two strings HARDCODED, so every simulation of every system
 *     fetched papers about lactate dehydrogenase regardless of the query.
 *   - It built `Literature` objects with `extractedParameters: []`, so the
 *     recommender had no values to recommend and validation always failed
 *     with NO_LITERATURE.
 *   - It set `peerReviewed: true` with the comment "Papers in PubMed are
 *     peer-reviewed by definition". That is false — PubMed indexes
 *     preprints, editorials, letters and retracted papers — and the field
 *     feeds a verifier that trusts it.
 *
 * This path uses the resolver that returns actual measurements: BRENDA
 * exact, BRENDA cross-species, then PubMed candidates, each carrying a
 * value, a unit, an organism and a citation.
 *
 * THE PROVENANCE TABLE IS THE POINT. A number on screen with no source is
 * what every other tool gives you. Every parameter printed here says where
 * it came from, and anything that could not be sourced stops the run rather
 * than being defaulted.
 */

import { ScientificPipeline } from '../integration/scientificPipeline';
import {
  ResolverUnavailableError,
  resolveKinetic,
} from '../literature/literatureResolver';
import { convertConcentration } from '../units';
import { parseQuantity } from './parseQuantity';

const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RED = '\x1b[31m';
const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';

const useColour = process.stdout.isTTY === true;
const c = (code: string, text: string): string =>
  useColour ? `${code}${text}${RESET}` : text;

/** How a parameter's value was obtained. Printed for every one. */
export interface ParameterProvenance {
  name: string;
  value: number;
  unit: string;
  /** 'user' | 'brenda_exact' | 'brenda_cross_species' | ... */
  origin: string;
  citation?: string;
  organism?: string;
  crossSpecies?: boolean;
  /** true when the CLI had to assume the unit rather than being told. */
  unitAssumed?: boolean;
}

export interface SimulateResolvedOptions {
  enzyme?: string;
  ec?: string;
  substrate: string;
  organism: string;
  /** Explicit values from the command line. These WIN over literature. */
  overrides: Record<string, string>;
  /** [E]0 with its unit, if given. Bridges kcat to Vmax. */
  enzymeConc?: string;
  json: boolean;
}

/** Exit codes mirror `resolve`: 0 ran, 1 could not look up, 2 no data. */
export async function commandSimulateResolved(
  options: SimulateResolvedOptions,
): Promise<number> {
  const provenance: ParameterProvenance[] = [];
  const unresolved: string[] = [];

  // ---- user-supplied values first -------------------------------------
  //
  // A value the user typed is not a guess and must not be overwritten by a
  // lookup. It is still recorded with its origin so the table is complete.
  const userValues: Record<string, { value: number; unit: string }> = {};
  for (const [name, raw] of Object.entries(options.overrides)) {
    const quantity = parseQuantity(name, raw);
    userValues[name] = { value: quantity.value, unit: quantity.unit };
    provenance.push({
      name,
      value: quantity.value,
      unit: quantity.unit,
      origin: 'user',
      unitAssumed: !quantity.unitDeclared,
    });
  }

  let enzymeConcMM: number | undefined;
  if (options.enzymeConc) {
    const parsed = parseQuantity('e0', options.enzymeConc);
    // The Python bridge takes [E]0 in mM (ADR 0013). Converted rather than
    // assumed, so `--enzyme-conc 1uM` is not read as 1 mM.
    enzymeConcMM = convertConcentration(parsed.value, parsed.unit, 'mM');
    provenance.push({
      name: 'e0',
      value: parsed.value,
      unit: parsed.unit,
      origin: 'user',
      unitAssumed: !parsed.unitDeclared,
    });
  }

  // ---- resolve what is missing ----------------------------------------
  const needed: Array<'km' | 'vmax'> = ['km', 'vmax'];

  for (const name of needed) {
    if (userValues[name]) continue;

    try {
      if (name === 'km') {
        const result = await resolveKinetic({
          enzymeName: options.enzyme,
          ecNumber: options.ec,
          substrate: options.substrate,
          organism: options.organism,
          quantity: 'km',
        });
        if (!result.found) {
          unresolved.push('km');
          continue;
        }
        userValues['km'] = { value: result.value, unit: result.unit };
        provenance.push({
          name: 'km',
          value: result.value,
          unit: result.unit,
          origin: result.source,
          citation: result.citation
            ? `${result.citation.source} ref ${result.citation.reference_id ?? '?'}`
            : undefined,
          organism: result.organism ?? undefined,
          crossSpecies: result.crossSpecies,
        });
      } else {
        // Vmax is not a BRENDA table. It is kcat x [E]0, and [E]0 is a
        // caller input BRENDA does not supply per row (ADR 0012/0013).
        // Without it, a resolved kcat is a citable number that cannot
        // reach a simulation -- said out loud rather than defaulted.
        if (enzymeConcMM === undefined) {
          unresolved.push(
            'vmax (needs --enzyme-conc: Vmax = kcat x [E]0, and BRENDA does ' +
              'not report [E]0)',
          );
          continue;
        }
        const result = await resolveKinetic({
          enzymeName: options.enzyme,
          ecNumber: options.ec,
          substrate: options.substrate,
          organism: options.organism,
          quantity: 'kcat',
          enzymeConc: enzymeConcMM,
        });
        if (!result.found || result.bridgedVmax === undefined) {
          unresolved.push('vmax (no kcat found to bridge)');
          continue;
        }
        userValues['vmax'] = { value: result.bridgedVmax, unit: 'mM/s' };
        provenance.push({
          name: 'vmax',
          value: result.bridgedVmax,
          unit: 'mM/s',
          origin: `${result.source} → kcat x [E]0`,
          citation: result.citation
            ? `${result.citation.source} ref ${result.citation.reference_id ?? '?'}`
            : undefined,
          organism: result.organism ?? undefined,
          crossSpecies: result.crossSpecies,
        });
      }
    } catch (err) {
      if (err instanceof ResolverUnavailableError) {
        if (options.json) {
          process.stdout.write(
            JSON.stringify(
              { ok: false, status: 'unavailable', parameter: name, reason: err.message },
              null,
              2,
            ) + '\n',
          );
        } else {
          process.stderr.write(
            `${c(RED, '✗')} Could not look up ${name}: ${err.message}\n` +
              `${c(DIM, '  Nothing was learned about this system. This is not the same as')}\n` +
              `${c(DIM, '  the literature having no value.')}\n`,
          );
        }
        return 1;
      }
      throw err;
    }
  }

  // s0 has no literature source: it is an experimental condition the user
  // chooses, not a property of the enzyme.
  if (!userValues['s0']) {
    unresolved.push('s0 (an experimental condition — supply it, e.g. --s0 10mM)');
  }

  if (unresolved.length > 0) {
    if (options.json) {
      process.stdout.write(
        JSON.stringify({ ok: false, status: 'unresolved', unresolved, provenance }, null, 2) + '\n',
      );
    } else {
      printProvenance(provenance);
      process.stdout.write(
        `\n${c(RED, '✗')} ${c(BOLD, 'Cannot run.')} These are unresolved:\n`,
      );
      for (const item of unresolved) {
        process.stdout.write(`    ${item}\n`);
      }
      process.stdout.write(
        `\n${c(DIM, 'No value has been invented to fill the gap. A simulation on a')}\n` +
          `${c(DIM, 'defaulted parameter produces a result that looks measured and is not.')}\n\n`,
      );
    }
    return 2;
  }

  // ---- run it ----------------------------------------------------------
  const pipeline = new ScientificPipeline();
  const numeric: Record<string, number> = {};
  for (const [name, v] of Object.entries(userValues)) {
    numeric[name] = v.value;
  }

  // The pipeline resolves through the SAME resolver used above, and
  // returns provenance for everything it touched. Passing `system` lets it
  // attach citations to what it resolves; passing the values we already
  // resolved as `parameters` keeps user overrides authoritative.
  // Hand the pipeline the provenance for everything resolved above, so a
  // BRENDA-sourced Km arrives as sourced rather than as a hand-typed number.
  const providedProvenance: Record<
    string,
    { source: string; citations?: string[]; unit?: string }
  > = {};
  for (const row of provenance) {
    providedProvenance[row.name] = {
      source: row.origin,
      unit: row.unit,
      ...(row.citation ? { citations: [row.citation] } : {}),
    };
  }

  const response = await pipeline.execute({
    query: `${options.enzyme ?? options.ec} / ${options.substrate}`,
    parameters: numeric,
    providedProvenance,
    system: {
      enzymeName: options.enzyme,
      ecNumber: options.ec,
      substrate: options.substrate,
      organism: options.organism,
    },
    ...(options.enzymeConc
      ? {
          enzymeConcentration: {
            value: parseQuantity('e0', options.enzymeConc).value,
            unit: parseQuantity('e0', options.enzymeConc).unit,
          },
        }
      : {}),
  });

  // The pipeline returns a fully-shaped response even when validation
  // STOPS the run -- empty trajectory, finalValue 0, blank reproducibility
  // key. Printing that as a result rendered "initial undefined, points 0"
  // and exited 0, which is a success report for a simulation that never
  // executed. Checked before anything is presented.
  if (!response.validated) {
    if (options.json) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            status: 'validation_failed',
            errors: response.validationErrors,
            provenance,
          },
          null,
          2,
        ) + '\n',
      );
    } else {
      printProvenance(provenance);
      process.stdout.write(
        `\n${c(RED, '✗')} ${c(BOLD, 'Validation stopped the run.')} No simulation was executed.\n`,
      );
      for (const message of response.validationErrors) {
        process.stdout.write(`    ${message}\n`);
      }
      process.stdout.write('\n');
    }
    return 2;
  }

  if (options.json) {
    process.stdout.write(
      JSON.stringify({ ok: true, status: 'ran', provenance, response }, null, 2) + '\n',
    );
    return 0;
  }

  // Merge in what the pipeline reported. Anything it resolved carries the
  // citations that our own pass could not (the CLI hands it plain numbers,
  // so provenance has to come back rather than go in).
  for (const [name, resolved] of Object.entries(response.parameterProvenance ?? {})) {
    const existing = provenance.find((row) => row.name === name);
    if (existing && !existing.citation && resolved.citations?.length) {
      existing.citation = resolved.citations.join(', ');
    }
  }

  printProvenance(provenance);

  const substrateUnit = userValues['s0']?.unit ?? '';
  const first = response.results.trajectory[0];
  process.stdout.write(`\n${c(BOLD, 'Result')}\n`);
  process.stdout.write(
    `  ${c(DIM, 'initial   ')} ${first?.value.toFixed(4)} ${substrateUnit}\n`,
  );
  process.stdout.write(
    `  ${c(DIM, 'final     ')} ${response.results.finalValue.toFixed(4)} ${substrateUnit}\n`,
  );
  process.stdout.write(
    `  ${c(DIM, 'consumed  ')} ${((first?.value ?? 0) - response.results.finalValue).toFixed(4)} ${substrateUnit}\n`,
  );
  process.stdout.write(`  ${c(DIM, 'points    ')} ${response.results.trajectory.length}\n`);
  process.stdout.write(`\n  ${c(DIM, 'job       ')} ${response.jobId}\n`);
  process.stdout.write(
    `  ${c(DIM, 'repro key ')} ${response.reproducibilityKey.slice(0, 32)}…\n\n`,
  );

  return 0;
}

/**
 * The provenance table.
 *
 * Units are printed from each parameter's own `unit` field, not from a
 * hardcoded "mM" -- the previous output appended "mM" to every number
 * regardless of what the parameter actually was, so a Vmax in mM/s and a
 * Km in µM both rendered as millimolar.
 */
function printProvenance(rows: ParameterProvenance[]): void {
  if (rows.length === 0) return;

  process.stdout.write(`\n${c(BOLD, 'Parameters and where they came from')}\n`);

  const nameWidth = Math.max(...rows.map((r) => r.name.length), 4);
  const valueStrings = rows.map((r) => `${r.value} ${r.unit}`);
  const valueWidth = Math.max(...valueStrings.map((v) => v.length), 5);

  rows.forEach((row, index) => {
    const value = valueStrings[index]!.padEnd(valueWidth);
    let line = `  ${row.name.padEnd(nameWidth)}  ${value}  ${c(DIM, row.origin)}`;
    if (row.citation) line += c(DIM, `  ${row.citation}`);
    process.stdout.write(line + '\n');

    if (row.crossSpecies) {
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(YELLOW, '⚠ measured in ' + (row.organism ?? 'another organism') + ', not the organism requested')}\n`,
      );
    }
    if (row.unitAssumed) {
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(YELLOW, `⚠ unit not given; ${row.unit} assumed`)}\n`,
      );
    }
  });

  const sourced = rows.filter((r) => r.citation).length;
  process.stdout.write(
    `\n  ${c(DIM, `${sourced} of ${rows.length} parameter(s) carry a literature citation.`)}\n`,
  );
  if (sourced < rows.length) {
    process.stdout.write(
      `  ${c(DIM, 'The rest are user inputs or experimental conditions, which is fine —')}\n` +
        `  ${c(DIM, 'but they are not literature-backed and must not be reported as such.')}\n`,
    );
  }
}
