#!/usr/bin/env python3
"""Build the release artifacts: sdist first, then the wheel FROM the sdist.

WHY THE ORDER MATTERS
---------------------
The first 0.2.0 wheel, built while preparing the release straight from the
working tree, carried
`caterva/conftest.py`, the repository's own pytest path shim. `MANIFEST.in`
excludes that file, but `MANIFEST.in` governs the SDIST, and
`[tool.setuptools.exclude-package-data]` governs data files, not `.py`
modules. Neither touches a wheel built directly from the tree.

A wheel built from the extracted sdist cannot contain anything the sdist
does not, so the sdist's exclusions hold for the wheel as well. That is also
what `python -m build` does by default; this script does the same through
the PEP 517 hooks so that building a release needs nothing beyond
setuptools, and so the procedure is written down where the next person can
read it rather than remembered.

(`python -m build` has a second hazard here: setuptools leaves a `build/`
directory in the checkout, and `-m` puts the current directory first on
`sys.path`, so `build/` shadows the `build` package. `python -P -m build`
avoids it on 3.11+. Not needing the package avoids it on every version.)

REPRODUCIBILITY, STATED EXACTLY
-------------------------------
With `SOURCE_DATE_EPOCH` set, two runs of this script on the same commit
produce byte-identical artifacts, both of them. The script sets it to the
HEAD commit's timestamp when the caller has not, so "check out the tag and
run the script" is enough to reproduce both checksums.

The wheel is reproducible as setuptools writes it. The sdist is not:
setuptools regenerates `PKG-INFO` and `*.egg-info/` with fresh mtimes inside
the tar, and gzip stores a timestamp of its own. So the sdist is rewritten
after the build (`_normalize_sdist`): same members, same bytes per member,
members in sorted order, every mtime set to the epoch, uid/gid 0, empty
owner names, gzip mtime 0 and no embedded filename. That is the
reproducible-builds.org recipe; `python -m build` does not apply it. The
rewritten archive is then re-opened and its member list and contents
compared with the original's before it is kept, so a rewrite that lost or
changed a byte cannot be shipped.

THE LITERATURE LAYER
--------------------
Before the sdist is built, scripts/vendor_literature.py copies the modules of
`Tests/` that `caterva.checkout.literature_module` can load, and the modules
those import, into `caterva/_literature/` (git-ignored, deterministic bytes).
`MANIFEST.in` and package-data carry them into the sdist and the wheel, and the
wheel is refused if the core of the layer is not in it.

WHAT IT CHECKS BEFORE IT WRITES SHA256SUMS
------------------------------------------
The wheel is opened and its file list is held to what the release notes
and NOTICE claim: every member under `caterva/` or the dist-info, LICENSE and
NOTICE present, no test, conftest or pytest configuration inside, and no
native object (`.so`, `.pyd`, `.dylib`, `.dll`), because NOTICE says the
wheel conveys no third-party library. A wheel that fails a check is
deleted, not shipped with a caveat.

Usage:
    python3 scripts/build_release.py            # writes dist/
    python3 scripts/build_release.py --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Paths that must not appear in a release wheel, as substrings of the
#: archive member names. Each is something the working tree contains and
#: the sdist prunes; seeing one means the wheel was not built from the sdist.
FORBIDDEN_IN_WHEEL = (
    "conftest.py",
    "pytest.ini",
    "/tests/",
    "/Tests/",
    ".coverage",
    "__pycache__",
    # NOTICE says the wheel conveys no third-party library. A native object
    # in it would make that false, and the pure-Python tag would be a lie.
    ".so",
    ".pyd",
    ".dylib",
    ".dll",
)

#: Files the release notes say are inside the wheel.
REQUIRED_IN_WHEEL = ("LICENSE", "NOTICE")

#: Literature modules the wheel must carry (caterva/_literature/, vendored from
#: Tests/ by scripts/vendor_literature.py). A wheel without them cannot run a
#: literature search, the headline feature, and reports that it cannot.
REQUIRED_LITERATURE = ("fallback_logic", "brenda_client", "http_retry", "enzyme_lookup", "citation",
                       "parameterize", "model_compatibility", "assay_conditions", "evidence_rank")


def _build_sdist(out_dir: Path) -> Path:
    from setuptools import build_meta  # PEP 517 backend, imported lazily

    name = build_meta.build_sdist(str(out_dir))
    return out_dir / name


def _build_wheel_from_sdist(sdist: Path, out_dir: Path, work: Path) -> Path:
    """Extract the sdist and build the wheel from INSIDE it.

    The backend builds whatever is in the current directory, so we change
    into the extracted tree for the duration of the call and back out
    afterwards, even on failure.
    """
    import os

    from setuptools import build_meta

    with tarfile.open(sdist) as tar:
        tar.extractall(work, filter="data")
    (src,) = [p for p in work.iterdir() if p.is_dir()]
    previous = os.getcwd()
    os.chdir(src)
    try:
        name = build_meta.build_wheel(str(out_dir))
    finally:
        os.chdir(previous)
    return out_dir / name


def _check_wheel(wheel: Path) -> list[str]:
    """Return the ways this wheel falls short of a release wheel. Empty is good."""
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    for member in names:
        for bad in FORBIDDEN_IN_WHEEL:
            if bad in member:
                problems.append(f"contains {member} (matches {bad!r})")
    for required in REQUIRED_IN_WHEEL:
        if not any(m.endswith("/" + required) or m == required for m in names):
            problems.append(f"missing {required}")
    for module in REQUIRED_LITERATURE:
        if f"caterva/_literature/{module}.py" not in names:
            problems.append(f"missing caterva/_literature/{module}.py (the literature layer was not vendored)")
    modules = [m for m in names if m.endswith(".py")]
    # Every member is Caterva's package or its own metadata; nothing else.
    outside = [m for m in names if not (m.startswith("caterva/") or ".dist-info/" in m)]
    if outside:
        problems.append(f"members outside caterva/ and the dist-info: {outside[:5]}")
    if not modules:
        problems.append("no Python modules at all")
    return problems


def _head_commit_epoch() -> str | None:
    """The HEAD commit's timestamp, or None outside a git checkout."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT,
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def _normalize_sdist(sdist: Path, epoch: int) -> None:
    """Rewrite the sdist so its bytes depend only on its contents and `epoch`.

    The archive setuptools produced is read completely, its members sorted
    by name with mtime/uid/gid/owner names normalised, and written back
    through gzip with mtime=0 and no filename field. Contents are untouched.
    The result is re-read and compared member-by-member with the original
    before it replaces it; any difference in names or bytes raises.
    """
    import gzip
    import io
    import os

    with tarfile.open(sdist, "r:gz") as tar:
        original = [(m, tar.extractfile(m).read() if m.isfile() else None) for m in tar.getmembers()]
    original.sort(key=lambda md: md[0].name)

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as out:
        for member, data in original:
            # A PAX archive carries a second copy of mtime (sub-second, as a
            # header string) that wins over the field on write; drop it, or
            # the "normalised" archive keeps the build machine's clock.
            member.pax_headers = {}
            member.mtime = int(epoch)
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            out.addfile(member, io.BytesIO(data) if data is not None else None)

    rewritten = sdist.with_name(sdist.name + ".normalized")
    with rewritten.open("wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
        gz.write(raw.getvalue())

    with tarfile.open(rewritten, "r:gz") as tar:
        check = {m.name: (tar.extractfile(m).read() if m.isfile() else None) for m in tar.getmembers()}
    expected = {m.name: data for m, data in original}
    if check != expected:
        rewritten.unlink()
        raise RuntimeError("sdist normalisation changed the archive's contents; refusing to keep it")
    os.replace(rewritten, sdist)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist"), help="output directory (default: dist/)")
    args = parser.parse_args(argv)

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    import os

    os.chdir(ROOT)
    # The literature layer is part of the package at release time: copy it in
    # before the sdist is built, exactly as the Studio page is built first.
    sys.path.insert(0, str(ROOT / "scripts"))
    import vendor_literature

    vendored = vendor_literature.vendor()
    print(f"vendor: {len(vendored)} literature modules copied into caterva/_literature/")
    epoch = os.environ.get("SOURCE_DATE_EPOCH") or _head_commit_epoch()
    if epoch:
        os.environ["SOURCE_DATE_EPOCH"] = epoch
    with tempfile.TemporaryDirectory(prefix="caterva-release-") as tmp:
        work = Path(tmp)
        # Build the sdist into a scratch directory first so a failed wheel
        # build does not leave a lone sdist in dist/ looking like a release.
        try:
            sdist = _build_sdist(work / "sdist")
        finally:
            # The sdist carries the copies into the wheel; leaving them in the
            # checkout would make every scan of caterva/ see each literature
            # module twice.
            vendor_literature.remove()
        wheel = _build_wheel_from_sdist(sdist, work / "wheel", work / "src")

        problems = _check_wheel(wheel)
        if problems:
            print("NOT A RELEASE WHEEL:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1

        final_sdist = out_dir / sdist.name
        final_wheel = out_dir / wheel.name
        shutil.copy2(sdist, final_sdist)
        shutil.copy2(wheel, final_wheel)
        if epoch:
            _normalize_sdist(final_sdist, int(epoch))

    sums = out_dir / "SHA256SUMS"
    with sums.open("w", encoding="utf-8") as fh:
        for artifact in (final_wheel, final_sdist):
            fh.write(f"{_sha256(artifact)}  {artifact.name}\n")

    with zipfile.ZipFile(final_wheel) as zf:
        module_count = sum(1 for m in zf.namelist() if m.endswith(".py"))
    print(f"sdist : {final_sdist.relative_to(ROOT) if final_sdist.is_relative_to(ROOT) else final_sdist}")
    print(f"wheel : {final_wheel.relative_to(ROOT) if final_wheel.is_relative_to(ROOT) else final_wheel}"
          f"  ({module_count} modules, all under caterva/)")
    print(f"sums  : {sums.relative_to(ROOT) if sums.is_relative_to(ROOT) else sums}")
    print(f"epoch : SOURCE_DATE_EPOCH={os.environ.get('SOURCE_DATE_EPOCH', '(unset)')}"
          "  (both artifacts are byte-reproducible under this value)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
