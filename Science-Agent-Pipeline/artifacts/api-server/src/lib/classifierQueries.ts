/**
 * The labelled queries the domain classifier is scored against.
 *
 * Split into two sets, and the split is the point.
 *
 * `dev` is the original set from ADR 0190. It was written *after* reading
 * the keyword table, specifically probing orderings that looked fragile.
 * That makes it good at finding defects and disqualifying as evidence that a
 * fix generalises: tuning a classifier until it passes the set that was
 * written to break it measures memorisation, not classification.
 *
 * `heldout` was written from what each model *is* -- the domain meanings in
 * the resolver's system prompt and the paper each domain cites -- without
 * consulting the keyword list, and before any tuning was attempted. It is
 * the set that decides whether a change actually helped.
 *
 * Both are authored, not sampled from real student traffic. Nobody has
 * collected any. That is a real limit on what these numbers mean and it is
 * stated here rather than left for a reader to infer: they measure a
 * classifier against one person's idea of the questions, not against the
 * questions.
 */

import type { SimulationDomain } from "./catervaRunner";

export interface LabelledQuery {
  query: string;
  expected: SimulationDomain;
  /** Why this label is the right answer, in one line. */
  why: string;
  /** `dev` was written knowing the keyword table; `heldout` was not. */
  split: "dev" | "heldout";
  /**
   * Set when the ordered keyword table was expected to mis-route this query
   * because an earlier domain's keyword matches first. Recorded on the dev
   * set only, where the traps were deliberately sought.
   */
  orderingTrap?: boolean;
}

/**
 * Written while reading the keyword table, to find where it breaks.
 * Diagnostic. Not evidence that a fix generalises.
 */
export const DEV_QUERIES: LabelledQuery[] = [
  {
    query: "How fast does lactate dehydrogenase convert pyruvate in humans?",
    expected: "mm",
    why: "Single enzyme acting on a single substrate, no inhibitor named.",
    split: "dev",
  },
  {
    query:
      "What is the reaction rate of catalase breaking down hydrogen peroxide?",
    expected: "mm",
    why: "Single-enzyme turnover question.",
    split: "dev",
  },
  {
    query:
      "Show how an enzyme's velocity saturates as I raise substrate concentration.",
    expected: "mm",
    why: "The saturation curve is the Michaelis-Menten result.",
    split: "dev",
  },
  {
    query:
      "How does adding a molecule that competes with the substrate change hexokinase's rate?",
    expected: "mm_competitive_inhibition",
    why: "A competitor for the active site is competitive inhibition.",
    split: "dev",
  },
  {
    query:
      "Model enzyme velocity when an inhibitor binds the same site as the substrate.",
    expected: "mm_competitive_inhibition",
    why: "Same-site binding is the definition of competitive inhibition.",
    split: "dev",
  },
  {
    query:
      "Simulate the random decay of a small number of molecules, one reaction at a time.",
    expected: "gillespie_ssa",
    why: "Discrete first-order decay at low copy number.",
    split: "dev",
  },
  {
    query: "Simulate two reactants A and B coming together to form C.",
    expected: "gillespie_ssa_bimolecular",
    why: "Two distinct reactants associating is the bimolecular case.",
    split: "dev",
  },
  {
    query: "Model a second-order association reaction at low molecule counts.",
    expected: "gillespie_ssa_bimolecular",
    why: "Second-order association with stochastic counts.",
    split: "dev",
  },
];

/**
 * Written from each domain's definition and its cited paper, without looking
 * at the keyword table, before any tuning. This is the set that decides
 * whether a classifier change generalises.
 */
export const HELDOUT_QUERIES: LabelledQuery[] = [
  // --- Michaelis-Menten -------------------------------------------------
  {
    query:
      "At what rate does alcohol dehydrogenase clear ethanol from the blood?",
    expected: "mm",
    why: "One enzyme, one substrate, turnover rate.",
    split: "heldout",
  },
  {
    query: "How long until trypsin has digested most of the protein I added?",
    expected: "mm",
    why: "Substrate depletion under a single enzyme.",
    split: "heldout",
  },
  {
    query: "Plot product formation against time for a single purified enzyme.",
    expected: "mm",
    why: "Progress curve for one enzyme acting on one substrate.",
    split: "heldout",
  },

  // --- Competitive inhibition --------------------------------------------
  {
    query:
      "If I add a drug that occupies the active site, how much slower does the enzyme run?",
    expected: "mm_competitive_inhibition",
    why: "Active-site occupancy by a rival ligand is competitive inhibition.",
    split: "heldout",
  },
  {
    query:
      "Compare enzyme activity with and without a rival ligand that the substrate must outcompete.",
    expected: "mm_competitive_inhibition",
    why: "Substrate and ligand competing for the same site.",
    split: "heldout",
  },

  // --- SIR ----------------------------------------------------------------

  // --- SEIR ----------------------------------------------------------------

  // --- Wright-Fisher --------------------------------------------------------

  // --- Two-locus Wright-Fisher ----------------------------------------------

  // --- Gillespie SSA (first-order) --------------------------------------------
  {
    query:
      "With only forty molecules left, how jagged does the decay curve get run to run?",
    expected: "gillespie_ssa",
    why: "Run-to-run noise at low copy number in a single decay reaction.",
    split: "heldout",
  },
  {
    query:
      "Model a single species converting to another, one discrete event at a time.",
    expected: "gillespie_ssa",
    why: "One-species, first-order conversion as discrete events.",
    split: "heldout",
  },

  // --- Gillespie SSA (bimolecular) --------------------------------------------
  {
    query:
      "Two different species must collide to make a product -- how does that look with few copies?",
    expected: "gillespie_ssa_bimolecular",
    why: "Collision of two distinct species is the bimolecular reaction.",
    split: "heldout",
  },
  {
    query:
      "Model a receptor and its ligand pairing up when only a handful of each is present.",
    expected: "gillespie_ssa_bimolecular",
    why: "Two reactants pairing at low counts.",
    split: "heldout",
  },

  // --- PCR ----------------------------------------------------------------------

  // --- Molecular dynamics ---------------------------------------------------------

  // --- Lotka-Volterra --------------------------------------------------------------

  // --- Cell cycle oscillator --------------------------------------------------------

  // --- Repressilator ------------------------------------------------------------------
];

export const LABELLED_QUERIES: LabelledQuery[] = [
  ...DEV_QUERIES,
  ...HELDOUT_QUERIES,
];
