"""Every number a composed model contains, with what it means and where from.

THE GAP THIS CLOSES
-------------------
`core.network.Parameter` carries an id, a value and -- since this module
argued for it -- a unit. It does not carry the other four things the builder
drops, and by the time a model is a `ReactionNetwork` its numbers are
otherwise bare. Three separate modules discovered the same hole
independently:

  * `scale.py` cannot judge a number without its unit, so on a bare network
    it reports every parameter unchecked -- honest, and nearly useless.
  * `perturbation.py` cannot tell a rate constant from an affinity, so
    `catalytically_dead` had to refuse rather than risk zeroing a Km, which
    describes a different experiment entirely.
  * `robustness.py` could not vary concentrations, because a concentration
    in a composed model is a SPECIES INITIAL and not a parameter at all --
    so a request to vary one silently varied nothing.

`scale.units_from_model` was the workaround: recover the unit from the
motifs the builder read. It works, and it recovers one field out of five.

WHY A SIDE TABLE *AND* A FIELD ON `Parameter`
----------------------------------------------
This module first argued that `unit` should NOT go on `core.network.
Parameter`: adding it closes a fifth of the gap and makes the other four
fifths look closed, which is worse than leaving the hole plainly open.

The hazard was right and the conclusion was wrong. The remedy for "a
partial fix looks total" is to SAY SO at the partial fix, which
`core.network.Parameter`'s docstring now does -- it states what it does not
carry and sends a reader here for the rest.

And there is a real line between the two, which is why this is a split and
not a compromise:

    the IR carries what you need to READ a number     -- the unit
    this table carries where the number CAME FROM     -- kind, motif,
                                                        instance, table

`0.1` cannot be interpreted at all without its unit; that is a property of
the value, and every serialisation format worth the name puts it there
(SBML does). Kind, motif and source table are provenance, they are
meaningless for a network built outside the composer, and a field on the
shared IR that is empty for every catalogue model would be a field that
teaches readers to ignore it.

So the IR carries the unit, and this carries everything else the
`MotifParameter` knew, keyed by the same id.

WHY SPECIES INITIALS ARE IN THE SAME TABLE
-------------------------------------------
Because a concentration is one. `builder.py` writes kcat and the enzyme
separately (ADR 0013), which is exactly what makes a composed model more
resolvable than a catalogue one -- and the consequence is that every
concentration in a composed model lives on a `Species`, not a `Parameter`.

A table of "parameters" would therefore have a blind spot shaped precisely
like the bug `robustness.py` had: it offered to vary concentrations, looked
for them among the parameters, found none, and varied nothing. The
partition that matters to a reader is resolvable-versus-chosen, and that
partition cuts across the IR's parameter/species split. So the table covers
both and records which side of the IR each id lives on.

KIND IS CARRIED, NEVER INFERRED FROM THE NAME
----------------------------------------------
A `kcat` and a `Km` are both plain floats with a unit each, and telling them
apart by looking for `_km` or `_kd` in the id works until somebody writes a
motif whose affinity is called `L` -- and `library_enzymology.mwc_allostery`
has exactly that. The motif already declared the kind. Carrying the
declaration is free; re-deriving it from a string is a guess that will be
right often enough to be trusted and wrong often enough to matter.

The kind also decides what may be asked for. `KIND_RATE_CONSTANT` and
`KIND_AFFINITY` are RESOLVABLE -- properties of a molecule that somebody
measured. `KIND_CONCENTRATION` and `KIND_EXPONENT` are CHOSEN -- how much
you put in the tube, and a modelling convention. A concentration is never
resolvable, no matter what it is called, and `Quantity.resolvable` is
derived from the kind rather than stored, so the two cannot drift apart.

WHAT A `table` FIELD IS AND IS NOT
-----------------------------------
It names the BRENDA table that would serve this quantity IF somebody went
and searched it. It is an address, not a source. The value sitting in
`Quantity.value` is the motif library's ILLUSTRATIVE placeholder until a
resolver replaces it, and nothing here attaches a citation to a number --
`table` says where to look, and `resolved` is not a field this type has.

CONVERSION REFUSES RATHER THAN GUESSES
---------------------------------------
`to_molar`, `to_per_second` and `dimension_of` read the unit with the same
parser `units.py` uses to check rate laws, so the two cannot disagree about
what `1/mM*s` means. An unrecognised unit raises, with what was read and
what to write instead. A converter that fell back to "assume molar" would
be the thousandfold error that `scale.py` exists to catch, introduced by the
module meant to prevent it.

An EMPTY unit is refused separately from an unreadable one, because they are
different facts: `dimensionless` is a declaration, `""` is a missing
declaration, and treating the second as the first is the original gap
wearing a value.

A NOTE ON THE NAME
------------------
`sensitivity.Quantity` is a different thing with the same word: a quantity
of INTEREST, a function OF the model that a derivative is taken of. This one
is a quantity the model CONTAINS. Both names are right in their own module
and neither is importable into the other without saying which it means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple,
)

try:
    from .motifs import (
        CHOSEN_KINDS, KIND_AFFINITY, KIND_CONCENTRATION, KIND_EXPONENT,
        KIND_RATE_CONSTANT, RESOLVABLE_KINDS,
    )
    from .units import UnitError, parse_unit
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        CHOSEN_KINDS, KIND_AFFINITY, KIND_CONCENTRATION, KIND_EXPONENT,
        KIND_RATE_CONSTANT, RESOLVABLE_KINDS,
    )
    from units import UnitError, parse_unit  # type: ignore[no-redef]


KNOWN_KINDS = frozenset(RESOLVABLE_KINDS | CHOSEN_KINDS)


class QuantityError(ValueError):
    """A quantity could not be read, converted, or located.

    One exception type for the whole module, because every failure here is
    the same failure in a different place: something about a number was not
    recorded, and guessing it would produce an answer indistinguishable from
    a correct one.
    """


# ---------------------------------------------------------------------------
# Where in the IR a quantity lives
# ---------------------------------------------------------------------------

#: The number is a `core.network.Parameter`.
SOURCE_PARAMETER = "parameter"

#: The number is a `core.network.Species`' initial amount.
#:
#: A separate source rather than a kind, because it is a fact about the IR
#: and not about the biochemistry. Every quantity with this source is a
#: concentration; not every concentration has this source, since a motif may
#: declare one as a parameter.
SOURCE_SPECIES_INITIAL = "species_initial"

SOURCES = (SOURCE_PARAMETER, SOURCE_SPECIES_INITIAL)


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------
#
# Named for the five shapes a rate law can contain, because "concentration"
# is what a reader is deciding about and "{'M': 1}" is not. Anything else
# parseable gets its dimensions rendered rather than a name -- an honest
# description of something this module has no name for, which is different
# from a refusal.

DIMENSION_CONCENTRATION = "concentration"
DIMENSION_PER_TIME = "per time"
DIMENSION_PER_CONCENTRATION_PER_TIME = "per concentration per time"
DIMENSION_CONCENTRATION_PER_TIME = "concentration per time"
DIMENSION_DIMENSIONLESS = "dimensionless"

_NAMED_DIMENSIONS = {
    (): DIMENSION_DIMENSIONLESS,
    (("M", 1),): DIMENSION_CONCENTRATION,
    (("s", -1),): DIMENSION_PER_TIME,
    (("M", -1), ("s", -1)): DIMENSION_PER_CONCENTRATION_PER_TIME,
    (("M", 1), ("s", -1)): DIMENSION_CONCENTRATION_PER_TIME,
}


def _signature(unit: Any) -> Tuple[Tuple[str, Any], ...]:
    """The dimension vector, as a hashable key.

    Exponents are left as the `Fraction`s the parser produced rather than
    coerced to int. A half-power is a real thing a unit string can say, and
    rounding it away would make `M^1/2` compare equal to `M` -- a silent
    reinterpretation of the number, which is the failure mode this whole
    module is built against. `Fraction(1)` hashes and compares equal to `1`,
    so the named table below can still be written with plain integers.
    """
    return tuple(sorted(unit.dimensions.items()))


def _render(unit: Any) -> str:
    parts = [
        base if exponent == 1 else f"{base}^{exponent}"
        for base, exponent in sorted(unit.dimensions.items())
    ]
    return "*".join(parts) or DIMENSION_DIMENSIONLESS


def _read(unit: str, *, what: str = "this quantity") -> Any:
    """Parse a unit, or refuse with what is missing and what to write.

    An empty unit is refused BEFORE the parser sees it, because
    `parse_unit("")` returns dimensionless -- a reasonable reading for a
    unit checker and the wrong one here. "No unit was recorded" and "this
    number is a pure ratio" are opposite statements, and the whole reason
    this module exists is that the first was being read as though it were
    harmless.
    """
    text = (unit or "").strip()
    if not text:
        raise QuantityError(
            f"no unit is recorded for {what}, so nothing can be converted or "
            f"compared. An empty unit is NOT `dimensionless` -- the first "
            f"says the declaration is missing and the second says the number "
            f"is a pure ratio. If the quantity really is a ratio (a Hill "
            f"coefficient, an equilibrium constant), write 'dimensionless'; "
            f"otherwise the motif that declares it needs a unit."
        )
    try:
        return parse_unit(text)
    except UnitError as exc:
        raise QuantityError(
            f"cannot read the unit {text!r} of {what}: {exc}. It is left "
            f"uninterpreted rather than guessed at -- assuming molar for an "
            f"unrecognised unit is the thousandfold error compose/scale.py "
            f"exists to catch."
        ) from None


def dimension_of(unit: str) -> str:
    """What kind of thing a unit measures, by name where there is one.

    Returns one of the DIMENSION_* constants for the five shapes a rate law
    can contain, and a rendering of the dimension vector (`M^2`) for
    anything else that parses. Raises `QuantityError` for a unit that does
    not parse or is not there at all.

    NOT the kind. `mM` is a concentration dimensionally whether it holds a
    Km or the amount of enzyme in the tube, and which of those it is decides
    whether the literature may be asked for it. That comes from the motif --
    see `Quantity.kind` -- and this says only what the number measures.
    """
    parsed = _read(unit)
    named = _NAMED_DIMENSIONS.get(_signature(parsed))
    return named if named is not None else _render(parsed)


def to_molar(value: float, unit: str) -> float:
    """A concentration in the stated unit, as molar.

    Refuses anything that is not a concentration. mM and uM are
    dimensionally identical and differ by a thousand, so this conversion is
    the one place a silent default would produce a number that looks exactly
    like a correct one.
    """
    parsed = _read(unit)
    if _signature(parsed) != (("M", 1),):
        raise QuantityError(
            f"{unit!r} is {dimension_of(unit)}, not a concentration, so it "
            f"has no value in molar. to_per_second is the conversion for a "
            f"first-order rate; a second-order rate constant "
            f"(per concentration per time) has no single-unit conversion at "
            f"all and must be compared against the diffusion limit as it "
            f"stands -- see compose/scale.py."
        )
    return float(value) * parsed.scale


def to_per_second(value: float, unit: str) -> float:
    """A first-order rate in the stated unit, per second.

    Refuses a second-order rate constant (`1/(mM*s)`) as loudly as it
    refuses a concentration. Dividing one by sixty because it contained a
    time unit would turn a per-molar-per-second association constant into a
    number that reads as a turnover number, which is the confusion that made
    `perturbation.catalytically_dead` refuse to act without a unit.
    """
    parsed = _read(unit)
    if _signature(parsed) != (("s", -1),):
        raise QuantityError(
            f"{unit!r} is {dimension_of(unit)}, not a rate per unit time, so "
            f"it has no value per second. A second-order rate constant is "
            f"per concentration per time and converting it as though it were "
            f"first-order would silently change what it describes; a "
            f"concentration converts with to_molar."
        )
    return float(value) * parsed.scale


# ---------------------------------------------------------------------------
# One quantity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """One number in a model, with everything the motif knew about it.

    `value` is whatever the IR currently holds, which for an unresolved
    model is the motif library's ILLUSTRATIVE placeholder. Nothing on this
    type asserts that the number is right, and `table` names where a search
    would go rather than where this number came from.
    """

    id: str
    value: float
    unit: str
    kind: str
    #: The motif that declared it, and the instance of that motif this one
    #: belongs to. Two tiers of a cascade have the same motif and different
    #: instances, and "which kcat is this" has no other answer once the
    #: prefix has been flattened into an id.
    motif: str
    instance: str
    #: The motif-local name -- `kcat`, `Km`, the port name for a species.
    #: The id is `instance_name`, and keeping the parts is what lets a
    #: report say "the kinase turnover number of tier 2" rather than
    #: `tier2_kcat_kin`.
    name: str
    source: str = SOURCE_PARAMETER
    #: The BRENDA table that would serve this quantity. AN ADDRESS, NOT A
    #: SOURCE: `None` means no lookup exists, which a report must say rather
    #: than reporting a search that failed.
    table: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KNOWN_KINDS:
            raise QuantityError(
                f"quantity {self.id!r} has kind {self.kind!r}, which is not "
                f"one of {sorted(KNOWN_KINDS)}. Kind decides whether the "
                f"literature is asked for this number and whether a caller "
                f"may supply it, so an unknown kind has no defined "
                f"behaviour -- it would be neither resolvable nor chosen."
            )
        if self.source not in SOURCES:
            raise QuantityError(
                f"quantity {self.id!r} claims source {self.source!r}; it is "
                f"either a {SOURCE_PARAMETER} or a {SOURCE_SPECIES_INITIAL}, "
                f"and which one decides where a caller has to write to "
                f"change it"
            )
        if (
            self.source == SOURCE_SPECIES_INITIAL
            and self.kind != KIND_CONCENTRATION
        ):
            raise QuantityError(
                f"quantity {self.id!r} is a species initial of kind "
                f"{self.kind!r}. A starting amount is a concentration by "
                f"construction, and any other kind would make it resolvable "
                f"-- nobody publishes how much of it you put in the tube."
            )

    # -- what may be asked of the literature --------------------------

    @property
    def resolvable(self) -> bool:
        """A measurement of the molecule, so a paper could supply it.

        DERIVED from the kind rather than stored, so the two cannot drift.
        A concentration is never resolvable however it is named.
        """
        return self.kind in RESOLVABLE_KINDS

    @property
    def chosen(self) -> bool:
        """The caller's to set: a starting amount, a Hill coefficient.

        Not the same as "we could not find it". Nobody publishes how much
        enzyme is in your tube, so a missing value here is not a gap in the
        literature and must never be reported as one.
        """
        return self.kind in CHOSEN_KINDS

    # NO `illustrative` PROPERTY, DELIBERATELY. It would have to return
    # `resolvable`, and that is a different claim: after a resolver writes a
    # measured kcat into the network, the quantity is still resolvable and
    # its value is no longer a placeholder. This type does not record which
    # -- `agents/assembly.py` does -- so a property asserting it would be
    # confidently wrong exactly when a model has been grounded, which is the
    # one case where being wrong about provenance matters most.

    # -- conversions --------------------------------------------------

    @property
    def dimension(self) -> str:
        return dimension_of(self.unit)

    def molar(self) -> float:
        """This quantity in molar, or a refusal naming what it actually is."""
        if _signature(_read(self.unit, what=self.id)) != (("M", 1),):
            raise QuantityError(
                f"{self.id} is a {self.kind} in {self.unit!r}, which is "
                f"{self.dimension}. Only a concentration or an affinity has "
                f"a value in molar."
            )
        return to_molar(self.value, self.unit)

    def per_second(self) -> float:
        """This quantity per second, or a refusal naming what it actually is."""
        if _signature(_read(self.unit, what=self.id)) != (("s", -1),):
            raise QuantityError(
                f"{self.id} is a {self.kind} in {self.unit!r}, which is "
                f"{self.dimension}. Only a first-order rate has a value per "
                f"second."
            )
        return to_per_second(self.value, self.unit)

    def describe(self) -> str:
        origin = f"{self.motif}.{self.name} in {self.instance}"
        if self.resolvable:
            standing = (
                f"measurable, from the {self.table} table"
                if self.table else
                "measurable, but only from a paper -- no database table "
                "serves it"
            )
        else:
            standing = "yours to choose -- no paper supplies it"
        return (
            f"{self.id} = {self.value:g} {self.unit} "
            f"[{self.kind}, {origin}] ({standing})"
        )


# ---------------------------------------------------------------------------
# The consistency check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyReport:
    """Whether the side table and the network still describe one model.

    A SIDE TABLE CAN GO STALE, AND SILENTLY. The whole design rests on the
    two being built from the same composition; anything that edits a network
    afterwards -- and `perturbation.py`, `robustness.py` and every test that
    calls `dataclasses.replace` do exactly that -- can produce a network
    holding a number this table has never heard of. That number is the
    original gap, reappearing one level up: a bare float with no unit, no
    kind and no provenance.

    So it is reported loudly rather than tolerated. `ungoverned` is the
    important list and the summary leads with it.
    """

    #: Ids the network holds that no quantity describes. THE GAP.
    ungoverned: Tuple[str, ...] = ()
    #: Quantities naming nothing in the network -- a table describing a
    #: model that no longer exists. Less dangerous than an ungoverned
    #: number (nothing reads it) and still a sign the two have diverged.
    orphaned: Tuple[str, ...] = ()
    #: Quantities carrying no unit at all. Distinct from an unreadable one:
    #: nothing was declared, rather than something that could not be read.
    unitless: Tuple[str, ...] = ()
    #: Quantity id -> why its unit could not be interpreted.
    unreadable: Mapping[str, str] = field(default_factory=dict)
    #: How many network ids were examined. Reported because "no problems"
    #: over zero ids is not a clean result, it is an empty scan.
    checked: int = 0
    #: How many of them a quantity described.
    governed: int = 0

    @property
    def complete(self) -> bool:
        """Every number in the network is described, and readable.

        False on an empty scan. A checker that returns True for a network
        with nothing in it reports success in precisely the case where it
        verified nothing, which is the defect
        `scripts/check_no_vacuous_tests.py` exists to find in tests.
        """
        return (
            self.checked > 0
            and not self.ungoverned
            and not self.orphaned
            and not self.unitless
            and not self.unreadable
        )

    def summary(self) -> str:
        if self.checked == 0:
            return (
                "Nothing was checked: the network holds no parameters and no "
                "species. Refusing to report a consistent table over an "
                "empty model -- an empty scan is not a clean one."
            )

        lines: List[str] = []
        if self.ungoverned:
            lines.append(
                f"{len(self.ungoverned)} number(s) in this network have NO "
                f"quantity: " + ", ".join(self.ungoverned) + ". This is the "
                "unit gap reappearing -- each of these is a bare float with "
                "no unit, no kind and no motif behind it, so nothing can say "
                "whether it is a rate or an affinity, whether the literature "
                "may be asked for it, or whether its magnitude is possible. "
                "They were almost certainly added to the network after it "
                "was built; rebuild the table from the model that now owns "
                "them, or add them through a motif so they arrive with their "
                "meaning attached."
            )
        if self.orphaned:
            lines.append(
                f"{len(self.orphaned)} quantity(ies) name nothing in this "
                f"network: " + ", ".join(self.orphaned) + ". The table and "
                "the network have diverged; nothing reads these, but they "
                "mean the table is describing a model this is not."
            )
        if self.unitless:
            lines.append(
                f"{len(self.unitless)} quantity(ies) carry no unit: "
                + ", ".join(self.unitless)
                + ". An empty unit is not `dimensionless` -- it says the "
                "declaration is missing, so the number cannot be converted "
                "or compared with anything."
            )
        if self.unreadable:
            lines.append(
                f"{len(self.unreadable)} quantity(ies) have a unit that "
                f"cannot be read: "
                + "; ".join(f"{k} ({v})" for k, v in sorted(self.unreadable.items()))
                + ". Left uninterpreted rather than guessed at."
            )

        if not lines:
            return (
                f"All {self.checked} number(s) in this network have a "
                f"quantity with a readable unit, and every quantity names a "
                f"parameter or species that exists. That says the table and "
                f"the network describe the same model; it says nothing about "
                f"whether any value in it is right."
            )
        lines.insert(
            0,
            f"{self.governed} of {self.checked} number(s) in this network "
            f"are described by a quantity.",
        )
        return "\n".join(lines)

    def raise_if_incomplete(self) -> None:
        """Refuse to continue past an inconsistency.

        For callers that cannot do anything sensible with a half-described
        model -- a converter, an export. A caller that CAN (a report) should
        print `summary()` instead, because losing the rest of a dossier over
        one stray parameter is a poor trade.
        """
        if not self.complete:
            raise QuantityError(self.summary())


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


class QuantityTable:
    """Every number in a composed model, indexable by the id the IR uses.

    Built from a `ComposedModel` or from the `Composition` behind one --
    never from a bare `ReactionNetwork`, because a bare network is the thing
    that has already lost this information. Asking for a table from one is
    not a case to handle gracefully; it is the gap, and it refuses.
    """

    def __init__(
        self,
        quantities: Sequence[Quantity],
        *,
        model_name: str = "",
        concentration_unit: str = "",
    ) -> None:
        self.model_name = model_name
        #: The unit every species in this model is measured in.
        #:
        #: ONE unit for the whole model, taken from the composition that
        #: declared it. `scale.LIBRARY_CONCENTRATION_UNIT` had to assume this
        #: because it worked from the network; a table built from the
        #: composition can read it, so the assumption is retired here.
        self.concentration_unit = concentration_unit

        by_id: Dict[str, Quantity] = {}
        for quantity in quantities:
            if quantity.id in by_id:
                raise QuantityError(
                    f"two quantities claim the id {quantity.id!r} "
                    f"({by_id[quantity.id].describe()} and "
                    f"{quantity.describe()}). The IR has one number under "
                    f"that id, so one of these descriptions of it is wrong "
                    f"and there is no way to tell which."
                )
            by_id[quantity.id] = quantity
        self._by_id = by_id

    # -- construction -------------------------------------------------

    @classmethod
    def from_model(cls, model: Any) -> "QuantityTable":
        """The table for a `ComposedModel`.

        Refuses a bare network by name, because the error a caller most
        needs here is the one that says WHY there is nothing to recover.
        """
        composition = getattr(
            getattr(model, "recognition", None), "composition", None
        )
        if composition is None:
            raise QuantityError(
                "a quantity table can only be built from a composed model, "
                "which still knows the motifs its numbers came from. What "
                "was passed has no composition behind it -- if it is a bare "
                "ReactionNetwork then its units, kinds and provenance were "
                "dropped when it was built, and nothing can recover them "
                "from the network alone. That is the gap this module "
                "exists to keep closed, not a failure to handle."
            )
        return cls.from_composition(
            composition, network=getattr(model, "network", None)
        )

    @classmethod
    def from_composition(
        cls, composition: Any, network: Any = None
    ) -> "QuantityTable":
        """The table for a `Composition`, with values from `network`.

        `network` is where the VALUES come from, so the table describes the
        numbers the IR actually holds rather than the defaults the motifs
        declared -- those differ the moment a resolver writes a measured
        value in. Everything else -- unit, kind, motif, instance, table --
        comes from the composition, which is the only place it survives.

        Without a network the composition builds its own, so the table is
        still about real numbers rather than about defaults.
        """
        instances = tuple(getattr(composition, "instances", ()))
        if not instances:
            raise QuantityError(
                "this composition holds no motifs, so there is nothing to "
                "describe. An empty table is not a model with no numbers in "
                "it; it is a missing model."
            )
        if network is None:
            network = composition.to_network()

        values = {p.id: float(p.value) for p in getattr(network, "parameters", ())}
        initials = {s.id: float(s.initial) for s in getattr(network, "species", ())}
        concentration_unit = str(
            getattr(composition, "concentration_unit", "") or ""
        )

        quantities: List[Quantity] = []

        for instance in instances:
            for parameter in instance.motif.parameters:
                identifier = instance.parameter_id(parameter.name)
                quantities.append(
                    Quantity(
                        id=identifier,
                        value=values.get(identifier, float(parameter.default)),
                        unit=parameter.unit,
                        kind=parameter.kind,
                        motif=instance.motif.name,
                        instance=instance.prefix,
                        name=parameter.name,
                        source=SOURCE_PARAMETER,
                        table=parameter.table,
                        description=parameter.description,
                    )
                )

        origins = _species_origins(instances)
        for species_id in _species_ids(composition, network):
            origin = origins.get(species_id)
            if origin is None:
                # Reachable only for a species no port refers to, which the
                # builder cannot produce. Skipped rather than invented: the
                # consistency check will report it ungoverned, which is a
                # true statement, and a quantity with a guessed motif behind
                # it would not be.
                continue
            instance, port = origin
            quantities.append(
                Quantity(
                    id=species_id,
                    value=initials.get(species_id, float(port.default_initial)),
                    unit=concentration_unit,
                    kind=KIND_CONCENTRATION,
                    motif=instance.motif.name,
                    instance=instance.prefix,
                    name=port.name,
                    source=SOURCE_SPECIES_INITIAL,
                    table=None,
                    description=port.description,
                )
            )

        return cls(
            quantities,
            model_name=str(getattr(network, "name", "")
                           or getattr(composition, "name", "")),
            concentration_unit=concentration_unit,
        )

    # -- lookup -------------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Quantity]:
        return iter(self._by_id.values())

    def __contains__(self, identifier: object) -> bool:
        return identifier in self._by_id

    def __getitem__(self, identifier: str) -> Quantity:
        try:
            return self._by_id[identifier]
        except KeyError:
            raise QuantityError(
                f"no quantity for {identifier!r}. This model's numbers are: "
                + ", ".join(sorted(self._by_id))
                + ". If the network really holds that id, the table was "
                "built from a different model and the number is ungoverned "
                "-- see check_consistency."
            ) from None

    def get(self, identifier: str) -> Optional[Quantity]:
        return self._by_id.get(identifier)

    def ids(self) -> Tuple[str, ...]:
        return tuple(self._by_id)

    # -- partitions ---------------------------------------------------

    @property
    def parameters(self) -> Tuple[Quantity, ...]:
        return tuple(q for q in self if q.source == SOURCE_PARAMETER)

    @property
    def species(self) -> Tuple[Quantity, ...]:
        return tuple(q for q in self if q.source == SOURCE_SPECIES_INITIAL)

    @property
    def resolvable(self) -> Tuple[Quantity, ...]:
        """What a scout may be sent for: rate constants and affinities."""
        return tuple(q for q in self if q.resolvable)

    @property
    def chosen(self) -> Tuple[Quantity, ...]:
        """What the caller sets: starting amounts and any cooperativity."""
        return tuple(q for q in self if q.chosen)

    def of_kind(self, kind: str) -> Tuple[Quantity, ...]:
        """Every quantity of one kind, by the motif's own declaration.

        The precise answer to questions that were being asked by name-match.
        `of_kind(KIND_CONCENTRATION)` is the dose axis -- exactly the
        species initials and the concentration parameters, and not the Hill
        coefficients that "everything the caller chooses" also contains.
        """
        if kind not in KNOWN_KINDS:
            raise QuantityError(
                f"{kind!r} is not a kind. The kinds are "
                f"{sorted(KNOWN_KINDS)}; asking for another would return an "
                f"empty tuple that reads as 'this model has none'."
            )
        return tuple(q for q in self if q.kind == kind)

    # -- units --------------------------------------------------------

    def units(self) -> Dict[str, str]:
        """Every quantity's unit, species initials included."""
        return {q.id: q.unit for q in self}

    def parameter_units(self) -> Dict[str, str]:
        """Units of the network's PARAMETERS only.

        Narrower than `units` on purpose. `scale.check` takes a mapping it
        looks up per parameter and handles species through its own
        `species_unit` argument, so handing it species entries would be
        harmless and misleading -- it would look as though the species were
        being checked through this mapping when they are not.
        """
        return {q.id: q.unit for q in self.parameters}

    # -- consistency --------------------------------------------------

    def consistency(self, network: Any) -> ConsistencyReport:
        """Whether this table and that network describe the same model."""
        network_ids: List[str] = [
            p.id for p in getattr(network, "parameters", ())
        ]
        network_ids += [s.id for s in getattr(network, "species", ())]

        present = set(network_ids)
        ungoverned = tuple(i for i in network_ids if i not in self._by_id)
        orphaned = tuple(i for i in self._by_id if i not in present)

        unitless: List[str] = []
        unreadable: Dict[str, str] = {}
        for quantity in self:
            if quantity.id not in present:
                continue
            if not (quantity.unit or "").strip():
                unitless.append(quantity.id)
                continue
            try:
                parse_unit(quantity.unit)
            except UnitError as exc:
                unreadable[quantity.id] = str(exc)

        return ConsistencyReport(
            ungoverned=ungoverned,
            orphaned=orphaned,
            unitless=tuple(unitless),
            unreadable=unreadable,
            checked=len(network_ids),
            governed=sum(1 for i in network_ids if i in self._by_id),
        )

    # -- display ------------------------------------------------------

    def summary(self) -> str:
        resolvable = self.resolvable
        chosen = self.chosen
        lines = [
            f"{len(self)} quantity(ies) in {self.model_name or 'this model'}: "
            f"{len(self.parameters)} parameter(s) and {len(self.species)} "
            f"species initial(s), the latter being where a composed model "
            f"keeps its concentrations.",
            f"{len(resolvable)} could be resolved from the literature "
            f"(rate constants and affinities). Whether the values here are "
            f"measured ones is NOT recorded in this table -- it describes "
            f"the slots, not their provenance -- so they are the motif "
            f"library's illustrative placeholders unless a search report "
            f"says otherwise.",
            f"{len(chosen)} are yours to choose -- starting amounts and any "
            f"cooperativity. No paper supplies those, so a missing one is "
            f"not a gap in the literature.",
        ]
        no_table = [q.id for q in resolvable if q.table is None]
        if no_table:
            lines.append(
                f"{len(no_table)} resolvable quantity(ies) have no database "
                f"table behind them ("
                + ", ".join(no_table[:6])
                + ("..." if len(no_table) > 6 else "")
                + "): they are findable in a paper and not by a lookup, "
                "which is a different sentence from a search that failed."
            )
        return "\n".join(lines)


def _species_ids(composition: Any, network: Any) -> Tuple[str, ...]:
    """Species of the network, or of the composition when it has none.

    The network is preferred so that the table covers what actually exists.
    """
    from_network = tuple(s.id for s in getattr(network, "species", ()))
    return from_network or tuple(getattr(composition, "species_ids", ()))


def _species_origins(instances: Sequence[Any]) -> Dict[str, Tuple[Any, Any]]:
    """Which instance and port each species came from.

    RECONSTRUCTED FROM THE NAMING RULE rather than read out of the
    composition's private bookkeeping. `builder.Composition.add` creates a
    species as `<prefix>_<port>` and every prefix in a composition is unique,
    so a binding that matches that pattern is the port that CREATED the
    species and any other binding merely uses it. That is a documented rule
    of the builder, not an inference about it.

    Creators are preferred over users because the creator is what decides
    the starting amount -- a cascade intermediate starts at the upstream
    product's default of zero, not at the downstream substrate's default of
    one, and attributing it to the consumer would describe the wrong choice.
    A species with no creator among the instances (only reachable if a
    binding was rewritten by hand) falls back to a port that uses it, which
    is a true statement about where it appears.
    """
    created: Dict[str, Tuple[Any, Any]] = {}
    used: Dict[str, Tuple[Any, Any]] = {}
    for instance in instances:
        for port in instance.motif.ports:
            species_id = instance.bindings.get(port.name)
            if species_id is None:
                continue
            if species_id == f"{instance.prefix}_{port.name}":
                created.setdefault(species_id, (instance, port))
            else:
                used.setdefault(species_id, (instance, port))
    for species_id, origin in used.items():
        created.setdefault(species_id, origin)
    return created


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def quantities_of(model: Any) -> QuantityTable:
    """The quantity table for a composed model. The entry point worth using."""
    return QuantityTable.from_model(model)


def check_consistency(model: Any, *, network: Any = None) -> ConsistencyReport:
    """Whether a model's numbers are all described.

    `network` defaults to the model's own. Pass one explicitly to check a
    network that has been EDITED since -- a knockout, a resampled draw, a
    test's `replace` -- which is the case where a number can appear that the
    table has never heard of.
    """
    table = QuantityTable.from_model(model)
    return table.consistency(network if network is not None else model.network)


__all__ = [
    "Quantity", "QuantityTable", "ConsistencyReport", "QuantityError",
    # Re-exported from `motifs` because `of_kind` takes one and a caller
    # should not need two imports to ask a table for its concentrations.
    "KIND_RATE_CONSTANT", "KIND_AFFINITY", "KIND_CONCENTRATION",
    "KIND_EXPONENT", "RESOLVABLE_KINDS", "CHOSEN_KINDS",
    "quantities_of", "check_consistency",
    "dimension_of", "to_molar", "to_per_second",
    "SOURCE_PARAMETER", "SOURCE_SPECIES_INITIAL", "SOURCES",
    "DIMENSION_CONCENTRATION", "DIMENSION_PER_TIME",
    "DIMENSION_PER_CONCENTRATION_PER_TIME",
    "DIMENSION_CONCENTRATION_PER_TIME", "DIMENSION_DIMENSIONLESS",
    "KNOWN_KINDS",
]
