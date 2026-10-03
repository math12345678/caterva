/**
 * WCAG 2.1 contrast for the stylesheet's OKLCH tokens.
 *
 * The chart series are told apart by luminance as well as hue, and a test
 * (src/__tests__/seriesContrast.test.ts) holds the stylesheet to numbers.
 * That test needs the same arithmetic a browser applies: OKLCH to linear
 * sRGB (Bjorn Ottosson's matrices), channels clipped to the gamut, relative
 * luminance by the WCAG weights, then (lighter + 0.05) / (darker + 0.05).
 */

export interface Oklch {
  l: number;
  c: number;
  h: number;
}

/** "oklch(0.309 0.055 240)" (an optional "/ alpha" is ignored) to its parts, or null. */
export function parseOklch(text: string): Oklch | null {
  const m = /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/.exec(text);
  return m ? { l: Number(m[1]), c: Number(m[2]), h: Number(m[3]) } : null;
}

export function oklchToLinearSrgb({ l, c, h }: Oklch): [number, number, number] {
  const a = c * Math.cos((h * Math.PI) / 180);
  const b = c * Math.sin((h * Math.PI) / 180);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
}

/** True when the colour is inside the sRGB gamut (a hair of tolerance for rounding). */
export function inSrgbGamut(color: Oklch): boolean {
  return oklchToLinearSrgb(color).every((v) => v >= -0.002 && v <= 1.002);
}

export function relativeLuminance(color: Oklch): number {
  const [r, g, b] = oklchToLinearSrgb(color).map((v) => Math.min(1, Math.max(0, v)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: Oklch, b: Oklch): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
