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
    #: Constants whose row names no isozyme although one was asked for. None when that was not
    #: checked (a caller with no cited rows to look at).
    unstated: Optional[Tuple[str, ...]] = ()

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
    def detail(self) -> str:
        """What is the case, for the verdict's concern line."""
        named = f" ({_named(self.symbols)})" if self.symbols and not self.broad else ""
        if self.isoform:
            if self.unstated is None:
                return (f"--isoform {self.isoform} was given for EC {self.ec}, which is {self.count} {self.label} "
                        f"proteins{named}, but whether the cited rows state that isozyme was not checked")
            names = ", ".join(f"`{n}`" for n in self.unstated)
            return (f"--isoform {self.isoform} was given for EC {self.ec}, which is {self.count} {self.label} "
                    f"proteins{named}, but {names} {'comes' if len(self.unstated) == 1 else 'come'} from a row "
                    f"that does not say which isozyme it measured, so whether it measured {self.isoform} is "
                    "unknown; isozymes of one enzyme can differ many-fold in Km and kcat")
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
        """What to do, for the verdict's next step."""
        first = self.symbols[0] if self.symbols else "its name"
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
        isoform=isoform or None, unstated=None if (isoform and unstated is None) else tuple(unstated or ()))


def describe_isoform(ec: Optional[str], organism: Optional[str], label: Optional[str]) -> Optional[str]:
    """What `--isoform LABEL` was read as, in a sentence: which protein of the EC it names and the
    names its rows are matched on, or that it names none of them. None when the EC is not several
    proteins in the organism (there is nothing to read the label as)."""
    if not ec or not organism or not label or not _COMPLETE_EC.match(ec.strip()):
        return None
    found = isozymes(ec.strip(), organism)
    if found.organism is None or found.count < 2:
        return None
    from .isoforms import keys_of, names_for

    wanted = keys_of(label)
    for protein in found.proteins:
        names = names_for(protein.accession, protein.symbol)
        have = set()
        for name in names:
            have |= keys_of(name)
        if wanted & have:
            return (f"--isoform {label!r} was read as {protein.label}, {organism_precise(found.organism)} protein "
                    f"{protein.entry_name} (UniProt {protein.accession}); a row is taken as measuring it when its "
                    f"commentary names it as any of: {_named([n for n in names if len(n) <= 40][:8])}")
    shown = _named(found.symbols) if not found.count > BROAD_CLASS else f"{found.count} proteins"
    return (f"--isoform {label!r} is not a gene symbol or name the enzyme nomenclature's UniProt entries give "
            f"any of the {organism_precise(found.organism)} proteins of EC {ec} ({shown}), so rows are compared "
            "with it as spelled and a row that states the isozyme in other words will not match")


def _states(commentary: Optional[str], isoform: str) -> bool:
    try:
        from caterva.bind.core import read_isoform, same_isoform
    except ImportError:  # pragma: no cover - flat layout
        return False
    return same_isoform(read_isoform(commentary), isoform)


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
            if not _states(getattr(measured[identifier], "commentary", None), isoform)]
    return isozyme_notice(getattr(model, "subject", None), getattr(model, "organism", None), isoform,
                          unstated=unstated)


__all__ = ["BROAD_CLASS", "IsozymeNotice", "describe_isoform", "isozyme_notice", "notice_for_model", "organism_precise"]
