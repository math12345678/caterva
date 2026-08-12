# Architecture assessment — the application layer vs. the 100-stage plan

Written 2026-08-01, after reviewing the data-flow diagram against what is
actually in the repository.

## 0. The headline

The diagram is not a proposal. **Every box in it is real code that already
exists** in `Science-Agent-Pipeline/artifacts/api-server/`. It is wired to the
real engine — `terium_runner.py` does
`from Terium import terium_engine` and calls the same functions the
100-stage build has been hardening.

So the integration question is not "how do we build this." It is: *there are
two halves of this system being held to wildly different standards, and the
half with less rigour is the half the product's central claim depends on.*

## 1. What exists, verified file by file

| Diagram node | Real file |
|---|---|
| api-server `POST /simulate` | `src/index.ts`, `src/app.ts` |
| `normalizeQuery` + cache | `src/lib/cache.ts` |
| `createJob() → jobId` | `src/lib/queue.ts` |
| `resolveQuery(query)` | `src/lib/queryResolver.ts` |
| LLM resolver | `src/lib/llmResolver.ts` |
| keyword/regex fallback | `src/lib/queryResolver.ts` |
| `science_agent_runner.py` | `src/lib/science_agent_runner.py` |
| `fallback_logic.resolve_kinetic_value()` | `Tests/fallback_logic.py` |
| BRENDA → cross-species → PubMed | `Tests/brenda_client.py` |
| `terium_runner.py` (semaphore) | `src/lib/terium_runner.py`, `teriumRunner.ts` |
| `validateParameters()` | `src/lib/validate.ts`, `schemas.ts` |

## 2. Three findings, in order of how much they matter

### 2.1 The engine work is unreachable from the product

`terium_runner.py` dispatches exactly three domains:

```
run_mm(params)     -> simulate_michaelis_menten
run_sir(params)    -> simulate_sir
run_seir(params)   -> simulate_seir
```

That is it. **PCR, Monte Carlo, Wright-Fisher and Molecular Dynamics are not
exposed.** Every domain built in Stages 1, 2 and 3 — the mutation testing, the
literature-backed LJ13 verification, Kimura's fixation probability, the
`2N → N` mutation contract — cannot be reached by a user of the application.

Three stages of work, invisible to the product. This is the most immediately
actionable finding and the cheapest to fix.

### 2.2 The validation contract survives the boundary — this part is right

Worth stating plainly because it is good news and it was not guaranteed:

```python
"ok": True,
"flagged": result.flagged,
"flagReason": result.validation.flag_reason if result.flagged else None,
```

The engine's `ok` / `flagged` / `flag_reason` contract is propagated intact
into the JSON the API returns. Rule 2 holds across the language boundary. No
work needed here.

### 2.3 The trust trail has no verification discipline at all

This is the real finding.

The engine's `SimulationResult` docstring reads: *"Simulation output plus the
provenance needed for the trust trail."* But the engine has **no citation
field, no source field, no organism field.** It carries validation state, not
provenance. Grep for `citation` in `terium_engine.py` returns nothing.

Provenance lives entirely in `queryResolver.ts`, which does return
`citations: string[]`. So the chain looks like this:

```
BRENDA row  ->  fallback_logic  ->  queryResolver (citations attached)
            ->  terium_runner (citations DROPPED)
            ->  engine (simulates a bare number)
            ->  result (no provenance)
            ->  api-server (citations re-attached from the resolver)
```

The citation and the number travel in **separate channels** and are rejoined
at the end. Nothing checks that the citation attached to the response is the
citation the simulated number actually came from.

Now put that next to the product's headline claim: *every number traces back
to a citation that has been independently checked.* The engine verifies the
**mathematics** to a very high standard — closed forms, published minima,
mutation testing, independent reproduction. It verifies nothing about
**where the parameters came from**, because it never sees that information.

Concretely: if the resolver picks a Km from the wrong organism, or misparses a
BRENDA row, or the LLM resolver hallucinates a plausible value, the engine
will faithfully simulate it and the pipeline will return `ok: true,
flagged: false` with a citation attached. **The system will report VERIFIED
for a wrong number.** No test anywhere in the repository would catch this.

That is not a hypothetical risk. It is the exact failure mode the whole
product exists to prevent, sitting in the one layer the constitution has never
been applied to.

### 2.4 CI does not test the application layer at all

`.github/workflows/tests.yml` runs two steps: `Terium/` pytest and `Tests/`
pytest. Zero mentions of `api-server`, `npm`, `pnpm` or `vitest`.

The application layer *has* tests — `routes.test.ts`, `queue.test.ts`,
`rateLimit.test.ts` — and CI never runs them. So the engine has roughly eight
hundred gated tests, and the layer between the engine and the user has none
that are enforced.

## 3. What this means for the 100-stage plan

The plan has a blind spot. Stages 1–3 hardened the engine to a standard most
research software never reaches. But the plan is *entirely* engine domains, and
at this rate stages 4 through 100 will keep deepening a component that the
product cannot fully reach, while the trust-critical layer stays unverified.

The rigour stops at the engine boundary, and the product claim lives on the
other side of it.

**Recommendation: interleave.** Do not spend the next ten stages on domains 7
through 16. Spend the next two closing the gap, then resume domains with the
application layer held to the same standard.

## 4. Proposed stage revisions

### Stage 4 — Expose the engine, and put the application layer in CI

Mechanical, mostly small, high value.

- Add `run_pcr`, `run_monte_carlo`, `run_wright_fisher`, `run_molecular_dynamics`
  to `terium_runner.py`, following the existing `run_mm` pattern exactly,
  including `ok` / `flagged` / `flagReason` propagation.
- Extend `schemas.ts` and `validate.ts` for the new parameter sets.
- Add a CI job: Node, `npm ci`, `vitest run` in the api-server directory.
- **A cross-boundary contract test**, per Rule 4: a test that fails if the
  engine's `__all__` gains a `simulate_*` function the runner does not
  dispatch. Otherwise this gap silently reopens at Stage 5.

### Stage 5 — The provenance contract (the important one)

This is the constitution applied to the resolver, and it is a genuine
research-and-design stage, not a coding stage.

Open questions it must answer:

- Does provenance travel *with* the parameter through the engine, or stay in
  a parallel channel that is rejoined at the end? (Recommendation: with. A
  `ParameterSource` carried alongside each value, so the citation and the
  number cannot be separated by a refactor.)
- What is the `ok` / `flagged` / `rejected` contract for a *citation*, as
  opposed to a value? Proposal: `VERIFIED` = exact organism and substrate
  match from a primary source; `FLAGGED` = cross-species or inferred
  substrate, usable with a warning; `REJECTED` = no source, or LLM-generated
  with no corroborating record. That last case is the one that matters.
- What is Rule 1 for provenance? The numeric side has closed forms. The
  provenance side needs an equivalent: a golden set of enzyme/substrate pairs
  with hand-verified Km values and citations, asserted end to end.
- What is a mutation test for the resolver? Proposal: swap a returned Km for
  a plausible wrong-organism value and require an end-to-end test to fail.
  If nothing fails, the trust trail is decorative.

### Stage 6 onward — resume domains

With the contract test from Stage 4 in place, every new domain reaches the
product automatically, and with Stage 5's provenance contract every parameter
carries verified provenance. Domains resume from a foundation that actually
delivers them.

## 5. What I would not do

- Do not rewrite the application layer. It is reasonable code and the
  validation contract already survives it.
- Do not move the api-server into the Python repo. The language split is fine;
  the boundary just needs a contract test.
- Do not add more domains before Stage 4. Every domain added now increases the
  amount of unreachable work.
