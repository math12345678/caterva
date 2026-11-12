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
| inhibitor | Ki rows in the organism, the chosen substrate excluded; a substrate or product of the reaction (from BRENDA's Natural Substrates and Substrates/Products tables: D-glucose 6-phosphate for hexokinase) and cofactors ranked after every other compound with a row; then the most Ki rows; then the name | -- |
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
| `"glucose-6-phosphate dehydrogenase Michaelis-Menten" --organism "S. cerevisiae"` | exit 3, "Re-run with --substrate NAME" | exit 3, "BRENDA holds no Km row for EC 1.1.1.49 in Saccharomyces cerevisiae ... The organism, not the substrate, is what is missing", listing Homo sapiens (57 rows), Escherichia coli (19), Trypanosoma cruzi (14), ...; the verdict's next step is the same sentence |
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

- **A Km and a kcat of one substrate come from one paper when one holds
  both.** `fallback_logic.resolve_kinetic_pair` resolves the two together;
  when their papers differ but some paper holds a row of each among the rows
  each was chosen from, both are taken from it. Compose marks the two
  requests `paired` (`ComposedModel.parameter_requests`) and the live
  resolver answers both from one pair; the API's runner pairs a Km or a
  kcat unless the caller sends `needsKcat: false`. Human hexokinase and
  D-glucose is now **Km 6.3 mM and kcat 40.1 1/s, both BRENDA ref 739603**
  (a human glucokinase paper, pH 7.6 and 25 C for both; the Km row is a
  K0.5 with a Hill coefficient of 1.8, which its SOURCE ROW line says), where
  the independent picks carried HK-I's 0.06 mM (ref 640237, 37 C) beside
  another paper's 60.4 1/s (ref 703624). The Km rows chosen from span 0.034
  to 6.3 mM, 185-fold, and the report says so. A lookup of a Km alone
  (`scripts/cite.py`, the Studio's constants) still takes the median,
  0.06 mM.
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
  exactly counts.
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
synonyms (donepezil under its systematic name) are not mapped.

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
