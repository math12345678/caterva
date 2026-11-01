/**
 * What leaves the Rates screen as a file, made in the browser so it works
 * offline: the figure as SVG and as PNG at 300 dpi, the parameter and model
 * tables as CSV, the methods paragraph as text.
 *
 * Nothing is recomputed here. The figure is `figureSvg` on the server's
 * numbers; the tables are the server's rows written out; the methods text is
 * the server's. The CSV writers do one thing of their own, for the person's
 * safety: a text cell that a spreadsheet would run as a formula (it starts
 * with =, +, -, @, a tab or a carriage return) is written with a leading
 * apostrophe, because a group label typed by the person (or pasted from
 * elsewhere) can come back in an export that is opened in Excel. A number is
 * never touched, a negative one included.
 */
import type { RatesComparison, RatesFigure, RatesParameter, RatesTurnover } from "@/api/types";

import { COLUMNS, type Column, figureSvg, paperOptions } from "./figureSvg";

const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

/** A text cell made inert for a spreadsheet; numbers are returned as they are. */
export function neutralise(cell: string): string {
  if (cell !== "" && "=+-@\t\r".includes(cell[0]) && !NUMBER.test(cell)) return `'${cell}`;
  return cell;
}

export function csvCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "number" ? (Number.isFinite(value) ? String(value) : "") : typeof value === "boolean" ? (value ? "yes" : "no") : neutralise(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function csv(rows: readonly (readonly (string | number | boolean | null | undefined)[])[]): string {
  return rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}

export const SOURCE_WORDS = "fitted from your data";

/** One row per constant of each reported law, with where the number came from. */
export function parametersCsv(rows: readonly RatesParameter[], turnover: readonly RatesTurnover[] = []): string {
  const level = rows[0]?.level ?? 0.95;
  const pct = `${Math.round(level * 1000) / 10}%`;
  const head = ["group", "law", "constant", "unit", "estimate", "standard_error", `low (${pct} profile)`, `high (${pct} profile)`, "determined", "interval_method", "source", "note"];
  const body = rows.map((r) => [
    r.group ?? "",
    r.law,
    r.constant,
    r.unit,
    r.determined ? r.estimate : null,
    r.determined ? r.standard_error : null,
    r.low,
    r.high,
    r.determined,
    r.interval_method,
    SOURCE_WORDS,
    r.statement ?? "",
  ]);
  const kcat = turnover.map((r) => [
    r.group ?? "",
    r.law,
    r.constant,
    r.unit,
    r.determined ? r.estimate : null,
    r.determined ? r.standard_error : null,
    r.low,
    r.high,
    r.determined,
    "profile likelihood of Vmax, divided by the enzyme concentration",
    "computed from your fitted Vmax and the enzyme concentration you gave",
    "",
  ]);
  return csv([head, ...body, ...kcat]);
}

export function modelsCsv(comparison: readonly RatesComparison[]): string {
  const head = ["group", "law", "status", "parameters", "n", "objective", "objective_is", "aicc", "delta_aicc", "lack_of_fit_p", "note"];
  const rows: (string | number | boolean | null)[][] = [];
  for (const c of comparison) {
    for (const l of c.laws) {
      rows.push([
        c.group ?? "",
        l.law ?? "",
        l.status ?? "",
        l.parameters ?? null,
        l.n ?? null,
        l.objective ?? null,
        l.objective_is ?? "",
        l.aicc ?? null,
        l.delta_aicc ?? null,
        l.lack_of_fit_p ?? null,
        l.fitted === false ? (l.refused ?? "not fitted") : "",
      ]);
    }
    for (const t of c.tests) {
      rows.push([c.group ?? "", `${t.restricted} against ${t.general}`, t.ruled_out ? "ruled out" : "not ruled out", null, null, null, "", null, null, t.p, t.sentence]);
    }
  }
  return csv([head, ...rows]);
}

/** A download of text the page made, which the macOS shell turns into a save panel like any other. */
export function saveBlob(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}

export function saveText(name: string, text: string, type = "text/plain;charset=utf-8"): void {
  saveBlob(name, new Blob([text], { type }));
}

export const DPI = 300;

/** The PNG's size in pixels at 300 dpi for a column width. */
export function pngSize(column: Column): { width: number; height: number } {
  const c = COLUMNS[column];
  return { width: Math.round(c.widthIn * DPI), height: Math.round(c.heightIn * DPI) };
}

export function figureFileName(base: string, column: Column, ext: "svg" | "png"): string {
  const stem = base.replace(/\.[A-Za-z0-9]{1,5}$/, "").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "rates";
  return `${stem}-figure-${column}-column.${ext}`;
}

/** The standalone SVG of a figure at a column's size, with the prolog an editor expects. */
export function figureFile(fig: RatesFigure, column: Column, logX: boolean, background: boolean): string {
  const { svg } = figureSvg(fig, paperOptions(column, logX, background));
  return `<?xml version="1.0" encoding="UTF-8"?>\n${svg}\n`;
}

// ---------------------------------------------------------------------------
// PNG at 300 dpi, with the resolution written into the file
// ---------------------------------------------------------------------------

function crc32(bytes: Uint8Array): number {
  let c: number;
  let crc = 0xffffffff;
  for (let n = 0; n < bytes.length; n++) {
    c = (crc ^ bytes[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** The PNG with a pHYs chunk after IHDR saying 300 dpi (11811 pixels per metre), so a layout program places it at its true size. */
export function withDpi(png: Uint8Array, dpi = DPI): Uint8Array {
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (png.length < 33 || signature.some((b, i) => png[i] !== b)) return png;
  const perMetre = Math.round(dpi / 0.0254);
  const chunk = new Uint8Array(21);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, 9);
  chunk.set([0x70, 0x48, 0x59, 0x73], 4); // "pHYs"
  view.setUint32(8, perMetre);
  view.setUint32(12, perMetre);
  chunk[16] = 1; // metres
  view.setUint32(17, crc32(chunk.subarray(4, 17)));
  const afterIhdr = 8 + 25;
  const out = new Uint8Array(png.length + chunk.length);
  out.set(png.subarray(0, afterIhdr), 0);
  out.set(chunk, afterIhdr);
  out.set(png.subarray(afterIhdr), afterIhdr + chunk.length);
  return out;
}

/** Rasterise the figure at 300 dpi for a column width. Rejects if the browser cannot decode the SVG. */
export async function figurePng(fig: RatesFigure, column: Column, logX: boolean, background: boolean): Promise<Blob> {
  const { width, height } = pngSize(column);
  const svg = figureFile(fig, column, logX, background);
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("the browser could not draw the figure to an image"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("this browser has no 2D canvas, so it cannot write a PNG");
    ctx.drawImage(image, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("the browser could not encode the PNG");
    const bytes = withDpi(new Uint8Array(await blob.arrayBuffer()));
    return new Blob([bytes as BlobPart], { type: "image/png" });
  } finally {
    URL.revokeObjectURL(url);
  }
}
