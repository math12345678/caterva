/**
 * How a number is written on the page. One function, so no screen rounds
 * differently from another.
 *
 * The server sends the library's float unrounded. The page shows four
 * significant figures (exponent form outside 1e-3..1e5) and puts the full
 * stored value in the provenance popover, so nothing is hidden by the
 * display precision. It never pads with zeros the library did not compute.
 */
import type { SourcedValue } from "@/api/types";

export function formatNumber(value: number, significant = 4): string {
  if (value === 0) return "0";
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
    return "none";
  }
  return formatNumber(v.value);
}

/** The full stored value, for the popover. */
export function fullValue(v: SourcedValue): string {
  return v.value === null ? formatValue(v) : String(v.value);
}
