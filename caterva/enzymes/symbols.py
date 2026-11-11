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

* `data/aliases.json`: names people type for ONE enzyme that the two lists
  above leave ambiguous or do not hold (CYP2B6, COX-2, MAO-B, PTP1B, HIV-1
  protease, angiotensin-converting enzyme, PEPCK in a mammal), each with the
  isoform it is (when it is one protein of a large EC number), the organism
  it implies, and the source of the reading. Curated by hand; every EC is
  checked against the nomenclature by a test.

WHEN A SYMBOL IS ONE ENZYME (`SymbolTable.read`)
-----------------------------------------------
A symbol that the table maps to exactly one EC number in the organism IS one
enzyme, and reading it as that enzyme is not a guess: "HK2" in human is
hexokinase, and refusing it sent people to type "--subject 2.7.1.1
--isoform HK2" by hand (owner decision 2026-11-11, ADR 0182). So `read`
returns ONE reading -- EC number, isoform, the organism assumed if none was
given -- with a sentence saying how, and returns None, keeping the choice
for a person, whenever the table holds more than one reading:

* an abbreviation the table lists for several enzymes (HK, LDH, ADH, NOS,
  SDH, AK, HMG-CoA reductase) stays a choice;
* a gene symbol is one organism's: with no organism given, a symbol written
  as a human gene symbol is written (upper case: HK2, LDHA, CYP2B6) is read
  for Homo sapiens, and the note says so; any other spelling is read only
  when every organism the table holds it for agrees on the EC;
* a gene UniProt files under several EC numbers stays a choice, except a
  cytochrome P450 filed under EC 1.14.14.1 (unspecific monooxygenase), where
  BRENDA files the drug-metabolism kinetics, and the note says so;
* an alias row decides over the rows above where it holds the name, because
  it was written for exactly that name (MAO-B is EC 1.4.3.4, not the
  primary-amine oxidase UniProt also lists).
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
ALIASES_PATH = Path(__file__).resolve().parent / "data" / "aliases.json"

GENE = "gene"
ABBREVIATION = "abbreviation"
#: A curated row of data/aliases.json: one name, one enzyme (or one per organism).
ALIAS = "alias"

#: The EC number BRENDA files cytochrome P450 drug-metabolism kinetics under.
#: A CYP gene UniProt also files under narrower single-reaction numbers is
#: read as this one.
P450_EC = "1.14.14.1"

#: Written the way a human gene symbol is: capitals and digits, maybe a
#: hyphen ("HK2", "LDHA", "CYP2B6", "COX-2"). Mouse symbols are capitalised
#: only ("Hk2"), and a lab abbreviation often mixes case ("AChE").
_HUMAN_STYLE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?$")


def human_style(text: str) -> bool:
    """True for a symbol written as HGNC writes a human gene symbol (HK2, CYP2B6)."""
    return bool(_HUMAN_STYLE.match(text.strip())) and any(ch.isalpha() for ch in text)


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
    #: The isoform the row names (a gene row's symbol, an alias row's isoform), or None.
    isoform: Optional[str] = None


@dataclass(frozen=True)
class SymbolReading:
    """One enzyme a symbol or alias was read as, and how. See `SymbolTable.read`."""

    ec: str
    #: The protein of that EC number the name is (HK2, CYP2B6, PTPN1), for
    #: `--isoform`; None when the name is the whole enzyme.
    isoform: Optional[str]
    #: The organism code the reading was made for: the one given, or the one assumed.
    organism: Optional[str]
    #: The binomial assumed because no organism was given (Homo sapiens for
    #: HK2, Human immunodeficiency virus 1 for HIV-1 protease), else None.
    assumed_organism: Optional[str]
    #: Plain English: why the name is this enzyme.
    why: str
    #: Sentences for the report about what was assumed or set aside.
    notes: Tuple[str, ...] = ()


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
    #: Alias rows only.
    isoform: Optional[str] = None
    organism: Optional[str] = None
    organism_rule: str = ""
    alias_by_organism: Tuple[Tuple[str, str], ...] = ()
    #: The organisms an alias row is read for when one is given (empty: all).
    organisms: Tuple[str, ...] = ()


class SymbolTable:
    def __init__(self, raw: Dict[str, object], aliases: Optional[Dict[str, object]] = None):
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
        for item in (aliases or {}).get("aliases", []):  # type: ignore[union-attr]
            names = list(item["names"])
            by_org = tuple(sorted(dict(item.get("by_organism", {})).items()))
            ecs = (item["ec"],) if "ec" in item else tuple(sorted({ec for _, ec in by_org}))
            row = _Row(ALIAS, names[0], self._keys(names), {}, ecs, names[0], item["source"],
                       isoform=item.get("isoform"), organism=item.get("organism"),
                       organism_rule=item.get("organism_rule", ""), alias_by_organism=by_org,
                       organisms=tuple(item.get("organisms", ())))
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
                            source=row.source, accession=accession, isoform=row.label))
            elif row.kind == ALIAS:
                if code is not None and row.organisms and code not in row.organisms:
                    continue
                by_org = dict(row.alias_by_organism)
                if by_org and code is not None:
                    listed = (by_org[code],) if code in by_org else ()
                else:
                    listed = row.ecs
                for order, ec in enumerate(listed):
                    why = f"{row.label} is a name people use for this enzyme ({row.source})"
                    if row.isoform:
                        why = f"{row.label} is the isoform {row.isoform} of this enzyme ({row.source})"
                    hits.append(SymbolHit(
                        ec=ec, symbol=row.label, kind=ALIAS, organism=code if by_org else _code_of(row.organism),
                        order=order,
                        why=why, source=row.source, isoform=row.isoform))
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
        # A curated alias row beside gene rows says the same thing again; the
        # gene rows' organisms are the sentence.
        others = [h for h in hits if h.kind != GENE and h.kind != ALIAS]
        if len(genes) <= 1 or others:
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

    def read(self, query: str, code: Optional[str]) -> Optional[SymbolReading]:
        """The ONE enzyme `query` is in organism `code`, or None when it is a choice.

        See the module docstring for the rules. `code` is the organism that
        was given (a UniProt code from `index.organism_code`), or None; a
        reading made for an organism nobody gave says so in `notes` and
        `assumed_organism`.
        """
        from .index import ORGANISMS

        rows = self.by_key.get(compact_key(query), ())
        if not rows:
            return None
        typed = " ".join(query.split())
        notes: List[str] = []

        # 1. A curated alias row decides where it holds the name.
        aliases = [r for r in rows if r.kind == ALIAS]
        if aliases:
            readings: List[Tuple[str, _Row]] = []
            for row in aliases:
                if code is not None and row.organisms and code not in row.organisms:
                    continue
                by_org = dict(row.alias_by_organism)
                if by_org:
                    if code is None or code not in by_org:
                        # PEPCK with no organism, or one the row does not
                        # hold: several enzymes, a person chooses.
                        return None
                    readings.append((by_org[code], row))
                else:
                    readings.append((row.ecs[0], row))
            ecs = {ec for ec, _ in readings}
            if len(ecs) == 1:
                ec, row = readings[0]
                assumed = None
                if code is None and row.organism and (
                        row.organism_rule == "always" or (row.organism_rule == "uppercase" and human_style(typed))):
                    assumed = row.organism
                    notes.append(_assumed_note(typed, row.organism, row.organism_rule))
                elif code is not None and row.organism and row.organism_rule == "always":
                    given = ORGANISMS.get(code, (code,))[0]
                    if given != row.organism:
                        notes.append(f"{typed} is an enzyme of {row.organism}, which is the organism BRENDA files "
                                     f"it under; {given} was searched because it was given.")
                if row.alias_by_organism:
                    notes.append(f"Read {typed!r} as EC {ec} because the organism is "
                                 f"{organism_label(code or '')}: {row.source}.")
                assumed_code = None
                if assumed is not None:
                    assumed_code = next((c for c, (b, _, _) in ORGANISMS.items() if b == assumed), None)
                return SymbolReading(
                    ec=ec, isoform=row.isoform, organism=code or assumed_code, assumed_organism=assumed,
                    why=(f"{typed} is " + (f"the isoform {row.isoform} of " if row.isoform else "")
                         + f"this enzyme (source: {row.source})"),
                    notes=tuple(notes))
            if len(ecs) > 1:
                return None

        # 2. Gene rows: one organism's symbol.
        genes = [r for r in rows if r.kind == GENE]
        gene_ec: Optional[str] = None
        gene_row: Optional[_Row] = None
        read_for = code
        assumed_binomial: Optional[str] = None
        if genes:
            per_organism: Dict[str, set] = {}
            for row in genes:
                for organism, (ecs, _, _) in row.by_organism.items():
                    per_organism.setdefault(organism, set()).update(ecs)
            if code is None:
                if human_style(typed) and "HUMAN" in per_organism:
                    read_for = "HUMAN"
                    assumed_binomial = ORGANISMS["HUMAN"][0]
                elif len({frozenset(v) for v in per_organism.values()}) == 1:
                    read_for = None
                else:
                    return None
            ecs = per_organism.get(read_for, set()) if read_for else set().union(*per_organism.values())
            if len(ecs) == 1:
                gene_ec = next(iter(ecs))
            elif P450_EC in ecs and compact_key(typed).startswith("cyp"):
                gene_ec = P450_EC
                notes.append(f"UniProt files {typed} under several EC numbers; EC {P450_EC} (unspecific "
                             "monooxygenase) was read because BRENDA files cytochrome P450 kinetics there.")
            elif ecs:
                return None
            if gene_ec is not None:
                gene_row = next((r for r in genes if read_for is None or read_for in r.by_organism), genes[0])

        # 3. Abbreviation rows: organism-independent.
        abbreviation_ecs = {ec for r in rows if r.kind == ABBREVIATION for ec in r.ecs}
        if len(abbreviation_ecs) > 1:
            # HK, LDH, CAT, IDH: several enzymes go by it. Only an organism
            # the person GAVE can decide, through that organism's gene.
            if gene_ec is None or code is None or gene_ec not in abbreviation_ecs:
                return None
        elif abbreviation_ecs:
            only = next(iter(abbreviation_ecs))
            if gene_ec is not None and gene_ec != only:
                return None
            if gene_ec is None:
                row = next(r for r in rows if r.kind == ABBREVIATION)
                return SymbolReading(
                    ec=only, isoform=None, organism=code, assumed_organism=None,
                    why=f"{row.label} is a common abbreviation for {row.meaning} ({row.source})")
        if gene_ec is None or gene_row is None:
            return None
        if assumed_binomial is not None:
            notes.insert(0, _assumed_note(typed, assumed_binomial, "uppercase"))
        organism, (_, accession, name) = next(
            ((o, v) for o, v in gene_row.by_organism.items() if read_for is None or o == read_for))
        label = organism_label(read_for) if read_for else ", ".join(organism_label(o) for o in gene_row.by_organism)
        # The isoform is what was typed when it was typed as a symbol ("PKM2"
        # is the M2 splice form of the PKM gene, and "PKM" would lose it);
        # otherwise the gene's own symbol ("CA II" is CA2).
        isoform: Optional[str] = gene_row.label
        if human_style(typed) and compact_key(typed) != compact_key(gene_row.label):
            isoform = typed
        # An isoform is only worth carrying when the EC number is several
        # proteins in the organism: "thrombin" is the F2 gene's protein, the
        # one human protein of EC 3.4.21.5, and "--isoform F2" would only
        # drop rows that name "alpha-thrombin".
        from .index import load_index

        entry = load_index().get(gene_ec)
        counts = entry.counts if entry is not None else {}
        several = (counts.get(read_for, 0) if read_for else max(
            (counts.get(o, 0) for o in gene_row.by_organism), default=0)) > 1
        if not several:
            isoform = None
        return SymbolReading(
            ec=gene_ec, isoform=isoform, organism=read_for, assumed_organism=assumed_binomial,
            why=(f"{gene_row.label} is the {label} gene symbol of {name or 'a protein'} (UniProtKB {accession}), "
                 "which UniProt files under this EC number"),
            notes=tuple(notes))


def _code_of(binomial: Optional[str]) -> Optional[str]:
    from .index import ORGANISMS

    return next((c for c, (b, _, _) in ORGANISMS.items() if b == binomial), None) if binomial else None


def _assumed_note(typed: str, organism: str, rule: str) -> str:
    if rule == "always":
        return (f"No organism was given; {typed} is an enzyme of {organism}, so that organism was searched "
                "(pass --organism to change it).")
    return (f"No organism was given; {typed} is written as a human gene symbol, so Homo sapiens was searched "
            "(pass --organism to change it).") if organism == "Homo sapiens" else (
        f"No organism was given; {typed} was read for {organism} (pass --organism to change it).")


@lru_cache(maxsize=1)
def load_symbols(path: Optional[str] = None, aliases_path: Optional[str] = None) -> SymbolTable:
    """The shipped symbol table with the curated aliases. A test that passes
    its own `path` gets no aliases unless it passes `aliases_path` too."""
    source = Path(path) if path else SYMBOLS_PATH
    with open(source, encoding="utf-8") as handle:
        raw = json.load(handle)
    alias_source = Path(aliases_path) if aliases_path else (ALIASES_PATH if path is None else None)
    aliases = None
    if alias_source is not None:
        with open(alias_source, encoding="utf-8") as handle:
            aliases = json.load(handle)
    return SymbolTable(raw, aliases)


__all__ = [
    "SYMBOLS_PATH", "ALIASES_PATH", "GENE", "ABBREVIATION", "ALIAS", "P450_EC", "SymbolHit", "SymbolReading",
    "SymbolTable", "compact_key", "human_style", "load_symbols",
]
