#!/usr/bin/env python3
"""Every file that names a licence must name the same one.

WHY THIS EXISTS
---------------
For months this repository said three different things about its own terms:

    LICENSE       "all rights reserved, no permission granted to copy"
    CITATION.cff  license: LicenseRef-Caterva-Proprietary
    package.json  "license": "MIT"

Nobody noticed, because nothing read more than one of them at a time. A
project whose entire claim is that every number is traceable to a source was
shipping a contradiction about the one fact a user checks first.

It surfaced only because a BRENDA curator linked the CC BY licence page in
an unrelated reply, and reading it forced someone to open LICENSE.

WHAT IT CHECKS
--------------
1. Every declared licence identifier agrees.
2. LICENSE actually contains the licence it claims to be.
3. The third-party carve-out is still present. Apache 2.0 does not conflict
   with CC BY 4.0, so the carve-out is no longer strictly load-bearing — but
   it is the only place a reader learns that the BRENDA fixtures are not
   Apache-licensed, and deleting it would quietly remove that.
4. NOTICE exists and credits BRENDA. Apache 2.0 §4(d) makes NOTICE the
   mechanism by which the CC BY attribution reaches downstream users; an
   empty or missing NOTICE breaks the chain silently.

WHERE IT LOOKS FOR DECLARATIONS
-------------------------------
Every tracked `package.json` and `*.cff`, and (since 2026-11-01) every
tracked OpenAPI spec and `pyproject.toml`. The first version read only the
first two, and that was the same defect in a smaller form: at f4ab5f7 the
root `openapi.yaml` said `license: name: MIT`, served to every client by
`GET /api/openapi.json`, while this guard printed OK. It was checking two
kinds of file and reporting on the repository. `pyproject.toml`'s
`[project] license` is the one the published wheel carries in its metadata,
so it is the declaration most people downstream actually read.

WHAT IT DOES NOT CHECK
----------------------
Whether Apache 2.0 is the right licence. That is a decision for a lawyer at
incorporation, and a script that appeared to validate it would be worse than
no script — the "check that cannot fail" failure, applied to a legal
question.

Exit 0 = consistent. Exit 1 = a real disagreement, or a published
manifest named in PUBLISHED_SPECS / PUBLISHED_PYPROJECT is missing.
Exit 3 = could not check (a declaration this machine cannot parse).
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The licence this repository is under. Changing it here is not enough --
#: every file below must change too, which is the entire point.
EXPECTED = "Apache-2.0"

#: A phrase that must appear in LICENSE for it to really BE that licence.
#: A file can say "Apache-2.0" in a comment while containing MIT's text.
LICENCE_BODY_MARKERS = {
    "Apache-2.0": [
        "Apache License",
        "Version 2.0, January 2004",
        "Grant of Patent License",
    ],
    "MIT": ["Permission is hereby granted, free of charge"],
}

#: Phrases that contradict any permissive licence. Present in the file that
#: caused this whole problem.
CONTRADICTIONS = [
    "all rights reserved, no permission granted",
    "no permission granted to copy",
    "LicenseRef-Caterva-Proprietary",
]


#: OpenAPI specs that are published, and so MUST declare a licence. For any
#: other spec a missing licence passes and only a wrong one fails.
#:
#: The root spec is served to every client by `GET /api/openapi.json`
#: (src/web/server.ts), and docs/api/OPENAPI_GUIDE.md calls it the spec
#: "Caterva publishes", so a reader takes its `info.license` as the terms.
#: `Science-Agent-Pipeline/lib/api-spec/openapi.yaml` is left out on
#: purpose: it is the codegen input of a `"private": true` workspace
#: package, nothing serves it, and its `info` block is generator
#: boilerplate ("Do not change the title"). Saying nothing there is not a
#: claim about the terms; saying MIT there would be one, and is caught.
PUBLISHED_SPECS = {"openapi.yaml"}

#: The pyproject whose `[project] license` becomes the published wheel's
#: metadata. It must declare one: a wheel without it says UNKNOWN on PyPI
#: and to every SBOM tool, which is a statement about the terms too.
PUBLISHED_PYPROJECT = "pyproject.toml"

#: A spec by file name, the way generators and the guide name them. Matched
#: on the base name, so a spec added in a new package is found without
#: editing this file. `openapitools.json` does not match: it is the
#: generator's own config, not a spec.
_SPEC_NAME = re.compile(r"^(openapi|swagger)([._-][^/]*)?\.(ya?ml|json)$", re.I)


class CouldNotCheckError(Exception):
    """A declaration exists that this machine cannot read.

    Reported as exit 3, not 0. A guard that skips the file it cannot parse
    and prints OK is the defect this file was written about.
    """


def tracked(pattern: str, root: pathlib.Path = REPO) -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", pattern], cwd=root, capture_output=True, text=True
    )
    return [root / line for line in out.stdout.splitlines() if line]


def openapi_specs(root: pathlib.Path = REPO) -> list[pathlib.Path]:
    return [
        p for p in tracked("*", root)
        if _SPEC_NAME.match(p.name) and "node_modules" not in p.parts
    ]


def _load_spec(path: pathlib.Path) -> object:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    # PyYAML, not a regex. It is pinned in requirements-dev.txt and CI
    # installs it for check_ci_toolchain.py. A regex for `name: MIT` would
    # have to know which block it sits in, and a spec may write
    # `license: {name: MIT}` in flow style on one line; the parser knows.
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is in requirements-dev
        raise CouldNotCheckError(
            f"{path.name} is YAML and PyYAML is not installed "
            "(pip install -r requirements-dev.txt)."
        ) from exc
    return yaml.safe_load(text)


def spec_licences(path: pathlib.Path) -> list[str] | None:
    """Every licence string a spec's `info.license` states.

    None when the file is not an OpenAPI or Swagger document at all. Both
    `name` and the 3.1 `identifier` are read: a spec saying
    `identifier: Apache-2.0` and `name: MIT` contradicts itself, and
    reading only one of them would pass it.
    """
    try:
        data = _load_spec(path)
    except CouldNotCheckError:
        raise
    except Exception as exc:  # a malformed spec is "could not check", not a skip
        raise CouldNotCheckError(f"{path.name} could not be parsed: {exc}") from exc
    if not isinstance(data, dict) or not ({"openapi", "swagger"} & set(data)):
        return None
    info = data.get("info")
    licence = info.get("license") if isinstance(info, dict) else None
    if isinstance(licence, str):
        return [licence]
    if not isinstance(licence, dict):
        return []
    return [str(licence[k]) for k in ("identifier", "name") if k in licence]


def pyproject_licence(path: pathlib.Path) -> str | None:
    """`[project] license` as a string, or None when it states none.

    tomllib is in the standard library from 3.11. The repository supports
    3.10 and declares no `tomli` (nothing else here parses TOML), so on 3.10
    a regex reads the one key, scoped to the `[project]` table. It accepts
    the PEP 639 string form and the older `{text = "..."}` table, the two
    forms that state an identifier. `{file = "LICENSE"}` states none, and
    returns None under both readers.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import tomllib
    except ImportError:  # Python 3.10
        tomllib = None  # type: ignore[assignment]
    if tomllib is not None:
        try:
            project = tomllib.loads(text).get("project", {})
        except tomllib.TOMLDecodeError as exc:
            raise CouldNotCheckError(f"{path.name} could not be parsed: {exc}") from exc
        licence = project.get("license")
        if isinstance(licence, str):
            return licence
        if isinstance(licence, dict) and isinstance(licence.get("text"), str):
            return licence["text"]
        return None
    return _pyproject_licence_by_regex(text)


def _pyproject_licence_by_regex(text: str) -> str | None:
    """The 3.10 reader. Kept separate so a test can run it on any Python."""
    section = re.search(r"^\[project\][ \t]*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not section:
        return None
    match = re.search(
        r'^license\s*=\s*(?:"([^"]+)"|\{\s*text\s*=\s*"([^"]+)"\s*\})',
        section.group(1), re.M,
    )
    return (match.group(1) or match.group(2)) if match else None


def missing_declarations(root: pathlib.Path = REPO) -> list[str]:
    """Published manifests that are missing, or that state no licence.

    A published file that is not there is a failure, not a pass. Until
    2026-11-01 each check ran only `if path.exists()`, so renaming or
    moving the root openapi.yaml (say, to a new name server.ts serves)
    would have turned the published spec into an "internal" one where
    silence passes, and nothing would have said the published file was
    gone. The constant names what is published; when it goes stale the
    reader is told to update it.
    """
    problems = []
    for rel in sorted(PUBLISHED_SPECS):
        path = root / rel
        if not path.is_file():
            problems.append(
                f"{rel} is listed in PUBLISHED_SPECS but does not exist. If "
                "the published spec moved or was renamed, update "
                "PUBLISHED_SPECS in scripts/check_license_consistency.py to "
                "the file GET /api/openapi.json now serves; until then the "
                "published spec's licence is not being checked."
            )
            continue
        if not spec_licences(path):
            problems.append(
                f"{rel} declares no info.license, and it is published "
                "(served by GET /api/openapi.json). A client reading it "
                "learns nothing about the terms."
            )
    pyproject = root / PUBLISHED_PYPROJECT
    if not pyproject.is_file():
        problems.append(
            f"{PUBLISHED_PYPROJECT} is PUBLISHED_PYPROJECT but does not "
            "exist. If the wheel is now built from another pyproject.toml, "
            "update PUBLISHED_PYPROJECT in "
            "scripts/check_license_consistency.py; until then the wheel's "
            "licence metadata is not being checked."
        )
    elif pyproject_licence(pyproject) is None:
        problems.append(
            f"{PUBLISHED_PYPROJECT} has no [project] license, so the "
            "published wheel's metadata says UNKNOWN."
        )
    return problems


def declared_licences(root: pathlib.Path = REPO) -> list[tuple[pathlib.Path, str]]:
    """(file, identifier) for every file that declares one."""
    found: list[tuple[pathlib.Path, str]] = []

    for path in tracked("*package.json", root):
        if "node_modules" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        licence = data.get("license")
        if isinstance(licence, str):
            found.append((path, licence))

    for path in tracked("*.cff", root):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^license:\s*(\S+)\s*$", text, re.M)
        if match:
            found.append((path, match.group(1).strip('"\'')))

    for path in openapi_specs(root):
        found.extend((path, licence) for licence in spec_licences(path) or [])

    for path in tracked("*pyproject.toml", root):
        if path.name != "pyproject.toml":
            continue
        licence = pyproject_licence(path)
        if licence is not None:
            found.append((path, licence))

    return found


def main(root: pathlib.Path | None = None) -> int:
    """Run every check on `root` (the repository by default).

    `root` exists so a test can run the whole guard, exit code included,
    on a planted tree instead of only calling the helpers.
    """
    root = REPO if root is None else root
    problems: list[str] = []
    checked = 0

    # --- 1. identifiers agree ------------------------------------------
    try:
        declarations = declared_licences(root)
        problems.extend(missing_declarations(root))
    except CouldNotCheckError as exc:
        print(f"check_license_consistency: could not check: {exc}")
        print("This is 'could not check', NOT 'checked and fine'. Exiting 3.")
        return 3
    for path, licence in declarations:
        checked += 1
        if licence != EXPECTED:
            problems.append(
                f"{path.relative_to(root)} declares license '{licence}', "
                f"but the repository is {EXPECTED}. Two files claiming "
                "different terms is the exact defect this guard was written "
                "for."
            )

    if not declarations:
        problems.append(
            "No file declares a licence at all. Either the guard's search is "
            "wrong or the declarations were deleted; both are failures."
        )

    # --- 2. LICENSE contains the licence it claims ---------------------
    licence_file = root / "LICENSE"
    if not licence_file.exists():
        problems.append("LICENSE is missing.")
    else:
        body = licence_file.read_text(encoding="utf-8", errors="replace")
        checked += 1
        for marker in LICENCE_BODY_MARKERS.get(EXPECTED, []):
            if marker not in body:
                problems.append(
                    f"LICENSE does not contain {EXPECTED} marker text "
                    f"{marker!r}. A file can name a licence it does not "
                    "contain; only the body is binding."
                )

        for phrase in CONTRADICTIONS:
            # The historical account of the breach quotes the old wording,
            # so a bare substring search would flag the explanation itself.
            # Only unquoted occurrences count.
            for line in body.splitlines():
                stripped = line.strip()
                if phrase.lower() in stripped.lower() and not (
                    stripped.startswith('"')
                    or '"' in stripped
                    or stripped.startswith("*")
                    or stripped.startswith("#")
                ):
                    problems.append(
                        f"LICENSE still asserts {phrase!r} outside a quotation: "
                        f"{stripped[:90]!r}"
                    )

        # --- 3. the third-party carve-out survives ---------------------
        checked += 1
        if "THIRD-PARTY DATA IS NOT COVERED" not in body:
            problems.append(
                "LICENSE has lost its third-party carve-out. It is the only "
                "place a reader learns that Tests/fixtures/brenda_*.html is "
                "CC BY 4.0 rather than Apache 2.0."
            )

    # --- 4. NOTICE credits BRENDA --------------------------------------
    notice = root / "NOTICE"
    checked += 1
    if not notice.exists():
        problems.append(
            "NOTICE is missing. Apache 2.0 §4(d) makes it the mechanism that "
            "carries BRENDA's CC BY attribution downstream; without it the "
            "attribution stops at this repository."
        )
    else:
        notice_text = notice.read_text(encoding="utf-8", errors="replace")
        for required in ["BRENDA", "CC BY", "DSMZ"]:
            if required not in notice_text:
                problems.append(f"NOTICE does not mention {required!r}.")

    # --- 4. the INBOUND licence is stated somewhere a contributor looks --
    #
    # LICENSE names this as one of the three reasons for relicensing:
    #
    #     "An all-rights-reserved repository cannot accept outside
    #      contributions cleanly -- there is no inbound licence for the
    #      contribution to arrive under."
    #
    # The problem was named and the answer was never written down. A
    # contributor who went looking found a paragraph explaining why the old
    # state was bad and nothing saying what the current state is.
    #
    # Apache-2.0 section 5 supplies the answer implicitly, which is exactly
    # why it needs saying explicitly: an implicit term is one a contributor
    # has to already know to find. Somebody deciding whether to spend a
    # weekend on a pull request is deciding what happens to a weekend of
    # their work.
    #
    # Checked here rather than in a new guard because "the repository is
    # unambiguous about its own terms" is this file's subject, and inbound
    # terms are terms.
    inbound = root / "docs" / "INBOUND_LICENSE.md"
    if not inbound.exists():
        problems.append(
            "docs/INBOUND_LICENSE.md is missing. Nothing states what a "
            "contribution arrives under, which LICENSE itself names as the "
            "defect that made the old licence unworkable."
        )
    else:
        checked += 1
        inbound_text = inbound.read_text(encoding="utf-8", errors="replace")
        for required, why in [
            ("Apache-2.0", "the inbound licence itself"),
            ("Section 5", "the clause that supplies it"),
            ("copyright", "that the contributor keeps theirs"),
            ("university", "the student IP question, which is the one most "
                           "likely to cause a real problem"),
        ]:
            if required.lower() not in inbound_text.lower():
                problems.append(
                    f"docs/INBOUND_LICENSE.md does not mention {required!r} "
                    f"({why})."
                )

    contributing = root / "CONTRIBUTING.md"
    if contributing.exists():
        checked += 1
        contributing_text = contributing.read_text(encoding="utf-8", errors="replace")
        if "INBOUND_LICENSE" not in contributing_text:
            problems.append(
                "CONTRIBUTING.md does not link docs/INBOUND_LICENSE.md. A "
                "statement of inbound terms that contributors are not sent "
                "to is one nobody reads."
            )

    # --- report ---------------------------------------------------------
    print(f"Checked {checked} licence declaration(s) across "
          f"{len(declarations)} manifest file(s), LICENSE and NOTICE.")
    for path, licence in sorted(declarations):
        print(f"  {path.relative_to(root)}: {licence}")

    if problems:
        print()
        print(f"Licence declarations disagree ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print(
            "A project about provenance cannot be unclear about its own "
            "terms. Fix every file, not the one the guard names first."
        )
        return 1

    print(f"OK: every declaration says {EXPECTED}, LICENSE contains it, "
          "the third-party carve-out is intact, and NOTICE credits BRENDA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
