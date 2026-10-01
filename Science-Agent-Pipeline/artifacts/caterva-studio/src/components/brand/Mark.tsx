/**
 * The caterva mark: a C of eight dots, seven ink and one signal.
 *
 * The geometry is the measured one from docs/brand/caterva-mark.svg, the
 * same numbers as the site's Mark.tsx; it is never redrawn by eye. Ink
 * follows `currentColor` and the signal dot follows `--signal`, so both
 * flip with the theme.
 *
 * `MARK_RING` lists the same dots in the order a reader's eye travels the
 * C, from its upper end (the signal dot) round the back to its open end.
 * The loading mark (MarkLoader) moves along that order, so its motion
 * follows the letter rather than spinning.
 */
import { cn } from "@/lib/cn";

export type MarkDot = readonly [cx: number, cy: number, r: number, signal: boolean];

export const MARK_DOTS: ReadonlyArray<MarkDot> = [
  [541.3, 242.6, 61.7, false],
  [386.5, 281.7, 44.2, false],
  [688.7, 309.3, 50.9, true],
  [305.1, 403.8, 59.6, false],
  [297.4, 569.0, 44.2, false],
  [382.6, 697.4, 60.2, false],
  [680.8, 684.5, 44.2, false],
  [542.5, 744.6, 53.5, false],
];

/** The dots from the C's upper end (signal) to its open end. */
export const MARK_RING: ReadonlyArray<MarkDot> = [
  [688.7, 309.3, 50.9, true],
  [541.3, 242.6, 61.7, false],
  [386.5, 281.7, 44.2, false],
  [305.1, 403.8, 59.6, false],
  [297.4, 569.0, 44.2, false],
  [382.6, 697.4, 60.2, false],
  [542.5, 744.6, 53.5, false],
  [680.8, 684.5, 44.2, false],
];

export const MARK_VIEWBOX = "236 172 514 634";
const ASPECT = 514 / 634;

export function Mark({ size = 20, className = "", title }: { size?: number; className?: string; title?: string }) {
  return (
    <svg
      viewBox={MARK_VIEWBOX}
      height={size}
      width={size * ASPECT}
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {MARK_DOTS.map(([cx, cy, r, signal]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} fill={signal ? "var(--signal)" : "currentColor"} />
      ))}
    </svg>
  );
}

/** The wordmark alone: lowercase Spectral, widely tracked. */
export function Wordmark({ size = 16, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={cn("wordmark leading-none", className)} style={{ fontSize: size }}>
      caterva
    </span>
  );
}

/** Mark and wordmark together. */
export function Lockup({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center", className)} style={{ gap: size * 0.5 }}>
      <Mark size={size} />
      <Wordmark size={size * 0.74} />
    </span>
  );
}
