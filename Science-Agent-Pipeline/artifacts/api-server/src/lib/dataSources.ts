/**
 * Who licensed the data in an exported file — read from the one table.
 *
 * WHY THIS EXISTS
 * ---------------
 * Dr Lisa Jeske (BRENDA / Leibniz Institute DSMZ) raised BRENDA's CC BY 4.0
 * obligations. `NOTICE` answers them for the repository, and ADR 0063 put the
 * attribution into the exported Antimony model and SBML — because `NOTICE`
 * stays in the repository and those files leave.
 *
 * The trajectory CSV leaves too. Its own docstring calls it "the artifact
 * that OUTLIVES THE SESSION... opened in Excel, plotted, pasted into a lab
 * report, mailed to a supervisor", and it carries the resolved Km in its
 * header with the BRENDA reference beside it. It had no licence on it.
 *
 * WHY IT READS A JSON FILE INSTEAD OF DECLARING THE TABLE HERE
 * -----------------------------------------------------------
 * The model exports are built in Python, this one in TypeScript. Restating
 * the licence in a second language is ADR 0003 (two copies of a numeric
 * bound, drifted) and ADR 0027 (one reliability score implemented twice,
 * computing different things) with a licence attached — and a licence is a
 * worse thing to be wrong about, because the failure is silent and the party
 * harmed is not the person running the code.
 *
 * So `docs/data-sources.json` is the source, and both languages read it.
 * Not generated, so it is not committed build output either
 * (`check_no_generated_files_tracked.py`).
 *
 * WHAT IT REFUSES TO DO
 * ---------------------
 * Credit a source that contributed nothing to THIS export. A CSV built from
 * user-supplied values names nobody. Naming BRENDA on a file BRENDA had no
 * part in is a false provenance claim, and under CC BY 4.0 §2(a)(6) it is
 * the endorsement the licence forbids implying — the defect ADR 0073 found
 * in `modelCitations`.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

import { findRepositoryRoot } from "./repoRoot";

export interface DataSource {
  /** Matched case-insensitively against a provenance `source`/`citation`. */
  tokens: string[];
  /** CC BY 4.0 §3(a)(1)(A)(i) — identification of the creator. */
  creator: string;
  /** §3(a)(1)(A)(v) — a URI to the Licensed Material. */
  source_uri: string;
  /** §3(a)(1)(C) — the licence and a URI to its text. */
  licence: string | null;
  licence_uri: string | null;
  /** §3(a)(1)(B) — what Caterva does to the data. */
  modifications: string;
  /** Where the full attribution lives, per §3(a)(2). */
  notice_uri: string;
  /** How the source asks to be cited. Distinct from the licence obligation. */
  citation_request: string | null;
}

let cached: DataSource[] | undefined;

/**
 * The table, read once.
 *
 * Throws rather than returning `[]` if the file is missing or empty.
 * Degrading to "no sources" would strip attribution from every export while
 * every test asserting "a file with no resolved values credits nobody" kept
 * passing — the first sign would be a shipped CSV with no licence on it.
 */
export function loadDataSources(repoRoot?: string): DataSource[] {
  if (cached && !repoRoot) return cached;

  const root = repoRoot ?? findRepositoryRoot(__dirname);
  const file = path.join(root, "docs", "data-sources.json");
  const parsed = JSON.parse(readFileSync(file, "utf8")) as {
    sources?: DataSource[];
  };

  if (!parsed.sources || parsed.sources.length === 0) {
    throw new Error(
      `${file} lists no data sources. An empty table would silently strip ` +
        "attribution from every export rather than fail visibly.",
    );
  }

  if (!repoRoot) cached = parsed.sources;
  return parsed.sources;
}

/** Reset the cache. Tests only. */
export function _resetCache(): void {
  cached = undefined;
}

interface ProvenanceLike {
  source?: string;
  citation?: string;
}

/**
 * Which described sources contributed to this export, plus any that are
 * named in the provenance but have no licence record here.
 *
 * An unrecorded source produces a line saying so, never silence: "we do not
 * know the terms" and "there are no terms" must not render alike.
 */
export function sourcesUsed(
  provenance: Record<string, ProvenanceLike | undefined> | undefined,
  sources: DataSource[] = loadDataSources(),
): Array<{ source: DataSource | null; label: string }> {
  const labels = new Set<string>();
  for (const entry of Object.values(provenance ?? {})) {
    for (const value of [entry?.source, entry?.citation]) {
      if (typeof value === "string" && value.trim()) labels.add(value.trim());
    }
  }

  const described = new Set<DataSource>();
  const unknown = new Set<string>();
  for (const label of labels) {
    const lowered = label.toLowerCase();
    const match = sources.find((s) =>
      s.tokens.some((token) => lowered.includes(token)),
    );
    if (match) described.add(match);
    else if (looksLikeADatabaseReference(lowered)) unknown.add(label);
  }

  const ordered: Array<{ source: DataSource | null; label: string }> = [];
  for (const source of sources) {
    if (described.has(source)) ordered.push({ source, label: source.creator });
  }
  for (const label of [...unknown].sort()) ordered.push({ source: null, label });
  return ordered;
}

/**
 * Whether a provenance label names an external source at all.
 *
 * Deliberately narrow, mirroring the Python side: `origin: user` and a
 * model-structure note are not databases, and an "unknown licence" warning on
 * every hand-supplied value would train a reader to skip the block — ADR
 * 0028's reasoning about buffer strings.
 */
function looksLikeADatabaseReference(label: string): boolean {
  if (label.includes("://")) return true;
  const parts = label.replace(/:/g, " ").split(/\s+/);
  if (parts.includes("ref")) return true;
  return parts.some((part) => /^\d{4,}$/.test(part));
}

/**
 * What, if anything, a source requires of someone publishing this run.
 *
 * Three states, because two would make a `null` do the work of a fact:
 *
 *   `cite`     the source asks to be cited, and `citationRequest` says how.
 *   `none`     the source's terms are recorded and require no citation.
 *              NCBI Taxonomy is public domain; NOTICE says it "asks to be
 *              cited but does not require it as a licence condition".
 *   `unknown`  Caterva has no record of this source's terms. Not the same
 *              as `none`, and the distinction is the whole point.
 */
export type ObligationKind = "cite" | "none" | "unknown";

export interface SourceObligation {
  /** The source's short name, e.g. `brenda`. */
  source: string;
  creator: string;
  licence: string | null;
  licenceUri: string | null;
  sourceUri: string | null;
  /**
   * What is required. Read this rather than inferring from
   * `citationRequest === null`, which cannot distinguish "nothing is
   * required" from "we do not know what is required".
   */
  requirement: ObligationKind;
  /** How to cite, when `requirement === "cite"`. `null` otherwise. */
  citationRequest: string | null;
}

/**
 * What the sources behind this run ask of someone who publishes it.
 *
 * WHY THE AUDIT NEEDS THIS
 * ------------------------
 * `/api/simulate/:jobId/audit` is described as a "publication-ready audit"
 * and returns `publicationReady: boolean` — a green light for putting the
 * numbers in a paper. It reported per-parameter DOIs and PMIDs and said
 * nothing about what publishing the data obliges, while `NOTICE` says:
 *
 *   "If you use BRENDA data in scientific work, cite BRENDA's current
 *    publication [...] Citing Caterva is not a substitute for citing
 *    BRENDA."
 *
 * The one surface that judges publication-readiness was silent on the
 * requirements of publication.
 *
 * This does NOT change what `publicationReady` means. Whether the user has
 * actually cited BRENDA is not something Caterva can observe, and folding an
 * unobservable condition into a boolean would make the boolean a guess.
 * The obligations are reported alongside it, for the person to act on.
 */
export function citationObligations(
  provenance: Record<string, ProvenanceLike | undefined> | undefined,
  sources: DataSource[] = loadDataSources(),
): SourceObligation[] {
  return sourcesUsed(provenance, sources)
    .filter((used) => used.source !== null)
    .map(({ source }) => ({
      source: source!.tokens[0]!,
      creator: source!.creator,
      licence: source!.licence,
      licenceUri: source!.licence_uri,
      sourceUri: source!.source_uri || null,
      // A source that contributed is always LISTED -- a reader about to
      // publish should know NCBI Taxonomy was used even though it requires
      // no citation. What varies is what it REQUIRES, and that is stated
      // rather than left to be inferred from a null.
      requirement: source!.citation_request
        ? ("cite" as const)
        : source!.licence
          ? ("none" as const)
          : ("unknown" as const),
      citationRequest: source!.citation_request,
    }));
}

/**
 * The attribution as comment lines, prefixed for the target format.
 *
 * Returns `[]` when no described source contributed.
 */
export function attributionLines(
  provenance: Record<string, ProvenanceLike | undefined> | undefined,
  comment = "#",
  sources: DataSource[] = loadDataSources(),
): string[] {
  const used = sourcesUsed(provenance, sources);
  if (used.length === 0) return [];

  const lines: string[] = [
    `${comment} DATA SOURCES AND THEIR LICENCES`,
    `${comment}`,
    `${comment} Values in this file were resolved from the sources below. They are`,
    `${comment} credited here because the file travels without the repository that`,
    `${comment} documents them.`,
    `${comment}`,
    `${comment} None of these sources produced, reviewed or endorsed this file.`,
    `${comment} Caterva selected and combined the values; any error in doing so is`,
    `${comment} Caterva's, not theirs.`,
  ];

  for (const { source, label } of used) {
    lines.push(`${comment}`);
    if (!source) {
      lines.push(`${comment}   ${label}`);
      lines.push(
        `${comment}     licence: NOT RECORDED by Caterva. Check the source's own`,
        `${comment}              terms before redistributing this file.`,
      );
      continue;
    }

    lines.push(`${comment}   ${source.creator}`);
    const licence = source.licence
      ? source.licence_uri
        ? `${source.licence} (${source.licence_uri})`
        : source.licence
      : "NOT RECORDED by Caterva";
    lines.push(`${comment}     licence: ${licence}`);
    if (source.source_uri) {
      lines.push(`${comment}     source:  ${source.source_uri}`);
    }
    lines.push(`${comment}     changes: ${source.modifications}`);
    if (source.citation_request) {
      lines.push(`${comment}     cite:    ${source.citation_request}`);
    }
    lines.push(
      `${comment}     full attribution and warranty disclaimer: ${source.notice_uri}`,
    );
  }

  return lines;
}
