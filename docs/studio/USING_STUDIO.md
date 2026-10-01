# Running Caterva Studio from a checkout

Caterva Studio is a page in a browser (or in the macOS app's window) over a
small server on your own computer. The server runs the same library
functions the `caterva` commands run, and keeps every run so you can reopen
or export it later. This page is for running it from a source checkout; the
rules the server follows are in [CONTRACT.md](CONTRACT.md).

## Start it

From the repository root, with the project's Python environment:

```sh
python -m caterva.app studio
```

It picks a free port on 127.0.0.1, opens your default browser on it, and
logs to the terminal. Stop it with Ctrl-C.

The first time, the page itself may not be built (it is made at release
time and not committed). The server then answers with a short page saying
so; build it once from `Science-Agent-Pipeline/`:

```sh
pnpm install --frozen-lockfile --filter @workspace/caterva-studio...
pnpm --filter @workspace/caterva-studio run build
```

and reload. The build is written to `caterva/studio/static/`.

## The flags

```
caterva studio [--host 127.0.0.1] [--port N] [--no-browser] [--dev-origin URL]
               [--data-dir PATH] [--print-url] [--self-test]
```

| flag | what it does |
|---|---|
| `--host` | The loopback address to listen on: `127.0.0.1` (default), `::1` or `localhost`. Any other address is refused (exit 2): the studio is never reachable from another computer. |
| `--port N` | The port to listen on. `0` (default) picks a free one. A port in use is refused (exit 3). |
| `--no-browser` | Do not open the browser. |
| `--dev-origin URL` | For working on the page: also accept requests from the Vite development server at `URL` (`http://127.0.0.1:<port>` or `http://localhost:<port>`). Development only. |
| `--data-dir PATH` | Where runs, settings and the log are kept. Default: `~/Library/Application Support/Caterva` on macOS, `$XDG_DATA_HOME/caterva` or `~/.local/share/caterva` on Linux, `%APPDATA%\Caterva` on Windows. A folder that cannot be written is refused (exit 3). |
| `--print-url` | Once listening, print one line `CATERVA_STUDIO_URL=<url>` to stdout. Nothing else is ever printed to stdout. The macOS app reads this line. |
| `--self-test` | Start on a free port in a temporary data folder (or `--data-dir`), request `/api/health` and `/` over a real socket, print one line per check, stop. Exit 0 when every check passed, 1 otherwise. |

Exit codes: 0 stopped cleanly (or the self-test passed), 1 a crash or a
failed self-test, 2 a malformed command line, 3 refused and said why.

The server stops cleanly on Ctrl-C, on SIGTERM, when the process that
started it exits, and when its stdin is a pipe and that pipe closes (how
the macOS app tells it to stop). Runs still going are marked interrupted;
they are never resumed later.

## Where things are kept

```
<data dir>/
  settings.json     theme, how many runs at once, the GROMACS path, offline mode
  studio.log        the server's log (rotated at 5 MB, one old copy kept)
  runs/<run id>/    one folder per run: run.json, request.json, result.json,
                    events.jsonl, artifacts/
  trash/            runs deleted from History; delete this folder yourself to free the space
```

A run can be exported from History as a zip holding those files, the
command that reproduces it in a terminal (`command.txt`), and a README
saying what each file is.

## Settings

Set on the page (Settings) or with `PUT /api/settings`:

- `theme`: `system`, `light` or `dark`.
- `max_parallel_runs`: 1 to 8 runs at once (default 2). Runs that drive the
  simulation engine still run one at a time.
- `confirm_delete`: ask before deleting a run.
- `gromacs_path`: the `gmx` program to use, when it is not found on its own
  (it is looked for as `$GMX`, `gmx` on PATH, then `/opt/homebrew/bin/gmx`
  and `/usr/local/bin/gmx`).
- `offline`: the studio contacts no network host on its own, and refuses to
  start a run of any kind that may need the network (literature lookups,
  structure searches), saying why. Turn it off to run those.

## Security, briefly

The server listens on loopback only, refuses requests whose `Host` header
does not name it (a defence against DNS rebinding), refuses requests from
other web origins, and requires a per-launch session token on every API
request. The token is written into the page the server serves and is never
put in a URL or on disk. Section 3 of [CONTRACT.md](CONTRACT.md) has the
full list.

## Working on the page

Run the server with a development origin, then the Vite server, as the
launch configurations do (section 5 of [CONTRACT.md](CONTRACT.md)):

```sh
python -m caterva.app studio --port 18740 --no-browser --dev-origin http://127.0.0.1:18741
cd Science-Agent-Pipeline/artifacts/caterva-studio
STUDIO_API=http://127.0.0.1:18740 PORT=18741 node node_modules/vite/bin/vite.js --config vite.config.ts
```
