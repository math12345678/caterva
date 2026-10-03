#!/usr/bin/env python3
"""Wrap the frozen `caterva` folder in Caterva.app, and Caterva.app in a DMG.

WHAT IT BUILDS
--------------
    dist/studio/
      Caterva.app/
        Contents/MacOS/Caterva          the Swift shell (macos/Sources), built by swiftc
        Contents/Info.plist             macos/Info.plist, version from caterva/__init__.py
        Contents/Resources/Caterva.icns drawn by macos/Icon/MakeIcon.swift, packed by iconutil
        Contents/Resources/first-run.txt
        Contents/Resources/caterva/     the PyInstaller folder scripts/build_app.py checked,
                                        copied whole (its LICENSE, NOTICE and licenses/ with it)
      Caterva-<version>-macos-arm64.dmg (with --dmg) Caterva.app, an Applications link,
                                        README.txt on opening an unsigned app
      Caterva-<version>-macos-arm64.dmg.sha256

The shell launches `Contents/Resources/caterva/caterva studio --port 0
--no-browser --print-url` and shows the URL it prints
(docs/studio/CONTRACT.md, section 16).

THE ORDER, AND WHO DOES EACH STEP
---------------------------------
1. The page: `pnpm --filter @workspace/caterva-studio run build` writes
   caterva/studio/static/ (`--build-page` runs it; CI runs it as its own step).
2. The wheel: scripts/build_release.py, after step 1, so the wheel carries
   the page (pyproject package-data).
3. The folder: scripts/build_app.py --require-studio-page --keep-folder DIR,
   in a venv where that wheel is installed. It refuses a folder whose
   `caterva studio --self-test` fails or that lacks the page.
4. This script, `--frozen DIR/caterva`: compile, draw the icon, assemble,
   seal with an ad-hoc signature, run `Caterva --smoke --require-page`
   against the assembled bundle, then (--dmg) make and verify the image.

Steps 2 and 3 install packages and run PyInstaller; this script does not do
them for you, because both decide what a person downloads and each already
refuses what it should refuse.

UNSIGNED, AND SAID SO
---------------------
The repository holds no Apple Developer ID, so nothing here is signed with
one or notarised. The bundle gets an AD-HOC signature (`codesign --sign -`):
Apple silicon will not run an unsigned arm64 binary at all, and a bundle
whose resources are not sealed is reported by Gatekeeper as "damaged" rather
than as "from an unidentified developer", which a person can approve in
System Settings (Apple's current instructions list only that route).
The DMG's README and the app's first-run sheet say how (Privacy & Security,
Open Anyway; then the xattr command); neither claims notarisation, and `check_unsigned_wording` refuses a
README or first-run text that does.

A DEVELOPMENT APP
-----------------
`--dev` assembles the same bundle with no frozen folder; its Info.plist sets
CATERVA_STUDIO_COMMAND (LSEnvironment) to a venv's python running
`-m caterva.app studio` in a checkout. LSEnvironment is read only when
Launch Services opens the app (Finder, `open`); running
Contents/MacOS/Caterva directly needs the variables in the environment,
and `--smoke` here passes them. A development app is never put in a DMG.

Usage:
    python3 scripts/build_studio_app.py --frozen dist/frozen/caterva --dmg
    python3 scripts/build_studio_app.py --dev --python .venv/bin/python --checkout . --out /tmp/studio-dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
MACOS = ROOT / "macos"
SOURCES = MACOS / "Sources"
STUDIO_PACKAGE = ROOT / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio"

#: The oldest macOS Caterva.app runs on, written into Info.plist
#: (LSMinimumSystemVersion), the DMG README and the docs. 14.0, because the
#: pinned wheels inside the app are built for it: NumPy 2.2.6 and SciPy 1.15.3
#: are macosx_14_0_arm64 and libRoadRunner 2.8.0 macosx_14_0_universal2
#: (`vtool -show-build` on their extension modules reports minos 14.0).
MIN_MACOS = "14.0"

#: The deployment target the Swift shell itself is compiled for. Lower than
#: MIN_MACOS on purpose: a shell that could not start on macOS 12 or 13 could
#: not tell the person why, and macos/Sources/Requirement.swift (which checks
#: ProcessInfo against MIN_MACOS) is how it does. WKDownload needs 11.3, so
#: 12.0 is enough for everything else the shell uses.
SHELL_TARGET_MACOS = "12.0"

#: What the page carries until the server writes the session token in
#: (caterva.studio.contract.TOKEN_PLACEHOLDER), read as text.
TOKEN_PLACEHOLDER = "__CATERVA_SESSION_TOKEN__"

#: The resources the shell reads at run time, from macos/Resources/.
RESOURCES = ("first-run.txt",)

#: Words that would claim a signature or a review the app does not have,
#: matched case-insensitively in text a person reads before opening it.
_CLAIMS = re.compile(r"\b(notari[sz]ed|signed|verified by apple|apple[- ]approved)\b", re.I)
#: A sentence that mentions those words only to deny them.
_DENIAL = re.compile(r"\b(not|never|no|isn't|hasn't|has not|is not|without|cannot)\b", re.I)


def _fail(msg: str) -> NoReturn:
    print(f"NOT A RELEASE APP: {msg}", file=sys.stderr)
    sys.exit(1)


@contextmanager
def step(name: str):
    """Say exactly which step failed, in the words of the step.

    A failing command raises CalledProcessError and `_fail` raises SystemExit;
    either way the job's log ends with one line naming the step (a GitHub
    annotation when CI reads it), instead of a traceback from somewhere in it.
    """
    print(f"== {name}", flush=True)
    try:
        yield
    except subprocess.CalledProcessError as exc:
        print(f"::error::Caterva.app build failed at the step: {name} (`{exc.cmd[0] if exc.cmd else '?'}` exited {exc.returncode})",
              flush=True)
        sys.exit(1)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"::error::Caterva.app build failed at the step: {name}", flush=True)
        raise


def package_version(root: Path = ROOT) -> str:
    """caterva.__version__, read as text: importing caterva needs the engine."""
    text = (root / "caterva" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.M)
    if not match:
        _fail("caterva/__init__.py has no __version__ line")
    return match.group(1)


def dmg_name(version: str, arch: str = "arm64") -> str:
    return f"Caterva-{version}-macos-{arch}.dmg"


def render_info_plist(template: str, version: str, build: str,
                      environment: Optional[dict] = None) -> bytes:
    """macos/Info.plist with the version and build filled in, as plist bytes.

    `environment` becomes LSEnvironment (a development app only). Refuses a
    template that still holds a placeholder afterwards, or a version that is
    not dotted numbers (CFBundleShortVersionString's rule).
    """
    if not re.fullmatch(r"\d+(\.\d+){0,2}", version):
        raise ValueError(f"version {version!r} is not one to three dot-separated numbers")
    if not re.fullmatch(r"\d+(\.\d+){0,2}", build):
        raise ValueError(f"build {build!r} is not one to three dot-separated numbers")
    text = template.replace("@VERSION@", version).replace("@BUILD@", build)
    left = sorted(set(re.findall(r"@[A-Z_]+@", text)))
    if left:
        raise ValueError(f"Info.plist still holds {', '.join(left)}")
    data = plistlib.loads(text.encode("utf-8"))
    if environment:
        data["LSEnvironment"] = dict(environment)
    return plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True)


def unsigned_wording_problems(text: str, where: str) -> list[str]:
    """Sentences in `text` that claim a signature or notarisation.

    A sentence may name either only to deny it ("is not signed", "has not
    been notarised"). Everything a person reads before opening the app is
    held to that, because the first time it would be wrong is the release
    that gets a Developer ID, and that release should change this text on
    purpose.
    """
    problems = []
    for sentence in re.split(r"(?<=[.!?:])\s+", " ".join(text.split())):
        if _CLAIMS.search(sentence) and not _DENIAL.search(sentence):
            problems.append(f"{where}: {sentence!r} claims a signature or notarisation")
    return problems


def frozen_problems(folder: Path, require_page: bool = True) -> list[str]:
    """What is wrong with a PyInstaller folder before it goes into the app."""
    problems = []
    exe = folder / "caterva"
    if not exe.is_file() or not os.access(exe, os.X_OK):
        problems.append(f"{exe} is not an executable file (run scripts/build_app.py --keep-folder first)")
    for name in ("LICENSE", "NOTICE", "licenses/README.txt"):
        if not (folder / name).is_file():
            problems.append(f"{folder / name} is missing: the app would convey the folder without its terms")
    literature = folder / "_internal" / "caterva" / "_literature"
    for name in ("fallback_logic.py", "brenda_client.py", "http_retry.py", "enzyme_lookup.py", "cite.py", "report_lab.py"):
        if not (literature / name).is_file():
            problems.append(f"{literature / name} is missing: the app would have no literature search")
    if require_page:
        notices = folder / "_internal" / "caterva" / "studio" / "static" / "licenses" / "THIRD-PARTY-NOTICES.txt"
        if not notices.is_file():
            problems.append(f"{notices} is missing: the page's packages would be conveyed without their licences")
        page = folder / "_internal" / "caterva" / "studio" / "static" / "index.html"
        if not page.is_file():
            problems.append(f"{page} is missing: the wheel was built before the page")
        elif TOKEN_PLACEHOLDER not in page.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"{page} has no {TOKEN_PLACEHOLDER}: not the studio's built page")
    return problems


def smoke_passed(stdout: str) -> bool:
    """`Caterva --smoke` ends with the line `caterva smoke: OK` and only then."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return bool(lines) and lines[-1] == "caterva smoke: OK" and not any(" FAIL " in f" {l} " for l in lines)


def swiftc_command(sources: Sequence[Path], output: Path, arch: str, module_cache: Path,
                   parse_as_library: bool = False) -> list[str]:
    command = ["xcrun", "swiftc", "-swift-version", "5", "-O",
               "-target", f"{arch}-apple-macos{SHELL_TARGET_MACOS}",
               "-module-cache-path", str(module_cache)]
    if parse_as_library:
        command.append("-parse-as-library")
    return command + [str(s) for s in sources] + ["-o", str(output)]


def _run(command: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    print("$ " + " ".join(str(c) for c in command), flush=True)
    return subprocess.run([str(c) for c in command], check=True, **kwargs)


#: hdiutil create fails now and then on a busy runner ("Resource busy"), with
#: nothing wrong in what it was asked to pack. Three tries, a pause between.
DMG_ATTEMPTS = 3
DMG_PAUSE_SECONDS = 20


def _retry(command: Sequence[str], attempts: int, pause: float) -> subprocess.CompletedProcess:
    """`_run`, repeated up to `attempts` times with `pause` seconds between."""
    for attempt in range(1, attempts + 1):
        try:
            return _run(command)
        except subprocess.CalledProcessError as exc:
            print(f"attempt {attempt} of {attempts}: {command[0]} exited {exc.returncode}", flush=True)
            if attempt == attempts:
                raise
            time.sleep(pause)
    raise AssertionError("unreachable")


def _need_macos() -> None:
    if platform.system() != "Darwin":
        _fail("Caterva.app is built on macOS (swiftc, iconutil, codesign, hdiutil)")
    for tool in ("xcrun", "iconutil", "codesign", "plutil"):
        if shutil.which(tool) is None:
            _fail(f"{tool} is not on PATH; install the Xcode Command Line Tools (xcode-select --install)")


def build_page(root: Path = ROOT) -> None:
    """The Vite build into caterva/studio/static/ (CONTRACT.md, section 19)."""
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        _fail("pnpm is not on PATH (corepack enable, then rerun)")
    _run([pnpm, "--filter", "@workspace/caterva-studio", "run", "build"], cwd=root / "Science-Agent-Pipeline")
    page = root / "caterva" / "studio" / "static" / "index.html"
    if not page.is_file() or TOKEN_PLACEHOLDER not in page.read_text(encoding="utf-8"):
        _fail(f"the page build did not write {page} with the token placeholder")


def compile_shell(work: Path, arch: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    binary = work / "Caterva"
    sources = sorted(SOURCES.glob("*.swift"))
    if not sources:
        _fail(f"no Swift sources under {SOURCES}")
    env = {**os.environ, "CLANG_MODULE_CACHE_PATH": str(cache)}
    _run(swiftc_command(sources, binary, arch, cache), env=env)
    return binary


def draw_icon(work: Path, arch: str, cache: Path, own_icns: bool = False) -> Path:
    """Caterva.icns: MakeIcon.swift draws every size, iconutil packs them.

    `own_icns` ships MakeIcon's own packing of the same PNGs instead, for a
    machine where iconutil cannot run (it writes to the per-user temporary
    folder, which a sandbox may refuse).
    """
    cache.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CLANG_MODULE_CACHE_PATH": str(cache)}
    tool = work / "make-icon"
    _run(swiftc_command([MACOS / "Icon" / "MakeIcon.swift", SOURCES / "Mark.swift"], tool, arch, cache,
                        parse_as_library=True), env=env)
    iconset = work / "Caterva.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    own = work / "Caterva-own.icns"
    _run([tool, iconset, own])
    if own_icns:
        return own
    icns = work / "Caterva.icns"
    _run(["iconutil", "-c", "icns", iconset, "-o", icns])
    return icns


def assemble(app: Path, binary: Path, icns: Path, plist: bytes, frozen: Optional[Path]) -> None:
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    shutil.copy2(binary, contents / "MacOS" / "Caterva")
    (contents / "Info.plist").write_bytes(plist)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    shutil.copy2(icns, contents / "Resources" / "Caterva.icns")
    for name in RESOURCES:
        shutil.copy2(MACOS / "Resources" / name, contents / "Resources" / name)
    if frozen is not None:
        shutil.copytree(frozen, contents / "Resources" / "caterva", symlinks=True)
    _run(["plutil", "-lint", contents / "Info.plist"])


def seal(app: Path) -> None:
    """An ad-hoc signature over the whole bundle; not a Developer ID."""
    _run(["codesign", "--force", "--deep", "--sign", "-", "--timestamp=none", app])
    _run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])


def smoke(app: Path, environment: Optional[dict], require_page: bool) -> str:
    args = [str(app / "Contents" / "MacOS" / "Caterva"), "--smoke"]
    if require_page:
        args.append("--require-page")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CATERVA_STUDIO_")}
    env.update(environment or {})
    print("$ " + " ".join(args), flush=True)
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=240)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0 or not smoke_passed(result.stdout):
        _fail(f"Caterva --smoke failed (exit {result.returncode}); the app would open onto an error view")
    return result.stdout


def make_dmg(app: Path, out: Path, version: str, arch: str) -> Path:
    if shutil.which("hdiutil") is None:
        _fail("hdiutil is not on PATH")
    readme = (MACOS / "dmg" / "README.txt").read_text(encoding="utf-8").replace("@VERSION@", version)
    if re.search(r"@[A-Z_]+@", readme):
        _fail("macos/dmg/README.txt still holds a placeholder")
    dmg = out / dmg_name(version, arch)
    with tempfile.TemporaryDirectory(prefix="caterva-dmg-") as tmp:
        stage = Path(tmp) / "Caterva"
        stage.mkdir()
        shutil.copytree(app, stage / "Caterva.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        (stage / "README.txt").write_text(readme, encoding="utf-8")
        if dmg.exists():
            dmg.unlink()
        with step("make the disk image (hdiutil create)"):
            _retry(["hdiutil", "create", "-volname", f"Caterva {version}", "-srcfolder", stage,
                    "-fs", "HFS+", "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", dmg],
                   attempts=DMG_ATTEMPTS, pause=DMG_PAUSE_SECONDS)
    with step("verify the disk image (hdiutil verify)"):
        _run(["hdiutil", "verify", dmg])
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    (out / (dmg.name + ".sha256")).write_text(f"{digest}  {dmg.name}\n", encoding="utf-8")
    print(f"dmg    : {dmg} ({dmg.stat().st_size / 1e6:.1f} MB)\nsha256 : {digest}")
    return dmg


def dev_environment(python: Path, checkout: Path, data_dir: Optional[Path]) -> dict:
    """CATERVA_STUDIO_* for a development app: the venv's python, the checkout."""
    if not python.is_absolute() or not os.access(python, os.X_OK):
        _fail(f"--python {python} is not an absolute path to an executable")
    if not (checkout / "caterva" / "app.py").is_file():
        _fail(f"--checkout {checkout} is not a Caterva checkout (no caterva/app.py)")
    environment = {
        "CATERVA_STUDIO_COMMAND": json.dumps([str(python), "-m", "caterva.app", "studio"]),
        "CATERVA_STUDIO_CWD": str(checkout),
    }
    if data_dir is not None:
        environment["CATERVA_STUDIO_DATA_DIR"] = str(data_dir)
    return environment


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--frozen", metavar="DIR", help="the checked PyInstaller folder (build_app.py --keep-folder DIR/..)")
    source.add_argument("--dev", action="store_true", help="a development app that runs --python in --checkout")
    parser.add_argument("--python", default=sys.executable, help="--dev: the interpreter to run (default: this one)")
    parser.add_argument("--checkout", default=str(ROOT), help="--dev: the checkout to run (default: this one)")
    parser.add_argument("--data-dir", help="--dev: pass --data-dir to the server (keeps development runs apart)")
    parser.add_argument("--out", default=str(ROOT / "dist" / "studio"), help="where Caterva.app goes (default: dist/studio/)")
    parser.add_argument("--build-page", action="store_true", help="run the page build first (needs pnpm)")
    parser.add_argument("--build-number", default="1", help="CFBundleVersion (CI passes the commit count)")
    parser.add_argument("--arch", default="arm64", choices=("arm64", "x86_64"), help="the shell's architecture (default: arm64)")
    parser.add_argument("--no-smoke", action="store_true", help="skip Caterva --smoke (a sandbox that cannot bind ports)")
    parser.add_argument("--allow-no-page", action="store_true", help="--dev: accept a checkout whose page is not built")
    parser.add_argument("--dmg", action="store_true", help="also make the DMG (not with --dev)")
    parser.add_argument("--own-icns", action="store_true",
                        help="use the icon tool's own .icns, not iconutil's (where iconutil cannot run)")
    parser.add_argument("--module-cache", help="keep swiftc's module cache here between builds "
                        "(the first build of the SDK's modules is the slow part)")
    args = parser.parse_args(argv)

    _need_macos()
    if args.dev and args.dmg:
        _fail("a development app is never put in a DMG")
    version = package_version()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    with step("check the README and first-run text claim no signature"):
        for name, path in (("README", MACOS / "dmg" / "README.txt"), ("first-run text", MACOS / "Resources" / "first-run.txt")):
            problems = unsigned_wording_problems(path.read_text(encoding="utf-8"), name)
            if problems:
                _fail("; ".join(problems))

    if args.build_page:
        with step("build the page (pnpm)"):
            build_page()

    frozen: Optional[Path] = None
    environment: Optional[dict] = None
    require_page = True
    if args.frozen:
        frozen = Path(args.frozen).resolve()
        with step("check the frozen folder"):
            problems = frozen_problems(frozen)
            if problems:
                _fail("; ".join(problems))
            r = subprocess.run([str(frozen / "caterva"), "--version"], capture_output=True, text=True, timeout=300)
            if r.stdout.strip() != f"caterva {version}":
                _fail(f"the frozen folder says {r.stdout.strip()!r}; this checkout is caterva {version}")
    else:
        checkout = Path(args.checkout).resolve()
        environment = dev_environment(Path(args.python), checkout,
                                      Path(args.data_dir).resolve() if args.data_dir else None)
        page = checkout / "caterva" / "studio" / "static" / "index.html"
        require_page = not args.allow_no_page
        if require_page and not page.is_file():
            _fail(f"{page} is missing; build the page or pass --allow-no-page")

    template = (MACOS / "Info.plist").read_text(encoding="utf-8")
    try:
        plist = render_info_plist(template, version, args.build_number, environment)
    except ValueError as exc:
        _fail(str(exc))

    with tempfile.TemporaryDirectory(prefix="caterva-shell-") as tmp:
        work = Path(tmp)
        # Not resolved: swiftc records the spelling, and /tmp and /private/tmp
        # naming one cache make it load each module twice and crash.
        cache = Path(os.path.abspath(args.module_cache)) if args.module_cache else work / "module-cache"
        with step("compile the Swift shell (swiftc)"):
            binary = compile_shell(work, args.arch, cache)
        with step("draw the icon"):
            icns = draw_icon(work, args.arch, cache, own_icns=args.own_icns)
        app = out / "Caterva.app"
        with step("assemble Caterva.app"):
            assemble(app, binary, icns, plist, frozen)
    with step("seal the bundle with an ad-hoc signature (codesign)"):
        seal(app)
    print(f"app    : {app}")

    if not args.no_smoke:
        with step("run Caterva --smoke on the assembled bundle"):
            smoke(app, environment, require_page)
    if args.dmg:
        make_dmg(app, out, version, args.arch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
