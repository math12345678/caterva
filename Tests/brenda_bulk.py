"""BRENDA bulk TSV download — the path Lisa Jeske recommended.

WHAT SHE SAID
-------------
Asked whether to use SOAP or SPARQL for per-parameter lookups, Lisa Jeske
(BRENDA curation team, Leibniz Institute DSMZ) recommended neither:

    "Simply use the following links to download the data completely as CSV
     files... If this solution does not fit your algorithm, simply use the
     SOAP API."

Her reasoning was sound and Caterva accepted it: she is building a REST API,
so SOAP work would be thrown away, and bulk files are gentler on DSMZ's
servers than per-parameter queries.

THE FINDING THAT CHANGES THE PLAN
---------------------------------
**The bulk KM download has no organism column.**

A capture of her exact URL, verified across all 623 rows of the response,
has a constant nine-field schema:

    EC | enzyme name | value | "-" | substrate | commentary | ligand id |
    reference id(s) | (empty)

Organism appears nowhere as a field value. It occurs in about 2.5% of rows
only as prose inside the commentary, and there almost always as an
*expression host* ("recombinant enzyme expressed from Saccharomyces
cerevisiae") rather than the organism the enzyme came from. Reading those as
the source organism would be worse than having no organism at all.

That matters because of what Jeske herself insisted on in the same email:

    "Enzyme kinetics are species-specific... The simulation should rather
     abort or leave the value empty if there is no exact organism match."

ADR 0024 implements exactly that. So this download cannot feed the
resolution path: it has no organism, and the resolver's central rule is
organism-specific. **The two halves of her advice are in tension, and it is
the data that decides it, not us.**

WHAT THIS MODULE IS THEREFORE FOR
---------------------------------
Not resolution. `resolve_kinetic_value` still reads per-enzyme BRENDA pages,
which do carry organism.

This is a corpus reader. It gives Caterva, for the first time, the ability
to ask questions about BRENDA *in aggregate* — how many KM values report
both pH and temperature, how the STRENDA-completeness picture actually looks
across an EC class rather than across the handful of enzymes anyone has
looked at by hand. That is a real capability and it is the honest use of
this file.

`iter_rows` refuses to be mistaken for a resolver: every row it yields
carries `organism = None`, and `BulkRow.for_resolution()` raises rather than
returning something a caller might treat as organism-specific.

ENCODING
--------
The live download is served as ISO-8859-1 despite what its Content-Type
header claims; the degree sign in "25 °C" arrives as byte 0xB0. Decoding it
as UTF-8 turns it into U+FFFD and the temperature parser then fails to find
a degree sign it can anchor on.

`read_bytes` decodes Latin-1. `parse_rows` additionally repairs U+FFFD where
the surrounding text makes the intent unambiguous, because captures taken
through UTF-8-assuming tooling exist in the wild and silently dropping their
temperatures would be worse than a documented repair.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

#: The nine-field schema, verified against all 623 rows of a real capture.
#: A row with a different field count is malformed, and this parser says so
#: rather than index-erroring or silently reading the wrong column.
EXPECTED_FIELDS = 9

#: BRENDA writes this literal in the value column for rows that describe
#: kinetics in prose rather than reporting a number. 21 of 623 rows in the
#: capture. They are records ABOUT measurements, not measurements, and are
#: never yielded as values.
ADDITIONAL_INFORMATION = "additional information"

#: Sentinel for an absent commentary. A real value, never the empty string —
#: 103 of 623 rows in the capture.
ABSENT = "-"

#: `pH 10.0`, `pH 8.8`, `(pH 10.5)`
_PH_RE = re.compile(r"\bpH\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

#: `25°C`, `21-23°C`, `at 25 °C`, `60<U+FFFD>C`. The degree character is
#: optional-ish because captures decoded as UTF-8 replace it, and a
#: temperature that reads `25 C` is still a temperature.
_TEMP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*[°�]?\s*C\b"
)

#: BRENDA states missing conditions explicitly, and that is a fact about the
#: publication rather than a parse failure. Distinguishing them is the whole
#: point of ADR 0010's `assay_unreported`.
_NOT_SPECIFIED_RE = re.compile(
    r"(pH and temperature|temperature|pH)\s+not specified in the publication",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BulkRow:
    ec_number: str
    enzyme_name: str
    substrate: str
    value: float | None
    commentary: str | None
    ligand_id: str
    reference_ids: tuple[str, ...]
    assay_ph: float | None = None
    assay_temperature_c: float | None = None
    #: Conditions BRENDA states the publication did not report. A fact about
    #: the literature, distinct from "we could not parse one".
    assay_unreported: tuple[str, ...] = ()
    #: Always None. Present so the absence is explicit in every consumer's
    #: type rather than discovered at runtime.
    organism: None = None

    @property
    def is_additional_information(self) -> bool:
        return self.value is None

    def for_resolution(self) -> None:
        """Always raises.

        This file has no organism, and Caterva's resolution path is
        organism-specific by policy (ADR 0024, on Jeske's own
        recommendation). A row from here cannot answer "what is the Km in
        Homo sapiens" and must not be able to pretend it can.

        Raising is deliberate rather than returning None: a None would be
        checked in one call site and forgotten in the next, and the failure
        would be a cross-species substitution with no warning -- the exact
        thing ADR 0024 exists to prevent, reintroduced through a side door.
        """
        raise TypeError(
            "A bulk-download row carries no organism and cannot be used for "
            "organism-specific resolution. BRENDA's bulk KM export has no "
            "organism column (verified across a full capture); use the "
            "per-enzyme page path in fallback_logic.py instead. See "
            "Tests/brenda_bulk.py for why."
        )


def read_bytes(raw: bytes) -> str:
    """Decode a downloaded file: UTF-8 if it is valid UTF-8, else Latin-1.

    BRENDA serves `Content-Type: text/plain;charset=UTF-8` and then sends
    ISO-8859-1 bytes -- the degree sign in "25 C" arrives as 0xB0, which is
    not valid UTF-8. Trusting the header yields either an exception or,
    worse, with errors="replace", silently corrupted temperatures.

    THE FIRST VERSION ASSUMED LATIN-1 UNCONDITIONALLY, AND THAT WAS ALSO
    WRONG. It was right for a live download and wrong for anything already
    re-encoded: a UTF-8 file containing a real degree sign decodes as
    Latin-1 into the two characters "Â°", the temperature regex no longer
    matches, and every row silently loses its temperature. The corpus
    statistics then reported "0 rows report both pH and temperature" for a
    file where most of them do -- a confidently wrong number, which is the
    failure this project cares about most.

    Found by running the statistics script against the repository's own
    fixture, which is UTF-8. Two passes of unit tests did not find it,
    because they fed the decoder bytes rather than files.

    Detection is unambiguous here rather than a heuristic: Latin-1 bytes
    carrying 0xB0 are NOT valid UTF-8, so a successful strict UTF-8 decode
    means the file really is UTF-8. Latin-1 cannot fail, so the fallback
    always terminates.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1")


def _parse_conditions(commentary: str) -> tuple[float | None, float | None, tuple[str, ...]]:
    """(pH, temperature, explicitly-unreported) from a commentary string."""
    unreported: list[str] = []
    for match in _NOT_SPECIFIED_RE.finditer(commentary):
        stated = match.group(1).lower()
        if stated == "ph and temperature":
            unreported.extend(["pH", "temperature"])
        elif stated == "ph":
            unreported.append("pH")
        else:
            unreported.append("temperature")

    ph_match = _PH_RE.search(commentary)
    ph = float(ph_match.group(1)) if ph_match and "pH" not in unreported else None

    temperature: float | None = None
    if "temperature" not in unreported:
        temp_match = _TEMP_RE.search(commentary)
        if temp_match:
            low = float(temp_match.group(1))
            # A range like "21-23 C" is reported as its midpoint, and the
            # fact that it WAS a range is not lost -- the raw commentary
            # travels on the row. Reporting the low end would understate a
            # temperature that a reader would otherwise see stated as a
            # range in the source.
            high = float(temp_match.group(2)) if temp_match.group(2) else low
            temperature = (low + high) / 2

    return ph, temperature, tuple(dict.fromkeys(unreported))


@dataclass(frozen=True)
class ParseReport:
    """What the parser saw, so a caller can check its own denominator.

    A reader that returns rows without saying how many it skipped lets a
    truncated download look like a small one. Every count here is reported
    even when zero.
    """

    rows: int
    additional_information: int
    skipped_comments: int
    skipped_blank: int
    malformed: tuple[tuple[int, str], ...] = ()

    @property
    def total_lines_considered(self) -> int:
        return (
            self.rows
            + self.skipped_comments
            + self.skipped_blank
            + len(self.malformed)
        )


def parse_rows(text: str) -> tuple[list[BulkRow], ParseReport]:
    """Parse a bulk download into rows, with a report of what was skipped."""
    rows: list[BulkRow] = []
    malformed: list[tuple[int, str]] = []
    comments = blanks = extra_info = 0

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            blanks += 1
            continue
        if line.lstrip().startswith("#"):
            comments += 1
            continue

        # NOT rstrip()ped. Every row ends in a tab that produces a ninth,
        # always-empty field, and stripping it makes the row eight fields
        # long -- so a reader that strips and one that does not disagree
        # about the schema, and the one that strips reads every column
        # correctly right up until it does not.
        fields = line.split("\t")
        if len(fields) != EXPECTED_FIELDS:
            # The real capture ends mid-record, so a truncated final line is
            # an expected shape rather than an exotic one. It is reported,
            # not silently dropped: a download cut short is a fact the
            # caller needs.
            malformed.append((number, line[:60]))
            continue

        ec, name, value_text, _dash, substrate, commentary, ligand, refs = fields[:8]

        value: float | None
        if value_text.strip().lower() == ADDITIONAL_INFORMATION:
            value = None
            extra_info += 1
        else:
            try:
                value = float(value_text)
            except ValueError:
                malformed.append((number, line[:60]))
                continue

        commentary_clean = None if commentary == ABSENT else commentary
        ph = temperature = None
        unreported: tuple[str, ...] = ()
        if commentary_clean:
            ph, temperature, unreported = _parse_conditions(commentary_clean)

        rows.append(
            BulkRow(
                ec_number=ec,
                enzyme_name=name,
                substrate=substrate,
                value=value,
                commentary=commentary_clean,
                ligand_id=ligand,
                reference_ids=tuple(r.strip() for r in refs.split(",") if r.strip()),
                assay_ph=ph,
                assay_temperature_c=temperature,
                assay_unreported=unreported,
            )
        )

    return rows, ParseReport(
        rows=len(rows),
        additional_information=extra_info,
        skipped_comments=comments,
        skipped_blank=blanks,
        malformed=tuple(malformed),
    )


def strenda_completeness(rows: list[BulkRow]) -> dict[str, int]:
    """How many rows report both conditions, one, or neither.

    The aggregate question this file makes answerable for the first time.
    Caterva's claim that "roughly three quarters of values are unverified"
    came from its own small default set; this counts a whole EC class.

    `additional information` rows are excluded from the denominator: they
    are records about measurements, not measurements, and counting them
    would understate completeness by including rows that never had a value
    to report conditions for.
    """
    measured = [row for row in rows if not row.is_additional_information]
    both = sum(
        1
        for row in measured
        if row.assay_ph is not None and row.assay_temperature_c is not None
    )
    neither = sum(
        1
        for row in measured
        if row.assay_ph is None and row.assay_temperature_c is None
    )
    return {
        "measured_rows": len(measured),
        "both_conditions": both,
        "one_condition": len(measured) - both - neither,
        "neither_condition": neither,
        "explicitly_unreported": sum(1 for row in measured if row.assay_unreported),
    }
