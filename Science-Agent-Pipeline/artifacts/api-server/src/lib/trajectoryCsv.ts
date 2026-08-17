/**
 * The trajectory CSV, with the provenance attached to it.
 *
 * WHY THIS EXISTS
 * ---------------
 * `GET /api/simulate/:jobId/export` returned the trajectory and nothing
 * else: a header row and numbers. Its own docstring described it as "great
 * for researchers who want to import results into R, Python, or Excel".
 *
 * That file is the artifact which OUTLIVES THE SESSION. It gets opened in
 * Excel, plotted, pasted into a lab report, mailed to a supervisor. Every
 * other surface Terrium has — the CLI warning, the API flags, the Antimony
 * comment — is attached to a session that ends. The CSV is the one that
 * leaves the building.
 *
 * And it carried no citation. Terrium's entire claim is that every number
 * traces to a source; the file a student actually takes away had no source
 * on it at all, and no indication that the Km came from a mutant, a
 * different tissue, or another organism.
 *
 * This is the same defect class as ADR 0039 — computed, and not delivered —
 * at the surface where it matters most, because a plot in a report cannot
 * be re-interrogated later.
 *
 * WHY `#` COMMENT LINES
 * ---------------------
 * CSV has no comment standard, so this is a trade-off with a stated reason.
 *
 *   - `pandas.read_csv(path, comment="#")` skips them.
 *   - R's `read.csv(path, comment.char="#")` skips them.
 *   - Excel shows them as rows at the top of column A.
 *
 * The Excel case is the one worth arguing about, and it is why `#` won: a
 * student opening this in Excel SEES the provenance. A sidecar file would
 * parse more cleanly and would be separated from the data the first time
 * anyone emailed one of the two.
 *
 * Stripping the `#` lines yields byte-identical data to the previous
 * behaviour, so nothing that consumed the old format breaks.
 *
 * WHAT IT REFUSES TO DO
 * ---------------------
 * It does not summarise, rank or soften. Every flag the resolver produced
 * is written out verbatim, including the pool-level findings of ADR 0033,
 * 0035 and 0037 — a header that quietly dropped the inconvenient ones would
 * be worse than no header, because it would look complete.
 */

import { attributionLines } from "./dataSources";
import type { ParameterProvenance } from "./provenance";

export interface TrajectoryExportInput {
  runId: string;
  domain: string;
  completedAt?: string;
  parameters: Record<string, unknown>;
  trajectory: Record<string, unknown>[];
  provenance?: {
    reasoning?: string;
    modelCitations?: string[];
    flags?: string[];
  };
  parameterProvenance?: Record<string, ParameterProvenance>;
}

/** `#`-prefixed, and every embedded newline flattened so one logical line
 * stays one physical line. A reason containing a newline would otherwise
 * emit a bare data row into the middle of the header. */
function commentLines(text: string): string[] {
  return text
    // `\s` matches newlines in JS, so this one substitution flattens
    // everything. An explicit `.replace(/\r?\n/g, " ")` sat above it until
    // a mutation removing that line changed no behaviour and failed no
    // test -- it was dead, and a dead line reads as load-bearing to the
    // next person. One mechanism, not two.
    .replace(/\s+/g, " ")
    .trim()
    .split("\n")
    .map((line) => `# ${line}`);
}

function describeParameter(
  key: string,
  value: unknown,
  provenance: ParameterProvenance | undefined,
): string[] {
  const out: string[] = [];
  const origin = provenance?.origin ?? "unknown";
  out.push(...commentLines(`  ${key} = ${String(value)}   [${origin}]`));

  if (provenance?.citation) {
    out.push(...commentLines(`      source: ${provenance.citation}`));
  }
  if (provenance?.organism) {
    out.push(...commentLines(`      organism: ${provenance.organism}`));
  }
  const conditions = provenance?.assayConditions;
  if (conditions && (conditions.ph != null || conditions.temperatureC != null)) {
    const parts: string[] = [];
    if (conditions.ph != null) parts.push(`pH ${conditions.ph}`);
    if (conditions.temperatureC != null) parts.push(`${conditions.temperatureC} C`);
    if (conditions.buffer) parts.push(String(conditions.buffer));
    out.push(...commentLines(`      measured at: ${parts.join(", ")}`));
  }
  // `note` is where a refusal explains itself (ADR 0024, 0029). A defaulted
  // parameter with a note is the single most important thing on this page,
  // because the number beside it was NOT resolved from anything.
  if (provenance?.note) {
    out.push(...commentLines(`      note: ${provenance.note}`));
  }
  return out;
}

/**
 * Build the full CSV: provenance header, then the trajectory.
 *
 * Exported separately from the route so it is testable without an HTTP
 * server — the route it replaced was untested for exactly that reason.
 */
export function buildTrajectoryCsv(input: TrajectoryExportInput): string {
  const lines: string[] = [];

  lines.push(...commentLines("Terrium simulation export"));
  lines.push(...commentLines(`run: ${input.runId}`));
  lines.push(...commentLines(`domain: ${input.domain}`));
  if (input.completedAt) {
    lines.push(...commentLines(`completed: ${input.completedAt}`));
  }
  lines.push("#");

  const paramKeys = Object.keys(input.parameters ?? {}).sort();
  if (paramKeys.length > 0) {
    lines.push(...commentLines("PARAMETERS AND WHERE THEY CAME FROM"));
    for (const key of paramKeys) {
      lines.push(
        ...describeParameter(
          key,
          input.parameters[key],
          input.parameterProvenance?.[key],
        ),
      );
    }
    lines.push("#");
  }

  const citations = input.provenance?.modelCitations ?? [];
  if (citations.length > 0) {
    lines.push(...commentLines("MODEL CITATIONS"));
    for (const citation of citations) {
      lines.push(...commentLines(`  ${citation}`));
    }
    lines.push("#");
  }

  // EVERY flag, verbatim. These now include the pool-level findings of
  // ADR 0033/0035/0037 -- that a compound was present in some candidate
  // rows and absent in others, that the pool mixed enzyme forms, that a
  // row's commentary contradicted its organism column.
  //
  // A reader plotting this file has no other way to learn any of it.
  const flags = input.provenance?.flags ?? [];
  if (flags.length > 0) {
    lines.push(...commentLines("WHAT TO KNOW ABOUT THESE NUMBERS"));
    for (const flag of flags) {
      lines.push(...commentLines(`  - ${flag}`));
    }
    lines.push("#");
  }

  lines.push(
    ...commentLines(
      "Lines beginning with # are provenance, not data. " +
        'pandas: read_csv(path, comment="#")   R: read.csv(path, comment.char="#")',
    ),
  );
  // Who licensed the data, in the file that carries it.
  //
  // NOTICE satisfies CC BY 4.0 §3(a) for the repository, and this file does
  // not travel with the repository — that is the whole premise of the header
  // above. Same reasoning, one clause further: §3(a)(2) allows satisfying the
  // conditions "in any reasonable manner based on the medium", which a
  // comment block naming the licensor and pointing at NOTICE is.
  //
  // Derived from the provenance actually present, and read from
  // docs/data-sources.json so the licence is not restated in a second
  // language. See dataSources.ts and ADR 0063.
  const attribution = attributionLines(input.parameterProvenance);
  if (attribution.length > 0) {
    lines.push(...attribution, "#");
  }

  const trajectory = input.trajectory ?? [];
  if (trajectory.length === 0) {
    // A header with no data is still a truthful document: it says what was
    // asked and that nothing came back. Returning an empty string instead
    // would lose the reason.
    return lines.join("\n") + "\n";
  }

  const headers = Object.keys(trajectory[0]!);
  const rows = trajectory.map((point) =>
    headers.map((h) => String(point[h] ?? "")).join(","),
  );
  return [...lines, headers.join(","), ...rows].join("\n");
}
