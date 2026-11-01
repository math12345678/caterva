"""A small, sourced table of gene symbols and lab abbreviations, and the ECs they can be.

WHY THIS EXISTS
---------------
People do not type "acetylcholinesterase", they type ACHE, AChE or BuChE; not
"hexokinase 2", HK2; not "dipeptidyl peptidase 4", DPP-4. The nomenclature
the finder reads has names, not gene symbols, and the only symbols in the
index are UniProt entry-name mnemonics, which are not gene symbols
(`ACES_HUMAN` is ACHE, `KSYK_HUMAN` is SYK, `SYK_HUMAN` is a lysine--tRNA
ligase). Matching a typed symbol against those mnemonics resolved SYK to
lysine--tRNA ligase, ACHE to nothing, and IDH1 to a yeast enzyme.

`data/symbols.json` is the other half: for each symbol, the EC numbers it can
mean, with the source of that reading on the row.

* `genes`: a gene symbol UniProt gives a REVIEWED entry, per organism. The EC
  numbers are the ones UniProtKB's recommended name for that entry carries,
  or, where it carries none, the ones the enzyme index lists the entry under.
  Per organism because one symbol is different enzymes in different
  organisms: IDH1 is isocitrate dehydrogenase [NADP] (EC 1.1.1.42) in human
  and mouse and the NAD-dependent one (EC 1.1.1.41) in yeast. A symbol is
  only offered for an organism the table holds it for.
* `abbreviations`: a lab abbreviation or a full name written another way
  (PK, ADH, HIV protease, T4 lysozyme), independent of organism, with the
  accepted name of each EC it can mean.

WHAT IT DOES NOT DO
-------------------
Resolve. Every hit is a CANDIDATE: a person confirms it with one flag, as for
any other name that is not an accepted name, because an abbreviation is
exactly what is shared between enzymes (HK is hexokinase and histidine
kinase; AK is adenylate kinase, acetate kinase and adenosine kinase). The one
exception is in finder.py: an abbreviation the nomenclature also lists as an
exact alternative name of exactly one enzyme resolves when this table lists
it for that enzyme alone and for no other.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .index import organism_label

SYMBOLS_PATH = Path(__file__).resolve().parent / "data" / "symbols.json"

GENE = "gene"
ABBREVIATION = "abbreviation"


_FILLER = re.compile(r"\b(?:type|isozyme|isoenzyme|isoform)\b")


def compact_key(text: str) -> str:
    """Letters and digits only, lower case, and without the words "type", "isozyme",
    "isoenzyme" or "isoform": "DPP-4", "DPP4" and "dpp 4" are one key, and so are
    "hexokinase type II" and "hexokinase II"."""
    folded = _FILLER.sub(" ", unicodedata.normalize("NFKC", str(text)).lower())
    return re.sub(r"[^0-9a-z]+", "", folded)


@dataclass(frozen=True)
class SymbolHit:
    ec: str
    #: The row's own spelling of what matched.
    symbol: str
    kind: str
    #: The organism code a gene row read for (None for an abbreviation).
    organism: Optional[str]
    #: Position among the row's ECs: 0 is the one it most often means.
    order: int
    #: Plain English: why this EC is offered.
    why: str
    source: str
    #: The UniProtKB accession of the gene row's entry, or "".
    accession: str = ""


@dataclass(frozen=True)
class _Row:
    kind: str
    label: str
    keys: Tuple[str, ...]
    #: organism code -> (ECs, accession, protein name) for a gene row.
    by_organism: Dict[str, Tuple[Tuple[str, ...], str, str]]
    ecs: Tuple[str, ...]
    meaning: str
    source: str


class SymbolTable:
    def __init__(self, raw: Dict[str, object]):
        self.fetched: str = str(raw.get("fetched", ""))
        self.sources: Dict[str, str] = dict(raw.get("sources", {}))  # type: ignore[arg-type]
        self.rows: List[_Row] = []
        self.by_key: Dict[str, List[_Row]] = {}
        for item in raw.get("genes", []):  # type: ignore[union-attr]
            by_org = {
                code: (tuple(entry["ecs"]), entry["accession"], entry.get("name", ""))
                for code, entry in item["organisms"].items()
            }
            row = _Row(GENE, item["symbol"], self._keys([item["symbol"], *item.get("aliases", [])]), by_org,
                       (), item.get("meaning", ""), item["source"])
            self._add(row)
        for item in raw.get("abbreviations", []):  # type: ignore[union-attr]
            symbols = list(item["symbols"])
            row = _Row(ABBREVIATION, symbols[0], self._keys(symbols), {}, tuple(item["ecs"]),
                       item.get("meaning", ""), item["source"])
            self._add(row)

    @staticmethod
    def _keys(texts: Sequence[str]) -> Tuple[str, ...]:
        out: List[str] = []
        for text in texts:
            key = compact_key(text)
            if key and key not in out:
                out.append(key)
        return tuple(out)

    def _add(self, row: _Row) -> None:
        self.rows.append(row)
        for key in row.keys:
            self.by_key.setdefault(key, []).append(row)

    # -- asking --------------------------------------------------------------

    def lookup(self, query: str, code: Optional[str]) -> List[SymbolHit]:
        """Every EC the table lists for this symbol in this organism, in the row's order.

        A gene row is read for `code` only; with no organism given it is read
        for every organism it holds, each hit saying which."""
        hits: List[SymbolHit] = []
        for row in self.by_key.get(compact_key(query), ()):
            if row.kind == GENE:
                for organism, (ecs, accession, name) in row.by_organism.items():
                    if code is not None and organism != code:
                        continue
                    label = organism_label(organism)
                    for order, ec in enumerate(ecs):
                        hits.append(SymbolHit(
                            ec=ec, symbol=row.label, kind=GENE, organism=organism, order=order,
                            why=(f"{row.label} is the {label} gene symbol of {name or 'a protein'} "
                                 f"(UniProtKB {accession}), which UniProt files under this EC number"),
                            source=row.source, accession=accession))
            else:
                for order, ec in enumerate(row.ecs):
                    others = [e for e in row.ecs if e != ec]
                    why = f"{row.label} is a common abbreviation for {row.meaning}"
                    if others:
                        why += "; it is also used for other enzymes, so the choice is yours"
                    hits.append(SymbolHit(
                        ec=ec, symbol=row.label, kind=ABBREVIATION, organism=None, order=order,
                        why=why, source=row.source))
        return hits

    @staticmethod
    def combine(hits: Sequence[SymbolHit]) -> str:
        """One sentence for the hits that name the same EC: the gene symbol is one organism's or several's."""
        first = hits[0]
        genes = [h for h in hits if h.kind == GENE and h.organism]
        if len(hits) == 1 or len(genes) != len(hits):
            return first.why
        labels = ", ".join(organism_label(h.organism) for h in genes if h.organism)
        accessions = ", ".join(h.accession for h in genes)
        return (f"{first.symbol} is the {labels} gene symbol (UniProtKB {accessions}) of a protein UniProt files "
                "under this EC number")

    def organisms_for(self, query: str) -> Tuple[str, ...]:
        """Organism codes the table holds this gene symbol for (empty when it holds none)."""
        found: List[str] = []
        for row in self.by_key.get(compact_key(query), ()):
            if row.kind == GENE:
                found.extend(o for o in row.by_organism if o not in found)
        return tuple(found)

    def knows(self, query: str) -> bool:
        return compact_key(query) in self.by_key


@lru_cache(maxsize=1)
def load_symbols(path: Optional[str] = None) -> SymbolTable:
    source = Path(path) if path else SYMBOLS_PATH
    with open(source, encoding="utf-8") as handle:
        return SymbolTable(json.load(handle))


__all__ = ["SYMBOLS_PATH", "GENE", "ABBREVIATION", "SymbolHit", "SymbolTable", "compact_key", "load_symbols"]
