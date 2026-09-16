"""Getting a composed model out of Terrium without laundering it on the way.

WHY AN EXPORT MODULE AT ALL
---------------------------
A model that exists only inside Terrium is not a model a lab can use. The
people this is built for run COPASI, Tellurium and JWS Online, they deposit
in BioModels, and they paste a methods paragraph into a manuscript. Every
one of those is a FILE, and until there is a file the composer's output is a
screenful of text that dies with the terminal session.

THE FAILURE THIS MODULE EXISTS TO PREVENT
-----------------------------------------
Not "no export". A working export that loses the provenance.

A composed model's numbers are of three kinds and they are not
interchangeable:

    measured      somebody published this number and there is a citation
    placeholder   the motif library's ILLUSTRATIVE value, present so the
                  structure can be checked and simulated. No paper supplies
                  it and nobody measured it
    chosen        a concentration or a Hill exponent. Nobody publishes how
                  much enzyme is in your tube (ADR 0013, ADR 0044), so this
                  is not a gap in a search -- it is the modeller's to set

Written into SBML, all three arrive as

    <parameter id="e1_Km" value="0.1" constant="true"/>

and are indistinguishable. The moment that file leaves Terrium the
distinction is gone and a placeholder has acquired the authority of the tool
it passed through. That is laundering; it is the thing this project exists
to prevent; and an export written without thinking about it is the most
efficient way to do it that Terrium has ever had.

So every artefact here states the origin of every number, and one string --
`PLACEHOLDER_MARKER` -- sits next to every unmeasured constant in every
format. One string rather than four sentences, because a marker four
exporters spell four ways is a marker three of them can lose, and
`Terium/tests/test_compose_export.py` asserts it in each.

WHAT EACH FORMAT CAN CARRY, AND WHAT IT CANNOT
----------------------------------------------
`to_sbml`
    SBML `<notes>` per parameter and per species, plus MIRIAM RDF CVTerms
    where a citation has a resolvable identifier. Structured, so a pipeline
    that never renders notes to a human still sees the citation. This is the
    format that travels furthest and therefore the one where the provenance
    matters most.

`to_antimony`
    Trailing `//` comments, Herbert Sauro's mechanism (see
    `core/model_provenance.py`). Readable, and it does NOT survive
    translation to SBML -- that is measured, not assumed, in
    `core/sbml_provenance.py`'s docstring. Antimony is the format a person
    opens; SBML is the format a program reads; the two exporters here put
    the same facts in each, in that format's own idiom, rather than one
    converting into the other and losing them.

`to_parameter_csv`
    The audit trail, and the only artefact of the four whose SUBJECT is the
    provenance rather than the model. Nothing else in this space produces
    it: a row per quantity saying which of the three kinds it is, what it is
    worth, in what unit, from which motif, and with what citation. It is
    what a reviewer asks for and what neither SBML nor Antimony makes easy
    to read off.

THE ASSAY CONDITIONS TRAVEL TOO
-------------------------------
Lisa Jeske (BRENDA curation, DSMZ) on what makes a resolved value
meaningless: pH, temperature, cofactors and buffers come from thousands of
different papers, and mixing values measured under different ones produces
"fantasy numbers". A cited Km whose conditions were dropped at the export
boundary is therefore not a smaller version of a good citation -- it is a
number the reader cannot judge, wearing the look of one that was checked.

So `Measurement` carries them and all three per-quantity formats print
them: the Antimony footer, the SBML `<notes>`, and four columns of the CSV.
The two annotators already render conditions in their own idiom, so nothing
here writes a third sentence about them -- and the conditions a source did
NOT state are named rather than omitted, because "the 1974 paper reported no
pH" sends a researcher to the bench while "Terrium has no pH" is a bug on
this side.

`to_methods_paragraph`
    Markdown for a manuscript. States the structure, reproduces each motif's
    own stated basis verbatim, and names every placeholder individually.
    Prose is the format most able to hide a caveat, so the placeholders get
    their own bold paragraph rather than a footnote.

WHAT IS REUSED, AND WHY THAT MATTERS MORE THAN IT USUALLY DOES
--------------------------------------------------------------
Nothing here writes SBML by hand. `core/network.py::compile_to_antimony`
renders the model, `continuous/model_building.py::antimony_to_sbml` does the
translation, `core/sbml_provenance.py::annotate_sbml` writes the annotations
and `audit_annotations` reads them back with an independent parser. Those
modules already learned, expensively, what a hand-rolled provenance encoder
gets wrong: RDF written against a metaid no element carries is silently
dropped, and `libsbml.checkConsistency()` reports nothing. A second
implementation here would be a second thing to be wrong, and the way it
would be wrong is invisible.

Hand-rolled XML is refused outright. If libSBML is absent, `to_sbml` raises
with the install line rather than emitting something that looks like SBML.
A subtly invalid file that COPASI opens anyway is worse than no file.

THE ONE THING ADDED TO THE ANTIMONY, AND WHY
--------------------------------------------
`compile_to_antimony` declares no `species` line, so Antimony infers what is
a species from the reactions. A motif's ENZYME appears only in rate laws --
it is neither consumed nor produced -- so Antimony makes it a parameter, and
a five-species composed model reaches SBML with four species and an enzyme
that no longer plots. Measured on a single catalytic step: 3 network species
in, 2 SBML species out.

So the exporters emit one extra line, `species <every species id>;`. Then
all of them arrive as species, Antimony attaches the enzyme as a reaction
MODIFIER on its own, and `libsbml.checkConsistency()` reports zero errors.
The line is a declaration, not a change: it renames nothing, adds no
reaction and alters no rate law.

UNITS ARE NOT DECLARED IN THE SBML, AND THE FILE SAYS SO
---------------------------------------------------------
`core/sbml_units.py::declare_units` exists and is deliberately not used
here. It refuses any domain outside `{"mm", "mm_competitive_inhibition"}`
and its vocabulary covers concentrations and `<conc>/s`; a composed model
carries `1/s`, `1/(mM*s)` and dimensionless exponents. Calling it would
produce a refusal, and hand-writing the `unitDefinition` blocks it declines
to write would be the invented declaration its docstring is about -- "a
wrong declared unit is worse than none, because a consumer trusts
declarations and merely guesses at absences".

So the SBML is unitless, the units live in the CSV's `unit` column where
they are exact, and the SBML's own model notes say that in those words. A
limitation stated inside the artefact is a limitation; one stated only in a
docstring is a trap for whoever receives the file.

WHAT THIS DOES NOT CLAIM
------------------------
**That an exported model is correct.** It says where each number came from.
A model whose every constant is a properly cited measurement in the wrong
organism is fully annotated and still not a model of anything you asked
about.

**That a citation supports the value attached to it.** Nothing here reads
the paper. A `Measurement` is trusted to be what its caller says it is, and
the artefacts report the caller's claim as the caller's claim.

**That the CSV is a certificate.** It is a statement of what Terrium was
told, laid out so that a reader can check it. Its value is that a
placeholder is visibly a placeholder, not that a measurement is verified.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple
from xml.sax.saxutils import escape

try:
    from .motifs import (
        CHOSEN_KINDS, KIND_CONCENTRATION, RESOLVABLE_KINDS,
    )
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        CHOSEN_KINDS, KIND_CONCENTRATION, RESOLVABLE_KINDS,
    )


class ExportRefused(RuntimeError):
    """An artefact was not written, and the reason says what to do instead.

    Deliberately not a warning and never a partially-written file. Every
    condition that raises this one is a condition where the artefact would
    have made a claim Terrium cannot support -- a placeholder presented as
    a measurement, a value in a unit nobody converted, an SBML file whose
    annotations an independent reader cannot follow.
    """


# ---------------------------------------------------------------------------
# The three origins, and the strings that carry them into every artefact
# ---------------------------------------------------------------------------

#: A number somebody published, with a citation.
ORIGIN_MEASURED = "measured"

#: The motif library's illustrative value. Not a measurement of anything.
ORIGIN_PLACEHOLDER = "placeholder"

#: A concentration or an exponent. The modeller's, and legitimately so.
ORIGIN_CHOSEN = "chosen"

ORIGINS = (ORIGIN_MEASURED, ORIGIN_PLACEHOLDER, ORIGIN_CHOSEN)

#: The one string every artefact puts next to an unmeasured constant.
#:
#: Upper case and searchable on purpose: a reader who greps one exported
#: file for it, and a reader who greps four, must find the same word. The
#: alternative -- each exporter phrasing the caveat in its own voice -- is
#: how three of the four end up phrasing it softly.
PLACEHOLDER_MARKER = "ILLUSTRATIVE PLACEHOLDER"

#: The counterpart for a quantity that is the modeller's to set. A DIFFERENT
#: fact from a placeholder and never folded into it: a missing measurement is
#: a gap somebody could close at the bench, while a starting amount is not
#: missing at all.
CHOSEN_MARKER = "CHOSEN, NOT MEASURED"

#: The counterpart for a value that came from the literature.
MEASURED_MARKER = "LITERATURE-DERIVED"

#: What to do when SBML export cannot run. Names the distribution AND the
#: import name, because `pip install libsbml` is a different, wrong package.
SBML_INSTALL_INSTRUCTION = (
    "pip install python-libsbml==5.21.1 antimony==2.14.0 "
    "(both are pinned in requirements.txt, so `make setup` installs them; "
    "python-libsbml imports as `libsbml`)"
)

#: The CSV's columns, in order. A constant rather than a literal in the
#: writer so a test can assert the header against the same list the exporter
#: emits, and so a column cannot be added to one and not the other.
CSV_COLUMNS = (
    "identifier",
    "role",
    "origin",
    "value",
    "unit",
    "kind",
    "resolvable_from_literature",
    "motif",
    "motif_symbol",
    "what_it_is",
    "source_table",
    "citation",
    "organism",
    "cross_species",
    "assay_ph",
    "assay_temperature_c",
    "assay_buffer",
    "assay_not_reported_by_source",
    "provenance",
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    """A published value, and enough to find where it was published.

    `citation` is required and empty strings are refused. A value with no
    citation is not a measurement as far as any artefact here is concerned
    -- it is a number of unstated origin, and the whole point of this module
    is that such a number must not be exported wearing a measurement's
    clothes. A caller holding one should pass it as nothing at all and let
    it be reported as a placeholder, which is what it is.
    """

    value: float
    unit: str
    citation: str
    organism: Optional[str] = None
    #: The resolution path, e.g. "brenda/km". How Terrium got there, as
    #: distinct from what the paper is.
    source: Optional[str] = None
    #: Registry and accession, already split by whoever looked them up.
    #: Supplied separately from `citation` because re-parsing a string
    #: Terrium formatted is parsing your own output, and it guessed wrong
    #: the first time it ran for real (see `core/sbml_provenance.py`).
    citation_source: Optional[str] = None
    reference_id: Optional[str] = None
    #: True when this was measured in a different organism than the one the
    #: model is about. Real, citable, and not a measurement of your organism.
    cross_species: bool = False

    #: The conditions the measurement was made under.
    #:
    #: Carried because Lisa Jeske (BRENDA curation, DSMZ) named exactly this
    #: as what makes a resolved value meaningless without it: pH,
    #: temperature, cofactors and buffers decide whether two values from two
    #: papers may be mixed at all. Terrium parses them, and an export that
    #: dropped them would hand a lab a cited number it cannot judge -- which
    #: is a subtler version of the same laundering, since a citation with no
    #: conditions looks exactly like one that was checked.
    #:
    #: Both annotators this module exports through already render these, so
    #: nothing here formats a third sentence about them: they are passed
    #: down and the CSV prints the raw values in columns of their own.
    assay_ph: Optional[float] = None
    assay_temperature_c: Optional[float] = None
    assay_buffer: Optional[str] = None
    #: Conditions the SOURCE did not state, named rather than omitted. "The
    #: 1974 paper did not report a pH" is permanent and sends a researcher to
    #: the bench; "Terrium has no pH" may be a parser bug on our side. The
    #: conclusion is the same and the action is not.
    assay_unreported: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.citation).strip():
            raise ExportRefused(
                "a Measurement was built with no citation. Terrium will not "
                "export a number as literature-derived without saying where "
                "the literature is: in an SBML file that value is "
                "indistinguishable from a measured one, which is the "
                "laundering this module exists to prevent. Supply the "
                "citation, or omit the quantity entirely and it is exported "
                f"as an {PLACEHOLDER_MARKER.lower()}."
            )


@dataclass(frozen=True)
class ParameterOrigin:
    """One number in the exported model, and where it came from.

    Covers species initial amounts as well as motif parameters. They are the
    same question -- "who decided this number?" -- and splitting them into
    two record types would let one exporter carry the species and another
    forget them, which is precisely how a starting amount ends up looking
    like a measured constant.
    """

    identifier: str
    origin: str
    #: The motif's KIND_* for a parameter; KIND_CONCENTRATION for a species
    #: initial, which is what a starting amount is.
    kind: str
    value: float
    unit: str
    #: "parameter" or "species initial amount".
    role: str
    #: The motif this belongs to, and its name inside that motif. Both empty
    #: only if the composition somehow produced a species no port created,
    #: which the builder makes impossible.
    motif: str = ""
    symbol: str = ""
    description: str = ""
    #: Which database table serves this quantity, when one does. `None` is
    #: not a failure: an mRNA degradation rate has no BRENDA table, and
    #: "never searchable there" and "searched and not found" are different
    #: sentences.
    table: Optional[str] = None
    measurement: Optional[Measurement] = None

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise ExportRefused(
                f"{self.identifier!r} was given origin {self.origin!r}, which "
                f"is not one of {ORIGINS}. Origin decides what every artefact "
                f"says about this number, so an unknown one has no defined "
                f"rendering and would be exported as whatever the last "
                f"`elif` happened to be."
            )
        if self.origin == ORIGIN_MEASURED and self.measurement is None:
            raise ExportRefused(
                f"{self.identifier!r} is marked measured and carries no "
                f"Measurement. Every artefact would then print a citation "
                f"column with nothing in it beside a value presented as "
                f"literature-derived."
            )
        if self.origin != ORIGIN_MEASURED and self.measurement is not None:
            raise ExportRefused(
                f"{self.identifier!r} carries a Measurement and is not marked "
                f"measured. One of the two is wrong and Terrium cannot tell "
                f"which, so it refuses rather than picking the reading that "
                f"makes the model look better sourced."
            )
        if self.origin == ORIGIN_MEASURED and self.kind in CHOSEN_KINDS:
            raise ExportRefused(
                f"{self.identifier!r} is a {self.kind} and cannot be "
                f"literature-derived. Nobody publishes how much enzyme is in "
                f"your tube, and a Hill exponent is a modelling choice rather "
                f"than a measurement of this system (ADR 0013, ADR 0044). A "
                f"citation attached to one would be a citation for a number "
                f"the paper does not contain."
            )
        if self.origin == ORIGIN_PLACEHOLDER and self.kind not in RESOLVABLE_KINDS:
            raise ExportRefused(
                f"{self.identifier!r} is a {self.kind} and cannot be a "
                f"placeholder: a placeholder is a measurement that is "
                f"MISSING, and nothing is missing for a quantity the "
                f"literature is never asked for. It is {ORIGIN_CHOSEN!r}."
            )

    @property
    def measured(self) -> bool:
        return self.origin == ORIGIN_MEASURED

    @property
    def placeholder(self) -> bool:
        return self.origin == ORIGIN_PLACEHOLDER

    @property
    def chosen(self) -> bool:
        return self.origin == ORIGIN_CHOSEN

    @property
    def resolvable(self) -> bool:
        """Whether the literature is asked for this quantity at all."""
        return self.kind in RESOLVABLE_KINDS

    def sentence(self) -> str:
        """This number's provenance, in one sentence.

        THE SINGLE DERIVATION for the three exporters that speak about one
        quantity at a time: the Antimony trailing comment, the SBML
        `<notes>` block, and the CSV's `provenance` column all call this.
        Each writing its own wording is how an exported file and its audit
        trail come to disagree about the same value, and the disagreement
        would be invisible in whichever format had the softer sentence.

        `to_methods_paragraph` does NOT call it, and that is deliberate
        rather than an omission: it groups the quantities BY origin under
        one heading each, so repeating a per-quantity sentence nine times
        would bury the list it exists to present. It renders the same three
        marker constants, so the words a reader greps for still cannot
        drift between the artefacts even though the sentences differ.
        """
        if self.measured:
            assert self.measurement is not None  # __post_init__ guarantees it
            parts = [f"{MEASURED_MARKER}: {self.measurement.citation}"]
            if self.measurement.cross_species:
                parts.append(
                    "CROSS-SPECIES, measured in "
                    + (self.measurement.organism or "a different organism")
                    + ", which is not the organism this model is about; real "
                    "and citable, and not a measurement of your organism"
                )
            elif self.measurement.organism:
                parts.append(f"measured in {self.measurement.organism}")
            if self.measurement.source:
                parts.append(f"resolved via {self.measurement.source}")
            parts.append(
                "Terrium did not read the paper: this is the origin it was "
                "given, not a verification of it"
            )
            return "; ".join(parts) + "."
        if self.placeholder:
            where = f"{self.motif}.{self.symbol}" if self.motif else self.symbol
            return (
                f"{PLACEHOLDER_MARKER}: Terrium's motif library value for "
                f"{where}. No publication supplies this number and nobody "
                f"measured it. It is here so the structure can be checked, "
                f"dimensioned and simulated"
                + (
                    f"; the measurement that would replace it is in the "
                    f"{self.table} table"
                    if self.table
                    else "; no database table serves it, so it is resolvable "
                    "only from a paper"
                )
                + "."
            )
        what = (
            "a starting amount"
            if self.role != "parameter"
            else f"a {self.kind.replace('_', ' ')}"
        )
        return (
            f"{CHOSEN_MARKER}: {what}, which is yours to set. No paper "
            f"supplies it, so its absence from the literature is not a gap "
            f"in this model."
        )


@dataclass(frozen=True)
class ProvenancedModel:
    """A composed model plus the origin of every number in it.

    The one object the four exporters take. They share it rather than each
    walking the composition, so a change to how an origin is decided reaches
    all four or none.

    `network` is rebuilt from the composition with the measured values
    substituted in, so the numbers in the exported model and the numbers in
    the audit trail cannot disagree. Handing the exporters a caller's
    network instead would allow exactly that disagreement, and the CSV --
    the artefact whose whole job is to be trustworthy about values -- is
    where it would be least detectable.
    """

    name: str
    network: Any
    composition: Any
    origins: Tuple[ParameterOrigin, ...]
    concentration_unit: str
    query: Optional[str] = None
    subject: Optional[str] = None

    @property
    def measured(self) -> Tuple[ParameterOrigin, ...]:
        return tuple(o for o in self.origins if o.measured)

    @property
    def unmeasured(self) -> Tuple[str, ...]:
        """Identifiers of every PARAMETER still a placeholder.

        The same name as `ComposedModel.unmeasured`, so a caller holding
        either can ask the one question that decides whether a number is
        the library's or the literature's, without knowing which class it
        has. Species starting amounts are excluded: they are scenario
        choices, not constants a search would return.
        """
        return tuple(
            o.identifier for o in self.origins
            if o.origin == ORIGIN_PLACEHOLDER and o.role == "parameter"
        )

    @property
    def placeholders(self) -> Tuple[ParameterOrigin, ...]:
        return tuple(o for o in self.origins if o.placeholder)

    @property
    def chosen(self) -> Tuple[ParameterOrigin, ...]:
        return tuple(o for o in self.origins if o.chosen)

    @property
    def motifs_used(self) -> Tuple[Tuple[str, str, int], ...]:
        """(motif name, its stated basis, how many copies), in order placed.

        The basis text is the motif's own, reproduced and never paraphrased.
        It is the sentence that says which approximation the model rests on,
        and a summary of it is a different claim.
        """
        seen: List[str] = []
        basis: Dict[str, str] = {}
        counts: Dict[str, int] = {}
        for instance in self.composition.instances:
            motif = instance.motif
            if motif.name not in basis:
                seen.append(motif.name)
                basis[motif.name] = motif.basis or motif.summary
            counts[motif.name] = counts.get(motif.name, 0) + 1
        return tuple((name, basis[name], counts[name]) for name in seen)

    def origin_of(self, identifier: str) -> ParameterOrigin:
        for origin in self.origins:
            if origin.identifier == identifier:
                return origin
        raise ExportRefused(
            f"no origin recorded for {identifier!r}; this model knows about "
            + ", ".join(o.identifier for o in self.origins)
        )


# ---------------------------------------------------------------------------
# Building the provenance
# ---------------------------------------------------------------------------


def provenance_of(
    source: Any,
    *,
    measured: Optional[Mapping[str, Measurement]] = None,
    name: Optional[str] = None,
) -> ProvenancedModel:
    """Decide the origin of every number in a composed model.

    `source` is a `Composition` or a `ComposedModel` (what `pipeline.compose`
    returns). `measured` maps a parameter id to what the literature said
    about it; anything resolvable and absent from it is a placeholder, and
    anything the motifs mark as a caller's choice is chosen no matter what.

    THE RULE, AND WHY IT IS READ OFF THE MOTIF RATHER THAN THE NAME
    --------------------------------------------------------------
    `MotifParameter.kind` decides. Not a regex on the identifier, not a
    lookup table of names that look like rate constants. A model may call a
    parameter `Km_glucose` or `n` or `E_total`, and a name-matching rule
    would classify the third as a rate constant on the strength of an
    underscore. The kind is declared where the biochemistry is, in
    `library.py`, and this module reads it.
    """
    composition, network, query, subject = _unpack(source)
    supplied: Dict[str, Measurement] = dict(measured or {})

    for identifier, value in supplied.items():
        if not isinstance(value, Measurement):
            raise ExportRefused(
                f"the measured value for {identifier!r} is a "
                f"{type(value).__name__}, not a Measurement. Terrium reads "
                f"the citation off that record and refuses to guess which "
                f"attribute of an unknown object holds it."
            )

    origins: List[ParameterOrigin] = []
    creators = _species_creators(composition)

    for species_id in composition.species_ids:
        if species_id in supplied:
            raise ExportRefused(
                f"a measured value was supplied for {species_id!r}, which is "
                f"a starting amount. A concentration is never a literature "
                f"quantity: no paper reports how much of it is in your tube, "
                f"and attaching a citation to one would cite a paper for a "
                f"number it does not contain. Set it with "
                f"`Composition.set_initial` instead."
            )
        instance, port = creators.get(species_id, (None, None))
        origins.append(
            ParameterOrigin(
                identifier=species_id,
                origin=ORIGIN_CHOSEN,
                kind=KIND_CONCENTRATION,
                value=float(_initial_of(network, species_id)),
                unit=composition.concentration_unit,
                role="species initial amount",
                motif=instance.motif.name if instance is not None else "",
                symbol=port.name if port is not None else species_id,
                description=(
                    port.description or f"{port.role} of {instance.motif.name}"
                    if port is not None and instance is not None
                    else ""
                ),
            )
        )

    for instance in composition.instances:
        for parameter in instance.motif.parameters:
            identifier = instance.parameter_id(parameter.name)
            measurement = supplied.pop(identifier, None)
            if measurement is not None and parameter.kind in CHOSEN_KINDS:
                raise ExportRefused(
                    f"a measured value was supplied for {identifier!r}, which "
                    f"{instance.motif.name!r} declares as a {parameter.kind}. "
                    f"That kind is the caller's choice rather than a "
                    f"published quantity, so a citation on it would be a "
                    f"citation for something the paper does not report."
                )
            if measurement is not None:
                _check_unit(identifier, measurement, parameter.unit)
                origin = ORIGIN_MEASURED
                value = float(measurement.value)
            elif parameter.kind in RESOLVABLE_KINDS:
                origin = ORIGIN_PLACEHOLDER
                value = float(parameter.default)
            else:
                origin = ORIGIN_CHOSEN
                value = float(parameter.default)
            origins.append(
                ParameterOrigin(
                    identifier=identifier,
                    origin=origin,
                    kind=parameter.kind,
                    value=value,
                    unit=parameter.unit,
                    role="parameter",
                    motif=instance.motif.name,
                    symbol=parameter.name,
                    description=parameter.description or parameter.name,
                    table=parameter.table,
                    measurement=measurement,
                )
            )

    if supplied:
        # The resolver and the model disagree about what was built. Reported
        # rather than dropped: a silent drop hands the caller a
        # complete-looking export that omits a quantity they believe they
        # sourced, and the omission looks like a property of the model.
        raise ExportRefused(
            "measured values were supplied for quantities this model does "
            "not contain: " + ", ".join(sorted(supplied)) + ". The resolver "
            "and the composition disagree about what was built, and "
            "exporting the model anyway would hide that behind an artefact "
            "that looks complete."
        )

    _refuse_case_collisions(origins)

    return ProvenancedModel(
        name=name or getattr(network, "name", composition.name),
        network=_with_measured_values(network, origins),
        composition=composition,
        origins=tuple(origins),
        concentration_unit=composition.concentration_unit,
        query=query,
        subject=subject,
    )


def measured_from_search(search: Any) -> Dict[str, Measurement]:
    """Turn what `Terium/agents` resolved into `Measurement`s.

    Reads only documented attributes of `ParameterSource` -- value, unit,
    organism, citation, cross_species, origin -- so this module does not
    have to import the agent stack to export a model the agent stack
    produced.

    Refuses a resolved value with no citation rather than exporting it as
    literature-derived. That is the one place this conversion could quietly
    manufacture authority, since a `ParameterSource` with `citation=None` is
    a perfectly ordinary object and every downstream artefact would print it
    in the measured column.

    `ParameterSource.origin` -- "literature", "user" or "registry" -- lands
    in `Measurement.source`, which is the coarsest true answer to "how did
    Terrium get here": that record holds no finer resolution path. So a
    value the user supplied reads as "resolved via user" in every artefact
    rather than being folded into the literature ones, which is the
    distinction `model_provenance.py` keeps under the name `user_cited`.
    """
    build = search if hasattr(search, "resolutions") else getattr(search, "build", None)
    if build is None:
        raise ExportRefused(
            "this search settled on no single model, so there is nothing to "
            "export. `ModelSearch.build` is None when more than one organism "
            "yields a complete model and nothing separates them, or when "
            "none does; assembling the first pass instead would hand you a "
            "model made of constants that describe no animal. Name the "
            "organism you want and search again."
        )

    out: Dict[str, Measurement] = {}
    for quantity, resolution in build.resolutions.items():
        source = getattr(resolution, "source", None)
        if source is None:
            continue
        citation = getattr(source, "citation", None)
        if not citation or not str(citation).strip():
            raise ExportRefused(
                f"{quantity} was resolved to {getattr(source, 'value', '?')} "
                f"with no citation recorded. Terrium will not export it as "
                f"literature-derived on the strength of having been through "
                f"a resolver: supply the citation, or leave the quantity out "
                f"and it is exported as an {PLACEHOLDER_MARKER.lower()}."
            )
        out[quantity] = Measurement(
            value=float(getattr(source, "value")),
            unit=str(getattr(source, "unit", "") or ""),
            citation=str(citation),
            organism=getattr(source, "organism", None),
            source=getattr(source, "origin", None),
            cross_species=bool(getattr(source, "cross_species", False)),
            assay_ph=getattr(source, "ph", None),
            assay_temperature_c=getattr(source, "temperature_c", None),
            assay_buffer=getattr(source, "buffer", None),
            assay_unreported=tuple(
                getattr(source, "explicitly_unreported", ()) or ()
            ),
        )
    return out


def _unpack(source: Any) -> Tuple[Any, Any, Optional[str], Optional[str]]:
    """(composition, network, query, subject) from whatever was passed."""
    composition = getattr(getattr(source, "recognition", None), "composition", None)
    if composition is not None:
        return (
            composition,
            composition.to_network(),
            getattr(source, "query", None),
            getattr(source, "subject", None),
        )
    if hasattr(source, "instances") and hasattr(source, "to_network"):
        return source, source.to_network(), None, None
    raise ExportRefused(
        f"cannot export a {type(source).__name__}: pass a Composition or the "
        f"ComposedModel that `Terium.compose.pipeline.compose` returns. The "
        f"exporters need the composition and not only the network, because "
        f"the network has forgotten which motif each parameter came from and "
        f"therefore whether the literature is asked for it."
    )


def _species_creators(composition: Any) -> Dict[str, Tuple[Any, Any]]:
    """species id -> the (instance, port) that created it.

    Derived from the id rather than read out of the builder's private
    bookkeeping: `Composition.add` names a created species
    `<prefix>_<port>`, so a species whose id is exactly that is the one that
    port made. If that naming rule ever changes the ids change with it, so
    this cannot drift into being subtly wrong while still matching.
    """
    creators: Dict[str, Tuple[Any, Any]] = {}
    for instance in composition.instances:
        for port in instance.motif.ports:
            bound = instance.species_for(port.name)
            if bound == f"{instance.prefix}_{port.name}":
                creators.setdefault(bound, (instance, port))
    return creators


def _initial_of(network: Any, species_id: str) -> float:
    for species in network.species:
        if species.id == species_id:
            return species.initial
    raise ExportRefused(
        f"the composition has a species {species_id!r} that the compiled "
        f"network does not. Those two must agree before anything is written."
    )


def _check_unit(identifier: str, measurement: Measurement, expected: str) -> None:
    if not measurement.unit.strip():
        raise ExportRefused(
            f"{identifier} was resolved with no unit, and the motif declares "
            f"it in {expected!r}. Terrium cannot check the two agree, and "
            f"substituting a number whose unit is unknown into a model whose "
            f"unit is known is how a value lands three orders of magnitude "
            f"out and still simulates."
        )
    if measurement.unit.strip() != expected.strip():
        raise ExportRefused(
            f"{identifier} was resolved in {measurement.unit!r} and this "
            f"model is built in {expected!r}. Terrium does not convert: the "
            f"factor is not always dimensionless (mM to mg/mL needs a "
            f"molecular weight) and guessing one would invent a quantity. "
            f"Convert it yourself and pass the converted value, saying so."
        )


def _refuse_case_collisions(origins: List[ParameterOrigin]) -> None:
    """Two identifiers differing only in case cannot be exported.

    Both annotators this module reuses fold case when they look provenance
    up -- `annotate_antimony` because the resolution layer says `km` and
    Antimony says `Km`, `annotate_sbml` for the same reason. SBML ids are
    case-sensitive, so a model holding both `a_Km` and `A_km` has two
    distinct quantities that the fold would collapse, and one value's origin
    would be attached to the other. That is the failure this whole module
    exists to prevent, arriving by the back door, so it refuses here rather
    than letting the annotators pick one.
    """
    by_lower: Dict[str, List[str]] = {}
    for origin in origins:
        by_lower.setdefault(origin.identifier.lower(), []).append(origin.identifier)
    collisions = sorted(
        names for names in by_lower.values() if len(names) > 1
    )
    if collisions:
        raise ExportRefused(
            "these identifiers differ only in case: "
            + "; ".join(", ".join(sorted(names)) for names in collisions)
            + ". Both provenance annotators Terrium exports through match "
            "case-insensitively, so one quantity's origin would be attached "
            "to the other. Rename one of the motif instance prefixes."
        )


def _with_measured_values(network: Any, origins: List[ParameterOrigin]) -> Any:
    """The network with resolved values substituted for the placeholders.

    Done here rather than through `Terium.agents.adapters.with_resolved_values`
    on purpose, and the difference is not stylistic. That function checks the
    resolved unit against the REQUEST's `expected_unit`, which may be absent;
    here the motif's own declared unit is in hand and is the authority, so
    `_check_unit` above can be unconditional. It also keeps this module
    importable without the agent stack, which matters because exporting a
    structure-only model is the commonest thing a reader does.
    """
    values = {o.identifier: o.value for o in origins if o.measured}
    if not values:
        return network
    return replace(
        network,
        parameters=tuple(
            replace(p, value=values[p.id]) if p.id in values else p
            for p in network.parameters
        ),
    )


# ---------------------------------------------------------------------------
# Antimony
# ---------------------------------------------------------------------------


def _antimony_source(model: ProvenancedModel) -> str:
    """The model as Antimony, with every species declared.

    See the module docstring: without the declaration Antimony infers
    species from reactions and a motif's enzyme -- which appears only in
    rate laws -- silently becomes a parameter.
    """
    try:
        from Terium.core.network import compile_to_antimony
    except ImportError:  # pragma: no cover - flat layout
        from core.network import compile_to_antimony  # type: ignore[no-redef]

    text = compile_to_antimony(model.network)
    lines = text.splitlines()
    if not lines or not lines[0].startswith("model "):
        raise ExportRefused(
            "compile_to_antimony did not emit a `model` header, so this "
            "exporter cannot tell where to declare the species. Its output "
            "shape changed and this module has to change with it."
        )
    ids = [s.id for s in model.network.species]
    lines.insert(1, "  species " + ", ".join(ids) + ";")
    return "\n".join(lines) + "\n"


def _antimony_provenance(model: ProvenancedModel) -> Dict[str, Any]:
    try:
        from Terium.core.model_provenance import ParameterProvenance
    except ImportError:  # pragma: no cover - flat layout
        from core.model_provenance import ParameterProvenance  # type: ignore[no-redef]

    out: Dict[str, Any] = {}
    for origin in model.origins:
        if origin.measured:
            assert origin.measurement is not None
            out[origin.identifier] = ParameterProvenance(
                origin="resolved",
                citation=origin.measurement.citation,
                organism=origin.measurement.organism,
                source=origin.measurement.source,
                cross_species=origin.measurement.cross_species,
                assay_ph=origin.measurement.assay_ph,
                assay_temperature_c=origin.measurement.assay_temperature_c,
                assay_buffer=origin.measurement.assay_buffer,
                assay_unreported=origin.measurement.assay_unreported,
                note=origin.sentence(),
            )
        elif origin.placeholder:
            # "default" is `model_provenance`'s word for a number no
            # publication supplied, and it renders as "DEFAULT, not sourced".
            # The note carries Terrium's own marker alongside it so one grep
            # finds every unmeasured constant across all four artefacts.
            out[origin.identifier] = ParameterProvenance(
                origin="default", note=origin.sentence()
            )
        else:
            out[origin.identifier] = ParameterProvenance(
                origin="user", note=origin.sentence()
            )
    return out


def to_antimony(model: ProvenancedModel) -> str:
    """The model as annotated Antimony source.

    Every assignment carries a trailing comment naming its origin, and the
    footer restates all of them in full. Reuses
    `core/model_provenance.py::annotate_antimony`, which guarantees the
    annotation changes no value -- `strip_annotations` is its asserted
    inverse.

    THIS FORMAT LOSES ITS PROVENANCE ON TRANSLATION TO SBML. Comments are
    not part of the SBML data model, so `antimony.getSBMLString` deletes
    every one of them; that is measured in `core/sbml_provenance.py`, not
    assumed. Use `to_sbml` for a file that will be translated, and do not
    convert this one by hand.
    """
    text = _antimony_source(model)
    try:
        from Terium.core.model_provenance import (
            NO_PROVENANCE_MARKER, annotate_antimony, parameters_in,
        )
    except ImportError:  # pragma: no cover - flat layout
        from core.model_provenance import (  # type: ignore[no-redef]
            NO_PROVENANCE_MARKER, annotate_antimony, parameters_in,
        )

    # Checked against the assignments themselves, not by searching the
    # output for the marker: `annotate_antimony`'s HEADER prints the marker
    # in its legend, so a text search reports every file as defective.
    known = {o.identifier.lower() for o in model.origins}
    orphaned = [
        name for name in parameters_in(text) if name.lower() not in known
    ]
    if orphaned:
        raise ExportRefused(
            "the compiled model assigns " + ", ".join(orphaned) + ", which "
            f"this module has no origin for, so the file would carry "
            f"{NO_PROVENANCE_MARKER!r} beside a real number. Every species "
            f"and parameter must appear in the origin table before anything "
            f"is written."
        )

    result = annotate_antimony(
        text, _antimony_provenance(model), query=model.query
    )
    if result.unannotated:
        raise ExportRefused(
            "provenance was recorded for quantities that have no assignment "
            "in the compiled model: " + ", ".join(result.unannotated) + ". "
            "The origin table and the model disagree about what was built."
        )
    return result.text


# ---------------------------------------------------------------------------
# SBML
# ---------------------------------------------------------------------------


def _require_sbml_toolchain() -> Tuple[Any, Any]:
    """Both libraries, or a refusal naming what to install.

    Checked here rather than at module import so the other three exporters
    work in an environment with neither. A hand-rolled XML fallback is not
    on the table: SBML that is subtly invalid but opens anyway in COPASI is
    worse than an error message, because the error message is read.
    """
    missing: List[str] = []
    libsbml = None
    antimony = None
    try:
        import libsbml as _libsbml  # noqa: F401

        libsbml = _libsbml
    except ImportError:
        missing.append("python-libsbml (imported as `libsbml`)")
    try:
        import antimony as _antimony  # noqa: F401

        antimony = _antimony
    except ImportError:
        missing.append("antimony")

    if missing:
        raise ExportRefused(
            "SBML export needs " + " and ".join(missing) + ", which "
            + ("is" if len(missing) == 1 else "are")
            + " not installed. Terrium will not hand-write the XML instead: "
            "an SBML file that is subtly invalid still opens in COPASI, and "
            "a model that loads wrong is worse than one that does not load. "
            "Install with: " + SBML_INSTALL_INSTRUCTION + ". The Antimony, "
            "CSV and methods exports need neither library and are available "
            "now."
        )
    return libsbml, antimony


def _sbml_provenance(model: ProvenancedModel) -> Dict[str, Any]:
    try:
        from Terium.core.sbml_provenance import SbmlParameterProvenance
    except ImportError:  # pragma: no cover - flat layout
        from core.sbml_provenance import (  # type: ignore[no-redef]
            SbmlParameterProvenance,
        )

    out: Dict[str, Any] = {}
    for origin in model.origins:
        if origin.measured:
            assert origin.measurement is not None
            out[origin.identifier] = SbmlParameterProvenance(
                origin="resolved",
                citation=origin.measurement.citation,
                citation_source=origin.measurement.citation_source,
                reference_id=origin.measurement.reference_id,
                organism=origin.measurement.organism,
                source=origin.measurement.source,
                cross_species=origin.measurement.cross_species,
                assay_ph=origin.measurement.assay_ph,
                assay_temperature_c=origin.measurement.assay_temperature_c,
                assay_buffer=origin.measurement.assay_buffer,
                assay_unreported=origin.measurement.assay_unreported,
                note=origin.sentence(),
            )
        elif origin.placeholder:
            out[origin.identifier] = SbmlParameterProvenance(
                origin="default", note=origin.sentence()
            )
        else:
            out[origin.identifier] = SbmlParameterProvenance(
                origin="user", note=origin.sentence()
            )
    return out


def _species_notes(origin: ParameterOrigin) -> str:
    """The XHTML `<notes>` body for one species.

    `annotate_sbml` annotates PARAMETERS. A species initial amount is just
    as much a number somebody decided, and leaving it bare would make the
    starting amounts the one part of an exported model that says nothing
    about itself -- in a file where every parameter beside them does.
    """
    heading = CHOSEN_MARKER if origin.chosen else PLACEHOLDER_MARKER
    rows = [f"<p><strong>{escape(heading)}</strong></p>",
            f"<p>{escape(origin.sentence())}</p>"]
    if origin.description:
        rows.append(f"<p>{escape(origin.description)}</p>")
    rows.append(
        f"<p>Terrium composed this model in {escape(origin.unit)}. This file "
        f"declares no units; see the note on the model itself.</p>"
    )
    return (
        '<body xmlns="http://www.w3.org/1999/xhtml">' + "".join(rows) + "</body>"
    )


def _model_notes(model: ProvenancedModel, annotation_summary: str) -> str:
    """What the file says about itself, before anyone reads a value."""
    placeholders = model.placeholders
    rows = ["<h1>TERRIUM PROVENANCE</h1>"]
    if model.query:
        rows.append(f"<p>Composed from: {escape(model.query)}</p>")
    rows.append(
        f"<p>Of the {len([o for o in model.origins if o.resolvable])} "
        f"constant(s) in this model that the literature could supply, "
        f"{len(model.measured)} carry a citation and {len(placeholders)} do "
        f"not.</p>"
    )
    if placeholders:
        rows.append(
            f"<p><strong>{escape(PLACEHOLDER_MARKER)}S, which are NOT "
            "measurements and which no publication supplies: "
            + escape(", ".join(o.identifier for o in placeholders))
            + ".</strong> They are the motif library's illustrative values, "
            "present so the structure can be checked and simulated. Any "
            "conclusion resting on them is a statement about the shape of "
            "the mechanism and not about a real system.</p>"
        )
    else:
        rows.append(
            "<p>No rate constant or affinity in this model is a placeholder; "
            "each carries its own citation in its notes.</p>"
        )
    rows.append(
        "<p>Starting amounts and any cooperativity exponents are the "
        "modeller's choices rather than literature values, and each says so "
        "in its own notes: "
        + escape(", ".join(o.identifier for o in model.chosen))
        + ".</p>"
    )
    rows.append(
        f"<p><strong>This file declares no units.</strong> Terrium composed "
        f"the model in {escape(model.concentration_unit)} with rate "
        f"constants in the units its motifs declare, and the SBML unit "
        f"vocabulary Terrium implements does not cover them. Declaring a "
        f"unit it had guessed would be worse than declaring none, because a "
        f"consumer trusts a declaration and merely guesses at an absence. "
        f"The exact unit of every quantity is in the accompanying parameter "
        f"CSV.</p>"
    )
    rows.append(f"<p>Annotation outcome: {escape(annotation_summary)}</p>")
    rows.append(
        "<p>Terrium states where each number came from. It does not claim "
        "the model is correct, and it did not read the cited papers.</p>"
    )
    return (
        '<body xmlns="http://www.w3.org/1999/xhtml">' + "".join(rows) + "</body>"
    )


def to_sbml(model: ProvenancedModel) -> str:
    """The model as SBML Level 3, with the provenance in the annotations.

    Refuses rather than hand-writing XML when libSBML or Antimony is absent
    -- see `_require_sbml_toolchain`.

    WHAT THE FILE CARRIES
    ---------------------
    Per parameter: SBML `<notes>` saying which of the three origins it has,
    plus MIRIAM `bqbiol:isDescribedBy` RDF where the citation has a
    resolvable identifier. Per species: `<notes>` saying the starting amount
    is the modeller's. On the model: the placeholder list, in those words.

    The RDF is read back by an independent parser (`audit_annotations`)
    before this returns, because libSBML will happily write RDF that libSBML
    then declines to read and `checkConsistency()` reports nothing.

    WHAT IT CANNOT CARRY
    --------------------
    Units, for the reason the module docstring gives, and the model notes
    say so inside the file rather than only here.
    """
    libsbml, _antimony = _require_sbml_toolchain()

    try:
        from Terium.continuous.model_building import antimony_to_sbml
        from Terium.core.sbml_provenance import annotate_sbml, audit_annotations
    except ImportError:  # pragma: no cover - flat layout
        from continuous.model_building import (  # type: ignore[no-redef]
            antimony_to_sbml,
        )
        from core.sbml_provenance import (  # type: ignore[no-redef]
            annotate_sbml, audit_annotations,
        )

    # The UNANNOTATED Antimony is translated. Comments do not survive the
    # trip, so annotating first would be effort spent on something the
    # translator deletes -- and the same facts in two encodings in one file
    # rot apart. SBML gets them in SBML's own idiom below.
    outcome = annotate_sbml(
        antimony_to_sbml(_antimony_source(model)), _sbml_provenance(model)
    )
    if outcome.unannotated:
        raise ExportRefused(
            "these SBML parameters reached the file with no provenance: "
            + ", ".join(sorted(outcome.unannotated))
            + ". An unannotated parameter beside annotated ones reads as one "
            "that was fine, which is the most likely way an unsourced number "
            "escapes into somebody else's paper."
        )

    document = libsbml.readSBMLFromString(outcome.sbml)
    if document.getLevel() != 3:
        raise ExportRefused(
            f"the translation produced SBML Level {document.getLevel()}, and "
            f"this exporter promises Level 3. Antimony chooses the level; "
            f"nothing here silently converts one, because a down-conversion "
            f"can drop constructs and would do it quietly."
        )
    sbml_model = document.getModel()
    if sbml_model is None:
        raise ExportRefused("the translation produced a document with no model.")

    by_id = {o.identifier: o for o in model.origins}
    unannotated_species: List[str] = []
    for index in range(sbml_model.getNumSpecies()):
        species = sbml_model.getSpecies(index)
        origin = by_id.get(species.getId())
        if origin is None:
            unannotated_species.append(species.getId())
            continue
        if species.setNotes(_species_notes(origin)) != libsbml.LIBSBML_OPERATION_SUCCESS:
            raise ExportRefused(
                f"libSBML refused the notes for species {species.getId()!r}. "
                f"Writing the file without them would leave a starting "
                f"amount as the one number in it that says nothing about "
                f"itself."
            )
    if unannotated_species:
        raise ExportRefused(
            "these SBML species have no origin recorded: "
            + ", ".join(sorted(unannotated_species))
            + ". The composition and the translated model disagree about "
            "what this model contains."
        )

    # appendNotes, not setNotes: annotate_sbml has already written the data
    # sources' licence attribution here, and replacing it would ship
    # BRENDA-derived values with no licence statement.
    if sbml_model.appendNotes(
        _model_notes(model, outcome.summary().replace("\n", " "))
    ) != libsbml.LIBSBML_OPERATION_SUCCESS:
        raise ExportRefused(
            "libSBML refused the model-level provenance notes. That block "
            "names every placeholder in the file, so a document without it "
            "presents them exactly like the measured values."
        )

    written = libsbml.writeSBMLToString(document)

    # The second pass rewrote the document, so the RDF is re-checked with
    # the independent reader rather than trusted because it was valid before.
    audit = audit_annotations(written)
    if not audit.ok:
        raise ExportRefused(
            "after the species and model notes were added, the MIRIAM "
            "annotations are no longer ones an independent RDF reader can "
            "follow: " + "; ".join(audit.problems)
        )
    if len(audit.triples) < outcome.cvterms_written:
        raise ExportRefused(
            f"{outcome.cvterms_written} RDF term(s) were written and an "
            f"independent reader finds {len(audit.triples)}. Citations have "
            f"been lost between the annotator and the file."
        )
    return written


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _cell(measurement: Optional[Measurement], field: str) -> str:
    """One assay-condition cell: the value, or empty when there is none.

    Empty rather than "unknown": a CSV cell reading "unknown" is a value a
    spreadsheet will sort and a script will compare, and the difference
    between "the source was silent" and "there is no measurement here at
    all" is carried by the `origin` column beside it.
    """
    if measurement is None:
        return ""
    value = getattr(measurement, field)
    if value is None:
        return ""
    return f"{value:g}" if isinstance(value, float) else str(value)


def to_parameter_csv(model: ProvenancedModel) -> str:
    """Every number in the model, one row each, with where it came from.

    The artefact nothing else produces, and the one a reviewer should ask
    for. SBML and Antimony are models that happen to carry provenance; this
    IS the provenance, in the form a person can sort and a script can diff.

    One row per species initial amount and per parameter, with no exceptions
    and no summary rows: a reader must be able to check the row count
    against the model and find nothing missing. A commented preamble would
    be friendlier to read and would break `csv.reader`, so the caveats live
    in the `provenance` column of each row, where they cannot be separated
    from the value they qualify.

    `origin` is one of `measured`, `placeholder`, `chosen`, and the
    `provenance` column spells out what that means for that row.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for origin in model.origins:
        measurement = origin.measurement
        writer.writerow(
            [
                origin.identifier,
                origin.role,
                origin.origin,
                repr(origin.value),
                origin.unit,
                origin.kind,
                "yes" if origin.resolvable else "no",
                origin.motif,
                origin.symbol,
                origin.description,
                origin.table or "",
                measurement.citation if measurement else "",
                (measurement.organism if measurement else "") or "",
                "yes" if measurement and measurement.cross_species else "no",
                _cell(measurement, "assay_ph"),
                _cell(measurement, "assay_temperature_c"),
                _cell(measurement, "assay_buffer"),
                ", ".join(measurement.assay_unreported) if measurement else "",
                origin.sentence(),
            ]
        )
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Methods paragraph
# ---------------------------------------------------------------------------


def _quantity_line(origin: ParameterOrigin) -> str:
    return f"`{origin.identifier}` = {origin.value:g} {origin.unit}".rstrip()


def to_methods_paragraph(model: ProvenancedModel) -> str:
    """A Markdown methods section, ready to paste into a manuscript.

    States the structure, reproduces each motif's own basis text verbatim,
    and then lists the constants BY ORIGIN with the placeholders named
    individually.

    WHY THE PLACEHOLDERS GET THEIR OWN PARAGRAPH
    --------------------------------------------
    Prose is the format most able to hide a caveat, and a methods section is
    the artefact most likely to be skimmed by someone deciding whether to
    believe a figure. "Parameters were taken from the literature where
    available" is the sentence this replaces: it is true, it is what people
    write, and it leaves a reader unable to tell which numbers those were.
    Naming each placeholder costs a line and removes the ambiguity.

    A model with no placeholders says so explicitly rather than omitting the
    paragraph. An absent caveat and a satisfied one look identical, and only
    one of them is good news.
    """
    network = model.network
    resolvable = [o for o in model.origins if o.resolvable]
    lines: List[str] = ["## Methods", ""]

    instances = list(model.composition.instances)
    described = ", ".join(
        f"{name} (x{count})" if count > 1 else name
        for name, _basis, count in model.motifs_used
    )
    opening = (
        f"The model `{model.name}` was assembled with Terrium's "
        f"compositional model builder from {len(instances)} motif "
        f"instance(s) -- {described} -- giving {len(network.species)} "
        f"species, {len(network.reactions)} reaction(s) and "
        f"{len(network.parameters)} parameter(s)."
    )
    if model.query:
        opening += f' The structure was composed from the description "{model.query}".'
    if model.subject:
        opening += f" Constants were sought for {model.subject}."
    lines += [opening, ""]

    for note in getattr(model.composition, "notes", ()):
        lines.append(f"- {str(note).rstrip('.')}.")
    if getattr(model.composition, "notes", ()):
        lines.append("")

    laws = _conservation_laws(network)
    if laws:
        lines += [
            "The following are conserved and were derived from the model's "
            "own stoichiometry rather than asserted: "
            + ", ".join(f"`{law}`" for law in laws)
            + ".",
            "",
        ]

    lines += ["### Assumptions each motif carries", ""]
    for name, basis, _count in model.motifs_used:
        lines.append(f"- **{name}** -- {basis}")
    lines.append("")

    lines += ["### Where every constant came from", ""]

    if model.measured:
        lines.append(
            f"**{MEASURED_MARKER} ({len(model.measured)} of "
            f"{len(resolvable)}).** Each of the following was taken from the "
            f"cited source; Terrium recorded the citation and did not verify "
            f"that the source reports the value:"
        )
        lines.append("")
        for origin in model.measured:
            assert origin.measurement is not None
            detail = origin.measurement.citation
            if origin.measurement.cross_species:
                detail += (
                    ", CROSS-SPECIES: measured in "
                    + (origin.measurement.organism or "another organism")
                    + ", not in the organism this model is about"
                )
            elif origin.measurement.organism:
                detail += f", measured in {origin.measurement.organism}"
            lines.append(f"- {_quantity_line(origin)} ({detail})")
        lines.append("")
    elif resolvable:
        lines += [
            f"**No constant in this model was taken from the literature.** "
            f"All {len(resolvable)} of its rate constants and affinities are "
            f"{PLACEHOLDER_MARKER.lower()}s, listed below.",
            "",
        ]

    if model.placeholders:
        lines.append(
            f"**{PLACEHOLDER_MARKER}S ({len(model.placeholders)} of "
            f"{len(resolvable)}). These are not measurements. No publication "
            f"supplies them and nobody measured them; they are Terrium's "
            f"motif library values, present so that the structure could be "
            f"checked, dimensioned and simulated:**"
        )
        lines.append("")
        for origin in model.placeholders:
            where = f"{origin.motif}.{origin.symbol}"
            table = (
                f"the {origin.table} table would supply it"
                if origin.table
                else "no database table serves it; it is resolvable only "
                "from a paper"
            )
            lines.append(f"- {_quantity_line(origin)} -- {where}; {table}")
        lines += [
            "",
            "Any result that depends on these values is a statement about "
            "the shape of the mechanism rather than about a particular real "
            "system, and should be read as one.",
            "",
        ]
    elif resolvable:
        lines += [
            f"**No {PLACEHOLDER_MARKER.lower()}s remain**: every rate "
            f"constant and affinity in this model carries a citation above.",
            "",
        ]

    lines.append(
        f"**{CHOSEN_MARKER} ({len(model.chosen)}).** Starting amounts and "
        f"any cooperativity exponents are the modeller's, not the "
        f"literature's -- no paper reports how much enzyme is in a "
        f"particular tube, so their absence from the literature is not a gap "
        f"in this model: "
        + ", ".join(_quantity_line(o) for o in model.chosen)
        + "."
    )
    lines += [
        "",
        "The parameter-by-parameter audit trail, including the source table "
        "each unmeasured constant would come from, accompanies this model as "
        "a CSV.",
    ]
    return "\n".join(lines) + "\n"


def _conservation_laws(network: Any) -> List[str]:
    try:
        from Terium.core.network import describe_conservation_laws
    except ImportError:  # pragma: no cover - flat layout
        from core.network import (  # type: ignore[no-redef]
            describe_conservation_laws,
        )
    return list(describe_conservation_laws(network))


__all__ = [
    "CHOSEN_MARKER",
    "CSV_COLUMNS",
    "ExportRefused",
    "MEASURED_MARKER",
    "Measurement",
    "ORIGINS",
    "ORIGIN_CHOSEN",
    "ORIGIN_MEASURED",
    "ORIGIN_PLACEHOLDER",
    "PLACEHOLDER_MARKER",
    "ParameterOrigin",
    "ProvenancedModel",
    "SBML_INSTALL_INSTRUCTION",
    "measured_from_search",
    "provenance_of",
    "to_antimony",
    "to_methods_paragraph",
    "to_parameter_csv",
    "to_sbml",
]
