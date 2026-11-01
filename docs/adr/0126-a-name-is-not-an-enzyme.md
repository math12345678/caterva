# ADR 0126: A name is not an enzyme

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Tests/enzyme_lookup.py`, `scripts/report_enzyme_catalog.py`,
`src/cli/scientificCLI.ts`

**Relates to:** ADR 0124 (the catalog, which needed an EC number), ADR 0024
(refusals name what they refused)

## The finding

ADR 0124 removed two of the three guesses in a first query and named the
third: a student who knows only "lactate dehydrogenase" still has to get to
an EC number. Following that thread found something worse than a missing
convenience.

`fetch_ec_number_by_name` asked UniProt with `size: 1`, and
`parse_ec_number_search` took `results[0]` and then `ec_numbers[0]`. Two
silent picks. Measured:

```python
# one protein carrying two EC numbers
parse_ec_number_search({...ecNumbers: [1.1.1.27, 1.1.1.28]})  -> "1.1.1.27"

# two proteins matching one name
parse_ec_number_search({results: [{...1.1.1.27}, {...1.1.1.28}]}) -> "1.1.1.27"
```

**EC 1.1.1.27 is L-lactate dehydrogenase. EC 1.1.1.28 is D-lactate
dehydrogenase.** Different proteins, different stereoisomers, one common
name — and "lactate dehydrogenase" is the example in this repository's own
CLI help text.

This is the first step of the workflow, and the one where a silent choice
costs the most. An EC number is not a parameter; it is the **identity of the
protein** everything downstream is about. A wrong Km is a wrong number. A
wrong EC is a real, correctly formatted citation for a different enzyme —
which is precisely the failure this project exists to prevent, arriving
before any of the machinery that prevents it gets a chance to run.

`size: 1` also meant the second shape could not be detected even in
principle: asking for one answer and receiving one answer says nothing about
whether there was a second.

## Decision

`parse_ec_number_candidates` returns **every** distinct EC number in a
UniProt response, in relevance order, and `fetch_ec_numbers_by_name` asks
for 25 results rather than 1 — the same single request, a larger page.

`catalog --enzyme NAME` uses it and **refuses to pick**:

> 'lactate dehydrogenase' names more than one enzyme: 1.1.1.27, 1.1.1.28.
> These are different proteins, so Caterva will not pick one for you — a
> wrong EC number is a citation for the wrong enzyme, not merely a wrong
> value. Re-run with the one you meant.

The same shape as the cross-species and variant refusals: name what was
refused, so the choice can actually be exercised.

`parse_ec_number_search` is reimplemented on top of the plural function and
still returns the first candidate, so existing callers are unchanged. Two
parsers of one document drift (ADR 0003); there is now one.

## What is NOT fixed, and why it is recorded rather than done

`science_agent_runner.resolve_ec_number` still takes the first candidate
silently. It is one call, and the fix is obvious — but the function returns
`str | None` into an API path with no exception boundary around it, and this
session has three other agents writing in the same tree. Changing the
control flow of the entry point on an untested path, blind, is how a
"correct" fix becomes an outage.

So it is written down with the measurement rather than half-done:

**Open: the API path silently picks an EC number when a name is ambiguous.**
The candidates are now computable — `fetch_ec_numbers_by_name` exists — so
the remaining work is deciding what that path should DO with an ambiguity,
which is a product decision about an interface, not a parsing problem.

## Consequences

- The name→EC step can no longer hide an ambiguity from the CLI, and says
  which enzymes it found.
- `size: 1` is gone from the name search, so ambiguity is visible at all.
- Four mutations, all caught: reading only the first result, reading only
  the first EC on a protein, sorting the candidates (which would discard
  UniProt's relevance order and make "the first" arbitrary), and dropping
  alternative-name EC numbers.
- The runner's silent pick is now a named open item rather than an
  undiscovered one.
