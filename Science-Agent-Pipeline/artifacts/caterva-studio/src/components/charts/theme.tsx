/**
 * The charts' visual vocabulary, from the stylesheet's tokens.
 *
 * Series take `--series-1` to `--series-6` (index.css defines them for
 * both themes, each at 3:1 or better against the surface) and, after the
 * sixth, repeat with a dash pattern, so two series are never told apart
 * by colour alone. Colours are given as `var(--token)`, which SVG
 * presentation attributes accept, so a theme switch recolours a drawn
 * chart without re-rendering it.
 */
import { formatNumber } from "@/lib/format";

export const SERIES_COUNT = 6;

export function seriesColor(index: number): string {
  return `var(--series-${(index % SERIES_COUNT) + 1})`;
}

/** Solid for the first six series, then dashed, then dotted. */
export function seriesDash(index: number): string | undefined {
  const round = Math.floor(index / SERIES_COUNT);
  return round === 0 ? undefined : round === 1 ? "6 3" : "1.5 3";
}

export const AXIS = {
  stroke: "var(--rule-strong)",
  tick: { fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-mono)" },
  tickLine: { stroke: "var(--rule-strong)" },
} as const;

export const GRID = { stroke: "var(--rule)", strokeDasharray: "2 4" } as const;

/** Axis tick text: the page's one number format, short. */
export function tick(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? formatNumber(value, 3) : String(value ?? "");
}

export function SeriesSwatch({ index }: { index: number }) {
  return (
    <svg width="18" height="8" viewBox="0 0 18 8" aria-hidden="true" focusable="false">
      <line
        x1="1"
        y1="4"
        x2="17"
        y2="4"
        stroke={seriesColor(index)}
        strokeWidth="2"
        strokeDasharray={seriesDash(index)}
        strokeLinecap="round"
      />
    </svg>
  );
}
