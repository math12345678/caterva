# ADR 0040: The findings never reached the student

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0027 (the same defect, one layer in), ADR 0038 (the same
defect, at the runner), ADR 0024, 0028, 0029, 0032

## Context

Terrium exists for a student in a teaching lab. Lisa Jeske's objection was
about exactly that person: they read a number off a screen and believe it.

Everything built in response to the professors' feedback was verified end to
end — through the resolver, across the wire, into `ScienceAgentResult`. Then
`literatureResolver.ts` mapped the runner's payload into `ResolvedKinetic`,
and the mapping had no fields for most of it.

| Finding | ADR | Emitted by the runner | Reached the CLI |
|---|---|---|---|
| reliability axes | 0024/0027 | yes | **yes** |
| cross-species flag | 0024 | yes | **yes** |
| buffer identity | 0028 | yes | no |
| protein variant | 0029 | yes | no |
| cofactors / effectors | 0032 | yes | no |
| relatedness verdicts | 0024 | yes | no |

`assayConditions` is the subtlest. It **was** copied through — cast as
`parsed['assayConditions'] as ResolvedKinetic['assayConditions']`. Because
the target type had no `bufferIdentity`, the resolution arrived at runtime
and was invisible to every typed consumer. Present, correct, unreachable.

Nothing errored. The producer saw a successful write; the consumer saw a
complete object. This is ADR 0027's defect one layer further out, and ADR
0038's one layer further in — three instances of the same shape in the same
week, all found by looking rather than by any test.

## Decision

### 1. The fields are plumbed and rendered

`ResolvedKinetic` gains `variant` and `effectors`, and `assayConditions`
gains `bufferIdentity`. `commandResolve.ts` renders all three.

The rendering choices are the substance:

**`unstated` gets a line.** It is the majority of BRENDA, it is not
wild-type, and printing nothing would let a reader infer the enzyme as
found. Absence of a warning is not a statement, and only one of the two is
checkable.

**An absence is printed as loudly as a presence.** "In the absence of
fructose 1,6-bisphosphate" is a deliberate experimental statement, not a gap
in reporting — a Km measured without a required cofactor is a *different
measurement*, not a noisier one.

**An unresolved buffer prints no compound line.** The raw string still shows
in the conditions. Printing a resolved-looking line for an unresolved buffer
would assert an identity nobody established.

### 2. The mapping was extracted so it could be tested

`mapFoundResult` was inline inside `resolveKinetic`, which spawns Python. It
was therefore unreachable from any unit test — and it is exactly where the
defect lived. A mapping only reachable through a subprocess is a mapping
nothing tests.

## Verification, and two tests that could not fail

`resolveOutput.test.ts` (14) asserts **rendered output**, not object shape. A
field plumbed through and never printed would satisfy a shape assertion and
fail the only thing that matters.

`mapFoundResult.test.ts` (9) asserts the mapping directly.

Five mutations. Three caught immediately. **Two were not, and both were mine.**

**The rendering tests could not catch the original defect.** They mock
`resolveKinetic`, so they assert what the CLI does *with* an object rather
than whether the object is ever populated. Deleting the plumbing left all
fourteen passing. That is why `mapFoundResult.test.ts` exists — with it, the
same mutation fails four tests.

Writing a test for a defect, in a file that cannot reach the defect, is a
subtler version of the same problem than anything found so far. The test was
about the right subject and pointed at the wrong layer.

**The unresolved-buffer test passed for the worst possible reason.** It
asserted `not.toMatch(/PubChem \d/)`. With the guard removed, an unresolved
identity has no `parent_cid`, so the mutated code printed
`PubChem undefined` — which the digit class does not match. The test was
*satisfied by the exact output it existed to prevent*. It now asserts the
section is absent and that `undefined` never reaches a reader.

| Mutation | Caught |
|---|---|
| the mapping drops `variant` and `effectors` (*the original defect*) | after `mapFoundResult.test.ts` existed |
| `unstated` prints nothing | yes |
| an absent effector renders like a present one | yes |
| the buffer line prints when unresolved | after the assertion was tightened |
| the mapping defaults an absent variant to `wild_type` | yes |

## Consequences

- `ResolvedKinetic.variant`, `.effectors`, and
  `assayConditions.bufferIdentity` are new.
- `mapFoundResult` is exported. It takes `logs` as a parameter rather than
  closing over it.
- The CLI prints three new sections. `--json` is unchanged in shape; it
  spreads the result, so the new fields appear there automatically.
- `relatedness` is still **not** rendered. It is a per-candidate list that
  only exists when cross-species was opted into, and the cross-species
  warning already names the organism. Named here rather than left implied.

## What this does not fix

The web UI is unexamined. This ADR covers the CLI because that is the
surface with a test harness and the one the README documents. Whether
`mule/` shows any of it is an open question, and asserting otherwise without
looking would be the mistake this ADR is about.
