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
    query: "What happens to a flu outbreak in a town of ten thousand people?",
    expected: "sir",
    why: "Spread through a closed population with no latent period mentioned.",
    split: "dev",
  },
  {
    query: "Model how measles spreads through an unvaccinated school.",
    expected: "sir",
    why: "Susceptible/infected/recovered dynamics, no exposed compartment.",
    split: "dev",
  },
  {
    query:
      "Model an epidemic where people who catch it are not contagious for the first few days.",
    expected: "seir",
    why: "A non-infectious interval after infection is the E compartment.",
    split: "dev",
    orderingTrap: true,
  },
  {
    query:
      "Simulate a disease with an incubation period before patients become infectious.",
    expected: "seir",
    why: "An incubation period before infectiousness is exactly SEIR's E state.",
    split: "dev",
    orderingTrap: true,
  },
  {
    query: "How does an allele drift to fixation in a small population?",
    expected: "wright_fisher",
    why: "Single-locus drift to fixation is the Wright-Fisher model.",
    split: "dev",
  },
  {
    query:
      "Model random changes in gene frequency across generations with no selection.",
    expected: "wright_fisher",
    why: "Neutral single-locus drift.",
    split: "dev",
  },
  {
    query: "How does linkage disequilibrium decay between two loci over time?",
    expected: "two_locus_wright_fisher",
    why: "Two loci and LD decay require the two-locus model.",
    split: "dev",
  },
  {
    query:
      "Model two linked genes recombining in a finite population as allele frequencies drift.",
    expected: "two_locus_wright_fisher",
    why: "Recombination between two linked loci; single-locus drift cannot represent it.",
    split: "dev",
    orderingTrap: true,
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
  {
    query: "How many DNA copies do I have after 30 cycles of PCR?",
    expected: "pcr",
    why: "Cycle-by-cycle DNA amplification.",
    split: "dev",
  },
  {
    query: "Model DNA amplification efficiency across thermal cycles.",
    expected: "pcr",
    why: "Amplification per cycle is the PCR model.",
    split: "dev",
  },
  {
    query:
      "Simulate a cluster of argon atoms interacting through a Lennard-Jones potential.",
    expected: "molecular_dynamics",
    why: "Lennard-Jones atom cluster is the MD model.",
    split: "dev",
  },
  {
    query: "Model how particles move in a box at a fixed temperature.",
    expected: "molecular_dynamics",
    why: "Particle trajectories under a pair potential.",
    split: "dev",
  },
  {
    query: "What happens to rabbit and fox populations over time?",
    expected: "lotka_volterra",
    why: "Prey and predator abundance coupled over time.",
    split: "dev",
    orderingTrap: true,
  },
  {
    query: "Model predator-prey cycles in an ecosystem.",
    expected: "lotka_volterra",
    why: "Named predator-prey dynamics.",
    split: "dev",
  },
  {
    query: "Model how cyclin and CDK drive a cell through division.",
    expected: "cell_cycle_oscillator",
    why: "Cyclin-CDK regulation is Tyson's cell cycle model.",
    split: "dev",
  },
  {
    query:
      "Model three genes that repress each other in a ring to make a synthetic oscillator.",
    expected: "repressilator",
    why: "Three mutually repressing genes in a ring is the repressilator.",
    split: "dev",
    orderingTrap: true,
  },
  {
    query: "Simulate the Elowitz and Leibler synthetic genetic oscillator.",
    expected: "repressilator",
    why: "Named for the paper that introduced the repressilator.",
    split: "dev",
    orderingTrap: true,
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
  {
    query:
      "How many people in a closed town are still susceptible after the wave passes?",
    expected: "sir",
    why: "Susceptible depletion in a closed population, no exposed stage.",
    split: "heldout",
  },
  {
    query:
      "Model an illness where people become contagious immediately and then recover with immunity.",
    expected: "sir",
    why: "Immediate infectiousness plus permanent recovery is exactly SIR.",
    split: "heldout",
  },
  {
    query: "What fraction of a population gets infected before the wave ends?",
    expected: "sir",
    why: "Final attack size in a compartmental epidemic with no latent stage.",
    split: "heldout",
  },

  // --- SEIR ----------------------------------------------------------------
  {
    query:
      "Model an illness where someone carries it for several days before they can pass it on.",
    expected: "seir",
    why: "A carrying-but-not-transmitting stage is the E compartment.",
    split: "heldout",
  },
  {
    query:
      "How does a delay between catching something and being able to spread it change the peak?",
    expected: "seir",
    why: "The delay between infection and infectiousness is what E adds.",
    split: "heldout",
  },

  // --- Wright-Fisher --------------------------------------------------------
  {
    query:
      "In a herd of fifty animals, how long before one gene variant takes over by chance alone?",
    expected: "wright_fisher",
    why: "Neutral fixation time at one locus in a finite population.",
    split: "heldout",
  },
  {
    query:
      "Does a slightly advantageous variant reliably sweep through a small population?",
    expected: "wright_fisher",
    why: "Selection against drift at a single locus.",
    split: "heldout",
  },

  // --- Two-locus Wright-Fisher ----------------------------------------------
  {
    query:
      "How quickly do two nearby genes stop being inherited together as crossing over shuffles them?",
    expected: "two_locus_wright_fisher",
    why: "Crossing over between two nearby loci breaking association.",
    split: "heldout",
  },
  {
    query:
      "Track the joint frequencies of variants at a pair of sites that are close on the chromosome.",
    expected: "two_locus_wright_fisher",
    why: "Joint dynamics at two linked sites.",
    split: "heldout",
  },

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
  {
    query:
      "Starting from ten template strands, how much product after twenty five rounds of doubling?",
    expected: "pcr",
    why: "Repeated doubling from a starting template count.",
    split: "heldout",
  },
  {
    query:
      "If each round only copies eighty percent of strands, how does the yield fall short of doubling?",
    expected: "pcr",
    why: "Per-round efficiency below one is the PCR amplification model.",
    split: "heldout",
  },

  // --- Molecular dynamics ---------------------------------------------------------
  {
    query:
      "Track the positions of a few hundred atoms attracting at range and repelling up close.",
    expected: "molecular_dynamics",
    why: "A pair potential with attraction and short-range repulsion, integrated over atoms.",
    split: "heldout",
  },
  {
    query:
      "How does a small cluster of noble gas atoms arrange itself as it cools?",
    expected: "molecular_dynamics",
    why: "Noble gas cluster energetics is the Lennard-Jones case.",
    split: "heldout",
  },

  // --- Lotka-Volterra --------------------------------------------------------------
  {
    query:
      "When the lynx eat most of the hares, what happens to the lynx the following season?",
    expected: "lotka_volterra",
    why: "Coupled consumer-resource abundances feeding back on each other.",
    split: "heldout",
  },
  {
    query:
      "Model two species where one eats the other and both rise and fall out of step.",
    expected: "lotka_volterra",
    why: "Out-of-phase oscillation of consumer and resource.",
    split: "heldout",
  },

  // --- Cell cycle oscillator --------------------------------------------------------
  {
    query:
      "Model the protein switch that decides when a cell commits to dividing.",
    expected: "cell_cycle_oscillator",
    why: "The commitment switch driving division is Tyson's cyclin-CDK model.",
    split: "heldout",
  },
  {
    query:
      "How does a regulatory protein build up and then get destroyed each time a cell divides?",
    expected: "cell_cycle_oscillator",
    why: "Accumulation and abrupt degradation per division is cyclin behaviour.",
    split: "heldout",
  },

  // --- Repressilator ------------------------------------------------------------------
  {
    query:
      "Model an engineered loop of three genes, each shutting off the next, that blinks on its own.",
    expected: "repressilator",
    why: "An engineered three-gene inhibition ring that self-oscillates.",
    split: "heldout",
  },
  {
    query:
      "I built a circuit in E. coli where each gene turns the next one off in a cycle -- does it keep time?",
    expected: "repressilator",
    why: "A constructed cyclic repression circuit, the repressilator.",
    split: "heldout",
  },
];

export const LABELLED_QUERIES: LabelledQuery[] = [
  ...DEV_QUERIES,
  ...HELDOUT_QUERIES,
];
