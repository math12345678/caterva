"""Say when one EC number is several proteins in the organism asked about.

WHY THIS EXISTS
---------------
`caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human
--substrate glucose` reported a Km of 6 mM and a kcat of 40.1 1/s with the
verdict GROUNDED. Both came from papers on glucokinase (hexokinase IV). The
same BRENDA page holds hexokinase I and III rows 80 to 190 times lower, and
nothing in the report said an isozyme was in play, because EC 2.7.1.1 is one
number and four or five human proteins: BRENDA files them all under it, and
the resolver ranks rows, not proteins.

This does the smallest honest thing. The enzyme nomenclature lists the
UniProt entries for each EC number; when the organism has two or more for
the EC and the request names no `--isoform`, the report says so, names them
by gene symbol, and says the cited constants may belong to any of them. It
does not read isozymes out of BRENDA's reference titles, does not pick one,
and does not change a constant.

WHAT `--isoform` DOES, AND WHAT THIS DOES NOT TAKE FOR GRANTED
--------------------------------------------------------------
`--isoform HK2` asks the engine to take each constant from a row whose own
commentary names that isozyme ("hexokinase II", "HK-2", "HXK2": the names
UniProtKB gives the protein, enzymes/isoforms.py). Where no row names it, the
constant is taken from a row that names NO isozyme, and where every row names
another, the constant is refused. So typing `--isoform` does not make a
constant belong to that isozyme: a row that names none might be any of them.
The notice therefore goes quiet only when EVERY cited constant's row states
the isozyme asked for. When one does not, the notice stays, and says which
constant, because GROUNDED does not say which protein was measured.

WHEN IT STAYS QUIET
-------------------
When `--isoform` was given AND every cited constant's row states it; when the
EC number has one protein in the organism, or none; when no organism was
given, because there is nothing to count; and when the organism is one the
index does not recognise, because "no entries" would then mean "not known".

BIG CLASSES
-----------
EC 2.7.11.1 has 245 human proteins: 245 different kinases, not isozymes of
one. Above `BROAD_CLASS` proteins the notice says "N different human proteins
share this EC number (a broad class)" and does not call them isozymes or list
them.

WHAT THE LIST LEAVES OUT
------------------------
The nomenclature files a protein under the EC numbers of its activities, so a
protein can be missing from an EC's list that papers measured under it. Human
alcohol dehydrogenases ADH1B and ADH4 are filed under EC 1.1.1.105 only
(ADH1A, ADH1G, ADH5, ADH6 and ADH7 are under EC 1.1.1.1). The documented rule:
other proteins of the same organism whose gene symbols share the listed
proteins' stem (ADH for ADH1B) and are filed under other EC numbers are named
in the notice, as "this list may leave them out".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional, Sequence, Tuple

from .finder import isozymes
from .index import load_index, organism_label

_COMPLETE_EC = re.compile(r"^\d+\.\d+\.\d+\.n?\d+$")

#: Above this many proteins an EC number is a broad class, not isozymes of one enzyme.
BROAD_CLASS = 12
#: How many names a sentence lists before "and N more".
LISTED = 8


def organism_precise(code: str) -> str:
    """`E. coli K-12` for ECOLI, which is one strain; the label for any other code."""
    return "E. coli K-12" if code == "ECOLI" else organism_label(code)


def _stem(symbol: str) -> str:
    """The family of a numbered gene symbol: ADH from ADH1B. A symbol with no number
    after its letters (LDHA, adhE) names no family here."""
    found = re.match(r"([A-Za-z]{3,})\d", symbol)
    return found.group(1).upper() if found else ""


@lru_cache(maxsize=256)
def _filed_elsewhere(ec: str, code: str) -> Tuple[Tuple[str, str], ...]:
    """(label, EC) for proteins of this organism whose gene symbols share the listed
    proteins' family stem and that the nomenclature files under other EC numbers only."""
    index = load_index()
    entry = index.get(ec)
    listed = entry.proteins.get(code, ()) if entry else ()
    stems = {_stem(p.label) for p in listed} - {""}
    if not stems:
        return ()
    held = {p.accession for p in listed}
    found: Dict[str, Tuple[str, str]] = {}
    for other_ec, other in index.entries.items():
        if other_ec == ec or other.status != "active":
            continue
        for p in other.proteins.get(code, ()):
            if p.accession in held or _stem(p.label) not in stems or p.accession in found:
                continue
            found[p.accession] = (p.label, other_ec)
    return tuple(sorted(found.values()))[:LISTED]


def _named(labels: Sequence[str]) -> str:
    shown = list(labels[:LISTED])
    text = ", ".join(shown)
    if len(labels) > LISTED:
        text += f" and {len(labels) - LISTED} more"
    return text


@dataclass(frozen=True)
class IsozymeNotice:
    ec: str
    organism: str
    count: int
    #: The proteins' labels (gene symbols where UniProt gives one, else entry-name stems), empty
    #: when the index keeps a count and no list for this organism.
    symbols: Tuple[str, ...]
    #: The isoform that was asked for, when one was.
    isoform: Optional[str] = None
    #: What asked for it: "--isoform", or "your description" when it was
    #: read from the sentence (fifth round's review, V5-5).
    asked: str = "--isoform"
    #: Constants whose row names no isozyme although one was asked for. None when that was not
    #: checked (a caller with no cited rows to look at).
    unstated: Optional[Tuple[str, ...]] = ()
    #: False when `isoform` names none of the listed proteins: "TEM-1" under EC 3.5.2.6 in
    #: E. coli K-12, whose listed proteins are the chromosomal ampC and dacA. A plasmid-borne
    #: or other strain's enzyme is not in the reference proteome, and the listed proteins are
    #: then not its isozymes.
    isoform_listed: bool = True
    #: With no isoform asked for: the one isozyme every cited row names (by
    #: its words, its UniProt cell or its paper), when they all name the same
    #: one. The notice then says whose constants these are instead of "may
    #: belong to any of them" (third round's review: human hexokinase's rows
    #: all named GCK).
    measured_as: Optional[str] = None
    #: An isozyme a cited row names, offered as the example in the remedy
    #: before the first listed symbol: "for example --isoform HKDC1" led to a
    #: D-mannose model with a placeholder kcat, while the Km's row measured
    #: HK-I (fourth round of the real-values review).
    suggest: Optional[str] = None

    @property
    def broad(self) -> bool:
        return self.count > BROAD_CLASS

    @property
    def label(self) -> str:
        return organism_precise(self.organism)

    @property
    def elsewhere(self) -> Tuple[Tuple[str, str], ...]:
        """Proteins the nomenclature files under another EC that this list may leave out."""
        return () if self.broad else _filed_elsewhere(self.ec, self.organism)

    @property
    def elsewhere_text(self) -> str:
        found = self.elsewhere
        if not found:
            return ""
        ecs = sorted({ec for _, ec in found})
        return (f"The nomenclature files {_named([name for name, _ in found])} under "
                f"EC {', '.join(ecs)} instead, so this list may leave out a protein papers measured under "
                f"EC {self.ec}")

    @property
    def summary(self) -> str:
        """One clause for the provenance line."""
        if self.isoform:
            return f"EC {self.ec} ({self.count} proteins in {self.label}): {self.isoform} asked for, not every row states it"
        if self.broad:
            return f"EC {self.ec} is a broad class of {self.count} different proteins in {self.label}, none chosen"
        return f"EC {self.ec} is {self.count} proteins in {self.label}, none chosen"

    @property
    def headline(self) -> str:
        """One sentence for the top of the verdict."""
        if self.isoform:
            return (f"{self.isoform} was asked for, but {self._which()} not state which "
                    f"isozyme of EC {self.ec} it measured")
        if self.measured_as:
            return (f"EC {self.ec} is {self.count} proteins in {self.label} and no --isoform was given; "
                    f"every cited row names {self.measured_as}, so these are {self.measured_as}'s "
                    "constants, not the other proteins'")
        if self.broad:
            return (f"EC {self.ec} is a broad class ({self.count} different proteins in {self.label}) and no "
                    "--isoform was given, so the constants may belong to any of them")
        return (
            f"EC {self.ec} is {self.count} proteins in {self.label} and no --isoform "
            "was given, so the constants may belong to any of them"
        )

    def _which(self) -> str:
        names = ", ".join(f"`{n}`" for n in (self.unstated or ()))
        if self.unstated is None:
            return "whether the rows cited state it was not checked, and they may"
        return (f"the row for {names} does" if len(self.unstated) == 1
                else f"the rows for {names} do")

    @property
    def _given(self) -> str:
        """How the isoform was given: by the flag, or read from the sentence."""
        if self.asked == "--isoform":
            return f"--isoform {self.isoform} was given"
        return f"{self.isoform} was read from {self.asked}"

    @property
    def detail(self) -> str:
        """What is the case, for the verdict's concern line."""
        named = f" ({_named(self.symbols)})" if self.symbols and not self.broad else ""
        if self.isoform and not self.isoform_listed:
            return (f"--isoform {self.isoform} names none of the {self.count} proteins the enzyme "
                    f"nomenclature lists for EC {self.ec} in {self.label}{named}: it is not in that reference "
                    "proteome (a plasmid-borne enzyme or another strain's), so those proteins are not its "
                    "isozymes, and whether a cited row measured it is known only from the row's own words")
        if self.isoform:
            if self.unstated is None:
                return (f"{self._given} for EC {self.ec}, which is {self.count} {self.label} "
                        f"proteins{named}, but whether the cited rows state that isozyme was not checked")
            names = ", ".join(f"`{n}`" for n in self.unstated)
            return (f"{self._given} for EC {self.ec}, which is {self.count} {self.label} "
                    f"proteins{named}, but {names} {'comes' if len(self.unstated) == 1 else 'come'} from a row "
                    f"that does not say which isozyme it measured, so whether it measured {self.isoform} is "
                    "unknown; isozymes of one enzyme can differ many-fold in Km and kcat")
        if self.measured_as:
            return (f"EC {self.ec} is {self.count} {self.label} proteins{named} and no --isoform was given; "
                    f"every cited row names {self.measured_as} (in its words, its UniProt cell or its "
                    f"paper's other entries), so the model is of {self.measured_as}, and another of these "
                    "proteins can differ many-fold in Km and kcat")
        if self.broad:
            return (f"{self.count} different {self.label} proteins share EC {self.ec} (a broad class: the "
                    "nomenclature files them under one number, and they are not isozymes of one enzyme) and "
                    "no --isoform was given, so the cited constants may belong to any of them")
        text = (
            f"EC {self.ec} has {self.count} {self.label} isozymes in the enzyme nomenclature's UniProt "
            f"entries{named} and no --isoform was given, so the cited constants may belong to any of "
            f"them; isozymes of one enzyme can differ many-fold in Km and kcat"
        )
        return text + (f". {self.elsewhere_text}" if self.elsewhere else "")

    @property
    def lookup_detail(self) -> str:
        """The same fact for a lookup of constants, which has no --isoform to have been given."""
        named = f" ({_named(self.symbols)})" if self.symbols and not self.broad else ""
        if self.broad:
            return (f"{self.count} different {self.label} proteins share EC {self.ec} (a broad class: they are not "
                    "isozymes of one enzyme), so the constants this lookup returns may belong to any of them")
        text = (f"EC {self.ec} has {self.count} {self.label} isozymes in the enzyme nomenclature's UniProt "
                f"entries{named}, so the constants this lookup returns may belong to any of them; isozymes of one "
                "enzyme can differ many-fold in Km and kcat")
        return text + (f". {self.elsewhere_text}" if self.elsewhere else "")

    @property
    def remedy(self) -> str:
        """What to do, for the verdict's next step. The example is an
        isozyme a cited row names, else the first listed name; with no name
        to give, the remedy says so rather than printing a placeholder
        ("for example --isoform its name", horse liver ADH)."""
        first = self.suggest or (self.symbols[0] if self.symbols else None)
        if self.measured_as and not self.isoform:
            # Neprilysin: every cited row names MME, and "Do this next" offered
            # --isoform MMEL1, another protein (fourth round's review).
            return (f"the model is of {self.measured_as}, the protein every cited row names: pass "
                    f"--isoform {self.measured_as} to keep each constant to rows naming it, or another "
                    "protein's name only to model that protein instead")
        if first is None and not self.isoform:
            return ("pass --isoform with the name the rows' own commentary gives the isozyme you mean "
                    f"(the enzyme nomenclature gives these {self.count} proteins no names --isoform can "
                    "match here), or --subject with another EC number; a constant whose rows name none "
                    "is kept and flagged")
        if self.isoform:
            return ("look for a measurement that states the isozyme, or treat that constant as possibly "
                    "another isozyme's: --isoform takes a constant from a row that names the isozyme, and "
                    "from a row that names none only when no row names it")
        if self.broad:
            return (f"pass --isoform with the protein's gene symbol (for example --isoform {first}) to take each "
                    "constant from a row that names it; a constant whose rows name none is kept and flagged")
        return (f"pass --isoform with one of these names (for example --isoform {first}) to take each constant "
                "from a row whose commentary names that isozyme; a constant whose rows name none is kept and "
                "flagged, and one whose rows all name another isozyme is refused")

    @property
    def text(self) -> str:
        """The full notice, for the section beside the constants."""
        return f"{self.detail}. {self.remedy[0].upper()}{self.remedy[1:]}."


def isozyme_notice(
    ec: Optional[str], organism: Optional[str], isoform: Optional[str] = None,
    *, unstated: Optional[Sequence[str]] = None,
) -> Optional[IsozymeNotice]:
    """The notice, or None when it should stay quiet. See the module docstring.

    With no `isoform` the notice is about which protein is meant. With one,
    `unstated` is the list of cited constants whose row names no isozyme: an
    empty list means every row states it and the notice is quiet; None means
    nobody checked, and the notice says so rather than assume."""
    if not ec or not organism or not _COMPLETE_EC.match(ec.strip()):
        return None
    if isoform and unstated is not None and len(unstated) == 0:
        return None
    found = isozymes(ec.strip(), organism)
    if found.organism is None or found.count < 2:
        return None
    return IsozymeNotice(
        ec=ec.strip(), organism=found.organism, count=found.count, symbols=found.symbols,
        isoform=isoform or None, unstated=None if (isoform and unstated is None) else tuple(unstated or ()),
        isoform_listed=not isoform or found.count > BROAD_CLASS or _listed(found, isoform) is not None)


def _listed(found: Any, label: str) -> Optional[Tuple[Any, Tuple[str, ...]]]:
    """(protein, its names) for the listed protein `label` names, or None."""
    from .isoforms import keys_of, names_for

    wanted = keys_of(label)
    for protein in found.proteins:
        names = names_for(protein.accession, protein.symbol)
        have = set()
        for name in names:
            have |= keys_of(name)
        if wanted & have:
            return protein, tuple(names)
    return None


def describe_isoform(ec: Optional[str], organism: Optional[str], label: Optional[str]) -> Optional[str]:
    """What `--isoform LABEL` was read as, in a sentence: which protein of the EC it names and the
    names its rows are matched on, or that it names none of them. None when the EC is not several
    proteins in the organism (there is nothing to read the label as)."""
    if not ec or not organism or not label or not _COMPLETE_EC.match(ec.strip()):
        return None
    found = isozymes(ec.strip(), organism)
    if found.organism is None or found.count < 2:
        return None
    listed = _listed(found, label)
    if listed is not None:
        protein, names = listed
        return (f"--isoform {label!r} was read as {protein.label}, {organism_precise(found.organism)} protein "
                f"{protein.entry_name} (UniProt {protein.accession}); a row is taken as measuring it when its "
                f"commentary names it as any of: {_named([n for n in names if len(n) <= 40][:8])}")
    shown = _named(found.symbols) if not found.count > BROAD_CLASS else f"{found.count} proteins"
    elsewhere = _symbol_elsewhere(label)
    if elsewhere:
        # CYP2B6 (P20813) is a human gene symbol the enzyme nomenclature
        # files under another EC number than the one BRENDA keeps its
        # kinetics under: the report read it as P20813 and then said it is
        # "not a gene symbol" (fourth round of the real-values review).
        return (f"--isoform {label!r} is the gene symbol of UniProtKB {elsewhere}, which the enzyme "
                f"nomenclature files under another EC number than {ec}, so it is not among the "
                f"{organism_precise(found.organism)} proteins listed for EC {ec} ({shown}); rows are "
                "compared with it by name and by their own UniProt cell, and a row that states it in "
                "other words will not match")
    return (f"--isoform {label!r} is not a gene symbol or name the enzyme nomenclature's UniProt entries give "
            f"any of the {organism_precise(found.organism)} proteins of EC {ec} ({shown}), so rows are compared "
            "with it as spelled and a row that states the isozyme in other words will not match")


def _symbol_elsewhere(label: str) -> Optional[str]:
    """The UniProt accession the gene-symbol table gives `label`, or None."""
    try:
        from caterva.enzymes.symbols import load_symbols

        hits = load_symbols().lookup(label, "HUMAN")
    except Exception:  # noqa: BLE001
        return None
    for hit in hits:
        if getattr(hit, "accession", None):
            return hit.accession
        found = re.search(r"UniProtKB ([A-Z0-9]{6,10})", getattr(hit, "source", "") or "")
        if found:
            return found.group(1)
    return None


def _states(commentary: Optional[str], isoform: str) -> bool:
    try:
        from caterva.bind.core import read_isoform, same_isoform
    except ImportError:  # pragma: no cover - flat layout
        return False
    return same_isoform(read_isoform(commentary), isoform)


def _states_by_accession(measurement: Any, isoform: str) -> bool:
    """Whether the row's own UniProt cell names `isoform`, as the resolver
    read it (`Measurement.row_isoform`): an O75874 row measured IDH1."""
    named = getattr(measurement, "row_isoform", None)
    if not isinstance(named, str) or not named:
        return False
    try:
        from caterva.bind.core import same_isoform
    except ImportError:  # pragma: no cover - flat layout
        return False
    return bool(same_isoform(named, isoform))


def _listable(notice: IsozymeNotice, reading: str) -> Optional[str]:
    """The listed symbol a row's reading names (so it can be offered to
    --isoform), the reading itself when there is no list, or None."""
    if not notice.symbols:
        return reading
    try:
        from caterva.bind.core import same_isoform
    except ImportError:  # pragma: no cover
        return None
    return next((symbol for symbol in notice.symbols if same_isoform(reading, symbol)), None)


def notice_for_model(model: Any) -> Optional[IsozymeNotice]:
    """The notice for a composed model whose constants came from a literature search.

    Reads `subject`, `organism`, `isoform` and `measured` off the model, so a
    model with no measured constant (nothing cited, so nothing that could
    belong to the wrong isozyme) gets none. With an isoform it looks at each
    measured constant's own row commentary and names those that do not state it."""
    measured = getattr(model, "measured", None)
    if not measured:
        return None
    isoform = getattr(model, "isoform", None)
    unstated: Optional[Sequence[str]] = None
    if isoform:
        unstated = [
            str(identifier) for identifier in sorted(measured)
            if not _states(getattr(measured[identifier], "commentary", None), isoform)
            and not _states_by_accession(measured[identifier], isoform)]
    notice = isozyme_notice(getattr(model, "subject", None), getattr(model, "organism", None), isoform,
                            unstated=unstated)
    asked = getattr(model, "isoform_asked", None)
    if notice is not None and isoform and isinstance(asked, str) and asked and asked != "--isoform":
        from dataclasses import replace as _replace
        notice = _replace(notice, asked=asked)
    if notice is None or isoform:
        return notice
    readings = [getattr(m, "row_isoform", None) for m in measured.values()]
    ordered = [getattr(measured[k], "row_isoform", None) for k in sorted(
        measured, key=lambda k: (0 if "Km" in str(k) else 1 if "kcat" in str(k) else 2, str(k)))]
    suggest = next((found for r in ordered if isinstance(r, str) and r
                    for found in [_listable(notice, r)] if found), None)
    if suggest:
        from dataclasses import replace as _replace
        notice = _replace(notice, suggest=suggest)
    if readings and all(isinstance(r, str) and r for r in readings):
        try:
            from caterva.bind.core import same_isoform
        except ImportError:  # pragma: no cover - flat layout
            return notice
        first = readings[0]
        if all(r == first or same_isoform(r, first) for r in readings[1:]):
            from dataclasses import replace as _replace
            return _replace(notice, measured_as=first)
    return notice


__all__ = ["BROAD_CLASS", "IsozymeNotice", "describe_isoform", "isozyme_notice", "notice_for_model", "organism_precise"]
