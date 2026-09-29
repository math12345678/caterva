#!/usr/bin/env bash
#
# Build Terrium.app and Terrium.dmg.
#
#   ./release/build_dmg.sh [--sign "Developer ID Application: ..."]
#
# Everything the app needs is placed inside the bundle: the frozen report
# builder, the committed BRENDA fixture, and the viewer. The app makes no
# network requests, so a machine with no Python, no Node and no internet runs
# it.
#
# WHAT THIS SCRIPT REFUSES TO DO
# ------------------------------
# It will not produce a DMG whose app it has not just launched successfully.
# A release that ships an app nobody started is the shape this repository
# keeps finding: something that looks delivered and is not. The smoke test
# below runs the frozen builder for real and checks the document came back.
#
# SIGNING
# -------
# Without --sign the app is ad-hoc signed, which is enough to run on the
# machine that built it and NOT enough for anyone who downloads it: macOS
# quarantines it and reports the app as damaged. Distribution needs a
# "Developer ID Application" certificate and notarisation. See README.md in
# this directory -- the limitation is stated there rather than discovered by
# the first person who double-clicks.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
# Build somewhere the OS is not syncing.
#
# This repository lives under ~/Desktop, which macOS syncs to iCloud Drive.
# The file provider re-applies com.apple.FinderInfo and
# com.apple.fileprovider.fpfs#P to the bundle within moments of it being
# written, and codesign refuses a bundle carrying either: "resource fork,
# Finder information, or similar detritus not allowed". Clearing them with
# `xattr -cr` immediately before signing is not enough, because they come
# back between the two commands.
#
# So the app is assembled and signed outside the synced tree, and only the
# finished disk image is copied back. A DMG's contents are sealed inside the
# image, so attributes later applied to the .dmg file itself are harmless.
WORKROOT="${TMPDIR:-/tmp}/terrium-release-build"
BUILD="$WORKROOT"
OUTDIR="$HERE/build"
APP="$BUILD/Terrium.app"
DMG_ROOT="$BUILD/dmg"
DMG="$BUILD/Terrium.dmg"
mkdir -p "$WORKROOT" "$OUTDIR"

SIGN_IDENTITY="-"   # ad-hoc
while [ $# -gt 0 ]; do
  case "$1" in
    --sign) SIGN_IDENTITY="${2:?--sign needs an identity}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

VERSION="$(cat "$HERE/VERSION")"
COMMIT="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 1. builder
# The dependency set below was established by building and RUNNING the binary,
# not by reading imports. Three readings were wrong first:
#   * tracing scripts/demo.py showed no third-party imports -- it runs the
#     builder as a SUBPROCESS, so the trace saw only the parent;
#   * excluding numpy failed, because Terium/core/data_structures.py needs it;
#   * excluding antimony failed, because Terium/__init__ imports terium_engine,
#     which imports model_building, which imports antimony at module level --
#     so `import Terium` at all drags in the whole engine.
# antimony/roadrunner/libsbml are binary extensions with data files beside
# them, which is why they need --collect-all rather than a hidden import.
say "1/6  Freezing the report builder"
PY="${TERRIUM_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in "$REPO/.venv/bin/python" "$(command -v python3 || true)"; do
    if [ -x "$c" ] && "$c" -c 'import sys; raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "No Python 3.10-3.13 found. Set TERRIUM_PYTHON to one." >&2
  exit 3   # could not determine, not a build failure
fi
echo "     python: $PY"

"$PY" -m PyInstaller --onefile --name terrium-report \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  --paths "$REPO/Tests" --paths "$REPO" \
  --hidden-import brenda_client --hidden-import enzyme_lookup \
  --hidden-import fallback_logic --hidden-import lab_report \
  --hidden-import ensemble --hidden-import model_ensemble \
  --hidden-import spread_consequence \
  --collect-all antimony --collect-all roadrunner --collect-all libsbml \
  --exclude-module scipy --exclude-module pytest --exclude-module hypothesis \
  --exclude-module matplotlib --exclude-module PIL --exclude-module tkinter \
  --log-level WARN --noconfirm "$REPO/scripts/report_lab.py" >/dev/null

# ------------------------------------------------------------------ 2. shell
say "2/6  Compiling the app shell"
swiftc -O -o "$BUILD/Terrium" "$HERE/app/TerriumApp.swift" \
  -framework AppKit -framework WebKit

# ----------------------------------------------------------------- 3. bundle
say "3/6  Assembling Terrium.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/Terrium"                       "$APP/Contents/MacOS/Terrium"
cp "$BUILD/dist/terrium-report"           "$APP/Contents/Resources/terrium-report"
cp "$HERE/app/viewer.html"                "$APP/Contents/Resources/viewer.html"
cp "$HERE/app/lesson.js"                  "$APP/Contents/Resources/lesson.js"
cp "$HERE/app/Terrium.icns"               "$APP/Contents/Resources/Terrium.icns"
cp "$REPO/Tests/fixtures/brenda_ldh_fixture.html" \
                                          "$APP/Contents/Resources/brenda_ldh_fixture.html"
cp "$REPO/LICENSE"                        "$APP/Contents/Resources/LICENSE"
cp "$REPO/NOTICE"                         "$APP/Contents/Resources/NOTICE"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@COMMIT@/$COMMIT/g" \
    "$HERE/app/Info.plist" > "$APP/Contents/Info.plist"
chmod +x "$APP/Contents/MacOS/Terrium" "$APP/Contents/Resources/terrium-report"

# ------------------------------------------------------------- 4. smoke test
say "4/6  Smoke test: can the APP drive the bundled builder?"
# The app's own --selftest, not a direct call to the frozen binary.
#
# An earlier version ran `terrium-report` itself. That proves the builder
# works and says nothing about whether the app can find it, hand it the right
# payload, or read the reply -- which is most of what could break in a
# bundle. Screen recording is unavailable here, so "launch it and look" was
# not available either. Running the shipped executable in headless mode
# checks the path the user actually takes.
if ! "$APP/Contents/MacOS/Terrium" --selftest; then
  echo "     FAIL: the app could not produce a report. No DMG will be built." >&2
  exit 1
fi

# And the viewer, against the document this build actually produces -- not a
# stored sample, which would keep passing while the real report changed.
if command -v node >/dev/null 2>&1; then
  REPORT_MD="$BUILD/smoke-report.md"
  "$PY" - "$APP" "$REPORT_MD" <<'EXTRACT'
import json, pathlib, subprocess, sys
app, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
res = app / "Contents" / "Resources"
payload = {
    "title": "Lactate dehydrogenase in Homo sapiens",
    "question": "How fast is pyruvate consumed, and where did every number come from?",
    "ec": "1.1.1.27", "organism": "Homo sapiens",
    "fixture": str(res / "brenda_ldh_fixture.html"),
    "parameters": [{"name": "km", "substrate": "pyruvate", "quantity": "km"}],
    "supplied": [
        {"name": "s0", "value": 10.0, "unit": "mM", "basis": "chosen for this run"},
        {"name": "vmax", "value": 0.25, "unit": "mM/s", "basis": "chosen for this run"}],
    "s0": 10.0, "vmax": 0.25, "seed": 1,
}
done = subprocess.run([str(res / "terrium-report")], input=json.dumps(payload),
                      capture_output=True, text=True, timeout=300)
out.write_text(json.loads(done.stdout)["markdown"], encoding="utf-8")
EXTRACT
  if ! node "$HERE/test_viewer.mjs" "$REPORT_MD"; then
    echo "     FAIL: the viewer cannot typeset this report. No DMG will be built." >&2
    exit 1
  fi
  # The lesson layer, against the same report. It must either produce a
  # lesson whose every figure is in the document, or refuse -- a teaching
  # tool that always has something ready will eventually invent it.
  if ! node "$HERE/test_lesson.mjs" "$REPORT_MD"; then
    echo "     FAIL: the lesson layer disagrees with the report. No DMG will be built." >&2
    exit 1
  fi
else
  # Not a pass. Said out loud, because a skipped check that prints nothing is
  # indistinguishable from one that succeeded.
  echo "     NOT CHECKED: node is absent, so the viewer was not tested." >&2
fi

# ------------------------------------------------------------------ 5. sign
say "5/6  Signing ($SIGN_IDENTITY)"
# Extended attributes first. Copying files around macOS leaves Finder
# metadata behind, and codesign refuses with "resource fork, Finder
# information, or similar detritus not allowed" -- an accurate message that
# names none of the files responsible.
xattr -cr "$APP"

# Inner executables before the bundle that contains them. `--deep` is
# deprecated and, on a re-signed bundle, produced "code has no resources but
# signature indicates they must be present" -- a stale signature inside a
# fresh one. Signing inside-out avoids the situation rather than repairing it.
codesign --force --options runtime --timestamp=none \
         --sign "$SIGN_IDENTITY" "$APP/Contents/Resources/terrium-report"
codesign --force --options runtime --timestamp=none \
         --sign "$SIGN_IDENTITY" "$APP"
if ! codesign --verify --strict "$APP"; then
  # Hard stop. The previous version of this script printed the failure and
  # carried on to build a DMG from an unsigned app -- shipping exactly the
  # thing it promised at the top not to ship.
  echo "     FAIL: the signature does not verify. No DMG will be built." >&2
  exit 1
fi
echo "     signature verifies"

# ------------------------------------------------------------------- 6. dmg
say "6/6  Building the DMG"
rm -rf "$DMG_ROOT" "$DMG"
mkdir -p "$DMG_ROOT"
cp -R "$APP" "$DMG_ROOT/Terrium.app"
ln -s /Applications "$DMG_ROOT/Applications"
cp "$HERE/FIRST_RUN.txt" "$DMG_ROOT/READ ME FIRST.txt"

# An explicit size, with headroom.
#
# Left to size the volume itself, hdiutil underestimated and failed partway
# through with "No space left on device" -- on a disk with 111 GB free. The
# message is true of the volume it had just created and false of everything a
# reader would check, which cost twenty minutes.
SRC_MB="$(du -sm "$DMG_ROOT" | cut -f1)"
SIZE_MB=$(( SRC_MB * 2 + 50 ))
echo "     source ${SRC_MB}MB, allocating ${SIZE_MB}MB"
hdiutil create -volname "Terrium $VERSION" -srcfolder "$DMG_ROOT" \
        -ov -format UDZO -size "${SIZE_MB}m" "$DMG" >/dev/null

cp "$DMG" "$OUTDIR/Terrium.dmg"
rm -rf "$DMG_ROOT"

say "Done"
echo "  app: $APP  (built outside the synced tree)"
echo "  dmg: $OUTDIR/Terrium.dmg  ($(du -h "$OUTDIR/Terrium.dmg" | cut -f1))"
if [ "$SIGN_IDENTITY" = "-" ]; then
  cat <<'WARN'

  NOTE: ad-hoc signed. This DMG runs on THIS Mac. Anyone who downloads it
  will see "Terrium is damaged and can't be opened" until it is signed with
  a Developer ID Application certificate and notarised by Apple. That is an
  Apple account matter, not a code change. See release/README.md.
WARN
fi
