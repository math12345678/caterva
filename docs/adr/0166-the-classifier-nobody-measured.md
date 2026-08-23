# ADR 0166: The classifier nobody measured

**Status:** Accepted

**Date:** 2026-08-23

## Context

Terrium picks a simulation domain from a plain-language query two ways: an
LLM when one is configured, and an ordered keyword table when one is not.
The LLM path has existed since ADR 0011. Nobody had ever measured whether it
beats the table it falls back to.

That question mattered more than it looked, because three separate facts had
gone unmeasured underneath it.

**The keyword table always answers.** It is first-match-wins over an ordered
list, and when nothing matches it substitutes `mm`. A caller received a
domain either way and could not tell the two apart. Every unrecognised query
was silently scored as enzyme kinetics.

**The LLM was not being called at all.** A deployment had `GROQ_API_KEY`,
`OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `SILICONFLOW_API_KEY` and
`TOKENROUTER_API_KEY` set in `.env`, and no `LLM_PROVIDER`. `getApiKey`
consults a provider's own variable only once `LLM_PROVIDER` names that
provider, so it resolved nothing, `resolveQueryWithLLM` returned `null`, and
the pipeline classified by keyword forever. `/pipeline/status` reported
`"Not set — falling back to keyword matching"`, which pointed the operator at
the one thing that was not the problem: the keys were set.

**The Groq default model had been retired.** `llama-3.3-70b-versatile`
returns HTTP 404 `"model does not exist or you do not have access to it"`.
`resolveQueryWithLLM` turns every failure into `null` alike, so a dead model
id was indistinguishable from an absent key, and both were indistinguishable
from a correct fall-through. A unit test asserted the id and passed
throughout, because a mocked `fetch` cannot return a 404 nobody asked it for.

All three are the same shape, and it is the shape this repository keeps
finding: a third state — *I could not determine this* — collapsed into a
confident second state, so the system kept answering and nothing recorded
that it had stopped knowing.

## Decision

**Measure the classifier, and report the fallback as its own state.**

`classifyDomainByKeyword` is extracted from `resolveQuery` — extracted, not
copied, so the benchmark scores the code that actually runs — and returns
`{ defaults, matched }`. `matched: false` is the fallback. `resolveQuery`'s
behaviour is unchanged.

`classifierEval.ts` holds 25 labelled queries covering all 13 LLM-exposed
domains, and runs both classifiers over them. The labels are authored, and
the file says so: each carries a one-line justification, and they are not
literature values and are not presented as any.

Two rules the harness follows, both learned by getting them wrong first:

- **A rate limit is not a wrong answer.** The first run scored the LLM at
  −7 against the baseline. The misses were HTTP 429s from Groq's 8000 TPM
  free tier, which `resolveQueryWithLLM` had flattened into the same `null`
  as a genuine miss. Counting those would have published the provider's
  billing tier as the model's accuracy. The harness now paces and retries,
  and refuses to print a comparison at all — exit 3 — while any query is
  unanswered.
- **An absent LLM is not a score of zero.** With no provider reachable the
  LLM arm returns `null` and reports NOT MEASURED.

`describeLLMConfig` replaces the boolean key check with three states, and
`/pipeline/status` reports which one. It also stops saying queries
*"will use LLM resolution"*: the LLM classifies the domain and extracts
entities, and never supplies a parameter value that survives (ADR 0011). The
status line most likely to be trusted for the trust model should not
misdescribe it — the defect ADR 0164 fixed on a different page.

The Groq default becomes `openai/gpt-oss-120b`, verified present in Groq's
live `/v1/models`.

## Correction (ADR 0167)

The keyword baseline below — 15/25, 60.0% — is **overstated**, and this
record is the reason it went unnoticed. Its labelled set was written after
reading the keyword table, so the queries had absorbed the table's own
vocabulary; the number measures a set that shares an author with the thing
it scores.

Measured on queries written without consulting the keyword table, the same
committed classifier scores **17.9%**; on queries phrased by an LLM rather
than by this author, **69.2%**. Neither is 60%.

The LLM arm's 96% and the +36-point gap are subject to the same
contamination and should be read as "on a set written to probe the keyword
table", not as an accuracy. [ADR 0167](0167-the-set-that-shared-my-hand.md)
has the sets, the ablation, and the numbers this one should have reported.

## Verification

Measured on 2026-08-23, Groq `openai/gpt-oss-120b`, 25 labelled queries,
8 s pacing:

| classifier | correct | could not determine |
|---|---|---|
| keyword table | 15/25 (60.0%) | 4 |
| LLM | 24/25 (96.0%) | 0 |

**+9 of 25 queries, +36.0 points.** Zero undetermined on the LLM arm, so the
comparison is between two answered sets rather than against a rate limit.

The keyword table's misses are structural, not random. Four queries matched
no keyword and became `mm`. The rest are ordering: `sir` is checked before
`seir`, so *"an incubation period before patients become infectious"* — the
definition of the E compartment — routes to `sir`. `cell_cycle_oscillator`
matches `"oscillator"` before `repressilator` is reached, so both
repressilator queries become cell-cycle simulations. And *"Model predator-prey
cycles in an ecosystem"* becomes **`pcr`**, because `"cycles"` is a PCR
keyword and `pcr` sits earlier in the table: an ecology question answered
with a DNA amplification model.

The LLM's single miss is defensible rather than wrong — it labelled measles
`seir`, and measles does have a latent period. The benchmark counts it as a
miss anyway; the label is the benchmark's opinion, and softening it to
protect the score would make the number mean nothing.

Mutation results, `docs/mutations/adr-0166-classifier-three-state.json`:

| id | mutation | caught |
|---|---|---|
| M1 | the keyword fallback reports itself as a genuine match | yes — 4 tests |
| M2 | provider keys present but unselected reported as no keys | yes — 2 tests |

M1 leaves the returned domain unchanged, so every test asserting only on the
domain still passes; only a test asking whether a keyword matched can see it.
Both restores were verified with `diff` against a pre-mutation copy and both
reported identical.

Full api-server suite: 645 tests, 645 passing.

## Consequences

An operator whose keys are ignored is now told which of the two problems they
have. A future change to the keyword table shows up as a named test failure —
*"routes 'predator-prey cycles' to pcr"* — rather than as a score quietly
moving. And the +36 points is now a number somebody can re-run rather than a
belief.

**What this does not check.**

- **Nothing about parameter values.** This measures domain classification
  only. The trust model is untouched: `origin: "llm"` is still blocked
  identically to `origin: "default"`.
- **One provider, one model, one run.** `openai/gpt-oss-120b` on Groq. No
  claim is made about the other four configured providers, about run-to-run
  variance, or about temperature sensitivity.
- **25 authored queries.** Small, and written by the same person who read the
  keyword table beforehand. The ordering traps were chosen *because* the
  table looked likely to fail them, which raises the LLM's margin above what
  a neutrally-sampled set would show. The set is not a random sample of
  student questions and should not be read as one.
- **No offline check that a remote model id still exists.** The stale Groq
  default was found by querying the provider. Nothing in the suite would
  catch the next retirement — the mutation set says so explicitly rather
  than implying coverage it does not have.
- **The keyword table is not fixed.** Its ordering defects are measured and
  pinned by tests, not repaired. Reordering it is a separate decision with
  its own regression risk, and this record does not make it.
