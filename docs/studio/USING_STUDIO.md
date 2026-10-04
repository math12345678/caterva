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
| `--print-url` | Once listening, print one line `CATERVA_STUDIO_URL=<url>#token=<token>` to stdout. Open the whole address, including the part after the `#`. Nothing else is ever printed to stdout. The macOS app reads this line. |
| `--self-test` | Start on a free port in a temporary data folder (or `--data-dir`), request `/api/health` and `/` over a real socket, print one line per check, stop. Exit 0 when every check passed, 1 otherwise. |

Exit codes: 0 stopped cleanly (or the self-test passed), 1 a crash or a
failed self-test, 2 a malformed command line, 3 refused and said why.

The server stops cleanly on Ctrl-C, on SIGTERM, when the process that
started it exits, and when its stdin is a pipe and that pipe closes (how
the macOS app tells it to stop). Runs still going are marked interrupted;
they are never resumed later.

## Fitting your own rates

Open Rates (the second thing Home offers, "Start from your own
measurements", or Cmd-K and "Fit my data"). One screen, three parts you read
from the top.

1. **Your measurements.** Drop a CSV, TSV or text file on the page, choose
   one with the button, or paste the cells from your spreadsheet with Ctrl or
   Cmd V anywhere on the screen. "Open an example" loads R's real
   `datasets::Puromycin`. The browser reads the file as text and sends the
   text to the server on your computer; no path leaves the page. A table is
   limited to 524,288 bytes and 2,000 rows. The screen then says how it was
   read: the delimiter, the header, the decimal mark (a decimal comma is
   read), a byte-order mark and Windows line endings, which column is the
   substrate, the rate, a sigma, an inhibitor, a group, and each column's
   unit (read from a header such as `[S] (mM)` or `v0 (µM/min)`). Every
   decision is a sentence; every cell that could not be used is listed by line
   and column and its row is skipped, never repaired; a unit is never
   assumed (name it in the box, or in the header). Change a column's role in
   the heading's menu, change the unit or convert it (the screen writes the
   multiplier), or change the delimiter, decimal mark or header row.
   Layouts read: one row per measurement (substrate, rate, and optionally
   sigma, inhibitor, group), one substrate column with several replicate rate
   columns, and two pasted columns.
2. **What to fit.** By default every rate law that applies is fitted and
   tested (three without an inhibitor, four with one); any of the seven can be
   forced. The uncertainty of each rate comes from your sigma column, from
   the scatter of replicates, or from the scatter about the fitted curve; the
   screen says what each assumes in a sentence, offers only those the table
   has, and never invents one. Optional: an enzyme concentration (for kcat =
   Vmax / [E]) and a comparison with BRENDA through the enzyme finder when the
   literature layer and the network are available.
3. **Result.** Anything to read before you quote a number comes first: a
   constant the data cannot bound is shown without a value, with what to
   change; then what the data support, the figure (rates with error bars,
   the fitted curve with its band, the residuals beneath), the constants
   each marked as fitted from your data with a profile-likelihood interval,
   the lack-of-fit test, the laws compared with AICc, the comparison between
   groups and the literature, and the files to take away: the figure as SVG
   and as PNG at 300 dpi for a single or double column (white background
   optional), the parameter and model tables as CSV, the methods paragraph
   and a citation line, and the run's bundle (the table, the request, the
   result, the versions and the command).

The run is saved to History and reopens with its table, mapping and choices.
The same fit in a terminal is `caterva rates dataset.csv ...` in the bundle's
folder.

What is weak, plainly: it has been run on R's Puromycin data and formats of
its values, not on a laboratory's own tables; the literature comparison with
found BRENDA rows has not been exercised on real molar-unit rates here (the
declined path has); the figure's band is the engine's first-order, pointwise
band, not a band for the whole curve at once; a table with groups and an
inhibitor in wide layout is not read (use one row per measurement); and a
cancel stops the fit between laws, not inside one.

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
request. The token is in no page the server serves: it reaches the page in the
fragment of the address the app or `--print-url` gives (`#token=...`), which a
browser never sends to a server, and it is never put on disk. Section 3 of [CONTRACT.md](CONTRACT.md) has the
full list.

## Working on the page

Run the server with a development origin, then the Vite server, as the
launch configurations do (section 5 of [CONTRACT.md](CONTRACT.md)):

```sh
python -m caterva.app studio --port 18740 --no-browser --dev-origin http://127.0.0.1:18741
cd Science-Agent-Pipeline/artifacts/caterva-studio
STUDIO_API=http://127.0.0.1:18740 PORT=18741 node node_modules/vite/bin/vite.js --config vite.config.ts
```
