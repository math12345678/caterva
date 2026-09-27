# The LLM waterfall

One OpenAI-compatible endpoint in front of five free-tier providers. When one
runs out of quota, the next one answers.

Caterva holds keys for groq, openrouter, mistral, siliconflow and tokenrouter,
all on free tiers, all registered to `admin.terrium@gmail.com`. Any one of them
alone will hit a daily cap or a per-minute ceiling and stop working. Chained
behind a LiteLLM proxy they present a single endpoint -- `caterva-extract` --
and the proxy moves down the chain as each provider is exhausted.

Three files:

| File | What it is |
| --- | --- |
| `config.yaml` | The LiteLLM proxy config: the five deployments, the fallback chain, the retry and cooldown policy. Its header comments are the authority on every choice in it. |
| `quota.py` | Pure-Python provider ordering. Decides who to ask next from what providers reported about their own remaining quota. No network, no litellm import. |
| `test_quota.py` | 43 tests over `quota.py`. Pass with litellm absent. |

Each of those files argues for its own design in its own header. This README is
the operator's view: how to run it, and what it is and is not for. Where a
decision is explained in the source, this points at the source rather than
paraphrasing it -- two documents explaining the same decision in different
words drift apart, and then neither can be trusted.

---

## First: what an LLM is allowed to decide here

**Entity extraction and domain classification. Never a parameter value.**

The caller is `artifacts/api-server/src/lib/llmResolver.ts`, which uses it for
turning a typed sentence like "michaelis menten kinetics for hexokinase" into
an enzyme name, a substrate, an organism and a domain label. Those are language
tasks and a language model is the right tool for them.

A Km, a kcat, a temperature, a pH -- none of those ever come from a model here.
`docs/adr/0011-llm-parameter-origin.md` is the rule, and as amended on
2026-08-06 the resolver **hard-blocks** origin `llm`: an LLM-supplied parameter
throws `RequiredParametersMissingError` and names the key for the user to
supply, exactly as a missing value does. Read the ADR before touching this
directory.

This is the reason the project is worth anything to a lab, not a limitation of
it. A number a language model produced is not a measurement. The resolver used
to label such values `origin: "default"`, which is a false statement at the API
surface: a *default* is a value this project chose, documented and can defend,
and a student reading `default` had no way to tell the two apart. Closing that
gap is what makes the rest of Caterva's output checkable. A simulation whose
parameters all trace to a paper or to the person who typed them is a
simulation somebody can argue with. One where any number might have been
generated is not, and no amount of capacity in `config.yaml` changes that.

So: **adding providers here widens how reliably the language tasks get done.
It does not widen what a language model is allowed to decide.** If you find
yourself adding a deployment so that a parameter can be filled in, stop.

---

## Setup

litellm is deliberately **not** in `requirements.txt`. Nothing else in this
repository needs it, and the gateway is an optional deployment rather than a
dependency of the engine. Install it wherever the proxy runs:

```bash
pip install 'litellm[proxy]'
```

Generate the proxy's own key. It is required and has no default on purpose: a
master key with a default value is a master key everybody has, and an open port
on a laptop would otherwise be an open relay to five upstream accounts.

```bash
export LITELLM_MASTER_KEY=$(openssl rand -hex 32)
```

Run the proxy:

```bash
litellm --config Science-Agent-Pipeline/artifacts/llm-gateway/config.yaml
```

Then point the API server at it with three environment variables:

```bash
LLM_API_URL=http://127.0.0.1:4000/v1/chat/completions
LLM_API_KEY=$LITELLM_MASTER_KEY
LLM_MODEL=caterva-extract
```

**No application code changes.** The API server already accepts any
OpenAI-compatible endpoint through this generic override, and an explicit
`LLM_API_URL` wins over any named provider's default URL. The gateway is just
another such endpoint. `Science-Agent-Pipeline/.env.example` documents these
variables, the five provider keys, and which account each one belongs to; real
keys go in `.env`, which is gitignored.

Every provider key is optional. A provider whose key is unset is reported
`ABSENT` and skipped, and the waterfall runs on whatever is configured.

---

## How the order is decided

`quota.py` computes the live order. `config.yaml` carries a static fallback
order for when nothing has been measured yet.

**By measured headroom, not by price.** The usual advice is cheapest-first. For
a waterfall over free tiers that is meaningless: every tier costs the same
zero, so a price-ordered list of free providers is an arbitrary list wearing a
justification. What actually decides how long the gateway survives is
*headroom*. Sending the next request to the provider with the most measured
remaining quota drains all of them evenly and postpones the first exhaustion as
far as it will go. Providers that are actually priced come after the free ones,
ordered by a cost **the operator declares in configuration** -- `quota.py`
states no prices, because a price written into that file would be a number
nobody here measured and would go stale silently.

The full ordering, with its reasoning, is the docstring on `Ledger.order()`.

**No rate limit is hardcoded anywhere in this directory.** Not in `quota.py`,
and `rpm`/`tpm` are deliberately absent from `config.yaml`. Every such number
would be one nobody measured, it would go stale the next time a provider
changed its free tier, and it would be wrong in the worst direction: the
gateway believing it has headroom it does not, sending the request, and
failing. In this repository specifically it would be the same defect as a
fabricated Km, in a different file.

Limits are read from what providers report about themselves. Two of the five
report something this code knows how to read:

- **groq** sends `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`
  and reset timers on every call, which makes it the one provider whose
  headroom is known *before* a call fails. Documented at
  `https://console.groq.com/docs/rate-limits`.
- **openrouter** sends `X-RateLimit-Remaining` and `X-RateLimit-Reset` on
  *error* responses rather than on every call, so a healthy run leaves them
  absent. Documented at `https://openrouter.ai/docs/api-reference/limits`.

mistral, siliconflow and tokenrouter have no header names recorded in
`quota.py` at all, because their rate-limit documentation was never read for
this module. Their fields are empty rather than filled in by analogy with
groq's. Guessing that siliconflow uses groq's header names would produce a
confident misreading, which is worse than reading nothing.

---

## The availability states

`quota.py` has four. Three of them are about what a provider said; the fourth
is about whether anyone asked.

| State | Means |
| --- | --- |
| `AVAILABLE` | The provider reported remaining quota, and there is some. |
| `EXHAUSTED` | The provider reported remaining quota, and it is gone. Stays here until the reset time the provider itself gave. |
| `UNKNOWN` | The provider reported nothing this code knows how to read. |
| `ABSENT` | No key is set. Nothing was asked. |

### UNKNOWN is not AVAILABLE

This is the state the module is most careful about, and the easiest one to get
wrong by collapsing it.

A provider that said nothing has **not** said it is fine. Folding `UNKNOWN`
into `AVAILABLE` would make the gateway most confident about exactly the
providers it knows least about -- three of the five here -- and the failure
would be silent until a call came back 429. Folding it into `EXHAUSTED` would
drop working providers for not being chatty.

So `UNKNOWN` sits after everything measured-available and before everything
measured-exhausted: a measured yes beats a silence, and a silence beats a
measured no. `UNKNOWN` providers *are* tried -- they are in the chain -- but
they are tried after any provider whose headroom is a number somebody read.
`Ledger.summary()` names them, and says in words that they are unknown rather
than available.

`ABSENT` is kept separate from `UNKNOWN` for the same reason: "we asked and
learned nothing" and "we never asked" are different facts, and only one of them
is fixed by setting an environment variable.

---

## How to check it

### What works today

The ordering logic is pure Python with no network and no optional dependency,
so it can be checked exactly and offline:

```bash
cd Science-Agent-Pipeline/artifacts/llm-gateway
../../../.venv/bin/python -m pytest test_quota.py -c /dev/null --no-header -q -p no:cacheprovider
```

43 passed, with litellm not installed. The `-c /dev/null` matters: the repo
root pytest config pulls in heavy imports and turns collection into minutes.

To see the live order and the reasons behind it:

```bash
cd Science-Agent-Pipeline/artifacts/llm-gateway
../../../.venv/bin/python -c "from quota import Ledger; print(Ledger().summary())"
```

With keys set and nothing measured yet, that prints five providers `UNKNOWN`
and says so explicitly, including which three of them report no headers at all.
With no keys set it prints five `ABSENT` and names the missing variables. Both
outputs end with the statement that nothing here hardcodes a rate limit.

### status.py -- now in this directory, with different exit codes than proposed

`status.py` now exists. It answers "is the waterfall ok and how much is left"
for a person at a terminal and for a monitoring script:

```bash
cd Science-Agent-Pipeline/artifacts/llm-gateway
../../../.venv/bin/python -m status            # the order, and why
../../../.venv/bin/python -m status --json     # the same state, machine-readable
../../../.venv/bin/python -m status --probe    # spend quota to measure quota
../../../.venv/bin/python -m status --reset    # clear the persisted ledger
```

`--ledger PATH` says where the ledger lives; it otherwise follows
`$CATERVA_LLM_QUOTA_LEDGER`, and failing that a file under the user cache
directory. Reporting never writes; only `--probe` persists anything.

Exit codes AS SHIPPED. An earlier draft of this README proposed five codes,
splitting `UNKNOWN`-only from measured-available (`0` available, `1` unknown,
`2` exhausted, `3` no keys, `4` bad arguments). The implemented contract is
three, and the difference is deliberate rather than an oversight:

| Code | Meaning |
| --- | --- |
| `0` | At least one provider is `AVAILABLE` **or** `UNKNOWN` -- the waterfall has somewhere to send the next request. |
| `1` | Every provider is `EXHAUSTED` or `ABSENT`. Extraction will fail until a reset passes or a key is added. |
| `2` | The question could not be answered -- `--probe` was asked for and litellm is not installed, or the ledger path is unusable. |

**Why `UNKNOWN` exits 0 here.** The draft table made a fresh gateway exit `1`,
reasoning that a check returning OK while knowing nothing claims knowledge it
does not have. That reasoning is right about knowledge and wrong about what an
exit code is used for: a monitor branches on "should I page someone", and a
gateway with five working keys and no measurements yet is not an incident. The
normal state of three of these five providers is `UNKNOWN` forever, because
they report no headers at all -- so a nonzero code for `UNKNOWN` would be
nonzero almost always, and a signal that is always on carries nothing.

The honesty the draft was protecting is kept, in the place where it can be read
rather than inferred from a number: the output says in words that `UNKNOWN` is
not `AVAILABLE`, names which providers are in it, and states that exit `0`
**does not claim the next call will succeed**. `--json` carries the same thing
structurally as `claims.unknown_is_not_available` and `claims.ok_means`. A
caller that genuinely wants "measured available only" has the states in the
payload and can decide for itself; it cannot recover them from an exit code.

`2` exists so that "I could not check" is never read as "there is nothing
left". Those two need different responses and collapsing them pages somebody
for an outage that is not happening.

**`--probe` spends quota to measure quota.** That is not a side effect to be
engineered away; it is the only honest way to learn a provider's headroom.
Three of the five providers report nothing until a call is made, and openrouter
reports its numbers only on an error response -- so for those, the sole route
from `UNKNOWN` to a measured state is to send a real request and read what comes
back, and for openrouter, to send enough of them to be refused. A probe is
therefore a deliberate withdrawal from the same free-tier budget that entity
extraction draws on. Probe when you want to know, not on a timer, and never in
a loop. The help text says so, and a test asserts that it does.

A probe that succeeds and reports no headers leaves the provider `UNKNOWN`. One
answered call is evidence the key works, not a measurement of what is left, and
recording it as headroom would be a number nobody measured.

**Keys are never printed** -- not the value and not a prefix. Four characters is
enough to match a key against one that leaked elsewhere. Every byte the command
writes is assembled into one string and passed through a scrubber that removes
any configured key value, which covers the realistic leak: a provider rejecting
a key with a 401 that quotes it back, reported verbatim.

**The probe transport is the one unverified part.** It calls litellm, which is
not installed here, so `litellm_transport` is the only function in `status.py`
the test suite cannot exercise -- tests inject a fake. It is written so that
every way it can fail loses information rather than inventing it: if the
response headers cannot be found, nothing is recorded and the provider stays
`UNKNOWN`. It cannot manufacture a headroom figure or promote a provider to
`AVAILABLE`.
---

## Limits

Read this before relying on any of it.

**The litellm path is UNVERIFIED.** litellm could not be installed in the
sandbox where this gateway was written -- PyPI was unreachable -- so no request
has ever gone through this `config.yaml`. The proxy has not been started, the
fallback chain has not fired, and the three environment variables above have
not been observed to work end to end. `quota.py` is fully tested because it
imports nothing optional and touches no network; `config.yaml` is reviewed
prose and unexecuted configuration. Treat the first real run as the test it
has not had.

**Three of the five providers have UNKNOWN headroom by design.** mistral,
siliconflow and tokenrouter rate-limit headers were never read, so `quota.py`
holds no header names for them and can never report them `AVAILABLE`. They will
sit in `UNKNOWN` forever until somebody reads their documentation and adds the
header names with a citation. That is a known gap left open rather than papered
over with a guess.

**Nothing in the tree yet connects `quota.py` to the running proxy.** `quota.py`
decides an order and records outcomes, but no code here feeds litellm's response
headers into `Ledger.record()`, and nothing reads the `CATERVA_QUOTA_LEDGER`
path that `.env.example` documents -- `Ledger` takes its path from its caller
and persists nothing when given none. So today the ordering is a tested
function that the proxy does not consult. The static order in `config.yaml` is
what actually runs.

**The two orders can disagree, and the disagreement is visible.** With nothing
measured, `Ledger.chain()` returns its `UNKNOWN` providers alphabetically:
`groq, mistral, openrouter, siliconflow, tokenrouter`. `config.yaml` lists them
most-generous-documented-tier first: `groq, openrouter, mistral, siliconflow,
tokenrouter`. Neither is wrong, but they are not the same list, and once
`quota.py` is wired in, whichever one a request follows depends on which code
path it took.

**Free tiers change without notice.** Every documented limit cited above was
read once, on the date in each file's comments, and providers change these
without announcement. The design tolerates that -- it reads what the provider
says now rather than what a table says it used to allow -- but a URL in a
comment is not a promise that the page behind it still says the same thing.

**A waterfall raises the ceiling. It does not remove it.** Five free tiers is
more capacity than one free tier. It is still a finite daily budget, and
"never runs out" is not a guarantee this can make. When every provider is
exhausted, `Ledger.next_provider()` raises rather than returning a provider it
knows will fail, with the earliest reset time in the message. A caller that
treats the gateway as always-available will be wrong eventually. The value here
is not unlimited capacity; it is that the failure is reported honestly, states
what is known and what is not, and says when to try again.

**Prompts and responses are never logged.** `turn_off_message_logging: true` in
`config.yaml`, because a researcher's unpublished subject can be in a query and
a gateway that wrote them to disk would be a disclosure the rest of the project
is careful to avoid. The quota ledger holds counters and reset times only: no
keys, no prompts, no responses. It is safe to delete, at a cost of one wasted
429 per provider while the real state is relearned.

---

## Further reading

- `quota.py` header -- why no rate limit is hardcoded, why not order by price,
  and what the module is not.
- `config.yaml` header -- what the gateway is for, how it is wired in, and why
  `routing_strategy` is `simple-shuffle` rather than a cost- or usage-based
  strategy.
- `docs/adr/0011-llm-parameter-origin.md` -- the parameter-origin boundary and
  the 2026-08-06 amendment that hard-blocks it.
- `docs/adr/0008-parameter-provenance.md` -- the provenance contract ADR 0011
  extends. The api-server keeps its own copy as
  `artifacts/api-server/ADR_0008_Parameter_Provenance.md`.
- `Science-Agent-Pipeline/.env.example` -- every key, the account it belongs to,
  and what breaks when it is unset.
