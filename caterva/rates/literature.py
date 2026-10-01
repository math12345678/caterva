"""The fitted constants held against the cited ones.

WHAT IS ASKED, AND OF WHOM
--------------------------
The literature layer's resolver (Tests/fallback_logic.py,
`resolve_kinetic_value`), the one `caterva compose`, the API and the
TypeScript CLI all ask, asked the way compose has asked it since 2026-09-30
(compose/narrowed.py):

  Km   under the SUBSTRATE's name, from the km table, with the isoform
       `--isoform` names.
  Ki   under the INHIBITOR's name (BRENDA files a Ki under the inhibitor),
       from the ki table, with the isoform, the inhibition MODE of the law
       the data support, and the model's substrate, so the resolver ranks
       every row by what this experiment measured before it chooses on
       evidence. A competitive fit's Ki is compared with the row the
       resolver returns for "competitive", an uncompetitive fit's Ki' with
       "uncompetitive", a noncompetitive fit's constant with
       "noncompetitive" (a mixed row stands in for it, as row_scope reads
       it). Which constant each is: models.py's module docstring.

A mixed fit's two constants are not looked up: a database row does not say
which of the two it measured (`compose/library.MIXED_KI_REFUSAL`). When the
data cannot tell two mechanisms apart, each one's constant is compared with
its own mode's row, and the report says the comparison is conditional on a
mechanism the data did not choose.

WHAT IS PRINTED
---------------
The cited value, its unit, the BRENDA reference, the row's commentary and
what `compose/row_scope` reads in it (isoform, mode, what it was measured
against, the preparation), the spread of the rows the resolver found equally
well evidenced, whether the fitted profile interval contains the cited
value, and the ratio of the fitted estimate to it, both in one unit. When
the data do not determine the constant (its profile is open on a side, or
determine.py found it confounded with Vmax), there is no fitted estimate to
take a ratio of: the optimiser stopped somewhere along a flat direction,
1e8 times beyond the data at worst. Then only the one-sided interval is held
against the cited value, and the ratio is left out. A
fitted interval that excludes a cited value is a finding about two
measurements, not an error in either: assay conditions, isoform and
construct differ between laboratories, which is what the commentary is
printed for.

UNITS
-----
The fitted constant is in the column's unit and the cited one in BRENDA's
(mM, as a rule). Both go through `compose/units.py`'s parser; a column in an
arbitrary unit (ppm, mg/mL) cannot be converted without a molar mass nobody
stated, and the comparison is refused for it, by name, rather than guessed.

WHERE IT CANNOT RUN
-------------------
The literature layer is not in the wheel or the downloaded app folder (ADR
0177). There, as in compose, the comparison is refused with the reason, the
fit is still reported, and the exit code is 3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from caterva.compose.units import UnitError, parse_unit
from caterva.rates.fit import Interval
from caterva.rates.models import RateLaw
from caterva.rates.table import ColumnUnit


class LiteratureUnavailable(RuntimeError):
    """The literature layer cannot be imported here (the app folder)."""


Resolver = Callable[..., Any]


def default_resolver() -> Resolver:
    """The literature layer's resolver, or LiteratureUnavailable naming why."""
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        return literature_module("fallback_logic").resolve_kinetic_value
    except LiteratureLayerUnavailable as exc:
        raise LiteratureUnavailable(str(exc)) from exc


@dataclass
class Comparison:
    #: "Km", "Ki" or "Ki'", as fitted.
    constant: str
    law: str
    group: Optional[str]
    #: The name the resolver was asked under, and the mode, if any.
    compound: str
    mode: Optional[str]
    fitted: Optional[Interval]
    fitted_unit: str
    found: bool = False
    cited: Optional[float] = None
    cited_unit: Optional[str] = None
    reference: Optional[str] = None
    organism: Optional[str] = None
    commentary: Optional[str] = None
    source: Optional[str] = None
    #: The frontier: rows the resolver found equally well evidenced.
    spread: Optional[tuple] = None
    spread_rows: int = 0
    tie: Optional[str] = None
    concerns: List[str] = field(default_factory=list)
    evidence_against: Optional[str] = None
    #: The mode the contradicting row states, when there is one.
    evidence_mode: Optional[str] = None
    #: Whether the data determine the fitted constant (module docstring).
    #: When False the converted interval's estimate is not a value, and no
    #: ratio is computed.
    determined: bool = True
    #: The fitted interval in the cited unit, and the estimate over the cited.
    converted: Optional[Interval] = None
    contains: Optional[bool] = None
    ratio: Optional[float] = None
    #: Why no comparison was made, when none was.
    refused: Optional[str] = None
    #: True when THIS command declined the comparison (a unit it cannot
    #: convert, a mixed constant no row can be matched to); False when the
    #: resolver ran and returned no row, which is an answer, not a refusal.
    declined: bool = False
    #: Mechanism caveat when the data did not choose it.
    conditional: Optional[str] = None


def _convert(interval: Interval, factor: float) -> Interval:
    return Interval(interval.label, interval.estimate * factor,
                    None if interval.low is None else interval.low * factor,
                    None if interval.high is None else interval.high * factor,
                    interval.level, None if interval.se is None else interval.se * factor)


def _spread(result: Any) -> tuple:
    values = []
    for row in getattr(result, "ensemble_candidates", None) or []:
        value = row.get("value") if isinstance(row, dict) else getattr(row, "value", None)
        if value is not None:
            values.append(float(value))
    if not values:
        return None, 0
    return (min(values), max(values)), len(values)


def _scope(commentary: Optional[str], law: RateLaw, table: str, substrate: Optional[str],
           isoform: Optional[str]) -> List[str]:
    try:
        from caterva.compose.row_scope import read_scope
    except ImportError:  # pragma: no cover - flat layout
        return []
    scope = read_scope(commentary, motif=law.motif, table=table, substrate=substrate,
                       isoform=isoform)
    return [c.plain for c in scope.concerns] if scope is not None else []


def _evidence(result: Any) -> Optional[str]:
    e = getattr(result, "mechanism_evidence", None)
    if e is None:
        return None
    return (f"BRENDA ref {e.reference_id} states {e.inhibition_mode} inhibition versus {e.versus} "
            f"({e.value:g} {e.unit or ''}), measured against {e.model_substrate}: evidence against "
            f"a {e.model_mode} mechanism for this inhibitor, whatever row is compared")


def _refused_reason(result: Any) -> str:
    source = getattr(result, "source", "not_found")
    if source == "mode_withheld":
        modes = getattr(result, "modes_available", None) or []
        return ("every BRENDA row for it states another inhibition mode"
                + (f" ({'; '.join(modes)})" if modes else ""))
    if source == "isoform_withheld":
        found = getattr(result, "isoforms_available", None) or []
        return "BRENDA holds it only for other isoforms" + (f" ({', '.join(found)})" if found else "")
    if source == "cross_species_withheld":
        orgs = getattr(result, "cross_species_organisms_available", None) or []
        return ("BRENDA holds it for other organisms only"
                + (f" ({', '.join(orgs)})" if orgs else "") + "; values are species-specific and "
                "are not borrowed across species")
    if source == "variant_withheld":
        return "BRENDA holds it only for protein variants (mutants), which are not the enzyme"
    return "the resolver found no value for this enzyme, organism and compound"


def compare(
    *,
    constant: str,
    law: RateLaw,
    interval: Optional[Interval],
    column: ColumnUnit,
    ec: str,
    organism: Optional[str],
    compound: str,
    substrate: Optional[str],
    isoform: Optional[str],
    group: Optional[str] = None,
    resolver: Optional[Resolver] = None,
    conditional: Optional[str] = None,
    determined: bool = True,
) -> Comparison:
    """One fitted constant against the resolver's row for it. `determined`
    is False when determine.py found the constant undetermined even though
    its own profile may be closed (module docstring)."""
    is_ki = constant in ("Ki", "Ki'")
    out = Comparison(constant, law.name, group, compound, law.mode if is_ki else None,
                     interval, column.text, conditional=conditional,
                     determined=bool(determined and interval is not None and interval.bounded))
    if interval is None:
        out.refused = f"{constant} was not fitted"
        out.declined = True
        return out
    if not column.convertible:
        out.refused = (f"the {'inhibitor' if is_ki else 'substrate'} column is in {column.text!r}, "
                       f"which cannot be converted to a molar concentration without a molar mass "
                       f"the file does not give; a literature comparison needs a molar unit")
        out.declined = True
        return out
    if is_ki and law.mode is None:
        from caterva.compose.library import MIXED_KI_REFUSAL

        out.refused = MIXED_KI_REFUSAL
        out.declined = True
        return out
    resolve = resolver or default_resolver()
    kwargs: Dict[str, Any] = {"quantity": "ki" if is_ki else "km", "isoform": isoform or None}
    if is_ki:
        kwargs.update(inhibition_mode=law.mode, model_substrate=substrate)
    result = resolve(ec, organism, compound, **kwargs)
    out.source = getattr(result, "source", None)
    if not getattr(result, "found", False) or getattr(result, "value", None) is None:
        out.refused = _refused_reason(result)
        return out
    out.found = True
    out.cited = float(result.value)
    out.cited_unit = result.unit
    citation = getattr(result, "citation", None)
    out.reference = getattr(citation, "reference_id", None) if citation is not None else None
    out.organism = getattr(result, "organism", None)
    out.commentary = getattr(result, "commentary", None)
    (spread, count) = _spread(result)
    out.spread, out.spread_rows = spread, count
    tie = getattr(result, "selection_tie", None)
    out.tie = getattr(tie, "reason", None) if tie is not None else None
    out.concerns = _scope(out.commentary, law, "ki" if is_ki else "km", substrate, isoform)
    out.evidence_against = _evidence(result)
    evidence = getattr(result, "mechanism_evidence", None)
    out.evidence_mode = getattr(evidence, "inhibition_mode", None) if evidence is not None else None
    try:
        cited_unit = parse_unit(result.unit or "")
    except UnitError:
        cited_unit = None
    if cited_unit is None or dict(cited_unit.dimensions) != dict(column.unit.dimensions):
        out.refused = (f"the cited value is in {result.unit!r}, which does not convert to the "
                       f"column's {column.text!r}")
        out.declined = True
        return out
    factor = column.unit.scale / cited_unit.scale
    out.converted = _convert(interval, factor)
    out.contains = out.converted.contains(out.cited)
    out.ratio = (out.converted.estimate / out.cited
                 if out.determined and out.cited > 0 else None)
    return out


__all__ = ["Comparison", "LiteratureUnavailable", "compare", "default_resolver"]
