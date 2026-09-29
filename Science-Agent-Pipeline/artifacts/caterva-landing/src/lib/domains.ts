// What Caterva runs today (enzyme focus since 2026-09-27; the other
// domains are in archive/legacy_domains/ and v0.4.0 still runs them).
//
// `status` says WHERE a capability is, because "live" said nothing true: no
// release carried the MD tools it was attached to. "released" means the
// v0.4.0 download has it (caterva/app.py at the tag lists compose and sim);
// "main" means it is built and tested on the main branch and waits for the
// next release.
export type CapabilityStatus = "released" | "main";

export const RELEASE_TAG = "v0.4.0";

export const STATUS_LABEL: Record<CapabilityStatus, string> = {
  released: RELEASE_TAG,
  main: "main",
};

export const DOMAINS: { id: string; status: CapabilityStatus; desc: string }[] = [
  {
    id: "enzyme-kinetics",
    status: "released",
    desc: "caterva compose: Michaelis-Menten, inhibition and composed mechanisms, with Km, kcat and Ki from BRENDA, their citations and assay conditions",
  },
  {
    id: "stochastic-kinetics",
    status: "released",
    desc: "caterva sim: exact Gillespie SSA for first-order decay, bimolecular association and replicate ensembles",
  },
  {
    id: "structure-audit",
    status: "main",
    desc: "caterva prepare: PDB defects and uncertain protonation states ranked by distance to the M-CSA catalytic residues",
  },
  {
    id: "md-setup",
    status: "main",
    desc: "caterva md: a GROMACS setup at the assay conditions of a cited constant, three replicas by default",
  },
  {
    id: "trajectory-analysis",
    status: "main",
    desc: "caterva analyze: catalytic geometry, hydrogen bonds and active-site flexibility, reported only when the replicas agree",
  },
  {
    id: "binding-free-energy",
    status: "main",
    desc: "caterva bind, complex, fep: an absolute binding free energy judged against a cited Ki; not yet shown to reproduce one",
  },
];

/** How many capabilities are built, and how many a release carries.
 * Derived, so no copy of either number can drift from the list. */
export const CAPABILITY_COUNT = DOMAINS.length;
export const RELEASED_COUNT = DOMAINS.filter((d) => d.status === "released").length;

/**
 * scripts/check_*.py in the repository, as counted by
 * scripts/check_documented_counts.py ("guards"). Update with it.
 */
export const GUARD_COUNT = 76;
