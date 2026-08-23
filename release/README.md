# Terrium 0.1.0 — the first release

A macOS app that produces one lab report, offline, with every number marked
either *literature* (with the reference it came from) or *yours* (a condition
you chose, which no database reports).

    ./release/build_dmg.sh            # → release/build/Terrium.dmg

## What is in the DMG

| | |
|---|---|
| `Terrium.app` | the app. 83 MB, self-contained. |
| `READ ME FIRST.txt` | the first-run instructions, including why macOS will refuse a plain double-click. |
| `Applications` | a symlink, so the app can be dragged across. |

Inside the app:

| | |
|---|---|
| `MacOS/Terrium` | a native AppKit + WKWebView shell (Swift, ~250 lines). |
| `Resources/terrium-report` | `scripts/report_lab.py`, frozen with PyInstaller. **The same builder the CLI calls.** |
| `Resources/brenda_ldh_fixture.html` | the committed BRENDA page the Km is resolved from. |
| `Resources/viewer.html` | the typesetter. |

No Python, no Node, and no internet is needed on the machine that runs it.

## What it does, and what it does not

It runs one worked example: Michaelis-Menten kinetics of lactate
dehydrogenase acting on pyruvate. Km comes from BRENDA; s0 and Vmax are
marked **yours**, because you chose them and no database reports them.

It is **not** a general simulator yet. You cannot enter your own enzyme, and
the other twelve domains the engine supports are reachable only from the
command line. That is what "first release, most basic version" means here,
and the app's own first-run notes say so rather than leaving it to be
discovered.

## The rule this app is built around

`scripts/demo.py` states it:

> A demo with its own rendering path is the worst kind of check that cannot
> fail: it keeps looking impressive while the product it advertises rots, and
> the discrepancy surfaces in front of the first person who tries the real
> command.

A shipped app is a demo that ships. So the app does not simulate, does not
fetch, and does not write a report. It runs the real builder and displays the
bytes that come back. If the builder starts failing, the window says so
instead of showing something stale.

`viewer.html` typesets that markdown and **reports any line it cannot
typeset** rather than dropping it. In a document whose whole purpose is
disclosure, a silently omitted line is the worst available failure — and it
is the kind that looks perfect on screen.

## What the build refuses to do

`build_dmg.sh` will not produce a DMG it has not verified:

1. **The app's own `--selftest`** runs the shipped executable headlessly: it
   locates the bundled builder, sends the payload, parses the reply, and
   checks the report still contains its `## Parameters` and
   `## What Terrium would not do` sections and a BRENDA reference.
2. **`test_viewer.mjs`** typesets *the report this build just produced* —
   never a stored sample — and fails if any line is unhandled, if a table row
   is lost, or if markup is not escaped.
3. **A failed signature is fatal.** An earlier version printed the failure and
   carried on to build a DMG from an unsigned app.

If `node` is missing, the viewer test is skipped and says so out loud. A
skipped check that prints nothing is indistinguishable from one that passed.

## Signing: read this before sending the DMG to anyone

The build is **ad-hoc signed** by default. That is enough to run on the
machine that built it and **not enough for anybody who downloads it** — macOS
quarantines it and reports "Terrium is damaged and can't be opened". The app
is not damaged; it is unsigned for distribution.

The certificate on this machine is an **Apple Development** identity, which
signs for local development only. Distribution needs a **Developer ID
Application** certificate plus notarisation:

    ./release/build_dmg.sh --sign "Developer ID Application: YOUR NAME (TEAMID)"
    xcrun notarytool submit release/build/Terrium.dmg \
        --apple-id you@example.com --team-id TEAMID --wait
    xcrun stapler staple release/build/Terrium.dmg

That is an Apple account matter, not a code change. Until it is done,
`READ ME FIRST.txt` tells the user to right-click → Open, which is macOS's
own way through.

## Why the app is 83 MB

Almost all of it is the frozen Python runtime and the engine's binary
dependencies. The dependency set was established by building and **running**
the binary, not by reading imports, and three readings were wrong first:

- Tracing `scripts/demo.py` showed no third-party imports at all. It runs the
  builder as a **subprocess**, so the trace saw only the parent.
- Excluding numpy failed: `Terium/core/data_structures.py` imports it.
- Excluding antimony failed: `Terium/__init__.py` imports `terium_engine`,
  which imports `model_building`, which imports antimony at module level — so
  `import Terium` at all pulls in the whole engine.

`antimony`, `roadrunner` and `libsbml` are binary extensions with data files
beside them, which is why they need `--collect-all` rather than a hidden
import. Trimming this is real work and is not attempted here.

## Known limits of this release

- **One example, fixed.** No input fields; the payload is the same one
  `scripts/demo.py` sends.
- **Apple silicon only.** Built on arm64 and not tested on Intel. No universal
  binary is produced.
- **Not notarised**, as above.
- **No app icon.** The generic application icon is used.
- **The window has not been seen by a human in this build environment.**
  Screen recording is unavailable here, so the app was verified by running its
  headless selftest and by testing the viewer against real output — not by
  looking at it. Someone should look at it before this goes to a student.
