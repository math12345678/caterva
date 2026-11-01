/**
 * The conditions a simulation actually runs at.
 *
 * ## The question this module answers
 *
 * "What temperature is this simulation at?" has a counter-intuitive answer,
 * and getting it wrong is what this file exists to stop.
 *
 * The Michaelis-Menten ODE takes no temperature:
 *
 *     dS/dt = -Vmax * S / (Km + S)
 *
 * There is nowhere for a temperature to go. `ScientificPipeline.runSimulation`
 * discards the conditions object for exactly this reason, and that is correct:
 * a Km's temperature dependence is already inside the measured Km. Km and Vmax
 * ARE the temperature, encoded.
 *
 * So the simulation does not run at a temperature the student picks. It runs
 * at the temperature the papers were measured at — whatever that was, whether
 * or not anyone knows it.
 *
 * ## What was there before
 *
 * Nine call sites, every entry point in the product, passing the identical
 * literal:
 *
 *     conditions: { temperature: 37, pH: 7.4 }
 *
 * Three consequences, in increasing order of seriousness.
 *
 * It is a hardcoded value with no source, which this project forbids.
 *
 * It is a *human body* condition, so a student modelling a thermophile,
 * a plant enzyme or a lysosomal protease got 37 C and pH 7.4 without being
 * asked — the same silent species assumption ADR 0024 exists to prevent,
 * wearing different clothes.
 *
 * And the range checks in `AssumptionValidator` — "outside 4-45 C", "outside
 * pH 5-9" — could never fire. 37 and 7.4 are the dead centre of both ranges.
 * Those two warnings shipped in the product, were covered by unit tests that
 * called the validator directly with values the product never sends, and were
 * unreachable from every path a user could take. **A check that cannot fail
 * is worse than no check, because it is trusted.**
 *
 * The warning text is the sharpest part: it says *"confirm the kinetic
 * constants were measured at this temperature."* That confirmation is the one
 * Lisa Jeske (BRENDA/DSMZ) asked for. It was unreachable because the
 * temperature was a fiction.
 *
 * ## What this module does instead
 *
 * Reads the conditions off the parameters' own provenance, and reports
 * agreement as a first-class three-state verdict:
 *
 * - `agreed`       — every parameter that reported a value reported the same
 * - `conflicting`  — they reported different ones
 * - `not_reported` — none of them reported any
 *
 * `conflicting` is Jeske's case, in her words:
 *
 * > "pH value, temperature, cofactors, and buffers play a huge role... If you
 * > simply mix these together, the simulation will end up calculating with
 * > 'fantasy numbers'."
 *
 * A Km measured at 25 C and a Vmax measured at 37 C do not describe one
 * enzyme under one condition. They describe two experiments. The mixture has
 * no temperature, and this module returns none — it does not average them
 * (an average of two assay temperatures is not an assay temperature), and it
 * does not pick one (picking is choosing which paper to believe, silently).
 *
 * ## Three-state, not two
 *
 * `not_reported` is separated from `conflicting` because they are different
 * facts about the world. `not_reported` means BRENDA's curators did not write
 * it down — a gap in the record. `conflicting` means the record is complete
 * and the parameters disagree — a defect in the model being built. Collapsing
 * them into "no temperature available" would let a real incoherence hide
 * inside a common absence.
 *
 * The same distinction ADR 0012/0013 draw between a measurement and a choice,
 * and ADR 0024 draws between "we found nothing" and "we withheld something".
 * This project keeps rediscovering it in new places.
 */

/** What the provenance said about one condition, across all parameters. */
export type ConditionAgreement = 'agreed' | 'conflicting' | 'not_reported';

export interface ConditionVerdict<T> {
  status: ConditionAgreement;
  /**
   * The value, present ONLY when `status === "agreed"`.
   *
   * Deliberately absent under `conflicting`. The tempting alternative — carry
   * the first value and set a flag — makes the incoherent case structurally
   * identical to the coherent one, so every consumer that forgets to read the
   * flag silently simulates at a temperature one of its own parameters
   * contradicts.
   */
  value?: T;
  /**
   * Every distinct value found, in the order encountered, with the parameter
   * that reported it. Populated for `conflicting` so a refusal can name what
   * it refused; empty otherwise.
   */
  reported: Array<{ parameter: string; value: T }>;
  /** Parameters that reported nothing for this condition. */
  silent: string[];
}

export interface RunConditions {
  temperatureC: ConditionVerdict<number>;
  ph: ConditionVerdict<number>;
}

/** The minimum a parameter must look like to be read here. */
export interface ParameterWithProvenance {
  assayConditions?: {
    ph?: number | null;
    temperatureC?: number | null;
  } | null;
}

/**
 * Equality for assay conditions.
 *
 * Exact, deliberately. There is no tolerance here and adding one would be a
 * threshold with no source — the thing ADR 0026 refused to invent for the
 * same reason. 25 C and 25.1 C are reported as conflicting, which is
 * pedantic and honest; a 0.5 C tolerance would be neither sourced nor
 * defensible, and the first person to ask "why 0.5?" would get no answer.
 *
 * If a tolerance is ever wanted it must arrive with a citation, and it must
 * be the caller's, not this module's.
 */
function sameValue(a: number, b: number): boolean {
  return a === b;
}

function assess<T extends number>(
  parameters: Record<string, ParameterWithProvenance>,
  read: (p: ParameterWithProvenance) => T | null | undefined,
): ConditionVerdict<T> {
  const reported: Array<{ parameter: string; value: T }> = [];
  const silent: string[] = [];

  for (const [name, parameter] of Object.entries(parameters)) {
    const value = parameter?.assayConditions ? read(parameter) : undefined;
    // `null` is BRENDA's "the curator did not record this" and `undefined` is
    // "this parameter carries no provenance at all". Both are silence, and
    // neither is zero — `if (!value)` would have swallowed a genuine 0 C.
    if (value === null || value === undefined || !Number.isFinite(value)) {
      silent.push(name);
      continue;
    }
    reported.push({ parameter: name, value });
  }

  if (reported.length === 0) {
    return { status: 'not_reported', reported: [], silent };
  }

  const first = reported[0].value;
  const allAgree = reported.every(r => sameValue(r.value, first));

  if (!allAgree) {
    return { status: 'conflicting', reported, silent };
  }

  return { status: 'agreed', value: first, reported, silent };
}

/**
 * Derive the conditions a run is at from the provenance of its parameters.
 *
 * Note what is NOT an input: anything the caller chose. That is the point.
 * An earlier draft of this signature took a `fallback` argument for when the
 * provenance was silent, which is the hardcoded 37 with an extra step.
 */
export function deriveRunConditions(
  parameters: Record<string, ParameterWithProvenance>,
): RunConditions {
  return {
    temperatureC: assess(parameters, p => p.assayConditions?.temperatureC),
    ph: assess(parameters, p => p.assayConditions?.ph),
  };
}

/**
 * Human-readable warnings for conditions that disagree.
 *
 * Returns `[]` for `agreed` and for `not_reported`. Silence about a silent
 * record is right: "the papers did not report a temperature" is already
 * reported by the validator as `notEvaluated`, and saying it twice in two
 * voices would train a reader to skim both.
 */
export function describeConflicts(conditions: RunConditions): string[] {
  const messages: string[] = [];

  const describe = (
    verdict: ConditionVerdict<number>,
    label: string,
    unit: string,
  ): void => {
    if (verdict.status !== 'conflicting') return;
    const detail = verdict.reported
      .map(r => `${r.parameter} at ${r.value}${unit}`)
      .join(', ');
    messages.push(
      `Assay ${label} conflict: ${detail}. These parameters were measured ` +
      `under different conditions, so the model mixes experiments rather ` +
      `than describing one. No ${label} is assumed for this run and none is ` +
      `averaged -- the mean of two assay ${label}s is not an assay ${label}.`,
    );
  };

  describe(conditions.temperatureC, 'temperature', ' C');
  describe(conditions.ph, 'pH', '');

  return messages;
}
