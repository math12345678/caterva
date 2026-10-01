/**
 * The mark every number wears, saying what kind of number it is.
 *
 *   measured     solid signal dot (the mark's own signal dot)
 *   fitted       ring
 *   computed     small square
 *   placeholder  hollow dashed dot, in the caution colour
 *   chosen       short bar; caution when a default chose it, ink when you did
 *
 * Shape carries the meaning and colour only reinforces it, so the marks
 * stay distinguishable in greyscale and to a reader who does not see the
 * colours (docs/studio/CONTRACT.md 17.3). Each has an accessible name.
 */
import type { Provenance, ProvenanceKind } from "@/api/types";

export const PROVENANCE_LABEL: Record<ProvenanceKind, string> = {
  measured: "measured, cited",
  fitted: "fitted",
  computed: "computed by Caterva",
  placeholder: "placeholder, not measured",
  chosen: "chosen",
};

/** One line on what each kind means, for the legend and the detail's heading. */
export const PROVENANCE_MEANING: Record<ProvenanceKind, string> = {
  measured: "a published measurement; activate it for the paper",
  fitted: "estimated from data by a fit",
  computed: "derived by Caterva from other numbers",
  placeholder: "stands in for a measurement nobody has made here",
  chosen: "chosen by you, or a stated default",
};

export const PROVENANCE_ORDER: readonly ProvenanceKind[] = ["measured", "fitted", "computed", "placeholder", "chosen"];

export function provenanceLabel(p: Pick<Provenance, "kind" | "by">): string {
  if (p.kind === "chosen") return p.by === "user" ? "chosen by you" : "a stated default";
  return PROVENANCE_LABEL[p.kind];
}

export function ProvenanceMark({
  provenance,
  size = 10,
  decorative = false,
}: {
  provenance: Pick<Provenance, "kind" | "by">;
  size?: number;
  /** Hidden from assistive technology when the surrounding text already names the kind. */
  decorative?: boolean;
}) {
  const label = provenanceLabel(provenance);
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 10 10",
    focusable: "false" as const,
    ...(decorative ? { "aria-hidden": true as const } : { role: "img", "aria-label": label }),
  };
  switch (provenance.kind) {
    case "measured":
      return (
        <svg {...common} className="prov-mark" data-kind="measured">
          <circle cx="5" cy="5" r="4" fill="var(--prov-measured)" />
        </svg>
      );
    case "fitted":
      return (
        <svg {...common} className="prov-mark" data-kind="fitted">
          <circle cx="5" cy="5" r="3.35" fill="none" stroke="var(--prov-fitted)" strokeWidth="1.5" />
        </svg>
      );
    case "computed":
      return (
        <svg {...common} className="prov-mark" data-kind="computed">
          <rect x="2.25" y="2.25" width="5.5" height="5.5" fill="var(--prov-computed)" />
        </svg>
      );
    case "placeholder":
      return (
        <svg {...common} className="prov-mark" data-kind="placeholder">
          <circle
            cx="5"
            cy="5"
            r="3.4"
            fill="none"
            stroke="var(--prov-placeholder)"
            strokeWidth="1.35"
            strokeDasharray="1.7 1.35"
          />
        </svg>
      );
    case "chosen":
      return (
        <svg {...common} className="prov-mark" data-kind="chosen" data-by={provenance.by ?? "default"}>
          <rect
            x="1.25"
            y="4.1"
            width="7.5"
            height="1.8"
            rx="0.4"
            fill={provenance.by === "user" ? "var(--prov-chosen)" : "var(--prov-placeholder)"}
          />
        </svg>
      );
  }
}
