# ADR 0170: A model is a value, not a variant — the reaction-network IR, and the provenance rule that had to survive it

**Status:** Accepted

**Date:** 2026-09-06

**Relates to:** ADR 0007 (the engine's surface is the contract, and
`DISPATCH` is how that is written down), ADR 0008 (parameter provenance),
ADR 0022 (the three ODE oscillator domains), ADR 0028 (a check that fires
too broadly stops being read).

## Context

Caterva's simulable systems were a closed catalogue, and the catalogue was
written down four times:

| Where | What | Count |
|---|---|---|
| `catervaRunner.ts` | `SimulationDomain`, a string-literal union | 16 |
| `llmResolver.ts` | `SUPPORTED_DOMAINS`, a second list TypeScript never compares to the union | 13 |
| `queryResolver.ts` | `DOMAIN_DEFAULTS` | 15 |
| `caterva_runner.py` | `DISPATCH` | 16 |

kept in agreement by a test rather than by derivation, plus
`SimulationParameterSchemas` — a `Record` *total over the union*, so
sixteen hand-written Zod schemas — and seven hand-written Antimony builders
in `model_building.py`.

Adding any new biology therefore cost five coordinated edits across two
languages. The consequence was not merely inconvenience. **The language
model's entire job, in a product whose pitch is AI-assisted simulation, was
to choose one of thirteen names.** That is a router with a citation checker
attached, and it is why the system reads as a wrapper: it is one.

The comparison that matters is Tellurium, which is worth something to labs
for precisely the opposite reason — there is no catalogue. You describe a
system and it models it.

## Decision

**Make the model a value.**

`caterva/core/network.py` defines a reaction network as data: species,
parameters, reactions with stoichiometry and rate laws, plus rate rules and
assignment rules, with one compiler to Antimony. Every builder emitted the
same shape; that shape is now the interface.

`caterva/continuous/networks.py` rebuilds all seven ODE models through it,
and `caterva/tests/test_network_equivalence.py` integrates each one *both
ways* and requires the trajectories to agree. Measured, they agree to
**0.000e+00** at every point of every column, for all seven.

Three things follow that a catalogue cannot express.

**1. The parameter set becomes dynamic — and the hard rule had to survive
that.** This was the real risk. On the TypeScript side, provenance entries
are created only for keys present in `DOMAIN_DEFAULTS[domain].parameters`,
and `PARAMETER_NAMES` is a regex over 42 fixed names. For a constructed
model those fail in the worst direction: a parameter the catalogue never
heard of has no entry, and **a key with no entry is not judged**. Absence
reads as consent.

`caterva/core/network_provenance.py` inverts it. The quantities to judge come
from `network.quantity_ids()` — the model's own — so nobody enumerates them
in advance. A quantity with *no* source is refused rather than defaulted.
Species initials are judged, not only parameters. `resolved` without a
citation is refused. And the check sits at the *compile* boundary, so it
holds whichever front end built the network; today the rule lives only in
the TypeScript resolver, so anything reaching the engine another way is
unjudged. This is strictly stronger than what it generalises.

**2. Rate laws are checked against the network that owns them.** Every
symbol must resolve to a declared species or parameter; expressions only,
no statement syntax; a fixed list of mathematical functions. This is what
makes a machine-authored rate law safe to compile — rejected at
construction with the offending symbol named, rather than as a parser error
three layers down.

**3. Invariants are derived, not declared.** `conservation_laws()` computes
the left null space of the stoichiometry matrix exactly, over `Fraction`.
For SIR it derives `S + I + R` without being told epidemics conserve
people; for Michaelis-Menten, `S + P`. Rate-rule systems correctly derive
**nothing** — a rate rule may change its species by any amount, so each
contributes a column that excludes its target from the null space. Claiming
a conservation a rate rule is free to violate would be worse than deriving
none.

**And the model may propose structure, but not numbers.**
`networkResolver.ts` asks a language model for species, reactions and rate
laws — modelling choices, arguable in a paper, and exactly what it is good
for. It is the wrong thing to ask for a Km. A value the model emits
survives only if it quoted the span of the *user's own text* that states
it, and that quote is checked against the query, so fabricating an
attribution requires fabricating a substring of a text the model did not
write. Everything else is dropped and reported as needed.

The refusal is the useful answer: the response names the minimal set of
quantities that would make the system determined.

## Consequences

- `POST /api/simulate/network` runs a model nobody wrote a builder for.
  Verified end to end against the real engine, including a three-step
  cascade that is in no catalogue, whose `A + B + C + D` conservation law
  is derived from its own stoichiometry.
- **The catalogue stays.** Nothing is deprecated and no caller changes;
  `simulate_michaelis_menten` remains a better API for Michaelis-Menten
  than assembling a network by hand. What changed is that the builders are
  no longer the only way to reach the engine.
- **`DISPATCH` stays exactly as it was.** `network` composes three engine
  calls and has no single `simulate_*` for `DISPATCH` to name, so forcing
  it in would have required either a fictional engine function or a
  weakened parity check. `COMPOSED_DOMAINS` declares the category instead,
  the boundary contract test requires a composed domain to have a handler
  and to be reachable, and `check_domain_parity.py` still reports the same
  three layers agreeing on 15 domains plus the SBML escape hatch.
- One shape defect was found and fixed while doing this: the dispatch gate
  tested `DISPATCH` while the call indexed `_RUNNERS` — a guard on a
  different table from the one it protects. Harmless while the two were
  equal, wrong the moment a composed domain existed. It now gates on the
  declared domains and still reports a missing handler as a *build defect*
  rather than blaming the caller for a valid request.
- The `simulations` table's `domain` column is a Postgres enum of the
  catalogue domains, so a `network` run is not persistable to it.
  `asSimulationDomain` narrows with a runtime check at the three insert
  sites rather than an `as` cast, which would have compiled and then failed
  in the database with an error about an enum value instead of about the
  mistake.
- One Zod schema validates the *shape* of any network, replacing per-domain
  schemas on this path. It deliberately does **not** re-implement the
  symbol, stoichiometry or provenance checks: two enforcers of one rule in
  two languages drift into two rules, which is what the four duplicate
  domain lists above already demonstrate.

## What this does not yet do

`resolveQuery` still classifies into the catalogue and throws
`UnrecognizedQueryError` when it cannot. Falling through to network
construction is the next step, and it is a product decision as much as a
technical one: the honest failure mode of that path is a refusal naming
what the user must measure, and that is a different conversation with a
user than "no matching domain".
