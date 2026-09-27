#!/usr/bin/env python3
"""Diagnose a Caterva development environment that will not set up.

    python3 scripts/doctor.py        (or: make doctor)

Not the same job as `scripts/check_env.py`. check_env answers "does this
stack produce correct numbers" and to do that it has to import roadrunner --
so it cannot say anything at all about an environment where the import is
the thing that is broken. That is exactly the environment a new contributor
has. doctor runs on a bare interpreter, imports nothing that is not in the
standard library, and inspects the venv from the outside via subprocess, so
it still works when the venv is empty, half-installed, or pointing at a
Python that has been uninstalled.

Two rules this script holds itself to:

1. **Report what was checked, not just the verdict.** A tool that prints
   "environment OK" has told you nothing about its coverage. Every check
   below prints the value it found -- the interpreter path, the version
   string, the wheel that is missing -- so a wrong PASS is visible as a
   wrong value rather than hiding behind a green word.

2. **Name the fix, not the symptom.** "No module named pytest" is accurate
   and useless. Each FAIL carries the command that resolves it.

Exit codes: 0 when nothing is broken (warnings still exit 0, as in
check_env.py), 1 when something will stop `make test` from running.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV = REPO_ROOT / ".venv"

# The supported window, stated once. Kept in step with the Makefile gate,
# requirements.txt, README.md and CONTRIBUTING.md by
# scripts/check_python_support_claim.py.
SUPPORTED_MINORS = (10, 11, 12, 13)

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
)
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = DIM = RESET = ""

checked: list = []   # (name, status, detail) for every check that ran
problems: list = []  # (name, fix) for the FAILs only


def _record(name, status, detail, fix=None):
    colour = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}[status]
    checked.append((name, status, detail))
    print("  {}{:<4}{}  {:<26} {}".format(colour, status, RESET, name, detail))
    if fix:
        print("        {}fix: {}{}".format(DIM, fix, RESET))
    if status == "FAIL":
        problems.append((name, fix or ""))


def _run(argv, timeout=30):
    """Return (returncode, stdout+stderr). Never raises."""
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()


def _interpreter_version(python):
    """(major, minor, micro) for another interpreter, or None if it will not run."""
    code, out = _run([
        str(python), "-c",
        "import sys;print('%d %d %d' % sys.version_info[:3])",
    ])
    if code != 0:
        return None
    try:
        return tuple(int(part) for part in out.split()[:3])
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 1. Platform
# --------------------------------------------------------------------------

def check_platform():
    print("\nPlatform")
    system = platform.system()
    machine = platform.machine()
    _record("operating system", "PASS", "{} {} ({})".format(
        system, platform.release(), machine))

    # Not a style preference: the Makefile's interpreter resolver is POSIX
    # shell (`command -v`, shell functions) and every recipe uses
    # .venv/bin/..., which a Windows venv spells .venv\Scripts\. `make` is
    # also not present on a stock Windows install. WSL2 and the Dev
    # Container are the two routes that are actually exercised.
    if os.name == "nt":
        _record(
            "make support", "FAIL", "native Windows: the Makefile is POSIX shell",
            "use WSL2 (`wsl --install`, then run make inside it) or the Dev "
            "Container; see CONTRIBUTING.md 'Windows'",
        )
    else:
        _record("make", "PASS" if shutil.which("make") else "FAIL",
                shutil.which("make") or "not on PATH",
                None if shutil.which("make")
                else "install make (macOS: xcode-select --install; "
                     "Debian/Ubuntu: apt install make)")

    _record("git", "PASS" if shutil.which("git") else "WARN",
            shutil.which("git") or "not on PATH")


# --------------------------------------------------------------------------
# 2. Interpreters on PATH
# --------------------------------------------------------------------------

def check_interpreters():
    print("\nPython interpreters on PATH")
    found_supported = False
    seen_any = False
    for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        path = shutil.which(name)
        if path is None:
            continue
        seen_any = True
        version = _interpreter_version(path)
        if version is None:
            _record(name, "WARN", "{} does not run".format(path))
            continue
        text = "{} ({}.{}.{})".format(path, *version)
        if version[0] == 3 and version[1] in SUPPORTED_MINORS:
            found_supported = True
            _record(name, "PASS", text)
        else:
            _record(name, "WARN", text + " -- outside 3.10-3.13")

    if not seen_any:
        _record("supported interpreter", "FAIL", "no python3* found on PATH",
                "install Python 3.13 (or 3.10-3.12)")
    elif not found_supported:
        # The window is set by libroadrunner 2.8.0 and numpy 2.2.6, the only
        # pins whose wheels stop at cp313. It is not about SBML -- see ADR 0014.
        _record("supported interpreter", "FAIL",
                "nothing on PATH is Python 3.10-3.13",
                "install python3.13; libroadrunner 2.8.0 and numpy 2.2.6 "
                "publish no wheels outside cp310-cp313")
    return found_supported


# --------------------------------------------------------------------------
# 3. The project venv
# --------------------------------------------------------------------------

def check_venv():
    """Return the venv interpreter to interrogate, or None."""
    print("\nProject virtualenv (.venv)")
    if not VENV.is_dir():
        # Not automatically a problem: the Dev Container and CI both install
        # into the system interpreter and have no .venv at all. Whether that
        # is fine is decided by the package section below, not here, so this
        # reports the fact and does not prescribe `make setup`.
        _record(".venv", "WARN", "absent -- reading packages from {}".format(
            sys.executable))
        return None

    # Windows venvs use Scripts\; checking both keeps the diagnosis honest
    # about which layout is present rather than reporting a missing venv.
    candidates = [VENV / "bin" / "python", VENV / "Scripts" / "python.exe"]
    interpreter = next((c for c in candidates if c.exists()), None)
    if interpreter is None:
        _record(".venv", "FAIL", "{} exists but has no interpreter".format(VENV),
                "rm -rf .venv && make setup")
        return None

    version = _interpreter_version(interpreter)
    if version is None:
        # A venv's python is a symlink. Move or upgrade the interpreter it
        # points at and the symlink dangles: the directory still looks fine
        # to `ls`, and every command inside it fails.
        home = ""
        cfg = VENV / "pyvenv.cfg"
        if cfg.exists():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("home ="):
                    home = " (built from {})".format(line.split("=", 1)[1].strip())
        _record(".venv interpreter", "FAIL",
                "{} will not run{}".format(interpreter, home),
                "rm -rf .venv && make setup")
        return None

    status = "PASS" if version[0] == 3 and version[1] in SUPPORTED_MINORS else "FAIL"
    _record(".venv interpreter", status,
            "{} ({}.{}.{})".format(interpreter, *version),
            None if status == "PASS"
            else "rm -rf .venv && CATERVA_PYTHON=$(command -v python3.13) make setup")
    return interpreter


def check_hidden_pth():
    """Catch the macOS + iCloud failure that makes `caterva` vanish.

    WHY THIS EXISTS (2026-09-24)
    ----------------------------
    `make setup` installs Caterva in editable mode, which works through a
    `.pth` file in site-packages. Python 3.13's `site.py` skips any `.pth`
    file carrying the macOS `hidden` flag, deliberately. When the checkout
    lives under ~/Desktop or ~/Documents with iCloud Drive's "Desktop &
    Documents" sync on, iCloud sets that flag on files inside `.venv`.

    Measured on the owner's machine: `caterva --version` worked immediately
    after install; minutes later the same command from outside the
    repository failed with `ModuleNotFoundError: No module named 'caterva'`.
    Both `.pth` files had acquired the flag. Clearing it restored the
    command, including the full literature search. Nothing in the error
    points anywhere near iCloud, which is why this check names it.
    """
    print("\nHidden .pth files (macOS + iCloud)")
    if sys.platform != "darwin":
        _record("hidden .pth", "PASS", "not macOS; the flag does not exist here")
        return
    found = sorted(VENV.glob("lib/python*/site-packages/*.pth")) if VENV.is_dir() else []
    if not found:
        _record("hidden .pth", "PASS", "no .pth files in .venv to check")
        return
    import stat

    hidden = [p for p in found if getattr(p.lstat(), "st_flags", 0) & stat.UF_HIDDEN]
    if not hidden:
        _record("hidden .pth", "PASS", "{} .pth file(s), none hidden".format(len(found)))
        return
    icloud = any(part in ("Desktop", "Documents") for part in REPO_ROOT.parts)
    _record(
        "hidden .pth", "FAIL",
        "{} of {} .pth file(s) carry the macOS hidden flag, so Python skips "
        "them and `caterva` cannot find its own package{}".format(
            len(hidden), len(found),
            " -- this checkout is under ~/{}, which iCloud Drive syncs".format(
                next(part for part in REPO_ROOT.parts if part in ("Desktop", "Documents")))
            if icloud else ""),
        "chflags nohidden .venv/lib/python*/site-packages/*.pth   "
        "(and move the checkout out of iCloud, or it will come back: "
        "see docs/OWNER_CHECKLIST.md)",
    )


# --------------------------------------------------------------------------
# 4. Packages
# --------------------------------------------------------------------------

#: (import name, what breaks without it, is it fatal to `make test`)
CORE = [
    ("roadrunner", "ODE integration", True),
    ("antimony", "model definition -> SBML", True),
    ("libsbml", "SBML validation", True),
    ("numpy", "numerics", True),
    ("scipy", "independent reference integrator", True),
    ("pytest", "test runner", True),
    ("hypothesis", "property-based tests", True),
]


#: import name -> distribution name, where they differ.
DISTRIBUTION = {
    "roadrunner": "libroadrunner",
    "libsbml": "python-libsbml",
}


def _pins():
    """version pinned in requirements*.txt, keyed by import name.

    A version that merely imports is not the version this project is tested
    against. CONTRIBUTING.md's worked example is the eigenvector-sign bug:
    LAPACK chose different signs across numpy builds, producing silent NaN
    rather than an exception, so the suite passed under one build and failed
    deterministically under another. "installed" and "the pinned version"
    are different facts and this reports both.
    """
    found = {}
    reverse = {dist: name for name, dist in DISTRIBUTION.items()}
    for filename in ("requirements.txt", "requirements-dev.txt"):
        path = REPO_ROOT / filename
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if "==" not in line or line.startswith("-"):
                continue
            dist, _, version = line.partition("==")
            dist = dist.strip()
            found[reverse.get(dist, dist)] = version.strip()
    return found


def check_packages(interpreter):
    """Query the venv from outside, so a broken venv is still describable."""
    target = interpreter or Path(sys.executable)
    where = "in .venv" if interpreter else "in {} (no venv)".format(sys.executable)
    print("\nPython packages ({})".format(where))

    probe = (
        "import importlib\n"
        "for name in {!r}:\n"
        "    try:\n"
        "        m = importlib.import_module(name)\n"
        "        print(name, getattr(m, '__version__', '?'))\n"
        "    except Exception as exc:\n"
        "        print(name, 'MISSING', type(exc).__name__)\n"
    ).format([name for name, _, _ in CORE])

    code, out = _run([str(target), "-c", probe], timeout=180)
    if code != 0:
        _record("package probe", "FAIL", "could not run {}: {}".format(target, out),
                "rm -rf .venv && make setup")
        return

    versions = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            versions[parts[0]] = parts[1]

    pinned = _pins()
    for name, role, fatal in CORE:
        value = versions.get(name, "MISSING")
        if value == "MISSING":
            _record(name, "FAIL" if fatal else "WARN",
                    "not importable -- {} unavailable".format(role),
                    "make setup   (installs requirements-dev.txt)")
        elif name in pinned and value != pinned[name]:
            _record(name, "WARN",
                    "{} installed, {} pinned -- {}".format(
                        value, pinned[name], role),
                    "{} -m pip install -r requirements-dev.txt".format(target))
        else:
            _record(name, "PASS", "{}  {}".format(value, role))


def check_stdpopsim(interpreter):
    """stdpopsim is pinned but is the one dependency that genuinely may not install.

    It is not optional in principle -- Tests/popgen_resolver.py gets its
    mutation rates from it -- but msprime, its C-extension dependency,
    publishes wheels only for manylinux x86_64, macOS and win_amd64. On
    Linux aarch64 there is no wheel for any msprime version, so pip builds
    the sdist and needs GSL. That is the whole of the "needs libgsl-dev"
    story, and stating the architecture is the difference between a fix and
    a shrug: on x86_64 a missing stdpopsim means `pip install stdpopsim`,
    on arm64 it means installing system packages first.
    """
    print("\nPopulation-genetics resolver (stdpopsim)")
    target = interpreter or Path(sys.executable)
    code, out = _run([
        str(target), "-c",
        "import stdpopsim;print(getattr(stdpopsim,'__version__','?'))",
    ], timeout=120)

    if code == 0:
        _record("stdpopsim", "PASS", out.splitlines()[-1] if out else "installed")
        return

    arm_linux = platform.system() == "Linux" and platform.machine() in (
        "aarch64", "arm64")
    if arm_linux:
        fix = ("apt install build-essential libgsl-dev, then "
               "pip install stdpopsim -- msprime has no linux/aarch64 wheel, "
               "so it is built from source here")
    else:
        fix = "pip install stdpopsim"
    _record("stdpopsim", "WARN",
            "not importable -- 19 tests in Tests/test_popgen_resolver.py "
            "will skip", fix)

    # Only worth reporting where the source build is what actually happens.
    if arm_linux:
        gsl = shutil.which("gsl-config")
        _record("libgsl", "PASS" if gsl else "WARN",
                gsl or "gsl-config not on PATH (needed to build msprime here)")


# --------------------------------------------------------------------------
# 5. Node toolchain
# --------------------------------------------------------------------------

def check_node():
    """The Python suites do not need Node; the documented pre-PR command does.

    `python scripts/verify_build.py --quick` runs
    check_typescript_compiles.py, which shells out to `npx tsc` and fails
    when npx is missing. Someone who set up only Python gets a red guard
    with no obvious connection to Node, so it is checked here by name.
    """
    print("\nNode toolchain (needed by verify_build.py --quick, not by make test)")
    node = shutil.which("node")
    if node is None:
        _record("node", "WARN", "not on PATH",
                "install Node 22 (CI uses 22) -- only needed for the "
                "TypeScript guards")
        return

    _, version = _run([node, "--version"])
    major = 0
    if version.startswith("v"):
        try:
            major = int(version[1:].split(".")[0])
        except ValueError:
            major = 0
    _record("node", "PASS" if major >= 18 else "WARN",
            "{} ({})".format(version, node),
            None if major >= 18 else "Node 18+ required; CI uses 22")

    npx = shutil.which("npx")
    _record("npx", "PASS" if npx else "WARN", npx or "not on PATH")

    # check_typescript_compiles refuses to trust an npx that would download
    # a compiler on the fly, so a missing local typescript is a real gap.
    ts = REPO_ROOT / "node_modules" / "typescript"
    _record("node_modules/typescript", "PASS" if ts.is_dir() else "WARN",
            "present" if ts.is_dir() else "absent",
            None if ts.is_dir() else "npm install")

    # The api-server suite in CI is a pnpm workspace; absent, only that
    # suite is unavailable.
    pnpm = shutil.which("pnpm")
    _record("pnpm", "PASS" if pnpm else "WARN",
            pnpm or "not on PATH (only Science-Agent-Pipeline needs it)",
            None if pnpm else "corepack prepare pnpm@11.4.0 --activate")


# --------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Caterva environment doctor")
    print("=" * 70)

    check_platform()
    check_interpreters()
    interpreter = check_venv()
    check_hidden_pth()
    check_packages(interpreter)
    check_stdpopsim(interpreter)
    check_node()

    passes = sum(1 for _, status, _ in checked if status == "PASS")
    warns = sum(1 for _, status, _ in checked if status == "WARN")

    print("\n" + "=" * 70)
    print("Checked {} things: {} ok, {} warning(s), {} problem(s).".format(
        len(checked), passes, warns, len(problems)))
    print("Checked: " + ", ".join(name for name, _, _ in checked))

    if problems:
        print("\n{}These will stop `make test` from running:{}".format(RED, RESET))
        for index, (name, fix) in enumerate(problems, start=1):
            print("  {}. {}".format(index, name))
            if fix:
                print("     -> {}".format(fix))
        return 1

    if warns:
        print("\n{}Nothing is broken.{} The warnings above are things that are "
              "absent,\nnot things that are wrong -- each says what it costs "
              "you.".format(GREEN, RESET))
        return 0

    print("\n{}Everything checked is present and working.{} "
          "Next: make check && make test".format(GREEN, RESET))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
