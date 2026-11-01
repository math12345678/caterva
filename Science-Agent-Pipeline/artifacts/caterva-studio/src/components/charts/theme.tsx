/**
 * The charts' visual vocabulary, from the stylesheet's tokens.
 *
 * Series take `--series-1` to `--series-6` (index.css defines them for
 * both themes: each 3:1 or better against the surface, neighbours 3:1 or
 * better against each other). Every series also has its own dash pattern,
 * its own marker shape where it has few points, and a direct label at the
 * end of its line, so no two are told apart by colour alone. Colours are given as `var(--token)`, which SVG
 * presentation attributes accept, so a theme switch recolours a drawn
 * chart without re-rendering it.
 */
import { formatNumber } from "@/lib/format";

export const SERIES_COUNT = 6;

export function seriesColor(index: number): string {
  return `var(--series-${(index % SERIES_COUNT) + 1})`;
}

/**
 * One dash pattern per series, so no two are told apart by hue alone:
 * solid, long dashes, dots, dash-dot, fine dots, dash-dot-dot. After the
 * sixth the colours repeat, and the patterns are shifted by three so a
 * repeated colour never repeats its pattern.
 */
const DASHES: readonly (string | undefined)[] = [undefined, "8 4", "1.5 3.5", "9 3 2 3", "3 3", "7 3 2 3 2 3"];

export function seriesDash(index: number): string | undefined {
  const round = Math.floor(index / SERIES_COUNT);
  return DASHES[(index + round * 3) % SERIES_COUNT];
}

/** Marker shapes, one per series, drawn where a series has few enough points to count. */
export const MARKER_SHAPES = ["circle", "square", "triangle", "diamond", "cross", "ring"] as const;
export type MarkerShape = (typeof MARKER_SHAPES)[number];

export function seriesMarker(index: number): MarkerShape {
  return MARKER_SHAPES[index % MARKER_SHAPES.length];
}

/** At or below this many points a series wears markers, so each observation is visible. */
export const SPARSE_POINTS = 24;

/** A marker drawn at (cx, cy) in the series' colour. Returns null where the point is a gap. */
export function SeriesMarker({ cx, cy, index, value }: { cx?: number; cy?: number; index: number; value?: unknown }) {
  if (typeof cx !== "number" || typeof cy !== "number" || value === null || value === undefined) return null;
  const colour = seriesColor(index);
  const r = 3.5;
  switch (seriesMarker(index)) {
    case "square":
      return <rect x={cx - r + 0.5} y={cy - r + 0.5} width={2 * r - 1} height={2 * r - 1} fill={colour} />;
    case "triangle":
      return <polygon points={`${cx},${cy - r - 0.5} ${cx + r + 0.5},${cy + r - 0.5} ${cx - r - 0.5},${cy + r - 0.5}`} fill={colour} />;
    case "diamond":
      return <polygon points={`${cx},${cy - r - 1} ${cx + r + 1},${cy} ${cx},${cy + r + 1} ${cx - r - 1},${cy}`} fill={colour} />;
    case "cross":
      return <path d={`M${cx - r} ${cy - r}L${cx + r} ${cy + r}M${cx - r} ${cy + r}L${cx + r} ${cy - r}`} stroke={colour} strokeWidth={1.75} fill="none" />;
    case "ring":
      return <circle cx={cx} cy={cy} r={r} fill="var(--surface)" stroke={colour} strokeWidth={1.5} />;
    default:
      return <circle cx={cx} cy={cy} r={r} fill={colour} />;
  }
}

/** A readable end-of-line label's height in px; labels closer than this are spread apart. */
export const LABEL_GAP = 12;

/**
 * Where each end-of-line label sits, in px from the plot's top, so that
 * labels of series that finish at nearly the same value do not overprint.
 * `ends` are the series' last values (null for a series with none), `domain`
 * the y axis's [min, max] and `plotHeight` its height in px. Labels keep
 * their order; a crowd is spread symmetrically about its centre, then kept
 * inside the plot.
 */
export function spreadLabels(
  ends: readonly (number | null)[],
  domain: readonly [number, number],
  plotHeight: number,
): (number | null)[] {
  const [lo, hi] = domain;
  const span = hi - lo || 1;
  const wanted = ends.map((v) => (v === null || !Number.isFinite(v) ? null : (1 - (v - lo) / span) * plotHeight));
  const order = wanted
    .map((y, i) => ({ y, i }))
    .filter((e): e is { y: number; i: number } => e.y !== null)
    .sort((a, b) => a.y - b.y);
  const placed = order.map((e) => e.y);
  for (let pass = 0; pass < 50; pass++) {
    let moved = false;
    for (let k = 1; k < placed.length; k++) {
      const gap = placed[k] - placed[k - 1];
      if (gap < LABEL_GAP - 1e-9) {
        const push = (LABEL_GAP - gap) / 2;
        placed[k - 1] -= push;
        placed[k] += push;
        moved = true;
      }
    }
    if (!moved) break;
  }
  const shift = placed.length ? Math.max(0, 6 - placed[0]) : 0;
  const out: (number | null)[] = ends.map(() => null);
  order.forEach((e, k) => {
    out[e.i] = Math.min(plotHeight - 2, placed[k] + shift);
  });
  return out;
}

/**
 * Round ticks for an axis: `count` or so values on 1, 2, 5 steps, and the
 * domain widened to hold them when `nice` (a y axis); an x axis keeps its
 * data's own ends and takes only the round ticks inside them.
 */
export function niceTicks(min: number, max: number, count = 5, nice = false): { domain: [number, number]; ticks: number[] } {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { domain: [0, 1], ticks: [0, 1] };
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    return niceTicks(min - pad, max + pad, count, nice);
  }
  const rough = (max - min) / Math.max(1, count);
  const pow = 10 ** Math.floor(Math.log10(rough));
  const f = rough / pow;
  const step = (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * pow;
  const first = Math.ceil(min / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = first; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toPrecision(12)));
  if (!nice) return { domain: [min, max], ticks };
  const lo = Math.floor(min / step + 1e-9) * step;
  const hi = Math.ceil(max / step - 1e-9) * step;
  const all: number[] = [];
  for (let v = lo; v <= hi + step * 1e-9; v += step) all.push(Number(v.toPrecision(12)));
  return { domain: [Number(lo.toPrecision(12)), Number(hi.toPrecision(12))], ticks: all };
}

/** "time (s)", or just "time" when the unit is not specified ("time units" is not a unit). */
export function timeAxisTitle(timeUnit: string | null | undefined): string {
  const unit = (timeUnit ?? "").trim();
  return unit === "" || /^time units?$/i.test(unit) ? "time" : `time (${unit})`;
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
