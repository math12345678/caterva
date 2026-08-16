# What Terrium collects

Short version: an email address, only if you type one into the waitlist form,
and nothing else. No cookies, no analytics, no trackers, no accounts.

This is a statement of what the code does, written by reading it. **It is not
a privacy policy and it is not legal advice.** A privacy policy names a data
controller and a legal basis, and needs a lawyer — see
`Business/INCORPORATION_CHECKLIST.md`. This exists because collecting an
email address with *no* statement at all was worse than an imperfect one.

## The waitlist

**What is collected:** the email address you type, and the timestamp of the
signup. Nothing else — no name, no IP address, no browser fingerprint.

**Where it goes:** a JSON file on the server that runs the landing page
(`artifacts/api-server/data/waitlist.json`). Not a third-party mailing
service. It is `.gitignore`d, so it does not end up in the repository or its
history.

**Why:** to tell you when Terrium is ready to try. That is the only intended
use.

**Who can read it:** whoever operates that server. There is no HTTP endpoint
that returns the addresses — `/waitlist/count` returns a count and nothing
more, checked in `src/routes/waitlist.ts`.

**How long:** no retention period is set, and no deletion job exists. That is
a gap, stated rather than glossed: as written, an address stays until
somebody removes it by hand.

**How to get yours removed:** email mathlete.world@gmail.com. There is no
automated unsubscribe and no self-service deletion.

## The simulation tool

Different surface, different answer. `src/web/server.ts` stores the query
text somebody typed, the parameters, the results and a job id — and
`GET /api/jobs/history` returns the last 50 of those **to any caller**,
because the server has no authentication.

That is documented at length in [`SECURITY.md`](../SECURITY.md), including
why it is safe on localhost and not elsewhere. If you are running it for a
class, read that first.

No cookies, no `localStorage`, no analytics, no telemetry.

## Query text can be sent to an LLM provider, if someone turns it on

> **Correction (2026-08-15).** This document previously said "no third-party
> requests **from the page itself**." That qualifier made a misleading
> sentence technically true. The page does not call anyone; the *server*
> does — and a user's query text reaching OpenAI is a third-party disclosure
> regardless of which machine initiates it. Written by me, one pass earlier,
> in the document whose entire job is to describe this accurately.

`Science-Agent-Pipeline/artifacts/api-server/src/lib/llmResolver.ts` can send
the query somebody typed to an external language-model provider. It supports
six: OpenAI, Groq, OpenRouter, Mistral, SiliconFlow and TokenRouter.

What is sent: a fixed system prompt, and `{ role: "user", content: query }` —
the raw query text. Nothing else; no email, no job history.

**It is off unless somebody configures it.** The API key is read from an
environment variable (`LLM_API_KEY`, `OPENAI_API_KEY`, or a provider-specific
one). With no key set, `resolveWithLLM` returns `null` and no request is made.
No key is committed to this repository — `.env` files are gitignored and only
`.env.example` templates are tracked.

So the honest statement is conditional:

| | |
|---|---|
| default install | nothing leaves the machine |
| an LLM key configured | the query text goes to that provider, under **their** terms and retention policy, not Terrium's |

If you enable it, you are choosing to send your users' text to a third
party. That is your decision to make and your disclosure to give — read the
provider's data-processing terms, because this project has no control over
what they retain or train on.

`scripts/check_llm_disclosure.py` fails the build if the code can call an
external provider while this section is missing.

## What is deliberately not claimed here

- **That this is GDPR-compliant.** An email address is personal data. Doing
  it properly needs a named controller, a stated legal basis, a retention
  period and a deletion route. Three of those four do not exist yet.
- **That there is a policy.** There is not. This is a description of
  behaviour, which is the honest thing to publish while the policy is
  missing.
- **That any of this has been reviewed by a lawyer.** It has not.

If a school or institution is considering a deployment, this document is the
starting point for their own assessment, not a substitute for it.

## Keeping this true

`scripts/check_privacy_notice.py` fails the build if the waitlist form
collects an email while this file or the notice beside the form is missing.
A statement nobody checks is one that gets edited away in a cleanup, and the
whole reason this file exists is that collection was happening with no
statement at all.
