# `docs/` — why things are the way they are

If you are new, do not start here. Start with
[`START_HERE.md`](../START_HERE.md) and come back when you hit something
that makes no sense.

## What each document is for

| document | read it when |
|---|---|
| [`CONSTITUTION.md`](CONSTITUTION.md) | you want the engineering rules in full, stated once |
| [`adr/`](adr/README.md) | you want to know *why* a specific design is the way it is |
| [`EXPERT_FEEDBACK.md`](EXPERT_FEEDBACK.md) | you want to know what reviewers outside the project said and what changed because of it |
| [`API.md`](API.md) | you are calling the HTTP API |
| [`REPO_MAP.md`](REPO_MAP.md) | you want to know which of the 18 repositories a file belongs in |
| [`AGENT_BRIEF.md`](AGENT_BRIEF.md) | you are an AI agent working on this repo, or setting one going |
| [`ARCHITECTURE_RIGOR.md`](ARCHITECTURE_RIGOR.md) | you want the long-form argument for the verification approach |
| [`PUBLISHING.md`](PUBLISHING.md), [`INFRASTRUCTURE_DECISION.md`](INFRASTRUCTURE_DECISION.md), [`ARCHIVE_TRIAGE.md`](ARCHIVE_TRIAGE.md) | narrower, one-topic records |
| [`releases/`](releases/v0.3.0.md) | you want to know what a tagged version contains, and what it does not |
| [`status/`](status/2026-09-21.md) | you want a dated snapshot of where the repository stands: figures, open problems, next steps, and what going public still needs |

## The ADRs

Numbered decision records, `docs/adr/NNNN-slug.md`, indexed in
[`adr/README.md`](adr/README.md).

They are unusual in one way that matters: **each one states what was *not*
done as prominently as what was**, and most of them record a defect the
decision was a response to — often a defect in an earlier ADR's
implementation. Several document checks that could not fail, written by the
same people who wrote the rule against them.

If you are looking for the ones that explain the project's character, read
0012/0013 (measured quantity vs experimental condition), 0024 (a refusal
must name what it refused), 0027 (a value computed and discarded at a
boundary), and 0055 (a hardcoded 37 °C that made two shipped warnings
unreachable).

**Claim the next free number by checking `ls docs/adr/` immediately before
you write**, and re-check before you save. Concurrent agents consume numbers
quickly and collisions have happened five times.

## Two kinds of document, and one rule about editing

**Present-tense docs** describe how things are now: this file,
`CONSTITUTION.md`, `API.md`, `REPO_MAP.md`, `AGENT_BRIEF.md`,
`../START_HERE.md`, `../CONTRIBUTING.md`, `../README.md`. When reality
changes, these change. `scripts/check_documented_counts.py` fails the build
when one of them states a count that no longer matches the repository.

**Historical records** describe what was true on a date and are **never
rewritten**: `EXPERT_FEEDBACK.md`, `ARCHIVE_TRIAGE.md`, everything in
`Business/build-stages/`, and each ADR once accepted. A superseded ADR gets
a new ADR pointing at it, not an edit.

This distinction is load-bearing. The staleness guard deliberately skips the
historical files — flagging *"46 ADRs"* in a record of a pass when there were
46 would be flagging the truth.

## Writing here

Comments and docs explain **why**, not what. The valuable one says what went
wrong and what it cost. This codebase is full of them and they are the
reason the same bug has not landed four times.
