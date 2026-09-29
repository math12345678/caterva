"""Reusable pieces of mechanism, and the rules for wiring them together.

WHY A GRAMMAR RATHER THAN A LONGER CATALOGUE
--------------------------------------------
Measured on twenty realistic queries, the front door answers three. Of the
seventeen refusals, eleven are compositional: a three-step phosphorylation
cascade, two enzymes competing for one substrate, a toggle switch, an open
system with constant inflow. None of them is in the catalogue and none ever
will be, because the set of compositions is not enumerable -- "three step"
becomes "four step", and a catalogue entry is needed for each.

They are, however, all built from a handful of pieces that biochemistry has
been teaching for fifty years. A cascade is one phosphorylation cycle
chained N times. Competition is two catalytic steps sharing a substrate. A
toggle switch is two repressions pointing at each other. This module is
those pieces and the wiring rules; `builder.py` composes them.

THE PROPERTY THAT MAKES THIS WORTH DOING
----------------------------------------
Composed models are MORE resolvable than catalogue ones, not less.

The catalogue's `mm` domain has a `vmax` parameter, and Vmax is blocked
forever (ADR 0013) because it is kcat x [E]0 and [E]0 is the caller's. A
composed enzymatic step does not have a Vmax. It has

    kcat * E * S / (Km + S)

where `kcat` and `Km` are literature quantities the scouts resolve and `E`
is a SPECIES whose initial concentration is a scenario choice, exactly like
`s0` -- which ADR 0044 already settled as legitimate to pre-fill. The
fabrication the catalogue has to refuse simply does not arise, because
writing the mechanism out honestly removes the lumped parameter that caused
it.

WHAT A MOTIF IS
---------------
A fragment with named PORTS. A port is a species the motif needs but does
not own: the substrate of a catalytic step is a port, so two steps can be
wired by binding the first's product port and the second's substrate port to
the same species. Everything a motif does own -- its rate constants, its
internal intermediates -- is prefixed at instantiation so N copies coexist.

Every parameter declares whether the literature can supply it. That flag is
not decoration: it is what `builder.py` hands the agent pipeline as the list
of quantities to go and search for, and what separates a rate constant
somebody measured from a concentration the caller chose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence, Tuple

#: What a port is FOR. Used by the composition operators to decide which
#: ports may be wired to which -- a chain joins a `product` to a `substrate`
#: and never a `substrate` to a `substrate`.
ROLE_SUBSTRATE = "substrate"
ROLE_PRODUCT = "product"
ROLE_ENZYME = "enzyme"
ROLE_REGULATOR = "regulator"
ROLE_PARTNER = "partner"
ROLE_COMPLEX = "complex"

ROLES = (
    ROLE_SUBSTRATE,
    ROLE_PRODUCT,
    ROLE_ENZYME,
    ROLE_REGULATOR,
    ROLE_PARTNER,
    ROLE_COMPLEX,
)

#: What KIND of quantity a parameter is. This drives two decisions that must
#: not be made by name-matching a string later:
#:
#:   whether the literature is asked for it, and
#:   whether a caller may supply it without that being a fabrication.
#:
#: A `rate_constant` or an `affinity` is a property of the molecule and must
#: be measured or refused. A `concentration` is what is in the tube. An
#: `exponent` (a Hill coefficient) is a modelling choice with a conventional
#: value and no single measurement.
KIND_RATE_CONSTANT = "rate_constant"
KIND_AFFINITY = "affinity"
KIND_CONCENTRATION = "concentration"
KIND_EXPONENT = "exponent"

#: Kinds a scout should be sent to look for.
RESOLVABLE_KINDS = frozenset({KIND_RATE_CONSTANT, KIND_AFFINITY})

#: Kinds the caller legitimately chooses. Distinct from "we could not find
#: it": nobody publishes how much enzyme YOU put in.
CHOSEN_KINDS = frozenset({KIND_CONCENTRATION, KIND_EXPONENT})


class MotifError(ValueError):
    """A motif is malformed, or was wired in a way it does not permit."""


@dataclass(frozen=True)
class Port:
    """A species the motif uses but does not own.

    `default_initial` is used only when the port ends up creating the
    species rather than binding to an existing one. It is a concentration
    and therefore a scenario choice; nothing here treats it as measured.
    """

    name: str
    role: str
    default_initial: float = 0.0
    #: A port may be bound to a species that already exists, or create one.
    #: `required` ports must end up bound to something; an optional port
    #: that is never bound is dropped along with the reactions using it.
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise MotifError(
                f"port {self.name!r} has role {self.role!r}, which is not one "
                f"of {ROLES}. Roles decide which ports may be wired to which, "
                f"so an unknown one would make the wiring rules silently "
                f"permissive."
            )


@dataclass(frozen=True)
class MotifParameter:
    """A constant the motif needs, and where it is expected to come from."""

    name: str
    kind: str
    #: The value used when nothing resolves it. For a RESOLVABLE kind this
    #: is a placeholder that must never reach a simulation unlabelled -- the
    #: builder hands those to the agent pipeline as things to search for,
    #: and the pipeline refuses rather than defaulting them.
    default: float
    unit: str
    description: str = ""
    #: Which BRENDA table serves it, when one does. `None` means no lookup
    #: exists, which the report must say rather than claiming a failed search.
    table: Optional[str] = None
    #: The port whose COMPOUND this constant is measured for, when it is not
    #: the motif's first substrate port: a competitive inhibitor's Ki is the
    #: inhibitor's (port I), a reverse Km is the product's (port P), a
    #: phosphatase's Km is the phosphorylated form's (port Xp). BRENDA files
    #: every Km, Ki and kcat under a compound, so looking one up under the
    #: wrong compound returns another molecule's constant under this one's
    #: name. `None` means the first substrate port.
    ligand: Optional[str] = None
    #: Why no single database value can fill this constant, when none can:
    #: a mixed inhibitor's Kic and Kiu are two constants, and a BRENDA Ki row
    #: does not say which one it measured. Set, the constant is never looked
    #: up; the reason is reported instead.
    lookup_refused: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in RESOLVABLE_KINDS | CHOSEN_KINDS:
            raise MotifError(
                f"parameter {self.name!r} has kind {self.kind!r}. Kind decides "
                f"whether the literature is asked and whether a caller may "
                f"supply it, so an unknown kind has no defined behaviour."
            )
        if self.kind in RESOLVABLE_KINDS and self.table is None:
            # Not an error: a rate constant with no BRENDA table is real
            # (an mRNA degradation rate, say). But it must be visible,
            # because "searched and not found" and "never searched" are
            # different sentences in every refusal this project writes.
            object.__setattr__(self, "description",
                               (self.description + " (no database table serves "
                                "this; it is resolvable only from a paper)").strip())

    @property
    def resolvable(self) -> bool:
        return self.kind in RESOLVABLE_KINDS


@dataclass(frozen=True)
class ReactionTemplate:
    """One reaction, written in terms of port and parameter NAMES.

    `reactants` and `products` map a port name to a stoichiometric
    coefficient. `rate_law` is a Python format string over port and
    parameter names -- `"{kcat} * {E} * {S} / ({Km} + {S})"` -- which
    `instantiate` fills with the concrete, prefixed identifiers.

    Formatting rather than string replacement so a name that is a prefix of
    another cannot corrupt the law: replacing "S" in "Km + S" would also hit
    the S in a species called "S6K".
    """

    name: str
    reactants: Mapping[str, int] = field(default_factory=dict)
    products: Mapping[str, int] = field(default_factory=dict)
    rate_law: str = ""
    #: Species that appear in the rate law but are neither consumed nor
    #: produced -- an enzyme, a regulator. Declared so `instantiate` can
    #: check the law only references things the motif actually has.
    modifiers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Motif:
    """A named piece of mechanism, ready to be instantiated and wired."""

    name: str
    summary: str
    ports: Tuple[Port, ...]
    parameters: Tuple[MotifParameter, ...]
    reactions: Tuple[ReactionTemplate, ...]
    #: The biochemistry this encodes, for the model's own provenance. A
    #: composed model should be able to say why it has the shape it has.
    basis: str = ""

    def __post_init__(self) -> None:
        port_names = [p.name for p in self.ports]
        if len(set(port_names)) != len(port_names):
            raise MotifError(f"motif {self.name!r} has duplicate port names")
        for parameter in self.parameters:
            if parameter.ligand is not None and parameter.ligand not in port_names:
                raise MotifError(
                    f"motif {self.name!r}: parameter {parameter.name!r} names port "
                    f"{parameter.ligand!r} as its compound, and the motif has no such port. "
                    f"The lookup would be silently skipped.")
        parameter_names = [p.name for p in self.parameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise MotifError(f"motif {self.name!r} has duplicate parameter names")
        overlap = set(port_names) & set(parameter_names)
        if overlap:
            raise MotifError(
                f"motif {self.name!r} uses {sorted(overlap)} as both a port "
                f"and a parameter. The rate-law formatter cannot tell them "
                f"apart, so the law would silently reference whichever was "
                f"substituted last."
            )
        known = set(port_names) | set(parameter_names)
        for reaction in self.reactions:
            for side in (reaction.reactants, reaction.products):
                unknown = set(side) - set(port_names)
                if unknown:
                    raise MotifError(
                        f"motif {self.name!r} reaction {reaction.name!r} uses "
                        f"{sorted(unknown)} in its stoichiometry, which is not "
                        f"a port of this motif"
                    )
            unknown_modifiers = set(reaction.modifiers) - set(port_names)
            if unknown_modifiers:
                raise MotifError(
                    f"motif {self.name!r} reaction {reaction.name!r} declares "
                    f"modifier(s) {sorted(unknown_modifiers)} that are not ports"
                )
            # Every {placeholder} in the law must be a port or a parameter.
            for placeholder in _placeholders(reaction.rate_law):
                if placeholder not in known:
                    raise MotifError(
                        f"motif {self.name!r} reaction {reaction.name!r} has a "
                        f"rate law referencing {placeholder!r}, which is "
                        f"neither a port nor a parameter of this motif"
                    )

    def port(self, name: str) -> Port:
        for candidate in self.ports:
            if candidate.name == name:
                return candidate
        raise MotifError(f"motif {self.name!r} has no port {name!r}")

    def ports_with_role(self, role: str) -> Tuple[Port, ...]:
        return tuple(p for p in self.ports if p.role == role)


def _placeholders(template: str) -> Tuple[str, ...]:
    """Names inside {braces} in a rate-law template."""
    import re

    return tuple(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template))


__all__ = [
    "Motif",
    "MotifParameter",
    "MotifError",
    "Port",
    "ReactionTemplate",
    "ROLE_SUBSTRATE",
    "ROLE_PRODUCT",
    "ROLE_ENZYME",
    "ROLE_REGULATOR",
    "ROLE_PARTNER",
    "ROLE_COMPLEX",
    "ROLES",
    "KIND_RATE_CONSTANT",
    "KIND_AFFINITY",
    "KIND_CONCENTRATION",
    "KIND_EXPONENT",
    "RESOLVABLE_KINDS",
    "CHOSEN_KINDS",
]
