# ADR 0046: The two boundary guards are complementary

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0045 (`check_findings_reach_a_surface.py`, the stronger
and more general guard — this one covers the gap it cannot see by
construction), ADR 0027 / 0038 / 0039 / 0041 (the six occurrences), ADR 0043
(`claim_adr.py`, used to claim this number)

## Context

Two agents, working within an hour of each other and without knowledge of
each other's work, both concluded that the Python/TypeScript process
boundary needed a guard. Six ADRs record one defect there: a value computed
correctly on one side and never received on the other, invisible because
every test sat on one side of the boundary and none on the boundary itself.

Both guards were written. Both landed. The obvious next move is to delete
one as a duplicate.

**That would have been wrong, and the evidence says so.**

## What each one actually checks

`check_findings_reach_a_surface.py` (ADR 0045) walks every field on
`KineticResult` along `resolver → runner → TypeScript → a reader`. It is the
stronger design on that path, in three ways this ADR is not going to
duplicate: it **executes** the runner rather than reading its source, records
key **paths** so a container rename fails, and probes **all three** output
branches.

`check_runner_boundary.py` (this one) asks the mirrored question: does every
key the runner **emits** have a receiver on `ScienceAgentResult`?

Those sound like the same question. They are not, and the difference is
exactly ADR 0027.

## The measurement

Five defects replayed against both guards:

| Replay | 0045's guard | this guard |
|---|---|---|
| ADR 0027 — `ScienceAgentResult` loses `reliability` | **passes** | caught |
| ADR 0039 — runner stops emitting `poolFindings` | caught | caught |
| a new `KineticResult` field with no boundary decision | caught | caught |
| `variantCandidatesAvailable` loses its receiver | caught | caught |
| ADR 0038 — `effectors` not declared top-level | — | caught |

**ADR 0045's guard passes ADR 0027's defect**, and not through any oversight
in its implementation. Its field list comes from
`KineticResult.model_fields`, which is the right decision — a guard holding
its own copy of the field list keeps passing after a new field is added.

But `reliability` is **not a field of `KineticResult`**. It is graded inside
the runner from the result and emitted directly. So it lies outside that
guard's domain by construction, and it is precisely the field whose loss ADR
0027 is about.

The same applies to `vmax`, `disease`, `r0`, `beta`, `gamma` and their
validation objects: all emitted, none carried on `KineticResult`, all
invisible to a guard that starts from `KineticResult`.

## Decision

Keep both, with the division stated at the top of each file so the next
person does not delete one:

```
check_findings_reach_a_surface.py   every KineticResult field reaches a
                                    reader (executed, path-aware, all
                                    branches) — AUTHORITATIVE for these
check_runner_boundary.py            every EMITTED key has a receiver,
                                    including the runner-only ones
```

This guard's scope is narrowed to that gap and its docstring now opens by
pointing at the other one and saying to prefer it.

## The guard committed the defect it was written for

Worth recording separately, because it is the more useful finding.

The first version of `check_runner_boundary.py` **passed** when `reliability`
was deleted from `ScienceAgentResult` — the case named in its own docstring
as the motivating example.

The cause was one exemption list doing two jobs. `RUNNER_ONLY` meant "has no
`KineticResult` origin", and the receiver check read it as "needs no
receiver". Those are different questions, and every key in that list has no
origin *and still needs somewhere to land*.

Split into `RUNNER_ONLY` (no origin) and `NO_RECEIVER_NEEDED` (two envelope
keys, `ok` and `error`), the mutation fails.

It was found by **replaying the historical defects against the guard**, not
by reading it. ADR 0045 records the same experience from the other side —
three attempts, the first two mutation-tested and both passing on ADR 0039's
literal defect.

Two independent implementations, both of which had to be caught out by
replay before they worked. A guard's exemption list is where its blind spots
live, and reading it is not enough to find them.

## Consequences

- Both guards run in `verify_build`; both are declared in `EXPECTED_WIRING`.
- Adding a field to `KineticResult` fails until a boundary decision is
  recorded. Adding an emitted key without a receiver fails too.
- The number for this ADR was claimed with `scripts/claim_adr.py` (ADR
  0043) rather than by looking at the directory. The draft that became this
  file collided at 0042 — the eighth collision in two days — and that was
  the last one taken by looking.

## What neither guard checks

Neither sees the **HTTP** boundary. ADR 0041's defect — a route that reads a
request field and drops it — is between the client and the API server, and
both of these guards start downstream of it. That one is covered by
`allowVariantsReachesResolver.test.ts`, which posts real bodies.

Three boundaries, three mechanisms. There is no single check for "the parts
are connected", and a guard named `boundary` invites exactly that reading —
which is why both files now say what they do not cover, at the top, before
saying what they do.
