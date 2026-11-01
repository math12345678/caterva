# How decisions get made

Short version: one person decides, and that is a weakness rather than a
design. This file says so plainly because a contributor deciding whether to
invest time deserves to know what they are investing in.

## Who decides

Smyan Reddy, the author. There is no steering committee, no maintainer vote
and no formal review board. A pull request is merged when he merges it.

That is normal for a project this age and it has a cost: **the project has a
bus factor of one.** If he stops, nothing continues on its own. Everything
needed to pick it up is in the repository — the ADRs, the guards, the
build-stage record — but no other person currently has commit rights or the
context to use them.

If you are weighing whether to contribute substantially, that is the fact to
weigh.

## How a disagreement is resolved

**Say it in the pull request.** That is not a formality: several decisions in
this codebase were wrong and were changed because somebody pushed back.
`CONTRIBUTING.md` says it about guards specifically — *"If you think a guard
is wrong, say so in the PR and explain why — that is a legitimate position
and it has been right before"* — and the same applies to anything else.

If the disagreement is about a design rather than a line of code, it becomes
an ADR. That is what `docs/adr/` is: a record of decisions, including the
ones that superseded earlier decisions. **A superseded ADR is never edited;
a new one points at it.** So a decision you disagree with can be overturned
without the record of why it was made in the first place being erased.

What does not resolve a disagreement: weakening a check to make a build
green. If a guard is wrong, change the guard deliberately and say so. If it
is right, fix the cause.

## What agents are doing here

Several AI agents work on this repository concurrently, and their commits
appear alongside human ones. This is unusual enough to state.

Practical consequences a contributor will actually hit:

- **Files change under you.** Two agents editing the same file within
  minutes has happened repeatedly. Re-read before you edit; do not assume a
  file is as you left it.
- **ADR numbers collide.** Use `scripts/claim_adr.py` rather than picking
  the next free number by eye — it claims the number, waits, and yields if
  somebody else took it at the same instant.
- **Guards land unwired.** `scripts/check_guard_wiring.py` catches a guard
  connected to no harness. If it fails on a guard you did not write, wiring
  it is a small and welcome contribution.

Agent-authored work is held to the same standard as anybody's, which is
enforced by the same guards. It is not reviewed more leniently, and the
record shows it is not reliably better — a good deal of what
`docs/EXPERT_FEEDBACK.md` records is agents finding their own earlier
mistakes.

## Becoming a maintainer

There is no process, because there has not yet been a case. If you have
contributed substantially and want commit rights, ask. The honest state is
that the answer will be worked out when somebody asks rather than applied
from a policy that already exists.

## What would change this file

Incorporation. `Business/INCORPORATION_CHECKLIST.md` lists what needs a
lawyer, and several items there — whether a CLA becomes necessary, who holds
the copyright, what happens to contributions if the project is ever acquired
— would rewrite this document. See
[`docs/INBOUND_LICENSE.md`](docs/INBOUND_LICENSE.md) for the current
position on what your contribution arrives under.

## Related

| what | where |
|---|---|
| the engineering rules | [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) |
| why a design is the way it is | [`docs/adr/`](docs/adr/README.md) |
| what your contribution arrives under | [`docs/INBOUND_LICENSE.md`](docs/INBOUND_LICENSE.md) |
| how to get help | [`SUPPORT.md`](SUPPORT.md) |
| behaviour | [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) |
| how to start | [`START_HERE.md`](START_HERE.md) |
