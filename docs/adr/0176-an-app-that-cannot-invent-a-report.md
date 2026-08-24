# ADR 0176: An app that cannot invent a report

**Status:** Accepted

**Date:** 2026-08-23

## Context

The first release of Terrium: a macOS app, downloadable as a DMG, that a
teaching lab can open without installing Python, Node, or anything else.
Deliberately the smallest thing worth shipping — one worked example, not the
whole engine.

The design constraint came from the repository rather than from the request.
`scripts/demo.py` says:

> A demo with its own rendering path is the worst kind of check that cannot
> fail: it keeps looking impressive while the product it advertises rots, and
> the discrepancy surfaces in front of the first person who tries the real
> command.

**A shipped app is a demo that ships**, with a longer life and a wider
audience. So the app must not be able to produce a document of its own.

## Decision

`Terrium.app` = a native AppKit + WKWebView shell (Swift) that runs a frozen
`scripts/report_lab.py` — *the same builder the CLI calls* — and displays the
bytes it returns.

- The app does not simulate, fetch, or write a report. Every failure surfaces
  as a failure; none becomes an empty document.
- `viewer.html` typesets the markdown and **reports any line it cannot
  typeset** rather than dropping it. In a document whose purpose is
  disclosure, a silently omitted line is the worst available failure, and the
  kind that looks perfect on screen.
- The BRENDA page is a committed fixture inside the bundle. The app makes no
  network requests, and the report says so itself.

The build refuses to ship what it has not verified: the app's own headless
`--selftest`, the viewer tested against *that build's* report, and a fatal
signature check.

## Verification

```
4/6  Smoke test: can the APP drive the bundled builder?
SELFTEST OK: the app ran the bundled builder and got a 2662-character
             report with its provenance sections.
  ok    every line of the real report is typeset
  ok    all 13 table rows reach the output
  ok    an unsupported construct is reported rather than dropped
  ... 11 checks, viewer OK
5/6  Signing — signature verifies
6/6  Terrium.dmg (84M)
```

The DMG mounts, and the app launches from it and stays running.

### Four things were wrong, and measurement found each

**The dependency set, three times.** Tracing `scripts/demo.py` showed *no*
third-party imports — because it runs the builder as a **subprocess**, so the
trace saw only the parent. Excluding numpy failed:
`Terium/core/data_structures.py` needs it. Excluding antimony failed:
`Terium/__init__.py` imports `terium_engine` → `model_building` → `antimony`
at module level, so `import Terium` at all pulls in the whole engine. Only
building and *running* the frozen binary settled it.

**"No space left on device" on a disk with 111 GB free.** `hdiutil`
underestimated the volume it was creating. An explicit `-size` fixes it. The
message is true of the volume and false of everything a reader would check.

**Signing refused: "resource fork, Finder information, or similar detritus
not allowed."** This repository lives under `~/Desktop`, which macOS syncs to
iCloud Drive; the file provider re-applies `com.apple.FinderInfo` within
moments, so `xattr -cr` immediately before `codesign` loses the race. The app
is now assembled and signed outside the synced tree and only the finished
image is copied back.

**And the check that could not fail, in the file whose header warns about
them.** `viewer.html`'s `unhandled` list was unreachable: the paragraph branch
absorbed every unrecognised line, so a blockquote rendered as prose and the
"lines this viewer cannot typeset" banner could never appear. `test_viewer.mjs`
asserts the negative case — feed it a blockquote, demand it be reported — and
that assertion failed on the first run. Unsupported constructs are now matched
explicitly.

A fifth: the build script printed the signing failure and **carried on to
build a DMG from an unsigned app**, shipping precisely what its own header
promised not to. A failed signature is now fatal.

## Consequences

`make dmg` produces a signed, verified, 84 MB disk image containing an app
that runs on a Mac with nothing installed.

**What this does not check.**

- **Nobody has looked at the window.** Screen recording is unavailable in this
  environment, so the app was verified by its headless selftest and by testing
  the viewer against real output — not by seeing it. The layout, the fonts,
  the dark-mode palette: unverified by eye. **Someone should look before this
  reaches a student.**
- **Not notarised, and cannot be here.** The only certificate on this machine
  is an *Apple Development* identity, which signs for local use. A downloaded
  copy will be reported as damaged until it is signed with a *Developer ID
  Application* certificate and notarised. `READ ME FIRST.txt` tells the user
  the right-click → Open workaround; that is a mitigation, not a fix.
- **Apple silicon only.** Built and tested on arm64. No universal binary, and
  Intel is untested.
- **One example, fixed.** No inputs. Twelve of the thirteen domains are
  reachable only from the CLI, and the app's own notes say so.
- **83 MB of it is the frozen runtime**, most of that binary extensions the
  used code path never calls but `import Terium` drags in. Trimming that means
  breaking the engine's import graph, which is a real change and not attempted
  here.
- **The icon is a crop of `Logo.png`, not artwork made for an icon.** Built
  from a single continuous square of the existing logo, corners rounded, at
  80% inset. Two earlier attempts composited the mark onto a tile and both
  failed visibly -- a flat colour left a ghost rectangle, and feathering the
  join turned it into a glow -- because the logo's paper carries a vignette
  and the cube's pale glass faces sit at the same luminance as it, so
  brightness keying cannot separate them. Taking one uncut piece removes the
  seam by removing the join. Nobody has looked at it at 16px, where the thin
  linework probably disappears.
- **The version number is chosen, not derived.** `0.1.0` marks a first
  release; nothing computes it and nothing checks it against the tree.
