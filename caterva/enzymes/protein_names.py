"""The gene symbol and names UniProt gives the proteins the index lists.

WHY THIS EXISTS
---------------
ENZYME lists each protein only by UniProt entry name, and an entry name is a
mnemonic, not a gene symbol: `ACES_HUMAN` is the ACHE gene, `KSYK_HUMAN` is
SYK, and `SYK_HUMAN` is a lysine--tRNA ligase. The isozyme notice used to
offer those mnemonics (HXK1, LDH6A, AOFA) as if they were what a person
types, and the engine that reads papers' isoform names knew none of them.

`data/protein_names.json.gz` holds, for each protein the index lists for
the four organisms people ask about (human, mouse, yeast, E. coli K-12), the
gene symbol and the names UniProtKB gives it: the recommended name, its short
names, the alternative names and the gene's synonyms. It was read from
UniProtKB by `scripts/build_enzyme_symbols.py` and is never fetched at query
time. A protein the file does not hold has no gene symbol here, and every
caller falls back to its mnemonic and says it is one.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

NAMES_PATH = Path(__file__).resolve().parent / "data" / "protein_names.json.gz"


@dataclass(frozen=True)
class ProteinInfo:
    accession: str
    #: The gene symbol UniProt gives the entry (HK1), or None for an entry with none.
    gene: Optional[str]
    #: The recommended name (Hexokinase-1).
    name: str
    #: The gene symbol, gene synonyms, short names and other names, in that order, without repeats.
    names: Tuple[str, ...]


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, ProteinInfo], Dict[str, object]]:
    if not NAMES_PATH.exists():
        return {}, {}
    with gzip.open(NAMES_PATH, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    out: Dict[str, ProteinInfo] = {}
    for accession, (gene, name, others) in raw["entries"].items():
        names = []
        for text in ([gene] if gene else []) + list(others):
            if text and text not in names:
                names.append(text)
        out[accession] = ProteinInfo(accession, gene or None, name, tuple(names))
    meta = {k: v for k, v in raw.items() if k != "entries"}
    return out, meta


def info(accession: str) -> Optional[ProteinInfo]:
    return _load()[0].get(accession)


def provenance() -> Dict[str, object]:
    """Where the file came from: source, organisms, fetch date, entry count."""
    meta = dict(_load()[1])
    meta["entries"] = len(_load()[0])
    return meta


__all__ = ["NAMES_PATH", "ProteinInfo", "info", "provenance"]
