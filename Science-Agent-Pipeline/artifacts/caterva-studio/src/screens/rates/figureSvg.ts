/**
 * The Rates figure as one SVG string, drawn the same way for the page and for
 * a paper.
 *
 * WHY A STRING AND NOT A CHART COMPONENT
 * The figure has to leave the page as a file: a standalone SVG a journal's
 * editor can open, and a PNG at print resolution. A string built from the
 * server's numbers is the one thing both can be made from, so what is saved
 * is exactly what was drawn. The page draws it with the theme's tokens
 * (`var(--series-1)`), so a theme switch recolours it; a file cannot use
 * `var()`, so the paper theme uses fixed colours, the light theme's own, on
 * white or on nothing. Ticks, dash patterns and marker shapes come from
 * components/charts/theme.tsx, the same vocabulary the other charts use.
 *
 * WHAT IS DRAWN
 * Per series (a group, an inhibitor level): the measured rates as markers
 * with error bars, the fitted curve in the series' dash pattern, its band
 * (asymptotic and pointwise: the figure's caption says so) and, in the panel
 * beneath, the residuals about zero. Axis titles are the table's own column
 * names and units. Text is text (never outlines) in Helvetica or Arial for a
 * file, so an editor can restyle it. Every point carries a <title>, which is
 * its accessible and hover description; the numbers are also a table.
 *
 * Every string that came from the person (a group label, a column name) goes
 * through `esc`: an SVG built from text must not be able to carry markup.
 */
import { MARKER_SHAPES, niceTicks, type MarkerShape } from "@/components/charts/theme";
import type { RatesFigure, RatesSeries } from "@/api/types";
import { oklchToHex, parseOklch } from "@/lib/contrast";
import { formatNumber } from "@/lib/format";

/** The light theme's series tokens (index.css :root), for a file that cannot use var(). A test holds them equal. */
export const PAPER_SERIES_OKLCH = [
  "oklch(0.309 0.055 240)",
  "oklch(0.605 0.13 72)",
  "oklch(0.325 0.11 330)",
  "oklch(0.586 0.12 150)",
  "oklch(0.325 0.12 27)",
  "oklch(0.591 0.09 215)",
] as const;

const DASHES: readonly (string | null)[] = [null, "8 4", "1.5 3.5", "9 3 2 3", "3 3", "7 3 2 3 2 3"];

export const PAPER_SERIES: readonly string[] = PAPER_SERIES_OKLCH.map((c) => oklchToHex(parseOklch(c)!));

export interface FigureTheme {
  series: (i: number) => string;
  ink: string;
  muted: string;
  axis: string;
  grid: string;
  surface: string;
  bandOpacity: number;
  sans: string;
  mono: string;
}

export const PAGE_THEME: FigureTheme = {
  series: (i) => `var(--series-${(i % 6) + 1})`,
  ink: "var(--fg)",
  muted: "var(--muted)",
  axis: "var(--rule-strong)",
  grid: "var(--rule)",
  surface: "var(--surface)",
  bandOpacity: 0.2,
  sans: "var(--font-sans)",
  mono: "var(--font-mono)",
};

export const PAPER_THEME: FigureTheme = {
  series: (i) => PAPER_SERIES[i % PAPER_SERIES.length],
  ink: "#2A2D35",
  muted: "#55595f",
  axis: "#2A2D35",
  grid: "#e3e3e3",
  surface: "#ffffff",
  bandOpacity: 0.2,
  sans: "Helvetica, Arial, sans-serif",
  mono: "Helvetica, Arial, sans-serif",
};

export interface FigureOptions {
  theme: FigureTheme;
  /** The viewBox, in px for the page and in points (1/72 in) for a paper figure. */
  width: number;
  height: number;
  logX: boolean;
  /** An opaque background rectangle (a paper figure on white); the page draws none. */
  background: boolean;
  /** Text sizes, in the viewBox's units. */
  tick: number;
  label: number;
  legend: number;
  /** Marker radius and line width. */
  marker: number;
  line: number;
  /** A physical size, written on the root so an editor opens it at the right scale. */
  physical?: { widthIn: number; heightIn: number };
  title?: string;
}

export const PAGE_OPTIONS: Omit<FigureOptions, "logX"> = {
  theme: PAGE_THEME,
  width: 760,
  height: 560,
  background: false,
  tick: 11,
  label: 12,
  legend: 12,
  marker: 3.6,
  line: 1.8,
};

/** Inches of a journal's single and double column (89 mm and 183 mm), and the heights the figure is drawn at. */
export const COLUMNS = {
  single: { widthIn: 3.5, heightIn: 4.6, label: "single column (3.5 in, 89 mm)" },
  double: { widthIn: 7.2, heightIn: 4.8, label: "double column (7.2 in, 183 mm)" },
} as const;

export type Column = keyof typeof COLUMNS;

export function paperOptions(column: Column, logX: boolean, background: boolean): FigureOptions {
  const c = COLUMNS[column];
  const narrow = column === "single";
  return {
    theme: PAPER_THEME,
    width: c.widthIn * 72,
    height: c.heightIn * 72,
    logX,
    background,
    tick: narrow ? 6.5 : 7.5,
    label: narrow ? 7.5 : 8.5,
    legend: narrow ? 6.5 : 7.5,
    marker: narrow ? 2.2 : 2.8,
    line: narrow ? 1 : 1.2,
    physical: { widthIn: c.widthIn, heightIn: c.heightIn },
  };
}

export function esc(text: unknown): string {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const n = (x: number) => (Math.round(x * 100) / 100).toString();
const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

function marker(shape: MarkerShape, cx: number, cy: number, r: number, color: string, surface: string, title?: string): string {
  const t = title ? `<title>${esc(title)}</title>` : "";
  switch (shape) {
    case "square":
      return `<rect x="${n(cx - r)}" y="${n(cy - r)}" width="${n(2 * r)}" height="${n(2 * r)}" fill="${color}">${t}</rect>`;
    case "triangle":
      return `<polygon points="${n(cx)},${n(cy - r - 0.6)} ${n(cx + r + 0.6)},${n(cy + r - 0.4)} ${n(cx - r - 0.6)},${n(cy + r - 0.4)}" fill="${color}">${t}</polygon>`;
    case "diamond":
      return `<polygon points="${n(cx)},${n(cy - r - 1)} ${n(cx + r + 1)},${n(cy)} ${n(cx)},${n(cy + r + 1)} ${n(cx - r - 1)},${n(cy)}" fill="${color}">${t}</polygon>`;
    case "cross":
      return `<path d="M${n(cx - r)} ${n(cy - r)}L${n(cx + r)} ${n(cy + r)}M${n(cx - r)} ${n(cy + r)}L${n(cx + r)} ${n(cy - r)}" stroke="${color}" stroke-width="${n(r * 0.55)}" fill="none">${t}</path>`;
    case "ring":
      return `<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(r)}" fill="${surface}" stroke="${color}" stroke-width="${n(r * 0.45)}">${t}</circle>`;
    default:
      return `<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(r)}" fill="${color}">${t}</circle>`;
  }
}

function logTicks(lo: number, hi: number): number[] {
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= lo * 0.999 && v <= hi * 1.001 && (m === 1 || hi / lo < 30)) out.push(Number(v.toPrecision(6)));
    }
  }
  return out;
}

function axisTitle(axis: { column: string; unit: string }): string {
  return axis.unit ? `${axis.column} (${axis.unit})` : axis.column;
}

/** The point's description for hover and assistive technology. */
function pointTitle(series: RatesSeries, fig: RatesFigure, k: number): string {
  const p = series.points;
  const sigma = p.sigma[k];
  const label = series.label ? `${series.label}: ` : "";
  const bar = finite(sigma) ? `, error bar ${formatNumber(sigma)}` : "";
  return `${label}${fig.x.column} ${formatNumber(p.s[k] ?? NaN)}${fig.x.unit ? ` ${fig.x.unit}` : ""}, ${fig.y.column} ${formatNumber(p.v[k] ?? NaN)}${fig.y.unit ? ` ${fig.y.unit}` : ""}${bar}, residual ${formatNumber(p.residual[k] ?? NaN)} (table line ${p.line[k]})`;
}

export interface DrawnFigure {
  svg: string;
  /** Points left off a logarithmic axis because their concentration is zero. */
  hidden: number;
}

export function figureSvg(fig: RatesFigure, o: FigureOptions): DrawnFigure {
  const th = o.theme;
  const W = o.width;
  const H = o.height;
  const left = Math.round(o.label * 5.4);
  const right = Math.round(o.label * 1.2);
  const top = Math.round(o.label * 1.0);
  const bottom = Math.round(o.label * 3.9);
  const gap = Math.round(o.label * 1.6);
  const plotH = H - top - bottom - gap;
  const mainH = Math.round(plotH * 0.68);
  const resH = plotH - mainH;
  const x0 = left;
  const x1 = W - right;
  const yMain0 = top;
  const yMain1 = top + mainH;
  const yRes0 = yMain1 + gap;
  const yRes1 = yRes0 + resH;

  const finiteS: number[] = [];
  const values: number[] = [];
  let hidden = 0;
  for (const s of fig.series) {
    s.points.s.forEach((v, k) => {
      if (!finite(v)) return;
      if (o.logX && v <= 0) {
        hidden += 1;
        return;
      }
      finiteS.push(v);
      const y = s.points.v[k];
      const sd = s.points.sigma[k];
      if (finite(y)) {
        values.push(y);
        if (finite(sd)) values.push(y + sd, y - sd);
      }
    });
    s.curve.s.forEach((v, k) => {
      if (finite(v) && (!o.logX || v > 0)) finiteS.push(v);
      for (const arr of [s.curve.v, s.curve.high, s.curve.low]) {
        const y = arr[k];
        if (finite(y)) values.push(y);
      }
    });
  }
  const sMin = finiteS.length ? Math.min(...finiteS) : 0;
  const sMax = finiteS.length ? Math.max(...finiteS) : 1;
  const xScale = (() => {
    if (o.logX) {
      const lo = Math.max(sMin / 1.4, Number.MIN_VALUE);
      const hi = sMax * 1.3;
      const ticks = logTicks(lo, hi);
      const a = Math.log10(lo);
      const b = Math.log10(hi);
      return { ticks, to: (v: number) => x0 + ((Math.log10(v) - a) / (b - a)) * (x1 - x0) };
    }
    const t = niceTicks(0, sMax * 1.04, 6, true);
    const [a, b] = t.domain;
    return { ticks: t.ticks, to: (v: number) => x0 + ((v - a) / (b - a)) * (x1 - x0) };
  })();
  const yTop = values.length ? Math.max(...values) : 1;
  const yLow = values.length ? Math.min(...values) : 0;
  const yTicks = niceTicks(Math.min(0, yLow), yTop * 1.03, 5, true);
  const yTo = (v: number) => yMain1 - ((v - yTicks.domain[0]) / (yTicks.domain[1] - yTicks.domain[0])) * (yMain1 - yMain0);
  const resAbs = Math.max(
    1e-12,
    ...fig.series.flatMap((s) => s.points.residual.filter(finite).map((r) => Math.abs(r))),
  );
  const rTicks = niceTicks(-resAbs * 1.15, resAbs * 1.15, 4, true);
  const rTo = (v: number) => yRes1 - ((v - rTicks.domain[0]) / (rTicks.domain[1] - rTicks.domain[0])) * (yRes1 - yRes0);

  const out: string[] = [];
  const font = (family: string, size: number, extra = "") =>
    `font-family:${family};font-size:${n(size)}px;${extra}`;
  const unitsAttr = o.physical ? ` width="${o.physical.widthIn}in" height="${o.physical.heightIn}in"` : "";
  const title = o.title ?? "Initial rates and the fitted curves";
  const desc =
    `${fig.series.map((s) => (s.label ? `${s.label}: ` : "") + `${s.law_title} law, ${s.points.s.length} measurements`).join("; ")}. ` +
    `${fig.bars?.text ?? ""} Band: ${fig.series[0]?.band ?? "none"}. Residuals beneath.` +
    (hidden ? ` ${hidden} measurement(s) at zero concentration are not shown on the logarithmic axis.` : "");
  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n(W)} ${n(H)}"${unitsAttr} role="img" aria-labelledby="fig-title fig-desc" data-figure="rates">`,
    `<title id="fig-title">${esc(title)}</title><desc id="fig-desc">${esc(desc)}</desc>`,
  );
  if (o.background) out.push(`<rect x="0" y="0" width="${n(W)}" height="${n(H)}" fill="${th.surface}"/>`);

  // Grid and axes.
  for (const t of yTicks.ticks) {
    out.push(`<line x1="${x0}" x2="${x1}" y1="${n(yTo(t))}" y2="${n(yTo(t))}" stroke="${th.grid}" stroke-width="${n(o.line * 0.5)}"/>`);
  }
  for (const t of xScale.ticks) {
    const x = xScale.to(t);
    out.push(`<line x1="${n(x)}" x2="${n(x)}" y1="${yMain0}" y2="${yMain1}" stroke="${th.grid}" stroke-width="${n(o.line * 0.5)}"/>`);
    out.push(`<line x1="${n(x)}" x2="${n(x)}" y1="${yRes0}" y2="${yRes1}" stroke="${th.grid}" stroke-width="${n(o.line * 0.5)}"/>`);
  }
  const axisW = n(o.line * 0.75);
  out.push(
    `<path d="M${x0} ${yMain0}V${yMain1}H${x1}" fill="none" stroke="${th.axis}" stroke-width="${axisW}"/>`,
    `<path d="M${x0} ${yRes0}V${yRes1}H${x1}" fill="none" stroke="${th.axis}" stroke-width="${axisW}"/>`,
  );
  const tickLen = o.tick * 0.35;
  for (const t of yTicks.ticks) {
    const y = yTo(t);
    out.push(`<line x1="${x0 - tickLen}" x2="${x0}" y1="${n(y)}" y2="${n(y)}" stroke="${th.axis}" stroke-width="${axisW}"/>`);
    out.push(`<text x="${n(x0 - tickLen - 2)}" y="${n(y + o.tick * 0.35)}" text-anchor="end" fill="${th.muted}" style="${font(th.mono, o.tick)}">${esc(formatNumber(t, 3))}</text>`);
  }
  for (const t of rTicks.ticks) {
    const y = rTo(t);
    out.push(`<line x1="${x0 - tickLen}" x2="${x0}" y1="${n(y)}" y2="${n(y)}" stroke="${th.axis}" stroke-width="${axisW}"/>`);
    out.push(`<text x="${n(x0 - tickLen - 2)}" y="${n(y + o.tick * 0.35)}" text-anchor="end" fill="${th.muted}" style="${font(th.mono, o.tick)}">${esc(formatNumber(t, 3))}</text>`);
  }
  for (const t of xScale.ticks) {
    const x = xScale.to(t);
    out.push(`<line x1="${n(x)}" x2="${n(x)}" y1="${yRes1}" y2="${n(yRes1 + tickLen)}" stroke="${th.axis}" stroke-width="${axisW}"/>`);
    out.push(`<text x="${n(x)}" y="${n(yRes1 + tickLen + o.tick * 1.05)}" text-anchor="middle" fill="${th.muted}" style="${font(th.mono, o.tick)}">${esc(formatNumber(t, 3))}</text>`);
  }
  // Axis titles.
  out.push(
    `<text x="${n((x0 + x1) / 2)}" y="${n(H - o.label * 0.55)}" text-anchor="middle" fill="${th.ink}" style="${font(th.sans, o.label)}">${esc(axisTitle(fig.x))}${o.logX ? " (log scale)" : ""}</text>`,
    `<text transform="translate(${n(o.label * 0.95)} ${n((yMain0 + yMain1) / 2)}) rotate(-90)" text-anchor="middle" fill="${th.ink}" style="${font(th.sans, o.label)}">${esc(axisTitle(fig.y))}</text>`,
    `<text transform="translate(${n(o.label * 0.95)} ${n((yRes0 + yRes1) / 2)}) rotate(-90)" text-anchor="middle" fill="${th.ink}" style="${font(th.sans, o.label)}">${esc(fig.y.unit ? `residual (${fig.y.unit})` : "residual")}</text>`,
  );
  // Zero line of the residuals.
  out.push(`<line x1="${x0}" x2="${x1}" y1="${n(rTo(0))}" y2="${n(rTo(0))}" stroke="${th.ink}" stroke-width="${n(o.line * 0.6)}" stroke-dasharray="${n(o.line * 2)} ${n(o.line * 2)}"/>`);

  // Series.
  fig.series.forEach((s, i) => {
    const color = th.series(i);
    const shape = MARKER_SHAPES[i % MARKER_SHAPES.length];
    const dash = DASHES[(i + Math.floor(i / 6) * 3) % 6];
    const cs = s.curve.s;
    // Band.
    const upper: string[] = [];
    const lower: string[] = [];
    cs.forEach((v, k) => {
      const hi = s.curve.high[k];
      const lo = s.curve.low[k];
      if (!finite(v) || !finite(hi) || !finite(lo) || (o.logX && v <= 0)) return;
      upper.push(`${n(xScale.to(v))},${n(yTo(hi))}`);
      lower.push(`${n(xScale.to(v))},${n(yTo(lo))}`);
    });
    if (upper.length > 1) {
      out.push(`<polygon points="${upper.join(" ")} ${lower.reverse().join(" ")}" fill="${color}" fill-opacity="${th.bandOpacity}" stroke="none" data-role="band"/>`);
    }
    // Curve.
    const path = cs
      .map((v, k) => ({ v, y: s.curve.v[k] }))
      .filter((p) => finite(p.v) && finite(p.y) && (!o.logX || (p.v as number) > 0))
      .map((p, k) => `${k ? "L" : "M"}${n(xScale.to(p.v as number))} ${n(yTo(p.y as number))}`)
      .join("");
    if (path) {
      out.push(`<path d="${path}" fill="none" stroke="${color}" stroke-width="${n(o.line)}"${dash ? ` stroke-dasharray="${dash}"` : ""} stroke-linecap="round" stroke-linejoin="round" data-role="curve"/>`);
    }
    // Error bars, then markers.
    const cap = o.marker * 0.9;
    s.points.s.forEach((sv, k) => {
      const y = s.points.v[k];
      if (!finite(sv) || !finite(y) || (o.logX && sv <= 0)) return;
      const sd = s.points.sigma[k];
      const cx = xScale.to(sv);
      if (finite(sd) && sd > 0) {
        const a = yTo(y + sd);
        const b = yTo(y - sd);
        out.push(`<path d="M${n(cx)} ${n(a)}V${n(b)}M${n(cx - cap)} ${n(a)}H${n(cx + cap)}M${n(cx - cap)} ${n(b)}H${n(cx + cap)}" fill="none" stroke="${color}" stroke-width="${n(o.line * 0.7)}" data-role="bar"/>`);
      }
    });
    s.points.s.forEach((sv, k) => {
      const y = s.points.v[k];
      if (!finite(sv) || !finite(y) || (o.logX && sv <= 0)) return;
      out.push(`<g data-role="point" data-series="${esc(s.key)}">${marker(shape, xScale.to(sv), yTo(y), o.marker, color, th.surface, pointTitle(s, fig, k))}</g>`);
    });
    // Residuals.
    s.points.s.forEach((sv, k) => {
      const r = s.points.residual[k];
      if (!finite(sv) || !finite(r) || (o.logX && sv <= 0)) return;
      out.push(`<g data-role="residual" data-series="${esc(s.key)}">${marker(shape, xScale.to(sv), rTo(r), o.marker * 0.85, color, th.surface)}</g>`);
    });
  });

  // Legend, inside the main plot at the lower right, where a saturating curve leaves room.
  const labelled = fig.series.filter((s) => s.label);
  if (labelled.length > 0) {
    const lineH = o.legend * 1.45;
    const widest = Math.max(...labelled.map((s) => s.label.length)) * o.legend * 0.58;
    const boxW = widest + o.legend * 3.4;
    const boxH = lineH * labelled.length + o.legend * 0.6;
    const bx = x1 - boxW - o.legend * 0.4;
    const by = yMain1 - boxH - o.legend * 0.4;
    out.push(`<g data-role="legend"><rect x="${n(bx)}" y="${n(by)}" width="${n(boxW)}" height="${n(boxH)}" fill="${th.surface}" fill-opacity="0.9" stroke="${th.grid}" stroke-width="${n(o.line * 0.5)}"/>`);
    fig.series.forEach((s, i) => {
      const j = labelled.indexOf(s);
      if (j < 0) return;
      const y = by + o.legend * 0.3 + lineH * (j + 0.55);
      const dash = DASHES[(i + Math.floor(i / 6) * 3) % 6];
      out.push(
        `<line x1="${n(bx + o.legend * 0.5)}" x2="${n(bx + o.legend * 2.2)}" y1="${n(y)}" y2="${n(y)}" stroke="${th.series(i)}" stroke-width="${n(o.line)}"${dash ? ` stroke-dasharray="${dash}"` : ""}/>`,
        marker(MARKER_SHAPES[i % MARKER_SHAPES.length], bx + o.legend * 1.35, y, o.marker * 0.9, th.series(i), th.surface),
        `<text x="${n(bx + o.legend * 2.6)}" y="${n(y + o.legend * 0.35)}" fill="${th.ink}" style="${font(th.sans, o.legend)}">${esc(s.label)}</text>`,
      );
    });
    out.push("</g>");
  }
  out.push("</svg>");
  return { svg: out.join(""), hidden };
}
