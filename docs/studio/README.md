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
   `scripts/build_studio_app.py --frozen DIR/caterva --dmg --zip`, which
   fetches the pinned Sparkle, compiles the shell against it, embeds it, seals
   the bundle with an ad-hoc signature, runs `Caterva --updater-selftest` and
   `Caterva --smoke --require-page` against it, makes the update archive with
   `ditto` and the DMG with `hdiutil`, verifies both and writes their
   SHA-256s.

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

## Updates inside Caterva.app

From 0.5.1 the app updates itself with [Sparkle 2](https://sparkle-project.org).
**The first copy that has the updater (0.5.1) must be installed by hand**, from
the DMG, with the Open Anyway step the DMG's README describes. After that,
new versions are offered inside the app. A copy older than 0.5.1 has no
updater and is replaced by hand.

**What a person sees.** Caterva menu, Check for Updates...; Settings, Updates
(the installed version and build, when the app last checked, Check now, Check
automatically, Include prereleases). The app checks about once a day unless
that is turned off, and always asks before it installs. Installing closes the
app; the shell stops the server first (stdin closed, SIGTERM, 5 s, SIGKILL:
the same path as Quit), so no old server is left holding the data folder. If
the page reports runs in progress (bridge message `reportActiveRuns`), the
shell asks whether to wait for them or stop them and relaunch. Runs and
settings are in `~/Library/Application Support/Caterva`, not in the app; an
update replaces only the app. In a plain browser the Updates section says that
the app owns updates and shows nothing to press. A development app
(`--dev`) never updates and says so.

**Where the feed is.** Nothing but GitHub Releases, no server and no GitHub
Pages. Each release carries its own `appcast.xml` with one item (the release).

| who | feed |
|---|---|
| everyone (Info.plist `SUFeedURL`) | `https://github.com/math12345678/caterva/releases/latest/download/appcast.xml`, which GitHub redirects to the newest release that is not a prerelease |
| Include prereleases on | the `appcast.xml` of the newest release of any kind, its address read from `GET https://api.github.com/repos/math12345678/caterva/releases` (unauthenticated, so the answer is kept for an hour; a failure keeps the last good address and says so in Settings, and with none the app checks stable releases only) |

The address the API names is followed only if it is `https://github.com/math12345678/caterva/releases/download/<tag>/appcast.xml`
(`ReleaseFeed.isAcceptable`, exercised by `Caterva --updater-selftest`).
Versions are compared by `CFBundleVersion`, the build number (the commit
count at the tag), so `0.5.1-rc.1` and `0.5.1` are ordered by when they were
built.

**The update archive.** `Caterva-<version>-macos-arm64.zip`, the same
Caterva.app as the DMG, made with `ditto -c -k --keepParent` (it keeps the
symbolic links inside Sparkle.framework and the frozen folder, which `zip`
would not). `scripts/build_studio_app.py --zip` unpacks it again and runs
`codesign --verify --deep --strict` on the result. It is in `SHA256SUMS`
with the DMG and `appcast.xml`. The update-feed job in `release.yml` signs it
(below) and `scripts/make_appcast.py` writes `appcast.xml`: version and build
read from the archive, minimum system version 14.0, arm64, publication date,
length, signature, the first paragraph of `docs/releases/<tag>.md` and a link
to the release page. A candidate (`v0.5.1-rc.1`) uses the plain tag's notes.

**What is checked, and what that is not.** Sparkle verifies the archive's
EdDSA signature against `SUPublicEDKey` in the installed app's Info.plist
(`SUVerifyUpdateBeforeExtraction` is on, so before it is unpacked) and
refuses a downgrade. That protects against a tampered or substituted
archive. It is not an Apple signature: Caterva is not signed with an Apple
Developer ID and is not notarised, and nothing in the app says otherwise.
The feed itself is served over HTTPS by GitHub and is not separately signed;
a tampered feed can offer an update but cannot make the app install one that
the key did not sign.

**Sparkle in the build.** Not vendored: `scripts/fetch_sparkle.py` downloads
Sparkle 2.10.0 (`Sparkle-2.10.0.tar.xz`, SHA-256
`c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c`, the
digest GitHub shows for the asset) and refuses anything else. Sparkle is MIT;
its LICENSE also carries bsdiff, sais-lite, an Ed25519 implementation and
SUSignatureVerifier (NOTICE, item 2a, lists the set and
`scripts/check_release_artifacts.py` fails if the notice is missing). The
build compiles the shell with `-F` and `-framework Sparkle`, links with the
run-time search path `@executable_path/../Frameworks`, copies the framework
into `Contents/Frameworks` without its XPC services (for a sandboxed app
only; Caterva is not sandboxed), copies Sparkle's LICENSE into
`Contents/Resources/licenses/`, and seals Autoupdate, Updater.app, the
framework and then the app, all ad-hoc.

**The update key.** An Ed25519 key pair. The public half is in
`macos/Info.plist` (`SUPublicEDKey`). The private half is the repository
secret `SPARKLE_ED_PRIVATE_KEY`, used by one step of one job (`update-feed`
in `release.yml`), read from the environment into `sign_update --ed-key-file -`
(standard input, never a command-line argument), and never in a workflow that
runs for a pull request. The release stops, and nothing is published, if the
secret is empty or if it does not match the public key inside the app
(`macos/Updater/VerifyUpdateSignature.swift` checks the signature against the
key in the archive's own Info.plist). `scripts/check_release_artifacts.py`
holds those rules.

Setting the key up, once, on your Mac (the secret is read from standard input,
so it is not in `ps` or your shell history):

```sh
gh secret set SPARKLE_ED_PRIVATE_KEY --repo math12345678/caterva < /path/to/the-private-key-file
python3 scripts/fetch_sparkle.py --out dist/sparkle
# keep a copy in the login keychain (Sparkle's own import; no key on a command line)
dist/sparkle/Sparkle-2.10.0/bin/generate_keys --account caterva-updates -f /path/to/the-private-key-file
dist/sparkle/Sparkle-2.10.0/bin/generate_keys --account caterva-updates -p    # must print the key in macos/Info.plist
rm /path/to/the-private-key-file
```

If you lose the key, no installed app can verify an update signed by a new
one: make a new pair (`generate_keys --account caterva-updates`), put its
public half in `macos/Info.plist`, set the secret to the new private half, and
ship one more DMG by hand. Never commit or paste the private half.

**Testing an update by hand** (not run by the project's authors in the
sandbox that wrote this; it needs a Mac, a frozen folder and a loopback port).
Use a test key, never the real one:

```sh
python3 scripts/fetch_sparkle.py --out dist/sparkle
S=dist/sparkle/Sparkle-2.10.0
$S/bin/generate_keys --account caterva-test          # prints the TEST public key; the key goes to the keychain
# the frozen folder: steps 1 to 3 above, once
mkdir -p /tmp/upd/old /tmp/upd/serve
python3 scripts/build_studio_app.py --frozen dist/frozen/caterva --out /tmp/upd/old --build-number 1 \
    --update-feed http://127.0.0.1:8000/appcast.xml --update-public-key TESTKEY
python3 scripts/build_studio_app.py --frozen dist/frozen/caterva --out /tmp/upd/new --build-number 2 --zip \
    --update-feed http://127.0.0.1:8000/appcast.xml --update-public-key TESTKEY
cp /tmp/upd/new/Caterva-*-macos-arm64.zip /tmp/upd/serve/
sig="$($S/bin/sign_update --account caterva-test -p /tmp/upd/serve/Caterva-*-macos-arm64.zip)"
python3 scripts/make_appcast.py --zip /tmp/upd/serve/Caterva-*-macos-arm64.zip --signature "$sig" \
    --tag v$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' caterva/__init__.py) --notes docs/releases/v0.5.1.md \
    --download-prefix http://127.0.0.1:8000/ --out /tmp/upd/serve/appcast.xml
(cd /tmp/upd/serve && python3 -m http.server 8000 --bind 127.0.0.1)    # leave running
```

Then, in another terminal: copy `/tmp/upd/old/Caterva.app` to
`/Applications`, clear its download mark if it has one, open it, and choose
Caterva, Check for Updates. Check, in order: Sparkle offers build 2 and shows
the notes; Install and Relaunch quits the old app; `pgrep -f "caterva studio"`
shows no old server afterwards; the new app opens with no macOS prompt (this is
the one thing that cannot be settled from Sparkle's source alone, see below);
`Caterva --version` and Settings, Updates show build 2; History still lists
the runs from before. Repeat with a run in progress: the app should ask
whether to wait. Delete `/Applications/Caterva.app`, `/tmp/upd` and the test
keychain item afterwards.

**What was and was not verified** (2026-10-04, a sandboxed Mac with no GUI, no
loopback port and no keychain write):

- Verified by running it: the shell compiles against Sparkle 2.10.0 with
  `swiftc` and links with the rpath; the assembled app passes
  `codesign --verify --deep --strict` with every piece ad-hoc sealed; the
  feed rules pass `Caterva --updater-selftest`; the archive made by `ditto`
  unpacks and `scripts/make_appcast.py` writes an appcast that
  `--check` accepts; a signature made with `sign_update --ed-key-file` and the
  key pair verifies (CryptoKit, `VerifyUpdateSignature.swift`) against the
  public key in the built app's Info.plist.
- Read in Sparkle's source (tag 2.10.0), not run: its installer removes the
  `com.apple.quarantine` mark from the new app before it replaces the old
  one (`SUPlainInstaller`, `releaseItemFromQuarantineAtRootURL`), and its
  download is made by the app itself, not by a browser; its update validator
  accepts a bundle whose EdDSA key matches the old one, and refuses an update
  that drops code signing when the old app has it (an ad-hoc seal counts).
  From that, an update installed by Sparkle should open with no Gatekeeper
  prompt. **That was not observed.**
- Not done: a real update from an older build to a newer one; the relaunch;
  the server stopping during it; the "runs in progress" question; Gatekeeper's
  behaviour on the first launch after an update; the GitHub Releases API
  fallback. The release candidate's first run on `macos-14` is the first time
  the update-feed job runs.

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
