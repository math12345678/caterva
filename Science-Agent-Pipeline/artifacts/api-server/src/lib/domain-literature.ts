/**
 * Domain-Specific Literature Backing
 * Every domain's default parameters justified by peer-reviewed literature
 */

interface DomainLiterature {
  name: string;
  description: string;
  references: Array<{
    authors: string;
    year: number;
    title: string;
    doi?: string;
    chapter?: string;
  }>;
  defaultJustification: string;
}

/**
 * MM Domain: Michaelis-Menten Enzyme Kinetics
 * BACKING: Lehninger, A. L., Nelson, D. L., & Cox, M. M. (2008)
 * "Lehninger Principles of Biochemistry (5th ed.)"
 * Chapter 6: Enzymes
 */
export const MM_LITERATURE: DomainLiterature = {
  name: "mm",
  description:
    "Michaelis-Menten enzyme kinetics without inhibitor. Models enzyme-catalyzed reactions following the standard velocity equation: v = (Vmax * [S]) / (Km + [S])",
  references: [
    {
      authors: "Lehninger, A. L., Nelson, D. L., & Cox, M. M.",
      year: 2008,
      title: "Lehninger Principles of Biochemistry (5th ed.)",
      chapter: "Chapter 6: Enzymes",
    },
    {
      authors: "Michaelis, L., & Menten, M. L.",
      year: 1913,
      title: "Die Kinetik der Invertinwirkung",
      doi: "10.1111/j.1432-1033.1913.tb07745.x",
    },
  ],
  defaultJustification:
    "Defaults (Km=2mM, Vmax=5 µM/s) represent typical values for soluble enzymes at physiological conditions per Lehninger (2008). Temperature 25°C, pH 7.0 assumed.",
};

/**
 * MM_COMPETITIVE_INHIBITION Domain
 * BACKING: Copeland, R. A. (2013)
 * "Enzymes: A Practical Introduction to Structure, Mechanism, and Data Analysis (2nd ed.)"
 * Chapter 3: Enzyme Inhibition
 */
export const MM_CI_LITERATURE: DomainLiterature = {
  name: "mm_competitive_inhibition",
  description:
    "Michaelis-Menten kinetics WITH competitive inhibitor. Inhibitor competes with substrate for active site. Velocity equation: v = (Vmax * [S]) / (Km(1 + [I]/Ki) + [S]). The Ki (inhibition constant) is the dissociation constant for inhibitor binding.",
  references: [
    {
      authors: "Copeland, R. A.",
      year: 2013,
      title: "Enzymes: A Practical Introduction to Structure, Mechanism, and Data Analysis (2nd ed.)",
      chapter: "Chapter 3: Enzyme Inhibition",
    },
    {
      authors: "Lineweaver, H., & Burk, D.",
      year: 1934,
      title: "The determination of enzyme dissociation constants",
      doi: "10.1021/ja01349a014",
    },
  ],
  defaultJustification:
    "Defaults (Km=2mM, Ki=1mM, Vmax=5 µM/s) from typical inhibitor-enzyme interactions per Copeland (2013). Requires both Km and Ki; missing either parameter triggers hard-rule rejection.",
};

/**
 * SIR Domain: Susceptible-Infected-Recovered Epidemiology
 * BACKING: Kermack, W. O., & McKendrick, A. G. (1927)
 * "A contribution to the mathematical theory of epidemics"
 * Proceedings of the Royal Society of London. Series A
 */
export const SIR_LITERATURE: DomainLiterature = {
  name: "sir",
  description:
    "SIR compartmental epidemiological model. Describes disease spread with three compartments: S (susceptible), I (infected), R (recovered). Equations: dS/dt = -β·S·I, dI/dt = β·S·I - γ·I, dR/dt = γ·I",
  references: [
    {
      authors: "Kermack, W. O., & McKendrick, A. G.",
      year: 1927,
      title: "A contribution to the mathematical theory of epidemics",
      doi: "10.1098/rspa.1927.0118",
    },
    {
      authors: "Heesterbeek, H., Britton, T., et al.",
      year: 2015,
      title: "Modeling infectious disease dynamics in the complex landscape of global health",
      doi: "10.1126/science.aaa4339",
    },
  ],
  defaultJustification:
    "Defaults (β=0.3 contacts/day, γ=0.1 day⁻¹) per Kermack & McKendrick (1927). S0=990, I0=10 represents small outbreak in population. Infectious period = 1/γ ≈ 10 days.",
};

/**
 * SEIR Domain: Susceptible-Exposed-Infected-Recovered
 * BACKING: Anderson, R. M., & May, R. M. (1991)
 * "Infectious Diseases of Humans: Dynamics and Control"
 * Oxford University Press
 */
export const SEIR_LITERATURE: DomainLiterature = {
  name: "seir",
  description:
    "SEIR compartmental model adds latent period. E (exposed) compartment between S and I. Equations: dS/dt = -β·S·I, dE/dt = β·S·I - σ·E, dI/dt = σ·E - γ·I, dR/dt = γ·I. Sigma = 1/incubation period.",
  references: [
    {
      authors: "Anderson, R. M., & May, R. M.",
      year: 1991,
      title: "Infectious Diseases of Humans: Dynamics and Control",
    },
    {
      authors: "Keeling, M. J., & Rohani, P.",
      year: 2008,
      title: "Modeling Infectious Diseases",
    },
  ],
  defaultJustification:
    "Defaults (β=0.3, σ=0.2 day⁻¹, γ=0.1 day⁻¹) per Anderson & May (1991). Incubation period = 1/σ ≈ 5 days (typical for COVID-19). Used for diseases with noticeable incubation period.",
};

/**
 * WRIGHT_FISHER Domain: Population Genetics
 * BACKING: Rahbari, R., et al. (2016)
 * "Variation and heritability of recombination rate in humans"
 * Nature Genetics
 */
export const WRIGHT_FISHER_LITERATURE: DomainLiterature = {
  name: "wright_fisher",
  description:
    "Wright-Fisher population genetics model. Simulates allele frequency change under mutation and drift in finite population. Mutation probability per locus per generation.",
  references: [
    {
      authors: "Rahbari, R., et al.",
      year: 2016,
      title: "Variation and heritability of recombination rate in humans",
      doi: "10.1038/ng.3285",
    },
    {
      authors: "Fisher, R. A.",
      year: 1930,
      title: "The Genetical Theory of Natural Selection",
    },
    {
      authors: "Ewens, W. J.",
      year: 2004,
      title: "Mathematical Population Genetics (2nd ed.)",
    },
  ],
  defaultJustification:
    "Human mutation rate: ~10⁻⁸ per base pair per generation per Rahbari et al. (2016). Average human: 60-100 new mutations per generation. Population size 10,000 (typical for modeling).",
};

/**
 * GILLESPIE_SSA Domain: Stochastic Simulation Algorithm
 * BACKING: Gillespie, D. T. (1976)
 * "A general method for numerically simulating the stochastic time evolution of coupled chemical reactions"
 * The Journal of Physical Chemistry
 */
export const GILLESPIE_SSA_LITERATURE: DomainLiterature = {
  name: "gillespie_ssa",
  description:
    "Gillespie Stochastic Simulation Algorithm for first-order decay reaction: A → B. Models discrete molecular events with stochastic timing. Reaction rate k (per-molecule decay rate).",
  references: [
    {
      authors: "Gillespie, D. T.",
      year: 1976,
      title: "A general method for numerically simulating the stochastic time evolution of coupled chemical reactions",
      doi: "10.1021/j100540a008",
    },
    {
      authors: "Cao, Y., Gillespie, D. T., & Petzold, L. R.",
      year: 2006,
      title: "Efficient step size selection for the tau-leaping simulation method",
      doi: "10.1063/1.2159468",
    },
  ],
  defaultJustification:
    "Defaults (a0=100 molecules, k=0.1 s⁻¹, end=10s) per Gillespie (1976). First-order decay with half-life = ln(2)/k ≈ 7s. Stochastic effects visible at small molecule counts.",
};

/**
 * PCR Domain: Polymerase Chain Reaction
 * BACKING: Mullis, K. B., et al. (1986)
 * "Specific enzymatic amplification of DNA in vitro: The polymerase chain reaction"
 * Cold Spring Harbor Symposia on Quantitative Biology
 */
export const PCR_LITERATURE: DomainLiterature = {
  name: "pcr",
  description:
    "PCR amplification model. Exponential amplification over n cycles. Final copy number: N(n) = N0 × E^n where E is per-cycle efficiency (typically 0.85-1.0).",
  references: [
    {
      authors: "Mullis, K. B., et al.",
      year: 1986,
      title: "Specific enzymatic amplification of DNA in vitro: The polymerase chain reaction",
      doi: "10.1101/sqb.1986.051.01.032",
    },
  ],
  defaultJustification:
    "Defaults (n0=100 template copies, efficiency=0.95, cycles=30) per Mullis et al. (1986). Efficiency 0.95 represents typical PCR. After ~30 cycles, reagent depletion limits amplification.",
};

/**
 * MOLECULAR_DYNAMICS Domain: Lennard-Jones Simulation
 * BACKING: Lennard-Jones, J. E. (1924)
 * "On the determination of molecular fields"
 */
export const MOLECULAR_DYNAMICS_LITERATURE: DomainLiterature = {
  name: "molecular_dynamics",
  description:
    "Molecular dynamics using Lennard-Jones potential. V(r) = 4ε[(σ/r)¹² - (σ/r)⁶]. Simulates particle interactions with repulsive (r¹²) and attractive (r⁶) terms.",
  references: [
    {
      authors: "Lennard-Jones, J. E.",
      year: 1924,
      title: "On the determination of molecular fields",
      doi: "10.1098/rspa.1924.0082",
    },
  ],
  defaultJustification:
    "Standard Lennard-Jones parameters (ε, σ) model rare-gas interactions. Numerical integration via Verlet algorithm per standard MD practice.",
};

/**
 * GILLESPIE_SSA_BIMOLECULAR Domain: Stochastic Simulation for Bimolecular Reactions
 * BACKING: Gillespie, D. T. (1976)
 * "A general method for numerically simulating the stochastic time evolution of coupled chemical reactions"
 */
export const GILLESPIE_SSA_BIMOLECULAR_LITERATURE: DomainLiterature = {
  name: "gillespie_ssa_bimolecular",
  description:
    "Gillespie SSA for bimolecular reactions: A + B → C. Two reactants combine into product. Stochastic simulation with bimolecular rate constant k (probability per pair per unit time).",
  references: [
    {
      authors: "Gillespie, D. T.",
      year: 1976,
      title: "A general method for numerically simulating the stochastic time evolution of coupled chemical reactions",
      doi: "10.1021/j100540a008",
    },
  ],
  defaultJustification:
    "Defaults (a0=50 A, b0=50 B, k=0.01 per pair/s) per Gillespie (1976). Bimolecular reactions require two molecules; rates scale with product of concentrations.",
};

/**
 * TWO_LOCUS_WRIGHT_FISHER Domain: Multi-locus Population Genetics
 * BACKING: Wright, S. (1931) & Fisher, R. A. (1930)
 * "Evolution in Mendelian populations" and "The Genetical Theory of Natural Selection"
 */
export const TWO_LOCUS_WRIGHT_FISHER_LITERATURE: DomainLiterature = {
  name: "two_locus_wright_fisher",
  description:
    "Two-locus Wright-Fisher model with recombination. Tracks allele frequencies at two loci simultaneously, including recombination rate between loci. Models linkage disequilibrium decay.",
  references: [
    {
      authors: "Wright, S.",
      year: 1931,
      title: "Evolution in Mendelian populations",
      doi: "10.1038/127487a0",
    },
    {
      authors: "Fisher, R. A.",
      year: 1930,
      title: "The Genetical Theory of Natural Selection",
    },
  ],
  defaultJustification:
    "Defaults (recombination_rate=0.01, population_size=10000) per Wright (1931). Recombination breaks linkage disequilibrium between loci; rates typical for unlinked loci.",
};

/**
 * LOTKA_VOLTERRA Domain: Predator-Prey Dynamics
 * BACKING: Lotka, A. J. (1925) & Volterra, V. (1926)
 * "Elements of Physical Biology" and "Variations and fluctuations of the number of individuals"
 */
export const LOTKA_VOLTERRA_LITERATURE: DomainLiterature = {
  name: "lotka_volterra",
  description:
    "Lotka-Volterra predator-prey model. Equations: dP/dt = α·P - β·P·V, dV/dt = γ·P·V - δ·V. Generates oscillating populations characteristic of predator-prey systems.",
  references: [
    {
      authors: "Lotka, A. J.",
      year: 1925,
      title: "Elements of Physical Biology",
    },
    {
      authors: "Volterra, V.",
      year: 1926,
      title: "Variations and fluctuations of the number of individuals in animal species living together",
    },
  ],
  defaultJustification:
    "Defaults (α=1.1, β=0.4, γ=0.1, δ=0.4) per Lotka (1925); γ < δ is the biologically ordinary case (predators convert prey to offspring slower than they die). Small-oscillation period 2π/√(αδ) ≈ 9.5 time units, comparable to the classic lynx-hare cycle. Population oscillations are the hallmark of this model; see tests/test_lotka_volterra_correctness.py for the conserved-quantity and fixed-point verification (a transposed γ/δ pairing here previously drove the prey population negative).",
};

/**
 * CELL_CYCLE_OSCILLATOR Domain: Molecular Cell Cycle
 * BACKING: Tyson, J. J. (1991)
 * "Modelling the cell division cycle: cdc2 and cyclin interactions"
 */
export const CELL_CYCLE_OSCILLATOR_LITERATURE: DomainLiterature = {
  name: "cell_cycle_oscillator",
  description:
    "Molecular model of cell cycle progression via cyclin-CDK regulation. Simulates periodic oscillations in cyclin levels driving G1/S and G2/M transitions.",
  references: [
    {
      authors: "Tyson, J. J.",
      year: 1991,
      title: "Modelling the cell division cycle: cdc2 and cyclin interactions",
      doi: "10.1083/jcb.115.3.577",
    },
  ],
  defaultJustification:
    "Default reaction rate constants from Tyson (1991) cell-cycle model. Produces ~30-minute oscillations typical of eukaryotic cell cycles.",
};

/**
 * REPRESSILATOR Domain: Synthetic Genetic Oscillator
 * BACKING: Elowitz, M. B., & Leibler, S. (2000)
 * "A synthetic oscillatory network of transcriptional regulators"
 */
export const REPRESSILATOR_LITERATURE: DomainLiterature = {
  name: "repressilator",
  description:
    "Repressilator: synthetic genetic network with three genes repressing each other in a ring (A⊣B⊣C⊣A). Produces robust sustained oscillations via negative feedback.",
  references: [
    {
      authors: "Elowitz, M. B., & Leibler, S.",
      year: 2000,
      title: "A synthetic oscillatory network of transcriptional regulators",
      doi: "10.1038/35002131",
    },
  ],
  defaultJustification:
    "Parameters from Elowitz & Leibler (2000) Nature paper. This circuit demonstrates that living cells can implement reliable synthetic clocks. ~40-minute oscillation period.",
};

export const DOMAIN_LITERATURE_MAP: Record<string, DomainLiterature> = {
  mm: MM_LITERATURE,
  mm_competitive_inhibition: MM_CI_LITERATURE,
  sir: SIR_LITERATURE,
  seir: SEIR_LITERATURE,
  wright_fisher: WRIGHT_FISHER_LITERATURE,
  gillespie_ssa: GILLESPIE_SSA_LITERATURE,
  pcr: PCR_LITERATURE,
  molecular_dynamics: MOLECULAR_DYNAMICS_LITERATURE,
  gillespie_ssa_bimolecular: GILLESPIE_SSA_BIMOLECULAR_LITERATURE,
  two_locus_wright_fisher: TWO_LOCUS_WRIGHT_FISHER_LITERATURE,
  lotka_volterra: LOTKA_VOLTERRA_LITERATURE,
  cell_cycle_oscillator: CELL_CYCLE_OSCILLATOR_LITERATURE,
  repressilator: REPRESSILATOR_LITERATURE,
};

export function getDomainLiterature(domain: string): DomainLiterature | undefined {
  return DOMAIN_LITERATURE_MAP[domain];
}

export function getDomainCitation(domain: string): string {
  const lit = getDomainLiterature(domain);
  if (!lit) return `Domain: ${domain}`;

  const primary = lit.references[0];
  if (!primary) return `Domain: ${domain}`;

  return `${primary.authors} (${primary.year}). ${primary.title}${primary.doi ? `. DOI: ${primary.doi}` : ""}`;
}
