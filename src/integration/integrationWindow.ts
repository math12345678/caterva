/**
 * How long to integrate for, derived from the kinetics rather than fixed.
 *
 * THE DEFECT
 * ----------
 * `SIMULATION_END_TIME_S = 10` — ten seconds, for every Michaelis-Menten
 * run this pipeline has ever performed, whatever Km, Vmax and S0 were.
 *
 * BRENDA reports Vmax in μM/min. For the CLI's own documented example
 * (Km 5.2 mM, Vmax 12.8 μM/min, S0 10 mM) the reaction takes **32 hours**
 * to reach 95% conversion, so a ten-second window shows
 *
 *     0.014%
 *
 * of it: a flat line at 10.000, ten times over. The same constant applied
 * to a Vmax in mM/s puts the entire reaction inside the first two printed
 * points. A student gets a flat line or a cliff and almost never a curve,
 * and neither tells them anything about the enzyme.
 *
 * This was invisible until units started being honoured (ADR 0117), because
 * before that every run was integrated as though Vmax were in mM/s — the one
 * regime where ten seconds happens to be right.
 *
 * THE DERIVATION
 * --------------
 * Michaelis-Menten has a closed-form integral. Separating
 *
 *     dS/dt = -Vmax·S / (Km + S)
 *
 * and integrating from S0 to S gives the standard implicit solution
 *
 *     Km·ln(S0/S) + (S0 - S) = Vmax·t
 *
 * (Michaelis & Menten 1913; the integrated form as usually presented in
 * Segel, *Enzyme Kinetics*, Wiley 1975, §2.3). Setting S = f·S0 for a
 * chosen remaining fraction f and solving for t:
 *
 *     t = [ Km·ln(1/f) + S0·(1 - f) ] / Vmax
 *
 * Every term comes from the caller's own parameters. Nothing is assumed
 * about the timescale.
 *
 * WHAT IS STILL A CHOICE
 * ----------------------
 * `f` — how much substrate should remain at the right-hand edge of the
 * plot. That is a **display** decision, not a physical constant: the
 * reaction never finishes, so some cut-off must be picked. 5% is the
 * default because it puts the visible curvature — the transition from
 * zero-order to first-order, which is the thing Michaelis-Menten is taught
 * to show — inside the frame.
 *
 * It is a parameter rather than a literal so that a caller who wants the
 * early linear phase, or the long tail, can say so.
 */

/** Substrate remaining at the end of the window, as a fraction of S0. */
export const DEFAULT_FRACTION_REMAINING = 0.05;

export interface WindowInputs {
  /** Km, in the same concentration units as `s0`. */
  km: number;
  /** Vmax, in `s0`'s concentration units per SECOND. */
  vmaxPerSecond: number;
  /** Initial substrate concentration. */
  s0: number;
  /** Substrate remaining at the end of the window. Default 5%. */
  fractionRemaining?: number;
}

/**
 * Seconds until `fractionRemaining` of the substrate is left.
 *
 * Returns undefined when the window cannot be derived — a missing or
 * non-positive parameter — rather than substituting a number. The caller
 * then falls back to its documented default and says so; a silently
 * invented timescale is the failure this replaces.
 */
export function substrateDepletionWindowSeconds(
  inputs: WindowInputs
): number | undefined {
  const { km, vmaxPerSecond, s0 } = inputs;
  const f = inputs.fractionRemaining ?? DEFAULT_FRACTION_REMAINING;

  if (![km, vmaxPerSecond, s0].every(Number.isFinite)) return undefined;
  if (vmaxPerSecond <= 0 || s0 <= 0) return undefined;
  // Km may legitimately be 0 in the zero-order limit; a negative one is not
  // a kinetics parameter and must not be smuggled through as a shorter
  // window.
  if (km < 0) return undefined;
  if (!(f > 0) || f >= 1) return undefined;

  const seconds = (km * Math.log(1 / f) + s0 * (1 - f)) / vmaxPerSecond;
  return Number.isFinite(seconds) && seconds > 0 ? seconds : undefined;
}

/** Depletion the initial-rate convention tolerates, as a fraction of S0. */
export const INITIAL_RATE_DEPLETION = 0.05;

/**
 * How long an initial-rate reading stays defensible, in seconds.
 *
 * A DIFFERENT WINDOW FROM THE ONE ABOVE, and conflating them was a real
 * mistake in this pipeline.
 *
 * `substrateDepletionWindowSeconds` answers "how long to plot" and is
 * chosen to show the whole reaction. `AssumptionValidator`'s second check
 * asks something else — over the period you would read a *rate* from, does
 * the substrate stay approximately constant? Feeding it the plot window
 * made it report 95% depletion on every run and warn every time, which is
 * true and useless: it is a warning about a window nobody claimed.
 *
 * The formula is the convention's own definition. The validator bounds
 * depletion by the zero-order worst case, Vmax·t/S0, so the window where
 * that bound reaches 5% is
 *
 *     t = 0.05·S0 / Vmax
 *
 * Because the bound is an upper bound, actual depletion over this window is
 * strictly less than 5% — which is what an experimentalist choosing an
 * assay window would do, and is conservative in the right direction.
 *
 * **This makes the validator's depletion check pass by construction on the
 * pipeline's own path**, and that is stated here rather than left for
 * someone to discover: the check is doing real work for any caller that
 * supplies its own window, and on this path it is a definition rather than
 * a finding. Reading it as independent evidence would be reading a
 * tautology as a result.
 *
 * The 5% figure is a textbook convention, not a measured threshold — the
 * validator says so where it uses it, and no primary source establishing it
 * was found.
 */
export function initialRateWindowSeconds(inputs: {
  vmaxPerSecond: number;
  s0: number;
  depletionFraction?: number;
}): number | undefined {
  const { vmaxPerSecond, s0 } = inputs;
  const d = inputs.depletionFraction ?? INITIAL_RATE_DEPLETION;

  if (![vmaxPerSecond, s0].every(Number.isFinite)) return undefined;
  if (vmaxPerSecond <= 0 || s0 <= 0) return undefined;
  if (!(d > 0) || d >= 1) return undefined;

  const seconds = (d * s0) / vmaxPerSecond;
  return Number.isFinite(seconds) && seconds > 0 ? seconds : undefined;
}
