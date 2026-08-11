/**
 * Inhibition models, resolved from literature and run by the real engine.
 *
 * WHY THIS IS NOT A FIFTH SIMULATOR
 *
 * `src/engine/kinetic-models.ts` contains rate equations for competitive,
 * non-competitive and product inhibition. Wiring those would have made a
 * fifth implementation of enzyme kinetics in this repository, and every
 * serious defect this project has found lived in a duplicate implementation
 * nobody was watching.
 *
 * `src/engine/sbml-builder.ts` takes the other route: it emits SBML, and
 * the Python engine has an `sbml` escape-hatch domain that runs it with the
 * same solver as every first-class domain. So the model definition lives
 * here in TypeScript, and the *integration* stays where it has always been.
 * One simulator, more models.
 *
 * This matters beyond tidiness. The engine has `mm` and
 * `mm_competitive_inhibition` as first-class domains, but NOT
 * non-competitive or product inhibition — so before this, a student
 * studying non-competitive inhibition had no way to simulate it here at
 * all.
 *
 * WHAT MAKES IT WORTH USING
 *
 * Ki is a BRENDA table, exactly like Km. So an inhibition model can be
 * resolved from literature end to end: Km from the KM Values table, Ki from
 * the Ki Values table, each with its own citation, each resolved by its own
 * call so a cross-species Ki can never borrow a verified Km's provenance
 * (ADR 0008).
 */

import {
  buildCompetitiveInhibition,
  buildMichaelisMenten,
  buildNonCompetitiveInhibition,
  buildProductInhibition,
} from '../engine/sbml-builder';
import { runTellurium } from '../engine/telluriumBridge';

/**
 * BRENDA's Ki table records an inhibition constant for a NAMED inhibitor,
 * which is not necessarily the reaction's own product. Product inhibition
 * needs Kp specifically. Using a resolved Ki as Kp is therefore an
 * assumption, and the CLI states it rather than burying it -- the whole
 * point of this tool is that a number carries where it came from.
 */
export const PRODUCT_INHIBITION_CAVEAT =
  'Product inhibition uses Kp, the inhibition constant of the reaction\'s ' +
  'own product. The resolved value comes from BRENDA\'s Ki table, which ' +
  'records a constant for a named inhibitor — confirm that inhibitor IS ' +
  'the product of this reaction before relying on the result.';

export type InhibitionModel =
  | 'mm'
  | 'competitive'
  | 'noncompetitive'
  | 'product';

export const INHIBITION_MODELS: Record<
  InhibitionModel,
  { description: string; requires: string[]; engineDomain: string }
> = {
  mm: {
    description: 'Michaelis-Menten, no inhibitor',
    requires: ['km', 'vmax', 's0'],
    // A first-class engine domain: use it directly rather than via SBML,
    // so the well-trodden path stays the default.
    engineDomain: 'mm',
  },
  competitive: {
    description:
      'Competitive inhibition — inhibitor competes for the active site, ' +
      'raising apparent Km without changing Vmax',
    requires: ['km', 'vmax', 'ki', 's0', 'i0'],
    engineDomain: 'mm_competitive_inhibition',
  },
  noncompetitive: {
    description:
      'Non-competitive inhibition — inhibitor binds elsewhere, lowering ' +
      'apparent Vmax without changing Km',
    requires: ['km', 'vmax', 'ki', 's0', 'i0'],
    // No first-class domain exists. Runs as SBML through the same engine.
    engineDomain: 'sbml',
  },
  product: {
    description:
      'Product inhibition — accumulating product inhibits the enzyme, so ' +
      'the rate falls as the reaction proceeds',
    requires: ['km', 'vmax', 'ki', 's0'],
    engineDomain: 'sbml',
  },
};

export interface InhibitionRunParameters {
  km: number;
  vmax: number;
  s0: number;
  ki?: number;
  i0?: number;
  end: number;
  points: number;
}

/**
 * Run an inhibition model through the Python engine.
 *
 * For models with a first-class domain, dispatches to it. For the rest,
 * builds SBML and uses the engine's `sbml` domain — the same solver either
 * way.
 */
export async function runInhibitionModel(
  model: InhibitionModel,
  parameters: InhibitionRunParameters,
): Promise<{
  trajectory: Array<Record<string, number>>;
  domain: string;
  viaSbml: boolean;
}> {
  const spec = INHIBITION_MODELS[model];

  const asRecord = parameters as unknown as Record<string, unknown>;
  const missing = spec.requires.filter((name) => {
    const value = asRecord[name];
    return value === undefined || value === null;
  });
  if (missing.length > 0) {
    throw new Error(
      `${model} inhibition needs ${missing.join(', ')}. Terrium does not ` +
        'default a missing parameter -- a run on an invented value produces ' +
        'a result that looks measured and is not.',
    );
  }

  if (spec.engineDomain !== 'sbml') {
    const result = await runTellurium(
      spec.engineDomain as never,
      {
        km: parameters.km,
        vmax: parameters.vmax,
        s0: parameters.s0,
        ...(parameters.ki !== undefined ? { ki: parameters.ki } : {}),
        ...(parameters.i0 !== undefined ? { i0: parameters.i0 } : {}),
        end: parameters.end,
        points: parameters.points,
      },
      { required: spec.requires.filter((r) => r !== 'i0') },
    );
    return { trajectory: result.trajectory, domain: spec.engineDomain, viaSbml: false };
  }

  const built =
    model === 'noncompetitive'
      ? buildNonCompetitiveInhibition({
          km: parameters.km,
          vmax: parameters.vmax,
          ki: parameters.ki!,
          s0: parameters.s0,
          i0: parameters.i0!,
        })
      : buildProductInhibition({
          km: parameters.km,
          vmax: parameters.vmax,
          // Kp, the PRODUCT's inhibition constant. Passed from the resolved
          // Ki because for product inhibition the inhibitor is the product
          // -- but see the caveat in PRODUCT_INHIBITION_CAVEAT: BRENDA's Ki
          // table names an inhibitor, and it is not necessarily this
          // reaction's product. That is a modelling assumption the user
          // must be told about, not one to make silently.
          kp: parameters.ki!,
          s0: parameters.s0,
        });

  const result = await runTellurium(
    'sbml',
    {
      sbml_string: built.xml,
      end: parameters.end,
      points: parameters.points,
    },
    // The runner echoes only {start, end, points} for this domain; it does
    // not return the SBML document it was given. That is sensible, not a
    // dropped parameter.
    { notEchoed: ['sbml_string'] },
  );

  return { trajectory: result.trajectory, domain: 'sbml', viaSbml: true };
}

/**
 * Which model do these parameters imply?
 *
 * Replaces the "model advisor" role that `kinetic-models.ts` could not
 * fill without becoming a second simulator. Supplying a Ki and then running
 * plain `mm` silently discards the inhibitor — the run succeeds, the
 * numbers look fine, and the inhibition the user was studying is simply
 * absent from the result.
 */
export function suggestModel(supplied: {
  ki?: unknown;
  i0?: unknown;
}): { model: InhibitionModel; why: string } | null {
  const hasKi = supplied.ki !== undefined && supplied.ki !== null;
  const hasI0 = supplied.i0 !== undefined && supplied.i0 !== null;

  if (hasKi && hasI0) {
    return {
      model: 'competitive',
      why:
        'you supplied both a Ki and an inhibitor concentration, so plain ' +
        'Michaelis-Menten would ignore the inhibitor entirely',
    };
  }
  if (hasKi && !hasI0) {
    return {
      model: 'product',
      why:
        'you supplied a Ki but no inhibitor concentration, which is the ' +
        'shape of product inhibition (the inhibitor is generated by the ' +
        'reaction itself)',
    };
  }
  return null;
}
