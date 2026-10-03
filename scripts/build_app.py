#!/usr/bin/env python3
"""Freeze the installed Caterva wheel into a downloadable, runnable folder.

WHAT IT BUILDS
--------------
One folder, one executable:

    caterva/                    (caterva-<version>-<os>-<arch>.tar.gz or .zip)
      caterva(.exe)             `caterva compose "..."`, `caterva sim wf ...`
      _internal/                the Python runtime, Caterva, and its libraries
      LICENSE, NOTICE           Caterva's own terms and what this folder conveys
      licenses/                 every third-party licence the folder carries
      README.txt                how to run it, and how to replace libSBML

It is a PyInstaller ONEDIR freeze of `caterva.app:main`, built from the wheel
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
folder in which that file is not a separate file.

That is not the only libSBML in the folder. libroadrunner's `_roadrunner`
extension and Antimony's `libantimony` library each carry their own
statically linked copy (measured on this machine: 5.20.4 and 5.20.2, beside
python-libsbml's 5.21.1), put there by their upstream projects, and those a
recipient cannot swap. So the script scans every binary it collected for
libSBML, writes each copy, its version and whether it is replaceable into
README.txt and into a `libsbml-copies-<platform>.tsv` beside the archive,
and the release workflow attaches the corresponding source for every
version listed. It also copies, for every component the folder conveys, the
licence files that component's own wheel declares, keeping their paths,
plus the LGPL-2.1 text (which python-libsbml's wheel points at but does not
include), and lists them in licenses/README.txt. NOTICE says what this
means; this script makes sure the folder matches what NOTICE says.

WHAT IT CHECKS BEFORE IT WRITES THE ARCHIVE
-------------------------------------------
- Caterva was imported from site-packages, not from this checkout.
- The frozen executable, run from an empty directory, prints the installed
  version, shows the engine's help, integrates a time course (roadrunner and
  antimony ran, not just a page printed), exports SBML (libsbml, lxml and
  the two packaged data files), and builds a shape from an expansion
  library (reached only through importlib, invisible to static analysis).
  A folder that cannot do all of that is not archived.
- The literature layer is inside: `_internal/caterva/_literature/` holds the
  modules the wheel carries (scripts/vendor_literature.py), their imports are
  analysed by the freezer, and the frozen executable runs
  `caterva compose --subject 2.7.1.1 --organism human --substrate glucose`
  OFFLINE from the repository's recorded BRENDA page and database answers
  (Tests/fixtures/recorded/, read from the checkout this script sits in, set
  for that one child process only, with every proxy closed so a request with
  no recording fails instead of reaching a database), and the report must
  say the two constants came from the literature with their citations.
- libSBML's extension is a separate file; roadrunner's 48 MB of test
  fixtures are pruned and the executable still runs afterwards.
- `caterva studio --self-test` passes from the frozen folder: the studio
  server starts on a real loopback socket, answers /api/health with its
  session token and refuses it without, and serves `/`. Caterva.app runs
  exactly this executable, so a folder whose studio cannot start would
  ship an app that opens onto an error view. With `--require-studio-page`
  the built page must also be inside (_internal/caterva/studio/static/,
  collected from the installed wheel) and be the page `/` serves; the DMG
  build passes it, the plain archive does not, because the release wheel
  is built without the page (docs/studio/CONTRACT.md, section 16).

`--keep-folder DIR` also copies the checked folder to DIR/caterva, which
scripts/build_studio_app.py wraps into Caterva.app. It is the same folder
the archive holds, copied after every check above passed.

NOT REPRODUCIBLE BYTE-FOR-BYTE
------------------------------
PyInstaller's bootloader and archive carry timestamps and the runner's own
Python build. Two runs give the same files with different checksums. The
wheel inside is reproducible (see scripts/build_release.py); the folder is
not, and SHA256SUMS on the release page records the folder that was tested.

Usage (in a venv where `pip install pyinstaller dist/caterva-*.whl` ran):
    python3 scripts/build_app.py --out dist/app
    python3 scripts/build_app.py --out dist/app --require-studio-page --keep-folder dist/frozen
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata as md
import os
import platform
import re
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
CONVEYED = ("caterva", "python-libsbml", "libroadrunner", "antimony", "numpy", "scipy", "pyinstaller")

#: Directories inside _internal/ that are test fixtures, not the program.
PRUNE = ("roadrunner/tests",)

LAUNCHER = "from caterva.app import main\nimport sys\nsys.exit(main())\n"

#: The recorded real answers the offline literature smoke check replays: the
#: BRENDA page for EC 2.7.1.1 and the NCBI, UniProt and PubChem responses one
#: human hexokinase Km lookup makes (Tests/fixtures/recorded/README.md). They
#: stay in the repository; no release artifact carries them, and nothing at
#: run time reads them unless these variables point at them.
RECORDED = ROOT / "Tests" / "fixtures" / "recorded"
PROXY_VARIABLES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
#: Port 9 on loopback: nothing listens, so a request with no recording fails at once.
CLOSED_PROXY = "http://127.0.0.1:9"


def _fail(msg: str) -> NoReturn:
    print(f"NOT A RELEASE FOLDER: {msg}", file=sys.stderr)
    sys.exit(1)


def _platform_tag() -> str:
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{machine}"


def _installed_caterva():
    """Import Caterva and refuse to continue if it came from this checkout."""
    caterva = importlib.import_module("caterva")
    where = Path(caterva.__file__).resolve()
    # An installed wheel lives under a site-packages directory, wherever the
    # venv is; an editable install or a bare checkout does not.
    if "site-packages" not in where.parts and "dist-packages" not in where.parts:
        _fail(
            f"Caterva imported from the checkout ({where}), not from an installed wheel.\n"
            "  Build the wheel (scripts/build_release.py), `pip install dist/caterva-*.whl`,\n"
            "  and run this script from a directory that is not the repository root."
        )
    return caterva


def _literature_dir(caterva) -> Path:
    """The installed wheel's copy of the literature layer, or fail."""
    directory = Path(caterva.__file__).resolve().parent / "_literature"
    if not (directory / "fallback_logic.py").is_file():
        _fail(
            f"{directory} has no fallback_logic.py: the installed wheel carries no literature layer.\n"
            "  scripts/build_release.py vendors it (scripts/vendor_literature.py) before building the wheel."
        )
    return directory


def _run_pyinstaller(launcher: Path, work: Path, stage: Path, literature: Path) -> None:
    modules = sorted(p.stem for p in literature.glob("*.py"))
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--log-level", "WARN",
        "--onedir", "--console", "--name", "caterva",
        "--workpath", str(work / "build"),
        "--distpath", str(stage),
        "--specpath", str(work),
        # --collect-all, not --collect-submodules: the two JSON files under
        # caterva/core/data/ and the enzyme index under caterva/enzymes/data/
        # are package data, and submodule collection alone would leave them
        # out of _internal/, failing the SBML export and enzyme-finder smokes.
        "--collect-all", "caterva",
    ]
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    # The literature layer is a directory of flat modules that
    # caterva.checkout imports through importlib, so the freezer sees no
    # import of them. Its files go in as data at caterva/_literature/ (the
    # directory checkout.py looks in; --collect-all does not take .py data),
    # and each module is a hidden import found through --paths, so the
    # libraries THEY import (bs4, httpx, requests, ...) are analysed too.
    cmd += ["--paths", str(literature)]
    for module in modules:
        cmd += ["--hidden-import", module]
    for source in sorted(literature.glob("*")):
        if source.is_file():
            cmd += ["--add-data", f"{source}{os.pathsep}caterva/_literature"]
    cmd.append(str(launcher))
    # cwd is the scratch directory so the checkout is never on the analysis path.
    subprocess.run(cmd, cwd=str(work), check=True)


def _exe(bundle: Path) -> Path:
    return bundle / ("caterva.exe" if platform.system() == "Windows" else "caterva")


def _prune(bundle: Path) -> list[str]:
    removed = []
    for rel in PRUNE:
        target = bundle / "_internal" / rel
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(rel)
    return removed


#: A binary that mentions libSBML this often has the library compiled in.
#: Measured: _roadrunner.so 20,582 mentions, libantimony.dylib 20,051,
#: _libsbml.*.so 7,902; numpy's largest extension 0.
_LIBSBML_MENTIONS = 1000
_LIBSBML_VERSION = re.compile(rb"\x00(5\.\d{1,2}\.\d{1,2})\x00")


def _libsbml_copies(bundle: Path) -> list[tuple[Path, str, bool]]:
    """Every binary in the folder that carries libSBML: (path, version, replaceable).

    python-libsbml's extension is the LGPL library as a separate, loadable,
    swappable file. libroadrunner's `_roadrunner` extension and Antimony's
    `libantimony` shared library each carry their OWN statically linked
    copy of libSBML (measured here: 5.20.4 and 5.20.2 against
    python-libsbml's 5.21.1), which a recipient cannot replace without
    rebuilding those libraries. NOTICE and README.txt must say all of this,
    so this function finds every copy rather than assuming one.
    """
    found = []
    for path in sorted((bundle / "_internal").rglob("*")):
        if not path.is_file() or path.suffix not in (".so", ".pyd", ".dylib", ".dll"):
            continue
        data = path.read_bytes()
        if len(re.findall(rb"libsbml", data, re.I)) < _LIBSBML_MENTIONS:
            continue
        versions = sorted({m.decode() for m in _LIBSBML_VERSION.findall(data)})
        version = versions[0] if len(versions) == 1 else "unknown (" + ", ".join(versions) + ")"
        replaceable = path.name.startswith("_libsbml")
        found.append((path, version, replaceable))
    if not any(r for _, _, r in found):
        _fail(f"python-libsbml's extension is not a separate file under _internal/; found {[(str(p), v) for p, v, _ in found]}")
    return found


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
        "Caterva itself: ../LICENSE (Apache-2.0). What is conveyed and under",
        "which terms: ../NOTICE.",
        "",
    ]
    for dist_name in CONVEYED:
        files = _licence_files(dist_name)
        if dist_name == "caterva":
            # Caterva's LICENSE and NOTICE sit at the folder root, from the
            # installed wheel's dist-info, so they are the released texts.
            for f in files:
                shutil.copy2(f, bundle / f.name)
            if not ((bundle / "LICENSE").is_file() and (bundle / "NOTICE").is_file()):
                _fail("the installed caterva wheel does not declare LICENSE and NOTICE")
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
        copied = []
        for f in files:
            # numpy ships two files named LICENSE.txt (its own, carrying the
            # OpenBLAS and libgfortran notices, and one under licenses/);
            # a flat copy would overwrite the one NOTICE says is retained.
            info = next(parent for parent in f.parents if parent.name.endswith(".dist-info"))
            dest = target / f.relative_to(info)
            if dest.exists():
                _fail(f"{dist_name}: two licence files would land at {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied.append(dest.relative_to(bundle).as_posix())
        lines.append(f"{dist_name} {version}: " + ", ".join(copied))
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


def _first_run_text() -> str:
    system = platform.system()
    if system == "Darwin":
        return """FIRST RUN ON macOS
    This folder is not signed with an Apple Developer ID, so macOS quarantines
    every file in it after download and refuses the first run ("cannot be
    opened because the developer cannot be verified"). "Open Anyway" in
    System Settings approves ONE file and will not unblock the libraries under
    _internal/, so use this instead, once, from a terminal INSIDE this folder:

        xattr -dr com.apple.quarantine .

    (from the folder above it: xattr -dr com.apple.quarantine caterva/)
"""
    if system == "Windows":
        return """FIRST RUN ON WINDOWS
    This folder is not code-signed. Run it from a terminal (PowerShell or
    cmd) inside this folder as  .\\caterva.exe  -- PowerShell does not run a
    program from the current directory without the  .\\  prefix. If
    SmartScreen shows "Windows protected your PC", choose More info > Run
    anyway. Some antivirus products quarantine freshly built PyInstaller
    programs; if caterva.exe disappears after extraction, restore it from
    the quarantine and add an exclusion for this folder.
"""
    return ""


def _write_readme(bundle: Path, version: str, copies: list[tuple[Path, str, bool]], tag: str) -> None:
    windows = platform.system() == "Windows"
    exe = ".\\caterva.exe" if windows else "./caterva"
    rows = "\n".join(
        f"        {p.relative_to(bundle).as_posix():60s} libSBML {v}  "
        + ("separate file, replaceable" if r else "compiled into this library, not separately replaceable")
        for p, v, r in copies
    )
    text = f"""Caterva {version} ({tag})

Unaffiliated with Tellurium. See NOTICE.

WHAT TO TYPE FIRST (from a terminal, inside this folder)

    {exe} compose "a toggle switch between two repressors"

        Builds a model from the shape of a mechanism and reports on it.
        Read the VERDICT at the top -- what the model supports and the worst
        thing wrong with it -- then "Where the numbers come from", which
        says which constants are measurements and which are placeholders
        nobody measured.

    {exe} compose --shapes

        Every mechanism it can build, one line each. Describe any of them in
        your own words.

    {exe} compose "Michaelis-Menten with a competitive inhibitor" --design

        Which measurement to make next, and what it would newly pin down.

    {exe}
        the quick start, whenever you are lost
    {exe} compose --help
        every option on the model builder, with examples
    {exe} compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose
        The same model with measured constants from BRENDA, each cited
        (needs a network connection: see below).
    {exe} enzyme "pyruvate kinase"
        Which enzyme a name means: the EC number, and why.
    {exe} sim --help
        exact stochastic chemical kinetics (Gillespie SSA)
    {exe} studio --help
        the local window onto all of the above (the page is in the macOS
        app; this folder serves a "not built" page instead)

IT RECOGNISES A SHAPE, NEVER A SUBJECT
    "two genes repressing each other" builds. "glycolysis" does not, and
    says why: naming a pathway needs a pathway database, and guessing one
    would be worse than refusing. Most refusals you meet are this.

USEFUL FLAGS ON compose
    --screen        knock out every species in turn and rank the effects
    --robustness N  does the conclusion survive resampling the placeholders
    --scale         are the numbers going IN physically possible
    --predictions   are the numbers coming OUT physically possible
    --sweep PARAM   where the behaviour changes qualitatively
    --export FORMAT methods | csv | sbml | antimony, written to stdout
    --no-ranking    skip the slowest step when you just want the structure

Nothing is installed and nothing is written outside the directory you run it
in. No network connection is made, except when you ask for measured constants
(--subject, `caterva bind`, `caterva rates --ec`): those read BRENDA, NCBI
Taxonomy, UniProt and PubChem live, and the report says what could not be
reached rather than substituting a value.

The full guide, with worked examples, is docs/USING_CATERVA.md in the
repository, and the release notes for this version are on the release page
you downloaded this from.

{_first_run_text()}
WHAT IS INSIDE, AND THE LGPL
    _internal/ holds the Python runtime, Caterva, and the libraries Caterva
    uses. libSBML (GNU LGPL v2.1) is in this folder {len(copies)} times:

{rows}

    The python-libsbml copy is one separate file loaded at run time; you may
    replace it with your own interface-compatible build of python-libsbml
    for this Python version and platform by putting the new file at the same
    path. The other copies are compiled into libroadrunner and Antimony by
    their upstream projects and cannot be swapped without rebuilding those
    libraries; the corresponding source for every version listed above is
    attached to the release page this folder came from, beside this archive
    (libsbml-<version>-source.tar.gz, and the roadrunner and antimony
    sources), and at https://github.com/sbmlteam/libsbml/releases.
    libSBML's own terms and the LGPL text are in licenses/python-libsbml/.
    Every other component's licence is in licenses/ too, listed in
    licenses/README.txt.

THE LITERATURE SEARCH
    _internal/caterva/_literature/ holds the resolvers that read BRENDA and
    rank what they find (copies of the repository's Tests/ modules, made by
    the release build). BRENDA's data is licensed CC BY 4.0 (Chang et al.
    2021, Nucleic Acids Res. 49:D498, doi:10.1093/nar/gkaa1025); NOTICE gives
    the attribution. No recorded answer is in this folder: every lookup is
    live.
"""
    (bundle / "README.txt").write_text(text, encoding="utf-8")


def _smoke(bundle: Path, version: str, require_studio_page: bool = False) -> None:
    exe = _exe(bundle)
    if not exe.is_file():
        _fail(f"executable missing: {exe}")
    with tempfile.TemporaryDirectory(prefix="caterva-smoke-") as empty:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        # The report contains non-ASCII (em dashes, degree signs). On Windows
        # the frozen program writes them in the console code page unless
        # told otherwise, and reading that as UTF-8 raised inside
        # subprocess's reader thread and returned stdout=None (rc.2, the
        # Windows leg). So: ask the child for UTF-8, and decode what comes
        # back leniently. Every marker checked below is ASCII.
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        def run(*args: str, timeout: int = 900, extra_env: dict | None = None) -> subprocess.CompletedProcess:
            raw = subprocess.run([str(exe), *args], cwd=empty, env={**env, **(extra_env or {})},
                                 capture_output=True, timeout=timeout)
            return subprocess.CompletedProcess(
                raw.args, raw.returncode,
                raw.stdout.decode("utf-8", errors="replace"),
                raw.stderr.decode("utf-8", errors="replace"),
            )

        r = run("--version", timeout=120)
        if r.returncode != 0 or r.stdout.strip() != f"caterva {version}":
            _fail(f"--version: exit {r.returncode}, stdout {r.stdout!r}, stderr {r.stderr[-400:]!r}")
        # `sim` is the Gillespie engine only (the population-genetics domains
        # were archived), so its help names the one subcommand, `ssa`.
        r = run("sim", "--help", timeout=300)
        if r.returncode != 0 or "ssa" not in r.stdout or "Gillespie" not in r.stdout:
            _fail(f"sim --help: exit {r.returncode}, stdout {r.stdout[-300:]!r}, stderr {r.stderr[-400:]!r}")
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
            # The enzyme finder reads a packaged data file and nothing else:
            # a folder missing it would resolve no name.
            (("enzyme", "pyruvate kinase"), ("EC 2.7.1.40", "Resolved:")),
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
        print("smoke  : --version, sim --help, a simulated time course, an SBML export, an")
        print("         expansion-library shape and an enzyme-name lookup all ran from an empty directory")

        _literature_smoke(run, bundle)

        r = run("studio", "--self-test", timeout=300)
        problems = studio_self_test_problems(r.returncode, r.stdout, require_studio_page)
        if problems:
            _fail(
                "caterva studio --self-test: " + "; ".join(problems)
                + f"; stdout {r.stdout[-1200:]!r}, stderr {r.stderr[-1200:]!r}"
            )
        for line in r.stdout.strip().splitlines():
            print(f"studio : {line}")


#: What the offline literature check must find in the report, and must not.
LITERATURE_MARKERS = ("VERDICT:", "2 of 2 constant(s) came from the literature", "BRENDA ref 641068", "BRENDA ref 739603")
LITERATURE_REFUSAL = "could not run"


def literature_problem(bundle: Path) -> str | None:
    """Why the folder lacks the literature layer's files, or None."""
    directory = bundle / "_internal" / "caterva" / "_literature"
    needed = ("fallback_logic.py", "brenda_client.py", "http_retry.py", "enzyme_lookup.py", "cite.py", "report_lab.py")
    missing = [name for name in needed if not (directory / name).is_file()]
    if missing:
        return f"_internal/caterva/_literature/ lacks {missing}: the folder cannot run a literature search"
    return None


def _literature_smoke(run, bundle: Path) -> None:
    """The headline feature, run from the frozen folder, offline."""
    problem = literature_problem(bundle)
    if problem:
        _fail(problem)
    page = RECORDED / "brenda_2.7.1.1.html.gz"
    if not page.is_file() or not (RECORDED / "http").is_dir():
        _fail(f"the recorded answers the literature check replays are not at {RECORDED}; run this script from a checkout of the tagged commit")
    replay = {
        "CATERVA_BRENDA_RECORDED": str(RECORDED),
        "CATERVA_HTTP_RECORDED": str(RECORDED / "http"),
        "NO_PROXY": "", "no_proxy": "",
        **{name: CLOSED_PROXY for name in PROXY_VARIABLES},
    }
    args = ("compose", "Michaelis Menten", "--subject", "2.7.1.1", "--organism", "human",
            "--substrate", "glucose", "--no-ranking")
    r = run(*args, extra_env=replay)
    missing = [m for m in LITERATURE_MARKERS if m not in r.stdout]
    if r.returncode != 0 or missing or LITERATURE_REFUSAL in r.stdout:
        _fail(
            f"{' '.join(args)} (offline, recorded BRENDA page): exit {r.returncode}, missing {missing}, "
            f"'{LITERATURE_REFUSAL}' present: {LITERATURE_REFUSAL in r.stdout}; "
            f"stdout tail {r.stdout[-400:]!r}, stderr {r.stderr[-600:]!r}"
        )
    print("smoke  : compose --subject 2.7.1.1 ran the literature search from the frozen folder, offline,")
    print("         and cited BRENDA ref 641068 and 739603 for the constants")


#: Where the studio's built page lands inside a onedir folder: PyInstaller's
#: `--collect-all caterva` copies the installed package's data files there.
STUDIO_PAGE = Path("_internal") / "caterva" / "studio" / "static" / "index.html"
#: What the built page carries until the server writes the session token in
#: (caterva.studio.contract.TOKEN_PLACEHOLDER; read as text, not imported,
#: so this script needs nothing but the standard library).
TOKEN_PLACEHOLDER = "__CATERVA_SESSION_TOKEN__"


def studio_page_problem(bundle: Path) -> str | None:
    """Why the folder does not carry the studio's built page, or None."""
    page = bundle / STUDIO_PAGE
    if not page.is_file():
        return (f"{STUDIO_PAGE.as_posix()} is missing: the installed wheel was built without the page "
                "(build it first: pnpm --filter @workspace/caterva-studio run build, from Science-Agent-Pipeline/)")
    if TOKEN_PLACEHOLDER not in page.read_text(encoding="utf-8", errors="replace"):
        return f"{STUDIO_PAGE.as_posix()} has no {TOKEN_PLACEHOLDER} to replace: it is not the studio's built page"
    if not any((page.parent / "assets").glob("*.js")):
        return f"{STUDIO_PAGE.as_posix()} is there but static/assets/ holds no script"
    if not (page.parent / "licenses" / "THIRD-PARTY-NOTICES.txt").is_file():
        return (f"{STUDIO_PAGE.parent.as_posix()}/licenses/THIRD-PARTY-NOTICES.txt is missing: the page's packages "
                "would be conveyed without their licences (the page build writes it)")
    return None


def studio_self_test_problems(returncode: int, stdout: str, require_page: bool) -> list[str]:
    """What is wrong with one run of `caterva studio --self-test`, or [].

    The self-test prints one line per check, `ok   ...` or `FAIL ...`
    (caterva/studio/__main__.py), and exits 0 only when all passed. Both are
    read: an exit status alone would pass a self-test that checked nothing.
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    problems = []
    if returncode != 0:
        problems.append(f"exit {returncode}")
    failed = [line for line in lines if line.startswith("FAIL")]
    if failed:
        problems.append("failed checks: " + " | ".join(failed))
    if not any(line.startswith("ok") and "/api/health" in line for line in lines):
        problems.append("no passing /api/health check was reported")
    if not any(line.startswith("ok") and line[2:].lstrip().startswith("/:") for line in lines):
        problems.append("no passing check of / was reported")
    if require_page and "not built" in stdout:
        problems.append("the server served its not-built page; this folder must carry the built page")
    return problems


def _archive(bundle: Path, out_dir: Path, version: str, tag: str) -> Path:
    if platform.system() == "Windows":
        archive = out_dir / f"caterva-{version}-{tag}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(bundle.rglob("*")):
                zf.write(path, Path("caterva") / path.relative_to(bundle))
    else:
        archive = out_dir / f"caterva-{version}-{tag}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(bundle, arcname="caterva")
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
    parser.add_argument("--keep-folder", metavar="DIR",
                        help="also copy the checked folder to DIR/caterva (scripts/build_studio_app.py reads it)")
    parser.add_argument("--require-studio-page", action="store_true",
                        help="refuse a folder without the studio's built page (the DMG build passes this)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        importlib.import_module("PyInstaller")
    except ImportError:
        _fail("PyInstaller is not installed in this interpreter (pip install pyinstaller)")
    caterva = _installed_caterva()
    version = caterva.__version__
    tag = _platform_tag()

    with tempfile.TemporaryDirectory(prefix="caterva-app-") as tmp:
        work = Path(tmp)
        launcher = work / "caterva_launcher.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        stage = work / "stage"
        _run_pyinstaller(launcher, work, stage, _literature_dir(caterva))
        bundle = stage / "caterva"
        if not bundle.is_dir():
            _fail(f"PyInstaller did not produce {bundle}")

        pruned = _prune(bundle)
        copies = _libsbml_copies(bundle)
        _write_licences(bundle)
        _write_readme(bundle, version, copies, tag)
        if args.require_studio_page:
            problem = studio_page_problem(bundle)
            if problem:
                _fail(problem)
        _smoke(bundle, version, require_studio_page=args.require_studio_page)
        if args.keep_folder:
            kept = Path(args.keep_folder).resolve() / "caterva"
            if kept.exists():
                shutil.rmtree(kept)
            kept.parent.mkdir(parents=True, exist_ok=True)
            # symlinks=True: PyInstaller's macOS folder links Python.framework's
            # members, and following them would duplicate the runtime.
            shutil.copytree(bundle, kept, symlinks=True)
            print(f"kept   : {kept}")

        archive = _archive(bundle, out_dir, version, tag)
        size = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
        copy_lines = [f"{p.relative_to(bundle).as_posix()}\t{v}\t{'replaceable' if r else 'embedded'}" for p, v, r in copies]

    digest = _sha256(archive)
    (out_dir / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    # The publish job attaches the corresponding source for every libSBML
    # version any folder carries; this is how it learns which.
    (out_dir / f"libsbml-copies-{tag}.tsv").write_text("\n".join(copy_lines) + "\n", encoding="utf-8")
    print(f"folder : {size / 1e6:.0f} MB unpacked; pruned {pruned or 'nothing'}")
    for line in copy_lines:
        print(f"libsbml: {line}")
    print(f"archive: {archive}")
    print(f"sha256 : {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
