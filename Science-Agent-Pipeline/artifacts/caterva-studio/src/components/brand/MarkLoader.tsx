/**
 * The mark in motion: how the studio says "working", instead of a spinner.
 *
 * The C is drawn faint and a reading head travels round it, dot by dot,
 * from the upper end to the open end: each dot swells and takes the signal
 * colour as the head passes, the way a chain of evidence is read link by
 * link. When the work can be counted (a stage with a `fraction`), the dots
 * fill in instead: eight dots, each one-eighth of the work, the next one
 * breathing. Transform and opacity only (index.css, `.mark-loader`).
 *
 * Under prefers-reduced-motion nothing travels: the mark stands complete,
 * and a counted stage still fills its dots, because that is state, not
 * motion. The label beside it (Loading.tsx) always carries the meaning.
 */
import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";

import { MARK_RING, MARK_VIEWBOX } from "./Mark";

const ASPECT = 514 / 634;

export function MarkLoader({
  size = 36,
  fraction = null,
  still = false,
  className,
}: {
  size?: number;
  /** 0..1 when the work can be counted; null when it cannot. */
  fraction?: number | null;
  /** Draw the finished mark without motion (a paused or static place). */
  still?: boolean;
  className?: string;
}) {
  const counted = fraction !== null && Number.isFinite(fraction);
  const done = counted ? Math.max(0, Math.min(MARK_RING.length, Math.floor((fraction as number) * MARK_RING.length))) : 0;
  const mode = still ? "static" : counted ? "determinate" : "indeterminate";
  return (
    <svg
      viewBox={MARK_VIEWBOX}
      height={size}
      width={size * ASPECT}
      className={cn("mark-loader", className)}
      data-mode={mode}
      aria-hidden="true"
      focusable="false"
      overflow="visible"
    >
      {MARK_RING.map(([cx, cy, r], i) => (
        <g
          key={`${cx}-${cy}`}
          className="ml-dot"
          style={{ "--i": i } as CSSProperties}
          data-home={i === 0 ? "true" : undefined}
          data-done={counted ? String(i < done) : undefined}
          data-next={counted && i === done ? "true" : undefined}
        >
          <circle className="ml-ink" cx={cx} cy={cy} r={r} fill="currentColor" />
          <circle className="ml-signal" cx={cx} cy={cy} r={r} fill="var(--signal)" />
        </g>
      ))}
    </svg>
  );
}
