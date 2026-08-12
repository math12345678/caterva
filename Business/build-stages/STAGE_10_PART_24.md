# Stage 10, Part 24 — the guard that produced confident false accusations

Stage: 10 · Part: 24 · 2026-08-11

## 1. The mistake, first

I built `check_example_endpoints.py` in Part 23 and reported that **242 of
294 endpoint mentions across the documentation were wrong — 82%**.

That number was wrong. The real figure is **19 of 282**, and of those 19,
**two** were genuine defects. The rest are wildcards in prose
(`/api/jobs/*`), an nginx `location /api/` block, "here is how you would add
your own endpoint" tutorials, a roadmap proposal, and — most pointedly —
correction banners *warning readers that a fabricated endpoint does not
exist*.

### Why it was wrong

Terrium serves **two** HTTP APIs:

| Server | Style | Routes |
|---|---|---|
| `Science-Agent-Pipeline/artifacts/api-server/` | Express `router.get(...)` | 22 |
| `src/web/server.ts` | raw `http.createServer`, `pathname === '/api/...'` | 19 |

My route parser matched Express only. It never saw the second server, so
every endpoint that server owns — `/api/batch`, `/api/sweep`,
`/api/compare/jobs`, `/api/jobs/<id>`, `/api/stats`, `/api/export/jobs/csv`
— was reported as nonexistent.

### What I did on the strength of it

Rewrote both client examples against the wrong service. The originals had
eleven endpoints; I called ten of them fabricated. **All eleven were real.**
The request shape I "fixed" was correct too: the web server does take
`{query, parameters, enzyme, substrate}`.

Both have been put back, targeting the server they were written for, and
each now names which server it talks to in its first paragraph.

### The lesson, stated so it transfers

A guard with an incomplete source of truth **does not fail quietly**. It
produces confident false accusations — and they get acted on precisely
because a guard is trusted. That is worse than no guard, and it is the same
shape as every defect this stage has been correcting:

| # | guard | how it was confidently wrong |
|---|---|---|
| 1 | `check_citation_format` | printed OK on a zero parse (Part 20) |
| 2 | `check_typescript_compiles` | every dir found a tsconfig, so membership was vacuous (Part 14) |
| 3 | `check_no_silent_skips` | one suite ran, so "every collected test ran" (Part 23) |
| 4 | `check_guard_wiring` | loop body was empty (Part 23) |
| 5 | `check_example_endpoints` | **half the route table (here)** |

The first four could only ever report false *negatives* — green when they
should have been red. This one reported false *positives*, which is the
more dangerous direction, because a red build compels action.

**The rule it earns: a guard must be able to state how much of the world it
looked at, and a number it reports should be reproduced by hand before
anyone acts on it.** I reproduced the 242 by re-running my own script, which
is not reproduction — it is asking the same wrong question twice.

The guard now parses both servers, and refuses to run at all if
`src/web/server.ts` cannot be read, rather than checking against a table it
knows is half-empty.

## 2. The two real documentation defects

- `READY_TO_SHIP.md` listed `GET /api/literature/search` as a shipped
  endpoint.
- `WEB_INTERFACE.md` documented it with a working-looking `curl` and a fake
  example response.

It exists on neither server. PubMed search is not a route — it happens
**inside** `POST /api/simulate` when the request supplies `enzyme` and
`substrate`. Both now show that, and the stale correction banners that said
"this doc lists X" were rewritten, because after the fix they were
themselves false.

`API_DOCUMENTATION.md` had 725 lines describing an API that genuinely never
existed — bearer auth, webhooks, cursor pagination, URL versioning with a
deprecation date, npm and PyPI SDKs. Those eight endpoints were checked
against **both** route tables and are absent. It is now a signpost to
`docs/API.md`, which documents both servers and is checked on every build.

## 3. Four defects in the untracked work

All of it was sitting in the working tree, uncommitted.

### A date-range query hid every failed job

```ts
if (filter.dateFrom) filtered = filtered.filter(j => new Date(j.startTime) >= dateFrom);
if (filter.dateTo)   filtered = filtered.filter(j => new Date(j.endTime)   <= dateTo);
```

`dateTo` tested `endTime`. A job that errored or is still running has none,
so `new Date(undefined) <= dateTo` is false and it vanished. In the fixture
that caught it, the one job with `status: 'error'` was simply absent from
"everything on 2026-08-11" — someone debugging a bad day would have been
shown only the runs that went well.

### CSV export blanked every zero

Every cell was `escapeCsvField(x || '')`. A `finalValue` of **0** exported as
an empty cell — and a substrate fully consumed is the *normal* end state of
a Michaelis-Menten run. So did `validated: false`, which is not missing data
but the most important thing on the row. 18 cells fixed.

One needed care: `ranking?.indexOf(x) + 1` is `NaN` when ranking is absent
and `0` when the model is unranked. The `|| ''` had been hiding both, so the
blank was right by accident.

### The model comparator could not tell two models apart

```ts
if (job1.result?.query === job2.result?.query) {
  insights.push(`Both jobs used the ${job1.result.query} model`);
```

`query` lives on the job, not on `job.result`. So the comparison was
`undefined === undefined`, always true, and every comparison of any two jobs
reported **"Both jobs used the undefined model"** — printing the word
`undefined` to the user on every run. `compareMultipleJobs`, in the same
file, reads `job.query` correctly: the duplicate-source-of-truth shape,
inside one module.

### Two assertions that could only ever fail

`expect(insights).toContain(expect.stringContaining(...))` — `toContain`
uses `Object.is` on members, so an asymmetric matcher never matches. Jest's
own failure message says to use `toContainEqual`.

Five other tests demanded output that would have been *wrong*: three
asserted raw JSON in CSV cells where RFC 4180 requires quoting and doubled
inner quotes, and two asserted `"1.0"` for a value that is the number `1` by
the time it reaches the exporter. Rewritten to assert whole rows, which also
pins *where* a value appears.

## 4. The CLI printed results for runs that never happened

`scientificCLI.ts` had been changed to warn instead of exit on validation
failure, then fall through to the results block. The pipeline returns
`trajectory: []` on that path, so it printed:

```
Results:
  Trajectory points: 0
  Initial value: undefined
  Final value: 0.000
```

and exited 0.

The instinct behind the change was right and is preserved. Refusing to run
merely because a value is unbacked *was* wrong — an experimental condition
cannot be cited, so blocking on it is a category error (Part 16). But that
was fixed in Layer 1, and `validated: false` no longer means "unbacked": a
run on entirely user-supplied values validates fine and scores zero
confidence. It now means the run could not be performed.

So: **cannot run → stop, naming what is missing. Ran but nothing backs it →
say so loudly, in the success path, where there are real numbers to
caveat.**

## 5. Verification

| check | result |
|---|---|
| static guards | **21/21** |
| `check_example_endpoints` | 68 endpoints, 2 examples + 2 docs, against 39 routes on both servers |
| root (jest) — storage, validation, integration, engine | **226/226** |
| api-server (vitest) | **433/433** |
| `tsc --noEmit`, both trees | 0 errors |
| untracked files remaining | **0** |

Mutation-tested this part: a broken JS endpoint, a fake endpoint reappearing
in the signpost doc, `docs/API.md` gutted, the web-server route table
unreadable, and a comment mentioning a dead endpoint (must *not* fire).

## 6. Open

- `check_example_endpoints` covers 4 files. The other 22 root documents are
  tracked but unchecked; adding them needs the guard to understand wildcard
  prose (`/api/jobs/*`) and "how to add an endpoint" tutorials, or it will
  produce exactly the false positives this part is about.
- Two servers is itself the finding. Nothing decides which one is canonical,
  and a reader has to know which they are pointed at before any other
  document makes sense. `docs/API.md` now says so first.
