# ADR 0182: A named enzyme gets its best-measured substrate, said out loud

**Status:** Accepted, implemented

**Date:** 2026-11-11

**Relates to:** ADR 0024 (refusing versus defaulting an unsourced parameter;
cross-species stays opt-in, and that part is unchanged), ADR 0076 (the
adjacent paper is the one you miscite; a choice picks the question, never
relabels a neighbour's answer), ADR 0178 (a motif cannot know what its Km is
FOR; this supersedes its refuse-without-a-substrate rule), ADR 0181 (the
sentence names the enzyme; this supersedes its "otherwise the existing refusal
runs" for a substrate)

## Context

On 2026-11-11 the product owner ran 56 descriptions a professor would type
through `caterva compose` on main (10cd687), each with a note of whether
BRENDA really holds the data:

| outcome | runs |
|---|---|
| every constant measured and cited | 7 |
| some measured, some placeholders | 4 |
| every constant a placeholder | 39 |
| refused or crashed | 6 |

By cause, 26 were **no substrate named**: the enzyme was read, the organism
was read, and `_search_resolved` returned before a single table was looked
at, because "a motif knows it needs a Km; it cannot know what the Km is FOR"
(ADR 0178). The refusal then listed what BRENDA holds -- for human hexokinase
D-glucose with 25 Km rows and, on the same page, 61 kcat rows. The kcat and
the Ki were not looked up either, because the whole search was gated on the
Km's substrate. The others: gene symbols not read (9; out of scope here),
names that are a few enzymes (3), no organism (the search chose Eimeria
tenella for hexokinase and Musca domestica for chymotrypsin), an inhibitor
named in the sentence but dropped ("dihydrofolate reductase with
methotrexate" built plain Michaelis-Menten), and two runs that crashed with
an uncaught `ExportRefused` traceback ("pepsin" and "alpha-amylase" with a
substrate and no organism).

Read as a user reads it, the report said "placeholder, placeholder,
placeholder" under a list of the measurements it had declined to use. The
owner's summary -- the actual data is never used -- was a fair reading of
39 of 56 runs, and it was about to reach the professors the product is for.

ADR 0178's refusal was right about what must never happen (a Km cited for a
reaction nobody asked about, presented as the one they did) and wrong about
the remedy: the cure for an unstated choice is a stated one, not no answer.

## Decision

**When the user names an enzyme but not its substrate, inhibitor or
organism, Caterva chooses the best-measured real option BRENDA holds, runs
the search with it, and says in the report what it chose, why, and what the
alternatives are with their row counts, so the user can switch with one
flag.** Placeholders remain only where BRENDA has no usable row, and then the
report says exactly what is missing and what would fix it.

`caterva/compose/defaults.py` makes the choices, from the one BRENDA page the
search reads anyway, parsed by the resolver's own parsers in permissive mode,
so a count is a count of rows the resolver can reach:

| role | ranked by | never |
|---|---|---|
| organism (none named) | Homo sapiens if it has rows for every constant the model needs; else the organism covering the most of them (a Km and a kcat count only when one substrate has both), then the most rows, then the name; the named substrate and inhibitor are honoured | an organism with no row for the substrate named; switching an organism the user NAMED |
| substrate | cosubstrates and cofactors (ATP, NAD(P)(H), FAD, FMN, CoA, water, H+, phosphate, diphosphate, SAM, O2, metal ions, the respiratory quinones and quinols: ubiquinone, menaquinol, ...) set aside unless nothing else has rows; then both a Km and a kcat row in the organism; then one with a Km row of the native enzyme's own constant before one whose every Km row is a construct or altered preparation, an apparent constant with an inhibitor or effector present, or a K0.5 (the rows the resolver passes over, `row_form`); then one BRENDA files under Natural Substrates; then the most Km + kcat rows; then the name | a word of the sentence relabelled as a listed substrate (ADR 0076): "glucose 6-phosphate" is not D-glucose, and the report says the typed word was not used |
| inhibitor | Ki rows in the organism, the chosen substrate excluded; a substrate or product of the reaction (from BRENDA's Natural Substrates and Substrates/Products tables: D-glucose 6-phosphate for hexokinase) and cofactors ranked after every other compound with a row; then the most Ki rows; then the most BRENDA references; then the most Ki rows under the EC counting every organism (so a tie among one-row analogues goes to the compound measured widely, oseltamivir carboxylate for influenza A virus neuraminidase); then the name | -- |
| enzyme (a name that is a few enzymes) | of the finder's best-tied candidates, at most four, the only one with Km rows in the organism, or with no organism one with five times the rows of every other | a class word, an abbreviation or symbol, typo suggestions, or two candidates that both have rows: those stay refused with the candidates named (ADR 0181) |

Spellings that differ only in case or spacing are one compound; anything
subtler ("Z-Gly-Pro-Arg-pNA" and "N-benzyloxycarbonyl-...") is left as
BRENDA wrote it.

**Order.** In `_choose_what_was_not_named`, before the search: the organism
(given the substrate and inhibitor when named), then the substrate (in that
organism), then the inhibitor (given both). Each is filled into the request as
if the flag had been typed, so the resolver matches rows to that name exactly
as it always has, and every value it returns is a real BRENDA row for exactly
the compound and organism stated beside it. Flags and words of the sentence
always win; a choice never replaces them.

**Every choice is said.** `ComposedModel.choices` carries each
`Choice`; each becomes a note in the report, for example

> No substrate was named, so Caterva used D-glucose: of the 10 substrates
> BRENDA lists Km rows for under EC 2.7.1.1 in Homo sapiens, it has the most
> Km and kcat rows (25 Km, 61 kcat; the cosubstrate ATP set aside). Others:
> 2-deoxy-D-glucose (5 Km, 1 kcat); D-mannose (9 Km); D-fructose (7 Km);
> D-glucosamine (3 Km); 2-deoxyglucose (1 Km); and 4 more. Pass --substrate
> NAME to model another.

and an entry of the Studio's `search.choices` (`Choice.to_json()`:
`{role, chosen, why, alternatives: [{name, rows}], considered}`, documented in
docs/studio/CONTRACT.md). `--export` prints them to stderr as `Chose: ...`;
`python -m caterva.compose.defaults --ec EC [--organism] [--substrate]
[--role] --json` prints what would be chosen (exit 3 when nothing can be).

**When nothing can be chosen**, the refusal names the real blocker:

- an organism the user named with no Km row for the EC at all ("glucose-6-
  phosphate dehydrogenase in S. cerevisiae") is refused as the organism, with
  the organisms that have Km rows and their counts, never "pass --substrate";
- a page that could not be read keeps ADR 0178's "Re-run with --substrate
  NAME";
- no Ki row for any inhibitor leaves the Ki a placeholder whose reason names
  `--inhibitor`.

**What came with it.**

- A description that named an enzyme and an inhibitor and no mechanism
  ("dihydrofolate reductase with methotrexate", where methotrexate has a Ki
  row and no Km row under EC 1.5.1.3) reads the word as the inhibitor and is
  built as competitive inhibition, the note quoting the modes BRENDA's rows
  for that inhibitor state.
- The verdict of a partly measured model stays STRUCTURAL (a conclusion
  about the whole system rests on every constant) but no longer claims every
  constant is illustrative: its heading says "partly grounded: 2 of 3
  constants measured", its licence names which are measured and which are
  placeholders, and "Do this next" names the missing piece -- the inhibitor,
  the substrate, the organism -- read from each placeholder's reason, instead
  of advising a different organism for a Ki that was never looked up.
- The search note no longer says a constant "not looked up" was searched and
  "returned nothing".
- A search over every organism that settles on none is a report naming the
  organisms, not an `ExportRefused` traceback.
- `--antimony` reads and searches exactly as the report does, compiles the
  measured values into the source, and prefixes a comment block naming each
  constant's origin; it printed the library's placeholders without a word
  while the report beside it carried three cited values.

## Verified live, 2026-11-11

BRENDA live. The "after" column was re-run on the merged tree after the round-1
review fixes (the literature layer's median pick and the paired Km/kcat lookup
changed several values from the engine branch's). "Before" is the 2026-11-11 baseline on main.

| description | before | after |
|---|---|---|
| `"Michaelis-Menten of granzyme B with a competitive inhibitor" --organism "Homo sapiens"` | exit 3, all three placeholders | exit 0, GROUNDED. Chose 2-aminobenzoyl-IEPDSSMEK-dnp (3 Km, 3 kcat; tied with Boc-Ala-Ala-Asp-SBzl, broken by name) and the inhibitor with the most human Ki rows: Km 0.0058 mM and kcat 4.4 1/s (BRENDA ref 652110), Ki 0.013 mM (ref 732601), all Homo sapiens |
| `"hexokinase Michaelis-Menten kinetics" --organism human` | exit 3, placeholders | exit 0. Chose D-glucose (25 Km, 61 kcat; ATP set aside): Km 6.3 mM and kcat 40.1 1/s (both ref 739603, a Km and its kcat from one paper; that paper measured glucokinase, and the isozyme concern says no --isoform was given) |
| `"acetylcholinesterase from human, Michaelis-Menten"` | exit 3, placeholders | exit 0. Chose acetylthiocholine (40 Km, 3 kcat; acetylcholine has 4 Km and no human kcat): Km 0.11 mM, kcat 7.18 1/s (both ref 749746) |
| `"chymotrypsin follows Michaelis-Menten kinetics"` (no organism) | exit 3, placeholders; with a substrate, Musca domestica | exit 0. Chose Homo sapiens (covers Km and kcat; Bos taurus, 136 Km and 143 kcat, listed first among the others) and L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide: Km 0.304 mM, kcat 10.9 1/s (both ref 769319). On the engine branch alone the Km was a labelled placeholder, the 0.219 mM returned being the N-succinyl compound's row (see "A value is never carried under a neighbour's name") |
| `"carbonic anhydrase in human follows Michaelis-Menten"` | exit 3, placeholders | exit 0. Chose CO2 (61 Km, 59 kcat): Km 9.3 mM, kcat 1.4e6 1/s (both ref 729384). The engine branch alone carried kcat 1e-06 1/s (ref 729224); the implausible-row rule below removed it |
| `"angiotensin-converting enzyme inhibited by captopril" --subject 3.4.15.1 --organism human` | exit 3, placeholders | exit 0. Chose angiotensin I, the natural substrate (11 Km, 3 kcat; hippuryl-His-Leu, 18 Km, listed): Km 0.052 mM and kcat 52 1/s (both ref 669424), Ki of captopril 1.6e-05 mM (ref 650001), GROUNDED. On the engine branch alone the Km was a labelled placeholder, the 0.011 mM returned being [Phe9,Arg10]angiotensin I's row |
| `"xanthine oxidase inhibited by allopurinol"` | exit 3, placeholders; with xanthine, human Km and kcat and no Ki | exit 0, GROUNDED. Chose Bos taurus, the one organism with an allopurinol Ki row (the note says Homo sapiens does not cover it), and xanthine: Km 0.0167 mM (ref 766313), kcat 16.2 1/s (ref 393008), Ki 0.0018 mM (ref 676739) |
| `"glucose-6-phosphate dehydrogenase Michaelis-Menten" --organism "S. cerevisiae"` | exit 3, "Re-run with --substrate NAME" | exit 3, "BRENDA holds no Km row for EC 1.1.1.49 in Saccharomyces cerevisiae ... The organism, not the substrate, is what is missing", listing Homo sapiens (30 rows), Escherichia coli (13), Rattus norvegicus (10), ... (the rows a search would use: variant rows are not counted); the verdict's next step is the same sentence |
| `"lactate dehydrogenase with pyruvate in human"` | exit 3, name refused | exit 0. EC 1.1.1.27 chosen (the only one of 1.1.1.27 and 1.1.1.28 with human Km rows, 6), pyruvate read from the sentence: Km 0.03 mM (ref 286469); kcat a labelled placeholder (human has none; the organisms that do are named). Verdict "STRUCTURAL (partly grounded: 1 of 2 constants measured)", next step the organism |
| `"dihydrofolate reductase with methotrexate in E. coli"` | plain Michaelis-Menten, methotrexate dropped | exit 0, competitive inhibition ("BRENDA's Ki rows for methotrexate ... state: competitive (1 row)"), 7,8-dihydrofolate chosen: Km 0.0013 mM and kcat 24.8 1/s (both ref 724416), Ki 0.0059 mM (ref 655867) |
| `"kinetics of pepsin" --substrate hemoglobin` | uncaught `ExportRefused` traceback | exit 0. Chose Saurida micropectoralis, the organism with the most hemoglobin Km and kcat rows (no human row): Km 0.25265 mM, kcat 27.3 1/s (both ref 771228, the median of that paper's three rows each). `"pepsin with hemoglobin"` gives the same; it was built as cooperative binding before the round-1 fix below |
| `"citrate synthase Michaelis-Menten"` | exit 3, name refused | exit 0. EC 2.3.3.1 chosen (28 Km rows against 4 for 2.3.3.3), Homo sapiens, acetyl-CoA: Km 0.0077 mM, kcat 260 1/s (ref 756131). With `--organism mouse` still refused, and the refusal now says none of the five candidates has a mouse Km row, so the organism is what is missing, naming the organisms with rows for EC 2.3.3.1 |
| `"HIV-1 protease with a competitive inhibitor" --subject 3.4.23.16` | exit 3, placeholders | exit 0. Chose Human immunodeficiency virus 1 (not a binomial, read from the table's organism cells), Lys-Ala-Arg-Val-Nle-Phe(4-NO2)-Glu-Ala-Nle-Gly and indinavir (25 Ki rows): Km 0.017 mM, kcat 5.6 1/s (ref 678346), Ki 3.1e-06 mM (ref 664013) |
| `"thrombin with a competitive inhibitor in human" --substrate D-Phe-Pro-Arg-4-nitroanilide --inhibitor argatroban --antimony` | kcat = 100, Km = 0.1, Ki = 0.5, no comment | kcat = 3.5, Km = 0.00033 (both ref 709074), Ki = 6.4e-06 (ref 732938), each with its BRENDA ref in a comment |

All 56 baseline descriptions re-run: 34 fully measured (was 7), 3 partly
measured, 19 without a measured constant; HIV-1 protease with `--subject`
was one of the 19 (its organism is not a binomial) and, re-checked after the
fix in this ADR, is measured, so 35 / 3 / 18. Of those 18, 14 are names the
sentence reader does not read (gene symbols, "HIV-1 protease",
"angiotensin-converting enzyme", "amylase", a typo), 3 are organisms with no
row (yeast G6PD, human urease, mouse citrate synthase: refused as the
organism, correctly), and 1 is a name of two enzymes whose Km rows do not single
one out ("PEPCK", no organism), refused with both named.

### A value is never carried under a neighbour's name

Found in review of this ADR's own live table. The resolver finds a compound's
rows by looking for its name INSIDE each row's compound cell (the literature
layer's documented courtesy, so "lactate" reaches "(S)-lactate"). A name
Caterva now chooses is BRENDA's exact spelling, and inside longer names it is
another compound: "L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide"
reached the N-succinyl compound's rows, and chymotrypsin's Km was carried as
0.219 mM (ref 769319) -- the succinyl compound's value, which the choice's
note named as the alternative. ACE's angiotensin I Km, 0.011 mM, was
[Phe9,Arg10]angiotensin I's. "D-glucose" reaches 2-deoxy-D-glucose likewise.

So after the search, each Km, kcat and Ki carried is traced back to its
BRENDA row by reference and value (`defaults.neighbour_of`); when the
compound the constant is for is a name the table lists exactly and the row
is another compound's, the value is withheld, a labelled placeholder whose
reason names the other compound. This applies to typed names as well as
chosen ones, since a typed exact name is the same claim. A loosely typed name
BRENDA does not list exactly is not judged, and a row that cannot be found is
not withheld.

### Integrated: one paper for a Km and its kcat, and no implausible value

The rows above were measured on the engine branch alone. Merged with the
literature layer's new pick (the median of the best-described rows, not the
minimum) two more rules hold for every caller -- `caterva compose`, the
Studio, the API's runner and the TypeScript CLI:

- **A Km and a kcat of one substrate come from one paper only when the two
  rows were measured together** (revised after the adversarial round below).
  `fallback_logic.resolve_kinetic_pair` resolves each independently, then
  pairs a Km row and a kcat row of one paper only when they state the same
  pH, temperature and remaining conditions, the paper's matching rows hold
  one value each, and neither lies more than tenfold from its constant's own
  pick; otherwise the independent picks stand and both say why. Compose
  marks the two requests `paired` (`ComposedModel.parameter_requests`); the
  API's runner pairs a Km or a kcat unless the caller sends `needsKcat:
  false`. The first version paired by paper alone and carried human
  hexokinase's Km 6.3 mM with kcat 40.1 1/s (ref 739603): the 6.3 mM row is
  glucokinase's K0.5 with a Hill coefficient of 1.8, and the report never
  said so. The independent picks then carried HK-I's Km 0.06 mM (ref
  640237) beside glucokinase's kcat 60.4 1/s (ref 703624, UniProt P35557):
  two proteins in one rate law. So a pair is also kept to one isozyme: when
  the two rows name different isozymes (by words or UniProt cell), the kcat
  is sought among rows naming the Km's isozyme, then the Km among rows naming
  the kcat's, and the note names the swap. Every human D-glucose kcat row is
  glucokinase's, so human hexokinase now carries glucokinase's Km 6.3 mM and
  kcat 40.1 1/s (ref 739603, one measurement), and the report says the Km row
  is a K0.5 with a Hill coefficient of 1.8 and that P35557 is GCK. A pair
  states a pH or temperature only when both picks do: mouse hexokinase
  carries ref 758915's Km 0.42 and kcat 93.39 (Hk2), not 0.42 beside another
  paper's 53.2. Of several matched pairs, one at 25-37 C comes first (bovine
  trypsin and BAPNA, ref 678548: 0.26 mM and 0.94 1/s at 25 C, not the 15 C
  pair).
- **Why each row was carried is said.** The resolver's own reason
  (`KineticResult.chosen_because`: the median of how many rows, what was set
  aside, the paired constant's paper, a spread wider than 100-fold) reaches
  the report's "Where the evidence did not settle" line in place of "the
  resolver's pick, not a verdict", the Studio's spread sentence, and the
  API's `chosenBecause` / `wideSpread`.
- **An implausible value is never reported.** Rows outside the plausible
  range (a kcat below 1e-3 or above 1e8 1/s, a Km below 1e-7 or above 1e4
  mM) were already set aside when plausible rows existed; when every row is
  outside it the constant is now withheld (`implausible_withheld`, each row
  named) instead of carried. Human carbonic anhydrase and CO2 now carries
  Km 9.3 mM and kcat 1.4e6 1/s, both ref 729384, live.
- **A compound named beside the substrate is the inhibitor when BRENDA
  lists Ki rows for it**: "hexokinase with glucose in the presence of
  glucose 6-phosphate in human" builds competitive inhibition with
  D-glucose 6-phosphate; "dihydrofolate reductase with dihydrofolate and
  methotrexate in E. coli" carries methotrexate's Ki (0.0059 mM, ref
  655867). A gene symbol on the TypeScript CLI's `resolve` ("CYP2B6") now
  searches the organism the symbol is a gene of, with the symbol as the
  isoform, as compose does; it chose Priestia megaterium by row count.

### Which row: the second adversarial round

A second round read every carried row back against BRENDA as a professor
would, and found real rows that were still the wrong ones to carry. Each is
now a rule in `fallback_logic._best_evidenced` (row facts read by
`Tests/row_form.py`), pinned by `Tests/test_row_quality.py` on the real rows:

| found | rule now |
|---|---|
| xanthine oxidase Km 0.0167 mM (ref 766313), measured "in the presence of 0.0005 mM (E)-5-(3-nitrophenyl)-..." | a row with an inhibitor or other effector in the assay (the page's Ki table lists it, the commentary calls it one, or the paper has an "in the absence of inhibitor" row) is passed over when a row without one exists: 0.01208 mM. The effector reader now reads names starting "(E)-" or "2,3-" |
| glucokinase's K0.5 (Hill 1.8) carried as a Michaelis-Menten Km, unsaid | K0.5 / Hill rows after true Km rows; when carried, `row_notes` says what it is |
| AChE kcat 7.18 1/s paired over the wild-type 93; fumarase Km at pH 9.0 with kcat at pH 6.5; thrombin's NaCl Km with its choline-chloride kcat; TEM-1's seven indistinguishable rows | pairing as above |
| ACE's C-domain Ki, a chimeric ACE's kcat, a benzoate-modified glucose oxidase, trypsin in 20% methanol, an immobilised LDH | constructs and altered preparations after native rows, and named when carried |
| pyruvate kinase's no-K+ control (3.2 1/s against 1182) | an ion is an activator, not an addition: the minus-activator control (including a cation stand-in such as choline chloride) is passed over |
| HK2 carrying a GCK row (P35557), CYP2B6 a CYP3A5/CYP3A43 row | the isoform check reads the row's own UniProt cell through the enzyme index, so those rows are another isoform's and withheld |
| IDH1 R132H carrying wild-type rows as GROUNDED | a mutant typed after the enzyme is sent as `mutation`; only rows naming it are used, else `mutant_not_found` |
| hirudin's Ki 2.37e-10 mM flagged implausible | the Ki table's floor is 1e-12 mM |
| "noncompetitive versus substrate xanthine" not read as versus xanthine | the word "substrate" is not part of the molecule |
| "HIV-1" read as an isoform; TEM-1 given E. coli K-12's ampC and dacA as isozymes | a virus name is not an isoform; an isoform naming none of the listed proteins is said to be outside the reference proteome |
| a row naming IDH1 or GCK only by its UniProt cell reported as "names no isoform"; compose replacing the resolver's reason with "the resolver's row for this model" | the resolver's `row_isoform` reaches `Measurement.row_isoform` and the report's isoform checks; the resolver's own reason follows compose's |
| HIV-1 subtype C Km and kcat beside a LAI (subtype B) Ki, each note naming only itself | the report says when the constants' rows name different subtypes (`row_scope.variant_mix`) |
| glucose oxidase's Aga2 surface-display fusion carried over the soluble enzyme | "in fusion with" is a fusion construct |
| carbonic anhydrase I's "25 mM hydroxyurea" row beside the plain one | a compound the Ki table lists, given bare at a concentration, is an inhibitor in the assay |

Review of the round, live (2026-11-12):

| found | rule now |
|---|---|
| HK1 and HK2 carrying ref 722237's "67.6 \| D-glucose \| - \| wild-type, 37°C", a row naming no isoform from a paper whose other entries on the page ("hGK", "glucokinase", T228M) are glucokinase's | a row naming no isoform in its words or its own UniProt cell takes the isoform(s) its paper's other entries on BRENDA's page name (synonyms, organism accessions, other measurements), read as a UniProt cell is: one names it, several name none of them for a request of any one and are another protein's for a request of none |
| "beta lactamase TEM-1 with ampicillin" carrying, as TEM-1 rows "naming no isoform", ref 775641 (NDM-4), then ref 771150 (CTX-M-15, which the isoform reader did not read), then ref 734041 (a paper naming only NDM variants, whose UniProt cell the enzyme index does not know), then ref 663646 (AmpC, 0.0062 mM and 0.43 1/s) | the isoform reader reads beta-lactamase names ("CTX-M-15", three-digit alleles such as "TEM-149", "AmpC"); a UniProt cell the enzyme index does not know says nothing, so the paper is read. No E. coli ampicillin row on BRENDA's page names TEM-1; live, the constants now come from rows whose papers name no beta-lactamase (Km 0.148 mM and kcat 1090 1/s, ref 209359, one paper), still flagged as naming none; clavulanate's only Ki row (ref 663646) is withheld as AmpC's |
| PKM2's kcat refused as "every row measured a variant": the one row whose cell names PKM is the mutant G415R | when no mutant is asked for, the isoform tiers are decided on rows not measuring a variant first |
| triosephosphate isomerase (T. brucei) carrying 0.31 mM and 5000 1/s, rows "in complex with monomer from Trypanosoma cruzi", over the same paper's wild-type pair | an interspecies or hybrid heterodimer is a construct (a complex with a ligand or regulatory protein is not) |
| bovine trypsin's "enzyme with O-carboxymethyl-poly-beta-cyclodextrin attached to surface" beside its wild-type row | a polymer-conjugated, grafted, encapsulated or entrapped enzyme is a modified enzyme (a conjugated substrate is not) |
| TEM-1 with clavulanate: a window moving the kcat of ref 771150's matched pair to another paper's row, while the Km's reason still named the pair | a constant carried as one measurement with its pair is not moved alone by an assay window; the report says so |

### Round 1 of review: advice that leads to a run that succeeds

An adversarial round ran the advice the reports gave. Much of it led to a
second refusal or to nothing, and the engine now words each remedy for the
thing actually missing (`caterva/compose/__main__.py`,
`caterva/compose/verdict.py`, `caterva/agents/adapters.py`):

- **A Ki is the inhibitor's.** A Ki placeholder said "BRENDA has no row for
  that substrate name ... Re-run with --substrate" (donepezil on human AChE,
  celecoxib on COX-2); the reason now names the inhibitor and `--inhibitor`,
  and lists BRENDA's names as every organism's. Compose then replaces that
  clause with what BRENDA holds in the organism searched: the inhibitors with
  Ki rows there with their counts (human AChE: tacrine 3, edrophonium 2,
  ...), and whether the one named has rows only in another organism
  (labelled, never substituted) or none under that name ("a compound is filed
  under the name its paper used": BRENDA has donepezil's Ki rows, mouse and
  Tetronarce, under its systematic name, which Caterva does not map).
- **The organism, when it is the blocker.** When the organism has no row of
  the table under the EC number at all (human kcat for EC 1.14.14.1), the
  placeholder says so and names the organisms that have rows, instead of
  listing Bacillus substrates under `--substrate`.
- **An isoform's rows.** A constant withheld because every row measured
  another isoform names the compounds measured on the isoform asked for
  (CYP3A4 in human: fenthion, 4 Km rows).
- **"Do this next" is read from the reasons when nothing was measured too**,
  not "re-run with --organism" for every all-placeholder model (CYP3A4, an
  isoform question; luciferase, a neighbour's row).
- **A name refused with an organism none of its enzymes has.** "citrate
  synthase --organism mouse" now says none of the five candidates has a mouse
  Km row, so following the refusal's `--subject` is not refused again.
- **The organism's protein under another EC number.** "glucokinase in human"
  (EC 2.7.1.2, no human Km row) now gives first: human glucokinase is GCK,
  filed under EC 2.7.1.1 (54 human Km rows that are not a variant's), re-run with `--subject 2.7.1.1
  --isoform GCK`, which runs GROUNDED (Km 6.0 mM ref 641068, kcat 37 1/s ref
  702320, the kcat from the row naming GCK; the Km row names no isozyme and
  the report says so). Only a protein whose UniProt names include the words
  exactly counts. That kcat row is "glucokinase with C-terminal 5 alanine
  addition", an engineered construct the variant reader does not recognise;
  the wild-type GCK rows (40.1 1/s ref 739603, 29 1/s ref 702320) name no
  isozyme, so the isoform rule prefers the construct. Left to the row-reading
  stream (see "Not done" below).
- **The sibling advice says whether any row names the protein** (reviewer
  of round 1). "glucokinase with glucose in mouse" was told to re-run with
  `--subject 2.7.1.1 --isoform Gck`, and that run came back GROUNDED with Km
  0.42 mM (ref 758915) and kcat 53.2 1/s from mouse rows naming no isozyme, a
  low-Km hexokinase's values, not glucokinase's (S0.5 near 8 mM). The advice
  now counts the organism's rows that name the protein; when none does
  (mouse: 0 of 3; human: 0 of 54 Km rows), it says each may have measured
  another protein of that EC number, to read the papers of the rows the run
  carries, or to supply the constants.
- **A substrate offered for one constant says whether it fills the others**
  (reviewer). "Renilla-type luciferase with coelenterazine" had no kcat row
  for coelenterazine and was told to re-run with `--substrate Luciferin`,
  which has no Km row in Renilla reniformis, so the advice traded the kcat
  placeholder for a Km one. The substrates that fill every constant looked up
  under the substrate are named; when none does, the reason says so and
  "Do this next" is to supply it. With an isoform asked for, a compound whose
  rows all name another isoform is not offered, since the isoform rule
  refuses those rows.
- **No organism has the compound** (reviewer). "cathepsin D with hemoglobin"
  (rabbit chosen: the only organism with hemoglobin rows) has no rabbit kcat
  row; the organisms offered have kcat rows only for other substrates, and
  the reason now says the model there would not be of hemoglobin.
- **A typed substrate measured only elsewhere** (second reviewer). "pepsin
  with hemoglobin --organism pig" said hemoglobin "is not a substrate BRENDA
  lists for Sus scrofa" and to pass --substrate with BRENDA's own name.
  BRENDA lists Hemoglobin + H2O as pig pepsin's natural substrate, and the
  name typed is BRENDA's own; what is missing is the organism. The note now
  says hemoglobin has Km rows in other organisms only and names them with
  their counts (Saurida micropectoralis, 3 rows; Micropterus salmoides, 2;
  ...), variant rows left out, so the re-run it advises is grounded.
- **An organism Caterva chose is not "your own request"** (reviewer). The
  scout's suffix read "organism must be Bos taurus, raised by your own
  request" for "xanthine oxidase inhibited by febuxostat", where no organism
  was typed; it now says Caterva chose it because none was named.
- **An isozyme's letter is not a possible substrate** (reviewer). With the
  substrate list unread, "lactate dehydrogenase A in human" was refused for
  "what may be the substrate ('A')"; a lone letter, digit or Roman numeral no
  longer stops the search.
- **A substrate word survives a failed read.** The substrate list is read up
  to three times; if it still fails, the search refuses rather than letting
  the chooser model another substrate under "No substrate was named"
  ("hexokinase with mannose in human" had carried D-glucose's Km).
- **"pepsin with hemoglobin"** is pepsin on hemoglobin: a compound named
  beside an enzyme is not read as a mechanism when it is the only cue for
  one (masking it must leave no recognised shape).
- **An organism is offered only for rows the search would use.** "PTGS2 with
  arachidonic acid" (human) was told to re-run in Mus musculus (3 kcat rows),
  and "COX-2 inhibited by celecoxib" that arachidonate's kcat was "available
  in: Mus musculus"; every one of those rows measured the N580A mutant, which
  the search withholds (ADR 0029), so the advised run came back with
  placeholders. Organisms, compounds and isoform rows listed as a way out now
  count only rows that are not a variant's; when none is left the reason says
  so and the step is to supply the constant. The refusal's sentence that no
  candidate has the organism is now its own sentence ("... --subject 2.3.3.1.
  None of ...").
- **With an isoform asked for, an organism is offered only for rows naming
  it.** "CYP3A4 metabolising testosterone in human" has no human kcat row on
  EC 1.14.14.1, and the reason listed Bacillus licheniformis (9 rows) to
  re-run in; those rows measured CYP102A7, so that run was refused again by
  the isoform rule. The organisms listed now count only rows that name the
  isoform, and when none does the reason says no organism's rows name it and
  the step is to supply the constant. An isoform placeholder with no compound
  measured on the isoform in that organism no longer advises `--substrate`.

Live after: AChE/donepezil and COX-2/celecoxib Ki placeholders name
`--inhibitor` and the human inhibitors; CYP3A4's human kcat says EC
1.14.14.1 has no human Turnover row and no organism's rows name CYP3A4, so
it is to be supplied (following the Km placeholder's `--substrate fenthion
--isoform CYP3A4` gives Km 0.089 mM ref 706823); "glucokinase with glucose
in human" followed with `--subject 2.7.1.1 --isoform GCK` is GROUNDED (Km
6.0 mM ref 641068, kcat 37.0 1/s ref 702320); PTGS2/arachidonic
acid and COX-2/celecoxib say every kcat row on EC 1.14.99.1 is a variant's
and to supply it; "citrate synthase --organism mouse" followed with
`--subject 2.3.3.1 --organism human` is GROUNDED (Km 0.0077 mM, kcat 260
1/s, ref 756131); AChE/donepezil followed with `--inhibitor tacrine` is
GROUNDED (Ki 3.7e-05 mM ref 749746); "pepsin with hemoglobin" is GROUNDED in Saurida
micropectoralis (ref 771228). Not done: a PubMed search returns papers for a
made-up inhibitor name (the reason now says the papers were not checked to
name the compound; the search itself is the literature layer's); compound
synonyms (donepezil under its systematic name, galantamine as galanthamine,
febuxostat under its IUPAC name) are not mapped; construct rows ("C-terminal
5 alanine addition", "truncated enzyme with removed helix") are not read as
variants; "Renilla luciferase" is read as firefly luciferase (EC 1.13.12.7),
the word "Renilla" unused; glucokinase in rat gets no sibling advice (the
enzyme index lists proteins for human, mouse, yeast and E. coli K-12 only),
though BRENDA has rat glucokinase rows under EC 2.7.1.1.

## Consequences

- A run with no substrate, organism or inhibitor reads BRENDA's page for the
  choice before the search: two to four extra parses of a page that can be
  four megabytes (about two seconds each), shared by an in-process cache keyed
  on the page's digest. The page itself is fetched once (http_retry's memo).
- Exit 3 now means a search could not be run for a reason the user can act
  on (no rows in the named organism, a page that could not be read, a name
  that is several enzymes with measurements for each), not "you did not name
  a substrate".
- A choice is a modelling decision Caterva made. It is printed with its
  alternatives every time, and `search.choices` lets a page offer the switch;
  it is never silent, and never made where the user said something.

## Not done

- Gene symbols and abbreviations (HK2, CYP2B6, PTP1B, COX-2) are still not
  read (nine of the 56); that is the names workstream's.
- Isozyme ranking within a chosen substrate (MAO-A rows for MAO-B, GCK rows
  for "hexokinase") is unchanged: the existing isozyme concern still says
  when rows name different proteins.
- The inhibitor's mode is not used to rank inhibitors: a chosen inhibitor
  whose rows state another mode is withheld by the existing mode selection,
  with its reason, rather than another inhibitor being tried.
- Substrate spellings that differ chemically but not textually (Z- versus
  N-benzyloxycarbonyl-) are not merged, so their counts stay split.
- The resolver is not taught to match compound cells exactly, so a
  neighbour's row is withheld rather than replaced by the right compound's
  best row (chymotrypsin's L-alanyl compound has four human Km rows of its
  own; the Km stays a placeholder). That belongs in the literature layer.
  The spread note beside a carried value can still count a neighbour's row
  among "one source reports 2 values".
- The resolver's choice among the chosen substrate's rows (the lowest of a
  spread, the carbonic anhydrase kcat of 1e-6 1/s) was not addressed on the
  engine branch; the literature layer's median pick and the integration
  above address it.

## Fourth round (2026-11-12): what a careful enzymologist would pick

An adversarial round of 59 findings, read as a professor reads the output.
What changed, each with a regression test:

- **Spellings.** `compound_names.identity_key` reads a peptide in one-letter,
  three-letter or full residue names as one compound (Ac-DEVD-pNA is
  acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide; benzoyl-DL-Arg-pNA is
  N-benzoyl-DL-arginine 4-nitroanilide), an acid as its anion, a free amino
  acid by its code (D-Ala), and a short list of names a reader types for what
  a paper prints (L-NMMA, DFMO, galantamine, donepezil, O2.-, HMG-CoA). The
  racemate stays distinct from the L form.
- **Effector-present rows.** "activation by X" is an activator present, and a
  compound the page's Activating Compounds table lists is an effector when a
  row says it is present (PKM2's FBP-activated Km), as is "0.008 mM
  inhibitor X" written bare (bovine GDH). The chooser ranks substrates by the
  rows of the enzyme's own constant, a paper's treated arm not counted
  (pig elastase's spermidine series).
- **Rows that are probable errors.** A row more than 100-fold from every
  other row is set aside before choosing among the rows naming an isoform
  (DPP4's kcat 279000 1/s); two middle rows a power of a thousand apart are
  told apart by the rest of the candidates (Candida rugosa lipase).
- **One protein.** A Ki follows the protein the model's Km and kcat rows
  measured (CA II's acetazolamide Ki, not CA IX's); a native Michaelis-Menten
  Km is not traded for another isozyme's K0.5 (human hexokinase is HK-I's Km
  beside glucokinase's kcat, said as two isozymes' constants); an organism
  is chosen only among those with the named isoform's ortholog (CA I is not
  modelled in a bacterium); the only protein an EC holds in an organism is
  the enzyme, not "a named isozyme" (pig CELA1).
- **Series and pairs.** A paper's salt series is read nearest 0.15 M NaCl;
  a paper's row labelled wild-type beats its unlabelled row; a kcat taken
  from the rows naming no isoform takes its own paper's Km as its pair.
- **Inhibitors.** Ranked by papers, not rows of one paper's series; rows
  stating no pH or temperature rank after rows that do; irreversible
  inactivators (chloromethyl ketones, serpins, selegiline, DFMO) rank after
  reversible ones and are said to be irreversible when named; a name of
  its own beats a screening compound's systematic name in a tie; a Ki
  measured on another assay substrate is said, in the row note and the
  verdict (ACE and Abz-SDK(Dnp)P, an N-domain substrate).
- **Names.** A name several enzymes go by is settled by the one with Ki rows
  for the inhibitor named (HMG-CoA reductase and atorvastatin); a name with
  its cofactor written first is read (NADP-isocitrate dehydrogenase); the
  organism named singles out the qualified sibling EC (bovine GDH is EC
  1.4.1.3); an enzyme and its inhibitor named build inhibition, not the
  enzyme's transport shape.
- **Words.** A page that could not be read is an outage ("re-run"), not
  advice to pass --substrate; the next step for a missing Ki names
  --inhibitor; the isozyme remedy offers an isozyme a cited row measured,
  and never a placeholder name; an inhibitor with no Ki row anywhere is said
  to be what is missing; a spread made of two forms of an enzyme
  (membrane-bound and soluble COMT) says so; condition lines carry salts.
- **Surfaces.** The API never resolves values with its older reader when
  compose's reader gave no reading, and passes compose's refusal of an
  enzyme name through; the reader and the TypeScript CLI wait 600 s for
  BRENDA under load; every constant's provenance note carries its row's
  isoform.

A page that could not be read no longer keeps ADR 0178's "Re-run with
--substrate NAME": that advice pointed at the wrong remedy.

## Fifth round (2026-11-13): which row is carried

The fifth review found rows that were real and cited but were not the
enzyme's own measurement. The rules below decide which row a constant
carries.

- **One protein.** A Km and a kcat are always one protein's. The fourth
  round kept HK-I's Km (0.06 mM) beside glucokinase's kcat to avoid a K0.5.
  The model's kcat/Km was then neither enzyme's. Now Caterva first looks for
  another isozyme with both constants. If none has both, it carries the
  kcat's isozyme's pair and says that its Km is a K0.5. For human
  hexokinase that is glucokinase's 6.3 mM and 40.1 1/s (ref 739603).
- **Engineered substrates.** An engineered reporter or construct (a
  fluorescent protein with a grafted cleavage site, FRET pairs, fusions)
  is never a natural substrate, even when BRENDA's Natural Substrates table
  lists it. It ranks with proteins and polymers. Human trypsin is modelled
  on Z-Gly-Pro-Arg-pNA again (0.0298 mM and 88.2 1/s, ref 678332), not on
  EGFP-T1.
- **Probable errors.** A paper that has one constant more than 100-fold
  from every other row supplies neither constant. DPP4's Km of 1.43 mM came
  from the paper whose kcat is 279000 1/s. It now comes from ref 678195,
  0.09 mM with that paper's 87 1/s.
- **Outliers by pairing.** Pairing cannot carry another protein's row more
  than 10-fold from the median of the constant's other rows (when there are
  at least three). Tyrosinase's 26.1 mM is no longer carried. When the rows
  stating pH and temperature lie, by their median, more than 10-fold from
  the median over at least five papers, the rows stating less are kept too.
  Each paper counts once, so one paper's long series does not outvote the
  rest. Pig DAAO's kcat is now 10 1/s (ref 686277), not 440.
- **What a row is.** These rows are read as altered preparations, not the
  native enzyme:
  - "addition of X during measurement" (an assay additive);
  - "after treatment with X for 3 months" (enzyme from treated animals);
  - Co- and Cu-substituted enzymes.
  "10fold higher than wild-type" marks a variant's row. A "predicted" or
  docking value is no measurement. A "heart phosphorylase" row is the heart
  form, not muscle's. A UniProt cell listing several proteins, beside rows
  of the same paper that name one protein each, is no single protein's. A
  subunit of another enzyme filed under the same EC (E. coli FrdA under
  succinate dehydrogenase) is that enzyme's, not an isoform. Such rows no
  longer count toward an organism's coverage.
- **One compound.** dUMP, 2'-deoxyuridylate and deoxyuridine monophosphate
  (and the other deoxynucleotides) are one compound, so thymidylate
  synthase's wild-type rows are counted together.
- **Series.** A pH BRENDA printed unreadably ("pH 4.u") is treated as
  unknown, not as different, so HIV-1 protease's 0.1 M NaCl pair is
  carried. The note names the salt series. Two middle rows from one paper
  that differ only in pH are read nearest pH 7.4. Bovine GDH now carries
  1.01 mM at pH 7.4.
- **Said, not hidden.** When no paper gives a pair, the note says so in
  terms of the conditions compared. If the kcat's own paper gives a Km, the
  note names it and how far it is from the Km carried (ALDH2: 0.2 mM,
  417-fold). Rows set aside for stating less are listed with their values.
  When they lie more than 3-fold from a carried row that has no spread, the
  report shows them under "Where the evidence did not settle" (E. coli
  beta-galactosidase's 400 and 620 1/s). An isoform read from the
  description is said to be that, not "as --isoform asked".

Not done here: reading "influenza" in a description as an organism hint
and preferring "phosphorylase b" rows when the description names that form.
Both belong to the sentence reader. Also not done: choosing between ACE's
N- and C-domain-selective captopril Ki rows. The note already says that
the evidence does not settle it.

## Fifth round (2026-11-13): reading the enzyme's name

The names half of the fifth adversarial round. Each change has a regression
test in `caterva/tests/test_fifth_round_review_names.py` or
`Tests/test_fifth_round_review_names.py`.

- **The organism settles a name several enzymes match.** When an organism is
  named and exactly one candidate both lists a protein of it in the enzyme
  nomenclature and has Km rows for it in BRENDA, and no other candidate read
  has a Km row there, that candidate is used and the note says why and names
  the others. "soybean lipoxygenase" is EC 1.13.11.12 (two candidates list a
  soybean protein; only it has soybean rows); "thioredoxin reductase in rat"
  is EC 1.8.1.9 (only it lists rat proteins, TRXR1 and TRXR2). A class word,
  a typo, an abbreviation, a symbol or a mnemonic is never settled this way.
  A phrase inside many names is no longer said to be "part of one enzyme's
  name".
- **A protein filed under another EC number.** When the name's own EC number
  lists no protein of the organism and has no Km row there, and the words
  name a protein of the organism filed under another EC number whose rows
  name it, that EC number and protein are used: rat glucokinase is HXK4 of EC
  2.7.1.1 (rows "adult glucokinase", "hexokinase IV"), human glucokinase is
  GCK of EC 2.7.1.1. A row names the protein in its words or by its own
  UniProt accession; the refusal for a run where none does (mouse) now
  counts both, and no longer says no row names GCK when the K0.5 row of ref
  739603 names it by P35557.
- **Spelling.** A typo ranks the whole name it is close to before a name that
  only contains it, and the refusal suggests the name people use: "enolse"
  is enolase (EC 4.2.1.11), not acireductone synthase.
- **Industrial names and gene symbols.** "glucose isomerase" is xylose
  isomerase (EC 5.3.1.5) and "penicillin G acylase" penicillin amidase (EC
  3.5.1.11), in the curated alias table. An entry-name mnemonic is read as
  the gene when UniProt gives that very entry the typed word as its gene
  symbol and the entry is under one EC number (NQO1 in human); ACES, HXK4
  and KSYK, whose genes are ACHE, GCK and SYK, stay choices. When no shape
  matches and the words are part of enzyme names, those names are listed
  instead of the mechanisms.
- **Saying what was matched.** A substrate typed in peptide codes is read as
  the name BRENDA prints when the literature layer's identity key says they
  are one compound, and the note says so ("Suc-Ala-Ala-Ala-pNA" as
  succinyl-L-Ala-L-Ala-L-Ala-4-nitroanilide). A carried value whose row
  BRENDA files under another name of the compound says so in the search
  note (donepezil's Ki row is filed as racemic donepezil hydrochloride's
  systematic name). The enzyme's words are echoed with their closing
  bracket.
- **One compound, one alternative.** `identity_key` reads hippuryl as an acyl
  group (hippuryl-L-Phe is hippuryl-L-phenylalanine), the keto group of a
  2-oxo acid as oxo and butyrate, propionate and valerate as their
  systematic names (2-ketobutyrate is 2-oxobutanoate), and dihydroxyacetone
  3-phosphate as dihydroxyacetone phosphate. A tie on usable rows goes to
  more references, then to the compound measured more widely under the EC
  number, and only then to rows the search cannot use; each break is said
  (chymotrypsin in human: Suc-Ala-Ala-Pro-Phe-pNA, 62 rows in every organism
  against 8).

## Fifth round (2026-11-13): advice, notes and surfaces that agree

The fifth adversarial round's advice findings. Each piece of advice was
followed and the run checked; each has a regression test
(`caterva/tests/test_fifth_round_review_advice.py`,
`Tests/test_fifth_round_review_advice.py` and the two TypeScript
`fifthRoundAdvice.test.ts`).

- **Organisms are organisms.** In every-organism mode the parser took the
  first binomial-shaped cell as the row's organism, so "Phenolphthalein
  diphosphate" and "Sodium diphosphate" were offered as organisms for potato
  acid phosphatase's kcat, and both matched "diphosphate" through the whole
  row. The organism is now read by the layout (cell 2, else cell 1), and a
  compound in cell 1 beside the organism in cell 2 is the compound cell.
- **Advice names what it offers.** The verdict's next step names the
  organisms (with row counts) where a constant is measured, and for a Ki,
  the inhibitors the organism searched has rows for, counted the way the
  inhibitor choice counts them (human AChE and donepezil: Mus musculus and
  Tetronarce californica, or tacrine, edrophonium, ...). A Ki with no
  inhibitor named, in an organism with no Ki row at all (rat acetyl-CoA
  carboxylase), says the organism is what is missing, not "name it with
  --inhibitor", and lists first the organisms where the whole model is
  measured.
- **No opt-in that would be refused again.** The resolver says which other
  organisms hold only a variant's rows (`cross_species_variant_only`); the
  TypeScript CLI and the API offer --allow-cross-species only for the rest
  (human COX-2's kcat: Mus musculus held one N580A row).
- **One list on every surface.** For a compound with no row in the organism,
  the runner sends compose's clause (`availableInTheOrganism`), so the API
  and the CLI offer the same inhibitors with the same counts as compose.
  Papers offered for a missing constant must name the enzyme in their title.
- **Irreversible inactivators everywhere.** A Ki of an irreversible
  inactivator (selegiline) is said in compose's row notes and the verdict's
  qualifications, and in Studio's constants, as the API already did.
- **Words.** A row stating a cofactor and no pH stated conditions, and is
  quoted; a labelled wild-type row carried over its paper's unlabelled one
  is said; the robustness line points to the spread section only when the
  page has one; the paired-across-tiers note says "the kcat measured with
  the Km" for a kcat; "as --isoform asked" only when the flag was passed
  (otherwise "as your description asked"); the natural substrate's counts
  follow its own name, its tie with other natural substrates is said, and
  the assay substrate ranked after it is named with its counts;
  "irreversible inactivators" agrees in number.

Not done: among inhibitors tied on every count, the order is still
alphabetical (thrombin's "Aspartame" before bivalirudin); the note says so.

### Merging the fifth round (2026-11-13)

Two ways of saying where an isoform came from met in the merge. The picks
branch passed a flag (`isoform_from_words`), the advice branch a string
(`isoform_asked`). The string is kept: notes now read "as your description
asked" or "as --isoform asked" everywhere. The advice branch had named its
`select_mode` parameter `asked`, which a local variable of the same name
overwrote inside the loop; it is `isoform_asked` again.

A paper whose own row is the probable error now supplies neither constant.
Human acetyl-CoA carboxylase carried ref 676983's Km of 0.0002 mM, 170-fold
below every other Km row, while the note said ref 676983 was not used. It
now carries ref 702459's pair (0.048 mM, 2.9 1/s).

The picks branch's matched-pair limit (a pair more than 10-fold from the
constants' own picks is not carried) also changes a run the advice branch
checked: "acid phosphatase" in Homo sapiens now carries Km 0.36 mM (ref
134741) beside kcat 14.1 1/s (ref 663781), not ref 663781's pair (4.7 mM,
26.4 1/s), and says why. It is still fully measured.
