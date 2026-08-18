# Standing brief for coding agents on Terrium

Paste this into any agent working on this repository. It is short on
purpose. Everything here was written after an agent got it wrong.

Two ready-to-paste prompts — one that corrects an agent which worked here
before, one that sets a fresh agent going — are in
[`AGENT_BRIEFING.md`](AGENT_BRIEFING.md). Human contributors want
[`../START_HERE.md`](../START_HERE.md) instead.

## The one rule everything else follows from

**Nothing is real until it is verified against something that is not this
codebase.** A closed-form solution, an independent integrator, a published
value, a captured primary source. The suite deliberately does not check the
solver against itself. See `docs/CONSTITUTION.md`.

## Before you claim you are done

```bash
python3 scripts/verify_build.py --quick     # the guards, ~30s, offline
```

If it does not print `ALL CHECKS PASSED`, you are not done. Do not report
success with a failing guard and an explanation of why the failure is fine.
If a guard is genuinely wrong, fix the guard and say so explicitly.

For anything touching the API server, also:

```bash
cd Science-Agent-Pipeline/artifacts/api-server && npx tsc --noEmit -p . && npx vitest run
```

## Do not invent capability

The most damaging thing done to this repo so far was declaring three
simulation domains (`lotka_volterra`, `cell_cycle_oscillator`,
`repressilator`) across the TypeScript union, the Zod schemas, the test
fixtures, the dispatch table and the runner handlers — when
`simulate_lotka_volterra` **did not exist in the engine**. Every layer
type-checked. Every request to those domains would have raised
`AttributeError`.

Order of construction is always: **engine implementation → verification
against an independent result → mutation test → ADR → only then the API
surface.** Never the reverse. `scripts/check_domain_parity.py` now enforces
the endpoint of this, but it cannot tell you the science is right.

## The engine is the contract (ADR 0007)

When Python and TypeScript disagree about what exists, **Python's
`__all__` and `DISPATCH` win** and TypeScript is updated to match. Someone
deleted two real, working domains (`monte_carlo_pi`,
`gillespie_ssa_replicates`) from `DISPATCH` to silence a stale TypeScript
union. That is backwards and broke five contract tests.

## Parameters must be literature-backed, and nothing may be hardcoded

Every parameter reaching a simulation carries a `ParameterProvenance` with
an `origin` of `resolved` (literature, with a locatable citation), `user`
(explicit in the query), or it does not run at all. `default` and `llm`
origins are hard-blocked by `RequiredParametersMissingError`.

- A citation must be **locatable** — a real ref id or URL. `BRENDA (ref n/a)`
  is not a citation.
- Never fabricate a value to make a lookup succeed. `found: false` is a
  correct answer.
- STRENDA (pH/temperature) governs enzyme kinetic constants **only** —
  `km`, `ki`, `kcat`, `vmax`. Applying it to anything else is a hard
  provenance violation that throws at runtime (ADR 0021).

## Write the test that would have failed

A test that passes both before and after your change proves nothing. For
any non-trivial change, deliberately break the thing you just fixed,
confirm your new test fails, revert, confirm it passes. Say in your report
that you did this, and what failed. Reports that claim a mutation test
without naming what broke are not trusted here.

## Environment gaps are not free

`stdpopsim` cannot install in some sandboxes, so 9 popgen tests fail there.
For as long as that was "the known gap", it was also an unmonitored region
— and it hid a real crash for its entire existence (ADR 0021). If an
environment gap disables a code path, add a mocked substitute that keeps
the path covered.

## Do not write summary documents

No `BUILD_STATUS_SUMMARY.md`, no `COMPLETE_SESSION_SUMMARY.md`. Durable
reasoning goes in an ADR (`docs/adr/`) or a build-stage report
(`Business/build-stages/`). Prose describing what you just did, in past
tense, addressed to nobody, is bloat — several thousand lines of it already
had to be cleaned up.

## Concurrency

Multiple agents write to this tree simultaneously. Consequences:

- Re-read a file before editing it. Code you wrote an hour ago may not be
  the code that is there now — this has already happened.
- Run the guards **immediately before** reporting, not at the start of your
  work.
- If `.git/index.lock` blocks you, check `ps aux | grep git` for a live
  process before removing it.
