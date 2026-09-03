/**
 * Resolving a caller's own model against the literature.
 *
 * `modelAnnotations.ts` reads what the caller DECLARED each parameter to
 * be. This module goes and looks it up, and reports what it found beside
 * what the caller wrote. See that file's header for why the declaration
 * is mandatory and never inferred.
 *
 * THE UNIT PROBLEM IS THE WHOLE PROBLEM
 *
 * BRENDA normalises Km and Ki to mM. A model written in uM whose Km is
 * compared against a literature mM value disagrees by 1000x for a reason
 * that has nothing to do with the science -- and the comparison would
 * look like a finding. Worse in `resolve` mode: writing a millimolar
 * number into a micromolar model is a silent 1000x error in a simulation
 * that runs perfectly and produces a plausible curve.
 *
 * So:
 *   - `check` without a unit reports both values and explicitly does NOT
 *     compare them. The citation is still worth having on its own.
 *   - `resolve` without a unit REFUSES. There is no safe number to write
 *     when you do not know what unit to write it in.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 *
 * It does not decide whether your value is right. It reports yours,
 * theirs, the fold difference, the organism, and the assay conditions,
 * and stops. "Km differs 3x from BRENDA" is a fact; "your Km is wrong" is
 * a judgement that depends on your buffer, your temperature and your
 * construct, none of which this code knows. Presenting the second as the
 * first is the failure mode this project exists to avoid, so the audit
 * surfaces the numbers and leaves the science to the scientist.
 */
import { matchEnzyme } from "./enzymes";
import type { CitationLocator } from "./citeVerify";
import { locatableCitation } from "./queryResolver";
import { resolveKineticValue } from "./scienceAgent";
import { CONCENTRATION_TO_MM } from "./statedQuantities";
import {
  parseModelAnnotations,
  type AnnotationProblem,
  type ModelAnnotation,
} from "./modelAnnotations";

/** The unit each quantity resolves in. Set by the sources, not by us. */
const LITERATURE_UNIT: Record<ModelAnnotation["quantity"], string> = {
  // BRENDA's client normalises both to mM (Tests/brenda_client.py).
  km: "mM",
  ki: "mM",
  // A turnover number is a first-order rate constant.
  kcat: "1/s",
};

/** Spellings of "per second" a caller might reasonably write. */
const PER_SECOND = new Set(["1/s", "s^-1", "s-1", "/s", "per second", "sec^-1"]);

export interface GroundedParameter {
  parameter: string;
  quantity: ModelAnnotation["quantity"];
  mode: ModelAnnotation["mode"];
  line: number;
  /** What the caller wrote, in the caller's unit. */
  yourValue?: number;
  yourUnit?: string;
  /** What the literature says, in LITERATURE_UNIT[quantity]. */
  literatureValue?: number;
  literatureUnit?: string;
  citation?: string;
  /**
   * Machine-readable locators for the citation.
   *
   * Not decoration: `validateParameterProvenance` requires them on any
   * origin "resolved" entry, and a `resolve` parameter becomes exactly
   * that. Omitting them would turn a successful grounding into an
   * internal provenance error -- the ADR 0021 failure shape.
   */
  citationLocators?: CitationLocator[];
  organism?: string;
  /** True when the value came from a different organism than requested. */
  crossSpecies?: boolean;
  status: "grounded" | "not_found" | "no_locator";
  /**
   * The literature value expressed in the caller's own unit, present
   * whenever the units could be reconciled.
   *
   * `literatureInYourUnit` and `foldDifference` are two different facts
   * and were once one field, which was a bug: `resolve` mode has no
   * caller value to compare against, so anything gated on a comparison
   * was undefined exactly when substitution needed it. The converted
   * value is what gets written into the model; the fold difference is
   * only meaningful when there is a caller value to differ from, and
   * carries no verdict either way -- see the header.
   */
  comparison?: {
    literatureInYourUnit: number;
    foldDifference?: number;
  };
  /** Why no comparison was made, when there is a reason worth stating. */
  comparisonSkipped?: string;
  note: string;
}

export interface ModelGroundingReport {
  /** Annotation mistakes. Non-empty means the run should not proceed. */
  problems: AnnotationProblem[];
  entries: GroundedParameter[];
  /**
   * `resolve` parameters that could not be grounded. Non-empty means the
   * run must refuse: a `resolve` annotation is a request for a
   * literature value, and there is no fallback that would not be the
   * fabrication this project refuses.
   */
  blocking: string[];
  /**
   * The caller's source with every `resolve` placeholder filled in, ready
   * to simulate. Undefined when nothing needed filling.
   */
  groundedSource?: string;
}

/** Convert a literature value into the unit the caller's model is in. */
function intoCallerUnit(
  quantity: ModelAnnotation["quantity"],
  literatureValue: number,
  unit: string | undefined,
): { value: number } | { skipped: string } {
  if (unit === undefined) {
    return {
      skipped:
        `no unit was declared, so this cannot be compared with the ` +
        `literature value (${LITERATURE_UNIT[quantity]}). Add ` +
        `unit="${LITERATURE_UNIT[quantity]}" to the annotation.`,
    };
  }
  const normalised = unit.trim().toLowerCase();

  if (quantity === "kcat") {
    if (!PER_SECOND.has(normalised)) {
      return {
        skipped:
          `kcat is a first-order rate constant and the literature value ` +
          `is in 1/s; '${unit}' is not a spelling of that, so no ` +
          "comparison was made.",
      };
    }
    return { value: literatureValue };
  }

  // km/ki: literature is mM, so divide by "how many mM is one of yours".
  const mmPerCallerUnit = CONCENTRATION_TO_MM[normalised];
  if (mmPerCallerUnit === undefined) {
    return {
      skipped:
        `'${unit}' is not a concentration unit Terrium knows ` +
        `(${Object.keys(CONCENTRATION_TO_MM).join(", ")}), so no ` +
        "comparison was made.",
    };
  }
  return { value: literatureValue / mmPerCallerUnit };
}

/** Symmetric, verdict-free: how far apart two positive numbers are. */
function foldDifference(a: number, b: number): number | undefined {
  if (!(a > 0) || !(b > 0)) return undefined;
  return a > b ? a / b : b / a;
}

/**
 * Look up one declared parameter and describe what was found.
 *
 * `organism` is required by the science agent. When the caller did not
 * state one, the enzyme table's own organism is used -- the same source
 * `extractEntitiesFromQuery` already uses on the query path, rather than
 * a new assumption invented here. When the enzyme is not in that table
 * and no organism was given, this refuses rather than picking one:
 * kinetic constants are species-specific, and a silently assumed species
 * is a wrong answer wearing a citation.
 */
async function groundOne(
  annotation: ModelAnnotation,
  options: { allowCrossSpecies: boolean; allowVariants: boolean },
): Promise<GroundedParameter> {
  const base = {
    parameter: annotation.parameter,
    quantity: annotation.quantity,
    mode: annotation.mode,
    line: annotation.line,
    ...(annotation.value !== undefined ? { yourValue: annotation.value } : {}),
    ...(annotation.unit !== undefined ? { yourUnit: annotation.unit } : {}),
  };

  const organism =
    annotation.organism ??
    (annotation.enzymeName ? matchEnzyme(annotation.enzymeName)?.organism : undefined);
  if (organism === undefined) {
    return {
      ...base,
      status: "not_found",
      note:
        "no organism was declared and this enzyme is not in Terrium's " +
        "table, so there is no species to look up. Kinetic constants are " +
        'species-specific; add organism="..." to the annotation.',
    };
  }

  const result = await resolveKineticValue({
    organism,
    quantity: annotation.quantity,
    ...(annotation.enzymeName ? { enzymeName: annotation.enzymeName } : {}),
    ...(annotation.ecNumber ? { ecNumber: annotation.ecNumber } : {}),
    ...(annotation.substrate ? { substrate: annotation.substrate } : {}),
    allowCrossSpecies: options.allowCrossSpecies,
    allowVariants: options.allowVariants,
  });

  const value = result[annotation.quantity];
  if (!result.found || typeof value !== "number") {
    return {
      ...base,
      status: "not_found",
      note:
        `BRENDA, KEGG and PubMed hold no ${annotation.quantity.toUpperCase()} ` +
        `for ${annotation.enzymeName ?? annotation.ecNumber}` +
        `${annotation.substrate ? ` with ${annotation.substrate}` : ""} ` +
        `in ${organism}.`,
    };
  }

  const located = locatableCitation(result.citation);
  if (located === undefined) {
    return {
      ...base,
      status: "no_locator",
      literatureValue: value,
      literatureUnit: LITERATURE_UNIT[annotation.quantity],
      note:
        `A value of ${value} ${LITERATURE_UNIT[annotation.quantity]} was ` +
        "found, but its citation carries no reference id or URL — nothing " +
        "a reader could follow to check it. An uncheckable citation is not " +
        "a citation, so it was not used.",
    };
  }

  const grounded: GroundedParameter = {
    ...base,
    status: "grounded",
    literatureValue: value,
    literatureUnit: LITERATURE_UNIT[annotation.quantity],
    citation: located.display,
    citationLocators: located.locators,
    organism: result.organism ?? organism,
    ...(result.crossSpecies === true ? { crossSpecies: true } : {}),
    note: `${annotation.quantity.toUpperCase()} = ${value} ${
      LITERATURE_UNIT[annotation.quantity]
    } (${result.organism ?? organism}), ${located.display}.`,
  };

  const converted = intoCallerUnit(
    annotation.quantity,
    value,
    annotation.unit,
  );
  if ("skipped" in converted) {
    grounded.comparisonSkipped = converted.skipped;
    return grounded;
  }
  const fold =
    annotation.value === undefined
      ? undefined
      : foldDifference(annotation.value, converted.value);
  grounded.comparison = {
    literatureInYourUnit: converted.value,
    ...(fold !== undefined ? { foldDifference: fold } : {}),
  };
  return grounded;
}

/**
 * Write a grounded value into the caller's source, on its own line.
 *
 * Anchored to the parameter name AND the recorded line, so a symbol that
 * also appears in a rate law elsewhere cannot be rewritten by accident.
 */
function substitute(
  lines: string[],
  entry: GroundedParameter,
  value: number,
): boolean {
  const index = entry.line - 1;
  const line = lines[index];
  if (line === undefined) return false;
  const pattern = new RegExp(
    `^(\\s*${entry.parameter}\\s*=\\s*)(?:\\?|-?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?)(\\s*;?)`,
  );
  if (!pattern.test(line)) return false;
  lines[index] = line.replace(pattern, `$1${value}$2`);
  return true;
}

/**
 * Ground every annotated parameter in an Antimony source.
 *
 * Antimony only. SBML carries no comments in this sense; its annotation
 * story is `<annotation>` RDF, a different and much larger job. The
 * caller reports that limit rather than returning an empty report, which
 * would read as "nothing to check".
 */
export async function groundAnnotatedModel(
  source: string,
  options: { allowCrossSpecies?: boolean; allowVariants?: boolean } = {},
): Promise<ModelGroundingReport> {
  const { annotations, problems } = parseModelAnnotations(source);
  if (problems.length > 0) {
    // Do not spend network calls resolving a model whose declarations are
    // already known to be wrong; the caller has to fix them first.
    return { problems, entries: [], blocking: [] };
  }
  if (annotations.length === 0) {
    return { problems: [], entries: [], blocking: [] };
  }

  const opts = {
    allowCrossSpecies: options.allowCrossSpecies === true,
    allowVariants: options.allowVariants === true,
  };
  const entries = await Promise.all(
    annotations.map((annotation) => groundOne(annotation, opts)),
  );

  const lines = source.split(/\r?\n/);
  const blocking: string[] = [];
  let substituted = false;

  for (const entry of entries) {
    if (entry.mode !== "resolve") continue;

    if (entry.status !== "grounded") {
      blocking.push(
        `${entry.parameter} (line ${entry.line}): ${entry.note}`,
      );
      continue;
    }
    // A grounded value still cannot be written without knowing which unit
    // to write it in. Refusing here is the difference between a citation
    // and a silent 1000x error.
    if (entry.comparison === undefined) {
      blocking.push(
        `${entry.parameter} (line ${entry.line}): ${
          entry.comparisonSkipped ??
          "the literature value could not be expressed in this model's unit."
        }`,
      );
      continue;
    }
    if (!substitute(lines, entry, entry.comparison.literatureInYourUnit)) {
      blocking.push(
        `${entry.parameter} (line ${entry.line}): Terrium resolved a value ` +
          "but could not write it into the model source at that line.",
      );
      continue;
    }
    entry.yourValue = entry.comparison.literatureInYourUnit;
    substituted = true;
  }

  return {
    problems: [],
    entries,
    blocking,
    ...(substituted && blocking.length === 0
      ? { groundedSource: lines.join("\n") }
      : {}),
  };
}
