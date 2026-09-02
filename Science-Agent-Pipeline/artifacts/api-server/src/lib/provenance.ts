/**
 * Thrown by resolveQuery() when one or more parameters could neither be
 * resolved from literature nor were supplied by the person running the
 * query. This is a hard requirement, not a soft warning: a simulation may
 * never run on a value nobody chose and nothing verified. The message is
 * built to be directly actionable -- copy-pasteable key=value syntax for
 * exactly what's missing, not just a list of names.
 */
import {
  citationConsistentWithLocators,
  isValidLocator,
  type CitationLocator,
} from "./citeVerify";

import type { ReliabilityScore } from "./reliabilityScore";

export class RequiredParametersMissingError extends Error {
  readonly domain: string;
  readonly missing: string[];
  /** Per-key explanation of WHY the key is missing, keyed by parameter
   * name. Carried alongside the message so a caller can render the reason
   * without re-parsing prose. */
  readonly details: Record<string, string>;
  /**
   * Everything the resolver DID establish before refusing -- literature
   * values it found, and anything the caller already supplied inline.
   * Optional and defaulting to `{}` so no existing call site (or a future
   * one that forgets it) has to change; a caller that ignores it loses
   * nothing it had before.
   *
   * Without this, a UI catching the refusal had the keys it was missing
   * but not the ones it already had, and made the user re-type values
   * that had already resolved correctly (e.g. a literature Km) just to
   * fill in the one experimental condition (s0) that was actually
   * missing.
   */
  readonly resolvedSoFar: Record<string, number | number[]>;

  /**
   * `details` exists because the summary sentence is not always true.
   *
   * "could not be resolved from literature" is accurate when BRENDA and
   * PubMed genuinely hold nothing. It is FALSE when a value was found in
   * another organism and withheld because cross-species use was not opted
   * into (ADR 0024) — that value was resolved from the literature, and the
   * refusal is this system's policy, not the literature's silence.
   *
   * Telling a user the literature has nothing, when it has something they
   * could have had by flipping a flag, is the true-sounding-and-misleading
   * shape this project treats as a defect everywhere else. So any
   * provenance note attached to a missing key is appended verbatim, and
   * the generic sentence is dropped for keys that have one.
   */
  constructor(
    domain: string,
    missing: string[],
    details: Record<string, string> = {},
    resolvedSoFar: Record<string, number | number[]> = {},
  ) {
    const explained = missing.filter((k) => details[k]);
    const unexplained = missing.filter((k) => !details[k]);

    const parts: string[] = [];
    if (unexplained.length > 0) {
      const example = unexplained.map((k) => `${k}=<value>`).join(" ");
      parts.push(
        `Cannot simulate '${domain}': ${unexplained.join(", ")} could not be ` +
          `resolved from literature and ${unexplained.length > 1 ? "were" : "was"} not ` +
          `supplied in the query. Add ${example} to your query and try again.` +
          // THE SECOND SENTENCE IS THE POINT.
          //
          // Herbert Sauro predicted that a refusing tool makes the
          // researcher "hardcode a number with no warning at all -- a
          // strictly worse outcome caused by the strict rule". Terrium was
          // not merely vulnerable to that: this message INSTRUCTED it. A
          // user who goes and finds a Km in a paper, types it in, and gets
          // it recorded as origin=user with no citation has been walked
          // into exactly the outcome he described, by the tool whose
          // entire purpose is not losing sources.
          //
          // Pointing at --cite here is what closes it, and here is the
          // only place it can be said: the moment the user is about to go
          // find a number somewhere.
          " If you have a source for the value, attach it with " +
          `--cite ${unexplained[0]}=\"...\" so it is recorded rather than ` +
          "lost.",
      );
    } else {
      parts.push(
        `Cannot simulate '${domain}': ${missing.join(", ")} ` +
          `${missing.length > 1 ? "are" : "is"} unresolved.`,
      );
    }
    for (const key of explained) {
      parts.push(`${key}: ${details[key]}`);
    }

    super(parts.join(" "));
    this.name = "RequiredParametersMissingError";
    this.domain = domain;
    this.missing = missing;
    this.details = details;
    this.resolvedSoFar = resolvedSoFar;
  }
}

/**
 * Thrown by the keyword fallback resolver when a query matches none of
 * Terrium's fifteen domains -- even after word-set matching and light
 * stemming, not just an exact-phrase miss.
 *
 * This replaces a worse behavior: silently classifying an unmatched query
 * as Michaelis-Menten enzyme kinetics ("mm"), because `mm` happened to sit
 * first in the domain table when nothing else matched. A query about
 * "the spread of measles in a school" or "predator and prey populations"
 * would silently receive an enzyme-kinetics simulation, with the model
 * mismatch invisible anywhere in the response -- no error, no flag, just
 * the wrong physics for the question asked. Guessing the wrong SCIENTIFIC
 * MODEL is a worse failure than guessing a wrong NUMBER (the case
 * `RequiredParametersMissingError` already refuses): a wrong number is
 * visibly wrong once checked against a source, but a wrong model produces
 * an internally consistent, plausible-looking trajectory for a question
 * that was never actually asked.
 */
export class UnrecognizedQueryError extends Error {
  readonly query: string;
  readonly availableDomains: string[];

  constructor(query: string, availableDomains: string[]) {
    super(
      `Could not match this query to any of Terrium's ${availableDomains.length} ` +
        `simulation domains: ${availableDomains.join(", ")}. Try naming the ` +
        "domain directly (e.g. \"simulate sir ...\"), using terms closer to " +
        "the science (\"outbreak\", \"enzyme kinetics\", \"predator-prey\", " +
        '"population genetics"), or supplying parameters directly with ' +
        "key=value pairs.",
    );
    this.name = "UnrecognizedQueryError";
    this.query = query;
    this.availableDomains = availableDomains;
  }
}

/**
 * Per-parameter provenance: what is actually known about each value the
 * resolver returns. See ADR 0008 and Business/build-stages/STAGE_04_PART_03.md.
 */

/**
 * Where a parameter's value came from.
 *
 * - `resolved` — looked up from a primary source (BRENDA/KEGG/PubMed) and
 *   carrying a locatable citation.
 * - `user` — supplied explicitly in the query by the person running it.
 * - `llm` — produced by the LLM query resolver with no corroborating
 *   record.
 * - `default` — the domain's documented default value.
 *
 * `llm` exists because collapsing it into `default` states something false.
 * A default is a value this project chose and documented; an LLM-supplied
 * number is one a language model generated from a prompt, and the two carry
 * different warrants entirely. Stage 4 Part 6 (open question 2) proposed
 * treating "LLM-generated with no corroborating record" as its own tier and
 * called it "the one that matters" — this is that tier.
 *
 * It is deliberately NOT `resolved`: nothing was looked up, so it must never
 * be able to carry a citation. `validateParameterProvenance` enforces that.
 */
export type ParameterOrigin = "resolved" | "user" | "llm" | "default";

/**
 * Stage 5 Part 3: the citation-status contract, as distinct from the value
 * contract. A citation that supports a resolved value is either:
 *  - `verified` — exact organism and substrate match from a primary source
 *    (BRENDA exact tier);
 *  - `flagged` — cross-species or inferred (BRENDA cross-species tier).
 * There is no `rejected` on a resolved entry: a citation with no source, or
 * one that is LLM-generated with no corroborating record, cannot support a
 * `resolved` value at all — it manifests as origin `default` with a note.
 */
export type CitationStatus = "verified" | "flagged";

/**
 * Stage 5 Part 5: the deliberate narrowness. Only these parameters are
 * ever resolved from literature; everything else in the domain is a
 * teaching default, by decision, not by accident. Extending this list is
 * a new trust commitment: each entry needs a lookup path, a hand-verified
 * golden tuple, and contract tests (see STAGE_05_PART_05.md).
 */
export const RESOLVABLE_FIELDS: Record<string, string[]> = {
  mm: ["km"],
  // Ki (inhibition constant) resolves from BRENDA's "Ki Values" table via
  // the same exact-match / cross-species / literature chain as Km, selected
  // by quantity="ki" (science_agent_runner.py -> fallback_logic's
  // KI_TABLE_LABEL). The two constants for this domain resolve
  // independently -- each with its own runner call, source, citation, and
  // assay conditions -- so a cross-species Ki never borrows a verified Km's
  // provenance (see applyKineticResolution in queryResolver.ts).
  mm_competitive_inhibition: ["km", "ki"],
  // Population genetics: mutation_rate resolved from published literature
  // (Rahbari et al., Nature Genetics, 2015 for human; other organisms
  // in Tests/popgen_resolver.py with primary citations).
  wright_fisher: ["mutation_rate"],
};

/**
 * Assay conditions under which a kinetic constant was measured.
 *
 * This is not bookkeeping. The STRENDA Guidelines — the reporting standard
 * for enzymology data, registered in FAIRsharing and recommended by more than
 * 60 biochemistry journals — state the requirement without qualification:
 *
 *   "The temperature, pH and pressure (if other than atmospheric) of the
 *    assay MUST always be included, even if previously published."
 *   — STRENDA Guidelines v1.4.0, Beilstein-Institut
 *
 * The reason is physical, not clerical. Km is not a property of an enzyme; it
 * is a property of an enzyme measured under conditions. The same enzyme and
 * substrate yield different Km values at different pH and temperature, so a
 * Km reported without them cannot be reproduced and cannot be compared
 * against another laboratory's number.
 *
 * BRENDA — the source Terrium resolves from — stores pH optimum, temperature
 * optimum, and an experimental-conditions commentary alongside every Km
 * entry (Schomburg et al., Nucleic Acids Research). So these fields are
 * available upstream; omitting them discards data the source already
 * supplied.
 *
 * `pressure` is deliberately absent: STRENDA requires it only when other than
 * atmospheric, and no path in Terrium currently resolves a non-atmospheric
 * measurement. Adding it later is a field addition, not a contract change.
 */
export interface AssayConditions {
  /** Assay pH. STRENDA: mandatory. */
  ph?: number;
  /** Assay temperature in degrees Celsius. STRENDA: mandatory. */
  temperatureC?: number;
  /** Buffer system, when reported. Not STRENDA-mandatory but materially useful. */
  buffer?: string;
  /**
   * `buffer` resolved to a comparable chemical identity by
   * `Tests/buffer_identity.py` (ADR 0028).
   *
   * An ADDITION to `buffer`, never a replacement: the raw string is what a
   * reader needs in order to disagree with the resolution, and a resolution
   * nobody can check is a claim rather than a fact.
   */
  bufferIdentity?: BufferIdentity;
  /**
   * Cofactors and effectors named in the same commentary (ADR 0032).
   *
   * Lives on `assayConditions` rather than beside it because that is what
   * they are: part of what the assay contained, in the same sense as pH.
   */
  effectors?: Effector[];
}

/**
 * A reported buffer string resolved to a PubChem compound.
 *
 * Mirrors `buffer_identity.BufferIdentity`. Field names are snake_case
 * because they cross the wire as the Python model emits them; renaming here
 * would create a second place the two halves could drift.
 */
/**
 * A cofactor or allosteric effector reported for this measurement.
 *
 * Mirrors `effector.Effector`. snake_case because it crosses the wire as
 * Python emits it; renaming here would create a second place the two halves
 * could drift (ADR 0027).
 */
export interface Effector {
  /** The clause exactly as written, so a reader can disagree with the parse. */
  raw: string;
  compound_text: string;
  /**
   * "present" | "absent" | "unstated".
   *
   * NOT a detail of identity. Two rows naming the same compound with
   * opposite presence are the case ADR 0032 exists for — a wild-type LDH
   * measured with and without fructose 1,6-bisphosphate, at the same pH and
   * temperature, from the same paper. Every other field agrees.
   */
  presence: string;
  /** Recorded and NOT compared. See ADR 0032 on why no threshold. */
  concentration_text?: string | null;
  /** PubChem resolution, reused from the buffer machinery. */
  identity?: BufferIdentity | null;
}

export interface BufferIdentity {
  /** The string exactly as the source reported it. */
  raw: string;
  /** Species name after stripping concentration and the word "buffer". */
  species?: string | null;
  /** PubChem compound id for `species`. */
  cid?: number | null;
  /**
   * Parent (neutral form) compound id — what identity is compared on, so
   * that Tris and Tris-HCl read as one buffer system rather than two
   * compounds.
   */
  parent_cid?: number | null;
  /**
   * The concentration text that was stripped and NOT compared. Present so a
   * reader can see that 0.5 M and 10 mM were treated as the same buffer.
   */
  concentration_text?: string | null;
  /** "resolved" | "unresolvable" | "not_reported". Three states, never two. */
  status: string;
  reason?: string | null;
}

/**
 * Whether a resolved value meets STRENDA's minimum reporting requirement.
 *
 *  - `complete`   — pH and temperature both present.
 *  - `incomplete` — one or both missing. The value may still be correct; it
 *                   is not independently reproducible, which is what the
 *                   standard is about.
 *
 * There is deliberately no `not_applicable`: this status is only ever set on
 * parameters in `STRENDA_GOVERNED_FIELDS`, and for anything else the field is
 * simply absent.
 */
export type StrendaStatus = "complete" | "incomplete";

/**
 * Parameters that are enzyme kinetic constants, and therefore fall under
 * STRENDA's reporting requirement.
 *
 * Km is the only one Terrium currently resolves (see RESOLVABLE_FIELDS). vmax
 * and kcat are listed because they are governed by the same standard the
 * moment a lookup path exists for them — the list states the rule, not the
 * current implementation, so extending RESOLVABLE_FIELDS cannot silently
 * bypass the requirement.
 *
 * WHAT THIS RULE EXISTS TO PREVENT, in the words of a client that did it
 * ---------------------------------------------------------------------
 * A second, unreachable BRENDA client (`src/integrations/brenda-real.ts`,
 * retired 2026-08-11 — see STAGE_10_PART_19/23 and git history) parsed
 * responses like this:
 *
 *     km:          entry.km,
 *     kmUnit:      entry.kmUnit  || 'mM',
 *     vmaxUnit:    entry.vmaxUnit || 'μM/min',
 *     organism:    entry.organism || 'Unknown',
 *     temperature: entry.temperature || 25,
 *     pH:          entry.pH || 7.0,
 *     dataQuality: this.scoreDataQuality(entry)
 *
 * Every `||` on that list is a STRENDA-governed fact being invented when
 * the source did not report it. A value measured at an unknown pH became a
 * value measured at pH 7.0; an unknown temperature became 25 °C. Then
 * `scoreDataQuality` read back the fields the same function had just
 * fabricated two lines earlier and rated the record `'excellent'`.
 *
 * That is the precise inversion this module exists to forbid: a missing
 * condition is a reason to FLAG a value, never a reason to fill one in. The
 * quote is kept here rather than in the file, because the lesson should
 * outlive the code — and because a defect preserved in a live module is a
 * defect waiting for someone to import it.
 */
export const STRENDA_GOVERNED_FIELDS: ReadonlySet<string> = new Set([
  "km",
  "vmax",
  "kcat",
  "ki",
]);

export interface ParameterProvenance {
  /** How this value was obtained for THIS query. */
  origin: ParameterOrigin;
  /** Only when `origin === "resolved"`: what looked the value up. */
  source?: string;
  /** Only when `origin === "resolved"`: the citation supporting THIS value. */
  citation?: string;
  /** Only when `origin === "resolved"`. */
  organism?: string;
  /** Only when `origin === "resolved"` (Stage 5 Part 3). */
  citationStatus?: CitationStatus;
  /**
   * Only when `origin === "resolved"` and the parameter is a kinetic constant.
   * The conditions the value was measured under (STRENDA).
   */
  assayConditions?: AssayConditions;
  /**
   * Only for STRENDA-governed resolved parameters: whether the assay
   * conditions meet the standard's minimum.
   */
  strendaStatus?: StrendaStatus;
  /**
   * Only when `origin === "resolved"`. Machine-checkable locators for the
   * citation (citeVerify.ts): `(kind, value, deepLink)` triples so a human
   * or a tool can re-find the exact source of this number. Kept in lockstep
   * with the display `citation` string by validateParameterProvenance.
   */
  citationLocators?: CitationLocator[];
  /** Why a lookup was attempted and failed, if so. */
  note?: string;
  /**
   * Machine-readable reason a REQUIRED parameter is unresolved, when the
   * reason is something other than "the literature has nothing".
   *
   * Exists so the error message can be assembled from a fact rather than
   * from pattern-matching on `note`. The one case so far is
   * `cross_species_withheld` (ADR 0024): a value WAS found in the
   * literature, in another organism, and withheld by policy. The default
   * sentence — "could not be resolved from literature" — is simply false
   * for it, and a message that is false in a way that sounds authoritative
   * is the failure mode this project spends most of its effort on.
   */
  unresolvedReason?:
    | "cross_species_withheld"
    | "cross_species_too_distant"
    | "variant_withheld"
    /**
     * The run stopped at the ENZYME NAME, before any database was asked
     * for a value.
     *
     * `ec_not_resolved` — UniProt indexed nothing under that name.
     * `ec_ambiguous`    — it indexed several, and they are different
     *                     proteins (EC 1.1.1.27 and EC 1.1.1.28 are the L-
     *                     and D- lactate dehydrogenases).
     *
     * Both belong here for the reason the others do, and more sharply: the
     * generic sentence names BRENDA, KEGG and PubMed, none of which was
     * consulted. It does not merely omit a fact — it blames the wrong
     * stage, and sends a reader to look for a problem they do not have.
     */
    | "ec_not_resolved"
    | "ec_ambiguous"
    /**
     * Nothing was found anywhere. The plain case, and the only one the
     * generic sentence actually describes — named explicitly so the union
     * covers what `buildUnresolvedKineticProvenance` can produce, rather
     * than leaving its widest branch unassignable.
     */
    | "not_found"
    /**
     * BRENDA held nothing, and the PubMed/CORE fallback found papers that
     * may report the value.
     *
     * Every other member of this union means "a value existed and Terrium
     * declined it". This one means "no value, but here is where to look",
     * and it belongs here for the same reason the others do: it makes the
     * generic sentence ("could not be resolved from literature") false by
     * omission. The literature was not silent — nobody read it out.
     */
    | "literature_candidates";
  /**
   * Graded reliability of a RESOLVED value, on three independently
   * reported axes (ADR 0024 Decision 3, on Barbara Bakker's method).
   *
   * Deliberately not a number. See reliabilityScore.ts for why combining
   * the axes would require a trade-off Terrium does not have and must not
   * invent.
   */
  reliability?: ReliabilityScore;
}

/**
 * Helper to check if a value is a valid finite number.
 * Used to validate STRENDA-required assay conditions.
 */
function isValidFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * STRENDA completeness for a single parameter.
 *
 * Both pH and temperature must be present and finite. A `null` pH is not the
 * same as pH 0 — 0 is a real (if extreme) value, so the check is on presence
 * and finiteness rather than truthiness, which would silently reject pH 0.
 */
export function strendaStatusFor(
  conditions: AssayConditions | undefined,
): StrendaStatus {
  if (!conditions) return "incomplete";
  const hasPh = isValidFiniteNumber(conditions.ph);
  const hasTemp = isValidFiniteNumber(conditions.temperatureC);
  return hasPh && hasTemp ? "complete" : "incomplete";
}

/** Which STRENDA-mandatory fields are missing, for a human-readable reason. */
export function missingStrendaFields(
  conditions: AssayConditions | undefined,
): string[] {
  const missing: string[] = [];
  if (!conditions || !isValidFiniteNumber(conditions.ph)) {
    missing.push("pH");
  }
  if (!conditions || !isValidFiniteNumber(conditions.temperatureC)) {
    missing.push("temperature");
  }
  return missing;
}

/**
 * Stage 5 Part 1: a resolved citation is stricter than a modelCitations entry.
 * A `resolved` citation is attached to a NUMBER; it must let a human re-find
 * the exact source of that number. A citation with no locator cannot.
 */
export function isLocatableCitation(citation: string): boolean {
  if (/https?:\/\//.test(citation)) return true;
  const refMatch = citation.match(/\(ref ([^)]*)\)/);
  if (refMatch) {
    const id = refMatch[1]!.trim();
    return id !== "" && id !== "n/a";
  }
  return false;
}

/**
 * Rule 2's analogue for provenance: hard violations mean the response must
 * not be returned. Returns a list of human-readable violations (empty when
 * the provenance is structurally sound).
 *
 * Violations:
 *  - a key in `parameterProvenance` absent from `parameters`, or vice versa
 *  - `origin: "resolved"` with no `citation`
 *  - a `citation` on any entry whose origin is not `"resolved"`
 *  - a `resolved` citation that carries no locator (ref id or URL) — the
 *    strict format rule (Stage 5 Part 1)
 *  - a `resolved` entry with no `citationStatus`, or a `citationStatus` on
 *    an entry whose origin is not `"resolved"` (Stage 5 Part 3)
 */
export function validateParameterProvenance(
  parameters: Record<string, unknown>,
  parameterProvenance: Record<string, ParameterProvenance>,
): string[] {
  const violations: string[] = [];
  const paramKeys = new Set(Object.keys(parameters));
  const provKeys = new Set(Object.keys(parameterProvenance));

  for (const key of provKeys) {
    if (!paramKeys.has(key)) {
      violations.push(`${key} has provenance but no parameter value`);
    }
  }
  for (const key of paramKeys) {
    if (!provKeys.has(key)) {
      violations.push(`${key} has a parameter value but no provenance`);
    }
  }

  for (const [key, prov] of Object.entries(parameterProvenance)) {
    if (prov.origin === "resolved" && !prov.citation) {
      violations.push(`${key} is marked resolved but carries no citation`);
    }
    if (prov.origin !== "resolved" && prov.citation !== undefined) {
      violations.push(`${key} has a citation but origin is '${prov.origin}'`);
    }
    if (
      prov.origin === "resolved" &&
      prov.citation &&
      !isLocatableCitation(prov.citation)
    ) {
      violations.push(
        `${key} is marked resolved but its citation carries no locator (ref id or URL)`,
      );
    }
    if (
      prov.origin === "resolved" &&
      prov.citation &&
      prov.citationStatus === undefined
    ) {
      violations.push(
        `${key} is marked resolved but carries no citation status`,
      );
    }
    if (prov.origin !== "resolved" && prov.citationStatus !== undefined) {
      violations.push(
        `${key} has a citation status but origin is '${prov.origin}'`,
      );
    }

    // --- Citation locators travel with the citation ----------------------
    //
    // A `resolved` entry's machine-checkable locators (citeVerify.ts) must
    // agree with the display citation string and be well-formed. Non-resolved
    // entries must not carry locators at all -- locators would be another
    // locator-shaped claim that locates nothing, the exact failure Stage 5
    // Part 1 removed.
    if (prov.origin !== "resolved" && prov.citationLocators !== undefined) {
      violations.push(
        `${key} carries citation locators but origin is '${prov.origin}'`,
      );
    }
    // Required, not optional. Every rule below used to sit inside
    // `citationLocators !== undefined`, and `buildResolvedKineticProvenance`
    // strips the property when the array is empty -- so the one violation
    // that catches "resolved, but nothing can re-find the source" was
    // unreachable from any production path, and reachable only from a
    // hand-written test literal, which is what made it look enforced.
    //
    // The net rule was: produce zero locators and you are exempt from every
    // locator check; produce a wrong one and you are caught. That inverts
    // the incentive. A citation a reader cannot follow is the failure this
    // whole subsystem exists to prevent.
    if (prov.origin === "resolved") {
      if (
        prov.citationLocators === undefined ||
        prov.citationLocators.length === 0
      ) {
        violations.push(
          `${key} is marked resolved but carries no citation locators -- ` +
            `its citation string cannot be machine-followed back to a source`,
        );
      } else {
        for (const locator of prov.citationLocators) {
          if (!isValidLocator(locator)) {
            violations.push(`${key} carries a malformed citation locator`);
          }
        }
        if (
          prov.citation &&
          !citationConsistentWithLocators(prov.citation, prov.citationLocators)
        ) {
          violations.push(
            `${key} has citation locators that do not match its citation string`,
          );
        }
      }
    }

    // --- LLM-supplied values must say so --------------------------------
    //
    // An `llm` value has no citation by construction (the rule above already
    // forbids one), so the note is the ONLY thing standing between a student
    // and a number a language model invented. An unexplained `llm` entry is
    // indistinguishable from a documented default at the API surface, which
    // is exactly the conflation this origin was introduced to end.
    if (prov.origin === "llm" && !prov.note) {
      violations.push(
        `${key} is marked llm but carries no note explaining that the value is unverified`,
      );
    }

    // --- STRENDA reporting requirement ---------------------------------
    //
    // The rule that carries the weight: a kinetic constant whose assay
    // conditions are unknown cannot be called `verified`. It may well be the
    // right number, but "verified" in this codebase means a human can go and
    // check it, and a Km without pH and temperature cannot be re-measured or
    // compared. Degrading it to `flagged` keeps the value usable while
    // saying plainly what is missing -- the same shape as Rule 2's
    // impossible/implausible distinction, applied to reporting completeness
    // rather than to physics.
    const strendaGoverned =
      prov.origin === "resolved" &&
      STRENDA_GOVERNED_FIELDS.has(key.toLowerCase());

    if (strendaGoverned) {
      const expected = strendaStatusFor(prov.assayConditions);
      if (prov.strendaStatus === undefined) {
        violations.push(
          `${key} is a resolved kinetic constant but carries no STRENDA status`,
        );
      } else if (prov.strendaStatus !== expected) {
        violations.push(
          `${key} claims STRENDA status '${prov.strendaStatus}' but its assay ` +
            `conditions are '${expected}' (missing: ` +
            `${missingStrendaFields(prov.assayConditions).join(", ") || "none"})`,
        );
      }
      if (prov.citationStatus === "verified" && expected === "incomplete") {
        violations.push(
          `${key} is marked citationStatus 'verified' but its assay conditions ` +
            `are incomplete (missing: ${missingStrendaFields(prov.assayConditions).join(", ")}). ` +
            `STRENDA requires temperature and pH for kinetic data; a value ` +
            `without them is not independently reproducible, so it must be ` +
            `'flagged' rather than 'verified'.`,
        );
      }
    }

    if (!strendaGoverned && prov.strendaStatus !== undefined) {
      violations.push(
        `${key} carries a STRENDA status but is not a resolved kinetic constant`,
      );
    }
    if (prov.origin !== "resolved" && prov.assayConditions !== undefined) {
      violations.push(
        `${key} carries assay conditions but origin is '${prov.origin}'`,
      );
    }
  }

  return violations;
}

/**
 * Build the provenance entry for a resolved parameter, applying the STRENDA
 * rule in one place so no caller can forget it.
 *
 * Callers pass the citation tier they believe applies; this function may
 * degrade `verified` to `flagged` when the assay conditions are incomplete.
 * It never upgrades — a cross-species match with perfect conditions is still
 * cross-species.
 *
 * `parameterKey` is REQUIRED, and is what decides whether the STRENDA rule
 * applies at all. It was added after this helper silently corrupted every
 * resolved `mutation_rate`: STRENDA governs enzyme kinetic constants
 * (`STRENDA_GOVERNED_FIELDS`), and unconditionally stamping `strendaStatus`
 * onto a field outside that set is a hard `validateParameterProvenance`
 * violation ("carries a STRENDA status but is not a resolved kinetic
 * constant") that `provenanceViolations` then throws on — turning a
 * successful literature resolution into an internal error. It also
 * downgraded the citation to `flagged` and attached a note about
 * unreported assay pH to a quantity (a per-generation substitution rate)
 * that has no assay pH.
 *
 * Making the key mandatory rather than optional is deliberate: an optional
 * parameter would have defaulted to the old, wrong behaviour and let the
 * same bug reappear at the next call site that forgot it. See ADR 0021.
 *
 * `citationLocators` is REQUIRED for the same reason, and was made so after
 * the same failure in a different place. It was optional; the body then
 * dropped the property whenever the array came back empty; and
 * `validateParameterProvenance` gated every locator rule behind "was this
 * property present". The three together meant: produce zero locators and
 * you are exempt from every locator check, produce a wrong one and you are
 * caught. All four production call sites already passed it, so the only
 * thing an optional parameter bought was the chance for the fifth to
 * forget.
 *
 * Pass the array even when it is empty. An empty array is a fact about the
 * citation — it says nothing could be machine-extracted from it — and the
 * validator is the right place to have an opinion about that, not this
 * constructor.
 */
export function buildResolvedKineticProvenance(args: {
  parameterKey: string;
  source: string;
  citation: string;
  organism?: string;
  citationStatus: CitationStatus;
  assayConditions?: AssayConditions;
  citationLocators: CitationLocator[];
  note?: string;
}): ParameterProvenance {
  // A parameter STRENDA does not govern gets no strendaStatus, no
  // conditions-based downgrade, and no assay-conditions note.
  if (!STRENDA_GOVERNED_FIELDS.has(args.parameterKey.toLowerCase())) {
    return {
      origin: "resolved",
      source: args.source,
      citation: args.citation,
      ...(args.organism !== undefined ? { organism: args.organism } : {}),
      citationStatus: args.citationStatus,
      // Carried through even when empty. Stripping an empty array hid the
      // input from the validator, which then had nothing to complain about
      // -- the constructor was quietly deciding that "no locators" is not
      // worth reporting. Let the validator speak.
      ...(args.citationLocators !== undefined
        ? { citationLocators: args.citationLocators }
        : {}),
      ...(args.note ? { note: args.note } : {}),
    };
  }

  const strendaStatus = strendaStatusFor(args.assayConditions);
  const missing = missingStrendaFields(args.assayConditions);

  const citationStatus: CitationStatus =
    args.citationStatus === "verified" && strendaStatus === "incomplete"
      ? "flagged"
      : args.citationStatus;

  const notes: string[] = [];
  if (args.note) notes.push(args.note);
  if (strendaStatus === "incomplete") {
    notes.push(
      `Assay ${missing.join(" and ")} not reported by the source; ` +
        `STRENDA requires ${missing.length > 1 ? "them" : "it"} for kinetic data, ` +
        `so this value is flagged rather than verified.`,
    );
  }

  return {
    origin: "resolved",
    source: args.source,
    citation: args.citation,
    ...(args.organism !== undefined ? { organism: args.organism } : {}),
    citationStatus,
    ...(args.assayConditions !== undefined
      ? { assayConditions: args.assayConditions }
      : {}),
    ...(args.citationLocators !== undefined && args.citationLocators.length > 0
      ? { citationLocators: args.citationLocators }
      : {}),
    strendaStatus,
    ...(notes.length > 0 ? { note: notes.join(" ") } : {}),
  };
}

/** True when every parameter entry has origin "default". */
export function isAllDefaults(
  parameterProvenance: Record<string, ParameterProvenance>,
): boolean {
  return (
    Object.keys(parameterProvenance).length > 0 &&
    Object.values(parameterProvenance).every((p) => p.origin === "default")
  );
}

/**
 * The keys carrying a value that this specific query never established:
 * either a project-chosen default or a number invented by the LLM resolver.
 * Used to enforce the hard rule: nothing may reach the simulation engine on
 * an unrequested, unsourced number. A value is only trusted when it is a
 * literature lookup ("resolved") or the person typing the query ("user");
 * both "default" and "llm" are unverified and are blocked identically.
 */
export function unverifiedOriginKeys(
  parameterProvenance: Record<string, ParameterProvenance>,
): string[] {
  return Object.entries(parameterProvenance)
    .filter(
      ([, p]) => p.origin === "default" || p.origin === "llm",
    )
    .map(([key]) => key);
}
