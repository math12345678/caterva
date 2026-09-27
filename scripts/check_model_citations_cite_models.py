#!/usr/bin/env python3
"""A `modelCitation` must cite the model, not the database it drew numbers from.

WHY THIS EXISTS
---------------
ADR 0008 is explicit about what the field means:

    `modelCitations` describes the MODEL, never an individual parameter
    value.

Every domain in `DOMAIN_DEFAULTS` honoured that except the two most central
to this project. Measured across all fifteen:

    sir                     Kermack W.O., McKendrick A.G. (1927) ...
    gillespie_ssa           Gillespie D.T. (1977) ...
    lotka_volterra          Lotka A.J. (1925) ...
    repressilator           Elowitz M.B., Leibler S. (2000) ...
    mm                      BRENDA -- The Comprehensive Enzyme Information System
    mm_competitive_inhibition   BRENDA -- The Comprehensive Enzyme Information System

Thirteen cite the paper that defines the model. Two cited a database, so
the Michaelis-Menten domains were the only ones whose model was uncited --
in an enzyme-kinetics tool.

It was wrong a second way. Those `parameters` are hardcoded defaults
(km 2, vmax 5) used when nothing resolved, so on that path BRENDA supplied
no number in the response and was named anyway. That is a credit claim for
output the source had no part in -- the false-provenance defect ADR 0063
refuses in the exported model's attribution block, and under CC BY 4.0
2(a)(6) the endorsement the licence forbids implying.

WHAT IT CHECKS
--------------
That no `modelCitations` entry is a bare database name. A database is
recognised by naming a known data source WITHOUT the marks of a paper --
an author-year, a volume/pages, or a DOI. `Johnson K.A., Goody R.S. (2011)
Biochemistry 50(39), 8264-8269` is a paper that happens to be about
enzymology; `BRENDA -- The Comprehensive Enzyme Information System` is not
a paper at all.

That distinction matters: BRENDA publishes a real, citable database paper
in Nucleic Acids Research, and citing THAT is correct and encouraged by
NOTICE. What this refuses is the bare database name standing in for a
model reference.

WHAT IT DOES NOT CHECK
----------------------
Whether the cited paper is the RIGHT one for the model. That needs a
reader who knows the field. `check_citation_format.py` checks the entry is
lookuppable; this checks it is the kind of thing a model can be cited to.

Exit 0 = every model citation cites a model. Exit 1 = one cites a database.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
RESOLVER = (
    REPO
    / "Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts"
)

#: Data sources Caterva draws values from. Named here rather than imported
#: from `data_sources.py` on purpose: that table is the list of sources it
#: is CORRECT to attribute, and this is the list it is INCORRECT to cite as
#: a model. Coupling them would make adding a source silently change what
#: this guard forbids.
DATABASE_NAMES = ("BRENDA", "SABIO-RK", "KEGG", "UniProt", "PubChem", "MetaCyc")

#: What makes a string a citable work rather than a name.
_AUTHOR_YEAR = re.compile(r"\(\d{4}[a-z]?\)")
_VOLUME_PAGES = re.compile(r"\b\d+(\(\d+\))?,\s*\d+")
_DOI = re.compile(r"\bdoi\.org/|<?doi:", re.I)


def looks_like_a_paper(entry: str) -> bool:
    """Whether this entry has the marks of a citable work.

    An author-year alone is enough -- `Fisher R.A. (1930) The Genetical
    Theory of Natural Selection. Oxford: Clarendon Press.` is a book with
    no volume, pages or DOI, and refusing it would be this guard having an
    opinion about publication formats rather than about model citations.
    """
    return bool(
        _AUTHOR_YEAR.search(entry)
        or _VOLUME_PAGES.search(entry)
        or _DOI.search(entry)
    )


def citations_by_domain(source: str) -> dict[str, list[str]]:
    """Read `DOMAIN_DEFAULTS` out of the TypeScript.

    Parsed rather than executed, because running the TS would need a
    toolchain this guard should not depend on. Parsing is fragile in
    general; here it is checked by `--selftest` and, more importantly, by
    refusing to report success when it finds nothing.
    """
    start = source.find("const DOMAIN_DEFAULTS")
    if start == -1:
        return {}
    block = source[start : source.find("\n];", start)]

    found: dict[str, list[str]] = {}
    for match in re.finditer(
        r'domain:\s*"([^"]+)".*?modelCitations:\s*\[(.*?)\]', block, re.S
    ):
        entries = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(2))
        found[match.group(1)] = entries
    return found


def check(source: str) -> list[str]:
    problems: list[str] = []
    for domain, entries in sorted(citations_by_domain(source).items()):
        if not entries:
            problems.append(
                f"{domain} lists no model citation. A simulation offered to "
                "a student with no reference to the model it implements is "
                "the gap this field exists to close."
            )
            continue
        for entry in entries:
            # A blank entry is a citation that cites nothing while making
            # the list look populated -- worse than an empty list, which at
            # least reads as absent. `check_citation_format.py` also
            # rejects these; both guards say so because either one could be
            # narrowed later and this is not a fact worth losing.
            if not entry.strip():
                problems.append(
                    f"{domain} has an empty model citation. A blank entry "
                    "makes the list look populated while naming nothing."
                )
                continue

            named = next(
                (db for db in DATABASE_NAMES if db.lower() in entry.lower()),
                None,
            )
            if named and not looks_like_a_paper(entry):
                problems.append(
                    f"{domain} cites {named} as a model citation: "
                    f"{entry[:70]!r}. ADR 0008: modelCitations describes the "
                    "MODEL. A database is where values come from, not what "
                    "the model IS -- and on the defaults path it supplied no "
                    "value either. Cite the paper defining the model; credit "
                    "the database per parameter."
                )
    return problems


def main() -> int:
    if not RESOLVER.is_file():
        print(f"{RESOLVER.relative_to(REPO)} is missing; refusing to report.")
        return 1

    source = RESOLVER.read_text(encoding="utf-8", errors="replace")
    by_domain = citations_by_domain(source)
    if not by_domain:
        # Reading nothing is not the same as finding nothing wrong. This
        # project has repeatedly found checks that examined an empty set
        # and printed OK.
        print(
            "No DOMAIN_DEFAULTS entries were parsed out of "
            f"{RESOLVER.name}. Either the table moved or this reader is "
            "broken; refusing to report success on an empty set."
        )
        return 1

    problems = check(source)
    print(f"Checked model citations for {len(by_domain)} domain(s).")

    if problems:
        print()
        print(f"A model citation names a database ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("OK: every domain cites the work that defines its model.")
    return 0


def _selftest() -> int:
    """Prove each branch fires, on sources this function writes."""
    failures: list[str] = []

    def table(domain: str, citation: str) -> str:
        return (
            "const DOMAIN_DEFAULTS: DomainDefaults[] = [\n"
            f'  {{ domain: "{domain}", modelCitations: ["{citation}"] }},\n'
            "];\n"
        )

    # Negative case first: a real citation must pass, or every positive
    # below would fire on anything.
    good = table("sir", "Kermack W.O., McKendrick A.G. (1927) ... 115, 700-721.")
    if check(good):
        failures.append(f"a real paper was rejected: {check(good)}")

    book = table("wright_fisher", "Fisher R.A. (1930) The Genetical Theory. Oxford.")
    if check(book):
        failures.append("a book with no volume/pages was rejected")

    bare = table("mm", "BRENDA — The Comprehensive Enzyme Information System")
    if not check(bare):
        failures.append("a bare database name was accepted (the real defect)")

    # BRENDA's own database PAPER is a legitimate citation and must pass.
    paper = table(
        "mm",
        "Chang A. et al. (2021) BRENDA, the ELIXIR core data resource. "
        "Nucleic Acids Research 49(D1), D498-D508.",
    )
    if check(paper):
        failures.append(
            "BRENDA's database paper was rejected; the guard is refusing a "
            "name rather than a non-citation"
        )

    empty = table("mm", "")
    if not check(empty):
        failures.append("an empty citation string was accepted")

    if not citations_by_domain("nothing here") == {}:
        failures.append("the parser invented a table from unrelated text")

    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELFTEST OK: every branch fires, and real citations still pass.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    sys.exit(main())
