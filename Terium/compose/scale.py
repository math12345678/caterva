"""What the numbers in a model imply about the physical thing it describes.

THE QUESTION THIS ANSWERS
-------------------------
A composed model is a set of rate laws and a set of numbers. Nothing in
`analysis.py`, `simulate.py` or `sensitivity.py` ever asks whether those
numbers describe something that could exist. They will happily integrate a
model whose enzyme turns over faster than a molecule can diffuse to it, whose
"concentration" is a third of a molecule in a bacterium, or whose binding
constant is tighter than any measured antibody.

Every one of those is a real error that a student makes, a placeholder
produces, or a unit slip introduces -- and every one of them is invisible to a
dimensional check, because the dimensions are perfectly correct. mM and µM are
dimensionally identical and differ by a thousand; `units.py` catches the
mismatch between two laws, and nothing catches a single number that is simply
not physical.

WHAT A LIMIT IS HERE, AND WHAT IT IS NOT
-----------------------------------------
Each check compares a number against a PHYSICAL BOUND or an EMPIRICAL RANGE,
and the two are treated differently because they mean different things.

A physical bound is a fact about the universe. The diffusion-limited
association rate is set by how fast two molecules can find each other in
water; nothing binds faster, and a model that says otherwise is wrong rather
than unusual. Exceeding one of these is an ERROR.

An empirical range is a summary of what has been observed. Enzyme turnover
numbers cluster over a few decades and the extremes are famous exactly because
they are extreme. Falling outside one of these is a QUESTION -- carbonic
anhydrase really does run at about a million per second, and a model of it
should not be told it is broken.

Conflating the two would make this module useless in the way ADR 0028
describes: a check that fires on everything unusual stops being read, and the
one time it fires on something genuinely impossible nobody looks.

WHY THE BOUNDS ARE ORDER-OF-MAGNITUDE AND SAY SO
-------------------------------------------------
Every constant here is stated to one significant figure with its reasoning,
because that is the precision the underlying physics is being used at. The
diffusion limit depends on molecular radii, temperature and viscosity, and
quoting it as 1e9 rather than 6.7e8 M/s is not sloppiness -- it is the honest
resolution of a bound used to ask "is this off by a factor of a thousand".

Nothing here is a measurement of anything. These are bounds and ranges used to
ask a question, and the module reports which one it used every time it speaks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Physical bounds -- facts about the universe. Exceeding one is an error.
# ---------------------------------------------------------------------------

#: Diffusion-limited second-order association rate, per molar per second.
#:
#: The Smoluchowski limit: two molecules cannot react faster than they can
#: find each other. For proteins in water at room temperature this lands
#: around 1e9-1e10 /M/s depending on molecular size and on whether
#: electrostatic steering helps. Stated as 1e10 -- the generous end -- so
#: that flagging one means the number is clear of every reasonable version
#: of the bound, not merely of a strict reading of it.
#:
#: Barnase-barstar, one of the fastest measured associations, sits near
#: 1e9 /M/s with electrostatic steering. A model above 1e10 is not fast; it
#: is wrong.
DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND = 1e10

#: Loosest binding worth calling binding, as a dissociation constant in M.
#:
#: Above about 1 M the "complex" is not a complex: the partners are at
#: concentrations no cell reaches, and the interaction is weaker than the
#: nonspecific association of any two molecules in solution. A Kd above this
#: usually means a unit slip rather than a weak binder.
WEAKEST_MEANINGFUL_KD_MOLAR = 1.0

#: Tightest dissociation constant ever measured, in M, to an order of
#: magnitude. Avidin-biotin is the textbook extreme at roughly 1e-15 M.
#: Anything tighter in a model is a unit error, not a discovery.
TIGHTEST_MEASURED_KD_MOLAR = 1e-16

#: One molecule in an E. coli cell, in molar.
#:
#: A coli cell is about 1e-15 L, so one molecule is 1/(6.022e23 * 1e-15) M,
#: near 1.7e-9 M. Concentrations far below this describe a fraction of a
#: molecule, which is not a small amount of something -- it is a statement
#: that the deterministic model has stopped applying and a stochastic one is
#: needed. See `compose/stochastic.py`.
ONE_MOLECULE_PER_BACTERIUM_MOLAR = 1.7e-9

#: Total intracellular protein concentration, in molar, order of magnitude.
#: About 200-300 mg/mL of protein at a mean mass near 40 kDa gives a few
#: millimolar of protein in total. A SINGLE species above this is claiming
#: more of itself than the cell contains of all protein together.
TOTAL_CELLULAR_PROTEIN_MOLAR = 5e-3

# ---------------------------------------------------------------------------
# Empirical ranges -- summaries of what has been observed. Outside is a
# question, not an error.
# ---------------------------------------------------------------------------

#: Turnover numbers of characterised enzymes, per second, as a range that
#: covers essentially all of BRENDA. The low end is proteins that turn over
#: once a minute or slower; the high end is carbonic anhydrase near 1e6/s.
#: Outside this is unusual and worth a question, not an error -- carbonic
#: anhydrase is real.
TYPICAL_KCAT_RANGE_PER_SECOND = (1e-3, 1e7)

#: Michaelis constants of characterised enzymes, in molar. Most sit between
#: micromolar and low millimolar; the range here is deliberately wider than
#: "most" so that being outside it means something.
TYPICAL_KM_RANGE_MOLAR = (1e-9, 1e-1)

#: First-order rate constants that appear in cell-biological models, per
#: second, spanning a protein degraded over days to a phosphorylation
#: reversed in milliseconds.
TYPICAL_FIRST_ORDER_RANGE_PER_SECOND = (1e-7, 1e4)

#: Hill coefficients that a real oligomer can produce. The coefficient
#: cannot exceed the number of binding sites, and above about 10 no natural
#: system is known -- haemoglobin, the textbook cooperative protein, sits
#: near 3 with four sites.
#:
#: A Hill coefficient below 1 is real and means NEGATIVE cooperativity, so
#: the low end is not an error either; only a non-positive one is.
PLAUSIBLE_HILL_RANGE = (0.1, 10.0)

#: Severities, ordered.
ERROR = "error"        # violates a physical bound
QUESTION = "question"  # outside an empirical range
NOTE = "note"          # worth knowing, implies nothing is wrong

SEVERITIES = (ERROR, QUESTION, NOTE)


class ScaleError(ValueError):
    """A scale check could not be performed, as distinct from failing."""


@dataclass(frozen=True)
class Finding:
    """One number, and what it implies about the thing being described."""

    parameter: str
    value: float
    unit: str
    severity: str
    #: What was compared against, named. A finding that does not say what
    #: bound it used cannot be argued with, and every bound here is arguable.
    against: str
    detail: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ScaleError(
                f"severity {self.severity!r} is not one of {SEVERITIES}. The "
                f"difference between a physical impossibility and an unusual "
                f"value is the whole point of this module, so an unknown "
                f"severity has no defined meaning."
            )

    def describe(self) -> str:
        return (
            f"[{self.severity}] {self.parameter} = {self.value:g} "
            f"{self.unit}: {self.detail} (against {self.against})"
        )


@dataclass(frozen=True)
class ScaleReport:
    findings: Tuple[Finding, ...]
    #: Parameters that were not checked, with the reason. Reported because
    #: "no findings" must not be confused with "nothing was checked" -- a
    #: parameter whose unit this module does not recognise is unexamined,
    #: and silence about it would read as approval.
    unchecked: Mapping[str, str] = field(default_factory=dict)
    #: Names this module actually compared against a bound. The other half
    #: of the distinction `unchecked` was added for, and the half that was
    #: missing: `unchecked` records what was SKIPPED, so a report with
    #: neither findings nor skips is silent about whether it examined
    #: twelve parameters and found nothing wrong, or examined none at all.
    #:
    #: Those are the two most different states this module can be in, and
    #: until this field existed they printed identically. A composed
    #: three-tier cascade -- twelve parameters, every unit recognised,
    #: every value plausible -- returned `ScaleReport(findings=(),
    #: unchecked={})`, which is byte-for-byte what a `check` over an empty
    #: network returns.
    checked: Tuple[str, ...] = ()

    @property
    def examined_nothing(self) -> bool:
        """Nothing reached a bound, for any reason.

        Ask this BEFORE `physically_possible`, which is also True here: a
        report over nothing breaks no law. A clean verdict over an empty
        examination is the most misleading output this module can produce,
        and it is the one a caller is least likely to suspect.
        """
        return not self.checked and not self.unchecked

    @property
    def coverage(self) -> str:
        """One line a caller can print instead of inferring the above."""
        if self.examined_nothing:
            return "nothing was examined"
        if not self.unchecked:
            return f"{len(self.checked)} examined, none skipped"
        return (
            f"{len(self.checked)} examined, {len(self.unchecked)} skipped "
            "for want of a recognised unit"
        )

    @property
    def errors(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == ERROR)

    @property
    def questions(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == QUESTION)

    @property
    def physically_possible(self) -> bool:
        """No number violates a physical bound.

        Deliberately NOT called `valid`. A model can be physically possible
        and biologically absurd, and this says only that nothing in it
        breaks a law.

        It also says nothing about COVERAGE. A report that examined no
        parameter at all is physically possible, vacuously -- so ask
        `examined_nothing` first. That is not a hypothetical: before
        `checked` existed, a twelve-parameter cascade and an empty network
        produced the same clean report.
        """
        return not self.errors

    def summary(self) -> str:
        lines = []
        if self.examined_nothing:
            # The clean sentence below would be true and worthless here.
            # Saying "every checked number is fine" when none were checked
            # is the sentence a reader is least equipped to doubt.
            lines.append(
                "NOTHING WAS EXAMINED. No parameter carried a unit this "
                "module recognises, so there is no clean bill of health "
                "here -- only an absence of examination."
            )
        elif not self.findings:
            lines.append(
                f"All {len(self.checked)} of the numbers examined are "
                f"physically possible and within the ranges these constants "
                f"describe."
            )
        else:
            if self.errors:
                lines.append(
                    f"{len(self.errors)} number(s) violate a physical bound "
                    f"-- these are errors rather than unusual values:"
                )
                for finding in self.errors:
                    lines.append("  - " + finding.describe())
            if self.questions:
                lines.append(
                    f"{len(self.questions)} number(s) sit outside the range "
                    f"of what has been measured. That is a question, not a "
                    f"fault: carbonic anhydrase really does turn over a "
                    f"million times a second."
                )
                for finding in self.questions:
                    lines.append("  - " + finding.describe())

        if self.unchecked:
            lines.append(
                f"{len(self.unchecked)} parameter(s) were NOT checked: "
                + "; ".join(f"{k} ({v})" for k, v in sorted(self.unchecked.items()))
                + ". Silence about those is absence of examination, not "
                "approval."
            )

        lines.append(
            "Every bound above is stated to one significant figure, which is "
            "the resolution these questions are asked at. Nothing here is a "
            "measurement; they are bounds and ranges used to ask whether a "
            "number is off by orders of magnitude."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit handling
# ---------------------------------------------------------------------------

#: Multipliers converting a stated concentration unit to molar. Only the
#: units the motif library actually uses are here; an unrecognised unit
#: makes the parameter unchecked rather than assumed.
_TO_MOLAR = {
    "M": 1.0,
    "mM": 1e-3,
    "uM": 1e-6,
    "µM": 1e-6,
    "nM": 1e-9,
    "pM": 1e-12,
}

#: Multipliers converting a stated time unit to per-second.
_TO_PER_SECOND = {
    "1/s": 1.0,
    "/s": 1.0,
    "s^-1": 1.0,
    "1/min": 1.0 / 60.0,
    "1/h": 1.0 / 3600.0,
    "1/hr": 1.0 / 3600.0,
}


def _as_molar(value: float, unit: str) -> Optional[float]:
    factor = _TO_MOLAR.get(unit.strip())
    return None if factor is None else value * factor


def _as_per_second(value: float, unit: str) -> Optional[float]:
    factor = _TO_PER_SECOND.get(unit.strip())
    return None if factor is None else value * factor


#: Second-order association units, as a (concentration prefix, remainder)
#: split. `1/(mM*s)` is the form the motif library actually emits, and the
#: original matcher looked only for the unprefixed molar spellings -- so
#: the one hard physical law in this module never ran on any model the
#: composer builds. See `_as_per_molar_per_second`.
_SECOND_ORDER_SHAPES = (
    "/{c}/s", "/{c}s", "{c}^-1s^-1", "{c}^-1*s^-1",
    "1/({c}*s)", "1/({c}s)", "1/{c}/s",
)


def _second_order_concentration(unit: str) -> Optional[str]:
    """The concentration unit in a second-order rate, or None.

    `1/(mM*s)` -> "mM". Returned rather than a bool because the CALLER
    has to convert: a limit stated per molar cannot be compared against a
    value stated per millimolar, and those differ by a thousand -- which
    is the exact mistake this module exists to catch, made by this module.
    """
    cleaned = unit.replace(" ", "")
    for concentration in _TO_MOLAR:
        for shape in _SECOND_ORDER_SHAPES:
            if shape.format(c=concentration) in cleaned:
                return concentration
    return None


def _as_per_molar_per_second(value: float, unit: str) -> Optional[float]:
    """A second-order rate in /M/s, whatever concentration unit it used.

    A rate per MILLIMOLAR is a thousand times larger per MOLAR: 1 /(mM*s)
    is 1e3 /(M*s), because the same rate is being divided by a
    concentration a thousand times smaller. Getting this backwards turns
    the diffusion-limit check into one that passes values a thousandfold
    over it.
    """
    concentration = _second_order_concentration(unit)
    if concentration is None:
        return None
    # value / [concentration] / s, expressed per molar: divide by the
    # factor that converts that concentration TO molar.
    return value / _TO_MOLAR[concentration]


def _is_second_order(unit: str) -> bool:
    return _second_order_concentration(unit) is not None


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def _check_concentration(name: str, value: float, unit: str) -> List[Finding]:
    molar = _as_molar(value, unit)
    if molar is None:
        return []
    findings: List[Finding] = []

    if molar > TOTAL_CELLULAR_PROTEIN_MOLAR:
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=ERROR,
            against=f"total cellular protein, ~{TOTAL_CELLULAR_PROTEIN_MOLAR:g} M",
            detail=(
                "a single species at more than the cell's entire protein "
                "content. Almost always a unit slip -- mM read as M is "
                "exactly this factor"
            ),
        ))
    elif 0.0 < molar < ONE_MOLECULE_PER_BACTERIUM_MOLAR:
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=QUESTION,
            against=(
                f"one molecule per bacterium, "
                f"~{ONE_MOLECULE_PER_BACTERIUM_MOLAR:g} M"
            ),
            detail=(
                "below one copy per bacterial cell. Not impossible -- a "
                "eukaryotic cell is a thousand times larger -- but if this "
                "is a bacterium the deterministic model has stopped "
                "applying and a stochastic one is needed"
            ),
        ))
    return findings


def _check_affinity(name: str, value: float, unit: str) -> List[Finding]:
    molar = _as_molar(value, unit)
    if molar is None or molar <= 0.0:
        return []
    findings: List[Finding] = []

    if molar < TIGHTEST_MEASURED_KD_MOLAR:
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=ERROR,
            against=f"the tightest measured Kd, ~{TIGHTEST_MEASURED_KD_MOLAR:g} M",
            detail=(
                "tighter than avidin-biotin, the textbook extreme. This is "
                "a unit error rather than a discovery"
            ),
        ))
    elif molar > WEAKEST_MEANINGFUL_KD_MOLAR:
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=ERROR,
            against=f"the weakest meaningful Kd, {WEAKEST_MEANINGFUL_KD_MOLAR:g} M",
            detail=(
                "weaker than the nonspecific association of any two "
                "molecules in solution, and at a concentration no cell "
                "reaches. This is not a weak binder, it is a unit slip"
            ),
        ))
    else:
        low, high = TYPICAL_KM_RANGE_MOLAR
        if not (low <= molar <= high):
            findings.append(Finding(
                parameter=name, value=value, unit=unit, severity=QUESTION,
                against=f"characterised Km values, {low:g}-{high:g} M",
                detail=(
                    "outside the range most measured Michaelis constants "
                    "fall in. Real enzymes sit outside it, so this is worth "
                    "checking rather than fixing"
                ),
            ))
    return findings


def _check_rate(name: str, value: float, unit: str) -> List[Finding]:
    findings: List[Finding] = []

    per_molar_per_second = _as_per_molar_per_second(value, unit)
    if per_molar_per_second is not None:
        if per_molar_per_second > DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND:
            findings.append(Finding(
                parameter=name, value=value, unit=unit, severity=ERROR,
                against=(
                    f"the diffusion limit, "
                    f"~{DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND:g} /M/s"
                ),
                detail=(
                    f"{per_molar_per_second:g} /M/s -- faster than two "
                    "molecules in water can find each other. Nothing "
                    "associates this fast; the Smoluchowski limit is a "
                    "property of diffusion, not of the protein"
                ),
            ))
        return findings

    per_second = _as_per_second(value, unit)
    if per_second is None or per_second <= 0.0:
        return findings

    low, high = TYPICAL_FIRST_ORDER_RANGE_PER_SECOND
    kcat_low, kcat_high = TYPICAL_KCAT_RANGE_PER_SECOND
    if per_second > max(high, kcat_high):
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=QUESTION,
            against=f"characterised turnover numbers, up to ~{kcat_high:g} /s",
            detail=(
                "faster than carbonic anhydrase, which is the fastest "
                "enzyme anyone has measured. Possible, and worth being "
                "sure about"
            ),
        ))
    elif per_second < min(low, kcat_low):
        findings.append(Finding(
            parameter=name, value=value, unit=unit, severity=QUESTION,
            against=f"rates that appear in cell-biological models, from ~{low:g} /s",
            detail=(
                "slower than a protein degraded over days. Real for "
                "geological processes and for some structural proteins; "
                "unusual inside a cell"
            ),
        ))
    return findings


def _check_exponent(name: str, value: float) -> List[Finding]:
    low, high = PLAUSIBLE_HILL_RANGE
    if value <= 0.0:
        return [Finding(
            parameter=name, value=value, unit="dimensionless", severity=ERROR,
            against="a Hill coefficient, which is positive by construction",
            detail=(
                "a non-positive Hill coefficient inverts the rate law's "
                "meaning rather than describing weak cooperativity. "
                "Negative cooperativity is a coefficient BELOW one, not "
                "below zero"
            ),
        )]
    if value > high:
        return [Finding(
            parameter=name, value=value, unit="dimensionless", severity=QUESTION,
            against=f"known cooperative systems, up to ~{high:g}",
            detail=(
                "higher than any natural system known. The coefficient "
                "cannot exceed the number of binding sites, and "
                "haemoglobin -- the textbook cooperative protein -- sits "
                "near 3 with four sites"
            ),
        )]
    if value < low:
        return [Finding(
            parameter=name, value=value, unit="dimensionless", severity=QUESTION,
            against=f"known cooperative systems, from ~{low:g}",
            detail=(
                "far below one, which would be extreme negative "
                "cooperativity. Values below one are real and meaningful; "
                "this one is unusually low"
            ),
        )]
    return []


#: The concentration unit the motif library writes its species amounts in.
#:
#: STATED because it is an assumption this module cannot verify. The core
#: `Species` type carries an initial amount and no unit, so a species'
#: number is dimensionless as far as the IR is concerned, and every motif in
#: `library.py` declares its concentration parameters in mM. If a motif ever
#: declares one in µM this constant becomes wrong by a thousand, which is
#: precisely the class of error this module exists to catch -- so it is
#: named here rather than written inline, and `species_unit` overrides it.
LIBRARY_CONCENTRATION_UNIT = "mM"


def units_from_model(model: Any) -> Dict[str, str]:
    """Parameter units, recovered from the motifs that declared them.

    WHY THIS IS NEEDED AT ALL, WHICH IS A FINDING IN ITSELF. Terrium's
    `core.network.Parameter` has an id and a value and NO UNIT. The network
    IR carries bare numbers, and the unit exists only on the
    `MotifParameter` the builder read to produce it -- so it is dropped at
    the moment the network is built.

    That is why `check` on a bare network reports everything unchecked: it
    is not being cautious, it genuinely has nothing to check against.

    NOW A SHIM OVER `compose/quantities.py`, WHICH KEEPS ALL OF IT
    --------------------------------------------------------------
    This function recovered ONE of the five things the builder dropped.
    `quantities.QuantityTable` recovers the unit, the kind, the motif, the
    instance and the BRENDA table together, and covers species initials as
    well as parameters -- which matters because a concentration in a
    composed model is a species initial and this mapping never held one.

    The signature is unchanged and so is the behaviour, including the
    tolerance: a model with no composition behind it yields an empty
    mapping rather than an exception, which `check` renders as "everything
    unchecked" -- the honest report for a network that has lost this.
    `QuantityTable.from_model` refuses that case loudly instead, which is
    right for new callers and would be a behaviour change here.
    """
    composition = getattr(
        getattr(model, "recognition", None), "composition", None
    )
    if composition is None or not getattr(composition, "instances", ()):
        return {}

    try:
        from .quantities import QuantityTable
    except ImportError:  # pragma: no cover - flat import
        from quantities import QuantityTable  # type: ignore[no-redef]

    return QuantityTable.from_composition(
        composition, network=getattr(model, "network", None)
    ).parameter_units()


def check(
    network: Any,
    *,
    units: Optional[Mapping[str, str]] = None,
    species_unit: str = LIBRARY_CONCENTRATION_UNIT,
) -> ScaleReport:
    """Every parameter, against the bounds and ranges above.

    The unit string decides which check applies, which means a parameter
    whose unit this module does not recognise is UNCHECKED rather than
    assumed to be a concentration. That distinction is the difference
    between a report that means something and one that quietly examined
    half of what it claimed to.

    PRECEDENCE: the parameter's OWN unit wins, and `units` fills gaps.
    `core.network.Parameter` now carries a unit, populated by the builder
    from the motif that declared it, so a composed network arrives already
    describing itself. A caller-supplied mapping cannot override that --
    the motif is the authority on what its own constant means, and letting
    an argument silently reinterpret a declared mM as something else would
    be a worse failure than the gap this replaced.

    `units` therefore exists for networks built OUTSIDE the composer, which
    carry no units at all. Without either, every parameter is reported
    unchecked -- honest, and nearly useless.
    """
    findings: List[Finding] = []
    unchecked: Dict[str, str] = {}
    checked: List[str] = []
    supplied = dict(units or {})

    for parameter in network.parameters:
        name = parameter.id
        value = float(parameter.value)
        unit = str(
            getattr(parameter, "unit", None) or supplied.get(name, "") or ""
        )

        if not math.isfinite(value):
            # Recorded as EXAMINED: finding it non-finite is the
            # examination. Without this the report says "nothing was
            # examined" while carrying the error it just produced.
            checked.append(name)
            findings.append(Finding(
                parameter=name, value=value, unit=unit or "unknown",
                severity=ERROR,
                against="the finite numbers",
                detail="not a finite value, so nothing downstream can use it",
            ))
            continue

        if value < 0.0 and unit.strip() != "dimensionless":
            # NEEDS NO UNIT, WHICH IS WHY IT RUNS BEFORE THE DISPATCH.
            #
            # `dimensionless` is excluded because `_check_exponent` already
            # refuses a non-positive Hill coefficient AND says something
            # sharper about it -- a Hill coefficient below one is
            # NEGATIVE cooperativity and a real thing, so the interesting
            # boundary there is one rather than zero. Intercepting it here
            # would replace a specific diagnosis with a generic one, which
            # is a loss even though both are errors.
            #
            # Every quantity this module sees is a rate constant, a
            # concentration, an affinity or an exponent, and none of them
            # is negative: a rate constant is a proportionality between
            # non-negative amounts, a concentration is molecules per
            # volume, and an affinity is a concentration. Zero is allowed
            # and meaningful -- `perturbation.catalytically_dead` produces
            # exactly a zero rate, and an absent species is zero.
            #
            # `_check_exponent` already refused a non-positive Hill
            # coefficient. This is that same bound, applied to the other
            # three kinds, which were letting negatives through silently:
            # each check compared against an UPPER limit only, and
            # `_check_rate` returned early on a non-positive value. So
            # `physically_possible` answered yes about a negative
            # concentration.
            #
            # Placing it before the unit dispatch also means it reaches
            # parameters whose unit has no converter -- `mM/s` among them
            # -- which are otherwise reported unchecked entirely.
            checked.append(name)
            findings.append(Finding(
                parameter=name, value=value, unit=unit or "unknown",
                severity=ERROR,
                against="zero, below which none of these quantities exists",
                detail=(
                    "negative. A rate constant, a concentration and an "
                    "affinity are all non-negative by what they are; zero "
                    "is allowed and means absent or inactive. A negative "
                    "one is a sign error, and it integrates without "
                    "complaint into a trajectory that runs backwards"
                ),
            ))
            continue

        if not unit:
            unchecked[name] = (
                "no unit is recorded for it -- core.network.Parameter carries "
                "none, and none was supplied. See units_from_model"
            )
            continue

        if unit == "dimensionless":
            checked.append(name)
            findings += _check_exponent(name, value)
        elif _is_second_order(unit) or _as_per_second(value, unit) is not None:
            checked.append(name)
            findings += _check_rate(name, value, unit)
        elif _as_molar(value, unit) is not None:
            # Affinities and concentrations share a unit, so both apply: an
            # affinity check on a concentration would misread a legitimate
            # 1 M buffer, and a concentration check on a Km would miss a
            # unit slip. The NAME is the only signal available for which is
            # which, and guessing from it would be worse than running both
            # -- so both run, and each says what it compared against.
            checked.append(name)
            lowered = name.lower()
            if any(k in lowered for k in ("_km", "_kd", "_ki", "_ksi", "_k")):
                findings += _check_affinity(name, value, unit)
            else:
                findings += _check_concentration(name, value, unit)
        else:
            unchecked[name] = f"unit {unit!r} is not one this module recognises"

    for species in getattr(network, "species", ()):
        initial = float(getattr(species, "initial", 0.0))
        if initial > 0.0:
            checked.append(species.id)
            findings += _check_concentration(species.id, initial, species_unit)

    return ScaleReport(
        findings=tuple(findings),
        unchecked=unchecked,
        checked=tuple(checked),
    )


def check_model(model: Any, **kwargs: Any) -> ScaleReport:
    """`check`, with the units the model's own motifs declared.

    This is the entry point worth using. `check` on a bare network cannot
    know what its numbers mean, because the IR does not record it.
    """
    kwargs.setdefault("units", units_from_model(model))
    return check(model.network, **kwargs)


__all__ = [
    "ERROR", "QUESTION", "NOTE", "SEVERITIES",
    "Finding", "ScaleError", "ScaleReport", "check", "check_model",
    "units_from_model", "LIBRARY_CONCENTRATION_UNIT",
    "DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND",
    "WEAKEST_MEANINGFUL_KD_MOLAR", "TIGHTEST_MEASURED_KD_MOLAR",
    "ONE_MOLECULE_PER_BACTERIUM_MOLAR", "TOTAL_CELLULAR_PROTEIN_MOLAR",
    "TYPICAL_KCAT_RANGE_PER_SECOND", "TYPICAL_KM_RANGE_MOLAR",
    "TYPICAL_FIRST_ORDER_RANGE_PER_SECOND", "PLAUSIBLE_HILL_RANGE",
]
