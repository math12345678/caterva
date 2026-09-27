"""Assay-condition extraction from BRENDA commentary strings.

Every string in REAL_COMMENTARIES was taken verbatim from the BRENDA
fixtures in Tests/fixtures/. They are not invented examples -- inventing test
inputs for a parser is how a parser ends up passing against data it will never
see.

Context: STRENDA requires temperature and pH for all reported kinetic data
(Guidelines v1.4.0, Beilstein-Institut). Caterva captured BRENDA's commentary
string and never read it, so every resolved Km was reported without the
conditions it was measured under. See ADR 0010.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assay_conditions import (  # noqa: E402
    AssayConditions,
    buffers_equivalent,
    parse_assay_conditions,
)

# Verbatim from Tests/fixtures/brenda_*.html
REAL_COMMENTARIES = [
    "pH 8.5, 25°C, isozyme H4",
    "inhibition assay, pH 7.4, 37°C",
    "pH 8.0, temperature not specified in the publication, healthy breast tissue",
]


class TestRealFixtureStrings:
    def test_ph_and_temperature_together(self):
        c = parse_assay_conditions("pH 8.5, 25°C, isozyme H4")
        assert c.ph == 8.5
        assert c.temperature_c == 25.0
        assert c.strenda_complete is True
        assert c.missing_strenda_fields() == []

    def test_conditions_after_leading_prose(self):
        c = parse_assay_conditions("inhibition assay, pH 7.4, 37°C")
        assert c.ph == 7.4
        assert c.temperature_c == 37.0
        assert c.strenda_complete is True

    def test_explicitly_unreported_temperature(self):
        """The case that makes the STRENDA distinction real.

        BRENDA is telling us the original publication did not report the
        temperature. That is a fact about the literature, not a parse
        failure, and the value must not be guessed.
        """
        c = parse_assay_conditions(
            "pH 8.0, temperature not specified in the publication, healthy breast tissue"
        )
        assert c.ph == 8.0
        assert c.temperature_c is None
        assert "temperature" in c.explicitly_unreported
        assert c.strenda_complete is False
        assert c.missing_strenda_fields() == ["temperature"]

    @pytest.mark.parametrize("commentary", REAL_COMMENTARIES)
    def test_never_raises_on_real_data(self, commentary):
        assert isinstance(parse_assay_conditions(commentary), AssayConditions)


class TestPhParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("pH 7.4", 7.4),
            ("pH 8", 8.0),      # no decimal, seen in fixtures
            ("pH7.2", 7.2),     # no space
            ("PH 5.5", 5.5),    # case-insensitive
            ("assay at pH 6.8 with cofactor", 6.8),
        ],
    )
    def test_accepts_real_shapes(self, text, expected):
        assert parse_assay_conditions(text).ph == expected

    def test_range_reports_low_end_not_a_midpoint(self):
        """pH is logarithmic; the mean of a pH range is not a pH.

        Averaging would also invent a number the source never stated.
        """
        c = parse_assay_conditions("pH 7.0-8.0, 30°C")
        assert c.ph == 7.0
        assert c.ph_is_range is True

    @pytest.mark.parametrize("text", ["pH 25", "pH 99.9", "pH -3"])
    def test_rejects_values_outside_the_ph_scale(self, text):
        # Out of 0-14 means the regex caught something that is not a pH.
        assert parse_assay_conditions(text).ph is None

    def test_absent_ph_is_none_not_a_default(self):
        assert parse_assay_conditions("25°C, isozyme H4").ph is None


class TestTemperatureParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("25°C", 25.0),
            ("25 °C", 25.0),
            ("37 degrees C", 37.0),
            ("pH 7, 15°C", 15.0),
            ("30.5°C", 30.5),
            ("4°C cold room", 4.0),
        ],
    )
    def test_accepts_real_shapes(self, text, expected):
        assert parse_assay_conditions(text).temperature_c == expected

    def test_range_reports_low_end(self):
        c = parse_assay_conditions("pH 7.4, 20-25°C")
        assert c.temperature_c == 20.0
        assert c.temperature_is_range is True

    @pytest.mark.parametrize("text", ["500°C", "-100°C"])
    def test_rejects_implausible_temperatures(self, text):
        # Outside liquid-phase enzymology: a parse error, not a measurement.
        assert parse_assay_conditions(text).temperature_c is None

    def test_bare_number_is_not_a_temperature(self):
        """A concentration must not become a temperature."""
        assert parse_assay_conditions("50 mM substrate, pH 7.4").temperature_c is None

    def test_explicit_unreported_overrides_a_stray_number(self):
        c = parse_assay_conditions(
            "37°C growth, but assay temperature not specified in the publication"
        )
        assert c.temperature_c is None
        assert "temperature" in c.explicitly_unreported


class TestBuffer:
    @pytest.mark.parametrize(
        ("text", "expected_fragment"),
        [
            ("pH 7.4, 25°C, 50 mM phosphate buffer", "phosphate"),
            ("Tris-HCl, pH 8.0, 37°C", "Tris-HCl"),
            ("pH 7.0, 25°C, HEPES buffer", "HEPES"),
        ],
    )
    def test_named_buffers(self, text, expected_fragment):
        buf = parse_assay_conditions(text).buffer
        assert buf is not None and expected_fragment.lower() in buf.lower()

    def test_buffer_is_not_strenda_mandatory(self):
        """STRENDA mandates temperature, pH and non-atmospheric pressure.

        Buffer is materially useful and deliberately not required, so its
        absence must not make an otherwise-complete record incomplete.
        """
        c = parse_assay_conditions("pH 7.4, 25°C")
        assert c.buffer is None
        assert c.strenda_complete is True

    def test_does_not_invent_a_buffer_from_the_bare_word(self):
        assert parse_assay_conditions("pH 7.4, 25°C, in buffer").buffer is None


class TestDegenerateInput:
    @pytest.mark.parametrize("text", [None, "", "   ", "isozyme H4", "n/a"])
    def test_yields_empty_conditions_and_never_raises(self, text):
        c = parse_assay_conditions(text)
        assert c.ph is None
        assert c.temperature_c is None
        assert c.strenda_complete is False
        assert set(c.missing_strenda_fields()) == {"pH", "temperature"}


class TestNothingIsEverGuessed:
    def test_no_default_temperature_anywhere_in_the_module(self):
        """Guard against a future 'assume 25 C if unstated' convenience.

        A plausible default is exactly the class of unchecked claim this
        project keeps finding; it would silently manufacture STRENDA
        completeness that the source never supported.
        """
        source = (
            pathlib.Path(__file__).resolve().parent / "assay_conditions.py"
        ).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert not re.search(r"temperature_c\s*=\s*2[05]\b", code)
        assert not re.search(r"\bph\s*=\s*7(\.0|\.4)?\b", code)


class TestMatchesTypescriptContract:
    """The Python and TypeScript sides must agree on STRENDA completeness.

    `strenda_complete` here and `strendaStatusFor` in provenance.ts encode the
    same rule in two languages -- exactly the shape Rule 4 requires a test
    for. This checks the truth table rather than the implementation.
    """

    @pytest.mark.parametrize(
        ("ph", "temp", "expected"),
        [
            (7.4, 25.0, True),
            (7.4, None, False),
            (None, 25.0, False),
            (None, None, False),
            (0.0, 0.0, True),   # both are real values, not falsy placeholders
        ],
    )
    def test_completeness_truth_table(self, ph, temp, expected):
        c = AssayConditions(ph=ph, temperature_c=temp)
        assert c.strenda_complete is expected


class TestBuffersEquivalent:
    """The buffer identity rule the assay window and the judge share (ADR
    0175, ADR 0027).

    Buffer is a categorical identity, not a scalar: either two buffers are
    the same or they are not. The rule is case/whitespace-insensitive text
    equality -- deliberately NOT molarity-aware chemical identity, so the
    window and model_compatibility's `buffer_mismatch` never disagree.
    """

    def test_exact_and_case_insensitive(self):
        assert buffers_equivalent("0.1 M MOPS buffer", "0.1 M MOPS buffer")
        assert buffers_equivalent("HEPES", "hepes")
        assert buffers_equivalent("Tris-HCl", "  tris-hcl ")

    def test_collapsed_whitespace_is_equivalent_only_for_padding(
        self
    ):
        # Leading/trailing padding is ignored (strip, like the judge), but
        # an internal run of spaces is NOT -- the strict direction is the
        # safe one, because this rule must never call two buffers equal
        # where model_compatibility reports a buffer_mismatch (ADR 0027).
        # The window's canonical RENDERING collapses runs via
        # window_requirement, so both spellings still deduplicate there.
        assert buffers_equivalent(" 0.1 M MOPS buffer ", "0.1 M MOPS buffer")
        assert not buffers_equivalent("0.1 M  MOPS buffer", "0.1 M MOPS buffer")

    def test_different_buffers_are_not_equivalent(self):
        assert not buffers_equivalent("0.1 M MOPS buffer", "Tris")
        assert not buffers_equivalent("0.5 M Tris-HCl", "500 mM Tris")

    def test_never_equivalent_to_absent(self):
        assert not buffers_equivalent("0.1 M MOPS buffer", None)
        assert not buffers_equivalent(None, "0.1 M MOPS buffer")
        assert not buffers_equivalent(None, None)
