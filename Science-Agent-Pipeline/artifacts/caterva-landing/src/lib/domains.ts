// What Caterva runs today (enzyme focus since 2026-09-27; the other
// domains are in archive/legacy_domains/, and the v0.4.0 tag, cut before
// they were moved, still runs them).
//
// `status` says WHERE a capability is, because "live" said nothing true: no
// release carried the MD tools it was attached to. "released" means the
// RELEASE_TAG download has it; "main" means it is built and tested on the
// main branch and waits for the next release.
//
// Corrected 2026-11-01: this said v0.4.0, whose caterva/app.py registers
// only compose and sim, and marked the other four capabilities "main".
// v0.6.0 (published 2026-10-28) was then the latest release, and `git show
// v0.6.0:caterva/app.py` (v0.7.0's is the same file) registers prepare, md, analyze, bind, complex and
// fep as well, so every capability below is in it.
import repoFacts from "./generated/repoFacts.json";

export type CapabilityStatus = "released" | "main";

/**
 * The release the page offers, "v" + __version__ in caterva/__init__.py,
 * read from the generated repoFacts.json rather than typed here: the
 * literal this replaced still said v0.4.0 after v0.6.0 was published.
 * scripts/check_landing_test_counts.py fails when the file disagrees with
 * the package, and `--write` regenerates it.
 */
export const RELEASE_TAG: string = repoFacts.releaseTag;

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
    status: "released",
    desc: "caterva prepare: PDB defects and uncertain protonation states ranked by distance to the M-CSA catalytic residues",
  },
  {
    id: "md-setup",
    status: "released",
    desc: "caterva md: a GROMACS setup at the assay conditions of a cited constant, three replicas by default",
  },
  {
    id: "trajectory-analysis",
    status: "released",
    desc: "caterva analyze: catalytic distances and angles, hydrogen bonds, side-chain rotamers, active-site water and flexibility, each checked against GROMACS and reported only when the replicas agree",
  },
  {
    id: "binding-free-energy",
    status: "released",
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
