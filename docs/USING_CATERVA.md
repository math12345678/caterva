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

## The same thing in a window: Caterva Studio

`caterva studio` starts a small server on this computer (127.0.0.1 only)
and opens a page in your browser. On macOS, Caterva.app opens the same page
in its own window and stops the server when you quit. The page runs the
same library functions as the commands in this guide, so a number on screen
is the number the command prints, and keeps every run so you can reopen or
export it later.

```bash
caterva studio                      # opens your browser
caterva studio --no-browser --port 8765 --data-dir ~/caterva-runs
caterva studio --self-test          # starts, checks itself over a socket, exits 0 or 1
```

**Where the page comes from.** The page is built from the repository's
`Science-Agent-Pipeline/artifacts/caterva-studio` and is not in the wheel or
in the plain app folder from the Releases page: there `caterva studio`
starts, answers its API, and serves a short "the page is not built" page
saying how to build it. You get the page in one of two ways: the macOS app
from the DMG (Apple silicon, macOS 14 or later) carries it, and in a
checkout `make studio-page` builds it (Node 22 and pnpm needed) and `make
studio` builds it and opens it. The Rates screen takes a table of your own initial rates
to a figure and a methods paragraph; `caterva rates` is the same fit in the
terminal, below.

What you will see:

- **Every number wears a mark.** A solid dot is a cited measurement; click
  it for the paper, the organism, the assay conditions and the source
  row's own words. A ring is a fitted value, a small square a value Caterva
  computed, and a hollow dashed dot a placeholder, with the reason it is
  one. Values you chose, and defaults a command states, say so.
- **Home** starts a model from one written line, the same line you would
  give `caterva compose`.
- **Compose** puts the verdict and the worst thing wrong with the model
  first, then a table of where every constant came from.
- **History** keeps every run. Reopen one with its question back in the
  form, copy its link, or export it as a zip holding its files, the
  command that reproduces it in a terminal, and a README.
- **Settings** has the theme (light paper by default, a dark theme for the
  evening, or follow the system), offline mode, and the GROMACS program to
  use.

Runs and settings are kept in `~/Library/Application Support/Caterva` on
macOS (`~/.local/share/caterva` on Linux, `%APPDATA%\Caterva` on Windows)
unless you pass `--data-dir`. The macOS app is not signed with an Apple
Developer ID and is not notarised; the first time, try to open it, then use
System Settings, Privacy & Security, Open Anyway, and if macOS keeps
refusing run `xattr -dr com.apple.quarantine /Applications/Caterva.app`.
From 0.5.1 the app also offers new versions itself (Caterva menu, Check for
Updates; Settings, Updates has the switches): the first copy with the updater
is installed by hand, and later versions arrive in the app. Updates replace
only the app; the runs and settings above stay.
[docs/studio/README.md](studio/README.md)
says what each screen runs and how the app is built, and
[docs/studio/USING_STUDIO.md](studio/USING_STUDIO.md) lists every flag.

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
protein's value. The names compare without case, spaces or hyphens ("MAO B",
"MAO-B" and "MAOB" are one isoform), and are read by the same parser
`caterva bind --isoform` uses, which reads the ways BRENDA writes them:
"LDH-A", "isoform MAO B", "monoamine oxidase B", "HK I", "hexokinase II".
What you ask for is read the same way, and a code alone is that code after
the enzyme's abbreviation: for potato hexokinase, whose rows write "HK2" and
"hexokinase 2", `--isoform 2`, `HK2`, `HK-2` and `"hexokinase 2"` all ask for
those rows, and `--isoform B` on monoamine oxidase asks for MAO-B. Two
numberings of one protein are taken as one only where UniProtKB itself names
one protein both ways, for human, mouse, yeast and E. coli K-12 proteins that
share an EC number with others: `HK2`, `HXK2`, `HK II` and `"hexokinase type
II"` are human hexokinase 2, so `--isoform HK2` takes the row that says
"hexokinase II" (on the recorded page of EC 2.7.1.1, Km 0.37 mM, BRENDA 702867,
not 6.0 mM from a row that names no isozyme), and `GCK`, `HK-IV` and
`glucokinase` are one protein. The report says what a label was read as ("read
as HK2, human protein HXK2_HUMAN (UniProt P52789); a row is taken as measuring
it when its commentary names it as any of: ...") or that it matched no protein
and is compared as spelled. A refusal names the isoforms BRENDA holds, spelled
as it will match them.

`--isoform` takes a row that names the isozyme; it does not make a constant
belong to it. Where no row names it, the constant comes from a row that names
none and the report says whether it measured the isozyme is unknown; and the
isozyme notice below stays, naming that constant, until every cited constant's
own row states the isozyme.

### When one EC number is several human proteins

`--subject 2.7.1.1 --organism human` is hexokinase, and the nomenclature lists
five human proteins under that one number (HKDC1, HK1, HK2, HK3, GCK, by gene
symbol; UniProt files them as HKDC1_HUMAN and HXK1 to HXK4, which are labels,
not the symbols a paper uses).
BRENDA files their measurements under the one number too, and the resolver
ranks rows, not proteins. A search that names no `--isoform` can therefore
return a Km from one isozyme and a kcat from another, and say GROUNDED. So
the report says it:

```
Qualified: EC 2.7.1.1 is 5 proteins in human and no --isoform was given, so the constants may belong to any of them.

1 concern(s), worst first:
  - [isozymes] EC 2.7.1.1 has 5 human isozymes in the enzyme nomenclature's UniProt entries (HKDC1, HK1, HK2, HK3, GCK) and no --isoform was given, so the cited constants may belong to any of them; isozymes of one enzyme can differ many-fold in Km and kcat -- pass --isoform with one of these names (for example --isoform HKDC1) to take each constant from a row whose commentary names that isozyme; a constant whose rows name none is kept and flagged, and one whose rows all name another isozyme is refused
```

The verdict is still GROUNDED: every constant is measured and cited. The
notice says what that does not tell you. It appears when the organism has two
or more proteins for the EC number and `--isoform` is not given, and also when
it is given and a cited constant's own row does not state it ("HK2 was asked
for, but the row for `reaction_kcat` does not state which isozyme of EC 2.7.1.1
it measured"); it goes quiet only when every cited constant's row states the
isozyme. It does not read isozymes out of BRENDA's reference titles and it does
not change a constant. Above 12 proteins an EC number is not isozymes of one
enzyme but a broad class ("245 different human proteins share EC 2.7.11.1"),
and the notice says that and lists none. The nomenclature files a protein under
the EC numbers of its activities, so a list can leave one out: human ADH1B and
ADH4 are filed under EC 1.1.1.105, not under EC 1.1.1.1, and the notice for
EC 1.1.1.1 says so. `E. coli` means the K-12 strain (UniProt code `ECOLI`); an
EC number whose E. coli proteins are all in another strain lists none for it,
and says which strain it counted.

### A Ki from a row of the model's own inhibition mode

```bash
caterva compose "Michaelis-Menten with a noncompetitive inhibitor" \
    --subject 1.1.1.27 --organism human --substrate pyruvate \
    --inhibitor "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
```

BRENDA 739793 gives two Ki values for this inhibitor and human LDH, from
one paper under one set of conditions: 0.00059 mM, "competitive versus
NADH", and 0.00252 mM, "noncompetitive versus pyruvate". They are constants
of two mechanisms. The resolver grades rows on their evidence, gives these
two the same grades, and returns the first, so until 2026-09-29 this
noncompetitive model carried the competitive constant and only the report
said it was the wrong one.

An inhibition constant now comes from a row whose stated mode is the
model's (a mixed row counts for noncompetitive), preferring a row measured
against the model's substrate, then one naming nothing it was measured
against, then one measured against another molecule. Failing that it comes
from a row stating no mode, and the report says whether it is this model's
constant is unknown. A Ki BRENDA holds only for other modes is refused: it
stays a labelled placeholder, and the reason names each row's mode. The run
above carries 0.00252 mM. The report says which row it replaced and why,
and every export says why the carried row was carried, in its sentence
about the spread of values. The competitive model keeps 0.00059 mM, and its
report still says that row was measured against NADH. It also says more: the
other row found this inhibitor noncompetitive against pyruvate, the
competitive model's own substrate, which is evidence that a competitive
model of this inhibitor and substrate is the wrong mechanism, and no choice
of row can fix that. A row of the model's mode measured against another
molecule is still preferred to a row stating no mode, because it names the
mechanism the model uses and its report says what it was measured against;
it is not known to be the constant against the model's substrate. The
gossypol example is unchanged: none of its rows states a mode, so the
resolver's pick stays and the report says the mode is unknown.

```bash
caterva compose "Michaelis-Menten with a noncompetitive inhibitor" \
    --subject 2.7.1.1 --organism "Oryctolagus cuniculus" --substrate glucose \
    --inhibitor MgADP-
```

Both of rabbit hexokinase's MgADP- rows (BRENDA 640206) state mixed
inhibition, one versus MgATP2- (3 mM, the resolver's pick) and one versus
glucose (7.8 mM). A model with glucose as its substrate carries 7.8 mM.

With `--isoform`, the isoform is chosen first and the mode second, and the
mode step is told the isoform, so it never moves a constant onto another
isoform's row. For human monoamine oxidase and benzylhydrazine (BRENDA
702238), `--isoform MAO-A` alone takes MAO-A's first ranked row, 1.95 mM; a
competitive model then moves to MAO-A's 2.096 mM row, "determined from
competitive inhibition data". Choosing the mode first would keep MAO-B's
competitive 0.026 mM, and the isoform step, which does not read modes,
would then take 1.95 mM; a mode step not told the isoform would move 1.95 mM
to MAO-B's 0.026 mM. Within the choice, a row naming the isoform you asked
for beats a row naming none, whatever either says about mode.

The 1.95 mM row was "determined from Kitz-Wilson plots". That is not a
reversible Ki: it is the K_I of an irreversible inactivation (the paper,
Binda et al. 2008, shows these hydrazines alkylate the enzyme's flavin).
BRENDA files it in the Ki table and states no mode, so it is ranked after
every other row stating no mode. When one is carried the report says what
it is, and when the choice moved to one, so does the reason every export
prints for it. It is not refused, because the alternative is a placeholder
that says less than the row does. Only the words "Kitz-Wilson" are
recognised.

A row in another unit is never substituted, because the constant keeps the
resolver's unit. When one states the model's mode and the row carried
states none, the report says it was passed over and why.

`--any-mode` turns the choice off and keeps the resolver's pick whatever
mode it states. The report still flags a mismatch, and says which row the
default would have used, or that it would have refused the constant.

The API's competitive-inhibition model and the TypeScript CLI's
`scientific resolve --quantity ki --mode competitive|uncompetitive|noncompetitive`
choose with the same ranking, one function in `caterva/compose/ki_mode.py`.
They apply it in the literature layer, before a row is chosen, to every row
the isoform and variant steps kept, and so, since 2026-09-30, does
`caterva compose`: it sends each constant's isoform, mode and substrate to
the same resolver and carries the row it returns, so the three front ends
carry one row for one model. Before then compose applied the ranking after
the resolver, to the best-evidenced rows it returned, and that could differ.
Trypanosoma cruzi hexokinase has four Ki rows for ADP: 0.13 mM, 1.3 mM ("at
pH 7.5"), 1.5 mM ("competitive to ATP") and 7.0 mM ("noncompetitive to
glucose"). The evidence alone keeps 1.3 mM, the one row reporting a pH,
which states no mode; a competitive model now carries 1.5 mM in compose as
in the API, and the report says it replaced 1.3 mM and why. A Ki every row
of which states another mode is refused there too, with the modes named.
The API always sends its model's mode. The CLI has no `--any-mode`: leaving
`--mode` out keeps the resolver's pick, with its stated mode printed beside
it.

`--any-mode` asks the resolver the question the CLI asks with no `--mode`,
and carries its answer: 1.3 mM for Trypanosoma cruzi and ADP, the row the
CLI returns. It also sends the model's mode as one to compare with, and the
resolver, from the same rows and without fetching the page again, says what
it would have returned asked for it. The report names that row and why the
two differ: "--any-mode kept the resolver's pick (1.3 mM, BRENDA ref
640265), which states no inhibition mode; without it the row stating
competitive inhibition versus ATP (1.5 mM, BRENDA ref 640216), this model's
mechanism though not its substrate (glucose), would be used". Until
2026-09-30 `--any-mode` worked out the default's row from the rows its
answer held, which lack 1.5 mM, so it said nothing there. The value and
reference carried are the no-mode answer's. The rows printed beside it are
not quite: the default's row is added to the carried constant's
alternatives, so the spread is 1.3 to 1.5 mM either way, where the no-mode
answer's own candidates hold 1.3 mM alone.

"Competitive to ATP" is read as measured versus ATP. Until 2026-10-01 the
row reader took only "versus", "vs." and "with respect to", so this row
read as measured against nothing and was carried for a glucose model with
no remark; the 7 mM row, "noncompetitive to glucose", is now also read as
measured versus glucose, and the API and the CLI return it as
`mechanismEvidence` against a competitive model of glucose. Compose's report
says the 1.5 mM row was measured versus ATP, not glucose, but does not name
the 7 mM row: the resolver's answer does not give compose that row.

The API sends its model's substrate with the mode; the CLI takes it as
`--model-substrate`, because `--substrate` names the inhibitor for a Ki.
Without it a row measured versus the model's substrate and one measured
versus another molecule rank alike, as they do in `caterva compose` without
`--substrate`: rabbit hexokinase's two mixed MgADP- rows (BRENDA ref 640206)
give a noncompetitive model 7.8 mM "versus glucose" with `--model-substrate
glucose`, and 3.0 mM "versus MgATP2-", the lower, without it.

With the mode and the model's substrate, both also say what `caterva
compose`'s report says when a row is evidence against the model's
mechanism: a row stating another mode, measured versus the model's
substrate, while the row returned does not state the model's mode versus
it. For human LDH and the quinoline sulfonamide of BRENDA ref 739793, a
competitive pyruvate model gets 0.00059 mM "competitive versus NADH", the
only competitive row, and the API's `provenance.flags` and `scientific
resolve` both name 0.00252 mM "noncompetitive versus pyruvate": measured
against pyruvate the inhibitor is not competitive, and no choice of row
fixes that. The runner sends the row as `mechanismEvidence`, found by the
function in `ki_mode.py` that compose's note comes from. A row saying
"versus X", "vs. X", "with respect to X" or "<mode> to X" is read as
measured against X, so for a competitive model of glucose the Trypanosoma
cruzi ADP row 7 mM "noncompetitive to glucose" is sent as
`mechanismEvidence` against the 1.5 mM "competitive to ATP" row returned.

`scientific simulate --resolve --model competitive|noncompetitive|product`
looks its Ki up the same way, and needs `--inhibitor NAME` to do it. Until
2026-09-30 it looked the Ki up under `--substrate`, with no mode, so an
inhibition model of LDH on pyruvate asked BRENDA for a Ki "of" pyruvate.
Without `--inhibitor`, and without a `--ki` of your own, the run now refuses
and names the flag. The lookup sends the inhibitor as the compound, the
model's mode, and `--substrate` as the model's substrate:

```bash
scientific simulate mm --resolve --model noncompetitive \
    --ec 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate \
    --inhibitor "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid" \
    --km 0.1mM --vmax 0.01mM/s --s0 10mM --i0 0.001mM
```

Run against BRENDA on 2026-09-30, this carries Ki 0.00252 mM (BRENDA ref
739793) and prints what its row measured: noncompetitive inhibition versus
pyruvate. The Km and Vmax above are typed, so the Ki is the only lookup.

A competitive model asks for competitive rows. The noncompetitive and the
product model both ask for noncompetitive rows (a mixed row counts). That is
not the mode `caterva compose` gives product inhibition, and deliberately:
compose's product motif is the product competing for the free enzyme,
`Km(1 + P/Kp) + S` in the denominator, so its Ki is competitive. This
command's product model integrates `Vmax·S / ((Km + S)(1 + P/Kp))`, which is
the noncompetitive rate law with the product as the inhibitor. A Ki is asked
for by the equation it goes into, not by the model's name. For
`--model product`, `--inhibitor` is the reaction's own product. There is no
uncompetitive model in `simulate`.

A Ki every row of which states another mode is refused. The refusal names
the modes BRENDA holds and the `--model` that would take one, since
`simulate` has no `--mode`; a refused `--model product` is offered no other
model, because a competitive or noncompetitive model holds the inhibitor at a
fixed `--i0` rather than letting the product accumulate. `--isoform` works as
on `resolve`, and applies to the Km, the kcat and the Ki alike: a model of
LDH-A is a model of one protein. `--allow-cross-species`, listed in
`simulate`'s help since 2026-08-18 and suggested by every one of its
literature refusals, reached none of its lookups until the same day; it now
reaches all three. With a `--ki` of your own nothing is looked up, and
`--inhibitor` names whose constant it is.

A successful inhibition run under `--json` prints one document (the
provenance, with the Ki's `inhibitor`, `askedMode` and `rowScope`, and the
result), as the Michaelis-Menten run does; until 2026-09-30 it printed
the human table instead. `--export-citations` is written, and a Ki's entry
names its inhibitor. `--export-model` is not written for an inhibition model,
and the run says why: the model exporter builds plain Michaelis-Menten and
competitive inhibition only, and its competitive model names the inhibitor
concentration `i` where this command has `i0`.

The catalogue entry `scientific domains` prints for competitive inhibition
runs end to end:

```bash
scientific simulate mm --resolve --model competitive --ec 1.1.1.27 \
    --substrate pyruvate --organism "Homo sapiens" --inhibitor gossypol \
    --isoform LDH-A --s0 10mM --i0 1mM --enzyme-conc 0.001mM --allow-cross-species
```

Run against BRENDA on 2026-09-30 it used Km 0.03 mM (ref 286469, a row
naming no isoform), Vmax from rabbit's kcat (ref 741355, marked as measured
in another organism: BRENDA holds no human LDH kcat) and gossypol's LDH-A Ki
of 0.0019 mM (ref 711801, which states no mode, and the run says so).

A model you write yourself (`POST /api/simulate/model`) declares a Ki the same
way, in its annotation:

```
// caterva: ki ec="2.7.1.1" organism="Oryctolagus cuniculus" inhibitor="MgADP-" inhibition="noncompetitive" substrate="glucose" unit="mM" resolve
Ki_adp = ?;
```

`inhibitor=` is the compound the Ki is looked up under. `inhibition=` is the
mechanism of your rate law (`competitive`, `noncompetitive` or
`uncompetitive`), and is optional: without it the resolver's pick is used,
and the note says what mode that row states. On a `ki` annotation,
`substrate=` names the model's substrate, the one the Ki should have been
measured against, and is read only with `inhibition=`: the resolver ranks Ki
rows by what they were measured versus only when it chooses by mechanism, so
`substrate=` beside `inhibitor=` with no `inhibition=` is refused rather than
ignored (as `scientific resolve` refuses `--model-substrate` without
`--mode`). A `ki` annotation with no `inhibitor=` is not looked up at all,
and in `resolve` mode the run refuses. `inhibitor=` and `inhibition=`
are refused on a `km` or `kcat`. On the recorded rabbit hexokinase page the
annotation above fills 7.8 mM (BRENDA ref 640206, mixed inhibition versus
glucose). With `inhibition="competitive"` it refuses and names both mixed
rows.

### `caterva structure`: which structures exist, and which protein each is

```bash
caterva structure --subject 1.1.1.27 --organism human
```

`--subject` takes an EC number or an enzyme name; a name is read by the same
function `compose` uses (see `caterva enzyme` above), so a name that is
several enzymes is refused with each one named. EC 1.1.1.27 in human is five
proteins (LDHA, LDHB, LDHC and two LDHAL6),
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

It measures the angles between catalytic groups. Where two groups are both
within 0.6 nm of a third in the crystal (functional-group centres), the
angle between them at the third is read in every frame, between the same
centres the distances use, each arm to its nearest periodic image. 0.6 nm
is as far apart as two groups can be and still have two atoms within a
hydrogen bond or salt bridge (0.35 nm), given the 0.10-0.14 nm from each
group's centre to its atoms, measured on 1AKI; groups within it need not
be bonded. An angle is fixed, frame by frame, by three distances already
in the report (the sides of its triangle), so it adds no information about
where the groups are: it states the triangle as its shape at one group,
with a verdict of its own. It cannot tell which side of a group a partner
is on, since a partner that turns about the line through the other two
keeps its angle; the next measurement does. Each angle is reported as a
distance is: its crystal value, each replica's mean, the change, and held
or moved (more than 15 degrees, the
turn that moves a group 0.4 nm from the vertex by about the 0.1 nm
distance threshold) only when the replicas agree. An angle that is not yet
a result makes the exit code 4, as a distance does, but the other
sections' verdicts (hydrogen bonds, rotamers, water, flexibility) are
judged by the distances alone. Lysozyme's six catalytic residues give 24
angles, among five of them (Glu35 has no partner within 0.6 nm). On 21
frames of a lysozyme replica every one equals `gmx gangle -g1 angle`'s to
0.001 degree, the precision it prints, both as the run stored the frames
and with the frames translated so that the active site straddles the
periodic box; both comparisons are tests. The GROMACS route runs
`gmx gangle`, and CI compares the two routes' angle tables.

For each of those angles it also says which face of the vertex the two
partners are on: seen from the vertex residue's own Cα, does the first run
clockwise or anticlockwise to the second about the vertex? No angle or
distance can see this, since a partner that turns about the line through
the other two keeps them all. It is measured as the elevation of the arm
from the vertex's functional-group centre to its Cα out of the plane of the
angle, signed as the dihedral first partner-vertex-second partner-Cα. That
dihedral was the obvious choice and was not used: it has no value when the
Cα is in line with the vertex and the second partner, and on a lysozyme
replica Asp48 sits almost in line with Asn59 and its Cα (179.3 degrees), so
the dihedral Asn46-Asn59-Asp48-Cα ranged from -168.9 to +132.4 degrees over
21 frames while the Cα stayed within 11.3 degrees of the plane of the
angle. The elevation has the dihedral's sign in every frame, and is
undefined only when the angle itself is straight. A frame counts on a face
only when sin(angle) × sin(elevation) is at least sin 7.5°, which puts each
of the three arms from the vertex at least 7.5 degrees out of the plane of
the other two; nearer flat the sign is noise. 7.5 degrees is half the
15-degree angle threshold, so a partner counted on opposite faces in two
frames has turned at least 15 degrees across the flat arrangement. Without
that band the sign of lysozyme's 24 angles flipped 81 times between
consecutive frames over two 10 ps replicas. With it, counting only the
frames that are on a face and skipping the flat frames between them, the
face changed 6 times, each to or from a lone frame just past the band; the
two counts are of different things, and only 2 of the 6 fall on strictly
consecutive frames. Each angle is reported with how far
its crystal arms are from flat, the crystal's face, and per replica the
fraction of frames on the crystal's face and on the other; it is called
kept its face, changed face, went flat, partial or replicas disagree, with
the thresholds printed, and like the rotamers and water it is a result only
when the distances are. When the crystal's own arms are within 7.5 degrees
of flat there is no face to keep, and the row says "in plane in the
crystal"; each replica's cell then gives the fractions of frames on the
clockwise face, on the anticlockwise face and flat, and the verdict says
whether the replicas stayed in plane or left it for one face, by the same
thresholds. Until 2026-09-30 those rows printed n/a for every replica. On
the 21-frame lysozyme replica, taking its minimised starting structure as
the crystal, 5 of the 24 angles are in plane there, and Ser50-Asn46-Asn59
is on the anticlockwise face in 8 of the 21 frames. Because the Cα is the
vertex's own, a side chain that turns over under its partners changes face
too, which the rotamer table will show. On 21 frames of a lysozyme replica
every elevation equals `gmx gangle -g1 plane -g2 vector`'s to 0.001 degree,
as stored and across the periodic box, and both are tests. The GROMACS
route runs that `gmx gangle`, and CI checks that the two routes' face
tables are identical.

And the water at each catalytic residue: in every frame, the number of
water oxygens within 0.35 nm of any of its functional atoms, reported per
replica as the mean count and the fraction of frames with at least one
water, beside the count in `em.gro`, and called hydrated, dry,
intermittent or replicas disagree with the thresholds printed. Every frame
is counted, as for the hydrogen bonds and rotamers; nothing is discarded
as relaxation. 0.35 nm is the donor-acceptor limit of `gmx hbond`, so a
counted water can hydrogen-bond to the group. On a lysozyme run it also
takes in the first shell of water around the protein's carboxylate and
hydroxyl oxygens and stops short of the second: `gmx rdf` puts that
water's first peak at 0.27-0.28 nm and its first low at 0.32 nm. A
residue standing in with its Cα (glycine, say) has its count shown but
marked as a stand-in and given no verdict: water at a Cα is backbone
exposure, not the hydration of a catalytic group. On 21 frames of a
lysozyme replica, cut down to residues 1-59 and the 272 waters that come
near the active site, every count equals `gmx select`'s, as stored and
translated across the periodic box, and both are tests. The GROMACS route
runs `gmx select`, and CI checks that the two routes' water tables are
identical.

It also measures how much of each catalytic residue solvent can reach:
its solvent-accessible surface area (Lee & Richards' surface, measured
on Caterva's own route with Shrake & Rupley's points: 2,000 per atom, a
0.14 nm probe, and Bondi's radii exactly as GROMACS's `vdwradii.dat`
lists them, hydrogens included). The surface is the whole protein in every frame, because a
residue's exposure is set by its neighbours; water and ions are not part
of it, and `caterva md` simulates no ligand. The protein is made whole
first and its periodic images are not counted. Each residue is reported
in `em.gro` (the structure every replica began from; the crystal's
`protein.pdb` has no hydrogens, so set against an all-atom surface a
change would be only the hydrogens) and per replica as the mean ± SD over
every frame, with the range the middle 95% of frames fall in. An area
alone does not say buried or exposed, since a fully exposed glycine has
less surface than a buried tryptophan, so each is also given as a share
of the largest area its residue type can have (Tien et al. 2013, PLoS ONE
8:e80635, Table 1). Those maxima are DSSP's heavy-atom areas with other
radii, so the share is a guide rather than a value on their scale; on
the minimised structures of hen lysozyme and T4 lysozyme no residue's
all-atom area exceeds its maximum (chain ends aside; the largest share is
0.96). A residue
is called buried below 20% of it, exposed at 40% or above, and partly
exposed in between (chosen thresholds, printed with the table), at the
start and in each replica: "buried throughout", "buried at the start,
exposed in every replica", or which replicas left the starting state when
they disagree. A mean near a threshold can fall on either side of it in
another run of the same system (lysozyme's Asn46 was at 19% in one smoke
run and 20% in the next), so a replica whose mean crosses a threshold
while the middle 95% of its frames still reaches back into the starting
state is reported as "buried in rep2 by its mean, with frames still partly
exposed", not as having left that state, and does not make the replicas
disagree. The start is one structure, so a start near a threshold is only
as firm as the share printed beside it. A residue without a peptide bond on
both sides in `em.gro` (either end of the chain, or beside a break) has
no maximum and no verdict, and with one replica there is no verdict. A
residue number that belongs to two residues (two chains simulated, which
`caterva md` does by default, or an insertion code, which `.gro` files
drop) has no area of its own: on both routes the section then says "Not
measured" and why, and the rest of the report is written as before. Like
the water, the verdict is a result only when the distances are, and it
does not set the exit code.

2,000 points per atom is a choice between accuracy and time. On eight
lysozyme smoke runs (not committed), one structure's residue areas were
within 0.0098 to 0.0157 nm² of the same areas with 20,000 points, so the
area at the start can be off by one or two in its last printed digit
(0.01 nm²); over only five frames a replica's mean was within 0.0052.
4,000 points would roughly halve the error for about 1.4 times the time.

Every frame is measured, with no stride, and the areas are the largest
cost of the native route: about 0.25 to 0.4 s a frame for lysozyme (1,960
protein atoms) and T4 lysozyme (2,603), timed on a heavily loaded machine
(`caterva/analyze/sasa.py`), so the 1,000 frames a replica of the default
10 ns run writes add several minutes per replica, and more for a larger
protein or a longer run (a 100 ns replica at the same output rate, about
an hour). `--gromacs` measures with `gmx sasa` in `analyze.sh` instead.

The GROMACS route runs `gmx sasa`, which places its points differently
(Eisenhaber et al.'s double cubic lattice), with the same probe, radii
and surface (`-surface Protein -nopbc`) and `-ndots 2000`, which it rounds
up to 2,252 points per atom (its tessellation's next size); the section
names the method that produced its numbers. Its `-or` file has every
residue's mean area, for the rest of the protein. The two converge on
the same surface: on T4 lysozyme, `gmx sasa -ndots 10000` and Caterva at
10,000 points agree to 0.0044 nm² on all 162 residues. As the routes run
(2,000 points against 2,252) they differ by the two point sets' errors
added, which grow with the area a residue exposes: over 11,514 residue
areas (every residue of 88 structures from eight lysozyme smoke runs,
which are not committed, and of T4 lysozyme) the root mean square
difference was about 0.0047 √area nm² (area in nm²) and the largest
0.0205 nm², on an arginine with 1.80 nm² exposed. The routes are held to
0.03 √area nm², and at least 0.0075, a margin chosen over those
measurements: none of them came nearer than 0.71 of it. The tests check
an isolated atom and two overlapping atoms against the areas worked out
by hand; every residue of T4 lysozyme against `gmx sasa` at 10,000
points and at 2,000; the six catalytic residues of 21 committed lysozyme
frames against `gmx sasa` frame by frame, and two replicas made from
those frames, which get the same verdicts on both routes; and the same
frames moved so that the active site straddles the periodic box, which
give the same areas. CI compares the two routes' tables on every run, to
that bound plus 0.01 nm² for the rounding of the two printed values, and
their verdicts: a verdict may differ only where an area rounds into
another state on each route, which the smoke run reports by name.

And the principal motions of the active site: every heavy atom of the
catalytic residues (backbone and side chain, 47 atoms on lysozyme), each
frame superposed on the same atoms of `em.gro`, and the covariance of
their coordinates split into modes, per replica and with every replica's
frames pooled. The report gives the three largest eigenvalues (the
mean-square fluctuation along each mode, nm²), the total, the share of it
in the first mode and in the first ten, and, from the pooled analysis, the
share that is the replicas sitting in different places rather than moving
about them. Two questions are answered from it. Do the replicas move the
same way? The root-mean-square inner product (RMSIP) of each pair's first
ten modes (Amadei, Ceruso & Di Nola 1999) is set beside what two random
ten-dimensional subspaces of the 3N - 6 directions the fit leaves would
give (RMSIP² = 10/(3N - 6), 0.074 with standard deviation 0.010 on
lysozyme; derived exactly, and checked against random subspaces), and
called same motions (RMSIP² at least 0.5), no more alike than chance
(within three standard deviations of that) or partly shared. Is a
replica's largest motion only diffusion? The cosine content of its
projection on PC1 and PC2 (Hess 2000, 2002) is 1 when the projection has
the shape random diffusion gives that mode: a half cosine for PC1 (a drift
one way with no return), a full cosine for PC2 (one excursion out and
back); at 0.5 or more (a stated choice: the cosine is then at least half of
the projection's mean square) the replica is called diffusion-like, not
converged. Frames with no correlation in time would give PC1 0.05 at 21
frames, and would be called diffusion-like (PC1 or PC2 at 0.5 or more)
with probability at most 0.0007, and the report prints both beside the
values. A low cosine content does not show convergence: a
replica can sample one basin thoroughly and never find the next. A
replica whose total fluctuation is below 1e-8 nm² (every atom within 1e-4
nm RMS, a tenth of what an xtc records) is called no motion, and its
cosine contents and RMSIP are not reported. A diffusion-like replica, or a pair no more alike than chance, makes the exit
code 4. Fewer than 21 frames per replica is refused rather than reported:
the ten modes compared must be at most half of the directions the frames
can span. On the 21 frames of a lysozyme replica the first ten eigenvalues
agree with `gmx covar`'s to within 6e-6 relative (three of them differ by
one in the sixth digit it prints), the projections agree with
`gmx anaeig`'s to the 1e-5 nm it prints (up to each mode's sign), the
cosine contents agree with `gmx analyze -cc`'s to 7e-6 once its
normalisation is converted (it prints (n + 1)/n times the bounded value,
so a pure cosine reads 1.048 there at 21 frames), and the RMSIP² between
the replica's two halves equals `gmx anaeig -over`'s to the 0.001 it
prints; all four are tests. That replica's PC1 has a cosine content of
0.77 over its 10 ps. The GROMACS route runs `gmx covar`, `gmx anaeig` and
`gmx analyze` (the atoms are written to `pca.ndx`), and CI compares the
two routes' tables.

`--gromacs --no-run` on a run whose `analyze.sh` was written before the
angle, face, water and solvent-exposure tables or the principal motions
existed is refused, naming the missing file, rather than reporting
without them: run `analyze.sh` again first.

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

**This is what Caterva is for.** It reads BRENDA, NCBI Taxonomy, UniProt and
PubChem live, so it needs a network connection. The resolvers that do it ship
in the wheel, the app folder and the macOS app (the release build copies them
into `caterva/_literature/`); a source checkout is only needed to change them.

`caterva compose ... --subject` and `caterva bind` work from any install.
The `make cite` and `scripts/cite.py` commands below are in the repository, so
they need a checkout.

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
naming each enzyme it could mean (EC number, enzyme name, and your
organism's proteins), because a wrong EC number is a citation for the wrong
protein rather than merely a wrong value. Pick one, pass `--ec`. The next
section is the command that does the looking.

**No network, no account:** `--fixture Tests/fixtures/brenda_ldh_fixture.html`
reads a saved page, and the document then says no search was run. `make
demo` is that path end to end.

### Finding the enzyme: `caterva enzyme`

Every command that takes an enzyme (`compose --subject`, `structure
--subject`, `catalog`, `report`, `cite --enzyme`) turns a name into an EC
number the same way, and `caterva enzyme` shows you that step. It looks the
name up in the IUBMB enzyme nomenclature (the ExPASy ENZYME database, shipped
inside Caterva, so it works offline), ranks every enzyme whose *name*
matches, and says why each one did:

```bash
caterva enzyme "pyruvate kinase" --organism human --limit 2
```

```
Enzyme finder: 'pyruvate kinase' (ExPASy ENZYME release 02-Sep-2026, human)

Resolved: EC 2.7.1.40 (pyruvate kinase) -- accepted name matches exactly.

 1. EC 2.7.1.40  pyruvate kinase
      why: accepted name matches exactly
      reaction: pyruvate + ATP = phosphoenolpyruvate + ADP + H(+).
      class: Transferases > transferring phosphorus-containing groups > phosphotransferases with an alcohol group as acceptor
      human proteins (2): PKM (P14618), PKLR (P30613)
      use: caterva compose "Michaelis Menten" --subject 2.7.1.40 --organism human --substrate <substrate>

 2. EC 3.1.3.49  [pyruvate kinase]-phosphatase
      why: your query is a phrase inside the accepted name
      reaction: [pyruvate kinase] phosphate + H2O = [pyruvate kinase] + phosphate.
      class: Hydrolases > acting on ester bonds > phosphoric monoester hydrolases
      human proteins: none listed
      use: caterva compose "Michaelis Menten" --subject 3.1.3.49 --organism human --substrate <substrate>

3 more; raise --limit to see them.
```

The accepted name is an exact match for exactly one enzyme, so it resolved.
The second entry is there because the phrase sits inside its name, and it is
a phosphatase: nothing is chosen by relevance alone. A name that is several
enzymes is not resolved:

```bash
caterva enzyme "lactate dehydrogenase" --organism human --limit 2
```

```
Enzyme finder: 'lactate dehydrogenase' (ExPASy ENZYME release 02-Sep-2026, human)

Not resolved: 12 enzymes match 'lactate dehydrogenase'; these 2 match best. Caterva will not pick one for you: a wrong EC number is a citation for the wrong enzyme, not merely a wrong value.
Recommended: EC 1.1.1.27 (L-lactate dehydrogenase), the only enzyme matched that has a protein from the organism you gave. Confirm it with --subject 1.1.1.27.

 1. EC 1.1.1.27  L-lactate dehydrogenase   <- recommended
      why: accepted name matches once stereo labels (L-, D-, (S)-) and Greek letters are set aside
      reaction: (S)-lactate + NAD(+) = pyruvate + NADH + H(+).
      class: Oxidoreductases > acting on the CH-OH group of donors > with NAD(+) or NADP(+) as acceptor
      human proteins (5): LDHAL6A (Q6ZMR3), LDHAL6B (Q9BYZ2), LDHA (P00338), LDHB (P07195), LDHC (P07864)
      use: caterva compose "Michaelis Menten" --subject 1.1.1.27 --organism human --substrate <substrate>

 2. EC 1.1.1.28  D-lactate dehydrogenase
      why: accepted name matches once stereo labels (L-, D-, (S)-) and Greek letters are set aside
      reaction: (R)-lactate + NAD(+) = pyruvate + NADH + H(+).
      class: Oxidoreductases > acting on the CH-OH group of donors > with NAD(+) or NADP(+) as acceptor
      human proteins: none listed
      use: caterva compose "Michaelis Menten" --subject 1.1.1.28 --organism human --substrate <substrate>

10 more; raise --limit to see them.
```

"Recommended" is shown only when, across EVERYTHING that matched (here 12
enzymes, of which the 2 shown match best), exactly one enzyme has a protein
from the organism you gave, and it matched by name. It is never applied for
you: you confirm it with `--subject 1.1.1.27`, and it is never made for an
abbreviation, a gene symbol or a misspelling. A misspelling gets a
did-you-mean and exit code 3:

```bash
caterva enzyme "hexokinse" --organism human --limit 2
```

```
Enzyme finder: 'hexokinse' (ExPASy ENZYME release 02-Sep-2026, human)

Not resolved: no enzyme is named 'hexokinse'; these are close. Did you mean one of these?

 1. EC 2.7.1.1  hexokinase
      why: close to the accepted name: did you mean?
      reaction: a D-hexose + ATP = a D-hexose 6-phosphate + ADP + H(+).
      class: Transferases > transferring phosphorus-containing groups > phosphotransferases with an alcohol group as acceptor
      human proteins (5): HKDC1 (Q2TB90), HK1 (P19367), HK2 (P52789), HK3 (P52790), GCK (P35557)
      use: caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate <substrate>
```

An abbreviation or a gene symbol is not an enzyme name, and Caterva never
resolves one by itself, because most are shared (HK is hexokinase and histidine
kinase; AK is adenylate kinase and adenosine kinase; SDH is succinate
dehydrogenase and sorbitol dehydrogenase) and a symbol is a different protein
in each organism. It lists what the symbol can mean, from a small table that
cites its source on every row (UniProtKB reviewed entries for the gene
symbols, per organism; the accepted name of each EC number for the lab
abbreviations), and you confirm one:

```bash
caterva enzyme "HK2" --organism human --limit 2
```

```
Enzyme finder: 'HK2' (ExPASy ENZYME release 02-Sep-2026, human)

Not resolved: 'HK2' is an abbreviation or symbol, not an enzyme name, and Caterva does not resolve one by itself. Caterva will not pick one for you: a wrong EC number is a citation for the wrong enzyme, not merely a wrong value.

 1. EC 2.7.1.1  hexokinase
      why: HK2 is the human gene symbol of Hexokinase-2 (UniProtKB P52789), which UniProt files under this EC number
      reaction: a D-hexose + ATP = a D-hexose 6-phosphate + ADP + H(+).
      class: Transferases > transferring phosphorus-containing groups > phosphotransferases with an alcohol group as acceptor
      human proteins (5): HKDC1 (Q2TB90), HK1 (P19367), HK2 (P52789), HK3 (P52790), GCK (P35557)
      use: caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate <substrate>

 2. EC 2.7.13.1  protein-histidine pros-kinase
      why: another name for this enzyme is written 'HK2', but the abbreviation table lists 'HK2' for other enzymes
      reaction: L-histidyl-[protein] + ATP = N(pros)-phospho-L-histidyl-[protein] + ADP + H(+).
      class: Transferases > transferring phosphorus-containing groups > protein-histidine kinases
      human proteins: none listed
      use: caterva compose "Michaelis Menten" --subject 2.7.13.1 --organism human --substrate <substrate>
```

The same rule keeps `SYK` from being the lysine--tRNA ligase whose UniProt
entry name is `SYK_HUMAN` (an entry name is a label, not a gene symbol; the
SYK gene is `KSYK_HUMAN`), and `IDH1` is EC 1.1.1.42 for human and mouse and
EC 1.1.1.41 for yeast, never offered across organisms. A few abbreviations
resolve, because the nomenclature itself lists them as another name of exactly
one enzyme and the table agrees (`GAPDH`, `ACE`, `PKA`, `PKC`, `HDAC`). A name
that is a full alternative name still resolves, unless the enzyme it names has
no protein in your organism while another matching enzyme has one:

```bash
caterva enzyme "glycogen synthase" --organism human --limit 2
```

```
Enzyme finder: 'glycogen synthase' (ExPASy ENZYME release 02-Sep-2026, human)

Not resolved: 'glycogen synthase' is a name of EC 2.4.1.21 (starch synthase), which lists no human protein, and also matches EC 2.4.1.11 (glycogen(starch) synthase), which lists human GYS1, GYS2, EC 2.7.11.26 ([tau protein] kinase), which lists human PRKAA1, BRSK1, BRSK2, GSK3A. Caterva will not pick one for you: a wrong EC number is a citation for the wrong enzyme, not merely a wrong value.

 1. EC 2.4.1.21  starch synthase
      why: listed as another name for this enzyme: 'glycogen synthase'
      reaction: [(1->4)-alpha-D-glucosyl](n) + ADP-alpha-D-glucose = [(1->4)-alpha-D-glucosyl](n+1) + ADP + H(+).
      class: Transferases > glycosyltransferases > hexosyltransferases
      human proteins: none listed
      use: caterva compose "Michaelis Menten" --subject 2.4.1.21 --organism human --substrate <substrate>

 2. EC 2.4.1.11  glycogen(starch) synthase
      why: accepted name matches once a parenthesised alternative word in it is set aside
      reaction: [(1->4)-alpha-D-glucosyl](n) + UDP-alpha-D-glucose = [(1->4)-alpha-D-glucosyl](n+1) + UDP + H(+).
      class: Transferases > glycosyltransferases > hexosyltransferases
      human proteins (2): GYS1 (P13807), GYS2 (P54840)
      use: caterva compose "Michaelis Menten" --subject 2.4.1.11 --organism human --substrate <substrate>

2 more; raise --limit to see them.
```

What it reads, in order of strength: an EC number (`1.1.1.27`, `EC 1.1.1.27`,
or a class like `1.1.1.-`); the accepted name; another name for the enzyme
(`aldehyde reductase`); the same once stereo labels (`L-`, `(S)-`) and Greek
letters are set aside; a phrase inside a name; every word of your query in
a name (two real words at least; a single letter must be a word of the name
and not inside a parenthesis); an abbreviation or gene symbol from the table
(always for you to confirm); a UniProt entry name of your organism, when the
table does not know the symbol (listed, never chosen, never recommended); and
last, only when nothing else matched, a close spelling (never for a word of
five letters or fewer, a word with a digit, or a word that is itself part of an
enzyme name). A number the nomenclature has
transferred resolves to its replacement and says so; a deleted one is
refused. Options: `--organism` (human, mouse, rat, yeast, E. coli and others,
or a Latin name or its abbreviation: `H. sapiens`, `S. cerevisiae`; `E. coli`
means the K-12 strain), `--limit N`, `--json`. Exit codes: 0 resolved or candidates
listed, 3 nothing matched (suggestions still printed), 2 malformed command.

Two things to know. It lists proteins by gene symbol (UniProt's, where the
names file has one for human, mouse, yeast and E. coli K-12; the UniProt entry
name otherwise) for 13 organisms (human, mouse, rat, yeast, E. coli, cow, pig,
chicken, Arabidopsis, B. subtilis, fruit fly, C. elegans, rabbit) and counts them
for every other.
And a resolved name can still be the wrong organism's enzyme: `glucokinase`
resolves to EC 2.7.1.2, which lists no human protein, while human glucokinase
is filed under EC 2.7.1.1 (hexokinase, as "hexokinase type IV"). The report
says so beside the resolution; `caterva enzyme glucokinase --organism human`
shows both.

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
- Having no network connection, or a database that is down: BRENDA, NCBI
  Taxonomy, UniProt and PubChem are read live. The report names which one
  could not be reached rather than failing obscurely.

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

## Your own rates: `caterva rates`

Everything above asks the literature for a constant. `caterva rates` is the
other door: you measured initial rates yourself, at several substrate
concentrations and perhaps several inhibitor concentrations, and want the
constants, how well your data determine them, which mechanisms they rule
out, and how they compare with the values BRENDA cites. It runs from the app
folder; the literature comparison also needs a network connection.

**The file** is a CSV whose header names each column and its unit:

```
substrate (mM),rate (uM/min),sigma (uM/min),inhibitor (uM),group
```

Only `substrate` and `rate` are required; `--substrate-column` and its
siblings name columns called something else. Lines starting with `#` are
comments. Rows with identical conditions are replicates. A unit it cannot
read is refused with the column named; an arbitrary readout that needs no
conversion (`counts/min/min`, `A340/min`, `ppm`) is accepted, and then the
literature comparison is refused for it, because a Km in ppm cannot be
compared with one in mM without a molar mass.

**The error bars are never invented.** Give exactly one of: a `sigma` column;
`--sigma-from replicates` (the pooled spread of your replicates, with its
degrees of freedom; add `--error-model proportional` when the noise grows
with the rate); or `--sigma-from residuals` (ordinary least squares, sigma
from the fit's own scatter, which is what R's `nls` reports and which
assumes the rate law is right, so no goodness-of-fit chi-square is printed
for it). With none of these it refuses, names the three, and exits 3. With
`--group` and `--sigma-from replicates`, one sigma is pooled across all the
groups' replicates, which assumes every group was measured with the same
precision; the report says so.

### A worked example, on real data

`examples/rates/puromycin.csv` is Treloar's 1974 galactosyltransferase data,
published in Bates & Watts (1988), *Nonlinear Regression Analysis and Its
Applications*, Appendix A1.3, and shipped with R as `datasets::Puromycin`:
rates from puromycin-treated and untreated cells, in duplicate except the
untreated cells' highest concentration (1.10 ppm, measured once), substrate
in parts per million and rate in counts per minute per minute.

```
caterva rates examples/rates/puromycin.csv --sigma-from residuals --group state --model michaelis-menten
```

The verdict comes first (real output; this is the whole of it):

```
- [treated] Michaelis-Menten, the law asked for (--model michaelis-menten); no other law was fitted or tested.
- [treated] Michaelis-Menten: Vmax 212.7 (197.3 to 229.3 counts/min/min), Km 0.06412 (0.04692 to 0.08616 ppm) (95% profile intervals).
- [untreated] Michaelis-Menten, the law asked for (--model michaelis-menten); no other law was fitted or tested.
- [untreated] Michaelis-Menten: Vmax 160.3 (145.6 to 176.5 counts/min/min), Km 0.04771 (0.03137 to 0.07006 ppm) (95% profile intervals).
- Between groups: Vmax differs between treated and untreated: sharing it fits worse than separate values (F(1, 19) = 25.5, p = 7.08e-05).
- Between groups: Km: no difference between treated and untreated detectable by these data (F(1, 19) = 1.72, p = 0.206); the shared fit gives Km = 0.05797 (0.04599 to 0.07234). Not detected is not the same as equal.
```

then each group's fit, here the treated one in full:

```
| constant | estimate | standard error | 95% profile interval | unit |
|---|---|---|---|---|
| Vmax | 212.7 | 6.947 | 197.3 to 229.3 | counts/min/min |
| Km | 0.06412 | 0.008281 | 0.04692 to 0.08616 | ppm |

- Residual standard error 10.93 counts/min/min on 10 degrees of freedom. No goodness-of-fit chi-square is given: sigma was estimated from these residuals, so the chi-square is 10 by construction and cannot test the law it was computed from.
- Correlations of the estimates: Vmax-Km +0.765.
- Starts: 6 of 6 reached this minimum; no start found a different one.
- Condition number of the weighted Jacobian (log constants): 6.38.
- Lack of fit: lack of fit F = 1.07 on 4 and 6 degrees of freedom, p = 0.447: no departure from this law's shape beyond the replicates' own scatter.
- Substrate range: Your 6 substrate concentration(s) span 0.31 to 17 times Km (below Km: 2; above: 4; in the guideline range of 0.2 to 5 times Km: 4). The Assay Guidance Manual asks for 8 or more in that range, with several on each side of Km.
- Substrate range: The range brackets Km with fewer than 8 concentrations in the guideline range. Eight concentrations evenly spaced on a log scale from 0.2 times the lowest to 5 times the highest Km in its interval would satisfy the guideline wherever Km lies: 0.0094, 0.016, 0.028, 0.048, 0.084, 0.14, 0.25, 0.43 ppm.
```

and the test between groups:

```
| shared constant | statistic | p | verdict |
|---|---|---|---|
| Vmax | F(1, 19) = 25.52 | 7.08e-05 | differs |
| Km | F(1, 19) = 1.718 | 0.206 | no difference detected |
| all | F(2, 19) = 24.14 | 6.07e-06 | the groups differ |
```

These are R's numbers. R 4.6.0's `nls` on `datasets::Puromycin` gives Vm
212.7 (standard error 6.947), K 0.06412 (0.008281) and a residual standard
error of 10.93 on 10 degrees of freedom for the treated cells, and `confint`
the same profile intervals, 197.3 to 229.3 and 0.04692 to 0.08616; the tests
hold the command to them (`caterva/tests/test_rates_puromycin.py`). The
interval for Km is asymmetric, 0.0172 below the estimate and 0.0220 above,
which a +-2 SE interval cannot be. The shared-Km row is Bates & Watts' own
question of these data, whether puromycin changes Vm only; its F of 1.718 on
1 and 19 degrees of freedom is R's `anova` of the same two fits, and the
test also recomputes it with `scipy.optimize.curve_fit`, sharing no code with
the command.

Without `--model`, rates with no inhibitor are also tested against substrate
inhibition and the Hill law, and on this file the untreated group says:

```
- [untreated] The data reject Michaelis-Menten in favour of the Hill law (p = 0.0232).
- [untreated] The Hill exponent is below 1 (n = 0.621): the rate rises more gradually with [S] than Michaelis-Menten allows. Negative cooperativity, a mixture of enzyme forms with different Km, or an error that changes with [S] all do this, and the exponent cannot say which.
- [untreated] Two alternatives were tested, each at 0.05, so the chance that at least one rejects a true Michaelis-Menten law is up to 0.0975.
- [untreated] Hill: Vmax 195.1 (160.1 to 399 counts/min/min), K0.5 0.08241 (0.04204 to 2.583 ppm), n 0.6207 (0.3334 to 0.9288) (95% profile intervals).
```

That F test is R's too (`anova` of the two `nls` fits gives F 7.84 on 1 and
8, p 0.0232), and so are the Hill estimates and standard errors. R's
`confint` cannot profile this fit (it stops at its iteration limit), so the
Hill intervals are held instead to an independent profile, computed in the
tests with the other two constants refitted without bounds. Whether the
departure matters is a judgement about the experiment the command cannot
make for you; it reports the finding and what it can and cannot mean. The
groups' verdicts now differ, so the comparison between groups uses
Michaelis-Menten for both and a note says so.

### Inhibitors: which mechanism, and what would decide it

With an inhibitor column, the default fits competitive, uncompetitive,
noncompetitive and mixed inhibition, and tests each simpler one against
mixed. Competitive (Ki' going to infinity) and uncompetitive (Ki going to
infinity) are restrictions on the boundary of the parameter space, and are
tested against the 50:50 mixture of chi-square(0) and chi-square(1), half
the ordinary p-value (Self & Liang 1987); noncompetitive (Ki = Ki') is an
ordinary one-degree-of-freedom test. Competitive against uncompetitive is not
a test at all, and the report says so, printing their fit statistics and
AICc side by side as a description. The verdict names what the data rule
out, what they cannot tell apart, and the measurement that would: inhibited
rates at [S] of 5 Km or more separate competitive from the rest, and at 0.2
Km or less separate uncompetitive.

Ki is the dissociation constant of the inhibitor from free enzyme (Kic) and
Ki' from the enzyme-substrate complex (Kiu); a noncompetitive inhibitor has
one constant that is both.

### What the data determine

A constant the data cannot bound is never printed as a number. Rates taken
only far below Km determine Vmax/Km and neither constant alone, and the
report says exactly that, with the interval of the ratio and a one-sided
bound on each ("Km > [the bound]: the data do not determine an upper bound"),
instead of an estimate with an absurd interval. For the Hill law the
combination the low-[S] rates fix is Vmax/K0.5^n, not Vmax/K0.5, and the
report names it without an interval, since its exponent is itself fitted.
It also says whether your substrate range brackets Km, against the Assay
Guidance Manual's design range of 0.2 to 5 Km with 8 or more concentrations,
and lists concentrations that would (above, for the puromycin rates, whose
lowest concentration is a third of Km).

### Against the literature

Name the enzyme, the organism and the compounds (this reads BRENDA live, so it needs a network connection):

```
caterva rates my_rates.csv --sigma-from replicates --ec 1.1.1.27 --organism human --substrate pyruvate --inhibitor oxamate
```

The fitted Km is compared with the Km BRENDA cites for the substrate, and
the fitted inhibition constant with the Ki BRENDA files under the inhibitor
for the mechanism your data support, chosen by the same resolver
`caterva compose` asks (`--isoform` narrows both). Each comparison prints the
cited value, its BRENDA reference and commentary, what the commentary says
about isoform, mode and construct, the spread of equally good rows, whether
your interval contains the cited value, and the ratio, with units converted.
When your data do not determine the constant (rates far below Km, say), no
fitted value or ratio is printed: only the one-sided bound is held against
the cited value.
A mixed fit's two constants are not compared, because a database row does
not say which of the two it measured. From the app folder the fit is
reported; if BRENDA cannot be reached the comparison is refused, with exit code 3.

### For teaching, and for papers

`--show-linearizations` prints the Lineweaver-Burk, Eadie-Hofstee and
Hanes-Woolf points and the Km and Vmax each straight line gives, beside the
nonlinear fit, with one sentence on why they differ. They are never the
reported estimate. For the treated cells (points left out here):

```
| Lineweaver-Burk | 1/[S] | 1/v | ... | 195.8 | 0.04841 |
| Eadie-Hofstee | v/[S] | v | ... | 193.9 | 0.04352 |
| Hanes-Woolf | [S] | [S]/v | ... | 216.2 | 0.06791 |
| nonlinear fit (michaelis-menten) | | | | 212.7 | 0.06412 |
```

`--json` prints everything; `--export csv` the constants with units and
intervals; `--export curves` the fitted curves on a grid, with the measured
rates, one row per point and units in the headers; `--export methods` a
methods paragraph naming the law, the weighting, the interval method, the
references and the software versions. Exit codes are compose's: `0` done,
`2` malformed question, `3` refused and said why, `1` a crash.

The same fit is a screen in Caterva Studio (Rates): drop a CSV or paste cells
from a spreadsheet, check how the table was read, and the run is this command
on the table the screen writes into the run's bundle as `dataset.csv`, so
`caterva rates dataset.csv ...` in that folder gives the screen's numbers to
the last digit. The screen adds a figure, tables and a methods paragraph; the
guide is `docs/studio/USING_STUDIO.md`, "Fitting your own rates".

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
| `caterva rates`: "no uncertainty was given for the rates" | Exit 3. Add a `sigma` column, or pass `--sigma-from replicates` or `--sigma-from residuals`; the refusal names all three and what each assumes. |
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
