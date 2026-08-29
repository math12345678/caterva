"""A run somebody else can re-run.

WHAT WAS MISSING
----------------
Terrium exports an annotated SBML model, a citation file, a job id and a
reproducibility key. None of that lets another person **repeat the
experiment**. The model says what the system is; it does not say that this
run integrated from 0 to 20 with 101 output points, which is the part that
decides what the figure looks like.

So a Terrium result could be inspected but not reproduced, in a tool whose
entire pitch is traceability. Sauro's and König's field solved this years
ago and the answer is two standards:

* **SED-ML** (Waltemath et al. 2011, *BMC Systems Biology* 5:198) describes
  the simulation experiment -- algorithm, time course, what to record.
* **COMBINE archive / OMEX** (Bergmann et al. 2014, *BMC Bioinformatics*
  15:369) bundles the model, the experiment and anything else into one file
  with a manifest saying what each entry is.

An `.omex` opens in COPASI, Tellurium, JWS Online and the BioSimulators
runners. Handing an instructor one file that re-runs is the teaching-lab
version of reproducibility, and it costs the student nothing.

WHAT IS VERIFIED, AND WHAT IS NOT
---------------------------------
The SED-ML is **built through libSEDML**, not string-formatted, and the
document is validated before it is written -- so it is well-formed and
schema-conformant to the extent libSEDML checks, which is what any consumer
will use to read it anyway.

The stronger claim, and the one that actually matters, is proven by
execution rather than by validation: `Terium/tests/test_combine_archive.py`
opens the archive, reads the time course **out of the SED-ML**, runs the
SBML **from the archive**, and compares against the original trajectory. A
schema-valid experiment that reproduces a different curve is still a broken
export.

TELLURIUM HAS NOW OPENED ONE (2026-08-28)
-----------------------------------------
This paragraph used to say no Tellurium install existed to try it against,
and that claiming "opens in Tellurium" without having done so was not a
claim this project makes. One was installed and it was tried:

    te.executeCombineArchive("terrium_export.omex")   -> succeeded

Tellurium 2.2.13.1 opened the archive, read the SED-ML, resolved all four
data generators (time, [S], [P], J0) against the model, and ran the exact
time course the export recorded -- `simulate(start=0.0, end=10.0,
steps=50)`. Loading `model.xml` alone and simulating gives a last row of
[10.0, 7.5857, 2.4143], identical to four decimal places to what Terrium's
own in-process run produces from the same parameters.

WHAT THAT DOES AND DOES NOT ESTABLISH
-------------------------------------
It establishes that the archive is readable and runnable by a tool that did
not write it, which is what this module exists for.

It is NOT two independent solvers agreeing. Terrium integrates through
roadrunner and so does Tellurium, so the matching trajectory says the
exported SBML reconstructs the same model by a different route -- fresh
parse of the written bytes rather than the in-process object -- not that two
implementations of the mathematics concur.

And COPASI is still untried. The plural in "opens in COPASI, Tellurium, JWS
Online and the BioSimulators runners" above is now one-quarter measured.

A NOTE FOR ANYONE TRYING THIS
-----------------------------
Tellurium cannot be installed alongside Terrium's pinned environment.
requirements.txt pins `antimony==2.14.0`; tellurium 2.2.13.1 requires
`antimony>=3.1.0`, and pip resolves that by upgrading antimony out from
under the pin. The check above was run with two separate virtualenvs -- one
pinned, which exported, and one with tellurium, which read -- which is also
the arrangement a real consumer is in.

WHY THE FORMAT URIs ARE `http://`
---------------------------------
MIRIAM annotations in `miriam.py` use `https://identifiers.org/...`. The
OMEX manifest uses `http://identifiers.org/combine.specifications/...` --
the http form -- because that is the literal string the COMBINE archive
specification defines and what existing readers match on. Two spellings in
one codebase looks like an inconsistency and is not: one is a resolvable
citation, the other is an enum value that happens to look like a URL.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import libsbml

#: Manifest format identifiers. The `combine.specifications` namespace is
#: real (MIR:00000258, sample `sed-ml.level-1.version-1`), captured with the
#: others in Tests/fixtures/identifiers/ so the freshness guard watches it.
OMEX = "http://identifiers.org/combine.specifications/omex"
OMEX_MANIFEST = "http://identifiers.org/combine.specifications/omex-manifest"
SBML_L3V2 = "http://identifiers.org/combine.specifications/sbml.level-3.version-2"
SEDML_L1V3 = "http://identifiers.org/combine.specifications/sed-ml.level-1.version-3"
#: BibTeX has no COMBINE specification, so it travels as a media type. A
#: made-up combine.specifications entry would be an invented identifier in
#: the one file whose job is saying truthfully what each entry is.
BIBTEX = "application/x-bibtex"
#: Citation File Format (CITATION.cff). No COMBINE specification exists for
#: it either, so it travels as its media type for the same reason BibTeX
#: does -- inventing `combine.specifications/cff` would put a fabricated
#: identifier in the file whose job is saying truthfully what each entry is.
CFF = "application/x-yaml"
PLAIN_TEXT = "text/plain"

#: The provenance report, as a file a program can read.
#:
#: Frank Bergmann, asked whether SED-ML should carry per-parameter
#: provenance, said it should not, and said where it should go instead
#: (personal communication, 2026-08-25):
#:
#:   "What I'd suggest is to use a combination, perhaps stored as COMBINE
#:    archive, that would contain: the sbml model, the sed-ml experiment,
#:    some kind of structured format of your provenance report (could be
#:    json, markdown, anything really), and all the other data..."
#:
#: The archive already carried the first two. The provenance existed only
#: inside SBML `notes`, which is prose -- and his objection to that is not
#: that it is wrong but that "this makes automated extraction difficult".
#:
#: Eduard Kerkhoven arrived at the same file from the other direction, on
#: whether provenance belongs per-parameter or in Git history (personal
#: communication, 2026-08-25): "It is essential though that the metadata is
#: provided in flat-text format, so that Git can easily diff any changes."
#: JSON with sorted keys and one field per line diffs; an XML blob does not.
JSON = "application/json"

MANIFEST_PATH = "manifest.xml"

#: CVODE, the solver libRoadRunner actually uses for these models. KiSAO is
#: how SED-ML names an algorithm; picking a term that does not match the
#: solver would describe an experiment nobody ran.
KISAO_CVODE = "KISAO:0000019"


@dataclass(frozen=True)
class RecordedQuantity:
    """One thing the SED-ML report records, and where it lives in the SBML.

    The kind is carried, not inferred, because the XPath differs:

        species    /sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id=...]
        parameter  /sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id=...]

    `build_sedml` used to take bare names and emit the SPECIES path for all
    of them. Every Terrium domain today records only species, so it was
    correct -- and it would have gone on being correct right up until a
    model recorded a parameter, at which point the archive would carry a
    target resolving to nothing. Correct-by-accident, with the accident
    scheduled.
    """

    id: str
    #: "species" or "parameter".
    kind: str

    @property
    def target(self) -> str:
        if self.kind == "species":
            return (
                "/sbml:sbml/sbml:model/sbml:listOfSpecies/"
                f"sbml:species[@id='{self.id}']"
            )
        if self.kind == "parameter":
            return (
                "/sbml:sbml/sbml:model/sbml:listOfParameters/"
                f"sbml:parameter[@id='{self.id}']"
            )
        if self.kind == "compartment":
            return (
                "/sbml:sbml/sbml:model/sbml:listOfCompartments/"
                f"sbml:compartment[@id='{self.id}']"
            )
        if self.kind == "reaction":
            return (
                "/sbml:sbml/sbml:model/sbml:listOfReactions/"
                f"sbml:reaction[@id='{self.id}']"
            )
        raise ValueError(
            f"Unknown quantity kind {self.kind!r} for {self.id!r}. Guessing a "
            "target would produce an XPath that silently resolves to nothing."
        )


@dataclass(frozen=True)
class ArchiveEntry:
    """One file inside the archive, and what it is."""

    location: str
    format_uri: str
    #: Exactly one entry should be master: the thing a reader should open
    #: first. For a Terrium run that is the SED-ML, because the SED-ML
    #: references the model -- opening the model first loses the experiment.
    master: bool = False
    description: str | None = None


@dataclass
class ArchiveResult:
    path: Path
    entries: list[ArchiveEntry] = field(default_factory=list)
    sedml_errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        master = [e.location for e in self.entries if e.master]
        return (
            f"{len(self.entries)} entr(ies), master: "
            f"{master[0] if master else 'NONE'}"
        )


def build_sedml(
    *,
    model_location: str,
    model_id: str,
    end_time: float,
    points: int,
    recorded: list[RecordedQuantity],
    start_time: float = 0.0,
) -> tuple[str, list[str]]:
    """A SED-ML L1V3 document for one uniform time course.

    Returns (xml, errors). A non-empty `errors` means the caller must not
    write the archive: an invalid experiment file is worse than none,
    because the archive still looks complete.

    L1V3 rather than L1V4 on purpose. V4 is newer and less widely read, and
    the point of this export is that other people's tools open it. Nothing
    here needs anything V4 added.
    """
    import libsedml

    doc = libsedml.SedDocument(1, 3)

    model = doc.createModel()
    model.setId(model_id)
    model.setSource(model_location)
    model.setLanguage("urn:sedml:language:sbml")

    simulation = doc.createUniformTimeCourse()
    simulation.setId("sim_timecourse")
    simulation.setInitialTime(start_time)
    simulation.setOutputStartTime(start_time)
    simulation.setOutputEndTime(end_time)
    # SED-ML counts INTERVALS, not samples. `points` here is the number of
    # rows Terrium reports, so 101 rows is 100 intervals. Off by one and
    # every re-run lands its samples between the original's.
    simulation.setNumberOfPoints(max(points - 1, 1))
    algorithm = simulation.createAlgorithm()
    algorithm.setKisaoID(KISAO_CVODE)

    task = doc.createTask()
    task.setId("task_run")
    task.setModelReference(model.getId())
    task.setSimulationReference(simulation.getId())

    report = doc.createReport()
    report.setId("report_timecourse")

    def add_generator(gen_id: str, symbol: str | None, target: str | None, label: str):
        generator = doc.createDataGenerator()
        generator.setId(gen_id)
        variable = generator.createVariable()
        variable.setId(f"var_{gen_id}")
        variable.setTaskReference(task.getId())
        if symbol is not None:
            variable.setSymbol(symbol)
        else:
            variable.setTarget(target)
        generator.setMath(libsedml.parseFormula(variable.getId()))

        data_set = report.createDataSet()
        data_set.setId(f"ds_{gen_id}")
        data_set.setLabel(label)
        data_set.setDataReference(generator.getId())

    add_generator("dg_time", "urn:sedml:symbol:time", None, "time")
    for quantity in recorded:
        add_generator(f"dg_{quantity.id}", None, quantity.target, quantity.id)

    errors = [
        doc.getError(i).getMessage()
        for i in range(doc.getNumErrors())
        if doc.getError(i).getSeverity() >= libsedml.LIBSEDML_SEV_ERROR
    ]
    return libsedml.writeSedMLToString(doc), errors


def species_in(sbml_text: str) -> list[str]:
    """Every species id in the model, in document order.

    The SED-ML report used to record a list the CALL SITE named -- literally
    `['S', 'P']`, correct for Michaelis-Menten and wrong for anything with a
    third species. A competitively-inhibited model has an inhibitor, and its
    archive would have re-run correctly while reporting a curve that omitted
    the thing the experiment was about.

    Reading them from the model instead means the archive describes whatever
    was actually built, and a new domain gets a correct report without
    anybody remembering to update a list. Hardcoding what the model already
    states is the defect this project keeps finding one layer down; this is
    that layer.

    Boundary species are INCLUDED. A clamped concentration is still a
    quantity someone plotting the run wants to see, and a reader can tell it
    is clamped from the model.
    """
    document = libsbml.readSBMLFromString(sbml_text)
    model = document.getModel()
    if model is None:
        raise ValueError("Cannot list species: the SBML has no model.")
    return [model.getSpecies(i).getId() for i in range(model.getNumSpecies())]


def recorded_quantities(sbml_text: str) -> list[RecordedQuantity]:
    """Everything in the model that VARIES over the run.

    Species, plus non-constant parameters, plus anything a rule assigns to.
    Constant parameters are excluded: their value is in the model file and a
    flat line in a time-course report is noise, not information.

    Today this returns exactly the species for all four domains -- measured,
    not assumed:

        mm     species=[S, P]     nonconstant=[]  rules=[]
        mm_ci  species=[S, P]     nonconstant=[]  rules=[]
        sir    species=[S, I, R]  nonconstant=[]  rules=[]
        seir   species=[S,E,I,R]  nonconstant=[]  rules=[]

    So this changes no output. It is written anyway because the alternative
    -- `species_in` -- is correct only for as long as that stays true, and
    the failure would be a report silently missing a curve rather than an
    error. The previous pass recorded that gap in prose; this closes it in
    code.
    """
    document = libsbml.readSBMLFromString(sbml_text)
    model = document.getModel()
    if model is None:
        raise ValueError("Cannot list quantities: the SBML has no model.")

    found: list[RecordedQuantity] = []
    seen: set[str] = set()

    def add(identifier: str, kind: str) -> None:
        if identifier and identifier not in seen:
            seen.add(identifier)
            found.append(RecordedQuantity(identifier, kind))

    for index in range(model.getNumSpecies()):
        add(model.getSpecies(index).getId(), "species")

    # Reaction fluxes.
    #
    # This question was deferred twice before being settled with numbers.
    # Two facts decided it:
    #
    #   * libSEDML accepts a reaction target -- checked, not assumed.
    #   * A Michaelis-Menten teaching lab plots v against S. An archive of
    #     an enzyme-kinetics run that cannot produce the rate curve is
    #     missing the point of the experiment it claims to reproduce.
    #
    # WHICH QUANTITY THIS IS, precisely, because it is NOT the one Terrium
    # prints. `scientificPipeline.ts` derives a `velocity` by backward
    # finite difference on the concentration series (forward at t=0). This
    # target is the EXACT rate-law value. On the Michaelis-Menten model at
    # 101 output points the two differ by at most **0.082% relative**
    # (0.000147 absolute) -- measured, on this model, at this resolution,
    # and larger at coarser spacing.
    #
    # The exact flux is the right thing for an archive to carry: the
    # archive describes the MODEL and the EXPERIMENT, not Terrium's
    # post-processing, and a consumer re-running it computes the flux the
    # rate law defines. Said out loud here because a reader comparing the
    # archive's curve against Terrium's screen will find a small difference
    # and deserves to know it is expected and why.
    for index in range(model.getNumReactions()):
        add(model.getReaction(index).getId(), "reaction")

    for index in range(model.getNumParameters()):
        parameter = model.getParameter(index)
        if not parameter.getConstant():
            add(parameter.getId(), "parameter")

    # Rule targets.
    #
    # This loop first carried the comment "libSBML will not stop you writing
    # a rule for a parameter left marked constant". That was ASSERTED, not
    # tested, and it is false -- libSBML raises
    #
    #     An assignment rule cannot assign an entity declared to be constant
    #
    # which means every rule target in a VALID document already has
    # constant=false and is therefore caught above. Two mutation tests
    # surviving is what prompted checking: deleting either this loop or the
    # parameter loop changed nothing, because for species and parameters
    # they cover the same ground.
    #
    # The loop stays for the case neither other loop reaches: a rule whose
    # target is a COMPARTMENT. A varying compartment volume is a quantity
    # someone plotting the run wants, and nothing else here would find it.
    for index in range(model.getNumRules()):
        variable = model.getRule(index).getVariable()
        if not variable:
            continue
        if model.getSpecies(variable):
            kind = "species"
        elif model.getCompartment(variable):
            kind = "compartment"
        else:
            kind = "parameter"
        add(variable, kind)

    return found


#: Fallback SBML namespace, used only if the model document does not
#: declare one. The real namespace is read FROM THE MODEL -- see
#: `resolve_targets`. Hardcoding `level3/version2` here would make this
#: check reject every archive the day Antimony emits a different level,
#: and it would look like the targets were broken rather than the checker.
SBML_NS_FALLBACK = "http://www.sbml.org/sbml/level3/version2/core"


@dataclass
class TargetResolution:
    """Which SED-ML targets actually select something in the model."""

    resolved: list[tuple[str, str]]
    #: (variable id, target, how many elements it selected)
    unresolved: list[tuple[str, str, int]]

    @property
    def ok(self) -> bool:
        return not self.unresolved


def resolve_targets(sbml_text: str, sedml_text: str) -> TargetResolution:
    """Evaluate every SED-ML variable target against the model.

    WHY THIS EXISTS, and why the existing tests could not have caught it:

    libSEDML **stores** targets as strings. It never resolves them, because
    it does not have the model -- the target is an XPath into a separate
    document. So a one-character typo in a generated path produces a
    document libSEDML calls valid, an archive that opens, and a report
    whose every column selects nothing.

    Demonstrated rather than argued: changing `listOfSpecies` to
    `listOfSpeciez` in this module left **all 37 archive tests passing**.
    The replay tests do not catch it either, because they run the SBML
    directly with libRoadRunner and never read the targets.

    So the one property that makes the report meaningful had nothing
    checking it, inside the feature three passes went into.

    Exactly one match is required. Zero means the column is empty. More than
    one means the report has an ambiguous column, which is arguably worse:
    a consumer picks, and two consumers may pick differently.
    """
    from lxml import etree

    model = etree.fromstring(sbml_text.encode("utf-8"))
    document = etree.fromstring(sedml_text.encode("utf-8"))

    # The namespace comes from the document being queried, not from a
    # constant. An SBML level bump changes it, and a hardcoded one would
    # turn every target into a non-match -- reporting that the archive is
    # broken when it is this function that stopped understanding the model.
    namespaces = {"sbml": etree.QName(model).namespace or SBML_NS_FALLBACK}

    resolved: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str, int]] = []

    for variable in document.iter("{http://sed-ml.org/sed-ml/level1/version3}variable"):
        target = variable.get("target")
        # A symbol (urn:sedml:symbol:time) is not an XPath and has nothing
        # to resolve against. Skipping it is correct; counting it as
        # resolved would be a check reporting on something it did not do.
        if not target:
            continue
        identifier = variable.get("id") or "<unnamed>"
        try:
            matches = model.xpath(target, namespaces=namespaces)
        except etree.XPathEvalError:
            unresolved.append((identifier, target, -1))
            continue
        if len(matches) == 1:
            resolved.append((identifier, target))
        else:
            unresolved.append((identifier, target, len(matches)))

    return TargetResolution(resolved=resolved, unresolved=unresolved)


def build_manifest(entries: list[ArchiveEntry]) -> str:
    """The OMEX manifest.

    Every entry in the archive must appear here, and every entry here must
    exist in the archive. Both directions are checked by
    `verify_archive()` -- a manifest that omits a file and one that names a
    missing file are equally broken, and only one of them is the obvious
    one to test for.
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{OMEX}"/>',
        f'  <content location="./{MANIFEST_PATH}" format="{OMEX_MANIFEST}"/>',
    ]
    for entry in entries:
        master = ' master="true"' if entry.master else ""
        lines.append(
            f'  <content location="./{escape(entry.location)}" '
            f'format="{entry.format_uri}"{master}/>'
        )
    lines.append("</omexManifest>")
    return "\n".join(lines) + "\n"


def write_archive(
    destination: str | Path,
    files: dict[str, tuple[str, ArchiveEntry]],
) -> ArchiveResult:
    """Write `files` as a COMBINE archive.

    `files` maps location -> (content, entry). Raises ValueError rather
    than writing something malformed: an archive that exists and does not
    open is worse than a failed export, because the failure is discovered
    by whoever the file was handed to.
    """
    destination = Path(destination)
    entries = [entry for _, entry in files.values()]

    masters = [e for e in entries if e.master]
    if len(masters) != 1:
        raise ValueError(
            f"A COMBINE archive needs exactly one master entry; got {len(masters)}. "
            "The master is what a reader opens first, and for a Terrium run that "
            "is the SED-ML -- opening the model first loses the experiment."
        )

    manifest = build_manifest(entries)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_PATH, manifest)
        for location, (content, _) in files.items():
            archive.writestr(location, content)

    return ArchiveResult(path=destination, entries=entries)


@dataclass
class VerifyOutcome:
    ok: bool
    problems: list[str]
    listed: list[str]
    present: list[str]


def verify_archive(path: str | Path) -> VerifyOutcome:
    """Does the archive say truthfully what is in it?

    Checked in BOTH directions. The tempting version walks the manifest and
    confirms each file exists, which passes an archive whose manifest omits
    half its contents -- and an unlisted entry is exactly what a strict
    reader ignores, so the export would appear to work while silently
    dropping the citations.
    """
    import re

    problems: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if MANIFEST_PATH not in names:
            return VerifyOutcome(False, [f"no {MANIFEST_PATH}"], [], sorted(names))
        manifest = archive.read(MANIFEST_PATH).decode("utf-8")

    listed = [
        location.lstrip("./")
        for location in re.findall(r'location="([^"]+)"', manifest)
        if location not in (".",)
    ]
    present = sorted(names)

    for location in listed:
        if location not in names:
            problems.append(f"manifest names {location!r}, which is not in the archive")
    for name in names:
        if name not in listed:
            problems.append(f"{name!r} is in the archive and not in the manifest")

    if manifest.count('master="true"') != 1:
        problems.append(
            f"expected exactly one master entry, found {manifest.count('master=')}"
        )

    return VerifyOutcome(not problems, problems, sorted(listed), present)