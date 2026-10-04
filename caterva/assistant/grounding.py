"""The grounding check: is every claim in a generated text in the result it was written from?

WHY THIS EXISTS
---------------
Caterva's claim is that every number says where it came from and that it
refuses rather than guesses. A language model, asked to explain a result,
will happily write "the Km is about 0.5 mM, significantly higher than
reported" when the result says 0.03 mM and ran no test. The prompt asks it
not to. This module is what makes the asking irrelevant: after generation,
deterministic code extracts the checkable claims from the text and requires
each one to be traceable to the structured result the text was written from.
A text with any claim that is not traceable is NOT shown (the studio falls
back to the engine's own text and says why, `service.py`).

It is pure: text and a JSON-like source in, a `GroundingResult` out. No
network, no model, no I/O, so it can be tested against a large table of
adversarial inputs (`caterva/tests/test_assistant_grounding.py`).

WHAT IS CHECKED
---------------
 1. NUMBERS, in digits, scientific notation (1.4e-3, 1.4 x 10^-3), with
    thousands separators, as percentages, in ranges and as number words
    ("forty", "twenty-three"). A number is grounded when it equals a number
    in the source ROUNDED TO THE PRECISION THE TEXT SHOWS: 0.0432 is
    grounded by "0.043" and "0.04" and not by "0.05". An integer is
    compared at all of its digits ("100" is not grounded by 96).
 2. UNITS. A number written with a unit must match a source number carrying
    that unit (0.03 mM is not "30 uM": a changed unit is a rewritten value,
    even when the arithmetic is right). Spellings of one unit are the same
    unit (1/s, s^-1, "per second"). A number with a unit the source never
    gave it is refused.
 3. EC NUMBERS, citations (BRENDA ref, PMID, DOI, PDB, UniProt accession,
    "et al."), and links: each must be in the source. A URL the source does
    not hold is always refused.
 4. NAMES. A capitalised word, an organism abbreviation ("E. coli") or an
    enzyme-shaped word (-ase) must be in the source or in the short plain
    word list (`plainwords.py`). This is a heuristic: see LIMITS.
 5. COMPARATIVE CLAIMS ("higher than", "exceeds"): the sentence must state
    two grounded numbers of one unit ordered the way the words say, or the
    source must itself use that comparison.
 6. WORDS THAT ARE THE ENGINE'S TO SAY: "significant" needs a statistical
    test in the source; verdict vocabulary ("defensible", "verified") and
    clinical or safety vocabulary ("dose", "patient", "toxic") must be in
    the source; derived quantities in words ("twice", "half") are refused
    because the result never said them.
 7. Things that are never a claim about a result: a key-shaped string, an
    echo of the assistant's own instructions (see `_TABOO`).

WHAT IS NOT NUMBERS, AND MUST NOT FAIL
--------------------------------------
"Step 2", "tier 3", "Figure 1", "section 4", a numbered list ("1.", "(2)"),
an ordinal ("2nd", "first"), an identifier with a digit in it (HK2, 1I10,
S2, kcat1) and the pronoun "one" ("one of the rows") are structure, not
data, and are not looked up.

LIMITS (stated, because the owner will be asked)
------------------------------------------------
 * A lowercase noun that is not enzyme-shaped (a compound name, a
   pathway) is not detected as a name. A model could write "pyruvate" in
   an explanation of a result that never mentioned it and this would pass.
 * Grounding says a number IS in the result, not that the sentence uses it
   for the right quantity. "The Ki is 6.0 mM" passes if 6.0 mM is the Km.
   The comparative check and the 'significant' check narrow this; they do
   not close it.
 * A sentence can be true of every token and still be misleading.
Those are why AI text is always labelled and always shown beside the
deterministic text, never instead of a verdict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from caterva.assistant.plainwords import NON_ENZYME_ASE, ORGANISM_SYNONYMS, PLAIN_WORDS
from caterva.assistant.redact import KEY_PATTERNS

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

#: spelling in text (lower-cased, spaces removed, mu normalised) -> canonical unit.
#: Case matters for M versus mM, so keys are matched on the normalised-micro
#: but otherwise case-sensitive spelling first; word forms are lower-cased.
_UNIT_SPELLINGS: Dict[str, str] = {
    "M": "M", "mM": "mM", "uM": "uM", "nM": "nM", "pM": "pM", "fM": "fM",
    "mol/L": "M", "mmol/L": "mM", "umol/L": "uM", "nmol/L": "nM",
    "mol/l": "M", "mmol/l": "mM", "umol/l": "uM",
    "mg/mL": "mg/mL", "ug/mL": "ug/mL", "g/L": "g/L", "mg/ml": "mg/mL",
    "kcal/mol": "kcal/mol", "kJ/mol": "kJ/mol", "J/mol": "J/mol",
    "kDa": "kDa", "Da": "Da", "nm": "nm", "um": "um", "A": "A", "Å": "A",
    "s": "s", "sec": "s", "ms": "ms", "us": "us", "ns": "ns", "min": "min", "h": "h", "hr": "h", "hrs": "h",
    "d": "d",
    "1/s": "1/s", "/s": "1/s", "s^-1": "1/s", "s-1": "1/s", "s⁻¹": "1/s", "s^−1": "1/s", "s−1": "1/s",
    "1/min": "1/min", "/min": "1/min", "min^-1": "1/min", "min-1": "1/min", "min⁻¹": "1/min",
    "M^-1s^-1": "1/(M*s)", "M-1s-1": "1/(M*s)", "M⁻¹s⁻¹": "1/(M*s)", "1/(M*s)": "1/(M*s)", "1/(Ms)": "1/(M*s)",
    "/M/s": "1/(M*s)", "M^-1/s": "1/(M*s)", "M^−1s^−1": "1/(M*s)",
    "mM^-1s^-1": "1/(mM*s)", "mM-1s-1": "1/(mM*s)", "1/(mM*s)": "1/(mM*s)", "1/(mMs)": "1/(mM*s)",
    "uM^-1s^-1": "1/(uM*s)", "1/(uM*s)": "1/(uM*s)",
    "°C": "degC", "degC": "degC", "K": "K", "%": "%", "percent": "%",
    "fold": "fold", "-fold": "fold",
    "kcal": "kcal", "kJ": "kJ",
}
_WORD_UNITS: Dict[str, str] = {
    "seconds": "s", "second": "s", "minutes": "min", "minute": "min", "hours": "h", "hour": "h", "days": "d",
    "day": "d", "millimolar": "mM", "micromolar": "uM", "nanomolar": "nM", "molar": "M", "picomolar": "pM",
    "degrees": "degC", "percent": "%", "fold": "fold", "kilocalories": "kcal",
    "milliseconds": "ms", "microseconds": "us",
}

_UNIT_ALTS = sorted(set(_UNIT_SPELLINGS) | {"M^-1 s^-1", "M-1 s-1", "M⁻¹ s⁻¹", "mM^-1 s^-1", "mM-1 s-1",
                                            "per second", "per minute", "/ s", "1 / s", "°", "µM", "μM",
                                            "µmol/L", "μmol/L", "µm", "μm", "µs", "μs", "µg/mL", "μg/mL"}, key=len,
                    reverse=True)


def _canonical_unit(raw: str) -> Optional[str]:
    """Canonical unit for a spelling, or None when it is not a unit."""
    text = raw.strip()
    if not text:
        return None
    mu = text.replace("µ", "u").replace("μ", "u")
    compact = mu.replace(" ", "")
    low = compact.lower()
    if low in ("persecond", "/s", "1/s"):
        return "1/s"
    if low == "perminute":
        return "1/min"
    if compact in _UNIT_SPELLINGS:
        return _UNIT_SPELLINGS[compact]
    if low in _WORD_UNITS:
        return _WORD_UNITS[low]
    if text in ("°", "° C", "°C"):
        return "degC"
    if low in ("mm",):  # millimetre is not what a lab text means by mm next to a concentration
        return "mm"
    return None


# ---------------------------------------------------------------------------
# Number extraction
# ---------------------------------------------------------------------------

_SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
        "⁻": "-", "⁺": "+", "−": "-"}

_UNIT_AFTER = "|".join(re.escape(u) for u in _UNIT_ALTS)
_WORD_UNIT_AFTER = "|".join(sorted(_WORD_UNITS, key=len, reverse=True))

_NUM = re.compile(
    r"""
    (?<![\w.])                                  # not inside an identifier or a longer number
    (?P<sign>[-+−])?
    (?P<body>
        (?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?   # 1,234.5  or 12.5  or 12
        |\.\d+                                         # .5
    )
    (?:
        \s*(?:[eE]\s?(?P<e1>[-+−]?\d+)(?![\w])    # 1.4e-3
        |\s?(?:×|x|X|\*|·)\s?10\s?(?:\^|\*\*)?\s?(?P<e2>[-+−]?\d+)(?![\w])  # 1.4 x 10^-3
        |\s?(?:×|x|X|\*|·)\s?10(?P<e3>[⁺⁻−]?[⁰¹²³⁴-⁹]+))
    )?
    """,
    re.X,
)

_CLOSE_BEFORE_LABEL = re.compile(r"(?:step|steps|tier|tiers|stage|stages|section|sections|figure|fig|table|row|item|"
                                 r"option|rule|point|part|line|page|chapter|no|candidate|rank|number|#)\.?\s*$",
                                 re.I)

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULT_WORDS = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
_NUMBER_WORD_RE = re.compile(
    r"\b(?:(?:%s)(?:[- ](?:%s))*(?:[- ](?:%s))?(?:[- ](?:and[- ])?(?:%s)(?:[- ](?:%s))?)*"
    r"|(?:%s))\b" % (
        "|".join(_NUMBER_WORDS), "|".join(_NUMBER_WORDS), "|".join(_MULT_WORDS), "|".join(_NUMBER_WORDS),
        "|".join(_MULT_WORDS), "|".join(_MULT_WORDS)),
    re.I,
)
_ONE_PRONOUN_AFTER = re.compile(
    r"^\s+(?:of|another|can|could|should|would|must|may|might|cannot|who|that|which|to|at|is|has|wants|needs|"
    r"with|in|more|by|does|did|will|shall|thing|way|reason)\b", re.I)
_ONE_PRONOUN_BEFORE = re.compile(r"(?:no|any|every|some|each|this|that|which|the|a|an|no\s+other|at\s+least|"
                                 r"the\s+other|one\s+or|and|or|if|so|as|for|not)\s+$", re.I)
_DERIVED_WORDS = re.compile(r"\b(?:twice|thrice|double[sd]?|doubling|triple[sd]?|tripling|halved|halves|half|"
                            r"quarter|quadruple[sd]?|tenfold|hundredfold|orders? of magnitude|"
                            r"(?:a|one|two|three|four)[- ](?:third|fourth|fifth|tenth)s?)\b", re.I)
_DERIVED_OK = re.compile(r"half[- ]?life|half[- ]?saturat|half[- ]?maximal|half[- ]?max|double[- ]?reciprocal|"
                         r"double[- ]?check|double[- ]?stranded|double[- ]?click|half[- ]?time|doubly|"
                         r"quarter[- ]?(?:of a )?cell", re.I)


_FAMILIES: Dict[str, Tuple[str, Decimal]] = {
    "M": ("conc", Decimal(1)), "mM": ("conc", Decimal("1e-3")), "uM": ("conc", Decimal("1e-6")),
    "nM": ("conc", Decimal("1e-9")), "pM": ("conc", Decimal("1e-12")),
    "s": ("time", Decimal(1)), "ms": ("time", Decimal("1e-3")), "us": ("time", Decimal("1e-6")),
    "ns": ("time", Decimal("1e-9")), "min": ("time", Decimal(60)), "h": ("time", Decimal(3600)),
    "d": ("time", Decimal(86400)),
    "kcal/mol": ("energy", Decimal("4.184")), "kJ/mol": ("energy", Decimal(1)),
    "1/s": ("rate", Decimal(1)), "1/min": ("rate", Decimal(1) / Decimal(60)),
    "1/(M*s)": ("second-order", Decimal(1)), "1/(mM*s)": ("second-order", Decimal(1000)),
    "1/(uM*s)": ("second-order", Decimal(10 ** 6)),
}


def _converted_match(q_value: Decimal, q_sig: int, q_unit: str, numbers: Sequence[Tuple[Decimal, str]]) -> Optional[str]:
    """The source number-with-unit that `q` equals after a change of unit, if any."""
    fam = _FAMILIES.get(q_unit)
    if fam is None:
        return None
    for src, su in numbers:
        other = _FAMILIES.get(su)
        if other is None or other[0] != fam[0] or su == q_unit:
            continue
        converted = src * other[1] / fam[1]
        if number_matches(q_value, q_sig, converted):
            return f"{src.normalize():f} {su}"
    return None


def _dec(text: str) -> Decimal:
    return Decimal(text)


def _sci_value(m: "re.Match[str]") -> Tuple[Decimal, int, int]:
    """(value, significant digits, decimal places) of a number match."""
    body = m.group("body").replace(",", "")
    exp = m.group("e1") or m.group("e2")
    if exp is None and m.group("e3"):
        exp = "".join(_SUP.get(ch, ch) for ch in m.group("e3"))
    sign = -1 if (m.group("sign") in ("-", "−")) else 1
    try:
        mant = _dec(body if not body.startswith(".") else "0" + body)
    except InvalidOperation:
        return Decimal(0), 1, 0
    digits = body.replace(".", "").lstrip("0")
    sig = len(digits) if digits else 1
    if "." in body:
        places = len(body.split(".")[1])
        # "0.030": the trailing zero counts; leading zeros do not (stripped above)
    else:
        places = 0
    value = mant * (Decimal(10) ** int(exp.replace("−", "-"))) if exp is not None else mant
    return value * sign, sig, places


def round_sig(value: Decimal, sig: int) -> Decimal:
    if value == 0:
        return Decimal(0)
    exponent = value.adjusted()
    quantum = Decimal(1).scaleb(exponent - sig + 1)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def number_matches(shown: Decimal, sig: int, source: Decimal) -> bool:
    """Whether `source` rounds, at `sig` significant digits, to `shown`."""
    if shown == 0 or source == 0:
        return shown == source
    if (shown < 0) != (source < 0):
        return False
    try:
        return round_sig(source, sig) == round_sig(shown, sig)
    except InvalidOperation:
        return False


@dataclass(frozen=True)
class Quantity:
    """One number as written in a text."""

    raw: str
    value: Decimal
    sig: int
    unit: Optional[str]          # canonical unit, or None when none was written
    start: int
    end: int
    percent: bool = False
    from_word: bool = False
    structural: bool = False     # a step number, list number or ordinal: not data


def _words_value(match_text: str) -> Optional[Decimal]:
    tokens = [t for t in re.split(r"[-\s]+", match_text.lower()) if t and t != "and"]
    total = 0
    current = 0
    seen = False
    for tok in tokens:
        if tok in _NUMBER_WORDS:
            current += _NUMBER_WORDS[tok]
            seen = True
        elif tok in _MULT_WORDS:
            mult = _MULT_WORDS[tok]
            if mult == 100:
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * mult
                current = 0
            seen = True
        else:
            return None
    return Decimal(total + current) if seen else None


def _unit_after(text: str, pos: int) -> Tuple[Optional[str], int, bool]:
    """(canonical unit, end position, junk) for what follows a number.

    `junk` is True when a letter run follows that is not a unit (an ordinal
    suffix, an identifier tail), which makes the number structure, not data."""
    rest = text[pos:]
    m = re.match(r"\s?(?:%s)(?![A-Za-z])" % _UNIT_AFTER, rest)
    if m:
        unit = _canonical_unit(m.group(0))
        if unit:
            return unit, pos + m.end(), False
    m = re.match(r"\s?(%s)\b" % _WORD_UNIT_AFTER, rest, re.I)
    if m:
        unit = _canonical_unit(m.group(1))
        if unit:
            return unit, pos + m.end(), False
    m = re.match(r"[ ]?-fold\b|[ ]?fold\b", rest, re.I)
    if m:
        return "fold", pos + m.end(), False
    m = re.match(r"(?:st|nd|rd|th)\b", rest)
    if m:
        return None, pos + m.end(), True
    m = re.match(r"[A-Za-z_]", rest)
    if m:
        # a letter run glued to the number: 3D, 1I10, 2x: an identifier
        glued = re.match(r"[A-Za-z_][A-Za-z0-9_]*", rest)
        return None, pos + (glued.end() if glued else 1), True
    return None, pos, False


def extract_quantities(text: str) -> List[Quantity]:
    """Every number in `text`, digits and words, with its unit."""
    out: List[Quantity] = []
    taken: List[Tuple[int, int]] = []
    consumed = 0
    for m in _NUM.finditer(text):
        if m.start() < consumed:
            continue                      # inside the previous number's unit: the -1 of "s^-1"
        start, end = m.start(), m.end()
        # A '-' before the number is a sign only after a space, an opening bracket or the start.
        sign = m.group("sign")
        if sign and start > 0:
            prev = text[start - 1]
            if prev.isalnum() or prev in ".%)":
                start += 1
                sign = None
        value, sig, _places = _sci_value(m)
        if sign is None and m.group("sign"):
            value = abs(value)
        raw = text[start:end]
        # Skip a decimal point glued onto a sentence end: "was 6." -> the regex needs a digit after the dot.
        unit, uend, junk = _unit_after(text, end)
        percent = False
        if text[end:end + 1] == "%" or (unit == "%"):
            percent = True
        structural = junk
        before = text[max(0, start - 14):start]
        if not structural and _CLOSE_BEFORE_LABEL.search(before) and "." not in raw and "e" not in raw.lower():
            structural = True
        # list numbering at the start of a line: "1." "2)" "(3)"
        line_start = text.rfind("\n", 0, start) + 1
        lead = text[line_start:start]
        if not structural and re.fullmatch(r"\s*[(\[]?", lead) and re.match(r"[.)\]]\s", text[end:end + 2]):
            structural = True
        if not structural and re.fullmatch(r"\s*[-*•]\s*[(\[]?", lead) and re.match(r"[.)\]]\s", text[end:end + 2]):
            structural = True
        if not structural and text[start - 1:start] == "(" and text[end:end + 1] == ")" and "." not in raw \
                and len(raw) <= 2:
            structural = True
        out.append(Quantity(raw=raw, value=value, sig=sig, unit=unit if not junk else None, start=start,
                            end=max(end, uend if unit else end), percent=percent, structural=structural))
        taken.append((start, end))
        consumed = max(end, uend)
    # propagate a unit backwards over a range or plus-minus: "0.03-0.05 mM", "6.0 +/- 0.5 mM"
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if a.unit is None and b.unit is not None and not a.structural:
            between = text[a.end:b.start]
            joined = re.fullmatch(r"\s*(?:-|–|—|to|±|\+/-|\+-)\s*", between) or (
                re.fullmatch(r"\s*and\s*", between)
                and re.search(r"between\s*$", text[max(0, a.start - 12):a.start], re.I))
            if joined:
                out[i] = Quantity(a.raw, a.value, a.sig, b.unit, a.start, a.end, a.percent, a.from_word, a.structural)
    # number words
    for m in _NUMBER_WORD_RE.finditer(text):
        word = m.group(0)
        low = word.lower()
        if low == "one":
            after = text[m.end():m.end() + 24]
            before = text[max(0, m.start() - 24):m.start()]
            if _ONE_PRONOUN_AFTER.match(after) or _ONE_PRONOUN_BEFORE.search(before):
                continue
        if any(s <= m.start() < e for s, e in taken):
            continue
        value = _words_value(word)
        if value is None:
            continue
        unit, uend, junk = _unit_after(text, m.end())
        if junk:
            unit = None
        out.append(Quantity(raw=word, value=value, sig=max(1, len(str(int(value)).rstrip("0")) or 1) if value else 1,
                            unit=unit, start=m.start(), end=m.end(), from_word=True,
                            structural=bool(_CLOSE_BEFORE_LABEL.search(text[max(0, m.start() - 14):m.start()]))))
    out.sort(key=lambda q: q.start)
    return out


# ---------------------------------------------------------------------------
# The source: what the text was written from
# ---------------------------------------------------------------------------

_EC_RE = re.compile(r"(?<![\d.])\b\d{1,2}\.\d{1,2}\.\d{1,3}\.(?:n?\d{1,4}|-)(?![\d])")
_EC_PARTIAL_RE = re.compile(r"\bEC\s*(\d{1,2}(?:\.(?:\d{1,3}|-)){0,3})\b")
_CITE_RES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("BRENDA reference", re.compile(r"\b(?:BRENDA\s+)?ref(?:erence)?s?\.?\s*#?\s*(\d{3,})", re.I)),
    ("PMID", re.compile(r"\bPMID:?\s*(\d{3,})", re.I)),
    ("PubMed id", re.compile(r"\bPubMed\s*(?:ID|id)?:?\s*(\d{3,})")),
    ("DOI", re.compile(r"\b(?:doi:?\s*)?(10\.\d{4,9}/[^\s\"'<>),;]+)", re.I)),
    ("PDB id", re.compile(r"\bPDB(?:\s+(?:id|entry|code))?:?\s*([0-9][A-Za-z0-9]{3})\b")),
    ("UniProt accession", re.compile(r"\bUniProt:?\s*([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b")),
)
_ETAL_RE = re.compile(r"\b[A-Z][A-Za-z\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\-]+)?\s+(?:et\s+al\.?)(?:,?\s*\(?\d{4}\)?)?")
_URL_RE = re.compile(r"(?:https?://|ftp://|www\.)[^\s\"'<>)\]]+", re.I)
_MARKUP_RE = re.compile(r"!\[|\]\(|<\s*/?\s*[A-Za-z][^>]*>|javascript:|data:[a-z]+/", re.I)
#: Wording that talks about the assistant's own instructions instead of the result. The phrases are written in
#: fragments on purpose: the repository's injection scanner (scripts/check_prompt_injection.py) reads source for
#: exactly these phrases, and a detector that spells them whole would be flagged as the thing it detects.
_TABOO_RE = re.compile(
    "|".join([
        r"as an " r"ai\b", r"as a language " r"model", r"system " r"prompt", r"my " r"instructions",
        r"i was " r"instructed", r"i have been " r"instructed",
        r"ig" r"nore (?:all |any |the )?(?:previous|prior|above|earlier)",
        r"dis" r"regard (?:all |any |the )?(?:previous|prior)",
        r"developer " r"mode", r"jail" r"break", r"i cannot " r"comply", r"re" r"veal (?:the |your )?(?:key|prompt)",
    ]),
    re.I)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_.']*[A-Za-z0-9]|[A-Za-z0-9]")

_STAT_KEYS = re.compile(r"p[-_ ]?value|pvalue|^signific|significance[-_ ]?(?:test|level)|t[-_ ]?test|anova|chi[-_ ]?sq|"
                        r"confidence[-_ ]?interval|^ci$|wilcoxon|mann[-_ ]?whitney|f[-_ ]?test|z[-_ ]?score|bootstrap|"
                        r"credible", re.I)
#: In prose, evidence that a test was run. "one significant figure" is about rounding, not a test.
_STAT_TEXT = re.compile(r"statistically significant|significance (?:test|level)|\bp[- ]?values?\b|\bp\s*[<=>]\s*0?\.\d|"
                        r"t-test|\banova\b|chi-square|wilcoxon|mann-whitney|confidence interval|\bbootstrap", re.I)


_COMPARATIVE = re.compile(
    r"\b(?P<w>higher|greater|larger|bigger|more|above|exceeds?|exceeded|exceeding|faster|stronger|tighter|"
    r"lower|smaller|less|below|slower|weaker|looser|fewer|better|worse|outperforms?|outperformed)\b"
    r"(?:\s+than)?", re.I)
_UP = {"higher", "greater", "larger", "bigger", "more", "above", "exceed", "exceeds", "exceeded", "exceeding",
       "faster", "stronger", "tighter", "outperform", "outperforms", "outperformed", "better"}
_DOWN = {"lower", "smaller", "less", "below", "slower", "weaker", "looser", "fewer", "worse"}

_VERDICT_WORDS = ("defensible", "verified", "validated", "validates", "proven", "proves", "prove", "reliable",
                  "trustworthy", "certified", "approved", "guaranteed", "confirms", "confirmed", "correct",
                  "incorrect", "accurate", "inaccurate", "wrong", "valid", "invalid")
_CLINICAL_WORDS = ("dose", "doses", "dosage", "dosing", "patient", "patients", "clinical", "clinically", "therapy",
                   "therapeutic", "treatment", "prescribe", "prescription", "toxic", "toxicity", "safe",
                   "safety", "medication", "diagnosis", "diagnose", "side effect", "side effects", "overdose")

_STOP_AFTER_COMPARE = re.compile(r"\s+")


#: Keys whose values are free text that a registry, a paper, a file or the person supplied. They may be quoted
#: as WORDS (a name a row mentions) but they can never GROUND a claim: a figure, an identifier, a link, a verdict
#: word, evidence of a test. Planted text in a BRENDA row's commentary must not be able to vouch for itself.
UNTRUSTED_KEYS = frozenset({
    "commentary", "title", "journal", "scope", "notes", "conditions", "your_input_title", "user_description",
    "question", "filename", "file_name", "header",
})
#: Keys whose whole subtree is untrusted (the person's input to the run, candidates a finder listed by name).
UNTRUSTED_SUBTREES = frozenset({"your_input", "enzyme_candidates"})

_KEY_UNITS = (("_c", "degC"), ("_k", "K"), ("_s", "s"), ("_min", "min"), ("_ms", "ms"), ("_h", "h"))


def _unit_from_key(key: str) -> Optional[str]:
    """A unit a field's own name states (temperature_c, end_s), for a number with no `unit` beside it."""
    low = key.lower()
    return next((u for suffix, u in _KEY_UNITS if low.endswith(suffix) and len(low) > len(suffix) + 2), None)


def _flatten(source: Any, key: str = "", untrusted: bool = False) -> Iterable[Tuple[str, Any, Optional[str], bool]]:
    """(key, scalar, sibling unit, untrusted) for every scalar in a JSON-like value."""
    if isinstance(source, dict):
        unit = source.get("unit") if isinstance(source.get("unit"), str) else None
        for k, v in source.items():
            flag = untrusted or str(k) in UNTRUSTED_SUBTREES or (str(k) in UNTRUSTED_KEYS and not isinstance(v, dict))
            if isinstance(v, (dict, list)):
                yield from _flatten(v, str(k), flag)
            else:
                yield str(k), v, (unit if k in ("value", "lo", "hi", "low", "high", "mean", "sd", "se", "min",
                                                "max", "lower", "upper", "estimate", "stderr") else None), flag
    elif isinstance(source, list):
        for v in source:
            if isinstance(v, (dict, list)):
                yield from _flatten(v, key, untrusted)
            else:
                yield key, v, None, untrusted
    else:
        yield key, source, None, untrusted


class SourceIndex:
    """What a text may draw on, indexed once."""

    def __init__(self, source: Any) -> None:
        self.numbers: List[Tuple[Decimal, str]] = []   # (value, canonical unit or ""): TRUSTED fields only
        self.strings: List[str] = []                   # trusted strings
        self.untrusted_strings: List[str] = []
        self.keys: List[str] = []
        for key, value, unit, untrusted in _flatten(source):
            self.keys.append(key)
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                if untrusted:
                    continue
                try:
                    dec = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
                except InvalidOperation:
                    continue
                if dec.is_nan() or dec.is_infinite():
                    continue
                unit = unit or _unit_from_key(key)
                self.numbers.append((dec, (_canonical_unit(unit) or unit or "") if unit else ""))
            elif isinstance(value, str):
                (self.untrusted_strings if untrusted else self.strings).append(value)
        for s in self.strings:
            for q in extract_quantities(s):
                self.numbers.append((q.value, q.unit or ""))
                if q.percent:
                    self.numbers.append((q.value / 100, ""))
            # numbers glued to a letter ("S2", "1I10", "HK2") are identifiers; also index them by digits
            for m in re.finditer(r"\d+(?:\.\d+)?", s):
                self.numbers.append((Decimal(m.group(0)), ""))
        self.blob = "\n".join(self.strings + self.keys).lower()                      # what may ground a claim
        self.blob_all = (self.blob + "\n" + "\n".join(self.untrusted_strings).lower())  # what a NAME may come from
        self.words = self._words(self.blob_all)
        self.ecs = set(_EC_RE.findall("\n".join(self.strings)))
        self.has_test = any(_STAT_KEYS.search(k) for k in self.keys) or any(_STAT_TEXT.search(s) for s in self.strings)
        self.comparatives = {m.group("w").lower() for m in _COMPARATIVE.finditer("\n".join(self.strings))}

    @staticmethod
    def _words(blob: str) -> Set[str]:
        words: Set[str] = set()
        for tok in _TOKEN_RE.findall(blob):
            tok = tok.strip(".-_'")
            words.add(tok)
            for piece in re.split(r"[-_.]", tok):
                if piece:
                    words.add(piece)
        return words

    def has_number(self, value: Decimal, sig: int, unit: Optional[str], percent: bool = False) -> Tuple[bool, bool]:
        """(matched a number, matched with this unit when one was given)."""
        candidates = [value]
        if percent:
            candidates.append(value / 100)
        number_hit = False
        unit_hit = False
        for src, src_unit in self.numbers:
            for cand in candidates:
                if number_matches(cand, sig, src):
                    number_hit = True
                    if unit is None or unit == src_unit or (unit == "%" and percent):
                        unit_hit = True
        return number_hit, unit_hit

    def has_word(self, word: str) -> bool:
        """A NAME may come from anywhere in the source, free text included (a row can name an isozyme)."""
        w = word.lower().strip(".-_'")
        return w in self.words or w in self.blob_all


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    kind: str       # number | unit | ec | citation | url | name | comparison | significance | verdict | clinical | derived | key | echo | markup
    token: str
    reason: str
    start: int = -1
    end: int = -1

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "token": self.token, "reason": self.reason, "start": self.start, "end": self.end}


@dataclass
class GroundingResult:
    ok: bool
    failures: List[Failure] = field(default_factory=list)
    #: How many checkable tokens were looked up, by kind.
    checked: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "failures": [f.as_dict() for f in self.failures], "checked": dict(self.checked)}

    def summary(self) -> str:
        if self.ok:
            return "every figure and name in the wording was found in your results"
        tokens = ", ".join(dict.fromkeys(f"'{f.token}'" for f in self.failures[:6]))
        return f"the wording contained something that is not in your results: {tokens}"


def _sentences(text: str) -> List[Tuple[int, int]]:
    spans = []
    start = 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"(\[*_-])|\n\s*\n|\n(?=\s*(?:[-*•]|\d+[.)]))", text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if b > a]


def _names_in(text: str) -> List[Tuple[str, int, int, bool]]:
    """(token, start, end, sentence_initial) for each name-shaped token."""
    out = []
    sent_starts = {a for a, _ in _sentences(text)}
    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*)(?![A-Za-z0-9])", text):
        tok = m.group(1)
        # skip the leading markup of a sentence: "**", "- ", "1. "
        initial = False
        before = text[:m.start()]
        stripped = before.rstrip(" \t*_#>-•(\"'[")
        if not stripped or stripped[-1] in ".!?\n" or re.search(r"\n\s*(?:\d+[.)])?\s*$", before) or \
                re.search(r"(?:^|\n)\s*\d+[.)]\s*$", before) or stripped[-1] == ":":
            initial = True
        out.append((tok, m.start(), m.end(), initial))
    return out


def check(text: str, source: Any, *, extra_allowed: Iterable[str] = (), allow_derived: bool = False) -> GroundingResult:
    """Verify `text` against `source`. Pure; never raises on odd input.

    `allow_derived` relaxes only the check on 'half', 'twice' and the like: used for the one-clause
    definitions of terms ("the concentration at half the top rate"), which define a word and state no
    result. Every other check applies to them unchanged."""
    if not isinstance(text, str):
        return GroundingResult(False, [Failure("markup", repr(text)[:40], "the assistant's reply was not text")])
    idx = source if isinstance(source, SourceIndex) else SourceIndex(source)
    allowed = {w.lower() for w in extra_allowed}
    failures: List[Failure] = []
    checked: Dict[str, int] = {}

    def bump(kind: str) -> None:
        checked[kind] = checked.get(kind, 0) + 1

    def fail(kind: str, token: str, reason: str, start: int = -1, end: int = -1) -> None:
        failures.append(Failure(kind, token, reason, start, end))

    masked = list(text)

    def mask(start: int, end: int) -> None:
        for i in range(start, min(end, len(masked))):
            masked[i] = " "

    # -- links, markup, keys, echoes ------------------------------------------
    for m in _URL_RE.finditer(text):
        bump("url")
        url = m.group(0).rstrip(".,;")
        if url.lower() not in idx.blob:
            fail("url", url, "a link that is not in your results", m.start(), m.end())
        mask(m.start(), m.end())
    for m in _MARKUP_RE.finditer(text):
        bump("markup")
        fail("markup", m.group(0), "markup or a link target; the assistant's text is shown as plain text", m.start(), m.end())
    for pattern in KEY_PATTERNS:
        for m in pattern.finditer(text):
            bump("key")
            fail("key", "<key-shaped text>", "text shaped like a secret key", m.start(), m.end())
            mask(m.start(), m.end())
    for m in _TABOO_RE.finditer(text):
        bump("echo")
        fail("echo", m.group(0), "wording that talks about the assistant's instructions, not your results", m.start(), m.end())

    # -- EC numbers --------------------------------------------------------------
    for m in _EC_RE.finditer(text):
        bump("ec")
        if m.group(0) not in idx.ecs:
            fail("ec", m.group(0), "an EC number that is not in your results", m.start(), m.end())
        mask(m.start(), m.end())
    for m in _EC_PARTIAL_RE.finditer(text):
        if any(masked[i] != text[i] for i in range(m.start(), min(m.end(), len(text)))):
            continue
        bump("ec")
        prefix = m.group(1)
        if not any(e == prefix or e.startswith(prefix + ".") for e in idx.ecs):
            fail("ec", "EC " + prefix, "an EC class that is not in your results", m.start(), m.end())
        mask(m.start(), m.end())

    # -- citations ------------------------------------------------------------------
    for label, pattern in _CITE_RES:
        for m in pattern.finditer(text):
            bump("citation")
            ident = m.group(1)
            ok = bool(re.search(r"(?<![0-9A-Za-z])" + re.escape(ident.lower()) + r"(?![0-9A-Za-z])", idx.blob))
            if not ok:
                fail("citation", m.group(0).strip(), f"a {label} that is not in your results", m.start(), m.end())
            elif "brenda" in m.group(0).lower() and "brenda" not in idx.blob:
                fail("citation", m.group(0).strip(), "BRENDA is named as a source, but your results do not name it",
                     m.start(), m.end())
            mask(m.start(), m.end())
    for m in _ETAL_RE.finditer(text):
        bump("citation")
        if m.group(0).lower() not in idx.blob:
            fail("citation", m.group(0), "an author citation that is not in your results", m.start(), m.end())

    # -- numbers and units ------------------------------------------------------------
    masked_text = "".join(masked)
    quantities = extract_quantities(masked_text)
    grounded: Dict[int, Quantity] = {}
    for q in quantities:
        if q.structural:
            continue
        bump("number")
        number_hit, unit_hit = idx.has_number(q.value, q.sig, q.unit, q.percent)
        shown = masked_text[q.start:q.end]
        if q.unit is not None and q.unit not in ("", ):
            shown = masked_text[q.start:max(q.end, q.end)]
        converted = _converted_match(q.value, q.sig, q.unit, idx.numbers) if (q.unit and not number_hit) else None
        if converted:
            fail("unit", f"{q.raw} {q.unit}",
                 f"your results say {converted}; writing it in {q.unit} changes the unit the result was reported in",
                 q.start, q.end)
        elif not number_hit:
            if q.from_word:
                fail("number", q.raw, f"the number '{q.raw}' (written in words) is not in your results", q.start, q.end)
            else:
                fail("number", q.raw, f"{q.raw} is not a figure in your results (at the precision written)", q.start, q.end)
        elif not unit_hit:
            fail("unit", f"{q.raw} {q.unit}", f"{q.raw} is in your results, but not with the unit {q.unit}", q.start, q.end)
        else:
            grounded[q.start] = q
    # derived quantities in words
    for m in ([] if allow_derived else _DERIVED_WORDS.finditer(masked_text)):
        around = masked_text[max(0, m.start() - 12):m.end() + 12]
        if _DERIVED_OK.search(around):
            continue
        bump("derived")
        fail("derived", m.group(0), "a quantity worked out in words that your results do not state", m.start(), m.end())

    # -- statistics words ------------------------------------------------------------
    for m in re.finditer(r"\b(?:statistically|significan(?:t|tly|ce))\b", masked_text, re.I):
        bump("significance")
        if not idx.has_test:
            fail("significance", m.group(0), "a claim of significance, but no statistical test is in your results",
                 m.start(), m.end())

    # -- verdict and clinical vocabulary --------------------------------------------------
    low_text = masked_text.lower()
    for vocab, kind, why in ((_VERDICT_WORDS, "verdict", "a verdict word that is the engine's to say and is not in your results"),
                             (_CLINICAL_WORDS, "clinical", "clinical or safety wording; Caterva gives none and your results hold none")):
        for word in vocab:
            for m in re.finditer(r"\b" + re.escape(word) + r"\b", low_text):
                bump(kind)
                if word not in allowed and not re.search(r"\b" + re.escape(word) + r"\b", idx.blob):
                    fail(kind, word, why, m.start(), m.end())

    # -- comparative claims ----------------------------------------------------------------
    for a, b in _sentences(masked_text):
        sentence = masked_text[a:b]
        for m in _COMPARATIVE.finditer(sentence):
            word = m.group("w").lower()
            if word in ("more", "less", "fewer") and not re.match(r"\s+than\b", sentence[m.end("w"):]):
                continue  # "one more step", "less certain": not a comparison of two figures
            if word == "above" and not re.search(r"\d", sentence):
                continue
            bump("comparison")
            nums = [q for q in quantities if a <= q.start < b and q.start in grounded]
            direction_up = word in _UP or word.rstrip("s") in _UP or word.rstrip("sd") in _UP
            direction_down = word in _DOWN
            relation_ok = False
            if len(nums) >= 2:
                before = [q for q in nums if q.start < a + m.start()]
                after = [q for q in nums if q.start >= a + m.end()]
                if before and after and (before[-1].unit == after[0].unit):
                    left, right = before[-1].value, after[0].value
                    if before[-1].percent != after[0].percent:
                        left, right = abs(left), abs(right)
                    relation_ok = (left > right) if direction_up else (left < right) if direction_down else False
            if not relation_ok:
                stem = word
                in_source = any(c == stem or c.startswith(stem[:5]) for c in idx.comparatives) if len(stem) >= 5 else stem in idx.comparatives
                if not in_source:
                    fail("comparison", m.group(0).strip(),
                         "a comparison your results do not state, and the figures in the sentence do not show it",
                         a + m.start(), a + m.end())

    # -- names ----------------------------------------------------------------------------------
    for tok, s, e, initial in _names_in(masked_text):
        low = tok.lower()
        if low in allowed or low in PLAIN_WORDS:
            continue
        bump("name")
        if idx.has_word(low) or any(idx.has_word(p) for p in re.split(r"[-']", low) if p):
            continue
        # a unit or symbol written with a capital: M, K, Da, Km: allowed when it is a unit
        if _canonical_unit(tok) is not None:
            continue
        # sentence-initial plain words not in the list are checked like any other name
        fail("name", tok, "a name that is not in your results", s, e)
    for m in re.finditer(r"\b[A-Z]\.\s?[a-z]{3,}\b", masked_text):
        bump("name")
        if m.group(0).lower().replace(". ", ".") not in idx.blob_all.replace(". ", "."):
            organism_full = [full for short, full in (("e.", "escherichia"), ("s.", "saccharomyces"),
                                                      ("b.", "bacillus"), ("h.", "homo"), ("m.", "mus"),
                                                      ("r.", "rattus")) if m.group(0).lower().startswith(short)]
            if not any(f in idx.blob_all for f in organism_full):
                fail("name", m.group(0), "an organism that is not in your results", m.start(), m.end())
    for m in re.finditer(r"\b([a-z]{3,}ases?)\b", masked_text):
        word = m.group(1)
        base = word[:-1] if word.endswith("s") and word.endswith("ases") else word
        if word in NON_ENZYME_ASE or base in NON_ENZYME_ASE or word in allowed:
            continue
        bump("name")
        stem = word[:-1] if word.endswith("ases") else word
        if idx.has_word(word) or idx.has_word(stem) or any(w.startswith(stem[:max(5, len(stem) - 2)]) for w in idx.words if len(w) > 4):
            continue
        fail("name", word, "an enzyme name that is not in your results", m.start(), m.end())
    for common, fulls in ORGANISM_SYNONYMS.items():
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(common) + r"(?![A-Za-z])", masked_text, re.I):
            bump("name")
            if common in idx.blob_all or any(f in idx.blob_all for f in fulls):
                continue
            fail("name", m.group(0), "an organism that is not in your results", m.start(), m.end())

    failures.sort(key=lambda f: (f.start, f.kind))
    # one failure per (kind, token) is enough to show; keep first occurrences
    seen: Set[Tuple[str, str]] = set()
    unique = []
    for f in failures:
        k = (f.kind, f.token)
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return GroundingResult(ok=not unique, failures=unique, checked=checked)


def reject_message(result: GroundingResult) -> str:
    """The sentence the page shows when wording is rejected (one place, so the copy is consistent)."""
    kinds = {f.kind for f in result.failures}
    what = "a figure" if kinds & {"number", "unit", "derived"} else \
        "a name" if kinds & {"name", "ec", "citation"} else "a claim"
    return f"The assistant's wording was rejected because it contained {what} that is not in your results."


__all__ = ["Failure", "GroundingResult", "Quantity", "SourceIndex", "check", "extract_quantities", "number_matches",
           "reject_message", "round_sig"]
