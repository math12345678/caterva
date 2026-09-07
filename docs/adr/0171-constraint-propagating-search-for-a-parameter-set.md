# ADR 0171: Search for a parameter SET, not a parameter — a blackboard architecture with constraint propagation

**Status:** Accepted

**Date:** 2026-09-07

**Relates to:** ADR 0170 (a model is a value, which is what made this
possible), ADR 0024 (the cross-species flagged tier), ADR 0010 / STRENDA
(assay conditions), ADR 0008 (parameter provenance), ADR 0013 (Vmax = kcat
x [E]0, and [E]0 is never resolved), ADR 0028 (a check that fires too
broadly stops being read).

## Context

ADR 0170 removed the model catalogue. What remained was still a chain:

```
resolveQuery()                        3,015 lines
  -> keyword match into a catalogue
  -> applyKineticResolution()
  -> applyVmaxFromKcatResolution()
  -> applyBetaGammaFromR0Resolution()
  -> applyPopgenResolution()
```

One hand-written branch per domain, executed in a fixed order, each
resolving its constants independently. Two properties of that shape matter
more than its length.

**It resolves parameters, never a parameter set.** Each `apply*` function
asks the literature for one number and records its provenance. Nothing
compares two answers. A Km measured in rat liver at pH 7.4 and a kcat
measured in *E. coli* at pH 6.0 both pass every provenance check that
exists, and their product is a Vmax describing no enzyme in any organism.

**It cannot act on what it finds.** Even once `model_compatibility.assess`
was added and the mismatch was detected, detection was the end of it. The
report said the constants came from two organisms and stopped. Nothing went
back and looked for a kcat in the organism the Km came from — although, for
most enzymes in BRENDA, one is there.

That gap is the whole product. BRENDA can tell you each value's conditions.
COPASI and Tellurium will integrate whatever you hand them. Neither asks
whether the set is jointly usable, because neither has both halves. The
missing capability is not a better lookup; it is a **search over sets under
a coherence constraint**.

## Decision

`Terium/agents/` is a blackboard architecture — the HEARSAY-II shape —
specialised to literature-grounded model building.

```
Blackboard        append-only shared state; every entry records who wrote
                  it, in which round, and under which constraints
ConstraintStore   monotone set of requirements agents have discovered
Agent             pure function of (declared reads, constraints) ->
                  (writes, new constraints, notes)
Scheduler         topological levels, parallel within a level, iterating
                  to a fixpoint on the constraint set
```

with the agents:

| Agent | Reads | Writes | Emits constraints |
|---|---|---|---|
| `scout:<quantity>` (one per constant) | — | `param:<quantity>` | no |
| `critic:structure` | `network` | `structure` | no |
| `critic:coherence` | every `param:*` | `compatibility` | **yes** |
| `executor` | all of the above | `simulation` | no |

Three decisions carry the design.

### 1. Declarations are enforced, not documented

The scheduler decides what to re-run from each agent's declared `reads`. If
an agent reads something it did not declare, the graph is wrong, the
invalidation is unsound, and the run serves a stale answer while looking
like a fresh one.

So `View` is a capability, not a dictionary: it exposes exactly the declared
keys and raises `UndeclaredRead` on anything else. An agent cannot reach the
blackboard except through its view. **The dependency graph is true by
construction rather than by discipline**, which is what makes the
invalidation sound, which is what makes the trace an audit rather than a
log.

### 2. A finding becomes a constraint only when an agent can act on it

| Finding | Becomes a constraint? | Why |
|---|---|---|
| organism mismatch | **yes** | a scout can search one organism |
| cross-species value | **yes** | a scout can decline the transfer |
| pH / temperature / buffer gap | no | `resolve_kinetic_value` selects by evidence rank and exposes no condition filter, so the requirement could not be met |
| conditions never published | no, permanently | no search finds a number the 1974 paper did not print |

An unactionable constraint is worse than none. It changes the fingerprint,
re-runs every agent, deduplicates on the next round, converges — and the
report then states that the model was built under a requirement no search
ever applied. Nothing raises and the sentence is false.
`scripts/check_constraints_are_actionable.py` reads the AST of every agent
module and fails when a raised kind is honoured by nobody.

### 3. On a tie, explore — do not choose

Two constants from two organisms is the commonest real mismatch and it is
*always* a tie: one value each. The coherence critic declines it, because
preferring whichever organism sorted first would be an invisible scientific
decision.

The answer is not a cleverer tiebreak. `search_model` runs the whole build
once inside **each** organism the literature actually offered and reports
what each yields:

```
Values came from 2 different organisms, so Terrium built the model
separately inside each rather than choosing one:
  [Homo sapiens: no measured Ki]
  [Oryctolagus cuniculus: no measured Km]
No single organism has every constant this model needs, so Terrium has not
assembled one. The measurements that would complete it, in whichever
organism you choose: Ki, Km.
```

That is a fact about the literature rather than a preference of ours, and it
is the answer a per-parameter resolver cannot produce. When no organism
completes, `ModelSearch.build` is `None` — deliberately, rather than the
mixed-organism first pass, which would hand a caller an assembled model made
of constants describing no animal.

## Consequences

**Termination is bounded, and honestly reported.** Constraints accumulate
monotonically, so a round that adds none is identical to the next: that is
convergence. It is *not* a bound on rounds — an agent emitting an endlessly
narrowing requirement runs forever. `max_rounds` stops that, and the report
says `DID NOT CONVERGE` and names the constraints still arriving rather than
presenting a partial result as finished.

**Failures are isolated but never laundered.** One scout raising does not
lose its seven level-mates, and it is recorded as a failure rather than as
an empty result — because an outage presented as a literature gap would have
Terrium tell a researcher that a measurement does not exist when a server
was down.

**Inputs are not derived.** A seeded network carries the fingerprint in
force at run start, so it looked stale the instant any critic spoke, and was
deleted out from under the agents that needed it one round in. `Entry.derived`
distinguishes them. Found by an integration test, not by inspection.

**The simulator gets the resolved network.** A network is constructed with
placeholder constants so its structure can be checked before any literature
is searched. Simulating that object after resolution would plot the
placeholders beneath a report full of citations. `with_resolved_values`
substitutes, and refuses to substitute partially: a gap in one constant
would otherwise leave that placeholder in a model that runs.

**Units are checked only where they can be.** `ReactionNetwork` carries no
units. A `ParameterRequest` may declare `expected_unit`, which is enforced;
where none is declared, nothing is verified, and the report says the unit
that was substituted rather than implying a check that did not happen.

### What this does not yet do

- The pH and temperature gaps are reported and not actionable, as above.
  Making them actionable means exposing candidate rows from
  `_best_evidenced` so a scout could prefer the row whose conditions match
  the rest of the set. That is the natural next capability and it is not
  built.
- `resolveQuery` still routes through its own chain; `parameterize` is
  registered in `COMPOSED_DOMAINS` and reachable through the runner, and
  the TypeScript front door has not been moved onto it.
