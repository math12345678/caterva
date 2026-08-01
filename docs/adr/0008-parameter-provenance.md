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
