# `Tests/` — the literature layer

Badly named, for historical reasons: this is **not** the test suite. It is
the code that finds real parameters in the scientific literature and decides
whether a value is usable. The engine's tests live in `caterva/tests/`.

This directory is what makes Caterva different from a solver with a
textbook table in it.

## The resolution chain

`fallback_logic.py` is the centre. Read it first. It takes an enzyme, a
substrate and an organism and returns either a value with its provenance or
a refusal that names what it refused.

Supporting modules, roughly in the order the chain uses them:

| module | job |
|---|---|
| `brenda_client.py`, `brenda_parse.py`, `brenda_structured.py` | fetch and parse BRENDA rows |
| `enzyme_lookup.py` | resolve an enzyme name to an EC number |
| `taxonomy.py` | NCBI lineage; decides whether two organisms are close enough to substitute |
| `protein_variant.py` | is this row measuring the enzyme, or a point mutant of it? |
| `assay_conditions.py`, `buffer_identity.py` | the conditions a value was measured under; buffers compared at the PubChem parent compound |
| `effector.py`, `effector_presence.py` | cofactors and effectors named in the commentary |
| `evidence_rank.py`, `selection_tie.py` | which of several candidate rows wins, and whether the win was a tie |
| `form_mixture.py`, `source_context.py` | facts about the candidate *pool* rather than the winner |
| `reliability.py` | Bakker's three axes |
| `citation.py`, `citation_export.py` | the reference that travels with the value |
| `epidemiology_resolver.py`, `popgen_resolver.py` | the non-enzyme domains |
| `golden_set.py`, `fixture_lineages.py` | recorded corpora the tests run against offline |

Files ending `_debug.py` and `big_test*.py` are exploration scratch, not
part of the chain.

## Three-state, everywhere

Almost every verdict in this directory has three states, not two, and the
third is always some form of *"we do not know"*:

- `resolved` / `unresolvable` / `not_reported`
- `close_enough` / `too_distant` / `unknown`
- `wild_type` / `variant` / `unstated` / `absent`
- `agreed` / `conflicting` / `not_reported`

This is the single most important convention here. "The literature has
nothing" and "the lookup failed" are different facts, and collapsing them
lets a gap in *our code* be reported as a gap in *science*.

**Write the positive test.** `status == "same"`, never `status != "different"`.
The negative form lets silence certify itself: a new state nobody thought
about passes a `!=` check by default.

## Running it

```bash
make test-lit                # this layer only
python -m pytest Tests -q
```

The suite runs offline against recorded fixtures. Network access to BRENDA,
PubChem and NCBI is often blocked in sandboxes; a test that needs the
network and cannot reach it must skip *loudly*, and
`scripts/check_no_silent_skips.py` enforces that.

## Things that will bite you

**A refusal must name what it refused.** Returning `found: false` with no
reason makes "the literature has nothing" indistinguishable from "we
withheld something for policy reasons" — and the second one demands an
opt-in the user cannot exercise if nothing told them it existed
([ADR 0024](../docs/adr/)).

**Cross-species and variant substitution are opt-in.** Lisa Jeske
(BRENDA/DSMZ) asked for these to be an active decision. Absent must read as
false.

**BRENDA is CC BY 4.0.** Attribution obligations are real and are recorded
in `NOTICE`; `scripts/check_license_consistency.py` guards them.

**`unstated` is not `wild_type`.** It is the majority of the corpus. BRENDA
does not require curators to write "wild-type", so treating silence as
wild-type would quietly convert most of the database into a claim it never
made.
