/**
 * The chart series are told apart by luminance and by dash pattern, not by
 * hue alone. This reads the stylesheet's own tokens for both themes and
 * holds them to numbers: every series 3:1 or better against its surface,
 * every pair of neighbouring series 3:1 or better against each other, and
 * the colours inside the sRGB gamut so the browser does not shift them.
 */
import { describe, expect, it } from "vitest";

import { css } from "./stylesheet";

import { MARKER_SHAPES, niceTicks, seriesDash, spreadLabels, LABEL_GAP, timeAxisTitle } from "@/components/charts/theme";
import { contrastRatio, inSrgbGamut, parseOklch, type Oklch } from "@/lib/contrast";

/** The declarations inside the first block that starts with `opener`. */
function blockAfter(opener: string): string {
  const start = css.indexOf(opener);
  expect(start, `${opener} is in index.css`).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = css.indexOf("{", start); i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(css.indexOf("{", start) + 1, i);
  }
  throw new Error("unclosed block");
}

function tokens(block: string, names: string[]): Record<string, Oklch> {
  const out: Record<string, Oklch> = {};
  for (const n of names) {
    const m = new RegExp(`--${n}:\\s*([^;]+);`).exec(block);
    expect(m, `--${n} is declared`).not.toBeNull();
    const parsed = parseOklch(m![1]);
    expect(parsed, `--${n} is an oklch() value`).not.toBeNull();
    out[n] = parsed!;
  }
  return out;
}

const SERIES = [1, 2, 3, 4, 5, 6].map((n) => `series-${n}`);

const THEMES: Record<string, string> = {
  light: blockAfter(":root {"),
  "dark (system)": blockAfter(':root:not([data-theme="light"])'),
  "dark (chosen)": blockAfter(':root[data-theme="dark"]'),
};

describe.each(Object.entries(THEMES))("chart series in the %s theme", (_name, block) => {
  const t = tokens(block, ["surface", ...SERIES]);

  it("puts every series 3:1 or better against the surface", () => {
    for (const s of SERIES) expect(contrastRatio(t[s], t.surface), s).toBeGreaterThanOrEqual(3);
  });

  it("puts neighbouring series 3:1 or better apart from each other", () => {
    for (let i = 0; i < SERIES.length - 1; i++) {
      expect(contrastRatio(t[SERIES[i]], t[SERIES[i + 1]]), `${SERIES[i]} against ${SERIES[i + 1]}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("keeps every series inside the sRGB gamut", () => {
    for (const s of SERIES) expect(inSrgbGamut(t[s]), s).toBe(true);
  });
});

describe("the two dark declarations agree", () => {
  it("gives the system dark theme and the chosen dark theme the same series", () => {
    const a = tokens(THEMES["dark (system)"], SERIES);
    const b = tokens(THEMES["dark (chosen)"], SERIES);
    expect(a).toEqual(b);
  });
});

describe("series that are not told apart by colour", () => {
  it("gives each of the first six series its own dash pattern and marker", () => {
    const dashes = [0, 1, 2, 3, 4, 5].map((i) => seriesDash(i) ?? "solid");
    expect(new Set(dashes).size).toBe(6);
    expect(new Set(MARKER_SHAPES).size).toBe(6);
  });

  it("does not repeat a colour with the same dash pattern", () => {
    for (let i = 0; i < 6; i++) expect(seriesDash(i)).not.toBe(seriesDash(i + 6));
  });
});

describe("end-of-line labels", () => {
  it("keeps labels at least a label's height apart when series end together", () => {
    const placed = spreadLabels([1.0, 1.001, 1.002, 0.2], [0, 1.1], 270) as number[];
    const sorted = [...placed].sort((a, b) => a - b);
    for (let i = 1; i < sorted.length; i++) expect(sorted[i] - sorted[i - 1]).toBeGreaterThanOrEqual(LABEL_GAP - 0.01);
  });

  it("leaves a series with no value unlabelled", () => {
    expect(spreadLabels([null, 3], [0, 4], 100)[0]).toBeNull();
  });
});

describe("axes", () => {
  it("chooses round ticks, evenly spaced", () => {
    const { ticks } = niceTicks(0, 97.3, 6);
    const gaps = ticks.slice(1).map((v, i) => Number((v - ticks[i]).toPrecision(10)));
    expect(new Set(gaps).size).toBe(1);
    expect(ticks.every((v) => /^\d+$/.test(String(v)))).toBe(true);
  });

  it("widens a y domain to hold its ticks", () => {
    const { domain, ticks } = niceTicks(0.013, 0.847, 5, true);
    expect(domain[0]).toBeLessThanOrEqual(0.013);
    expect(domain[1]).toBeGreaterThanOrEqual(0.847);
    expect(ticks[0]).toBe(domain[0]);
    expect(ticks[ticks.length - 1]).toBe(domain[1]);
  });

  it("omits the parenthetical when the time unit is not a unit", () => {
    expect(timeAxisTitle("time units")).toBe("time");
    expect(timeAxisTitle("")).toBe("time");
    expect(timeAxisTitle("s")).toBe("time (s)");
  });
});
