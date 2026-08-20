# ADR 0128: The stage that failed

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts`

**Completes:** ADR 0127 (the runner emits `ec_ambiguous`; nothing rendered it)

## The finding

Neither `ec_not_resolved` nor `ec_ambiguous` appeared anywhere in the
TypeScript. Both fell into `queryResolver`'s generic branch and produced:

> Could not resolve a real **KM** value from BRENDA/KEGG/PubMed; using
> default KM.

**BRENDA, KEGG and PubMed were never asked.** Both of these stop at the
enzyme name, before any database is consulted for a value. The message names
three sources that were not involved and blames the literature for a failure
that happened two steps earlier.

That is worse than a vague message. A vague one leaves a reader looking; a
wrong one sends them away — to hunt for a substrate-name problem, a rare
organism, a gap in BRENDA's coverage — when what actually happened is that
Terrium could not tell which enzyme they meant.

The three stages send a reader to three different fixes:

| stage | what to do |
|---|---|
| enzyme identity | check the name, or give the EC number |
| substrate label | use the database's own spelling (ADR 0118) |
| organism coverage | opt in to a related organism (ADR 0024) |

A message covering two of them sends the reader to neither.

## Decision

Two new reasons, each naming its own stage. `ec_ambiguous` lists the
candidate EC numbers the runner now carries (ADR 0127) and says why it will
not choose: they are different proteins, and picking one attaches a real
citation to an enzyme the reader did not ask about.

`ec_not_resolved` says the opposite thing clearly — a problem with the
**name**, not with the literature, and that the databases were never
reached.

## The test that passed for the wrong reason

The message for `ec_ambiguous` carries a worked example:

> EC 1.1.1.27 and EC 1.1.1.28 are the L- and D- lactate dehydrogenases

and the test asserting that candidates are rendered used **those same two
numbers** as its candidate list. So `toContain("1.1.1.27")` matched the
prose whether or not the candidates were rendered at all.

Measured: replacing `ecCandidates.join(", ")` with a constant left the test
green. It now uses `3.2.1.1` / `3.2.1.2`, which appear nowhere in the
sentence, and the mutation fails it.

This is the ninth instance this session of a verification artifact asserting
something adjacent to the thing it names, and the first where the *example
inside the message being tested* was what made it vacuous. Worth noting as
its own hazard: prose written to teach a reader gives a test something to
match on for free.

## A second thing the mutations caught — about the mutations

The first attempt at this reported two of three mutations "not caught", and
both readings were wrong:

- One was a **no-op**. Adding `|| reason === "ec_not_resolved"` to a branch
  placed *after* the `ec_ambiguous` branch changes nothing, because
  `ec_not_resolved` reaches it either way. A mutation that does not alter
  behaviour tells you nothing about the tests, and reading it as "not
  caught" is an accusation against a test that was fine — exactly what
  `scripts/mutate.py` documents as failure mode 1.
- The other was the vacuous test above, which was real.

`--no-cache` was used to rule out vitest caching before concluding either
way, since a cached transform would have made every TypeScript mutation this
session unreliable. It was not caching.

## Consequences

- A student whose enzyme name is ambiguous or unrecognised is told which
  step failed and what to do, instead of being told the literature is empty.
- `ecCandidates` now reaches the sentence, not just the response body.
- Three mutations, all caught after the vacuous test was repaired: reverting
  both branches, folding the two identity failures into one message, and
  dropping the candidates from the sentence.
