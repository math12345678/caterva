#!/usr/bin/env python3
"""Build the enzyme-name index the finder ships with.

WHY THIS EXISTS
---------------
`caterva enzyme` and every command that takes an enzyme name look names up
in the IUBMB nomenclature as distributed in the ExPASy ENZYME database
(SIB Swiss Institute of Bioinformatics, CC BY 4.0). The finder must work
offline and must not download a 9.6 MB flat file at query time, so this
script reads `enzyme.dat` and `enzclass.txt` once and writes a compact,
committed index: `caterva/enzymes/data/enzyme_index.json.gz`.

WHAT GOES IN, AND WHAT IS LEFT OUT
----------------------------------
Per EC number: the accepted name, the alternative names, the reaction text,
the status (active, transferred with the new number, or deleted) and the
UniProt entries that ENZYME lists for it. The entries are kept as a count per
organism code (the suffix of the entry name, such as HUMAN in LDHA_HUMAN) for
every organism, and as the full list of accessions and entry names only for
FULL_LIST_ORGANISMS. The comments, which are prose about a reaction and make
up most of the file, are left out: the finder ranks by name, and a name found
only in somebody else's comment is exactly what it must not rank by.

Output is deterministic: records in EC order, keys in a fixed order,
compressed with a zeroed timestamp and no file name. The same two input
files give the same bytes, and the only date inside is the release string
printed in the file's own header.

USAGE
-----
    python scripts/build_enzyme_index.py                # download, then build
    python scripts/build_enzyme_index.py --dat enzyme.dat --enzclass enzclass.txt

`make enzyme-index` runs the first form. It is the only thing in this
repository that fetches the nomenclature, and it is run by a person who is
refreshing the index, never by a test or by the application.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from caterva.enzymes.source import (  # noqa: E402
    ACTIVE, DELETED, TRANSFERRED, parse_enzclass, parse_enzyme_dat,
)

DAT_URL = "https://ftp.expasy.org/databases/enzyme/enzyme.dat"
CLASS_URL = "https://ftp.expasy.org/databases/enzyme/enzclass.txt"
DEFAULT_OUT = REPO / "caterva" / "enzymes" / "data" / "enzyme_index.json.gz"

#: Organism codes whose UniProt entries are listed in full. Every other
#: organism keeps a count only, which is what keeps the index small.
FULL_LIST_ORGANISMS = (
    "HUMAN", "MOUSE", "RAT", "YEAST", "ECOLI", "BOVIN", "PIG", "CHICK",
    "ARATH", "BACSU", "DROME", "CAEEL", "RABIT",
)

LICENCE = "CC BY 4.0"
LICENCE_URI = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_URI = "https://enzyme.expasy.org/"
CREATOR = (
    "the SIB Swiss Institute of Bioinformatics (ExPASy ENZYME database, "
    "Bridge and Axelsen), which distributes the IUBMB enzyme nomenclature"
)
MODIFICATIONS = (
    "reduced to accepted names, alternative names, reactions, status, "
    "enzyme-class names and the UniProt entry names listed per EC number; "
    "comments dropped; UniProt entries kept as counts per organism, and in "
    "full only for 13 organisms"
)


def _ec_key(ec: str):
    """Sort key: numeric parts first, `n1`-style preliminary numbers after."""
    out = []
    for part in ec.split("."):
        if part.isdigit():
            out.append((0, int(part)))
        elif part.startswith("n") and part[1:].isdigit():
            out.append((1, int(part[1:])))
        else:
            out.append((2, 0))
    return tuple(out)


def build_index(dat_text: str, class_text: str) -> Dict[str, object]:
    """The index as a plain dict, ready to serialise."""
    parsed = parse_enzyme_dat(dat_text)
    if not parsed.release:
        raise SystemExit("enzyme.dat has no 'Release of ...' line in its header; refusing to guess a release")
    if not parsed.records:
        raise SystemExit("enzyme.dat held no records")
    classes = parse_enzclass(class_text)
    if not classes:
        raise SystemExit("enzclass.txt held no classes")

    full = set(FULL_LIST_ORGANISMS)
    enzymes: Dict[str, Dict[str, object]] = {}
    for record in sorted(parsed.records, key=lambda r: _ec_key(r.ec)):
        item: Dict[str, object] = {}
        if record.status == ACTIVE:
            item["n"] = record.name
            if record.alternative_names:
                item["a"] = record.alternative_names
            if record.reaction:
                item["r"] = record.reaction
        elif record.status == TRANSFERRED:
            item["s"] = "t"
            item["to"] = record.superseded_by
        elif record.status == DELETED:
            item["s"] = "d"
        counts: Dict[str, int] = {}
        listed: Dict[str, List[str]] = {}
        for accession, entry_name in record.entries:
            stem, _, code = entry_name.rpartition("_")
            counts[code] = counts.get(code, 0) + 1
            if code in full:
                listed.setdefault(code, []).append(f"{accession}:{stem}")
        if counts:
            item["c"] = dict(sorted(counts.items()))
        if listed:
            item["p"] = dict(sorted(listed.items()))
        enzymes[record.ec] = item

    return {
        "format": 1,
        "release": parsed.release,
        "source": "ExPASy ENZYME nomenclature database (enzyme.dat, enzclass.txt)",
        "source_uri": SOURCE_URI,
        "creator": CREATOR,
        "licence": LICENCE,
        "licence_uri": LICENCE_URI,
        "modifications": MODIFICATIONS,
        "full_list_organisms": list(FULL_LIST_ORGANISMS),
        "classes": classes,
        "enzymes": enzymes,
    }


def serialise(index: Dict[str, object]) -> bytes:
    """Deterministic gzip of the index: fixed timestamp, no file name."""
    payload = json.dumps(index, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return gzip.compress(payload, compresslevel=9, mtime=0)


def _download(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed https URL above
        return response.read().decode("utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dat", type=Path, help="a local enzyme.dat (default: download it)")
    parser.add_argument("--enzclass", type=Path, help="a local enzclass.txt (default: download it)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the index")
    args = parser.parse_args(argv)

    dat_text = args.dat.read_text(encoding="utf-8") if args.dat else _download(DAT_URL)
    class_text = args.enzclass.read_text(encoding="utf-8") if args.enzclass else _download(CLASS_URL)
    index = build_index(dat_text, class_text)
    data = serialise(index)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(
        f"Wrote {args.out}: release {index['release']}, "
        f"{len(index['enzymes'])} EC numbers, {len(index['classes'])} classes, "
        f"{len(data):,} bytes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
