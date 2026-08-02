# Stage 5 Part 4: the runner-boundary contract (question 1)

Stage: 5 (the provenance contract) · Part: 4 · 2026-08-01

## 1. Question answered

Stage 5 open question 1: **does provenance travel **with** the parameter
through the engine, or stay in a parallel channel rejoined at the end?**

Two distinct boundaries:

1. **Science-agent boundary** (Python lookup → API). The record already
   travels as one unit: `KineticResult` (value + unit + organism + source +
   citation + cross-species flag) → one JSON record → one
   `ScienceAgentResult` → one resolved branch in the resolver. Nothing
   assembles a value and its citation from independent sources. This is
   "with" — and it is now enforced.
2. **Simulation engine boundary** (parameters → tellurium). Stays
   flag-only, per ADR 0007. Provenance is about parameters, not simulation
   outputs; the engine needs the number, not its biography.

## 2. The hole closed

The runner↔`ScienceAgentResult` field mapping was hand-maintained and
untested: the JSON emitted by `science_agent_runner.py` and the TypeScript
types in `scienceAgent.ts` agreed by convention only. A refactor renaming
a field on either side (e.g. `km` → `value`, `crossSpecies` →
`crossSpeciesFlag`) would silently mis-map — the golden API test mocks the
agent, so it could never notice.

## 3. Changes

- `scienceAgent.ts`: the spawn callback's parse logic is extracted into
  `parseAgentOutput(stdout)` — a pure, exported function, the single
  parser. Empty output, unexpected JSON, Python error reports, and
  malformed JSON each produce a specific error.
- `Tests/test_runner_contract.py` (new): runs the real
  `science_agent_runner.main()` in-process with a golden `KineticResult`
  substituted for the lookup, and pins the **exact** output JSON for:
  - golden G1 (found, km 10.73, source brenda_exact, `crossSpecies: false`,
    citation dict with referenceId 740253 and title/notes nulls),
  - cross-species (`crossSpecies: true`, ref 740001, organism Sus scrofa),
  - not-found (`literatureCandidates` serialization),
  - error path (missing ecNumber → `ok: false` + message, exit 1).
- `src/lib/scienceAgent.test.ts` (new): pins parsing of the same shapes
  from the TS side (golden record field-by-field, cross-species flag,
  not-found, error report, unexpected JSON, empty output, malformed JSON).

## 4. Why this answers question 1

The citation and the number it supports are one record from Python to the
resolver; the resolver derives `parameters.km` and
`parameterProvenance.km` from that single record; and now **both sides of
the boundary are pinned by tests** that fail if the pairing is disturbed.
The chain is fully guarded end to end: fixtures → resolution chain
(golden set, Part 2) → runner JSON (Part 4, Python side) → parse (Part 4,
TS side) → pairing (Target G) → response validation (Parts 1–3).

## 5. Status

Complete and committed. Carried forward:

- question 5 — widening `km`-in-`mm` vs making the narrowness explicit
  (the deliberate decision, in writing).
