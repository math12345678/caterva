"""Provenance that survives the trip out of Caterva.

`model_provenance.py` writes each parameter's origin into the Antimony as a
trailing comment. That is Sauro's mechanism and it is the right one *for a
file a person reads*. It has one hard limit, measured rather than assumed:

    text = annotate_antimony(model, provenance)
    sbml = antimony.getSBMLString(...)
    'BRENDA' in sbml   -> False
    '649716' in sbml   -> False
    'Homo sapiens' in sbml -> False

Comments are not part of the SBML data model, so translation deletes all of
it. SBML is what COPASI, JWS Online, Tellurium and every BioModels
deposition actually read. Provenance that dies at the export boundary is
provenance that never leaves this tool.

This module puts it back, in the form the standard defines:

* **RDF/CVTerm annotations** (MIRIAM; Le Novère et al. 2005) for the parts
  that have resolvable identifiers -- `bqbiol:isDescribedBy` for a
  publication, `bqbiol:hasTaxon` for the organism a value was measured in.
  Machine-actionable, and read by other tools without being told to.
* **SBML `<notes>`** for everything else, in XHTML. That includes the parts
  with no URI form at all, which is not a small category: a BRENDA
  reference id has no identifiers.org representation (see `miriam.py`), and
  neither does "you supplied this value".

## Why both, rather than notes alone

Notes are prose. A reader sees them; a pipeline does not. Cross-species
substitution is exactly the fact that must survive being processed by
something that never displays notes to anyone, so the *warning* travels as
structure, not only as a sentence.

## Why both, rather than CVTerms alone

A CVTerm can only say things that have identifiers. "This value was
measured in a different organism from the one requested, and is therefore
not a measurement of your organism" has no ontology term. Dropping what
cannot be encoded, and keeping only what can, would quietly reshape the
provenance into whatever RDF happens to support -- and the discarded part
is the part that carries the warnings.

## What this does NOT claim

That an annotated model is *correct*. It says where the numbers came from.
A model built entirely from cross-species values, every one properly
annotated as such, is fully annotated and still not a model of the organism
its author had in mind.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape

try:
    import libsbml
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "libsbml is required to annotate SBML. It is a direct pin in "
        "requirements.txt; run `make setup`."
    ) from exc

from . import data_sources
from .miriam import identifiers_in, mint

#: Written into the model notes when a parameter reached SBML with nothing
#: known about it. Mirrors model_provenance.NO_PROVENANCE_MARKER so the two
#: exports cannot disagree about what "unknown" looks like.
NO_PROVENANCE_MARKER = "NO PROVENANCE RECORDED"

XHTML = "http://www.w3.org/1999/xhtml"


@dataclass(frozen=True)
class SbmlParameterProvenance:
    """What can be said about one parameter, in SBML's vocabulary.

    Deliberately separate from `model_provenance.ParameterProvenance`.
    That one describes what to *print*; this one describes what can be
    *encoded*, and the two differ in exactly the place that matters:
    `taxon_id`.

    `organism` is a name. A name is not an identifier -- "Homo sapiens" does
    not become taxonomy:9606 without a lookup, and guessing the number from
    the string is how a model ends up asserting a taxon nobody resolved. So
    the taxon annotation is emitted **only** when `taxon_id` is supplied by
    something that actually looked it up (`Tests/taxonomy.py`), and the
    organism name alone lands in the notes.
    """

    origin: str
    citation: str | None = None
    #: The registry and accession, already split by the caller. Preferred
    #: over re-parsing `citation`: that string is FORMATTED by Caterva, so
    #: extracting identifiers back out of it is parsing your own output.
    #: The first end-to-end run wrote zero annotations because
    #: "PubMed ref 12345678" did not match a pattern written against
    #: "PubMed 12345678".
    citation_source: str | None = None
    reference_id: str | None = None
    organism: str | None = None
    #: NCBI Taxonomy id, from a real lookup. None means "not resolved",
    #: never "assume from the name".
    taxon_id: str | None = None
    source: str | None = None
    cross_species: bool = False
    #: (axis, grade, reason) triples. The reason was dropped for a while
    #: and only the grade travelled -- so an exported model said
    #: "assay completeness: complete" and never what that meant. A grade is
    #: a token; the reason is the sentence someone learns from, and it costs
    #: nothing to carry in a file nobody has to read.
    reliability: tuple[tuple[str, str, str], ...] = ()
    note: str | None = None

    #: The conditions the measurement was made under.
    #:
    #: WHY THESE TRAVEL IN THE FILE
    #: ----------------------------
    #: Lisa Jeske (BRENDA curation, DSMZ) on what makes a resolved value
    #: meaningless:
    #:
    #:     Reaction conditions: pH value, temperature, cofactors, and
    #:     buffers play a huge role in the reactions. The values in BRENDA
    #:     come from thousands of different papers, each with different
    #:     laboratory conditions. If you simply mix these together, the
    #:     simulation will end up calculating with "fantasy numbers".
    #:
    #: Caterva parses all of this (ADR 0010, ADR 0026, ADR 0028) and it
    #: reached the screen. It did NOT reach the exported model. Measured
    #: before this existed, the notes on an exported Km read:
    #:
    #:     Reliability [...] assay completeness: complete -- pH and
    #:     temperature both reported
    #:
    #: which tells a reader the conditions exist and not what they were.
    #: The artifact is the thing that outlives the terminal session -- it
    #: is shared, attached to a report, opened months later -- so it is
    #: precisely where Jeske's sentence needed to survive, and it was the
    #: one place it did not. Herbert Sauro's mechanism is the same point
    #: from the other side: the assumption travels inside the artifact, not
    #: in a console.
    assay_ph: float | None = None
    assay_temperature_c: float | None = None
    assay_buffer: str | None = None

    #: Conditions the SOURCE did not state, named rather than omitted.
    #:
    #: `assay_ph=None` alone is ambiguous between "the paper did not report
    #: it" and "Caterva did not look". An omitted line in a document reads
    #: as an oversight; a line saying the source is silent is a fact about
    #: the source, and it is the fact ADR 0010 exists to preserve.
    assay_unreported: tuple[str, ...] = ()


@dataclass
class AnnotationOutcome:
    """What was written, and — equally — what could not be."""

    sbml: str
    annotated: list[str]
    #: Parameters present in the SBML with no provenance supplied.
    unannotated: list[str]
    #: (parameter, accession, why) for identifiers Caterva declined to mint.
    refused_uris: list[tuple[str, str, str]]
    cvterms_written: int
    #: How many RDF triples an INDEPENDENT parser finds in `sbml`.
    #:
    #: Reported alongside `cvterms_written` rather than instead of it,
    #: because they answer different questions -- what was intended, and
    #: what a consumer will actually see. `annotate_sbml` refuses to return
    #: when the second is smaller than the first, so a caller reading only
    #: `cvterms_written` is not misled; this field is here so the
    #: independently measured number reaches the reader too, instead of
    #: being computed at the boundary and discarded.
    triples_read_back: int = 0

    def summary(self) -> str:
        lines = [
            f"{len(self.annotated)} parameter(s) annotated, "
            f"{self.cvterms_written} RDF term(s) written "
            f"({self.triples_read_back} read back by an independent parser).",
        ]
        if self.unannotated:
            lines.append(
                f"{len(self.unannotated)} parameter(s) carry no provenance: "
                + ", ".join(sorted(self.unannotated))
            )
        if self.refused_uris:
            lines.append(
                f"{len(self.refused_uris)} identifier(s) had no resolvable "
                "URI form and travel as text instead:"
            )
            for name, accession, why in self.refused_uris:
                lines.append(f"  {name}: {accession} -- {why}")
        return "\n".join(lines)


#: Terrium's origin -> the ECO term stating HOW the value is known.
#:
#: John Gennari, asked whether there is an accepted way to mark an
#: annotation as computed rather than taken from a source (personal
#: communication, 2026-08-27):
#:
#:   "Yes! There is an established way to indicate an annotation is computed
#:    and predicted rather than 'from the source': An evidence code."
#:
#: This is also the one CVTerm use Frank Bergmann's advice positively
#: endorses (ADR 0181). He warned that provenance PROSE in a CVTerm "changes
#: the semantic intent ... tools reading them would expect them to be
#: ontology-based". An ECO term is ontology-based: it is a class from a
#: published ontology, resolvable, and means the same thing to every reader.
#: Prose stays in notes; identity stays in isDescribedBy/hasTaxon; how the
#: value is KNOWN becomes its own term.
#:
#: WHY ONLY ONE ORIGIN APPEARS HERE
#: --------------------------------
#: Terrium has four origins and only `resolved` gets a term.
#:
#:   resolved  a measurement curated from a publication -> ECO:0000269
#:   user      the person chose it                      -> NO TERM, on purpose
#:   llm       a language model produced it             -> never exported
#:   default   nothing was found                        -> never exported
#:
#: `user` is not weakly-evidenced; it is not evidence at all. An s0 of 10 mM
#: is a condition of the experiment being run, not a claim about the world,
#: and there is nothing for an evidence ontology to say about it. ECO:0000035
#: ("no evidence data found") would be wrong: nobody looked for evidence,
#: because none was called for. Leaving it unannotated is the accurate
#: statement, and the notes already say the value was supplied.
#:
#: `llm` and `default` block the run (ADR 0011), so a model carrying one
#: never reaches this exporter. Mapping them would be describing a case that
#: cannot occur.
#:
#: Labels verified against the EBI Ontology Lookup Service on 2026-08-28,
#: not recalled: ECO:0000269 is "experimental evidence used in manual
#: assertion" -- experimental because BRENDA's rows come from measurements,
#: manual because a curator made the assertion.
_ECO_FOR_ORIGIN = {"resolved": "ECO:0000269"}

#: Registry name (as the resolvers spell it) -> identifiers.org prefix.
#: Only registries whose accessions have a resolvable URI appear here.
#: BRENDA is absent on purpose: its namespace is EC numbers, and a BRENDA
#: reference id has no URI form at all.
_REGISTRY_PREFIX = {"pubmed": "pubmed", "doi": "doi"}


def _identifiers_for(prov: SbmlParameterProvenance) -> list[tuple[str, str]]:
    """Structured fields first; free text only as a fallback.

    A caller that split the citation already knows the answer, and asking
    it is exact. Re-deriving from prose is a guess about a string format,
    and it guessed wrong the first time it ran for real.
    """
    if prov.citation_source and prov.reference_id:
        prefix = _REGISTRY_PREFIX.get(prov.citation_source.strip().lower())
        if prefix:
            return [(prefix, prov.reference_id.strip())]
        # A known-but-unmintable registry (BRENDA) or an unknown one. Fall
        # through to the text scan rather than returning nothing: the
        # citation may still name a PMID alongside the reference id.
    return identifiers_in(prov.citation or "")


def _assay_sentences(prov: SbmlParameterProvenance) -> tuple[str, str]:
    """(what was measured, what the source did not state).

    Two strings rather than one, because they are two different facts and
    collapsing them is how "we were not told" starts reading as "it does
    not matter". Either may be empty; both empty means the source said
    nothing and nothing was recorded about its silence either, which is
    itself distinct from a source that explicitly reported nothing.

    ONE DERIVATION. `assayCoherence.ts` compares these conditions ACROSS
    parameters and this renders them for one -- if both formatted their own
    sentence from the same fields there would be two spellings of one
    measurement in one project, which is ADR 0003. This returns fragments
    and does not name the parameter, so it composes rather than competes.
    """
    measured: list[str] = []
    if prov.assay_ph is not None:
        measured.append(f"pH {prov.assay_ph:g}")
    if prov.assay_temperature_c is not None:
        measured.append(f"{prov.assay_temperature_c:g} °C")
    if prov.assay_buffer:
        measured.append(f"in {prov.assay_buffer}")

    # Deduplicated against what IS present. A source cannot both report a
    # pH and be silent about it, and a payload saying so is a contradiction
    # a reader should not be shown -- `test_a_condition_cannot_be_both`
    # pins this, and it is the shape a hand-built payload arrives in.
    present = {
        "ph": prov.assay_ph is not None,
        "temperature": prov.assay_temperature_c is not None,
        "buffer": bool(prov.assay_buffer),
    }
    silent = [
        item
        for item in prov.assay_unreported
        if not present.get(str(item).strip().lower(), False)
    ]
    return ", ".join(measured), ", ".join(str(s) for s in silent)


#: STRENDA requires temperature and pH for all reported kinetic data, which
#: is what an "assay completeness: complete" grade asserts. Named here so
#: the check below is about the standard rather than about two strings that
#: happen to be nearby.
_COMPLETENESS_REQUIRES = ("ph", "temperature")


def _completeness_discrepancy(prov: SbmlParameterProvenance) -> str | None:
    """When the graded axis and the conditions in the same file disagree.

    The notes carry a grade -- "assay completeness: complete -- pH and
    temperature both reported" -- and, now, the conditions themselves. Two
    encodings of one fact in one document, which is ADR 0003's subject, and
    they can disagree in two quite different ways:

    * the source WAS silent about a condition, and the grade still says
      complete -- the grade is wrong, and a reader trusting it would
      believe the value is reproducible when it is not;
    * the conditions were simply never handed to this export -- the grade
      may be perfectly right, and the file still cannot show its working.

    Those need different sentences, because the first is a defect in the
    scoring and the second is a defect in the payload, and telling a reader
    "inconsistent" without saying which would leave them unable to act.

    Returns None when the grade claims nothing, which is the common case.
    """
    claims_complete = any(
        "assay" in axis.lower() and grade.strip().lower() in {"complete", "full"}
        for axis, grade, _ in prov.reliability
    )
    if not claims_complete:
        return None

    held = {"ph": prov.assay_ph is not None, "temperature": prov.assay_temperature_c is not None}
    absent = [field for field in _COMPLETENESS_REQUIRES if not held[field]]
    if not absent:
        return None

    declared_silent = {str(item).strip().lower() for item in prov.assay_unreported}
    contradicted = [field for field in absent if field in declared_silent]

    if contradicted:
        return (
            "The assay-completeness grade says this measurement is complete, "
            f"while the same record states the source did not report "
            f"{', '.join(contradicted)}. Both cannot be true. Trust the "
            "statement about the source: a grade is a summary, and this is "
            "the thing summarised."
        )
    return (
        "The assay-completeness grade says this measurement is complete, but "
        f"the conditions themselves ({', '.join(absent)}) were not supplied to "
        "this export, so this file cannot show what they were. The grade may "
        "be right; nothing here demonstrates it."
    )


def _notes_xhtml(name: str, prov: SbmlParameterProvenance | None) -> str:
    """The human-readable half, as valid XHTML."""
    rows: list[str] = []

    if prov is None:
        rows.append(f"<p>{NO_PROVENANCE_MARKER}. Caterva was given no origin "
                    f"for <code>{escape(name)}</code>.</p>")
        return f'<body xmlns="{XHTML}">' + "".join(rows) + "</body>"

    if prov.origin == "user_cited":
        rows.append(
            "<p><strong>Cited by the user, unverified by Caterva.</strong> "
            "Caterva did not check that the named source reports this "
            "value.</p>"
        )
    elif prov.origin == "user":
        rows.append("<p><strong>Supplied by the user.</strong> Not a "
                    "literature value.</p>")
    elif prov.origin == "default":
        rows.append("<p><strong>Default, not sourced from any "
                    "publication.</strong></p>")
    elif prov.origin == "llm":
        rows.append("<p><strong>Produced by a language model.</strong> Not a "
                    "measurement.</p>")

    if prov.cross_species:
        # Structural too (SBO/qualifier cannot express it), but the sentence
        # has to be here as well: a reader of the notes must not have to
        # cross-reference an RDF block to learn the value is not theirs.
        rows.append(
            "<p><strong>CROSS-SPECIES.</strong> Measured in "
            f"{escape(prov.organism or 'a different organism')}, which is "
            "not the organism this model is about. Real and citable, and "
            "not a measurement of your organism.</p>"
        )
    elif prov.organism:
        rows.append(f"<p>Measured in {escape(prov.organism)}.</p>")

    # The conditions, before the citation: a reader deciding whether this
    # number applies to their experiment needs them earlier than they need
    # the reference id.
    measured, silent = _assay_sentences(prov)
    if measured:
        rows.append(f"<p>Measured at {escape(measured)}.</p>")
    if silent:
        rows.append(
            f"<p><strong>Not reported by the source: {escape(silent)}.</strong> "
            "A kinetic value cannot be reproduced or compared without them "
            "(STRENDA). This is a statement about the publication, not an "
            "omission by Caterva.</p>"
        )

    if prov.citation:
        rows.append(f"<p>Source: {escape(prov.citation)}</p>")
    if prov.source:
        rows.append(f"<p>Resolution path: <code>{escape(prov.source)}</code></p>")
    if prov.note:
        rows.append(f"<p>{escape(prov.note)}</p>")

    if prov.reliability:
        items = "".join(
            f"<li><strong>{escape(axis)}: {escape(grade)}</strong>"
            + (f" &#8212; {escape(reason)}" if reason else "")
            + "</li>"
            for axis, grade, reason in prov.reliability
        )
        rows.append(
            "<p>Reliability, graded on separate axes because they are not "
            f"commensurable:</p><ul>{items}</ul>"
        )

    # AFTER the grade, so a reader meets the claim and then immediately the
    # reason to doubt it. Placing this earlier would have them discount a
    # grade they had not yet seen.
    discrepancy = _completeness_discrepancy(prov)
    if discrepancy:
        rows.append(f"<p><strong>{escape(discrepancy)}</strong></p>")

    return f'<body xmlns="{XHTML}">' + "".join(rows) + "</body>"


def annotate_sbml(
    sbml_text: str,
    provenance: dict[str, SbmlParameterProvenance],
    *,
    ec_number: str | None = None,
    model_taxon_id: str | None = None,
) -> AnnotationOutcome:
    """Return `sbml_text` with MIRIAM annotations and notes on parameters.

    `model_taxon_id` is the organism the MODEL is about, as distinct from
    the organism each value was measured in. Supplying it is what makes
    cross-species substitution **machine-detectable**: the model carries
    one `bqbiol:hasTaxon`, each parameter carries its own, and a consumer
    that never renders notes to anyone can still see the two disagree.

    Without it the mismatch is only prose, and prose is invisible to a
    pipeline. This is the difference between a warning a person might read
    and a fact a program can act on.

    Raises ValueError if the input is not parseable SBML -- silently
    returning the input unchanged would let a caller write an unannotated
    file believing it annotated.
    """
    document = libsbml.readSBMLFromString(sbml_text)
    if document.getNumErrors() > 0:
        fatal = [
            document.getError(i).getMessage()
            for i in range(document.getNumErrors())
            if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        if fatal:
            raise ValueError("Input is not valid SBML: " + "; ".join(fatal))

    model = document.getModel()
    if model is None:
        raise ValueError("SBML document contains no model.")

    annotated: list[str] = []
    unannotated: list[str] = []
    refused: list[tuple[str, str, str]] = []
    ambiguous: list[str] = []
    cvterms = 0

    # Who licensed the data, in the format that travels furthest.
    #
    # `build_sbml` strips the Antimony comments before converting -- rightly,
    # since the same facts in two encodings in one file rot apart -- which
    # also strips the attribution block. So SBML has to state it in SBML's
    # own idiom, or the export that is most likely to outlive its context is
    # the one carrying no credit at all.
    #
    # Notes rather than a model-level CVTerm: `bqmodel:isDescribedBy`
    # pointing at BRENDA would assert that BRENDA describes THIS MODEL,
    # which is false and is the endorsement CC BY 4.0 2(a)(6) forbids
    # implying. Per-parameter CVTerms already carry each value's identity
    # for machines; this is the credit for the file as a whole.
    attribution = data_sources.attribution_xhtml(provenance)
    if attribution and model.setNotes(attribution) != libsbml.LIBSBML_OPERATION_SUCCESS:
        raise ValueError(
            "libSBML refused the data-source attribution notes. Writing the "
            "model without them would ship BRENDA-derived values with no "
            "licence statement, which is the defect this exists to fix."
        )

    # The builders emit `Km` and `Vmax`; the resolution layer speaks `km`
    # and `vmax`. The Antimony annotator absorbs that by lowercasing, so an
    # exact-match lookup here annotated NOTHING while still reporting
    # success -- two parameters listed as unannotated, two model-level
    # CVTerms written, and a green run.
    #
    # Case-insensitive, but NOT blindly: SBML ids are case-sensitive, so a
    # model with both `km` and `Km` has two distinct parameters and folding
    # them would attach one value's provenance to the other. An ambiguous
    # fold is reported and refused rather than resolved by picking one.
    by_lower: dict[str, list[str]] = {}
    for key in provenance:
        by_lower.setdefault(key.lower(), []).append(key)

    def provenance_for(parameter_id: str) -> SbmlParameterProvenance | None:
        if parameter_id in provenance:
            return provenance[parameter_id]
        candidates = by_lower.get(parameter_id.lower(), [])
        if len(candidates) == 1:
            return provenance[candidates[0]]
        if len(candidates) > 1:
            ambiguous.append(parameter_id)
        return None

    for index in range(model.getNumParameters()):
        parameter = model.getParameter(index)
        name = parameter.getId()
        prov = provenance_for(name)

        # A metaid is REQUIRED for RDF annotation: the RDF subject is
        # `#metaid`, so an element without one cannot be the subject of a
        # statement. libSBML accepts addCVTerm() on such an element and
        # silently writes nothing.
        if not parameter.isSetMetaId():
            parameter.setMetaId(f"caterva_{name}")

        parameter.setNotes(_notes_xhtml(name, prov))

        if prov is None:
            unannotated.append(name)
            continue
        annotated.append(name)

        for prefix, accession in _identifiers_for(prov):
            result = mint(prefix, accession)
            if not result.minted:
                refused.append((name, f"{prefix}:{accession}", result.reason or ""))
                continue
            term = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
            term.setBiologicalQualifierType(libsbml.BQB_IS_DESCRIBED_BY)
            term.addResource(result.uri)
            if parameter.addCVTerm(term) == libsbml.LIBSBML_OPERATION_SUCCESS:
                cvterms += 1

        # The citation may name a source with no URI form at all. Recorded
        # as a refusal so the caller can see the gap rather than infer it
        # from a missing annotation.
        if prov.citation and "brenda" in prov.citation.lower():
            result = mint("brenda", prov.citation)
            if not result.minted:
                refused.append((name, prov.citation, result.reason or ""))

        # How the value is known, as an ontology term rather than prose --
        # and only when there is something to point at.
        #
        # ECO:0000269 says a person read an experiment and asserted this. A
        # `resolved` parameter carrying no citation at all was getting that
        # term anyway: the model claimed a paper measured the value while
        # naming no paper. That is a provenance tool inventing evidence, in
        # the field added to describe evidence.
        #
        # The citation is the thing the term is about, so its absence is the
        # condition. Two ways a value can be `resolved` and uncited -- a
        # resolver bug, or a caller filling in the origin by hand -- and
        # neither is a reason to assert experimental support.
        #
        # This is also the honest reading of what could NOT be established
        # about BRENDA (ADR 0187). Its manually curated core is what the
        # scraper reads, but BRENDA also publishes AMENDA and FRENDA, which
        # are text-mined with a measured precision of 64.8% (Chang et al.,
        # NAR 2009). The 2009 paper does not say whether those results ever
        # surface on the enzyme page this parser reads, and nothing here can
        # tell a curated row from a mined one after the fact. What a row DOES
        # carry when it is curated is a reference id -- so requiring one is
        # the closest available proxy, and it is stated as a proxy rather
        # than as proof.
        eco = _ECO_FOR_ORIGIN.get(prov.origin)
        if eco and not (prov.citation or prov.reference_id):
            refused.append((
                name, eco,
                "a resolved value with no citation or reference id: "
                "ECO:0000269 asserts that a person read an experiment, and "
                "there is nothing here to have read.",
            ))
            eco = None
        if eco:
            evidence = mint("eco", eco)
            if evidence.minted:
                term = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
                # BQB_IS_DESCRIBED_BY: the parameter is described by this
                # evidence class. Not BQB_IS -- the parameter is not an
                # instance of an evidence code, it has one.
                term.setBiologicalQualifierType(libsbml.BQB_IS_DESCRIBED_BY)
                term.addResource(evidence.uri)
                if parameter.addCVTerm(term) == libsbml.LIBSBML_OPERATION_SUCCESS:
                    cvterms += 1
            else:
                refused.append((name, eco, evidence.reason or ""))

        if prov.taxon_id:
            taxon = mint("taxonomy", prov.taxon_id)
            if taxon.minted:
                term = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
                term.setBiologicalQualifierType(libsbml.BQB_HAS_TAXON)
                term.addResource(taxon.uri)
                if parameter.addCVTerm(term) == libsbml.LIBSBML_OPERATION_SUCCESS:
                    cvterms += 1
            else:
                refused.append((name, f"taxonomy:{prov.taxon_id}", taxon.reason or ""))

    if model_taxon_id:
        taxon = mint("taxonomy", model_taxon_id)
        if taxon.minted:
            if not model.isSetMetaId():
                model.setMetaId("caterva_model")
            term = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
            term.setBiologicalQualifierType(libsbml.BQB_HAS_TAXON)
            term.addResource(taxon.uri)
            if model.addCVTerm(term) == libsbml.LIBSBML_OPERATION_SUCCESS:
                cvterms += 1
        else:
            refused.append(("<model>", f"taxonomy:{model_taxon_id}", taxon.reason or ""))

    if ec_number:
        result = mint("ec-code", ec_number)
        if result.minted:
            if not model.isSetMetaId():
                model.setMetaId("caterva_model")
            term = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
            term.setBiologicalQualifierType(libsbml.BQB_IS_VERSION_OF)
            term.addResource(result.uri)
            if model.addCVTerm(term) == libsbml.LIBSBML_OPERATION_SUCCESS:
                cvterms += 1
        else:
            refused.append(("<model>", f"ec-code:{ec_number}", result.reason or ""))

    if ambiguous:
        raise ValueError(
            "Provenance keys differ only by case for: "
            + ", ".join(sorted(set(ambiguous)))
            + ". SBML ids are case-sensitive, so Caterva cannot tell which "
            "parameter each entry describes. Attaching one value's source to "
            "another is the exact failure this whole module exists to "
            "prevent, so it refuses rather than picks."
        )

    written = libsbml.writeSBMLToString(document)

    # Read the result back with an INDEPENDENT parser before returning it.
    # libSBML happily writes RDF that libSBML then declines to read (an
    # rdf:about naming no element), and checkConsistency() reports nothing,
    # so neither the writer nor the standard validator would notice. This
    # is the one place both the document and the intent exist.
    audit = audit_annotations(written)
    if not audit.ok:
        raise ValueError(
            "The annotations written are not ones an independent RDF reader "
            "could use: " + "; ".join(audit.problems)
        )

    # THE AUDIT ALONE CANNOT CATCH TOTAL LOSS.
    #
    # `audit.ok` is True when the reader finds nothing, and that is correct
    # for the audit -- as a standalone reader it has no way of knowing how
    # many annotations were meant to be there, and an unannotated model is
    # legitimate. But THIS function knows: it counted `cvterms` as it wrote
    # them.
    #
    # Measured. Deleting every `<annotation>` block from a document that had
    # just been annotated:
    #
    #     cvterms_written=3   audit triples=0   ok=True   problems=[]
    #
    # So the check written precisely because "libSBML happily writes RDF that
    # libSBML then declines to read" was blind to the RDF not being there at
    # all. And this is not hypothetical for this module: the comment above
    # `by_lower` records a pass where the lookup "annotated NOTHING while
    # still reporting success -- two parameters listed as unannotated, two
    # model-level CVTerms written, and a green run". That defect was fixed at
    # the lookup. The detector that should have caught it was left unable to.
    #
    # Two facts sat in the same function and were never compared: the count
    # the writer intended, and the count an independent reader found.
    #
    # `>=` rather than `==`: every CVTerm here carries exactly one resource,
    # so the two are equal today, but a term with two resources would yield
    # more triples than terms and must not fail. Loss is the failure being
    # caught, and loss always shows up as fewer.
    if len(audit.triples) < cvterms:
        raise ValueError(
            f"{cvterms} RDF term(s) were written but an independent reader "
            f"finds only {len(audit.triples)} in the serialised document. "
            "The annotations did not survive writing. libSBML reports success "
            "on the write and checkConsistency() reports nothing, so this "
            "count is the only place the loss is visible."
        )

    return AnnotationOutcome(
        sbml=written,
        annotated=sorted(annotated),
        unannotated=sorted(unannotated),
        refused_uris=refused,
        cvterms_written=cvterms,
        triples_read_back=len(audit.triples),
    )


def cross_species_parameters(sbml_text: str) -> list[tuple[str, str, str]]:
    """(parameter, its taxon URI, the model's taxon URI) where they differ.

    The machine-readable half of the cross-species warning, and the reason
    `model_taxon_id` exists. Anything that can parse SBML can call this --
    it reads nothing Caterva-specific, only standard `bqbiol:hasTaxon`
    terms, so a consumer that has never heard of Caterva can reach the same
    conclusion from the file alone.

    Returns empty when the model carries no taxon: **that is not a
    statement that nothing is cross-species.** It means the question was
    not asked, and a caller must not read the empty list as reassurance.
    """
    document = libsbml.readSBMLFromString(sbml_text)
    model = document.getModel()
    if model is None:
        return []

    def taxa(element) -> list[str]:
        out: list[str] = []
        for i in range(element.getNumCVTerms()):
            term = element.getCVTerm(i)
            if term.getBiologicalQualifierType() != libsbml.BQB_HAS_TAXON:
                continue
            for j in range(term.getNumResources()):
                out.append(term.getResourceURI(j))
        return out

    model_taxa = taxa(model)
    if not model_taxa:
        return []

    mismatched: list[tuple[str, str, str]] = []
    for index in range(model.getNumParameters()):
        parameter = model.getParameter(index)
        for uri in taxa(parameter):
            if uri not in model_taxa:
                mismatched.append((parameter.getId(), uri, model_taxa[0]))
    return mismatched


#: RDF and the BioModels qualifier namespaces, as MIRIAM defines them.
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
BQBIOL_NS = "http://biomodels.net/biology-qualifiers/"

#: Every SBML namespace begins here; the level and version follow it
#: (`.../level2/version4`, `.../level3/version2/core`). Verified against the
#: documents this repository actually handles: libSBML's own output is
#: level3/version2/core, and the BioModels fixtures are level2/version3 and
#: level2/version4. Matching the stem rather than a list of full URIs means a
#: level 3 version 3 document is read rather than rejected as foreign.
SBML_NS_STEM = "http://www.sbml.org/sbml/"


@dataclass
class AnnotationAudit:
    """What an independent RDF reader finds in the annotations."""

    #: (element id, qualifier local-name, resource URI)
    triples: list[tuple[str, str, str]]
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def audit_annotations(sbml_text: str) -> AnnotationAudit:
    """Read the MIRIAM annotations WITHOUT libSBML.

    WHY THIS EXISTS

    `read_back()` uses libSBML's CVTerm reader on libSBML's CVTerm writer.
    That is the producer verified against itself -- it establishes that the
    round trip is self-consistent and nothing about whether a third-party
    RDF consumer can use the file. The whole point of writing MIRIAM rather
    than a Caterva-specific format is that other tools read it.

    And there is a measured blind spot. An RDF block whose `rdf:about`
    names a metaid no element carries is **silently dropped** by
    `read_back()`, and `libsbml.checkConsistency()` reports **zero**
    errors on that document. So the guard this module's tests lean on
    cannot see an annotation that has come unmoored from the thing it
    describes.

    This parses with lxml only and checks the linkage a consumer depends
    on: every `rdf:Description` must point at an element that exists, by
    the metaid that element actually carries.

    Deliberately NOT checked: whether the resource URIs resolve over the
    network. `miriam.py` decides what may be minted, and a formatter that
    quietly made HTTP calls would be a different kind of surprise.
    """
    from lxml import etree

    root = etree.fromstring(sbml_text.encode("utf-8"))
    sbml_ns = etree.QName(root).namespace

    triples: list[tuple[str, str, str]] = []
    problems: list[str] = []

    # WHETHER THIS IS EVEN AN SBML DOCUMENT.
    #
    # `sbml_ns` was computed here and then never read -- found by ruff's F841,
    # which this repository's lint guard lists as a bug class and does not yet
    # enforce. Measured before fixing: `audit_annotations("<html><body>404 Not
    # Found</body></html>")` returned `ok=True`, no triples, no problems.
    #
    # The test below this one is right that "nothing to check" must not be an
    # error -- an unannotated model is legitimate. But an HTML error page is
    # not "nothing to check": it is the wrong document, and the two were
    # collapsed into the same clean verdict. That collapse is this project's
    # most-repeated defect wearing yet another hat.
    if sbml_ns is None or not sbml_ns.startswith(SBML_NS_STEM):
        problems.append(
            f"the root element is {etree.QName(root).localname!r} in namespace "
            f"{sbml_ns!r}, which is not SBML. Nothing here was audited. An "
            "unannotated SBML model audits clean on purpose; a document that "
            "is not SBML at all must not, or a fetch that returned an error "
            "page reads as a model with no annotations."
        )
        return AnnotationAudit(triples=triples, problems=problems)

    # Every metaid actually present, so a dangling reference is detectable
    # rather than merely absent.
    known: dict[str, str] = {}
    for element in root.iter():
        meta = element.get("metaid")
        if meta:
            known[meta] = element.get("id") or etree.QName(element).localname

    for description in root.iter(f"{{{RDF_NS}}}Description"):
        about = description.get(f"{{{RDF_NS}}}about") or ""
        target = about.lstrip("#")
        if target not in known:
            problems.append(
                f"rdf:about={about!r} names no element in the document. "
                "libSBML drops this silently and checkConsistency() reports "
                "nothing, so the annotation would simply vanish."
            )
            continue

        owner = known[target]
        # The Description must sit INSIDE the element it claims to describe.
        # RDF does not require that; SBML's annotation scheme does, and a
        # consumer walking the model tree will never find a block filed
        # under a different element.
        ancestor_metaids = {
            ancestor.get("metaid")
            for ancestor in description.iterancestors()
            if ancestor.get("metaid")
        }
        if target not in ancestor_metaids:
            problems.append(
                f"the RDF for {owner!r} is not nested inside the element it "
                f"describes (rdf:about={about!r})"
            )

        for qualifier in description:
            name = etree.QName(qualifier)
            if name.namespace != BQBIOL_NS:
                continue
            resources = [
                item.get(f"{{{RDF_NS}}}resource")
                for item in qualifier.iter(f"{{{RDF_NS}}}li")
            ]
            resources = [r for r in resources if r]
            if not resources:
                problems.append(
                    f"{owner!r} carries a {name.localname} qualifier with no "
                    "resource. An empty qualifier asserts a relationship to "
                    "nothing."
                )
            for resource in resources:
                triples.append((owner, name.localname, resource))

    return AnnotationAudit(triples=triples, problems=problems)


def read_back(sbml_text: str) -> dict[str, list[str]]:
    """Parameter id -> the resource URIs annotated on it.

    The asserted inverse of the write. A writer with no reader is a writer
    nobody checked: this is what lets a test assert that the annotation
    survived serialisation rather than that `addCVTerm` returned success.
    """
    document = libsbml.readSBMLFromString(sbml_text)
    model = document.getModel()
    if model is None:
        return {}

    out: dict[str, list[str]] = {}
    for index in range(model.getNumParameters()):
        parameter = model.getParameter(index)
        uris: list[str] = []
        for term_index in range(parameter.getNumCVTerms()):
            term = parameter.getCVTerm(term_index)
            for resource_index in range(term.getNumResources()):
                uris.append(term.getResourceURI(resource_index))
        out[parameter.getId()] = uris
    return out