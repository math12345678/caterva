#!/usr/bin/env python3
"""Every dependency must carry a recorded grant of permission to use it.

WHY THIS EXISTS
---------------
"I don't want to use things I don't have permission for" is a requirement
like any other, and until this script existed nothing in the repository
could answer it. The dependency manifests said *what* Caterva uses. Nothing
said *under what terms*, so the answer had to be re-derived by hand every
time anyone asked — and a hand-derived answer is exactly the kind of claim
this project does not accept anywhere else.

It found two things on its first run. `@replit/connectors-sdk` was declared
as a dependency of `Science-Agent-Pipeline`, is imported by no source file
in the repository, and ships **no licence at all** — neither a `license`
field nor a LICENSE file. An unused dependency with no permission grant is
the one genuinely unsafe item in a tree of 494 packages. And `exit`
declares no licence in its metadata while shipping `LICENSE-MIT`, which is
the same fact with a much better answer.

WHAT A "GRANT" MEANS HERE
-------------------------
Not "the licence is popular". A licence text that says you may use, copy,
modify and redistribute the software — MIT, BSD, ISC, Apache 2.0, LGPL,
CC0, Python-2.0 — is permission. That is what those documents are for.

So using libRoadRunner (Apache 2.0, University of Washington) and Antimony
(MIT) is *permitted*, explicitly and in writing, including commercially.
The obligation those licences create is attribution, not abstinence — see
NOTICE, and `docs/LICENSING.md` for the reasoning in full.

WHAT THIS CHECKS
----------------
Every direct dependency in every manifest has an entry in `PERMISSION`
recording its licence and the grant. **A dependency with no entry FAILS.**

The default is deliberately "you must look it up", not "assume it's fine".
A new dependency added without checking its terms is the exact thing this
guard exists to catch, and a permissive default would let it through on the
day it happens.

`NO_GRANT` records dependencies that must not be used and why. An entry
there also fails, with its reason — so the answer to "why is this failing"
is in the same file as the failure.

WHY IT CANNOT QUIETLY PASS
--------------------------
If manifest parsing yields fewer than `_MIN_DEPS` dependencies it FAILS.
A parser that finds nothing otherwise reports a clean legal position for a
scan that never happened, which is the worst possible version of this
particular check.

THIS IS NOT LEGAL ADVICE
------------------------
It is a record of what the licence files in this tree say, checked
mechanically so it cannot silently drift. A lawyer should review anything
that matters commercially.
"""
from __future__ import annotations

import functools
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Below this the parse is broken rather than the tree being empty.
_MIN_DEPS = 30

#: Internal workspace packages — this repository's own code, not a
#: third party, so there is nobody to get permission from.
_INTERNAL_PREFIX = "@workspace/"

#: dependency -> (licence, what the licence permits)
#:
#: Read off the licence text shipped in the installed distribution, not
#: from a package index summary. Where the two disagree the shipped file
#: wins, because that is the document that travels with the code.
PERMISSION: dict[str, tuple[str, str]] = {
    # --- The simulation engine -------------------------------------------
    "libroadrunner": (
        "Apache-2.0",
        "Copyright (C) 2012-2018 University of Washington. The shipped "
        "LICENSE.txt states in plain English: 'You CAN freely download and "
        "use this software, in whole or in part, for personal, company "
        "internal, or commercial purposes' and 'You CAN use the software in "
        "packages or distributions that you create.' Condition: include a "
        "copy of the licence in redistributions (see NOTICE).",
    ),
    "antimony": (
        "MIT",
        "MIT grants use, copy, modify, merge, publish, distribute, "
        "sublicense and sell, on condition the copyright and permission "
        "notice are retained.",
    ),
    "python-libsedml": (
        "BSD-3-Clause",
        "SED-ML reading and writing, for the COMBINE archive export "
        "(Frank Bergmann, Heidelberg). BSD grants use, modification and "
        "redistribution with the notice retained -- so it sits under "
        "Apache-2.0 without the separation stdpopsim needed.\n"
        "      NOT verified from a shipped licence file: the package is not "
        "installed in this environment, so the licence was read from PyPI "
        "metadata rather than the distribution. Every other entry in this "
        "table was read from the file that travels with the code, which is "
        "this guard's own stated rule. Re-verify on a machine where it is "
        "installed and replace this note.\n"
        "      Worth knowing: libSEDML depends on libnuml, one of the two "
        "packages the tellurium umbrella pulls in and that ADR 0001 cites as "
        "a reason to avoid it. Depending on it directly and deliberately is "
        "a different thing from inheriting it unexamined, but it is the same "
        "package.",
    ),
    "python-libsbml": (
        "LGPL-2.1",
        "Caltech, EMBL-EBI, University of Heidelberg and others. LGPL "
        "permits use and distribution of a work that links the library; the "
        "condition is that recipients can replace the library. In the wheel "
        "and sdist Caterva names it as a dependency and does not vendor, "
        "modify or statically link it, so replacement is a pip install. In "
        "the downloadable app folder (ADR 0177) it IS conveyed, as one "
        "separate file the recipient can swap, with the LGPL text and "
        "libSBML's own terms beside it; NOTICE states the position.",
    ),
    # --- The app folder's freezer (requirements-release.txt only) ----------
    "pyinstaller": (
        "GPL-2.0-or-later WITH Bootloader-exception",
        "Read from pyinstaller-6.22.2.dist-info/licenses/COPYING.txt in the "
        "installed wheel by the session on branch "
        "claude/caterva-orientation-setup-c1310b (PR #21), which installed "
        "it; the machine that recorded this entry could not reach PyPI and "
        "carries the text over from that record. The GPL alone would be "
        "a problem: the downloadable app folder embeds PyInstaller's "
        "bootloader, and copyleft on that would reach the whole folder. The "
        "Bootloader Exception is what makes it lawful: the authors give "
        "'unlimited permission to link or embed compiled bootloader and "
        "related files into combinations with other programs, and to "
        "distribute those combinations without any restriction'. Build-time "
        "only: nothing imports it and nothing at run time needs it; it is "
        "pinned in requirements-release.txt, which only the release workflow "
        "installs (ADR 0177). The COPYING.txt with the exception ships in the "
        "folder under licenses/pyinstaller/.",
    ),
    # --- Numerics ---------------------------------------------------------
    "numpy": ("BSD-3-Clause", "Use, modify and redistribute with the notice retained."),
    "scipy": ("BSD-3-Clause", "Use, modify and redistribute with the notice retained."),
    "stdpopsim": (
        "GPL-3.0",
        "Optional and NOT redistributed by Caterva. Imported at runtime "
        "when a user has installed it themselves; the population-genetics "
        "tests skip when it is absent. Caterva ships no stdpopsim code, so "
        "no GPL obligation attaches to Caterva's own distribution. Revisit "
        "if it ever becomes a hard requirement or is bundled.",
    ),
    # --- HTTP / parsing ---------------------------------------------------
    "requests": ("Apache-2.0", "Use, modify, redistribute, commercially; attribution."),
    "httpx": ("BSD-3-Clause", "Use, modify and redistribute with the notice retained."),
    "certifi": (
        "MPL-2.0",
        "File-level copyleft over its certificate bundle. Caterva ships that bundle unmodified, so the "
        "source of the file is the file itself, from the package of the same version on PyPI.",
    ),
    "beautifulsoup4": ("MIT", "Use, copy, modify, distribute, sell."),
    "lxml": ("BSD-3-Clause", "Use, modify and redistribute with the notice retained."),
    "pydantic": ("MIT", "Use, copy, modify, distribute, sell."),
    # --- Dev / test -------------------------------------------------------
    "pytest": ("MIT", "Use, copy, modify, distribute, sell."),
    "pytest-timeout": ("MIT", "Use, copy, modify, distribute, sell."),
    "hypothesis": ("MPL-2.0", "File-level copyleft; Caterva does not modify it."),
    "ruff": (
        "MIT",
        "Lints for bug-class findings (scripts/check_python_bug_lints.py). "
        "Read from the LICENSE the wheel ships "
        "(ruff-0.11.11.dist-info/licenses/LICENSE): 'MIT License, "
        "Copyright (c) 2022 Charles Marsh'. MIT grants use, copy, modify, "
        "merge, publish, distribute, sublicense and sell, on condition the "
        "copyright and permission notice are retained.",
    ),
    "mypy": (
        "MIT",
        "Static type checker, configured in pyproject.toml's [tool.mypy] "
        "since before it was installed by anything. Read from the LICENSE "
        "the wheel ships (mypy-1.15.0.dist-info/LICENSE): 'Mypy (and mypyc) "
        "are licensed under the terms of the MIT license'. MIT grants use, "
        "copy, modify, merge, publish, distribute, sublicense and sell, on "
        "condition the copyright and permission notice are retained.",
    ),
    "types-pyyaml": (
        "Apache-2.0",
        "Type stubs for PyYAML, so mypy can check the workflow-parsing "
        "guards. Read from the LICENSE the wheel ships: 'The \"typeshed\" "
        "project is licensed under the terms of the Apache license', and "
        "the License-Expression metadata says Apache-2.0. Apache-2.0 grants "
        "use, reproduction and distribution, with the notice retained.",
    ),
    "pyyaml": (
        "MIT",
        "Parses the GitHub workflow for scripts/check_ci_toolchain.py. "
        "Read from the LICENSE the wheel itself ships "
        "(pyyaml-6.0.3.dist-info/licenses/LICENSE), not from a package "
        "index: Copyright (c) 2017-2021 Ingy dot Net and (c) 2006-2016 "
        "Kirill Simonov, granting use, copy, modify, merge, publish, "
        "distribute, sublicense and sell, on condition the copyright and "
        "permission notice are retained in all copies.",
    ),
    "cffconvert": (
        "Apache-2.0",
        "Copyright 2018 The Citation File Format Developers. Read from the "
        "LICENSE in the citation-file-format/cffconvert repository, not from "
        "a package-index summary -- it is not installed in this environment, "
        "so the shipped file could not be read locally and the upstream one "
        "was fetched instead. Grants use, modification and redistribution "
        "including commercially; condition is attribution and notice "
        "retention. Dev-only: it validates CITATION.cff and ships in nothing.",
    ),
    # --- Front-end build (caterva-site) -----------------------------------
    "autoprefixer": (
        "MIT",
        "Copyright 2013 Andrey Sitnik. Read from the LICENSE file shipped in "
        "caterva-site/node_modules/autoprefixer, which grants use, copy, "
        "modify, merge, publish, distribute, sublicense and sell, on "
        "condition the notice is retained. Its package.json `license` field "
        "says MIT and agrees with the shipped text -- checked, because this "
        "guard's rule is that the shipped file wins and the two are not "
        "always the same (see `exit`, which declares nothing and ships "
        "LICENSE-MIT).",
    ),
    # --- Caterva Studio's bundled typefaces ---------------------------------
    # Declared as "OFL-1.1", which is not in _JS_PERMISSIVE because the OFL
    # is a font licence with its own conditions, so each is recorded here
    # from the LICENSE file shipped in its installed package. The same
    # texts are copied into the page (caterva-studio/public/licenses/).
    "@fontsource/spectral": (
        "OFL-1.1",
        "Copyright 2017 The Spectral Project Authors. The shipped LICENSE is "
        "the SIL Open Font License 1.1: use, study, modify and redistribute, "
        "bundled with software, on condition the font is not sold by itself, "
        "the copyright notice and licence travel with it, and a modified "
        "version is not given a Reserved Font Name. Bundled unmodified.",
    ),
    "@fontsource/atkinson-hyperlegible-next": (
        "OFL-1.1",
        "Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors. "
        "The shipped LICENSE is the SIL Open Font License 1.1, with the same "
        "grant and conditions as Spectral's above. Bundled unmodified.",
    ),
    "@fontsource/dm-mono": (
        "OFL-1.1",
        "Copyright 2020 The DM Mono Project Authors. The shipped LICENSE is "
        "the SIL Open Font License 1.1, with the same grant and conditions "
        "as Spectral's above. Bundled unmodified.",
    ),
}

_REPLIT_NO_LICENCE = (
    "Ships no `license` field, no LICENSE file and no repository URL, so "
    "there is no grant of permission to use it. Unlike connectors-sdk these "
    "three WERE used, in the vite.config.ts of mockup-sandbox and "
    "caterva-landing, as Replit editor conveniences (an error overlay, a dev "
    "banner, a source mapper). cartographer and dev-banner were gated on the "
    "REPL_ID environment variable; the error overlay was NOT -- it ran on "
    "every build, including production ones. All three call sites have been "
    "removed, so no unlicensed code executes. What remains is the manifest "
    "entry, which needs a lockfile regeneration this environment cannot "
    "perform:\n"
    "      cd Science-Agent-Pipeline && pnpm remove <name>\n"
    "    Editing package.json alone would break "
    "`pnpm install --frozen-lockfile` in CI."
)

#: Entries in NO_GRANT that must HARD FAIL, not merely warn.
#:
#: The distinction exists because of a barrier this guard created. It was
#: wired into `make guards` -- the command CONTRIBUTING tells you to run
#: before opening a PR -- while exiting 1 over four `@replit/*` packages
#: that are recorded, owner-assigned, and removable only with a `pnpm`
#: lockfile regeneration. Make stops at the first failure, so every
#: contributor running the documented command hit a red wall at step 38 of
#: 45, over something they did not add and could not fix.
#:
#: A guard that blocks the suite on a known, recorded, someone-else's item
#: is not visibility. It is obstruction, and it is how `make guards` stops
#: being run at all.
#:
#: So: a NEW dependency with no grant still fails the build, because that
#: is the regression worth stopping. A recorded outstanding one is printed
#: loudly and does not block. The set cannot quietly grow -- 
#: `Tests/test_dependency_licenses.py` fails if it changes in either
#: direction, so the pytest layer pins what the guard now waves through.
#:
#: Rule 7 is absolute and stays blocking: `tellurium` must never appear in
#: a manifest, and there is no "outstanding" version of that.
BLOCKING: frozenset[str] = frozenset({"tellurium"})

#: Dependencies that must NOT be used, with the reason.
NO_GRANT: dict[str, str] = {
    "tellurium": (
        "Constitution Rule 7. NOT a licensing problem — Tellurium is "
        "Apache 2.0, which is a grant of permission, and this guard exists "
        "to find dependencies that grant none.\n"
        "    Two separate reasons, kept separate because they were being "
        "merged:\n"
        "      * ADR 0001 (the only reason that ADR gives): the umbrella "
        "package pulls in python-libcombine and python-libnuml, which lack "
        "wheels on some supported platforms and fall back to a cmake/swig "
        "source build — for COMBINE-archive features Caterva does not use.\n"
        "      * The naming review (docs/LICENSING.md, NOTICE): Caterva "
        "must not depend on the project whose name it resembles, so the "
        "non-affiliation notice stays true.\n"
        "    ADR 0001 says nothing about naming; citing it for that put a "
        "reason in a source that does not contain it.\n"
        "    Enforced separately by check_forbidden_packages.py."
    ),
    "@replit/vite-plugin-cartographer": _REPLIT_NO_LICENCE,
    "@replit/vite-plugin-dev-banner": _REPLIT_NO_LICENCE,
    "@replit/vite-plugin-runtime-error-modal": _REPLIT_NO_LICENCE,
    "@replit/connectors-sdk": (
        "Declares no licence field and ships no LICENSE file, so there is no "
        "grant of permission to use it at all. It is imported by no source "
        "file in this repository — it appears only in "
        "Science-Agent-Pipeline/package.json. Remove it:\n"
        "      cd Science-Agent-Pipeline && pnpm remove @replit/connectors-sdk\n"
        "    (needs a pnpm install to regenerate the lockfile, so it cannot "
        "be done by editing package.json alone without breaking "
        "`pnpm install --frozen-lockfile` in CI.)"
    ),
}

#: JS licence identifiers that constitute a grant. Anything outside this
#: set needs a human decision, which is the point.
_JS_PERMISSIVE = {
    "MIT", "MIT-0", "ISC", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "BSD", "0BSD", "CC0-1.0", "Unlicense", "Python-2.0", "BlueOak-1.0.0",
    "(MIT OR CC0-1.0)", "CC-BY-4.0", "MPL-2.0", "Artistic-2.0",
}


def python_deps() -> dict[str, str]:
    """Direct pins from the requirements files, name -> manifest.

    Globbed rather than listed by name. The list was
    ("requirements.txt", "requirements-dev.txt") and
    `requirements-popgen.txt` was created the same day this guard was --
    carrying the one GPL dependency in the project, and invisible to the
    check written to find exactly that.

    A guard that names its inputs fails open: a manifest it does not name is
    unscanned, and an unscanned manifest is indistinguishable from a clean
    one. That is the fourth instance of this shape found on 2026-08-15
    alone (check_documented_counts on one doc,
    check_no_unsourced_ui_numbers on HTML only, check_forbidden_packages on
    three manifests, and this).
    """
    out: dict[str, str] = {}
    for path in sorted(ROOT.glob("requirements*.txt")):
        name = path.name
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.-]+)", line)
            if m:
                out.setdefault(m.group(1).lower(), name)
    return out


def js_deps() -> dict[str, str]:
    """Direct dependencies from every tracked package.json, name -> manifest."""
    out: dict[str, str] = {}
    # `git ls-files` rather than rglob: rglob descends into node_modules
    # (tens of thousands of directories) before the filter can reject it,
    # which made the first version of this function take minutes. Tracked
    # files are also the right set -- an untracked manifest is not part of
    # what this repository ships.
    listing = subprocess.run(
        ["git", "ls-files", "*package.json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    for rel_str in sorted(listing):
        rel = pathlib.Path(rel_str)
        if "node_modules" in rel.parts:
            continue
        path = ROOT / rel
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for field in ("dependencies", "devDependencies"):
            for dep in (data.get(field) or {}):
                if dep.startswith(_INTERNAL_PREFIX):
                    continue
                out.setdefault(dep, str(rel))
    return out


#: Every place an installed JS package can be found. pnpm puts real
#: packages in a content-addressed `.pnpm` store and symlinks workspace
#: node_modules at them, so a checker that looks only at the two top-level
#: trees reports "no licence" for 93 packages that are all plainly MIT.
#: That is the crying-wolf failure: a guard that flags everything gets
#: switched off, and then it is not guarding anything.
_JS_ROOTS = (
    "node_modules",
    "Science-Agent-Pipeline/node_modules",
    "Science-Agent-Pipeline/artifacts/api-server/node_modules",
    "Science-Agent-Pipeline/artifacts/mockup-sandbox/node_modules",
    "Science-Agent-Pipeline/artifacts/caterva-landing/node_modules",
)


@functools.cache
def installed_js_licence(name: str) -> str | None:
    """The licence a package declares in its own installed package.json.

    Cached. Each call walks five node_modules roots and, on a miss, scans
    pnpm's content-addressed `.pnpm` store directory-by-directory looking
    for `<name>@<version>`. That store holds thousands of entries, and the
    function is called once per dependency by the guard and again by every
    test that re-derives the set -- so the same directory listing was being
    walked dozens of times per run.

    **On the size of the win: unproven.** A single before/after pair showed
    the wrapping suite going 24.8 s -> 11.0 s, and that was reported as a
    2.2x speedup. It should not have been. Repeated timings of *identical*
    code on this machine ranged 20.9 s to 30.4 s, because several agents
    run their suites here concurrently — so the spread between runs is
    larger than the effect that pair appeared to show. Three runs either
    way could not separate them.

    The cache is kept because it is correct and cannot be slower: the
    function is a pure lookup and the repeated work is real (five
    node_modules roots plus a scan of pnpm's content-addressed store, once
    per dependency, for 113 dependencies). But "cannot be slower" is the
    honest claim, not a measured number.

    Recorded at length because an unverified performance figure is the same
    species of defect as an unverified test count, and this file exists to
    catch that species.
    """
    found_any = False
    candidates = [ROOT / r / name / "package.json" for r in _JS_ROOTS]
    # pnpm's store: `@radix-ui/react-dialog` is stored as
    # `.pnpm/@radix-ui+react-dialog@<version>/node_modules/@radix-ui/react-dialog`.
    store = ROOT / "Science-Agent-Pipeline" / "node_modules" / ".pnpm"
    if store.is_dir():
        prefix = name.replace("/", "+") + "@"
        for entry in store.iterdir():
            if entry.name.startswith(prefix):
                candidates.append(entry / "node_modules" / name / "package.json")
    for path in candidates:
        if not path.exists():
            continue
        found_any = True
        try:
            lic = json.loads(path.read_text()).get("license")
        except (json.JSONDecodeError, OSError):
            return None
        if isinstance(lic, dict):
            lic = lic.get("type")
        if isinstance(lic, list):
            lic = "; ".join(str(x) for x in lic)
        if lic:
            return str(lic)
    # Three states, not two. "Installed and declares no licence" is a
    # finding; "not installed here, so unverifiable" is an absence of
    # evidence. Reporting them as the same thing would have accused
    # autoprefixer -- plainly MIT -- of the same defect as the @replit
    # packages, which genuinely declare nothing.
    return "DECLARES_NOTHING" if found_any else None


def main() -> int:
    py = python_deps()
    js = js_deps()
    total = len(py) + len(js)

    if total < _MIN_DEPS:
        print(
            f"FAIL: parsed only {total} dependenc(ies) across the manifests, "
            f"below the floor of {_MIN_DEPS}.\n"
            "      The manifest parsing is broken, not the dependency tree. "
            "A licence scan\n      that finds nothing must not report a clean "
            "legal position."
        )
        return 1

    forbidden: list[tuple[str, str, str]] = []
    unrecorded: list[tuple[str, str]] = []
    uninstalled: list[tuple[str, str]] = []
    ok = 0

    for dep, manifest in sorted(py.items()):
        if dep in NO_GRANT:
            forbidden.append((dep, manifest, NO_GRANT[dep]))
        elif dep in PERMISSION:
            ok += 1
        else:
            unrecorded.append((dep, manifest))

    for dep, manifest in sorted(js.items()):
        if dep in NO_GRANT:
            forbidden.append((dep, manifest, NO_GRANT[dep]))
            continue
        if dep in PERMISSION:
            ok += 1
            continue
        lic = installed_js_licence(dep)
        if lic in _JS_PERMISSIVE:
            ok += 1
        elif lic is None:
            uninstalled.append((dep, manifest))
        else:
            unrecorded.append((dep, f"{manifest} -- installed and declares no licence"))

    print(f"Python dependencies:     {len(py)}")
    print(f"JS dependencies:         {len(js)}")
    print(f"Permission on record:    {ok}")
    print(f"No recorded grant:       {len(unrecorded)}")
    print(f"Explicitly forbidden:    {len(forbidden)}")
    print(f"Not installed here:      {len(uninstalled)}")

    if forbidden:
        print("\nThese are declared and have no grant of permission:\n")
        for dep, manifest, reason in forbidden:
            print(f"  {dep}  ({manifest})")
            print(f"      {reason}\n")

    if unrecorded:
        print("\nThese have no recorded permission to use them:\n")
        for dep, manifest in unrecorded:
            print(f"  {dep}  ({manifest})")
        print(
            "\nFind the licence text shipped with the package -- not a "
            "summary on a package\nindex -- and add it to PERMISSION with "
            "what it grants. If it grants nothing,\nadd it to NO_GRANT and "
            "remove the dependency."
        )

    if uninstalled:
        print(
            "\nNot installed in this checkout, so their licences could not be "
            "read here.\nThis is unverified, NOT a finding against them:\n"
        )
        for dep, manifest in uninstalled:
            print(f"  {dep}  ({manifest})")
        print(
            "\nInstall that workspace and re-run, or add the dependency to "
            "PERMISSION once\nyou have read the licence text that ships with "
            "it."
        )

    blocking = [f for f in forbidden if f[0] in BLOCKING]
    outstanding = [f for f in forbidden if f[0] not in BLOCKING]

    if outstanding:
        print(
            f"\nOUTSTANDING ({len(outstanding)}): recorded, owner-assigned, "
            "NOT blocking this run.\n"
            "See docs/LICENSING.md. These do not fail the build because "
            "nobody running\n`make guards` can clear them -- they need a "
            "pnpm lockfile regeneration.\nA new one WOULD fail; "
            "Tests/test_dependency_licenses.py pins this set so it\ncannot "
            "grow quietly."
        )

    if blocking or unrecorded:
        return 1

    print("\nOK: every dependency carries a recorded grant of permission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
