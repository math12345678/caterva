"""What a BRENDA row measured, beyond its value: the facts that decide
whether it may stand for the enzyme's own constant.

WHY THIS EXISTS
---------------
The adversarial round of 2026-11-11 read every carried row back against
BRENDA, as a professor would, and found numbers that were real rows and still
the wrong ones to carry:

- an apparent Km measured with an inhibitor in the assay (xanthine oxidase,
  ref 766313: 0.0167 mM "in the presence of 0.0005 mM (E)-5-(3-nitrophenyl)-
  ...", while the same paper's "in the absence of inhibitor" row is 0.01208);
- a K0.5 with a Hill coefficient of 1.8 (glucokinase, ref 739603) put into a
  hyperbolic Michaelis-Menten law as if it were a Km;
- constants of constructs: ACE's isolated C-domain (ref 650001), a chimeric
  ACE (ref 678511), a benzoate-modified glucose oxidase (ref 742144), an
  immobilised LDH (ref 741355), trypsin in 20% methanol (ref 95437);
- the minus-K+ control of pyruvate kinase (ref 674499, kcat 3.2 1/s against
  1182 with K+, its essential activator) taken because K+ looked "added";
- a glucokinase row (UniProt P35557) carried for HK2, and a CYP3A5/CYP3A43
  row (P20815, Q9HB55) for CYP2B6, because only the commentary was read.

Each function here reads one of those facts from the row and says it in
words a reader can check against the row. None changes a value; the
resolver (fallback_logic._best_evidenced) decides what to prefer.
"""
from __future__ import annotations

import functools
import re
from typing import Iterable, Optional

# -- K0.5 / Hill ---------------------------------------------------------------

_HALF_SATURATION = re.compile(
    r"\b[KS]\s*\(?\s*0\.5\s*\)?(?=[\s,;:)]|$)|\b[KS]0\.5\b|\[S\]\s*0\.5|\bS50\b"
    r"|\bHill\s+(?:coefficient|constant|value|number)\b|\bnH\s*[=:]?\s*\d"
    r"|\bhalf[- ]saturation\b|\bsigmoid(?:al)?\s+kinetics\b",
    re.IGNORECASE,
)
_HILL_VALUE = re.compile(r"\bHill\s+coefficient\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def half_saturation(commentary: Optional[str]) -> Optional[str]:
    """How the row says its constant is a K0.5 (cooperative half-saturation
    constant) rather than a Michaelis-Menten Km, or None. "K0.5 value, Hill
    coefficient 1.8" gives "a K0.5 with a Hill coefficient of 1.8"."""
    text = commentary or ""
    if not _HALF_SATURATION.search(text):
        return None
    hill = _HILL_VALUE.search(text)
    if hill:
        return f"a K0.5 with a Hill coefficient of {hill.group(1)}"
    return "a K0.5 (half-saturation constant of cooperative kinetics)"


# -- Constructs and preparations -------------------------------------------------

_NEGATED = re.compile(r"\b(?:without|absence\s+of|no)\b[^,;]*$", re.IGNORECASE)

_COSOLVENTS = (r"methanol|ethanol|DMSO|dimethyl\s*sulfoxide|dimethylsulfoxide|glycerol|acetonitrile"
               r"|(?:iso)?propanol|dioxane|acetone|trifluoroethanol|dimethylformamide|DMF|formamide"
               r"|ethylene\s+glycol|sucrose|trehalose|urea|guanidin\w*")

#: (pattern, what the row measured). First match decides.
_CONSTRUCTS = (
    (re.compile(r"\bchimer(?:a|ic)\w*|\bdomain[- ]swap\w*|\b\w+dom-\w+", re.IGNORECASE),
     "a chimeric construct"),
    (re.compile(r"\b(?:[NC]|carboxyl|amino)-?(?:terminal\s+)?(?:half|domain)\b|\b[NC]dom\b|\b(?:isolated|catalytic|single)"
                r"\s+domain\b|\bdomain\s+(?:construct|only)\b", re.IGNORECASE),
     "an isolated domain"),
    (re.compile(r"\b[NC]-terminal\b[^,;]{0,30}\b(?:addition|extension|deletion|truncation)\b|\btruncat\w+|\bdeletion\s+(?:mutant|construct|variant)\b", re.IGNORECASE),
     "a truncated or extended construct"),
    # "recombinant wild-type enzyme in fusion with Aga2" (glucose oxidase,
    # ref 743744): yeast surface display, the enzyme tethered to a protein.
    (re.compile(r"\bfusion\s+(?:protein|enzyme|construct)\b|\bfused\s+(?:to|with)\b"
                r"|\bin\s+fusion\s+with\b|\bfusion\s+with\b|\bsurface[- ]displayed\b", re.IGNORECASE),
     "a fusion construct"),
    (re.compile(r"\bimmobi(?:li[sz]|iz)ed\b|\bimmobili[sz]ation\b|\bcross[- ]?linked\s+"
                r"(?:enzyme|crystal|aggregate)", re.IGNORECASE),
     "an immobilised enzyme"),
    (re.compile(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-modified\b|\bchemically\s+modified\b"
                r"|\bmodified\s+enzyme\b|\bpegylat\w+|\bglycated\b|\bacetylated\s+enzyme\b",
                re.IGNORECASE),
     "a chemically modified enzyme"),
    (re.compile(rf"\b\d+(?:\.\d+)?\s*%\s*(?:\(?[vw]/[vw]\)?\s*)?(?:{_COSOLVENTS})\b"
                rf"|\b\d+(?:\.\d+)?\s*M\s+(?:urea|guanidin\w*)\b", re.IGNORECASE),
     "an assay with a cosolvent or denaturant added"),
    (re.compile(r"\bsubtype\s+[A-Z0-9]{1,3}\b|\bclade\s+[A-Z]\b|\bdrug[- ]resistant\b"
                r"|\bmultidrug[- ]resistant\b", re.IGNORECASE),
     "a named subtype or variant of the enzyme"),
)


def construct_of(commentary: Optional[str]) -> Optional[str]:
    """What non-native form of the enzyme, or what added cosolvent, the row
    names, with the words that say so: "an isolated domain ('C-domain')".
    None for a row naming none. A mention after "without" / "absence of"
    ("without addition of methanol") is the control, not the construct."""
    text = commentary or ""
    for pattern, what in _CONSTRUCTS:
        for m in pattern.finditer(text):
            if _NEGATED.search(text[max(0, m.start() - 40):m.start()]):
                continue
            return f"{what} ({m.group(0).strip()!r})"
    return None


# -- Ions --------------------------------------------------------------------------

_ION = re.compile(
    r"^(?:\(?NH4\)?\d?\+?|[A-Z][a-z]?\d?[+-]|[A-Z][a-z]?\d*\+{1,3}|[A-Z][a-z]?(?:Cl|Br|I|F)\d?"
    r"|[A-Z][a-z]?\d?\(?(?:SO4|NO3|PO4|CO3|OAc|acetate)\)?\d?|\(NH4\)2SO4|NH4Cl"
    r"|(?:potassium|sodium|lithium|rubidium|caesium|cesium|ammonium|magnesium|manganese|calcium"
    r"|zinc|cobalt|nickel|iron|copper)(?:\s+(?:ions?|chloride|sulfate|acetate|nitrate))?)$",
    re.IGNORECASE,
)


#: A salt whose cation is a stand-in for an activating one: thrombin's
#: Na+-free slow form is measured in choline chloride at the ionic strength
#: of the NaCl rows (BRENDA ref 709074). A row naming one is the paper's
#: minus-cation control.
_CATION_STAND_IN = re.compile(
    r"\b(?:choline|tetramethylammonium|tetraethylammonium|tetrabutylammonium|TMA|"
    r"N-methyl-D-glucamine)\s*(?:chloride|Cl|acetate|bromide)?\b", re.IGNORECASE)


def cation_stand_in(commentary: Optional[str]) -> Optional[str]:
    """The stand-in salt a row was measured in, or None."""
    m = _CATION_STAND_IN.search(commentary or "")
    return m.group(0) if m else None


def is_ion(compound: Optional[str]) -> bool:
    """A metal or inorganic ion, or its simple salt: K+, Mg2+, NaCl, MgCl2,
    (NH4)2SO4, potassium. These are cofactors and activators (K+ for pyruvate
    kinase, Na+ for thrombin's fast form, Zn2+ for carbonic anhydrase); a row
    measured without one is a minus-activator control, never the enzyme's
    physiological constant."""
    return bool(compound and _ION.match(compound.strip()))


# -- Isoform from the UniProt column ----------------------------------------------

_ACCESSION = re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b")


def accessions(cell: Optional[str]) -> tuple:
    """The UniProt accessions a row's own accession cell lists, in order."""
    return tuple(dict.fromkeys(_ACCESSION.findall(cell or "")))


@functools.lru_cache(maxsize=512)
def _labels_of_ec(ec: str) -> tuple:
    """((accession, label, organism code), ...) the enzyme index files under
    `ec`, or () where the caterva package (and its index) is not importable."""
    try:
        from caterva.enzymes.index import load_index
    except ImportError:
        return ()
    try:
        entry = load_index().get(ec)
    except Exception:  # an index that cannot be read names nothing
        return ()
    if entry is None:
        return ()
    return tuple((p.accession, p.label, code)
                 for code, proteins in entry.proteins.items() for p in proteins)


def isoforms_of_accessions(ec: Optional[str], cell: Optional[str]) -> tuple:
    """The gene symbols (as the enzyme index labels them) of the proteins a
    row's own UniProt cell names under `ec`, or () when any accession is not
    one the index files under that EC (then the column cannot say which
    protein the row measured) or the cell names none.

    P35557 under EC 2.7.1.1 is ("GCK",); "P20815,Q9HB55" under 1.14.14.1 is
    ("CYP3A5", "CYP3A43")."""
    found = accessions(cell)
    if not ec or not found:
        return ()
    labels = {acc: label for acc, label, _ in _labels_of_ec(ec)}
    if not all(a in labels for a in found):
        return ()
    return tuple(dict.fromkeys(labels[a] for a in found))


def proteins_in_organism_of(ec: Optional[str], cell: Optional[str]) -> int:
    """How many proteins the index files under `ec` in the organism of the
    row's first accession: a row naming GCK is worth naming when the EC is
    five human proteins."""
    found = accessions(cell)
    if not ec or not found:
        return 0
    entries = _labels_of_ec(ec)
    code = next((c for acc, _, c in entries if acc == found[0]), None)
    return sum(1 for _, _, c in entries if c == code) if code else 0


# -- Matching a Km row with a kcat row ---------------------------------------------

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
#: Words that say which table a row is in, not what was measured.
_TABLE_WORDS = frozenset({"km", "kcat", "value", "values", "turnover", "number", "numbers",
                          "s", "mm", "min", "sec", "the", "for", "of", "and", "at", "in", "c",
                          "degrees", "a", "an", "with", "constant", "michaelis"})


_HALF_SATURATION_STATEMENT = re.compile(
    r"\b[ks]\s*\(?\s*0\.5\s*\)?(?:\s+values?)?(?![\w.])"
    r"|\bhill\s+coefficient\s*(?:of|=|:)?\s*\d+(?:\.\d+)?|\bnh\s*[=:]?\s*\d+(?:\.\d+)?")
#: A name and its number written apart ("Adh 1"), not a pH or a temperature.
_NAME_NUMBER = re.compile(r"\b(?!pH\b)([A-Z][A-Za-z]+)\s+(\d+)\b(?![.\d])")


def condition_words(conditions: Optional[str], substrate: Optional[str] = None) -> frozenset:
    """The words of a row's commentary that say what was measured, for
    comparing a Km row with a kcat row of one paper: "pH 8, 25°C, 200 mM NaCl"
    and "pH 8, 25°C, 200 mM choline chloride" differ (thrombin's fast and slow
    forms, ref 709074); "recombinant enzyme, pH 7.5" and "pH 7.5, recombinant
    enzyme" do not."""
    # "Adh 1" and "Adh1" are one name (horse liver ADH, ref 285647): a
    # capitalised name and its number written apart.
    text = _NAME_NUMBER.sub(r"\1\2", conditions or "")
    text = text.lower().replace("°", " ")
    # How the constant is reported is not what was measured: BRENDA copies
    # "K0.5 value, Hill coefficient 1.8" onto only some of a paper's rows of
    # one assay (glucokinase, ref 739603).
    text = _HALF_SATURATION_STATEMENT.sub(" ", text)
    words = set(_WORD.findall(text)) - _TABLE_WORDS
    if substrate:
        words -= set(_WORD.findall(substrate.lower()))
    return frozenset(words)


def same_measurement(a: dict, b: dict, substrate: Optional[str] = None) -> bool:
    """Whether two rows (dicts with conditions, ph, temperature_c) were
    measured under one set of stated conditions: the same pH and temperature
    (both stated alike, or both unstated) and the same remaining words."""
    def close(x, y, tol):
        if x is None or y is None:
            return x is None and y is None
        return abs(float(x) - float(y)) <= tol
    return (close(a.get("ph"), b.get("ph"), 0.05)
            and close(a.get("temperature_c"), b.get("temperature_c"), 0.5)
            and condition_words(a.get("conditions"), substrate)
            == condition_words(b.get("conditions"), substrate))


def distinct_values(rows: Iterable[dict]) -> set:
    return {float(r["value"]) for r in rows}


__all__ = [
    "accessions", "condition_words", "construct_of", "half_saturation", "is_ion",
    "isoforms_of_accessions", "proteins_in_organism_of", "same_measurement",
]
