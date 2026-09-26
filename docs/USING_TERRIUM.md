# Using Terrium

A guide for someone who has just downloaded it and wants to get something
useful out of it today. No prior knowledge of the codebase assumed.

Unaffiliated with Tellurium. See [NOTICE](../NOTICE).

---

## The one idea to get first

**Terrium builds a model from the SHAPE of a mechanism, not from the NAME of
a system.**

```
terrium compose "two genes repressing each other"      ->  builds a model
terrium compose "glycolysis"                           ->  refuses, and says why
```

"Glycolysis" is a name. To build it you need its actual enzymes and
stoichiometry, which is a pathway database Terrium does not read. So it
refuses rather than inventing a plausible-looking pathway. "Two genes
repressing each other" is a shape: a toggle switch, and Terrium knows what
one is made of.

That single rule explains almost every refusal you will meet. When something
does not build, you are usually naming a subject where a mechanism is wanted.

The second idea, which is the whole point of the project:

**Every number is labelled with where it came from.** Measured, placeholder,
or yours. A number nobody measured is never presented as though someone did.

---

## Your first three minutes

Get the folder for your machine from the
[Releases page](https://github.com/math12345678/terrium/releases), unpack it,
and from a terminal inside the folder:

```bash
# macOS only, once: the folder is not code-signed
xattr -dr com.apple.quarantine .
```

```bash
./terrium compose "a toggle switch between two repressors"
```

You get a document. Read the **Verdict** at the top: it tells you what the
model does and does not support, names the single worst problem with it, and
says what to do next. Then:

```bash
./terrium compose --shapes
```

All 36 mechanisms it can build, each with a one-line description. This is
the menu. Describe any of them in your own words and it will recognise
them.

```bash
./terrium compose "Michaelis-Menten with a competitive inhibitor" --export methods
```

A methods paragraph for a write-up, with every constant's origin stated. On
Windows write `.\terrium.exe` instead of `./terrium`; installed from the
wheel, write `terium-compose` instead of `terrium compose`.

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

That is Terrium telling you, honestly, that you have a model of a *kind of
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

If you want those checks, you have to ask for them. Terrium will never let a
check it did not run look like a check that succeeded.

---

## A worked example, start to finish

Someone in a lab meeting says: *we think the middle kinase in our cascade is
the one that matters — can you check before we spend three weeks on it?*

**1. Build the shape.**

```bash
terrium compose "three step phosphorylation cascade"
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
terrium compose "three step phosphorylation cascade" --screen
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
terrium compose "three step phosphorylation cascade" --robustness 50
```

If the ranking holds while every placeholder is resampled fifty times, it was
a conclusion about the architecture. If it moves, it was a conclusion about
numbers nobody measured — and you have just saved three weeks.

**4. Ask what to measure instead.**

```bash
terrium compose "three step phosphorylation cascade" --design
```

This ranks candidate measurements by how much *new* information each adds,
names the parameter combinations nothing you have measured can currently
distinguish, and tells you which observations would merely repeat what you
already know. It also states its own blind spot without being asked: the
ranking is by information only, and knows nothing about cost or how long an
assay takes.

**5. Leave a record anyone can check.**

```bash
terrium compose "three step phosphorylation cascade" --export methods > methods.md
terrium compose "three step phosphorylation cascade" --export csv > params.csv
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
terrium compose "three step phosphorylation cascade" --screen
```

Knocks out every species in turn and ranks the effects by fold change. Note
what it says about what a knockout *is*: it removes the gene product
permanently, so nothing can resynthesise it — which is different from a
catalytically dead mutant that still sits there sequestering its substrate.
For one species at a time:

```bash
terrium compose "..." --knockout tier2_X --overexpress tier1_kinase
```

### "Which measurement should I make next?"

```bash
terrium compose "Michaelis-Menten with a competitive inhibitor" --design
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
terrium compose "a toggle switch between two repressors" --robustness 50
```

Resamples every placeholder 50 times and re-solves. If your conclusion
("it switches") holds across the resampling, it was a conclusion about the
shape. If it evaporates, it was a conclusion about numbers nobody measured.

### "Is this model physically possible at all?"

```bash
terrium compose "..." --scale --predictions
```

Two different checks, and each can pass while the other fails:

- `--scale` checks the numbers going **in** — against the diffusion limit,
  the tightest measured Kd, one molecule per bacterium.
- `--predictions` checks the numbers coming **out** — a steady state above
  the cell's total protein content, or below one molecule per cell.

### "Where does this thing switch?"

```bash
terrium compose "a toggle switch between two repressors" --sweep geneA_n \
    --sweep-from 1 --sweep-to 4 --sweep-steps 30
```

Sweeps a parameter and reports where the behaviour changes qualitatively.

### "Give me something I can put in a paper"

```bash
terrium compose "..." --export methods > methods.md   # a methods paragraph
terrium compose "..." --export csv     > params.csv   # every constant, with its origin
terrium compose "..." --export sbml    > model.xml    # SBML, for COPASI, Tellurium, anything
terrium compose "..." --export antimony > model.txt   # Antimony source
```

The CSV has one row per constant with columns for `origin`
(`measured` / `placeholder` / `chosen`), the source table a measurement
would come from, the citation, organism, assay pH, temperature and buffer.
It is an audit trail, not just a parameter list.

### "It is too slow"

The steady-state search and the influence ranking are the expensive parts:

```bash
terrium compose "..." --no-ranking            # skip the influence ranking
terrium compose "..." --no-simulate           # skip the time course
terrium compose "..." --no-analysis           # skip the steady-state analysis
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
terrium compose "reversible binding of a ligand to a receptor" --stochastic 1e-15
```

An exact Gillespie simulation in a compartment of that volume in litres
(an *E. coli* cell is about 1e-15 L). It refuses any rate law that is not mass
action, because a Michaelis-Menten rate has no propensity — that is a real
restriction of the method, not a missing feature. The seed is reported in the
output so the trajectory can be reproduced.

---

## The other half: population genetics

The same executable carries a simulation engine that has nothing to do with
the model builder.

```bash
terrium sim scenarios                 # thirteen teaching presets, listed
terrium sim wf --scenario bottleneck --seed 42
terrium sim kimura --p0 0.1 --s 0.01 --population-size 100
```

`wf` is Wright-Fisher: drift, selection, mutation, dominance, population
structure with migration between demes. The presets are built for teaching —
`bottleneck`, `founder-effect`, `balancing-selection`, `island-model` — and
any option overrides the preset:

```bash
terrium sim wf --scenario bottleneck --generations 500 --replicate-runs 200 \
    --seed 42 --out results.csv
```

It flags what it notices, in words, rather than leaving you to spot it:

```
Flagged: population_size_series minimum (5) is below 10; some generations
will have extremely rapid drift
```

Other subcommands: `kimura` (fixation probability under selection), `ne`
(effective population size from a saved CSV), `ld` (two-locus linkage
disequilibrium decay), `ssa` (exact stochastic decay), `sweep` (one run per
parameter value, as a table).

---

## Real constants, with real citations

**This is what Terrium is for.** It needs the source checkout, not the app
folder: the resolvers that read BRENDA are not shipped in the download.

**Getting the checkout, once** (about five minutes, most of it downloading
dependencies). Put it somewhere iCloud does not sync — *not* under
`~/Desktop` or `~/Documents` on a Mac with iCloud Drive, which silently
breaks the `terrium` command (`make doctor` detects this and says so):

```bash
mkdir -p ~/Code && cd ~/Code
git clone https://github.com/math12345678/terrium.git
cd terrium
make setup
source .venv/bin/activate
```

From then on, in a new terminal: `cd ~/Code/terrium && source
.venv/bin/activate`, and `terrium` works. Then, one command:

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
terrium compose "Michaelis-Menten with a competitive inhibitor" \
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

If you find Terrium doing any of these, that is a bug worth reporting.

---

## When something goes wrong

| what you see | what it means |
|---|---|
| `Not built.` + a list of shapes | You named a subject, not a mechanism. Describe the mechanism, or pick from `--shapes`. |
| `Not built.` + "is a named pathway" | Needs a pathway database Terrium does not read. Describe the steps you want. |
| `Not exported.` | The export refused and the reason is printed above it. The report still ran. |
| Exit code 3 | Something refused and said why; the rest of the report is still there and still valid. A **refused literature search** is one of these: an enzyme name that means more than one enzyme, or a model needing a Km with no `--substrate`. A search that ran and found nothing is *not* a refusal — it produced its answer, and the provenance table states it per constant. |
| Exit code 2 | The question was not well formed. |
| macOS: "cannot be opened because the developer cannot be verified" | The folder is unsigned. `xattr -dr com.apple.quarantine .` inside the folder. "Open Anyway" in System Settings clears one file, not the libraries, so it will not work. |
| Windows: "Windows protected your PC" | SmartScreen. More info > Run anyway. Run `.\terrium.exe` from a terminal. |
| `terrium.exe is not recognized` in PowerShell | PowerShell needs the prefix: `.\terrium.exe`. |

Exit codes are stable enough to script against: `0` produced everything,
`2` the question was malformed, `3` something refused and said why, `1` a
crash.

---

## Where to go next

- `terrium compose --help` — every option, with examples.
- [`docs/releases/v0.3.0.md`](releases/v0.3.0.md) — what the current release
  contains and, more importantly, what it does not.
- [`README.md`](../README.md) — the project's own account of why it exists.
- [`docs/adr/`](adr/README.md) — why each design decision was made, including
  the ones that were reversed.
