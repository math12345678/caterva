# Terrium HTTP API

Every endpoint below is registered by the server. This file is checked by
`scripts/check_example_endpoints.py`, which resolves each path against the
Express route table on every build — so a route that is renamed or removed
fails the build here rather than 404-ing for a reader.

## There are two servers

This is the single most important thing to know before reading any other
document in this repository, and it is what most of them get wrong.

| Server | Started by | Reference |
|---|---|---|
| `Science-Agent-Pipeline/artifacts/api-server/` (Express) | its own `npm start` | this page |
| `src/web/server.ts` (raw `http.createServer`) | `npm run web` | [below](#the-web-server) |

They share no routes. The Express service has `/api/healthz` and
`/api/simulate/:jobId`; the web server has `/api/health` and
`/api/jobs/:jobId`. Point a client at the wrong one and every call 404s,
which reads as a broken product rather than a wrong base URL.

`scripts/check_example_endpoints.py` resolves documented endpoints against
**both** route tables.

> **A correction worth keeping.** The first version of that guard parsed only
> the Express routers, and on that half-a-route-table it reported *242 of 294*
> endpoint mentions across the documentation as nonexistent. The real figure
> is **19 of 282**. Almost every "wrong" endpoint was a real route on the
> other server. Two client examples were rewritten against the wrong service
> before the error surfaced.
>
> A checker with an incomplete source of truth does not fail quietly — it
> produces confident false accusations, and they are acted on precisely
> because a guard is trusted. Same shape as a citation guard that parses zero
> entries and prints OK. The rule it earns: **a guard must be able to say how
> much of the world it looked at**, and a number it reports should be
> reproducible by hand before anyone acts on it.

Base URL: `http://localhost:3000`

## Running a simulation

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/simulate` | Enqueue a simulation. Returns `202` with `{ jobId, status, query }`. |
| `GET` | `/api/simulate` | List simulation jobs. |
| `GET` | `/api/simulate/:jobId` | Job state: `pending`, `running`, `completed`, `failed`. |
| `GET` | `/api/simulate/:jobId/stream` | Server-sent events for a running job. |
| `POST` | `/api/simulate/:jobId/cancel` | Cancel a pending or running job. |
| `GET` | `/api/simulate/:jobId/export` | Trajectory as CSV. |

### Parameters go in the query string

```json
{ "query": "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" }
```

There is **no separate `parameters` field**. The resolver reads
`km=2 vmax=5 s0=10` out of the text.

Anything it cannot find there and cannot resolve from literature is
reported, never guessed:

```json
{
  "error": "MISSING_REQUIRED_INPUT",
  "message": "Cannot simulate 'sir': s0, i0, r0_recovered, end, points could not be resolved from literature and were not supplied in the query. Add s0=<value> i0=<value> r0_recovered=<value> end=<value> points=<value> to your query and try again."
}
```

This is the product working. `s0`, `i0`, `end` and `points` are
**experimental conditions** — chosen by whoever runs the experiment, not
properties of an enzyme — so they are never defaulted and never resolved
from a paper (ADR 0012/0013).

## Where the numbers came from

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/simulate/:jobId/confidence` | Per-parameter confidence, derived from provenance. |
| `GET` | `/api/simulate/:jobId/audit` | Publication audit: which parameters can be cited. |

`audit` applies the distinction the rest of the system runs on: a
**measured quantity** (km, ki, kcat, vmax) needs a citation; an
**experimental condition** (s0, i0, temperature, pH) is reported rather than
cited, and never blocks publication readiness. A citation is required for
what someone measured and meaningless for what the experimenter chose.

## Enzymes and resolution

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/enzymes` | Enzymes the resolver recognises by name. |
| `POST` | `/api/resolve` | Resolve a kinetic parameter from the literature layer. |

## Health, metrics and status

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/healthz` | Liveness. Returns `{ "status": "ok" }`. |
| `GET` | `/api/pipeline/status` | Per-subsystem status and queue depth. |
| `GET` | `/api/pipeline/literature` | Literature backing per domain. |
| `GET` | `/api/metrics` | Pipeline metrics. |
| `GET` | `/api/metrics/health` | Health verdict with the denominator behind it. |
| `POST` | `/api/metrics/reset` | Reset collected metrics. |
| `GET` | `/api/simulate/metrics/pipeline` | Stage-level metrics with Wilson confidence intervals. |
| `GET` | `/api/snapshot` | Point-in-time metrics snapshot. |
| `GET` | `/api/dashboard/overview` | System state: queue, literature backing, STRENDA compliance. |
| `GET` | `/api/dashboard/health` | Dashboard health verdict. |

## Waitlist

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/waitlist` | Join the waitlist. |
| `GET` | `/api/waitlist/count` | Current waitlist size. |

## Root

| Method | Path | What it does |
|---|---|---|
| `GET` | `/` | Service banner. |

## The web server

`src/web/server.ts`, started with `npm run web`. Accepts
`{query, parameters, enzyme, substrate}` — parameters are a field here, not
part of the query string. Supplying `enzyme` and `substrate` makes it search
PubMed for real kinetics before running.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/simulate` | Enqueue a simulation. Returns `{ jobId, status }`. |
| `GET` | `/api/jobs/:jobId` | Job state and result. |
| `GET` | `/api/jobs/history` | The 50 most recent jobs. |
| `GET` | `/api/jobs/query` | Filtered job query (`status=`, `minConfidence=`, `dateFrom=`, …). |
| `GET` | `/api/stats` | Aggregate statistics. |
| `POST` | `/api/sweep` | Sweep one parameter across a range. |
| `GET` | `/api/sweeps/:sweepId` | Sweep results. |
| `GET` | `/api/analyze/sweep/:sweepId` | Sensitivity analysis of a sweep. Also `/analyze/sweeps/:sweepId`. |
| `POST` | `/api/batch` | Run many parameter sets. |
| `GET` | `/api/batches/:batchId` | Batch results. |
| `POST` | `/api/compare` | Compare models. |
| `POST` | `/api/compare/jobs` | Compare finished jobs. |
| `GET` | `/api/health` | Liveness. |
| `GET` | `/api/export/jobs/csv` | Job history as CSV. |
| `GET` | `/api/export/stats/csv` | Statistics as CSV. |
| `GET` | `/api/export/sweep/:sweepId/csv` | Sweep results as CSV. Also `/api/export/sweeps/:sweepId/csv`. |
| `GET` | `/api/export/batch/:batchId/csv` | Batch results as CSV. Also `/api/export/batches/:batchId/csv`. |
| `GET` | `/api/export/comparison/:compareId/csv` | Comparison as CSV. Also `/api/export/comparisons/:compareId/csv`. |

### Singular and plural both work

The reads are plural (`/api/sweeps/:id`, `/api/batches/:id`) and the exports
were singular (`/api/export/sweep/:id/csv`). Anyone who has just fetched a
sweep reaches for the plural export and gets a 404 with no hint that one
letter is the problem.

That is not hypothetical — it caught the author of
`API_QUICK_REFERENCE.md`, who documented the plural forms throughout because
they were the reasonable guess. The document was right about what the API
*should* serve; the API was the inconsistent thing.

Both spellings now route, rather than one being renamed, so any existing
caller using the singular form keeps working.

## Clients

Working, checked examples — one per server, because they are not
interchangeable:

- [`examples/python_integration.py`](../examples/python_integration.py) — the web server
- [`examples/nodejs_integration.js`](../examples/nodejs_integration.js) — the Express service

Both are covered by the same guard as this page.
