# ADR 0018: Ki (inhibition constant) resolved via per-quantity BRENDA table lookup, wired end-to-end into `RESOLVABLE_FIELDS`

**Status:** Accepted

**Date:** 2026-08-09

**Relates to:** ADR 0008 (parameter provenance), Stage 8 Part 1 "Candidate A"
(named and blocked), ADR 0012/0013/0017 (the same resolved-but-not-yet-wired
staging pattern, here carried all the way through to `RESOLVABLE_FIELDS`)

## Context

Stage 8 Part 1 named "widen literature resolution to a second field" as
Candidate A and left it blocked on a fixture that could not be captured from
the review sandbox at the time. The second field is Ki, the inhibition
constant `mm_competitive_inhibition` needs alongside Km — without it, a
competitive-inhibition simulation could only ever get Km from literature and
had to take Ki as a caller-supplied override or an unverifiable default,
which is exactly the class of thing `RequiredParametersMissingError` exists
to block.

BRENDA carries Ki in its own "Ki Values" table, structurally identical in
markup to the "KM Values" table the resolver already parsed (same six-cell
row shape: value | substrate | organism | uniprot | commentary | reference
id), just under a different nav tab (`tab49` vs. the Km tab). That similarity
made a full second parser unnecessary but also made the failure mode from
Km/Ki confusion easy to introduce by accident: a naive implementation that
merges "the resolved kinetic value" into one field per call risks exactly
the bug this ADR's tests are built to catch — a Km lookup's value silently
answering a Ki request, or vice versa, whenever one of the two is missing
for a given substrate/organism pair.

## Decision

**Km and Ki are resolved through the same pipeline with an explicit
`quantity: "km" | "ki"` parameter threaded through every layer, and each
call resolves exactly one quantity with its own independent citation.**

Concretely:

1. `Tests/brenda_client.py` gains `KI_TABLE_LABEL = "Ki Values"` and
   `parse_brenda_ki_html(...)`, which delegates to the existing
   `parse_brenda_km_html(..., table_label=KI_TABLE_LABEL)` rather than
   duplicating the row parser.
2. `Tests/fallback_logic.py`'s `resolve_kinetic_value()` takes
   `table_label: str = "KM Values"` and derives `quantity_label = "Ki" if
   table_label == KI_TABLE_LABEL else "Km"`, threading the label into both
   the BRENDA table selection and the PubMed fallback query text (so a Ki
   fallback search asks PubMed for "Ki kinetics," not "Km kinetics").
3. `science_agent_runner.py` (the Python/Node bridge) takes
   `quantity: str = "km"` and emits the resolved value under a **matching**
   output key — `value_key = "ki" if quantity == "ki" else "km"` — so the
   TypeScript side reads Ki from `"ki"` and Km from `"km"`, never the other
   way around.
4. `queryResolver.ts`'s `applyKineticResolution()` calls
   `resolveKineticValue({..., quantity: key as "km" | "ki"})`
   **independently per key**, rather than resolving once and splitting the
   result — the design that makes cross-contamination structurally
   impossible rather than merely untested.
5. `RESOLVABLE_FIELDS.mm_competitive_inhibition` is now `["km", "ki"]`.

### The regression this guards against, named explicitly

An earlier shape of this code read `agentResult.km ?? agentResult.ki` to
extract "the resolved value," which meant a Ki lookup that returned a result
object without a populated `km` field (as any real Ki-only lookup would)
fell through to the object's `ki` field, and vice versa — a Km lookup
missing `km` could read a stale `ki`. `kiProvenance.test.ts`'s "a
wrong-constant swap is never cross-applied" test exists specifically to
catch a regression back to that pattern.

## Verification

- **Real, non-mocked end-to-end citation**: `Tests/fixtures/brenda_ldh_ki_fixture.html`,
  captured live 2026-08 from `brenda-enzymes.org/enzyme.php?ecno=1.1.1.27`.
  Golden-set entries G4/G5 in `Tests/test_golden_set.py` resolve LDH
  (EC 1.1.1.27) + gossypol + *Homo sapiens* to **Ki = 0.0014 mM, BRENDA
  reference 711801** (LDH-B), and the *Mus musculus* cross-species fallback
  to Ki = 0.0007 mM, reference 654758 (*Plasmodium falciparum*, flagged
  cross-species). Both pass, independently re-run and confirmed as part of
  this ADR rather than trusted from an agent report.
- 63 Python tests across `test_fallback_logic.py`, `test_table_scoping.py`,
  `test_brenda_client.py`, `test_golden_set.py` — including a
  `mixed_tables_provider` fixture proving Ki resolves to the Ki row's value,
  not the Km row's, for the same fixture page and substrate.
- `kiProvenance.test.ts` (TypeScript, `vitest`): per-key resolution, citation
  attached to the `ki` provenance entry independently of `km`'s, cross-species
  flagging, and the hard-block rule (an unresolved Ki still blocks the
  simulation rather than defaulting).
- Full suite re-run after this ADR was written: 342/342 TypeScript tests
  (23 files) and the Python literature layer, both green.

## Consequences

**Easier.** Competitive-inhibition queries naming a real enzyme/inhibitor
pair can now resolve both Km and Ki from literature with independent
citations, closing the gap `RequiredParametersMissingError` was otherwise
permanently blocking for this domain.

**Harder.** None identified — the per-key design means adding a third
kinetic quantity later (should one ever be needed) follows the same
`quantity` threading rather than requiring new plumbing.

**Unchanged.** `RESOLVABLE_FIELDS.mm`'s `["km"]` entry, and every existing
plain-Michaelis-Menten resolution path.

## References

- Golden-set fixture `Tests/fixtures/brenda_ldh_ki_fixture.html`, captured
  live from BRENDA (`brenda-enzymes.org/enzyme.php?ecno=1.1.1.27`), 2026-08.
  LDH-B (*Homo sapiens*) + gossypol, Ki = 0.0014 mM, BRENDA reference 711801.
- ADR 0008 — parameter provenance, the `origin`/`citationStatus` contract
  this ADR's Ki entries populate the same way Km's already do.
- Stage 8, Part 1 — where this was named Candidate A and left blocked.
