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
      // The 1913 original has NO DOI: Biochemische Zeitschrift 49, 333-369
      // predates DOI assignment entirely, and the journal itself ceased
      // publication in 1967.
      //
      // This entry previously carried doi "10.1111/j.1432-1033.1913.tb07745.x",
      // which does not exist -- CrossRef returns 404 for it. The prefix
      // 1432-1033 belongs to the European Journal of Biochemistry, founded
      // in 1967, so no 1913 article could ever have borne it. It was
      // fabricated, and it was served to users as a citation until
      // verify_citations_live.py began discovering DOIs from source
      // (Stage 9 Part 5).
      //
      // The citable modern source is Johnson & Goody's complete English
      // translation, which reproduces the original in full and is the
      // reference English-speaking authors are directed to. Verified
      // against PubMed 2026-08-09: PMID 21888353, PMC3381512.
      authors: "Michaelis, L., Menten, M. L., Johnson, K. A., & Goody, R. S.",
      year: 2011,
      title:
        "The original Michaelis constant: translation of the 1913 " +
        "Michaelis-Menten paper [Michaelis & Menten (1913) Die Kinetik der " +
        "Invertinwirkung, Biochem. Z. 49, 333-369]. Biochemistry 50(39), " +
        "8264-8269",
      doi: "10.1021/bi201284u",
    },
  ],
  defaultJustification:
    "Lehninger (2008) is the source of the MICHAELIS-MENTEN MODEL, not of these numbers. Km=2mM and Vmax=5 are unverified teaching defaults chosen for legibility, and the hard rule (ADR 0008) blocks them from ever reaching a simulation: Km must resolve from BRENDA or be supplied explicitly. Vmax is reachable only via the ADR 0019 kcat x [E]0 bridge. An earlier version of this string read \'per Lehninger (2008)\', which asserted a citation for values no source supplies. See docs/literature-inventory.toml.",
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
      // doi "10.1021/ja01349a014" was WRONG: CrossRef registers it as
      // "THE RAMAN SPECTRUM OF GERMANIUM TETRACHLORIDE" -- a real paper on
      // an unrelated subject. Caught by the CrossRef title check.
      //
      // No replacement DOI is asserted here. J. Am. Chem. Soc. 1934 predates
      // PubMed's coverage, so it could not be verified against a primary
      // source from this environment, and substituting a plausible-looking
      // DOI is exactly the mistake being corrected. The journal, volume and
      // pages below are sufficient to locate the paper.
      title:
        "The Determination of Enzyme Dissociation Constants. " +
        "J. Am. Chem. Soc. 56(3), 658-666",
    },
  ],
  defaultJustification:
    "Copeland (2013) is the source of the COMPETITIVE-INHIBITION MODEL, not of these numbers. Km=2mM, Ki=1mM and Vmax=5 are unverified teaching defaults. Both Km and Ki resolve live from BRENDA (ADR 0018) and the hard rule rejects the query if either fails to resolve and is not supplied. See docs/literature-inventory.toml.",
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
    "Kermack & McKendrick (1927) is the source of the SIR MODEL, not of these rates. β=0.3 and γ=0.1 are unverified placeholders; for a recognised disease both are DERIVED live from a literature (R0, infectious period) pair via ADR 0020 (COVID-19: Hussein et al. 2021, giving β=0.576, γ=0.183). S0=990/I0=10 is a scenario choice, not a measurement. See docs/literature-inventory.toml.",
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
    "Anderson & May (1991) is the source of the SEIR MODEL, not of these rates. σ=0.2 (a 5-day latent period) is an UNVERIFIED teaching default: the ADR 0017 registry pairs R0 with a serial interval only, so no source in this system reports a latent period and σ has no literature backing today. β and γ derive from that registry for a recognised disease (ADR 0020). See docs/literature-inventory.toml.",
};

/**
 * WRIGHT_FISHER Domain: Population Genetics
 * BACKING: Rahbari, R., et al. (2016)
 * "Timing, rates and spectra of human germline mutation"
 * Nature Genetics 48(2), 126-133. DOI 10.1038/ng.3469, PMID 26656846.
 */
export const WRIGHT_FISHER_LITERATURE: DomainLiterature = {
  name: "wright_fisher",
  description:
    "Wright-Fisher population genetics model. Simulates allele frequency change under mutation and drift in finite population. Mutation probability per locus per generation.",
  references: [
    {
      // This entry previously cited doi 10.1038/ng.3285, "Variation and
      // heritability of RECOMBINATION rate in humans", to justify a
      // MUTATION rate. That DOI resolves perfectly well -- which is why
      // the live citation checker passed it -- but the paper is about a
      // different quantity than the one being claimed. A citation that
      // exists is not a citation that supports the statement.
      //
      // Corrected to Rahbari et al.'s germline-mutation paper, verified
      // against PubMed 2026-08-09: PMID 26656846, PMC4731925,
      // Nat Genet 48(2), 126-133.
      authors: "Rahbari, R., Wuster, A., Lindsay, S. J., et al.",
      year: 2016,
      title:
        "Timing, rates and spectra of human germline mutation. " +
        "Nature Genetics 48(2), 126-133",
      doi: "10.1038/ng.3469",
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
    "Human mutation rate: ~1.29e-8 per base pair per generation. The value actually resolved at runtime comes from stdpopsim's HomSap mean_mutation_rate (see Tests/popgen_resolver.py), which carries its own bundled citations (International Human Genome Sequencing Consortium 2001; Jonsson et al. 2017); Rahbari et al. (2016) is the pedigree-based germline mutation study backing the order of magnitude. Population size 10,000 (typical for modeling).",
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
    "Gillespie (1976) is the source of the STOCHASTIC SIMULATION ALGORITHM, not of these numbers. a0=1000 molecules and k=0.5 s⁻¹ are unverified illustrative values, not measured constants for any real species. (This string previously read \'a0=100 molecules, k=0.1 s⁻¹\' — both figures were also simply wrong against DOMAIN_DEFAULTS, which is what happens when a justification is prose nothing checks.) See docs/literature-inventory.toml.",
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
    "Mullis et al. (1986) is the source of the PCR METHOD, not of these numbers. n0=100 template copies and efficiency=0.95 are unverified teaching defaults: template count is an experimental input, and real PCR efficiency is assay-specific (conventionally reported in the 0.9-1.0 band, which 0.95 sits in without being taken from any specific measurement). 30 cycles is a protocol length, not a scientific claim. See docs/literature-inventory.toml.",
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
    "Gillespie (1976) is the source of the ALGORITHM, not of these numbers. a0=100, b0=100 and k=0.005 per pair/s are unverified illustrative values. (This string previously read \'a0=50, b0=50, k=0.01\', none of which matched DOMAIN_DEFAULTS.) See docs/literature-inventory.toml.",
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
      // Previously doi "10.1038/127487a0" -- a real Nature DOI for
      // "Oceanographical Expedition of the Dana, 1928-1930", an entirely
      // unrelated paper. Caught by the CrossRef title check.
      // Verified via PubMed 2026-08-09: PMID 17246615, PMC1201091.
      title: "Evolution in Mendelian Populations. Genetics 16(2), 97-159",
      doi: "10.1093/genetics/16.2.97",
    },
    {
      authors: "Fisher, R. A.",
      year: 1930,
      title: "The Genetical Theory of Natural Selection",
    },
  ],
  defaultJustification:
    "Wright (1931) is the source of the TWO-LOCUS DRIFT MODEL, not of these numbers — and this string previously stated both of them wrongly (recombination_rate=0.01, population_size=10000; the actual defaults are 0.1 and 100, off by 10x and 100x). Both are unverified teaching defaults: a real recombination rate is locus-pair specific, and 0.1 is chosen so linkage disequilibrium decay is visible over ~20 generations. mutation_rate DOES resolve live from stdpopsim. See docs/literature-inventory.toml.",
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
    "Lotka (1925) and Volterra (1926) are the source of the PREDATOR-PREY MODEL, not of these rates. α=1.1, β=0.4, γ=0.1, δ=0.4 are unverified teaching defaults; γ < δ is the biologically ordinary case (predators convert prey to offspring slower than they die), and the small-oscillation period 2π/√(αδ) ≈ 9.5 is comparable to the classic lynx-hare cycle, but no source supplies these four numbers. What IS verified is the model\'s behaviour under them: the exact first integral, the coexistence fixed point, the linearised period and agreement with an independent integrator — see tests/test_lotka_volterra_correctness.py. A transposed γ/δ pairing previously drove the prey population negative (ADR 0023). See docs/literature-inventory.toml.",
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
      // This entry previously carried doi "10.1083/jcb.115.3.577", which is
      // a REAL, resolving DOI for an entirely different paper: McIntosh &
      // Pfarr, "Mitotic motors", J Cell Biol 115(3), 577-585, 1991 -- a
      // review of kinesins and the mitotic spindle, with no connection to
      // Tyson's cdc2/cyclin ODE model. Verified against PubMed 2026-08-09
      // (PMID 1918154).
      //
      // Existence checks cannot catch this: the DOI resolved cleanly. It
      // was found by comparing the registered CrossRef title against the
      // title claimed here, which verify_citations_live.py now does.
      //
      // Correct source, already used by Tellurium/continuous/model_building.py:
      // PNAS 88(16), 7328-7332. PMID 1831270, PMC52288.
      authors: "Tyson, J. J.",
      year: 1991,
      title:
        "Modeling the cell division cycle: cdc2 and cyclin interactions. " +
        "PNAS 88(16), 7328-7332",
      doi: "10.1073/pnas.88.16.7328",
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
      doi: "10.1038/35002125",
    },
  ],
  defaultJustification:
    "Parameters from Elowitz & Leibler (2000) Nature paper. This circuit demonstrates that living cells can implement reliable synthetic clocks. ~40-minute oscillation period.",
};

/**
 * MONTE_CARLO_PI Domain
 * BACKING: Metropolis, N., & Ulam, S. (1949) "The Monte Carlo Method",
 * Journal of the American Statistical Association 44(247), 335-341.
 *
 * No DOI is asserted. JASA 1949 predates DOI assignment and the paper is
 * outside PubMed's biomedical scope, so it could not be verified against a
 * primary source from here -- and inventing a plausible-looking DOI is the
 * exact failure five other citations in this file turned out to be
 * (Stage 9 Part 6). Journal, volume, issue and pages locate it.
 */
export const MONTE_CARLO_PI_LITERATURE: DomainLiterature = {
  name: "monte_carlo_pi",
  description:
    "Monte Carlo estimation of pi by uniform sampling in [-1,1]^2 and counting the fraction falling inside the unit circle. Convergence follows the CLT error rate 1/sqrt(N).",
  references: [
    {
      authors: "Metropolis, N., & Ulam, S.",
      year: 1949,
      title:
        "The Monte Carlo Method. Journal of the American Statistical " +
        "Association 44(247), 335-341",
    },
  ],
  defaultJustification:
    "Metropolis & Ulam (1949) is the source of the METHOD, not of a sample count. n_samples is a precision/runtime tradeoff chosen by the caller, not a measured quantity. What IS verified is the convergence behaviour: the estimator's error is checked against the CLT rate 1/sqrt(N) in Tellurium/tests/test_monte_carlo_correctness.py. See docs/literature-inventory.toml.",
};

/**
 * GILLESPIE_SSA_REPLICATES Domain
 * BACKING: the same algorithm as gillespie_ssa -- Gillespie (1976). This
 * domain is the ensemble view of it, not a different method.
 */
export const GILLESPIE_SSA_REPLICATES_LITERATURE: DomainLiterature = {
  name: "gillespie_ssa_replicates",
  description:
    "Ensemble of independent Gillespie SSA trajectories, averaged onto a common time grid. The ensemble mean converges on the closed form E[a(t)] = a0*exp(-k*t).",
  references: GILLESPIE_SSA_LITERATURE.references,
  defaultJustification:
    "Gillespie (1976) is the source of the ALGORITHM. n_replicates is an ensemble size — a precision/runtime tradeoff, not a measured value. The ensemble mean is verified against the exact closed form E[a(t)] = a0*exp(-k*t) in Tellurium/tests/test_ssa_ensemble_unbiased.py, which pins that the bias SHRINKS as replicates grow. See docs/literature-inventory.toml.",
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
  monte_carlo_pi: MONTE_CARLO_PI_LITERATURE,
  gillespie_ssa_replicates: GILLESPIE_SSA_REPLICATES_LITERATURE,
  // `sbml` is deliberately absent: it is the raw-SBML escape hatch, where
  // the caller supplies the model. Terrium makes no scientific claim about
  // a document it did not author, so it has no domain citation to give.
};

export function getDomainLiterature(domain: string): DomainLiterature | undefined {
  return DOMAIN_LITERATURE_MAP[domain];
}

/**
 * Returns undefined -- NOT a placeholder -- when a domain has no literature
 * entry.
 *
 * This used to return the string `` `Domain: ${domain}` ``, which callers
 * pushed straight into `provenance.modelCitations`. So a Monte Carlo run
 * shipped "Domain: monte_carlo_pi" to the client in the list of citations
 * backing its result. A label is not a citation, and a citations array is
 * the one place a placeholder must never appear.
 *
 * `sbml` legitimately has no domain citation: the caller supplies the
 * model, so there is nothing for Terrium to cite. Returning undefined lets
 * the caller omit it rather than inventing one.
 */
export function getDomainCitation(domain: string): string | undefined {
  const lit = getDomainLiterature(domain);
  if (!lit) return undefined;

  const primary = lit.references[0];
  if (!primary) return undefined;

  return `${primary.authors} (${primary.year}). ${primary.title}${primary.doi ? `. DOI: ${primary.doi}` : ""}`;
}
