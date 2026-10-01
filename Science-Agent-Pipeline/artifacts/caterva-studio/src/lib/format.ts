/**
 * How a number is written on the page. One module, so no screen rounds
 * differently from another.
 *
 * The server sends the library's float unrounded. The page shows four
 * significant figures (exponent form outside 1e-3..1e5) and puts the full
 * stored value in the provenance detail, so nothing is hidden by the
 * display precision, and the full value is what a copy takes. It never
 * pads with zeros the library did not compute.
 *
 * The other helpers here write things that are not measurements (a count,
 * a byte size, a time, a duration) and are equally display-only.
 */
import type { SourcedValue } from "@/api/types";

export function formatNumber(value: number, significant = 4): string {
  if (value === 0) return "0";
  if (!Number.isFinite(value)) return value > 0 ? "∞" : value < 0 ? "−∞" : "not a number";
  const magnitude = Math.abs(value);
  if (magnitude < 1e-3 || magnitude >= 1e5) {
    const [mantissa, exponent] = value.toExponential(significant - 1).split("e");
    return `${trimZeros(mantissa)}e${Number(exponent)}`;
  }
  return trimZeros(value.toPrecision(significant));
}

function trimZeros(text: string): string {
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
}

/** The text a SourcedValue is drawn as, without its unit. */
export function formatValue(v: SourcedValue): string {
  if (v.nonfinite === "nan") return "not a number";
  if (v.nonfinite === "inf") return "∞";
  if (v.nonfinite === "-inf") return "−∞";
  if (v.value === null) {
    if (v.interval && v.interval.low !== null && v.interval.high !== null) {
      return `${formatNumber(v.interval.low)} to ${formatNumber(v.interval.high)}`;
    }
    if (v.interval && v.interval.low !== null) return `≥ ${formatNumber(v.interval.low)}`;
    if (v.interval && v.interval.high !== null) return `≤ ${formatNumber(v.interval.high)}`;
    return "none";
  }
  return formatNumber(v.value);
}

/** The full stored value, for the provenance detail and for copying. */
export function fullValue(v: SourcedValue): string {
  return v.value === null ? formatValue(v) : String(v.value);
}

/** A count (atoms, events, runs): every digit, grouped. */
export function formatCount(n: number): string {
  return Number.isInteger(n) ? n.toLocaleString("en-US") : formatNumber(n);
}

/** A file size in SI units (1 kB = 1000 bytes), three significant figures. */
export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let v = bytes / 1000;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i += 1;
  }
  return `${trimZeros(v.toPrecision(3))} ${units[i]}`;
}

/** A duration in milliseconds, to the second above a minute. */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${trimZeros(s.toPrecision(s < 10 ? 2 : 3))} s`;
  const minutes = Math.floor(s / 60);
  const seconds = Math.round(s - minutes * 60);
  if (minutes < 60) return seconds ? `${minutes} min ${seconds} s` : `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes - hours * 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** An ISO time in the reader's time zone, as "30 Sept 2026, 14:15". */
export function formatDateTime(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso : DATE_TIME.format(t);
}

/** "just now", "4 min ago", "14:15" today, else the date and time. */
export function formatWhen(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const ago = now - t;
  if (ago < 45_000 && ago > -45_000) return "just now";
  if (ago > 0 && ago < 3_600_000) return `${Math.round(ago / 60_000)} min ago`;
  const then = new Date(t);
  const today = new Date(now);
  if (then.toDateString() === today.toDateString()) return `today ${TIME.format(t)}`;
  return DATE_TIME.format(t);
}

/** Elapsed time between two ISO stamps (or until now), or "" when unknown. */
export function elapsed(startIso: string | null, endIso: string | null, now: number = Date.now()): string {
  if (!startIso) return "";
  const start = Date.parse(startIso);
  const end = endIso ? Date.parse(endIso) : now;
  if (Number.isNaN(start) || Number.isNaN(end)) return "";
  return formatDuration(end - start);
}
