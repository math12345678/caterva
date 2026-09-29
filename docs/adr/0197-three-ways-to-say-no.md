# ADR 0197: Three ways to say no

**Status:** Accepted

**Date:** 2026-08-23

## Context

The question that started this whole sequence was *"is the AI agent pipeline
working?"*. Answering it took an afternoon of manual `curl`, and the answer
turned out to be three separate configuration failures, none of which
anything in Terrium reported:

- **Groq** — the configured model `llama-3.3-70b-versatile` had been retired
  and returned HTTP 404 (ADR 0190).
- **SiliconFlow** — key valid, account balance empty. It answers **HTTP 200**
  with an error body.
- **TokenRouter** — the key is malformed; the API wants a `tr_` prefix.

Two of five providers are unusable today. Nothing said so.

From inside Terrium all three are identical, and so is a correct
fall-through: `resolveQueryWithLLM` flattens every failure into `null` and
classifies by keyword instead. That flattening is *right* in production — a
student's simulation should not fail because a vendor is down — which is
exactly why the diagnosis cannot live there. The pipeline kept answering; it
just quietly stopped using the LLM.

## Decision

**One command that asks each provider, and reports four states.**

`make llm-doctor` sends one small completion per provider that has a key,
using the model Terrium would actually send.

| state | meaning |
|---|---|
| `ok` | answered with a usable completion |
| `unconfigured` | no key — absent, not a fault |
| `broken` | answered, and the answer was a refusal |
| `unreachable` | no answer at all: DNS, timeout, refused |

`broken` and `unreachable` are split because one is the provider's answer and
the other is the absence of one, and only the second might be the checking
machine's network.

**A completion, not a `/v1/models` listing.** The listing is cheaper and
proves less: SiliconFlow listed its models perfectly while refusing every
completion, and Groq listed models while the *configured* one was absent.
Only a real completion exercises key, endpoint, model id and quota together —
the combination that actually broke.

**A 200 is not a success.** SiliconFlow returns 200 with `{"code":30001,
"message":"Sorry, your account balance is insufficient"}`. A checker that
trusts the status reports an unusable provider as healthy.

Exit **0** if any provider works, **1** if every configured one is broken,
**3** if none is configured. The 3 matters most: zero failures over zero
providers is the same shape of lie as an empty test suite passing.

## Verification

Against the real keys in this deployment:

```
  not set     openai       no OPENAI_API_KEY set
  OK          groq         answered in 1666 ms
  OK          openrouter   answered in 631 ms
  OK          mistral      answered in 488 ms
  BROKEN      siliconflow  account balance or quota exhausted -- the key is
                           valid, there is nothing to spend
  BROKEN      tokenrouter  the API key was rejected (check for a required
                           prefix or a stale key)

  3 provider(s) usable. Set LLM_PROVIDER to one of: groq, openrouter, mistral.
```

It independently found both failures that had taken manual investigation, and
named each in terms somebody can act on.

### It got one wrong first, and that is the interesting part

The first run reported **Groq BROKEN** — *"answered 200 with no completion
content"*. Groq was fine; 78 queries had gone through it an hour earlier.

The probe asked for `max_tokens: 8`. `openai/gpt-oss-120b` is a reasoning
model: it spent the entire budget on reasoning tokens and returned
`finish_reason: "length"` with empty content. Measured directly — at 8 tokens
the content is `''`, at 64 it is `'ok'`.

**A check that condemns something working is worse than no check**, because
the report is acted on: this one would have sent somebody to fix the only
provider that had just produced every measurement in ADR 0191 through 0170.
Fixed by raising the budget to 256 *and* by treating `finish_reason: "length"`
with empty content as `ok` — the key authenticated, the model existed, tokens
were generated. Both halves are asserted, including that empty content for
any *other* reason is still `broken`, so the fix cannot mean "accept every
empty answer".

Also fixed: the abort timer was never cleared, so each probe held the event
loop open for its full 20-second timeout. A six-provider run now takes 4
seconds.

Mutations, `docs/mutations/adr-0197-llm-doctor.json`, **4 caught, 0 not
caught**:

| id | mutation | caught |
|---|---|---|
| D1 | a 200 is accepted without reading the body | yes |
| D2 | a provider with no key reported as broken | yes |
| D3 | nothing configured exits 0 instead of 3 | yes |
| D4 | a reasoning model that used its budget called broken | yes |

Full api-server suite: **748 tests, all passing** — 18 of them new.

## Consequences

The original question now has a one-line answer, and so does its follow-up:
*which* provider. `/pipeline/status` already reports whether a provider is
selected (ADR 0190); this reports whether the selected one works, which is a
different fact and was the one nobody had.

**Two things for the operator, neither a code defect:**
`SILICONFLOW_API_KEY` is valid with an empty balance, and
`TOKENROUTER_API_KEY` is malformed. Both are usable again once fixed; nothing
in this repository can fix them.

**What this does not check.**

- **`explain` matches on substrings** — "balance", "does not exist",
  "invalid_api_key". A vendor phrasing the same refusal differently falls
  through to the raw HTTP line: honest, but unhelpful, and untested.
- **It is not a capacity test.** A 429 is reported as `broken` with the note
  that the key works. One probe says nothing about throughput, and ADR 0190's
  rate-limit trap is a reminder that free tiers fail under load in ways a
  single request never shows.
- **One model per provider.** Whichever `LLM_MODEL` or the provider default
  names. A provider can be `ok` here and fail on a model Terrium is later
  configured to use.
- **Nothing runs this automatically.** It is not wired into `make guards` or
  the server's health endpoint, both of which would make network calls in
  places that must not depend on the network. Somebody has to run it.
