# Getting help

## If something does not work

**Run `make doctor` first.** It runs on a bare interpreter and imports
nothing outside the standard library, so it still works when the virtual
environment is the broken thing. It prints every interpreter it found, the
venv's state and which Python built it, each required package's version
against its pin, and whether Node is present.

Paste its output into your report. It is the whole environment in one block
and it saves a round trip.

## Two things that are not your fault

**`No module named 'Terrium'`** — the package is spelled `Terium`, one r.
The product is `Terrium`, two. Your install is fine. See
[`START_HERE.md`](START_HERE.md).

**A run that refuses instead of producing a number** — that is usually
Terrium working. It declines to invent a parameter it cannot source, and
says which one and why. If the refusal does not tell you what was missing,
*that* is a bug worth reporting.

## Where to ask

| what | where |
|---|---|
| something is broken | open a [bug report](.github/ISSUE_TEMPLATE/bug_report.md) |
| a document contradicts the code | [documentation mismatch](.github/ISSUE_TEMPLATE/documentation-mismatch.md) — these are genuinely valued, a sweep once found a 725-line API reference describing endpoints that never existed |
| I want to work on something | [`docs/FIRST_TASKS.md`](docs/FIRST_TASKS.md), then open an issue saying which one |
| why is the code like this | [`docs/adr/`](docs/adr/README.md) — start with the index |
| what happens to my contribution | [`docs/INBOUND_LICENSE.md`](docs/INBOUND_LICENSE.md) |
| who decides, and what agents are doing here | [`GOVERNANCE.md`](GOVERNANCE.md) |
| I think a guard is wrong | say so in the PR and explain why. That is a legitimate position and it has been right before |

## What a good question looks like

Three parts: **what you ran**, **what happened**, **what you expected.**
That is enough. You do not need to have diagnosed it, and you do not need to
propose a fix.

## Things that are genuinely fine to ask

- A question with an obvious answer you could not find.
- A bug that turns out to be your environment. That is still a
  documentation bug — the setup instructions failed to prevent it.
- Disagreeing with a decision in the codebase. Several were wrong.
- Not knowing the biology. Most of the work here is software.

## Response times

This is a small pre-launch project. There is no support rota and no
guaranteed response time. Issues are read; they are not always answered
quickly.

Saying that plainly is better than implying a service level that does not
exist — which is the same standard the code holds itself to.

## Security

Do not open a public issue for a security problem. See
[`SECURITY.md`](SECURITY.md).
