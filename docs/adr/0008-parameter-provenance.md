# ADR-0008: Honest parameter provenance at the API surface

- **Status**: Accepted
- **Context**: see Stage 4 Part 3 (`Business/build-stages/STAGE_04_PART_03.md`)
- **Decision**: per-parameter provenance on every resolved response
- **Consequences**: `citations` is renamed (breaking), validation rejects unsound provenance

## Status

Accepted (Stage 4 Part 3, 2026-08-01).

## Context

The API returned a flat `provenance.citations` array beside the resolved
parameter block. In isolation that reads as the trust trail working across
layers, but it is structurally misleading:

- Model citations (Fisher 1930 for Wright-Fisher, Kermack & McKendrick 1927
  for SIR, ...) are attached to invented teaching defaults. Nothing in the
  response distinguishes "this value was looked up in primary literature for
  THIS query" from "this value is a convenient default, and its model has a
  canonical citation".
- The only real literature path (BRENDA/KEGG/PubMed Km lookup for
  Michaelis-Menten) pushes its citation into the same array as model
  citations, erasing which citation supports which parameter.
- A consumer cannot tell a user-supplied value (`km=0.5` in the query text)
  from a default, and cannot tell whether the resolver even tried to look
  anything up.

The earlier Stage 4 Part 2 audit (documented in
`Business/build-stages/STAGE_04_PART_02.md`) already established that
citation provenance does not survive the engine boundary: the runner drops
everything except flags. The API surface is the right place to make the
claim, and it must be honest per parameter.

## Decision

1. Rename `provenance.citations` → `provenance.modelCitations` throughout
   the API surface. This is deliberately breaking: a field named
   `citations` sitting beside a parameter block invites exactly the
   misreading this ADR removes. `modelCitations` describes the MODEL, never
   an individual parameter value. The rename applies to `openapi.yaml`, the
   orval-generated clients (`api-zod`, `api-client-react`), the queue job
   result type, the `/api/resolve` preview endpoint, the API CLI, and the
   landing app's live consumers.

2. Every response carries `parameterProvenance`, a
   `Record<string, ParameterProvenance>` with exactly one entry per key in
   `parameters`:

   - `origin: "resolved"` — the value was looked up in primary literature
     for THIS query. Carries `source` (what looked it up), `citation`
     (supports THIS value), and `organism` where relevant. The only current
     producer is the BRENDA/KEGG/PubMed Km lookup (mm + recognisable EC
     number).
   - `origin: "user"` — the value was supplied explicitly in the query text
     (`PARAMETER_PATTERN` regex extraction). An explicit user value wins
     over a literature lookup: the resolver does not silently overwrite a
     number the user typed.
   - `origin: "default"` — everything else. Nothing was looked up; the value
     is a teaching default. A failed lookup records why in `note`.

3. Structural validation runs on every resolved response before it can be
   returned (`validateParameterProvenance` in `lib/provenance.ts`). Hard
   rejections (the response must not be returned):

   - key sets of `parameters` and `parameterProvenance` differ;
   - an entry marked `resolved` has no `citation`;
   - an entry with `origin !== "resolved"` carries a `citation`.

4. Soft signals stay in the `flags` array:

   - when every parameter has origin `default`, a flag naming the absence
     ("No parameter values were resolved from literature; all values are
     defaults.");
   - when a lookup was attempted and failed, the failure message moves from
     the flags into that parameter's `note`.

5. LLM-supplied parameter values (LLM resolver path, env-gated) are
   recorded as origin `default` with a note that they were not verified
   against literature. They are not literature-resolved and not typed by the
   user; of the three allowed origins, `default` is the only honest one.

## Consequences

**Easier**: a consumer can now answer "which value in this response is
actually supported by a citation?" by inspecting `parameterProvenance`
directly, and "did the resolver find anything?" from the all-defaults flag.
The breaking rename prevents silent misinterpretation of `citations` as
value citations. The runtime validation makes the provenance contract
self-enforcing rather than convention.

**Harder**: any client reading `provenance.citations` must migrate to
`provenance.modelCitations`. The API surface is slightly larger. Tests must
cover provenance structurally (Stage 4 Part 3 Targets A–E plus five
mutation tests), which is intentional.

**Foreclosed**: claiming per-value citations at the API surface without
implementing per-value provenance. The engine boundary remains
flag-only (ADR 0007); this ADR does not extend provenance through the
engine, it makes the API's claims about parameters precise.

## Verification

Stage 4 Part 3 tests in `api-server/src/__tests__/provenance.test.ts`
(Targets A–E, the naming test, and five validation unit tests) plus five
mutation checks: citation on a default entry, dropped provenance key,
`resolved` without citation, renaming `modelCitations` back to
`citations`, and breaking the EC branch. All five were caught by the suite
(see the Stage 4 Part 3 report for before/after outputs).

## Amendment (Stage 5 Part 1): resolved citations must be locatable

- **Status**: Accepted (Stage 5 Part 1, 2026-08-01).
- **Context**: carried from Stage 4 Part 5 / the Stage 4 close — whether a
  `resolved` citation must satisfy a stricter format than a `modelCitations`
  entry. The old resolver template rendered a citation with no ref id as
  `"BRENDA (ref n/a)"`: a locator-shaped string that locates nothing.
- **Decision**: a `resolved` citation is attached to a NUMBER, so it must
  let a human re-find the exact source of that number. Locatable means the
  string carries a URL or a `(ref <id>)` with an id other than the `n/a`
  placeholder (`isLocatableCitation` in `lib/provenance.ts`). Validation
  rejects any `resolved` citation that is not locatable. The resolver
  (`formatResolvedCitation` in `lib/queryResolver.ts`) refuses to fabricate
  a locator: when the agent returns a value whose citation has no ref id
  and no URL, the parameter degrades to origin `default` with an honest
  `note` instead of claiming `resolved`. `resolved` now means "value with a
  locatable citation", not merely "value found".
- **Consequences**: a consumer can trust that a `resolved` citation can be
  re-found. A found-but-unverifiable value is reported as a default with an
  explanation, never as resolved. The strictness rule runs with the rest of
  `validateParameterProvenance` on every response.
- **Verification**: Targets A–F plus Mutation 6 in
  `api-server/src/__tests__/provenance.test.ts` (locator unit tests, the
  honest-degradation path, and the `(ref n/a)` reintroduction check).

## Amendment (Stage 5 Part 2): the golden set

- **Status**: Accepted (Stage 5 Part 2, 2026-08-01).
- **Decision**: Rule 1 for provenance — a golden set of hand-verified
  enzyme/substrate/Km/citation tuples (`Tests/test_golden_set.py`: G1 LDH
  10.73 mM/ref 740253, G2 AChE 0.09 mM/ref 649716, G3 LDH cross-species
  0.0026 mM/ref 740001), asserted end to end through the real offline
  resolution chain, mirrored at the API level (Target G in
  `provenance.test.ts`).
- **Verification**: the mutation proof (Stage 5 question 4) — flipping the
  exact-match row selection (`min`→`max`) fails G1; dropping the citation
  from the resolved branch fails 8 tests across 2 files. The trust trail
  is non-decorative.

## Amendment (Stage 5 Part 3): the verified/flagged citation-status contract

- **Status**: Accepted (Stage 5 Part 3, 2026-08-01).
- **Context**: the BRENDA cross-species flag was dropped at the runner
  boundary; the API could not tell a verified exact match from a flagged
  cross-species one except by string-matching `source`.
- **Decision**: every `resolved` entry carries `citationStatus` —
  `verified` (exact organism and substrate match from a primary source;
  BRENDA exact tier) or `flagged` (cross-species fallback). There is no
  `rejected` on a resolved entry: a citation with no source, or an
  LLM-generated one with no corroborating record, cannot support a
  resolved value at all — it manifests as origin `default` with a note.
  Validation enforces: resolved-with-citation must have a status;
  non-resolved entries must not. The runner now emits `crossSpecies` as a
  first-class field.
- **Verification**: Target H and Mutation 7 in
  `api-server/src/__tests__/provenance.test.ts`; the runner output verified
  live (`crossSpecies: true` on a cross-species lookup).

## Amendment (Stage 5 Part 4): provenance travels with the parameter, and the pairing is contract-tested

- **Status**: Accepted (Stage 5 Part 4, 2026-08-01).
- **Context**: Stage 5 question 1 — does provenance travel **with** the
  parameter or in a parallel channel? Within the science-agent boundary the
  record already travels as one unit (`KineticResult` → one JSON record →
  one `ScienceAgentResult` → one resolved branch). The real hole was
  contractual: the runner's JSON↔`ScienceAgentResult` field mapping was
  hand-maintained and untested, so a refactor could rename a field on
  either side and the value and its citation would silently drift apart.
- **Decision**: provenance travels with the parameter inside a single
  record; nothing in the resolver assembles a value and its citation from
  independent sources. The simulation engine boundary stays flag-only
  (ADR 0007) — provenance is about parameters, not simulation outputs. The
  pairing is enforced, not hoped: `parseAgentOutput` (extracted from the
  spawn callback) is the single parser, and the boundary is contract-tested
  from both directions — `Tests/test_runner_contract.py` pins the runner's
  exact JSON for golden, cross-species, not-found, and error outputs;
  `src/lib/scienceAgent.test.ts` pins parsing of the same shapes, plus
  empty/malformed/error-report handling.
- **Consequences**: a field rename or drop on either side of the boundary
  fails CI immediately. The golden set (Part 2) now covers the full chain:
  fixtures → resolution chain → runner JSON → parse → pairing → response.
- **Verification**: 4 new pytest tests and 7 new vitest tests; full suites
  green.
