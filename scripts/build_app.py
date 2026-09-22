#!/usr/bin/env python3
"""Freeze the installed Terrium wheel into a downloadable, runnable folder.

WHAT IT BUILDS
--------------
One folder, one executable:

    terrium/                    (terrium-<version>-<os>-<arch>.tar.gz or .zip)
      terrium(.exe)             `terrium compose "..."`, `terrium sim wf ...`
      _internal/                the Python runtime, Terrium, and its libraries
      LICENSE, NOTICE           Terrium's own terms and what this folder conveys
      licenses/                 every third-party licence the folder carries
      README.txt                how to run it, and how to replace libSBML

It is a PyInstaller ONEDIR freeze of `Terium.app:main`, built from the wheel
that is INSTALLED in the interpreter running this script, not from the
checkout, so what a recipient runs is the released code and nothing else.

WHY ONEDIR, AND WHY THE LICENCES FOLDER
---------------------------------------
python-libsbml is LGPL-2.1. A onefile freeze packs its shared object inside
the executable, which a recipient cannot replace, and that is what PR #21
did (reviewed, not merged; see NOTICE). In a onedir freeze the object stays
an ordinary file, `_internal/libsbml/_libsbml.<abi>.so` (or `.pyd`), loaded
at run time by the interpreter's import mechanism, and a recipient can swap
it for an interface-compatible build. This script REFUSES to package a
folder in which that file is not a separate file. It also copies, for every
component the folder conveys, the licence files that component's own wheel
declares, plus the LGPL-2.1 text (which python-libsbml's wheel points at but
does not include), and lists them in licenses/README.txt. NOTICE says what
this means; this script makes sure the folder matches what NOTICE says.

WHAT IT CHECKS BEFORE IT WRITES THE ARCHIVE
-------------------------------------------
- Terium was imported from site-packages, not from this checkout.
- The frozen executable, run from an empty directory, prints the installed
  version, shows the engine's help, integrates a time course (roadrunner and
  antimony ran, not just a page printed), exports SBML (libsbml, lxml and
  the two packaged data files), and builds a shape from an expansion
  library (reached only through importlib, invisible to static analysis).
  A folder that cannot do all of that is not archived.
- libSBML's extension is a separate file; roadrunner's 48 MB of test
  fixtures are pruned and the executable still runs afterwards.

NOT REPRODUCIBLE BYTE-FOR-BYTE
------------------------------
PyInstaller's bootloader and archive carry timestamps and the runner's own
Python build. Two runs give the same files with different checksums. The
wheel inside is reproducible (see scripts/build_release.py); the folder is
not, and SHA256SUMS on the release page records the folder that was tested.

Usage (in a venv where `pip install pyinstaller dist/terrium-*.whl` ran):
    python3 scripts/build_app.py --out dist/app
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata as md
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent.parent

#: Packages whose native libraries the folder carries and which PyInstaller
#: has no hook for. `--collect-all` takes their modules, data and binaries.
COLLECT_ALL = ("libsbml", "roadrunner", "antimony")

#: Distributions whose licence files must be in licenses/. The names are
#: distribution (PyPI) names; the folder is checked to actually contain
#: each one's files before its licence is required.
CONVEYED = ("terrium", "python-libsbml", "libroadrunner", "antimony", "numpy", "scipy", "pyinstaller")

#: Directories inside _internal/ that are test fixtures, not the program.
PRUNE = ("roadrunner/tests",)

LAUNCHER = "from Terium.app import main\nimport sys\nsys.exit(main())\n"


def _fail(msg: str) -> NoReturn:
    print(f"NOT A RELEASE FOLDER: {msg}", file=sys.stderr)
    sys.exit(1)


def _platform_tag() -> str:
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{machine}"


def _installed_terium():
    """Import Terium and refuse to continue if it came from this checkout."""
    terium = importlib.import_module("Terium")
    where = Path(terium.__file__).resolve()
    # An installed wheel lives under a site-packages directory, wherever the
    # venv is; an editable install or a bare checkout does not.
    if "site-packages" not in where.parts and "dist-packages" not in where.parts:
        _fail(
            f"Terium imported from the checkout ({where}), not from an installed wheel.\n"
            "  Build the wheel (scripts/build_release.py), `pip install dist/terrium-*.whl`,\n"
            "  and run this script from a directory that is not the repository root."
        )
    return terium


def _run_pyinstaller(launcher: Path, work: Path, stage: Path) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--log-level", "WARN",
        "--onedir", "--console", "--name", "terrium",
        "--workpath", str(work / "build"),
        "--distpath", str(stage),
        "--specpath", str(work),
        "--collect-submodules", "Terium",
    ]
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    cmd.append(str(launcher))
    # cwd is the scratch directory so the checkout is never on the analysis path.
    subprocess.run(cmd, cwd=str(work), check=True)


def _exe(bundle: Path) -> Path:
    return bundle / ("terrium.exe" if platform.system() == "Windows" else "terrium")


def _prune(bundle: Path) -> list[str]:
    removed = []
    for rel in PRUNE:
        target = bundle / "_internal" / rel
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(rel)
    return removed


def _libsbml_object(bundle: Path) -> Path:
    hits = sorted((bundle / "_internal").rglob("_libsbml*"))
    hits = [h for h in hits if h.is_file() and h.suffix in (".so", ".pyd", ".dylib")]
    if len(hits) != 1:
        _fail(f"expected exactly one libSBML extension as a separate file under _internal/, found {hits}")
    return hits[0]


def _licence_files(dist_name: str) -> list[Path]:
    """The licence files a distribution declares (`License-File` metadata).

    Resolved through the distribution's own file list, so the dist-info
    directory's name never has to be guessed. Newer wheels put them under
    `licenses/`; older ones beside METADATA. Both are found.
    """
    try:
        dist = md.distribution(dist_name)
    except md.PackageNotFoundError:
        return []
    declared = {Path(name).name for name in (dist.metadata.get_all("License-File") or [])}
    found = []
    for entry in dist.files or []:
        parts = entry.parts
        if not any(part.endswith(".dist-info") for part in parts):
            continue
        # Declared, under licenses/, or named like a licence file: numpy and
        # scipy ship LICENSE.txt beside METADATA with no License-File header.
        looks_like_one = entry.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS"))
        if entry.name in declared or "licenses" in parts or looks_like_one:
            path = Path(str(dist.locate_file(entry)))
            if path.is_file():
                found.append(path)
    return sorted(set(found))


#: MIT's permission notice, verbatim. Antimony's wheel declares `License: MIT`
#: and `Author: Lucian Smith` and carries no licence file, so the notice the
#: licence requires to travel with copies has to be supplied here.
MIT_NOTICE = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


def _antimony_licence(target: Path) -> str:
    """Write antimony's licence into `target` and return a one-line provenance.

    First choice: the project's own LICENSE.txt for the installed version,
    fetched from its repository (GitHub, sys-bio/antimony) and accepted only
    if it is the MIT text. Fallback, when there is no network: the MIT
    notice above with the copyright holder as the package metadata names
    it, and a note saying exactly that.
    """
    import urllib.request

    version = md.version("antimony")
    meta = md.metadata("antimony")
    author = meta.get("Author", "the Antimony authors")
    url = f"https://raw.githubusercontent.com/sys-bio/antimony/v{version}/LICENSE.txt"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - fixed https host
            text = resp.read().decode("utf-8", "replace")
        if "Permission is hereby granted" in text and "Copyright" in text:
            (target / "LICENSE.txt").write_text(text, encoding="utf-8")
            return f"antimony {version}: licenses/antimony/LICENSE.txt (fetched from {url})"
    except (OSError, ValueError):
        pass
    note = (
        f"Antimony {version} is distributed under the MIT License; its wheel declares\n"
        f"`License: MIT` and `Author: {author}` and carries no licence file, and the\n"
        f"project's own LICENSE.txt could not be fetched from {url}\n"
        f"when this folder was built. The MIT permission notice follows, with the\n"
        f"copyright holder as the package metadata names it. The authoritative text\n"
        f"is in the Antimony repository (sys-bio/antimony, LICENSE.txt).\n\n"
        f"Copyright (c) {author}\n\n"
    ) + MIT_NOTICE
    (target / "LICENSE.txt").write_text(note, encoding="utf-8")
    return f"antimony {version}: licenses/antimony/LICENSE.txt (MIT notice reconstructed from package metadata; upstream file not fetched)"


def _python_licence() -> Path | None:
    for candidate in (
        Path(sysconfig.get_paths()["stdlib"]) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
    ):
        if candidate.is_file():
            return candidate
    return None


def _write_licences(bundle: Path) -> None:
    out = bundle / "licenses"
    out.mkdir(exist_ok=True)
    lines = [
        "Third-party software conveyed in this folder, and its licence files.",
        "Terrium itself: ../LICENSE (Apache-2.0). What is conveyed and under",
        "which terms: ../NOTICE.",
        "",
    ]
    for dist_name in CONVEYED:
        files = _licence_files(dist_name)
        if dist_name == "terrium":
            # Terrium's LICENSE and NOTICE sit at the folder root, from the
            # installed wheel's dist-info, so they are the released texts.
            for f in files:
                shutil.copy2(f, bundle / f.name)
            if not ((bundle / "LICENSE").is_file() and (bundle / "NOTICE").is_file()):
                _fail("the installed terrium wheel does not declare LICENSE and NOTICE")
            continue
        try:
            version = md.version(dist_name)
        except md.PackageNotFoundError:
            _fail(f"{dist_name} is not installed, so the folder cannot have been built with it")
        target = out / dist_name
        target.mkdir(exist_ok=True)
        if not files and dist_name == "antimony":
            lines.append(_antimony_licence(target))
            continue
        if not files:
            _fail(f"{dist_name} {version} declares no licence file; the folder would convey it without its terms")
        for f in files:
            shutil.copy2(f, target / f.name)
        lines.append(f"{dist_name} {version}: " + ", ".join(f"licenses/{dist_name}/{f.name}" for f in files))
    # The LGPL text python-libsbml's LICENSE.txt refers to but does not carry.
    lgpl = ROOT / "third_party_licenses" / "LGPL-2.1.txt"
    if not lgpl.is_file():
        _fail("third_party_licenses/LGPL-2.1.txt is missing; the folder conveys libSBML and must carry the LGPL text")
    shutil.copy2(lgpl, out / "python-libsbml" / "LGPL-2.1.txt")
    lines.append("python-libsbml: licenses/python-libsbml/LGPL-2.1.txt (the GNU LGPL v2.1 its terms refer to)")
    py = _python_licence()
    if py is None:
        _fail("the Python runtime's LICENSE.txt was not found on this machine; the folder conveys the runtime and must carry it")
    (out / "python").mkdir(exist_ok=True)
    shutil.copy2(py, out / "python" / "LICENSE.txt")
    lines.append(f"Python {platform.python_version()} runtime: licenses/python/LICENSE.txt (PSF licence)")
    (out / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_readme(bundle: Path, version: str, libsbml: Path, tag: str) -> None:
    rel = libsbml.relative_to(bundle).as_posix()
    exe = "terrium.exe" if platform.system() == "Windows" else "./terrium"
    text = f"""Terrium {version} ({tag})

Unaffiliated with Tellurium. See NOTICE.

RUN
    {exe} compose "a toggle switch between two repressors"
    {exe} sim wf --help
    {exe} --version

Run it from a terminal, inside this folder or with its full path. Nothing is
installed, nothing is written outside the directory you run it in, and no
network connection is made.

macOS: this folder is not signed with an Apple Developer ID, so the first
run is blocked with "cannot be opened because the developer cannot be
verified". Either allow it once under System Settings > Privacy & Security,
or remove the download flag:  xattr -dr com.apple.quarantine <this folder>

WHAT IS INSIDE, AND THE LGPL
    _internal/ holds the Python runtime, Terrium, and the libraries Terrium
    uses. One of them, libSBML (python-libsbml), is licensed under the GNU
    LGPL v2.1. It is the single file

        {rel}

    loaded at run time as a separate file, not compiled into the executable.
    You may replace it with your own interface-compatible build of
    python-libsbml for this Python version and platform; put the new file at
    the same path. Its terms are in licenses/python-libsbml/, with the LGPL
    text. Every other component's licence is in licenses/ too, listed in
    licenses/README.txt. Source for libSBML: https://github.com/sbmlteam/libsbml
    and https://pypi.org/project/python-libsbml/ (sdist).

WHAT THIS FOLDER DOES NOT DO
    The literature search (BRENDA resolvers) is not included; `--subject`
    builds the model and says no search was run. See the release notes.
"""
    (bundle / "README.txt").write_text(text, encoding="utf-8")


def _smoke(bundle: Path, version: str) -> None:
    exe = _exe(bundle)
    if not exe.is_file():
        _fail(f"executable missing: {exe}")
    with tempfile.TemporaryDirectory(prefix="terrium-smoke-") as empty:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}

        def run(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
            return subprocess.run([str(exe), *args], cwd=empty, env=env, capture_output=True, text=True, timeout=timeout)

        r = run("--version", timeout=120)
        if r.returncode != 0 or r.stdout.strip() != f"terrium {version}":
            _fail(f"--version: exit {r.returncode}, stdout {r.stdout!r}, stderr {r.stderr[-400:]!r}")
        r = run("sim", "--help", timeout=300)
        if r.returncode != 0 or "kimura" not in r.stdout:
            _fail(f"sim --help: exit {r.returncode}, stderr {r.stderr[-400:]!r}")
        # A VERDICT alone proves little: the report turns a failed simulation
        # into the note "no time course: ..." and still exits 0. So the time
        # course must have been integrated (roadrunner + antimony ran), the
        # SBML export must have produced SBML (libsbml, lxml and both packaged
        # data files), and an expansion-library shape must build (the five
        # motif libraries are reached only through importlib and are
        # invisible to the freezer's static analysis).
        checks = (
            (("compose", "reversible binding of a ligand to a receptor", "--no-ranking"), ("VERDICT:", "Integrated to t=")),
            (("compose", "reversible binding of a ligand to a receptor", "--export", "sbml"), ("<?xml", "<sbml")),
            (("compose", "two stage gene expression", "--no-analysis", "--no-simulate", "--no-ranking"), ("VERDICT:",)),
        )
        for args, markers in checks:
            r = run(*args)
            missing = [m for m in markers if m not in r.stdout]
            if r.returncode != 0 or missing or "no time course" in r.stdout:
                _fail(
                    f"{' '.join(args)}: exit {r.returncode}, missing {missing}, "
                    f"'no time course' present: {'no time course' in r.stdout}; "
                    f"stdout tail {r.stdout[-300:]!r}, stderr {r.stderr[-600:]!r}"
                )
        print("smoke  : --version, sim --help, a simulated time course, an SBML export and an")
        print("         expansion-library shape all ran from an empty directory")


def _archive(bundle: Path, out_dir: Path, version: str, tag: str) -> Path:
    if platform.system() == "Windows":
        archive = out_dir / f"terrium-{version}-{tag}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(bundle.rglob("*")):
                zf.write(path, Path("terrium") / path.relative_to(bundle))
    else:
        archive = out_dir / f"terrium-{version}-{tag}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(bundle, arcname="terrium")
    return archive


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "dist" / "app"), help="where the archive goes (default: dist/app/)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        importlib.import_module("PyInstaller")
    except ImportError:
        _fail("PyInstaller is not installed in this interpreter (pip install pyinstaller)")
    terium = _installed_terium()
    version = terium.__version__
    tag = _platform_tag()

    with tempfile.TemporaryDirectory(prefix="terrium-app-") as tmp:
        work = Path(tmp)
        launcher = work / "terrium_launcher.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        stage = work / "stage"
        _run_pyinstaller(launcher, work, stage)
        bundle = stage / "terrium"
        if not bundle.is_dir():
            _fail(f"PyInstaller did not produce {bundle}")

        pruned = _prune(bundle)
        libsbml = _libsbml_object(bundle)
        _write_licences(bundle)
        _write_readme(bundle, version, libsbml, tag)
        _smoke(bundle, version)

        archive = _archive(bundle, out_dir, version, tag)
        size = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())

    digest = _sha256(archive)
    (out_dir / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"folder : {size / 1e6:.0f} MB unpacked; pruned {pruned or 'nothing'}")
    print(f"libsbml: {libsbml.relative_to(bundle).as_posix()} (separate file, replaceable)")
    print(f"archive: {archive}")
    print(f"sha256 : {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
