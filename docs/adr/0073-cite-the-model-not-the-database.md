# ADR 0073: Cite the model, not the database it drew numbers from

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0008 (what `modelCitations` means), ADR 0063
(attribution derived from what actually contributed), ADR 0024 (defaults
versus refusal), and Jeske's CC BY 4.0 obligations

## Context

ADR 0008 is explicit:

> `modelCitations` describes the MODEL, never an individual parameter value.

Measured across all fifteen entries in `DOMAIN_DEFAULTS`, thirteen honour
that by citing the paper that defines the model:

| domain | model citation |
|---|---|
| `sir`, `seir` | Kermack & McKendrick (1927) |
| `gillespie_ssa` (×3) | Gillespie (1977) |
| `lotka_volterra` | Lotka (1925) |
| `repressilator` | Elowitz & Leibler (2000) |
| `cell_cycle_oscillator` | Tyson (1991) |
| `wright_fisher` | Fisher (1930) |
| `two_locus_wright_fisher` | Lewontin (1964) |
| `pcr` | Mullis et al. (1986) |
| `molecular_dynamics` | Hoare & Pal (1971) |
| `monte_carlo_pi` | Metropolis & Ulam (1949) |
| **`mm`** | **BRENDA — The Comprehensive Enzyme Information System** |
| **`mm_competitive_inhibition`** | **BRENDA — The Comprehensive Enzyme Information System** |

The two Michaelis-Menten domains cited a **database**. So in an
enzyme-kinetics tool, the two domains most central to it were the only ones
whose model carried no reference to the work defining it — and Michaelis &
Menten (1913) appeared nowhere in the repository.

### It was wrong a second way

Those `parameters` are hardcoded defaults — `km: 2, vmax: 5` — used when
nothing resolved. On that path BRENDA supplied no number in the response and
was named anyway.

That is a credit claim for output the source had no part in: the same
false-provenance defect ADR 0063 refuses in the exported model's attribution
block, and under CC BY 4.0 §2(a)(6) precisely the endorsement the licence
forbids implying. Jeske raised BRENDA's licence obligations; being named as
the reference for numbers BRENDA never supplied is the sharper end of that
than any missing notice.

## Decision

Both domains cite the work that defines the model. Verified against PubMed
rather than written from memory:

- **Michaelis L., Menten M.L. (1913)** *Die Kinetik der Invertinwirkung.*
  Biochemische Zeitschrift 49, 333–369. English translation: Johnson K.A.,
  Goody R.S. (2011) Biochemistry 50(39), 8264–8269,
  [doi:10.1021/bi201284u](https://doi.org/10.1021/bi201284u) (PMID 21888353)
- **Briggs G.E., Haldane J.B.S. (1925)** *A note on the kinetics of enzyme
  action.* Biochemical Journal 19(2), 338–339,
  [doi:10.1042/bj0190338](https://doi.org/10.1042/bj0190338)
  (PMID 16743508) — the steady-state derivation the competitive form rests
  on, added to `mm_competitive_inhibition`.

The 1913 paper is cited *with* its translation because the original is in
German and this is a teaching tool; a student following the reference should
land somewhere they can read.

### BRENDA is still credited, where it earned it

Nothing is removed from BRENDA's due. It is credited per parameter in
`parameterProvenance`, in the CSV export's header, and in the exported
model's attribution block (ADR 0063) — in every case **only when it actually
supplied the value**. What changed is that it is no longer named as the
citation for a rate law it did not formulate, on numbers it did not provide.

Citing BRENDA's own database paper in Nucleic Acids Research would be
correct and is what `NOTICE` asks users to do. That is a different act from
listing the bare database name as a model reference, and the guard
distinguishes them.

## Verification

`scripts/check_model_citations_cite_models.py` refuses a `modelCitations`
entry that names a known data source without the marks of a citable work —
an author-year, a volume/page range, or a DOI.

That distinction is the whole design. `Chang A. et al. (2021) BRENDA, the
ELIXIR core data resource. Nucleic Acids Research 49(D1), D498–D508` passes;
`BRENDA — The Comprehensive Enzyme Information System` does not. A guard
that banned the string "BRENDA" would forbid the correct citation along with
the incorrect one.

`Fisher R.A. (1930) The Genetical Theory of Natural Selection. Oxford:
Clarendon Press.` is a book with no volume, pages or DOI, and passes on its
author-year alone — the guard is about model citations, not publication
formats.

Mutation: restoring BRENDA as `mm`'s citation fails the guard, naming the
domain and quoting ADR 0008.

### The selftest found a hole on its first run

`modelCitations: [""]` was accepted. The `if not entries` branch catches an
empty *list*, but a list holding one empty *string* is non-empty, and a
blank entry then matched no database name and passed — a citation list that
looks populated and names nothing. Caught by `--selftest`, which exists
because of the guard-selftest wiring added earlier this session.

`DOMAIN_DEFAULTS` is parsed out of the TypeScript rather than executed,
which is fragile; the guard refuses to report success when it parses nothing,
for the same reason `check_adr_index.py` refuses an empty directory.

## Consequences

- Two API responses change: `mm` and `mm_competitive_inhibition` now return
  a different `modelCitations` list. No test pinned the old string —
  measured, not assumed — and `tsc` plus 114 tests across the provenance,
  CSV-export and literature-backed suites are green.
- Michaelis & Menten now appear in a project built on their equation.
- The guard covers the whole table, so a sixteenth domain cannot arrive
  citing a database.
- It does not check that the cited paper is the *right* one for the model.
  That needs a reader who knows the field, and the ADR says so rather than
  implying the guard is stronger than it is.
