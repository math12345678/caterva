# Using Caterva

A guide for someone who has just downloaded it and wants to get something
useful out of it today. No prior knowledge of the codebase assumed.

Unaffiliated with Tellurium. See [NOTICE](../NOTICE).

---

## The one idea to get first

**Caterva builds a model from the SHAPE of a mechanism, not from the NAME of
a system.**

```
caterva compose "two genes repressing each other"      ->  builds a model
caterva compose "glycolysis"                           ->  refuses, and says why
```

"Glycolysis" is a name. To build it you need its actual enzymes and
stoichiometry, which is a pathway database Caterva does not read. So it
refuses rather than inventing a plausible-looking pathway. "Two genes
repressing each other" is a shape: a toggle switch, and Caterva knows what
one is made of.

That single rule explains almost every refusal you will meet. When something
does not build, you are usually naming a subject where a mechanism is wanted.

The second idea, which is the whole point of the project:

**Every number is labelled with where it came from.** Measured, placeholder,
or yours. A number nobody measured is never presented as though someone did.

---

## Your first three minutes

Get the folder for your machine from the
[Releases page](https://github.com/math12345678/caterva/releases), unpack it,
and from a terminal inside the folder:

```bash
# macOS only, once: the folder is not code-signed
xattr -dr com.apple.quarantine .
```

```bash
./caterva compose "a toggle switch between two repressors"
```

You get a document. Read the **Verdict** at the top: it tells you what the
model does and does not support, names the single worst problem with it, and
says what to do next. Then:

```bash
./caterva compose --shapes
```

All 36 mechanisms it can build, each with a one-line description. This is
the menu. Describe any of them in your own words and it will recognise
them.

```bash
./caterva compose "Michaelis-Menten with a competitive inhibitor" --export methods
```

A methods paragraph for a write-up, with every constant's origin stated. On
Windows write `.\caterva.exe` instead of `./caterva`; installed from the
wheel, write `caterva-compose` instead of `caterva compose`.

That is the whole product in three commands. Everything below is detail.

---

## How to read the report

A report has fixed sections, in this order. You can skip most of them most
of the time.

| section | what it answers | read it when |
|---|---|---|
| **Verdict** | Is this model good for anything, and what is wrong with it? | always, first |
| **Structure** | What reactions and rate laws did it build? | you want to check it understood you |
| **Invariants** | What is conserved? (derived from stoichiometry, exact) | you are checking a simulation is trustworthy |
| **Dimensions** | Do all the rate laws balance, in units and in scale? | it is checked every time; look if it complains |
| **Where the numbers come from** | Which constants are measured, which are placeholders, which are yours | **always, second** |
| **Behaviour** | Steady states, stability, does it switch or oscillate | you asked a question about long-run behaviour |
| **Time course** | The trajectory, and whether anything independent confirmed it | you want a curve |

### The verdict is a grade, not a score

It will say one of a few things, of which the common one is:

```
VERDICT: STRUCTURAL

What this supports: Questions about the MECHANISM: can this shape oscillate,
can it switch, which constants would matter if you measured them. Not
questions about any particular enzyme or cell, because the constants are the
library's illustrative values.
```

That is Caterva telling you, honestly, that you have a model of a *kind of
system*, not of *your* system. It is still useful — "can this shape switch at
all" is a real question — but it will not tell you what your cells do until
you put your numbers in.

There is deliberately no 0-to-100 score. A model that is structurally sound
and numerically absurd is not "medium"; it has one specific problem, and the
verdict names it.

### "Did not run" is not "passed"

Every report distinguishes the two:

```
2 check(s) did NOT run: robustness (not run -- pass --robustness ...);
validate (not run -- pass --validate ...). Those are unexamined, not passed.
```

If you want those checks, you have to ask for them. Caterva will never let a
check it did not run look like a check that succeeded.

---

## A worked example, start to finish

Someone in a lab meeting says: *we think the middle kinase in our cascade is
the one that matters — can you check before we spend three weeks on it?*

**1. Build the shape.**

```bash
caterva compose "three step phosphorylation cascade"
```

The verdict comes back `STRUCTURAL`, with one concern:

```
all 12 rate constant(s) are the motif library's illustrative values,
because no enzyme was named
```

Read that as the honest answer to the question you just asked: you have a
model of *a* three-step cascade, not of *yours*. Everything below is
therefore about the shape — which is still worth knowing, and the report
keeps saying so rather than letting you forget.

**2. Ask which step matters.**

```bash
caterva compose "three step phosphorylation cascade" --screen
```

```
Effect on tier3_Xp, 5 perturbation(s):
  - tier1_X knocked out ... tier3_Xp 0.9999 -> -1.007e-16, -1.01e-16x down
  - tier2_X knocked out ... tier3_Xp 0.9999 -> -6.496e-24, -6.5e-24x down
  - tier1_phosphatase knocked out ... tier3_Xp 0.9999 -> 1, 1x up
```

Every tier is essential; the phosphatase is not. That is a property of the
shape (a cascade in series), not of your kinase — and the section says so
underneath, along with a distinction worth carrying into the wet lab: a
knockout removes the protein, while a catalytically dead mutant leaves it in
place still sequestering its substrate, and the two give different answers.

**3. Ask whether that survives not knowing the constants.**

```bash
caterva compose "three step phosphorylation cascade" --robustness 50
```

If the ranking holds while every placeholder is resampled fifty times, it was
a conclusion about the architecture. If it moves, it was a conclusion about
numbers nobody measured — and you have just saved three weeks.

**4. Ask what to measure instead.**

```bash
caterva compose "three step phosphorylation cascade" --design
```

This ranks candidate measurements by how much *new* information each adds,
names the parameter combinations nothing you have measured can currently
distinguish, and tells you which observations would merely repeat what you
already know. It also states its own blind spot without being asked: the
ranking is by information only, and knows nothing about cost or how long an
assay takes.

**5. Leave a record anyone can check.**

```bash
caterva compose "three step phosphorylation cascade" --export methods > methods.md
caterva compose "three step phosphorylation cascade" --export csv > params.csv
```

The methods paragraph says, in prose, that no constant came from the
literature and lists all twelve placeholders with the table each would come
from. The CSV is the same thing row by row, with the citation, organism,
assay pH, temperature and buffer columns ready for when a real measurement
replaces a placeholder.

Total time on an idle laptop: about a minute for all four steps (the
`--design` and `--robustness` runs are the slow ones; see the timings under
"It is too slow"). What you can now say in the meeting is not "the middle
kinase matters" but something better: *in this architecture every
tier is essential, that conclusion does or does not survive our ignorance of
the constants, and here is the one measurement that would tell us most.*

---

## Recipes

Each of these is a real command. Add them to any `compose` call.

### "Which step in my pathway actually matters?"

```bash
caterva compose "three step phosphorylation cascade" --screen
```

Knocks out every species in turn and ranks the effects by fold change. Note
what it says about what a knockout *is*: it removes the gene product
permanently, so nothing can resynthesise it — which is different from a
catalytically dead mutant that still sits there sequestering its substrate.
For one species at a time:

```bash
caterva compose "..." --knockout tier2_X --overexpress tier1_kinase
```

### "Which measurement should I make next?"

```bash
caterva compose "Michaelis-Menten with a competitive inhibitor" --design
```

This is the one to show a lab. It works out which parameter combinations your
current measurements cannot distinguish, then ranks candidate measurements by
how much *new* direction each one adds. On the example above it says: measure
the **settling time**, because four different steady-state concentrations
would each repeat information you already have.

It also tells you its own limits, unprompted: the ranking is by information
only. It does not know that the top measurement takes three weeks and the one
below it takes an afternoon. That is your call; the ranking is one input.

### "Does my conclusion survive not knowing the constants?"

```bash
caterva compose "a toggle switch between two repressors" --robustness 50
```

Resamples every placeholder 50 times and re-solves. If your conclusion
("it switches") holds across the resampling, it was a conclusion about the
shape. If it evaporates, it was a conclusion about numbers nobody measured.

### "Is this model physically possible at all?"

```bash
caterva compose "..." --scale --predictions
```

Two different checks, and each can pass while the other fails:

- `--scale` checks the numbers going **in** — against the diffusion limit,
  the tightest measured Kd, one molecule per bacterium.
- `--predictions` checks the numbers coming **out** — a steady state above
  the cell's total protein content, or below one molecule per cell.

### "Where does this thing switch?"

```bash
caterva compose "a toggle switch between two repressors" --sweep geneA_n \
    --sweep-from 1 --sweep-to 4 --sweep-steps 30
```

Sweeps a parameter and reports where the behaviour changes qualitatively.

### "Give me something I can put in a paper"

```bash
caterva compose "..." --export methods > methods.md   # a methods paragraph
caterva compose "..." --export csv     > params.csv   # every constant, with its origin
caterva compose "..." --export sbml    > model.xml    # SBML, for COPASI, Tellurium, anything
caterva compose "..." --export antimony > model.txt   # Antimony source
```

The CSV has one row per constant with columns for `origin`
(`measured` / `placeholder` / `chosen`), the source table a measurement
would come from, the citation, organism, assay pH, temperature and buffer.
It is an audit trail, not just a parameter list.

### "It is too slow"

The steady-state search and the influence ranking are the expensive parts:

```bash
caterva compose "..." --no-ranking            # skip the influence ranking
caterva compose "..." --no-simulate           # skip the time course
caterva compose "..." --no-analysis           # skip the steady-state analysis
```

Measured on one idle laptop (Apple silicon), a three-step cascade with
twelve constants: everything 20 s, `--no-ranking` 15 s, `--no-ranking
--no-simulate` 11 s, `--no-analysis` 14 s. A toggle switch with eight
constants is 2 s either way. Those are one machine's numbers, and anything
else running on yours changes them a lot — the same commands took five to
ten times longer here while two test suites were running. Reach for these
flags when a model is large enough to be slow, not by default.

### "I want single-molecule noise, not a smooth curve"

```bash
caterva compose "reversible binding of a ligand to a receptor" --stochastic 1e-15
```

An exact Gillespie simulation in a compartment of that volume in litres
(an *E. coli* cell is about 1e-15 L). It refuses any rate law that is not mass
action, because a Michaelis-Menten rate has no propensity — that is a real
restriction of the method, not a missing feature. The seed is reported in the
output so the trajectory can be reproduced.

---

## Structures and dynamics: from a constant to a simulation

Two commands carry an enzyme from its kinetics to its structure and on to a
molecular dynamics setup, with the same rule throughout: every number says
where it came from.

### Which compound each constant belongs to

BRENDA files every Km, Ki and kcat under a compound, and a constant is only
meaningful under the right one. A competitive inhibitor's Ki is the
inhibitor's; a reverse Km is the product's; a phosphatase's Km is the
phosphorylated form's. `compose` looks each constant up under its own
compound: `--substrate` names the substrate, `--inhibitor` the inhibitor,
`--product` the product, and `--compound PORT=NAME` any other (the report
names the port each unsearched constant needs). A constant whose compound
was not named is not searched under the substrate's name: it stays a
labelled placeholder, and the reason says which flag would fill it. Mixed
inhibition's Kic and Kiu are never filled from one database row, which
cannot say which of the two it measured.

Until 2026-09-29 every constant was looked up under the one substrate, so
an inhibition model's Ki came back as a Ki "of" the substrate, or not at
all. The API server did the same until the same day; it now looks a Ki up
under the inhibitor the query names ("... inhibited by gossypol") and looks
none up when the query names none.

The report and every export also say what each value's own BRENDA row
measured, where that could make it the wrong number for the model: another
isoform, another inhibition mode, a mode not stated, inhibition measured
against a different molecule than the model's substrate, or a tagged,
immobilised or modified preparation rather than the free enzyme.

### Asking for one isoform

```bash
caterva compose "Michaelis-Menten with a competitive inhibitor" \
    --subject 1.1.1.27 --organism human --substrate pyruvate \
    --inhibitor gossypol --isoform LDH-A
```

Human LDH is three proteins, and BRENDA 711801 gives gossypol's Ki for each
(0.0019 mM for LDH-A, 0.0014 for LDH-B, 0.0042 for LDH-C). Without
`--isoform` the resolver returns the first it ranks, LDH-B's, and the report
says so. With it, each constant comes from a row that measured the isoform
asked for; where no row names that isoform, a row naming none is used and
the report says whether it measured LDH-A is unknown; and a constant BRENDA
only holds for other isoforms is refused rather than filled with another
protein's value. The names compare without case or hyphens, and are read by
the same parser `caterva bind --isoform` uses.

### `caterva structure`: which structures exist, and which protein each is

```bash
caterva structure --subject 1.1.1.27 --organism human
```

EC 1.1.1.27 in human is five proteins (LDHA, LDHB, LDHC and two LDHAL6),
with 55 PDB entries between them. A structure belongs to one protein, so
this lists them and refuses (exit 3) to pick one for you. Choose:

```bash
caterva structure --subject 1.1.1.27 --organism human --gene LDHA \
    --ligand oxamate --chimerax ldha.cxc
```

Entries with the ligand bound come first, then by method and resolution.
Each shows its ligands, cofactors and metals, kept apart from
crystallisation additives (glycerol, sulfate, acetate), and its primary
citation, or, for the depositions whose paper never appeared, says
"unpublished deposition" and cites the entry's own DOI. `oxamate` finds
OXAMIC ACID: the carboxylate and its acid are folded together, nothing
further. `ldha.cxc` opens the top entry in ChimeraX with the ligand, the
residues within 5 A of it, and the citations in its header:
`chimerax ldha.cxc`.

### `caterva prepare`: what is wrong with the structure before you simulate it

```bash
caterva prepare 1I10
```

It reads the entry's own records and ranks every defect by how close it
sits to the enzyme's catalytic residues, which it takes from M-CSA and maps
onto each chain by alignment. For 1I10 the answer is a table:

```
| chain | blocking defects | findings within 10 Å of the active site | catalytic residues intact |
| A | 0 | 0 | yes |
| D | 2 | 3 | **no** |
| G | 2 | 2 | **no** |
...
Chains with no blocking defect: A, C.
```

Chain D's catalytic Arg105 has no side chain; chain G's is not modelled at
all. Both sit in the active-site loop, which is disordered in several
chains. A setup that took "chain D" would have run without complaint.

It also reports substitutions whatever the depositors called them
(1L63's two engineered mutations are labelled 'conflict'), and says what it
did not check. It changes nothing; `--json` writes the findings for a
script. Exit code 4 means every chain has a blocking defect.

### `caterva md`: a GROMACS setup at the conditions the constants were measured under

```bash
caterva md --pdb 1I10 --chain A \
    --subject 1.1.1.27 --organism human --substrate pyruvate --out ldha-md
bash ldha-md/run.sh
```

With `--subject`, `--organism` and `--substrate`, the literature is searched
first, and the simulation runs at the temperature and pH of the first cited
constant whose paper states them: here 37 C and pH 7.5, from the assay
behind human LDHA's Ki (BRENDA ref 739793). `ldha-md/PROVENANCE.md` lists
every setting in the `.mdp` files as **measured**, **chosen** or
**method** (with a verified DOI). Without a measured temperature the run
still writes, at 25 C labelled a choice, and exits 3 to say so.

What it will not do: invent a topology for a ligand (it strips and lists
them; parameterise them with ACPYPE/GAFF or CGenFF), or pretend GROMACS's
standard protonation states match an assay at pH 5 (it records the pH and
points at PROPKA). `run.sh` needs `gmx` on PATH (or `GMX=/path/to/gmx`);
it was run end to end with GROMACS 2021 on 1I10 chain A, and CI runs every
stage on lysozyme (1AKI) with Ubuntu's GROMACS.

**Three replicas by default.** `run.sh` builds and minimises the system
once, then runs `rep1`, `rep2`, `rep3`, which differ only in their initial
velocities (seeds recorded in PROVENANCE.md). One trajectory is an
anecdote; `--replicas 1` is allowed and labelled one sample. When the runs
finish:

```bash
caterva md --summarise ldha-md
```

It reads each replica's backbone RMSD, estimates its error by block
averaging (Flyvbjerg & Petersen 1989, which corrects for correlated frames),
counts how many independent samples each run is really worth, and compares
the replicas with each other. The verdict is **consistent**, **replicas
disagree** (each run found a different state), **unconverged** (a run is
shorter than its own correlation time), or **one sample**; anything but
consistent exits 4. On synthetic runs with a known correlation time it
called every under-sampled set unconverged, and raised a false alarm on
about 6 in 100 converged ones: it errs towards "not yet".

With `--ph` (the assay pH), `caterva prepare` also judges every titratable
residue within the active-site radius. It does not predict pKa values: it
takes how far folded proteins move each group's pKa (Grimsley, Scholtz &
Pace 2009: 541 measured values in 78 proteins, a mean and standard
deviation per group) and asks whether, for any pKa within one standard
deviation, the residue is below 10% or above 90% protonated at that pH
(Henderson-Hasselbalch). If so its charge is settled; if not it is
uncertain, and needs PROPKA or a constant-pH simulation before the state
GROMACS assigns can be trusted. It also says when pdb2gmx's default
contradicts even typical behaviour (Asp at pH 1, for instance), which is
an error to fix by hand. On lactate dehydrogenase (1I10) at pH 7.5 it
flags the catalytic His192, the proton relay, as uncertain; pdb2gmx would
set it from hydrogen bonds without consulting the pH at all.

### `caterva analyze`: the questions the mechanism asks

```bash
caterva analyze ldha-md
```

After `run.sh`, this takes the enzyme's catalytic residues (M-CSA, mapped
onto your chain by `caterva prepare`) and measures, in every replica, the
distance between the functional groups of each pair: a histidine's ring
nitrogens, a carboxylate's oxygens. Each distance is set beside its value
in the starting crystal structure and called **held** or **moved** (more
than 0.1 nm, a stated choice) only when the replicas agree; otherwise it is
not yet a result. It also compares the active-site pocket's flexibility
(Cα RMSF within 8 Å of a catalytic residue) with the rest of the protein.

Caterva does the measuring itself, reading the trajectories with its own
.xtc decoder, so this runs where GROMACS is not installed. The same
measurements as GROMACS commands go in `analyze.sh`: `--gromacs` runs
them instead, `--script-only` writes them for a cluster and `--no-run`
reads what they produced. On two real lysozyme replicas the two routes
give the same fifteen catalytic distances (two differ by 0.001 nm, the
precision GROMACS prints) and the same verdicts, and the same RMSF to
0.0001 nm on every residue. Until 2026-09-29 `gmx rmsf` read about 10%
higher in the most mobile loop (residues 67-72): `analyze.sh` gave it the
tpr's coordinates as the fit reference, and a tpr stores them wrapped into
the box, with those residues a box length from their neighbours. The script
now makes the reference and the trajectory whole first, and CI compares the
two routes' RMSF on every run.

It also counts hydrogen bonds between each pair of catalytic side chains,
frame by frame, with the criterion of `gmx hbond` (donor-acceptor at most
0.35 nm, acceptor-donor-hydrogen at most 30 degrees; backbone excluded),
and reports each pair's occupancy per replica: kept, lost, formed, rarely
formed or partial, with the thresholds printed. On the two lysozyme
replicas, every per-frame count for six catalytic pairs equals
`gmx hbond`'s, and those counts are a test.

It reads each catalytic residue's first side-chain dihedral (chi1,
N-CA-CB-gamma) in every frame too, because a side chain can turn over while
every distance between functional-group centres stays put. Each frame is
put in the well it is nearest (+60, 180 or -60 degrees; named by angle
because gauche+ and gauche- are used both ways round), and each residue is
reported as kept, flipped (to which well, when the replicas agree),
partial, or replicas disagree, with the thresholds printed. The angles
equal `gmx angle -type dihedral`'s to 0.001 degree on six lysozyme
catalytic residues over 21 frames, and that comparison is a test. The
GROMACS route measures the same with `gmx angle` (an index of the four
atoms per residue is written to `chi1.ndx`), and CI checks that the two
routes' rotamer tables are identical.

Each catalytic distance now carries the 95% confidence interval of its
mean across replicas (Student's t, which is 12.7 for two replicas), and
the report says whether there are enough replicas to decide held or moved:
the interval must be within +/- 0.05 nm, half the moved threshold. When it
is not, it says how many replicas would be, if the spread between runs
stays as observed. On two 10 ps lysozyme replicas: 13 of 15 distances are
unresolved, and 10 replicas would resolve them. `caterva md --summarise`
reports the same interval. On a 200-step test run of lysozyme it lists all fifteen
distances between the six M-CSA catalytic residues, and correctly calls
every one unconverged.

### `caterva bind`: the number a free-energy calculation is held to

```bash
caterva bind --ec 1.1.1.27 --organism human --list
caterva bind --ec 1.1.1.27 --organism human --inhibitor gossypol --isoform LDH-A --computed "-7.2±0.4"
```

Every Ki BRENDA records for the inhibitor becomes ΔG°bind = RT ln(Ki / 1 M)
at the temperature it was measured at. A row with no temperature gets a
range over 4-37 °C, not a guessed value. Before any row is used, three
questions are asked of it, because each is a way to validate against the
wrong number:

- **Which binding event.** A competitive Ki is the Kd of inhibitor and free
  enzyme; an uncompetitive one is the Kd of inhibitor and enzyme-substrate
  complex; a mixed-type row gives one of two constants without saying
  which. `--state free` (the default) or `--state ternary` says what you
  simulated, and rows that measured something else are listed as not
  comparable, with the reason.
- **Which protein.** Gossypol's three human rows are LDH-A, LDH-B and
  LDH-C: three proteins. `--isoform` keeps the one simulated.
- **Which molecule.** A Ki belongs to the compound in its row. "Competitive
  versus NADH" names what the inhibitor competes with; it is not a Ki of
  NADH, and `--inhibitor NADH` is refused.

The report gives the band's width before any verdict, because a computed
value cannot be judged more finely than the literature disagrees with
itself. `--computed` (kcal/mol, or `--unit kj`) is judged at 2σ: **agrees**
(exit 0) or **disagrees** (exit 4), with the gap in kcal/mol and as a
fold error in Ki. Agreement with a single publication is reported as
consistency, not validation. Tagged or immobilised constructs, and the
molecule each Ki was measured against, travel as caveats.

### `caterva bind --survey`: which Ki values can judge a method

```bash
caterva bind --ec 1.1.1.27 --organism human --survey
```

Before a force field or a free-energy protocol is validated against an
enzyme's published Ki values, it is worth knowing whether those values can
judge it. The survey builds the target for every inhibitor BRENDA records,
one per compound, species and isoform (never pooled), and calls one a
benchmark only with at least two publications, a stated inhibition mode
and a stated assay temperature. On the recorded human LDH page the answer
is none: every Ki comes from a single paper, and gossypol's rows state
neither mode nor temperature. `--organism ""` surveys every species.

### `caterva complex`: the ligand where the crystal put it

```bash
caterva complex --pdb 181L --ligand BNZ --ligand-itp bnz.itp --ligand-coords bnz.gro --out t4l
```

`caterva fep` starts from an equilibrated complex; this builds one from a
PDB entry and the two files your parameterisation tool wrote (the .itp and
its coordinates). Your ligand is superposed onto the entry's own copy by
the heavy-atom names they share (Kabsch 1976), carrying its hydrogens, and
the fit is printed. It refuses, and says which atoms, when fewer than
three names are shared or the fit is worse than 1 Å (a different
conformer). It also refuses a ligand whose handedness differs from the
crystal's: writing its tests showed that the mirror image of a small
ligand can superpose within 1 Å, so an inverted stereocentre is checked
directly, from the sign of the volume of every compact group of four
heavy atoms. `build.sh` then runs pdb2gmx, inserts the ligand into the
topology after the force field, solvates, neutralises, minimises and
equilibrates (NVT, NPT, protein restrained) with the same settings as
`caterva md`. Waters and every other HETATM are dropped, and listed.

On 181L, an ideal benzene built elsewhere and rotated at random fits the
crystal's at 0.026 Å.

After `build.sh`, `caterva complex --check t4l --ligand BNZ` says whether
the ligand kept its crystal pose through equilibration: the protein's
C-alpha atoms are superposed on the start, and the ligand's heavy atoms
are compared (exit 4 when they moved more than 2 Å), counting the
molecule's symmetric poses as one. Its graph symmetries are found from the
.itp's bonds (benzene has twelve). On 181L the benzene read 2.70 Å by atom
name and 0.77 Å counting symmetry, with its centroid 0.29 Å from where it
started: it had turned in its cavity, not left it. A ligand that
wandered off during 200 ps of equilibration would take the Boresch
restraints `caterva fep` chooses with it, so this is checked before the
compute is spent. When `npt.xtc` is there, every frame is checked, not
only the last: on 181L the benzene stayed within 0.29-0.91 Å of the
crystal pose over all 11 frames, centroid within 0.62 Å.

Trajectories are read by Caterva itself (`caterva/md/xtc.py`), a direct
implementation of GROMACS's compressed-coordinate decoder: on the real
181L equilibration, every coordinate of every frame (11 x 33,327 atoms)
equals what `gmx trjconv` writes, and C-alpha RMSF computed from it
agrees with `gmx rmsf` to 0.0002 nm on average. Given the equilibration
(`caterva fep --trajectory npt.xtc`), restraint anchors are chosen only
among C-alpha atoms that fluctuate less than 1 Å, and their RMSF is
recorded in PROVENANCE.md. (On 181L the anchors picked by geometry alone
were already still, 0.12-0.14 Å; that equilibration restrained the
protein, so an unrestrained trajectory is the test that matters.)

### `caterva fep`: a binding free energy that knows what it must reproduce

```bash
caterva fep --ec 1.1.1.27 --organism human --inhibitor gossypol --isoform LDH-A --complex complex.gro --topology topol.top --ligand GSP --ligand-itp gossypol.itp --out ldha-gossypol
caterva fep --summarise ldha-gossypol
```

The target is the band `caterva bind` builds from the same Ki rows, with
the same `--state` and `--isoform` choices, and the calculation runs at
those rows' assay temperature when they agree on one (310.15 K for the
quinoline sulfonamide's 37 °C rows); otherwise at a labelled 25 °C.

It writes both legs of a double-decoupling calculation: the ligand's
charges, then its van der Waals interactions, switched off bound and in
water, 34 and 25 λ windows. In the complex the ligand is held by six
Boresch restraints on C-alpha atoms chosen so that no angle nears 0° or
180°, the choice that keeps their analytic standard-state correction
finite; the correction is computed at the run's temperature and printed.
Each window of each replica gets its own stochastic-dynamics seed, and
every setting is in `PROVENANCE.md` with its origin and, for methods,
its DOI.

You supply two things, and neither is invented: an equilibrated,
solvated complex, and the ligand's topology (ACPYPE/GAFF, CGenFF, OpenFF).
`run.sh` builds the solvent leg from the ligand's pose in the complex,
runs every window (`ONLY=leg:rep:lambda` runs one, for a cluster), and
integrates each leg with `gmx bar`. `--summarise` closes the cycle per
replica, ΔG°bind = ΔG_solvent + ΔG_restraints_on − ΔG_complex, reports
the mean ± the larger of the SEM and the propagated BAR error, and judges
it at 2σ (exit 0 agrees, 4 disagrees). Fewer than two finished replicas
is not a result.

The legs are integrated by Caterva's own estimators
(`caterva/fep/estimators.py`), not by `gmx bar` alone: per window,
equilibration is detected (Chodera 2016) and the samples are thinned to
independent ones at the statistical inefficiency (Chodera et al. 2007);
MBAR (Shirts & Chodera 2008) then uses every sample at every state, with
BAR over neighbours beside it. The report gives the smallest overlap
between neighbouring states, whether the first and second halves of the
data agree, and whether MBAR and BAR agree, and says which fails. Their
tests are harmonic oscillators, whose free energies are known exactly:
the estimates recover them, and the 2σ error bars cover the exact answer
about 95% of the time over hundreds of datasets. That test caught a wrong
BAR variance (69% coverage) and a statistical inefficiency that read 3.5
for a process whose exact value is 3.0, both fixed.

On real GROMACS output (the solvent leg for benzene, 25 windows, 50 ps
each), Caterva's BAR on the same samples as `gmx bar` reproduces every
one of its 24 neighbour free energies to within 0.005 kJ/mol, and its
total exactly (-1.31 kJ/mol). With equilibration removed and the samples
thinned to independent ones (3,107 of 6,275), MBAR gives -0.33 +/- 0.83
and BAR -0.17 +/- 0.66: the same answer, with an error bar that counts
independent samples rather than all of them. Those files are kept as a
test (`caterva/tests/fixtures/fep/`). Thermodynamic integration (Kirkwood
1935) on the same windows' dH/dλ gives -0.05 +/- 0.97: three estimators,
one answer. When TI parts from MBAR, <dH/dλ> is too curved between
windows for the trapezoid rule, and the report says so.

```bash
caterva fep --optimise ldha-gossypol --leg solvent --rep 1
```

`--optimise` reads a finished pilot leg and says where its windows should
go. It measures each step's thermodynamic length (Shenfeld et al. 2009:
the spread, in kT, of the energy gap between neighbouring states) and
places the same number of windows at equal length along the same path,
and says how many are needed to keep every step under 1 kT. On the
benzene solvent leg the 25 windows' steps ran from 0.21 to 0.91 kT, and
15 windows would keep every step under 1 kT: about 40% less compute.

It has been run end to end on T4 lysozyme L99A with benzene (PDB 181L),
GROMACS 2026.1: 118 windows over two replicas and both legs, BAR, the
correction and the verdict, with every stage cut to 0.5 ps to test the
machinery, not the answer. At that length the complex leg is nowhere near
converged, and the verdict said so by disagreeing. The solvent leg already
brackets what benzene's measured hydration free energy implies (3.05 and
5.99 ± 1.5-2.4 kJ/mol against +3.6). That first run is also where grompp
pointed out that one stochastic-dynamics seed reused across windows
correlates their noise; each window and stage now has its own.

## Exact stochastic kinetics: `caterva sim ssa`

When the molecule counts are small enough that a smooth curve hides what
matters, `caterva sim ssa` runs the exact Gillespie algorithm and prints the
closed-form expectation next to the one trajectory it drew:

```bash
caterva sim ssa --a0 200 --k 0.5 --end 4 --seed 42
```

```
A(0) = 200   events = 174   final A = 26
expected B(end) = a0*(1-e^(-k*end)) = 172.9
```

`--bimolecular` switches to A + B → C, and `--out` writes the table to CSV.
The same seed gives the same trajectory, bit for bit.

Population genetics, epidemiology, PCR and the other domains Caterva used to
carry were archived on 2026-09-27; v0.4.0 still runs them (see
`archive/legacy_domains/README.md`).

---

## Real constants, with real citations

**This is what Caterva is for.** It needs the source checkout, not the app
folder: the resolvers that read BRENDA are not shipped in the download.

**Getting the checkout, once** (about five minutes, most of it downloading
dependencies). Put it somewhere iCloud does not sync — *not* under
`~/Desktop` or `~/Documents` on a Mac with iCloud Drive, which silently
breaks the `caterva` command (`make doctor` detects this and says so):

```bash
mkdir -p ~/Code && cd ~/Code
git clone https://github.com/math12345678/caterva.git
cd caterva
make setup
source .venv/bin/activate
```

From then on, in a new terminal: `cd ~/Code/caterva && source
.venv/bin/activate`, and `caterva` works. Then, one command:

```bash
make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"
```

```
| parameter | value     | origin     | source            |
|-----------|-----------|------------|-------------------|
| km        | 0.03 mM   | literature | BRENDA ref 286469 |
| s0        | 10 mM     | **yours**  | chosen for this run |
| vmax      | 0.25 mM/s | **yours**  | chosen for this run |
```

That is a live BRENDA lookup: a measured Km, the reference that measured
it, and — under it — a section naming the papers that disagree and what the
disagreement does to your answer. The same command, for human
acetylcholinesterase, returns `km = 0.0714 mM` from BRENDA ref 713996,
tells you it was measured at **pH 7.4, 37 °C, in 0.1 M MOPS buffer**, and
reports `kcat` as **not sourced** rather than filling it in.

More than one quantity, or the full flag set:

```bash
python3 scripts/cite.py --ec 3.1.1.7 --organism "Homo sapiens" \
    --substrate acetylcholine --quantity km --quantity kcat
```

**A name is not an enzyme.** `--enzyme "lactate dehydrogenase"` is refused,
naming all six EC numbers it could mean, because a wrong EC number is a
citation for the wrong protein rather than merely a wrong value. Ask
UniProt, pick one, pass `--ec`.

**No network, no account:** `--fixture Tests/fixtures/brenda_ldh_fixture.html`
reads a saved page, and the document then says no search was run. `make
demo` is that path end to end.

### A model whose constants are sourced

`compose` searches too. Give it the enzyme, the organism and the substrate
a Km belongs to:

```bash
caterva compose "Michaelis-Menten with a competitive inhibitor" \
    --subject 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate
```

and "Where the numbers come from" is no longer a list of things to measure:

```
**2 of 3 constant(s) came from the literature**, searched for `1.1.1.27`
in Homo sapiens, substrate pyruvate.

| quantity        | value      | origin                    | source            |
|-----------------|------------|---------------------------|-------------------|
| `reaction_Ki`   | 0.00059 mM | literature (Homo sapiens) | BRENDA ref 739793 |
| `reaction_Km`   | 0.03 mM    | literature (Homo sapiens) | BRENDA ref 286469 |
| `reaction_kcat` | 100.0 1/s  | **placeholder**           | searched the kcat table and found nothing |
```

Every section below it — stability, the influence ranking, the time course,
the verdict — then runs on those numbers rather than the library's. The
exports carry them too, so an SBML file and the report beside it cannot
disagree about what was measured.

**And it tells you what the evidence did not settle.** Where more than one
row was ranked equal, the report says so rather than presenting the
resolver's pick as the answer:

```
### Where the evidence did not settle on one value

- `reaction_Km`: 2 sources report 2 values (BRENDA ref 286442, 286469),
  spanning **0.03 to 0.398 mM** (13.3-fold). The model carries 0.03 — the
  resolver's pick, not a verdict; which one is right is a question about
  the papers.
```

A 13-fold spread on the constant your conclusion rests on is the most
important thing on the page, and a citation beside a single number hides
it. Note that it distinguishes *two papers disagreeing* from *one paper
reporting two rows* — the second is usually different conditions or a
different substrate, and sending you to one paper to adjudicate itself
would be nonsense.

**And the conditions each value was measured under**, because pH,
temperature and buffer decide whether two constants may be put in one model
at all:

```
### The conditions these were measured under

- `reaction_Ki` — measured at pH 7.5, 37 °C.
- `reaction_Km` — the source stated no conditions. That is a fact about the
  paper, not a gap in the search, and it cannot be assumed to match the
  rows above.
```

When two constants *do* state conditions, the report compares them and
says whether they can be mixed, against this project's own thresholds
(1 pH unit, 10 °C — a Q10 of 2-3 makes ten degrees roughly a factor of two
in rate). If they clash it says so: *a model built from them describes an
experiment nobody ran.*

**Read the placeholder rows especially.** They say what the search
actually met, which is very often not "nothing":

```
| `reaction_kcat` | 100.0 1/s | **placeholder** | no value in the organism
  requested; measurements exist in other organisms, and one is never
  substituted for yours (ADR 0024) -- re-run with --organism set to one of
  them to build the model there -- available in: Cimex lectularius, Drosophila
  melanogaster, Macroptilium atropurpureum, Mus musculus |

| `reaction_Ki`   | 0.5 mM    | **placeholder** | no database value;
  candidate papers were found but a number was not extracted from free text |
```

Four different outcomes, four different next actions: the value exists in
another species and you can decide to accept it; it exists only in distant
ones; papers exist and nobody extracted the number, so go and read them; or
there is genuinely nothing. Only the last means stop looking.

A partial result is the normal case: BRENDA has a Km for
acetylcholinesterase and no kcat. The constants the search did not
find keep the library's placeholder and are listed as such, with the
distinction that matters — *searched and not found* is not *not looked
for*. Any conclusion resting on one of them is a statement about the motif
library, and the report says so.

**Three things it will refuse**, each for the same reason:

- `--subject "lactate dehydrogenase"` without an EC number, if the name
  means more than one enzyme. It names all six.
- A search with no `--substrate` when the model needs a Km or Ki. Those
  BRENDA tables are per-substrate, and a motif knows it needs a Km but not
  what the Km is *for*.
- Running at all from the app folder rather than the checkout: the
  resolvers live in `Tests/`, which the wheel does not ship. It says so
  rather than failing obscurely.

None of those costs you the report. The structure, the invariants, the
dimensions and the behaviour are true regardless, and the refusal arrives
as a note on the document rather than an error instead of it.

That prints a document with real BRENDA values, and — this is the part worth
showing students — a section on **what the literature disagrees about**:

> The evidence ranked 2 values of km equal: 0.03 to 0.398. Running the model
> at each — and at no other value, since no other value was measured — the
> substrate remaining at t=10 ranges from 7.509 to 7.609. A factor of 1.01.
> This is the disagreement among the sources carried through the model. It is
> NOT an uncertainty estimate: the spread is bounded by which papers happen
> to be in BRENDA, not by any statement about the true value.

**Putting your own numbers in** today means exporting to SBML or Antimony,
editing the constants, and simulating from there — or, from the checkout,
driving `scripts/report_lab.py` with a JSON payload that names the enzyme,
organism and the values you supply. A friendlier path for supplying your own
constants directly to `compose` is not built yet; that is a real gap and it is
recorded as one rather than papered over.

---

## What it refuses to do

These are decisions, not gaps, and each refusal says why:

- **Name a pathway** (`glycolysis`, `the TCA cycle`) — needs a pathway
  database; guessing would be worse than refusing.
- **Invent a constant** — an unmeasured constant is labelled a placeholder
  everywhere it appears, including in the exports.
- **Average its checks into a score** — the worst finding sets the verdict
  and is named.
- **Call a check it could not run a pass** — "could not check" and "checked
  and fine" are different facts, and the report keeps them apart.
- **Claim a simulation was verified when nothing verified it** — if a model
  has no conservation law, the time course says so: *"there is no independent
  check on the integration here."*

If you find Caterva doing any of these, that is a bug worth reporting.

---

## When something goes wrong

| what you see | what it means |
|---|---|
| `Not built.` + a list of shapes | You named a subject, not a mechanism. Describe the mechanism, or pick from `--shapes`. |
| `Not built.` + "is a named pathway" | Needs a pathway database Caterva does not read. Describe the steps you want. |
| `Not exported.` | The export refused and the reason is printed above it. The report still ran. |
| Exit code 3 | Something refused and said why; the rest of the report is still there and still valid. A **refused literature search** is one of these: an enzyme name that means more than one enzyme, or a model needing a Km with no `--substrate`. A search that ran and found nothing is *not* a refusal — it produced its answer, and the provenance table states it per constant. |
| Exit code 2 | The question was not well formed. |
| macOS: "cannot be opened because the developer cannot be verified" | The folder is unsigned. `xattr -dr com.apple.quarantine .` inside the folder. "Open Anyway" in System Settings clears one file, not the libraries, so it will not work. |
| Windows: "Windows protected your PC" | SmartScreen. More info > Run anyway. Run `.\caterva.exe` from a terminal. |
| `caterva.exe is not recognized` in PowerShell | PowerShell needs the prefix: `.\caterva.exe`. |

Exit codes are stable enough to script against: `0` produced everything,
`2` the question was malformed, `3` something refused and said why, `1` a
crash.

---

## Where to go next

- `caterva compose --help` — every option, with examples.
- [`docs/releases/v0.3.0.md`](releases/v0.3.0.md) — what the current release
  contains and, more importantly, what it does not.
- [`README.md`](../README.md) — the project's own account of why it exists.
- [`docs/adr/`](adr/README.md) — why each design decision was made, including
  the ones that were reversed.
