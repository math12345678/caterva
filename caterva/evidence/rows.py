"""Rows as the literature layer's parser reads them, and the bytes that hold them.

WHY THE PARSER IS BORROWED, NOT REWRITTEN
-----------------------------------------
The resolver (Tests/fallback_logic.py) chooses among rows that
Tests/brenda_client.py parsed. A claim that the resolver "took this row"
must name a row the same parser yields, with the same value, commentary and
reference, or the claim is about a different reading of the page than the
one that was used. So `rows_from_page` calls the literature layer's own
parsers through `caterva.checkout.literature_module` (ADR 0178), with no
substrate filter and no organism default, and turns each entry into a Row
(claims.py). It records what the parser yielded: `value_text` is the
parser's float formatted with ".15g", not the cell's spelling, and the Row
says so in its docstring.

WHAT A LOCATOR IS
-----------------
    brenda:<ec>:<table>:<organism>:<substrate>:<reference>:<value_text>:<n>

`n` is the index among rows that share every preceding field, in parse
order, because the recorded hexokinase page lists one paper's value twice
in places (18 mM and 6 mM, ref 641068, one commentary) and a locator that
could name two rows would let a claim cite either. The structured fields on
the Row are the form to re-find by; the locator is one line for a reader.

CERTIFICATES
------------
`certificates_for` finds the row's bytes on the page. A BRENDA data row is

    <div id="tab12r4sr0" class="row rgrey2"> ... </div>      (shown)
    <div id="tab12r13sr112" class="hidden rgrey1"> ... </div> (hidden until expanded)

with one `<div id="...cN" class="cell"><span>text\\n</span>` per cell, so a
row is the bytes from one row opening (ROW_OPENING: a div whose id is
tabN_head, tabNrN or tabNrNsrN and whose class starts with "row" or
"hidden") to the next. Within the first such row that holds the reference id, the
value cell and the commentary, a certificate is issued per text found: the
reference id, the value text (or the cell text that parses to the same
number, when the cell spells it otherwise), the commentary, the substrate
and the organism. A text the row does not hold gets no certificate; a page
with no such row gets none at all, and the claim then cannot be cited
(claims.py refuses a cited claim without a certificate).

AMBIGUITY
---------
`find_row` applies the identity rule the compose layer uses everywhere
(`caterva/compose/narrowed.py` `same_row`: equal value, verbatim commentary,
equal reference when both have one). When more than one row matches it
returns the first in parse order and records the fact in AMBIGUITIES, so a
test or a report can see that the pick was by position; the checker
re-finds by locator, where the index makes the position explicit.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

try:
    from caterva.checkout import literature_module
    from caterva.evidence.claims import (
        PARSE_BRENDA_TABLE,
        QUANTITIES,
        Certificate,
        EvidenceRefused,
        Row,
        make_row,
    )
except ImportError:  # pragma: no cover - flat layout
    from checkout import literature_module  # type: ignore[no-redef]
    from evidence.claims import (  # type: ignore[no-redef]
        PARSE_BRENDA_TABLE,
        QUANTITIES,
        Certificate,
        EvidenceRefused,
        Row,
        make_row,
    )

#: Which brenda_client parser reads which table.
PARSERS = {
    "km": "parse_brenda_km_html",
    "kcat": "parse_brenda_turnover_html",
    "ki": "parse_brenda_ki_html",
}

#: The opening of a row on a BRENDA enzyme page (see module docstring). The
#: four shapes on the recorded hexokinase page, counted 2026-10-17:
#:   <div id="tab12_head" class="row">               a table's header row
#:   <div id="tab12r3" class="row rgrey1">           a shown row (one entry, or an aggregate)
#:   <div id="tab12r4sr0" class="row rgrey2">        a shown sub-row
#:   <div id="tab12r13sr112" class="hidden rgrey1">  a sub-row hidden until expanded
#: Cells are `<div id="tab12r4sr0c5" class="cell">`, whose ids end in cN, so
#: the id shape alone tells a row from a cell.
ROW_OPENING = re.compile(rb'<div id="tab\d+(?:_head|r\d+(?:sr\d+)?)" class="(?:row|hidden)[ "]')

#: A value cell's text, as the parser reads it (brenda_client: `^(\d+\.?\d*)$`).
_VALUE_CELL = re.compile(rb"<span>(\d+\.?\d*)\n</span>")

#: Notes of every ambiguous `find_row`, in order; "" when none happened.
AMBIGUITIES: list[str] = []

#: The organism segment of a locator when the parser read every organism.
ANY_ORGANISM = "any"


def value_text_of(value: float) -> str:
    """The decimal string this slice records for a parsed value."""
    return format(float(value), ".15g")


def locator_ec(locator: str) -> str | None:
    """The EC number a locator names, or None for a locator of another shape."""
    parts = str(locator).split(":")
    return parts[1] if len(parts) >= 8 and parts[0] == "brenda" and parts[1] else None


def _parse(html: str, *, ec: str, table: str, organism: str | None) -> list[Any]:
    if table not in QUANTITIES:
        raise EvidenceRefused(f"table {table!r} is not one of {QUANTITIES}")
    client = literature_module("brenda_client")
    parser = getattr(client, PARSERS[table])
    return parser(
        html, ec, [], target_organism=organism, require_substrate_match=False,
    )


def rows_from_entries(
    entries: Sequence[Any], *, ec: str, table: str, organism: str | None, snapshot_ref: str,
) -> list[Row]:
    """Rows from parsed BRENDAKmEntry objects, in parse order, with locators."""
    seen: dict[tuple, int] = {}
    rows: list[Row] = []
    for entry in entries:
        value_text = value_text_of(entry.km_value)
        row_organism = entry.organism or ANY_ORGANISM
        key = (ec, table, row_organism, entry.substrate, entry.reference_id, value_text)
        index = seen.get(key, 0)
        seen[key] = index + 1
        locator = ":".join([
            "brenda", ec, table, row_organism, str(entry.substrate),
            entry.reference_id or "none", value_text, str(index),
        ])
        rows.append(make_row(
            snapshot=snapshot_ref, parser=PARSE_BRENDA_TABLE, locator=locator, quantity=table,
            value_text=value_text, unit=str(entry.unit), substrate=str(entry.substrate),
            organism=row_organism, accession=entry.uniprot, commentary=entry.conditions,
            reference=entry.reference_id,
        ))
    return rows


def rows_from_page(
    html: str, *, ec: str, table: str, organism: str | None, snapshot_ref: str,
) -> list[Row]:
    """Every row of `table` on the page, for `organism` (None: every organism),
    as the literature layer's parser yields them, in parse order."""
    entries = _parse(html, ec=ec, table=table, organism=organism)
    return rows_from_entries(entries, ec=ec, table=table, organism=organism, snapshot_ref=snapshot_ref)


def parsed_rows(
    html: str, *, ec: str, table: str, organism: str | None, snapshot_ref: str,
) -> list[tuple[Any, Row]]:
    """`rows_from_page`, with each Row beside the parser's entry it was made
    from, for a caller that also needs the entry (evidence ordinals)."""
    entries = _parse(html, ec=ec, table=table, organism=organism)
    rows = rows_from_entries(entries, ec=ec, table=table, organism=organism, snapshot_ref=snapshot_ref)
    return list(zip(entries, rows))


def same_row(row: Row, *, value: float, commentary: str | None, reference: str | None) -> bool:
    """The compose layer's row identity: equal value, verbatim commentary,
    equal reference when both have one."""
    try:
        if float(row.value_text) != float(value_text_of(value)):
            return False
    except (TypeError, ValueError):
        return False
    if (row.commentary or None) != (commentary or None):
        return False
    return reference is None or row.reference is None or str(reference) == row.reference


def find_row(
    rows: Sequence[Row], *, value: float, commentary: str | None, reference: str | None,
) -> Row | None:
    """The first row matching the identity rule, or None; an ambiguity is noted."""
    matches = [r for r in rows if same_row(r, value=value, commentary=commentary, reference=reference)]
    if not matches:
        return None
    if len(matches) > 1:
        AMBIGUITIES.append(
            f"find_row: {len(matches)} rows match value={value!r} commentary={commentary!r} "
            f"reference={reference!r}; the first in parse order was returned: "
            + ", ".join(r.locator for r in matches)
        )
    return matches[0]


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

def _row_bounds(page: bytes) -> list[int]:
    return [m.start() for m in ROW_OPENING.finditer(page)]


def _region_of(offset: int, starts: list[int], length: int) -> tuple[int, int] | None:
    """The [start, end) of the row that holds byte `offset`, or None outside every row."""
    index = bisect_right(starts, offset) - 1
    if index < 0:
        return None
    start = starts[index]
    end = starts[index + 1] if index + 1 < len(starts) else length
    return start, end


def _cell_text(page: bytes, text: str, start: int, end: int) -> tuple[int, int] | None:
    """The span of `text` where it is a cell's whole text: right after a `>`
    and right before the cell's newline or closing tag. A substring inside a
    tag or inside a longer text is not the row saying that text."""
    needle = text.encode("utf-8")
    at = page.find(b">" + needle, start, end)
    while at >= 0:
        after = at + 1 + len(needle)
        if page[after:after + 1] in (b"\n", b"<"):
            return at + 1, after
        at = page.find(b">" + needle, at + 1, end)
    return None


def _value_span(page: bytes, value_text: str, start: int, end: int) -> tuple[tuple[int, int], str] | None:
    """The value cell: the exact text first, else a cell that spells the same number."""
    exact = page.find(b"<span>" + value_text.encode("utf-8") + b"\n</span>", start, end)
    if exact >= 0:
        at = exact + len(b"<span>")
        return (at, at + len(value_text.encode("utf-8"))), value_text
    for match in _VALUE_CELL.finditer(page, start, end):
        cell = match.group(1).decode("ascii")
        try:
            if float(cell) == float(value_text):
                return (match.start(1), match.end(1)), cell
        except ValueError:
            continue
    return None


def _anchors(page: bytes, row: Row) -> list[int]:
    """Offsets to start from: the reference id as link text, else the
    commentary, else the value cell. The most specific text available."""
    if row.reference:
        needle = b">" + row.reference.encode("utf-8") + b"</a>"
    elif row.commentary:
        needle = row.commentary.encode("utf-8")
    else:
        needle = b"<span>" + row.value_text.encode("utf-8") + b"\n</span>"
    found = []
    at = page.find(needle)
    while at >= 0:
        found.append(at)
        at = page.find(needle, at + 1)
    return found


def certificates_for(row: Row, page_bytes: bytes) -> tuple[Certificate, ...]:
    """Byte spans in `page_bytes` for the row's reference id, value, commentary,
    substrate and organism, all within one table row; () when no row of the
    page holds the reference, the value and the commentary together."""
    page = bytes(page_bytes)
    starts = _row_bounds(page)
    tried: set[tuple[int, int]] = set()
    for anchor in _anchors(page, row):
        region = _region_of(anchor, starts, len(page))
        if region is None or region in tried:
            continue
        tried.add(region)
        start, end = region
        reference = _cell_text(page, row.reference, start, end) if row.reference else None
        if row.reference and reference is None:
            continue
        value = _value_span(page, row.value_text, start, end)
        if value is None:
            continue
        commentary = _cell_text(page, row.commentary, start, end) if row.commentary else None
        if row.commentary and commentary is None:
            continue
        found: list[Certificate] = []
        if reference is not None:
            found.append(Certificate(row.snapshot, reference, row.reference))
        found.append(Certificate(row.snapshot, value[0], value[1]))
        if commentary is not None:
            found.append(Certificate(row.snapshot, commentary, row.commentary))
        for text in (row.substrate, row.organism if row.organism != ANY_ORGANISM else None):
            if text:
                span = _cell_text(page, text, start, end)
                if span is not None:
                    found.append(Certificate(row.snapshot, span, text))
        return tuple(found)
    return ()


# ---------------------------------------------------------------------------
# Evidence ordinals, for settings["ordinals"]
# ---------------------------------------------------------------------------

#: The resolver's own axes (Tests/evidence_rank.py `profile`), as ordinals,
#: higher is better. The names are the axes' names there.
PROFILE_AXES = ("assay_completeness", "variant_statement", "organism_match")

#: The reliability grades the resolver's frontier dicts carry
#: (`grades{assay_completeness, condition_proximity, organism_match}`,
#: Tests/reliability.py), as ordinals, higher is better. "not_assessed" is
#: not in a scale: it becomes None, which a checker skips rather than scores,
#: as evidence_rank's `dominates` skips an axis it cannot compare. "unknown"
#: (a cross-species row with no relatedness verdict) shares the lowest rank
#: with "distant" for the reason evidence_rank gives: an unanswered question
#: cannot beat or lose to a fact, so it does not get a rank of its own.
GRADE_SCALES: Mapping[str, Mapping[str, int]] = {
    "assay_completeness": {"absent": 0, "partial": 1, "complete": 2},
    "condition_proximity": {"far": 0, "near": 1},
    "organism_match": {"unknown": 0, "distant": 0, "related": 1, "exact": 2},
}


def ordinals_from_profile(profile: Any) -> dict[str, str | None]:
    """The three comparable ordinals of an `EvidenceProfile`, as decimal strings."""
    values = tuple(profile.ordinals())[:3]
    return {
        name: (None if value is None else str(int(value)))
        for name, value in zip(PROFILE_AXES, values)
    }


def ordinals_from_grades(grades: Mapping[str, Any]) -> dict[str, str | None]:
    """A frontier dict's `grades` as ordinals; a grade outside its scale is None."""
    out: dict[str, str | None] = {}
    for name, scale in GRADE_SCALES.items():
        grade = grades.get(name)
        out[name] = str(scale[grade]) if grade in scale else None
    return out


__all__ = [
    "AMBIGUITIES",
    "ANY_ORGANISM",
    "GRADE_SCALES",
    "PARSERS",
    "PROFILE_AXES",
    "ROW_OPENING",
    "certificates_for",
    "find_row",
    "locator_ec",
    "ordinals_from_grades",
    "ordinals_from_profile",
    "parsed_rows",
    "rows_from_entries",
    "rows_from_page",
    "same_row",
    "value_text_of",
]
