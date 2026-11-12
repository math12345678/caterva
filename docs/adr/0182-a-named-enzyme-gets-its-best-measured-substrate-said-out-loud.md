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
| substrate | cosubstrates and cofactors (ATP, NAD(P)(H), FAD, FMN, CoA, water, H+, phosphate, diphosphate, SAM, O2, metal ions) set aside unless nothing else has rows; then both a Km and a kcat row in the organism; then one BRENDA files under Natural Substrates; then the most Km + kcat rows; then the name | a word of the sentence relabelled as a listed substrate (ADR 0076): "glucose 6-phosphate" is not D-glucose, and the report says the typed word was not used |
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

BRENDA live, this branch. "Before" is the 2026-11-11 baseline on main.

| description | before | after |
|---|---|---|
| `"Michaelis-Menten of granzyme B with a competitive inhibitor" --organism "Homo sapiens"` | exit 3, all three placeholders | exit 0, GROUNDED. Chose 2-aminobenzoyl-IEPDSSMEK-dnp (3 Km, 3 kcat; tied with Boc-Ala-Ala-Asp-SBzl, broken by name) and the inhibitor with the most human Ki rows: Km 0.0058 mM and kcat 4.4 1/s (BRENDA ref 652110), Ki 0.013 mM (ref 732601), all Homo sapiens |
| `"hexokinase Michaelis-Menten kinetics" --organism human` | exit 3, placeholders | exit 0. Chose D-glucose (25 Km, 61 kcat; ATP set aside): Km 6.0 mM (ref 641068), kcat 40.1 1/s (ref 739603) |
| `"acetylcholinesterase from human, Michaelis-Menten"` | exit 3, placeholders | exit 0. Chose acetylthiocholine (40 Km, 3 kcat; acetylcholine has 4 Km and no human kcat): Km 0.086 mM, kcat 93 1/s (ref 775647) |
| `"chymotrypsin follows Michaelis-Menten kinetics"` (no organism) | exit 3, placeholders; with a substrate, Musca domestica | exit 0. Chose Homo sapiens (covers Km and kcat; Bos taurus, 136 Km and 143 kcat, listed first among the others) and L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide: kcat 22.8 1/s (ref 769319); Km a labelled placeholder, because the 0.219 mM the search returned (ref 769319) is the N-succinyl compound's row (see "A value is never carried under a neighbour's name") |
| `"carbonic anhydrase in human follows Michaelis-Menten"` | exit 3, placeholders | exit 0. Chose CO2 (61 Km, 59 kcat): Km 9.3 mM (ref 729384), kcat 1e-06 1/s (ref 729224) -- the resolver's pick among CO2's kcat rows, physically absurd, unchanged here (Not done) |
| `"angiotensin-converting enzyme inhibited by captopril" --subject 3.4.15.1 --organism human` | exit 3, placeholders | exit 0. Chose angiotensin I, the natural substrate (11 Km, 3 kcat; hippuryl-His-Leu, 18 Km, listed): kcat 52 1/s (ref 669424), Ki of captopril 1e-05 mM (ref 650001); Km a labelled placeholder, because the 0.011 mM the search returned (ref 669424) is [Phe9,Arg10]angiotensin I's row. STRUCTURAL, partly grounded, 2 of 3 |
| `"xanthine oxidase inhibited by allopurinol"` | exit 3, placeholders; with xanthine, human Km and kcat and no Ki | exit 0, GROUNDED. Chose Bos taurus, the one organism with an allopurinol Ki row (the note says Homo sapiens does not cover it), and xanthine: Km 0.01208 mM (ref 766313), kcat 16.2 1/s (ref 393008), Ki 0.0018 mM (ref 676739) |
| `"glucose-6-phosphate dehydrogenase Michaelis-Menten" --organism "S. cerevisiae"` | exit 3, "Re-run with --substrate NAME" | exit 3, "BRENDA holds no Km row for EC 1.1.1.49 in Saccharomyces cerevisiae ... The organism, not the substrate, is what is missing", listing Homo sapiens (57 rows), Escherichia coli (19), Trypanosoma cruzi (14), ...; the verdict's next step is the same sentence |
| `"lactate dehydrogenase with pyruvate in human"` | exit 3, name refused | exit 0. EC 1.1.1.27 chosen (the only one of 1.1.1.27 and 1.1.1.28 with human Km rows, 6), pyruvate read from the sentence: Km 0.03 mM (ref 286469); kcat a labelled placeholder (human has none; the organisms that do are named). Verdict "STRUCTURAL (partly grounded: 1 of 2 constants measured)", next step the organism |
| `"dihydrofolate reductase with methotrexate in E. coli"` | plain Michaelis-Menten, methotrexate dropped | exit 0, competitive inhibition ("BRENDA's Ki rows for methotrexate ... state: competitive (1 row)"), 7,8-dihydrofolate chosen: Km 0.0007 mM (ref 747067), kcat 5.3 1/s (ref 674549), Ki 0.0059 mM (ref 655867) |
| `"kinetics of pepsin" --substrate hemoglobin` | uncaught `ExportRefused` traceback | exit 0. Chose Saurida micropectoralis, the organism with the most hemoglobin Km and kcat rows (no human row): Km 0.10764 mM, kcat 18.3 1/s (ref 771228) |
| `"citrate synthase Michaelis-Menten"` | exit 3, name refused | exit 0. EC 2.3.3.1 chosen (28 Km rows against 4 for 2.3.3.3), Homo sapiens, acetyl-CoA: Km 0.0077 mM, kcat 260 1/s (ref 756131). With `--organism mouse` still refused: neither EC has a mouse row |
| `"HIV-1 protease with a competitive inhibitor" --subject 3.4.23.16` | exit 3, placeholders | exit 0. Chose Human immunodeficiency virus 1 (not a binomial, read from the table's organism cells), Lys-Ala-Arg-Val-Nle-Phe(4-NO2)-Glu-Ala-Nle-Gly and indinavir (25 Ki rows): Km 0.017 mM, kcat 5.6 1/s (ref 678346), Ki 3.1e-06 mM (ref 664013) |
| `"thrombin with a competitive inhibitor in human" --substrate D-Phe-Pro-Arg-4-nitroanilide --inhibitor argatroban --antimony` | kcat = 100, Km = 0.1, Ki = 0.5, no comment | kcat = 3.5, Km = 0.00033, Ki = 6.4e-06, each with its BRENDA ref in a comment |

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
