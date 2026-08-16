# ADR 0092: A preparation of the enzyme is not the enzyme

**Status:** Accepted, implemented. One policy question deliberately open.

**Date:** 2026-08-15

**Relates to:** ADR 0029 (a mutant's constant is not the enzyme's), ADR 0031
(measuring what the parser cannot read), ADR 0024 (Jeske on reaction
conditions), ADR 0027 / 0038 (computed and not delivered)

## Context

ADR 0031 introduced `docs/commentary-residue-baseline.txt`: a record of the
BRENDA commentary Terrium cannot read, so that unread text is *reviewed*
rather than merely unparsed. Coverage has risen 73% → 92% since.

One group in that file is marked **OPEN FINDING**:

```
acrylodan
attachment polyethylene glycol side chains lysine residues does not alter Kcat
benzyl
competitive versus His tagged
immobiized
noncompetitive versus pyruvate His tagged
soluble
```

Covalent modification, affinity tags and immobilisation change kinetics.
None is a sequence change, so **ADR 0029's variant filter cannot see them.**

Measured across the corpus: **18 rows** carry such a marker, and ADR 0029
classifies every one `unstated` — eligible for selection as ordinary enzyme.

### It reaches the student

Through the real resolver, before this change:

```
resolve_kinetic_value("1.1.1.27", "Homo sapiens", "NADH", quantity="ki")
  -> value 0.00059
  -> citation notes: None
  -> search log: "BRENDA exact: 1.1.1.27, Homo sapiens, NADH (ki)"
  -> any flag mentioning the tag? False
```

That row's commentary reads *"competitive versus NADH, pH 7.5, 37 °C,
**recombinant His-tagged enzyme**"*. Terrium returned a His-tagged
construct's inhibition constant as the human LDH inhibition constant, with a
real citation attached and nothing anywhere saying what it measured.

The fact was parsed the whole time — it sits in `conditions`. It simply
never reached anyone.

This is ADR 0029 one category over. A mutant's constant is not the enzyme's;
neither is an immobilised enzyme's (diffusional limitation, altered
microenvironment), a PEGylated one's, or a tagged construct's. And it is
Jeske's own list: *"pH value, temperature, cofactors, and buffers play a
huge role"* — preparation belongs in it.

## Decision

`Tests/enzyme_preparation.py` classifies the commentary into
`native` / `immobilised` / `tagged` / `modified` / `unstated` / `absent`,
and the verdict for the winning row travels on `KineticResult.preparation`.

### `recombinant` alone is not a modification

Deliberately not matched. Recombinant expression is how most enzyme is
produced; the protein is the protein. Only the *tag* changes it, so
`"recombinant His-tagged enzyme"` is `tagged` and `"recombinant enzyme"` is
`unstated`.

Both errors are costly. Matching `recombinant` would flag most of the corpus
and train readers to skip the warning — ADR 0028's cry-wolf reasoning.
Not matching the tag is the defect above.

### Five states, because silence is not a clean bill of health

`unstated` and `native` are different facts: the second is a curator writing
"native enzyme". `is_as_isolated` is a positive test on `native` alone —
`status != "modified"` would call tagged, immobilised, unstated and absent
rows "as isolated", which is the inversion this project keeps finding.

`describe()` returns nothing for `unstated` and `absent`. A line saying
"preparation not stated" on every row is noise, and noise is how the lines
that matter stop being read.

## What is deliberately NOT decided

**Whether to exclude these rows from selection by default**, as ADR 0029
does for variants.

There is a real cost either way: excluding narrows what a student can
resolve — for some enzymes the only reported Ki *is* from a tagged
construct — while including keeps a preparation's constant eligible to be
returned as the enzyme's. ADR 0029 chose exclusion for variants, and the
argument transfers, but silently narrowing resolution is the kind of change
that should be argued for rather than slipped in beside a reporting fix.

Reporting first. The exclusion question is open, and named here so it is a
decision somebody makes rather than a default nobody chose.

## Verification

`Tests/test_enzyme_preparation.py` (17). Every commentary string tested is
real text from this repository's fixtures, not an invented example.

Three mutations, all caught:

| Mutation | Failures |
|---|---|
| the verdict never reaches the result field (log only) | 2 |
| `recombinant` alone counted as a tag | 3 |
| `unstated` reported as `native` | 4 |

### The first version delivered it to nobody

It appended to `search_log` and stopped there. `queryResolver.ts` says
plainly:

> `provenance.flags` is what the CLI and the web UI render. The resolver's
> diagnostic `logs` are not — and for four ADRs these findings reached only
> the logs, which is the same as reaching nobody.

Mine would have been the fifth. Caught by asking the question this project
asks of everything else — *does it reach the reader?* — of my own change,
one step after writing it. The verdict is now a field, and
`test_it_travels_as_a_FIELD_not_only_a_log_line` asserts on the result
object rather than the log.

`_preparation_of()` is the single derivation point, so the field and the log
line cannot disagree — deriving it twice would be ADR 0027 exactly.

## Consequences

- `KineticResult.preparation` is new and populated on both the exact-match
  and cross-species tiers.
- No selection behaviour changes; no golden value moves. 801 literature
  tests pass.
- The residue baseline's OPEN FINDING group is now read rather than merely
  reviewed. `benzyl` and `soluble` remain in the accepted tail — `benzyl`
  names a chemical group inside substrate names, and `soluble` is matched
  only in the phrase "soluble enzyme".
- The exclusion policy is open. Until it is decided, a tagged or immobilised
  value can still be returned — but never again without saying so.
