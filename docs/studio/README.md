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
| Constants | `scripts/cite.py` | Every BRENDA row the resolver read for a constant, with its reference, organism, conditions and the row's own words |
| Stochastic | `caterva sim ssa` | One exact trajectory beside the ODE expectation, with its seed |
| Binding | `caterva bind` | Each cited Ki turned into a ΔG°bind band, with the method and each row's temperature |
| Structures | `caterva structure` | PDB entries for an EC number or enzyme name, grouped by protein, and the chosen entry in 3D |
| Prepare | `caterva prepare` | What is wrong with an entry before it is simulated, ranked by distance to the active site |
| Dynamics | `caterva md`, `caterva md --summarise`, `caterva fep --summarise`, `caterva complex --check` | A GROMACS setup whose every parameter says where it came from; convergence of finished replicas |
| Analyze | `caterva analyze` | Catalytic geometry and flexibility per replica, each verdict beside its threshold |
| History | | Every run: search, reopen, export as a zip, delete to the workspace's trash folder with an undo |
| Settings | | Theme, runs at once, offline mode, the GROMACS program, the workspace folder |
| About | | How a number's kind is decided, the data sources and their licences, how to cite them |

`/rates` is reserved for `caterva rates`. It appears only when
`/api/capabilities` reports the rates kind as available; until then the
address says the screen is not in this installation, and why.

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
say how to open it (Control-click, Open; or System Settings, Privacy &
Security, Open Anyway), and the build script refuses either text if a
sentence in it claims a signature or notarisation.

## What is not done yet

- No signed or notarised build. macOS asks before the first open of each
  downloaded version.
- The DMG is built for Apple silicon (arm64) only. The page and the server
  run on Linux and Windows through `caterva studio` in a browser; there is
  no native window there.
- `caterva rates` is not in this branch; its screen is reserved and hidden.
- The 3D viewer draws a C-alpha trace with highlighted side chains on a 2D
  canvas. It does not draw cartoons or surfaces, and it does not label
  residues on the canvas itself (the list and the side panel name them).
- A deleted run can be undone only while its note is on screen; after
  that it is restored by moving its folder back from `trash/` by hand.
- The page's largest chunks (charts, the shell) are over 500 kB before
  compression; they load from disk, but nothing splits them further yet.
