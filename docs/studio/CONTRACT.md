# Caterva Studio: the contract

Caterva Studio is the desktop app: a native macOS window (or any local
browser) onto a local HTTP server that runs the same library functions the
`caterva` commands run, and shows every number with the kind of number it
is and where it came from. This document is what five builders work from at
once. Where it and the code disagree, the code is wrong or this document is
amended; nobody resolves a disagreement silently.

- The shapes that cross HTTP are declared once in
  `caterva/studio/contract.py` and mirrored in
  `Science-Agent-Pipeline/artifacts/caterva-studio/src/api/types.ts`.
  `caterva/tests/test_studio_contract.py` fails when the two differ in a
  type name, a key, a key's optionality or a union's members.
- The API routes are data in `caterva/studio/routes.py`. The same test fails
  when a route there is not written below as `METHOD /path`.
- Adapters register through `caterva/studio/adapters/__init__.py`.

Contents: 1 Architecture. 2 The command. 3 Security. 4 Static serving and
the session token. 5 Development: the dev origin and the Vite proxy.
6 Errors. 7 Endpoints. 8 Runs, jobs and events. 9 Provenance. 10
Capabilities. 11 The workspace on disk. 12 Adapters. 13 Kinds, one by one.
14 Gaps. 15 User paths. 16 The desktop shell. 17 The page: screens, themes,
provenance as the visual system. 18 Ownership map. 19 How to install in a
new worktree. 20 Verification and guards. 21 Amending this contract.

---

## 1. Architecture

```
Caterva.app (Swift, AppKit + WKWebView)          any local browser
   | launches, reads CATERVA_STUDIO_URL=...          |
   v                                                 v
caterva studio  (caterva/studio/__main__.py, Python standard library only)
   socket layer    ThreadingHTTPServer, loopback only           (core)
   dispatch        (method, path, headers, body) -> response    (core)
                   pure: testable without binding a port
   security        Host, Origin, token, headers                 (core)
   jobs            queue, worker threads, SSE, cancel           (core)
   workspace       <data dir>/runs/<id>/..., settings.json      (core)
   adapters        one per CLI command family                   (sci-kinetics, sci-structure)
                   JSON request -> the CLI's argv -> the CLI's own parser
                   -> the library functions the CLI calls -> JSON with provenance
   static          caterva/studio/static/ (Vite build, not committed)
```

Fixed decisions, restated so nobody re-opens them:

- No new Python runtime dependency. `http.server`, `json`, `threading`,
  `secrets`, `hmac`, `zipfile`, `mimetypes`: nothing else. The app is
  frozen with PyInstaller by `scripts/build_app.py` and pyproject pins every
  dependency.
- The dispatch layer is a pure function of (method, path, headers, body)
  plus the server's state. The socket layer only reads bytes into that call
  and writes the answer back (SSE streams are the one exception, see 8.4).
  Every rule in sections 3 to 8 is testable through dispatch.
- Adapters never compute. A number the library did not produce, a rounding
  it did not apply, or a sentence summarising one it wrote is a defect.
  Where the library only prints something, the fix is a structured accessor
  beside the printer that both the printer and the adapter call (section 14).

## 2. The command

```
caterva studio [--host 127.0.0.1] [--port N] [--no-browser] [--dev-origin URL]
               [--data-dir PATH] [--print-url] [--self-test]
```

| flag | meaning |
|---|---|
| `--host` | loopback address to bind: `127.0.0.1` (default), `::1` or `localhost`. Anything else is exit 2 ("not a loopback address"). |
| `--port N` | port to bind; `0` (default) picks a free one. Outside 0..65535 is exit 2. |
| `--no-browser` | do not open the default browser (the macOS shell and CI pass it). |
| `--dev-origin URL` | also accept requests whose `Origin` is exactly `URL` and serve `GET /api/dev/session`. Development only. `URL` must be `http://127.0.0.1:<port>` or `http://localhost:<port>`; anything else is exit 2. |
| `--data-dir PATH` | where runs and settings live; default in section 11. Created (mode 0700) if absent; not writable is exit 3 with the reason. |
| `--print-url` | once the socket is listening, print exactly one line `CATERVA_STUDIO_URL=<url>` to stdout and flush. `<url>` is `http://127.0.0.1:<port>/` (or `http://[::1]:<port>/`, `http://localhost:<port>/`). Nothing else is ever printed to stdout; logs go to stderr and `<data dir>/studio.log`. |
| `--self-test` | start on a free port, request `/api/health` (with the token) and `/` over a real socket, check the health body and that `/` is either the built page with the token injected or the "not built" page, print one line per check to stdout, stop, exit 0 or 1. Used by the frozen-app checks and CI. |

Exit codes follow the rest of Caterva: 0 served and stopped cleanly (Ctrl-C,
SIGTERM, or the shell quitting) or a self-test passed; 1 a crash or a failed
self-test; 2 a malformed command line; 3 refused and said why (data dir not
writable, port in use). The parser is already in `caterva/studio/__main__.py`;
core replaces `main`, not the flags.

The macOS shell launches `caterva studio --port 0 --no-browser --print-url`,
reads stdout until the `CATERVA_STUDIO_URL=` line, and loads that URL. The
server stops when its stdin closes (the shell's pipe) as well as on SIGTERM,
so a crashed shell never leaves an orphan server behind.

## 3. Security

A local server is reachable by every web page the user visits and every
process on the machine. The rules, all enforced in dispatch before any
handler runs, in this order:

1. **Bind loopback only.** `--host` refuses anything but the three loopback
   names. There is no flag to bind elsewhere.
2. **Host header.** The request's `Host` must be exactly one of the bound
   authorities: for `127.0.0.1` bound on port P, `127.0.0.1:P` or
   `localhost:P`; for `::1`, `[::1]:P` or `localhost:P`; for `localhost`,
   `localhost:P` or `127.0.0.1:P`. Anything else (a rebinding attacker's
   `evil.example:P`, a missing Host) is 403 `forbidden`. This applies to
   static files too, because index.html carries the token.
3. **Origin.** A request carrying `Origin` must have exactly the server's own
   origin (`http://` + an allowed Host) or the `--dev-origin` value; else 403.
   A request with `Sec-Fetch-Site: cross-site` is 403 whatever its Origin.
   No response ever carries `Access-Control-Allow-*`; there is no CORS and
   no preflight handling (`OPTIONS` is 405).
4. **Session token.** Every `/api/` route except `GET /api/dev/session`
   requires header `X-Caterva-Session` (contract.SESSION_HEADER) equal to the
   per-launch token, compared with `hmac.compare_digest`. Missing or wrong is
   401 `unauthorized`. The token is `secrets.token_urlsafe(32)`, minted at
   start, held in memory only, never written to disk, never logged, never
   accepted from a query string or cookie. Static files need no token.
5. **Bodies.** `POST` and `PUT` must send `Content-Type: application/json`
   (a form cannot, so a cross-site form post is refused even before the
   token check matters): else 415 `unsupported_media_type`. Bodies over
   contract.MAX_BODY_BYTES (1 MiB) are 413 `too_large`, judged from
   `Content-Length` before reading; a body without `Content-Length` is 411
   reported as 400 `malformed`. Invalid UTF-8 or JSON is 400.
6. **Paths.** Matched after percent-decoding, no trailing slash, against
   the typed placeholders in `routes.py` (a run id, an artifact name, a PDB
   id). A value that does not match is 404, never echoed back.
7. **Response headers**, on every response:
   `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
   `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin`,
   `Cross-Origin-Resource-Policy: same-origin`,
   `Permissions-Policy: camera=(), microphone=(), geolocation=()`, and
   `Server: caterva-studio` (the standard library's default names the Python
   version; it is replaced). `/api/` responses and index.html add
   `Cache-Control: no-store`.
8. **Content Security Policy**, on every HTML response:
   `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'`.
   The built page has no inline script or style element (Vite emits files);
   React, Radix and framer-motion set styles through the CSSOM, which this
   policy allows. A component that needs an inline `<style>` or `eval` is
   refused in review rather than the policy loosened.
9. **Static files** are served only from `caterva/studio/static/`, resolved
   with `Path.resolve()` and required to stay inside it (`..`, symlinks out,
   absolute paths: 404). No directory listing: a directory path serves
   index.html only at `/`; every other unmatched non-`/api/` path serves
   index.html (the page's client-side routes), never a listing.
10. **User paths** (trajectories, output folders) are accepted only by the
    kinds that need them and only by the rules of section 15, and are never
    served back. The only files the server returns are the built page and a
    run's recorded artifacts (by recorded name).

`scripts/check_port_binding.py` already checks published ports bind
loopback; the studio binds no fixed port.

## 4. Static serving and the session token

- `GET /` and every non-`/api/` path that is not a file under `static/`
  answer with `static/index.html`, after replacing the one occurrence of
  contract.TOKEN_PLACEHOLDER (`__CATERVA_SESSION_TOKEN__`) inside
  `<meta name="caterva-session" content="...">` with the token. If the
  placeholder is absent the page was not built from this package: 500
  `crash` with that sentence, not a page without a token.
- Files under `static/assets/` are served with their `mimetypes` type
  (`.js` as `text/javascript`, `.woff2` as `font/woff2`, `.svg` as
  `image/svg+xml`) and `Cache-Control: public, max-age=31536000, immutable`
  (their names carry content hashes). Other static files: `no-cache`.
- **Missing build.** When `static/index.html` does not exist, `/` answers
  200 with a small built-in page (inline, owned by core, no script) saying:
  the page has not been built; build it with the command in section 19
  (`pnpm --filter @workspace/caterva-studio run build` from
  `Science-Agent-Pipeline/`); and that the API is running. Capabilities
  reports `ui.built: false` with the same reason.
- The page reads the token from the meta tag (`src/api/client.ts`,
  `sessionToken()`), sends it as a header on every `/api/` request, and never
  puts it in a URL. A page whose tag still holds the placeholder says it was
  not served by `caterva studio`.

## 5. Development: the dev origin and the Vite proxy

The launch configurations (for example `studio-foundation-backend` +
`studio-foundation-ui`) start:

```
python -m caterva.app studio --port 18740 --no-browser --dev-origin http://127.0.0.1:18741
STUDIO_API=http://127.0.0.1:18740 PORT=18741 node node_modules/vite/bin/vite.js --config vite.config.ts
```

- `vite.config.ts` proxies `/api` to `process.env.STUDIO_API`
  (`changeOrigin: true`, so the backend sees `Host: 127.0.0.1:18740`; the
  browser's `Origin: http://127.0.0.1:18741` is forwarded and allowed because
  it equals `--dev-origin`).
- `GET /api/dev/session` exists only when `--dev-origin` was given. It
  needs no token (it is how the token is obtained) and refuses (403) any
  request carrying `Origin`, or `Sec-Fetch-Site` other than `none`: the Vite
  server's own Node `fetch` sends neither, and a web page cannot avoid
  sending them. It answers `DevSession` `{token, api_version}`.
- The Vite plugin `caterva-studio-dev-session` fetches it when index.html is
  served and writes the token into the same meta tag, so the page reads it
  the same way in both modes. If the backend is not up yet, the placeholder
  stays and the page says so; reload once the backend is running.
- `studio-packaged` serves the built page from `caterva/studio/static` with
  no dev origin: that is the configuration that proves the release shape.

## 6. Errors

Every error response has body `ErrorBody` `{"error": {"code", "message",
"field"?, "details"?}}` and one of these statuses:

| HTTP | code | when | CLI equivalent |
|---|---|---|---|
| 400 | `malformed` | bad JSON; a request that fails the kind's own argparse parser (argparse's message, verbatim, through `adapters.parse_cli`); a missing or wrongly typed key; a user path breaking section 15 | exit 2, "the question was not well formed" |
| 401 | `unauthorized` | token missing or wrong | none |
| 403 | `forbidden` | Host, Origin, Sec-Fetch-Site, dev-session rules | none |
| 404 | `not_found` | no such route, run, artifact; a placeholder value not matching its pattern; an adapter endpoint's `contract.NotFound` | none |
| 405 | `method_not_allowed` | the path exists with another method; `Allow` header lists them | none |
| 409 | `conflict` | result of a run not finished; cancelling a finished run; deleting a running run | none |
| 413 | `too_large` | body over 1 MiB | none |
| 415 | `unsupported_media_type` | POST/PUT without `application/json` | none |
| 503 | `unavailable` | the kind or adapter endpoint cannot run in this installation (`contract.Unavailable`: literature layer absent, module not built, `rates` not integrated), with the reason in `message` | the CLI's refusal to start ("needs the source checkout") |
| 500 | `crash` | a handler raised something undeclared; the message names the exception type; the traceback goes to stderr and `studio.log`, not to the page | exit 1 |

Three outcomes of a science question are kept apart all the way to the
page, because the CLI keeps them apart in its exit code:

- **malformed** (exit 2): never becomes a run. `POST /api/runs` answers 400
  and nothing is written to the workspace.
- **refused and said why** (exit 3): a run that finishes with
  `outcome.meaning = "refused"` and `outcome.reason` = what the CLI prints
  to stderr, verbatim. It may still have a result (compose prints its report
  and exits 3 when a section refused; md setup writes files and exits 3 when
  measured conditions were asked for and not found), or none (compose's
  UnrecognisedShape): then `GET /api/runs/{id}/result` is 404 and the page
  shows the reason.
- **a crash** (exit 1): status `failed`, `RunRecord.error` `{type, message,
  traceback}`. The traceback is kept for the report-a-bug path; the page
  shows type and message.

Plus one the CLI has and most tools lack: exit 4, a **negative finding**
(`outcome.meaning = "negative"`, `outcome.reason` =
contract.NEGATIVE_MEANING[kind], the command's own words: "the computed
value disagrees with the measured band", "every chain has a blocking
defect", ...). It is a result, drawn as a result with its verdict, never as
an error.

## 7. Endpoints

All paths are under the server's origin. "Token" means rule 3.4.

### Meta

`GET /api/health` -> `Health` `{ok: true, version, api_version, started_at}`.
`version` is `caterva.__version__`, `api_version` is
contract.STUDIO_API_VERSION (1); the page refuses to run against a different
number. Must answer in milliseconds: imports nothing of the engine.

`GET /api/capabilities` -> `Capabilities` (section 10).
`GET /api/capabilities?probe=network` additionally contacts the hosts in
10.2 and fills `network`; without `probe` it never does. Other query keys:
400.

`GET /api/settings` -> `Settings`. `PUT /api/settings` with a full
`Settings` -> the stored `Settings`. Keys: `theme` (`system` | `light` |
`dark`, default `system`), `max_parallel_runs` (1..8, default 2),
`confirm_delete` (default true). Two optional keys (amended by core): a
PUT without one keeps its stored value; GET always returns both.
`gromacs_path` (absolute path of an executable `gmx`, or null to look for
it as section 10 says; it also sets `$GMX` for the runs) and `offline`
(default false; when true the network probe contacts nothing and a run of
any kind whose `needs` include `network` is 503 with that reason).
Unknown or missing keys, or values out of range: 400 naming the `field`.
Stored in `<data dir>/settings.json`.

### Adapter-owned helpers

`GET /api/compose/shapes` -> `ShapesResponse` `{shapes: [...]}`, exactly
`caterva.compose.grammar.shapes()` (owner: compose).

`POST /api/organisms/normalise` with `{name}` -> `NormaliseOrganismResponse`
`{organism, note}`, exactly `compose.organisms.normalise_organism(name)`
(owner: compose). For form hints only; a run normalises through its CLI path
as the CLI does.

`GET /api/structure/{pdb_id}/coordinates` -> `CoordinatesResponse` (owner:
structure): the first model's atoms of the entry's mmCIF, fetched and cached
exactly as `caterva prepare` fetches it, parsed with
`caterva/prepare/cif.py`, columnar (`atoms.x[i]`, `atoms.element[i]`, ...),
coordinates in angstroms as the file gives them, plus the entry's primary
citation. Over contract.MAX_VIEWER_ATOMS (60,000) atoms: only polymer and
ligand atoms of the first model, `truncated: true`. Unknown id: 404 with the
RCSB's words; no network: 503.

### Runs

`POST /api/runs` with `CreateRunBody` `{kind, request, title?}` -> 202
`RunCreated` `{run: RunRecord}` (status `queued`). Before answering, the
adapter's `argv(request)` runs and the result goes through the command's own
parser (`parse_cli`): a malformed request is 400 and no run exists. A kind
that is not available is 503. `title` defaults to the adapter's
`describe(request)`, else the reproducing command line.

`GET /api/runs` -> `RunList` `{runs: [RunSummary], next_cursor}`, newest
first. Query: `kind` (a RunKind), `status` (a RunStatus), `limit` (1..200,
default 50), `cursor` (the previous page's `next_cursor`, opaque). Anything
else: 400.

`GET /api/runs/{id}` -> `RunRecord`.

`DELETE /api/runs/{id}` -> `RunSummary` of the removed run. Moves
`<data dir>/runs/<id>/` into `<data dir>/trash/` (amended by core: out of
History, never erased by the studio, so a mistaken delete is undone by
moving the folder back; files a run wrote into a user directory, section
15, are the user's and are never touched). 409 while `queued` or
`running`.

`GET /api/runs/{id}/result` -> the kind's Result (contract.KIND_SHAPES). 409
while not finished; 404 when the run finished without one (a refusal before
anything was produced, a crash, a cancel, an interruption).

`GET /api/runs/{id}/events` -> `text/event-stream` (section 8.4). Honours a
`Last-Event-ID` request header.

`POST /api/runs/{id}/cancel` with `{}` -> 202 `RunRecord`. 409 when already
finished.

`GET /api/runs/{id}/artifacts/{name}` -> the file, with the recorded
`content_type` and `Content-Disposition: attachment; filename="<name>"`.
`name` must be in the run's `artifacts` list; else 404.

`GET /api/runs/{id}/bundle` -> `application/zip`, filename
`caterva-<id>.zip`: `run.json`, `request.json`, `result.json` (when
present), `events.jsonl`, `artifacts/<name>` for each artifact,
`command.txt` holding `shlex.join(run.cli)`, the command that reproduces the
run in a terminal, and `README.txt` saying what each file is (amended by
core).

### Development

`GET /api/dev/session` -> `DevSession` `{token, api_version}`. Exists only
with `--dev-origin`; section 5.

## 8. Runs, jobs and events

### 8.1 Kinds

`contract.RunKind`: `compose`, `constants`, `sim`, `bind`, `structure`,
`prepare`, `md.setup`, `md.summarise`, `analyze`, `fep.status`,
`complex.check`, `rates`. Section 13 gives each one's request, command,
result and duration. `caterva fep` setup and `caterva complex` build are not
kinds: they write GROMACS inputs from user topologies and are left to the
command line in this version (the Md screen says so and shows the command).

### 8.2 Life of a run

```
queued -> running -> done        (outcome: produced | refused | negative)
                  -> failed      (error: a crash)
                  -> cancelled
queued|running -> interrupted    (found at startup: the server stopped mid-run)
```

- A run id is `yyyymmdd-hhmmss-<kind with . as ->-<8 hex>` in UTC
  (routes.RUN_ID_PATTERN), e.g. `20260930-141502-md-setup-3f9a0c1d`.
- Runs execute in worker threads, at most `settings.max_parallel_runs` at
  once, in submission order. Kinds whose AdapterSpec has `serial=True`
  (compose, sim: they drive roadrunner, antimony and libsbml, none of which
  documents concurrent calls from two threads as supported) also take one process-wide engine lock, so two of them
  never run at once, while network-bound kinds run beside them.
- **Cancel** is cooperative: `POST .../cancel` sets a flag;
  `Progress.check_cancelled()` raises `adapters.Cancelled` at the adapter's
  next check (every stage boundary, and inside loops the adapter drives,
  such as per analysis section). A library call already running finishes
  first; the page says "cancelling" until the `cancelled` status arrives. A
  cancelled run keeps no result.
- **Interrupted**: at startup every run whose `run.json` says `queued` or
  `running` is marked `interrupted` with `finished_at` = now and error
  `{type: "Interrupted", message: "the studio stopped while this run was in
  progress"}`, and its events end. It is never resumed: a search resumed
  later would mix two days' database answers in one result.
- `RunRecord.cli` is the argv that reproduces the run from the repository
  root: `["caterva", "<command>", ...argv]`, or
  `["python3", "scripts/cite.py", ...]` for `constants`. For md.setup with
  the default output directory the recorded `--out` is the absolute run
  directory path.

### 8.3 Outcome

`Outcome` `{exit_code, meaning, summary, reason}`: `exit_code` is what the
CLI exits with for the same request (0, 3 or 4; 2 never becomes a run, 1 is
`failed`), `meaning` from contract.EXIT_MEANING, `summary` one line for
History taken from the result (never invented), `reason` per section 6.
Built only by `contract.outcome_for(kind, exit_code, summary, refusal)`,
which refuses a 3 without the CLI's reason and a 4 from a kind whose command
never exits 4.

### 8.4 Server-Sent Events

`GET /api/runs/{id}/events`, `Content-Type: text/event-stream`,
`Cache-Control: no-store`. Each event is:

```
id: <seq>
event: <status|stage|log|result|error|end>
data: <one line of JSON>

```

- `seq` starts at 1 per run and increases by one; every event is appended to
  `events.jsonl` before it is sent, so a stream opened at any time replays
  the run's whole history, then continues live. With `Last-Event-ID: n` only
  events with `seq > n` are sent.
- The page reads the stream with `fetch`, not EventSource, which cannot add
  a request header (rule 3.4): `src/api/runs.ts`, `followRun`.
- A comment line `: keep-alive` is sent every 15 s while a run is live.
- The server closes the stream after sending `end`.
- Order: `status{queued}`, `status{running}`, then any `stage`/`log`, then
  exactly one of: `result{outcome}` + `status{done, outcome}`;
  `error{error}` + `status{failed}`; `status{cancelled}`;
  `status{interrupted}`; and finally `end{status}`.
- Shapes: `StatusEvent`, `StageEvent` `{stage, label, fraction}`,
  `LogEvent` `{line}`, `ResultEvent` `{outcome}`, `ErrorEvent` `{error}`,
  `EndEvent` `{status}`; every one carries `run_id`, `seq`, `at` (ISO 8601
  UTC, `Z`).
- `stage` keys are per kind (section 13); `label` is a short present-tense
  phrase the page shows under the loading mark ("Searching BRENDA for EC
  2.7.1.1"); `fraction` is 0..1 only where the adapter can count (robustness
  samples done of N), else null. Never a fabricated percentage.
- `log` carries lines the library itself wrote (a compose note, a refusal
  counted on stderr). At most 2,000 per run; then one line saying how many
  were omitted.

## 9. Provenance

Every number that reaches the page is a `SourcedValue`:
`{value, unit, provenance, id?, label?, nonfinite?, interval?}`. `value` is
the library's float, unrounded (JSON round-trips Python floats exactly);
null only when `nonfinite` (`nan`, `inf`, `-inf`) or `interval` says why.
Integers that are counts (events, replicas, atoms) are plain JSON numbers
inside a structure that says what they count; they are not SourcedValues.

`Provenance.kind` is one of five words. The adapter that produced the number
says which, from the library object that carried it; nothing decides a kind
from a name.

| kind | means | required | optional |
|---|---|---|---|
| `measured` | a published measurement, cited | `citation.text` (verbatim, "BRENDA ref 286469"); `organism`; `cross_species`; `conditions` `{ph, temperature_c, buffer, unreported}`; `commentary` (the source row's own text, verbatim, or null); `scope` (row_scope concerns' `plain` text: where the row could be the wrong number for this model) | `spread` (export.Spread, with its own `sentence()`), `chosen_because`, `citation.registry/reference_id/url/pubmed/doi/title/journal/year/via` |
| `fitted` | estimated from data by a fit | `fit.method` | `fit.n_points/residual/stderr/r_squared` |
| `computed` | derived by Caterva from other numbers (a free energy from a Ki, a block average, an ODE expectation) | `method` in the library's words; `inputs` (ids of the numbers it came from) | `note` |
| `placeholder` | stands in for a measurement nobody has made here | `reason`: the library's own sentence (`ParameterOrigin.sentence()`, the resolver's not-found text); `contract.placeholder` refuses an empty one | `table` (the database table that would supply it) |
| `chosen` | somebody chose it | `by`: `user` (in this request) or `default` (a stated default of the command: an argparse default, a motif's starting amount) | `reason` |

Helpers in contract.py, used by every adapter: `sourced`, `computed`,
`chosen`, `placeholder`, `fitted`, `measured_from_measurement`,
`from_parameter_origin` (compose: transcribes `export.provenance_of`, the
one place compose decides an origin, and uses the origin's own sentence), and
`jsonable` (library dataclasses to JSON, no rounding, non-finite to null,
complex to `{re, im}`, numpy to Python, unknown objects refused).

**Citation links.** `citation.url` is set only to a link of a form known to
work: PubMed `https://pubmed.ncbi.nlm.nih.gov/<pmid>/`, DOI
`https://doi.org/<doi>`, RCSB `https://www.rcsb.org/structure/<id>`, UniProt
`https://www.uniprot.org/uniprotkb/<accession>`, and for a BRENDA row the
enzyme page it was read from,
`https://www.brenda-enzymes.org/enzyme.php?ecno=<ec>` (BRENDA has no page per
reference; the page lists the reference by number). Otherwise null, never a
guessed link.

**On the page** every SourcedValue is drawn by one component
(`src/components/provenance/Value.tsx`), which cannot draw a value without
its mark. Section 17.3.

## 10. Capabilities

`GET /api/capabilities` -> `Capabilities`:

| key | how it is decided |
|---|---|
| `version`, `api_version`, `python`, `platform`, `frozen` | `caterva.__version__`, contract.STUDIO_API_VERSION, `platform.python_version()`, `sys.platform`, `getattr(sys, "frozen", False)` |
| `literature` `{available, reason}` | `caterva.checkout.literature_module("fallback_logic")` imports; else `available: false` and `LiteratureLayerUnavailable`'s message. Cached for the process. |
| `network` `{checked, reachable, hosts, checked_at, reason}` | `checked: false` and nulls until `?probe=network`; then one HTTPS HEAD (5 s timeout, `urllib.request`) to each of `www.brenda-enzymes.org`, `rest.uniprot.org`, `search.rcsb.org`, `files.rcsb.org`, `eutils.ncbi.nlm.nih.gov`; `hosts` maps each to true/false; `reachable` is true when all are. |
| `gromacs` `{found, path, version, reason}` | `$GMX` if set, else `gmx`, through `shutil.which` (and `/opt/homebrew/bin/gmx`, `/usr/local/bin/gmx` if not on PATH: a GUI app's PATH is short); version from the first line of `gmx --version` matching `GROMACS version:`, 5 s timeout. Run once per process and on each capabilities request after a failure. |
| `rates` `{available, reason}` | `importlib.util.find_spec("caterva.rates")` is not None AND an adapter registered kind `rates`; else false with which of the two is missing. |
| `ui` `{built, static_dir, reason}` | `static/index.html` exists and holds the placeholder. |
| `data_dir` `{path, writable, runs, reason}` | the resolved data dir, a write probe, the number of run directories. |
| `kinds` | kind -> `KindCapability` `{available, title, command, needs, reason}` for every RunKind: not registered -> "not built yet"; registered -> the adapter's `unavailable()`. |
| `dev_origin` | the `--dev-origin` value or null. |

## 11. The workspace on disk

Default data dir: macOS `~/Library/Application Support/Caterva`; Linux
`$XDG_DATA_HOME/caterva` or `~/.local/share/caterva`; Windows
`%APPDATA%\Caterva`. `--data-dir` overrides. Layout:

```
<data dir>/
  settings.json                  Settings
  studio.log                     server log; rotated at 5 MB, one old copy kept
  instances/<id>.lock            held by each running server (amended by core: a run is
                                 marked interrupted only when its owner's lock is free)
  trash/<run id>/                runs deleted from History (amended by core)
  runs/<run id>/
    run.json                     RunRecord, schema "caterva.studio.run/1"
    request.json                 the request as accepted (after parse_cli)
    result.json                  the kind's Result, when one was produced
    events.jsonl                 {"event": name, "data": {...}} per line, in seq order
    owner                        the instance id of the server running it (amended by core)
    artifacts/<name>             every file listed in run.artifacts
    md-setup/                    md.setup's default output directory
```

- Directories are created 0700, files 0600. Every JSON file is written to a
  temporary name in the same directory and moved into place with
  `os.replace`, so a reader never sees half a file.
- `run.json` is rewritten on every status change and when the run finishes;
  `events.jsonl` is append-only.
- A `schema` other than `caterva.studio.run/1` is listed in History as
  unreadable by this version, not guessed at.
- History reopens a run from `run.json` + `result.json`; a rerun is a new
  `POST /api/runs` with the stored request. The engine's own caches stay
  where the CLI keeps them (`caterva prepare`'s `~/.cache/caterva/prepare`).

## 12. Adapters

`caterva/studio/adapters/__init__.py` holds the registry; one module per
owner-area exists already, each with `register(registry)` that registers
nothing until built (`ADAPTER_MODULES` is fixed: nobody appends to it).

An adapter module:

1. Builds an `AdapterSpec` per kind: `kind`, `title`, `command`, `needs`
   (subset of `network`, `literature`, `gromacs`), `argv(request)`,
   `run(request, ctx)`, `unavailable()`, `describe(request)`, `cli_prefix`,
   `serial`.
2. `argv(request)` turns the JSON request into the exact argv the CLI would
   receive; unknown keys or wrong types raise `contract.Malformed(message,
   field)`. The server then runs `parse_cli(build_parser, argv, prog)` (the
   command's own parser, with `error` raising Malformed) and any post-parse
   checks the CLI makes with `parser.error`. Where a CLI makes a check after
   parsing without `parser.error` (section 14), the owner moves it into the
   parser path first.
3. `run(request, ctx)` imports the engine lazily (so `/api/health` stays
   fast), calls the same library functions the CLI calls in the same order,
   reports `ctx.progress.stage(...)`, checks `ctx.progress.check_cancelled()`,
   and returns `AdapterOutcome(exit_code, result, summary, refusal,
   artifacts)`. Anything it raises other than Malformed or Cancelled is a
   crash (status `failed`).
4. Owns its endpoints through `registry.add_endpoint(handler, fn,
   owner=<module>)`, only for routes whose `Route.owner` is that module.
5. Never names the test-only recorded-answer environment variables
   (`Tests/test_recorded_env_is_test_only.py` fails if a module under
   `caterva/studio/` does). Offline parity tests set them in `caterva/tests/`.

**Parity test, one per kind** (`caterva/tests/test_studio_<kind>.py`): run
the CLI's `main(argv)` with stdout captured, and the adapter's `run` on the
request that `argv` maps to the same argv, on real inputs (committed BRENDA
pages under `Tests/fixtures/recorded/` with the replay variables set by the
test; `Tests/fixtures/brenda_ldh_fixture.html`; committed mmCIF/GROMACS
fixtures where they exist), and assert: the same exit code; every number in
the Result equals the library value the CLI printed from (compared on the
library object, not by parsing text, and where the CLI prints the number,
the printed text formats the Result's value to the same string); the
`report_markdown`/`report_text` equals the CLI's stdout. Network-only kinds
without a recording are tested for their refusal path offline and marked for
the live CI job rather than skipped silently (`check_no_silent_skips`).

## 13. Kinds, one by one

Durations are measured orders of magnitude on this machine, for the page's
expectations; they are not promises.

| kind | command | library path (what the adapter calls) | needs | duration | exit codes |
|---|---|---|---|---|---|
| `compose` | `caterva compose DESCRIPTION ...` | `organisms.normalise_organism`; `pipeline.compose`; with `subject`: `__main__._search_the_literature`; `_precompute_for_verdict`; `report.dossier(...)` (stability, time course, ranking, sweeps, verdict); `_analyses` sections; `export.provenance_of` and `to_sbml`, `to_antimony`, `to_parameter_csv`, `to_methods_paragraph` | network + literature only with `subject` | seconds; a search adds seconds to a minute; `--robustness` (default 200 samples, each a steady-state search) minutes | 0, 3 (UnrecognisedShape; a refused section; a refused search) |
| `constants` | `python3 scripts/cite.py ...` | payload as `cite.build_payload`; report_lab's resolution (fallback_logic: BRENDA, UniProt, NCBI Taxonomy, PubMed) | network, literature; source checkout only | seconds to a minute | 0, 3 |
| `sim` | `caterva sim ssa ...` | `caterva_engine.simulate_gillespie_ssa` / `_bimolecular` | none | milliseconds to seconds | 0 |
| `bind` | `caterva bind --ec ...` | `brenda_client.fetch_brenda_html`; `_rows`/`survey`/`_compound_names`; `bind.core.target`, `judge`; `report(...)` returning (text, code, payload) | network, literature | seconds | 0, 3, 4 (disagrees) |
| `structure` | `caterva structure --subject ...` | `normalise_organism`; `search.find_structures`; `StructureSearch.ranked()`; `Structure.cite()`; `chimerax.script` | network | seconds | 0, 3 |
| `prepare` | `caterva prepare ENTRY` | `run_audit(entry, cached(live_fetch(), _cache_dir()))`; `report(audit, ph)`; `dataclasses.asdict(audit)` | network unless a local .cif | seconds | 0, 3, 4 (every chain blocked) |
| `md.setup` | `caterva md --pdb ... --out ...` | `_from_kinetics` (a compose search) when subject+substrate; `setup.MdSetup(...)`, `.files()`, `.parameters` | network + literature only with subject | milliseconds; a search adds seconds | 0, 3 (measured conditions asked for, not found; files still written) |
| `md.summarise` | `caterva md --summarise DIR` | `convergence.collect`, `summarise`, `report` | none | seconds | 0, 3, 4 (not consistent) |
| `analyze` | `caterva analyze DIR [--gromacs\|--no-run\|--script-only]` | `setup_info`, `catalytic_residues` (M-CSA via prepare: network), `plan`, `measure_native` or `run_gromacs` + `measure`, `Analysis`, `report` | network; gromacs for `gromacs` mode | seconds to minutes (reads every .xtc) | 0, 3, 4 (not a result) |
| `fep.status` | `caterva fep --summarise DIR` | `summarise` (reads caterva-fep.json and BAR output; `bind.core.judge`) | none | seconds | 0, 3, 4 |
| `complex.check` | `caterva complex --check DIR --ligand RES` | `complex.check`, `pose_over_trajectory`, `centroid_shift` | none | seconds | 0, 3, 4 (left its pose) |
| `rates` | reserved for `caterva rates` | arrives from another branch | declared then | | |

Request to argv mapping, stated where it is not one flag per key:

- compose: `description` positional; `compounds` -> repeated
  `--compound PORT=NAME` in key order; `sweep.parameters` -> repeated
  `--sweep`, `low/high/steps` -> `--sweep-from/--sweep-to/--sweep-steps`;
  `analyses.robustness.samples` null -> bare `--robustness`;
  `analyses.stochastic` -> `--stochastic V [--stochastic-end] [--stochastic-seed]`;
  `knockout`/`overexpress` repeated. `--export`, `--antimony`, `--shapes`
  are never produced (exports are artifacts; shapes is an endpoint).
- constants: exactly one of `ec`, `enzyme`; `quantities` -> repeated
  `--quantity`; never `--json` or `--fixture`.
- sim: `ssa` subcommand first; `seed` required here (a trajectory whose seed
  is not recorded cannot be reproduced, ADR 0005) although the CLI allows
  none; never `--out` (the table is the result, and a CSV artifact).
- bind: `mode` -> `--inhibitor NAME` | `--list` | `--survey`; `computed`
  -> `--computed=VALUE±ERROR` (the `=` form) and `--unit`; never `--html`
  or `--json`.
- structure: `chimerax: true` -> `--chimerax <run dir>/artifacts/structure.cxc`,
  recorded as an artifact.
- prepare: never `--out` or `--json` (the report and the audit are the
  result); `entry` is a PDB id or a user path (section 15).
- md.setup: `out` absent -> `--out <run dir>/md-setup`; `temperature_k` ->
  `--temperature`; `ionic_strength_m` -> `--ionic-strength`.
- analyze: `mode` -> nothing (`native`) | `--gromacs` | `--no-run` |
  `--script-only`.

Stage keys (the owner may add, never rename once shipped): compose
`compose`, `search`, `precompute`, `dossier`, `section:<flag>`, `exports`;
constants `resolve`, `document`; sim `simulate`; bind `fetch`, `rows`,
`target`, `judge`; structure `search`, `rank`; prepare `fetch`, `audit`;
md.setup `conditions`, `write`; md.summarise `read`, `summarise`; analyze
`plan`, `measure`, `report`; fep.status `read`, `judge`; complex.check
`check`, `trajectory`.

Result shapes are the TypedDicts in contract.py's "Kinetics kinds" and
"Structure kinds" sections. Every Result that has a CLI report carries it
verbatim (`report_markdown` or `report_text`) so the page can show "the same
document the terminal prints" and a parity test can compare them.

## 14. Gaps: what the CLI prints that has no structured form yet

Each is fixed by its owner with an accessor beside the printer that the
printer and the adapter both call, keeping the CLI's stdout byte-identical
(the owner adds a test proving it). Never a second computation in the adapter.

| module | gap | fix |
|---|---|---|
| `caterva/compose/__main__.py` | `_analyses` prints each section to stdout through `Sections`; each section's report object (ScaleReport, RobustnessReport, DesignReport, ...) is built inside a closure and dropped | give `Sections` a list of records (key, title, status, text, refusals, data) and `_analyses` a `stream` argument; return the records with the code |
| same | `_search_the_literature`, `_precompute_for_verdict` are private; `caterva md` already imports the first | make them public, same behaviour |
| `scripts/cite.py` | parser built inside `main`; runs report_lab with `sys.executable`, which in a frozen app is `caterva`; `scripts/` is not in the wheel | `build_parser(prog)`; an in-process report_lab function returning its dict; constants is source-checkout only and says so |
| `scripts/report_lab.py` | the JSON carries the document, not the per-constant KineticResult | add `"resolved": {name: result.model_dump(mode="json")}` |
| `caterva/cli.py` | parser built inside `main`; the ODE expectation and the event count are computed inside the printing code | `build_parser(prog)`; a function returning `expected`, used by the printer |
| same | `--k` defaults to 0.5 for the bimolecular reaction while its help says 0.005 | report as a CLI defect; the page always sends `k` |
| `caterva/bind/__main__.py` | parser built inside `main`; `--computed` rewritten before parsing; `_compound_names` private | `build_parser(prog)`; argv emits the `=` form; make the names function public |
| `caterva/structure/__main__.py` | `--chimerax` with an empty ranking crashes on `ranked()[0]` | refuse with a reason (exit 3) |
| `caterva/prepare/__main__.py` | the protonation table is computed inside `protonation_section`; the exit rule ("clean chain") is an expression in `main` | a per-residue assessment function; a `clean` function or Audit property |
| `caterva/md/__main__.py` | computing the setup is interleaved with writing and printing; four refusals return 2 after parsing, outside argparse | extract the pre-write part; move the checks into `parser.error` |
| `caterva/md/setup.py` | `Conditions` carries the measured temperature's citation only inside the `temperature_source` sentence | keep the Measurement beside the sentence |
| `caterva/analyze/__main__.py` | `main` builds the Analysis inline between argument handling and printing (feat/analyze-pca and feat/analyze-sasa edit this file: keep the change small) | one function returning the Analysis and whether a script was written |
| `caterva/fep/__main__.py` | `summarise` computes and prints in one pass, returns only the code; parser inside `main` | a function returning per-replica values, mean, sigma, Verdict; a printer over it; `build_parser(prog)` |
| `caterva/fep/complex.py` | `--check`'s "kept" judgement is inside `main`; `--ligand-itp` is accepted with `--check` and not passed to `check()` | a function returning values and the judgement; report the ignored flag as a CLI defect (the request has no ligand_itp) |

## 15. User paths

Accepted only here: `prepare.entry` (a local `.cif`/`.mmcif` file),
`md.setup.out` (a directory to write), and `directory` of `md.summarise`,
`analyze`, `fep.status`, `complex.check` (a finished run's directory). Rules,
enforced in the adapter's `argv` (so they are 400 `malformed` with `field`):

- absolute, no NUL, at most 4,096 characters; resolved with
  `Path.resolve(strict=True)` (inputs) or the parent resolved strictly
  (`md.setup.out`), so symlinks are followed once and the resolved path is
  what is recorded and used;
- an input file must be a regular file with an allowed suffix; an input
  directory must be a directory;
- `md.setup.out` must not exist, or be an empty directory, or be a directory
  holding a previous `caterva md` setup (its `PROVENANCE.md`); it must not be
  inside `<data dir>` except the run's own default;
- whether the directory is the right kind of directory (a finished md run, a
  caterva fep run) is the library's decision and its refusal (exit 3), not
  re-checked by the adapter.

These kinds write into the user's directory exactly what the CLI writes
there (md setup files; `CONVERGENCE.md`; `analyze.sh`, the chi1 index,
`ANALYSIS.md`), and the Result lists what was written. Those files are never
served over HTTP; the page shows the path, and inside the app can reveal it
in Finder (section 16).

## 16. The desktop shell

`macos/` (owner: desktop): a Swift AppKit app compiled with `swiftc` from the
Command Line Tools (no Xcode project).

- Launch the bundled frozen `caterva studio --port 0 --no-browser
  --print-url` from `Caterva.app/Contents/Resources/caterva/caterva`, with
  stdin a pipe the shell holds open; read stdout until
  `CATERVA_STUDIO_URL=`; give up after 60 s with the native error view
  showing the last stderr lines.
- One window, a `WKWebView` loading the URL, unified title bar in the paper
  colour (`#FDF8EE`; ink `#2A2D35` in dark appearance), minimum size 1024 x
  680.
- Navigation outside the server's origin opens in the default browser, never
  in the web view (citations, PubMed, RCSB links).
- `<input type=file>`: `WKUIDelegate`'s open panel. Downloads (artifact and
  bundle exports, which the page makes as Blob object URLs): `WKDownload`
  with an `NSSavePanel`.
- Bridge: a `WKScriptMessageHandlerWithReply` named `caterva`, answering
  `{action: "chooseDirectory", purpose}` and `{action: "chooseFile",
  purpose, extensions}` with an absolute path or null (NSOpenPanel), and
  `{action: "reveal", path}` (NSWorkspace). The page's side is
  `src/lib/desktop.ts`; in a plain browser the page falls back to a text
  field for the path.
- If the server process exits, a native error view replaces the web view
  with the exit status, the last stderr lines and a Restart button.
- Quit: close stdin, SIGTERM, wait 5 s, SIGKILL.
- Unsigned: no Apple Developer ID. The DMG's README and the app's first-run
  sheet say how to open an unsigned app (Control-click, Open; or System
  Settings, Privacy & Security, Open Anyway). Never claim notarisation.
- Packaging: the page is built (`pnpm ... run build`), the wheel is built
  with `caterva/studio/static/**` inside (pyproject package-data), frozen by
  `scripts/build_app.py`, wrapped as `Caterva.app`, and put in a DMG with
  `hdiutil`, by a build script and a GitHub Actions workflow (macos-14
  runner), which runs `caterva studio --self-test` from the frozen folder
  before packaging.

## 17. The page

### 17.1 Screens

Routes are the table in `src/routes.tsx`; nav, command palette and router
all read it. Every screen is lazy-loaded, has one primary action, and has
the four states below. "Loading" is always the dotted-C mark's dots in
motion with the current SSE stage label, never a generic spinner. A refusal
is shown as a result with its reason, in the command's words, never as a
red error.

| route | purpose | primary action | endpoints | empty | loading | error | refusal / negative |
|---|---|---|---|---|---|---|---|
| `/` Home | what this installation can do and the runs opened last | open a recent run, or start one from a kind | health, capabilities, runs (limit 8) | no runs yet: the three first questions to ask, as real commands the forms prefill | mark + "Connecting to the studio server" | server not reachable: how to start it | capabilities that are off, each with its reason (no literature layer, no gmx) |
| `/compose` | build a model from the shape of a mechanism; see where every number came from | Compose | compose/shapes, organisms/normalise, runs (kind compose), result, artifacts | description field with the shapes list one keystroke away | stage labels (search, dossier, each section) | request 400 under the field it names; crash with type and message | UnrecognisedShape's text; refused sections under their own headings |
| `/constants` | an enzyme's measured constants, each with the paper | Look up | runs (constants) | the form; which fields are required | resolve, document | 503 when not a source checkout, with the reason | ambiguous enzyme name with every candidate named |
| `/rates` | reserved for `caterva rates` | declared when integrated | capabilities | shown only when `rates.available` | | | |
| `/sim` | exact stochastic kinetics, seeded | Simulate | runs (sim) | the form, seed prefilled and editable | simulate | 400 | none |
| `/bind` | the measured binding free energy a simulation is held to | Build the target / Judge | runs (bind) | EC and organism; list compounds | fetch, rows, target | 503 without the literature layer | no Ki rows; none fits the state (with the other state suggested); negative: "disagrees" drawn as a verdict |
| `/structure` | an enzyme's PDB entries, cited, with a 3D view | Search | runs (structure), structure coordinates, artifacts (.cxc) | EC, organism, gene | search, rank; viewer loading its atoms | no network | several proteins for one EC: choose gene or UniProt |
| `/prepare` | audit an entry before simulating it | Audit | runs (prepare) | PDB id or a chosen .cif | fetch, audit | 400 for a bad path | negative: every chain blocked, the blocking findings first |
| `/md` | a GROMACS setup whose every parameter says where it came from; whether replicas converged; FEP and complex status | Write setup / Summarise / Check | runs (md.setup, md.summarise, fep.status, complex.check), capabilities (gromacs) | choose a PDB entry (from Structure or Prepare) | conditions, write | gmx not found: setup still works, running it needs GROMACS | measured conditions not found (files still written); negative: not converged, disagrees, left its pose |
| `/analyze` | catalytic geometry across replicas, a result only when replicas agree | Analyze | runs (analyze) | choose a finished md directory | plan, measure | not a finished run, in the library's words | negative: which quantities are not results and why |
| `/history` | every run: request, outcome, files | reopen, rerun, export bundle, delete | runs list, run, result, bundle, delete | nothing run yet | list skeleton in the mark's rhythm | workspace unreadable, with the path | refused and negative runs listed with their reasons, filterable |
| `/settings` | theme, parallel runs, where the workspace is | save | settings, capabilities (data_dir) | | | 400 per field | |
| `/about` | version, licences (Caterva, fonts, BRENDA terms), what this installation can reach | probe the network | health, capabilities?probe=network | | probing | | each unreachable host named |

### 17.2 Look and behaviour

Identity from `Science-Agent-Pipeline/artifacts/caterva-landing`
(PRODUCT.md, DESIGN.md, `src/index.css`, the mark component): paper
`#FDF8EE`, ink `#2A2D35`, signal `#5D7F8D`; the dotted C (8 dots, one signal
dot); the wordmark in widely tracked lowercase Spectral. Tokens are OKLCH in
`src/index.css` (names fixed: `--surface`, `--surface-raised`, `--fg`,
`--muted`, `--rule`, `--signal`, `--signal-deep`, `--caution`, `--danger`,
`--focus`, `--prov-*`); neutrals tinted, never `#000`/`#fff`.

- Themes: light paper by default; dark (ink surfaces) follows
  `prefers-color-scheme`; `[data-theme="light"|"dark"]` on `<html>`
  overrides; Settings stores the choice (`settings.theme`) and the page
  mirrors it in `localStorage` (`caterva.theme`) so the first paint is right.
- Type: Spectral for display and the wordmark; Atkinson Hyperlegible Next for
  UI text; DM Mono with `font-variant-numeric: tabular-nums` for every
  number, unit, citation and piece of code. Fonts are bundled
  (`@fontsource/*`, OFL-1.1; licence texts in `public/licenses/`), never
  fetched: the app works offline.
- Motion: exponential ease-out (`--ease-out-expo`) on transform and opacity
  only; `prefers-reduced-motion` stops the loading dots' travel and every
  transition.
- Keyboard: Cmd-K (Ctrl-K elsewhere) opens the command palette (cmdk) with
  every route and every primary action; every action reachable by keyboard;
  visible focus ring in `--focus`; WCAG AA contrast in both themes.
- Layout works from a 1024 px window to a 27-inch display
  (react-resizable-panels for form | result splits).
- Refused by design: side-stripe borders, gradient text, decorative glass,
  hero-metric templates, identical card grids, modal-first flows, em dashes
  in copy, sample numbers, mock results, lorem ipsum.

### 17.3 Provenance as the visual system

Every SourcedValue wears a mark (`ProvenanceMark.tsx`), shape first and
colour second so it survives greyscale:

| kind | mark |
|---|---|
| measured | solid signal dot (the mark's own signal dot); the number is a button: one click opens the citation (text, registry, reference, commentary, conditions, scope, spread, link) |
| fitted | ring |
| computed | small square; hover/focus shows method and inputs |
| placeholder | hollow dashed dot in the caution colour; hover/focus shows the reason |
| chosen | short bar; caution when a default chose it, ink when the user did |

A number is formatted for display only by `src/lib/format.ts`, from the
value the API sent; the full-precision value is one hover away and is what
is copied.

### 17.4 Test fixtures

Component tests render real API responses captured from the running backend
(or the contract helpers over the real engine), committed under
`src/__fixtures__/api/<area>/` with a README saying the exact command and
date that produced them (`src/__fixtures__/api/contract/README.md` is the
model). No hand-typed numbers.

### 17.5 Dependencies the page may use

Everything in the package's `package.json`, and nothing else:
React 19.1 (catalog), react-dom, wouter, @tanstack/react-query,
@tanstack/react-virtual (long tables: Ki rows, atoms, history), zod,
@radix-ui/react-{accordion, checkbox, collapsible, context-menu, dialog,
dropdown-menu, hover-card, label, popover, progress, radio-group,
scroll-area, select, separator, slider, slot, switch, tabs, toggle,
toggle-group, tooltip, visually-hidden}, cmdk, sonner, lucide-react,
framer-motion, react-resizable-panels, recharts, d3-{array, color, format,
interpolate, scale, shape}, three and @react-three/fiber (the structure
viewer), markdown-it (showing the CLI's own markdown report), clsx,
class-variance-authority, tailwind-merge, @fontsource/{spectral,
atkinson-hyperlegible-next, dm-mono}. Dev: vite, @vitejs/plugin-react,
tailwindcss + @tailwindcss/vite, typescript, vitest, jsdom,
@testing-library/{react, dom, jest-dom, user-event}, @types/*.

A builder who truly needs another package says so in their report, with
the reason; nobody but the integrator edits `package.json` dependencies or
`pnpm-lock.yaml`.

## 18. Ownership map

Five builders work at once from branch `studio/contract`. A file is edited
only by its owner. "Shared" files were pre-created here so that nobody needs
to edit them; changing one is a contract amendment (section 21).

**core** (backend server; worktree `wt-studio`, launch configs
`studio-backend`/`studio-ui`, `studio-packaged`):
- `caterva/studio/__main__.py` (replace `main`; keep the parser's flags)
- new: `caterva/studio/server.py` (socket layer, SSE writing),
  `caterva/studio/dispatch.py` (pure dispatch, the core handlers of every
  route whose `owner` is `core`), `caterva/studio/security.py`,
  `caterva/studio/jobs.py`, `caterva/studio/workspace.py`,
  `caterva/studio/capabilities.py`, `caterva/studio/static_files.py`
  (static serving, token injection, the missing-build page)
- tests: `caterva/tests/test_studio_server.py`,
  `test_studio_security.py`, `test_studio_jobs.py`,
  `test_studio_workspace.py`, `test_studio_capabilities.py`, and
  `test_studio_socket.py` (real sockets; run in CI, fail loudly where binding
  is refused rather than skipping)

**sci-kinetics** (worktree `wt-studio-kin`, `studio-kin-backend`/`studio-kin-ui`):
- `caterva/studio/adapters/compose.py`, `constants.py`, `sim.py`, `bind.py`
- the gaps of section 14 in `caterva/compose/__main__.py`, `scripts/cite.py`,
  `scripts/report_lab.py`, `caterva/cli.py`, `caterva/bind/__main__.py`
- contract.py section "Kinetics kinds" and the same section of `types.ts`
  (add optional keys or new types only, both files in one commit)
- screens `src/screens/Compose.tsx`, `Constants.tsx`, `Sim.tsx`, `Bind.tsx`,
  and new files under `src/screens/kinetics/`
- tests `caterva/tests/test_studio_{compose,constants,sim,bind}.py`; UI
  fixtures under `src/__fixtures__/api/kinetics/`

**sci-structure** (worktree `wt-studio-str`, `studio-str-backend`/`studio-str-ui`):
- `caterva/studio/adapters/structure.py`, `prepare.py`, `md.py`,
  `analyze.py`, `fep.py`
- the gaps of section 14 in `caterva/structure/__main__.py`,
  `caterva/prepare/__main__.py`, `caterva/md/__main__.py`,
  `caterva/md/setup.py`, `caterva/analyze/__main__.py` (small),
  `caterva/fep/__main__.py`, `caterva/fep/complex.py`
- contract.py section "Structure kinds" and the same section of `types.ts`
- screens `src/screens/Structure.tsx`, `Prepare.tsx`, `Md.tsx`,
  `Analyze.tsx`, and new files under `src/screens/structure/` (the 3D viewer
  lives there)
- tests `caterva/tests/test_studio_{structure,prepare,md,analyze,fep}.py`;
  UI fixtures under `src/__fixtures__/api/structure/`

**ui** (the page's foundation; worktree `wt-studio-ui`,
`studio-foundation-backend`/`studio-foundation-ui`):
- in `Science-Agent-Pipeline/artifacts/caterva-studio/`: `index.html`,
  `src/main.tsx`, `src/App.tsx`, `src/index.css`, `src/components/**`,
  `src/lib/**`, `src/api/client.ts`, `src/api/runs.ts`, `src/api/useRun.ts`,
  `src/screens/{Home,History,Settings,About,Rates}.tsx`, `src/__tests__/**`,
  `public/**`, `vite.config.ts`, `vitest.config.ts`, `tsconfig*.json`,
  package.json `scripts` (not dependencies)
- `src/routes.tsx`: the ui owner may change titles, purposes and groups; no
  one adds, removes or renames a path
- the components every screen uses (`Value`, `ProvenanceMark`, `Screen`,
  states, `Loading`, forms, tables, charts, the command palette) are the ui
  owner's; science screens import them and do not fork them. A science owner
  who needs a change asks in their report and meanwhile composes, never
  copies.

**desktop** (macOS shell, packaging, workflows):
- `macos/**` (Swift sources, Info.plist, icon set, the first-run text, the
  DMG README)
- new `scripts/build_studio_app.py` (the page build, wheel, freeze,
  Caterva.app, DMG) and its test
- the studio-specific parts of `scripts/build_app.py` (the frozen-folder
  checks gain `caterva studio --self-test`)
- `.github/workflows/studio-dmg.yml` (new), and the CI steps that build and
  test the page and run the socket tests (`.github/workflows/tests.yml`: the
  desktop owner is the only builder who edits workflows)

**Shared, pre-created by the contract, edited by nobody else in parallel:**
`docs/studio/CONTRACT.md`; `caterva/studio/__init__.py`;
`caterva/studio/contract.py` (outside the two science sections);
`caterva/studio/routes.py`; `caterva/studio/adapters/__init__.py`
(`ADAPTER_MODULES`, the registry); `caterva/studio/adapters/rates.py`;
`src/api/types.ts` (outside the two science sections); `src/routes.tsx`
paths; `caterva/app.py` (`studio` is registered); `pyproject.toml`
(package-data); `.gitignore`; `Science-Agent-Pipeline/pnpm-lock.yaml`,
`pnpm-workspace.yaml` and the package's `dependencies`/`devDependencies`;
`caterva/tests/test_studio_contract.py`.

Not edited by any builder: `CHANGELOG.md`, `README.md`, `docs/readmes/*`,
`Science-Agent-Pipeline/artifacts/caterva-landing/**`, any
`.claude/launch.json`. CHANGELOG entries and README text go in the report.

## 19. How to install in a new worktree

Proven on 2026-09-30 in `/tmp/claude-501/wt-contract` from a state with no
`node_modules` anywhere in the workspace. pnpm 11.20.0 puts its content store
beside the project (`/private/tmp/claude-501/.pnpm-store/v11` for worktrees
under `/tmp/claude-501`), and every package the studio needs is in it now,
so `--offline` works from any worktree there.

Any node 24 and pnpm 11.20.0 will do; the two lines below are where they
are on the machine these worktrees were made on.

```sh
export PATH=/Users/smyan/.openclawdesk/node/bin:$PATH      # node 24
PNPM=/Users/smyan/.nvm/versions/node/v24.17.0/bin/pnpm       # pnpm 11.20.0
cd <worktree>/Science-Agent-Pipeline

# the studio package and its dependencies only (about 15 s):
$PNPM install --frozen-lockfile --offline --filter @workspace/caterva-studio...
# if the store lacks a package (a new machine), the same without --offline:
#   $PNPM install --frozen-lockfile --prefer-offline --filter @workspace/caterva-studio...
# the whole workspace (root typecheck, landing, api-server):
#   CI=true $PNPM install --frozen-lockfile --prefer-offline

cd artifacts/caterva-studio
$PNPM run typecheck      # tsc over src and over the two build configs
$PNPM run test           # vitest, jsdom
$PNPM run build          # writes <worktree>/caterva/studio/static/
```

- The "failed to copy trust settings" lines pnpm prints are harmless.
- `--frozen-lockfile` is not optional: it proves the lockfile satisfies
  every `package.json`, and it never rewrites the lockfile.
  `minimumReleaseAge: 1440` in `pnpm-workspace.yaml` stays.
- `node_modules/vite/bin/vite.js` is reachable from the package directory
  because pnpm links each direct dependency into the package's own
  `node_modules/` (`node_modules/vite` is a symlink into the workspace's
  `node_modules/.pnpm/vite@7.3.6_.../node_modules/vite`). That is what the
  launch configs run: `node node_modules/vite/bin/vite.js --config
  vite.config.ts` from `artifacts/caterva-studio`, with `STUDIO_API` and
  `PORT` in the environment.
- If an install ever asks to remove a modules directory ("Aborted removal of
  modules directory due to no TTY"), rerun with `CI=true` or remove that
  worktree's `node_modules` first.
- `vite build` empties and rewrites `caterva/studio/static/` (ignored by
  git). The Python side needs nothing installed beyond the venv:
  `/Users/smyan/Desktop/Coding/Terrium/.claude/worktrees/optimistic-taussig-6914c2/.venv/bin/python -m caterva.app studio --help`.

## 20. Verification and guards

Every builder, before finishing, from the worktree root with the venv
python:

```sh
PY=/Users/smyan/Desktop/Coding/Terrium/.claude/worktrees/optimistic-taussig-6914c2/.venv/bin/python
$PY -m pytest -p no:cacheprovider -o addopts="" caterva/tests/test_studio_contract.py caterva/tests/test_studio_*.py -q
$PY -m caterva.app --help | grep studio
```

plus the page commands of section 19 for anyone who touched the package,
and the guards: `scripts/check_python_bug_lints.py`,
`check_no_orphan_modules.py`, `check_cli_surface_documented.py`,
`check_exports_reach_a_caller.py`, `check_no_vacuous_tests.py`,
`check_no_silent_skips.py`, `check_no_generated_files_tracked.py`,
`check_no_unsourced_ui_numbers.py`, `check_doc_paths_resolve.py`,
`check_doc_links.py`, `check_guard_wiring.py`, `check_runner_boundary.py`,
`check_findings_reach_a_surface.py`, `check_both_front_ends_read_it.py`,
`check_prompt_injection.py`, `check_port_binding.py`,
`check_dependencies_declared.py`. Several read only tracked files: commit,
then run them. Complaints from `check_landing_test_counts.py` or
`check_documented_counts.py` about counts are expected; report them, do not
fix counts.

The sandbox these builders run in cannot bind ports (EPERM): test the
server through dispatch; the socket tests run in CI. To see the app, start
the named launch configurations with the preview tools and stop them when
done.

## 21. Amending this contract

A builder who finds the contract wrong (a shape the library cannot fill, a
rule that cannot hold) does not work around it. They write the amendment in
their report: the section, the change, the reason and which other owners it
touches. The integrator applies amendments to `contract.py`, `types.ts`,
`routes.py` and this document in one commit, and bumps
contract.STUDIO_API_VERSION when a page built against the old shapes would
misread the new ones.
