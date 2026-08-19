# ADR 0127: The runner picked too

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Science-Agent-Pipeline/artifacts/api-server/src/lib/science_agent_runner.py`,
`Tests/test_runner_contract.py`

**Closes the open item recorded in:** ADR 0126

## The item, and why it was left open

ADR 0126 fixed the silent name→EC pick in the CLI's catalog and recorded
that the API runner still had it, deliberately not fixed:

> It is one call, and the fix is obvious — but the function returns
> `str | None` into an API path with no exception boundary around it, and
> this session has three other agents writing in the same tree. Changing
> the control flow of the entry point on an untested path, blind, is how a
> "correct" fix becomes an outage.

**That caution was over-stated, and reading the code showed it.** The runner
already has a clean refusal for this exact position:

```python
else:
    print(json.dumps({
        "ok": True, "found": False, "source": "ec_not_resolved", ...
    }))
    return
```

An early return with a JSON body, exercised by an existing contract test.
There was never a need to raise, and nothing needed an exception boundary.
I had reasoned about the risk instead of looking at the branch.

Worth recording because the caution was not free: it left a live defect in
the API for a pass, on the argument that fixing it was dangerous, when
fifteen lines of reading would have shown it was not.

## Decision

Three outcomes where there were two.

| candidates | outcome |
|---|---|
| 0 | `ec_not_resolved` — unchanged |
| 1 | proceed — unchanged |
| >1 | **`ec_ambiguous`**, naming them |

`ec_ambiguous` is deliberately **not** folded into `ec_not_resolved`.
UniProt resolved the name perfectly well — to more than one enzyme. Telling
a reader "could not resolve an EC number" would deny the existence of the
answer rather than asking which one was meant, and that is a *worse* message
than the silent pick it replaces: the silent pick at least produced a
simulation, while this would produce a dead end for a question that has two
good answers.

The candidates travel as `ecCandidates` as well as in the log line, for the
reason `cross_species_organisms_available` and `variant_candidates_available`
exist: a refusal that cannot name what it refused leaves the choice
unexercisable.

## The tests had to move with it

Three monkeypatches in `test_runner_contract.py` patched
`fetch_ec_number_by_name`. The runner now calls `fetch_ec_numbers_by_name`,
so those patches would have stopped taking effect — and the tests would have
reached the network instead of failing. A test that silently starts making
live requests is worse than one that breaks, because it still passes, just
slowly and non-deterministically.

They now patch the function the runner actually calls.

## Consequences

- A student asking about "lactate dehydrogenase" through the API is asked
  which of EC 1.1.1.27 and EC 1.1.1.28 they meant, instead of receiving a
  Km for whichever UniProt ranked first.
- Three mutations, all caught: restoring the silent pick, reporting the
  ambiguity as `ec_not_resolved`, and firing the refusal whenever there is
  more than *zero* candidate — the cry-wolf version, which would demand
  confirmation on every ordinary query and be ignored by the second one.
- `queryResolver.ts` does not yet render `ec_ambiguous` specially; it falls
  into the generic unresolved path, so the candidates reach the response
  and not yet the sentence. That is the next step and is smaller than this
  one — the information is now present, which is the part that was missing.
