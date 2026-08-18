"""Export every source behind a run in a format a reference manager reads.

WHY THIS EXISTS
---------------
Daniel S. Katz (NCSA; co-founder of JOSS), asked whether attaching a
citation to every resolved parameter was novel, replied:

    "I don't really understand the idea of per constant citation. Most
     constants are well known and are not typically cited."

He is right about constants and was describing something Terrium does not
do — the wording was ours, and ADR 0024 records the language fix. But there
is a second, sharper reading of his reply that is not a misunderstanding at
all:

    a citation nobody can act on is not a citation.

Terrium was attaching provenance to every number and then offering it only
as prose on a terminal. From the software-citation perspective Katz works
in, that is not a citation; it is a claim about one. A citation is something
that goes into a bibliography.

So this module emits BibTeX and RIS — the two formats every reference
manager (Zotero, Mendeley, EndNote, JabRef) imports. A student who runs a
simulation can now put the sources of their parameters into the same
bibliography as the papers they read.

WHAT IT REFUSES TO DO
---------------------
It does not invent bibliographic fields.

A BibTeX entry wants author, title, journal and year. BRENDA gives Terrium a
reference id and, sometimes, a title; PubMed gives a PMID. Filling the rest
with plausible-looking values would produce an entry that imports cleanly,
looks complete, and is fiction — the single most damaging thing this module
could do, because it would enter someone's bibliography and be cited onward
with Terrium's name attached to the fabrication.

Absent fields are omitted, and every entry carries a `note` saying exactly
what was and was not known, so the person can complete it deliberately
rather than trust it silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from citation import Citation

from Terium.core import data_sources

#: BibTeX keys must be ASCII-ish and free of the characters BibTeX treats as
#: syntax. Anything else is stripped rather than escaped: a key is an
#: identifier, not content, and an unparseable .bib file helps nobody.
_KEY_SAFE = re.compile(r"[^A-Za-z0-9_:-]")

#: Characters BibTeX treats as markup inside a field value.
_BIBTEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


@dataclass(frozen=True)
class CitedParameter:
    """One parameter and the source it came from."""

    parameter: str
    citation: Citation
    value: float | None = None
    unit: str | None = None
    organism: str | None = None


def _escape_bibtex(text: str) -> str:
    return "".join(_BIBTEX_SPECIALS.get(char, char) for char in text)


def _disambiguator(index: int) -> str:
    """0 -> 'a', 25 -> 'z', 26 -> 'aa', 27 -> 'ab'.

    The spreadsheet-column sequence, and the convention BibTeX styles
    already use for same-author-same-year keys, so the output looks like
    what a reader expects rather than like an escape.

    It replaces `chr(ord("a") + index)`, which ran off the end of the
    alphabet on the 27th collision and produced `{`, `|`, `}`, `~` -- see
    `bibtex_key` below.
    """
    out = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(ord("a") + remainder) + out
    return out


def bibtex_key(cited: CitedParameter, seen: set[str] | None = None) -> str:
    """A stable, unique, valid BibTeX key.

    Uniqueness is enforced against `seen` rather than assumed: two
    parameters resolved from the same BRENDA reference would otherwise emit
    two entries with the same key, and BibTeX silently keeps one of them.
    Silently keeping one is the failure that matters -- the bibliography
    would be short by an entry and nothing would say so.

    THE ENFORCEMENT USED TO BREAK WORSE THAN THE THING IT PREVENTS
    --------------------------------------------------------------
    The suffix was `chr(ord("a") + n)`, walking the ASCII table. Past `z`
    that is `{`, `|`, `}`, `~`. Measured, with 30 parameters sharing one
    BRENDA reference:

        @misc{brenda740253z,
        @misc{brenda740253{,
        @misc{brenda740253|,
        @misc{brenda740253},

    The third opens a group that never closes. The fourth **closes the
    `@misc{` group early**, so BibTeX reads a complete empty entry and then
    tries to parse the rest of the body at top level -- one duplicate key
    costs one entry, whereas this corrupts the parse of everything after
    it. The guard against silent loss was, past 26, a louder way to lose
    more.

    Reachable, not theoretical: `scripts/export_citations.py` builds this
    list from a JSON payload of arbitrary length, and one BRENDA reference
    routinely supplies several constants for the same enzyme.

    `test_keys_are_valid_bibtex_identifiers` already asserted exactly the
    right property -- `[A-Za-z0-9_:-]+` -- on three parameters, which
    reaches at most one collision. The property was right and the input
    could not exercise it.
    """
    source = _KEY_SAFE.sub("", (cited.citation.source or "source").lower())
    ident = _KEY_SAFE.sub("", cited.citation.reference_id or "")
    stem = f"{source}{ident}" if ident else f"{source}_{cited.parameter.lower()}"

    if seen is None:
        return stem

    # BOUNDED, not `while key in seen`.
    #
    # The unbounded version was correct with a correct `_disambiguator` and
    # hung with a broken one -- found by mutation: making the suffix cycle
    # a..z..a instead of carrying to `aa` did not fail the suite, it stopped
    # the test run dead, because every candidate past the 26th was already
    # in `seen`. A hang in a path driven by a JSON payload is worse than a
    # wrong key: nothing is reported at all.
    #
    # `len(seen) + 1` candidates are always enough when the suffixes are
    # distinct -- one of them must be unused -- so exhausting the range
    # means `_disambiguator` has stopped being injective, which is a bug in
    # this module and says so.
    for index in range(len(seen) + 1):
        key = stem if index == 0 else f"{stem}{_disambiguator(index - 1)}"
        if key not in seen:
            seen.add(key)
            return key

    raise RuntimeError(
        f"could not find an unused BibTeX key for {stem!r} in "
        f"{len(seen) + 1} attempts. That is only possible if the "
        "disambiguating suffixes have stopped being distinct, which would "
        "silently merge two entries into one."
    )


#: The bibliographic fields a BibTeX entry wants, in the order a reader
#: expects to see them named.
#:
#: Asked of the citation rather than assumed. The previous version built its
#: "missing" list from a tuple of hardcoded `None`s:
#:
#:     [field for field, value in (("author", None), ("year", None),
#:                                ("journal", None)) if value is None]
#:
#: which can only ever return all three. A constant wearing the costume of a
#: computation -- and it produced two false notes, one in each direction.
#: `title` IS sometimes known and IS emitted, so an entry carrying a title
#: still said Terrium "records the source identifier only"; and an entry
#: with NO title listed author, year and journal as absent while saying
#: nothing about the field a reference manager displays first.
_BIBTEX_WANTS = ("author", "year", "journal", "title")


def _known_and_missing(citation: Citation) -> tuple[list[str], list[str]]:
    """Which wanted fields this citation actually carries, and which it does not.

    `getattr` rather than a literal list: `Citation` today has a `title`
    field and no author, year or journal, so the answer is the same one the
    old constant gave for three of the four. The difference is that this
    asks. If `Citation` ever gains a `year`, the note starts telling the
    truth about it instead of continuing to say it is unknown.
    """
    known, missing = [], []
    for field in _BIBTEX_WANTS:
        (known if getattr(citation, field, None) else missing).append(field)
    return known, missing


def _note_for(cited: CitedParameter) -> str:
    """What was and was not known, stated on the entry itself."""
    parts = [f"Resolved by Terrium as the {cited.parameter.upper()}"]
    if cited.value is not None:
        parts[0] += f" = {cited.value}{(' ' + cited.unit) if cited.unit else ''}"
    if cited.organism:
        parts.append(f"measured in {cited.organism}")

    known, missing = _known_and_missing(cited.citation)
    records = (
        f"Terrium records the source identifier and the {', '.join(known)}"
        if known
        else "Terrium records the source identifier only"
    )
    parts.append(
        f"{records}; "
        f"{', '.join(missing)} are NOT known to it and have been omitted "
        "rather than guessed. Complete them from the source before citing"
    )
    # Each part is a clause without terminal punctuation, so joining adds
    # exactly one period per sentence. The previous version appended a
    # period to a part that already ended in one and produced ". .".
    return ". ".join(part.rstrip(". ") for part in parts) + "."


def contributing_sources(parameters: list[CitedParameter]) -> list:
    """The described data sources that supplied a value in this run.

    WHY THE DATABASE GETS ITS OWN ENTRY
    -----------------------------------
    `NOTICE` is unambiguous:

        If you use BRENDA data in scientific work, cite BRENDA's current
        publication [...] Citing Terrium is not a substitute for citing
        BRENDA.

    The export emitted one record per parameter -- `howpublished = {BRENDA
    database record}` -- and no entry for BRENDA itself. A student importing
    this into Zotero got the records and not the database, so they would not
    cite BRENDA. In the one artifact whose entire purpose is to populate a
    bibliography, the citation the source actually asks for was the one
    thing missing.

    Read from `docs/data-sources.json`, the same table the exported model,
    SBML and CSV read (ADR 0079), so the request cannot drift between them.

    Only sources that supplied a value appear. An entry for a database that
    contributed nothing would put a citation in someone's paper for data
    they did not use.
    """
    labels = {
        f"{cited.citation.source} {cited.citation.reference_id or ''}".lower()
        for cited in parameters
    }
    return [
        source
        for source in data_sources.SOURCES
        if source.citation_request
        and any(
            token in label for label in labels for token in source.tokens
        )
    ]


def _source_entry_note(source) -> str:
    """What is known about the database entry, and what is not.

    No author, year, volume or title is emitted. BRENDA's `citation_request`
    is an instruction and a URL -- *"cite BRENDA's current publication, see
    .../references.php"* -- not a reference. Rendering it as one would
    fabricate a bibliographic record, which is the single thing this module
    refuses to do, and a fabricated entry is worse here than a missing one
    because it imports cleanly and looks complete.
    """
    return (
        f"The database this run drew values from. {source.citation_request}. "
        "Terrium does not record that publication's author, year or volume "
        "and has NOT guessed them -- look it up and complete this entry "
        "before submitting. Licensed under "
        f"{source.licence or 'terms Terrium has not recorded'}"
        + (f" ({source.licence_uri})" if source.licence_uri else "")
    )


def to_bibtex(parameters: list[CitedParameter]) -> str:
    """A .bib document for every cited parameter.

    Entry type is `@misc`, deliberately. `@article` would assert that the
    source is a journal article, which Terrium does not know: a BRENDA
    reference id identifies a record, and the record may be a paper, a
    chapter or a submission. Asserting a publication type nobody verified
    is the same class of error as asserting an author.
    """
    if not parameters:
        return (
            "% No parameter in this run carried a citation.\n"
            "% This is not an empty bibliography -- it is a run with no\n"
            "% literature-backed values, which is a different fact.\n"
        )

    seen: set[str] = set()
    # The header is ONE block, joined with single newlines. Building it as
    # separate list items meant the "\n\n".join below put a blank line
    # between every comment line -- valid BibTeX, and an eyesore in a file
    # someone is about to paste into a bibliography.
    header = "\n".join(
        [
            "% Generated by Terrium. One entry per literature-backed parameter.",
            "%",
            "% Author, year and journal are ABSENT, not omitted for brevity:",
            "% Terrium resolves a source identifier and does not fabricate the",
            "% rest of a bibliographic record. Complete each entry from its",
            "% source before citing it.",
        ]
    )
    blocks: list[str] = [header]

    for cited in parameters:
        key = bibtex_key(cited, seen)
        fields: list[tuple[str, str]] = []

        if cited.citation.title:
            fields.append(("title", cited.citation.title))
        fields.append(("howpublished", f"{cited.citation.source} database record"))
        if cited.citation.reference_id:
            fields.append(
                (f"{cited.citation.source.lower()}-reference", cited.citation.reference_id)
            )
        if cited.citation.url:
            fields.append(("url", cited.citation.url))
        fields.append(("note", _note_for(cited)))

        body = ",\n".join(
            f"  {name} = {{{_escape_bibtex(value)}}}" for name, value in fields
        )
        blocks.append(f"@misc{{{key},\n{body}\n}}")

    # The databases themselves, after the records they supplied.
    for source in contributing_sources(parameters):
        name = source.tokens[0]
        fields = [
            ("title", f"{name.upper()} — the database these values came from"),
            ("howpublished", source.creator),
        ]
        if source.source_uri:
            fields.append(("url", source.source_uri))
        fields.append(("note", _source_entry_note(source)))
        body = ",\n".join(
            f"  {field} = {{{_escape_bibtex(value)}}}" for field, value in fields
        )
        blocks.append(f"@misc{{terrium-source-{name},\n{body}\n}}")

    return "\n\n".join(blocks) + "\n"


def to_ris(parameters: list[CitedParameter]) -> str:
    """The same records as RIS.

    RIS is what EndNote and older Zotero imports prefer. Type is `DATA`
    rather than `JOUR`, for the same reason the BibTeX entry is `@misc`.
    """
    if not parameters:
        return (
            "TY  - GEN\r\n"
            "TI  - No literature-backed parameters in this run\r\n"
            "N1  - Terrium resolved no value carrying a citation. This is a "
            "run with no literature-backed values, not an empty export.\r\n"
            "ER  - \r\n"
        )

    lines: list[str] = []
    for cited in parameters:
        lines.append("TY  - DATA")
        if cited.citation.title:
            lines.append(f"TI  - {cited.citation.title}")
        else:
            lines.append(
                f"TI  - {cited.citation.source} record "
                f"{cited.citation.reference_id or '(no identifier)'}"
            )
        lines.append(f"DB  - {cited.citation.source}")
        if cited.citation.reference_id:
            lines.append(f"AN  - {cited.citation.reference_id}")
        if cited.citation.url:
            lines.append(f"UR  - {cited.citation.url}")
        if cited.organism:
            lines.append(f"KW  - {cited.organism}")
        lines.append(f"N1  - {_note_for(cited)}")
        lines.append("ER  - ")
        lines.append("")

    # The databases themselves, for the same reason as the BibTeX side: the
    # per-record entries are the values, not the source NOTICE asks be cited.
    for source in contributing_sources(parameters):
        lines.append("TY  - DBASE")
        lines.append(
            f"TI  - {source.tokens[0].upper()} — the database these values "
            "came from"
        )
        lines.append(f"DB  - {source.tokens[0].upper()}")
        if source.source_uri:
            lines.append(f"UR  - {source.source_uri}")
        lines.append(f"N1  - {_source_entry_note(source)}")
        lines.append("ER  - ")
        lines.append("")

    # RIS is a CRLF format. Emitting LF produces a file some managers
    # import as a single malformed record.
    return "\r\n".join(lines)
