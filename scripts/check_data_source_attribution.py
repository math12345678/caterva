#!/usr/bin/env python3
"""Two places state each data source's licence. They must not disagree.

WHY THIS EXISTS
---------------
`NOTICE` states BRENDA's licence in prose, for a human reading the
repository. `caterva/core/data_sources.py` states it in a table, to be
written into every exported model.

Two statements of one fact drift. ADR 0003 exists because two copies of a
numeric bound drifted; ADR 0027 because a reliability score was implemented
twice and the copies computed different things. A licence is a worse thing
to be wrong about than either, because the failure is silent and the party
harmed is not the person running the code.

The direction of the check matters. It asserts that everything the *table*
claims is also in `NOTICE`, not the reverse. `NOTICE` is longer on purpose
-- it covers dependencies, SABIO-RK's absence, warranty text -- and
requiring the table to restate all of that would push the whole document
into a Python file, which is where nobody looking for a licence would think
to look.

WHAT IT CHECKS
--------------
1. Every creator, licence name, licence URI, source URI and citation
   request in the table appears in `NOTICE`.
2. `NOTICE` names the CC BY 4.0 clause that requires modifications to be
   indicated, and the table's `modifications` field is non-empty for any
   source under a licence that requires it.
3. The attribution block a model receives actually contains the licence and
   the creator -- rendered, not merely stored. A table nobody renders is
   ADR 0027 again.

WHAT IT DOES NOT CHECK
----------------------
Whether the licence statements are legally correct. That needs a lawyer,
and the ADR says so. This checks that the project says one thing rather
than two.

Exit 0 = the statements agree. Exit 1 = they do not.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from caterva.core.data_sources import SOURCES, attribution_lines  # noqa: E402
from caterva.core.model_provenance import (  # noqa: E402
    ParameterProvenance,
    annotate_antimony,
)

NOTICE = REPO / "NOTICE"

#: A minimal real model, so the check exercises the annotator rather than a
#: string builder standing in for it.
_MODEL = "model m\n  J0: S -> P; Vmax * S / (Km + S);\n  Km = 2.5;\nend\n"


def _Entry(source: str) -> ParameterProvenance:
    """A real provenance record, not a stand-in.

    This was a hand-rolled stub with just `source` and `citation` on it,
    which was enough for `attribution_lines` and not enough for
    `annotate_antimony` -- it crashed on `one_line()` the moment the check
    started going through the real annotator. The stub had been quietly
    limiting the guard to the shallower path.
    """
    return ParameterProvenance(origin="resolved", source=source, citation=source)


def _normalise(text: str) -> str:
    """Collapse whitespace so a line break in NOTICE is not a mismatch.

    NOTICE is hard-wrapped prose; the table is not. Comparing them
    literally would report a wrap as a licence disagreement, and a guard
    that fires on formatting gets switched off.
    """
    return " ".join(text.split())


def _code_only(path: pathlib.Path) -> str:
    """The file's executable string values, with prose removed.

    A module that *explains* CC BY by quoting the legalcode URL is
    documenting itself, not holding a second copy of the licence. The first
    version of this check did not distinguish the two and reported
    `data_sources.py` for the URL in its own docstring -- a guard firing on
    the explanation of the rule it enforces.

    Python is parsed, so docstrings are excluded structurally rather than by
    guessing at quote characters. TypeScript has its comments stripped, which
    is cruder and sufficient: a `//` or `/* */` there is never a value.
    """
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix == ".py":
        import ast

        tree = ast.parse(text)
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        return "\n".join(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        )

    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # `(?<!:)` because `//` is both the comment marker and half of every URL.
    #
    # Without it this stripper deleted from the `//` in `https://` onward,
    # which removed the licence URI from the very text being searched for the
    # licence URI -- so inlining `https://creativecommons.org/licenses/by/4.0/`
    # into the renderer passed the guard. Caught by mutation, not by reading.
    #
    # Fourth time today that `//` handling has eaten a URL: a test helper, the
    # guard's own flattener, and now this. In a codebase where every licence
    # and citation carries a URL, `//` is not safely a comment marker.
    return "\n".join(
        re.sub(r"(?<!:)//.*$", "", line) for line in without_block.splitlines()
    )


def _flatten(annotated: str) -> str:
    """Strip the comment marker at LINE STARTS only, then normalise.

    Not `replace("//", " ")`: that also eats the `//` in `https://`, so any
    check involving a URI would compare against a mangled string and pass or
    fail for a reason unrelated to the licence. The first version did that
    and got away with it only because the two URI checks happen to run
    against NOTICE rather than against this text.
    """
    return _normalise(
        " ".join(
            re.sub(r"^\s*//\s?", "", line) for line in annotated.splitlines()
        )
    )


def main() -> int:
    if not NOTICE.is_file():
        print(f"{NOTICE.name} is missing; refusing to report on attribution.")
        return 1

    notice = _normalise(NOTICE.read_text(encoding="utf-8", errors="replace"))
    problems: list[str] = []

    if not SOURCES:
        print(
            "caterva/core/data_sources.py describes no sources. Either the "
            "table was emptied or this reader is broken; refusing to report "
            "success on an empty set."
        )
        return 1

    for source in SOURCES:
        name = source.tokens[0]

        for label, value in (
            ("creator", source.creator),
            ("source URI", source.source_uri),
            ("licence", source.licence),
            ("licence URI", source.licence_uri),
            ("citation request", source.citation_request),
        ):
            if not value:
                continue
            # The citation request carries explanatory wording around a URL;
            # the URL is the checkable part.
            needles = [value]
            if label == "citation request":
                needles = [part for part in value.split() if "://" in part]
            for needle in needles:
                if _normalise(needle) not in notice:
                    problems.append(
                        f"{name}: the {label} in data_sources.py is not in "
                        f"NOTICE -- {needle!r}. One of the two is wrong, and "
                        "a reader has no way to tell which."
                    )

        if source.licence and source.licence.lower() != "public domain":
            if not source.modifications.strip():
                problems.append(
                    f"{name} is licensed under {source.licence} but the table "
                    "records no modifications. CC BY 4.0 3(a)(1)(B) requires "
                    "modification to be indicated, and Caterva does modify "
                    "what it extracts."
                )

    # The table must actually reach a model. Storing the licence and never
    # rendering it is ADR 0027's defect wearing a licence.
    for source in SOURCES:
        # Through `annotate_antimony`, NOT `attribution_lines`.
        #
        # The first version called the renderer directly, and mutation
        # showed what that was worth: deleting the one line in
        # model_provenance.py that puts the block into a model left this
        # guard green. It was checking that the text could be produced, not
        # that a model receives it -- a copy of the thing instead of the
        # thing, which is the failure this repository keeps finding and the
        # one this guard's own docstring claimed to be immune to.
        #
        # Flattened before comparison for the same reason NOTICE is: the
        # block hard-wraps, and a creator name long enough to wrap would
        # otherwise be reported as missing from the very text containing it.
        annotated = annotate_antimony(
            _MODEL, {"km": _Entry(f"{source.tokens[0]}_exact")}
        ).text
        rendered = _flatten(annotated)
        if "DATA SOURCES" not in annotated:
            problems.append(
                f"{source.tokens[0]}: a model containing a value from this "
                "source carries no attribution block. The licence facts are "
                "recorded and never reach the artifact that leaves."
            )
            continue
        if source.licence and source.licence not in rendered:
            problems.append(
                f"{source.tokens[0]}: the rendered block omits the licence "
                f"({source.licence}). It is stored and not delivered."
            )
        if _normalise(source.creator) not in rendered:
            problems.append(
                f"{source.tokens[0]}: the rendered block omits the creator."
            )

        # CC BY 3(a)(1)(A)(v) and (C) ask for URIs, and this could not be
        # checked until the flattening stopped mangling them.
        for clause, uri in (
            ("3(a)(1)(A)(v) URI to the material", source.source_uri),
            ("3(a)(1)(C) URI to the licence", source.licence_uri),
        ):
            if uri and uri not in rendered:
                problems.append(
                    f"{source.tokens[0]}: the rendered block omits the "
                    f"{clause} -- {uri}"
                )

    # Neither renderer may carry the licence as a literal.
    #
    # `docs/data-sources.json` is the one table precisely so the Antimony,
    # SBML and CSV exports cannot come to state different terms. That holds
    # only while both readers READ it -- the failure mode is a hurried edit
    # that inlines "CC BY 4.0" into one language "just for now", after which
    # the two agree until the day they do not. ADR 0003 and ADR 0027 are both
    # that story.
    #
    # Values, not clause references: the modules discuss 3(a)(1) and 2(a)(6)
    # in comments, which is documentation, not a second source of truth.
    renderers = {
        "caterva/core/data_sources.py": REPO / "caterva/core/data_sources.py",
        "dataSources.ts": (
            REPO
            / "Science-Agent-Pipeline/artifacts/api-server/src/lib/dataSources.ts"
        ),
    }
    literals = [
        value
        for source in SOURCES
        for value in (source.licence_uri, source.source_uri, source.creator)
        if value
    ]
    for label, path in renderers.items():
        if not path.is_file():
            problems.append(
                f"{label} is missing, so one of the two renderers was NOT "
                "checked for inlined licence values."
            )
            continue
        text = _code_only(path)
        for literal in literals:
            if literal in text:
                problems.append(
                    f"{label} contains the licence value {literal!r} as a "
                    "literal. It must read docs/data-sources.json instead; "
                    "two copies of a licence drift the way ADR 0003's two "
                    "copies of a numeric bound did."
                )

    # Crediting a source that contributed nothing is a false provenance
    # claim and the endorsement CC BY 4.0 2(a)(6) forbids implying.
    user_only = attribution_lines({"km": _Entry("user")})
    if user_only:
        problems.append(
            "a model built only from user-supplied values still produces an "
            "attribution block. Naming a source that contributed nothing is "
            "a false claim about provenance."
        )

    print(f"Checked {len(SOURCES)} data source(s) against NOTICE.")

    if problems:
        print()
        print(f"Attribution statements disagree ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print(
            "NOTICE and caterva/core/data_sources.py must say the same thing "
            "about the same licence. Fix whichever is wrong -- do not delete "
            "the check."
        )
        return 1

    print("OK: every licence fact in the table is also in NOTICE, and reaches a model.")
    return 0


def _selftest() -> int:
    """Prove each branch fires, by breaking a copy of the table."""
    import copy
    import dataclasses
    import io
    import contextlib

    global SOURCES
    saved = SOURCES
    failures: list[str] = []

    def run() -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main()
        return code, buffer.getvalue()

    def expect(label: str, want_code: int, want: str = "") -> None:
        code, out = run()
        if code != want_code or (want and want.lower() not in out.lower()):
            failures.append(
                f"{label}: exit {code} (wanted {want_code})"
                + (f", message did not mention {want!r}" if want else "")
                + f"\n      output: {' '.join(out.split())[:200]}"
            )

    try:
        # Negative case first: if the real table does not pass, every
        # positive below would fire on anything.
        expect("the real table agrees with NOTICE", 0, "OK")

        brenda = next(s for s in SOURCES if s.tokens[0] == "brenda")

        SOURCES = tuple(
            dataclasses.replace(s, creator="The Ministry of Enzymes")
            if s is brenda else s
            for s in saved
        )
        expect("a creator not in NOTICE is caught", 1, "creator")

        SOURCES = tuple(
            dataclasses.replace(s, licence="CC BY-NC 4.0") if s is brenda else s
            for s in saved
        )
        expect("a licence not in NOTICE is caught", 1, "licence")

        SOURCES = tuple(
            dataclasses.replace(s, modifications="  ") if s is brenda else s
            for s in saved
        )
        expect("an empty modifications field is caught", 1, "3(a)(1)(B)")

        SOURCES = ()
        expect("an empty table is refused, not passed", 1, "refusing")
    finally:
        SOURCES = saved

    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELFTEST OK: every branch fires, and the real table still passes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    sys.exit(main())
