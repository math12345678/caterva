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
 * stay distinguishable without colour (docs/studio/CONTRACT.md, "Provenance
 * as the visual system"). Each has an accessible name.
 */
import type { Provenance, ProvenanceKind } from "@/api/types";

export const PROVENANCE_LABEL: Record<ProvenanceKind, string> = {
  measured: "measured, cited",
  fitted: "fitted",
  computed: "computed by Caterva",
  placeholder: "placeholder, not measured",
  chosen: "chosen",
};

export function provenanceLabel(p: Provenance): string {
  if (p.kind === "chosen") return p.by === "user" ? "chosen by you" : "a stated default";
  return PROVENANCE_LABEL[p.kind];
}

export function ProvenanceMark({ provenance, size = 10 }: { provenance: Provenance; size?: number }) {
  const label = provenanceLabel(provenance);
  const common = { width: size, height: size, viewBox: "0 0 10 10", role: "img", "aria-label": label } as const;
  switch (provenance.kind) {
    case "measured":
      return (
        <svg {...common} className="prov-mark prov-measured">
          <circle cx="5" cy="5" r="4" fill="var(--prov-measured)" />
        </svg>
      );
    case "fitted":
      return (
        <svg {...common} className="prov-mark prov-fitted">
          <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--prov-fitted)" strokeWidth="1.4" />
        </svg>
      );
    case "computed":
      return (
        <svg {...common} className="prov-mark prov-computed">
          <rect x="2" y="2" width="6" height="6" fill="var(--prov-computed)" />
        </svg>
      );
    case "placeholder":
      return (
        <svg {...common} className="prov-mark prov-placeholder">
          <circle
            cx="5"
            cy="5"
            r="3.4"
            fill="none"
            stroke="var(--prov-placeholder)"
            strokeWidth="1.3"
            strokeDasharray="1.6 1.4"
          />
        </svg>
      );
    case "chosen":
      return (
        <svg {...common} className="prov-mark prov-chosen">
          <rect
            x="1.5"
            y="4.2"
            width="7"
            height="1.6"
            fill={provenance.by === "user" ? "var(--prov-chosen)" : "var(--prov-placeholder)"}
          />
        </svg>
      );
  }
}
