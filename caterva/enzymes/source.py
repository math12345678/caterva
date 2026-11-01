"""Read the ExPASy ENZYME flat files into plain records.

WHY THIS EXISTS
---------------
Caterva turns an enzyme NAME into an EC number, and an EC number is the
identity of the protein every citation downstream refers to. The name-to-EC
step used to be a UniProt phrase search that returned bare EC numbers in
relevance order. It never consulted the nomenclature that defines which name
belongs to which number, so it could not tell an accepted name from a passing
mention, and it had nothing to show a person who had to choose.

The IUBMB nomenclature, as distributed by the SIB Swiss Institute of
Bioinformatics in the ExPASy ENZYME database (`enzyme.dat` and
`enzclass.txt`, CC BY 4.0), is that authority. This module only reads its
two files. `scripts/build_enzyme_index.py` turns the result into the compact
index the finder ships with, and nothing at query time reads these files.

THE FORMAT, AS READ FROM THE FILE
---------------------------------
Records end with a line `//`. Each line starts with a two-letter code and
three spaces:

    ID   1.1.1.27                 the EC number (some are `1.1.1.n1`)
    DE   L-lactate dehydrogenase. the accepted name
    AN   L-lactic acid dehydrogenase.   one alternative name per entry
    CA   (S)-lactate + NAD(+) = pyruvate + NADH + H(+).   a reaction
    CC   -!- comment text            comments; not used here
    DR   P00338, LDHA_HUMAN;  P07195, LDHB_HUMAN;   UniProt entries

`DE`, `AN` and `CA` may wrap over several lines. A name or a reaction ends
with a full stop, so a line that does not end with one continues on the next
line; a line ending in a hyphen continues without a space, because the break
fell inside a hyphenated word. The file header is a block of `CC` lines
before the first `//`.

A record with no name says what happened to the number instead:
`DE   Transferred entry: 1.1.1.303 and 1.1.1.304.` or `DE   Deleted entry.`.
Those are kept as a status, never as a name, so a transferred number can
never match a query by its "name".

WHAT THIS DOES NOT DO
---------------------
Guess. A line it cannot read is skipped and counted, and the caller sees
the count, so a format change shows up as a number rather than as quietly
missing enzymes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

#: `1.1.1.27`, `1.1.1.n1`, and the partial forms used inside transfer notes.
EC_PATTERN = re.compile(r"\d+\.\d+\.\d+\.(?:n?\d+|-)")

ACTIVE = "active"
TRANSFERRED = "transferred"
DELETED = "deleted"


@dataclass
class EnzymeRecord:
    """One ID block of enzyme.dat."""

    ec: str
    name: str = ""
    alternative_names: List[str] = field(default_factory=list)
    reaction: str = ""
    status: str = ACTIVE
    #: For a transferred entry, the numbers it moved to.
    superseded_by: List[str] = field(default_factory=list)
    #: (UniProt accession, entry name) pairs, in file order.
    entries: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class ParsedEnzymeFile:
    release: str
    records: List[EnzymeRecord]
    #: Lines that carried a known code but could not be read.
    skipped_lines: int = 0


def _join(lines: Iterable[str]) -> str:
    """Join wrapped lines: a hyphen at the end of a line continues the word."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-"):
            out += line
        elif out:
            out += " " + line
        else:
            out = line
    return out


def _entries_of(lines: Iterable[str]) -> Tuple[List[Tuple[str, str]], int]:
    """`P00338, LDHA_HUMAN;  P07195, LDHB_HUMAN;` -> pairs, plus a skip count."""
    pairs: List[Tuple[str, str]] = []
    skipped = 0
    text = " ".join(lines)
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 2 or not parts[0] or "_" not in parts[1]:
            skipped += 1
            continue
        pairs.append((parts[0], parts[1]))
    return pairs, skipped


def _terminated(lines: List[str]) -> List[str]:
    """Group wrapped lines into whole items: an item ends with a full stop."""
    items: List[List[str]] = []
    open_item = False
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not open_item:
            items.append([])
        items[-1].append(text)
        open_item = not text.endswith(".")
    return [_join(item) for item in items]


def parse_record(block: str) -> Tuple[Optional[EnzymeRecord], int]:
    """One record's text -> a record, or None when it has no ID line."""
    fields: Dict[str, List[str]] = {}
    for line in block.splitlines():
        if len(line) < 5 or line[2:5] != "   ":
            continue
        fields.setdefault(line[:2], []).append(line[5:])
    if "ID" not in fields:
        return None, 0
    ec = fields["ID"][0].strip()
    record = EnzymeRecord(ec=ec)

    designation = _join(fields.get("DE", []))
    if designation.startswith("Transferred entry"):
        record.status = TRANSFERRED
        record.superseded_by = EC_PATTERN.findall(designation)
    elif designation.startswith("Deleted entry"):
        record.status = DELETED
    else:
        record.name = designation.rstrip(".").strip()

    record.alternative_names = [
        item.rstrip(".").strip() for item in _terminated(fields.get("AN", []))
    ]
    record.reaction = " ".join(_terminated(fields.get("CA", [])))
    record.entries, skipped = _entries_of(fields.get("DR", []))
    return record, skipped


_RELEASE = re.compile(r"Release of (\d{1,2}-[A-Za-z]{3}-\d{4})")


def parse_enzyme_dat(text: str) -> ParsedEnzymeFile:
    """The whole file. The release string comes from its header."""
    release_match = _RELEASE.search(text[:4000])
    records: List[EnzymeRecord] = []
    skipped = 0
    for block in text.split("\n//\n"):
        record, bad = parse_record(block)
        skipped += bad
        if record is not None:
            records.append(record)
    return ParsedEnzymeFile(
        release=release_match.group(1) if release_match else "",
        records=records,
        skipped_lines=skipped,
    )


_CLASS_LINE = re.compile(r"^\s*(\d+)\.\s*(-|\d+)\.\s*(-|\d+)\.\s*(-|\d+)\s+(\S.*?)\s*$")


def parse_enzclass(text: str) -> Dict[str, str]:
    """`enzclass.txt` -> {'1': 'Oxidoreductases', '1.1': 'Acting on ...', '1.1.1': ...}.

    Lines look like `1. 1. 1.-    With NAD(+) or NADP(+) as acceptor.`; the
    key keeps only the numbered levels, so a class is addressed by its EC
    prefix. The trailing full stop is dropped.
    """
    classes: Dict[str, str] = {}
    for line in text.splitlines():
        match = _CLASS_LINE.match(line)
        if not match:
            continue
        parts = [match.group(i) for i in range(1, 5)]
        levels = []
        for part in parts:
            if part == "-":
                break
            levels.append(part)
        if not levels:
            continue
        classes[".".join(levels)] = match.group(5).rstrip(".").strip()
    return classes


__all__ = [
    "ACTIVE", "TRANSFERRED", "DELETED", "EC_PATTERN",
    "EnzymeRecord", "ParsedEnzymeFile",
    "parse_record", "parse_enzyme_dat", "parse_enzclass",
]
