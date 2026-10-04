# Caterva Studio

Caterva Studio is a desktop window onto the same engine the `caterva`
commands run. A small server on your own computer (`caterva studio`) calls
the library functions the CLI calls, keeps every run in a local workspace,
and serves a page that shows each result with the kind of every number on
it: a cited measurement, a fit, a computation, a value you chose, or a
placeholder with the reason it is one. On macOS the page opens in a native
window (Caterva.app); anywhere else it opens in your browser.

Nothing in the studio computes a number of its own. Each screen's adapter
(`caterva/studio/adapters/`) calls the CLI's library function and
serialises what it returns, and a parity test per adapter
(`caterva/tests/test_studio_*.py`) holds the API's numbers equal to the
CLI's for real inputs.

| document | what it covers |
|---|---|
| [USING_STUDIO.md](USING_STUDIO.md) | Starting the server, its flags, where runs are kept, settings, working on the page |
| [CONTRACT.md](CONTRACT.md) | The rules the server and the page follow: security, endpoints, runs and events, provenance, the desktop shell, ownership |
| [../USING_CATERVA.md](../USING_CATERVA.md) | The commands each screen runs, and how to read their results |

## The screens

| screen | runs | what it shows |
|---|---|---|
| Home | `caterva compose "<line>"` | One written line starts a model; recent runs; what this machine can reach |
| Compose | `caterva compose` | The verdict and the worst thing wrong with the model first, then where every constant came from, the time course, influence, steady states, sweeps and each requested analysis |
| Constants | `scripts/cite.py` (a copy of it rides in the wheel and the app, in `caterva/_literature/`) | Every BRENDA row the resolver read for a constant, with its reference, organism, conditions and the row's own words |
| Stochastic | `caterva sim ssa` | One exact trajectory beside the ODE expectation, with its seed |
| Rates | `caterva rates` | Your own initial rates fitted: the figure, the constants with profile intervals, which rate law the data support, and a methods paragraph |
| Binding | `caterva bind` | Each cited Ki turned into a ΔG°bind band, with the method and each row's temperature |
| Structures | `caterva structure` | PDB entries for an EC number or enzyme name, grouped by protein, and the chosen entry in 3D |
| Prepare | `caterva prepare` | What is wrong with an entry before it is simulated, ranked by distance to the active site |
| Dynamics | `caterva md`, `caterva md --summarise`, `caterva fep --summarise`, `caterva complex --check` | A GROMACS setup whose every parameter says where it came from; convergence of finished replicas |
| Analyze | `caterva analyze` | Catalytic geometry and flexibility per replica, each verdict beside its threshold |
| History | | Every run: search, reopen, export as a zip, delete to the workspace's trash folder with an undo |
| Settings | | Theme, runs at once, offline mode, the GROMACS program, the workspace folder |
| About | | How a number's kind is decided, the data sources and their licences, how to cite them |

**Rates starts from your own measurements.** Drop a CSV, TSV or text file on
the Rates screen (or choose one, or paste the cells from a spreadsheet), check
how it was read, choose what to fit, and get a figure, a table of constants
with profile intervals, the lack-of-fit test, the rate laws compared and a
methods paragraph, as files you can put in a lab report. The guide is
[USING_STUDIO.md](USING_STUDIO.md), "Fitting your own rates".

## Run it from a checkout

From the repository root, with the project's Python environment, build the
page once and start the server:

```sh
cd Science-Agent-Pipeline
pnpm install --frozen-lockfile --filter @workspace/caterva-studio...
pnpm --filter @workspace/caterva-studio run build      # writes caterva/studio/static/
cd ..
python -m caterva.app studio                            # opens your browser
```

The page build is not committed. Without it the server answers with a short
page saying how to build it. `python -m caterva.app studio --self-test`
starts the server on a free port, requests `/api/health` and `/` over a real
socket and exits 0 or 1. [USING_STUDIO.md](USING_STUDIO.md) has every flag,
the workspace layout and how to work on the page with Vite.

The checks for the studio, as CI runs them (`make test-studio` runs the
same):

```sh
cd Science-Agent-Pipeline/artifacts/caterva-studio
pnpm run typecheck && pnpm run test && pnpm run build
cd ../../..
python -m pytest -p no:cacheprovider -o addopts="" caterva/tests/test_studio_*.py
```

`test_studio_socket.py` binds real loopback ports. Where binding is refused
(some sandboxes), those tests fail at setup and say so; they are not
skipped.

## How the macOS app and the DMG are built

`scripts/build_studio_app.py` assembles Caterva.app: the Swift shell in
`macos/Sources` (AppKit and WKWebView, compiled with `swiftc` from the
Command Line Tools, no Xcode project), the icon drawn by
`macos/Icon/MakeIcon.swift`, `macos/Info.plist`, the first-run text, and the
frozen `caterva` folder. The shell starts
`caterva studio --port 0 --no-browser --print-url`, reads the
`CATERVA_STUDIO_URL=` line, and shows the page in a window. File inputs open
the native open panel, exports open the save panel, a server that stops
shows a native error view naming its log and offering Restart, and quitting stops the server.

A release build, in order (`.github/workflows/studio-dmg.yml` runs exactly
this on a macOS arm64 runner, by hand or from `release.yml`):

1. the page: `pnpm --filter @workspace/caterva-studio run build`;
2. the wheel, carrying the page: `scripts/build_release.py`;
3. the frozen folder, in a venv holding that wheel and PyInstaller:
   `scripts/build_app.py --require-studio-page --keep-folder DIR`, which
   refuses a folder whose `caterva studio --self-test` fails;
4. the app and the image:
   `scripts/build_studio_app.py --frozen DIR/caterva --dmg`, which compiles
   the shell, seals the bundle with an ad-hoc signature, runs
   `Caterva --smoke --require-page` against it, makes the DMG with `hdiutil`,
   verifies it and writes its SHA-256.

A development app needs no frozen folder. It runs a checkout's Python
instead:

```sh
python3 scripts/build_studio_app.py --dev --python .venv/bin/python --checkout . --out /tmp/studio-dev
/tmp/studio-dev/Caterva.app/Contents/MacOS/Caterva --smoke --require-page
open /tmp/studio-dev/Caterva.app
```

A development app is never put in a DMG.

The app is not signed with an Apple Developer ID and is not notarised: the
project holds no Developer ID. The DMG's README and the app's first-run text
say how to open it (System Settings, Privacy & Security, Open Anyway; then
`xattr -dr com.apple.quarantine /Applications/Caterva.app` if macOS keeps
refusing), and the build script refuses either text if a sentence in it
claims a signature or notarisation. Control-click, Open is not offered: the
route is not in Apple's current instructions for opening an app from an
unknown developer (support.apple.com, "Open a Mac app from an unknown
developer", read 2026-10-03, lists only Open Anyway), and on recent macOS
releases it does not work for this kind of app. What was verified is that
page's text; what was not is the behaviour on each macOS release, which
needs a Mac of each kind.

The app needs **macOS 14 or later** on Apple silicon: the wheels the app
carries (NumPy 2.2.6, SciPy 1.15.3, libRoadRunner 2.8.0) are built for macOS
14. `LSMinimumSystemVersion` says 14.0, and the shell itself checks
`ProcessInfo` and shows a plain alert on an older macOS instead of starting a
server that cannot import them.

## Looking at the page while developing

The session token is in the URL fragment of the address the server prints,
never in a page it serves, so a browser opened at the bare address
(`http://127.0.0.1:PORT`, which is all a preview pane opens) has no token and
says so. Two routes work:

- **The development origin.** Start the server with
  `--dev-origin http://127.0.0.1:18711` and the Vite dev server
  (`pnpm run dev` in `artifacts/caterva-studio`, `STUDIO_API` set to the
  server's address, port 18711). Vite fetches `/api/dev/session` itself and
  the page gets the token without a fragment (docs/studio/CONTRACT.md,
  section 5). This shows the source, not the built page.
- **The built page, with the fragment.** Build it
  (`pnpm run build`), start the server with `--dev-origin` as above, open
  `http://127.0.0.1:PORT/api/dev/session` as a top-level navigation (it
  refuses any request that carries an `Origin`, so `fetch` from another page
  is refused), copy the `token` it answers, and open
  `http://127.0.0.1:PORT/#token=THAT_TOKEN`. The page reads the fragment,
  removes it from the address and keeps the token for the tab. Without
  `--dev-origin`, use `caterva studio --no-browser --print-url` and open the
  address it prints.

## Things to know when running more than one server

- **Settings are last-writer-wins.** Each server reads `settings.json` from
  the data folder when it starts and writes the whole file, atomically, each
  time a setting changes. Two servers on one data folder (two `caterva
  studio` commands, or the app beside a terminal) each hold their own copy:
  the one that saved last decides what the next server reads, and a change
  made in one is not seen by the other until it restarts. Give a second
  server its own `--data-dir` to keep them apart. Runs do not have this
  problem: each run is its own folder, claimed by the server that started it.
- **A server started in the background stops with its parent.** The server
  watches the process that launched it and, about one second after that
  process has gone (`PARENT_POLL_S`), shuts itself down. So
  `caterva studio --no-browser &` in a shell that then exits (a script, an
  `ssh` command, a CI step) stops about a second later. Keep the launching
  shell open, or run it in a terminal multiplexer (`tmux`, `screen`),
  whose shell stays alive. `nohup` and `setsid` do not help: the check is
  whether the parent process id changed, and it changes to 1 when the
  parent dies however the server was detached; there is no flag to turn the
  check off. When stdin is a pipe (as it is when Caterva.app starts the
  server) closing that pipe stops the server too.

## What is not done yet

- No signed or notarised build. macOS asks before the first open of each
  downloaded version.
- The DMG is built for Apple silicon (arm64) only. The page and the server
  run on Linux and Windows through `caterva studio` in a browser; there is
  no native window there.
- The Rates screen has not been tried on a real laboratory's tables beyond
  R's Puromycin data and formats of its values: see "What is weak" in
  USING_STUDIO.md.
- The 3D viewer draws a C-alpha trace with highlighted side chains on a 2D
  canvas. It does not draw cartoons or surfaces, and it does not label
  residues on the canvas itself (the list and the side panel name them).
- A deleted run can be undone only while its note is on screen; after
  that it is restored by moving its folder back from `trash/` by hand.
- The page's largest chunks (charts, the shell) are over 500 kB before
  compression; they load from disk, but nothing splits them further yet.
