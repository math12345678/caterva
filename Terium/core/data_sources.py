"""Who licensed the data in a generated model, stated inside the model.

WHY THIS EXISTS
---------------
Dr Lisa Jeske (BRENDA / Leibniz Institute DSMZ) raised BRENDA's CC BY 4.0
licence obligations directly. `NOTICE` answers them thoroughly at the
repository level: licensor, copyright, licence URI, warranty disclaimer, the
modifications Terrium makes, and how to cite BRENDA.

**`NOTICE` stays in the repository. The model file leaves.**

The artifact a student actually shares -- the Antimony file they attach to a
lab report, email to a demonstrator, or commit alongside a paper -- carried
BRENDA-derived values, named BRENDA as `BRENDA ref 740253`, and said nothing
about who licensed it or under what terms. The attribution existed where a
lawyer would look and not where the data went. The same last-mile shape this
project keeps finding (ADR 0027, 0038, 0039, 0047), applied to a licence
obligation instead of a computation.

WHAT CC BY 4.0 ACTUALLY REQUIRES
--------------------------------
Read from the legal code, not from memory
(https://creativecommons.org/licenses/by/4.0/legalcode.en):

  §3(a)(1)(A)  when Sharing the Licensed Material, retain -- if supplied by
               the licensor -- identification of the creator, a copyright
               notice, a notice referring to the licence, a notice referring
               to the warranty disclaimer, and a URI to the material.
  §3(a)(1)(B)  indicate if you modified it.
  §3(a)(1)(C)  indicate the material is licensed under CC BY 4.0 and include
               the licence text or a URI to it.
  §3(a)(2)     "You may satisfy the conditions [...] in any reasonable
               manner based on the medium, means, and context [...]. For
               example, it may be reasonable to satisfy the conditions by
               providing a URI or hyperlink to a resource that includes the
               required information."

§3(a)(2) is what makes a comment header the right size for this. The block
below carries the creator, the licence, and two URIs -- one to the licence
and one to the fuller notice -- rather than inlining several pages of NOTICE
into every model file.

WHAT THIS DELIBERATELY DOES NOT CLAIM
-------------------------------------
**Not that the obligation certainly applies.** Whether a handful of numeric
values is "the Licensed Material" at all is genuinely unsettled: bare facts
are not copyrightable in the United States, and §4(c) conditions the sui
generis database-right obligation on Sharing "all or a substantial portion
of the contents". Four Km values are not a substantial portion of BRENDA.

So this is not compliance theatre performed under legal certainty. It is the
cheap, correct thing to do when the answer is unclear, and it is also the
*scientific* courtesy Jeske was asking for independently of the licence.
Saying which of those two it is, rather than implying a legal conclusion
nobody here is qualified to reach, is the honest framing.

**Not that the licensor endorses the model.** CC BY 4.0 §2(a)(6):

    "Nothing in this Public License constitutes or may be construed as
     permission to assert or imply that You are [...] connected with, or
     sponsored, endorsed, or granted official status by, the Licensor"

This matters more here than boilerplate usually does. A researcher already
read a Terrium outreach email as claiming credit that was not ours, and an
attribution block naming DSMZ next to Terrium's generated numbers is exactly
the shape that misreads. So the block states the non-endorsement explicitly
rather than relying on a reader to infer it.

NOTHING HERE IS ASSERTED WITHOUT THE DATA TO BACK IT
----------------------------------------------------
`attribution_lines` emits a source's block only when a parameter in *this
model* actually came from that source. A model built entirely from
user-supplied values names nobody.

That is not tidiness. Naming BRENDA on a model BRENDA contributed nothing to
is a false statement about provenance, which is the defect class this whole
project is organised around -- and under §2(a)(6) it is also the precise
thing the licence forbids implying.

A source that appears in the provenance but is not described here produces a
line saying so, never silence. "We do not know the terms" and "there are no
terms" must not look alike.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class DataSource:
    """Everything CC BY §3(a)(1) asks to be retained, for one source.

    Fields map onto the licence clauses one-for-one so that a reader can
    check the block against the legal code rather than against taste.
    """

    #: Token(s) that identify this source in a provenance record. Matched
    #: case-insensitively against the `source` and `citation` fields.
    tokens: tuple[str, ...]

    #: §3(a)(1)(A)(i) -- identification of the creator.
    creator: str

    #: §3(a)(1)(A)(v) -- a URI to the Licensed Material.
    source_uri: str

    #: §3(a)(1)(C) -- the licence, and a URI to its text. `None` means the
    #: terms are not recorded here, which is reported rather than hidden.
    licence: str | None
    licence_uri: str | None

    #: §3(a)(1)(B) -- what Terrium does to the data. Kept short; NOTICE
    #: carries the full list, and `notice_uri` points at it.
    modifications: str

    #: Where the full attribution lives, per §3(a)(2).
    notice_uri: str

    #: How the source asks to be cited in scientific work. Distinct from the
    #: licence obligation: citing Terrium is not citing BRENDA.
    citation_request: str | None = None


#: The one place the attribution facts live: `docs/data-sources.json`.
#:
#: WHY A DATA FILE RATHER THAN A LITERAL HERE
#: The Antimony and SBML exports are built in Python; the trajectory CSV is
#: built in TypeScript. All three carry BRENDA-derived values and all three
#: owe the same attribution. A second copy of the licence in TypeScript
#: would be ADR 0003 (two copies of a numeric bound, drifted) and ADR 0027
#: (one score implemented twice, computing different things) with a licence
#: attached -- and a licence is a worse thing to be wrong about, because the
#: failure is silent and the party harmed is not the person running the code.
#:
#: Both languages read this file. Neither owns it. It is not generated, so
#: it is not build output committed to git either.
#:
#: `NOTICE` stays authoritative prose; every field here is transcribed from
#: it, and `scripts/check_data_source_attribution.py` fails when the two
#: disagree.
SOURCES_FILE = (
    pathlib.Path(__file__).resolve().parents[2] / "docs" / "data-sources.json"
)


def _load_sources(path: pathlib.Path | None = None) -> tuple[DataSource, ...]:
    """Read the table, refusing to degrade quietly if it cannot be read.

    A missing or malformed file raises. The alternative -- returning an empty
    tuple -- would silently stop crediting every source while every test
    about "a model with no resolved values credits nobody" kept passing, and
    the first sign would be an exported model with no licence on it.
    """
    location = path or SOURCES_FILE
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"The data-source table {location} is missing. Terrium cannot "
            "state who licensed the data it redistributes, so it refuses to "
            "export rather than export without attribution."
        ) from exc

    entries = raw.get("sources")
    if not entries:
        raise ValueError(
            f"{location} lists no sources. An empty table would silently "
            "strip attribution from every export."
        )

    return tuple(
        DataSource(
            tokens=tuple(entry["tokens"]),
            creator=entry["creator"],
            source_uri=entry.get("source_uri", ""),
            licence=entry.get("licence"),
            licence_uri=entry.get("licence_uri"),
            modifications=entry.get("modifications", ""),
            notice_uri=entry.get("notice_uri", ""),
            citation_request=entry.get("citation_request"),
        )
        for entry in entries
    )


SOURCES: tuple[DataSource, ...] = _load_sources()


def _describes(source: DataSource, haystack: str) -> bool:
    return any(token in haystack for token in source.tokens)


def sources_used(provenance) -> tuple[tuple[DataSource | None, str], ...]:
    """Which described sources contributed to *this* model, plus the rest.

    Returns `(source_or_None, label)` pairs. A `None` source means the
    provenance names something this module has no licence record for --
    reported, not dropped, because an unrecorded licence and no licence must
    never render the same.

    Reads the same `source` and `citation` fields the annotator already
    writes into the file, so a source can only be credited here if it is
    visible to a reader there. An attribution derived from a channel the
    reader cannot check is a claim, not a citation.
    """
    labels: dict[str, None] = {}
    for entry in provenance.values():
        for field_name in ("source", "citation"):
            value = getattr(entry, field_name, None)
            if isinstance(value, str) and value.strip():
                labels[value.strip()] = None

    described: dict[int, DataSource] = {}
    unknown: dict[str, None] = {}
    for label in labels:
        lowered = label.lower()
        match = next((s for s in SOURCES if _describes(s, lowered)), None)
        if match is not None:
            described[id(match)] = match
        elif _looks_like_a_database_reference(lowered):
            unknown[label] = None

    ordered = [
        (source, source.creator)
        for source in SOURCES
        if id(source) in described
    ]
    ordered += [(None, label) for label in sorted(unknown)]
    return tuple(ordered)


def _looks_like_a_database_reference(label: str) -> bool:
    """Whether a provenance label names an external source at all.

    `origin: user` and `model structure: fixed by the model definition` are
    not databases and must not produce an "unknown licence" warning -- a
    guard that cries wolf on the common case gets switched off, which is the
    reasoning ADR 0028 used for buffer strings.

    The test is deliberately narrow: a label naming a reference id or a URL
    is a source, anything else is not.
    """
    if "://" in label:
        return True
    return "ref" in label.split() or any(
        part.isdigit() and len(part) >= 4 for part in label.replace(":", " ").split()
    )


#: The standing text, in one place.
#:
#: Antimony takes it as `//` comments and SBML as XHTML `<notes>`. Writing
#: it twice would be two statements of one thing that drift -- the defect
#: `check_data_source_attribution.py` exists to catch between this module
#: and NOTICE, and it would be no better inside this module than across it.
PREAMBLE = (
    "Values in this model were resolved from the sources below. They are "
    "credited here because the model travels without the repository that "
    "documents them.",
    "None of these sources produced, reviewed or endorsed this model. "
    "Terrium selected and combined the values; any error in doing so is "
    "Terrium's, not theirs.",
)

HEADING = "DATA SOURCES AND THEIR LICENCES"

#: What a source with no licence record gets. Never silence: "we do not
#: know the terms" and "there are no terms" must not render alike.
UNRECORDED = (
    "licence: NOT RECORDED by Terrium. Check the source's own terms "
    "before redistributing this file."
)


def attribution_fields(provenance) -> list[tuple[str, list[tuple[str, str]]]]:
    """The attribution as data: `(subject, [(label, value), ...])` per source.

    Both renderers below consume this, so the Antimony comment block and the
    SBML notes cannot come to say different things about the same licence.
    """
    blocks: list[tuple[str, list[tuple[str, str]]]] = []
    for source, label in sources_used(provenance):
        if source is None:
            blocks.append((label, [("licence", UNRECORDED)]))
            continue

        licence = source.licence or "NOT RECORDED by Terrium"
        if source.licence and source.licence_uri:
            licence = f"{source.licence} ({source.licence_uri})"

        fields = [("licence", licence)]
        if source.source_uri:
            fields.append(("source", source.source_uri))
        fields.append(("changes", source.modifications))
        if source.citation_request:
            fields.append(("cite", source.citation_request))
        fields.append(
            ("full attribution and warranty disclaimer", source.notice_uri)
        )
        blocks.append((source.creator, fields))
    return blocks


def attribution_lines(provenance, comment: str = "//") -> list[str]:
    """Comment lines crediting the sources this model actually used.

    Empty when no described source contributed. A model built from
    user-supplied values gets no attribution block, because there is nobody
    to attribute and a block naming BRENDA anyway would be false.
    """
    blocks = attribution_fields(provenance)
    if not blocks:
        return []

    lines = [
        "",
        f"{comment} " + "-" * 68,
        f"{comment} {HEADING}",
        f"{comment} " + "-" * 68,
    ]
    for paragraph in PREAMBLE:
        lines.append(f"{comment}")
        lines += _wrap_block(paragraph, comment, " ")

    for subject, fields in blocks:
        lines.append(f"{comment}")
        lines += _wrap_block(subject, comment, " ")
        for label, value in fields:
            lines += _field(comment, label, value)

    lines.append(f"{comment} " + "-" * 68)
    return lines


def attribution_xhtml(provenance) -> str:
    """The same attribution as an SBML `<notes>` body, or `""` if none.

    SBML is the format that travels furthest -- a student's model opened in
    COPASI or Tellurium months later -- and `build_sbml` strips the Antimony
    comments before converting, deliberately, so the credit has to be put
    back in SBML's own idiom rather than carried across.

    Notes, not a model-level CVTerm. A `bqmodel:isDescribedBy` pointing at
    BRENDA would assert that BRENDA describes *this model*, which is false
    and is the endorsement CC BY 4.0 2(a)(6) forbids implying. The
    per-parameter CVTerms already carry the machine-readable identity of
    each value; this is the human-readable credit for the file as a whole.
    """
    blocks = attribution_fields(provenance)
    if not blocks:
        return ""

    parts = [f"<h1>{_escape(HEADING)}</h1>"]
    parts += [f"<p>{_escape(paragraph)}</p>" for paragraph in PREAMBLE]
    for subject, fields in blocks:
        parts.append(f"<p><strong>{_escape(subject)}</strong></p>")
        items = "".join(
            f"<li>{_escape(label)}: {_escape(value)}</li>"
            for label, value in fields
        )
        parts.append(f"<ul>{items}</ul>")
    body = "".join(parts)
    return f'<notes><body xmlns="http://www.w3.org/1999/xhtml">{body}</body></notes>'


def _escape(text: str) -> str:
    """XML-escape. A licence notice that breaks the file it is in helps
    nobody, and `&` appears in real institution names."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _field(comment: str, name: str, text: str) -> list[str]:
    """One labelled field, wrapped so no line runs past a terminal width."""
    prefix = f"   {name}:  "
    return _wrap_block(text, comment, prefix)


def _wrap_block(text: str, comment: str, prefix: str) -> list[str]:
    width = 70 - len(prefix)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    pad = " " * len(prefix)
    return [
        f"{comment}{prefix if index == 0 else pad}{line}"
        for index, line in enumerate(lines)
    ]
