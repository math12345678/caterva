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
the EC and the request names no `--isoform`, the report says so, names them,
and says the cited constants may belong to any of them and that `--isoform`
is how to state which is meant. It does not read isozymes out of BRENDA's
reference titles, does not pick one, and does not change a constant.

WHEN IT STAYS QUIET
-------------------
When `--isoform` was given (the constants were then chosen for it, and the
report says what that did); when the EC number has one protein in the
organism, or none; when no organism was given, because there is nothing to
count; and when the organism is one the index does not recognise, because
"no entries" would then mean "not known".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .finder import isozymes
from .index import organism_label

_COMPLETE_EC = re.compile(r"^\d+\.\d+\.\d+\.n?\d+$")


@dataclass(frozen=True)
class IsozymeNotice:
    ec: str
    organism: str
    count: int
    #: The entries' symbols (HXK1, HXK2, ...), empty when the index keeps a
    #: count and no list for this organism.
    symbols: Tuple[str, ...]

    @property
    def headline(self) -> str:
        """One sentence for the top of the verdict."""
        return (
            f"EC {self.ec} is {self.count} proteins in {organism_label(self.organism)} and no --isoform "
            "was given, so the constants may belong to any of them"
        )

    @property
    def detail(self) -> str:
        """What is the case, for the verdict's concern line."""
        label = organism_label(self.organism)
        named = f" ({', '.join(self.symbols)})" if self.symbols else ""
        return (
            f"EC {self.ec} has {self.count} {label} isozymes in the enzyme nomenclature's UniProt "
            f"entries{named} and no --isoform was given, so the cited constants may belong to any of "
            f"them; isozymes of one enzyme can differ many-fold in Km and kcat"
        )

    @property
    def remedy(self) -> str:
        """What to do, for the verdict's next step."""
        return (
            "pass --isoform with the isoform's name as the papers write it (for example "
            "--isoform LDH-A) to take each constant from a row that measured it"
        )

    @property
    def text(self) -> str:
        """The full notice, for the section beside the constants."""
        return f"{self.detail}. {self.remedy[0].upper()}{self.remedy[1:]}."


def isozyme_notice(ec: Optional[str], organism: Optional[str], isoform: Optional[str]) -> Optional[IsozymeNotice]:
    """The notice, or None when it should stay quiet. See the module docstring."""
    if isoform or not ec or not organism or not _COMPLETE_EC.match(ec.strip()):
        return None
    found = isozymes(ec.strip(), organism)
    if found.organism is None or found.count < 2:
        return None
    return IsozymeNotice(ec=ec.strip(), organism=found.organism, count=found.count, symbols=found.symbols)


def notice_for_model(model: Any) -> Optional[IsozymeNotice]:
    """The notice for a composed model whose constants came from a literature search.

    Reads `subject`, `organism`, `isoform` and `measured` off the model, so a
    model with no measured constant (nothing cited, so nothing that could
    belong to the wrong isozyme) gets none.
    """
    if not getattr(model, "measured", None):
        return None
    return isozyme_notice(
        getattr(model, "subject", None), getattr(model, "organism", None), getattr(model, "isoform", None))


__all__ = ["IsozymeNotice", "isozyme_notice", "notice_for_model"]
