"""Keep the constants that were measured on the isoform a model is about.

Human lactate dehydrogenase is three proteins. BRENDA 711801 gives gossypol's
Ki for each: 0.0014 mM for LDH-B, 0.0019 mM for LDH-A, 0.0042 mM for LDH-C,
from one paper, in three rows. The resolver ranks them as equally well
evidenced and returns the first, LDH-B's. A model of LDH-A, the isoform
cancer glycolysis runs through, then carries LDH-B's constant; the report says
so (row_scope), and until now there was nothing the user could do about it.

`caterva compose --isoform LDH-A` asks for the isoform. For each measured
constant, among the rows the resolver already ranked:

1. a row that names the isoform asked for is used;
2. failing that, a row that names no isoform is used, and the report says
   whether it measured that isoform is unknown;
3. failing that, every row measured another isoform, and the constant is
   refused rather than filled with a different protein's value.

A row is read by `caterva.bind.core.read_isoform`, the reader `caterva bind
--isoform` uses, so the two commands agree about what a row measured. Names
compare without case, spaces or hyphens: "LDH-A", "ldha" and "LDH A" are one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional


def _key(name: Optional[str]) -> Optional[str]:
    return re.sub(r"[\s_-]+", "", name).lower() if name else None


def same_isoform(a: Optional[str], b: Optional[str]) -> bool:
    return a is not None and b is not None and _key(a) == _key(b)


def _read_isoform(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    try:
        from caterva.bind.core import read_isoform
    except ImportError:  # pragma: no cover - flat layout
        from bind.core import read_isoform  # type: ignore[no-redef]
    return read_isoform(text)


@dataclass
class IsoformSelection:
    #: The measured constants to build the model from.
    measured: Dict[str, Any]
    #: Constants refused because every row measured another isoform: id -> why.
    refused: Dict[str, str] = field(default_factory=dict)
    #: What was changed or could not be told, one sentence per constant.
    notes: List[str] = field(default_factory=list)


def _from_row(m: Any, row: Mapping[str, Any], because: str) -> Any:
    """The same Measurement, taken from another of its own ranked rows."""
    conditions = row.get("conditions") or None
    unreported = tuple(
        what for what, word in (("pH", "ph"), ("temperature", "temperature"))
        if conditions and re.search(rf"\b{word}\b[^,]*not specified", conditions, re.IGNORECASE)
    )
    ref = row.get("reference_id")
    return replace(
        m,
        value=float(row["value"]),
        citation=f"BRENDA ref {ref}" if ref else m.citation,
        reference_id=str(ref) if ref else m.reference_id,
        organism=row.get("organism") or m.organism,
        commentary=conditions,
        assay_ph=row.get("ph"),
        assay_temperature_c=row.get("temperature_c"),
        assay_buffer=row.get("buffer"),
        assay_unreported=unreported,
        chosen_because=because,
    )


def select_isoform(measured: Mapping[str, Any], isoform: str) -> IsoformSelection:
    """Each measured constant, taken from a row that measured `isoform` where
    the resolver ranked one. See the module docstring for the three cases."""
    out = IsoformSelection(measured={})
    for identifier in sorted(measured):
        m = measured[identifier]
        chosen = _read_isoform(getattr(m, "commentary", None))
        if same_isoform(chosen, isoform):
            out.measured[identifier] = m
            continue
        rows = [r for r in getattr(m, "alternatives", ()) or ()
                if isinstance(r, dict) and r.get("value") is not None
                and (r.get("unit") in (None, m.unit))]
        named = [(r, _read_isoform(r.get("conditions"))) for r in rows]
        matching = [r for r, iso in named if same_isoform(iso, isoform)]
        if matching:
            row = matching[0]
            out.measured[identifier] = _from_row(m, row, f"the row for {isoform}, as --isoform asked")
            was = f"measured {chosen}" if chosen else "named no isoform"
            out.notes.append(
                f"`{identifier}`: the resolver's pick ({m.value:g} {m.unit}) {was}; the row for "
                f"{isoform} ({float(row['value']):g} {m.unit}, BRENDA ref {row.get('reference_id')}) "
                f"is used instead, as --isoform asked")
            continue
        if chosen is None:
            out.measured[identifier] = m
            out.notes.append(
                f"`{identifier}`: no ranked row names {isoform}; the one used names no isoform, "
                f"so whether it measured {isoform} is unknown")
            continue
        unnamed = [r for r, iso in named if iso is None]
        if unnamed:
            out.measured[identifier] = _from_row(
                m, unnamed[0], f"a row naming no isoform, used because none names {isoform}")
            out.notes.append(
                f"`{identifier}`: the resolver's pick measured {chosen}, not {isoform}; a row naming "
                f"no isoform ({float(unnamed[0]['value']):g} {m.unit}) is used instead, and whether it "
                f"measured {isoform} is unknown")
            continue
        seen = sorted({iso for _, iso in named if iso} | {chosen})
        out.refused[identifier] = (
            f"no row for {isoform}: the rows BRENDA holds measured {', '.join(seen)}, and a constant "
            f"of another isoform is a different protein's (--isoform {isoform})")
    return out


__all__ = ["IsoformSelection", "select_isoform", "same_isoform"]
