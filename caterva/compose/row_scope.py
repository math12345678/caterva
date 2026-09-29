"""What a measured constant's own source row says it measured, and where that
makes it the wrong number for the model it was put in.

A BRENDA row carries a free-text commentary beside its value. For most rows
it is assay conditions. For some it says the thing that decides whether the
value belongs in this model at all:

- **the isoform.** Human LDH has three. `--inhibitor gossypol` resolves to
  0.0014 mM, which is gossypol's Ki for LDH-B; the same paper gives 0.0019
  mM for LDH-A and 0.0042 mM for LDH-C. A model of "human LDH" built on the
  first is a model of one protein that says it is about another.
- **the inhibition mode**, for an inhibition constant. A competitive Ki and
  a noncompetitive Ki are constants of different mechanisms, and a row that
  states no mode leaves it unknown which one this is.
- **what the inhibitor was measured against.** A Ki measured versus NADH
  is not the Ki versus pyruvate, even in a competitive model.

The commentary is parsed by `caterva.bind.core` (`read_isoform`,
`read_mode`), the same reader `caterva bind` uses, so the model builder, the
report and the four export formats cannot disagree about what a row said.
This module decides only what that reading MEANS for a given model; the
report prints it in Markdown and the exports print it in their own columns
and comments, from the one `RowScope` this returns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

#: The inhibition mode each inhibition motif's Ki belongs to. Product
#: inhibition in these motifs is the product competing for the active site.
MODE_OF_MOTIF = {
    "competitive_inhibition": "competitive",
    "uncompetitive_inhibition": "uncompetitive",
    "noncompetitive_inhibition": "noncompetitive",
    "product_inhibition": "competitive",
}

#: The source tables that hold inhibition constants. Only these rows are read
#: for a mode: a Km row's commentary says nothing about inhibition, and
#: reporting "states no inhibition mode" for one would be noise.
INHIBITION_TABLES = frozenset({"ki"})

#: Concern kinds, in the order a reader should meet them.
ISOFORM = "isoform"
MODE_UNSTATED = "mode_unstated"
MODE_MISMATCH = "mode_mismatch"
VERSUS = "versus"


@dataclass(frozen=True)
class Concern:
    kind: str
    #: Markdown, as the report prints it (bold marks what differs).
    text: str

    @property
    def plain(self) -> str:
        """The same sentence without Markdown, for a CSV cell or a comment."""
        return re.sub(r"\*\*(.+?)\*\*", r"\1", self.text)


@dataclass(frozen=True)
class RowScope:
    """What one source row says it measured."""
    #: The isoform the row names, or None when it names none.
    isoform: Optional[str]
    #: The inhibition mode the row states, "unstated" when it states none,
    #: and None when the constant is not an inhibition constant.
    mode: Optional[str]
    #: The molecule the inhibition was measured against, when stated.
    versus: Optional[str]
    concerns: Tuple[Concern, ...] = ()

    @property
    def any(self) -> bool:
        return bool(self.concerns)


def _reader():
    try:
        from caterva.bind.core import read_isoform, read_mode
    except ImportError:  # pragma: no cover - flat layout
        from bind.core import read_isoform, read_mode  # type: ignore[no-redef]
    return read_isoform, read_mode


def read_scope(
    commentary: Optional[str],
    *,
    motif: Optional[str] = None,
    table: Optional[str] = None,
    substrate: Optional[str] = None,
) -> Optional[RowScope]:
    """The scope of one row, judged against the model it was put in.

    `motif` and `table` are the motif the constant belongs to and the table
    it was looked up in; `substrate` is the model's substrate. None when the
    row carries no commentary: there is nothing to read, which is not the
    same as a row that was read and found consistent.
    """
    if not commentary or not str(commentary).strip():
        return None
    read_isoform, read_mode = _reader()
    text = str(commentary)
    isoform = read_isoform(text)
    concerns = []
    if isoform:
        concerns.append(Concern(ISOFORM, (
            f"the row measured isoform {isoform}; if the enzyme you mean is another "
            f"isoform, this is a different protein's constant")))

    mode: Optional[str] = None
    versus: Optional[str] = None
    if table in INHIBITION_TABLES:
        mode, versus = read_mode(text)
        want = MODE_OF_MOTIF.get(motif or "")
        if want:
            if mode == "unstated":
                concerns.append(Concern(MODE_UNSTATED, (
                    f"the row states no inhibition mode, so whether it is the {want} "
                    f"constant this model uses is unknown")))
            elif mode != want and not (want == "noncompetitive" and mode == "mixed"):
                concerns.append(Concern(MODE_MISMATCH, (
                    f"the row measured **{mode}** inhibition"
                    + (f" (versus {versus})" if versus else "")
                    + f"; this model is {want}, so the value belongs to a different mechanism")))
            if versus and substrate and versus.strip().lower() != substrate.strip().lower():
                concerns.append(Concern(VERSUS, (
                    f"the row measured inhibition **versus {versus}**, not versus "
                    f"{substrate}, the substrate in this model: a Ki is specific to the "
                    f"assay it was measured in")))
    return RowScope(isoform, mode, versus, tuple(concerns))


__all__ = [
    "Concern", "RowScope", "read_scope", "MODE_OF_MOTIF", "INHIBITION_TABLES",
    "ISOFORM", "MODE_UNSTATED", "MODE_MISMATCH", "VERSUS",
]
