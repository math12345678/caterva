"""Dimensional and scale checking of composed rate laws.

WHAT MAKES THIS WORTH HAVING
----------------------------
A rate law with the wrong dimensions parses, compiles to Antimony,
integrates, and draws a smooth curve. The trajectory is wrong by whatever
factor the mistake introduced and there is no later point in the pipeline
where that becomes visible. This is the only check that looks.

The scale half is the part a plain dimensional analysis misses: mM and uM
have identical dimensions and differ by a thousand.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from Terium.compose.grammar import recognise
from Terium.compose.units import (
    CONCENTRATION, DIMENSIONLESS, Unit, UnitError, check_rate_law,
    parse_unit, rate_unit_for,
)

mM = parse_unit("mM")
uM = parse_unit("uM")
RATE = rate_unit_for(mM)


def env(**kwargs):
    return {name: parse_unit(unit) for name, unit in kwargs.items()}


class TestReadingAUnit:
    @pytest.mark.parametrize("text,dims,scale", [
        ("mM", {"M": 1}, 1e-3),
        ("uM", {"M": 1}, 1e-6),
        ("M", {"M": 1}, 1.0),
        ("1/s", {"s": -1}, 1.0),
        ("1/(mM*s)", {"M": -1, "s": -1}, 1e3),
        ("mM/s", {"M": 1, "s": -1}, 1e-3),
        ("1/min", {"s": -1}, 1.0 / 60.0),
        ("dimensionless", {}, 1.0),
    ])
    def test_it_reads_the_units_enzymology_uses(self, text, dims, scale) -> None:
        unit = parse_unit(text)
        assert {k: int(v) for k, v in unit.dimensions.items()} == dims
        assert unit.scale == pytest.approx(scale)

    def test_an_unknown_symbol_is_refused_rather_than_guessed(self) -> None:
        # A checker that shrugged at an unrecognised unit would pass every
        # model containing one, which is worse than having no checker.
        with pytest.raises(UnitError, match="not a unit this checker knows"):
            parse_unit("furlongs")

    def test_division_is_left_associative_and_says_so(self) -> None:
        # `1/mM*s` is s/mM, not 1/(mM*s). A parser that silently read the
        # second would accept a wrong declaration as right.
        loose = parse_unit("1/mM*s")
        tight = parse_unit("1/(mM*s)")
        assert not loose.same_dimensions(tight)

    def test_a_unit_compares_equal_to_itself(self) -> None:
        # Floating-point prefix arithmetic is not exact; an equality test on
        # scale would report mM as differing from mM.
        assert parse_unit("1/(mM*s)").agrees_with(parse_unit("1/(mM*s)"))


class TestCatchingRealMistakes:
    def test_a_second_order_constant_in_first_order_units(self) -> None:
        """The commonest single error in a hand-written kinetic model."""
        _, findings = check_rate_law(
            "kon * A * B", env(kon="1/s", A="mM", B="mM"), expected=RATE,
        )
        assert [f.severity for f in findings] == ["blocking"]
        assert "reaction rate is mM/s" in findings[0].detail

    def test_adding_a_concentration_to_a_rate(self) -> None:
        _, findings = check_rate_law(
            "kcat * E * S / (Km + kcat)",
            env(kcat="1/s", E="mM", S="mM", Km="mM"), expected=RATE,
        )
        assert any("cannot be added" in f.detail for f in findings)

    def test_mixing_millimolar_and_micromolar(self) -> None:
        # Dimensions agree perfectly. The model is wrong by a thousand.
        _, findings = check_rate_law(
            "kcat * E * S / (Km + S)",
            env(kcat="1/s", E="mM", S="uM", Km="mM"), expected=RATE,
        )
        assert any(f.severity == "scale" for f in findings)
        assert any("1e+03" in f.detail for f in findings)

    def test_a_correct_michaelis_menten_law_is_clean(self) -> None:
        # The check has to pass what is right, or it is noise and gets
        # switched off.
        _, findings = check_rate_law(
            "kcat * E * S / (Km + S)",
            env(kcat="1/s", E="mM", S="mM", Km="mM"), expected=RATE,
        )
        assert findings == ()

    def test_an_undeclared_symbol_is_refused(self) -> None:
        with pytest.raises(UnitError, match="no unit declared"):
            check_rate_law("k * S", env(S="mM"), expected=RATE)


class TestHillTerms:
    """Cooperative terms, which a naive checker has to give up on."""

    def test_a_hill_ratio_is_dimensionless_for_every_n(self) -> None:
        # K^n / (K^n + R^n) is dimensionless whatever n is, because the SAME
        # symbol raises bases with the same units. A checker that stopped at
        # the first symbolic exponent would report every cooperative term in
        # biology as unverifiable.
        _, findings = check_rate_law(
            "ks * K^n / (K^n + R^n)",
            env(ks="mM/s", K="mM", R="mM", n="dimensionless"), expected=RATE,
        )
        assert findings == ()

    def test_a_scale_mismatch_under_the_exponent_is_still_caught(self) -> None:
        """The hole that tracking symbolic scale closes.

        M^n and M^n are dimensionally identical however n turns out, so a
        purely dimensional treatment passes this. The bases differ by a
        thousand, so the terms differ by 1000^n -- an unknown amount, and
        certainly an error.
        """
        _, findings = check_rate_law(
            "ks * K^n / (K^n + R^n)",
            env(ks="mM/s", K="mM", R="uM", n="dimensionless"), expected=RATE,
        )
        assert len(findings) == 1
        assert "1e+03^n" in findings[0].detail
        assert "not known here" in findings[0].detail

    def test_an_exponent_carrying_units_is_refused(self) -> None:
        _, findings = check_rate_law(
            "ks * K^S / (K^S + R^S)",
            env(ks="mM/s", K="mM", R="mM", S="mM"), expected=RATE,
        )
        assert any("must be dimensionless" in f.detail for f in findings)

    def test_a_numeric_exponent_still_raises_the_scale(self) -> None:
        # The symbolic path must not swallow the concrete one: mM^2 has
        # scale 1e-6, and a checker that forgot would miss a real error.
        squared = mM.power(Fraction(2))
        assert squared.scale == pytest.approx(1e-6)
        assert {k: int(v) for k, v in squared.dimensions.items()} == {"M": 2}


class TestEveryComposedModel:
    def test_nothing_the_grammar_builds_has_a_unit_error(self) -> None:
        """The library's own units have to be right, or none of this helps."""
        for query in (
            "three step phosphorylation cascade",
            "a toggle switch between two repressors",
            "repressilator oscillations",
            "two enzymes competing for the same substrate",
            "reversible binding of a ligand to a receptor",
            "substrate inhibition at high substrate concentration",
            "an open system with constant substrate inflow",
            "enzyme kinetics with a competitive inhibitor",
            "sequential feedback inhibition in amino acid synthesis",
            "allosteric activation of an enzyme by its product",
        ):
            findings = recognise(query).composition.unit_findings()
            assert findings == (), (query, [f.detail for f in findings])

    def test_a_composition_in_micromolar_is_internally_consistent(self) -> None:
        # The standard is consistency, not conformity to SI. A model written
        # in uM is correct and its rates are uM/s.
        recognition = recognise("three step phosphorylation cascade")
        composition = recognition.composition
        composition.concentration_unit = "uM"
        # The motif parameters are declared in mM, so switching the species
        # unit alone SHOULD now be inconsistent -- and is caught.
        assert composition.unit_findings() != ()

    def test_the_environment_covers_every_symbol_a_law_uses(self) -> None:
        # A missing entry raises rather than silently skipping, so this
        # would fail loudly if a motif grew a symbol nothing declared.
        composition = recognise("three step phosphorylation cascade").composition
        environment = composition.unit_environment()
        network = composition.to_network()
        for reaction in network.reactions:
            for token in set(__import__("re").findall(
                r"[A-Za-z_][A-Za-z0-9_]*", reaction.rate_law
            )):
                assert token in environment, (reaction.id, token)


class TestTheSymbolicDimensionCheck:
    """Two different quantities raised to the same exponent, and added.

    Written after a mutation removing the symbolic-dimension comparison
    survived the whole suite. Every existing case where symbolic dimensions
    differed ALSO had differing scales, so `same_scale` was catching them
    and the dimension check was never the thing that fired.

    The hole it left is real: a concentration and a time raised to the same
    Hill coefficient and added together. `M^n + s^n` is meaningless for any
    n, and if the two bases happen to share a scale nothing else notices.
    """

    def test_a_concentration_and_a_time_under_one_exponent_do_not_add(self) -> None:
        # Both bases scale 1e-3, so the scale comparison passes and only the
        # dimension comparison can catch this.
        millimolar = Unit({"M": Fraction(1)}, 1e-3, "mM")
        millisecond = Unit({"s": Fraction(1)}, 1e-3, "ms")
        assert millimolar.scale == millisecond.scale

        _, findings = check_rate_law(
            "ks * K^n / (K^n + T^n)",
            {
                "ks": parse_unit("mM/s"),
                "K": millimolar,
                "T": millisecond,
                "n": DIMENSIONLESS,
            },
            expected=RATE,
        )
        assert any("cannot be added" in f.detail for f in findings), [
            f.detail for f in findings
        ]

    def test_the_same_quantity_under_one_exponent_does_add(self) -> None:
        # The other direction, or the check is just a refusal.
        millimolar = Unit({"M": Fraction(1)}, 1e-3, "mM")
        _, findings = check_rate_law(
            "ks * K^n / (K^n + T^n)",
            {
                "ks": parse_unit("mM/s"),
                "K": millimolar,
                "T": millimolar,
                "n": DIMENSIONLESS,
            },
            expected=RATE,
        )
        assert findings == ()

    def test_an_exponent_that_carries_units_is_rejected(self) -> None:
        # A concentration is not a Hill coefficient.
        _, findings = check_rate_law(
            "ks * K^S",
            env(ks="mM/s", K="mM", S="mM"),
            expected=RATE,
        )
        assert any("must be dimensionless" in f.detail for f in findings)
