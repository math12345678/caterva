/**
 * The key to the six marks (the engine's five and the assistant's), in the same order everywhere. A screen shows
 * it once, near the first table of numbers; with `counts` it also says how
 * many of each kind the screen holds, so "three placeholders" is visible
 * before anyone opens a number.
 */
import type { MarkKind, ProvenanceKind, SourcedValue } from "@/api/types";

import { PROVENANCE_MEANING, PROVENANCE_ORDER, ProvenanceMark, provenanceLabel } from "./ProvenanceMark";

/** How many values of each kind (chosen split by who chose). */
export function countKinds(values: readonly SourcedValue[]): Partial<Record<ProvenanceKind, number>> {
  const out: Partial<Record<ProvenanceKind, number>> = {};
  for (const v of values) out[v.provenance.kind] = (out[v.provenance.kind] ?? 0) + 1;
  return out;
}

export function ProvenanceLegend({
  counts,
  layout = "row",
  only,
}: {
  counts?: Partial<Record<MarkKind, number>>;
  layout?: "row" | "stack";
  /** Show only these kinds (those that occur on the screen). */
  only?: readonly MarkKind[];
}) {
  const kinds = PROVENANCE_ORDER.filter((k) => (only ? only.includes(k) : true));
  return (
    <ul className="legend" data-layout={layout} aria-label="What the marks mean">
      {kinds.map((kind) => (
        <li key={kind}>
          <ProvenanceMark provenance={{ kind, by: kind === "chosen" ? "user" : undefined }} decorative />
          <span>
            {kind === "chosen" ? (
              <>
                chosen by you <ProvenanceMark provenance={{ kind, by: "default" }} decorative /> stated default
              </>
            ) : (
              provenanceLabel({ kind })
            )}
            {counts && counts[kind] !== undefined ? (
              <span className="font-mono legend-count"> {counts[kind]}</span>
            ) : null}
            {layout === "stack" ? <span className="legend-meaning"> · {PROVENANCE_MEANING[kind]}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
