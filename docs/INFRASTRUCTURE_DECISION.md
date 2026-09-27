# Infrastructure for bringing contributors in

Written because the question asked was "should we set up Azure Databricks
or an Azure database", and the honest answer is no — with a real
alternative rather than just a refusal.

## Why not Databricks

Azure Databricks is a managed Apache Spark platform. It exists for
distributed processing of data too large for one machine: ETL over
terabytes, large-scale ML training, lakehouse analytics.

Caterva has no such workload. It is a Python simulation engine plus a
TypeScript library and API. Its largest data artefact is a 14 MB git
repository. Its heaviest computation — a 125-particle molecular dynamics
run — takes about eleven seconds on a laptop. There is no dataset to
distribute and no job to parallelise across a cluster.

Adopting it would mean paying for cluster hours, learning a platform, and
routing work through it, in exchange for nothing the project currently
needs. If a real workload appears later — say, sweeping ten thousand
parameter sets and storing the results — that is the moment to revisit it.

Organisations you have seen using Databricks are almost certainly doing
data engineering. That is a different job from this one.

## What contributors actually need

Interns doing error-finding and writing need four things, and none of them
is a data platform:

1. **A place to report what they find** — GitHub Issues.
2. **A place to commit** — the repositories, already set up.
3. **Something to work on** — labelled starting points.
4. **Automatic feedback** — CI that runs the guards on their PR, so they
   learn from the build rather than from waiting on review.

All four are free on GitHub for a public repository, and three are already
in place.

## What to set up (in order)

### 1. Issue templates — 10 minutes

`.github/ISSUE_TEMPLATE/` already exists with bug and feature templates.
Add one for the highest-value contribution:

**`documentation-mismatch.md`** — "a document says X, the code does Y."
That single category has produced the most valuable findings in this
project's history, and it needs no setup to hunt for.

### 2. Labels — 5 minutes

Three are enough to start:

| label | means |
|---|---|
| `good-first-issue` | self-contained, no deep context needed |
| `needs-reproduction` | reported but not yet confirmed |
| `docs-vs-code` | a claim in a document does not match the source |

### 3. CI on pull requests — already done

Every split repository now carries a workflow. `main` runs the 22 guards.
A contributor gets a red or green within minutes of pushing, which teaches
the standard faster than review comments do.

### 4. A discussion channel — 15 minutes

GitHub Discussions, or a Discord if the group prefers it. The thing that
matters is that "is this a bug or am I holding it wrong" gets answered in
under a day. That question is where new contributors are lost.

## If you do want Azure

There are two things it would genuinely buy you, neither of which is
Databricks:

**Azure Static Web Apps** — free tier, hosts `mule/` and `caterva-site/`
with automatic deploys from GitHub. Currently the sites have no host at
all. This is the one worth doing.

**Azure for Students** — $100 of credit with no credit card if you verify
with a school email. Worth having regardless; it covers the above with room
to spare.

A database is premature. Caterva currently persists job history to a local
JSON-lines file (`src/storage/job-database.ts`). Nothing needs a server
until multiple people share state, and no feature currently does.

## The honest summary

You do not have an infrastructure problem. You have a **contributor
onboarding** problem, and the fix is documentation, labelled issues and
fast CI feedback — all of which cost nothing and most of which now exist.

Spending on a data platform before there is data to process is the
infrastructure equivalent of the thing this project spends most of its
effort preventing: a system that looks rigorous without doing the work.
