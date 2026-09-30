import { randomUUID } from "node:crypto";
import type { SimulationDomain } from "./catervaRunner";
import { resolveQueryWithLLM, type EntityExtraction } from "./llmResolver";
import {
  coherenceFromProvenance,
  type CoherenceReport,
} from "./assayCoherence";
import { resolveKineticValue, resolveEpidemiologyParameters, type RelatednessVerdict } from "./scienceAgent";
import { buildCitationLocators, type CitationLocator } from "./citeVerify";
import { matchEnzyme } from "./enzymes";
import { matchOrganism } from "./organisms";
import { matchDisease } from "./diseases";
import { extractStatedQuantities } from "./statedQuantities";
import {
  RESOLVABLE_FIELDS,
  KI_MODE_OF_DOMAIN,
  DOMAINS_WITH_LITERATURE_RESOLUTION,
  EPIDEMIOLOGY_BRIDGE_DOMAINS,
  RequiredParametersMissingError,
  UnrecognizedQueryError,
  resolveGaps,
  buildResolvedKineticProvenance,
  unverifiedOriginKeys,
  isAllDefaults,
  validateParameterProvenance,
  type AssayConditions,
  type InhibitionMode,
  type ParameterProvenance,
} from "./provenance";
import type { ScienceAgentResult } from "./scienceAgent";
import { verifiableMetricsCollector } from "./verifiable-metrics";
import { validateSTREANDA } from "./strenda-validator";
import { verifyParameterAgainstLiterature } from "./literature-verifier";
import { getDomainCitation } from "./domain-literature";

/**
 * Type-safe validator for numeric assay conditions.
 * Ensures finite numbers only; rejects NaN and Infinity.
 */
function isValidFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Type-safe validator for non-empty string assay conditions.
 */
function isValidNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

/** Convert the Python runner's assay-conditions payload into the provenance
 * shape. The runner emits JSON `null` for values the source did not report;
 * `AssayConditions` uses absence for the same thing, so nulls are dropped
 * rather than passed through. A null that survived as `null` would be a
 * present-but-empty field, which `strendaStatusFor` would have to guess at.
 *
 * Nothing is defaulted here. If BRENDA did not report a pH, the result has
 * no pH, and the citation degrades to `flagged` downstream. See ADR 0010. */
function toAssayConditions(
  raw: ScienceAgentResult["assayConditions"],
  effectors?: ScienceAgentResult["effectors"],
): AssayConditions | undefined {
  // `effectors` alone is enough to build a conditions object: a row can
  // name a cofactor and report neither pH nor temperature, and dropping it
  // because `assayConditions` was absent would lose the one thing the
  // commentary DID say.
  if (!raw && !effectors?.length) return undefined;

  const conditions: AssayConditions = {};

  // Taken from the TOP LEVEL of the agent result, which is where the runner
  // emits it -- not from `raw`. Reading it off `raw` compiles, type-checks,
  // and yields `undefined` forever (ADR 0027's shape).
  if (effectors?.length) {
    conditions.effectors = effectors;
  }

  if (!raw) return conditions;

  if (isValidFiniteNumber(raw.ph)) {
    conditions.ph = raw.ph;
  }
  if (isValidFiniteNumber(raw.temperatureC)) {
    conditions.temperatureC = raw.temperatureC;
  }
  if (raw.bufferIdentity) {
    conditions.bufferIdentity = raw.bufferIdentity;
  }
  if (isValidNonEmptyString(raw.buffer)) {
    conditions.buffer = raw.buffer;
  }

  return Object.keys(conditions).length > 0 ? conditions : undefined;
}

/**
 * Map kinetic result fields to their output parameter names.
 * Supports scalability: adding new kinetic parameters only requires updating this map.
 */
const KINETIC_VALUE_MAP: Record<"km" | "ki", keyof ScienceAgentResult> = {
  km: "km",
  ki: "ki",
};

/**
 * The form the returned value actually is, as a line a reader will see
 * (ADR 0052).
 *
 * `poolFindingFlags` already emits the mixture warning — "returning the
 * lowest would pick a form rather than answer the question". That sentence
 * is conditional. This one is not: it fires only when the value in hand IS
 * one of those forms.
 *
 * The two are deliberately separate flags rather than one merged sentence.
 * The mixture is a fact about the pool and is worth saying whichever row
 * won; this is a fact about the answer. Merging them would make the
 * stronger claim disappear into the weaker one.
 */
function selectedFormFlags(
  key: string,
  form: ScienceAgentResult["selectedForm"],
): string[] {
  if (!form) return [];
  return [`${key.toUpperCase()} — a form was picked: ${form.reason}`];
}

/**
 * The tie the evidence could not break, as a line a reader will see
 * (ADR 0051).
 *
 * This goes into `provenance.flags` — the list the CLI and web UI both
 * render — rather than only onto a response field. ADR 0040 is the record
 * of what happens otherwise: findings that reached the API and never
 * reached the student.
 *
 * The alternatives are listed with their reference ids, because a named
 * alternative is checkable and a bare count is not. Capped at four with an
 * explicit remainder: a flag nobody finishes reading is a flag nobody
 * reads, and the cap is stated rather than silently truncating.
 */
/**
 * The papers Caterva found and then threw away.
 *
 * WHEN BRENDA HAS NOTHING, the resolver does not stop. It searches PubMed
 * and CORE, and when that turns up papers it returns
 * `source: "literature_candidates"` carrying the list — the fallback that
 * exists precisely for the case where the primary path fails.
 *
 * `literatureCandidates` was declared on `ScienceAgentResult`, populated by
 * `_candidates_to_dict`, emitted on two runner branches, and **read by
 * nothing**. Not a surface, not the CLI, not a flag. A student asking for a
 * constant BRENDA does not carry was told "could not resolve" while the
 * system held a list of papers that probably contain the number, fetched at
 * the cost of two API calls.
 *
 * That is ADR 0039's defect — computed, transported, dropped — on the one
 * path whose whole job is to help when everything else failed. It is also
 * Bakker's principle inverted: *do not exclude anything a priori*. Excluding
 * the entire remaining evidence base by not mentioning it is the most
 * complete exclusion available.
 *
 * Titles and locators, not a count. "We found 4 papers" is unusable; a
 * reader needs to know WHICH, and the PMID or URL is what makes the offer
 * checkable rather than a claim. Capped at four with an explicit remainder,
 * for the reason `selectionTieFlags` gives: a flag nobody finishes reading
 * is a flag nobody reads.
 */
function literatureCandidateNote(
  key: string,
  candidates: ScienceAgentResult["literatureCandidates"],
): string | undefined {
  if (!candidates || candidates.length === 0) return undefined;
  const K = key.toUpperCase();

  const shown = candidates.slice(0, 4);
  const listed = shown
    .map((c) => {
      // A locator, in the order that is most directly checkable. PubMed's
      // esummary never supplies a DOI, and CORE has no PMID, so neither
      // alone covers both sources.
      const locator = c.pmid
        ? ` [PMID ${c.pmid}]`
        : c.doi
          ? ` [doi ${c.doi}]`
          : c.url
            ? ` [${c.url}]`
            : "";
      return `"${c.title}"${locator}`;
    })
    .join("; ");
  const more =
    candidates.length > shown.length
      ? ` and ${candidates.length - shown.length} more`
      : "";

  return (
    `Caterva found ${candidates.length} candidate paper(s) that may report ` +
    `${K}. It does not extract numbers from full text, so these are for you ` +
    `to read rather than a value it will use: ${listed}${more}. ` +
    // THE INSTRUCTION, RESTATED, BECAUSE PROMOTING A NOTE DROPS IT.
    //
    // `missingKeyDetails` replaces the generic sentence for any key
    // carrying an `unresolvedReason` -- and the generic sentence is where
    // "Add km=<value> to your query" lives. Attaching this note therefore
    // took away the one instruction the student can act on, which is a
    // regression that function's own comment records having happened once
    // before. Caught here by the test, not by reading.
    `Once you have it, add ${key}=<value> to your query, and attach the ` +
    `source with --cite ${key}="..." so it is recorded rather than lost.`
  );
}

/**
 * What each published value is worth, and how a client can draw the band.
 *
 * `selectionTieFlags` says the evidence did not choose and names the
 * alternatives. This says how much each one WEIGHS — Bakker's three axes,
 * graded per candidate:
 *
 *   "We gave each parameter a score based on its reliability and
 *    applicability [...] These scores were then used to give the parameter a
 *    weight in the sampling."
 *
 * The flag is emitted whenever the frontier held more than one row, which is
 * exactly when the weights are decision-relevant. One row is not a
 * disagreement and a flag about it would be noise — and this project cannot
 * afford noisy flags, because it prints a lot of them.
 *
 * It names the command rather than describing it. `scientific ensemble` is
 * what turns these weights into a trajectory band, and a reader told that a
 * spread exists without being told how to see its effect is left where
 * ADR 0115 found them: holding a finding with no next step.
 */
function ensembleCandidateFlags(
  key: string,
  candidates: ScienceAgentResult["ensembleCandidates"],
): string[] {
  if (!candidates || candidates.length < 2) return [];
  const K = key.toUpperCase();

  // Capped at four with an explicit remainder, for the reason
  // `selectionTieFlags` gives: a flag nobody finishes reading is a flag
  // nobody reads.
  const shown = candidates.slice(0, 4);
  const listed = shown
    .map((c) => {
      const unit = c.unit ? ` ${c.unit}` : '';
      const ref = c.reference_id ? ` [ref ${c.reference_id}]` : '';
      const grades = [
        c.grades.assay_completeness,
        c.grades.condition_proximity,
        c.grades.organism_match,
      ].join('/');
      return `${c.value}${unit}${ref} (${grades})`;
    })
    .join('; ');
  const more =
    candidates.length > shown.length
      ? ` and ${candidates.length - shown.length} more`
      : '';

  return [
    `${K} — ${candidates.length} published values survive the evidence ranking, ` +
      `each graded on assay completeness / condition proximity / organism ` +
      `match: ${listed}${more}. These grades are the weights an ensemble ` +
      `samples by; \`scientific ensemble\` runs the model once per draw and ` +
      `shows whether the disagreement changes the answer.`,
  ];
}

function selectionTieFlags(
  key: string,
  tie: ScienceAgentResult["selectionTie"],
): string[] {
  if (!tie || (tie.candidates?.length ?? 0) < 2) return [];
  const K = key.toUpperCase();

  const shown = tie.candidates.slice(0, 4);
  const listed = shown
    .map((c) => {
      const mark = c.selected ? " (returned)" : "";
      const ref = c.reference_id ? ` [ref ${c.reference_id}]` : "";
      return `${c.value}${c.unit ? " " + c.unit : ""}${ref}${mark}`;
    })
    .join("; ");
  const more =
    tie.candidates.length > shown.length
      ? ` and ${tie.candidates.length - shown.length} more`
      : "";

  return [`${K} — the evidence did not choose: ${tie.reason} Candidates: ${listed}${more}.`];
}

/**
 * Turn pool-level findings into flags a reader will actually see.
 *
 * `provenance.flags` is what the CLI and the web UI render. The resolver's
 * diagnostic `logs` are not — and for four ADRs these findings reached only
 * the logs, which is the same as reaching nobody.
 *
 * Each finding already carries a `reason` written for a human. Nothing is
 * reworded here: a client that paraphrases a finding becomes a second place
 * the wording can drift, and the Python module is where the sentence was
 * argued over.
 */
/**
 * Say when the resolved value measured a PREPARATION, not the free enzyme.
 *
 * ADR 0029 removes rows measuring a sequence variant. An affinity tag, a
 * covalent modification and immobilisation are none of them a sequence
 * change, so that filter never saw them — and the human LDH Ki resolved to
 * 0.00059, a "recombinant His-tagged enzyme" row, with nothing in the
 * response saying so (ADR 0092).
 *
 * Silent for `unstated`, `absent` and `native`. A flag on every row in the
 * corpus is noise, and noise is how the flags that matter stop being read.
 */
/**
 * What the chosen row says it measured, when that can make it the wrong
 * number for this model: another isoform, or (for an inhibition constant)
 * a mode not stated or measured against another molecule. Reported, not
 * judged: the reading was made in Python (runner `_row_scope`).
 *
 * Found on human LDH: gossypol's Ki resolved to 0.0014 mM, which is its
 * LDH-B value (0.0019 for LDH-A, 0.0042 for LDH-C), and no row states a mode.
 */
export function rowScopeFlags(
  key: string,
  scope: ScienceAgentResult["rowScope"],
  isoform?: string,
): string[] {
  const name = key.toUpperCase();
  // With an isoform named, the runner already chose among rows for it
  // (fallback_logic, isoform=...). What is left to say is whether the chosen
  // row confirms it, names none, or (where the runner could not filter)
  // names another. A row with no commentary at all names none.
  if (!scope) {
    return isoform
      ? [`${name}: the source row names no isoform, so whether it measured ${isoform}, the one the query names, is unknown.`]
      : [];
  }
  const out: string[] = [];
  if (isoform) {
    if (!scope.isoform) {
      out.push(`${name}: the source row names no isoform, so whether it measured ${isoform}, the one the query names, is unknown.`);
    } else if (!sameIsoform(scope.isoform, isoform)) {
      out.push(`${name} was measured on isoform ${scope.isoform}, not ${isoform}, the one the query names: a different protein's constant.`);
    }
  } else if (scope.isoform) {
    out.push(
      `${name} was measured on isoform ${scope.isoform}; for another isoform it is a different protein's constant.`,
    );
  }
  if (key === "ki") {
    if (scope.kitzWilson) {
      // A mode-aware lookup takes one only when no row states the model's
      // mode and no reversible row states none; without a mode it can be
      // the lowest value like any other. Either way the reader is told what
      // the number is, in the words caterva compose's report uses.
      out.push(
        `${name}: the source row was determined from Kitz-Wilson plots, which give the K_I of ` +
          "an irreversible inactivation, not a reversible Ki; it states no inhibition mode.",
      );
    } else if (scope.inhibitionMode === "unstated") {
      out.push(`${name}: the source row states no inhibition mode, so which binding event it measured is unknown.`);
    } else {
      out.push(
        `${name}: the source row measured ${scope.inhibitionMode} inhibition` +
          (scope.versus ? ` versus ${scope.versus}` : "") +
          "; a Ki is specific to that mode and assay.",
      );
    }
  }
  return out;
}

/** A full enzyme name BRENDA writes before an isoform code, and its abbreviation. */
const ISOFORM_FULL_NAME = /^([Hh]exokinases?|[Mm]onoamine oxidase|[Ll]actate dehydrogenase)\s+/;
const ISOFORM_ABBREVIATION_OF: Record<string, string> = {
  hexokinase: "HK", hexokinases: "HK", "monoamine oxidase": "MAO", "lactate dehydrogenase": "LDH",
};

/**
 * One isoform name as caterva.bind.core `_compared_as` compares it: for each
 * isoform it names ("I and II" names two), its spelling without case or
 * separators, and its code when it is an abbreviation and a code ("HK-2")
 * or a code alone ("2").
 *
 * The row's side is the runner's reading, spelled one way already. The
 * query's side is extractIsoform's, or the LLM's entities.isoform, which can
 * be "hexokinase 2" or "isoform MAO B"; those are read here as the runner
 * reads a request: the keyword dropped, a full enzyme name as its
 * abbreviation, and an abbreviation joined to its code by a hyphen.
 */
function isoformParts(name: string): { key: string; code: string | null; abbreviated: boolean }[] {
  const code = String.raw`(?:P?(?:VI{0,3}|IV|I{1,3})[a-c]?|[A-Z]\d?(?:[A-Z]\d)*|\d{1,2})`;
  const compact = String.raw`(?:VI{0,3}|IV|I{1,3}|[A-Z]|\d{1,2})`;
  const stemmed = new RegExp(String.raw`^((?:[A-Z][a-z])?(?:HXK|LDH|MAO|HK))(?:[ -](${code})|(${compact}))$`);
  const abbreviated = /^(?:[A-Z][a-z])?[A-Z]{2,5}-([A-Za-z0-9]{1,4})$/;
  const alone = new RegExp(`^${code}$`, "i");
  const key = (s: string) => s.replace(/[\s_-]+/g, "").toLowerCase();
  let text = name.trim().replace(/^(?:isozyme|isoenzyme|isoform)s?\s+/i, "");
  const full = text.match(ISOFORM_FULL_NAME);
  if (full) text = `${ISOFORM_ABBREVIATION_OF[full[1].toLowerCase()]} ${text.slice(full[0].length)}`;
  return text.split(/\s+and\s+/).filter(Boolean).map((raw) => {
    const s = raw.match(stemmed);
    const part = s ? `${s[1]}-${s[2] ?? s[3]}` : raw;
    const a = part.match(abbreviated);
    if (a) return { key: key(part), code: key(a[1]), abbreviated: true };
    if (alone.test(part)) return { key: key(part), code: key(part), abbreviated: false };
    return { key: key(part), code: null, abbreviated: false };
  });
}

/**
 * caterva.bind.core.same_isoform, the comparison the runner filtered by, so
 * a row the runner kept for the query's isoform is not called another
 * protein's here, nor the reverse. Case, spaces, hyphens and underscores are
 * ignored ("MAO B" is "MAO-B"); a row naming two isoforms ("I and II") is
 * either; and a code alone is that code after an abbreviation ("2" is
 * "HK-2", "B" is "MAO-B"): the rows are one EC number's, so the abbreviation
 * says nothing the code does not. Two abbreviations with one code ("HK-1",
 * "HXK-1") and two numberings ("HK-II", "HK-2") stay two isoforms.
 */
function sameIsoform(a: string, b: string): boolean {
  const left = isoformParts(a);
  const right = isoformParts(b);
  return left.some((x) =>
    right.some((y) => x.key === y.key || (x.code !== null && x.code === y.code && x.abbreviated !== y.abbreviated)),
  );
}

/**
 * Say when a row BRENDA gives for this inhibitor is evidence against the
 * model's mechanism: it states another inhibition mode, measured versus the
 * model's own substrate.
 *
 * BRENDA ref 739793 gives human LDH and one quinoline sulfonamide 0.00059 mM
 * "competitive versus NADH" and 0.00252 mM "noncompetitive versus pyruvate".
 * A competitive model of pyruvate carries the first, which is the right row:
 * it is the only one stating the model's mode, and `rowScopeFlags` says it
 * was measured versus NADH. What that flag cannot say is that the same
 * paper, measuring against pyruvate, found the inhibitor noncompetitive:
 * the row that says so was set aside by the mode step and never reached this
 * side. `caterva compose` says it in its report; this is the same finding,
 * made by the same Python function (caterva.compose.ki_mode's
 * `evidence_against`), in the runner's `mechanismEvidence`.
 *
 * Nothing is decided here. The runner sends the row only when it is
 * evidence against the model, so this only puts its fields into words.
 */
export function mechanismEvidenceFlags(
  key: string,
  mechanismEvidence: ScienceAgentResult["mechanismEvidence"],
): string[] {
  if (key !== "ki" || !mechanismEvidence) return [];
  const name = key.toUpperCase();
  const where = [
    mechanismEvidence.organism,
    mechanismEvidence.referenceId ? `BRENDA ref ${mechanismEvidence.referenceId}` : null,
  ]
    .filter(Boolean)
    .join(", ");
  // No unit invented: a row the runner sent without one is printed without one.
  const value = mechanismEvidence.unit
    ? `${mechanismEvidence.value} ${mechanismEvidence.unit}`
    : `${mechanismEvidence.value}`;
  return [
    `${name}: evidence against this model's mechanism. Another row for this inhibitor, ` +
      `${value}${where ? ` (${where})` : ""}, states ${mechanismEvidence.inhibitionMode} ` +
      `inhibition versus ${mechanismEvidence.versus}, and ${mechanismEvidence.modelSubstrate} is ` +
      `this model's substrate: measured against it, the inhibitor is not ` +
      `${mechanismEvidence.modelMode}, and this model says it is. No choice of row fixes that.` +
      (mechanismEvidence.conditions ? ` The other row: "${mechanismEvidence.conditions}".` : ""),
  ];
}

function preparationFlags(
  key: string,
  preparation: ScienceAgentResult["preparation"],
): string[] {
  if (!preparation) return [];

  // The judgement is made ONCE, in Python, by the module that owns the
  // rule: `enzyme_preparation.differs_for(quantity)`. It answers both
  // halves — was the enzyme altered, and did the curator say the alteration
  // left THIS quantity alone ("... does not alter the Km value", which is
  // golden tuple G2's row).
  //
  // The first version re-derived that here from `status` and
  // `stated_not_to_affect`. It agreed with Python, and it was still wrong:
  // two implementations of one rule are what ADR 0027 is about, and they
  // agree right up until one of them is edited.
  //
  // `warrantsWarning` is undefined only for a payload predating the field,
  // in which case falling back to "there is a status we describe" is the
  // conservative reading — it warns rather than staying silent.
  if (preparation.warrantsWarning === false) return [];
  const altered: Record<string, string> = {
    immobilised: "an IMMOBILISED enzyme (diffusional limitation, altered microenvironment)",
    tagged: "a TAGGED construct, carrying peptide the native protein does not",
    modified: "a COVALENTLY MODIFIED enzyme",
  };
  const described = altered[preparation.status];
  if (!described) return [];

  const evidence = preparation.evidence ? ` — commentary: "${preparation.evidence}"` : "";
  return [
    `${key.toUpperCase()} — measured on ${described}${evidence}. This is a real, ` +
      `correctly cited measurement of a preparation of the enzyme, not of the free enzyme.`,
  ];
}

function poolFindingFlags(
  key: string,
  findings: ScienceAgentResult["poolFindings"],
): string[] {
  if (!findings) return [];
  const K = key.toUpperCase();
  const out: string[] = [];

  for (const c of findings.effectorContrasts ?? []) {
    out.push(`${K} — effector contrast: ${c.reason}`);
  }
  for (const m of findings.formMixtures ?? []) {
    out.push(`${K} — mixed enzyme forms: ${m.reason}`);
  }
  for (const d of findings.organismDiscrepancies ?? []) {
    out.push(`${K} — organism mismatch: ${d.reason}`);
  }
  for (const m of findings.sourceMixtures ?? []) {
    out.push(`${K} — mixed biological sources: ${m.reason}`);
  }
  // Reported as its own flag rather than folded into the mixtures above.
  // "we found no mixture" and "we could not look" must not share a
  // rendering, or the absence of a warning becomes ambiguous.
  if (findings.sourceCheckUnavailable) {
    out.push(
      `${K} — source check unavailable: ${findings.sourceCheckUnavailable.reason}`,
    );
  }
  return out;
}

/**
 * Collect the provenance notes for keys that failed validation, so the
 * thrown error can say WHY each one is missing rather than asserting one
 * generic reason for all of them.
 *
 * Only notes are carried across — never values. A note explains a refusal;
 * it must not become a channel through which an unresolved number reaches
 * the caller.
 */
function missingKeyDetails(
  missing: string[],
  provenance: Record<string, ParameterProvenance>,
): Record<string, string> {
  const details: Record<string, string> = {};
  for (const key of missing) {
    const entry = provenance[key];
    // Gated on `unresolvedReason`, NOT on the mere presence of a note.
    // Every unresolved key carries a note, including the ordinary
    // "nothing in BRENDA/KEGG/PubMed" one — promoting all of them would
    // strip the generic sentence (and the "Add km=<value>" instruction
    // that goes with it) from the common case, which is a regression the
    // first version of this function actually caused.
    if (!entry?.unresolvedReason) continue;
    const note = entry.note;
    if (typeof note === "string" && note.trim().length > 0) {
      details[key] = note;
    }
  }
  return details;
}

/**
 * Helper to build unresolved kinetic provenance (consistent format).
 */
/**
 * Exported for tests ONLY, under a name that says so.
 *
 * The alternative was asserting on this message through `resolveQuery`,
 * which throws `RequiredParametersMissingError` when a kinetic constant is
 * unresolved — the comment beside the offer below records that discovery.
 * A test that cannot reach the string it is about would be the vacuous
 * kind this repository already has a guard against.
 */
export const buildUnresolvedKineticProvenanceForTest = (
  ...args: Parameters<typeof buildUnresolvedKineticProvenance>
) => buildUnresolvedKineticProvenance(...args);

function buildUnresolvedKineticProvenance(
  key: string,
  reason:
    | "not_found"
    | "no_locator"
    | "cross_species_withheld"
    | "cross_species_too_distant"
    | "variant_withheld"
    | "isoform_withheld"
    | "mode_withheld"
    | "ec_not_resolved"
    | "ec_ambiguous",
  organismsAvailable?: string[],
  relatedness?: RelatednessVerdict[],
  substratesAvailable?: string[],
  ecCandidates?: string[],
  modelMode?: InhibitionMode,
): ParameterProvenance {
  const K = key.toUpperCase();

  // The opt-in was given and the relatedness check still refused
  // (ADR 0024, Jeske's third recommendation). This message must not read
  // like the previous one, because the user has already acted once.
  if (reason === "cross_species_too_distant") {
    const explanations = (relatedness ?? [])
      .filter((v) => v.status === "too_distant" && v.reason)
      .map((v) => v.reason as string);
    const detail = explanations.length > 0
      ? " " + explanations.join(" ")
      : organismsAvailable && organismsAvailable.length > 0
        ? ` The available organisms were ${organismsAvailable.join(", ")}.`
        : "";
    return {
      origin: "default",
      unresolvedReason: "cross_species_too_distant",
      note:
        `Cross-species use was enabled, and no candidate passed the ` +
        `relatedness check for ${K}.${detail} Enabling cross-species data ` +
        `permits a value from a related organism; it does not permit one ` +
        `from any organism.`,
    };
  }

  // `cross_species_withheld` is deliberately NOT folded into `not_found`.
  //
  // "BRENDA has no value" and "BRENDA has a value, in a species you did
  // not ask about, and cross-species use was not enabled" produce the same
  // `found: false` but are different facts. The first is a gap in the
  // literature. The second is a policy this code applied, and it is
  // reversible by the user — but only if the message says so and names
  // what is on the other side of the switch.
  //
  // See ADR 0024 and Lisa Jeske's (BRENDA/DSMZ) recommendation that
  // cross-species be an explicit opt-in with an educational warning.
  // A variant refusal is its own reason, not a flavour of "not found".
  //
  // "BRENDA holds nothing" and "BRENDA holds three values, all measured on
  // point mutants" are different facts, and only the second is reversible by
  // the reader. Same argument as cross-species, one field over — and the
  // same consequence if collapsed: the opt-in becomes unexercisable,
  // because nobody is told there is anything to opt into.
  // An isoform was asked for and BRENDA holds this constant only for
  // others. Not "not found": the reader can ask for one of those instead.
  if (reason === "isoform_withheld") {
    const named =
      organismsAvailable && organismsAvailable.length > 0
        ? organismsAvailable.join(", ")
        : "other isoforms";
    return {
      origin: "default",
      unresolvedReason: "isoform_withheld",
      note:
        `The query names an isoform, and every ${K} BRENDA holds for this system ` +
        `was measured on another (${named}). An isoform is a different gene ` +
        `product, so its ${K} is a different protein's; name one of those to use it.`,
    };
  }

  // Every Ki row states a mode other than the model's. Not "not found":
  // constants exist, of other mechanisms (BRENDA ref 739793: the one
  // quinoline sulfonamide is competitive versus NADH and noncompetitive
  // versus pyruvate). Not a value to fall back on either: a competitive
  // model run on a mixed-type constant simulates a mechanism the constant
  // was not measured under. The API has no model of those mechanisms to
  // offer instead, so the note says what exists and what the reader can
  // supply, and does not pretend a switch exists.
  if (reason === "mode_withheld") {
    const named =
      organismsAvailable && organismsAvailable.length > 0
        ? organismsAvailable.join("; ")
        : "other modes";
    // The runner only refuses by mode when it was sent one, so modelMode is
    // always known here; the fallback wording keeps the sentence true if a
    // caller ever reaches this without it.
    const head = modelMode
      ? `This model is ${modelMode} inhibition, and every`
      : "Every";
    return {
      origin: "default",
      unresolvedReason: "mode_withheld",
      note:
        `${head} ${K} BRENDA holds for this system states another inhibition ` +
        `mode (${named}). A ${K} belongs to the mechanism it was measured under, ` +
        `so none of these is this model's ${K}, and none was used. Supply ` +
        `${key}= with a ${modelMode ?? "fitting"} constant to run the model.`,
    };
  }

  if (reason === "variant_withheld") {
    const named =
      organismsAvailable && organismsAvailable.length > 0
        ? organismsAvailable.join(", ")
        : "a sequence variant";
    return {
      origin: "default",
      unresolvedReason: "variant_withheld",
      note:
        `Every ${K} BRENDA holds for this system was measured on a protein ` +
        `variant (${named}) rather than on the enzyme as found. A point ` +
        `substitution is usually chosen because it changes the kinetics, and ` +
        `an isozyme is a different gene product, so neither is a ${K} for the ` +
        `enzyme you asked about. Re-run with allowVariants to use one, ` +
        `understanding that the result describes that variant.`,
    };
  }

  if (reason === "cross_species_withheld") {
    const named =
      organismsAvailable && organismsAvailable.length > 0
        ? organismsAvailable.join(", ")
        : "another organism";
    return {
      origin: "default",
      unresolvedReason: "cross_species_withheld",
      note:
        `No ${K} was measured in the requested organism. BRENDA holds a ${K} ` +
        `for ${named}. Kinetic parameters are species-specific, so it was not ` +
        `substituted; re-run with allowCrossSpecies to use it, understanding ` +
        `that the resulting model is not a model of the organism you asked for.`,
    };
  }

  // THE RUN NEVER REACHED BRENDA.
  //
  // Both of these stop at the enzyme name, before any database is asked
  // for a value — and both used to fall into the generic message below:
  //
  //     "Could not resolve a real KM value from BRENDA/KEGG/PubMed"
  //
  // which names three sources that were never consulted. A student reads
  // that as "the literature has no value for my enzyme" and goes looking
  // for a different problem than the one they have. Naming the stage that
  // actually failed is the difference between a dead end and a next step.
  if (reason === "ec_ambiguous") {
    const named = ecCandidates && ecCandidates.length > 0
      ? ecCandidates.join(", ")
      : "more than one EC number";
    return {
      origin: "default",
      unresolvedReason: "ec_ambiguous",
      note:
        `The enzyme name you gave matches more than one enzyme (${named}), ` +
        `so no ${K} was looked up. These are different proteins — EC ` +
        `1.1.1.27 and EC 1.1.1.28 are the L- and D- lactate dehydrogenases ` +
        `— and picking one would attach a real citation to an enzyme you ` +
        `did not ask about. Re-run with the EC number you meant.`,
    };
  }

  if (reason === "ec_not_resolved") {
    return {
      origin: "default",
      unresolvedReason: "ec_not_resolved",
      note:
        `No EC number could be found for the enzyme name you gave, so no ` +
        `${K} was looked up — BRENDA, KEGG and PubMed were never asked. ` +
        `This is a problem with the NAME, not with the literature: check ` +
        `the spelling, or supply the EC number directly if you know it.`,
    };
  }

  // "BRENDA has nothing for this enzyme" and "BRENDA has plenty, under a
  // name you did not type" are different facts, and the second is the one
  // a student hits most.
  //
  // Measured: `substrate="lactate"` resolves to 10.73 and
  // `substrate="L-lactate"` returns not_found, because BRENDA's label is
  // `(S)-lactate` — "lactate" matches as a substring and "L-lactate" does
  // not. The student is told the literature is empty. It is not.
  //
  // This is the same courtesy the two branches above extend to organisms
  // and variants, for the field a reader is far MORE likely to get wrong:
  // an organism has one binomial name, a metabolite has a dozen aliases.
  if (reason === "not_found" && substratesAvailable && substratesAvailable.length > 0) {
    return {
      origin: "default",
      unresolvedReason: "not_found",
      note:
        `No ${K} was found for the substrate you named, but this enzyme ` +
        `reports ${K} values for: ${substratesAvailable.join(", ")}. ` +
        `Substrate names differ between databases and papers, so the one ` +
        `you meant may be spelled differently above. Caterva does not ` +
        `substitute one substrate for another — a similar name can be a ` +
        `salt, a stereoisomer or an ester, which is a different molecule — ` +
        `so re-run with the name you meant.`,
    };
  }

  const messages = {
    not_found: `Could not resolve a real ${K} value from BRENDA/KEGG/PubMed; using default ${K}.`,
    no_locator: `Found a ${K} but its citation carries no locator (ref id or URL); not trusted as resolved — using default ${K}.`,
  };
  return {
    origin: "default",
    note: messages[reason],
  };
}

/**
 * Apply literature resolution for kinetic constants (km, ki) from BRENDA.
 *
 * For `mm` only `km` is resolved. For `mm_competitive_inhibition` both
 * `km` and `ki` are resolved from the same literature lookup. Unresolved
 * values fall back to the defaults already in `parameters`; the provenance
 * records whether the lookup succeeded, was locatable, or failed entirely.
 */
async function applyKineticResolution(
  entities: EntityExtraction | undefined,
  overrides: Record<string, number | number[]>,
  domain: string,
  allowCrossSpecies: boolean,
  allowVariants: boolean,
  physiologicalReference: ResolveQueryOptions["physiologicalReference"],
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  if (!entities?.ecNumber && !entities?.enzymeName) {
    return { parameters, parameterProvenance, flags };
  }

  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const kineticKeys = resolvable.filter((k) => !(k in overrides));
  if (kineticKeys.length === 0) {
    return { parameters, parameterProvenance, flags };
  }

  // Accumulate parameter changes to avoid repeated object spreading
  const parameterUpdates: Record<string, number | number[]> = {};
  const provenanceUpdates: Record<string, ParameterProvenance> = {};

  // Resolve each quantity independently: the runner reads BRENDA's KM
  // Values table for "km" and its Ki Values table for "ki", so each key
  // gets its own lookup and its own citation (ADR 0008). A cross-species
  // Ki therefore never borrows a verified Km's provenance.
  for (const key of kineticKeys) {
    // A Ki is the INHIBITOR's constant: BRENDA files it under the inhibitor.
    // With none named, nothing is looked up; before, the substrate's name
    // was used and the Ki came back as one "of" the substrate, or not at all.
    if (key === "ki" && !entities.inhibitor) {
      provenanceUpdates[key] = {
        origin: "default",
        unresolvedReason: "not_found",
        note:
          "No Ki was looked up: a Ki belongs to the inhibitor, and the query names none. " +
          'Name it ("... inhibition of lactate dehydrogenase by gossypol") or supply ki=.',
      };
      continue;
    }
    // A Ki is also the constant of ONE mechanism. The domain's mode goes
    // with the lookup, with the model's own substrate (the lookup's
    // `substrate` is the inhibitor), so the runner takes a row stating that
    // mechanism rather than the lowest value of any (KI_MODE_OF_DOMAIN).
    const inhibitionMode = key === "ki" ? KI_MODE_OF_DOMAIN[domain] : undefined;
    const agentResult = await resolveKineticValue({
      ...entities,
      ...(key === "ki" ? { substrate: entities.inhibitor } : {}),
      ...(inhibitionMode ? { inhibitionMode } : {}),
      ...(inhibitionMode && entities.substrate ? { modelSubstrate: entities.substrate } : {}),
      quantity: key as "km" | "ki",
      allowVariants,
      physiologicalReference,
      allowCrossSpecies,
    });

    if (!agentResult.found) {
      if (agentResult.source === "mode_withheld") {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "mode_withheld",
          agentResult.modesAvailable,
          undefined,
          undefined,
          undefined,
          inhibitionMode,
        );
      } else if (agentResult.source === "isoform_withheld") {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "isoform_withheld",
          agentResult.isoformsAvailable,
        );
      } else if (agentResult.source === "variant_withheld") {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "variant_withheld",
          agentResult.variantCandidatesAvailable,
        );
      } else if (agentResult.source === "cross_species_withheld") {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "cross_species_withheld",
          agentResult.crossSpeciesOrganismsAvailable,
        );
      } else if (agentResult.source === "cross_species_too_distant") {
        // The user DID opt in, and the check still refused. Reporting this
        // as "not found" would be the cruellest possible message: they
        // took the action the previous error asked for and got the same
        // wall back with no acknowledgement that anything changed.
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "cross_species_too_distant",
          agentResult.crossSpeciesOrganismsAvailable,
          agentResult.relatedness,
        );
      } else if (
        agentResult.source === "ec_ambiguous" ||
        agentResult.source === "ec_not_resolved"
      ) {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          agentResult.source,
          undefined,
          undefined,
          undefined,
          agentResult.ecCandidates,
        );
      } else {
        provenanceUpdates[key] = buildUnresolvedKineticProvenance(
          key,
          "not_found",
          undefined,
          undefined,
          agentResult.substratesAvailable,
        );
      }
      // THE OFFER GOES IN THE PROVENANCE NOTE, NOT IN A FLAG.
      //
      // The first attempt pushed a flag. A probe showed why that reaches
      // nobody: when a kinetic constant cannot be resolved and was not
      // supplied, `resolveQuery` THROWS `RequiredParametersMissingError`.
      // There is no response, so there are no flags to read — the papers
      // were unreachable by construction on the one path where they matter.
      //
      // `missingKeyDetails` promotes a note to the error when the key
      // carries an `unresolvedReason`, and that mechanism exists for
      // precisely this reasoning: telling a user the literature has
      // nothing, when it has something they could have had, is the
      // true-sounding-and-misleading shape treated as a defect everywhere
      // else here. Caterva holding papers it does not mention is that
      // sentence again.
      const offer = literatureCandidateNote(
        key,
        agentResult.literatureCandidates,
      );
      if (offer) {
        const existing = provenanceUpdates[key];
        provenanceUpdates[key] = {
          ...existing,
          unresolvedReason: existing?.unresolvedReason ?? "literature_candidates",
          // Appended, never replacing. Promoting a note strips the generic
          // sentence — including the "Add km=<value>" instruction — and
          // that instruction is still the thing the student must act on.
          note: [existing?.note, offer].filter(Boolean).join(" "),
        };
      }
      continue;
    }

    const located = locatableCitation(agentResult.citation);
    if (located === undefined) {
      provenanceUpdates[key] = buildUnresolvedKineticProvenance(key, "no_locator");
      flags.push(
        `Found a ${key.toUpperCase()} value but its citation was not locatable; using default ${key.toUpperCase()}.`,
      );
      continue;
    }
    const citation = located.display;

    const citationStatus =
      agentResult.crossSpecies === true ||
      agentResult.source === "brenda_cross_species"
        ? "flagged"
        : "verified";

    const valueKey = KINETIC_VALUE_MAP[key as keyof typeof KINETIC_VALUE_MAP];
    const value = agentResult[valueKey] as number | undefined;

    if (value !== undefined) {
      parameterUpdates[key] = value;
      const resolvedProvenance = buildResolvedKineticProvenance({
        parameterKey: key,
        source: agentResult.source ?? "unknown",
        citation,
        organism: agentResult.organism,
        citationStatus,
        assayConditions: toAssayConditions(agentResult.assayConditions, agentResult.effectors),
        citationLocators: buildCitationLocators(agentResult.citation),
      });

      // Bakker's graded axes ride alongside the binary citationStatus
      // rather than replacing it. citationStatus governs whether the run
      // may proceed (a policy); reliability describes how much to trust
      // the number that did (a description). Collapsing the two would make
      // a nuanced description into a gate, which is how "partial" evidence
      // would start blocking runs it should only be annotating.
      // THE RUNNER'S SCORE IS THE SCORE. This does not recompute it.
      //
      // It used to. `science_agent_runner.py` has always graded the value
      // on Bakker's three axes and emitted the result, and this line threw
      // that away and ran the TypeScript grader instead — with no
      // `reference` argument, because none was reachable here. The
      // proximity axis therefore returned `not_assessed` on every request
      // the API server ever served. Not sometimes: always.
      //
      // Meanwhile the CLI consumed the Python score and reported real
      // grades. Two front ends, one of them structurally incapable of the
      // answer, and a parity test asserting they agreed — because the test
      // pinned the two implementations against a shared fixture, which
      // says nothing about a call site that hands one of them different
      // arguments.
      //
      // Falling back to the TypeScript grader when the runner sends
      // nothing was considered and rejected. A second implementation kept
      // "just in case" is how this drift started, and a score computed by
      // the fallback would be indistinguishable in the response from one
      // computed by the resolver. Absent is reported as absent.
      if (agentResult.reliability) {
        resolvedProvenance.reliability = agentResult.reliability;
      }

      provenanceUpdates[key] = resolvedProvenance;
      flags.push(
        `Resolved ${key.toUpperCase()}=${value} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`,
      );
      // Pool-level findings ride alongside the resolution flag, not instead
      // of it. The value WAS resolved and IS cited; what these add is that
      // the pool it came from held something the reader should look at.
      flags.push(...poolFindingFlags(key, agentResult.poolFindings));
      flags.push(...selectionTieFlags(key, agentResult.selectionTie));
      flags.push(
        ...ensembleCandidateFlags(key, agentResult.ensembleCandidates),
      );
      flags.push(...selectedFormFlags(key, agentResult.selectedForm));
      flags.push(...preparationFlags(key, agentResult.preparation));
      flags.push(...rowScopeFlags(key, agentResult.rowScope, entities.isoform));
      // After what the row measured, because it qualifies it: another row,
      // which the runner set aside for stating another mode, says the
      // mechanism this model gives the row is not the inhibitor's against
      // this model's substrate.
      flags.push(...mechanismEvidenceFlags(key, agentResult.mechanismEvidence));
    } else {
      provenanceUpdates[key] = buildUnresolvedKineticProvenance(key, "not_found");
    }
  }

  // Apply accumulated changes
  return {
    parameters: { ...parameters, ...parameterUpdates },
    parameterProvenance: { ...parameterProvenance, ...provenanceUpdates },
    flags,
  };
}

/**
 * ADR 0019: bridge a literature-resolved kcat into a simulable Vmax, but
 * ONLY when the query explicitly supplied an enzyme concentration override
 * (`enzyme_conc=...`). [E]0 is never resolved, inferred, or defaulted here
 * (ADR 0013) — this function's entire job is to combine a real citation
 * with a caller-supplied number, never to invent the caller-supplied half.
 *
 * Deliberately NOT reached through RESOLVABLE_FIELDS / applyKineticResolution's
 * generic per-key loop: that loop assumes one BRENDA table maps directly to
 * one engine parameter (km -> km, ki -> ki), which does not hold for kcat ->
 * vmax (an arithmetic bridge, not a 1:1 lookup). Keeping this as its own
 * function avoids corrupting that loop's `key === "km" ? ... : ...` value
 * selection with a third case it was never designed for.
 *
 * If `vmax` is already present in `overrides`, this is a no-op — an
 * explicit user-supplied Vmax always wins and is never second-guessed by a
 * literature bridge.
 */
async function applyVmaxFromKcatResolution(
  entities: EntityExtraction | undefined,
  overrides: Record<string, number | number[]>,
  domain: string,
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  if (domain !== "mm" && domain !== "mm_competitive_inhibition") {
    return { parameters, parameterProvenance, flags };
  }
  if ("vmax" in overrides) {
    return { parameters, parameterProvenance, flags };
  }
  if (!entities?.ecNumber && !entities?.enzymeName) {
    return { parameters, parameterProvenance, flags };
  }
  const enzymeConcOverride = overrides["enzyme_conc"];
  if (typeof enzymeConcOverride !== "number") {
    // Say WHY, instead of returning in silence.
    //
    // Silence here left the refusal to the generic sentence, which told
    // the user "vmax could not be resolved from literature. Add
    // vmax=<value>" — advice that is both wrong about the literature and
    // wrong about the science. A Vmax copied from a paper was measured at
    // that paper's [E]0, and dropping it into a run at a different [E]0 is
    // wrong by the ratio of the two, invisibly. See the
    // `enzyme_conc_not_supplied` doc comment in provenance.ts.
    //
    // We know an enzyme was identified (checked just above), so the kcat
    // route genuinely exists for this query. It is not promised to
    // succeed — if BRENDA holds no kcat, the flag above says so — only
    // offered, which is the honest shape.
    const existing = parameterProvenance["vmax"];
    if (existing) {
      parameterProvenance = {
        ...parameterProvenance,
        vmax: {
          ...existing,
          unresolvedReason: "enzyme_conc_not_supplied",
          note:
            "Vmax is not a property of the enzyme on its own — it is " +
            "kcat × [E]0, so it depends on how much enzyme is in YOUR " +
            "assay. Caterva resolves kcat from literature, but [E]0 is " +
            "your experimental choice and is never guessed (ADR 0013). " +
            "State the enzyme concentration — e.g. \"with 50 nM enzyme\" " +
            "or enzyme_conc=0.00005 (mM) — and Vmax is derived and cited " +
            "for you. Copying a Vmax out of a paper instead would import " +
            "that paper's enzyme concentration along with it.",
        },
      };
    }
    return { parameters, parameterProvenance, flags };
  }

  const agentResult = await resolveKineticValue({
    ...entities,
    quantity: "kcat",
    enzymeConc: enzymeConcOverride,
  });

  // Each failure below ALSO writes its reason onto vmax's provenance, not
  // just into `flags`.
  //
  // Flags are attached to a successful result. When the bridge fails,
  // vmax stays origin "default", the hard block throws, and the flags go
  // with it -- so the system computed a specific, actionable reason and
  // then discarded it, leaving the user the generic "vmax could not be
  // resolved from literature". Measured on real queries: lactate
  // dehydrogenase and catalase both fail here, and neither told the user
  // which of these three things happened, though they need different
  // responses.
  const explainVmax = (
    reason: "not_found" | "no_locator" | "enzyme_conc_rejected",
    note: string,
  ): Record<string, ParameterProvenance> => {
    const existing = parameterProvenance["vmax"];
    if (!existing) return parameterProvenance;
    return {
      ...parameterProvenance,
      vmax: { ...existing, unresolvedReason: reason, note },
    };
  };

  if (!agentResult.found || agentResult.kcat === undefined) {
    flags.push(
      "Could not resolve a real kcat value from BRENDA/KEGG/PubMed; " +
        "Vmax was not bridged from literature.",
    );
    return {
      parameters,
      parameterProvenance: explainVmax(
        "not_found",
        "Vmax = kcat × [E]0, and your enzyme concentration was read, but " +
          "BRENDA, KEGG and PubMed hold no kcat for this enzyme — so there " +
          "is nothing to multiply it by. Supply kcat=<value> (in 1/s) and " +
          "Vmax is computed from it, or supply vmax=<value> directly. " +
          "Either way, attach the paper with --cite so the source is " +
          "recorded rather than lost.",
      ),
      flags,
    };
  }

  if (!agentResult.vmaxValidation?.ok || agentResult.vmax === undefined) {
    const reason = agentResult.vmaxValidation?.reason ?? "enzyme_conc rejected";
    flags.push(
      `Resolved kcat=${agentResult.kcat} 1/s but could not bridge it to a ` +
        `Vmax: ${reason}.`,
    );
    return {
      parameters,
      parameterProvenance: explainVmax(
        "enzyme_conc_rejected",
        `A literature kcat of ${agentResult.kcat} 1/s was found, but the ` +
          `enzyme concentration it would be multiplied by ` +
          `(${enzymeConcOverride} mM) was rejected: ${reason}. The kcat is ` +
          "not the problem here; check the enzyme concentration.",
      ),
      flags,
    };
  }

  const located = locatableCitation(agentResult.citation);
  if (located === undefined) {
    flags.push(
      "Resolved a kcat but its citation carries no locator (ref id or URL); " +
        "not trusted as resolved — Vmax was not bridged from literature.",
    );
    return {
      parameters,
      parameterProvenance: explainVmax(
        "no_locator",
        `A kcat of ${agentResult.kcat} 1/s was found for this enzyme, but ` +
          "its citation carries no reference id or URL — nothing a reader " +
          "could follow to check it. An uncheckable citation is not a " +
          "citation, so it was not used. Supply kcat=<value> or " +
          "vmax=<value> with --cite naming a source you can point at.",
      ),
      flags,
    };
  }
  const citation = located.display;

  const citationStatus =
    agentResult.crossSpecies === true || agentResult.source === "brenda_cross_species"
      ? "flagged"
      : "verified";

  const bridgeNote =
    `Vmax = kcat (${agentResult.kcat} 1/s, cited below) × enzyme_conc ` +
    `(${enzymeConcOverride} mM, supplied in the query — never resolved or ` +
    `defaulted, ADR 0013).` +
    (agentResult.vmaxValidation.flagged
      ? ` ${agentResult.vmaxValidation.reason ?? ""}`
      : "");

  parameters = { ...parameters, vmax: agentResult.vmax };
  parameterProvenance = {
    ...parameterProvenance,
    vmax: buildResolvedKineticProvenance({
      parameterKey: "vmax",
      source: agentResult.source ?? "unknown",
      citation,
      organism: agentResult.organism,
      citationStatus,
      assayConditions: toAssayConditions(agentResult.assayConditions, agentResult.effectors),
      citationLocators: buildCitationLocators(agentResult.citation),
      note: bridgeNote,
    }),
  };
  flags.push(
    `Bridged Vmax=${agentResult.vmax} mM/s from a literature kcat= ` +
      `${agentResult.kcat} 1/s and the enzyme_conc supplied in the query.`,
  );

  return { parameters, parameterProvenance, flags };
}

/**
 * ADR 0017 / ADR 0020: resolve a named disease's (R0, infectious period)
 * from the hand-verified registry and bridge it to the SIR engine's own
 * (beta, gamma) — the epidemiology counterpart of applyVmaxFromKcatResolution.
 *
 * Unlike the kcat bridge, this needs no caller-supplied half: R0 and
 * infectious period are both intrinsic disease properties, both resolved
 * from literature (ADR 0017's Context section explains why kcat's [E]0
 * situation does NOT apply here). The gate is simpler as a result: fires
 * whenever the domain is "sir", a disease name is recognized in the query
 * text, and neither `beta` nor `gamma` was already supplied by the caller
 * or the LLM. If either is already present, the bridge is skipped entirely
 * rather than mixing one literature-derived rate with one arbitrary
 * caller-chosen rate — beta and gamma come from the same internally
 * consistent source or neither does.
 *
 * Scoped to "sir" only, not "seir": ADR 0017's verification (the SIR peak
 * condition S(t_peak) = N/R0) was checked against the two-compartment SIR
 * model specifically; SEIR's extra exposed compartment changes what
 * "infectious period" as a generation-time proxy would even mean, and that
 * has not been checked.
 */
async function applyBetaGammaFromR0Resolution(
  query: string,
  overrides: Record<string, number | number[]>,
  domain: string,
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  // The domain list lives in provenance.ts beside RESOLVABLE_FIELDS, so
  // that DOMAINS_WITH_LITERATURE_RESOLUTION can be derived from it rather
  // than restating which domains have a resolver. A hardcoded
  // `domain !== "sir"` here would be a second copy of that fact, and the
  // two would drift the way the enzyme and domain-keyword lists did.
  if (!EPIDEMIOLOGY_BRIDGE_DOMAINS.has(domain)) {
    return { parameters, parameterProvenance, flags };
  }
  if ("beta" in overrides || "gamma" in overrides) {
    return { parameters, parameterProvenance, flags };
  }
  const disease = matchDisease(query);
  if (!disease) {
    // Not "literature has nothing for this disease" -- this system only
    // recognizes disease NAMES it has a verified, methodology-compatible
    // (R0, infectious period) source for in the first place (see
    // diseases.ts and ADR 0017), so a name outside that short list never
    // even reaches the literature lookup below. Previously silent: a
    // query naming a real disease (measles, influenza, ...) that
    // correctly reaches the sir domain would refuse on missing beta/gamma
    // via the generic "could not be resolved from literature" sentence --
    // false by omission for a real, well-studied disease that simply
    // isn't registered here yet, not one the literature has nothing on.
    // Set directly on beta/gamma (not just a flag, which never reaches
    // the RequiredParametersMissingError response the client actually
    // sees) so missingKeyDetails can promote it into the error message.
    // Names the registry's ACTUAL contents and, for measles, the specific
    // paper behind the refusal.
    //
    // This said "currently COVID-19 only, per ADR 0017" until ADR 0169
    // registered the two influenza entries — a refusal that misdescribes
    // what the system can do is its own small inaccuracy, in the message
    // a user reads when they are already blocked.
    //
    // The measles clause matters more than it looks. Measles is the
    // disease most people try after COVID, and its refusal is NOT "we
    // haven't got to it": Vink et al. (2014) supplies a measles serial
    // interval (11.7 d), so half the pair exists. It is unregistered
    // because Guerra et al. (2017), the standard R0 systematic review,
    // concludes estimates "vary more than the often cited range of 12-18"
    // and endorses no single value. Citing that is the product's own
    // promise applied to its own gaps.
    const measlesAsked = /\bmeasles\b/i.test(query);
    const note =
      "No disease name in this query matches Caterva's literature-backed " +
      "R0 registry (currently COVID-19, seasonal influenza, and influenza " +
      "A(H1N1)pdm09 -- see ADR 0017 and ADR 0169). This is a gap in what " +
      "this system has verified so far, not a statement that the " +
      "literature is silent. " +
      (measlesAsked
        ? "Measles specifically is not registered because Guerra et al. " +
          "(2017), Lancet Infect Dis 17(12):e420-e428, " +
          "doi:10.1016/S1473-3099(17)30307-9 -- the standard R0 systematic " +
          "review -- found that R0 estimates vary far more than the often " +
          "cited 12-18 range and endorses no single value, so no honest " +
          "default exists. Supply beta and gamma for YOUR setting. "
        : "") +
      "Supply beta/gamma directly if you have a source for this disease.";
    for (const key of ["beta", "gamma"] as const) {
      if (!(key in overrides)) {
        parameterProvenance = {
          ...parameterProvenance,
          [key]: {
            ...parameterProvenance[key],
            origin: parameterProvenance[key]?.origin ?? "default",
            unresolvedReason: "disease_not_registered",
            note,
          },
        };
      }
    }
    return { parameters, parameterProvenance, flags };
  }

  const agentResult = await resolveEpidemiologyParameters(disease.diseaseName);
  if (!agentResult.found) {
    flags.push(
      `Could not resolve real (R0, infectious period) literature values for ` +
        `'${disease.diseaseName}'; beta/gamma were not bridged from literature.`,
    );
    return { parameters, parameterProvenance, flags };
  }

  if (
    !agentResult.betaGammaValidation?.ok ||
    agentResult.beta === undefined ||
    agentResult.gamma === undefined
  ) {
    flags.push(
      `Resolved R0=${agentResult.r0} for '${agentResult.disease}' but could not ` +
        `bridge it to beta/gamma: ${agentResult.betaGammaValidation?.reason ?? "invalid inputs"}.`,
    );
    return { parameters, parameterProvenance, flags };
  }

  const located = locatableCitation(agentResult.citation);
  if (located === undefined) {
    flags.push(
      `Resolved R0 for '${agentResult.disease}' but its citation carries no ` +
        `locator; beta/gamma were not bridged from literature.`,
    );
    return { parameters, parameterProvenance, flags };
  }
  const citation = located.display;

  const bridgeNote =
    `beta and gamma derived from R0=${agentResult.r0} and infectious_period=` +
    `${agentResult.infectiousPeriodDays} days for '${agentResult.disease}' ` +
    `(gamma = 1/infectious_period, beta = R0 * gamma).` +
    (agentResult.betaGammaValidation.flagged
      ? ` ${agentResult.betaGammaValidation.reason ?? ""}`
      : "");

  // beta/gamma are not STRENDA-governed (a disease has no assay pH), which
  // buildResolvedKineticProvenance now handles itself via parameterKey —
  // see ADR 0021.
  //
  // citationStatus was unconditionally "verified" here, on the reasoning
  // that the registry had no flagged tier to select between (ADR 0017,
  // when COVID-19 was the only entry and both its numbers came from one
  // paper). ADR 0169 adds that tier: an entry whose R0 and serial
  // interval come from two different systematic reviews is a CROSS-STUDY
  // COMPOSITE, and is flagged for the same reason a cross-species BRENDA
  // Km is — usable and cited, but visibly weaker than a single-source
  // value. Letting a composite inherit "verified" would erase the only
  // signal that two methodologies were combined.
  const composite = agentResult.crossStudyComposite === true;
  const secondary = locatableCitation(agentResult.secondaryCitation);

  // BOTH papers go in the citation string. A composite that displayed only
  // the R0 paper would read as single-source at exactly the layer built
  // for checking.
  //
  // The LOCATORS stay primary-only, deliberately. validateParameterProvenance
  // requires every locator to be findable in the citation string, and
  // buildCitationLocators emits a PubMed locator whose value is a PMID
  // while the citation carries a doi.org URL — so the secondary's locators
  // are not string-matchable here and adding them fails that check. That
  // check is right and is not being weakened to fit this feature: the
  // second paper reaches the reader through the citation text and the
  // note, and the machine-followable set stays honest about what it can
  // actually verify.
  const displayCitation =
    composite && secondary
      ? `${citation} + serial interval from ${secondary.display}`
      : citation;

  const fullNote = composite
    ? `${bridgeNote} ${agentResult.compositeNote ?? ""}`.trim()
    : bridgeNote;

  parameters = { ...parameters, beta: agentResult.beta, gamma: agentResult.gamma };
  const provenanceEntry = buildResolvedKineticProvenance({
    parameterKey: "beta",
    source: agentResult.source ?? "PubMed",
    citation: displayCitation,
    citationStatus: composite ? "flagged" : "verified",
    citationLocators: buildCitationLocators(agentResult.citation),
    note: fullNote,
  });
  parameterProvenance = {
    ...parameterProvenance,
    beta: provenanceEntry,
    gamma: provenanceEntry,
  };
  flags.push(
    `Bridged beta=${agentResult.beta}, gamma=${agentResult.gamma} from ` +
      `literature R0 and infectious period for '${agentResult.disease}'.`,
  );

  return { parameters, parameterProvenance, flags };
}

/**
 * Apply population genetics parameter resolution from literature.
 * Currently supports mutation_rate for Wright-Fisher domains.
 */
async function applyPopgenResolution(
  entities: EntityExtraction | undefined,
  overrides: Record<string, number | number[]>,
  domain: string,
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const popgenKeys = resolvable.filter((k) => !(k in overrides));
  if (popgenKeys.length === 0) {
    return { parameters, parameterProvenance, flags };
  }

  // Accumulate updates to avoid repeated object spreading
  const parameterUpdates: Record<string, number | number[]> = {};
  const provenanceUpdates: Record<string, ParameterProvenance> = {};

  // For now, only mutation_rate is supported
  if (popgenKeys.includes("mutation_rate") && entities?.organism) {
    const agentResult = await resolveKineticValue({
      ...entities,
      parameterType: "mutation_rate",
    });

    if (agentResult.found && agentResult.km !== undefined) {
      const value = agentResult.km;
      const located = locatableCitation(agentResult.citation);

      if (located !== undefined) {
        const citation = located.display;
        parameterUpdates["mutation_rate"] = value;
        // mutation_rate is a per-generation per-base-pair substitution
        // rate, not an enzyme kinetic constant: STRENDA does not govern it
        // and it has no assay pH or temperature. buildResolvedKineticProvenance
        // now enforces that itself via the mandatory parameterKey.
        //
        // Before that fix, this call unconditionally stamped a strendaStatus
        // here, which validateParameterProvenance rejects as a hard
        // violation and provenanceViolations THROWS on -- so every
        // successfully-resolved mutation_rate crashed resolveQuery() with
        // "Internal error: invalid parameter provenance". Never caught by
        // CI because stdpopsim is absent from the test sandbox, so the
        // popgen resolver always returned found=false and this branch never
        // executed. See ADR 0021.
        provenanceUpdates["mutation_rate"] = buildResolvedKineticProvenance({
          parameterKey: "mutation_rate",
          source: agentResult.source ?? "unknown",
          citation,
          organism: agentResult.organism,
          citationStatus: "verified",
          citationLocators: buildCitationLocators(agentResult.citation),
        });
        flags.push(
          `Resolved mutation_rate=${value} from ${agentResult.source ?? "literature"}.`,
        );
      } else {
        provenanceUpdates["mutation_rate"] = {
          origin: "default",
          note: "Found a mutation_rate value but its citation carries no locator; using default.",
        };
      }
    } else {
      provenanceUpdates["mutation_rate"] = {
        origin: "default",
        note: "Could not resolve a real mutation_rate value from literature; using default.",
      };
    }
  }

  // Apply accumulated changes
  return {
    parameters: { ...parameters, ...parameterUpdates },
    parameterProvenance: { ...parameterProvenance, ...provenanceUpdates },
    flags,
  };
}

export interface ResolvedSimulation {
  runId: string;
  domain: SimulationDomain;
  parameters: Record<string, number | number[]>;
  provenance: {
    reasoning: string;
    modelCitations: string[];
    flags: string[];
  };
  parameterProvenance: Record<string, ParameterProvenance>;
  /**
   * Whether the resolved parameters could have come from one experiment.
   *
   * Separate from `parameterProvenance` because it is not a property of any
   * single parameter — it is a property of the set, and there is nowhere
   * else for it to live. See assayCoherence.ts and ADR 0026.
   */
  assayCoherence: CoherenceReport;
}

/**
 * Splits text into lowercase word tokens for keyword matching. Kept
 * separate from `extractParameterOverrides`'s tokenizer above: that one
 * preserves punctuation meaningful to key=value syntax, this one only
 * needs plain words.
 */
function tokenizeForMatching(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 0);
}

/**
 * Deliberately not a real stemmer (no Porter algorithm, no dictionary) --
 * just enough suffix-stripping that a plural doesn't silently miss a
 * singular keyword, or vice versa. "allele frequencies" failing to match
 * the keyword "allele frequency" is the exact bug this exists to close:
 * every other part of the query was right, only the word ending differed.
 */
function lightStem(word: string): string {
  if (word.length > 4 && word.endsWith("ies")) return word.slice(0, -3) + "y";
  if (word.length > 4 && word.endsWith("es")) return word.slice(0, -2);
  if (word.length > 3 && word.endsWith("s") && !word.endsWith("ss")) {
    return word.slice(0, -1);
  }
  return word;
}

/**
 * Whether `keyword` matches the query, tried two ways:
 *
 * 1. Exact substring (the original, stricter check) -- keeps every
 *    existing single-word keyword and deliberately-phrased multi-word
 *    keyword ("lennard-jones") working exactly as before.
 * 2. Word-set match: every word in the keyword phrase appears SOMEWHERE
 *    among the query's tokens (order-independent, lightly stemmed). This
 *    is what makes "predator and prey" match the keyword "predator prey"
 *    and "allele frequencies in a population" match "allele frequency" --
 *    real phrasings that failed the old exact-substring check for no
 *    reason connected to whether the query was actually about that domain.
 *
 * A single-word keyword with no match in either query token set correctly
 * fails both checks; word-set matching only helps once a keyword has two
 * or more words to spread across the query.
 */
function keywordMatches(
  lowerQuery: string,
  queryTokens: Set<string>,
  keyword: string,
): boolean {
  if (lowerQuery.includes(keyword)) return true;
  const keywordWords = tokenizeForMatching(keyword);
  return (
    keywordWords.length > 0 &&
    keywordWords.every((w) => queryTokens.has(lightStem(w)))
  );
}

interface DomainDefaults {
  domain: SimulationDomain;
  parameters: Record<string, number | number[]>;
  keywords: string[];
  reasoning: string;
  modelCitations: string[];
}

const DOMAIN_DEFAULTS: DomainDefaults[] = [
  {
    domain: "mm_competitive_inhibition",
    parameters: {
      km: 2,
      ki: 1.0,
      vmax: 5,
      s0: 10,
      i0: 0.1,
      end: 10,
      points: 51,
    },
    keywords: [
      "competitive inhibition",
      "competitive",
      "inhibition",
      "inhibitor",
    ],
    reasoning:
      "Keywords related to enzyme kinetics with competitive inhibition were found; defaulting to a Michaelis-Menten competitive inhibition simulation.",
    // The paper that DEFINES this model, plus the steady-state derivation
    // the competitive form rests on. See the note on `mm` below for why
    // BRENDA is no longer listed here.
    modelCitations: [
      "Michaelis L., Menten M.L. (1913) Die Kinetik der Invertinwirkung. Biochemische Zeitschrift 49, 333-369. English translation: Johnson K.A., Goody R.S. (2011) Biochemistry 50(39), 8264-8269. https://doi.org/10.1021/bi201284u",
      "Briggs G.E., Haldane J.B.S. (1925) A note on the kinetics of enzyme action. Biochemical Journal 19(2), 338-339. https://doi.org/10.1042/bj0190338",
    ],
  },
  {
    domain: "mm",
    parameters: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
    keywords: [
      "enzyme",
      "michaelis",
      "km",
      "vmax",
      "substrate",
      "ldh",
      "pyruvate",
      "lactate",
      "hexokinase",
      "catalase",
      "alcohol dehydrogenase",
      "trypsin",
      "rubisco",
      "kinase",
      "kinetics",
      "enzymatic",
      "catalyze",
      "catalyzes",
      "catalyzed",
      "reaction rate",
      "turnover",
    ],
    reasoning:
      "Keywords related to enzyme kinetics were found; defaulting to a Michaelis-Menten simulation.",
    // BRENDA used to be the ONLY entry here, and it was wrong twice over.
    //
    // ADR 0008: `modelCitations` describes the MODEL, never a parameter
    // value. Every other domain in this table cites the paper that defines
    // its model -- Kermack & McKendrick for SIR, Gillespie for the SSA,
    // Lotka for Lotka-Volterra, Elowitz & Leibler for the repressilator.
    // These two cited a database, so the two domains most central to this
    // project were the only ones whose model was uncited.
    //
    // And these `parameters` are hardcoded defaults (km 2, vmax 5) used
    // when nothing resolved. On that path BRENDA supplied nothing, so
    // naming it credited a source for numbers it had no part in -- the same
    // false-provenance claim ADR 0063 refuses in the attribution block, and
    // under CC BY 4.0 2(a)(6) the endorsement the licence forbids implying.
    //
    // BRENDA is credited where it actually contributes: per parameter, in
    // `parameterProvenance`, and in the exported model's attribution block.
    modelCitations: [
      "Michaelis L., Menten M.L. (1913) Die Kinetik der Invertinwirkung. Biochemische Zeitschrift 49, 333-369. English translation: Johnson K.A., Goody R.S. (2011) Biochemistry 50(39), 8264-8269. https://doi.org/10.1021/bi201284u",
    ],
  },
  {
    domain: "gillespie_ssa_replicates",
    parameters: { a0: 100, k: 0.5, end: 10, n_replicates: 100 },
    keywords: ["replicates", "many seeds", "multiple runs", "ensemble"],
    reasoning:
      "Keywords related to repeated independent runs were found; defaulting to a Gillespie SSA ensemble view over n_replicates seeded trajectories.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
  {
    domain: "gillespie_ssa_bimolecular",
    parameters: { a0: 100, b0: 100, k: 0.005, end: 10 },
    keywords: [
      "bimolecular",
      "second order",
      "second-order",
      "association",
      "two reactants",
      "a + b",
      "a plus b",
      "binding",
    ],
    reasoning:
      "Keywords related to a two-reactant association were found; defaulting to a Gillespie SSA simulation of the bimolecular reaction A + B -> C.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
  {
    domain: "gillespie_ssa",
    parameters: { a0: 1000, k: 0.5, end: 10 },
    keywords: [
      "gillespie",
      "stochastic",
      "ssa",
      "chemical master equation",
      "decay",
      "reaction",
      "random walk",
      "birth-death",
    ],
    reasoning:
      "Keywords related to stochastic chemical kinetics were found; defaulting to a Gillespie SSA simulation of a single first-order decay reaction.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
];

const PARAMETER_NAMES =
  "km|ki|vmax|kcat|enzyme_conc|s0|beta|gamma|sigma|e0|i0|r0|r0_recovered|end|points|n0|efficiency|cycles|n_samples|population_size|starting_frequency|starting_frequencies|generations|replicate_runs|mutation_rate|selection_coefficient|recombination_rate|n_particles|temperature|timestep|n_steps|density|a0|b0|k|n_replicates|seed|alpha|delta|p0|v0";

/**
 * Matches a parameter token: the key name, an optional `=` or `:`
 * delimiter, and the value portion (which may be a scalar or a
 * comma-separated array).
 */
const PARAMETER_TOKEN_PATTERN = new RegExp(
  `^(${PARAMETER_NAMES})\\s*[=:]\\s*(.+)$`,
  "i",
);

/** Scalar: km=5, vmax 10, beta = 0.4
 *
 * ANCHORED (`^...$`), and that is load-bearing. Unanchored, this matched a
 * parameter name appearing ANYWHERE inside a whitespace-delimited token,
 * so any word ending in a digit was harvested as a user-supplied override:
 *
 *     "...decay of CDK1 a0=100"   ->  { k: 1, ... }    // k from a protein name
 *     "...decay of ERK2 a0=100"   ->  { k: 2, ... }
 *     "simulate backend2 ..."     ->  { end: 2 }
 *
 * The overrides were then stamped `origin: "user"`, so `unverifiedOriginKeys`
 * saw nothing to block and the simulation ran with a rate constant read off
 * a protein's NAME. That defeats the entire hard rule (ADR 0008): the point
 * is that no value nobody chose reaches the engine, and this minted values
 * out of arbitrary text while reporting them as deliberate user input. It
 * changed the scientific answer silently rather than failing loudly, which
 * is the worst available failure mode.
 *
 * Anchoring costs nothing real: callers are already split on whitespace
 * before this runs, so a delimiter-less pair ("km 5") could never reach it
 * anyway -- queryOverrides.test.ts pins that it returns {}.
 */
const PARAMETER_PATTERN = new RegExp(
  `^(${PARAMETER_NAMES})\\s*[=:]?\\s*([0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?)$`,
  "i",
);

/**
 * A token that is a known parameter name and NOTHING else -- no digits, no
 * `=`/`:` attached. Used to detect "km 5" style pairs, where the name and
 * the value are two SEPARATE whitespace-split tokens.
 *
 * `PARAMETER_PATTERN` above already makes its `[=:]?` optional, which reads
 * as if it were meant to catch this shape -- and its own "Fallback" comment
 * gives "km 5" as the worked example. It cannot: `query.split(/\s+/)`
 * yields "km" and "5" as two independent tokens, and a regex tested against
 * one token can never see the next one. No amount of rewriting that single
 * regex fixes this; the extraction loop has to look at the PAIR.
 */
const BARE_PARAMETER_NAME_PATTERN = new RegExp(`^(${PARAMETER_NAMES})$`, "i");

/** A bare numeric token: "5", "0.4", "1e-3" -- no key, no unit suffix. */
const BARE_NUMBER_PATTERN = /^[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$/i;

/**
 * Validation errors for malformed array overrides.
 */
export class ArrayOverrideValidationError extends Error {
  constructor(
    public readonly key: string,
    message: string,
  ) {
    super(message);
    this.name = "ArrayOverrideValidationError";
  }
}

/**
 * Parse a single comma-separated value string into a number array.
 * Returns undefined if the string contains no commas (meaning it should
 * be treated as a scalar, not an array).
 *
 * For array parameters, validation happens in `validateArrayOverride()`
 * after parsing — this function only extracts the raw numbers.
 */
function parseArrayValue(raw: string): number[] | undefined {
  const trimmed = raw.replace(/^\[|\]$/g, "").trim();
  if (!trimmed.includes(",")) return undefined;
  const parts = trimmed.split(",").map((s) => s.trim());
  if (parts.length === 0 || parts.some((s) => s === "")) return undefined;
  const nums = parts.map((s) => Number.parseFloat(s));
  if (!nums.every((n) => Number.isFinite(n))) return undefined;
  return nums;
}

/**
 * Known array-valued parameters and their validation constraints.
 *
 * Each entry specifies:
 *  - `length`: exact number of elements required
 *  - `sumTo`: if set, the elements must sum to this value within tolerance
 *  - `tolerance`: float tolerance for the sum check (default 1e-6)
 *
 * Mutation-test note (Rule 6): the sum tolerance is guarded by the array
 * override suite. Mutating `1e-6` -> `1e6` is caught by 4 tests across
 * arrayOverride.test.ts, provenance.test.ts, and queryOverrides.test.ts
 * ("rejects ... that sum to 0.9" / "do not sum to 1" / "rejects array that
 * doesn't sum to 1" / "rejects sum!=1"); the mutation was run and reverted.
 */
const ARRAY_VALIDATORS: Record<
  string,
  { length: number; sumTo?: number; tolerance?: number }
> = {
  starting_frequencies: { length: 4, sumTo: 1, tolerance: 1e-6 },
};

/**
 * Validate an array override against its declared constraints.
 * Throws `ArrayOverrideValidationError` with a clear, actionable message
 * if validation fails.
 */
function validateArrayOverride(key: string, arr: number[]): void {
  const spec = ARRAY_VALIDATORS[key];
  if (!spec) {
    throw new ArrayOverrideValidationError(
      key,
      `'${key}' is not an array-valued parameter. ` +
        `Remove the commas or use a valid array parameter.`,
    );
  }

  if (arr.length !== spec.length) {
    throw new ArrayOverrideValidationError(
      key,
      `${key} must have exactly ${spec.length} values (${arr.length} provided). ` +
        `Example: ${key}=${Array(spec.length).fill("0.25").join(",")}`,
    );
  }

  if (spec.sumTo !== undefined) {
    const sum = arr.reduce((a, b) => a + b, 0);
    const tolerance = spec.tolerance ?? 1e-6;
    if (Math.abs(sum - spec.sumTo) > tolerance) {
      throw new ArrayOverrideValidationError(
        key,
        `${key} values must sum to ${spec.sumTo} (got ${sum.toPrecision(6)}). ` +
          `Haplotype frequencies must sum to 1.0.`,
      );
    }
  }
}

/**
 * Extract numeric overrides from the query string.
 *
 * Supports both scalar and array-valued parameters:
 *   - Scalar: "km=5", "vmax 10", "beta = 0.4"
 *   - Array:  "starting_frequencies=0.5,0,0,0.5"
 *            "starting_frequencies=[0.5,0,0,0.5]"
 *
 * Array syntax requires `=` or `:` so it cannot be confused with a scalar
 * followed by unrelated text.
 */
export function extractParameterOverrides(
  query: string,
): Record<string, number | number[]> {
  const overrides: Record<string, number | number[]> = {};

  // --- Array overrides: scan the RAW query first -------------------------
  //
  // Tokenization splits on whitespace, which breaks `key=a, b, c, d` apart
  // into `key=a,` `b,` `c,` `d`. Scanning the raw query with a dedicated
  // pattern captures the full comma-separated group regardless of spaces.
  const arrayKeys = new Set<string>();
  for (const [key, spec] of Object.entries(ARRAY_VALIDATORS)) {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const arrayRe = new RegExp(
      `${escapedKey}\\s*[=:]\\s*\\[?([0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?(?:\\s*,\\s*[0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?)+)\\]?`,
      "i",
    );
    const m = arrayRe.exec(query);
    if (m) {
      const arr = parseArrayValue(m[1]!);
      if (arr !== undefined) {
        validateArrayOverride(key, arr);
        overrides[key] = arr;
        arrayKeys.add(key);
      }
    }
  }

  // --- Scalar / token-based extraction ----------------------------------
  //
  // Keys already captured as arrays are skipped so a partial token
  // (e.g. `starting_frequencies=0.5,` from a space-split list) cannot
  // overwrite the validated array with a scalar.
  const tokens = query.split(/\s+/);
  for (let tokenIdx = 0; tokenIdx < tokens.length; tokenIdx++) {
    const token = tokens[tokenIdx]!;
    // Try key=value or key:value pattern first
    const kvMatch = PARAMETER_TOKEN_PATTERN.exec(token);
    if (kvMatch) {
      const key = kvMatch[1]!.toLowerCase();
      if (arrayKeys.has(key)) continue;

      const rawValue = kvMatch[2]!;

      // If the value contains commas or brackets, it MUST be an array.
      // Do not fall back to scalar — a malformed array is rejected.
      if (rawValue.includes(",") || /\[/.test(rawValue)) {
        const arr = parseArrayValue(rawValue);
        if (arr !== undefined) {
          validateArrayOverride(key, arr);
          overrides[key] = arr;
        } else {
          throw new ArrayOverrideValidationError(
            key,
            `'${key}' value '${rawValue}' is not a valid comma-separated number list. ` +
              `Example: ${key}=0.5,0,0,0.5`,
          );
        }
        continue;
      }

      // Scalar parse — but only if this key is not an array parameter.
      // An array parameter supplied without commas (e.g. starting_frequencies=0.5)
      // is malformed and must be rejected, not silently accepted as a scalar.
      if (ARRAY_VALIDATORS[key] === undefined) {
        const value = Number.parseFloat(rawValue);
        if (Number.isFinite(value)) {
          overrides[key] = value;
          continue;
        }
      } else {
        // Array parameter supplied as scalar — reject with actionable message.
        throw new ArrayOverrideValidationError(
          key,
          `'${key}' requires a comma-separated list (e.g. ${key}=0.5,0,0,0.5), ` +
            `not a single number.`,
        );
      }
    }

    // Fallback: try scalar match without explicit delimiter (e.g. "km5",
    // glued with no space at all).
    const scalarMatch = PARAMETER_PATTERN.exec(token);
    if (scalarMatch) {
      const key = scalarMatch[1]!.toLowerCase();
      if (arrayKeys.has(key)) continue;
      const value = Number.parseFloat(scalarMatch[2]!);
      if (Number.isFinite(value)) {
        overrides[key] = value;
      }
      continue;
    }

    // Fallback: "km 5" -- name and value as two separate tokens, the shape
    // this function's own docstring and the "Fallback" comment above both
    // promised and neither could deliver, because a single-token regex
    // cannot see the next token. Consuming the pair here is what makes it
    // real. Only a BARE name (no `=`/`:`/digits already on it -- ruled out
    // by every branch above reaching here) followed by a BARE number
    // qualifies, so "km=5 10" or "beta: x" cannot accidentally pair with
    // an unrelated neighboring number.
    if (BARE_PARAMETER_NAME_PATTERN.test(token) && tokenIdx + 1 < tokens.length) {
      const key = token.toLowerCase();
      const nextToken = tokens[tokenIdx + 1]!;
      if (!arrayKeys.has(key) && BARE_NUMBER_PATTERN.test(nextToken)) {
        if (ARRAY_VALIDATORS[key] === undefined) {
          const value = Number.parseFloat(nextToken);
          if (Number.isFinite(value)) {
            overrides[key] = value;
            tokenIdx++; // consume the value token so it is not re-scanned
          }
        }
        // An array parameter named bare ("starting_frequencies 0.5") is
        // left unmatched here rather than rejected: unlike `key=0.5`,
        // typing the name and a lone number with a space is at least as
        // likely to be prose ("starting_frequencies 0.5 each" is not
        // natural) as an attempted override, so silence is safer than an
        // error a plain sentence could trigger by coincidence.
      }
    }
  }

  return overrides;
}

/**
 * Words that are never themselves the name of the enzyme being asked
 * about -- either generic query scaffolding, or (derived below) one of the
 * single words making up a DOMAIN_DEFAULTS keyword phrase (e.g.
 * "competitive"/"inhibition" from "competitive inhibition").
 */
const QUERY_CONNECTOR_WORDS = new Set([
  "simulate", "run", "the", "a", "an", "of", "for", "please", "with",
  "and", "to", "in", "on", "model", "reaction", "compute", "calculate",
  "show", "me", "kinetics", "kinetic", "using", "via", "estimate", "study",
  "analyze", "analyse", "dynamics", "system", "process",
]);

let cachedDomainKeywordWords: Set<string> | undefined;
function domainKeywordWords(): Set<string> {
  if (!cachedDomainKeywordWords) {
    cachedDomainKeywordWords = new Set(
      DOMAIN_DEFAULTS.flatMap((d) => d.keywords.flatMap((k) => k.split(/\s+/))),
    );
  }
  return cachedDomainKeywordWords;
}

/**
 * Best-effort enzyme-name guess from free text, used only when the
 * hardcoded `enzymes.ts` pattern list doesn't match anything.
 *
 * This is NOT a real named-entity extractor -- it strips known query
 * scaffolding and domain-routing keywords and returns whatever text is
 * left. It can guess wrong (e.g. it will mis-extract a genuinely novel
 * enzyme name that happens to share a word with a domain keyword, like
 * "kinase"). That is an acceptable failure mode here specifically because
 * the guess is never treated as ground truth: it is handed to a live
 * UniProt name search (science_agent_runner.py), which either resolves a
 * real EC number or comes back honestly empty. A wrong guess costs one
 * failed lookup; it never fabricates a parameter value.
 */
function guessEnzymeNameFromQuery(query: string): string | undefined {
  const domainWords = domainKeywordWords();
  const words = query
    .split(/\s+/)
    .filter((token) => !PARAMETER_TOKEN_PATTERN.test(token) && !PARAMETER_PATTERN.test(token))
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !QUERY_CONNECTOR_WORDS.has(w) && !domainWords.has(w));
  if (words.length === 0) return undefined;
  return words.join(" ");
}

/**
 * Fallback entity extraction when no LLM is configured (or the LLM path
 * didn't run).
 *
 * First tries the hardcoded `enzymes.ts` pattern list -- fast, and already
 * carries a verified EC number/substrate/organism with no network round
 * trip. If that list doesn't match, this used to give up entirely, which
 * meant only those ~30 enzymes could ever reach a real BRENDA lookup.
 * Instead it now falls through to a best-effort name guess with no EC
 * number; `resolveKineticValue` (scienceAgent.ts) passes that name to the
 * Python bridge, which resolves an EC number for it live via UniProt
 * before attempting BRENDA -- see science_agent_runner.py::resolve_ec_number.
 */
const NOT_AN_INHIBITOR = new Set([
  "a", "an", "the", "its", "this", "that", "competitive", "noncompetitive", "uncompetitive",
  "mixed", "product", "substrate", "feedback", "allosteric", "an", "some",
]);

/**
 * The inhibitor a query names, or undefined. Recognises "... inhibition of
 * X by Y", "inhibited by Y", "with Y as (an) inhibitor", "inhibitor Y" and
 * "Y inhibitor". Returns undefined rather than guessing: an unnamed
 * inhibitor means no Ki is looked up, never a Ki looked up under the
 * substrate's name.
 */
/**
 * The isoform a query names: "isozyme 2", "isoform LDH-A", "isoform MAO B",
 * or a code like "LDH-A", "MAO B" or "HK-II". Undefined when none is named.
 *
 * Spelled as caterva.bind.core.read_isoform spells a row's reading, so the
 * runner's filter and rowScopeFlags compare like with like: an abbreviation
 * BRENDA writes codes after (LDH, MAO, HK, HXK) and its code, joined by a
 * hyphen whatever joined them ("MAO B" is "MAO-B"). Until 2026-09-30 this
 * took one token after the keyword, so "isoform MAO B" was sent as "MAO",
 * which names no row; the row reader had the same defect. A code the keyword
 * leaves alone ("hexokinase isozyme 2" sends "2") is sent as it is: the
 * runner (caterva.bind.core.same_isoform) and rowScopeFlags (sameIsoform)
 * take a code alone as that code after the enzyme's abbreviation, so "2"
 * finds the rows written "HK2".
 *
 * It reads fewer forms than the row reader, which also takes a full enzyme
 * name and a code ("hexokinase II") and codes run together ("HK1"): in a
 * query those are as often the enzyme itself ("hexokinase 2 in yeast" names
 * yeast's second hexokinase, or a question about hexokinase), and an isoform
 * read where none was meant filters every constant by it.
 */
const ISOFORM_STEM = String.raw`(?:HXK|LDH|MAO|HK)`;
const ISOFORM_CODE = String.raw`(?:P?(?:VI{0,3}|IV|I{1,3})[a-c]?|[A-Z]\d?(?:[A-Z]\d)*|\d{1,2})`;
const STEM_AND_CODE = new RegExp(String.raw`(?<![\w-])(${ISOFORM_STEM})[ -](${ISOFORM_CODE})(?![\w-])`, "g");
const ISOFORM_KEYWORD = /\b(?:isozyme|isoenzyme|isoform)s?\s+/i;
/** A code right after these words is a strain ("E. coli XL-1 Blue", "strain HK-1"). */
const STRAIN_CONTEXT = /(?:\bcoli|\bstrains?)\s+$/i;
/**
 * Upper-case prefixes of hyphenated codes that name no protein: cofactors,
 * nucleotides, "EC-" and nucleic acids ("inhibition by NAD-H"). The row
 * reader's `_NOT_A_STEM`.
 */
const NOT_A_STEM = new Set([
  "EC", "NAD", "NADH", "NADP", "FAD", "FMN", "ATP", "ADP", "AMP", "GTP", "GDP", "CTP",
  "UTP", "ITP", "DNA", "RNA", "PEG", "SDS",
]);
/** Greek letters written out: the one lower-case form an isoform's name takes ("isoform alpha"). */
const GREEK_NAMES = new Set([
  "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
  "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi",
  "psi", "omega",
]);
/** Capitalised words that open a sentence and are not a name ("Isoform The"). */
const FUNCTION_WORDS = new Set([
  "an", "and", "as", "at", "by", "for", "from", "in", "is", "not", "of", "or", "the",
  "to", "was", "were", "with",
]);

/**
 * Whether the token after "isoform", "isozyme" or "isoenzyme" names one, by
 * the row reader's rule (caterva.bind.core `_is_a_name`): it holds a capital
 * or a digit ("A", "H4", "II", "2") or is a Greek letter's name. A
 * lower-case word is the sentence going on ("the isoform of LDH", "all
 * isozymes tested"). This compared the lower-cased token with a list that
 * held "a", so "LDH isoform A" named no isoform while "isoform B" named B.
 */
function isAnIsoformName(token: string): boolean {
  if (GREEK_NAMES.has(token.toLowerCase())) return true;
  if (!/[A-Z0-9]/.test(token)) return false;
  return token.length === 1 || !FUNCTION_WORDS.has(token.toLowerCase());
}

export function extractIsoform(query: string): string | undefined {
  const keyword = query.match(ISOFORM_KEYWORD);
  if (keyword && keyword.index !== undefined) {
    const rest = query.slice(keyword.index + keyword[0].length);
    const named = rest.match(new RegExp(`^${STEM_AND_CODE.source}`));
    if (named) return `${named[1]}-${named[2]}`;
    const token = rest.match(/^[A-Za-z0-9][A-Za-z0-9-]*/);
    if (token && isAnIsoformName(token[0])) return token[0];
  }
  // Excluded as the row reader excludes them: a strain ("coli HK1"), a
  // longer hyphenated name ("RO-28-1675"), a cofactor ("NAD-H").
  for (const named of query.matchAll(STEM_AND_CODE)) {
    if (!STRAIN_CONTEXT.test(query.slice(0, named.index))) return `${named[1]}-${named[2]}`;
  }
  for (const code of query.matchAll(/(?<![\w-])([A-Z]{2,5})-([A-Z0-9]{1,2})(?![\w-]|\.\d)/g)) {
    if (NOT_A_STEM.has(code[1]) || STRAIN_CONTEXT.test(query.slice(0, code.index))) continue;
    return code[0];
  }
  return undefined;
}

export function extractInhibitor(query: string): string | undefined {
  const word = "([a-z0-9][\\w\\-()\\[\\],'+]*(?:\\s+acid)?)";
  const patterns = [
    new RegExp(`\\binhibit(?:ed|ion|or|s)?\\b[^.;]*?\\bby\\s+${word}`, "i"),
    new RegExp(`\\b(?:with|using|plus)\\s+${word}\\s+as\\s+(?:an?\\s+)?inhibitor`, "i"),
    new RegExp(`\\binhibitor\\s+${word}`, "i"),
    new RegExp(`\\b${word}\\s+(?:as\\s+)?(?:an?\\s+)?inhibitor\\b`, "i"),
  ];
  for (const p of patterns) {
    const m = query.match(p);
    const name = m?.[1]?.trim().replace(/[.,;]+$/, "");
    if (name && !NOT_AN_INHIBITOR.has(name.toLowerCase())) return name;
  }
  return undefined;
}

function extractEntitiesFromQuery(query: string): EntityExtraction | undefined {
  // The organism the query NAMES wins over the table's default.
  //
  // This function never looked at the query for one. Measured before
  // organisms.ts existed: "simulate hexokinase in E. coli with glucose"
  // returned km 6 mM with organism "Homo sapiens", source
  // "brenda_exact", citationStatus "verified" -- the named species
  // discarded, and a human value badged as an EXACT MATCH for a species
  // nobody asked about.
  //
  // That is worse than the case ADR 0024 exists for. A real cross-species
  // value is withheld unless opted into and arrives flagged, because
  // kinetic constants are species-specific. That machinery never fired
  // here: from its point of view the requested organism matched, because
  // the request had been rewritten to match.
  //
  // `undefined` from matchOrganism is a real answer -- no organism was
  // named -- so the existing default stands rather than being replaced by
  // a guess.
  const namedOrganism = matchOrganism(query);

  const matched = matchEnzyme(query);
  if (matched) {
    // Look for the substrate OUTSIDE the enzyme's own name. "lactate
    // dehydrogenase" contains "lactate", and reading it as the substrate made
    // every LDH query a lactate query whatever it said (found 2026-09-29).
    const lower = query.toLowerCase().replace(new RegExp(matched.pattern.source, "gi"), " ");
    const substrate =
      matched.substrates.find((s) => lower.includes(s)) ?? matched.substrates[0]!;
    return {
      enzymeName: matched.enzymeName,
      substrate,
      inhibitor: extractInhibitor(query),
      isoform: extractIsoform(query),
      organism: namedOrganism ?? matched.organism,
      ecNumber: matched.ecNumber,
    };
  }

  const guess = guessEnzymeNameFromQuery(query);
  if (!guess) return undefined;
  return {
    enzymeName: guess,
    substrate: "",
    organism: namedOrganism ?? "Homo sapiens",
    ecNumber: undefined,
  };
}

/**
 * Per-parameter provenance for a fully merged parameter set.
 *
 * - Keys explicitly supplied in the query text -> origin "user".
 * - Keys supplied by the LLM resolver -> origin "default" with a note that
 *   they were not verified against literature.
 * - Everything else -> origin "default". In a domain that HAS
 *   literature-resolvable fields (RESOLVABLE_FIELDS), a default whose key
 *   is not among them states the narrowness explicitly (Stage 5 Part 5):
 *   it is a teaching default by decision, not by a failed lookup.
 */
function buildParameterProvenance(
  parameters: Record<string, number | number[]>,
  overrides: Record<string, number | number[]>,
  llmSupplied: Record<string, number | number[]>,
  domain: string,
): Record<string, ParameterProvenance> {
  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const provenance: Record<string, ParameterProvenance> = {};
  for (const key of Object.keys(parameters)) {
    if (key in overrides) {
      provenance[key] = { origin: "user" };
    } else if (key in llmSupplied) {
      // Not `default`: a default is a value this project chose and
      // documented, whereas this is a number a language model produced from
      // a prompt. Labelling the two the same way overstates the second and
      // understates nothing -- see ADR 0011.
      provenance[key] = {
        origin: "llm",
        note: "Value supplied by the LLM resolver; not verified against literature.",
      };
    } else if (resolvable.length > 0 && !resolvable.includes(key)) {
      provenance[key] = {
        origin: "default",
        note: `No literature lookup exists for ${key}; only ${resolvable.join(", ")} is resolved from literature in this domain.`,
      };
    } else if (!DOMAINS_WITH_LITERATURE_RESOLUTION.has(domain)) {
      // The whole domain has no lookup, so there is no "only X is
      // resolved" to point at. Say the true thing instead of nothing:
      // silence here is what let the refusal claim a search had happened.
      //
      // No `unresolvedReason` on purpose. Setting one would promote this
      // into the per-key detail list, which drops the generic sentence
      // AND the "Add key=<value>" instruction that goes with it — the
      // regression missingKeyDetails' own comment records. The refusal
      // sentence is corrected at its source instead.
      provenance[key] = {
        origin: "default",
        note:
          `No literature lookup exists for any parameter in the ` +
          `'${domain}' domain; every value must be supplied in the query.`,
      };
    } else {
      provenance[key] = { origin: "default" };
    }
  }
  return provenance;
}

/**
 * Quantities the user stated in words rather than as key=value.
 *
 * "model a covid-19 outbreak in a town of 10000 people" contains the
 * population. Before this existed, only CLI syntax was read, so that
 * number was invisible and the refusal asked the user to supply s0 -- a
 * number they had already given, in the same sentence. Reading it is not
 * inventing it; the difference between "a town of 10000 people" and
 * "s0=10000" is grammar, not provenance, and both are origin "user".
 *
 * An explicit key=value ALWAYS wins over prose. Someone who writes
 * "s0=500" after describing a town of 10000 is correcting themselves, and
 * the more precise statement is the one they meant.
 *
 * Shared by both resolution paths on purpose. This started life inline in
 * the keyword fallback only, which meant the entire natural-language
 * capability switched off the moment an LLM key was configured: the LLM
 * path built provenance from `overrides` alone, so prose numbers arrived
 * as origin "llm" (ADR 0011) at best and were hard-blocked, leaving a
 * plain question failing on one deployment and working on another for
 * reasons no user could see.
 */
function readStatedQuantities(
  query: string,
  domain: SimulationDomain,
  overrides: Record<string, number | number[]>,
): {
  effectiveOverrides: Record<string, number | number[]>;
  statedPhrases: Record<string, string>;
} {
  const statedPhrases: Record<string, string> = {};
  const statedValues: Record<string, number> = {};
  for (const stated of extractStatedQuantities(query, domain)) {
    if (stated.key in overrides) continue;
    statedValues[stated.key] = stated.value;
    statedPhrases[stated.key] = stated.sourcePhrase;
  }
  return {
    effectiveOverrides: { ...statedValues, ...overrides },
    statedPhrases,
  };
}

/**
 * Record WHICH WORDS produced each stated value.
 *
 * This is what makes a misreading catchable: without it, a wrong binding
 * is discoverable only from the trajectory, which is exactly the
 * invisible-failure shape this project treats as worse than an error.
 */
function noteStatedSources(
  provenance: Record<string, ParameterProvenance>,
  statedPhrases: Record<string, string>,
): Record<string, ParameterProvenance> {
  const out = { ...provenance };
  for (const [key, phrase] of Object.entries(statedPhrases)) {
    const entry = out[key];
    if (entry) {
      out[key] = { ...entry, note: `Read from your query: "${phrase}".` };
    }
  }
  return out;
}

function provenanceViolations(
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
): string[] {
  return validateParameterProvenance(
    parameters as Record<string, unknown>,
    parameterProvenance,
  );
}

/**
 * Generate flags about parameter extraction from query overrides.
 * Consolidated pattern used in both LLM and fallback resolution paths.
 */
function buildParameterExtractionFlags(overrides: Record<string, number | number[]>): string[] {
  const extractionFlags: string[] = [];
  if (Object.keys(overrides).length === 0) {
    extractionFlags.push("No parameters were extracted from the query; using defaults.");
  }
  if (Object.keys(overrides).length > 0) {
    extractionFlags.push("Applied parameter overrides found in the query string.");
  }
  return extractionFlags;
}

/**
 * Resolve a natural-language query to a simulation domain and parameters.
 *
 * The resolver tries an LLM first (if an API key is configured). If the LLM
 * is unavailable or returns bad output, it falls back to deterministic keyword
 * matching, regex parameter extraction, and a small hardcoded enzyme map. This
 * makes the pipeline robust whether or not an LLM provider is configured.
 *
 * For Michaelis-Menten queries, the resolver can also call the real science
 * agent (BRENDA/KEGG/PubMed) to fetch literature-backed Km values when an EC
 * number is available.
 */
/**
 * Build the citation string attached to a resolved parameter value.
 *
 * Stage 5 Part 1 strictness: a resolved citation must be locatable — a ref id
 * (other than the "n/a" placeholder) or a URL. Returns undefined when the
 * citation is missing or carries no locator, so the caller degrades honestly
 * instead of emitting a locator-shaped string like "BRENDA (ref n/a)" that
 * locates nothing.
 */
function formatResolvedCitation(citation?: {
  source?: string;
  referenceId?: string | null;
  url?: string | null;
  title?: string | null;
}): string | undefined {
  if (!citation?.source) return undefined;
  const hasRef =
    citation.referenceId !== undefined && citation.referenceId !== null;
  const hasUrl = citation.url !== undefined && citation.url !== null;
  if (!hasRef && !hasUrl) return undefined;
  const refPart = hasRef ? ` (ref ${citation.referenceId})` : "";
  const urlPart = hasUrl ? ` — ${citation.url}` : "";

  // THE TITLE, WHICH USED TO STOP HERE.
  //
  // `Citation.title` is resolved by the Python side, emitted by the runner
  // and declared on the TypeScript interface -- and this function's
  // parameter type did not mention it, so a student read
  //
  //     BRENDA (ref 740253) — https://www.brenda-enzymes.org/...
  //
  // and could not tell what paper it was without opening the link. In a
  // tool whose whole claim is that its values are literature-backed, the
  // one human-readable part of the evidence was the part not shown. Found
  // by the reachability guard once it learned to look inside nested models
  // (ADR 0102); deferred one pass on a cost that turned out to be wrong.
  //
  // POSITION IS LOAD-BEARING. Three things parse this string --
  // `/\(ref ([^)]*)\)/` in provenance.ts and twice in citeVerify.ts -- and
  // all of them read the ref id out of the parenthesis. The title goes
  // AFTER that group and before the URL, so every one of them still
  // matches the same span. Verified by test, not by reading.
  //
  // A title is not a locator, so it deliberately does NOT participate in
  // the `hasRef || hasUrl` gate above: a citation carrying a title and
  // nothing to find it by is still unlocatable, and must still degrade.
  const title = citation.title?.trim();
  const titlePart = title ? ` "${title}"` : "";
  return `${citation.source}${refPart}${titlePart}${urlPart}`;
}

/**
 * The single gate for "is this citation good enough to call resolved".
 *
 * TWO DEFINITIONS OF "LOCATABLE" USED TO DISAGREE, and the disagreement was
 * load-bearing:
 *
 *   - `formatResolvedCitation` (above) returns a string whenever the
 *     citation has a source and EITHER a ref id or a URL. Any ref id.
 *   - `buildCitationLocators` (citeVerify.ts:137-157) only produces a
 *     locator when the ref id is a DOI or purely numeric.
 *
 * A source supplying an accession-style reference — `SABIO:1234`,
 * `P00338`, anything not a DOI and not digits — satisfies the first and
 * fails the second. It would be admitted as `resolved` with an empty
 * locator array, and now that locators are mandatory
 * (`validateParameterProvenance`), `provenanceViolations` would throw:
 * "Internal error: invalid parameter provenance" in place of a working
 * literature answer.
 *
 * That is precisely the ADR 0021 failure — a helper stamping a field the
 * validator then rejects, turning a successful resolution into a 500 —
 * and it would have arrived the same way, via a source nobody had added
 * yet.
 *
 * So the decision and the record are now the same computation. If nothing
 * can be extracted that re-finds the source, the value degrades honestly
 * to a default instead of being published as literature-backed.
 */
export function locatableCitation(citation?: {
  source?: string;
  referenceId?: string | null;
  url?: string | null;
  // Declared here even though this function never reads it. The object is
  // passed whole to `formatResolvedCitation`, so the title survives at
  // runtime through structural typing while being invisible in the
  // signature -- which is how it came to be dropped by the composer in the
  // first place. A field that travels through a function unnamed is one
  // destructuring away from being lost again.
  title?: string | null;
}): { display: string; locators: CitationLocator[] } | undefined {
  const display = formatResolvedCitation(citation);
  if (display === undefined) return undefined;
  const locators = buildCitationLocators(citation);
  if (locators.length === 0) return undefined;
  return { display, locators };
}

export interface ResolveQueryOptions {
  /**
   * Permit a value measured in a different, sufficiently related organism
   * (ADR 0024). Off unless explicitly true.
   *
   * This is the "Allow cross-species data" checkbox Lisa Jeske asked for,
   * and this parameter is the only reason it is a real choice rather than
   * a message about a choice: an opt-in reachable only from an internal
   * subprocess payload is not an opt-in, it is a constant.
   */
  allowCrossSpecies?: boolean;
  /**
   * Permit a value measured on a sequence variant — a point mutant or a
   * named isozyme (ADR 0029). Off unless explicitly true.
   *
   * Same argument as `allowCrossSpecies`: a point substitution is usually
   * chosen BECAUSE it changes the kinetics, so its Km is not the enzyme's,
   * and an unlabelled opt-in reachable only from an internal payload is not
   * an opt-in.
   */
  allowVariants?: boolean;
  /**
   * The pH and temperature the model is meant to represent, plus how far a
   * measurement may drift from them before it stops representing the
   * modelled system (ADR 0024, Decision 3).
   *
   * Same reasoning as `allowCrossSpecies`: an input reachable only from an
   * internal subprocess payload is not an input, it is a constant. Until
   * this existed, the API server could not state what its model
   * represented, so Bakker's proximity axis had nothing to grade against
   * and returned `not_assessed` on every request.
   *
   * All five fields are required and a partial reference is refused rather
   * than completed — see `_parse_physiological` in science_agent_runner.py.
   * Half a reference plus an assumed 37 °C is an assumed mammal.
   */
  physiologicalReference?: {
    ph: number;
    temperatureC: number;
    basis: string;
    phTolerance: number;
    temperatureToleranceC: number;
  };
}

export async function resolveQuery(
  query: string,
  options: ResolveQueryOptions = {},
): Promise<ResolvedSimulation> {
  const allowCrossSpecies = options.allowCrossSpecies === true;
  const allowVariants = options.allowVariants === true;
  const physiologicalReference = options.physiologicalReference;
  const runId = randomUUID();
  const startTime = Date.now();
  const stageTimings: Record<string, { duration: number; success: boolean }> = {};

  verifiableMetricsCollector.recordJobStart(runId);

  // Stage 1: Entity Extraction - Parse query for enzyme information
  const stage1Start = Date.now();
  const overrides = extractParameterOverrides(query);
  const stage1Duration = Date.now() - stage1Start;
  stageTimings["Entity Extraction"] = { duration: stage1Duration, success: true };

  // Stage 3: Domain Classification - LLM classifies domain
  // (We do this before Stage 2 because domain determines which parameters to resolve)
  const stage3Start = Date.now();
  const llmResult = await resolveQueryWithLLM(query);
  const stage3Duration = Date.now() - stage3Start;
  stageTimings["Domain Classification"] = {
    duration: stage3Duration,
    success: !!llmResult,
  };

  if (llmResult) {
    const domainDefaults =
      DOMAIN_DEFAULTS.find((d) => d.domain === llmResult.domain) ||
      DOMAIN_DEFAULTS[0]!;
    // Prose quantities outrank the LLM's own extraction, and sit below an
    // explicit key=value. A number read deterministically out of the
    // user's sentence, carrying the phrase that produced it, is the user
    // stating it; the same number produced by a model from a prompt is
    // origin "llm" and hard-blocked (ADR 0011). Ordering them the other
    // way round would let model output shadow what the user actually
    // wrote, and then block the query for containing model output.
    const { effectiveOverrides, statedPhrases } = readStatedQuantities(
      query,
      llmResult.domain,
      overrides,
    );

    let parameters = {
      ...domainDefaults.parameters,
      ...llmResult.parameters,
      ...effectiveOverrides,
    };
    let flags: string[] = [];
    // The model's OWN modelCitations are deliberately NOT carried into
    // the response.
    //
    // `SYSTEM_PROMPT` asks the model for "modelCitations": ["optional
    // literature reference"], and whatever it returns used to be spread
    // straight into provenance.modelCitations alongside the curated
    // domain citation -- same array, same shape, no way for a reader to
    // tell which one a human had checked.
    //
    // auditIntegrity.test.ts already established the principle for the
    // easy case: the "Domain: <name>" placeholder was "a label shipped to
    // the client inside the list of citations backing a scientific
    // result", and was removed. An LLM-authored reference is the same
    // defect with a better disguise -- a placeholder is obviously not a
    // citation, whereas an invented reference looks exactly like a real
    // one. This is also the rule provenance.ts already applies to VALUES,
    // where an `llm` origin is blocked unless a resolvable citation backs
    // it; there is no reason a citation should be trusted on terms a
    // number is not.
    //
    // Discarded rather than silently dropped: if the model did offer
    // something, the response says so in `flags`, so the signal survives
    // without an unverified reference being published as a citation.
    const discardedLlmCitations = llmResult.modelCitations.length;
    let parameterProvenance = noteStatedSources(
      buildParameterProvenance(
        parameters,
        effectiveOverrides,
        llmResult.parameters,
        llmResult.domain,
      ),
      statedPhrases,
    );

    const resolvableForDomain = RESOLVABLE_FIELDS[llmResult.domain] ?? [];
    const hasUnoverriddenKinetic = resolvableForDomain.some(
      (k) => !(k in effectiveOverrides),
    );
    if (
      (llmResult.domain === "mm" ||
        llmResult.domain === "mm_competitive_inhibition") &&
      (llmResult.entities?.ecNumber || llmResult.entities?.enzymeName) &&
      hasUnoverriddenKinetic
    ) {
      const result = await applyKineticResolution(
        {
          ...llmResult.entities,
          inhibitor: llmResult.entities?.inhibitor ?? extractInhibitor(query),
          isoform: llmResult.entities?.isoform ?? extractIsoform(query),
        },
        effectiveOverrides,
        llmResult.domain,
        allowCrossSpecies,
        allowVariants,
        physiologicalReference,
        parameters,
        parameterProvenance,
        flags,
      );
      parameters = result.parameters;
      parameterProvenance = result.parameterProvenance;
      flags = result.flags;
    }

    // ADR 0019: bridge a literature kcat to Vmax, but only when the query
    // itself supplied enzyme_conc — never resolved, never defaulted.
    {
      const vmaxResult = await applyVmaxFromKcatResolution(
        llmResult.entities,
        effectiveOverrides,
        llmResult.domain,
        parameters,
        parameterProvenance,
        flags,
      );
      parameters = vmaxResult.parameters;
      parameterProvenance = vmaxResult.parameterProvenance;
      flags = vmaxResult.flags;
    }

    // ADR 0017 / ADR 0020: bridge a literature R0/infectious-period pair
    // to beta/gamma for a recognized disease name in the query text.
    {
      const epiResult = await applyBetaGammaFromR0Resolution(
        query,
        effectiveOverrides,
        llmResult.domain,
        parameters,
        parameterProvenance,
        flags,
      );
      parameters = epiResult.parameters;
      parameterProvenance = epiResult.parameterProvenance;
      flags = epiResult.flags;
    }


    if (
      Object.keys(effectiveOverrides).length === 0 &&
      Object.keys(llmResult.parameters).length === 0
    ) {
      flags.push(
        "No parameters were extracted from the query; using defaults.",
      );
    } else if (Object.keys(effectiveOverrides).length > 0) {
      flags.push("Applied parameter overrides found in the query string.");
    }
    const violations = provenanceViolations(parameters, parameterProvenance);
    if (violations.length > 0) {
      throw new Error(
        `Internal error: invalid parameter provenance: ${violations.join("; ")}`,
      );
    }

    if (isAllDefaults(parameterProvenance)) {
      flags.push(
        "No parameter values were resolved from literature; all values are defaults.",
      );
    }

    // Stage 2: Parameter Resolution - Resolve parameters from literature
    const stage2Start = Date.now();
    // (This happens during kinetic resolution above)
    const stage2Duration = Date.now() - stage2Start;
    stageTimings["Parameter Resolution"] = { duration: stage2Duration, success: true };

    // Stage 4: Validation - Check hard rule and provenance
    const stage4Start = Date.now();
    const missing = unverifiedOriginKeys(parameterProvenance);
    // Recorded HERE, before the refusal branch below returns, so the
    // literature hit rate counts queries that failed to resolve as
    // well as those that succeeded. See recordParameterProvenance.
    verifiableMetricsCollector.recordParameterProvenance(
      Object.values(parameterProvenance).map((p) => p.origin),
    );
    const stage4Duration = Date.now() - stage4Start;
    stageTimings["Validation"] = {
      duration: stage4Duration,
      success: missing.length === 0,
    };

    // A gap is not one thing. Before refusing, ask what KIND each one is:
    // a value the requested model fixes by definition, a quantity that
    // describes the user's own setup, or a measurement a real search failed
    // to find. Only the last still refuses. See `resolveGaps`.
    const gaps = resolveGaps(
      llmResult.domain,
      query,
      missing,
      missingKeyDetails(missing, parameterProvenance),
      // The CURATED table, not the merged set -- see `resolveGaps`.
      Object.fromEntries(
        missing
          .filter((k) => domainDefaults.parameters[k] !== undefined)
          .map((k) => [k, domainDefaults.parameters[k]!]),
      ),
      parameterProvenance,
    );
    if (Object.keys(gaps.filled).length > 0) {
      parameters = { ...parameters, ...gaps.filled };
      parameterProvenance = { ...parameterProvenance, ...gaps.provenance };
      flags = [...flags, ...gaps.flags];
    }
    const stillMissing = gaps.stillMissing;

    if (stillMissing.length > 0) {
      const latencyMs = Date.now() - startTime;
      verifiableMetricsCollector.recordJobFailure(runId);
      // `parameters` is seeded from DOMAIN_DEFAULTS before anything real
      // overlays it (see the `let parameters = {...domainDefaults.parameters,
      // ...}` above), so an unresolved key can still hold that seed's
      // illustrative number even while `missing` correctly says nobody
      // verified it. Filtering by `missing` is what keeps a caller of this
      // error from receiving a fabricated value labeled as resolved --
      // exactly the "confident wrong number" this project exists to refuse.
      // Caught by testing this feature end to end: without the filter, a
      // caller reasonably reads "resolvedSoFar.vmax === 5" as a real,
      // literature-grounded number.
      const resolvedOnly = Object.fromEntries(
        Object.entries(parameters).filter(([key]) => !missing.includes(key)),
      );
      throw new RequiredParametersMissingError(
        llmResult.domain,
        stillMissing,
        missingKeyDetails(stillMissing, parameterProvenance),
        resolvedOnly,
        // The domain table's own illustrative values, offered ONLY as
        // "Add end=200" hints. RequiredParametersMissingError filters
        // them through EXPERIMENTAL_CHOICE_KEYS, so the teaching-default
        // km/vmax in this same table can never reach the message and be
        // pasted back as a user value.
        Object.fromEntries(missing.map((k) => [k, parameters[k]!])),
      );
    }

    // Stage 5: Simulation Output (preparation)
    const stage5Start = Date.now();
    const domainCitation = getDomainCitation(llmResult.domain);
    const stage5Duration = Date.now() - stage5Start;
    stageTimings["Simulation Output"] = { duration: stage5Duration, success: true };

    const latencyMs = Date.now() - startTime;
    verifiableMetricsCollector.recordJobCompletion(runId, latencyMs);
    verifiableMetricsCollector.recordDomainUsage(
      llmResult.domain,
      latencyMs,
      missing.length === 0,
    );
    if (llmResult) {
      verifiableMetricsCollector.recordLLMClassification(true);
    }

    // Record stage timings to metrics
    for (const [stageName, timing] of Object.entries(stageTimings)) {
      verifiableMetricsCollector.recordStageExecution(
        stageName,
        timing.duration,
        timing.success,
      );
    }

    // Cross-parameter coherence. Computed once, after every resolver has run,
    // because it is a question about the finished set: a Km resolved in step
    // one and a Ki resolved in step two can each be flawless and still come
    // from experiments that were never performed together (Jeske, ADR 0026).
    //
    // The flag is pushed into the SAME list the reader already reads. A
    // finding filed somewhere the user does not look is indistinguishable
    // from no finding.
    const coherence = coherenceFromProvenance(parameterProvenance);
    if (coherence.verdict === "differing_conditions") {
      flags.push(`Assay coherence: ${coherence.reason}`);
    }

    return {
      runId,
      domain: llmResult.domain,
      parameters,
      provenance: {
        reasoning: llmResult.reasoning,
        // `domainCitation` is undefined for a domain with no literature
        // entry (sbml, where the caller supplies the model). Omit it
        // rather than pushing a placeholder into a citations list.
        modelCitations: domainCitation ? [domainCitation] : [],
        // Appended HERE rather than pushed at the point of discard: `flags`
        // is REASSIGNED further down this function (flags = result.flags,
        // = vmaxResult.flags, = epiResult.flags, = popgenResult.flags), so
        // anything pushed earlier is silently dropped on four of the paths
        // through it.
        flags:
          discardedLlmCitations > 0
            ? [
                ...flags,
                `discarded_unverified_model_citation: the language model ` +
                  `offered ${discardedLlmCitations} reference(s). Caterva ` +
                  `cites only the curated domain literature, because ` +
                  `nothing has checked that those references exist or say ` +
                  `what the model claims.`,
              ]
            : flags,
      },
      parameterProvenance,
      assayCoherence: coherence,
    };
  }

  // Strip explicit parameter-override tokens ("km=2", "vmax=5", ...)
  // before classifying. "km" and "vmax" are themselves mm keywords
  // (someone writing "the km of this reaction" IS naming enzyme kinetics
  // vocabulary) -- but every fully-specified mm/mm_competitive_inhibition
  // query ALSO writes "km=<value>" as parameter syntax, which would
  // otherwise inflate mm's score by 1-2 points purely from bookkeeping
  // that has nothing to do with which of the two domains is meant. That
  // let mm silently outscore mm_competitive_inhibition on a query that
  // explicitly said "competitive inhibition", just because it also
  // supplied km=/vmax= inline -- classification must run on what the
  // query SAYS, not on which parameter names it happens to assign.
  const classificationText = query
    .split(/\s+/)
    .filter((token) => !PARAMETER_TOKEN_PATTERN.test(token))
    .join(" ");
  const lower = classificationText.toLowerCase();
  const queryTokens = new Set(
    tokenizeForMatching(classificationText).map(lightStem),
  );

  // `matchEnzyme` already recognizes ~25 specific enzymes by name (with a
  // verified EC number, no network round trip) for the entity-extraction
  // step below -- but classification never consulted it, so a query
  // naming one of those exact enzymes (e.g. "citrate synthase kinetics",
  // "chymotrypsin activity") could still fail to reach "mm" if the enzyme
  // itself wasn't ALSO separately hardcoded into the mm keyword list. That
  // is the same class of bug as the domain-classification gap above, just
  // one layer down: two independent lists of the same enzymes, silently
  // drifting apart. Treating a real `matchEnzyme` hit as a strong
  // classification signal removes the second list rather than growing it.
  const enzymeMatch = matchEnzyme(query);

  let best: DomainDefaults | undefined;
  let bestScore = 0;
  for (const candidate of DOMAIN_DEFAULTS) {
    let score = candidate.keywords.filter((keyword) =>
      keywordMatches(lower, queryTokens, keyword),
    ).length;
    // Naming a real enzyme is generic evidence for "this is an enzyme-
    // kinetics question" -- it should land on plain mm by default, so mm
    // gets the larger share (+2). mm_competitive_inhibition gets a smaller
    // share (+1) rather than none: giving both the same boost made them
    // tie on any plain enzyme-kinetics query with no inhibitor language,
    // with array order (mm_competitive_inhibition is declared first)
    // silently deciding the wrong one every time. With the smaller share,
    // mm wins outright when nothing else distinguishes them, but a query
    // that ALSO says "inhibitor"/"competitive"/"inhibition" adds enough on
    // top (mm_competitive_inhibition's own keyword score) to still win --
    // inhibition is a real, additional claim the query has to make, not
    // the default assumption for every enzyme mentioned.
    if (enzymeMatch && candidate.domain === "mm") {
      score += 2;
    } else if (enzymeMatch && candidate.domain === "mm_competitive_inhibition") {
      score += 1;
    }
    if (score > bestScore) {
      best = candidate;
      bestScore = score;
    }
  }

  if (!best) {
    // Previously fell through to `mm` (Michaelis-Menten) unconditionally --
    // whatever domain happened to sit first in DOMAIN_DEFAULTS when nothing
    // else matched. That is a worse failure than refusing: a query about
    // "the spread of measles in a school" or "predator and prey
    // populations" would silently receive an enzyme-kinetics simulation,
    // with the domain mismatch invisible anywhere in the response. See
    // UnrecognizedQueryError's own doc comment for the full reasoning.
    throw new UnrecognizedQueryError(
      query,
      DOMAIN_DEFAULTS.map((d) => d.domain),
    );
  }

  const { effectiveOverrides, statedPhrases } = readStatedQuantities(
    query,
    best.domain,
    overrides,
  );

  let parameters = { ...best.parameters, ...effectiveOverrides };
  let flags: string[] = [];
  let parameterProvenance = noteStatedSources(
    buildParameterProvenance(parameters, effectiveOverrides, {}, best.domain),
    statedPhrases,
  );

  // If this looks like an enzyme query and no LLM is available, try the
  // hardcoded entity map and the science agent.
  const fallbackEntities = extractEntitiesFromQuery(query);
  const resolvableForDomain = RESOLVABLE_FIELDS[best.domain] ?? [];
  const hasUnoverriddenKinetic = resolvableForDomain.some(
    (k) => !(k in effectiveOverrides),
  );
  if (
    (best.domain === "mm" || best.domain === "mm_competitive_inhibition") &&
    (fallbackEntities?.ecNumber || fallbackEntities?.enzymeName) &&
    hasUnoverriddenKinetic
  ) {
    const result = await applyKineticResolution(
      fallbackEntities,
      effectiveOverrides,
      best.domain,
      allowCrossSpecies,
      allowVariants,
      physiologicalReference,
      parameters,
      parameterProvenance,
      flags,
    );
    parameters = result.parameters;
    parameterProvenance = result.parameterProvenance;
    flags = result.flags;
  }

  // ADR 0019: bridge a literature kcat to Vmax, but only when the query
  // itself supplied enzyme_conc — never resolved, never defaulted.
  //
  // `effectiveOverrides`, not `overrides`: an [E]0 stated in words ("with
  // 50 nM enzyme") is supplied by the query just as much as
  // "enzyme_conc=0.00005" is, and reading it while passing only the
  // key=value map here would have extracted the number and then dropped
  // it on the floor one call later.
  {
    const vmaxResult = await applyVmaxFromKcatResolution(
      fallbackEntities,
      effectiveOverrides,
      best.domain,
      parameters,
      parameterProvenance,
      flags,
    );
    parameters = vmaxResult.parameters;
    parameterProvenance = vmaxResult.parameterProvenance;
    flags = vmaxResult.flags;
  }

  // ADR 0017 / ADR 0020: bridge a literature R0/infectious-period pair to
  // beta/gamma for a recognized disease name in the query text.
  {
    const epiResult = await applyBetaGammaFromR0Resolution(
      query,
      effectiveOverrides,
      best.domain,
      parameters,
      parameterProvenance,
      flags,
    );
    parameters = epiResult.parameters;
    parameterProvenance = epiResult.parameterProvenance;
    flags = epiResult.flags;
  }


  flags.push(...buildParameterExtractionFlags(effectiveOverrides));
  const violations = provenanceViolations(parameters, parameterProvenance);
  if (violations.length > 0) {
    throw new Error(
      `Internal error: invalid parameter provenance: ${violations.join("; ")}`,
    );
  }

  if (isAllDefaults(parameterProvenance)) {
    flags.push(
      "No parameter values were resolved from literature; all values are defaults.",
    );
  }

  // Stage 2: Parameter Resolution (fallback path)
  const stage2Start = Date.now();
  const stage2Duration = Date.now() - stage2Start;
  stageTimings["Parameter Resolution"] = { duration: stage2Duration, success: true };

  // Stage 4: Validation (fallback path)
  const stage4Start = Date.now();
  const missing = unverifiedOriginKeys(parameterProvenance);
  // Recorded HERE, before the refusal branch below returns, so the
  // literature hit rate counts queries that failed to resolve as
  // well as those that succeeded. See recordParameterProvenance.
  verifiableMetricsCollector.recordParameterProvenance(
    Object.values(parameterProvenance).map((p) => p.origin),
  );
  const stage4Duration = Date.now() - stage4Start;
  stageTimings["Validation"] = {
    duration: stage4Duration,
    success: missing.length === 0,
  };

  // Same classification as the LLM branch above, same reason.
  const gaps = resolveGaps(
    best.domain,
    query,
    missing,
    missingKeyDetails(missing, parameterProvenance),
    // The CURATED table, not the merged set -- see `resolveGaps`.
    Object.fromEntries(
      missing
        .filter((k) => best.parameters[k] !== undefined)
        .map((k) => [k, best.parameters[k]!]),
    ),
    parameterProvenance,
  );
  if (Object.keys(gaps.filled).length > 0) {
    parameters = { ...parameters, ...gaps.filled };
    parameterProvenance = { ...parameterProvenance, ...gaps.provenance };
    flags = [...flags, ...gaps.flags];
  }
  const stillMissing = gaps.stillMissing;

  if (stillMissing.length > 0) {
    const latencyMs = Date.now() - startTime;
    verifiableMetricsCollector.recordJobFailure(runId);
    // Same filter as the LLM branch above, same reason: `parameters` here
    // is seeded `{...best.parameters, ...overrides}` and an unresolved key
    // can still carry that seed's placeholder number even though `missing`
    // correctly flags it as unverified.
    const resolvedOnly = Object.fromEntries(
      Object.entries(parameters).filter(([key]) => !missing.includes(key)),
    );
    throw new RequiredParametersMissingError(
      best.domain,
      stillMissing,
      missingKeyDetails(stillMissing, parameterProvenance),
      resolvedOnly,
      // Same as the LLM branch above, same filtering.
      Object.fromEntries(missing.map((k) => [k, parameters[k]!])),
    );
  }

  // Stage 5: Simulation Output (preparation - fallback path)
  const stage5Start = Date.now();
  const domainCitation = getDomainCitation(best.domain);
  const stage5Duration = Date.now() - stage5Start;
  stageTimings["Simulation Output"] = { duration: stage5Duration, success: true };

  const latencyMs = Date.now() - startTime;
  verifiableMetricsCollector.recordJobCompletion(runId, latencyMs);
  verifiableMetricsCollector.recordDomainUsage(
    best.domain,
    latencyMs,
    missing.length === 0,
  );
  if (!llmResult) {
    verifiableMetricsCollector.recordLLMClassification(false);
  }

  // Record stage timings to metrics (fallback path)
  for (const [stageName, timing] of Object.entries(stageTimings)) {
    verifiableMetricsCollector.recordStageExecution(
      stageName,
      timing.duration,
      timing.success,
    );
  }

  // Cross-parameter coherence. Computed once, after every resolver has run,
  // because it is a question about the finished set: a Km resolved in step
  // one and a Ki resolved in step two can each be flawless and still come
  // from experiments that were never performed together (Jeske, ADR 0026).
  //
  // The flag is pushed into the SAME list the reader already reads. A
  // finding filed somewhere the user does not look is indistinguishable
  // from no finding.
  const coherence = coherenceFromProvenance(parameterProvenance);
  if (coherence.verdict === "differing_conditions") {
    flags.push(`Assay coherence: ${coherence.reason}`);
  }

  return {
    runId,
    domain: best.domain,
    parameters,
    provenance: {
      reasoning: best.reasoning,
      modelCitations: [
        ...best.modelCitations,
        ...(domainCitation ? [domainCitation] : []),
      ],
      flags,
    },
    parameterProvenance,
    assayCoherence: coherence,
  };
}
