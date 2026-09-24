"""Extract assay conditions from a BRENDA commentary string.

BRENDA reports the experimental conditions for a kinetic measurement as free
text in the row's commentary cell, e.g.::

    pH 8.5, 25°C, isozyme H4
    inhibition assay, pH 7.4, 37°C
    pH 8.0, temperature not specified in the publication, healthy breast tissue

Terrium already captured that string (``BRENDAKmEntry.conditions``) and never
read it. This module parses it into structured fields.

Why this matters, and why it is not bookkeeping
-----------------------------------------------
The STRENDA Guidelines -- the reporting standard for enzymology data,
registered in FAIRsharing and recommended by more than 60 biochemistry
journals -- state:

    "The temperature, pH and pressure (if other than atmospheric) of the
     assay MUST always be included, even if previously published."
    -- STRENDA Guidelines v1.4.0, Beilstein-Institut

Km is not a property of an enzyme. It is a property of an enzyme *measured
under conditions*, and it moves with pH and temperature. A Km without them
cannot be reproduced by another laboratory or compared against another
laboratory's figure. See ADR 0010.

Design notes
------------
Absence is reported, never guessed. BRENDA frequently says "temperature not
specified in the publication" -- an explicit statement that the original
authors did not report it. That is different from a commentary that simply
does not mention temperature, and both are different from a parse failure.
The three cases are distinguished (`explicitly_unreported`) because only the
first is a fact about the literature; the others are facts about our parsing.

No value is ever inferred. There is no "assume 25 C if unstated" path, and
there must not be: a plausible default is exactly the kind of unchecked claim
this project keeps finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# pH 8.5 / pH 8 / pH7.4 / pH 7.0-8.0 (range -> midpoint is NOT taken; see below)
_PH_RE = re.compile(
    r"\bpH\s*(?P<low>\d{1,2}(?:\.\d+)?)"
    r"(?:\s*[-–]\s*(?P<high>\d{1,2}(?:\.\d+)?))?",
    re.IGNORECASE,
)

# 25°C / 25 °C / 25 C / 25 degrees C / 20-25°C
_TEMP_RE = re.compile(
    r"(?P<low>-?\d{1,3}(?:\.\d+)?)"
    r"(?:\s*[-–]\s*(?P<high>-?\d{1,3}(?:\.\d+)?))?"
    r"\s*(?:°\s*C\b|\bdegrees?\s*C\b|°C\b)",
    re.IGNORECASE,
)

# "temperature not specified in the publication", "temp. not given", etc.
_TEMP_UNREPORTED_RE = re.compile(
    r"\btemp(?:erature)?\.?\s+not\s+(?:specified|given|reported|stated)\b",
    re.IGNORECASE,
)
_PH_UNREPORTED_RE = re.compile(
    r"\bpH\s+not\s+(?:specified|given|reported|stated)\b",
    re.IGNORECASE,
)

# Buffer systems BRENDA commonly names. Deliberately a small, explicit list:
# a generic "word before the word buffer" heuristic pulls in noise like
# "in buffer" and "assay buffer".
_BUFFER_RE = re.compile(
    r"\b("
    # Concentration prefix. `m[MK]` matched "mM" and "mK" but NOT a bare
    # "M", so "0.5 M Tris-HCl buffer" captured as "Tris-HCl buffer" and
    # the molarity was dropped on the floor.
    #
    # That silently disabled the honesty mechanism in ADR 0028:
    # `BufferIdentity.concentration_text` exists so a reader can see that
    # 0.5 M and 10 mM were treated as the same buffer, and it was empty
    # for precisely the molar strings that motivated it. A field added to
    # disclose a limitation, blind to the case it was written for.
    #
    # Found by scripts/check_commentary_coverage.py, which reported
    # "0 5 M" as unread text beside eight kinetic values.
    r"(?:\d+(?:\.\d+)?\s*[munµ]?M\s+)?"
    r"(?:phosphate|Tris(?:-HCl)?|HEPES|MOPS|MES|PIPES|citrate|acetate|"
    r"glycine|borate|carbonate|imidazole|bicine|tricine|TAPS|CHES|CAPS)"
    r"(?:[\s-]+buffer)?"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class AssayConditions:
    """Structured assay conditions parsed from a BRENDA commentary."""

    ph: float | None = None
    temperature_c: float | None = None
    buffer: str | None = None

    #: True when a value was given as a range; the *low* end is stored.
    ph_is_range: bool = False
    temperature_is_range: bool = False

    #: Fields BRENDA explicitly says the original publication did not report.
    #: A fact about the literature, not about our parsing.
    explicitly_unreported: List[str] = field(default_factory=list)

    @property
    def strenda_complete(self) -> bool:
        """True when both STRENDA-mandatory fields are present.

        Mirrors ``strendaStatusFor`` in the TypeScript provenance module
        (ADR 0010). Both must agree; see
        ``Tests/test_assay_conditions.py::test_matches_typescript_contract``.
        """
        return self.ph is not None and self.temperature_c is not None

    def missing_strenda_fields(self) -> List[str]:
        missing: List[str] = []
        if self.ph is None:
            missing.append("pH")
        if self.temperature_c is None:
            missing.append("temperature")
        return missing


def _parse_ph(text: str) -> tuple[float | None, bool]:
    match = _PH_RE.search(text)
    if not match:
        return None, False
    low = float(match.group("low"))
    is_range = match.group("high") is not None
    # A range is reported at its low end rather than a midpoint. Averaging
    # would invent a number the source never stated -- and pH is logarithmic,
    # so the arithmetic mean of a pH range is not a meaningful quantity.
    if not 0.0 <= low <= 14.0:
        return None, False
    return low, is_range


def _parse_temperature(text: str) -> tuple[float | None, bool]:
    match = _TEMP_RE.search(text)
    if not match:
        return None, False
    low = float(match.group("low"))
    is_range = match.group("high") is not None
    # Liquid-phase enzymology. A value outside this window is a parse error
    # (a concentration, a wavelength, a percentage) rather than a temperature.
    if not -20.0 <= low <= 150.0:
        return None, False
    return low, is_range


def _parse_buffer(text: str) -> str | None:
    match = _BUFFER_RE.search(text)
    if not match:
        return None
    return " ".join(match.group(1).split())


def buffers_equivalent(a: str | None, b: str | None) -> bool:
    """Whether two stated buffers count as the same assay condition.

    ONE RULE, SHARED WITH THE MODEL JUDGE. `model_compatibility.assess`
    reports a `buffer_mismatch` when the distinct normalized buffer strings
    across the set number more than one -- its notion of "different" is
    exactly this case-and-whitespace normalization. The assay window (ADR
    0172) asks the same question when it decides whether a frontier row
    satisfies a buffer-naming window, and it must come to the same answer
    the judge would: a window that accepted a row the judge would call a
    different buffer could "resolve" a mismatch the judge still sees, which
    is two implementations of one judgement drifting apart (ADR 0027).

    Deliberately NOT the molarity-agnostic identity that
    `buffer_identity.py` resolves against PubChem: that is a second,
    network-dependent equivalence. Wiring it into the window would let a
    window claim "0.5 M Tris-HCl" and "500 mM Tris" are the same while the
    judge still reports them as different buffers -- the drift ADR 0027
    names. The judge's own (over)strict rule is the one this reuses.

    `None` means "no buffer stated", which is a distinct fact from any
    string and never compares equal to one.
    """
    if a is None or b is None:
        return False
    return a.strip().lower() == b.strip().lower()


def parse_assay_conditions(commentary: str | None) -> AssayConditions:
    """Parse a BRENDA commentary string into structured assay conditions.

    Never raises and never guesses. An unparseable or empty commentary yields
    an ``AssayConditions`` with everything ``None``, which
    ``strenda_complete`` correctly reports as incomplete.
    """
    if not commentary or not commentary.strip():
        return AssayConditions()

    text = commentary.strip()

    ph, ph_range = _parse_ph(text)
    temperature, temp_range = _parse_temperature(text)

    unreported: List[str] = []
    if _TEMP_UNREPORTED_RE.search(text):
        unreported.append("temperature")
        # An explicit "not specified" overrides any stray number that the
        # temperature regex may have picked up from elsewhere in the string.
        temperature, temp_range = None, False
    if _PH_UNREPORTED_RE.search(text):
        unreported.append("pH")
        ph, ph_range = None, False

    return AssayConditions(
        ph=ph,
        temperature_c=temperature,
        buffer=_parse_buffer(text),
        ph_is_range=ph_range,
        temperature_is_range=temp_range,
        explicitly_unreported=unreported,
    )
