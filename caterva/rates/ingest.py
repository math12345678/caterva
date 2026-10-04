"""A table a person pasted or dropped, read into the file `caterva rates` reads.

WHY THIS IS HERE AND NOT IN THE PAGE
------------------------------------
Real tables arrive as a spreadsheet's clipboard (tabs, a decimal comma, a
header like `[S] (mM)`), as a plate reader's export (a byte-order mark,
Windows line endings, blank lines between blocks) and as the file the
command reads. Deciding which of these a text is, which column is which and
what its unit means is the same decision whoever asks, so it is made once,
in Python, and the page only shows it. The output is a canonical CSV in the
format `table.read_table` documents (one header, a unit on every column,
`#` comment lines, a period for the decimal mark, no blank lines), so
`caterva rates dataset.csv` on that text gives the Studio's numbers to the
last digit.

NOTHING IS DROPPED OR CHANGED WITHOUT SAYING SO
-----------------------------------------------
Every decision is a sentence in `decisions`, and every cell that could not
be used is a problem with its line and column. A row whose substrate or rate
is blank, not a number, or impossible (a negative concentration) is skipped,
and the skip is listed with its reason, counted in `summary` and written into
the canonical file as a comment, so a result never rests on a table whose
cleaning is invisible. A cell is never repaired: `1,5` in a table whose other
decimals are points is a problem, not a guess. A column's unit is never
assumed: a header with none, and a pasted pair of numbers with none, leave
the table "not ready" until the units are named.

THE SHAPES
----------
long        one row per measurement: substrate, rate, and optionally sigma,
            inhibitor, a group (wild type and mutant) and a replicate id.
wide        one substrate column and several replicate rate columns; each
            replicate becomes a row (identical conditions are replicates).
two-column  pasted numbers, with or without a header.

WHAT IS REFUSED
---------------
A text with a NUL byte or other control characters, one over `MAX_BYTES` or
`MAX_ROWS`, with no table in it, or with no column that can be a substrate or
a rate. These come back as `ok: false` with the reason; the run endpoint
turns the same reason into a 400.
"""
from __future__ import annotations

import csv
import io
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: The largest dataset accepted, in bytes of UTF-8. The studio's request body
#: is limited to 1 MiB and JSON escaping grows a table (a newline is two
#: bytes), so half of it is the most a request can always carry.
MAX_BYTES = 512 * 1024
#: Data rows (measurements), not counting the header and comments. A rates
#: table is tens of rows; the profile intervals refit every law many times,
#: so a table of thousands is refused with this number rather than left to
#: run for the length of the run's time limit.
MAX_ROWS = 2000
MAX_COLUMNS = 24
MAX_LINE_CHARS = 4000
MAX_CELL_CHARS = 120
#: The preview shows the first rows, and then every row with a problem.
PREVIEW_HEAD = 40
PREVIEW_PROBLEM_ROWS = 60

DELIMITERS = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}
DELIMITER_CHOICES = ("auto", "tab", "comma", "semicolon", "pipe", "space")
ROLES = ("substrate", "rate", "sigma", "inhibitor", "group", "replicate")
CONCENTRATION_UNITS = ("M", "mM", "uM", "nM")
TIME_UNIT_CHOICES = ("s", "min", "h")

_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_COMMA_DECIMAL = re.compile(r"^[+-]?\d*,\d+(?:[eE][+-]?\d+)?$")
_POINT_DECIMAL = re.compile(r"^[+-]?\d*\.\d+(?:[eE][+-]?\d+)?$")
_SPREADSHEET_ERROR = re.compile(r"^#(?:DIV/0!|N/A|VALUE!|REF!|NAME\?|NUM!|NULL!)$", re.IGNORECASE)
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_SUBSTRATE = {"s", "sub", "substr", "substrate", "substrateconc", "substrateconcentration",
              "conc", "concentration", "x", "s0", "s₀"}
_RATE = {"v", "v0", "vi", "rate", "rates", "velocity", "initialrate", "initialvelocity", "activity",
         "y", "ratev0", "vinitial"}
_SIGMA = {"sigma", "sd", "stdev", "std", "stddev", "stdd", "standarddeviation", "sdv", "ratesd",
          "vsd", "sigmav"}
_SEM = {"sem", "se", "stderr", "standarderror", "stderror", "standarderrorofthemean"}
_INHIBITOR = {"i", "inh", "inhibitor", "inhibitorconc", "inhibitorconcentration", "inhib"}
_GROUP = {"group", "condition", "state", "treatment", "genotype", "mutant", "variant", "strain",
          "sample", "form", "isoform", "cell", "cells", "drug", "label", "type", "enzyme", "series",
          "compound", "construct", "batch"}
_REPLICATE = {"replicate", "rep", "trial", "run", "well", "experiment", "exp", "repeat", "n"}
_REPLICATE_COLUMN = re.compile(r"^(?:rep(?:licate)?|trial|run|r|v0?|rate|velocity|exp(?:eriment)?|repeat|n)\W*_?\d+$")


class IngestRefused(ValueError):
    """A request that is not a well-formed question (a mapping that is not
    one): the studio's HTTP 400."""


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------


def _key(text: str) -> str:
    """A header's name with case, spaces, brackets and punctuation removed."""
    t = text.translate(_SUBSCRIPTS).lower()
    return re.sub(r"[\s_\[\]\(\)\{\}.:'\"`’*\-]+", "", t)


def split_header(cell: str) -> Tuple[str, Optional[str]]:
    """'[S] (mM)' -> ('[S]', 'mM'); 'v0 (µM/min)' -> ('v0', 'µM/min'); 'group' -> ('group', None).

    The unit is the last bracketed or parenthesised group after a name. A
    header that is only a bracketed name, '[S]', has no unit."""
    text = cell.strip()
    match = re.match(r"^(?P<name>.+?)\s*[\(\[](?P<unit>[^\(\)\[\]]*)[\)\]]\s*$", text)
    if match and match.group("name").strip():
        unit = match.group("unit").strip()
        return match.group("name").strip(), unit or None
    return text, None


def normalise_unit(text: str) -> Tuple[str, Optional[str]]:
    """The unit as the engine's parser reads it, and what was changed (None
    when nothing was). Only spellings of the same unit are rewritten."""
    original = text.strip()
    t = original.replace("μ", "µ").replace("−", "-")
    t = re.sub(r"[·⋅×]", " ", t)
    t = t.replace("⁻¹", "^-1").replace("⁻²", "^-2")
    # 'uM min-1' and 'uM min^-1' are uM per min; 'min-1' alone stays as written.
    t = re.sub(r"\b(min|s|sec|h|hr)\s*\^?\s*-1\b", r"1/\1", t)
    match = re.fullmatch(r"(\S+)\s+1/(min|s|sec|h|hr)", t)
    if match:
        t = f"{match.group(1)}/{match.group(2)}"
    t = t.replace("µ", "u").strip()
    t = re.sub(r"\s+", " ", t)
    if t == original.replace("µ", "u").replace("μ", "u"):
        return t, None if t == original else (f"the unit {original!r} was read as {t!r} (the micro sign as u)")
    return t, f"the unit {original!r} was read as {t!r}"


def parse_number(cell: str, decimal: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """(value, problem, note). Exactly one of value and problem is set for a
    non-blank cell; a blank cell is (None, None, None)."""
    text = cell.strip()
    if text == "":
        return None, None, None
    note = None
    if "−" in text:
        text = text.replace("−", "-")
        note = "a typographic minus sign was read as -"
    if _SPREADSHEET_ERROR.match(text):
        return None, f"{text!r} is a spreadsheet error value, not a measurement", None
    if decimal == ",":
        if "." in text and "," in text:
            return None, (f"{text!r} uses both a point and a comma; remove the thousands separator "
                          f"so the decimal comma is the only one"), None
        if "." in text:
            return None, (f"{text!r} has a point where this table's decimal comma would be; the rest of "
                          f"the table uses commas, so it was not read as a decimal"), None
        text = text.replace(",", ".")
    else:
        if "," in text:
            if _THOUSANDS.match(text):
                return None, (f"{text!r} looks like a number with a thousands separator; remove the "
                              f"comma (this table writes decimals with a point)"), None
            return None, (f"{text!r} has a comma where this table's decimal point would be; the rest "
                          f"of the table uses points, so it was not read as a decimal"), None
    if not _NUMBER.match(text):
        return None, f"{cell.strip()!r} is not a number", None
    value = float(text)
    if not math.isfinite(value):
        return None, f"{cell.strip()!r} is not a finite number", None
    return value, None, note


def _clean_text(value: float, raw: str, decimal: str) -> str:
    """The number as the canonical file writes it: the cell's own digits
    with a point for the decimal mark."""
    text = raw.strip().replace("−", "-")
    if decimal == ",":
        text = text.replace(",", ".")
    return text


def neutralise_cell(cell: Any) -> Any:
    """A text cell that a spreadsheet would run as a formula, made inert for
    export: a leading =, +, -, @, tab or carriage return gets a leading
    apostrophe. A plain number (including a negative one) is left alone."""
    if not isinstance(cell, str) or not cell:
        return cell
    if cell[0] in "=+-@\t\r" and not _NUMBER.match(cell):
        return "'" + cell
    return cell


# ---------------------------------------------------------------------------
# The text: encoding, line endings, lines, delimiter
# ---------------------------------------------------------------------------


def _lines(text: str, decisions: List[str], fmt: Dict[str, Any]) -> List[Tuple[int, str]]:
    """(line number, line) for every non-blank, non-comment line."""
    bom = text.startswith("﻿")
    if bom:
        text = text[1:]
        decisions.append("A byte-order mark at the start of the file was ignored.")
    fmt["bom"] = bom
    crlf, cr_only = text.count("\r\n"), len(re.findall(r"\r(?!\n)", text))
    lf_only = len(re.findall(r"(?<!\r)\n", text))
    kinds = [name for name, n in (("CRLF", crlf), ("CR", cr_only), ("LF", lf_only)) if n]
    fmt["line_ending"] = kinds[0] if len(kinds) == 1 else ("mixed" if kinds else "LF")
    if fmt["line_ending"] == "CRLF":
        decisions.append("Windows line endings (CRLF) were read as ordinary line breaks.")
    elif fmt["line_ending"] == "CR":
        decisions.append("Old Mac line endings (CR) were read as ordinary line breaks.")
    elif fmt["line_ending"] == "mixed":
        decisions.append("The file mixes line-ending styles; each was read as a line break.")
    raw = re.split(r"\r\n|\r|\n", text)
    out: List[Tuple[int, str]] = []
    blank, comments = [], []
    fmt["comment_text"] = []
    for number, line in enumerate(raw, start=1):
        if not line.strip():
            blank.append(number)
            continue
        if line.lstrip().startswith("#"):
            comments.append(number)
            fmt["comment_text"].append(line.lstrip().lstrip("#").strip()[:200])
            continue
        out.append((number, line))
    # A trailing newline makes one empty last element that is not a "blank line".
    if blank and blank[-1] == len(raw) and not raw[-1]:
        blank.pop()
    fmt["blank_lines"] = len(blank)
    fmt["comment_lines"] = len(comments)
    if blank:
        decisions.append(f"{len(blank)} blank line(s) were skipped (line {_listing(blank)}).")
    if comments:
        decisions.append(f"{len(comments)} comment line(s) starting with # were not read as data "
                         f"(line {_listing(comments)}); their text is kept as comments in the table that is fitted.")
    return out


def _listing(numbers: Sequence[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in numbers[:limit])
    return shown + (f" and {len(numbers) - limit} more" if len(numbers) > limit else "")


def _split(line: str, delimiter: str) -> List[str]:
    if delimiter == "space":
        return [c for c in re.split(r"\s+", line.strip()) if c != ""]
    return next(csv.reader([line], delimiter=DELIMITERS[delimiter], quotechar='"'))


def _detect_delimiter(lines: Sequence[Tuple[int, str]]) -> Tuple[str, str]:
    """(delimiter name, why). Tab, semicolon and pipe first: a decimal comma
    makes a comma a poor delimiter, and a spreadsheet's clipboard is tabs."""
    sample = [line for _n, line in lines[:200]]
    if not sample:
        return "comma", "no lines to read"
    for name in ("tab", "semicolon", "pipe", "comma"):
        counts = [len(_split(line, name)) for line in sample]
        if min(counts) >= 2 and len(set(counts)) == 1:
            return name, f"every line has {counts[0]} fields when split at {_delimiter_words(name)}"
    best = None
    for name in ("tab", "semicolon", "pipe", "comma"):
        counts = [len(_split(line, name)) for line in sample]
        modal = max(set(counts), key=counts.count)
        share = counts.count(modal) / len(counts)
        if modal >= 2 and share >= 0.8 and (best is None or (share, modal) > best[0]):
            best = ((share, modal), name, f"{share:.0%} of lines have {modal} fields when split at "
                    f"{_delimiter_words(name)}")
    if best:
        return best[1], best[2]
    counts = [len(_split(line, "space")) for line in sample]
    modal = max(set(counts), key=counts.count)
    if modal >= 2 and counts.count(modal) / len(counts) >= 0.8:
        return "space", f"{counts.count(modal) / len(counts):.0%} of lines have {modal} fields when split at spaces"
    return "comma", "no delimiter gave two or more fields on most lines"


def _delimiter_words(name: str) -> str:
    return {"tab": "tabs", "comma": "commas", "semicolon": "semicolons", "pipe": "vertical bars",
            "space": "spaces"}[name]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def _guess_role(name: str) -> Optional[str]:
    k = _key(name)
    if not k:
        return None
    if k in _SUBSTRATE or k.startswith("substrate"):
        return "substrate"
    if k in _INHIBITOR or k.startswith("inhibitor"):
        return "inhibitor"
    if k in _SIGMA or k.startswith("standarddev") or k.endswith("sd") and k[:-2] in _RATE:
        return "sigma"
    if k in _SEM:
        return "sem"
    if k in _RATE or k.startswith("initialrate") or k.startswith("initialvelocity") or "velocity" in k:
        return "rate"
    if k in _REPLICATE:
        return "replicate"
    if k in _GROUP:
        return "group"
    if "rate" in k and "sd" not in k:
        return "rate"
    return None


def _detect_roles(headers: List[Tuple[str, Optional[str]]], numeric: List[bool], n_cols: int,
                  has_header: bool, decisions: List[str]) -> Tuple[Dict[str, Any], Dict[int, str]]:
    """({'substrate': i, 'rate': i, 'rates': [i...], ...}, reason per column)."""
    roles: Dict[str, Any] = {r: None for r in ROLES}
    roles["rates"] = []
    why: Dict[int, str] = {}
    if has_header:
        for index, (name, _unit) in enumerate(headers):
            guess = _guess_role(name)
            if guess == "sem":
                why[index] = ("named like a standard error of the mean, which is not the standard "
                              "deviation of one rate: not used unless you choose it")
                continue
            if guess and roles.get(guess) is None and guess != "rate" and numeric[index] == (guess not in ("group", "replicate")):
                roles[guess] = index
                why[index] = f"its name, {name!r}, reads as the {guess}"
            elif guess == "rate" and roles["rate"] is None and numeric[index]:
                roles["rate"] = index
                why[index] = f"its name, {name!r}, reads as the rate"
            elif guess in ("group", "replicate") and roles.get(guess) is None:
                roles[guess] = index
                why[index] = f"its name, {name!r}, reads as the {guess}"
    taken = {i for r in ROLES for i in ([roles[r]] if roles[r] is not None else [])}
    free = [i for i in range(n_cols) if i not in taken and numeric[i]]
    if roles["substrate"] is None and free:
        roles["substrate"] = free[0]
        why[free[0]] = "the first numeric column, taken as the substrate (no header said so)"
        free = free[1:]
    if roles["rate"] is None and free:
        like = [i for i in free if has_header and _REPLICATE_COLUMN.match(_key(headers[i][0]) or "")]
        if len(like) >= 2:
            roles["rates"] = like
            for i in like:
                why[i] = "a replicate of the rate: its name ends in a number, like its neighbours"
        elif len(free) >= 3 and not has_header:
            roles["rates"] = free
            for i in free:
                why[i] = "a replicate rate column (several numeric columns follow the substrate)"
        elif len(free) >= 2 and has_header and len({headers[i][1] for i in free}) == 1:
            roles["rates"] = free
            for i in free:
                why[i] = "one of several columns with the same unit beside the substrate: taken as replicate rates"
        else:
            roles["rate"] = free[0]
            why[free[0]] = ("the next numeric column, taken as the rate" if not has_header or
                            headers[free[0]][0] else "taken as the rate")
    return roles, why


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def _unit_info(role: str, column: str, given: Optional[str], headerless: bool = False) -> Dict[str, Any]:
    """The engine's reading of a unit: kind and convertibility, or the
    refusal in the engine's own words."""
    from caterva.rates.table import UnitRefused, read_unit

    if not given:
        return {"given": None, "text": None, "kind": None, "convertible": False,
                "problem": (f"the {role} column ({column}) has no unit: name it in the unit box below"
                            if headerless else
                            f"the {role} column {column!r} has no unit: name it in the unit box below, or "
                            f"write it in the header as '{column} (mM)'")}
    text, changed = normalise_unit(given)
    try:
        cu = read_unit(column, text, role)
    except UnitRefused as exc:
        return {"given": given, "text": text, "kind": None, "convertible": False, "problem": str(exc),
                "note": changed}
    return {"given": given, "text": text, "kind": cu.kind, "convertible": cu.convertible,
            "problem": None, "note": changed, "column_unit": cu}


def _factor(info: Dict[str, Any], target: Optional[str], role: str) -> Tuple[float, Optional[str], Optional[str]]:
    """(factor, statement, problem) to express `info`'s unit as `target`."""
    from caterva.rates.table import read_unit

    if not target or info.get("text") is None or target == info["text"]:
        return 1.0, None, None
    if not info.get("convertible"):
        return 1.0, None, (f"the {role} unit {info['text']!r} is not a molar unit, so it cannot be "
                           f"converted to {target!r}; it is used as it is")
    to, _ = normalise_unit(target)
    try:
        goal = read_unit(role, to, role)
    except Exception as exc:  # noqa: BLE001 - the unit the person typed, refused in the engine's words
        return 1.0, None, str(exc)
    factor = info["column_unit"].factor_to(goal)
    if factor is None:
        return 1.0, None, (f"{info['text']!r} cannot be converted to {to!r}: they do not measure the "
                           f"same thing")
    clean = float(f"{factor:.12g}")
    if clean == 1.0:
        return 1.0, f"{info['text']} and {to} are the same size; nothing was multiplied.", None
    return clean, (f"{role}: {info['text']} to {to}, every value multiplied by {clean:g} "
                   f"(for example 1 {info['text']} is {clean:g} {to})."), None


# ---------------------------------------------------------------------------
# The whole inspection
# ---------------------------------------------------------------------------

_MAPPING_KEYS = {"delimiter", "decimal", "header", "roles", "units", "target"}


def check_mapping(mapping: Any) -> Dict[str, Any]:
    """The mapping, or IngestRefused saying what is wrong with its shape."""
    if mapping is None:
        return {}
    if not isinstance(mapping, Mapping):
        raise IngestRefused("the mapping must be an object")
    for key in mapping:
        if key not in _MAPPING_KEYS:
            raise IngestRefused(f"{key!r} is not a mapping key; the keys are {', '.join(sorted(_MAPPING_KEYS))}")
    out: Dict[str, Any] = {}
    if "delimiter" in mapping and mapping["delimiter"] is not None:
        if mapping["delimiter"] not in DELIMITER_CHOICES:
            raise IngestRefused(f"delimiter must be one of {', '.join(DELIMITER_CHOICES)}")
        out["delimiter"] = mapping["delimiter"]
    if "decimal" in mapping and mapping["decimal"] is not None:
        if mapping["decimal"] not in ("auto", ".", ","):
            raise IngestRefused("decimal must be auto, '.' or ','")
        out["decimal"] = mapping["decimal"]
    if "header" in mapping and mapping["header"] is not None:
        if not isinstance(mapping["header"], bool):
            raise IngestRefused("header must be true or false")
        out["header"] = mapping["header"]
    if "roles" in mapping:
        roles = mapping["roles"]
        if not isinstance(roles, Mapping):
            raise IngestRefused("roles must be an object")
        checked: Dict[str, Any] = {}
        for key, value in roles.items():
            if key == "rates":
                if not isinstance(value, list) or not all(_index(v) for v in value) or len(value) > MAX_COLUMNS:
                    raise IngestRefused("roles.rates must be a list of column numbers")
                checked[key] = list(value)
            elif key in ROLES:
                if value is not None and not _index(value):
                    raise IngestRefused(f"roles.{key} must be a column number or null")
                checked[key] = value
            else:
                raise IngestRefused(f"{key!r} is not a role; the roles are {', '.join(ROLES)} and rates")
        out["roles"] = checked
    for name in ("units", "target"):
        if name in mapping:
            value = mapping[name]
            if not isinstance(value, Mapping):
                raise IngestRefused(f"{name} must be an object")
            checked_units: Dict[str, Optional[str]] = {}
            for key, text in value.items():
                if key not in ("substrate", "rate", "sigma", "inhibitor"):
                    raise IngestRefused(f"{name}.{key} is not one of substrate, rate, sigma, inhibitor")
                if text is not None and (not isinstance(text, str) or len(text) > 40):
                    raise IngestRefused(f"{name}.{key} must be a short text or null")
                checked_units[key] = text
            out[name] = checked_units
    return out


def _index(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < MAX_COLUMNS


def _refused(reason: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False, "ready": False, "refusal": reason, "bytes": 0, "lines": 0, "filename": None,
        "shape": None, "format": None, "columns": [], "mapping": {}, "units": {}, "decisions": [],
        "problems": [{"line": None, "column": None, "severity": "blocking", "message": reason}],
        "problems_total": 1, "preview": {"headers": [], "rows": [], "shown": 0, "total": 0},
        "summary": None, "canonical": None, "sigma_options": None, "group_column": None,
        "column_names": {},
        "units_needed": False, "limits": {"bytes": MAX_BYTES, "rows": MAX_ROWS},
    }
    out.update(extra)
    return out


def inspect(text: Any, *, filename: Optional[str] = None, mapping: Any = None) -> Dict[str, Any]:
    """Read `text` and say what it is (see `_inspect`); the answer always names the file."""
    name = re.sub(r"[\x00-\x1f\x7f]", " ", filename).strip()[:200] if isinstance(filename, str) else None
    out = _inspect(text, filename=name or None, mapping=mapping)
    out["filename"] = name or None
    return out


def _inspect(text: Any, *, filename: Optional[str] = None, mapping: Any = None) -> Dict[str, Any]:
    """Read `text` and say what it is. Always an answer, `ok: false` with the
    reason when the text cannot be a table; IngestRefused only for a mapping
    that is not well formed. `mapping` overrides the detected delimiter,
    decimal mark, header, column roles, units and target units; anything it
    leaves out is detected."""
    given = check_mapping(mapping)
    if not isinstance(text, str):
        raise IngestRefused("the dataset text must be a string")
    size = len(text.encode("utf-8", errors="replace"))
    if size > MAX_BYTES:
        return _refused(f"the table is {size:,} bytes, and a dataset is limited to {MAX_BYTES:,} bytes "
                        f"({MAX_ROWS:,} rows). A rates table is tens of rows: send the part you want fitted.",
                        bytes=size)
    if "\x00" in text:
        return _refused("the text contains a NUL byte, so it is not a text table (a spreadsheet saved "
                        "as .xlsx, or another binary file). Save it as CSV or TSV (UTF-8) and drop that.",
                        bytes=size)
    control = _CONTROL.findall(text)
    if control:
        return _refused(f"the text contains {len(control)} control character(s) (first: "
                        f"U+{ord(control[0]):04X}), so it is not a text table. Save it as CSV or TSV (UTF-8).",
                        bytes=size)

    decisions: List[str] = []
    problems: List[Dict[str, Any]] = []
    fmt: Dict[str, Any] = {}
    lines = _lines(text, decisions, fmt)
    if not lines:
        return _refused("there is no table in the text: every line is blank or a comment.", bytes=size)
    if any(len(line) > MAX_LINE_CHARS for _n, line in lines):
        long_line = next(n for n, line in lines if len(line) > MAX_LINE_CHARS)
        return _refused(f"line {long_line} is longer than {MAX_LINE_CHARS:,} characters, so this is not a "
                        f"table of measurements.", bytes=size)

    # Delimiter.
    if given.get("delimiter", "auto") != "auto":
        delimiter = given["delimiter"]
        decisions.append(f"Fields are split at {_delimiter_words(delimiter)}, as you chose.")
    else:
        delimiter, reason = _detect_delimiter(lines)
        decisions.append(f"Fields are split at {_delimiter_words(delimiter)}: {reason}.")
    fmt["delimiter"] = delimiter
    try:
        rows_raw = [(n, [c.strip() for c in _split(line, delimiter)]) for n, line in lines]
    except csv.Error as exc:
        return _refused(f"the text could not be split into fields: {exc}", bytes=size)
    width = max(len(cells) for _n, cells in rows_raw)
    if width > MAX_COLUMNS:
        return _refused(f"the table has {width} columns, and at most {MAX_COLUMNS} are read.", bytes=size)
    if width < 2:
        return _refused("only one column was found, and a rate needs a substrate concentration beside "
                        "it. If the columns are separated by something else, choose the delimiter.",
                        bytes=size, format=fmt)
    if any(len(c) > MAX_CELL_CHARS for _n, cells in rows_raw for c in cells):
        return _refused(f"a cell is longer than {MAX_CELL_CHARS} characters, so this is not a table of "
                        f"measurements.", bytes=size)

    # Decimal mark.
    body_cells = [c for _n, cells in rows_raw[1:] for c in cells if c]
    if given.get("decimal", "auto") != "auto":
        decimal = given["decimal"]
        decisions.append(f"Decimals are read with a {'comma' if decimal == ',' else 'point'}, as you chose.")
    elif delimiter == "comma":
        decimal = "."
        decisions.append("Commas separate the fields, so decimals are read with a point.")
    else:
        commas = sum(1 for c in body_cells if _COMMA_DECIMAL.match(c))
        points = sum(1 for c in body_cells if _POINT_DECIMAL.match(c))
        if commas and not points:
            decimal = ","
            decisions.append(f"Decimals are written with a comma ({commas} cell(s), none with a point), "
                             f"and were read as decimal commas.")
        elif commas and points:
            decimal = "," if commas > points else "."
            decisions.append(f"The table mixes decimal commas ({commas}) and decimal points ({points}); "
                             f"the more common, the {'comma' if decimal == ',' else 'point'}, was used, and the "
                             f"others are listed as problems below. Choose the decimal mark to change this.")
        else:
            decimal = "."
    fmt["decimal"] = decimal

    # Header.
    first_n, first = rows_raw[0]

    def numeric_cell(c: str) -> bool:
        return c == "" or parse_number(c, decimal)[0] is not None

    if "header" in given:
        has_header = given["header"]
        decisions.append("The first row is " + ("a header" if has_header else "data (no header)") + ", as you chose.")
    else:
        has_header = not all(numeric_cell(c) for c in first)
        decisions.append("The first row is a header: it has text where numbers would be."
                         if has_header else "The first row is numbers, so there is no header row.")
    fmt["header"] = has_header
    data_rows = rows_raw[1:] if has_header else rows_raw
    if not data_rows:
        return _refused("the table has a header and no rows of data.", bytes=size, format=fmt)
    if len(data_rows) > MAX_ROWS:
        return _refused(f"the table has {len(data_rows):,} rows, and a dataset is limited to {MAX_ROWS:,}. "
                        f"A rates table is tens of rows: send the part you want fitted.", bytes=size, format=fmt)

    raw_headers = [c for c in first] + [""] * (width - len(first)) if has_header else [""] * width
    headers = []
    for index in range(width):
        cell = raw_headers[index]
        name, unit = split_header(cell) if cell else (f"column {index + 1}", None)
        headers.append((name or f"column {index + 1}", unit))

    # Per-column statistics.
    columns: List[Dict[str, Any]] = []
    numeric_flags: List[bool] = []
    for index in range(width):
        values = [cells[index] if index < len(cells) else "" for _n, cells in data_rows]
        non_blank = [v for v in values if v != ""]
        good = sum(1 for v in non_blank if parse_number(v, decimal)[0] is not None)
        numeric_flags.append(bool(non_blank) and good >= max(1, math.ceil(0.5 * len(non_blank))))
        columns.append({"index": index, "header": raw_headers[index] if has_header else "",
                        "name": headers[index][0], "unit": headers[index][1], "role": None,
                        "role_reason": None, "numeric": good, "non_numeric": len(non_blank) - good,
                        "blank": len(values) - len(non_blank)})

    # Roles.
    detected, why = _detect_roles(headers, numeric_flags, width, has_header, decisions)
    roles = {k: (list(v) if isinstance(v, list) else v) for k, v in detected.items()}
    chosen = given.get("roles", {})
    for key, value in chosen.items():
        roles[key] = value
    if "rates" in chosen and chosen["rates"]:
        roles["rate"] = None
    if chosen.get("rate") is not None:
        roles["rates"] = []
    for key in ("substrate", "rate", "sigma", "inhibitor", "group", "replicate"):
        value = roles.get(key)
        if value is not None and value >= width:
            return _refused(f"the {key} column {value + 1} does not exist: the table has {width} columns.",
                            bytes=size, format=fmt)
    for index in roles["rates"]:
        if index >= width:
            return _refused(f"rate column {index + 1} does not exist: the table has {width} columns.",
                            bytes=size, format=fmt)
    used = [roles[k] for k in ROLES if roles.get(k) is not None] + list(roles["rates"])
    duplicated = sorted({i for i in used if used.count(i) > 1})
    if duplicated:
        return _refused("one column is given two roles (column " + ", ".join(str(i + 1) for i in duplicated)
                        + "). Each column plays one role.", bytes=size, format=fmt)
    wide = bool(roles["rates"])
    for key, index in (("substrate", roles["substrate"]), ("rate", roles["rate"]), ("sigma", roles["sigma"]),
                       ("inhibitor", roles["inhibitor"]), ("group", roles["group"]),
                       ("replicate", roles["replicate"])):
        if index is not None:
            columns[index]["role"] = key
            columns[index]["role_reason"] = (why.get(index) if detected.get(key) == index and key not in chosen
                                             else "chosen by you")
    for index in roles["rates"]:
        columns[index]["role"] = "rate"
        columns[index]["role_reason"] = why.get(index) if "rates" not in chosen else "chosen by you"
    for index, reason in why.items():
        if columns[index]["role"] is None:
            columns[index]["role_reason"] = reason
    shape = "wide" if wide else ("two-column" if width == 2 else "long")
    if not wide and roles["rate"] is not None and roles["substrate"] is not None and width == 2:
        shape = "two-column"
    role_names = {c["index"]: c["role"] for c in columns if c["role"]}
    if roles["substrate"] is None or (roles["rate"] is None and not wide):
        missing = "substrate" if roles["substrate"] is None else "rate"
        result = _refused(f"no column was found for the {missing}; choose which column holds it.",
                          bytes=size, format=fmt)
        result.update(columns=columns, decisions=decisions, mapping=_effective(given, delimiter, decimal,
                                                                            has_header, roles, {}, {}))
        return result
    if shape == "wide":
        decisions.append(
            f"Wide layout: one substrate column and {len(roles['rates'])} replicate rate columns "
            f"({', '.join(repr(headers[i][0]) for i in roles['rates'])}); each replicate becomes its own row, "
            f"and rows with the same substrate are replicates of one another.")
    elif shape == "two-column":
        decisions.append("Two columns: the first is the substrate concentration and the second the rate."
                         if roles["substrate"] == 0 and roles["rate"] == 1 else
                         "Two columns: substrate and rate, as assigned below.")
    else:
        decisions.append("One row per measurement (long layout).")
    for key in ("substrate", "rate", "sigma", "inhibitor", "group", "replicate"):
        index = roles["rate"] if key == "rate" else roles[key]
        if key == "rate" and wide:
            continue
        if index is not None and columns[index].get("role_reason"):
            decisions.append(f"Column {index + 1} ({headers[index][0]!r}) is the {key}: {columns[index]['role_reason']}.")
    if roles["replicate"] is not None:
        decisions.append("The replicate column is kept for reference and is not used: rows with identical "
                         "conditions are replicates, whatever they are numbered.")

    # Units.
    unit_text: Dict[str, Optional[str]] = {}
    units_given = given.get("units", {})
    target_given = given.get("target", {})
    for role, index in (("substrate", roles["substrate"]),
                        ("rate", roles["rates"][0] if wide else roles["rate"]),
                        ("sigma", roles["sigma"]), ("inhibitor", roles["inhibitor"])):
        if index is None:
            continue
        if role in units_given:
            unit_text[role] = units_given[role] or None
        else:
            unit_text[role] = headers[index][1]
    if wide:
        mixed = {headers[i][1] for i in roles["rates"] if headers[i][1] is not None}
        if len(mixed) > 1:
            problems.append({"line": first_n, "column": None, "severity": "blocking",
                             "message": "the replicate rate columns are in different units "
                                        f"({', '.join(sorted(mixed))}); they must share one."})
    unit_info, factors, target_used = _resolve_units(
        unit_text, roles, headers, wide, given.get("target", {}), first_n if has_header else None,
        decisions, problems)

    # Rows.
    rate_indices = list(roles["rates"]) if wide else [roles["rate"]]
    out_rows: List[Dict[str, Any]] = []
    skipped: List[Tuple[int, str]] = []
    preview_flags: Dict[int, Dict[int, str]] = {}
    notes_seen: set = set()

    def cell_of(cells: List[str], index: Optional[int]) -> str:
        return cells[index] if index is not None and index < len(cells) else ""

    def flag(line: int, index: int, reason: str, severity: str = "skipped") -> None:
        preview_flags.setdefault(line, {})[index] = reason
        problems.append({"line": line, "column": headers[index][0], "severity": severity, "message": reason})

    blocking_rows = 0
    for line, cells in data_rows:
        if len(cells) > width:
            problems.append({"line": line, "column": None, "severity": "note",
                             "message": f"the row has {len(cells)} cells and the table {width} columns; "
                                        f"the extra cells were ignored"})
        bad = False
        reasons: List[str] = []

        def numeric(index: Optional[int], role: str, required: bool = True) -> Optional[float]:
            nonlocal bad
            raw = cell_of(cells, index)
            value, problem, note = parse_number(raw, decimal)
            if note and note not in notes_seen:
                notes_seen.add(note)
                decisions.append(note[0].upper() + note[1:] + ".")
            if value is None:
                if raw.strip() == "":
                    if required:
                        bad = True
                        text_ = f"the {role} is blank"
                        flag(line, index, text_)  # type: ignore[arg-type]
                        reasons.append(text_)
                else:
                    bad = True
                    flag(line, index, problem or "not a number")  # type: ignore[arg-type]
                    reasons.append(problem or "not a number")
            return value

        s_raw = cell_of(cells, roles["substrate"])
        s = numeric(roles["substrate"], "substrate concentration")
        if s is not None and s < 0:
            bad = True
            text_ = f"a substrate concentration of {s:g} is negative"
            flag(line, roles["substrate"], text_)
            reasons.append(text_)
        sd = sd_raw = None
        if roles["sigma"] is not None:
            sd_raw = cell_of(cells, roles["sigma"])
            sd = numeric(roles["sigma"], "standard deviation")
            if sd is not None and sd <= 0:
                blocking_rows += 1
                flag(line, roles["sigma"], f"the standard deviation is {sd:g}; it must be positive, because a "
                     f"zero error bar gives that row infinite weight. Fix the value, or estimate the "
                     f"uncertainty from replicates or residuals instead.", "blocking")
                bad = True
        inh = inh_raw = None
        if roles["inhibitor"] is not None:
            inh_raw = cell_of(cells, roles["inhibitor"])
            inh = numeric(roles["inhibitor"], "inhibitor concentration")
            if inh is not None and inh < 0:
                bad = True
                text_ = f"an inhibitor concentration of {inh:g} is negative"
                flag(line, roles["inhibitor"], text_)
                reasons.append(text_)
            if inh_raw.strip() == "":
                problems[-1]["message"] += " (write 0 where there was no inhibitor)"
        label = None
        if roles["group"] is not None:
            label = cell_of(cells, roles["group"]).strip()
            if not label:
                bad = True
                flag(line, roles["group"], "the group label is blank")
                reasons.append("the group label is blank")
        rep_values: List[Tuple[int, Optional[float], str]] = []
        for index in rate_indices:
            raw = cell_of(cells, index)
            if wide:
                value, problem, note = parse_number(raw, decimal)
                if value is None and raw.strip() == "":
                    problems.append({"line": line, "column": headers[index][0], "severity": "note",
                                     "message": "blank replicate, so this measurement is absent (the row's other "
                                                "replicates are used)"})
                elif value is None:
                    flag(line, index, (problem or "not a number") + "; this replicate was skipped")
                    reasons.append(problem or "not a number")
                rep_values.append((index, value, raw))
            else:
                value = numeric(index, "rate")
                rep_values.append((index, value, raw))
        if bad:
            skipped.append((line, "; ".join(reasons) or "a value that must be positive is not"))
            continue
        any_replicate = False
        for index, value, raw in rep_values:
            if value is None:
                if wide and raw.strip() != "":
                    skipped.append((line, f"the replicate in column {index + 1} is not a number"))
                continue
            any_replicate = True
            out_rows.append({"line": line, "s": s, "s_raw": s_raw, "v": value, "v_raw": raw, "sd": sd,
                             "sd_raw": sd_raw, "i": inh, "i_raw": inh_raw, "label": label,
                             "rep": headers[index][0] if wide else None})
        if wide and not any_replicate:
            skipped.append((line, "no replicate has a number in it"))

    n_skipped_rows = len({ln for ln, _r in skipped})
    if skipped:
        decisions.append(f"{n_skipped_rows} row(s) were skipped, never silently changed: "
                         + "; ".join(f"line {ln}: {why_}" for ln, why_ in skipped[:6])
                         + (f"; and {len(skipped) - 6} more (every one is listed under problems)" if len(skipped) > 6 else "")
                         + ".")
    if not out_rows:
        problems.append({"line": None, "column": None, "severity": "blocking",
                         "message": "no row has a usable substrate concentration and rate."})

    # Canonical CSV.
    canonical: Optional[str] = None
    group_name = None
    column_names: Dict[str, str] = {}
    blocking = [p for p in problems if p["severity"] == "blocking"]
    if not blocking and out_rows:
        group_name = _group_header(headers[roles["group"]][0]) if roles["group"] is not None else None
        column_names = _column_names(headers, roles, wide, has_header, group_name)
        canonical = _canonical(out_rows, column_names, roles, unit_info, factors, target_used, group_name,
                               filename, fmt, decisions, skipped, decimal)

    summary = None
    sigma_options = None
    engine_problem = None
    if canonical is not None:
        summary, sigma_options, engine_problem = _engine_view(canonical, group_name, column_names)
        if engine_problem:
            problems.append({"line": None, "column": None, "severity": "blocking", "message": engine_problem})
            canonical = None
        else:
            summary["rows_read"] = len(data_rows)
            summary["rows_skipped"] = n_skipped_rows
            summary["wide_measurements_skipped"] = len(skipped) - n_skipped_rows if wide else 0

    blocking = [p for p in problems if p["severity"] == "blocking"]
    unit_missing = [p for p in blocking if "has no unit" in p["message"]]
    ready = canonical is not None and not blocking
    refusal = None if ready else (blocking[0]["message"] if blocking else "the table cannot be used yet")
    # Preview rows.
    flagged_lines = sorted(preview_flags)
    total = len(data_rows)
    keep: List[int] = [n for n, _c in data_rows[:PREVIEW_HEAD]]
    for ln in flagged_lines:
        if ln not in keep and len([k for k in keep if k not in [n for n, _c in data_rows[:PREVIEW_HEAD]]]) < PREVIEW_PROBLEM_ROWS:
            keep.append(ln)
    shown = []
    skipped_lines = {ln for ln, _r in skipped}
    for line, cells in data_rows:
        if line not in keep:
            continue
        padded = (cells + [""] * width)[:width]
        shown.append({"line": line, "cells": padded, "used": line not in skipped_lines,
                      "flags": {str(i): m for i, m in preview_flags.get(line, {}).items()}})
    mapping_out = _effective(given, delimiter, decimal, has_header, roles, unit_text, target_used)
    return {
        "ok": ready, "ready": ready, "refusal": refusal, "bytes": size, "lines": len(lines),
        "filename": filename, "shape": shape, "format": fmt, "columns": columns,
        "mapping": mapping_out,
        "units": {role: {"given": unit_info[role].get("given"), "read_as": unit_info[role].get("text"),
                         "kind": unit_info[role].get("kind"), "convertible": unit_info[role].get("convertible"),
                         "problem": unit_info[role].get("problem"), "target": target_used.get(role),
                         "factor": factors.get(role, 1.0)} for role in unit_info},
        "decisions": decisions, "problems": problems[:500], "problems_total": len(problems),
        "preview": {"headers": [c["header"] or c["name"] for c in columns], "rows": shown,
                    "shown": len(shown), "total": total},
        "summary": summary, "canonical": canonical, "sigma_options": sigma_options,
        "group_column": group_name, "column_names": column_names,
        "units_needed": bool(unit_missing),
        "limits": {"bytes": MAX_BYTES, "rows": MAX_ROWS},
    }


def methods_sentence(read: Mapping[str, Any]) -> str:
    """The sentence of a methods paragraph on how the table was read, from an
    `inspect` answer: what was converted, what was skipped, nothing more."""
    summary = read["summary"]
    parts = [f"The table ({summary['rows_used']} measurements used"]
    if summary["rows_skipped"]:
        parts[0] += f", {summary['rows_skipped']} row(s) skipped for the reasons recorded with the run"
    parts[0] += ") was read by Caterva Studio from " + (f"the file {read['filename']}" if read["filename"]
                                                         else "pasted text")
    layout = {"wide": "a layout with one substrate column and several replicate columns",
              "two-column": "two columns, substrate and rate", "long": "one measurement per row"}.get(read["shape"], "a table")
    parts[0] += f" ({layout})"
    conversions = [f"{role} from {u['read_as']} to {u['target']}" for role, u in read["units"].items()
                   if u.get("factor") not in (None, 1.0) and u.get("target")]
    parts[0] += ("; " + ", ".join(conversions) + " by exact multiplication" if conversions else "")
    return parts[0] + "."


def _resolve_units(unit_text: Dict[str, Optional[str]], roles: Mapping[str, Any], headers, wide: bool,
                   target_given: Mapping[str, Optional[str]], header_line: Optional[int],
                   decisions: List[str], problems: List[Dict[str, Any]]):
    """(the engine's reading of each unit, the factor to its target, the unit written in the canonical
    file). A sigma with no unit is read in the rate's unit, and a sigma always ends in the rate's final
    unit, so the two cannot differ; an inhibitor follows the substrate's target."""
    def column_of(role: str) -> int:
        return roles["rates"][0] if role == "rate" and wide else roles[role]

    unit_info: Dict[str, Dict[str, Any]] = {}
    for role, text_ in unit_text.items():
        name = headers[column_of(role)][0]
        if role == "sigma" and not text_ and unit_text.get("rate"):
            decisions.append(f"The sigma column {name!r} has no unit; the standard deviation of a rate is in "
                             f"the rate's unit, {unit_text['rate']}, and was read as that.")
            text_ = unit_text["sigma"] = unit_text["rate"]
        info = _unit_info(role, name, text_, headerless=header_line is None)
        unit_info[role] = info
        if info.get("note"):
            decisions.append(info["note"][0].upper() + info["note"][1:] + ".")
        if info.get("problem"):
            problems.append({"line": header_line, "column": name, "severity": "blocking",
                             "message": info["problem"]})
    factors: Dict[str, float] = {}
    target_used: Dict[str, Optional[str]] = {}
    for role in ("substrate", "rate", "inhibitor", "sigma"):
        info = unit_info.get(role)
        if info is None or info.get("problem"):
            continue
        if role == "sigma":
            goal = target_used.get("rate") or (unit_info.get("rate") or {}).get("text")
        elif role == "inhibitor":
            goal = target_given.get("substrate") if info.get("kind") == "concentration" else None
        else:
            goal = target_given.get(role)
        factor, statement, trouble = _factor(info, goal, role)
        factors[role] = factor
        target_used[role] = goal if goal and trouble is None else info["text"]
        if statement:
            decisions.append(statement)
        if trouble:
            problems.append({"line": None, "column": headers[column_of(role)][0],
                             "severity": "blocking" if role == "sigma" else "note", "message": trouble})
    return unit_info, factors, target_used


def _effective(given: Mapping[str, Any], delimiter: str, decimal: str, header: bool, roles: Mapping[str, Any],
               units: Mapping[str, Optional[str]], target: Mapping[str, Optional[str]]) -> Dict[str, Any]:
    return {"delimiter": delimiter, "decimal": decimal, "header": header,
            "roles": {k: (list(v) if isinstance(v, list) else v) for k, v in roles.items()},
            "units": {k: v for k, v in units.items()},
            "target": {k: v for k, v in (target or {}).items() if k in ("substrate", "rate")}}


def _column_names(headers, roles, wide: bool, has_header: bool, group_name: Optional[str]) -> Dict[str, str]:
    """The name each role's column has in the canonical file: the person's own
    header word where it is safe in a header (so an axis reads "S (mM)", not
    "substrate (mM)"), else the engine's default. A name that collides with
    another column's falls back to the default."""
    defaults = {"substrate": "substrate", "rate": "rate", "sigma": "sigma", "inhibitor": "inhibitor"}
    chosen: Dict[str, str] = {}
    taken = {group_name.lower()} if group_name else set()
    for role in ("substrate", "rate", "sigma", "inhibitor"):
        index = roles["rates"][0] if (role == "rate" and wide) else roles[role if role != "rate" else "rate"]
        if role == "sigma" and roles["sigma"] is None or role == "inhibitor" and roles["inhibitor"] is None:
            continue
        name = defaults[role]
        if has_header and index is not None and not (role == "rate" and wide):
            word = re.sub(r"[,()\[\]\"#\r\n\t]", " ", headers[index][0])
            word = re.sub(r"\s+", " ", word).strip()[:40]
            if word and word.lower() not in taken and word.lower() not in {d for d in defaults.values() if d != defaults[role]}:
                name = word
        taken.add(name.lower())
        chosen[role] = name
    return chosen


def _group_header(name: str) -> str:
    """The group column's name in the canonical file: the person's own word
    when it is safe in a header, else 'group'."""
    safe = re.sub(r"[,()\[\]\"#\r\n\t]", " ", name).strip()
    safe = re.sub(r"\s+", " ", safe)
    if not safe or safe.lower() in ("substrate", "rate", "sigma", "inhibitor"):
        return "group"
    return safe


def _canonical(rows: List[Dict[str, Any]], names: Mapping[str, str], roles, unit_info, factors, target_used,
               group_name: Optional[str], filename: Optional[str], fmt, decisions: List[str],
               skipped: List[Tuple[int, str]], decimal: str) -> str:
    def unit_of(role: str) -> str:
        info = unit_info[role]
        if role in target_used and target_used[role]:
            return target_used[role]
        return info["text"]

    def number(value: float, raw: str, role: str) -> str:
        factor = factors.get(role, 1.0)
        if factor == 1.0:
            return _clean_text(value, raw, decimal)
        return repr(float(f"{value * factor:.12g}"))

    head = [f"{names['substrate']} ({unit_of('substrate')})", f"{names['rate']} ({unit_of('rate')})"]
    if roles["sigma"] is not None:
        head.append(f"{names['sigma']} ({unit_of('sigma') if 'sigma' in unit_info else unit_of('rate')})")
    if roles["inhibitor"] is not None:
        head.append(f"{names['inhibitor']} ({unit_of('inhibitor')})")
    if group_name:
        head.append(group_name)
    buffer = io.StringIO()
    source = filename if filename else "pasted text"
    clean_source = re.sub(r"[\r\n]", " ", source)[:120]
    buffer.write(f"# Read by Caterva Studio from {clean_source}; the table below is what was fitted.\n")
    for piece in fmt.get("comment_text", [])[:60]:
        buffer.write(f"# source: {piece}\n")
    for decision in decisions:
        for piece in decision.splitlines():
            buffer.write(f"# {piece}\n")
    for line, why_ in skipped[:200]:
        buffer.write(f"# skipped line {line}: {why_}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(head)
    for row in rows:
        out = [number(row["s"], row["s_raw"], "substrate"), number(row["v"], row["v_raw"], "rate")]
        if roles["sigma"] is not None:
            out.append(number(row["sd"], row["sd_raw"], "sigma"))
        if roles["inhibitor"] is not None:
            out.append(number(row["i"], row["i_raw"], "inhibitor"))
        if group_name:
            out.append(row["label"])
        writer.writerow(out)
    return buffer.getvalue()


def _engine_view(canonical: str, group_name: Optional[str], column_names: Mapping[str, str]) -> Tuple[Optional[Dict[str, Any]],
                                                                      Optional[Dict[str, Any]], Optional[str]]:
    """What the engine makes of the canonical text: counts, and which sources
    of uncertainty are available. The engine's own refusal if it declines."""
    from caterva.rates.table import TableError, UnitRefused, read_table
    from caterva.rates.uncertainty import replicate_summary

    try:
        data = read_table("dataset.csv", text=canonical, group=group_name, names=dict(column_names))
    except (TableError, UnitRefused) as exc:
        return None, None, str(exc)
    sets, dof = replicate_summary(data)
    conditions = len({data.condition(r) for r in range(len(data))})
    summary = {
        "rows_used": len(data), "conditions": conditions, "replicate_rows": len(data) - conditions,
        "inhibitor": data.has_inhibitor,
        "groups": [{"label": g, "rows": len(data.rows_of(g))} for g in data.groups()],
        "substrate_unit": data.units["substrate"].text, "rate_unit": data.units["rate"].text,
        "substrate_convertible": data.units["substrate"].convertible,
        "rate_convertible": data.units["rate"].convertible,
        "rate_kind": data.units["rate"].kind,
        "highest_substrate": max(data.substrate), "lowest_substrate": min(data.substrate),
        "rows_read": len(data), "rows_skipped": 0, "wide_measurements_skipped": 0,
    }
    options = {"column": data.sigma is not None, "replicate_sets": sets, "replicate_dof": dof,
               "replicates": dof >= 1, "residuals": data.sigma is None}
    return summary, options, None


__all__ = ["DELIMITER_CHOICES", "IngestRefused", "MAX_BYTES", "MAX_COLUMNS", "MAX_ROWS", "check_mapping",
           "inspect", "neutralise_cell", "normalise_unit", "parse_number", "split_header"]
