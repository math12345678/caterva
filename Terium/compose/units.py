"""Unit algebra, and dimensional checking of rate laws.

WHAT THIS CATCHES THAT NOTHING ELSE DOES
----------------------------------------
A rate law is dimensionally constrained: a reaction rate is an amount of
substance per volume per time, and every term feeding it has to agree. A law
that does not balance still parses, still compiles to Antimony, still
integrates, and still produces a smooth curve. The trajectory is simply
wrong by whatever factor the mistake introduced, and there is no point in
the pipeline where that becomes visible.

The specific mistakes this finds:

  * a second-order rate constant declared as 1/s instead of 1/(mM*s), which
    is the commonest single error in a hand-written kinetic model;
  * a Km compared against a rate rather than a concentration;
  * a Hill exponent applied to something that carries dimensions, so K^n and
    X^n are not commensurable;
  * two motifs composed where one works in mM and the other in uM -- the
    scale mismatch that a purely dimensional check would MISS, which is why
    scale is tracked here alongside dimension.

The last one is the reason this is not simply dimensional analysis. mM and
uM have identical dimensions and differ by a thousand, and a model that
mixes them is wrong by a thousand while every dimension balances perfectly.

WHY NOT libSBML's UNIT SYSTEM
-----------------------------
Because the check has to happen at COMPOSITION time, before anything is
compiled -- a model that will be refused should cost nothing to refuse, and
by the time there is SBML the composition decisions have already been made
and are harder to attribute. `Terium/core/sbml_units.py` remains the
authority for units on an SBML document that arrived from outside; this is
the authority for units on a model Terrium built itself.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not convert. A composition mixing mM and uM is reported, not
silently rescaled, for the same reason `with_resolved_values` refuses to
convert a resolved value: the factor is not always dimensionless (mM to
mg/mL needs a molecular weight), and a checker that silently fixed the easy
cases would train a reader to trust it on the hard ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: Base dimensions. Deliberately small: concentration and time are enough
#: for every rate law a reaction network can express, and adding mass or
#: charge would create combinations nothing here can check.
BASE_CONCENTRATION = "M"
BASE_TIME = "s"
BASES = (BASE_CONCENTRATION, BASE_TIME)

#: Metric prefixes, as multipliers. Only the ones that appear in
#: enzymology; a prefix nobody uses is a typo waiting to be accepted.
PREFIXES: Dict[str, float] = {
    "": 1.0,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "k": 1e3,
}

#: Time units, as seconds.
TIME_UNITS: Dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "day": 86400.0,
}

#: How close two scales must be to count as the same. Floating-point
#: multiplication of prefixes is not exact -- 1e-3 * 1e3 is not 1.0 to the
#: bit -- so an equality test would report a mismatch between a unit and
#: itself.
SCALE_TOLERANCE = 1e-9


class UnitError(ValueError):
    """A unit string could not be read, or two units do not agree."""


@dataclass(frozen=True)
class Unit:
    """A dimension vector and a scale.

    `scale` is the multiplier taking this unit to the base unit: mM has
    dimensions {M: 1} and scale 1e-3, so 5 mM is 5 * 1e-3 in base molar.
    Tracking it separately from the dimensions is what lets a mM/uM mismatch
    be reported -- dimensionally they are identical.
    """

    dimensions: Mapping[str, Fraction] = field(default_factory=dict)
    scale: float = 1.0
    #: How it was written, for error messages. A reader debugging a unit
    #: error wants to see "1/(mM*s)", not "{M: -1, s: -1}".
    text: str = ""
    #: Dimensions carried under a SYMBOLIC exponent: `{"n": {"M": 1}}` for
    #: `X^n` where X is a concentration and n is a Hill coefficient.
    #:
    #: This is what makes a Hill function checkable. `K^n / (K^n + X^n)` is
    #: dimensionless for every n, but only because the SAME symbol raises
    #: bases with the same units -- and a checker that gave up at the first
    #: symbolic exponent would report every cooperative term in biology as
    #: unverifiable. Tracking which symbol carries which dimensions lets the
    #: addition be confirmed and the division cancel.
    symbolic: Mapping[str, Mapping[str, Fraction]] = field(default_factory=dict)
    #: The SCALE of each base that was raised to a symbolic exponent.
    #:
    #: Kept separately from `scale` because the magnitude it contributes is
    #: unknown -- 1000^n for an unknown n. But whether two symbolic terms
    #: came from bases of the SAME scale is knowable, and is the difference
    #: between `K^n + R^n` with both in mM and the same expression with R in
    #: uM. The second is wrong by 1000^n; without this it passed silently,
    #: because dimensionally M^n and M^n are identical.
    symbolic_scale: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned = {
            base: exponent
            for base, exponent in self.dimensions.items()
            if exponent != 0
        }
        object.__setattr__(self, "dimensions", dict(sorted(cleaned.items())))
        pruned = {
            symbol: dict(sorted(
                (base, exponent) for base, exponent in dims.items() if exponent != 0
            ))
            for symbol, dims in self.symbolic.items()
        }
        object.__setattr__(
            self, "symbolic",
            dict(sorted((s, d) for s, d in pruned.items() if d)),
        )
        object.__setattr__(
            self, "symbolic_scale",
            dict(sorted(
                (symbol, value) for symbol, value in self.symbolic_scale.items()
                if symbol in pruned and pruned[symbol]
            )),
        )

    # -- algebra ------------------------------------------------------

    def __mul__(self, other: "Unit") -> "Unit":
        merged: Dict[str, Fraction] = dict(self.dimensions)
        for base, exponent in other.dimensions.items():
            merged[base] = merged.get(base, Fraction(0)) + exponent
        return Unit(merged, self.scale * other.scale,
                    _join(self.text, "*", other.text),
                    _combine_symbolic(self.symbolic, other.symbolic, 1),
                    {**self.symbolic_scale, **other.symbolic_scale})

    def __truediv__(self, other: "Unit") -> "Unit":
        merged: Dict[str, Fraction] = dict(self.dimensions)
        for base, exponent in other.dimensions.items():
            merged[base] = merged.get(base, Fraction(0)) - exponent
        if other.scale == 0:
            raise UnitError(f"division by a zero-scaled unit: {other.text!r}")
        return Unit(merged, self.scale / other.scale,
                    _join(self.text, "/", other.text),
                    _combine_symbolic(self.symbolic, other.symbolic, -1),
                    {**self.symbolic_scale, **other.symbolic_scale})

    def power(self, exponent: Fraction) -> "Unit":
        return Unit(
            {base: value * exponent for base, value in self.dimensions.items()},
            self.scale ** float(exponent),
            f"({self.text})^{exponent}" if self.text else "",
            {
                symbol: {b: v * exponent for b, v in dims.items()}
                for symbol, dims in self.symbolic.items()
            },
            dict(self.symbolic_scale),
        )

    def symbolic_power(self, symbol: str) -> "Unit":
        """Raise to a symbolic exponent, remembering which symbol did it.

        The concrete dimensions move into `symbolic` under that name, so
        `X^n` and `K^n` compare equal when X and K do, and `K^n / X^n`
        cancels to dimensionless without either exponent ever being known.
        """
        moved: Dict[str, Dict[str, Fraction]] = {
            existing: dict(dims) for existing, dims in self.symbolic.items()
        }
        under = moved.setdefault(symbol, {})
        for base, exponent in self.dimensions.items():
            under[base] = under.get(base, Fraction(0)) + exponent
        # Scale is deliberately NOT raised: the exponent is unknown, so the
        # magnitude is too. A scale comparison against an unknown power
        # would be a guess, and this reports what it can check rather than
        # inventing what it cannot.
        scales = dict(self.symbolic_scale)
        scales[symbol] = scales.get(symbol, 1.0) * self.scale
        return Unit(
            {}, 1.0, f"({self.text})^{symbol}" if self.text else "",
            moved, scales,
        )

    # -- comparison ---------------------------------------------------

    @property
    def dimensionless(self) -> bool:
        return not self.dimensions and not self.symbolic

    def same_dimensions(self, other: "Unit") -> bool:
        return (
            self.dimensions == other.dimensions
            and self.symbolic == other.symbolic
        )

    def same_scale(self, other: "Unit") -> bool:
        if set(self.symbolic_scale) != set(other.symbolic_scale):
            return False
        for symbol, value in self.symbolic_scale.items():
            theirs = other.symbolic_scale[symbol]
            if value == 0 or theirs == 0:
                if value != theirs:
                    return False
            elif abs(value / theirs - 1.0) >= SCALE_TOLERANCE:
                return False
        if self.scale == 0 or other.scale == 0:
            return self.scale == other.scale
        return abs(self.scale / other.scale - 1.0) < SCALE_TOLERANCE

    def symbolic_scale_ratio(self, other: "Unit") -> Optional[Tuple[str, float]]:
        """The first symbol whose base scales differ, and by how much.

        Returned so the message can say "the bases differ by 1000, so these
        differ by 1000^n" -- naming the factor that IS known even though the
        power it is raised to is not.
        """
        for symbol, value in self.symbolic_scale.items():
            theirs = other.symbolic_scale.get(symbol)
            if theirs and value and abs(value / theirs - 1.0) >= SCALE_TOLERANCE:
                return symbol, max(value, theirs) / min(value, theirs)
        return None

    def agrees_with(self, other: "Unit") -> bool:
        return self.same_dimensions(other) and self.same_scale(other)

    def describe(self) -> str:
        if self.text:
            return self.text
        if self.dimensionless:
            return "dimensionless"
        parts = []
        for base, exponent in self.dimensions.items():
            parts.append(base if exponent == 1 else f"{base}^{exponent}")
        return "*".join(parts)

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.describe()


DIMENSIONLESS = Unit({}, 1.0, "dimensionless")
CONCENTRATION = Unit({BASE_CONCENTRATION: Fraction(1)}, 1.0, "M")
PER_TIME = Unit({BASE_TIME: Fraction(-1)}, 1.0, "1/s")
#: A reaction rate in BASE molar per second.
#:
#: Rarely the right thing to compare against directly -- see
#: `rate_unit_for`. A model written consistently in mM is correct and its
#: rates are mM/s, not M/s, and demanding base units would report every
#: enzymology model in the literature as wrong by a thousand.
REACTION_RATE = Unit(
    {BASE_CONCENTRATION: Fraction(1), BASE_TIME: Fraction(-1)}, 1.0, "M/s"
)


def rate_unit_for(concentration: Unit, time: Optional[Unit] = None) -> Unit:
    """The rate unit a model in `concentration` should have.

    The standard is INTERNAL CONSISTENCY, not conformity to SI. A model
    whose species are in mM and whose rates are in mM/s is correct; the same
    model with one rate in M/s is wrong by a thousand. Comparing everything
    against base molar would invert that -- reporting the correct model as
    wrong and, worse, reporting a model that mixed mM and uM as no more
    wrong than one consistently in mM.
    """
    return concentration / (time or Unit({BASE_TIME: Fraction(1)}, 1.0, "s"))


def _combine_symbolic(
    left: Mapping[str, Mapping[str, Fraction]],
    right: Mapping[str, Mapping[str, Fraction]],
    sign: int,
) -> Dict[str, Dict[str, Fraction]]:
    merged: Dict[str, Dict[str, Fraction]] = {
        symbol: dict(dims) for symbol, dims in left.items()
    }
    for symbol, dims in right.items():
        target = merged.setdefault(symbol, {})
        for base, exponent in dims.items():
            target[base] = target.get(base, Fraction(0)) + sign * exponent
    return merged


def _join(left: str, operator: str, right: str) -> str:
    if not left or not right:
        return left or right
    return f"{left}{operator}{right}"


# ---------------------------------------------------------------------------
# Parsing unit strings
# ---------------------------------------------------------------------------

_UNIT_TOKEN = re.compile(
    r"\s*(?P<token>\d+\.?\d*|[A-Za-zµ]+|\*|/|\(|\)|\^|-)"
)


def parse_unit(text: str) -> Unit:
    """Read a unit string like `1/(mM*s)` or `mM` or `dimensionless`.

    Recursive descent over the same grammar a rate law uses, so the two
    cannot disagree about what `a/b*c` means -- a real hazard, since
    division and multiplication are left-associative and `1/mM*s` is
    `s/mM`, not `1/(mM*s)`. Parenthesise, and this reports what it read.
    """
    stripped = (text or "").strip()
    if not stripped or stripped.lower() in {
        "dimensionless", "unitless", "none", "-", "1",
    }:
        return Unit({}, 1.0, "dimensionless")

    tokens = _tokenise_unit(stripped)
    parser = _UnitParser(tokens, stripped)
    unit = parser.expression()
    parser.expect_end()
    return Unit(unit.dimensions, unit.scale, stripped)


def _tokenise_unit(text: str) -> List[str]:
    tokens: List[str] = []
    position = 0
    while position < len(text):
        match = _UNIT_TOKEN.match(text, position)
        if not match:
            raise UnitError(
                f"cannot read unit {text!r}: unexpected character "
                f"{text[position]!r} at position {position}"
            )
        tokens.append(match.group("token"))
        position = match.end()
    return tokens


class _UnitParser:
    def __init__(self, tokens: Sequence[str], source: str) -> None:
        self.tokens = list(tokens)
        self.index = 0
        self.source = source

    def peek(self) -> Optional[str]:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise UnitError(f"unit {self.source!r} ends unexpectedly")
        self.index += 1
        return token

    def expect_end(self) -> None:
        if self.peek() is not None:
            raise UnitError(
                f"unit {self.source!r}: trailing {self.peek()!r}"
            )

    def expression(self) -> Unit:
        unit = self.term()
        while self.peek() in ("*", "/"):
            operator = self.take()
            right = self.term()
            unit = unit * right if operator == "*" else unit / right
        return unit

    def term(self) -> Unit:
        unit = self.atom()
        if self.peek() == "^":
            self.take()
            negative = False
            if self.peek() == "-":
                self.take()
                negative = True
            exponent = Fraction(self.take())
            unit = unit.power(-exponent if negative else exponent)
        return unit

    def atom(self) -> Unit:
        token = self.take()
        if token == "(":
            unit = self.expression()
            if self.take() != ")":
                raise UnitError(f"unit {self.source!r}: unbalanced parenthesis")
            return unit
        if re.fullmatch(r"\d+\.?\d*", token):
            value = float(token)
            if value == 0:
                raise UnitError(f"unit {self.source!r}: a zero factor")
            return Unit({}, value, "")
        return _symbol(token, self.source)


def _symbol(token: str, source: str) -> Unit:
    """One unit symbol: a time unit, or a prefixed molar."""
    lowered = token.lower()
    if lowered in TIME_UNITS:
        return Unit({BASE_TIME: Fraction(1)}, TIME_UNITS[lowered], token)

    # Molar, with an optional metric prefix. `M` alone is molar.
    if token.endswith("M"):
        prefix = token[:-1]
        if prefix in PREFIXES:
            return Unit(
                {BASE_CONCENTRATION: Fraction(1)}, PREFIXES[prefix], token
            )

    raise UnitError(
        f"unit {source!r}: {token!r} is not a unit this checker knows. It "
        f"reads molar with a metric prefix (M, mM, uM, nM, pM) and time "
        f"(s, min, h, day). Anything else has to be spelled in those, "
        f"because a unit it guessed at would make the check meaningless."
    )


# ---------------------------------------------------------------------------
# Dimensional checking of an expression
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitFinding:
    """One place an expression does not balance."""

    where: str
    detail: str
    #: `blocking` when the model is certainly wrong; `scale` when the
    #: dimensions agree and the magnitudes do not, which is wrong by a
    #: factor rather than wrong in kind.
    severity: str = "blocking"


_EXPR_TOKEN = re.compile(
    r"\s*(?P<token>\d+\.?\d*(?:[eE][-+]?\d+)?|[A-Za-z_][A-Za-z0-9_]*"
    r"|\*\*|[+\-*/^(),])"
)


class _ExpressionParser:
    """Recursive descent over a rate law, returning a `Unit`.

    Deliberately a second parser rather than reusing the unit one: the
    grammars overlap but the leaves differ -- a rate law's leaves are
    identifiers that must be LOOKED UP, and its `+` means dimensional
    agreement rather than addition of units.
    """

    def __init__(self, text: str, environment: Mapping[str, Unit]) -> None:
        self.source = text
        self.environment = environment
        self.tokens = self._tokenise(text)
        self.index = 0
        self.findings: List[UnitFinding] = []

    def _tokenise(self, text: str) -> List[str]:
        tokens: List[str] = []
        position = 0
        while position < len(text):
            match = _EXPR_TOKEN.match(text, position)
            if not match:
                raise UnitError(
                    f"cannot read expression {text!r}: unexpected "
                    f"{text[position]!r} at {position}"
                )
            tokens.append(match.group("token"))
            position = match.end()
        return tokens

    def peek(self) -> Optional[str]:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise UnitError(f"expression {self.source!r} ends unexpectedly")
        self.index += 1
        return token

    # -- grammar ------------------------------------------------------

    def parse(self) -> Unit:
        unit = self.sum()
        if self.peek() is not None:
            raise UnitError(
                f"expression {self.source!r}: trailing {self.peek()!r}"
            )
        return unit

    def sum(self) -> Unit:
        unit = self.product()
        while self.peek() in ("+", "-"):
            operator = self.take()
            right = self.product()
            # Addition is where dimensional errors surface. Km + S is fine;
            # Km + kcat is a model that will integrate and mean nothing.
            if not unit.same_dimensions(right):
                self.findings.append(
                    UnitFinding(
                        where=self.source,
                        detail=(
                            f"{unit.describe()} {operator} {right.describe()}: "
                            f"terms with different dimensions cannot be added. "
                            f"This expression will integrate and the result "
                            f"will not mean anything."
                        ),
                    )
                )
            elif not unit.same_scale(right):
                under_exponent = unit.symbolic_scale_ratio(right)
                if under_exponent is not None:
                    symbol, ratio = under_exponent
                    detail = (
                        f"{unit.describe()} {operator} {right.describe()}: the "
                        f"bases raised to {symbol} differ in scale by a factor "
                        f"of {ratio:.3g}, so these terms differ by "
                        f"{ratio:.3g}^{symbol}. The exponent is not known "
                        f"here, so the size of the error is not either -- but "
                        f"that it IS an error is known."
                    )
                else:
                    ratio = max(unit.scale, right.scale) / min(unit.scale, right.scale)
                    detail = (
                        f"{unit.describe()} {operator} {right.describe()}: "
                        f"same dimensions, different scale -- these differ by "
                        f"a factor of about {ratio:.3g}. Terrium does not "
                        f"rescale, because the factor is not always "
                        f"dimensionless."
                    )
                self.findings.append(
                    UnitFinding(where=self.source, detail=detail, severity="scale")
                )
        return unit

    def product(self) -> Unit:
        unit = self.power()
        while self.peek() in ("*", "/"):
            operator = self.take()
            right = self.power()
            unit = unit * right if operator == "*" else unit / right
        return unit

    def power(self) -> Unit:
        unit = self.unary()
        while self.peek() in ("^", "**"):
            self.take()
            exponent_unit, exponent_value, exponent_symbol = self.exponent()
            if not exponent_unit.dimensionless:
                self.findings.append(
                    UnitFinding(
                        where=self.source,
                        detail=(
                            f"raised to a power carrying units "
                            f"({exponent_unit.describe()}). An exponent must "
                            f"be dimensionless; a Hill coefficient is, a "
                            f"concentration is not."
                        ),
                    )
                )
                return DIMENSIONLESS
            if exponent_value is None:
                # A symbolic exponent -- a Hill coefficient. The dimensions
                # move under that symbol's name rather than being given up
                # on, so `K^n + X^n` can be confirmed when K and X agree and
                # `K^n / (K^n + X^n)` cancels to dimensionless for every n.
                if exponent_symbol is None:
                    self.findings.append(
                        UnitFinding(
                            where=self.source,
                            detail=(
                                "raised to an expression rather than to a "
                                "number or a single symbol. Nothing here can "
                                "decide what that does to the dimensions, and "
                                "a checker that assumed would be worse than "
                                "one that says so."
                            ),
                            severity="scale",
                        )
                    )
                    return DIMENSIONLESS
                unit = unit.symbolic_power(exponent_symbol)
                continue
            unit = unit.power(exponent_value)
        return unit

    def exponent(self) -> Tuple[Unit, Optional[Fraction], Optional[str]]:
        """(unit, numeric value, symbol name) for whatever follows `^`.

        The symbol name is what makes a Hill term checkable: `K^n` and `X^n`
        are commensurable because the SAME n raises both, and that fact is
        only available here, where the token is still visible.
        """
        negative = False
        while self.peek() == "-":
            self.take()
            negative = not negative
        token = self.peek()
        if token is not None and re.fullmatch(r"\d+\.?\d*", token):
            self.take()
            value = Fraction(token)
            return DIMENSIONLESS, (-value if negative else value), None
        if (
            token is not None
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token)
            and not negative
        ):
            # A bare symbol, which is the Hill case. Consumed here rather
            # than through `unary()` so its NAME survives; `unary` returns a
            # unit and the name is exactly what is needed.
            self.take()
            unit = self.environment.get(token)
            if unit is None:
                raise UnitError(
                    f"expression {self.source!r}: no unit declared for "
                    f"exponent {token!r}"
                )
            return unit, None, token
        unit = self.unary()
        return unit, None, None

    def unary(self) -> Unit:
        if self.peek() in ("+", "-"):
            self.take()
            return self.unary()
        return self.atom()

    def atom(self) -> Unit:
        token = self.take()
        if token == "(":
            unit = self.sum()
            if self.take() != ")":
                raise UnitError(
                    f"expression {self.source!r}: unbalanced parenthesis"
                )
            return unit
        if re.fullmatch(r"\d+\.?\d*(?:[eE][-+]?\d+)?", token):
            return Unit({}, float(token), token)
        if token in self.environment:
            return self.environment[token]
        raise UnitError(
            f"expression {self.source!r}: no unit declared for {token!r}. "
            f"Every symbol in a rate law must have one, or the check would "
            f"pass by not looking."
        )


def check_rate_law(
    rate_law: str,
    environment: Mapping[str, Unit],
    *,
    expected: Unit = REACTION_RATE,
    label: str = "",
) -> Tuple[Unit, Tuple[UnitFinding, ...]]:
    """Compute a rate law's units and compare them to what a rate must be.

    Returns `(unit, findings)`. Findings are not raised: a composition may
    contain several and a caller wants all of them, in the same spirit as
    `unsourced_quantities` naming every unsourced quantity rather than the
    first.
    """
    parser = _ExpressionParser(rate_law, environment)
    unit = parser.parse()
    findings = list(parser.findings)

    if not unit.same_dimensions(expected):
        findings.append(
            UnitFinding(
                where=label or rate_law,
                detail=(
                    f"this rate law evaluates to {unit.describe()}, and a "
                    f"reaction rate is {expected.describe()} -- an amount per "
                    f"volume per time. A law with the wrong dimensions "
                    f"integrates perfectly well and the trajectory is wrong "
                    f"by whatever the mistake introduced."
                ),
            )
        )
    elif not unit.same_scale(expected):
        ratio = unit.scale / expected.scale
        findings.append(
            UnitFinding(
                where=label or rate_law,
                detail=(
                    f"this rate law evaluates to {unit.describe()}, whose "
                    f"dimensions are right and whose scale is off by a factor "
                    f"of {ratio:.3g}. Every number on the resulting axis is "
                    f"wrong by that factor, and nothing about the shape of "
                    f"the curve would show it."
                ),
                severity="scale",
            )
        )
    return unit, tuple(findings)


__all__ = [
    "Unit", "UnitError", "UnitFinding",
    "parse_unit", "check_rate_law", "rate_unit_for",
    "DIMENSIONLESS", "CONCENTRATION", "PER_TIME", "REACTION_RATE",
    "PREFIXES", "TIME_UNITS", "BASES", "SCALE_TOLERANCE",
]
