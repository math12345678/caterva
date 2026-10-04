/**
 * What leaves the Rates screen as a file, checked on the real run
 * (src/__fixtures__/api/rates/run-puromycin-residuals.json: R's Puromycin
 * data fitted by the studio server). The SVG is parsed and holds every
 * measurement; the PNG's resolution is in its bytes; the CSV tables hold the
 * run's rows and a formula in a label is made inert; the series colours a
 * file uses are the stylesheet's own light tokens.
 */
import { describe, expect, it } from "vitest";

import runResiduals from "@/__fixtures__/api/rates/run-puromycin-residuals.json";
import runNever from "@/__fixtures__/api/rates/run-never-saturates.json";
import type { RatesFigure, RatesResult } from "@/api/types";
import { parseOklch } from "@/lib/contrast";

import { css } from "./stylesheet";
import { COLUMNS, esc, figureSvg, PAGE_OPTIONS, paperOptions, PAPER_SERIES, PAPER_SERIES_OKLCH } from "@/screens/rates/figureSvg";
import { csv, csvCell, figureFile, figureFileName, modelsCsv, neutralise, parametersCsv, pngSize, SOURCE_WORDS, withDpi } from "@/screens/rates/exports";

const result = (runResiduals as unknown as { result: RatesResult }).result;
const figure: RatesFigure = result.figure;
const never = (runNever as unknown as { result: RatesResult }).result;

function parse(svg: string): Document {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  expect(doc.querySelector("parsererror"), svg.slice(0, 200)).toBeNull();
  return doc;
}

describe("the figure as a standalone SVG", () => {
  const points = figure.series.reduce((n, s) => n + s.points.s.length, 0);

  it("parses, holds every measurement and its residual, and names the axes from the data", () => {
    const file = figureFile(figure, "single", false, true);
    expect(file.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
    const doc = parse(file);
    const svg = doc.documentElement;
    expect(svg.getAttribute("xmlns")).toBe("http://www.w3.org/2000/svg");
    expect(doc.querySelectorAll('[data-role="point"]')).toHaveLength(points);
    expect(doc.querySelectorAll('[data-role="residual"]')).toHaveLength(points);
    expect(doc.querySelectorAll('[data-role="curve"]')).toHaveLength(figure.series.length);
    expect(doc.querySelectorAll('[data-role="bar"]')).toHaveLength(points);
    const text = Array.from(doc.querySelectorAll("text")).map((t) => t.textContent);
    expect(text).toContain(`${figure.x.column} (${figure.x.unit})`);
    expect(text).toContain(`${figure.y.column} (${figure.y.unit})`);
    expect(text).toContain(`residual (${figure.y.unit})`);
    for (const s of figure.series) expect(text).toContain(s.label);
    // A point's description carries its numbers: the first treated measurement.
    const first = figure.series[0];
    const title = doc.querySelector(`[data-series="${first.key}"] title`)!.textContent!;
    expect(title).toContain(first.label);
    expect(title).toContain(`table line ${first.points.line[0]}`);
  });

  it("is sized for a column and written in text, not outlines, in a font a journal has", () => {
    for (const column of ["single", "double"] as const) {
      const svg = parse(figureFile(figure, column, false, true)).documentElement;
      expect(svg.getAttribute("width")).toBe(`${COLUMNS[column].widthIn}in`);
      expect(svg.getAttribute("height")).toBe(`${COLUMNS[column].heightIn}in`);
      expect(svg.getAttribute("viewBox")).toBe(`0 0 ${Math.round(COLUMNS[column].widthIn * 72 * 100) / 100} ${Math.round(COLUMNS[column].heightIn * 72 * 100) / 100}`);
    }
    const doc = parse(figureFile(figure, "double", false, true));
    expect(doc.querySelectorAll("text").length).toBeGreaterThan(20);
    expect(doc.querySelector("path[data-role='glyph']")).toBeNull();
    const fonts = new Set(Array.from(doc.querySelectorAll("text")).map((t) => /font-family:([^;]+);/.exec(t.getAttribute("style") ?? "")?.[1]));
    expect(fonts).toEqual(new Set(["Helvetica, Arial, sans-serif"]));
  });

  it("uses fixed colours in a file, so it looks the same wherever it is opened, and the page's tokens on the page", () => {
    const file = figureFile(figure, "single", false, true);
    expect(file).not.toContain("var(");
    for (const colour of PAPER_SERIES.slice(0, figure.series.length)) expect(file).toContain(colour);
    const page = figureSvg(figure, { ...PAGE_OPTIONS, logX: false }).svg;
    expect(page).toContain("var(--series-1)");
    expect(page).toContain("var(--series-2)");
    expect(page).not.toContain("<?xml");
  });

  it("has a white background only when asked", () => {
    const white = parse(figureFile(figure, "single", false, true)).documentElement;
    const clear = parse(figureFile(figure, "single", false, false)).documentElement;
    const full = (svg: Element) => Array.from(svg.querySelectorAll(":scope > rect")).filter((r) => r.getAttribute("x") === "0" && r.getAttribute("y") === "0");
    expect(full(white)).toHaveLength(1);
    expect(full(white)[0].getAttribute("fill")).toBe("#ffffff");
    expect(full(clear)).toHaveLength(0);
  });

  it("tells the series apart by marker shape and dash pattern as well as colour", () => {
    const doc = parse(figureFile(figure, "single", false, true));
    const curves = Array.from(doc.querySelectorAll('[data-role="curve"]'));
    const dashes = curves.map((c) => c.getAttribute("stroke-dasharray"));
    expect(new Set(dashes).size).toBe(curves.length);
    const shapes = figure.series.map((s) => doc.querySelector(`[data-series="${s.key}"] > *`)!.tagName);
    expect(new Set(shapes).size).toBe(figure.series.length);
  });

  it("draws a logarithmic axis, says so, and leaves out what cannot be on it", () => {
    const drawn = figureSvg(figure, paperOptions("single", true, true));
    expect(drawn.svg).toContain("(log scale)");
    expect(drawn.hidden).toBe(0);
    parse(drawn.svg);
    const withZero: RatesFigure = {
      ...figure,
      series: [{ ...figure.series[0], points: { ...figure.series[0].points, s: figure.series[0].points.s.map((v, i) => (i === 0 ? 0 : v)) } }],
    };
    const zero = figureSvg(withZero, paperOptions("single", true, true));
    expect(zero.hidden).toBe(1);
    expect(zero.svg).toContain("1 measurement(s) at zero concentration are not shown on the logarithmic axis");
  });

  it("cannot be made to carry markup by a label or a column name", () => {
    const hostile: RatesFigure = {
      ...figure,
      x: { ...figure.x, column: '"><script>alert(1)</script>' },
      series: figure.series.map((s, i) => (i === 0 ? { ...s, label: "<img src=x onerror=alert(1)> & co" } : s)),
    };
    const file = figureFile(hostile, "single", false, true);
    const doc = parse(file);
    expect(doc.querySelector("script")).toBeNull();
    expect(doc.querySelector("img")).toBeNull();
    expect(file).not.toContain("<script");
    expect(file).toContain("&lt;img src=x onerror=alert(1)&gt; &amp; co");
    expect(esc(`a"b'c<d>&`)).toBe("a&quot;b&#39;c&lt;d&gt;&amp;");
  });

  it("draws the figure of a table that cannot bound Km without a curve past what the fit says", () => {
    const doc = parse(figureFile(never.figure, "single", false, true));
    expect(doc.querySelectorAll('[data-role="point"]')).toHaveLength(never.figure.series[0].points.s.length);
  });

  it("names its files by the table and the column width", () => {
    expect(figureFileName("puromycin.csv", "single", "svg")).toBe("puromycin-figure-single-column.svg");
    expect(figureFileName("my data (1).txt", "double", "png")).toBe("my-data-1-figure-double-column.png");
    expect(figureFileName("", "single", "png")).toBe("rates-figure-single-column.png");
  });
});

describe("the colours a file uses", () => {
  it("are the light theme's own series tokens, read from the stylesheet", () => {
    const start = css.indexOf(":root {");
    const block = css.slice(start, css.indexOf("\n}", start));
    const declared = [1, 2, 3, 4, 5, 6].map((n) => new RegExp(`--series-${n}:\\s*(oklch\\([^)]*\\))`).exec(block)![1]);
    expect(PAPER_SERIES_OKLCH.map((c) => parseOklch(c))).toEqual(declared.map((c) => parseOklch(c)));
    for (const colour of PAPER_SERIES) expect(colour).toMatch(/^#[0-9a-f]{6}$/);
    expect(new Set(PAPER_SERIES).size).toBe(6);
  });
});

describe("the PNG at print resolution", () => {
  it("is 300 pixels to the inch at each column width", () => {
    expect(pngSize("single")).toEqual({ width: 1050, height: 1380 });
    expect(pngSize("double")).toEqual({ width: 2160, height: 1440 });
  });

  it("carries its resolution in a pHYs chunk after the header, with a correct checksum", () => {
    // A 1 x 1 PNG (the encoder's own output for a transparent pixel), as bytes.
    const png = Uint8Array.from(
      atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAfbLI3wAAAABJRU5ErkJggg==")
        .split("")
        .map((c) => c.charCodeAt(0)),
    );
    const out = withDpi(png);
    expect(out.length).toBe(png.length + 21);
    const view = new DataView(out.buffer);
    const at = 8 + 25;
    expect(String.fromCharCode(...out.subarray(at + 4, at + 8))).toBe("pHYs");
    expect(view.getUint32(at)).toBe(9);
    expect(view.getUint32(at + 8)).toBe(11811);
    expect(view.getUint32(at + 12)).toBe(11811);
    expect(out[at + 16]).toBe(1);
    // CRC-32 of "pHYs" and its data, computed independently here.
    let crc = 0xffffffff;
    for (const byte of out.subarray(at + 4, at + 17)) {
      crc ^= byte;
      for (let k = 0; k < 8; k++) crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    }
    expect(view.getUint32(at + 17)).toBe((crc ^ 0xffffffff) >>> 0);
    // The rest of the file is where it was.
    expect(Array.from(out.subarray(0, at))).toEqual(Array.from(png.subarray(0, at)));
    expect(Array.from(out.subarray(at + 21))).toEqual(Array.from(png.subarray(at)));
  });

  it("leaves bytes that are not a PNG alone", () => {
    const text = new TextEncoder().encode("not a png at all, just text of some length........");
    expect(withDpi(text)).toBe(text);
  });
});

describe("the tables as CSV", () => {
  it("holds one row per constant, with its unit, interval, provenance words and no number for what is not determined", () => {
    const rows = parseCsv(parametersCsv(result.parameters, result.turnover));
    expect(rows[0].slice(0, 4)).toEqual(["group", "law", "constant", "unit"]);
    expect(rows[0]).toContain("determined");
    expect(rows.length - 1).toBe(result.parameters.length);
    const vmax = result.parameters.find((p) => p.group === "treated" && p.constant === "Vmax")!;
    const row = rows.find((r) => r[0] === "treated" && r[2] === "Vmax")!;
    expect(Number(row[4])).toBe(vmax.estimate);
    expect(row[3]).toBe(vmax.unit);
    expect(row.slice(-2)[0]).toBe(SOURCE_WORDS);
    const undetermined = parseCsv(parametersCsv(never.parameters));
    const km = undetermined.find((r) => r[2] === "Km")!;
    expect(km[4]).toBe("");
    expect(km[8]).toBe("no");
    expect(km[11]).toContain("not determined");
  });

  it("holds every law of every group with its AICc and the tests between laws", () => {
    const rows = parseCsv(modelsCsv(result.comparison));
    const laws = result.comparison.reduce((n, c) => n + c.laws.length + c.tests.length, 0);
    expect(rows.length - 1).toBe(laws);
    expect(rows[0]).toContain("aicc");
    const hill = rows.find((r) => r[0] === "untreated" && r[1] === "hill")!;
    expect(hill[2]).toBe("reported");
  });

  it("makes a formula inert and leaves numbers alone", () => {
    for (const cell of ["=SUM(A1:A9)", "+puro", "-puro", "@mention", "\tcmd", "\rcmd"]) expect(neutralise(cell)).toBe(`'${cell}`);
    for (const cell of ["-0.5", "+1.5", "1e-3", "treated", "", "0"]) expect(neutralise(cell)).toBe(cell);
    expect(csvCell("=1+1")).toBe("'=1+1");
    expect(csvCell("a,b")).toBe('"a,b"');
    expect(csvCell('say "x"')).toBe('"say ""x"""');
    expect(csvCell(-0.5)).toBe("-0.5");
    expect(csvCell(null)).toBe("");
    expect(csvCell(Number.NaN)).toBe("");
    expect(csvCell(true)).toBe("yes");
    const hostile = result.parameters.map((p) => ({ ...p, group: p.group === "treated" ? "=cmd|' /C calc'!A0" : "+puro" }));
    const cells = parseCsv(parametersCsv(hostile)).flat();
    expect(cells).toContain("'=cmd|' /C calc'!A0");
    expect(cells).toContain("'+puro");
    expect(cells).not.toContain("+puro");
    expect(csv([["a", "-b"], [1, 2]])).toBe("a,'-b\n1,2\n");
  });
});

describe("the methods paragraph", () => {
  it("is the run's own, with the real numbers of this table", () => {
    const methods = result.methods;
    expect(methods).toContain("23 measurements at 12 distinct conditions, in 2 groups");
    expect(methods).toContain("substrate in ppm, rate in counts/min/min");
    expect(methods).toMatch(/Software: Caterva \S+ \(caterva rates\), Python \S+, NumPy \S+, SciPy \S+/);
    expect(methods).toContain("profile-likelihood intervals (Bates & Watts 1988)");
    expect(methods).toContain("Lack of fit was tested against pure error");
    expect(methods).toContain("The table (23 measurements used) was read by Caterva Studio from the file puromycin.csv");
    expect(methods).not.toMatch(/—| -- /);
  });

  it("makes no claim a run did not make", () => {
    expect(result.methods).not.toMatch(/state of the art|novel|significantly better|robust|best/i);
    expect(result.cite).not.toMatch(/doi|caterva\.app/i);
  });
});

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(cell);
      cell = "";
    } else if (c === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  return rows;
}
