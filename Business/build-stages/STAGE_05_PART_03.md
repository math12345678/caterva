# Stage 5 Part 3: the verified/flagged citation-status contract

Stage: 5 (the provenance contract) · Part: 3 · 2026-08-01

## 1. Question answered

Stage 5 open question 2: **what is the `verified`/`flagged`/`rejected`
contract for a *citation*, as distinct from a value?**

Per the Stage 4 close proposal, applied to this codebase's actual
resolution chain:

- `verified` — exact organism and substrate match from a primary source.
  Here: the BRENDA exact tier (`source: "brenda_exact"`).
- `flagged` — cross-species or inferred. Here: the BRENDA cross-species
  tier (`source: "brenda_cross_species"`, `crossSpecies: true`).
- `rejected` — no source, or LLM-generated with no corroborating record.
  Decided: there is **no** `rejected` on a `resolved` entry. A citation
  that cannot support the value must not be attached to a resolved value;
  it manifests as origin `default` with an explanatory `note` (the existing
  honest-degradation path from Part 1). `rejected` is the absence of
  resolution, not a fourth value status.

## 2. The defect closed

Part 2's finding: `science_agent_runner.py` dropped
`cross_species_flag` — only the `source` string survived, so the API could
only distinguish tiers by string-matching `"brenda_cross_species"`. The
flag now crosses the boundary as a first-class field (`crossSpecies`).

## 3. Changes

- `science_agent_runner.py`: emits `crossSpecies: result.cross_species_flag`
  in the found branch.
- `scienceAgent.ts`: `ScienceAgentResult.crossSpecies?: boolean`.
- `provenance.ts`: `ParameterProvenance.citationStatus?: "verified" |
  "flagged"`; validation rules — a resolved entry with a citation must
  carry a status; a non-resolved entry must not.
- `queryResolver.ts`: both resolved branches set `citationStatus`
  (`flagged` when `crossSpecies === true` or `source ===
  "brenda_cross_species"`, else `verified`).

## 4. Verification

- **Target H** (`provenance.test.ts`): exact match → `verified`;
  cross-species swap → `flagged`; missing status on resolved → violation;
  status on non-resolved → violation; verified+flagged accepted.
- **Mutation 7**: a refactor dropping `citationStatus` from the resolved
  branch is caught by the validator.
- **Live boundary check**: `science_agent_runner.py` run against live
  BRENDA — Homo sapiens query returns `crossSpecies: false`
  (km 10.73 — matching golden G1), Mus musculus query returns
  `crossSpecies: true` (km 0.0018, organism Cryptosporidium parvum).
- Suite: 130 vitest tests pass, typecheck clean; pytest full suite green.

## 5. Status

Complete and committed. Carried forward:

- question 1 — provenance travelling **with** the parameter through the
  engine (the golden set + status contract now guard both boundaries; the
  engine-internal channel question remains),
- question 5 — widening `km`-in-`mm` vs making narrowness explicit.
