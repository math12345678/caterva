/**
 * A K0.5 is not a Km, wherever the number is drawn.
 *
 * The engine carries a cooperative enzyme's half-saturation constant in the
 * model's Km slot (the rate law is hyperbolic) and says so in the row's
 * scope. Every place that names the constant (the result map, the ledger,
 * a value's accessible name) asks here, so none of them calls it a Km.
 */
import type { SourcedValue } from "@/api/types";

/**
 * Whether a constant carried as Km is a K0.5, and its Hill coefficient.
 *
 * Read from the engine's own scope sentence ("the row is a K0.5 with a Hill
 * coefficient of 1.8, not a Michaelis-Menten Km") first, then from the source
 * row's words as BRENDA files them ("K0.5 value, Hill coefficient 1.8"). A
 * row that says neither is a Km and this returns null; a K0.5 whose Hill
 * coefficient is not stated returns `hill: null`, never a guessed one.
 */
export function halfSaturationOf(v: SourcedValue): { hill: number | null } | null {
  // "Km" in a compose model, "km" for the pick of the constants lookup.
  if (v.label?.toLowerCase() !== "km") return null;
  return rowHalfSaturation(v);
}

/** The same reading for a row already known to be of the Km table (the constants lookup's unlabelled alternatives). */
export function rowHalfSaturation(v: SourcedValue): { hill: number | null } | null {
  if (v.provenance.kind !== "measured") return null;
  const texts = [...(v.provenance.scope ?? []), v.provenance.commentary ?? ""];
  if (!texts.some((t) => /\bK0\.5\b/.test(t))) return null;
  for (const t of texts) {
    const m = /Hill coefficient(?: of)? (\d+(?:\.\d+)?)/.exec(t);
    if (m) return { hill: Number(m[1]) };
  }
  return { hill: null };
}

/** The name a constant is shown under: K0.5 when its row is one, else the model's own label. */
export function constantName(v: SourcedValue): string {
  return halfSaturationOf(v) ? "K0.5" : (v.label ?? v.id ?? "constant");
}
