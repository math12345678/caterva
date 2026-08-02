# ADR 0011: An LLM-supplied parameter is its own origin, not a `default`

**Status:** Accepted

**Date:** 2026-08-02

## Context

`ParameterOrigin` (ADR 0008) had three values: `resolved`, `user`, `default`.
The query resolver has four paths, not three. When the LLM resolver returns a
parameter that the user did not supply and no literature lookup covers, the
resolver was labelling it:

```ts
provenance[key] = {
  origin: "default",
  note: "Value supplied by the LLM resolver; not verified against literature.",
};
```

That is a false statement at the API surface. A **default** in this codebase
is a value the project chose, documented, and can defend — the textbook figure
for a domain. An **LLM-supplied** value is a number a language model generated
from a prompt. The two carry entirely different warrants, and a student
reading `origin: "default"` has no way to tell which one they received.

Stage 4 Part 6 left this open as question 2 and named the case explicitly:

> "no source, or LLM-generated with no corroborating record, is `rejected`.
> **That last case is the one that matters.**"

It stayed open through Stages 5, 6 and 7 while the provenance contract was
built around it. Two facts made it worse than a naming quibble:

1. **Nothing tested the LLM path.** No test in the suite asserted the note, so
   the single thing distinguishing an LLM value from a default could have been
   deleted with a green suite.
2. **The distinction was carried entirely by prose.** `note` is free text.
   Nothing structural marked the value as unverified, so nothing could be
   filtered, counted, or enforced on it.

## Decision

**Add `llm` as a fourth `ParameterOrigin`.**

```ts
export type ParameterOrigin = "resolved" | "user" | "llm" | "default";
```

With three rules, all enforced by `validateParameterProvenance`:

1. **An `llm` entry must carry a note.** It has no citation by construction,
   so the note is the only thing standing between a student and a number a
   model invented. An unexplained `llm` entry is a hard violation.
2. **An `llm` entry must never carry a citation or a citation status.** This
   falls out of the existing `origin !== "resolved"` rules and is asserted
   directly, because nothing was looked up. A citation here would assert
   provenance that does not exist — worse than none, by the same reasoning
   that made a fabricated citation worse than a missing one in Stage 4.
3. **`default` is unchanged.** It still needs no note. The new requirement
   must not leak onto documented defaults, or every domain would start
   demanding explanations for values that have them already.

### Why not `rejected`, as Stage 4 proposed

Stage 4 Part 6 suggested such values be *rejected*. That was written before
Stage 5 built the two-tier `citationStatus`, and it conflates two axes:
`origin` says **where a value came from**; `citationStatus` says **how well a
citation supports it**. An LLM-supplied value has no citation at all, so
`citationStatus` does not apply to it — there is nothing to grade.

Rejecting the value outright would also hide the problem rather than surface
it. The simulation still runs, the warning travels with the value, and the
student sees `llm` plus a reason. That is Rule 2's
impossible-versus-implausible distinction applied to provenance: refuse to
*claim* what cannot be supported, without refusing to *compute*.

## Consequences

**Easier.** The API can now be filtered on origin: "show me every parameter in
this run that no human and no paper stands behind" is a structural query
instead of a substring search. A future strict mode can refuse to run a
simulation containing `llm` parameters without touching the resolver.

**Harder.** `ParameterOrigin` is a published enum, so this is a breaking change
for any consumer switching exhaustively on it. The OpenAPI spec, the generated
zod client, and the generated react-query client all had to be updated
together — a client validating against the old three-value enum would reject
its own server's responses.

**Unchanged.** Nothing about `resolved`, `user`, or `default` semantics moves.
Verified by direct assertion, not assumed.

## Verification

- 8 assertions against the compiled provenance module: `llm` + note accepted;
  `llm` without note rejected with an exact message; `llm` + citation and
  `llm` + citationStatus both rejected; `default`, `user`, `default` + note,
  and a full STRENDA-complete `resolved` entry all unaffected.
- A new suite (`src/__tests__/llmOrigin.test.ts`) covering the validator rules
  and the end-to-end resolver path — the first tests this path has ever had.
- `tsc --strict` clean across the api-server after the enum widened.

## References

- **ADR 0008** — parameter provenance, the original three origins.
- **ADR 0010** — STRENDA assay conditions; the `citationStatus` degradation
  precedent this decision deliberately does *not* reuse.
- **Stage 4 Part 6**, open question 2 — the question this closes.
- `docs/CONSTITUTION.md` Rule 2 — impossible versus implausible.
