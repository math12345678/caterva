# science-agent-pipeline-replit

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The Express API server and the science-agent pipeline. 360 files.

This is the service side: query → entity extraction → parameter resolution →
domain classification → validation → simulation, with provenance attached at
every step.

```bash
cd artifacts/api-server && npm start
```

## Endpoints

Reference: [`docs/API.md`](https://github.com/Terrium-sim/documents/blob/main/API.md). Highlights:

| method | path |
|---|---|
| `POST` | `/api/simulate` |
| `GET` | `/api/simulate/:jobId` |
| `GET` | `/api/simulate/:jobId/audit` — which parameters can be cited |
| `GET` | `/api/simulate/:jobId/confidence` — per-parameter confidence |

## Parameters go in the query string

```json
{ "query": "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" }
```

There is no separate `parameters` field. Anything the resolver cannot find
in the text and cannot source from literature is **reported, not guessed** —
`s0`, `end` and `points` are experimental conditions chosen by whoever runs
the experiment, so they are never defaulted (ADR 0012/0013).

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
