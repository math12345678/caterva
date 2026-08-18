# Where to look

The repository root holds 41 markdown files. It held 81 when
`docs/ARCHIVE_TRIAGE.md` was written and 98 by the time that triage was
executed; most were session reports from earlier in the build, and 58 were
read, classified and found to contain claims that are stale, superseded or
false — the triage records every one with the reason.

This file used to be a 424-line index of that whole set. Its first
section was headed *"I'm a new developer — where do I start?"* and it sent
you to three documents that the triage classifies ARCHIVE, one of which
describes files that never existed. The rest of it indexed a documentation
set that has since been dispersed.

Rather than leave a correction banner on top of it — a pattern this project
has already learned does not work, because a specific endpoint table reads
as more authoritative than a vague disclaimer above it — the index is
replaced by the short list of documents that are actually true.

## Start here

| I want to… | Read |
|---|---|
| get it running | [`README.md`](README.md) → `make setup && make check && make test` |
| fix a broken setup | `make doctor` — it reports what it checked, not just a verdict |
| contribute a change | [`CONTRIBUTING.md`](CONTRIBUTING.md), then `make pr` |
| understand the ground rules | [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) |
| find my way around the tree | [`docs/REPO_MAP.md`](docs/REPO_MAP.md) |
| know why something is built that way | [`docs/adr/`](docs/adr/) — the decision records, indexed in its README |
| use the CLI | [`COMPREHENSIVE_GUIDE.md`](COMPREHENSIVE_GUIDE.md) |
| call the HTTP API | [`docs/API.md`](docs/API.md) — kept true by `check_example_endpoints.py` |
| run the api-server tests | [`RUN_TESTS.md`](RUN_TESTS.md) |
| report a vulnerability | [`SECURITY.md`](SECURITY.md) |

## The rest of the root, honestly labelled

Fourteen documents are current and accurate (`KEEP`), three describe
deployment wiring that is partly verified and partly aspirational
(`WIRING`), six are design or strategy documents with no false status
claims (`MISC`), and 58 are archived history (`ARCHIVE`).

**As of 2026-08-15 the ARCHIVE set has moved** to
[`docs/archive/`](docs/archive/), 57 files, with `git mv` so history
follows. The root went from 98 markdown files to 41 as of 2026-08-16 —
a dated statement about the move, not a live count. Only this file stayed
behind, on purpose — [`docs/archive/README.md`](docs/archive/README.md)
says why, and records the mistaken reason four others were delayed a pass.

**`docs/ARCHIVE_TRIAGE.md` is the authority.** It lists all 81 by name with
a one-line reason for each classification. If a root document is not
mentioned in the table above, check the triage before trusting a number in
it.

Nothing has been deleted. Several of the archived documents are worth
keeping precisely because their mistakes are instructive — inflated line
counts, a test transcript that appears to have been synthesised, three
rival documents each claiming to be the final one.

## Why this is a documentation problem and not a tidiness problem

Every one of those 58 files was written to be helpful. The failure is not
that they were written; it is that a reader cannot tell, from the outside,
which of nine "complete guides" is the one that is still true — and a
specific, confident, wrong number is worse than no number at all.

The project's answer to that is not more documentation. It is to make
claims mechanically checkable so they cannot rot silently:

- `check_documented_counts.py` fails the build when README's test and
  domain counts drift from reality.
- `check_example_endpoints.py` fails when `docs/API.md` describes an
  endpoint the server does not serve. That is why that file, alone among
  the API documents, carries no correction banner.
- `check_doc_paths_resolve.py` fails when any document in the list above
  names a file that does not exist.
- `check_ci_reproducible_locally.py` fails when CI grows a step a
  contributor has no documented way to run.
- `check_commands_runnable.py` fails when a document or a guard's own error
  message tells someone to run a script that cannot run.

A document that is checked by one of these can be trusted. A document that
is not is a claim about the past.
