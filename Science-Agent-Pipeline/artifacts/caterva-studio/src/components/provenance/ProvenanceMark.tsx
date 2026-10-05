/**
 * The mark every number wears, saying what kind of number it is.
 *
 *   measured     solid signal dot (the mark's own signal dot)
 *   fitted       heavy solid ring
 *   computed     small square
 *   placeholder  lighter ring in four coarse dashes, in the caution colour
 *   chosen       filled diamond when you chose it; an outlined diamond with
 *                a tick, in the caution colour, when a stated default did
 *   ai           open hexagon with a centre dot, in the muted ink: text or a
 *                suggestion an assistant wrote, never a measurement. It is
 *                not an engine kind; no number ever wears it
 *
 * Shape carries the meaning and colour only reinforces it, so the marks
 * stay distinguishable in greyscale and to a reader who does not see the
 * colours (docs/studio/CONTRACT.md 17.3). They are drawn at 12 px at the
 * least, the size at which a dashed ring and a solid ring, and a filled and
 * an outlined diamond, can still be told apart. Each has an accessible name.
 */
import type { ChosenBy, MarkKind } from "@/api/types";

/** What a mark is drawn for: a kind, and for `chosen` who chose. */
export interface MarkSubject {
  kind: MarkKind;
  by?: ChosenBy;
}

export const PROVENANCE_LABEL: Record<MarkKind, string> = {
  measured: "measured, cited",
  fitted: "fitted",
  computed: "computed by Caterva",
  placeholder: "placeholder, not measured",
  chosen: "chosen",
  ai: "suggested by an assistant, not a measurement",
};

/** One line on what each kind means, for the legend and the detail's heading. */
export const PROVENANCE_MEANING: Record<MarkKind, string> = {
  measured: "a published measurement; activate it for the paper",
  fitted: "estimated from data by a fit",
  computed: "derived by Caterva from other numbers",
  placeholder: "stands in for a measurement nobody has made here",
  chosen: "chosen by you, or a stated default",
  ai: "wording or a suggestion from an assistant; checked against your results, never a measurement",
};

export const PROVENANCE_ORDER: readonly MarkKind[] = ["measured", "fitted", "computed", "placeholder", "chosen", "ai"];

export function provenanceLabel(p: MarkSubject): string {
  if (p.kind === "chosen") return p.by === "user" ? "chosen by you" : "a stated default";
  return PROVENANCE_LABEL[p.kind];
}

/** The smallest a mark is drawn, in px. */
export const MARK_SIZE = 12;

export function ProvenanceMark({
  provenance,
  size = MARK_SIZE,
  decorative = false,
}: {
  provenance: MarkSubject;
  size?: number;
  /** Hidden from assistive technology when the surrounding text already names the kind. */
  decorative?: boolean;
}) {
  const label = provenanceLabel(provenance);
  const common = {
    width: Math.max(size, MARK_SIZE),
    height: Math.max(size, MARK_SIZE),
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
          <circle cx="5" cy="5" r="3.1" fill="none" stroke="var(--prov-fitted)" strokeWidth="2" />
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
            r="3.6"
            fill="none"
            stroke="var(--prov-placeholder)"
            strokeWidth="1.3"
            strokeDasharray="3.1 2.15"
          />
        </svg>
      );
    case "ai":
      return (
        <svg {...common} className="prov-mark" data-kind="ai">
          <polygon
            points="5,0.9 8.55,2.95 8.55,7.05 5,9.1 1.45,7.05 1.45,2.95"
            fill="none"
            stroke="var(--prov-ai)"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
          <circle cx="5" cy="5" r="1.15" fill="var(--prov-ai)" />
        </svg>
      );
    case "chosen":
      return provenance.by === "user" ? (
        <svg {...common} className="prov-mark" data-kind="chosen" data-by="user">
          <polygon points="5,0.6 9.4,5 5,9.4 0.6,5" fill="var(--prov-chosen)" />
        </svg>
      ) : (
        <svg {...common} className="prov-mark" data-kind="chosen" data-by="default">
          <polygon points="5,0.9 9.1,5 5,9.1 0.9,5" fill="none" stroke="var(--prov-placeholder)" strokeWidth="1.2" />
          <path d="M3.3 5.1 4.6 6.4 6.8 3.7" fill="none" stroke="var(--prov-placeholder)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
  }
}
