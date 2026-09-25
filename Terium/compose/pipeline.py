"""From a sentence to a model the agent architecture can parameterise.

THE TWO HALVES MEETING
----------------------
`grammar.py` turns a description into a structure without a language model.
`Terium/agents` turns a structure's unknown constants into cited values, or
into a precise statement of what is missing. Neither was any use to a
researcher on its own: a structure with invented numbers is a drawing, and a
literature search with no model to put the numbers in is a bibliography.

This is the join, and it is deliberately thin -- it decides what to ask the
literature FOR, and nothing else.

WHAT IT ASKS FOR, AND WHAT IT WILL NOT
--------------------------------------
Only quantities whose motif marks them resolvable: rate constants and
affinities. Concentrations are never asked for, because nobody publishes how
much enzyme is in your tube, and a Hill coefficient is never asked for,
because it is a modelling choice with a conventional value rather than a
measurement of this system.

And nothing is asked for at all unless the query named an enzyme. A composed
model of "two enzymes competing for the same substrate" has six unknown
constants and no subject: there is no enzyme whose Km could be looked up,
because none was named. Sending a scout anyway would produce "not found" for
six quantities and report a failed search that never happened -- the
sentence this codebase spends its time not writing.

So the honest output for an unnamed system is the STRUCTURE plus the list of
measurements that would complete it. That is a smaller claim than a
simulation and a more useful one than a refusal: it tells a researcher
exactly what to go and measure, in a model that is already correct in shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .builder import Composition, ResolvableQuantity
    from .grammar import Recognition, UnrecognisedShape, recognise
except ImportError:  # pragma: no cover - flat import
    from builder import Composition, ResolvableQuantity  # type: ignore[no-redef]
    from grammar import (  # type: ignore[no-redef]
        Recognition, UnrecognisedShape, recognise,
    )


@dataclass(frozen=True)
class ComposedModel:
    """A structure, its unknowns, and what is known about resolving them."""

    query: str
    recognition: Recognition
    network: Any
    #: Parameters the literature could supply, IF a subject were named.
    resolvable: Tuple[ResolvableQuantity, ...]
    #: Everything the caller supplies: species initials, Hill coefficients.
    chosen: Tuple[str, ...]
    #: The enzyme named in the query, when one was. `None` means the model
    #: is a mechanism rather than a claim about a particular protein.
    subject: Optional[str] = None
    #: The organism the constants should belong to. Absent means "whatever
    #: the resolver's documented default is", which the resolver states.
    organism: Optional[str] = None
    #: The substrate a kinetic constant belongs to. A motif knows it needs
    #: a Km; it cannot know what the Km is FOR, so this is the caller's
    #: (ADR 0178). Without it BRENDA's km and ki tables cannot be read.
    substrate: Optional[str] = None
    #: What a literature search actually returned, parameter id ->
    #: `Measurement`. Empty until `with_measured` is called, which is the
    #: only way a value in this model comes from anywhere but the motif
    #: library. A partial result is the normal case and is kept partial:
    #: for acetylcholinesterase BRENDA has a Km and no kcat, and a model
    #: that quietly substituted one and left the other at a placeholder
    #: would simulate, plot, and look exactly like a sourced one.
    measured: Mapping[str, Any] = field(default_factory=dict)
    #: Why each quantity the search could not resolve came back empty, in
    #: the resolver's words. "The value exists in another organism and was
    #: not substituted" and "nothing anywhere" are different facts with
    #: different next actions, and a report that prints one sentence for
    #: both tells a reader to stop looking for a number that is in the
    #: database (ADR 0178).
    not_found: Mapping[str, str] = field(default_factory=dict)
    #: Why a search that was asked for could not run at all -- an EC number
    #: BRENDA does not have, an incomplete one, a missing substrate. Without
    #: it the verdict could only say "none has been run" and advise running
    #: one, which is circular when running one is what just failed.
    search_refused: Optional[str] = None

    @property
    def structure_only(self) -> bool:
        """True when nothing can be searched for, because nothing was named."""
        return self.subject is None

    @property
    def unmeasured(self) -> Tuple[str, ...]:
        """Every resolvable constant, because this model carries no provenance.

        THE QUESTION `structure_only` WAS BEING ASKED TO ANSWER, AND COULD
        NOT. Three modules -- the verdict, the trajectory, the dossier's
        behaviour caveat -- tested `structure_only` to decide whether the
        constants were placeholders. It says whether a SUBJECT was named.
        Naming one runs no search; a `ComposedModel` has no way to carry a
        measured value at all. So every resolvable constant here is
        unmeasured, subject or not, and the three readers that thought
        otherwise were laundering the library's placeholders into
        apparently-measured constants on the strength of a name typed
        into the query.

        A `ProvenancedModel` overrides this with its actual placeholders,
        and `with_measured` fills `measured` here so this model can answer
        the same question after a search (ADR 0178).
        """
        return tuple(
            q.parameter_id for q in self.resolvable
            if q.parameter_id not in self.measured
        )

    @property
    def searched(self) -> bool:
        """True when a literature search was run over this model."""
        return bool(self.measured) or bool(self.not_found)

    def with_measured(
        self,
        measured: Mapping[str, Any],
        not_found: Optional[Mapping[str, str]] = None,
    ) -> "ComposedModel":
        """This model with the literature's values substituted in.

        The network is rebuilt by `export.provenance_of`, which is already
        the one place that decides an origin and substitutes a measured
        value, so the numbers a report simulates and the numbers its audit
        trail prints cannot disagree. Constants the search did not return
        keep the motif library's placeholder and stay in `unmeasured`.
        """
        if not measured and not not_found:
            return self
        if not measured:
            # A search that resolved nothing still ran, and why it found
            # nothing is the whole of what it has to report.
            return replace(self, not_found=dict(not_found or {}))
        try:
            from .export import provenance_of
        except ImportError:  # pragma: no cover - flat layout
            from export import provenance_of  # type: ignore[no-redef]
        provenanced = provenance_of(self, measured=dict(measured))
        return replace(
            self, network=provenanced.network, measured=dict(measured),
            not_found=dict(not_found or {}),
        )

    def parameter_requests(self) -> List[Any]:
        """`ParameterRequest`s for `Terium/agents`, or an empty list.

        Empty when no subject was named -- see the module docstring. An
        empty list here is a decision, not an oversight, and the caller must
        report the structure rather than an empty search.
        """
        if self.subject is None:
            return []
        try:
            from Tests.parameterize import ParameterRequest  # type: ignore
        except ImportError:  # pragma: no cover - flat layout
            from Terium.checkout import literature_module
            ParameterRequest = literature_module("parameterize").ParameterRequest

        # THE THREE FIELDS THAT USED TO BE LEFT EMPTY (ADR 0178).
        # `ParameterRequest` declares ec_number, substrate and organism and
        # BRENDA requires them; this method built a request without any of
        # them, so every scout failed with "needs an EC number ... none was
        # identified" even after the imports were repaired. The EC number is
        # resolved once here rather than per scout, which is what the field's
        # own comment says it is for.
        ec_number = self.ec_number
        return [
            ParameterRequest(
                quantity=quantity.parameter_id,
                subject=self.subject,
                substrate=self.substrate,
                organism=self.organism,
                ec_number=ec_number,
                table=quantity.table,
                expected_unit=quantity.unit,
            )
            for quantity in self.resolvable
            if quantity.table is not None
        ]

    @property
    def ec_number(self) -> Optional[str]:
        """The subject as an EC number, or None when it is not one.

        An EC number given directly is used as given. A NAME is not resolved
        here: "lactate dehydrogenase" is EC 1.1.1.27 and 1.1.1.28 and four
        more, and picking one would attach a citation to the wrong protein.
        The caller resolves a name through the literature layer's
        `ec_number_for_name`, which refuses ambiguity by naming every
        candidate, and passes the answer as the subject.
        """
        if self.subject is None:
            return None
        text = self.subject.strip()
        parts = text.split(".")
        if len(parts) == 4 and all(p.strip() and (p.strip().isdigit() or p.strip() == "-") for p in parts):
            return text
        return None

    def summary(self) -> str:
        lines = [
            f"Built {_article(self.recognition.rule)} "
            f"{self.recognition.rule.replace('_', ' ')} from your "
            f"description: {len(self.network.species)} species, "
            f"{len(self.network.reactions)} reactions "
            f"({self.recognition.reading})."
        ]
        for note in self.recognition.composition.notes:
            lines.append(note.rstrip(".") + ".")

        laws = _conservation_laws(self.network)
        if laws:
            lines.append(
                f"{len(laws)} conservation law(s) follow from the "
                f"stoichiometry: " + "; ".join(laws) + ". Nobody asserted "
                f"these; they are the left null space of this model's own "
                f"stoichiometry matrix."
            )

        # The species in NO law are the interesting ones, and a binary
        # "are there laws at all" misses them. An open system usually still
        # conserves its enzymes, so it has laws -- while the fed species,
        # the one the openness is about, appears in none of them. Reporting
        # only the count would have said nothing about the thing the model
        # was built to show.
        unconserved = _unconserved_species(self.network, laws)
        if unconserved:
            lines.append(
                f"{', '.join(unconserved)} appear(s) in no conservation law: "
                f"{'they are' if len(unconserved) > 1 else 'it is'} created "
                f"or destroyed by this model rather than only moved around, "
                f"which is what makes the system open. That is a fact about "
                f"the model, not a gap in the analysis."
            )
        elif not laws:
            lines.append(
                "No conservation law holds here at all, which is a fact "
                "about the model rather than a gap in the analysis."
            )

        if self.structure_only:
            lines.append(
                f"No enzyme was named, so nothing was searched for. The "
                f"{len(self.resolvable)} constant(s) this model needs are: "
                + ", ".join(q.parameter_id for q in self.resolvable)
                + ". Name the enzyme and Terrium will look each one up; "
                "supply them yourself and they are recorded as yours."
            )
        else:
            lines.append(
                f"{len(self.resolvable)} constant(s) will be searched for in "
                f"{self.subject}."
            )

        lines.append(
            f"{len(self.chosen)} quantity(ies) are yours to set -- the "
            f"starting amounts and any cooperativity: "
            + ", ".join(self.chosen[:8])
            + ("..." if len(self.chosen) > 8 else "")
            + "."
        )
        return " ".join(lines)


def _article(word: str) -> str:
    """"a" or "an". Cosmetic, but this sentence is the first thing a
    researcher reads and "a enzyme competition" undermines it."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def _unconserved_species(network: Any, laws: Sequence[str]) -> List[str]:
    """Species that appear in no conservation law.

    Read off the rendered laws rather than recomputing the null space: the
    laws are already the authoritative statement, and a second computation
    here would be a second opinion that can drift from the first.
    """
    import re

    mentioned = set()
    for law in laws:
        mentioned.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", law))
    return [s.id for s in network.species if s.id not in mentioned]


def _conservation_laws(network: Any) -> List[str]:
    try:
        from Terium.core.network import describe_conservation_laws
    except ImportError:  # pragma: no cover
        from core.network import describe_conservation_laws  # type: ignore
    return list(describe_conservation_laws(network))


def compose(
    query: str,
    *,
    subject: Optional[str] = None,
    organism: Optional[str] = None,
    substrate: Optional[str] = None,
    name: Optional[str] = None,
) -> ComposedModel:
    """Recognise a shape and build the model, or raise `UnrecognisedShape`.

    `subject` is the enzyme the constants belong to, when the caller knows
    it. It is NOT inferred from the query here: guessing that "a MAP kinase
    cascade" means MAP2K1 specifically would attach a real protein's
    measured constants to a generic three-tier model, which is the
    adjacent-paper miscitation of ADR 0076 wearing different clothes.
    """
    recognition = recognise(query, name=name)
    composition = recognition.composition
    network = composition.to_network()
    problems = network.problems()
    if problems:
        # Should be unreachable: every motif validates at import and every
        # wiring operator checks its own bindings. Raising rather than
        # returning keeps it that way -- a composed model that does not
        # validate is a bug here, not a user error.
        raise AssertionError(
            f"composed a network that does not validate, from {query!r}: "
            + "; ".join(problems)
        )

    return ComposedModel(
        query=query,
        recognition=recognition,
        network=network,
        resolvable=composition.quantities_to_resolve(),
        chosen=composition.chosen_quantities(),
        subject=subject,
        organism=organism,
        substrate=substrate,
    )


def compose_and_parameterise(
    query: str,
    *,
    subject: Optional[str] = None,
    resolve: Optional[Callable[..., Any]] = None,
    organism: Optional[str] = None,
    substrate: Optional[str] = None,
    simulate: Optional[Callable[[Any], Any]] = None,
) -> Tuple[ComposedModel, Any]:
    """Compose, then run the agent architecture over the result.

    Returns `(model, search_or_None)`. The search is None when no subject
    was named -- there is nothing to search for, and returning an empty
    `ModelSearch` would report a completed search over zero quantities as
    though the model were parameterised.
    """
    model = compose(query, subject=subject, organism=organism, substrate=substrate)
    requests = model.parameter_requests()
    if not requests:
        return model, None

    try:
        from Terium.agents.assembly import search_model
        from Terium.agents.scouts import brenda_resolver
    except ImportError:  # pragma: no cover
        from agents.assembly import search_model  # type: ignore
        from agents.scouts import brenda_resolver  # type: ignore

    search = search_model(
        network=model.network,
        requests=requests,
        resolve=resolve or brenda_resolver(),
        requested_organism=organism,
        simulate=simulate,
    )
    return model, search


__all__ = [
    "ComposedModel",
    "compose",
    "compose_and_parameterise",
    "UnrecognisedShape",
]
