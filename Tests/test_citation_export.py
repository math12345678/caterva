"""Citation export — Katz's point, taken at its sharpest.

The assertions that matter are the ones about what is NOT emitted. An entry
that imports cleanly and is fiction would enter someone's bibliography and
be cited onward with Terrium's name on it.
"""
from __future__ import annotations

import re

import pytest

from citation import Citation
from citation_export import (
    _BIBTEX_SPECIALS,
    CitedParameter,
    bibtex_key,
    to_bibtex,
    to_ris,
)

KM = CitedParameter(
    parameter="km",
    citation=Citation(
        source="BRENDA",
        reference_id="740253",
        url="https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        organism="Homo sapiens",
    ),
    value=2.5,
    unit="mM",
    organism="Homo sapiens",
)

KI = CitedParameter(
    parameter="ki",
    citation=Citation(source="BRENDA", reference_id="711801"),
    value=0.0014,
    unit="mM",
    organism="Homo sapiens",
)

SAME_REFERENCE_AS_KM = CitedParameter(
    parameter="vmax",
    citation=Citation(source="BRENDA", reference_id="740253"),
    value=5.0,
    unit="mM/s",
)


# ---------------------------------------------------------------------------
# What it refuses to write
# ---------------------------------------------------------------------------

def test_no_author_is_fabricated():
    """The single most damaging thing this module could do."""
    out = to_bibtex([KM, KI])
    assert not re.search(r"^\s*author\s*=", out, re.M)


def test_no_year_or_journal_is_fabricated():
    out = to_bibtex([KM, KI])
    assert not re.search(r"^\s*year\s*=", out, re.M)
    assert not re.search(r"^\s*journal\s*=", out, re.M)


def test_the_absence_is_stated_rather_than_left_to_be_noticed():
    """An omitted field looks like an oversight. Saying so turns it into
    information the reader can act on."""
    out = to_bibtex([KM])
    assert "are NOT known to it and have been omitted" in out
    assert "rather than guessed" in out


def test_entry_type_does_not_assert_a_publication_type():
    """`@article` would claim the source is a journal article. A BRENDA
    reference id identifies a record, which may be a paper, a chapter or a
    submission — asserting which is the same error as asserting an author."""
    out = to_bibtex([KM])
    assert "@misc{" in out
    assert "@article{" not in out


def test_ris_type_is_data_not_journal():
    out = to_ris([KM])
    assert "TY  - DATA" in out
    assert "TY  - JOUR" not in out


# ---------------------------------------------------------------------------
# Uniqueness — the failure that hides itself
# ---------------------------------------------------------------------------

def test_two_parameters_from_one_reference_get_distinct_keys():
    """BibTeX silently keeps ONE entry when two share a key. The
    bibliography would be short by an entry and nothing would say so."""
    out = to_bibtex([KM, SAME_REFERENCE_AS_KM])
    keys = re.findall(r"@misc\{([^,]+),", out)
    # The property is uniqueness, not the total. The database's own entry
    # (`terrium-source-*`) is a third block and does not weaken the check --
    # it is excluded so this still measures the two PARAMETER keys.
    parameter_keys = [k for k in keys if not k.startswith("terrium-source-")]
    assert len(parameter_keys) == 2
    assert len(set(keys)) == len(keys), f"duplicate BibTeX key in {keys}"


def test_keys_are_valid_bibtex_identifiers():
    keys = re.findall(r"@misc\{([^,]+),", to_bibtex([KM, KI, SAME_REFERENCE_AS_KM]))
    for key in keys:
        assert re.fullmatch(r"[A-Za-z0-9_:-]+", key), key


def test_a_citation_with_no_identifier_still_gets_a_key():
    anonymous = CitedParameter(
        parameter="kcat", citation=Citation(source="PubMed"), value=12.0
    )
    out = to_bibtex([anonymous])
    keys = re.findall(r"@misc\{([^,]+),", out)
    assert keys and keys[0]


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "hostile",
    [
        "a & b",
        "50% yield",
        "under_score",
        "{braces}",
        "$math$",
        "back\\slash",
        "tilde~and^caret",
        "#hash",
    ],
)
def test_bibtex_specials_in_a_title_are_escaped(hostile):
    """An unescaped `&` or `%` makes the whole .bib file fail to parse, so a
    hostile title takes the entire bibliography down rather than one entry.

    THE VERSION THIS REPLACES CHECKED THE EASY CASES ONLY
    -----------------------------------------------------
    It looped `for char in "&%#$_"` and asserted inside `if char in hostile`.
    Two of the six parameters -- `{braces}` and `back\\slash` -- contain none
    of those five characters, so those runs asserted **nothing**.

    Those are the two hardest cases. `&` `%` `#` `$` `_` escape to a simple
    backslash prefix; `{` `}` `\\` `~` `^` escape to macros
    (`\\{`, `\\textbackslash{}`, `\\textasciitilde{}`). The coverage was
    exactly inverted from the risk, and the test passed either way.

    Caught by `scripts/check_no_vacuous_tests.py` once it was taught to read
    Python -- it had been TypeScript-only, so this sat unexamined.
    """
    cited = CitedParameter(
        parameter="km",
        citation=Citation(source="BRENDA", reference_id="1", title=hostile),
    )
    out = to_bibtex([cited])
    title_line = next(l for l in out.splitlines() if l.strip().startswith("title ="))

    # Premise. Without it a parameter containing no special at all would
    # make every assertion below vacuous -- which is how this test spent its
    # life. `citeSeen`, one file over, exists for the same reason.
    present = [char for char in _BIBTEX_SPECIALS if char in hostile]
    assert present, f"{hostile!r} contains no BibTeX special; it tests nothing"

    # 1. Each special is rendered in its escaped form.
    for char in present:
        assert _BIBTEX_SPECIALS[char] in title_line, (char, title_line)

    # 2. And no BARE special survives. Asserted independently of the mapping
    #    table, because check 1 alone would agree with a mapping that
    #    replaced `&` with something harmless-looking that still left a bare
    #    `&` behind. Removing every known escaped form must leave a string
    #    with no specials in it.
    residue = title_line
    for replacement in sorted(_BIBTEX_SPECIALS.values(), key=len, reverse=True):
        residue = residue.replace(replacement, "")
    # The field's own `title = { ... },` braces are structure, not content.
    residue = residue.replace("title = {", "").rstrip("},")
    leftover = [char for char in _BIBTEX_SPECIALS if char in residue]
    assert not leftover, (
        f"unescaped {leftover} survived into {title_line!r}; a bare special "
        "makes the whole .bib file fail to parse"
    )


# ---------------------------------------------------------------------------
# The empty case is a fact, not a blank file
# ---------------------------------------------------------------------------

def test_no_citations_says_so_rather_than_emitting_nothing():
    """An empty .bib file is indistinguishable from a failed export. 'This
    run had no literature-backed values' is a different fact and the one
    that is true."""
    out = to_bibtex([])
    # Unwrapped, because the comment block is line-broken and the phrase
    # spans a newline. Asserting on the wrapped form would make every
    # rewrap a test failure.
    unwrapped = " ".join(out.replace("%", " ").split())
    assert "no literature-backed values" in unwrapped
    assert "@misc" not in out

    ris = to_ris([])
    assert "No literature-backed parameters" in ris
    assert "TY  - DATA" not in ris


# ---------------------------------------------------------------------------
# Format conformance
# ---------------------------------------------------------------------------

def test_ris_uses_crlf_and_terminates_every_record():
    """RIS is a CRLF format. LF-only output imports as one malformed
    record in several managers."""
    out = to_ris([KM, KI])
    assert "\r\n" in out
    # The property is that every record is TERMINATED, not that there are
    # exactly two. Counting entries made this test fail when the database
    # itself was added as a third record -- a correct change breaking a test
    # that had encoded the count instead of the invariant.
    assert out.count("TY  - ") == out.count("ER  - ")
    assert out.count("TY  - ") >= 2


def test_every_entry_carries_the_value_it_supports():
    """A citation detached from the number it backs is a reading list. The
    point of per-parameter provenance is the pairing."""
    out = to_bibtex([KM])
    assert "KM = 2.5 mM" in out
    assert "Homo sapiens" in out

    ris = to_ris([KM])
    assert "KM = 2.5 mM" in ris


def test_bibtex_braces_balance():
    """An unbalanced brace makes the file unparseable, and the failure
    surfaces in the user's reference manager rather than here."""
    out = to_bibtex([KM, KI, SAME_REFERENCE_AS_KM])
    # Count only structural braces: escaped ones are \{ and \}.
    stripped = re.sub(r"\\[{}]", "", out)
    assert stripped.count("{") == stripped.count("}")


# ---------------------------------------------------------------------------
# The database itself belongs in the bibliography
#
# NOTICE: "If you use BRENDA data in scientific work, cite BRENDA's current
# publication [...] Citing Terrium is not a substitute for citing BRENDA."
#
# The export emitted one record per parameter and no entry for BRENDA, so a
# student importing it into Zotero would not cite BRENDA -- in the one
# artifact whose whole purpose is to populate a bibliography.
# ---------------------------------------------------------------------------


def _brenda_param(parameter: str = "km") -> CitedParameter:
    return CitedParameter(
        parameter=parameter,
        citation=Citation(source="BRENDA", reference_id="740253"),
        value=10.73,
        unit="mM",
        organism="Homo sapiens",
    )


def test_the_bibliography_contains_the_database_not_only_its_records() -> None:
    bib = to_bibtex([_brenda_param()])
    assert "@misc{terrium-source-brenda," in bib
    assert "brenda-enzymes.org/references.php" in bib, (
        "the entry must carry the citation NOTICE asks users to make"
    )


def test_the_database_entry_invents_no_bibliographic_fields() -> None:
    """The module's central refusal, applied to the new entry.

    BRENDA's citation_request is an instruction and a URL, not a reference.
    Rendering it as `author`/`year`/`journal` would import cleanly, look
    complete, and be fiction.
    """
    bib = to_bibtex([_brenda_param()])
    entry = bib[bib.index("@misc{terrium-source-brenda,") :]
    entry = entry[: entry.index("\n}")]
    for invented in ("author =", "year =", "journal =", "volume ="):
        assert invented not in entry, f"{invented} was fabricated"
    assert "NOT guessed" in entry


def test_a_run_without_brenda_values_does_not_cite_brenda() -> None:
    """Same rule as every other export: credited only where it contributed.

    An entry for a database that supplied nothing would put a citation in
    someone's paper for data they did not use.
    """
    pubmed_only = CitedParameter(
        parameter="km",
        citation=Citation(source="PubMed", reference_id="34962677"),
        value=1.0,
    )
    assert "terrium-source-brenda" not in to_bibtex([pubmed_only])
    assert "TY  - DBASE" not in to_ris([pubmed_only])


def test_the_ris_export_carries_it_too() -> None:
    ris = to_ris([_brenda_param()])
    assert "TY  - DBASE" in ris
    assert "brenda-enzymes.org/references.php" in ris
    # RIS is CRLF, and the new record must be terminated like every other.
    assert "\r\n" in ris
    assert ris.count("TY  - ") == ris.count("ER  - ")


def test_the_database_entry_is_emitted_once_for_many_parameters() -> None:
    """Two BRENDA-resolved parameters are two records and one database."""
    bib = to_bibtex([_brenda_param("km"), _brenda_param("ki")])
    assert bib.count("@misc{terrium-source-brenda,") == 1
