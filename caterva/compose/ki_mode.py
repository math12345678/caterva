"""Take an inhibition constant from a row whose stated mode fits the model.

BRENDA ref 739793 gives two Ki values for human lactate dehydrogenase and
3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic
acid, from one paper, under one set of conditions:

    0.00059 mM  "pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate
                 reduction, competitive versus NADH"
    0.00252 mM  "pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate
                 reduction, noncompetitive versus pyruvate"

They are constants of two different mechanisms. The resolver grades rows
on their evidence (assay completeness, closeness of conditions, organism),
gives these two identical grades, and returns the first. A noncompetitive
model built with `--substrate pyruvate` therefore carried 0.00059 mM, the
competitive constant measured against NADH, and `row_scope` said so in the
report ("the row measured **competitive** inhibition (versus NADH); this
model is noncompetitive, so the value belongs to a different mechanism")
while the row the model needed sat in the same `alternatives`, one line
below. The report was right and the model was still wrong.

For an inhibition constant (a row from `row_scope.INHIBITION_TABLES`) of an
inhibition motif (one in `row_scope.MODE_OF_MOTIF`), this chooses among the
rows the resolver already ranked, in this order:

1. rows whose stated mode is the model's. A mixed row counts for a
   noncompetitive model (`row_scope.mode_fits`, the definition the report
   uses). Among these, a row measured versus the model's substrate comes
   first, then a row that names nothing it was measured against, then a row
   measured versus another molecule; and within each of those, a row of the
   model's own mode before a mixed row standing in for noncompetitive.
   A row stating "versus pyruvate" is known to be the assay a model with
   substrate pyruvate means; a row stating nothing may be the NADH assay,
   so it comes second, not equal;
2. failing that, rows stating no mode at all. Whether the value is this
   model's constant is then unknown, and `row_scope` says so in the report
   for the row carried;
3. failing that, every row states another mode, and the constant is
   refused rather than filled with another mechanism's value. The reason
   names the modes found and `--any-mode`, which keeps the resolver's pick.

Ties inside a rank keep the resolver's order, with its pick first, so a
row is only ever replaced by one that is better for the model and never by
one that is merely different. A row in another unit is never substituted,
as in `isoform.py`: the carried Measurement keeps the pick's unit, so a
value moved across without conversion would be wrong by the factor between
the two units.

The selection is on by default because it is a correctness fix, not a
preference: a model that says it is noncompetitive and simulates a
competitive constant is wrong whether or not its report admits it.
`--any-mode` turns it off and keeps the resolver's pick whatever it states,
and the notes say what the default would have done; `row_scope` still
flags the mismatch in the report and in every export.

WITH --isoform: THE ISOFORM FIRST, THEN THE MODE
------------------------------------------------
`isoform.select_isoform` runs first, over the same alternatives, and this
runs on what it kept. Rows are then ranked by isoform first and mode
second: a row naming the isoform asked for beats a row naming none,
whatever either states about mode, and a row naming another isoform is
never taken. The order is deliberate. An isoform is a different protein,
and the user named the protein explicitly; a mode that is unstated is an
unknown about the right protein, which the report states. BRENDA ref 702238
is the case that separates the two orders. It gives human monoamine
oxidase's Ki for phenylhydrazine as 0.205 mM (MAO-A, "determined from
competitive inhibition data"), 0.523 mM (MAO-A) and 0.791 mM (MAO-B), the
last two from Kitz-Wilson plots, which state no mode. For a competitive
model with `--isoform MAO-B`, ranking by mode first makes MAO-A's 0.205 mM
the best row, a constant of the other protein; ranking by isoform first
keeps 0.791 mM, and the report says its mode is unknown. For benzylhydrazine the same paper gives MAO-A
rows of 1.95 mM (Kitz-Wilson) and 2.096 mM (competitive); `--isoform MAO-A`
takes the first it ranks, 1.95, and this then moves a competitive model to
2.096, and never to MAO-B's competitive 0.026 mM. A row that is known to be
the wrong mechanism is never taken either way: when every row for the
isoform states another mode, a row naming no isoform that fits is used, and
the note says whether it measured the isoform is unknown.

A row is read by `caterva.bind.core.read_mode`, the reader `row_scope` and
`caterva bind` use, so the three agree about what a row states. That reader
takes the first mode a commentary names. BRENDA's hexokinase Inhibitors
table has rows naming two, one per substrate ("mixed versus MgATP2-,
competitive inhibition versus 2-deoxyglucose", ref 660949); none of the Ki
rows parsed from the hexokinase, LDH and monoamine oxidase pages on
2026-09-29 does, and one that did would be read as its first mode here
exactly as in the report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

try:
    from caterva.compose.isoform import same_isoform
    from caterva.compose.row_scope import (
        INHIBITION_TABLES, MODE_OF_MOTIF, mode_fits, versus_is,
    )
except ImportError:  # pragma: no cover - flat layout
    from compose.isoform import same_isoform  # type: ignore[no-redef]
    from compose.row_scope import (  # type: ignore[no-redef]
        INHIBITION_TABLES, MODE_OF_MOTIF, mode_fits, versus_is,
    )

#: The flag that keeps the resolver's pick, named in every refusal.
ANY_MODE_FLAG = "--any-mode"


def _read(text: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    """(mode, versus, isoform) of one row's commentary."""
    try:
        from caterva.bind.core import read_isoform, read_mode
    except ImportError:  # pragma: no cover - flat layout
        from bind.core import read_isoform, read_mode  # type: ignore[no-redef]
    mode, versus = read_mode(text)
    return mode, versus, read_isoform(text)


@dataclass
class ModeSelection:
    #: The measured constants to build the model from.
    measured: Dict[str, Any]
    #: Constants refused because every row states another mode: id -> why.
    refused: Dict[str, str] = field(default_factory=dict)
    #: What was changed, or what --any-mode kept, one sentence per constant.
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Row:
    """One ranked row, read once."""
    value: float
    reference: Optional[str]
    conditions: Optional[str]
    mode: str
    versus: Optional[str]
    isoform: Optional[str]
    #: The dict the resolver ranked; None for the pick itself.
    source: Optional[Mapping[str, Any]]
    #: Position in the resolver's order, the pick at 0.
    order: int

    def says(self) -> str:
        """What the row states, as a clause: "competitive inhibition versus NADH"."""
        if self.mode == "unstated":
            return "no inhibition mode"
        return f"{self.mode} inhibition" + (f" versus {self.versus}" if self.versus else "")


def _reference(m: Any) -> Optional[str]:
    ref = getattr(m, "reference_id", None)
    if ref:
        return str(ref)
    found = re.search(r"\bref\s+(\S+)", str(getattr(m, "citation", "") or ""))
    return found.group(1) if found else None


def _same(row: Mapping[str, Any], pick: _Row) -> bool:
    """True when a ranked row is the pick itself. The resolver's candidates
    include the row it chose; counting it twice would let it tie itself."""
    try:
        value = float(row["value"])
    except (KeyError, TypeError, ValueError):
        return False
    ref = row.get("reference_id")
    return (value == pick.value and (row.get("conditions") or None) == (pick.conditions or None)
            and (ref is None or pick.reference is None or str(ref) == pick.reference))


def _rows(m: Any) -> Tuple[List[_Row], List[Mapping[str, Any]]]:
    """The pick and every other ranked row in its unit, in the resolver's
    order; and, apart, the rows skipped for being in another unit."""
    mode, versus, isoform = _read(getattr(m, "commentary", None))
    pick = _Row(float(m.value), _reference(m), getattr(m, "commentary", None) or None,
                mode, versus, isoform, None, 0)
    rows, other_unit = [pick], []
    for r in getattr(m, "alternatives", ()) or ():
        if not isinstance(r, dict) or r.get("value") is None or _same(r, pick):
            continue
        if r.get("unit") not in (None, m.unit):
            other_unit.append(r)
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError):
            continue
        mode, versus, isoform = _read(r.get("conditions"))
        ref = r.get("reference_id")
        rows.append(_Row(value, str(ref) if ref else None, r.get("conditions") or None,
                         mode, versus, isoform, r, len(rows)))
    return rows, other_unit


def _isoform_rank(row: _Row, wanted: Optional[str]) -> Optional[int]:
    """0 names the isoform asked for (or none was asked for), 1 names none,
    None names another: never a candidate."""
    if not wanted or same_isoform(row.isoform, wanted):
        return 0
    return 1 if row.isoform is None else None


def _mode_rank(row: _Row, want: str, substrate: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """(fits, versus, exactness), lower is better; None for another mode.

    fits: 0 the row states the model's mode, 1 it states none.
    versus: 0 measured versus the model's substrate, 1 names nothing (or the
    model names no substrate to judge it by), 2 versus another molecule.
    exactness: 0 the model's own mode, 1 mixed standing in for noncompetitive.
    """
    if row.mode == "unstated":
        return (1, 1, 0)
    if not mode_fits(row.mode, want):
        return None
    if row.versus is None or not substrate:
        versus = 1
    elif versus_is(row.versus, substrate):
        versus = 0
    else:
        versus = 2
    return (0, versus, 0 if row.mode == want else 1)


def _rank(row: _Row, want: str, substrate: Optional[str], isoform: Optional[str]):
    iso = _isoform_rank(row, isoform)
    mode = _mode_rank(row, want, substrate)
    if iso is None or mode is None:
        return None
    return (iso, *mode, row.order)


def _because(row: _Row, want: str, substrate: Optional[str],
             isoform: Optional[str]) -> Tuple[str, str, str]:
    """Why this row is carried, as (the row, why its mode fits, what it says
    of the isoform). `chosen_because` joins them, and the spread sentence
    and every export print it after "this model carries <value>, ..."; the
    note puts the value after the first."""
    if row.mode == "unstated":
        head, why = "a row stating no inhibition mode", f", used because none states {want} inhibition"
    else:
        head = f"the row stating {row.says()}"
        exact = row.mode == want
        why = ", this model's mechanism" if exact else f", which counts as {want}"
        if row.versus and substrate:
            if versus_is(row.versus, substrate):
                why += " and substrate" if exact else ", against this model's substrate"
            elif exact:
                why += f" though not its substrate ({substrate})"
            else:
                why += f", though not against this model's substrate ({substrate})"
    iso = ""
    if isoform:
        iso = (f"it names {isoform}, as --isoform asked" if same_isoform(row.isoform, isoform)
               else f"it names no isoform, so whether it measured {isoform} is unknown")
    return head, why, iso


def _joined(head: str, why: str, iso: str) -> str:
    return head + why + (f"; {iso}" if iso else "")


def _carried(m: Any) -> str:
    """What the row this module starts from is called: the resolver's pick,
    or the row an earlier selection (`--isoform`) put there."""
    return "the row --isoform chose" if getattr(m, "chosen_because", None) else "the resolver's pick"


def _pick_says(pick: _Row, best: Optional[_Row], want: str, substrate: Optional[str],
               isoform: Optional[str]) -> str:
    """What makes the resolver's pick worse than `best`, as a clause: the
    first component of the rank in which they differ, so the note names the
    reason the row was replaced and not merely a way the two differ."""
    if _isoform_rank(pick, isoform) is None:
        return f"measured {pick.isoform}, not {isoform}"
    rank = _mode_rank(pick, want, substrate)
    if rank is None:
        return f"measured {pick.says()}, and this model is {want}"
    other = _mode_rank(best, want, substrate) if best is not None else None
    if best is not None and _isoform_rank(best, isoform) < _isoform_rank(pick, isoform):
        return f"names no isoform, where a row names {isoform}"
    if other is None or rank[0] > other[0]:
        return "states no inhibition mode"
    if rank[1] > other[1]:
        if pick.versus and substrate:
            return f"measured {pick.says()}, not versus {substrate}, this model's substrate"
        return f"measured {pick.says()} and names nothing it was measured against"
    return f"measured {pick.mode} inhibition, where a row states {want} itself"


def _row_label(row: _Row, unit: str) -> str:
    ref = f", BRENDA ref {row.reference}" if row.reference else ""
    return f"{row.value:g} {unit}{ref}"


def _from_row(m: Any, row: _Row, because: str) -> Any:
    """The same Measurement, taken from another of its own ranked rows. The
    isoform module's conversion, so the two selections cannot build a row
    into a Measurement two different ways."""
    try:
        from caterva.compose.isoform import _from_row as convert
    except ImportError:  # pragma: no cover - flat layout
        from compose.isoform import _from_row as convert  # type: ignore[no-redef]
    return convert(m, row.source, because)


def select_mode(
    measured: Mapping[str, Any],
    constants: Mapping[str, Tuple[Optional[str], Optional[str]]],
    *,
    substrate: Optional[str] = None,
    isoform: Optional[str] = None,
    any_mode: bool = False,
) -> ModeSelection:
    """Each inhibition constant, taken from a row whose stated mode fits the
    model where the resolver ranked one. See the module docstring.

    `constants` maps a parameter id to (motif name, table), as the model's
    `resolvable` quantities carry them; a constant not in it, or not an
    inhibition constant of an inhibition motif, passes through untouched.
    `substrate` is the model's substrate; `isoform` is what `--isoform`
    asked for, when it did, and must be the same value `select_isoform` was
    given, because this ranks by it first.
    """
    out = ModeSelection(measured={})
    for identifier in sorted(measured):
        m = measured[identifier]
        motif, table = constants.get(identifier, (None, None))
        want = MODE_OF_MOTIF.get(motif or "")
        if want is None or table not in INHIBITION_TABLES:
            out.measured[identifier] = m
            continue
        rows, other_unit = _rows(m)
        pick = rows[0]
        ranked = sorted((r for r in rows if _rank(r, want, substrate, isoform) is not None),
                        key=lambda r: _rank(r, want, substrate, isoform))
        best = ranked[0] if ranked else None

        if any_mode:
            out.measured[identifier] = m
            if best is pick:
                continue
            kept = (f"{m.chosen_because}; kept by {ANY_MODE_FLAG}" if getattr(m, "chosen_because", None)
                    else f"the resolver's pick, kept by {ANY_MODE_FLAG}")
            if pick.mode != "unstated" and not mode_fits(pick.mode, want):
                kept += f" although it measured {pick.mode} inhibition and this model is {want}"
            out.measured[identifier] = replace(m, chosen_because=kept)
            if best is not None:
                head, why, iso = _because(best, want, substrate, isoform)
                instead = (f"{head} ({_row_label(best, m.unit)}){why}, would be used"
                           + (f"; {iso}" if iso else ""))
            else:
                instead = "the constant would be refused"
            out.notes.append(
                f"`{identifier}`: {ANY_MODE_FLAG} kept {_carried(m)} ({_row_label(pick, m.unit)}), "
                f"which {_pick_says(pick, best, want, substrate, isoform)}; without it {instead}")
            continue

        if best is pick:
            out.measured[identifier] = m
            continue
        if best is not None:
            head, why, iso = _because(best, want, substrate, isoform)
            out.measured[identifier] = _from_row(m, best, _joined(head, why, iso))
            out.notes.append(
                f"`{identifier}`: {_carried(m)} ({_row_label(pick, m.unit)}) "
                f"{_pick_says(pick, best, want, substrate, isoform)}; {head} "
                f"({_row_label(best, m.unit)}){why}, is used instead" + (f"; {iso}" if iso else ""))
            continue

        found: List[str] = []
        for r in rows:
            if _isoform_rank(r, isoform) is None:
                continue
            said = f"{r.says()} ({_row_label(r, m.unit)})"
            if said not in found:
                found.append(said)
        among = f" among those for {isoform} or naming no isoform" if isoform else ""
        why = (
            f"not used: every row BRENDA ranked for this constant{among} states a mode other "
            f"than {want}: {'; '.join(found)}. {'Each' if len(found) > 1 else 'That'} is a "
            f"constant of a different mechanism from this {want} model. Pass {ANY_MODE_FLAG} "
            f"to use {_carried(m)} ({_row_label(pick, m.unit)}) anyway; the report still "
            f"flags it")
        # "Every row" above means every row in this constant's unit. A row
        # in another unit that would have been taken is named, so the
        # sentence does not claim more than was compared.
        usable_elsewhere = sorted({
            str(r.get("unit")) for r in other_unit
            if _read(r.get("conditions"))[0] == "unstated"
            or mode_fits(_read(r.get("conditions"))[0], want)})
        if usable_elsewhere:
            why += (f". A row stating {want} inhibition or no mode exists in "
                    f"{', '.join(usable_elsewhere)}, and a row in another unit is never substituted")
        out.refused[identifier] = why
    return out


def constants_of(model: Any) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """parameter id -> (motif name, table), from a ComposedModel's
    resolvable quantities: what `select_mode` needs to know about each."""
    return {q.parameter_id: (q.motif_name, q.table) for q in getattr(model, "resolvable", ()) or ()}


__all__ = ["ANY_MODE_FLAG", "ModeSelection", "select_mode", "constants_of"]
