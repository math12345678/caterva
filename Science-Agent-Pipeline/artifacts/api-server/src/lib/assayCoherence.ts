/**
 * Cross-parameter assay coherence.
 *
 * THE GAP THIS FILLS
 * ------------------
 * `reliabilityScore.ts` grades each parameter on its own. That is necessary
 * and it is not sufficient, because the failure Lisa Jeske (BRENDA curation
 * team, Leibniz Institute DSMZ) warned about is invisible to any per-value
 * check:
 *
 *   "Reaction conditions: pH value, temperature, cofactors, and buffers play
 *    a huge role in the reactions. The values in BRENDA come from thousands
 *    of different papers, each with different laboratory conditions. If you
 *    simply mix these together, the simulation will end up calculating with
 *    'fantasy numbers'."
 *
 * A competitive-inhibition model needs a Km AND a Ki. Terrium resolves them
 * with two independent lookups — separate runner calls, separate sources,
 * separate citations — precisely so that a cross-species Ki can never borrow
 * a verified Km's provenance (ADR 0008). That independence is correct, and
 * it creates this problem: the Km may come from a 1974 paper at pH 7.4 and
 * 25 °C and the Ki from a 2003 paper at pH 6.0 and 37 °C.
 *
 * Both parameters can score perfectly on every individual axis. Both
 * citations are real. Both assays are fully described. And the model built
 * from them describes no experiment anyone ever ran, because those two
 * numbers were never true of the same enzyme at the same time.
 *
 * Per-parameter scoring cannot catch this by construction: the defect is not
 * in either value, it is in the pair. So it needs its own check.
 *
 * WHY THIS IS GROUNDED, NOT INVENTED
 * ----------------------------------
 * The STRENDA Guidelines require temperature and pH on every reported
 * kinetic measurement. The reason they are mandatory is exactly this — the
 * numbers are not meaningful, comparable, or combinable without them:
 *
 *   Swainston et al., "STRENDA DB: enabling the validation and sharing of
 *   enzyme kinetics data", FEBS Journal 285(12):2193-2204 (2018),
 *   doi:10.1111/febs.14427, PMID 29498804.
 *
 * Barbara Bakker — whose reply drove `reliabilityScore.ts` — is a co-author
 * of that paper. The two pieces of feedback are the same standard seen from
 * two sides: she described grading a parameter's applicability, and the
 * guideline she co-authored is what makes the grading possible at all.
 *
 * THERE IS NO INVENTED THRESHOLD HERE
 * -----------------------------------
 * The obvious implementation picks a number — "more than 0.5 pH units apart
 * is incoherent" — and that number would be a fabrication with no source,
 * governing which models a student is told to distrust. The same thing this
 * project refuses to do with Km, one level up.
 *
 * So the verdicts are built only from facts that need no threshold:
 *
 *   - Same reference id           -> jointly measured. A fact.
 *   - Different ids, equal pH/T   -> comparable conditions. Equality needs
 *                                    no tolerance.
 *   - Different ids, different    -> report the deltas and say plainly that
 *     conditions                     these values were never jointly
 *                                    measured. Whether 0.4 pH units matters
 *                                    for THIS enzyme is a scientific
 *                                    judgement, and the reader is the one
 *                                    holding the enzyme.
 *
 * A caller who has a defensible tolerance may supply one. It never creates
 * or changes a verdict — it only adds a sentence to the reason saying
 * whether the observed spread exceeded the tolerance the caller stated. The
 * facts do not depend on it.
 *
 * WHAT THIS DOES NOT DO
 * ---------------------
 * It does not block the run. ADR 0012/0013 govern whether a run may
 * proceed, and they are about a parameter being *unsourced*. Every value
 * here is sourced; the finding is about how they sit together. Turning a
 * description into a gate is how "these came from two papers" — the normal
 * case in any literature-assembled model, including published ones — would
 * start failing runs that are merely imperfect.
 *
 * Bakker's own answer is the argument against blocking: she does not exclude
 * anything a priori, and rejects at the level of the whole model after
 * validating against measured flux data. Terrium has no flux data to reject
 * against. Reporting the incoherence and naming it is what is left, and it
 * is considerably more than saying nothing.
 */

import type { AssayConditions } from "./provenance";
import type { CitationLocator } from "./citeVerify";

/**
 * Which locator kinds identify *a publication*, in order of preference.
 *
 * `brenda_ec` is deliberately absent. An EC number identifies the ENZYME,
 * not the paper — every Km and Ki for lactate dehydrogenase shares
 * `1.1.1.27`, so treating it as a source identity would report `same_source`
 * for every pair of LDH parameters ever resolved, which is both wrong and
 * the most reassuring possible wrong answer. That is the failure this module
 * exists to prevent, so it must not be the failure this module commits.
 */
const SOURCE_IDENTITY_KINDS: ReadonlySet<string> = new Set([
  "doi",
  "pubmed",
  "brenda_ref",
]);

export type CoherenceVerdict =
  /** Every parameter carries the same publication identifier. */
  | "same_source"
  /** Different publications, but the reported pH and temperature agree. */
  | "same_conditions"
  /** Different publications reporting different conditions. */
  | "differing_conditions"
  /** Fewer than two parameters could be compared at all. */
  | "unassessable";

export interface ParameterUnderTest {
  /** Parameter name as the user sees it: "km", "ki". */
  key: string;
  conditions?: AssayConditions;
  citationLocators?: CitationLocator[];
}

/**
 * An optional, caller-supplied statement of how much spread they consider
 * tolerable. Never used to decide a verdict — see the module header.
 */
export interface CoherenceTolerance {
  phTolerance: number;
  temperatureToleranceC: number;
  /** Where the tolerance came from. Required, for the same reason
   * `PhysiologicalReference.basis` is required. */
  basis: string;
}

export interface CoherenceReport {
  verdict: CoherenceVerdict;
  reason: string;
  /** Parameter keys that were actually compared. */
  comparedKeys: string[];
  /** Keys excluded from the comparison, and why. */
  excluded: Array<{ key: string; why: string }>;
  /** Observed spread, present whenever two or more conditions were read. */
  spread?: {
    phRange?: { min: number; max: number; delta: number };
    temperatureRangeC?: { min: number; max: number; delta: number };
  };
  /**
   * Populated only when the caller supplied a tolerance. Says whether the
   * observed spread exceeded it. Never changes `verdict`.
   */
  toleranceAssessment?: string;
  /**
   * Whether the compared parameters were measured in the same buffer
   * (ADR 0028). Reported ALONGSIDE `verdict`, not folded into it.
   *
   * Folding it in was the obvious move and it is wrong. `verdict` answers
   * "were these values measured under the same pH and temperature", a
   * question with a clean answer; buffer identity answers a second question
   * whose most common honest answer is "the sources did not say". Merging
   * them would let a missing buffer string downgrade a verdict about
   * temperature — degrading a fact that WAS established because a different
   * fact was not.
   */
  buffer?: BufferCoherence;
  /**
   * Whether the compared parameters were measured under the same cofactor
   * and effector conditions (ADR 0032).
   *
   * Reported ALONGSIDE `verdict`, for the same reason `buffer` is: it
   * answers a different question, whose most common honest answer is "the
   * sources did not say". Folding it in would let an unmentioned cofactor
   * downgrade a finding about temperature that WAS established.
   */
  effectors?: EffectorCoherence;
}

export type EffectorVerdict =
  /** Same compounds, same presence state, identities resolved. */
  | "same"
  /** Different compounds, or the same compound in opposite presence. */
  | "different"
  /** Names agree as text but at least one did not resolve to a compound. */
  | "unknown"
  /** Neither source named a cofactor. */
  | "not_reported";

export interface EffectorCoherence {
  verdict: EffectorVerdict;
  reason: string;
  /** What each parameter reported, as written. A reader has to be able to
   * disagree with the parse, and cannot without the clauses. */
  reported: Record<string, string[]>;
}

export type BufferVerdict =
  /** Both buffers resolved to the same PubChem parent compound. */
  | "same"
  /** Both resolved, to different compounds. */
  | "different"
  /** At least one was reported and could not be resolved. */
  | "unknown"
  /** At least one source reported no buffer at all. */
  | "not_reported";

export interface BufferCoherence {
  verdict: BufferVerdict;
  reason: string;
  /** The raw strings, per parameter key. A reader has to be able to
   * disagree with the resolution, and cannot without the strings. */
  reported: Record<string, string | undefined>;
}

function isFinite_(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * The publication identifier for one parameter, or `undefined`.
 *
 * Returns a `kind:value` composite rather than the bare value so that a
 * PMID of "740253" and a BRENDA reference id of "740253" — which is an
 * entirely plausible collision, since both are short numeric strings from
 * different namespaces — cannot be mistaken for the same paper.
 */
export function sourceIdentity(
  locators: CitationLocator[] | undefined,
): string | undefined {
  if (!locators) return undefined;
  for (const kind of ["doi", "pubmed", "brenda_ref"]) {
    const hit = locators.find(
      (l) => l.kind === kind && SOURCE_IDENTITY_KINDS.has(l.kind) && l.value,
    );
    if (hit) return `${hit.kind}:${hit.value.trim().toLowerCase()}`;
  }
  return undefined;
}

function range(values: number[]): { min: number; max: number; delta: number } {
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { min, max, delta: max - min };
}

/**
 * Compare the cofactors and effectors of the parameters under test.
 *
 * Extraction and PubChem resolution happen in Python (`effector.py`, ADR
 * 0032). This compares what arrived, and — as with buffers — deliberately
 * does NOT fall back to comparing raw text when an identity is missing:
 * the corpus spells fructose 1,6-bisphosphate four ways, so text agreement
 * is not compound agreement.
 *
 * THE KEY INCLUDES PRESENCE. Two rows naming the same compound with
 * opposite presence are the case this exists for — a wild-type LDH measured
 * with and without its allosteric activator, at the same pH and temperature,
 * from the same paper, where every other field agrees. A key built on
 * compound alone would report `same` for exactly that pair.
 */
function assessEffectors(parameters: ParameterUnderTest[]): EffectorCoherence {
  const reported: Record<string, string[]> = {};
  for (const p of parameters) {
    reported[p.key] = (p.conditions?.effectors ?? []).map((e) => e.raw);
  }

  const lists = parameters.map((p) => p.conditions?.effectors ?? []);
  const names = parameters.map((p) => p.key);

  if (lists.every((l) => l.length === 0)) {
    return {
      verdict: "not_reported",
      reason:
        "No source named a cofactor or effector. Comparability on this axis " +
        "is unknown — a gap in the sources, not a finding that the " +
        "conditions agreed. BRENDA does not distinguish 'absent' from " +
        "'not mentioned'.",
      reported,
    };
  }

  const empty = names.filter((_, i) => lists[i].length === 0);
  if (empty.length > 0) {
    const named = lists.flat().map((e) => e.compound_text);
    return {
      verdict: "different",
      reason:
        `${empty.join(" and ")} name no effector, while ` +
        `${[...new Set(named)].join(", ")} is reported for the others. That ` +
        "is a difference in what was reported, and may be a difference in " +
        "what was in the tube.",
      reported,
    };
  }

  const keyOf = (e: { identity?: { parent_cid?: number | null } | null;
                      compound_text: string; presence: string }) =>
    `${e.identity?.parent_cid ?? e.compound_text.trim().toLowerCase()}|${e.presence}`;

  const keySets = lists.map((l) => new Set(l.map(keyOf)));
  const first = keySets[0];
  const allAgree = keySets.every(
    (s) => s.size === first.size && [...s].every((k) => first.has(k)),
  );

  const unresolved = lists
    .flat()
    .filter((e) => !e.identity || e.identity.status !== "resolved");

  if (allAgree) {
    if (unresolved.length > 0) {
      return {
        verdict: "unknown",
        reason:
          "The effector names match as text, but " +
          `${[...new Set(unresolved.map((e) => e.compound_text))].join(", ")} ` +
          "could not be resolved to a compound, so they are not confirmed to " +
          "be the same substance. Matching text is not matching chemistry.",
        reported,
      };
    }
    const concentrations = lists
      .flat()
      .map((e) => e.concentration_text)
      .filter((c): c is string => Boolean(c));
    const note = concentrations.length
      ? ` Concentration was NOT compared (${[...new Set(concentrations)].join(", ")}).`
      : "";
    return {
      verdict: "same",
      reason:
        "Every compared parameter reports the same effectors in the same " +
        `presence state.${note}`,
      reported,
    };
  }

  // Same compound, opposite presence: the sharpest case, named as itself.
  const presenceByCompound = lists.map((l) => {
    const m = new Map<string | number, string>();
    for (const e of l) {
      m.set(e.identity?.parent_cid ?? e.compound_text.trim().toLowerCase(), e.presence);
    }
    return m;
  });
  const flipped: string[] = [];
  for (const e of lists.flat()) {
    const id = e.identity?.parent_cid ?? e.compound_text.trim().toLowerCase();
    const states = new Set(
      presenceByCompound.map((m) => m.get(id)).filter((s): s is string => Boolean(s)),
    );
    if (states.size > 1 && !states.has("unstated")) flipped.push(e.compound_text);
  }
  if (flipped.length > 0) {
    return {
      verdict: "different",
      reason:
        `One measurement was made in the PRESENCE of ` +
        `${[...new Set(flipped)].join(", ")} and another in its ABSENCE. ` +
        "These are opposite experimental conditions, not a difference of " +
        "degree: an allosteric effector is added precisely because it " +
        "changes the kinetics, so the values describe different states of " +
        "the same enzyme.",
      reported,
    };
  }

  const described = names
    .map((k, i) =>
      `${k}: ${lists[i].map((e) => `${e.compound_text} (${e.presence})`).join(", ")}`,
    )
    .join("; ");
  return {
    verdict: "different",
    reason:
      `Different effector conditions — ${described}. Cofactors change ` +
      "kinetics, so these measurements were not made under the same " +
      "conditions even where pH and temperature agree.",
    reported,
  };
}

/**
 * Compare the buffers of the parameters under test.
 *
 * The identity resolution happens in Python (`Tests/buffer_identity.py`,
 * ADR 0028) because that is where the BRENDA string is parsed and where the
 * PubChem lookup is cached. This function only compares what arrived — it
 * deliberately does not fall back to string equality when an identity is
 * missing, because `"0.5 M Tris-HCl buffer" !== "Tris-HCl"` is true as
 * strings and false as chemistry, and a fallback that is wrong in the
 * common case is worse than no fallback.
 */
function assessBuffers(parameters: ParameterUnderTest[]): BufferCoherence {
  const reported: Record<string, string | undefined> = {};
  for (const p of parameters) {
    reported[p.key] = p.conditions?.buffer ?? undefined;
  }

  const identities = parameters.map((p) => p.conditions?.bufferIdentity);
  const names = parameters.map((p) => p.key);

  const unreported = names.filter(
    (_, i) => !identities[i] || identities[i]!.status === "not_reported",
  );
  if (unreported.length > 0) {
    return {
      verdict: "not_reported",
      reason:
        `${unreported.join(" and ")} report no buffer, so buffer ` +
        "comparability is unknown. That is a gap in the sources, not a " +
        "finding about the model — and not evidence the buffers agree.",
      reported,
    };
  }

  const unresolved = names.filter((_, i) => identities[i]!.status !== "resolved");
  if (unresolved.length > 0) {
    const why = identities
      .filter((id) => id!.status !== "resolved")
      .map((id) => id!.reason)
      .filter(Boolean)
      .join(" ");
    return {
      verdict: "unknown",
      reason:
        `The buffer reported for ${unresolved.join(" and ")} could not be ` +
        `resolved to a compound, so the buffers could not be compared. ${why}`.trim(),
      reported,
    };
  }

  const parents = identities.map((id) => id!.parent_cid);
  const allSame = parents.every((c) => c === parents[0]);

  if (allSame) {
    const concentrations = identities
      .map((id) => id!.concentration_text)
      .filter(Boolean);
    const note = concentrations.length
      ? ` Concentration was not compared (${concentrations.join(", ")}).`
      : "";
    return {
      verdict: "same",
      reason:
        `${names.join(" and ")} were measured in the same buffer species ` +
        `(PubChem parent compound ${parents[0]}).${note}`,
      reported,
    };
  }

  const described = names
    .map((k, i) => `${k}: ${reported[k]} (compound ${parents[i]})`)
    .join("; ");
  return {
    verdict: "different",
    reason:
      `Different buffers — ${described}. Buffer composition affects enzyme ` +
      "kinetics, so these measurements were not made under the same " +
      "conditions even where pH and temperature agree.",
    reported,
  };
}

/**
 * Assess whether a set of resolved parameters could have come from one
 * experiment.
 */
export function assessCoherence(
  parameters: ParameterUnderTest[],
  tolerance?: CoherenceTolerance,
): CoherenceReport {
  const excluded: Array<{ key: string; why: string }> = [];
  const usable: ParameterUnderTest[] = [];

  for (const p of parameters) {
    const hasPh = isFinite_(p.conditions?.ph);
    const hasTemp = isFinite_(p.conditions?.temperatureC);
    if (!hasPh && !hasTemp) {
      excluded.push({
        key: p.key,
        why: `${p.key} reports neither pH nor temperature, so it cannot be placed alongside anything`,
      });
      continue;
    }
    usable.push(p);
  }

  if (parameters.length < 2) {
    return {
      verdict: "unassessable",
      reason:
        `Coherence compares parameters against each other, and this model ` +
        `resolves ${parameters.length === 1 ? "only one" : "no"} literature ` +
        "parameter. There is no pair to be incoherent.",
      comparedKeys: parameters.map((p) => p.key),
      excluded,
    };
  }

  if (usable.length < 2) {
    return {
      verdict: "unassessable",
      reason:
        "Fewer than two parameters report any assay conditions, so whether " +
        "they came from compatible experiments cannot be determined. This is " +
        "a gap in the sources, NOT a finding that the model is sound — an " +
        "unassessed model and a coherent one look identical from here.",
      comparedKeys: usable.map((p) => p.key),
      excluded,
    };
  }

  const comparedKeys = usable.map((p) => p.key);
  const identities = usable.map((p) => sourceIdentity(p.citationLocators));
  const allIdentified = identities.every((id) => id !== undefined);
  const singleSource =
    allIdentified && new Set(identities).size === 1;

  const phs = usable
    .map((p) => p.conditions?.ph)
    .filter(isFinite_) as number[];
  const temps = usable
    .map((p) => p.conditions?.temperatureC)
    .filter(isFinite_) as number[];

  const spread: CoherenceReport["spread"] = {};
  if (phs.length >= 2) spread.phRange = range(phs);
  if (temps.length >= 2) spread.temperatureRangeC = range(temps);

  const toleranceAssessment = tolerance
    ? describeTolerance(spread, tolerance)
    : undefined;

  // Computed for every real comparison, including `same_source`. A single
  // paper reporting a Km and a Ki in one buffer is the case where "same"
  // is most worth stating, because it is the only verdict that lets a
  // reader stop worrying about buffers entirely.
  const bufferCoherence = assessBuffers(usable);
  const effectorCoherence = assessEffectors(usable);

  if (singleSource) {
    return {
      verdict: "same_source",
      reason:
        `${comparedKeys.join(" and ")} carry the same publication ` +
        `(${identities[0]}), so they were reported together and are as ` +
        "jointly measured as literature values get. This is the strongest " +
        "coherence available and it required no judgement call.",
      comparedKeys,
      excluded,
      spread,
      toleranceAssessment,
      buffer: bufferCoherence,
      effectors: effectorCoherence,
    };
  }

  const phDiffers = spread.phRange !== undefined && spread.phRange.delta > 0;
  const tempDiffers =
    spread.temperatureRangeC !== undefined &&
    spread.temperatureRangeC.delta > 0;

  if (!phDiffers && !tempDiffers) {
    const stated: string[] = [];
    if (phs.length >= 2) stated.push(`pH ${phs[0]}`);
    if (temps.length >= 2) stated.push(`${temps[0]} °C`);
    return {
      verdict: "same_conditions",
      reason:
        `${comparedKeys.join(" and ")} come from different publications but ` +
        `report identical conditions (${stated.join(", ")}). They are ` +
        "comparable on the conditions STRENDA requires. Cofactors and buffer " +
        "are not compared here and may still differ.",
      comparedKeys,
      excluded,
      spread,
      toleranceAssessment,
      buffer: bufferCoherence,
      effectors: effectorCoherence,
    };
  }

  const differences: string[] = [];
  if (phDiffers) {
    const r = spread.phRange!;
    differences.push(
      `pH ranges from ${r.min} to ${r.max} (a spread of ${r.delta.toFixed(2)})`,
    );
  }
  if (tempDiffers) {
    const r = spread.temperatureRangeC!;
    differences.push(
      `temperature ranges from ${r.min} °C to ${r.max} °C (a spread of ${r.delta.toFixed(1)} °C)`,
    );
  }

  return {
    verdict: "differing_conditions",
    reason:
      `${comparedKeys.join(" and ")} were measured under different ` +
      `conditions: ${differences.join(", and ")}. These values were never ` +
      "true of the same enzyme at the same time, so the model combines " +
      "measurements from experiments that were never run together. Whether " +
      "that matters depends on how strongly this enzyme responds to pH and " +
      "temperature, which Terrium does not know and does not guess.",
    comparedKeys,
    excluded,
    spread,
    toleranceAssessment,
    buffer: bufferCoherence,
    effectors: effectorCoherence,
  };
}

function describeTolerance(
  spread: CoherenceReport["spread"],
  tolerance: CoherenceTolerance,
): string {
  const exceeded: string[] = [];
  if (spread?.phRange && spread.phRange.delta > tolerance.phTolerance) {
    exceeded.push(
      `pH spread ${spread.phRange.delta.toFixed(2)} exceeds the stated ±${tolerance.phTolerance}`,
    );
  }
  if (
    spread?.temperatureRangeC &&
    spread.temperatureRangeC.delta > tolerance.temperatureToleranceC
  ) {
    exceeded.push(
      `temperature spread ${spread.temperatureRangeC.delta.toFixed(1)} °C exceeds the stated ±${tolerance.temperatureToleranceC}`,
    );
  }
  if (exceeded.length === 0) {
    return `Within the tolerance supplied by the caller (${tolerance.basis}).`;
  }
  return `${exceeded.join("; ")}. Tolerance basis: ${tolerance.basis}.`;
}

/**
 * Build the report directly from a resolver's provenance map.
 *
 * Only `origin === "resolved"` entries participate. A defaulted or
 * user-supplied parameter has no assay behind it — asking whether a
 * student's chosen `s0` is coherent with a measured Km is the
 * measured-quantity/experimental-condition category error (ADR 0012/0013)
 * in a new costume, and including defaults would let a model full of
 * made-up numbers report `same_conditions` because none of them disagreed.
 */
export function coherenceFromProvenance(
  provenance: Record<string, { origin?: string; assayConditions?: AssayConditions; citationLocators?: CitationLocator[] }>,
  tolerance?: CoherenceTolerance,
): CoherenceReport {
  const resolved = Object.entries(provenance)
    .filter(([, p]) => p?.origin === "resolved")
    .map(([key, p]) => ({
      key,
      conditions: p.assayConditions,
      citationLocators: p.citationLocators,
    }));
  return assessCoherence(resolved, tolerance);
}
