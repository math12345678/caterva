# What Caterva collects

Short version: Caterva itself stores an email address, only if you type one
into the waitlist form. No cookies, no analytics, no trackers, no accounts.

The two marketing pages — `mule/index.html` and `caterva-site/index.html` —
make no third-party request at all as of 2026-08-16. The Google Fonts links
that used to hand every visitor's IP to Google on page load are gone.

Two pages still do: the dashboard and the API docs load Chart.js, Swagger UI
and Redoc from `cdnjs.cloudflare.com` and `cdn.jsdelivr.net`, so a visitor's
IP reaches Cloudflare or Fastly there. Those are running code rather than
typography, so removing them is a different job, and it is not done. Both are
described in
[Fonts and scripts the pages load from other people's servers](#fonts-and-scripts-the-pages-load-from-other-peoples-servers).

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

**Why:** to tell you when Caterva is ready to try. That is the only intended
use.

**Who can read it:** whoever operates that server. There is no HTTP endpoint
that returns the addresses — `/waitlist/count` returns a count and nothing
more, checked in `src/routes/waitlist.ts`.

**How long:** no retention period is set, and no deletion job exists. That is
a gap, stated rather than glossed: as written, an address stays until
somebody removes it by hand.

**How to get yours removed:** email admin.terrium@gmail.com. There is no
automated unsubscribe and no self-service deletion.

## Fonts and scripts the pages load from other people's servers

This section is the one thing here that affects **every visitor**, including
someone who reads a page and leaves without typing anything.

Each public page asks the visitor's browser to fetch files from a CDN. The
browser cannot do that without telling the CDN who is asking, so the visitor's
IP address, their browser's `User-Agent`, and the address of the Caterva page
they were on reach a third party before the page has finished rendering. No
click, no form, no consent.

| page | goes to | for |
|---|---|---|
| `mule/index.html` | *nothing* | — |
| `caterva-site/index.html` | *nothing* | — |
| `src/web/dashboard.html` | `cdnjs.cloudflare.com` | Chart.js 3.9.1 |
| `src/web/server.ts` (API docs) | `cdnjs.cloudflare.com`, `cdn.jsdelivr.net`, **and still `fonts.googleapis.com` in the published tree** | Swagger UI, Redoc, Montserrat/Roboto |

> **Correction (2026-08-16, hours after the update below).** That update, and
> the commit message of ce91290, both said the Google Fonts link had been
> removed from all three pages. Two of three. The removal in
> `src/web/server.ts` was written but the file was never staged, so the
> commit's message described work the commit did not contain, and the API
> docs page in the published tree still fetches Montserrat and Roboto from
> Google on every view.
>
> The fix is sitting in the working tree. It cannot be committed on its own:
> `src/web/server.ts` currently carries ~260 further uncommitted lines wiring
> up a refactor in progress elsewhere (`model-comparison.ts` renaming
> `compareModelPair`/`rankModelsByFit`), and committing the file would drag
> that half-finished work into the repository. It lands when that does.
>
> Recorded here rather than quietly corrected, because the whole subject of
> this document is not making claims wider than the facts, and this was the
> third unverified claim in three passes.

> **Update (2026-08-16).** The Google Fonts requests described below are gone.
> All three pages that loaded `fonts.googleapis.com` and `fonts.gstatic.com`
> now resolve their type locally: the named faces are kept first in the stack,
> so a visitor who already has Inter Tight or JetBrains Mono installed still
> gets them, and everyone else falls through to their own system UI font. No
> file was downloaded and nothing was vendored — the webfont link was simply
> removed and the fallback chains, which already existed, were widened to
> include the modern system faces instead of stopping at Arial.
>
> **The two marketing pages now make no third-party request at all.** What
> remains is the dashboard and the API docs page, which load Chart.js, Swagger
> UI and Redoc as functioning code rather than decoration; those are described
> under the supply-chain heading below and are not yet closed.

**Why this is a legal question and not a performance one.** A visitor's IP
address is personal data under GDPR Article 4 — settled by the CJEU in
*Breyer* (C-582/14, 2016). On 20 January 2022 the Landgericht München I
(Az. 3 O 17493/20) held that embedding Google Fonts this way, so that a
visitor's IP reaches Google without consent, breaches GDPR Article 6, and
awarded the visitor €100 with penalties of up to €250,000 for continuing.
Sending that address to a US server also engages Chapter V (Articles 44–46),
which wants an adequacy decision or Standard Contractual Clauses first.

Caterva is aimed at students, including students in the EU.

**The fix is to self-host.** The fonts are licensed for it — Inter, IBM Plex
Mono and JetBrains Mono are SIL Open Font License 1.1, Montserrat and Roboto
likewise or Apache-2.0 — so downloading the files into the repository and
serving them from the same origin removes the third-party request entirely
and changes nothing a visitor sees. That has **not been done yet**; this
section records the exposure rather than claiming it is closed.

### The same tags are a supply-chain risk

None of the three `<script>` tags above carries an `integrity=` attribute, so
the browser runs whatever those CDNs return without checking it against a
known hash. One of them is worse:

```
https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js
```

`@next` is not a version. It resolves to whatever was most recently published
under that tag, so the code served changes without anyone here deciding it
should.

**Checked on 2026-08-16, and it is worse than "unpinned".** jsDelivr's own
package API (`data.jsdelivr.com/v1/packages/npm/redoc`) reports:

```
"tags": { "latest": "2.5.3", "next": "3.0.0-rc.0" }
```

So this page has not merely been serving an unpinned version — it has been
serving readers a **release candidate of the next major version**, 3.0.0-rc.0,
while the `<redoc spec-url=...>` element it uses is written against the 2.x
API. Nobody chose that. It happened when Redoc moved its `next` tag, and it
will move again.

A pin to `redoc@2.5.3` — the current `latest` — is written and sits in the
working tree, uncommitted for the reason given in the correction above.

Combined with a server that has no authentication (see
[`SECURITY.md`](../SECURITY.md)), a bad publish or a compromised CDN executes
arbitrary JavaScript in the operator's browser.

Remedies, in order of how much they fix: self-host these too; or pin `@next`
to an exact version and add Subresource Integrity hashes to all three. The
hashes are deliberately not written here, because a hash that was guessed
rather than computed from the exact bytes is worse than none.

## The simulation tool

Different surface, different answer. `src/web/server.ts` stores the query
text somebody typed, the parameters, the results and a job id — and
`GET /api/jobs/history` returns the last 50 of those **to any caller**,
because the server has no authentication.

That is documented at length in [`SECURITY.md`](../SECURITY.md), including
why it is safe on localhost and not elsewhere. If you are running it for a
class, read that first.

No cookies, no `localStorage`, no analytics, no telemetry.

## Caterva.app asks GitHub whether a newer version exists

From 0.5.1 the Mac app checks for updates (about once a day, and when you
choose Check for Updates). A check is an HTTPS request to `github.com` for
`appcast.xml` (and to GitHub's download host if you accept an update). If
"Include prereleases" is on, the app also asks `api.github.com` for the list
of releases. Those hosts therefore see your IP address, the app's name and
version (in the User-Agent) and the time. The app sends no system profile,
nothing from your runs, and sets no identifier of its own. GitHub's own
privacy statement governs what GitHub keeps. Turn the daily check off in
Settings, Updates; it is separate from Offline mode, which concerns the
literature services. A copy built from a checkout (`caterva studio`, or a
development app) never checks.

## Query text can be sent to an LLM provider, if someone turns it on

> **Correction (2026-08-15).** This document previously said "no third-party
> requests **from the page itself**." That qualifier made a misleading
> sentence technically true. The page does not call anyone; the *server*
> does — and a user's query text reaching OpenAI is a third-party disclosure
> regardless of which machine initiates it. Written by me, one pass earlier,
> in the document whose entire job is to describe this accurately.
>
> **Correction to that correction (2026-08-16).** "The page does not call
> anyone" is false, and was false when written. Every public page loads fonts
> and scripts from third-party CDNs on page load. See
> [Fonts and scripts the pages load from other people's servers](#fonts-and-scripts-the-pages-load-from-other-peoples-servers)
> below. Two passes in a row, this document described the third-party
> question and got the client half wrong both times — the second time while
> in the act of correcting the first.

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
| an LLM key configured | the query text goes to that provider, under **their** terms and retention policy, not Caterva's |

If you enable it, you are choosing to send your users' text to a third
party. That is your decision to make and your disclosure to give — read the
provider's data-processing terms, because this project has no control over
what they retain or train on.

`scripts/check_llm_disclosure.py` fails the build if the code can call an
external provider (this resolver, or the Studio assistant below) while the section that covers it is missing.

## Caterva Studio's assistant can send a run's results to an LLM provider, if someone turns it on

Caterva Studio (the desktop app, `caterva studio`) has an optional assistant that can explain a result, draft
methods text, answer a question about one run, narrate the engine's ranked next measurements and interpret a
description of a mechanism. It is described in [`docs/studio/ASSISTANT.md`](studio/ASSISTANT.md); the code is
`caterva/assistant/`.

**It is off by default**, and it is off until a person switches on three things: the assistant (Settings, Assistant),
each feature they want, and, the first time they use each feature, their agreement to what that feature sends. With
it off, no request is made and no assistant code builds a payload; a test holds the code to that.

**What is sent**, per call: a fixed system prompt, and the data the feature needs, as one JSON document. For an
explanation, a methods draft, a question or a next-measurement account, that is a bounded digest of the run's result
(its figures, units, verdict, concerns, and where each figure came from), plus the question for a question. For
"describe it" it is the sentence the person typed, the list of mechanism shapes, and enzyme names the finder matched.
What the person typed or chose to start a run (its title, compound names) is left out unless they tick "include my
data" for that call. File paths, the home folder, the user name, e-mail addresses and anything shaped like an API key
are removed before anything is sent. Before the first send of each feature, and whenever asked ("Show exactly what
will be sent"), the page shows the real request, byte for byte, and the server sends exactly that. A status-line
indicator reads "Assistant active: sends to <provider>" whenever data can leave.

**Where it goes:** to the provider the person chooses (Anthropic, OpenAI, Groq, OpenRouter or Mistral), under **their
terms** and retention policy, not Caterva's. Or to a model on the same computer (an OpenAI-compatible server at a
loopback address, such as Ollama), in which case nothing leaves the machine and the page says so. Offline mode blocks
every provider except a local one.

**The key:** never in the repository, a `.env` file, the data folder, a run record, a bundle, a log, the page, a
command line or an error message. On macOS the app keeps it in the login Keychain and gives it to the server over a
private pipe; the server holds it in memory only. In a browser or development run it comes from the
`CATERVA_ASSISTANT_KEY` environment variable.

**What is recorded:** every call (provider, model, the exact payload sent, the reply, the result of the check on it,
accepted or rejected, the time, and the person's confirmation) in that run's record and in `assistant/calls.jsonl` in
the data folder, and in the run's bundle when it is exported. Nothing is sent anywhere else, and Caterva keeps no
chat history beyond the run.

| | |
|---|---|
| default install | nothing leaves the machine |
| assistant on, a provider chosen, a feature agreed to | that feature's payload goes to the provider, under **their** terms, as shown in the preview |
| assistant on with a model on this computer | nothing leaves the machine |

Everything the assistant writes is checked against the run's own result before it is shown (`caterva/assistant/
grounding.py`); that check protects the correctness of what is shown, not the privacy of what was sent.

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
