# Labelled sets: hand-read answers a future rule is measured against

A labelled set is a table of rows from a recorded BRENDA page with the
answer a person read off the page and its references, so that a rule which
is supposed to find that answer can be scored for precision and recall
against something other than itself. Nothing in the product reads these
files. They exist for the plan's milestone M3 (readings and labels, ADR
0179, "What is built in this slice and what is not"), where an isozyme rule
will be judged against this table rather than against the hope that it is
right.

## `ec_2.7.1.1_homo_sapiens_glucose_km_isozymes.tsv`

The 25 Km rows for D-glucose in *Homo sapiens* on the recorded hexokinase
page `Tests/fixtures/recorded/brenda_2.7.1.1.html.gz` (BRENDA EC 2.7.1.1,
fetched 2026-09-28; its sha256 is in `Tests/fixtures/recorded/README.md`),
each labelled with the human isozyme the measurement belongs to.
`Tests/test_labelled_hexokinase_isozymes.py` parses that page with the
literature layer's own parser, in permissive mode with the organism fixed to
*Homo sapiens*, and holds this table to it in both directions: every
(value, reference) pair here is on the page, every pair the parser yields
for D-glucose is here, the commentary column is the row's own words, and the
count is 25. The parser yielded 25 rows on 2026-10-17; if it ever yields a
different number, the test says so and this paragraph is wrong until it is
re-read.

Columns, tab-separated:

| column | meaning |
|---|---|
| `reference_id` | the BRENDA reference id the row cites |
| `pmid` | the paper's PubMed id, from BRENDA's literature page for that reference (empty when the reference was not checked) |
| `km_mM` | the value as the parser yields it, in mM; `6` and `2` are the page's `6` and `2` |
| `isozyme` | `hexokinase I`, `hexokinase II`, `hexokinase III`, `glucokinase` (hexokinase IV), or `unlabelled` |
| `how_known` | how the label was read: `row_text` (the row's commentary names the isozyme), `reference_title` (the paper's title does), `accession` (the row carries the UniProt accession P35557, human glucokinase), `not_checked` |
| `commentary` | the row's commentary cell, verbatim |
| `paper_title` | the title as BRENDA's literature page prints it, when that page was read (see below); empty otherwise |

## How the labels were read

By hand, from the rows' own commentary and from the titles on BRENDA's
per-reference literature pages (`literature.php?e=2.7.1.1&r=<reference>`),
on 2026-09-30 (the owner's plan, from which the grouping below is taken)
and again on 2026-10-17, when six of the literature pages were fetched and
their titles and PubMed ids copied into the `paper_title` and `pmid`
columns: references 640237, 640261, 641068, 674942, 702867 and 739603.

The grouping, 25 rows:

- **hexokinase I**, 5 rows: 0.032 (640219, "recombinant hexokinase I" in
  the row); 0.06 (640237, "hexokinase I" in the row; title "human placenta
  hexokinase type I"); 0.0732 wild-type and the mutants 0.065 and 0.0841
  (674942; the rows say only "wild-type enzyme" or "mutant enzyme", the
  title says "human brain hexokinase").
- **hexokinase II**, 1 row: 0.37 (702867, "wild type hexokinase II" in the
  row; the title agrees).
- **hexokinase III**, 2 rows: 0.034 and 0.038 (640261, "hexokinase III" in
  both rows; the title agrees).
- **glucokinase**, 15 rows: 6 wild-type and the Ser-151 mutants 0.15, 0.34
  and 2.1 (641068, title "Human beta-cell glucokinase"); 3.8 (641067); 8.6
  and 2, without and with the activator RO-28-1675 (663393); 0.23, mutant
  Y214C (672188); and the seven rows of 739603 that carry the accession
  P35557: 6.3 wild-type and six variants, 2.5, 3.1, 3.2, 3.3, 3.6 and 10.6
  (the plan's table said "five mutants"; the page holds six, and the test
  pins what the page holds).
- **unlabelled**, 2 rows: 0.63 and 0.76 (702314, "wild type enzyme" with an
  activator present). Not checked on either date.

Three glucokinase labels rest on the 2026-09-30 reading alone: 641067,
663393 and 672188. Their literature pages were not fetched on 2026-10-17, so
their `paper_title` is empty and their `pmid` is the plan's. The test names
these three as the set that may have an empty title under
`reference_title`; a fourth would fail it until this file says why.

The isozyme is not what the resolver selects on. Today's resolver (ADR 0047)
keeps every row in this table on one frontier and reports a spread; which
protein a row belongs to is exactly the reading M3 is to add, and this table
is what it will be scored against.

## Licence

The values, commentary and reference ids are BRENDA's (Chang et al. 2021,
Nucleic Acids Res. 49:D498, doi:10.1093/nar/gkaa1025), licensed CC BY 4.0,
and remain so; `LICENSE` says the Apache licence does not cover them. The
labels and this file are Caterva's. Cite BRENDA with any value taken from
here.
