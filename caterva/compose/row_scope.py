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
- **the preparation.** A His-tagged, immobilised or covalently modified
  enzyme is a real, citable measurement of that preparation and not of the
  free enzyme (ADR 0092). The API flagged it; the model builder did not:
  human LDH's quinoline sulfonamide Ki (0.00059 mM, BRENDA 739793) came
  from a His-tagged construct and the composed report said nothing.

The commentary is parsed by `caterva.bind.core` (`read_isoform`,
`read_mode`), the same reader `caterva bind` uses, and the preparation by
the literature layer's `enzyme_preparation.classify`, the reader the API
uses, so the model builder, the report, the four export formats and the API
cannot disagree about what a row said.
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


def mode_fits(mode: Optional[str], want: Optional[str]) -> bool:
    """True when a row's stated inhibition mode is the one a model of mode
    `want` uses. A mixed-type row counts for a noncompetitive model, as
    this module has always read it: noncompetitive inhibition is the limit
    of mixed inhibition in which the two constants are equal, which is the
    assumption a noncompetitive model already makes. One definition, read
    by this module's report and by `ki_mode`'s choice of row, so the row
    the model is made to carry is never a row the report then calls the
    wrong mechanism."""
    return mode is not None and want is not None and (
        mode == want or (want == "noncompetitive" and mode == "mixed"))


def versus_is(versus: Optional[str], substrate: Optional[str]) -> bool:
    """True when a row's "versus X" names the model's substrate. Compared
    without case or surrounding space, and nothing looser: "D-glucose" and
    "glucose" are not folded together here. A wrong guess at synonymy would
    silence a real concern, where a spurious concern costs the reader one
    sentence. Shared with `ki_mode`, so the row it prefers as "versus the
    substrate" is a row this module does not flag."""
    return bool(versus and substrate and versus.strip().lower() == substrate.strip().lower())


#: The assay substrate a Ki row's commentary names: "hydrolysis of
#: o-aminobenzoyl-SDK-(dinitrophenyl)-P-OH", "with X as substrate".
_ASSAY_SUBSTRATE = re.compile(
    r"\b(?:hydrolysis|cleavage|oxidation|reduction|phosphorylation) of\s+(?P<h>[^,;]+?)\s*(?=[,;]|$)"
    r"|\b(?:with|using)\s+(?P<s>[^,;]+?)\s+as (?:the )?substrate\b", re.IGNORECASE)
#: What an ACE FRET substrate reports on (Araujo et al. 2000; Bersanetti 2004).
_ACE_DOMAIN = ((re.compile(r"SDK", re.IGNORECASE), "an N-domain-selective substrate, so the constant "
                "reports on ACE's N-domain"),
               (re.compile(r"LFK", re.IGNORECASE), "a C-domain-selective substrate, so the constant "
                "reports on ACE's C-domain"),
               (re.compile(r"FRK", re.IGNORECASE), "a substrate both of ACE's domains hydrolyse"))


def assay_substrate(text: Optional[str]) -> Optional[str]:
    """The substrate a Ki row says its assay used, or None."""
    m = _ASSAY_SUBSTRATE.search(text or "")
    if not m:
        return None
    return " ".join((m.group("h") or m.group("s") or "").split()) or None


def _same_compound(a: str, b: str) -> bool:
    try:
        from caterva.checkout import literature_module

        return bool(literature_module("compound_names").same_compound(a, b))
    except Exception:  # noqa: BLE001
        return a.strip().lower() == b.strip().lower()


#: Concern kinds, in the order a reader should meet them.
ISOFORM = "isoform"
ASSAY_SUBSTRATE = "assay_substrate"
MODE_UNSTATED = "mode_unstated"
MODE_MISMATCH = "mode_mismatch"
VERSUS = "versus"
PREPARATION = "preparation"
HALF_SATURATION = "half_saturation"

#: A row reporting a cooperative half-saturation constant, not a Km: "K0.5
#: value, Hill coefficient 1.8" (human glucokinase, BRENDA ref 739603). The
#: same reading as the literature layer's (Tests/row_form.half_saturation).
_HALF_SATURATION = re.compile(
    r"\b[KS]\s*\(?\s*0\.5\s*\)?(?=[\s,;:)]|$)|\b[KS]0\.5\b|\[S\]\s*0\.5|\bS50\b"
    r"|\bHill\s+(?:coefficient|constant|value|number)\b|\bnH\s*[=:]?\s*\d"
    r"|\bhalf[- ]saturation\b|\bsigmoid(?:al)?\s+kinetics\b", re.IGNORECASE)
_HILL = re.compile(r"\bHill\s+coefficient\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

#: How each altered preparation is named in a sentence.
_PREPARED = {
    "tagged": "a tagged construct",
    "immobilised": "an immobilised enzyme",
    "modified": "a covalently modified enzyme",
}


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
    #: "tagged", "immobilised", "modified", "native" or "unstated", as the
    #: literature layer classifies the row; None when that layer is absent.
    preparation: Optional[str] = None

    @property
    def any(self) -> bool:
        return bool(self.concerns)


def _reader():
    try:
        from caterva.bind.core import read_isoform, read_mode
    except ImportError:  # pragma: no cover - flat layout
        from bind.core import read_isoform, read_mode  # type: ignore[no-redef]
    return read_isoform, read_mode


def _preparation(text: str):
    """The literature layer's verdict on how the enzyme was prepared, or
    None where that layer is not installed (the wheel and the app folder do
    not ship it, ADR 0177; a model that resolved a value from BRENDA always
    had it)."""
    try:
        from caterva.checkout import literature_module
        return literature_module("enzyme_preparation").classify(text)
    except Exception:  # LiteratureLayerUnavailable, or an import failure
        return None


def read_scope(
    commentary: Optional[str],
    *,
    motif: Optional[str] = None,
    table: Optional[str] = None,
    substrate: Optional[str] = None,
    isoform: Optional[str] = None,
    row_isoform: Optional[str] = None,
) -> Optional[RowScope]:
    """The scope of one row, judged against the model it was put in.

    `motif` and `table` are the motif the constant belongs to and the table
    it was looked up in; `substrate` is the model's substrate; `isoform` is
    the isoform the model was asked to be about (`--isoform`), if any. None
    when the row carries no commentary: there is nothing to read, which is
    not the same as a row that was read and found consistent.

    `row_isoform` is the isoform the resolver read off the row
    (`Measurement.row_isoform`): its words, else its own UniProt cell. A row
    whose words name none and whose accession is O75874 measured IDH1, and
    is not said to "name no isoform" (ADR 0182, second round).
    """
    if (not commentary or not str(commentary).strip()) and not row_isoform:
        if isoform:
            # Nothing to read, and an isoform was asked for: that it could
            # not be checked is itself the finding.
            return RowScope(None, None, None, (Concern(ISOFORM, (
                f"the row carries no commentary, so whether it measured **{isoform}**, the "
                f"one asked for, is unknown")),))
        return None
    read_isoform, read_mode = _reader()
    text = str(commentary or "")
    wanted = isoform
    isoform = read_isoform(text) or row_isoform
    concerns = []
    if wanted:
        from caterva.compose.isoform import same_isoform
        if isoform is None:
            concerns.append(Concern(ISOFORM, (
                f"the row names no isoform, so whether it measured **{wanted}**, the one "
                f"asked for, is unknown")))
        elif not same_isoform(isoform, wanted):
            concerns.append(Concern(ISOFORM, (
                f"the row measured isoform **{isoform}**, not {wanted}, the one asked for: "
                f"a different protein's constant")))
    elif isoform:
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
            elif not mode_fits(mode, want):
                concerns.append(Concern(MODE_MISMATCH, (
                    f"the row measured **{mode}** inhibition"
                    + (f" (versus {versus})" if versus else "")
                    + f"; this model is {want}, so the value belongs to a different mechanism")))
            assayed = assay_substrate(text)
            if assayed and substrate and not _same_compound(assayed, substrate) and not versus:
                # ACE and captopril: the Ki row is "hydrolysis of
                # o-aminobenzoyl-SDK-(dinitrophenyl)-P-OH", an N-domain FRET
                # substrate; the model's substrate is angiotensin I, and the
                # same paper's row on another substrate is 4.6-fold different
                # (fourth round of the real-values review).
                domain = next((said for pattern, said in _ACE_DOMAIN if pattern.search(assayed)
                               and "dinitrophenyl" in assayed.lower() or pattern.search(assayed)
                               and "dnp" in assayed.lower()), None)
                concerns.append(Concern(ASSAY_SUBSTRATE, (
                    f"the Ki was measured on the hydrolysis of **{assayed}**"
                    + (f" ({domain})" if domain else "")
                    + f", not of {substrate}, this model's substrate: a Ki is specific to the "
                      f"assay it was measured in, and the same inhibitor's Ki on another substrate "
                      f"can differ")))
            if versus and substrate and not versus_is(versus, substrate):
                concerns.append(Concern(VERSUS, (
                    f"the row measured inhibition **versus {versus}**, not versus "
                    f"{substrate}, the substrate in this model: a Ki is specific to the "
                    f"assay it was measured in")))

    if (table or "").lower() in ("km", "km values") and _HALF_SATURATION.search(text):
        hill = _HILL.search(text)
        what = (f"a K0.5 with a Hill coefficient of {hill.group(1)}" if hill
                else "a K0.5, the half-saturation constant of cooperative kinetics")
        concerns.append(Concern(HALF_SATURATION, (
            f"the row is **{what}**, not a Michaelis-Menten Km: a hyperbolic rate law built "
            f"with it approximates a cooperative enzyme")))

    verdict = _preparation(text)
    preparation = getattr(verdict, "status", None)
    # `differs_for` honours a curator's "does not alter the Km value": the
    # clause names one quantity, and only that quantity is excused.
    if verdict is not None and verdict.differs_for(table) and preparation in _PREPARED:
        concerns.append(Concern(PREPARATION, (
            f"the row measured **{_PREPARED[preparation]}** (\"{verdict.evidence}\"), not the "
            f"free enzyme; a real measurement of that preparation, which may not be the "
            f"protein you mean")))
    return RowScope(isoform, mode, versus, tuple(concerns), preparation)


#: A named natural variant of one enzyme: "HIV-1 subtype C protease",
#: "clade B". Not an isoform (one gene, one protein) and not a mutant.
_SUBTYPE = re.compile(r"\b(subtype|clade)\s+([A-Z][A-Z0-9]?|\d{1,2}[A-Z]?)\b", re.IGNORECASE)


def variant_mix(commentaries: "dict[str, Optional[str]]") -> Optional[str]:
    """A sentence when the constants' rows name different subtypes (or one
    names a subtype and another names none), else None.

    HIV-1 protease, ADR 0182 second round: the Km and kcat came from "HIV-1
    subtype C protease" rows (ref 678346) and the Ki from "recombinant LAI
    wild-type enzyme" (ref 664013), a subtype B strain the row does not
    call one. Each row's own note named only itself, so one model of two
    variants read as one enzyme's."""
    named: dict = {}
    for identifier, text in sorted(commentaries.items()):
        found = sorted({f"{m.group(1).lower()} {m.group(2).upper()}"
                        for m in _SUBTYPE.finditer(text or "")})
        named[identifier] = " and ".join(found) if found else None
    labels = set(named.values())
    if len(named) < 2 or labels == {None} or len(labels) == 1:
        return None
    groups: dict = {}
    for identifier, label in named.items():
        groups.setdefault(label, []).append(f"`{identifier}`")
    parts = [(f"{', '.join(ids)} measured {label}" if label else
              f"{', '.join(ids)} {'names' if len(ids) == 1 else 'name'} no subtype")
             for label, ids in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))]
    return ("the constants' rows are not all of one variant of the enzyme: " + "; ".join(parts)
            + ". The model may combine constants of different variants; a row naming no subtype "
            "may be any (often the reference strain)")


__all__ = [
    "Concern", "RowScope", "read_scope", "mode_fits", "versus_is", "variant_mix",
    "MODE_OF_MOTIF", "INHIBITION_TABLES",
    "ISOFORM", "MODE_UNSTATED", "MODE_MISMATCH", "VERSUS", "PREPARATION", "HALF_SATURATION",
]
