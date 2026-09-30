"""From a cited inhibition constant to a binding free energy a simulation can be held to.

ΔG°bind = RT ln(Ki / c°), c° = 1 M, at the temperature the Ki was measured
at. That line is textbook; what this module adds is everything the line
leaves out, because each omission is a way to validate a free-energy
calculation against the wrong number:

* **Which molecule.** A Ki belongs to the compound in the row, never to a
  molecule its commentary mentions ("competitive versus NADH" is what the
  inhibitor competes with). See brenda_client._compound_cell.
* **Which binding event.** Only some inhibition modes make Ki a
  dissociation constant of the state a simulation usually models. A
  competitive Ki is Kd for inhibitor + free enzyme. An uncompetitive Ki is
  Kd for inhibitor + enzyme-substrate complex, so it validates a ternary
  simulation and not an apo one. A mixed-type row gives one of two
  constants and does not say which. The mode is read from the row, and a
  row whose mode does not fit the simulated state is excluded, by name.
* **At what temperature.** ΔG scales with T. A row without one gets no ΔG
  at a guessed temperature; it gets the range over 4-37 °C, the span the
  corpus's assays cover, and says so.
* **How well the literature agrees with itself.** Two measurements of one
  constant typically differ several-fold. A computed ΔG inside that spread
  cannot be called right or wrong by it, and the report says how wide the
  band is in kcal/mol before it says anything about agreement.

Nothing here is estimated from a model; every number is a recorded row or
arithmetic on one.
"""
from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

#: Gas constant, kJ mol^-1 K^-1 (CODATA 2018, exact).
R_KJ = 8.314462618e-3
KJ_PER_KCAL = 4.184
#: Temperatures used when a row reports none: the coldest and warmest assay
#: temperatures in the LDH Ki corpus (Gadus morhua at 4 °C, human at 37 °C).
#: A stated range, not a guess at the missing value.
UNSTATED_T_RANGE_C = (4.0, 37.0)

# -- Which isoform a row measured ---------------------------------------------
#
# BRENDA files the isoforms of one EC number under one organism and says which
# one a row measured, when it says, in the row's free-text commentary. It does
# not say it one way. On the three committed pages (Tests/fixtures/ki_mode/ and
# Tests/fixtures/recorded/) the one isoform, human monoamine oxidase B, is
# written "MAO-B", "MAO B", "isoform MAO B", "isoform MAO-B" and "monoamine
# oxidase B"; rat hexokinase I is "HK I", "HKI" and "hexokinase I".
#
# THE DEFECT THIS REPLACES. The reader was two patterns: one token after
# "isoform", "isozyme" or "isoenzyme", or an upper-case code joined by a
# hyphen. So "isoform MAO B" read as "MAO" (one token), and "MAO B",
# "monoamine oxidase B", "HK I" and "hexokinase II" read as no isoform at all.
# Asked for human MAO-A and clorgyline, the resolver read ref 742446's
# "isoform MAO A" row (1.2e-05 mM) as some other isoform's, found no row
# naming MAO-A, and returned 1.28e-06 mM from a row naming no isoform. A row
# misread as naming none is worse than refused: it is taken as the fallback,
# and may be the other isoform's. Of the 2,140 Km, Ki and kcat rows parsed
# from the three committed full pages on 2026-09-30, the old reader missed the
# isoform of 192 and cut 45 short ("MAO" for "isoform MAO B", "I" for
# "isoenzyme I and isoenzyme II", "hexokinase" for "isozyme hexokinase 2").
# Its hyphen code also read "XL-1" out of "Escherichia coli XL-1 Blue" (a
# cloning strain) and "RO-28" out of "RO-28-1675" (an activator's code name).
#
# WHAT IS READ, in the order a commentary is searched (the first mention wins,
# as before):
#
# * after "isoform", "isozyme" or "isoenzyme" (or their plurals): a name in
#   any of the forms below, else the one token that follows if it is shaped
#   like a name ("isozyme H4", "isoenzyme II", "isoform A", "isoform
#   LDHL1": it holds a capital or a digit, or it is a Greek letter's name),
#   else nothing. A lower-case word after the keyword ("all isozymes tested",
#   "isoform specific inhibitor", "the isoform of") is prose, not a name;
#   every keyword in the committed corpus is followed by a capital;
# * an abbreviation from `_STEMS` and a code, spaced, hyphenated or run
#   together ("MAO B", "MAO-B", "MAOB", "HK I", "HKII", "HXK1"), with an
#   optional two-letter species prefix ("TbHK1", Trypanosoma brucei's HK1),
#   unless it names a strain ("coli HK1", "strain HK-1");
# * an enzyme name from `_FULL_NAMES` and a code ("hexokinase II",
#   "monoamine oxidase A"), read as the abbreviation;
# * "glucokinase", alone or with a one-letter code: on the hexokinase page it
#   names an isoform by its own name (mammalian hexokinase IV; yeast's
#   glucokinase beside its hexokinases PI and PII, ref 640222), except in
#   "glucokinase activator", which names a drug and not the protein measured;
# * any other upper-case code joined by a hyphen ("PFK-M"), as before, unless
#   it is part of a longer hyphenated name ("RO-28-1675"), a strain
#   ("coli XL-1") or a cofactor or other non-protein prefix (`_NOT_A_STEM`).
#
# Two isoforms named together ("isoenzyme I and isoenzyme II", "hexokinases
# Ib and Ic": BRENDA's way of giving one value for both) read as both, joined
# by " and ", and `same_isoform` matches either.
#
# WHAT A READING IS. The name, spelled one way: an abbreviation and its code
# joined by a hyphen, whatever joined them in the row ("MAO B" and "MAOB" read
# "MAO-B"; "hexokinase I" and "HK I" read "HK-I"). Two rows naming one isoform
# then read alike, so a comparison that ignores only case and separators
# (`isoform_key`) finds them equal.
#
# WHAT A REQUEST IS COMPARED AS. A request (`--isoform`, the resolver's
# `isoform=`, an API query's isoform) is not a row, and was compared as
# typed, so it missed the rows the reader had respelled: on the committed
# hexokinase page (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz) potato
# (Solanum tuberosum) rows read "HK-1", "HK-2" and "HK-3", and a request for
# "2" or "hexokinase 2" refused the Km for glucose as measured only on other
# isoforms, and for the Ki of ADP took 0.04 mM from a row naming no isoform
# over HK2's own 0.108 mM. So `same_isoform` reads each side with this
# reader first ("hexokinase 2" and "isoform MAO B" are then "HK-2" and
# "MAO-B"; a name it cannot read is kept as given), and a code written alone
# ("2", "B", "II": "isozyme 2", "monoamine oxidase isoform B", or a request
# that short) is the same as that code after an abbreviation ("HK-2",
# "MAO-B", "HK-II"). The rows compared are one EC number's, the ones BRENDA
# files under the enzyme asked about, so the abbreviation adds nothing there
# that the code does not say. Two different abbreviations with one code
# ("HK-1" and "HXK-1") stay two names. The API server's rowScopeFlags
# applies this same rule (queryResolver.ts).
#
# WHAT IS NOT EQUATED. Spelling is normalised; nomenclature is not. "HK-I"
# and "HK-1" stay two names, as do "glucokinase" and "HK-IV", "HK-B" (the
# A-D naming) and "HK-II", and LDH's "H4", "LDH-B4" and "LDH-1", although each
# pair can name one protein. Which numbering a paper used is a claim about
# that paper, and a reader that equated them would be asserting it; a request
# spelled in another numbering is refused naming the isoforms BRENDA holds,
# which says what to ask for instead. Tissue words ("enzyme from heart") and
# oligomeric states ("tetrameric enzyme form") are not read as isoforms.
#
# The whole committed corpus is read by caterva/tests/test_isoform_reader.py,
# which holds the expected reading of every row, checked by hand.

#: Enzyme names BRENDA writes in full before an isoform code, and the
#: abbreviation the same pages write for them. Only names on a committed page
#: are listed: a name is added when a page that writes it is committed and its
#: rows are audited, not in advance.
_FULL_NAMES = {
    "hexokinase": "HK",
    "hexokinases": "HK",
    "monoamine oxidase": "MAO",
    "lactate dehydrogenase": "LDH",
}
#: Abbreviations BRENDA writes an isoform code after, with or without a
#: separator. Run-together forms ("LDHB", "HK1") are read only after one of
#: these, because run-together upper case is also "ATP4", "IC50" and "NH3".
_STEMS = ("HXK", "LDH", "MAO", "HK")
#: Roman numerals I to VIII. X alone is left a letter: "LDH-X" names LDH's
#: sperm isozyme by letter, not by number.
_ROMAN = r"(?:VI{0,3}|IV|I{1,3})"
#: A code after a separator: a numeral with an optional sub-form letter
#: ("II", "Ia") or a "P" prefix (yeast "PII"); a letter with optional
#: subunit counts ("B", "A4", "A2B2"); or a number ("2").
_CODE = rf"(?:P?{_ROMAN}[a-c]?|[A-Z]\d?(?:[A-Z]\d)*|\d{{1,2}})"
#: A code run together with its abbreviation: a numeral, one letter, or a
#: number. Nothing longer, so "LDHL1" is not split into LDH and "L1".
_COMPACT_CODE = rf"(?:{_ROMAN}|[A-Z]|\d{{1,2}})"
_END = r"(?![\w-])"
_AND = rf"(?:\s+and\s+(?P<code2>{_CODE}){_END})?"

_STEM_NAME = re.compile(
    rf"(?<![\w-])(?P<prefix>[A-Z][a-z])?(?P<stem>{'|'.join(_STEMS)})"
    rf"(?:[ -](?P<code>{_CODE}){_END}{_AND}|(?P<compact>{_COMPACT_CODE}){_END})"
)
# The first letter may be a capital, and nothing else: the codes after a name
# are case-sensitive ("I" is a numeral, "in" is not).
_FULL_NAME = re.compile(
    r"(?<![\w-])(?P<name>"
    + "|".join(f"[{n[0].upper()}{n[0]}]{re.escape(n[1:])}"
               for n in sorted(_FULL_NAMES, key=len, reverse=True))
    + rf")\s+(?P<code>{_CODE}){_END}{_AND}"
)
_GLUCOKINASE = re.compile(rf"(?<![\w-])[Gg]lucokinase(?:\s+(?P<code>[A-Z]){_END})?")
_KEYWORD = re.compile(r"\b(?:isozyme|isoenzyme|isoform)s?\s+", re.IGNORECASE)
_KEYWORD_TOKEN = re.compile(
    r"(?P<token>[A-Za-z0-9][A-Za-z0-9-]*)"
    r"(?:\s+and\s+(?:(?:isozyme|isoenzyme|isoform)\s+)?(?P<token2>[A-Za-z0-9][A-Za-z0-9-]*))?"
)
_HYPHEN_CODE = re.compile(r"(?<![\w-])(?P<stem>[A-Z]{2,5})-(?P<code>[A-Z0-9]{1,2})(?![\w-]|\.\d)")
#: Upper-case prefixes of hyphenated codes that name no protein: cofactors,
#: nucleotides, "EC-" and nucleic acids.
_NOT_A_STEM = frozenset({
    "EC", "NAD", "NADH", "NADP", "FAD", "FMN", "ATP", "ADP", "AMP", "GTP", "GDP", "CTP",
    "UTP", "ITP", "DNA", "RNA", "PEG", "SDS",
})
#: Run-together forms that read like an isoform and are not one: "MAOI" is a
#: monoamine oxidase inhibitor.
_NOT_AN_ISOFORM = frozenset({"MAOI"})
#: A code right after these words is a strain ("Escherichia coli XL-1
#: Blue", "strain HK-1"), not an isoform. Applied to an abbreviation and its
#: code as well as to the generic hyphen code: "coli HK1" names a strain
#: whatever letters it is spelled with.
_STRAIN_CONTEXT = re.compile(r"(?:\bcoli|\bstrains?)\s+$", re.IGNORECASE)
#: Greek letters written out, the one lower-case form an isoform's own name
#: takes ("isoform alpha", "GST isozyme pi"). The reader before 2026-09-30
#: read any token after a keyword, these among them; they are kept.
_GREEK_NAMES = frozenset({
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi",
    "psi", "omega",
})
#: Capitalised words that open a sentence and are not a name ("Isoform The").
_FUNCTION_WORDS = frozenset({
    "an", "and", "as", "at", "by", "for", "from", "in", "is", "not", "of", "or", "the",
    "to", "was", "were", "with",
})


def _is_a_name(token: Optional[str]) -> bool:
    """Whether the token after "isoform", "isozyme" or "isoenzyme" names one.

    A name is written with a capital or a digit ("H4", "II", "A", "LDHL1",
    "2") or is a Greek letter's name; a lower-case word is the sentence going
    on ("all isozymes tested", "isoform specific inhibitor"). Case matters:
    this compared the lower-cased token with a list of function words that
    held "a", so "isoform A" read as no isoform (while "isoform B" read "B"),
    and a row so written became the fallback for a request for any isoform.
    """
    if not token:
        return False
    if token.lower() in _GREEK_NAMES:
        return True
    if not re.search(r"[A-Z0-9]", token):
        return False
    return len(token) == 1 or token.lower() not in _FUNCTION_WORDS


def _joined(first: str, second: Optional[str]) -> str:
    return f"{first} and {second}" if second else first


def _stem_reading(m: "re.Match") -> Optional[str]:
    if m.group("compact") and m.group(0) in _NOT_AN_ISOFORM:
        return None
    if _STRAIN_CONTEXT.search(m.string[:m.start()]):
        return None
    stem = (m.group("prefix") or "") + m.group("stem")
    code = m.group("code") or m.group("compact")
    second = m.group("code2")
    return _joined(f"{stem}-{code}", f"{stem}-{second}" if second else None)


def _full_name_reading(m: "re.Match") -> Optional[str]:
    stem = _FULL_NAMES[m.group("name").lower()]
    second = m.group("code2")
    return _joined(f"{stem}-{m.group('code')}", f"{stem}-{second}" if second else None)


def _glucokinase_reading(m: "re.Match") -> Optional[str]:
    if re.match(r"\s+activator\b", m.string[m.end():], re.IGNORECASE):
        return None
    word = m.group(0).split()[0]
    return f"{word} {m.group('code')}" if m.group("code") else word


def _hyphen_code_reading(m: "re.Match") -> Optional[str]:
    if m.group("stem") in _NOT_A_STEM or _STRAIN_CONTEXT.search(m.string[:m.start()]):
        return None
    return m.group(0)


#: Every form a name can take, in the order tried at one position.
_FORMS = (
    (_FULL_NAME, _full_name_reading),
    (_STEM_NAME, _stem_reading),
    (_GLUCOKINASE, _glucokinase_reading),
    (_HYPHEN_CODE, _hyphen_code_reading),
)
#: "... and" before a second name: "isozymes LDH-A and LDH-B".
_AND_ANOTHER = re.compile(r"\s+and\s+(?:(?:isozyme|isoenzyme|isoform)\s+)?")


def _name_at(text: str, pos: int) -> Optional[Tuple[str, int]]:
    """(reading, end) of a name starting exactly at `pos`, or None."""
    for pattern, reading_of in _FORMS:
        m = pattern.match(text, pos)
        if m:
            reading = reading_of(m)
            if reading is not None:
                return reading, m.end()
    return None


def _with_another(text: str, reading: str, end: int) -> str:
    """`reading`, joined to a second name written after "and" in one of the
    forms above. A bare code after "and" ("hexokinases Ib and Ic") is read by
    the form's own pattern; this reads a whole second name ("isozymes LDH-A
    and LDH-B")."""
    if " and " in reading:
        return reading
    more = _AND_ANOTHER.match(text, end)
    second = _name_at(text, more.end()) if more else None
    return _joined(reading, second[0]) if second else reading


def _candidates(text: str):
    """(start, reading) for every isoform mention in `text`, keyword first."""
    for k in _KEYWORD.finditer(text):
        named = _name_at(text, k.end())
        if named is not None:
            yield k.start(), _with_another(text, *named)
            continue
        t = _KEYWORD_TOKEN.match(text, k.end())
        if t and _is_a_name(t.group("token")):
            second = t.group("token2")
            yield k.start(), _joined(t.group("token"), second if _is_a_name(second) else None)
    for pattern, reading_of in _FORMS:
        for m in pattern.finditer(text):
            reading = reading_of(m)
            if reading is not None:
                yield m.start(), _with_another(text, reading, m.end())


def read_isoform(commentary: Optional[str]) -> Optional[str]:
    """The isoform a BRENDA row's commentary names, spelled one way, or None
    when it names none. The first mention wins. See the block above."""
    text = commentary or ""
    # min() over (start, order found): at one position a keyword's reading,
    # found first, wins over the bare name it introduces.
    found = [(start, i, reading) for i, (start, reading) in enumerate(_candidates(text))]
    return min(found)[2] if found else None


def isoform_names(reading: Optional[str]) -> tuple:
    """The isoforms one reading names: ("HK-Ib", "HK-Ic") for
    "HK-Ib and HK-Ic", one name otherwise, none for None."""
    if not reading:
        return ()
    return tuple(part for part in re.split(r"\s+and\s+", reading.strip()) if part)


def isoform_key(name: str) -> str:
    """One isoform name's spelling, compared: without case, spaces, hyphens
    or underscores. "MAO-B", "MAO B", "MAOB" and "mao_b" are one. Nothing
    about nomenclature (see "What is not equated" above)."""
    return re.sub(r"[\s_-]+", "", name).lower()


#: A name that is an abbreviation and its code, as the reader spells one
#: ("HK-2", "MAO-B", "TbHK-1", "LDH-A2B2", "PFK-M"): the code is group 1.
_ABBREVIATED = re.compile(r"(?:[A-Z][a-z])?[A-Z]{2,5}-([A-Za-z0-9]{1,4})")
#: A name that is a code alone ("2", "B", "II", "Ia", "PII", "H4"), in any
#: case, since a request is typed ("--isoform b").
_CODE_ALONE = re.compile(_CODE, re.IGNORECASE)


@functools.lru_cache(maxsize=4096)
def _compared_as(name: str) -> tuple:
    """((key, code key or None, abbreviated?), ...) for each isoform `name`
    names, after reading it as a row is read ("What a request is compared
    as", above). Cached: the resolver compares every row with one request."""
    reading = read_isoform(name) or name
    out = []
    for part in isoform_names(reading):
        abbreviated = _ABBREVIATED.fullmatch(part)
        if abbreviated:
            out.append((isoform_key(part), isoform_key(abbreviated.group(1)), True))
        elif _CODE_ALONE.fullmatch(part):
            out.append((isoform_key(part), isoform_key(part), False))
        else:
            out.append((isoform_key(part), None, False))
    return tuple(out)


def _one(x: tuple, y: tuple) -> bool:
    if x[0] == y[0]:
        return True
    # A code alone and the same code after an abbreviation; never two
    # abbreviations ("HK-1" and "HXK-1"), which the keys already compared.
    return x[1] is not None and x[1] == y[1] and x[2] != y[2]


def same_isoform(a: Optional[str], b: Optional[str]) -> bool:
    """True when two isoform names, a row's reading or a request, name one
    isoform. Each is read as a row is read first ("hexokinase 2" is "HK-2"),
    a code alone is that code after an abbreviation ("2" is "HK-2"), and a
    reading naming two ("I and II") is the same as either. The one
    comparison `caterva bind`, `caterva compose` and the literature layer's
    resolver use (Tests/fallback_logic.py, `_same_isoform`), and the API
    server's rowScopeFlags mirrors."""
    if not a or not b:
        return False
    left, right = _compared_as(a.strip()), _compared_as(b.strip())
    return any(_one(x, y) for x in left for y in right)


#: "competitive versus NADH", "mixed-type inhibition versus NAD+", and
#: "mixed inhibitor versus glucose". The last is BRENDA's own wording for
#: rabbit erythrocyte hexokinase and MgADP- (ref 640206: 3 mM versus
#: MgATP2-, 7.8 mM versus glucose). Before "inhibitor" was accepted here,
#: both rows read as mixed with nothing measured against, so a glucose
#: model could not tell the glucose Ki from the MgATP2- one. Of the 766 Ki
#: rows parsed from the hexokinase (recorded), LDH and monoamine oxidase
#: pages on 2026-09-29, those two are the only readings the word changes.
_MODE = re.compile(
    r"\b(non-?competitive|uncompetitive|competitive|mixed(?:-type)?|partial(?:ly)?\s+\w+)\b"
    r"(?:\s+(?:inhibit(?:ion|or)\s+)?(?:versus|vs\.?|with respect to)\s+([^,;]+))?",
    re.I,
)

#: What each mode's Ki is the dissociation constant OF, and so which
#: simulated state it can validate.
MODE_MEANING = {
    "competitive": ("free", "Kd of inhibitor + free enzyme (the site the competing ligand uses)"),
    "noncompetitive": ("either", "Kd of inhibitor for free enzyme and enzyme-substrate complex alike"),
    "uncompetitive": ("ternary", "Kd of inhibitor + enzyme-substrate complex; the apo enzyme does not bind it"),
    "mixed": ("ambiguous", "one of two unequal constants (Ki or Ki'), and the row does not say which"),
    "partial": ("ambiguous", "a partial inhibitor: Ki is a fitted parameter, not cleanly a Kd"),
    "unstated": ("unknown", "inhibition mode not stated, so which binding event this is is unknown"),
}


def dg_kj(ki_mM: float, temperature_c: float) -> float:
    """Standard binding free energy (kJ/mol) for a Ki in mM at T (°C), c° = 1 M."""
    if ki_mM <= 0:
        raise ValueError(f"Ki must be positive, got {ki_mM}")
    return R_KJ * (temperature_c + 273.15) * math.log(ki_mM / 1000.0)


def kj_to_kcal(x: float) -> float:
    return x / KJ_PER_KCAL


def read_mode(commentary: Optional[str]) -> tuple[str, Optional[str]]:
    """(mode, versus) from a BRENDA commentary cell; ('unstated', None) if absent."""
    m = _MODE.search(commentary or "")
    if not m:
        return "unstated", None
    word = m.group(1).lower().replace("-", "")
    if word.startswith("mixed"):
        mode = "mixed"
    elif word.startswith("partial"):
        mode = "partial"
    else:
        mode = word
    versus = m.group(2).strip() if m.group(2) else None
    return mode, versus


@dataclass
class Measurement:
    ki_mM: float
    compound: str
    organism: str
    reference: Optional[str]
    commentary: Optional[str]
    ph: Optional[float]
    temperature_c: Optional[float]
    mode: str
    versus: Optional[str]
    preparation: Optional[str] = None  # "tagged", "immobilised", ... from enzyme_preparation
    isoform: Optional[str] = None
    #: ΔG in kcal/mol: a single value at the stated T, or (lo, hi) over
    #: UNSTATED_T_RANGE_C when the row gave none.
    dg_kcal: tuple = ()
    excluded: Optional[str] = None  # why this row cannot validate the simulated state

    @property
    def dg_lo(self) -> float:
        return min(self.dg_kcal)

    @property
    def dg_hi(self) -> float:
        return max(self.dg_kcal)


def measurement(ki_mM, compound, organism, reference, commentary, ph, temperature_c,
                preparation=None) -> Measurement:
    mode, versus = read_mode(commentary)
    if temperature_c is not None:
        dg = (kj_to_kcal(dg_kj(ki_mM, temperature_c)),)
    else:
        dg = tuple(kj_to_kcal(dg_kj(ki_mM, t)) for t in UNSTATED_T_RANGE_C)
    return Measurement(ki_mM, compound, organism, reference, commentary, ph,
                       temperature_c, mode, versus, preparation, read_isoform(commentary), dg)


def fits_state(m: Measurement, state: str) -> Optional[str]:
    """None when the row can validate a simulation of `state`
    ('free' = inhibitor with apo enzyme, 'ternary' = with enzyme-substrate
    complex), else the reason it cannot."""
    kind, meaning = MODE_MEANING[m.mode]
    if kind in ("either",) or kind == state:
        return None
    if kind == "unknown":
        return None  # kept, and flagged in the verdict: excluding it would hide it
    if kind == "ambiguous":
        return f"{m.mode} inhibition: {meaning}"
    return f"{m.mode} inhibition measures the {kind} state ({meaning}); the simulation is of the {state} state"


@dataclass
class Target:
    """The experimental band a computed ΔG is judged against."""
    compound: str
    organism: str
    state: str
    used: List[Measurement]
    excluded: List[Measurement]
    lo: Optional[float] = None
    hi: Optional[float] = None
    references: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def width(self) -> Optional[float]:
        return None if self.lo is None else self.hi - self.lo


def target(rows: Sequence[Measurement], state: str = "free",
           isoform: Optional[str] = None) -> Target:
    if state not in ("free", "ternary"):
        raise ValueError("state is 'free' or 'ternary'")
    used, excluded = [], []
    for m in rows:
        why = fits_state(m, state)
        # By `same_isoform`, the comparison compose and the resolver use. This
        # compared `.lower()` strings, which called "LDH-A" and "LDH A" two
        # isoforms, and excluded a row naming "I and II" from a simulation of II.
        if not why and isoform and m.isoform and not same_isoform(m.isoform, isoform):
            why = f"measured on {m.isoform}; the simulation is of {isoform}"
        if why:
            m.excluded = why
            excluded.append(m)
        else:
            used.append(m)
    compound = rows[0].compound if rows else ""
    organism = rows[0].organism if rows else ""
    t = Target(compound, organism, state, used, excluded)
    if not used:
        return t
    t.lo = min(m.dg_lo for m in used)
    t.hi = max(m.dg_hi for m in used)
    t.references = sorted({m.reference for m in used if m.reference})
    if len(t.references) < 2:
        t.caveats.append(
            "one publication: how far this constant moves between laboratories is unknown, "
            "so agreement with it is consistency, not validation"
        )
    if any(m.temperature_c is None for m in used):
        t.caveats.append(
            f"a row reports no assay temperature; its ΔG is given over "
            f"{UNSTATED_T_RANGE_C[0]:g}-{UNSTATED_T_RANGE_C[1]:g} °C instead of at a guessed one"
        )
    isoforms = sorted({isoform_key(m.isoform): m.isoform for m in used if m.isoform}.values())
    if len(isoforms) > 1:
        t.caveats.append(
            f"the band pools {len(isoforms)} isoforms ({', '.join(isoforms)}), which are different "
            f"proteins; pass the one simulated (--isoform) to compare like with like"
        )
    if any(m.mode == "unstated" for m in used):
        t.caveats.append("a row does not state its inhibition mode, so which binding event it measured is unknown")
    preps = sorted({m.preparation for m in used if m.preparation and m.preparation not in ("unstated", "native")})
    if preps:
        t.caveats.append(
            f"measured on a {', '.join(preps)} enzyme; a simulation of the unmodified protein "
            f"is compared with a construct"
        )
    versus = sorted({m.versus for m in used if m.versus})
    if versus:
        t.caveats.append(f"inhibition was measured against {', '.join(versus)}; a Ki is specific to that assay")
    return t


@dataclass
class Verdict:
    word: str  # "agrees" | "disagrees" | "no target"
    gap_kcal: float = 0.0  # distance from the band's edge, 0 inside it
    ki_fold: float = 1.0   # the same gap as a fold error in Ki
    detail: str = ""


def judge(t: Target, computed_kcal: float, error_kcal: float, temperature_c: float = 25.0) -> Verdict:
    """Is the computed ΔG ± 2σ consistent with the experimental band?"""
    if t.lo is None:
        return Verdict("no target", detail="no measurement fits the simulated state")
    lo, hi = computed_kcal - 2 * error_kcal, computed_kcal + 2 * error_kcal
    if hi < t.lo:
        gap = t.lo - hi
    elif lo > t.hi:
        gap = lo - t.hi
    else:
        gap = 0.0
    rt_kcal = kj_to_kcal(R_KJ * (temperature_c + 273.15))
    fold = math.exp(gap / rt_kcal)
    if gap == 0.0:
        return Verdict("agrees", 0.0, 1.0,
                       "the computed value ± 2σ overlaps the measured band")
    side = "binds too tightly" if computed_kcal < t.lo else "binds too weakly"
    return Verdict("disagrees", gap, fold,
                   f"the simulation {side}: {gap:.2f} kcal/mol beyond the band even at 2σ, "
                   f"a {fold:.3g}-fold error in Ki")


def parse_computed(text: str) -> tuple[float, float]:
    """'-8.1', '-8.1+-0.5', '-8.1±0.5', '-8.1 0.5' -> (value, error)."""
    parts = re.split(r"\s*(?:±|\+/-|\+-|\s)\s*", text.strip().replace("−", "-"))
    parts = [p for p in parts if p]
    if not 1 <= len(parts) <= 2:
        raise ValueError(f"expected 'ΔG' or 'ΔG±error', got {text!r}")
    value = float(parts[0])
    error = abs(float(parts[1])) if len(parts) == 2 else 0.0
    return value, error
