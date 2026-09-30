"""Reading a lab's initial-rate table: its columns, their units, its replicates.

WHAT A ROW IS
-------------
One measured initial rate v at a substrate concentration [S], and optionally
an inhibitor concentration [I], a per-row standard deviation, and a group
label (wild type or mutant, treated or untreated). The header names every
column and its unit:

    substrate (mM), rate (uM/min), sigma (uM/min), inhibitor (uM), group

Lines starting with `#` before or among the rows are comments, so a data file
can carry its own source. A column is found by its NAME, the text before the
parenthesis, compared without case; `--substrate-column` and its siblings
name it when the header says something else ("conc (ppm)").

WHY A UNIT IS REQUIRED IN THE HEADER
------------------------------------
Every constant the fit reports inherits a column's unit: Km is in the
substrate's unit, Vmax in the rate's, Ki in the inhibitor's. A number with no
unit cannot be compared with anything, least of all with a cited Km, and
"assume mM" is the thousandfold error `compose/scale.py` exists to catch. So
a column with no unit is refused, naming the column, and so is a unit the
reader cannot parse. The parser is `compose/units.py`'s, the one the model
builder checks its rate laws with, so the two cannot disagree about what
`uM/min` means.

AN ARBITRARY UNIT IS ALLOWED, AND SAYS WHAT IT COSTS
----------------------------------------------------
Much real kinetics is measured in units nobody can convert: counts per minute
per minute from a radioactive product, A340 per minute from NADH, ppm of a
substrate whose molar mass the file does not state. The fit does not need a
conversion (Km comes out in ppm, and is a correct Km in ppm), so such a unit
is accepted when every word in it is a known unit of that kind (`ARBITRARY`,
a time unit, or a molar unit). What it cannot do is meet the literature: a
cited Km in mM cannot be compared with one in ppm, and the report says so
rather than guessing a molar mass. A word that is none of these ("mMol",
"uM/mn") is still refused, because a misspelled molar unit read as
"arbitrary" would silently turn off the conversion it needed; so is a unit
made only of molar and time words that the parser cannot read as written
("uM min^-1"), which is a molar unit in the wrong notation, not a readout.

REPLICATES ARE IDENTICAL CONDITIONS
-----------------------------------
Two rows with the same [S], the same [I] and the same group are replicates:
the same measurement made twice. They pool into a standard deviation
(`--sigma-from replicates`) and into the pure-error term of the lack-of-fit
test, and they do not count as a second condition when deciding whether a
model's constants can be determined at all (compose/fitting.py says why at
length). Identical means equal as numbers after parsing, so "0.10" and "0.1"
are one condition and "0.1" and "0.100001" are two.
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from caterva.compose.units import TIME_UNITS, Unit, UnitError, parse_unit

#: The roles a column can play, and the name each is found by when no flag
#: names it.
SUBSTRATE, RATE, SIGMA, INHIBITOR = "substrate", "rate", "sigma", "inhibitor"
DEFAULT_NAMES = {SUBSTRATE: "substrate", RATE: "rate", SIGMA: "sigma", INHIBITOR: "inhibitor"}

#: Words a unit may be made of when it cannot be converted to molar or to a
#: rate in molar per time. Deliberately a short list of the readouts initial
#: rates are actually taken in, so a typo of a molar unit cannot land here:
#: counts (and counts or disintegrations per minute), absorbance and optical
#: density, fluorescence and luminescence units, parts per million or
#: billion, per cent, mass per volume (which needs a molar mass nobody
#: stated), and an amount per time per mass of enzyme (umol/min/mg, a specific
#: activity, which needs the enzyme's concentration to become a molar rate).
#: `A` followed by a wavelength (A340) is absorbance at it.
ARBITRARY = frozenset({
    "count", "counts", "cpm", "dpm", "au", "a.u.", "od", "abs", "absorbance",
    "rfu", "rlu", "ppm", "ppb", "%", "percent", "arbitrary",
    "g", "mg", "ug", "µg", "ng", "l", "ml", "ul", "µl",
})
#: Amounts of substance, allowed only in a rate (umol/min/mg): an amount on
#: its own is not a concentration, and "mMol" for mM would otherwise read
#: as millimoles.
AMOUNTS = frozenset({"mol", "mmol", "umol", "µmol", "nmol", "pmol"})
_WAVELENGTH = re.compile(r"^(?:a|od)\d{3}$", re.IGNORECASE)
_MOLAR = re.compile(r"^(?:[munpkµ]?M)$")


class TableError(ValueError):
    """The file is not a table this reader can take: exit code 2."""


class UnitRefused(ValueError):
    """A column's unit could not be read, or is the wrong kind: exit code 3."""


@dataclass(frozen=True)
class ColumnUnit:
    """A column's unit, as written and as understood.

    `unit` is the parsed `compose.units.Unit` when the unit converts (molar,
    per time); None when it is arbitrary. `kind` is what it measures:
    "concentration", "concentration per time", "per time", or "arbitrary".
    """

    column: str
    text: str
    unit: Optional[Unit]
    kind: str

    @property
    def convertible(self) -> bool:
        return self.unit is not None

    def factor_to(self, other: "ColumnUnit") -> Optional[float]:
        """Multiply a number in this unit by this to express it in `other`;
        None when either is arbitrary or they measure different things."""
        if self.unit is None or other.unit is None:
            return None
        if dict(self.unit.dimensions) != dict(other.unit.dimensions):
            return None
        return self.unit.scale / other.unit.scale


def _split_header(cell: str) -> Tuple[str, Optional[str]]:
    """'substrate (mM)' -> ('substrate', 'mM'); 'group' -> ('group', None)."""
    text = cell.strip()
    match = re.fullmatch(r"(.*?)\s*[\(\[]\s*(.*?)\s*[\)\]]\s*", text)
    if match:
        return match.group(1).strip(), match.group(2).strip() or None
    return text, None


def _arbitrary_words(text: str, role: str) -> Optional[List[str]]:
    """The words of `text` if every one is a unit word this reader knows for
    `role`, else None. Operators and parentheses are separators; exponents
    are kept on the word they follow ("min^2")."""
    words = [w for w in re.split(r"[\s/*()]+", text) if w]
    known = []
    for word in words:
        bare = re.sub(r"\^-?\d+$", "", word)
        lowered = bare.lower()
        if (lowered in ARBITRARY or _WAVELENGTH.match(bare) or lowered in TIME_UNITS
                or (role in (RATE, SIGMA) and lowered in AMOUNTS)
                or _MOLAR.match(bare) or re.fullmatch(r"\d+(\.\d+)?", bare)):
            known.append(bare)
            continue
        return None
    return known


def _time_words(text: str) -> int:
    return sum(1 for w in re.split(r"[\s/*()]+", text) if re.sub(r"\^-?\d+$", "", w).lower() in TIME_UNITS)


def read_unit(column: str, text: Optional[str], role: str) -> ColumnUnit:
    """Parse one column's unit for the role it plays, or refuse naming it."""
    if not text:
        raise UnitRefused(
            f"column {column!r} has no unit in its header. Write it as "
            f"'{column} (mM)' or whatever it was measured in: every constant the "
            f"fit reports inherits this column's unit, and a Km with no unit "
            f"cannot be compared with anything. If the readout has no convertible "
            f"unit, name the one it has (counts/min, A340/min, ppm)."
        )
    try:
        unit = parse_unit(text)
    except UnitError:
        unit = None
    if unit is not None:
        dims = {k: v for k, v in unit.dimensions.items()}
        if role in (SUBSTRATE, INHIBITOR):
            if dims != {"M": 1}:
                raise UnitRefused(
                    f"column {column!r} is in {text!r}, which is not a concentration. "
                    f"A {role} concentration is molar with a prefix (M, mM, uM, nM, "
                    f"pM), or an arbitrary unit such as ppm or mg/mL."
                )
            return ColumnUnit(column, text, unit, "concentration")
        # A rate or its standard deviation.
        if dims == {"M": 1, "s": -1}:
            return ColumnUnit(column, text, unit, "concentration per time")
        if dims == {"s": -1}:
            return ColumnUnit(column, text, unit, "per time")
        raise UnitRefused(
            f"column {column!r} is in {text!r}, which is not a rate. A rate is a "
            f"concentration per time (uM/min), a turnover per time (1/s), or an "
            f"arbitrary readout per time (A340/min, counts/min/min)."
        )
    words = _arbitrary_words(text, role)
    if words is None:
        raise UnitRefused(
            f"cannot read the unit {text!r} of column {column!r}. Molar units are "
            f"M, mM, uM, nM or pM, time is s, min, h or day, and a readout with "
            f"no convertible unit may be written in "
            f"{', '.join(sorted(w for w in ARBITRARY if w.isalpha()))} or A340-style "
            f"absorbance. It is refused rather than read as arbitrary: a misspelled "
            f"molar unit taken as arbitrary would silently switch off the unit "
            f"conversion a literature comparison needs."
        )
    readout = [w for w in words
               if w.lower() in ARBITRARY or _WAVELENGTH.match(w) or w.lower() in AMOUNTS]
    if not readout:
        # Every word is molar, time or a number, so this IS a molar unit,
        # written in a form the parser does not read ("uM min^-1"). Taking
        # it as arbitrary would fit correctly and then refuse every unit
        # conversion for a unit that has one; the reader is asked to write
        # it in the parser's form instead.
        raise UnitRefused(
            f"cannot read the unit {text!r} of column {column!r} as written, and every "
            f"word in it is a molar or time unit, so it is not an arbitrary readout. "
            f"Write it with / or * between the units, as uM/min or uM*min^-1."
        )
    if role in (RATE, SIGMA) and _time_words(text) == 0:
        raise UnitRefused(
            f"column {column!r} is in {text!r}, which has no time in it, so it is "
            f"not a rate. An initial rate is a change per time: write it as "
            f"{text}/min or {text}/s."
        )
    if role in (SUBSTRATE, INHIBITOR) and _time_words(text):
        raise UnitRefused(
            f"column {column!r} is in {text!r}, which contains a time unit; a "
            f"{role} concentration does not."
        )
    return ColumnUnit(column, text, None, "arbitrary")


@dataclass(frozen=True)
class Dataset:
    """The table as numbers, with the units and the file lines they came from."""

    source: str
    substrate: Tuple[float, ...]
    rate: Tuple[float, ...]
    units: Mapping[str, ColumnUnit]
    #: file line of each row, for messages.
    lines: Tuple[int, ...]
    sigma: Optional[Tuple[float, ...]] = None
    inhibitor: Optional[Tuple[float, ...]] = None
    group: Optional[Tuple[str, ...]] = None
    group_column: Optional[str] = None
    notes: Tuple[str, ...] = ()
    comments: Tuple[str, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.rate)

    @property
    def has_inhibitor(self) -> bool:
        return self.inhibitor is not None and any(i > 0 for i in self.inhibitor)

    def condition(self, row: int) -> Tuple[object, ...]:
        """What was set for this row: two rows with the same key are
        replicates."""
        return (
            self.group[row] if self.group else None,
            self.substrate[row],
            self.inhibitor[row] if self.inhibitor is not None else 0.0,
        )

    def groups(self) -> List[str]:
        """Group labels in the order they first appear."""
        if not self.group:
            return []
        seen: List[str] = []
        for label in self.group:
            if label not in seen:
                seen.append(label)
        return seen

    def subset(self, rows: Sequence[int]) -> "Dataset":
        pick = list(rows)
        return Dataset(
            source=self.source,
            substrate=tuple(self.substrate[i] for i in pick),
            rate=tuple(self.rate[i] for i in pick),
            units=self.units,
            lines=tuple(self.lines[i] for i in pick),
            sigma=None if self.sigma is None else tuple(self.sigma[i] for i in pick),
            inhibitor=None if self.inhibitor is None else tuple(self.inhibitor[i] for i in pick),
            group=None if self.group is None else tuple(self.group[i] for i in pick),
            group_column=self.group_column,
            notes=self.notes,
            comments=self.comments,
        )

    def rows_of(self, label: str) -> List[int]:
        return [i for i, g in enumerate(self.group or ()) if g == label]


def _number(text: str, column: str, line: int) -> float:
    try:
        value = float(text.strip())
    except ValueError:
        raise TableError(
            f"line {line}: {column!r} is {text.strip()!r}, which is not a number"
        ) from None
    if not math.isfinite(value):
        raise TableError(f"line {line}: {column!r} is {text.strip()!r}, which is not a finite number")
    return value


def read_table(
    path: str | Path,
    *,
    names: Optional[Mapping[str, str]] = None,
    group: Optional[str] = None,
    text: Optional[str] = None,
) -> Dataset:
    """Read a CSV of initial rates.

    `names` maps a role (substrate, rate, sigma, inhibitor) to the column
    name that plays it, overriding `DEFAULT_NAMES`. `group` names a label
    column. `text` supplies the file's content directly (for tests and
    stdin); `path` is then only its name in messages.
    """
    wanted = dict(DEFAULT_NAMES)
    explicit = {role: name for role, name in (names or {}).items() if name}
    wanted.update(explicit)
    source = str(path)
    if text is None:
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            raise TableError(f"{source}: no such file") from None
        except UnicodeDecodeError as exc:
            raise TableError(f"{source} is not UTF-8 text ({exc}); save it as CSV (UTF-8)") from None

    comments: List[str] = []
    body: List[Tuple[int, List[str]]] = []
    for number, cells in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not cells or all(not c.strip() for c in cells):
            continue
        if cells[0].lstrip().startswith("#"):
            comments.append(",".join(cells).lstrip()[1:].strip())
            continue
        body.append((number, cells))
    if not body:
        raise TableError(f"{source} has no header row and no data")
    header_line, header = body[0]
    rows = body[1:]
    if not rows:
        raise TableError(f"{source} has a header and no rows of data")

    parsed = [_split_header(cell) for cell in header]
    by_name: Dict[str, int] = {}
    for index, (name, _unit) in enumerate(parsed):
        key = name.lower()
        if key in by_name:
            raise TableError(f"{source} line {header_line}: two columns are called {name!r}")
        by_name[key] = index
    found = ", ".join(repr(h.strip()) for h in header)

    def column(role: str, required: bool) -> Optional[int]:
        name = wanted[role]
        index = by_name.get(name.lower())
        if index is None and (required or role in explicit):
            flag = f"--{role}-column"
            raise TableError(
                f"{source} has no column called {name!r} for the {role}. Its columns "
                f"are {found}. Name the {role} column with {flag}."
            )
        return index

    index_s = column(SUBSTRATE, True)
    index_v = column(RATE, True)
    index_sd = column(SIGMA, False)
    index_i = column(INHIBITOR, False)
    index_g: Optional[int] = None
    if group:
        index_g = by_name.get(group.lower())
        if index_g is None:
            raise TableError(f"{source} has no column called {group!r} to group by. Its columns are {found}.")
    used = [i for i in (index_s, index_v, index_sd, index_i, index_g) if i is not None]
    if len(set(used)) != len(used):
        raise TableError(f"{source}: one column was named for two roles")

    units: Dict[str, ColumnUnit] = {}
    for role, index in ((SUBSTRATE, index_s), (RATE, index_v), (SIGMA, index_sd), (INHIBITOR, index_i)):
        if index is None:
            continue
        name, unit_text = parsed[index]
        units[role] = read_unit(name, unit_text, role)

    notes: List[str] = []
    sigma_scale = 1.0
    if SIGMA in units:
        rate_unit, sigma_unit = units[RATE], units[SIGMA]
        factor = sigma_unit.factor_to(rate_unit)
        if factor is None:
            if sigma_unit.unit is not None or rate_unit.unit is not None or (
                    sigma_unit.text.replace(" ", "") != rate_unit.text.replace(" ", "")):
                raise UnitRefused(
                    f"column {sigma_unit.column!r} is in {sigma_unit.text!r} and the rate "
                    f"column {rate_unit.column!r} in {rate_unit.text!r}. A standard "
                    f"deviation of a rate is in the rate's unit, or one that converts to it."
                )
        elif abs(factor - 1.0) > 1e-12:
            sigma_scale = factor
            notes.append(
                f"The standard deviations ({sigma_unit.text}) were converted to the rate's "
                f"unit ({rate_unit.text}) by a factor of {factor:g}."
            )

    substrate: List[float] = []
    rate: List[float] = []
    sigma: List[float] = []
    inhibitor: List[float] = []
    labels: List[str] = []
    lines: List[int] = []
    width = len(header)
    def cell(cells: List[str], number: int, index: int, role: str) -> float:
        raw = cells[index]
        if not raw.strip():
            hint = " (write 0 for no inhibitor)" if role == INHIBITOR else ""
            raise TableError(f"line {number}: the {role} column {parsed[index][0]!r} is empty{hint}")
        return _number(raw, parsed[index][0], number)

    for number, cells in rows:
        if len(cells) < width:
            cells = cells + [""] * (width - len(cells))
        s = cell(cells, number, index_s, SUBSTRATE)
        if s < 0:
            raise TableError(f"line {number}: a substrate concentration of {s:g} is negative")
        substrate.append(s)
        rate.append(cell(cells, number, index_v, RATE))
        if index_sd is not None:
            sd = cell(cells, number, index_sd, SIGMA) * sigma_scale
            if sd <= 0:
                raise UnitRefused(
                    f"line {number}: the standard deviation is {sd:g}. It must be positive: "
                    f"a zero error bar would give that row infinite weight, and the fit "
                    f"would pass through it exactly whatever the others say."
                )
            sigma.append(sd)
        if index_i is not None:
            i = cell(cells, number, index_i, INHIBITOR)
            if i < 0:
                raise TableError(f"line {number}: an inhibitor concentration of {i:g} is negative")
            inhibitor.append(i)
        if index_g is not None:
            label = cells[index_g].strip()
            if not label:
                raise TableError(f"line {number}: the group column {group!r} is empty")
            labels.append(label)
        lines.append(number)

    if index_i is not None and not any(i > 0 for i in inhibitor):
        notes.append(
            f"The inhibitor column {parsed[index_i][0]!r} is zero in every row, so these "
            f"are rates without inhibitor and are fitted as such."
        )

    return Dataset(
        source=source,
        substrate=tuple(substrate),
        rate=tuple(rate),
        units=units,
        lines=tuple(lines),
        sigma=tuple(sigma) if index_sd is not None else None,
        inhibitor=tuple(inhibitor) if index_i is not None else None,
        group=tuple(labels) if index_g is not None else None,
        group_column=parsed[index_g][0] if index_g is not None else None,
        notes=tuple(notes),
        comments=tuple(comments),
    )


__all__ = [
    "ARBITRARY", "ColumnUnit", "Dataset", "DEFAULT_NAMES", "INHIBITOR", "RATE", "SIGMA",
    "SUBSTRATE", "TableError", "UnitRefused", "read_table", "read_unit",
]
