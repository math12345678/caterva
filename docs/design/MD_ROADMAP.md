# Caterva as a molecular-dynamics tool: what to build, and why it is better

**Status:** design, 2026-09-27. Nothing here is built except where it says
"shipped". Citations were checked against Crossref on the date above; tools
named without a DOI were not.

## The claim, stated so it can be checked

Caterva will not be a faster MD engine than GROMACS or OpenMM. It will run
them. Where it will be better is the part of an enzyme simulation where
the errors actually are:

1. **the decisions before the run** (which structure, which chain, what is
   missing, which protonation, which ligand parameters, which conditions),
2. **the honesty of what the run is said to show** (one trajectory is an
   anecdote; a replica set with its spread is a result), and
3. **the connection to experiment** (a simulation of an enzyme is only
   worth something next to that enzyme's measured behaviour).

No tool we know of does all three with a record of *why* each choice was
made. That record is what Caterva already does for kinetic constants, and
what this document extends to dynamics.

The field has written down the problem: the *Reliability and
reproducibility checklist for molecular dynamics simulations*
(Communications Biology, 2023, doi:10.1038/s42003-023-04653-0) exists
because simulation papers routinely omit what a reader needs to trust or
repeat them. Caterva's design goal is that its output **is** a completed
checklist, generated from the run rather than written afterwards.

## The RDP5 pattern: many methods, one interface, disagreement shown

RDP5 is trusted not because it has the best recombination test but because
it runs many of them the same way and shows where they disagree. The same
shape fits MD preparation, where each step has several defensible methods
and nobody reports which one they used:

| step | methods that disagree in practice | what Caterva shows |
|---|---|---|
| protonation at the assay pH | PROPKA, and alternatives | residues whose state depends on the method |
| ligand charges | AM1-BCC (GAFF2 via ACPYPE), OpenFF | atoms whose charge differs by > 0.1 e |
| missing residues | leave gap, model loop | which analyses the gap touches |
| sampling | replicas with different seeds | the spread, before any mean |

This is the kinetics layer's "where the evidence did not settle on one
value", applied to simulation inputs.

## What exists today, and the gap each leaves

(Descriptions of other tools are from their public documentation and should
be re-checked before any comparison is published.)

- **GROMACS, OpenMM, AMBER** -- engines. Excellent at running a system;
  silent about why the system is what it is.
- **CHARMM-GUI** -- the best-known setup builder (web). Produces inputs; the
  reasoning stays in the user's head, and it knows nothing of the enzyme's
  measured kinetics.
- **MDAnalysis, MDTraj** -- analysis libraries. Every enzyme-specific
  question (is the catalytic geometry intact? does the inhibitor stay?) is a
  script someone writes again.
- **ACPYPE** (doi:10.1186/1756-0500-5-367), OpenFF tooling -- ligand
  parameters. The choice of model and charge method is rarely recorded next
  to the result.
- **Free-energy frameworks** (OpenFE, pmx and others) -- compute binding
  free energies; comparing them with *measured* inhibition constants is left
  to the user, including finding the measurements.

## Capabilities, in the order they should be built

Each has: what it does, why it is better than the status quo, and how we
will know it works.

### Shipped (2026-09-27)

- **`caterva structure`** -- PDB entries grouped by protein (isoforms kept
  apart), ligands separated from crystallisation additives, every entry
  cited, ChimeraX script.
- **`caterva md`** -- GROMACS setup where every mdp setting is measured,
  chosen or cited, run at the assay conditions of a cited constant. Run end
  to end with GROMACS 2021 and in CI.

### M1. `caterva prepare`: a structure-preparation audit (highest value)

Before any simulation, report what is wrong with the model of the protein
and fix only what the user agrees to:

- **Missing residues and atoms** from the entry's own records (unobserved
  residues, incomplete side chains), and which of them are within 10 A of
  the active site.
- **Engineered mutations**: residues that differ from the UniProt sequence
  (crystallographers mutate enzymes to trap intermediates; simulating a
  catalytically dead mutant as the wild type is a silent, common error).
- **Alternate conformations, non-standard residues, the biological
  assembly** vs the asymmetric unit (LDH is a tetramer; chain A alone is a
  choice, and should be recorded as one).
- **Protonation at the assay pH**, with the residues whose state is
  uncertain named.
- **Catalytic residues from M-CSA** (Ribeiro et al. 2018, Nucleic Acids
  Res., doi:10.1093/nar/gkx1012): the curated atlas of enzyme mechanisms
  says which residues do the chemistry, so every warning can say whether it
  touches them.

*Better because* these are the errors that invalidate a simulation before
it starts, and today they are found (if at all) by reading the PDB file by
hand. *Done when* the report on a known problem entry (a mutant, a
structure with missing loops) names every defect a structural biologist
would, verified on at least five hand-checked entries.

### M2. Replicas and convergence by default

`caterva md --replicas 5` writes independent runs with recorded seeds and
reports every quantity as a spread across replicas, with block averaging for
within-run convergence. A single run is allowed and labelled "one sample".

*Better because* one trajectory reported as a result is the commonest
overclaim in the field, and a tool can make the honest option the default.
*Done when* a deliberately under-sampled run is reported as unconverged.

### M3. `caterva analyze`: enzyme questions, not generic plots

Analyses chosen from the enzyme's own biology:

- catalytic geometry from M-CSA residues (distances and angles the
  mechanism needs), per replica, with the crystal value beside it;
- ligand pose stability (RMSD from the bound pose, residence time);
- active-site flexibility (RMSF of pocket residues vs the rest);
- hydrogen-bond occupancy between ligand and catalytic residues.

Built on MDAnalysis or MDTraj, not reimplemented. *Better because* the
question is fixed by the enzyme, not by whoever wrote the script. *Done
when* each analysis reproduces a published observation on a known system.

### M4. Ligands with provenance

`caterva ligand` parameterises a bound molecule (GAFF2 via ACPYPE, or
OpenFF), records the model, charge method, net charge at the assay pH and
tool versions, and -- in the RDP5 spirit -- can run both and show where the
charges disagree. The stripped ligands `caterva md` lists today become
simulatable.

*Better because* ligand parameters are the least reproducible input in
enzyme MD. *Done when* oxamate and NADH in LDHA (1I10) run end to end, with
the provenance table extended to every ligand parameter source.

### M5. The bridge to kinetics (the part nobody else has)

Caterva already holds measured Km, kcat and Ki with citations and assay
conditions. Simulation results can be put next to them:

- **Binding free energy vs measured Ki.** For a competitive inhibitor,
  deltaG_bind is approximately RT ln Ki. An alchemical calculation (through
  an existing framework) is reported beside the cited Ki converted the same
  way, with the conditions of both, and the disagreement stated in kcal/mol
  -- not "validated".
- **Mutants.** BRENDA records kinetic constants for mutant enzymes. A
  simulated effect of a mutation can be compared with the measured change in
  kcat or Km, per paper.
- **pH.** A computed pKa for a catalytic residue beside the enzyme's
  measured pH optimum and pH-rate data.

*Better because* this is what makes a simulation evidence rather than an
illustration, and the measurements are already in Caterva with their
sources. *Done when* the Ki comparison runs for one well-characterised
inhibitor and the report states the agreement or disagreement with its
error bars.

### M6. Engines: OpenMM beside GROMACS

OpenMM (Eastman et al. 2017, PLOS Comput. Biol., doi:10.1371/journal.pcbi.1005659)
is a Python library with GPU support on common hardware, which makes
"install and run" possible without a cluster. Same provenance table, same
analyses, either engine; running both on one system is itself a check.

### M7. A methods section, generated

`caterva report` writes the methods paragraph and the reproducibility
checklist from the run's own records -- every version, seed, citation and
choice -- the way `compose --export methods` already does for kinetic
models.

## Non-goals

- Writing an MD engine or a force field.
- QM/MM reaction modelling (possibly later; not this roadmap).
- Claiming a simulation predicts kcat. It does not, and the report says so.

## What would make this fail

- Wrapping so much that users cannot see or change the underlying commands.
  Every step must write the plain GROMACS/OpenMM input it ran.
- Defaults that look authoritative. Every default stays labelled "chosen".
- Comparisons with experiment that are presented as validation. They are
  comparisons, with both uncertainties shown.
