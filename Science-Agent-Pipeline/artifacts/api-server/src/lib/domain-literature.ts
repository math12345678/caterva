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
      // DOI corrected 2026-08-29 against CrossRef: the previous value,
      // 10.1021/j100540a008, is Gillespie 1977 "Exact stochastic
      // simulation of coupled chemical reactions" (J. Phys. Chem. 81) —
      // the adjacent-paper swap ADR 0076 is about, caught by the live
      // checker's ambiguity verdict. This title is the 1976 paper in
      // J. Comput. Phys. 22(4):403-434.
      doi: "10.1016/0021-9991(76)90041-3",
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
      // DOI corrected 2026-08-29 against CrossRef: the previous value,
      // 10.1021/j100540a008, is Gillespie 1977 "Exact stochastic
      // simulation of coupled chemical reactions" (J. Phys. Chem. 81) —
      // the adjacent-paper swap ADR 0076 is about, caught by the live
      // checker's ambiguity verdict. This title is the 1976 paper in
      // J. Comput. Phys. 22(4):403-434.
      doi: "10.1016/0021-9991(76)90041-3",
    },
  ],
  defaultJustification:
    "Gillespie (1976) is the source of the ALGORITHM, not of these numbers. a0=100, b0=100 and k=0.005 per pair/s are unverified illustrative values. (This string previously read \'a0=50, b0=50, k=0.01\', none of which matched DOMAIN_DEFAULTS.) See docs/literature-inventory.toml.",
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
    "Gillespie (1976) is the source of the ALGORITHM. n_replicates is an ensemble size — a precision/runtime tradeoff, not a measured value. The ensemble mean is verified against the exact closed form E[a(t)] = a0*exp(-k*t) in caterva/tests/test_ssa_ensemble_unbiased.py, which pins that the bias SHRINKS as replicates grow. See docs/literature-inventory.toml.",
};

export const DOMAIN_LITERATURE_MAP: Record<string, DomainLiterature> = {
  mm: MM_LITERATURE,
  mm_competitive_inhibition: MM_CI_LITERATURE,
  gillespie_ssa: GILLESPIE_SSA_LITERATURE,
  gillespie_ssa_bimolecular: GILLESPIE_SSA_BIMOLECULAR_LITERATURE,
  gillespie_ssa_replicates: GILLESPIE_SSA_REPLICATES_LITERATURE,
  // `sbml` is deliberately absent: it is the raw-SBML escape hatch, where
  // the caller supplies the model. Caterva makes no scientific claim about
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
 * model, so there is nothing for Caterva to cite. Returning undefined lets
 * the caller omit it rather than inventing one.
 */
export function getDomainCitation(domain: string): string | undefined {
  const lit = getDomainLiterature(domain);
  if (!lit) return undefined;

  const primary = lit.references[0];
  if (!primary) return undefined;

  return `${primary.authors} (${primary.year}). ${primary.title}${primary.doi ? `. DOI: ${primary.doi}` : ""}`;
}
