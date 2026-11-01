// Literature entries for the domains archived on 2026-09-27, moved verbatim
// from Science-Agent-Pipeline/artifacts/api-server/src/lib/domain-literature.ts.

/**
 * SIR Domain: Susceptible-Infected-Recovered Epidemiology
 * BACKING: Kermack, W. O., & McKendrick, A. G. (1927)
 * "A contribution to the mathematical theory of epidemics"
 * Proceedings of the Royal Society of London. Series A
 */
export const SIR_LITERATURE: DomainLiterature = {
  name: "sir",
  // Frequency-dependent transmission, matching what the engine integrates:
  // model_building.py emits `beta * S * I / N`. This description carried
  // Kermack & McKendrick's original density-dependent `-β·S·I` until
  // 2026-09-05. The distinction is not cosmetic -- R0 is beta/gamma under
  // the engine's form but beta*N/gamma under the one described here, so a
  // reader deriving R0 from this text for the registry's COVID-19
  // parameters and N = 1000 would have been off by a factor of 1000.
  //
  // Guarded by scripts/check_documented_equations_match_engine.py.
  description:
    "SIR compartmental epidemiological model. Describes disease spread with three compartments: S (susceptible), I (infected), R (recovered), with N = S + I + R. Equations: dS/dt = -β·S·I/N, dI/dt = β·S·I/N - γ·I, dR/dt = γ·I. Under this frequency-dependent form R₀ = β/γ.",
  references: [
    {
      authors: "Kermack, W. O., & McKendrick, A. G.",
      year: 1927,
      title: "A contribution to the mathematical theory of epidemics",
      doi: "10.1098/rspa.1927.0118",
    },
    {
      authors: "Heesterbeek, H., Anderson, R. M., et al.",
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
    // "Sigma = 1/incubation period" until 2026-09-05, which this entry's
    // OWN defaultJustification below argues is "directionally wrong, not
    // merely imprecise" -- sigma is the E→I rate, so it needs the LATENT
    // period (infection → infectiousness), and for SARS-CoV-2 the latent
    // period is SHORTER than the incubation period (Alene et al. 2021:
    // pooled serial interval 5.2 d < pooled incubation 6.5 d; Kang et al.
    // 2022: latent 3.9 d vs incubation 5.8 d). The description and the
    // justification contradicted each other in the same object, and the
    // description is the half that gets rendered.
    "SEIR compartmental model adds latent period. E (exposed) compartment between S and I, with N = S + E + I + R. Equations: dS/dt = -β·S·I/N, dE/dt = β·S·I/N - σ·E, dI/dt = σ·E - γ·I, dR/dt = γ·I. Sigma = 1/latent period (infection → becoming infectious), which is not the incubation period (infection → symptom onset).",
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
    "Anderson & May (1991) is the source of the SEIR MODEL, not of these rates. " +
    "σ=0.2 (a 5-day latent period) is an UNVERIFIED teaching default and cannot " +
    "currently be resolved: the ADR 0017 registry pairs R0 with a SERIAL INTERVAL, " +
    "while σ needs a LATENT period (infection → infectiousness). Substituting the " +
    "widely-published INCUBATION period (infection → symptoms) is directionally " +
    "wrong, not merely imprecise — pooled serial interval (5.2 d) is SHORTER than " +
    "pooled incubation (6.5 d) [Alene et al. 2021, BMC Infect Dis 21:257, PMID " +
    "33706702], the signature of presymptomatic transmission, so the latent period " +
    "is strictly shorter than the incubation period and an incubation-derived σ " +
    "would under-predict early epidemic speed. A measured latent period exists for " +
    "Delta (3.9 d, Kang et al. 2022) but this entry is the ancestral strain, whose " +
    "serial interval differs materially (5.45 d vs Delta's 3.9 d), so pairing them " +
    "would stitch together two incompatible parameter sets. β and γ derive from the " +
    "registry for a recognised disease (ADR 0020). See docs/literature-inventory.toml " +
    "[seir.sigma] for the full search record, and Tests/test_epidemiology_resolver.py " +
    "TestNoLatentPeriodIsOffered for the guard that keeps σ from acquiring a source " +
    "by accident.",
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
    // Named "International Human Genome Sequencing Consortium 2001;
    // Jonsson et al. 2017" as the bundled citations until 2026-09-05.
    // Both were wrong, checked by running stdpopsim 0.3.0: IHGSC 2001 is
    // bundled for the GENOME ASSEMBLY (stdpopsim tags each citation with
    // its reason), and Jónsson et al. is not in the HomSap catalog at
    // all. The rate's actual bundled source is Tian, Browning & Browning
    // (2019). popgen_resolver.py was surfacing the assembly paper's DOI
    // as this value's structured locator for the same reason -- see the
    // comment there, and ADR 0162 for the defect class.
    "Human mutation rate: ~1.29e-8 per base pair per generation. The value actually resolved at runtime comes from stdpopsim's HomSap mean_mutation_rate (see Tests/popgen_resolver.py); stdpopsim bundles that rate with Tian, Browning & Browning (2019), Am J Hum Genet 105(5):883-893, which is the citation this resolver surfaces. Rahbari et al. (2016) is an independent pedigree-based germline mutation study backing the order of magnitude. Population size 10,000 (typical for modeling).",
};

/**
 * PCR Domain: Polymerase Chain Reaction
 * BACKING: Mullis, K. B., et al. (1986)
 * "Specific enzymatic amplification of DNA in vitro: The polymerase chain reaction"
 * Cold Spring Harbor Symposia on Quantitative Biology
 */
export const PCR_LITERATURE: DomainLiterature = {
  name: "pcr",
  // The formula below said `N(n) = N0 × E^n` until 2026-09-05. With the
  // efficiency range it states in the same sentence (0.85-1.0), that is a
  // DECAY curve: at 30 cycles and E = 0.9 it yields 0.042*N0, a PCR
  // reaction that destroys 96% of its template. caterva/discrete/pcr.py
  // computes `n0 * (1.0 + efficiency) ** cycle` = 5.2e8*N0 -- a factor of
  // 1.2e10 apart. The engine was right; this description, which is served
  // to users through /api/pipeline/literature, was wrong.
  //
  // Guarded by scripts/check_documented_equations_match_engine.py.
  description:
    "PCR amplification model. Exponential amplification over n cycles. Final copy number: N(n) = N0 × (1 + E)^n, where E is the fraction of template copied per cycle (typically 0.85-1.0; E = 1 is perfect doubling). Passing a plateau capacity switches to discrete logistic growth toward that capacity.",
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
 * BACKING: Jones, J. E. (1924) -- published before his 1925 marriage, after
 * which he adopted "Lennard-Jones." The potential is still named for him
 * under that later name; the paper's own byline is not.
 * "On the determination of molecular fields"
 */
export const MOLECULAR_DYNAMICS_LITERATURE: DomainLiterature = {
  name: "molecular_dynamics",
  description:
    "Molecular dynamics using Lennard-Jones potential. V(r) = 4ε[(σ/r)¹² - (σ/r)⁶]. Simulates particle interactions with repulsive (r¹²) and attractive (r⁶) terms.",
  references: [
    {
      // Published as "Jones, J. E." -- he married Kathleen Lennard in 1925
      // and adopted "Lennard-Jones" afterward, so the 1924 byline itself
      // reads "Jones," not "Lennard-Jones" (confirmed against CrossRef's
      // metadata for this DOI). The potential is still correctly called
      // "Lennard-Jones" today; that's the model's later, eponymous name,
      // not what's actually printed on this specific paper.
      authors: "Jones, J. E.",
      year: 1924,
      title: "On the determination of molecular fields",
      doi: "10.1098/rspa.1924.0082",
    },
  ],
  defaultJustification:
    "Standard Lennard-Jones parameters (ε, σ) model rare-gas interactions. Numerical integration via Verlet algorithm per standard MD practice.",
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
      // Correct source, already used by caterva/continuous/model_building.py:
      // PNAS 88(16), 7328-7332. PMID 1831270, PMC52288.
      authors: "Tyson, J. J.",
      year: 1991,
      title:
        "Modeling the cell division cycle: cdc2 and cyclin interactions. " +
        "PNAS 88(16), 7328-7332",
      doi: "10.1073/pnas.88.16.7328",
    },
  ],
  // "~30-minute oscillations typical of eukaryotic cell cycles" until
  // 2026-09-05. Two errors in one clause. The period: integrating this
  // file's own parameter set (kappa=0.015, k6=1, k4=180, k4prime=0.018 --
  // which matches BIOMD0000000006 exactly) gives ~35.6 min, not ~30. And
  // the biology: a typical somatic eukaryotic cell cycle runs ~24 hours,
  // not half an hour. Tyson (1991) associates this spontaneous-oscillation
  // mode with the rapid division cycles of early embryos, which is what
  // ~35 minutes actually describes.
  defaultJustification:
    "Default reaction rate constants from Tyson (1991) cell-cycle model. Produces ~35-minute oscillations, comparable to the rapid division cycles of early embryos that Tyson associates with this oscillatory mode — not the ~24-hour cycle of a typical somatic eukaryotic cell.",
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
    "Metropolis & Ulam (1949) is the source of the METHOD, not of a sample count. n_samples is a precision/runtime tradeoff chosen by the caller, not a measured quantity. What IS verified is the convergence behaviour: the estimator's error is checked against the CLT rate 1/sqrt(N) in caterva/tests/test_monte_carlo_correctness.py. See docs/literature-inventory.toml.",
};
