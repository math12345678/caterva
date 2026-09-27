"""Instantiating motifs, wiring them together, and emitting a network.

WHAT COMPOSITION HAS TO GET RIGHT
---------------------------------
Three things, and all three are places a naive implementation goes quietly
wrong rather than loudly:

**Names must not collide.** Three phosphorylation cycles all want a species
called `X` and a parameter called `kcat_kin`. Everything a motif owns is
prefixed at instantiation; only PORTS may be shared, and only deliberately.

**Shared species must be shared, not duplicated.** A cascade is two steps
where the first's product IS the second's substrate -- not two species that
happen to be called the same thing. If they were duplicated the model would
run and would conserve nothing, which is the failure that looks most like
success on a plot.

**An intermediate starts where an intermediate starts.** When two ports bind
to one species, whose initial amount wins? The rule here is that the
UPSTREAM port creates it, so a cascade intermediate starts at its product
default of zero rather than at the next step's substrate default of one.
Left to dictionary order this would depend on the order the motifs happened
to be added, which is exactly the kind of invisible decision this codebase
spends its time removing.

WHAT COMES OUT
--------------
A `ReactionNetwork` from `caterva/core/network.py`, which then validates
itself, derives its own conservation laws from the stoichiometry, and can be
handed to `caterva/agents` for parameterisation. Nothing here resolves a
value or invents one: `quantities_to_resolve()` reports which parameters the
literature should be asked for, and the pipeline refuses the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .motifs import (
        CHOSEN_KINDS, KIND_CONCENTRATION, Motif, MotifError, MotifParameter,
        Port, RESOLVABLE_KINDS, ROLE_ENZYME, ROLE_PRODUCT, ROLE_REGULATOR,
        ROLE_SUBSTRATE,
    )
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        CHOSEN_KINDS, KIND_CONCENTRATION, Motif, MotifError, MotifParameter,
        Port, RESOLVABLE_KINDS, ROLE_ENZYME, ROLE_PRODUCT, ROLE_REGULATOR,
        ROLE_SUBSTRATE,
    )


class CompositionError(ValueError):
    """Two motifs were wired in a way that does not describe a system."""


@dataclass(frozen=True)
class ResolvableQuantity:
    """A parameter the literature should be asked for.

    Carries the motif's own description and BRENDA table so the request that
    reaches a scout says what it is looking for rather than only naming a
    symbol -- `mek_kcat_kin` means nothing on its own, and "kinase turnover
    number, from the kcat table" means something.
    """

    parameter_id: str
    motif_name: str
    parameter_name: str
    kind: str
    unit: str
    table: Optional[str]
    description: str
    placeholder: float


@dataclass
class Instance:
    """One motif, placed into a composition."""

    motif: Motif
    prefix: str
    #: port name -> species id it resolves to.
    bindings: Dict[str, str] = field(default_factory=dict)

    def species_for(self, port_name: str) -> str:
        try:
            return self.bindings[port_name]
        except KeyError:
            raise CompositionError(
                f"instance {self.prefix!r} has no binding for port "
                f"{port_name!r}; it should have been created at add() time"
            ) from None

    def parameter_id(self, parameter_name: str) -> str:
        return f"{self.prefix}_{parameter_name}"


class Composition:
    """A set of wired motif instances, buildable into a network."""

    def __init__(self, name: str, concentration_unit: str = "mM") -> None:
        self.name = name
        #: The unit every species in this composition is measured in.
        #:
        #: One unit for the whole model, not one per species. Two species in
        #: different units is precisely the mistake `unit_findings` exists to
        #: catch, and letting a composition declare it per-species would make
        #: the mistake expressible rather than detectable.
        self.concentration_unit = concentration_unit
        self._instances: List[Instance] = []
        #: species id -> initial amount. Insertion order is preserved and is
        #: the order species appear in the emitted network, so compilation
        #: is deterministic.
        self._species: Dict[str, float] = {}
        #: species id -> the (prefix, port) that created it, for diagnostics.
        self._created_by: Dict[str, Tuple[str, str]] = {}
        self._notes: List[str] = []

    # -- building -----------------------------------------------------

    def add(
        self,
        motif: Motif,
        prefix: str,
        bindings: Optional[Mapping[str, str]] = None,
        initials: Optional[Mapping[str, float]] = None,
    ) -> Instance:
        """Place a motif, binding ports to existing species where asked.

        A port not named in `bindings` creates a species `<prefix>_<port>`.
        A port named in `bindings` must refer to a species that already
        exists -- binding to a name nothing created is how a typo becomes a
        second, disconnected copy of a pathway that still simulates.
        """
        if any(existing.prefix == prefix for existing in self._instances):
            raise CompositionError(
                f"prefix {prefix!r} is already used in this composition; "
                f"every instance owns its own namespace"
            )
        bindings = dict(bindings or {})
        initials = dict(initials or {})

        resolved: Dict[str, str] = {}
        for port in motif.ports:
            if port.name in bindings:
                target = bindings[port.name]
                if target not in self._species:
                    raise CompositionError(
                        f"{prefix}.{port.name} was bound to {target!r}, which "
                        f"no motif has created. Existing species: "
                        f"{sorted(self._species) or 'none'}."
                    )
                resolved[port.name] = target
                continue
            species_id = f"{prefix}_{port.name}"
            initial = initials.get(port.name, port.default_initial)
            self._species[species_id] = float(initial)
            self._created_by[species_id] = (prefix, port.name)
            resolved[port.name] = species_id

        instance = Instance(motif=motif, prefix=prefix, bindings=resolved)
        self._instances.append(instance)
        return instance

    def set_initial(self, species_id: str, value: float) -> None:
        if species_id not in self._species:
            raise CompositionError(
                f"no species {species_id!r} in this composition; "
                f"have {sorted(self._species)}"
            )
        self._species[species_id] = float(value)

    def note(self, text: str) -> None:
        """Record something about HOW this model was composed.

        Carried into the built model's description. A composed network
        should be able to say why it has the shape it has, and "three
        phosphorylation cycles chained head to tail" is not recoverable from
        the stoichiometry afterwards.
        """
        self._notes.append(text)

    # -- inspection ---------------------------------------------------

    @property
    def instances(self) -> Tuple[Instance, ...]:
        return tuple(self._instances)

    @property
    def species_ids(self) -> Tuple[str, ...]:
        return tuple(self._species)

    @property
    def notes(self) -> Tuple[str, ...]:
        return tuple(self._notes)

    def quantities_to_resolve(self) -> Tuple[ResolvableQuantity, ...]:
        """Every parameter the literature should be asked for.

        Excludes concentrations and Hill exponents: nobody publishes how
        much enzyme is in your tube, and a Hill coefficient is a modelling
        choice with a conventional value rather than a measurement of this
        system.
        """
        out: List[ResolvableQuantity] = []
        for instance in self._instances:
            for parameter in instance.motif.parameters:
                if parameter.kind not in RESOLVABLE_KINDS:
                    continue
                out.append(
                    ResolvableQuantity(
                        parameter_id=instance.parameter_id(parameter.name),
                        motif_name=instance.motif.name,
                        parameter_name=parameter.name,
                        kind=parameter.kind,
                        unit=parameter.unit,
                        table=parameter.table,
                        description=parameter.description,
                        placeholder=parameter.default,
                    )
                )
        return tuple(out)

    def chosen_quantities(self) -> Tuple[str, ...]:
        """Every quantity the CALLER supplies: species initials and the
        parameters whose kind says they are choices."""
        chosen = list(self._species)
        for instance in self._instances:
            for parameter in instance.motif.parameters:
                if parameter.kind in CHOSEN_KINDS:
                    chosen.append(instance.parameter_id(parameter.name))
        return tuple(chosen)

    # -- emitting -----------------------------------------------------

    def to_network(self):
        """Build the `ReactionNetwork`.

        Imported here rather than at module scope so this module can be read
        and unit-tested without the engine package on the path.
        """
        try:
            from caterva.core.network import (
                Parameter, Reaction, ReactionNetwork, Species,
            )
        except ImportError:  # pragma: no cover - flat layout
            from core.network import (  # type: ignore[no-redef]
                Parameter, Reaction, ReactionNetwork, Species,
            )

        if not self._instances:
            raise CompositionError(
                "nothing to build: a composition with no motifs is not an "
                "empty model, it is a missing one"
            )

        species = tuple(
            Species(species_id, initial)
            for species_id, initial in self._species.items()
        )

        parameters: List[Parameter] = []
        reactions: List[Reaction] = []
        for instance in self._instances:
            for parameter in instance.motif.parameters:
                parameters.append(
                    Parameter(
                        instance.parameter_id(parameter.name),
                        float(parameter.default),
                        # The unit the motif declared, carried into the
                        # network rather than dropped here. This line is
                        # the fix for a gap three modules worked around:
                        # scale.py reported every parameter unchecked,
                        # perturbation.py could not tell a rate from an
                        # affinity, and both had to walk back to the motifs
                        # to recover what was discarded one line above.
                        parameter.unit,
                    )
                )
            substitutions = {
                port.name: instance.species_for(port.name)
                for port in instance.motif.ports
            }
            substitutions.update(
                {
                    parameter.name: instance.parameter_id(parameter.name)
                    for parameter in instance.motif.parameters
                }
            )
            for template in instance.motif.reactions:
                reactions.append(
                    Reaction(
                        id=f"{instance.prefix}_{template.name}",
                        reactants={
                            instance.species_for(port): count
                            for port, count in template.reactants.items()
                        },
                        products={
                            instance.species_for(port): count
                            for port, count in template.products.items()
                        },
                        rate_law=template.rate_law.format(**substitutions),
                    )
                )

        return ReactionNetwork(
            name=self.name,
            species=species,
            parameters=tuple(parameters),
            reactions=tuple(reactions),
        )


    # -- dimensional checking -----------------------------------------

    def unit_environment(self) -> Dict[str, object]:
        """Every symbol a rate law can reference, with its unit.

        Built from the composition rather than from the emitted network,
        because the network has forgotten which motif each parameter came
        from and therefore what unit that motif declared for it.
        """
        try:
            from .units import parse_unit
        except ImportError:  # pragma: no cover - flat import
            from units import parse_unit  # type: ignore[no-redef]

        concentration = parse_unit(self.concentration_unit)
        environment: Dict[str, object] = {
            species_id: concentration for species_id in self._species
        }
        for instance in self._instances:
            for parameter in instance.motif.parameters:
                environment[instance.parameter_id(parameter.name)] = parse_unit(
                    parameter.unit
                )
        return environment

    def unit_findings(self) -> Tuple[object, ...]:
        """Every rate law that does not balance.

        Run at COMPOSITION time, before anything compiles. A dimensionally
        wrong rate law integrates perfectly well and produces a smooth curve
        that is wrong by whatever factor the mistake introduced, and there
        is no later point at which that becomes visible.

        An empty result means every law balanced OR that there were no laws
        to check -- see `unit_check`, which returns both halves. Callers
        that print a verdict must use that one: "every rate law balances"
        over zero rate laws is a true sentence and a misleading one.
        """
        return self.unit_check()[1]

    def protein_species(self) -> frozenset:
        """Species this composition wires as an ENZYME or a REGULATOR.

        Those two roles are proteins without exception: an enzyme is one
        by definition and a Hill regulator is a transcription factor. The
        other roles are not decidable from the wiring -- a kinase's
        SUBSTRATE is a protein and a hexokinase's is glucose, and both are
        `ROLE_SUBSTRATE` -- so they are not claimed.

        WHY IT EXISTS. `scale.py` carries a bound on how much of one
        species a cell can hold, derived from total cellular PROTEIN, about
        five millimolar. It was applied to every species. Glutamate sits
        near a hundred millimolar in E. coli and ATP near ten, both
        measured, and both came back "physically impossible" -- a false
        alarm on the two most abundant metabolites there are, which is the
        cry-wolf failure that gets a check switched off. The protein bound
        now reaches only the species this method returns; the rest get a
        bound that is defensible for a solute.

        A species wired as an enzyme in one instance and a substrate in
        another is a protein: it is in the set if ANY binding says so.
        """
        proteins = set()
        for instance in self._instances:
            for port in instance.motif.ports:
                if port.role in (ROLE_ENZYME, ROLE_REGULATOR):
                    try:
                        proteins.add(instance.species_for(port.name))
                    except CompositionError:
                        continue
        return frozenset(proteins)

    def unit_check(self) -> Tuple[int, Tuple[object, ...]]:
        """(rate laws examined, findings).

        The count exists because `unit_findings() == ()` conflates the two
        states a reader most needs told apart. A composition with no
        instances, or whose motifs declare no reactions, produces exactly
        the same empty tuple as one whose every law balances.
        """
        try:
            from .units import check_rate_law, parse_unit, rate_unit_for
        except ImportError:  # pragma: no cover - flat import
            from units import (  # type: ignore[no-redef]
                check_rate_law, parse_unit, rate_unit_for,
            )

        environment = self.unit_environment()
        expected = rate_unit_for(parse_unit(self.concentration_unit))

        findings: List[object] = []
        examined = 0
        for instance in self._instances:
            substitutions = {
                port.name: instance.species_for(port.name)
                for port in instance.motif.ports
            }
            substitutions.update(
                {
                    parameter.name: instance.parameter_id(parameter.name)
                    for parameter in instance.motif.parameters
                }
            )
            for template in instance.motif.reactions:
                label = f"{instance.prefix}_{template.name}"
                examined += 1
                _, produced = check_rate_law(
                    template.rate_law.format(**substitutions),
                    environment,
                    expected=expected,
                    label=label,
                )
                findings.extend(produced)
        return examined, tuple(findings)


# ---------------------------------------------------------------------------
# Composition operators
# ---------------------------------------------------------------------------


def chain(
    composition: Composition,
    motif: Motif,
    count: int,
    *,
    prefix: str,
    upstream_port: str,
    downstream_port: str,
    shared: Sequence[str] = (),
    head_initial: Optional[float] = None,
) -> Tuple[Instance, ...]:
    """Place `count` copies head to tail.

    Copy i's `upstream_port` and copy i+1's `downstream_port` become the same
    species. The upstream port CREATES it, so an intermediate starts at the
    product's default rather than the substrate's -- see the module
    docstring; left to insertion order this depends on which motif was added
    first, which is not a fact about biology.

    `shared` names ports every copy binds to one species -- a phosphatase
    acting on the whole cascade, say. The first copy creates it.

    A cascade of one is a legal cascade and is not special-cased: it places
    one copy and wires nothing, which is what the words mean.
    """
    if count < 1:
        raise CompositionError(
            f"a chain of {count} is not a shorter chain, it is not a chain; "
            f"say how many steps you mean"
        )
    motif.port(upstream_port)
    motif.port(downstream_port)
    if upstream_port == downstream_port:
        raise CompositionError(
            f"chaining {motif.name!r} on {upstream_port!r} to itself would "
            f"bind a species to its own producer and consume the model"
        )

    placed: List[Instance] = []
    shared_targets: Dict[str, str] = {}

    for index in range(count):
        step_prefix = f"{prefix}{index + 1}"
        bindings: Dict[str, str] = {}
        initials: Dict[str, float] = {}

        if placed:
            # The previous copy's upstream port already made the species;
            # this copy binds its downstream port to it.
            bindings[downstream_port] = placed[-1].species_for(upstream_port)
        elif head_initial is not None:
            initials[downstream_port] = head_initial

        for port_name in shared:
            if port_name in shared_targets:
                bindings[port_name] = shared_targets[port_name]

        instance = composition.add(motif, step_prefix, bindings, initials)
        placed.append(instance)

        for port_name in shared:
            shared_targets.setdefault(port_name, instance.species_for(port_name))

    composition.note(
        f"{count} x {motif.name} chained {upstream_port} -> {downstream_port}"
        + (f", sharing {', '.join(shared)}" if shared else "")
    )
    return tuple(placed)


def compete(
    composition: Composition,
    motif: Motif,
    count: int,
    *,
    prefix: str,
    shared_port: str,
    shared_initial: float = 1.0,
) -> Tuple[Instance, ...]:
    """Place `count` copies all acting on ONE shared species.

    Two enzymes competing for a substrate: two catalytic steps whose `S`
    ports are the same species and whose enzymes and products are not. The
    competition is not a rate law -- it is the shared pool, and it emerges
    from the stoichiometry rather than being written down.
    """
    if count < 2:
        raise CompositionError(
            f"competition needs at least two competitors; got {count}"
        )
    motif.port(shared_port)

    placed: List[Instance] = []
    target: Optional[str] = None
    for index in range(count):
        step_prefix = f"{prefix}{index + 1}"
        bindings = {shared_port: target} if target else {}
        initials = {} if target else {shared_port: shared_initial}
        instance = composition.add(motif, step_prefix, bindings, initials)
        placed.append(instance)
        target = target or instance.species_for(shared_port)

    composition.note(
        f"{count} x {motif.name} competing for one {shared_port}"
    )
    return tuple(placed)


def couple(
    composition: Composition,
    first: Instance,
    first_port: str,
    second: Instance,
    second_port: str,
) -> None:
    """Make two already-placed ports refer to one species.

    Used for feedback, where the wiring is not a chain: the last stage of a
    cascade regulating the first is a coupling backwards, and a chain cannot
    express it.

    Rebinds the SECOND port onto the first's species and retires the
    second's own species if nothing else uses it, so no orphan is left
    behind for the network validator to complain about.
    """
    keep = first.species_for(first_port)
    drop = second.species_for(second_port)
    if keep == drop:
        return

    second.bindings[second_port] = keep

    still_used = any(
        species == drop
        for instance in composition.instances
        for species in instance.bindings.values()
    )
    if not still_used:
        composition._species.pop(drop, None)
        composition._created_by.pop(drop, None)

    composition.note(
        f"{second.prefix}.{second_port} coupled to {first.prefix}.{first_port}"
    )


__all__ = [
    "Composition",
    "CompositionError",
    "Instance",
    "ResolvableQuantity",
    "chain",
    "compete",
    "couple",
]
