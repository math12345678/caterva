# Stage 5 Part 5: the deliberate narrowness (question 5)

Stage: 5 (the provenance contract) · Part: 5 · 2026-08-01

## 1. Question answered

Stage 5 open question 5: **only one parameter in one domain (`km` in `mm`)
is currently resolved from literature at all. Widen it, or make the
narrowness explicit?**

## 2. The decision: not widened, and made explicit

**Widening is deliberately refused — for now.** The narrowness becomes a
per-parameter, machine-checked property of the response instead of a
hidden convention.

### Why not widen

- **mm Vmax** is the only feasible candidate (BRENDA carries Vmax data),
  but it is a new trust commitment: a parser, an implausibility filter,
  hand-verified golden tuples, runner serialization, contract tests. No
  consumer has asked for it; adding trust surface nobody uses violates the
  constitution's bias toward verified narrowness.
- **Other domains have no authoritative parameter database at all.** SIR
  beta/gamma, PCR efficiencies, drift population sizes are teaching
  defaults by nature. Widening them is not possible, only fabricatable —
  and fabrication is exactly what the provenance contract exists to
  prevent.

### How the narrowness is made explicit

- `lib/provenance.ts` now exports `RESOLVABLE_FIELDS` — the single source
  of truth: `{ mm: ["km"] }`. Extending it is a deliberate act with a
  documented price.
- `buildParameterProvenance` (domain-aware): in a domain with resolvable
  fields, every default parameter that has **no** lookup carries the note
  `No literature lookup exists for <key>; only <fields> is resolved from
  literature in this domain.` A consumer can now distinguish "default
  because the lookup failed" (km's note) from "default because nobody
  looks this up" (vmax/s0's note) from "default, nothing to say" (every
  other domain, which stays quiet).
- User-supplied values and the resolved km itself carry no such note.

## 3. The documented extension path (if widening is ever wanted)

1. Add the lookup path (e.g. BRENDA Vmax parse) to `fallback_logic.py`.
2. Hand-verify a golden tuple and add it to `Tests/test_golden_set.py`.
3. Serialize it through `science_agent_runner.py`.
4. Contract-test the boundary (runner + `parseAgentOutput`).
5. Add the field to `RESOLVABLE_FIELDS` and to Target G/H/I assertions.

## 4. Verification

- **Target I** (`provenance.test.ts`, +4): mm defaults beyond km carry the
  narrowness note naming km; user-supplied vmax carries no note; domains
  without resolvable fields stay quiet; resolved km carries the lookup
  path, not the narrowness note.
- Suite: 141 vitest tests pass, typecheck clean; full pytest suite green.

## 5. Status

Complete and committed. With this part, **all five Stage 5 open questions
are answered** (locator rule — Part 1; golden set — Part 2;
verified/flagged — Part 3; travels-with + boundary contract — Part 4;
deliberate narrowness — Part 5). The close follows as Part 6.
