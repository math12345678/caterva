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
   for the row carried. A row determined from Kitz-Wilson plots comes last
   among these (below);
3. failing that, every row states another mode, and the constant is
   refused rather than filled with another mechanism's value. The reason
   names the modes found and `--any-mode`, which keeps the resolver's pick.

Ties inside a rank keep the resolver's order, with its pick first, so a
row is only ever replaced by one that is better for the model and never by
one that is merely different. A row in another unit is never substituted,
as in `isoform.py`: the carried Measurement keeps the pick's unit, so a
value moved across without conversion would be wrong by the factor between
the two units. When such a row states the model's mode and the row carried
states none, the notes say it was passed over and why.

The selection is on by default because it is a correctness fix, not a
preference: a model that says it is noncompetitive and simulates a
competitive constant is wrong whether or not its report admits it.
`--any-mode` turns it off and keeps the resolver's pick whatever it states,
and the notes say what the default would have done; `row_scope` still
flags the mismatch in the report and in every export.

A MODE STATED AGAINST ANOTHER MOLECULE
--------------------------------------
For an enzyme with two substrates, the pattern of inhibition depends on
which substrate is varied, and ref 739793 shows it: the one inhibitor is
competitive versus NADH and noncompetitive versus pyruvate. A model of LDH
with `--substrate pyruvate` holds NADH fixed, so its "competitive" means
competing with pyruvate. The competitive row does not say that, and the
pyruvate row says the opposite. Rank 1 above still puts a row of the
model's mode measured versus another molecule before a row stating no mode:
the first names the mechanism the model uses and `row_scope` prints the
versus mismatch beside it, where a row stating nothing could have been
measured against either substrate. That is a choice, not a deduction, and
it must not let the contradiction pass unremarked. So when the row carried
does not state the model's mode versus the model's substrate, and a ranked
row states another mode versus that substrate, the notes say that row is
evidence against the model's mechanism for this inhibitor and substrate,
which no choice of row can fix. A competitive LDH model of this inhibitor
with `--substrate pyruvate` carries 0.00059 mM and gets that note.

MIXED FOR NONCOMPETITIVE, AND NOT THE REVERSE
---------------------------------------------
`mode_fits` lets a mixed row stand in for a noncompetitive model and
refuses a noncompetitive row for a competitive or an uncompetitive one.
The asymmetry is `row_scope`'s, kept so the row carried is never one the
report calls the wrong mechanism, and it is a convention rather than a
law. A pure noncompetitive Ki equals both constants of the mixed scheme
(Kic = Kiu), so as a number it is a competitive model's Kic; what a
competitive model gets wrong with it is the mechanism, which leaves out
the inhibitor binding the enzyme-substrate complex. A mixed row states
that the two constants differ and not which one it gives
(`caterva.bind.core.MODE_MEANING`), so for a noncompetitive model it is a
stand-in, and an exact row outranks it when both were measured versus the
same thing. What a row was measured versus comes first: "mixed versus
glucose" beats "noncompetitive" naming nothing for a model of glucose,
because only the first is known to be the assay the model means. No real
case decided that order. Of the 1,247 Ki rows parsed from fourteen BRENDA
pages on 2026-09-29 (hexokinase recorded; LDH, monoamine oxidase and eleven
others live), no inhibitor has both a mixed and a noncompetitive row.

KITZ-WILSON ROWS ARE NOT REVERSIBLE CONSTANTS
---------------------------------------------
BRENDA files the K_I of an irreversible inactivation in the Ki table. Ref
702238 (Binda et al. 2008, Biochemistry 47:5616, doi:10.1021/bi8002814)
gives human monoamine oxidase's hydrazine constants twice, "determined
from competitive inhibition data" and "determined from Kitz-Wilson plots";
the paper shows the hydrazines alkylate the flavin, and the second kind is
the K_I of that inactivation (Kitz and Wilson 1962, J. Biol. Chem.
237:3245): the inhibitor concentration at half the maximal inactivation
rate, not the dissociation constant a reversible inhibition model means.
`read_mode` reads such a row as stating no mode, which is true of its
words and hides what it is. So a Kitz-Wilson row ranks after every other
row stating no mode. When one is carried the notes say what it is, and when
the choice moved to one, so does its `chosen_because`, which every export
prints; a pick kept as it was has no `chosen_because` to say it in, by that
field's contract. It is not refused: no reversible row may exist, and the
report's statement of what the number is serves the reader better than a
placeholder. Only the words "Kitz-Wilson" are recognised, the wording ref
702238 uses; an inactivation constant described otherwise is read as a row
stating no mode.

WITH --isoform: THE ISOFORM FIRST, THEN THE MODE
------------------------------------------------
Two orders are fixed here, and they are separate questions.

The first is the order of the two steps. `isoform.select_isoform` runs
first, over the same alternatives, and this runs on what it kept, told the
same isoform. Human monoamine oxidase and benzylhydrazine (ref 702238) show
why, for a competitive model with `--isoform MAO-A`. The rows are 0.026 mM
(MAO-B, competitive), 0.048 mM (MAO-B, Kitz-Wilson), 1.95 mM (MAO-A,
Kitz-Wilson) and 2.096 mM (MAO-A, competitive). `select_isoform` takes the
first MAO-A row, 1.95, and this moves it to 2.096, MAO-A's competitive row.
Run the other way round, this keeps the competitive pick 0.026 and
`select_isoform`, which does not read modes, then takes 1.95, a
Kitz-Wilson row, with MAO-A's competitive row one line below. Run second
but not told the isoform, this would move 1.95 to 0.026, the other
protein's constant, undoing what `--isoform` asked for.

The second is the order inside this step's ranking: a row naming the
isoform asked for beats a row naming none, whatever either states about
mode, and a row naming another isoform is never taken. It decides between
a row that names the isoform and states no mode, and a row that names no
isoform and states the model's mode. The first is kept. `--isoform`
promises that a row naming the isoform is used when one exists
(`isoform.py`, rule 1), and a mode step that moved away from it would break
that promise; the unstated mode is an unknown about the right protein,
which the report states, where the other row adds the unknown of which
protein it measured. None of the 1,247 Ki rows parsed has that shape, so
the test compares the two rows' ranks directly.

Phenylhydrazine (ref 702238) with `--isoform MAO-B` shows the rule that a
row naming another isoform is never taken: MAO-A's 0.205 mM is the only
competitive row, and a competitive model keeps MAO-B's 0.791 mM (a
Kitz-Wilson row, which the notes say) rather than take it. Either order of
the two steps gives 0.791 there. When every row for the isoform states
another mode, a row naming no isoform that fits is used, and the note says
whether it measured the isoform is unknown.

THE SAME RANKING BEFORE A ROW IS CHOSEN
---------------------------------------
`rank` is also what the literature layer ranks BRENDA's rows with when the
API or the TypeScript CLI asks for a Ki by mode
(`fallback_logic.resolve_kinetic_value(inhibition_mode=...)`, reached from
the API's inhibition domains and `scientific resolve --mode`). There it
runs before a row is chosen, over every row the isoform and variant steps
kept, where `select_mode` runs after, over the rows the resolver returned;
`fallback_logic._partition_mode` says what that changes. The rule itself
is here once.

A row is read by `caterva.bind.core.read_mode`, the reader `row_scope` and
`caterva bind` use, so the three agree about what a row states. That reader
takes the first mode a commentary names. BRENDA's hexokinase Inhibitors
table has rows naming two, one per substrate ("mixed versus MgATP2-,
competitive inhibition versus 2-deoxyglucose", ref 660949); none of the Ki
rows parsed does, and one that did would be read as its first mode here
exactly as in the report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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

#: BRENDA's wording for an irreversible inactivation constant filed as a Ki
#: ("determined from Kitz-Wilson plots", ref 702238).
_KITZ_WILSON = re.compile(r"\bKitz[\s-]*Wilson\b", re.IGNORECASE)

#: What a Kitz-Wilson row is, as the clause the notes print, and the reason
#: of a row the choice moved to, which every export prints.
KITZ_WILSON_MEANING = (
    "it was determined from Kitz-Wilson plots, which give the K_I of an irreversible "
    "inactivation, not a reversible Ki")


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
    #: What was changed, what --any-mode kept, and what the rows say against
    #: the model; one sentence each.
    notes: List[str] = field(default_factory=list)


# -- The ranking ------------------------------------------------------------
#
# ONE RANKING, TWO CALLERS. `select_mode` below ranks a Measurement's
# alternatives with these functions, and the literature layer ranks BRENDA's
# rows with the same functions before it chooses one
# (Tests/fallback_logic.py, `resolve_kinetic_value(inhibition_mode=...)`),
# which is how the API and the TypeScript CLI ask for a Ki by mode. A
# second copy of the rule would drift from this one the way ADR 0027's two
# graders drifted, so there is none; the callers differ only in which rows
# they rank and how they break a tie between rows ranked alike.

#: The modes a model can be of, and so the modes a caller may rank for:
#: the values of `row_scope.MODE_OF_MOTIF`, derived rather than listed again.
#: No motif is a mixed or a partial inhibitor. A mixed row stands in for a
#: noncompetitive model (`mode_fits`); a partial row stands in for none.
MODES = tuple(sorted(set(MODE_OF_MOTIF.values())))


@dataclass(frozen=True)
class Reading:
    """What one row's commentary states, read once, by the reader `row_scope`
    and `caterva bind` use. Every rank below is a function of this and of
    the model, and of nothing else about the row."""
    mode: str
    versus: Optional[str]
    isoform: Optional[str]
    conditions: Optional[str]

    @property
    def kitz_wilson(self) -> bool:
        """An irreversible inactivation constant, which states no mode."""
        return self.mode == "unstated" and bool(_KITZ_WILSON.search(self.conditions or ""))

    def says(self) -> str:
        """What the row states, as a clause: "competitive inhibition versus NADH"."""
        if self.mode == "unstated":
            return ("no inhibition mode (a Kitz-Wilson inactivation constant)"
                    if self.kitz_wilson else "no inhibition mode")
        return f"{self.mode} inhibition" + (f" versus {self.versus}" if self.versus else "")


def read_row(conditions: Optional[str]) -> Reading:
    """The Reading of one row's commentary (BRENDA's conditions cell)."""
    mode, versus, isoform = _read(conditions)
    return Reading(mode, versus, isoform, conditions or None)


def isoform_rank(row: Reading, wanted: Optional[str]) -> Optional[int]:
    """0 names the isoform asked for (or none was asked for), 1 names none,
    None names another: never a candidate."""
    if not wanted or same_isoform(row.isoform, wanted):
        return 0
    return 1 if row.isoform is None else None


def mode_rank(row: Reading, want: str, substrate: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """(fits, versus, exactness), lower is better; None for another mode.

    fits: 0 the row states the model's mode, 1 it states none, 2 it states
    none and is a Kitz-Wilson inactivation constant.
    versus: 0 measured versus the model's substrate, 1 names nothing (or the
    model names no substrate to judge it by), 2 versus another molecule.
    exactness: 0 the model's own mode, 1 mixed standing in for noncompetitive.
    """
    if row.mode == "unstated":
        return (2 if row.kitz_wilson else 1, 1, 0)
    if not mode_fits(row.mode, want):
        return None
    if row.versus is None or not substrate:
        versus = 1
    elif versus_is(row.versus, substrate):
        versus = 0
    else:
        versus = 2
    return (0, versus, 0 if row.mode == want else 1)


def rank(row: Reading, want: str, substrate: Optional[str] = None,
         isoform: Optional[str] = None) -> Optional[Tuple[int, int, int, int]]:
    """(isoform, fits, versus, exactness): the isoform first, then the mode,
    lower is better. None for a row that is never a candidate, because it
    names another isoform or states another mode. Rows with equal ranks are
    equally good for the model; the caller breaks the tie by its own order."""
    iso = isoform_rank(row, isoform)
    mode = mode_rank(row, want, substrate)
    if iso is None or mode is None:
        return None
    return (iso, *mode)


@dataclass(frozen=True)
class _Row(Reading):
    """One ranked row, read once, with its value and its place."""
    value: float = 0.0
    unit: Optional[str] = None
    reference: Optional[str] = None
    #: The dict the resolver ranked; None for the pick itself.
    source: Optional[Mapping[str, Any]] = None
    #: Position in the resolver's order, the pick at 0.
    order: int = 0

    def label(self) -> str:
        ref = f", BRENDA ref {self.reference}" if self.reference else ""
        return f"{self.value:g} {self.unit or ''}".rstrip() + ref


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
    return (value == pick.value
            and (row.get("conditions") or None) == (pick.conditions or None)
            and (ref is None or pick.reference is None or str(ref) == pick.reference))


def _rows(m: Any) -> Tuple[List[_Row], List[_Row]]:
    """The pick and every other ranked row in its unit, in the resolver's
    order; and, apart, the rows skipped for being in another unit."""
    read = read_row(getattr(m, "commentary", None))
    pick = _Row(read.mode, read.versus, read.isoform, read.conditions,
                value=float(m.value), unit=m.unit, reference=_reference(m), source=None, order=0)
    rows, other_unit = [pick], []
    for r in getattr(m, "alternatives", ()) or ():
        if not isinstance(r, dict) or r.get("value") is None or _same(r, pick):
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError):
            continue
        read = read_row(r.get("conditions"))
        ref = r.get("reference_id")
        elsewhere = r.get("unit") not in (None, m.unit)
        row = _Row(read.mode, read.versus, read.isoform, read.conditions,
                   value=value, unit=str(r.get("unit")) if elsewhere else m.unit,
                   reference=str(ref) if ref else None, source=r,
                   order=len(other_unit) if elsewhere else len(rows))
        (other_unit if elsewhere else rows).append(row)
    return rows, other_unit


#: The names the rest of this module (and its tests) rank with.
_isoform_rank = isoform_rank
_mode_rank = mode_rank


def _rank(row: _Row, want: str, substrate: Optional[str], isoform: Optional[str]):
    """The whole ranking key: `rank`, then the resolver's order. None for a
    row that is never a candidate."""
    key = rank(row, want, substrate, isoform)
    return None if key is None else (*key, row.order)


@dataclass(frozen=True)
class _Because:
    """Why a row is carried, in the parts the sentences need: the row, why
    its mode fits, what it says of the isoform, and what else a reader must
    know about it. `chosen_because` joins them, and the spread sentence and
    every export print it after "this model carries <value>, ..."; a note
    puts the value after the row."""
    head: str
    why: str
    iso: str = ""
    caveat: str = ""

    def tail(self) -> str:
        return "".join(f"; {part}" for part in (self.iso, self.caveat) if part)

    def joined(self) -> str:
        return self.head + self.why + self.tail()


def _because(row: _Row, want: str, substrate: Optional[str],
             isoform: Optional[str]) -> _Because:
    caveat = KITZ_WILSON_MEANING if row.kitz_wilson else ""
    if row.mode == "unstated":
        head = "a row stating no inhibition mode"
        why = f", used because none states {want} inhibition"
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
    return _Because(head, why, iso, caveat)


def _carried(m: Any) -> str:
    """What the row this module starts from is called: the resolver's pick,
    or the row an earlier selection (`--isoform`) put there."""
    return ("the row --isoform chose" if getattr(m, "chosen_because", None)
            else "the resolver's pick")


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
        if pick.kitz_wilson:
            return ("was determined from Kitz-Wilson plots, the K_I of an irreversible "
                    "inactivation")
        return "states no inhibition mode"
    if rank[1] > other[1]:
        if pick.versus and substrate:
            return f"measured {pick.says()}, not versus {substrate}, this model's substrate"
        return f"measured {pick.says()} and names nothing it was measured against"
    return f"measured {pick.mode} inhibition, where a row states {want} itself"


def _from_row(m: Any, row: _Row, because: str) -> Any:
    """The same Measurement, taken from another of its own ranked rows. The
    isoform module's conversion, so the two selections cannot build a row
    into a Measurement two different ways."""
    try:
        from caterva.compose.isoform import _from_row as convert
    except ImportError:  # pragma: no cover - flat layout
        from compose.isoform import _from_row as convert  # type: ignore[no-redef]
    return convert(m, row.source, because)


def _about_the_carried_row(identifier: str, carried: _Row, best: Optional[_Row],
                           rows: Sequence[_Row], other_unit: Sequence[_Row], want: str,
                           substrate: Optional[str], isoform: Optional[str],
                           told_kitz_wilson: bool) -> List[str]:
    """What a reader must be told about the row the model ends up with,
    whichever way it was chosen: what it is, and what the other rows say
    against it. `best` is the row the default would carry."""
    notes: List[str] = []
    # A ranked row that states another mode versus the model's own
    # substrate, when the carried row does not state the model's mode
    # versus it: measured against this substrate, the inhibitor is not what
    # the model says it is. The module docstring gives the LDH case.
    settled = (carried.mode != "unstated" and mode_fits(carried.mode, want)
               and versus_is(carried.versus, substrate))
    if substrate and not settled:
        against = next((r for r in rows if r is not carried
                        and _isoform_rank(r, isoform) is not None
                        and r.mode != "unstated" and not mode_fits(r.mode, want)
                        and versus_is(r.versus, substrate)), None)
        if against is not None:
            notes.append(
                f"`{identifier}`: a ranked row states {against.says()} ({against.label()}), "
                f"measured against {substrate}, this model's substrate, and the row carried "
                f"({carried.label()}) states {carried.says()}. Measured against {substrate} "
                f"this inhibitor is not {want}, which is evidence against this model's "
                f"mechanism for it; no choice of row fixes that")
    if carried.kitz_wilson and not told_kitz_wilson:
        notes.append(
            f"`{identifier}`: the row carried ({carried.label()}) states no inhibition mode, "
            f"and {KITZ_WILSON_MEANING}"
            + (f"; no other row this model could take states {want} inhibition or is a "
               f"reversible constant stating no mode" if carried is best else ""))
    # A row this module would have preferred, passed over for its unit.
    rank = _mode_rank(carried, want, substrate)
    if rank is None or rank[0] >= 1:
        passed = next((r for r in other_unit if _isoform_rank(r, isoform) is not None
                       and (_mode_rank(r, want, substrate) or (1,))[0] == 0), None)
        if passed is not None:
            notes.append(
                f"`{identifier}`: a row stating {passed.says()} ({passed.label()}) was passed "
                f"over for the row carried ({carried.label()}), because it is in {passed.unit}, "
                f"not {carried.unit}, and a row in another unit is never substituted")
    return notes


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
        # The facts every carried row is checked for, whichever way below
        # it came to be carried.
        context = (best, rows, other_unit, want, substrate, isoform)

        if any_mode:
            out.measured[identifier] = m
            if best is not pick:
                kept = (f"{m.chosen_because}; kept by {ANY_MODE_FLAG}"
                        if getattr(m, "chosen_because", None)
                        else f"the resolver's pick, kept by {ANY_MODE_FLAG}")
                if pick.mode != "unstated" and not mode_fits(pick.mode, want):
                    kept += f" although it measured {pick.mode} inhibition and this model is {want}"
                out.measured[identifier] = replace(m, chosen_because=kept)
                if best is not None:
                    b = _because(best, want, substrate, isoform)
                    instead = f"{b.head} ({best.label()}){b.why}, would be used{b.tail()}"
                else:
                    instead = "the constant would be refused"
                out.notes.append(
                    f"`{identifier}`: {ANY_MODE_FLAG} kept {_carried(m)} ({pick.label()}), "
                    f"which {_pick_says(pick, best, want, substrate, isoform)}; without it "
                    f"{instead}")
            out.notes.extend(_about_the_carried_row(identifier, pick, *context, False))
            continue

        if best is pick:
            out.measured[identifier] = m
            out.notes.extend(_about_the_carried_row(identifier, pick, *context, False))
            continue
        if best is not None:
            b = _because(best, want, substrate, isoform)
            out.measured[identifier] = _from_row(m, best, b.joined())
            out.notes.append(
                f"`{identifier}`: {_carried(m)} ({pick.label()}) "
                f"{_pick_says(pick, best, want, substrate, isoform)}; {b.head} "
                f"({best.label()}){b.why}, is used instead{b.tail()}")
            out.notes.extend(_about_the_carried_row(identifier, best, *context, bool(b.caveat)))
            continue

        found: List[str] = []
        for r in rows:
            if _isoform_rank(r, isoform) is None:
                continue
            said = f"{r.says()} ({r.label()})"
            if said not in found:
                found.append(said)
        among = f" among those for {isoform} or naming no isoform" if isoform else ""
        why = (
            f"not used: every row BRENDA ranked for this constant{among} states a mode other "
            f"than {want}: {'; '.join(found)}. {'Each' if len(found) > 1 else 'That'} is a "
            f"constant of a different mechanism from this {want} model. Pass {ANY_MODE_FLAG} "
            f"to use {_carried(m)} ({pick.label()}) anyway; the report still flags it")
        # "Every row" above means every row in this constant's unit. A row
        # in another unit that would have been taken is named, so the
        # sentence does not claim more than was compared; one naming
        # another isoform would not have been taken, so it is not.
        usable_elsewhere = sorted({
            str(r.unit) for r in other_unit
            if _rank(r, want, substrate, isoform) is not None})
        if usable_elsewhere:
            why += (f". A row stating {want} inhibition or no mode exists in "
                    f"{', '.join(usable_elsewhere)}, and a row in another unit is never "
                    f"substituted")
        out.refused[identifier] = why
    return out


def constants_of(model: Any) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """parameter id -> (motif name, table), from a ComposedModel's
    resolvable quantities: what `select_mode` needs to know about each."""
    return {q.parameter_id: (q.motif_name, q.table)
            for q in getattr(model, "resolvable", ()) or ()}


__all__ = ["ANY_MODE_FLAG", "KITZ_WILSON_MEANING", "ModeSelection", "select_mode",
           "constants_of", "MODES", "Reading", "read_row", "isoform_rank", "mode_rank",
           "rank"]
