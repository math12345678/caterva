// What Caterva runs today (enzyme focus since 2026-09-27; the other
// domains are in archive/legacy_domains/ and v0.4.0 still runs them).
export const DOMAINS = [
  {
    id: "enzyme-kinetics",
    status: "live",
    desc: "Michaelis-Menten, plain and competitively inhibited: Km, kcat and Ki from BRENDA with their citations and assay conditions",
  },
  {
    id: "stochastic-kinetics",
    status: "live",
    desc: "Exact Gillespie SSA: first-order decay, bimolecular association, replicate ensembles",
  },
  {
    id: "structure-audit",
    status: "live",
    desc: "caterva prepare: PDB defects ranked by distance to the M-CSA catalytic residues, and which chain to start from",
  },
  {
    id: "md-setup",
    status: "live",
    desc: "caterva md: a GROMACS setup at the assay conditions of a cited constant, three replicas by default",
  },
  {
    id: "trajectory-analysis",
    status: "live",
    desc: "caterva analyze: catalytic geometry and active-site flexibility, reported only when the replicas agree",
  },
];

/** How many are live: derived, so no copy of the number can drift from the list. */
export const LIVE_DOMAIN_COUNT = DOMAINS.filter((d) => d.status === "live").length;

/**
 * scripts/check_*.py in the repository, as counted by
 * scripts/check_documented_counts.py ("guards"). Update with it.
 */
export const GUARD_COUNT = 76;
