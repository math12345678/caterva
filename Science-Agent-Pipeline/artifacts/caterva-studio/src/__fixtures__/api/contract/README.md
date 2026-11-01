# Contract fixtures

Real output of the contract's provenance helpers over the real engine, for
the page's component tests. Nothing here is typed by hand.

`michaelis-menten-parameters.json`, produced 2026-09-30 in the
`studio/contract` worktree:

- `searched`: `caterva compose "Michaelis Menten" --subject 2.7.1.1
  --organism human --substrate glucose`, composed and searched exactly as the
  CLI does (`pipeline.compose`, then `__main__._search_the_literature`),
  then every number through `export.provenance_of` and
  `contract.from_parameter_origin`. The BRENDA page and the NCBI, UniProt
  and PubChem answers were the committed recordings in
  `Tests/fixtures/recorded/` (the test-only `CATERVA_BRENDA_RECORDED` and
  `CATERVA_HTTP_RECORDED` variables pointed there for that one command), so
  the values are BRENDA's as fetched on the dates that README gives:
  Km 6.0 mM (BRENDA ref 641068) and kcat 40.1 1/s (BRENDA ref 739603), the
  same numbers the CLI prints for that command.
- `structure_only`: `caterva compose "Michaelis Menten"` with no subject:
  the motif library's placeholders and the default starting amounts, each
  with the sentence `ParameterOrigin.sentence()` gives it.

To regenerate, run the same calls; the JSON must not be edited by hand.
