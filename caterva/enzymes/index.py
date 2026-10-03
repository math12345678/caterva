"""Load the committed enzyme-name index and answer questions about one EC.

WHY THIS EXISTS
---------------
The finder (finder.py) ranks names; this module holds the data they are
ranked against. It reads `data/enzyme_index.json.gz`, which
`scripts/build_enzyme_index.py` wrote from the ExPASy ENZYME database, once
per process, and never touches the network. The same bytes ship in the wheel
and in the frozen app, so an offline machine gets the same answers as a
connected one.

The index is a reading of the IUBMB nomenclature at one release. It is not
UniProt: an enzyme UniProt has not yet filed under an EC number is absent
from it, and the finder says what release it read so that is checkable.

ORGANISMS
---------
ENZYME lists UniProt entries by entry name (`LDHA_HUMAN`); the part after the
last underscore is an organism code. The index keeps a count per code for
every organism and the entries themselves for 13, so an organism the index
holds no list for can still be asked "does this EC have a protein there?" but
cannot be asked to name them. `organism_code` reads a name a person types
(human, Homo sapiens, HUMAN) as one of those codes and refuses to guess for
anything else.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

INDEX_PATH = Path(__file__).resolve().parent / "data" / "enzyme_index.json.gz"

ACTIVE = "active"
TRANSFERRED = "transferred"
DELETED = "deleted"

#: code -> (binomial, short label used in messages, other names people type).
#: One species each, as in caterva/compose/organisms.py: "monkey" or "bacteria"
#: are many species and are not here. The first thirteen are the organisms
#: the index lists proteins for; the rest have counts only.
ORGANISMS: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {
    "HUMAN": ("Homo sapiens", "human", ("humans",)),
    "MOUSE": ("Mus musculus", "mouse", ()),
    "RAT": ("Rattus norvegicus", "rat", ()),
    "YEAST": ("Saccharomyces cerevisiae", "yeast", ("baker's yeast", "budding yeast")),
    "ECOLI": ("Escherichia coli", "E. coli", ("e.coli", "ecoli")),
    "BOVIN": ("Bos taurus", "cow", ("bovine", "cattle")),
    "PIG": ("Sus scrofa", "pig", ("porcine",)),
    "CHICK": ("Gallus gallus", "chicken", ()),
    "ARATH": ("Arabidopsis thaliana", "Arabidopsis", ("arabidopsis",)),
    "BACSU": ("Bacillus subtilis", "B. subtilis", ("b. subtilis",)),
    "DROME": ("Drosophila melanogaster", "fruit fly", ("fruit fly", "drosophila")),
    "CAEEL": ("Caenorhabditis elegans", "C. elegans", ("c. elegans",)),
    "RABIT": ("Oryctolagus cuniculus", "rabbit", ()),
    "SCHPO": ("Schizosaccharomyces pombe", "fission yeast", ("fission yeast",)),
    "DANRE": ("Danio rerio", "zebrafish", ()),
    "XENLA": ("Xenopus laevis", "Xenopus laevis", ("xenopus",)),
    "MYCTU": ("Mycobacterium tuberculosis", "M. tuberculosis", ("m. tuberculosis",)),
    "HORSE": ("Equus caballus", "horse", ()),
    "SHEEP": ("Ovis aries", "sheep", ()),
}

_NAME_TO_CODE: Dict[str, str] = {}
for _code, (_binomial, _label, _aliases) in ORGANISMS.items():
    for _name in (_binomial, _label, _code, *_aliases):
        _NAME_TO_CODE[" ".join(_name.lower().split())] = _code


def organism_code(text: Optional[str]) -> Optional[str]:
    """The UniProt organism code for what a person typed, or None.

    None means "not recognised", never "assume human": the caller then ranks
    without an organism and may say so.
    """
    if not text:
        return None
    return _NAME_TO_CODE.get(" ".join(str(text).lower().split()))


def organism_label(code: str) -> str:
    """Short name for messages: `human`, `E. coli`; the code itself if unknown."""
    entry = ORGANISMS.get(code)
    return entry[1] if entry else code


@dataclass(frozen=True)
class Protein:
    """One UniProt entry ENZYME lists under an EC number."""

    accession: str
    entry_name: str

    @property
    def symbol(self) -> str:
        """The entry name without its organism suffix: LDHA from LDHA_HUMAN."""
        return self.entry_name.rpartition("_")[0] or self.entry_name


@dataclass(frozen=True)
class EnzymeEntry:
    ec: str
    name: str
    alternative_names: Tuple[str, ...]
    reaction: str
    status: str
    superseded_by: Tuple[str, ...]
    #: organism code -> number of UniProt entries, for every organism.
    counts: Mapping[str, int]
    #: organism code -> entries, for the organisms the index lists in full.
    proteins: Mapping[str, Tuple[Protein, ...]] = field(default_factory=dict)


class EnzymeIndex:
    """The whole index, with the classes needed to describe an EC."""

    def __init__(self, raw: Mapping[str, object]):
        self.release: str = str(raw["release"])
        self.source_uri: str = str(raw["source_uri"])
        self.licence: str = str(raw["licence"])
        self.creator: str = str(raw["creator"])
        self.full_list_organisms: Tuple[str, ...] = tuple(raw["full_list_organisms"])  # type: ignore[arg-type]
        self.classes: Dict[str, str] = dict(raw["classes"])  # type: ignore[arg-type]
        self.entries: Dict[str, EnzymeEntry] = {}
        for ec, item in raw["enzymes"].items():  # type: ignore[union-attr]
            status = {"t": TRANSFERRED, "d": DELETED}.get(item.get("s", ""), ACTIVE)
            self.entries[ec] = EnzymeEntry(
                ec=ec,
                name=item.get("n", ""),
                alternative_names=tuple(item.get("a", ())),
                reaction=item.get("r", ""),
                status=status,
                superseded_by=tuple(item.get("to", ())),
                counts=dict(item.get("c", {})),
                proteins={
                    code: tuple(
                        Protein(accession=a, entry_name=f"{s}_{code}")
                        for a, _, s in (p.partition(":") for p in listed)
                    )
                    for code, listed in item.get("p", {}).items()
                },
            )
        self.known_codes = {c for e in self.entries.values() for c in e.counts}

    def get(self, ec: str) -> Optional[EnzymeEntry]:
        return self.entries.get(ec)

    def class_path(self, ec: str) -> str:
        """`Oxidoreductases > acting on the CH-OH group of donors > with NAD(+) or NADP(+) as acceptor`."""
        parts = ec.split(".")
        names: List[str] = []
        for depth in (1, 2, 3):
            name = self.classes.get(".".join(parts[:depth]))
            if not name:
                continue
            if depth > 1 and len(name) > 1 and not name[1].isupper():
                name = name[0].lower() + name[1:]
            names.append(name)
        return " > ".join(names)

    def class_name(self, prefix: str) -> str:
        return self.classes.get(prefix, "")

    def proteins_in(self, ec: str, code: Optional[str]) -> Tuple[Tuple[Protein, ...], int]:
        """(the listed entries, the count) for one EC in one organism."""
        entry = self.entries.get(ec)
        if entry is None or not code:
            return (), 0
        return tuple(entry.proteins.get(code, ())), int(entry.counts.get(code, 0))


@lru_cache(maxsize=1)
def load_index(path: Optional[str] = None) -> EnzymeIndex:
    """The shipped index, read once. `path` is for tests that build their own."""
    source = Path(path) if path else INDEX_PATH
    with gzip.open(source, "rt", encoding="ascii") as handle:
        return EnzymeIndex(json.load(handle))


__all__ = [
    "ACTIVE", "TRANSFERRED", "DELETED", "ORGANISMS", "INDEX_PATH",
    "Protein", "EnzymeEntry", "EnzymeIndex",
    "organism_code", "organism_label", "load_index",
]
