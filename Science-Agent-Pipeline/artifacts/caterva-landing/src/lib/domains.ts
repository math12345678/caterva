// What Caterva runs today (enzyme focus since 2026-09-27; the other
// domains are in archive/legacy_domains/ and v0.4.0 still runs them).
//
// `status` says WHERE a capability is, because "live" said nothing true: no
// release carried the MD tools it was attached to. "released" means the
// v0.4.0 download has it (caterva/app.py at the tag lists compose and sim);
// "main" means it is built and tested on the main branch and waits for the
// next release.
import repoFacts from "./generated/repoFacts.json";

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
    desc: "caterva analyze: catalytic distances and angles, hydrogen bonds, side-chain rotamers, active-site water and flexibility, each checked against GROMACS and reported only when the replicas agree",
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
 * scripts/check_*.py in the repository ("guards"), read from the generated
 * repoFacts.json rather than typed here: the literal this replaced said 76
 * while scripts/ held 79. scripts/check_landing_test_counts.py fails when
 * the file disagrees with the tree, and `--write` regenerates it.
 */
export const GUARD_COUNT: number = repoFacts.guardScripts;

/**
 * The external data sources docs/data-sources.json attributes (BRENDA,
 * NCBI Taxonomy, ExPASy ENZYME), from the same generated file. KEGG is
 * not among them: it is off unless an operator sets CATERVA_ENABLE_KEGG.
 */
export const DATA_SOURCES: readonly string[] = repoFacts.dataSources;

/** The literature suite's size as README.md states it, from the same file. */
export const LITERATURE_TEST_COUNT: number = repoFacts.tests.literature;
