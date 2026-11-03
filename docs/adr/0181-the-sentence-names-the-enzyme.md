# ADR 0181: The sentence names the enzyme

**Status:** Accepted, implemented

**Date:** 2026-11-02

**Relates to:** ADR 0178 (the literature search reachable from `compose
--subject`; this makes it reachable from the sentence itself), ADR 0076 (the
adjacent paper is the one you miscite; the reason a sentence's enzyme is never
spread over a cascade), ADR 0174 (an organism lookup that came back empty was
reported as a fact about the science; the reason every reading is a note)

## Context

ADR 0178 joined `caterva compose` to BRENDA behind flags. With them it works:

```
caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose
-> Km 6.0 mM (BRENDA ref 641068), kcat 40.1 1/s (BRENDA ref 739603)
```

Nobody types that first. Typed as a biochemist says it, on 2026-11-02:

- `caterva compose "Michaelis-Menten kinetics of human hexokinase on glucose"`
  built the model on the motif library's two placeholder constants, exit 0,
  and its verdict said they were placeholders **"because no enzyme was
  named"** -- in a report whose quoted description named one.
- `"hexokinase glucose human"`, `"yeast alcohol dehydrogenase with
  ethanol"`, `"E. coli beta-galactosidase lactose"` and `"EC 2.7.1.1
  glucose"` were refused, exit 3: *"No shape in this grammar matches."*
- `--organism human --substrate glucose` given without `--subject` were
  accepted and dropped without a word.
- With `--subject 2.7.1.1` and no `--substrate`, the search refused for want
  of a substrate even when the description said "glucose" and BRENDA lists
  D-glucose for the enzyme.

The measured value was one flag away, and the report sent the reader in the
wrong direction: the false sentence was about the user's input, which is the
one thing a report can always get right.

## Decision

**`caterva/enzymes/sentence.py` reads what a description names;
`compose/__main__.py` `read_description` applies it, once, for every path.**
`compose_report` (so the terminal and Caterva Studio, whose adapter calls it),
`--export` and `--antimony` all call `read_description`, so one sentence
cannot be read three ways. Flags always win: the sentence fills only what no
flag set, and a flag that disagrees with the sentence is used and the report
says so.

### What is inferred, and the rule for each

| | read when | never |
|---|---|---|
| enzyme | an EC number (`EC 2.7.1.1`, `2.7.1.1`), an accepted name typed exactly, a unique full alternative name typed exactly, or an abbreviation the curated table confirms for one enzyme alone, typed with a capital and at least three characters (`PKA`) | a typo, a phrase inside a longer name, a stereo-tolerant match ("lysine oxidase" is L-lysine oxidase only with the L- set aside: said, with the flag, not read), a gene symbol, a lower-case word that is also an abbreviation ("ace"), a bare number of fewer than four parts ("2.5 mM") |
| class words | -- | a window of words that are all class words is never resolved and never reported as ambiguous: "kinase", "enzyme", "protein kinase", "MAP kinase", "phosphatase", "dehydrogenase". The finder resolves "protein kinase" to histidine kinase (EC 2.7.13.3) and "MAP kinase" to EC 2.7.11.24 by exact alternative name, and "enzyme" to D-enzyme with the D- set aside; `CLASS_WORDS` is the guard, and the test holds that the finder still resolves "protein kinase", so the guard is known to be needed |
| organism | `index.organism_code`, the one normaliser every caller shares ("human", "humans", "human's", "H. sapiens", "E. coli", "yeast", "baker's yeast"), or a binomial after "in"/"from" ("in Thermus thermophilus") | two organisms named; "man" (an alias of Homo sapiens for `--organism`, an English word in a sentence); a capitalised word at the start of a sentence. `normalise_organism` now consults `organism_code` too, so `--organism "H. sapiens"` reaches Homo sapiens instead of being passed to BRENDA as typed |
| substrate | a word or phrase of the description that **BRENDA lists** for the resolved EC (and organism), compared case-insensitively; "glucose" is D-glucose only when exactly one listed name is the word with a D-/L-/alpha-/beta-/(S)-/(R)- prefix set aside | anything BRENDA does not list; two listed names that both fit ("alpha-D-glucose" and "beta-D-glucose"); two words naming two listed substrates ("glucose and ATP"). Then the substrate stays unset and the existing refusal, which names BRENDA's substrates, runs |
| inhibitor | "inhibited by X", "inhibitor X", "by X" in a sentence about inhibition, as typed | -- it is searched as `--inhibitor` is, and an inhibitor BRENDA has no Ki for is a labelled placeholder saying so |

The substrate list is `brenda_km_substrates`, the same reading the
missing-substrate refusal names its candidates from, so a sentence can never
be read as a substrate that refusal would not list.

### The single-enzyme-shape rule

A sentence's enzyme becomes the subject only in a one-enzyme mechanism
(`SINGLE_ENZYME_RULES`: Michaelis-Menten, the inhibition forms, cooperative,
reversible, ordered and ping-pong bi-bi, MWC). A cascade, a competition, a
pathway or a futile cycle has an enzyme per step, and one named enzyme's
constants on every step is ADR 0076's adjacent-paper miscitation: "three step
phosphorylation cascade of hexokinase" would carry hexokinase's Km on steps
hexokinase does not run. There the report says the named enzyme was not
applied and why, and "no enzyme was named" is not printed: `ComposedModel`
carries `unapplied_subject`, and the report, the verdict and the model summary
say what happened instead. `--subject` still applies an enzyme to every step
when a person asks for it, as before.

A description that names an enzyme and **no mechanism** ("hexokinase glucose
human") is built as Michaelis-Menten, one enzyme turning one substrate into
one product, and the first note says that is how it was read. One that names
an enzyme and a mechanism word the grammar lacks ("hexokinase oscillator") is
refused, with the command that would build it as Michaelis-Menten: building
one enzyme on one substrate there would answer a question nobody asked.

### What still refuses

- A name that is several enzymes. `"lactate dehydrogenase pyruvate human"`
  is refused exactly as `--subject "lactate dehydrogenase"` is, exit 3, each
  candidate named with its human proteins, ending with the whole command:
  `caterva compose "lactate dehydrogenase pyruvate human" --subject 1.1.1.27`.
  Nothing is searched.
- A named pathway ("glycolysis with hexokinase"): the pathway refusal is
  unchanged.
- A sentence naming two enzymes ("glucokinase and hexokinase"): neither is
  applied, and the report says so.
- `--organism`, `--substrate` or `--inhibitor` with no enzyme named by flag
  or sentence: still nothing is searched, and now stderr and the report say
  each flag went unused instead of dropping it.

## Verified live, 2026-11-02 (BRENDA, NCBI, UniProt, PubChem)

| description | before | after |
|---|---|---|
| `Michaelis-Menten kinetics of human hexokinase on glucose` | exit 0, placeholders, "no enzyme was named" | exit 0, Km 6.0 mM (ref 641068), kcat 40.1 1/s (ref 739603), Homo sapiens |
| `hexokinase glucose human` | exit 3, no shape matches | exit 0, the same two values and references |
| `yeast alcohol dehydrogenase with ethanol` | exit 3, no shape matches | exit 0, Km 5.7 mM (ref 668532), kcat 143 1/s (ref 699019), S. cerevisiae |
| `E. coli beta-galactosidase lactose` | exit 3, no shape matches | exit 0, Km 1.9 mM (ref 171273); kcat a labelled placeholder (no E. coli row; the organisms that have one are named) |
| `EC 2.7.1.1 glucose` | exit 3, no shape matches | exit 0, Km 0.67 mM and kcat 33.7 1/s (ref 739239), Eimeria tenella, with the existing note that no organism was given and the search chose one |
| `lactate dehydrogenase pyruvate human` | exit 3, no shape matches | exit 3, refused, 1.1.1.27 (recommended: LDHA, LDHB, LDHC, ...) and 1.1.1.28 named, and the command above; that command gives Km 0.03 mM (ref 286469) |
| `competitive inhibition of acetylcholinesterase by tacrine in human with acetylcholine` | exit 0, placeholders, "no enzyme was named" | exit 0, Km 0.0714 mM (ref 713996), Ki 3.7e-05 mM (ref 749746); kcat a labelled placeholder |
| `three step phosphorylation cascade` | placeholders, "no enzyme was named" | unchanged |
| `a toggle switch between two repressors` | placeholders, no enzyme step | unchanged |

## Consequences

- Reading a description now loads the enzyme index (about five seconds the
  first time in a process, cached after). A window is resolved only when some
  enzyme name has its key, because `resolve` scans the whole nomenclature on
  each call.
- `SINGLE_ENZYME_RULES` is a list of grammar rule names. A new one-enzyme rule
  must be added to it to be grounded from a sentence; until it is, the report
  says the enzyme was not applied, which is the safe failure.
- Not done: a sentence's product or second substrate is not read (`--product`,
  `--compound` remain the way); an organism abbreviation the index does not
  hold ("T. thermophilus") is not expanded; the TypeScript CLI's own query
  resolver is untouched.
