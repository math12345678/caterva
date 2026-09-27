/**
 * Graded reliability scoring for a resolved kinetic parameter.
 *
 * WHY THIS REPLACES A BOOLEAN
 * ---------------------------
 * Professor Barbara Bakker (UMC Groningen), asked whether "flag it, don't
 * use it" is the right response to a value missing its assay conditions,
 * answered that the question is malformed:
 *
 *   "In practice, we chose the best option, but do not exclude anything a
 *    priori. [...] We gave each parameter a score based on its reliability
 *    and applicability, such as physiological pH and T, species (in our
 *    case human was prioritized as we built a human-like model) and
 *    completeness of assay description. These scores were then used to
 *    give the parameter a weight in the sampling."
 *
 * — Odendaal, Krebs & Bakker, "Ensemble kinetic modelling links residual
 *   enzyme activity to clinical symptoms in mitochondrial β-oxidation
 *   defects", bioRxiv doi:10.64898/2026.05.05.722902
 *
 * The insight Caterva was missing: a measurement with a poor assay
 * description is not evidence of NOTHING. It is weak evidence. Caterva's
 * binary verified/unverified discarded it entirely, which is a loss of
 * information dressed up as caution — and it is why roughly three quarters
 * of this project's own defaults came back "unverified", a number that had
 * been read as a fact about the literature when it was partly a fact about
 * a crude threshold.
 *
 * THERE IS DELIBERATELY NO TOTAL
 * ------------------------------
 * This module reports three axes and refuses to combine them.
 *
 * Bakker uses her scores as sampling weights, which requires knowing how
 * the axes trade off against each other: is a right-species value with a
 * bad assay description better or worse than a thorough assay in the wrong
 * species? She has been asked and has not yet answered.
 *
 * Inventing weights that look reasonable would be the exact thing this
 * project refuses to do with parameters, one level up — a fabricated
 * number, presented with the authority of a computation, governing which
 * real numbers a student sees. A single reliability score would also be
 * strictly less informative than the three parts, because "0.61" cannot
 * tell a reader WHICH axis was weak, and that is the only part they can
 * act on.
 *
 * If and when the weights arrive with a citation, combining happens here
 * and gets its own ADR.
 *
 * WHAT THIS IS NOT
 * ----------------
 * Not a replacement for the hard block. ADR 0012/0013 still govern: an
 * unsourced required parameter still stops the run. This grades values
 * that WERE resolved, so a reader can see how much to trust one.
 */

import type { AssayConditions } from "./provenance";

/**
 * How completely the source described the assay.
 *
 * `partial` is the state the old boolean could not express, and it is the
 * common case in BRENDA: a paper that reports temperature but not pH.
 */
export type AssayCompleteness = "complete" | "partial" | "absent";

/**
 * How close the assay conditions are to the conditions being modelled.
 *
 * `not_assessed` is not a failure and not a pass. It means no reference
 * conditions were supplied, so the question was never asked. See
 * `PhysiologicalReference` for why that is the default.
 */
export type ConditionProximity = "near" | "far" | "not_assessed";

/**
 * How well the measured organism matches the requested one.
 *
 * Mirrors taxonomy.py's three states plus the exact-match case, so the two
 * halves of the system cannot disagree about what "related" means.
 */
export type OrganismMatch = "exact" | "related" | "distant" | "unknown";

/**
 * The conditions the model is meant to represent.
 *
 * THIS IS AN EXPERIMENTAL CONDITION, NOT A MEASURED QUANTITY, and the
 * distinction is the reason it has no default.
 *
 * "Physiological pH and temperature" has no organism-independent value.
 * 7.4 and 37 °C are physiological for a human and meaningless for Thermus
 * thermophilus, whose enzymes are measured near 70 °C — the very
 * comparison Lisa Jeske raised when she warned that mixing conditions
 * across sources produces "fantasy numbers".
 *
 * So the reference is supplied by whoever is building the model, exactly
 * as `s0` and `end` are (ADR 0012/0013). Baking in 7.4/37 would encode a
 * silent assumption that every model is a mammalian one, and would report
 * a confident `far` for a thermophile assay that was in fact ideal.
 *
 * When it is absent the axis reports `not_assessed` and says why. That is
 * the honest reading: nobody stated what the model represents, so nobody
 * can say whether 25 °C is close to it.
 */
export interface PhysiologicalReference {
  ph: number;
  temperatureC: number;
  /** Where these came from — a citation, a species, or the user. Required
   * so a reference can never be traced back to "someone typed it". */
  basis: string;
  /**
   * Tolerances. Also supplied, also not defaulted: how far a Km may drift
   * before it stops representing the modelled system is a property of the
   * enzyme, not a universal constant.
   */
  phTolerance: number;
  temperatureToleranceC: number;
}

/** One axis of the score: a grade, and the reason for it. */
export interface ScoreAxis<T extends string> {
  grade: T;
  /** Human-readable justification. Always populated — a grade with no
   * reason is a number the reader has to take on faith, which is the
   * failure mode this whole module exists to correct. */
  reason: string;
}

export interface ReliabilityScore {
  assayCompleteness: ScoreAxis<AssayCompleteness>;
  conditionProximity: ScoreAxis<ConditionProximity>;
  organismMatch: ScoreAxis<OrganismMatch>;
  /**
   * Why no single number is offered. Carried in the payload rather than
   * left to documentation, so a client that goes looking for a total finds
   * an explanation instead of an absence it might paper over with an
   * average of its own.
   */
  readonly noAggregateReason: string;
}

const NO_AGGREGATE_REASON =
  "The three axes are reported separately and deliberately not combined. " +
  "Weighting them against each other requires knowing how a right-species " +
  "value with a poor assay description trades off against a thorough assay " +
  "in the wrong species. That trade-off is an empirical finding Caterva " +
  "does not have, and inventing it would fabricate the very kind of number " +
  "this system refuses to fabricate. See ADR 0024, Decision 3.";

function isFinite_(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Relatedness verdict as it arrives from the Python resolver.
 * Mirrors taxonomy.Relatedness.
 */
export interface RelatednessVerdict {
  status: string;
  shared_rank?: string | null;
  shared_name?: string | null;
  query_organism?: string | null;
  candidate_organism?: string | null;
  reason?: string;
}

/**
 * GRADING LIVES IN PYTHON. THIS FILE IS TYPES ONLY.
 * ------------------------------------------------
 * There used to be a full TypeScript implementation of the three axes here,
 * alongside `Tests/reliability.py`. Two implementations of one score, and a
 * parity test asserting they agreed on a shared 16-case fixture — which they
 * did, and it did not help.
 *
 * The defect was never in either implementation. `queryResolver.ts` called
 * the TypeScript grader with no `reference` argument, because none was
 * reachable from an HTTP request, so `conditionProximity` returned
 * `not_assessed` on every response the API server ever produced. The CLI,
 * consuming the Python score, reported real grades. A parity test pins
 * IMPLEMENTATIONS; it cannot see a call site handing one of them different
 * arguments.
 *
 * So the second implementation is gone rather than merely bypassed. It was
 * dead in production and alive in its own test, which is the state this
 * repository's orphan guard describes as harder to notice than no test at
 * all — and the guard could not flag it, because the module is still
 * imported for these types.
 *
 * The behaviour is pinned in `Tests/reliability_cases.json`, 16 cases,
 * with `test_case_file_is_not_empty_and_covers_every_grade` asserting the
 * fixture exercises every grade of every axis. Deleting the TypeScript copy
 * removed no coverage.
 *
 * If a TypeScript grader is ever needed again — for a path that resolves a
 * value without going through the Python runner — it needs an ADR first,
 * and a test that fails when the two disagree at a CALL SITE rather than in
 * a unit fixture.
 */
