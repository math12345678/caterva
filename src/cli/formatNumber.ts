/**
 * Numbers as a person reads them on the terminal.
 *
 * A Vmax bridged from kcat x [E]0 printed as `0.0020050000000000003 mM/s`:
 * 40.1 x 0.00005 in binary floating point, shown to seventeen digits, as if
 * the last ones meant something. They do not -- the kcat has three
 * significant figures, BRENDA's -- and a student copying the number into a
 * lab book copies the noise with it.
 *
 * Display only. Every number written to --json, an exported model or a
 * citation file keeps its full value: rounding there would change what the
 * next tool computes from it.
 */

/** A value Caterva COMPUTED (kcat x [E]0 and the like), to `figures` s.f. */
export function formatDerived(value: number, figures = 4): string {
  if (!Number.isFinite(value)) return String(value);
  return String(Number(value.toPrecision(figures)));
}

/**
 * A value that was looked up or typed, with only the binary noise removed:
 * twelve significant figures keeps every digit a person or a paper wrote
 * and drops the `...0000000003` arithmetic leaves behind.
 */
export function formatValue(value: number | string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return String(value);
  return String(Number(value.toPrecision(12)));
}
