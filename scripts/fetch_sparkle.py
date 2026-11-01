#!/usr/bin/env python3
"""Fetch the pinned Sparkle distribution and check it against its SHA-256.

Caterva.app updates itself with Sparkle 2 (https://sparkle-project.org). The
framework is not vendored into git: this script downloads the release archive
the project publishes, refuses it unless its SHA-256 equals the pin below,
and unpacks it into a folder the build reads. The same pin serves
scripts/build_studio_app.py (which links and embeds Sparkle.framework) and
the release workflow (which runs Sparkle's `sign_update` on the update
archive).

THE PIN
-------
    version  2.10.0
    archive  Sparkle-2.10.0.tar.xz from the Sparkle project's GitHub release
    sha256   the value of SPARKLE_SHA256 below. It equals the digest GitHub
             shows for that release asset, and was recomputed from the
             downloaded file.

To move to another Sparkle release: change the three constants together,
read the new release's LICENSE for components added or dropped (NOTICE
records the set: Sparkle's MIT licence with the licences of bsdiff, sais-lite,
ed25519 and SUSignatureVerifier), then rebuild.

LICENCE
-------
Sparkle is MIT. Its LICENSE file also carries the notices of the components
compiled into it: bsdiff and bspatch (BSD-2-Clause, Colin Percival), sais-lite
(MIT, Yuta Mori), an Ed25519 implementation (zlib licence, Orson Peters) and
SUSignatureVerifier (BSD-2-Clause, Mark Hamlin). The build copies that file
into Caterva.app/Contents/Resources/licenses/Sparkle-LICENSE.txt.

Usage:
    python3 scripts/fetch_sparkle.py --out dist/sparkle
    python3 scripts/fetch_sparkle.py --out dist/sparkle --archive ~/Downloads/Sparkle-2.10.0.tar.xz
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import NoReturn, Optional, Sequence

SPARKLE_VERSION = "2.10.0"
SPARKLE_URL = (
    "https://github.com/sparkle-project/Sparkle/releases/download/"
    f"{SPARKLE_VERSION}/Sparkle-{SPARKLE_VERSION}.tar.xz"
)
SPARKLE_SHA256 = "c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"

#: What the archive must contain, relative to its top folder, for the build.
REQUIRED = (
    "Sparkle.framework/Versions/B/Sparkle",
    "Sparkle.framework/Versions/B/Autoupdate",
    "Sparkle.framework/Versions/B/Updater.app/Contents/MacOS/Updater",
    "Sparkle.framework/Versions/B/Modules/module.modulemap",
    "bin/sign_update",
    "LICENSE",
)


def _fail(message: str) -> NoReturn:
    print(f"SPARKLE NOT FETCHED: {message}", file=sys.stderr)
    sys.exit(1)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_problem(path: Path, expected: str = SPARKLE_SHA256) -> Optional[str]:
    """Why `path` is not the pinned archive, or None when it is."""
    if not path.is_file():
        return f"{path} is not a file"
    actual = sha256_of(path)
    if actual != expected:
        return f"{path.name} has SHA-256 {actual}, not the pinned {expected}"
    return None


def unsafe_members(names: Sequence[str]) -> list[str]:
    """Archive member names that would land outside the folder they are unpacked into."""
    bad = []
    for name in names:
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts or not parts:
            bad.append(name)
    return bad


def missing_files(top: Path) -> list[str]:
    return [name for name in REQUIRED if not (top / name).exists()]


def download(url: str, destination: Path, attempts: int = 3) -> None:
    last: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as out:  # noqa: S310 - https, pinned URL
                shutil.copyfileobj(response, out)
            return
        except OSError as exc:
            last = exc
            print(f"download attempt {attempt} of {attempts} failed: {exc}", file=sys.stderr)
            time.sleep(5 * attempt)
    _fail(f"could not download {url}: {last}")


def extract(archive: Path, into: Path) -> Path:
    """Unpack the archive into `into`; return the folder holding Sparkle.framework."""
    with tarfile.open(archive, "r:xz") as bundle:
        names = bundle.getnames()
        bad = unsafe_members(names)
        if bad:
            _fail(f"the archive has members outside its folder: {bad[:3]}")
        for member in bundle.getmembers():
            if member.issym() or member.islnk():
                target = (Path(member.name).parent / member.linkname)
                if member.linkname.startswith("/") or ".." in Path(os.path.normpath(target)).parts:
                    _fail(f"the archive has a link that leaves its folder: {member.name} -> {member.linkname}")
        bundle.extractall(into)  # members and links checked above  # noqa: S202
    return into


def fetch(out: Path, archive: Optional[Path] = None) -> Path:
    """The folder holding the verified Sparkle distribution (created or reused).

    `out/Sparkle-<version>/` is reused only when it holds every required file
    and the `.sha256` marker written beside it names the pinned digest.
    """
    top = out / f"Sparkle-{SPARKLE_VERSION}"
    marker = out / f"Sparkle-{SPARKLE_VERSION}.verified"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == SPARKLE_SHA256 and not missing_files(top):
        return top
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="caterva-sparkle-") as tmp:
        source = archive
        if source is None:
            source = Path(tmp) / f"Sparkle-{SPARKLE_VERSION}.tar.xz"
            print(f"downloading {SPARKLE_URL}", flush=True)
            download(SPARKLE_URL, source)
        problem = archive_problem(source)
        if problem:
            _fail(problem)
        print(f"sha256 ok : {SPARKLE_SHA256}", flush=True)
        if top.exists():
            shutil.rmtree(top)
        top.mkdir()
        extract(source, top)
    lacking = missing_files(top)
    if lacking:
        _fail(f"the archive lacks {', '.join(lacking)}")
    marker.write_text(SPARKLE_SHA256 + "\n", encoding="utf-8")
    return top


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="dist/sparkle", help="where Sparkle-<version>/ goes (default: dist/sparkle)")
    parser.add_argument("--archive", help="use this already downloaded archive (still checked against the pin)")
    args = parser.parse_args(argv)
    top = fetch(Path(args.out).resolve(), Path(args.archive).resolve() if args.archive else None)
    print(top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
