# Repository map

**This describes a plan, not the current layout.** Caterva is *to be*
published as 18 repositories under
[github.com/Terrium-sim](https://github.com/Terrium-sim); today it is one
repository, and `docs/PUBLISHING.md` holds the procedure that has not been
run. This file records what would go where and, where the answer was not
obvious, why.

That distinction is the reason for this paragraph. The line above read
"Caterva **is** published as 18 repositories", in the present tense, in a
document `DOCUMENTATION_INDEX.md` offers as "find my way around the tree" —
so a newcomer looking for `backend-main` would go hunting for a repository
that does not exist and conclude they had lost it.

After the split, `main` becomes an **umbrella**: top-level README, compose
and container files, CI, and git submodules pointing at the others. No
source file would live in two repositories, so nothing could drift out of
sync — the failure this project has spent most of its effort eliminating
everywhere else.

Clone today:

```bash
git clone https://github.com/math12345678/caterva.git
```

`--recursive` belongs on that command only once submodules exist. It was
there, doing nothing, and `Tests/test_clone_instructions_agree.py` will
require it again the moment a `.gitmodules` appears — so the flag comes
back with the split rather than ahead of it.

## The map

| repo | contents | source in the monorepo | history |
|---|---|---|---|
| `main` | umbrella: README, LICENSE, CITATION.cff, CONTRIBUTING, SECURITY, CHANGELOG, Docker/compose, submodules | root files (14 current docs) | new |
| `backend-main` | TypeScript library, CLI, engine bridge, web server, storage, validation, literature layer | `src/`, `examples/` | preserved |
| `frontend-main` | the dashboard UI served by the web server | `src/web/dashboard.html` | preserved |
| `wiring-main` | the guards, CI workflow, Makefile, build/lint/type config | `scripts/`, `.github/`, `Makefile`, `pyproject.toml`, `tsconfig.json`, `requirements*.txt` | preserved |
| `caterva` | the simulation engine (15 domains) and its tests | `caterva/` (was `Tellurium/`) | preserved, see below |
| `tests` | the literature layer — resolvers, BRENDA/PubMed clients | `Tests/` | preserved |
| `business` | strategy, pitch material, and the build-stage record | `Business/` | preserved |
| `documents` | ADRs, the constitution, architecture notes, Word deliverables | `docs/`, `Docw/` | preserved |
| `advanced-analysis` | analysis scripts and generated figures | `advanced_analysis/` | preserved |
| `benchmark-results` | benchmark output (CSV/JSON) | `benchmark_results/` | preserved |
| `landing` | landing page components | `landing/` | preserved |
| `caterva-site` | the marketing site (React + Vite) | `caterva-site/` | preserved |
| `worktrees` | git worktree scratch space | `Caterva.worktrees/` | new — see below |
| `science-agent-pipeline-replit` | the Express API server and science-agent pipeline | `Science-Agent-Pipeline/` | preserved |
| `archive` | 58 superseded status/session/completion reports | root `*.md` | new |
| `miscellaneous` | uncategorised docs, images, the pitch deck, throwaway scripts | root loose files | new |
| `mule` | MuleRun landing page | *(you add)* | new |
| `demo-repository` | GitHub demo repo | *(unchanged)* | — |

## Decisions worth recording

### Why `main` is an umbrella and not a copy

The alternative — `main` holding everything while `backend-main` and
`frontend-main` hold slices of the same files — puts the same source in two
places. It always ends the same way: the copies diverge, and nobody can say
which is authoritative. Submodules cost one `--recursive` flag and remove
the possibility entirely.

### `frontend-main` is deliberately small

It holds one file today: the dashboard the web server serves. The marketing
site (`caterva-site`) and the landing page (`landing`) are separate products
with their own build chains, so folding them together would create a repo
with three unrelated toolchains and no shared code.

The dashboard is split from `server.ts`, which stays in `backend-main`.
That is a real risk — a fetch URL in the dashboard and a route in the server
now live in different repositories — and it is precisely the drift that
`check_example_endpoints.py` exists to catch. That guard lives in
`wiring-main` and runs against the full checkout, which is another reason
`main` pulls everything in as submodules.

### `caterva`: the engine, renamed

`Tellurium/` became `caterva/` on 2026-08-11. The upstream Tellurium project
is unrelated to this code: `requirements.txt` has always said *"do NOT
`pip install tellurium`"*, and the codebase imports it nowhere, using
`libroadrunner` and `antimony` directly. The old name implied a
relationship that does not exist.

Splitting this one needed two steps. `git subtree split -P caterva` returns a
single commit, because the path only exists from the rename forward. The
history lives under the old path, so the split runs from a worktree at the
commit *before* the rename (`-P Tellurium`, 71 commits) and the rename is
replayed on top. Everything else splits directly, since no other path moved.

### `worktrees` starts empty

`Caterva.worktrees/` contains no tracked files — it is scratch space for
`git worktree add`. The repository is created with a README explaining what
it is for, so that an empty repo is not mistaken for a failed push.

### `archive` is large on purpose

58 of the 81 root-level markdown files are superseded status reports —
`EVERYTHING_COMPLETE.md`, `TRULY_FINAL_SUMMARY.md`, `READY_TO_SHIP.md` and
so on, several of which open with hand-written banners admitting their own
numbers are unverified. They are not deleted: they are the record of how the
project got here, and a few document mistakes worth remembering.

They are separated because a reader opening the repository root should not
have to guess which of nine "complete" documents is current. `main` keeps 14
documents that are true today; the rest move here.

Full per-file classification is in
[`docs/ARCHIVE_TRIAGE.md`](ARCHIVE_TRIAGE.md).

## Keeping it honest

The split does not weaken any guard. `wiring-main` holds all of them, and they
run against the recursive checkout, so:

- `check_example_endpoints.py` still resolves every documented endpoint
  against both servers' route tables, across repository boundaries.
- `check_no_orphan_modules.py` still sees the whole import graph.
- `check_documented_counts.py` still reconciles the README's test counts
  against `caterva` and `tests`.

Counts are deliberately not stated in this table. They changed under three
onboarding documents without anyone noticing — the figure a reader needs is
in `README.md`, which `scripts/check_documented_counts.py` keeps true.

A guard that only worked inside one repository would be a guard that stopped
working the moment the repository was split, which is the same
half-a-route-table failure recorded in `STAGE_10_PART_24`.
