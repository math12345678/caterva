// Labelled classifier queries for the domains archived on 2026-09-27.
//
// Parked, not deleted, and not compiled: nothing imports this file and the
// `LabelledQuery` type it was written against lives in
// src/lib/classifierQueries.ts, which no longer knows these domains. They are
// here because they are measurements -- 36 hand-labelled queries across SIR,
// SEIR, Wright-Fisher, two-locus Wright-Fisher, PCR, molecular dynamics,
// Lotka-Volterra, the cell-cycle oscillator and the repressilator -- and the
// benchmark they fed (ADR 0190/0191, and the 53/53 figure in ADR 0204) cannot
// be re-read without them.
//
// The surviving 17 stayed in src/lib/classifierQueries.ts.

const ARCHIVED_QUERIES = [
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
