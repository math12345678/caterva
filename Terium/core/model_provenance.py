"""Write a model's provenance into the model file itself.

WHY THIS EXISTS
---------------
Professor Herbert Sauro (University of Washington; author of libRoadRunner
and Antimony, which this engine is built on) was asked what a tool should do
when a kinetic parameter cannot be sourced. His answer contained a mechanism
as well as a policy:

    "If Brenda or pubmed has no value for a particular km I would just give
     it a default value, say 0.5 and write a warning comment in the antimony
     file you generate."

ADR 0024 has not settled the policy half — whether to default at all is
still open, and Terrium still refuses. But the *mechanism* is right
independently of that, and it is the part Terrium was missing entirely:

    the assumption should travel INSIDE the artifact,
    not in a console someone scrolled past.

A warning printed at run time is read once, by the person who ran it. A
comment in the model file is read by everyone who ever opens the model,
including the reviewer six months later who received it by email and never
saw the terminal. Sauro is describing where provenance has to live to
survive being passed on, and he is right about that whether or not the value
being annotated is a default or a refusal.

The gap was worse than a missing feature. Terrium generates Antimony and
never handed it to anyone — so the one artifact that could carry provenance
onward did not leave the process. A tool built on an interchange format that
never exports anything is not participating in the interchange.

THE PROPERTY THAT MATTERS
-------------------------
Annotation MUST NOT change the model.

Every function here only inserts comment lines and inline `//` trailers.
`strip_annotations()` is the inverse, and `Tests/` asserts round-trip
equality on real generated models — plus an antimony/libsbml load of the
annotated text, because "it is only a comment" is exactly the assumption
that is wrong when a comment character is not what you thought it was.

WHAT IT REFUSES TO DO
---------------------
A parameter with no provenance record gets an explicit
`// NO PROVENANCE RECORDED` marker rather than being left bare.

Silence reads as endorsement. A file where three parameters carry citations
and the fourth carries nothing looks like a file where the fourth was fine,
and that is the single most likely way a number with no source escapes this
system into someone else's paper.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import data_sources

#: Antimony's line-comment token. `#` also works, but `//` is what the
#: Antimony documentation uses and what round-trips through
#: sbml_to_antimony, so it is the one Terrium emits.
COMMENT = "//"

#: Marker written when a parameter has no provenance entry at all.
#:
#: Read by `unsourced_parameters()` below and asserted in
#: `Terium/tests/test_model_provenance.py`, so changing it is a contract
#: change rather than a wording change.
#:
#: An earlier version of this comment said the marker was "matched by
#: scripts/check_model_provenance.py". No such guard exists and none ever
#: did. A false claim about what enforces a rule is worse than no claim --
#: it invites the next reader to trust an enforcement that is not there --
#: and it sat, for several passes, in the file about provenance.
NO_PROVENANCE_MARKER = "NO PROVENANCE RECORDED"

#: An Antimony assignment: `  Km = 2.5;` with optional leading whitespace.
#: Deliberately anchored and conservative -- it must not match a reaction
#: line like `J0: S -> P; Vmax * S / (Km + S);`, which also contains `=`
#: in some rate laws. Requiring the line to START with the identifier is
#: what excludes those.
_ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_]\w*)\s*=\s*([^;]+);\s*$")


@dataclass(frozen=True)
class ParameterProvenance:
    """What is known about one parameter's value.

    Mirrors the TypeScript `ParameterProvenance` (provenance.ts). Kept as a
    plain dataclass rather than importing anything: this module is a string
    transform and must stay usable from the engine, which knows nothing
    about the resolution layer.
    """

    origin: str  # "resolved" | "user" | "llm" | "default"
    citation: str | None = None
    organism: str | None = None
    source: str | None = None
    citation_status: str | None = None
    cross_species: bool = False
    #: Bakker's axes, when scored. Pairs of (axis name, grade).
    reliability: tuple[tuple[str, str], ...] = ()
    note: str | None = None

    #: The conditions the measurement was made under, and the ones the
    #: source did not state. Jeske's "fantasy numbers" sentence names pH,
    #: temperature, cofactors and buffers as what decides whether mixing
    #: values is legitimate.
    #:
    #: Carried in BOTH exports, deliberately. The Antimony file and the
    #: SBML notes are two artifacts a reader may receive independently, and
    #: a fact that survives in one and not the other is worse than one
    #: absent from both: it makes the omission look like a property of the
    #: measurement rather than of the export path.
    assay_ph: float | None = None
    assay_temperature_c: float | None = None
    assay_buffer: str | None = None
    assay_unreported: tuple[str, ...] = ()

    def assay_line(self) -> str | None:
        """`measured at: ...` for the footer, or None when nothing is known.

        None rather than "conditions: unknown" when the payload carries
        neither values nor a record of the source's silence: a line on
        every parameter in a model whose conditions were never parsed is
        noise, and noise is how the lines that matter stop being read
        (ADR 0028).
        """
        measured = []
        if self.assay_ph is not None:
            measured.append(f"pH {self.assay_ph:g}")
        if self.assay_temperature_c is not None:
            measured.append(f"{self.assay_temperature_c:g} C")
        if self.assay_buffer:
            measured.append(f"in {self.assay_buffer}")

        present = {
            "ph": self.assay_ph is not None,
            "temperature": self.assay_temperature_c is not None,
            "buffer": bool(self.assay_buffer),
        }
        silent = [
            item
            for item in self.assay_unreported
            if not present.get(str(item).strip().lower(), False)
        ]

        if not measured and not silent:
            return None
        parts = []
        if measured:
            parts.append("measured at " + ", ".join(measured))
        if silent:
            # Named, not omitted. An absent line reads as an oversight by
            # whoever produced the file; this reads as a fact about the
            # publication, which is what it is.
            parts.append("NOT REPORTED by the source: " + ", ".join(silent))
        return "; ".join(parts)

    def one_line(self) -> str:
        """The inline trailer for this parameter's assignment line."""
        if self.origin == "user_cited":
            # A DIFFERENT KIND of thing from a resolved citation, and never
            # folded into one. Terrium cannot check that the cited source
            # reports this value, and presenting it with the authority of a
            # BRENDA reference id would let a number acquire borrowed
            # credibility by passing through a tool that promises
            # provenance. Better than a bare number, worse than resolved,
            # and never silently either.
            source = self.citation or "source not stated"
            return f"CITED BY YOU (unverified by Terrium) -- {source}"

        if self.origin == "user":
            # The note carries the distinction between a value the person
            # chose and one the model fixes structurally (`P = 0` means "no
            # product at t=0", which nobody supplied). Both are legitimately
            # uncited, and telling a reader they "supplied" a number they
            # never typed is a small lie that costs trust in the larger
            # claims on the same page.
            return self.note or "supplied by you; not a literature value"

        if self.origin == "default":
            detail = f" -- {self.note}" if self.note else ""
            return f"DEFAULT, not sourced{detail}"

        if self.origin == "llm":
            return (
                "produced by a language model with no corroborating record; "
                "treat as a guess"
            )

        parts: list[str] = []
        if self.source:
            parts.append(self.source)
        if self.organism:
            parts.append(f"in {self.organism}")
        if self.citation:
            parts.append(self.citation)
        summary = "; ".join(parts) if parts else "resolved, source unrecorded"

        if self.cross_species:
            summary = f"CROSS-SPECIES -- {summary}"
        return summary

    def detail_lines(self) -> list[str]:
        """Fuller notes for the footer block."""
        lines: list[str] = []
        if self.citation:
            lines.append(f"citation: {self.citation}")
        if self.organism:
            lines.append(f"organism: {self.organism}")
        if self.citation_status:
            lines.append(f"citation status: {self.citation_status}")
        assay = self.assay_line()
        if assay:
            lines.append(assay)
        for axis, grade in self.reliability:
            lines.append(f"reliability / {axis}: {grade}")
        if self.note:
            lines.append(f"note: {self.note}")
        return lines


@dataclass
class AnnotationResult:
    text: str
    annotated: tuple[str, ...] = field(default_factory=tuple)
    unannotated: tuple[str, ...] = field(default_factory=tuple)


def annotate_antimony(
    antimony_text: str,
    provenance: dict[str, ParameterProvenance],
    *,
    run_id: str | None = None,
    query: str | None = None,
    generated_at: str | None = None,
) -> AnnotationResult:
    """Return `antimony_text` with provenance written into it as comments.

    The model is not modified. Only comment lines are inserted and inline
    `//` trailers appended.

    `provenance` is keyed by parameter name as it appears in the Antimony
    (`Km`, `Vmax`, `S`, ...). Lookup is case-insensitive because the
    resolution layer speaks lower case (`km`) and Antimony is conventionally
    capitalised (`Km`) -- a mismatch there would silently annotate nothing
    while appearing to work, which is why `unannotated` is returned and the
    caller can assert on it.
    """
    lookup = {key.lower(): value for key, value in provenance.items()}
    seen: set[str] = set()

    body: list[str] = []
    for line in antimony_text.splitlines():
        match = _ASSIGNMENT_RE.match(line)
        if match is None:
            body.append(line)
            continue

        name = match.group(2)
        entry = lookup.get(name.lower())
        if entry is None:
            body.append(f"{line.rstrip()}  {COMMENT} {NO_PROVENANCE_MARKER}")
        else:
            seen.add(name.lower())
            body.append(f"{line.rstrip()}  {COMMENT} {entry.one_line()}")

    header = _header(run_id=run_id, query=query, generated_at=generated_at)
    footer = _footer(provenance, lookup, seen)

    text = "\n".join([*header, *body, *footer])
    if not text.endswith("\n"):
        text += "\n"

    return AnnotationResult(
        text=text,
        annotated=tuple(sorted(seen)),
        unannotated=tuple(
            sorted(key for key in lookup if key not in seen)
        ),
    )


def _header(
    *, run_id: str | None, query: str | None, generated_at: str | None
) -> list[str]:
    lines = [
        f"{COMMENT} " + "=" * 68,
        f"{COMMENT} Generated by Terrium. Every parameter below carries its origin.",
        f"{COMMENT}",
        f"{COMMENT} Read the trailing comment on each assignment before reusing any",
        f"{COMMENT} value. In particular:",
        f"{COMMENT}",
        f"{COMMENT}   CROSS-SPECIES  measured in a different organism than the one",
        f"{COMMENT}                  asked about. Real and citable, and NOT a",
        f"{COMMENT}                  measurement of your organism.",
        f"{COMMENT}   DEFAULT        not sourced from any publication.",
        f"{COMMENT}   CITED BY YOU   you supplied both the value and its source.",
        f"{COMMENT}                  Terrium did not check that the source",
        f"{COMMENT}                  reports this value.",
        f"{COMMENT}   {NO_PROVENANCE_MARKER}",
        f"{COMMENT}                  Terrium has no record of where this came",
        f"{COMMENT}                  from. Treat it as unsourced.",
        f"{COMMENT}",
        f"{COMMENT} An absent comment would read as approval, so there is never one.",
    ]
    if query:
        lines += [f"{COMMENT}", f"{COMMENT} query:  {query}"]
    if run_id:
        lines.append(f"{COMMENT} run id: {run_id}")
    if generated_at:
        lines.append(f"{COMMENT} at:     {generated_at}")
    lines.append(f"{COMMENT} " + "=" * 68)
    return lines


def _footer(
    provenance: dict[str, ParameterProvenance],
    lookup: dict[str, ParameterProvenance],
    seen: set[str],
) -> list[str]:
    lines = [
        "",
        f"{COMMENT} " + "-" * 68,
        f"{COMMENT} PROVENANCE IN FULL",
        f"{COMMENT} " + "-" * 68,
    ]

    for key in sorted(provenance):
        entry = provenance[key]
        lines.append(f"{COMMENT}")
        lines.append(f"{COMMENT} {key}  [{entry.origin}]")
        details = entry.detail_lines()
        if not details:
            lines.append(f"{COMMENT}   (nothing further recorded)")
        for detail in details:
            lines.append(f"{COMMENT}   {detail}")

    # A provenance entry that matched no parameter is reported rather than
    # dropped. It means the resolution layer and the model disagree about
    # what this model contains, and a silent drop would hide that -- the
    # reader would see a complete-looking file that omits a parameter
    # somebody thought they had sourced.
    orphans = sorted(key for key in lookup if key not in seen)
    if orphans:
        lines.append(f"{COMMENT}")
        lines.append(
            f"{COMMENT} WARNING: provenance was supplied for parameter(s) that do "
            "not appear"
        )
        lines.append(
            f"{COMMENT} in this model: {', '.join(orphans)}. The resolver and the "
            "model"
        )
        lines.append(f"{COMMENT} disagree about what was built.")

    lines.append(f"{COMMENT} " + "-" * 68)

    # Who licensed the data, stated in the file that carries it.
    #
    # NOTICE meets CC BY 4.0 §3(a) for the repository. This model does not
    # travel with the repository -- it is emailed, attached and committed on
    # its own -- so the attribution has to be in here too. §3(a)(2) permits
    # satisfying the conditions "in any reasonable manner based on the
    # medium", which is what a comment block pointing at NOTICE is.
    #
    # Derived from the provenance actually present: see data_sources.py for
    # why crediting a source that contributed nothing would be both a false
    # provenance claim and the implied endorsement §2(a)(6) forbids.
    lines += data_sources.attribution_lines(provenance, COMMENT)
    return lines


def strip_annotations(annotated_text: str) -> str:
    """Inverse of `annotate_antimony`: recover the original model text.

    Exists so the round-trip can be ASSERTED rather than assumed. If
    annotation ever changes a model, this is what catches it, and the test
    that uses it is the only thing standing between a provenance comment and
    a silently altered simulation.
    """
    lines: list[str] = []
    for line in annotated_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(COMMENT):
            continue
        # Remove an inline trailer, but only one that is genuinely a
        # comment: Antimony assignments end in `;`, so the comment can only
        # begin after it.
        index = line.find(f";  {COMMENT}")
        if index != -1:
            line = line[: index + 1]
        lines.append(line.rstrip())

    # Drop the blank line the footer opens with, and any trailing blanks.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def parameters_in(antimony_text: str) -> list[str]:
    """Every assignable name in the model, in file order."""
    names: list[str] = []
    for line in antimony_text.splitlines():
        match = _ASSIGNMENT_RE.match(line)
        if match is not None:
            names.append(match.group(2))
    return names


def unsourced_parameters(annotated_text: str) -> list[str]:
    """Parameters the annotated file marks as unsourced.

    Used by the CLI to print a one-line summary, and by
    `Terium/tests/test_model_provenance.py`, which asserts that no
    assignment survives annotation without a comment.

    An earlier version of this sentence named a guard,
    `scripts/check_model_provenance.py`, that does not exist. The check it
    described did not either.
    """
    flagged: list[str] = []
    for line in annotated_text.splitlines():
        match = re.match(r"^\s*([A-Za-z_]\w*)\s*=", line)
        if match is None:
            continue
        upper = line.upper()
        if (
            NO_PROVENANCE_MARKER in upper
            or "DEFAULT, NOT SOURCED" in upper
            or "CROSS-SPECIES" in upper
            # A user citation is a real improvement over a bare number and
            # is still not a source Terrium verified. It is listed so the
            # summary line stays honest about what the file rests on.
            or "CITED BY YOU" in upper
        ):
            flagged.append(match.group(1))
    return flagged


def provenance_as_json(
    provenance: "dict[str, ParameterProvenance]",
    *,
    rate_law: str | None = None,
    code_version: str | None = None,
) -> str:
    """The same facts as the notes, in a form a program can read.

    WHY THIS EXISTS
    ---------------
    Frank Bergmann, asked whether SED-ML should carry per-parameter
    provenance, said it should not and named where it should go (personal
    communication, 2026-08-25): a COMBINE archive holding the model, the
    experiment, and "some kind of structured format of your provenance
    report (could be json, markdown, anything really)". His objection to
    keeping it only in SBML `notes` was not that notes are wrong -- he
    recommends them -- but that "this makes automated extraction difficult".

    NOT A SECOND SOURCE
    -------------------
    This serialises the SAME objects that wrote the SBML notes -- the dict
    `build_sbml` hands to `annotate_sbml`, passed straight through rather
    than rebuilt from the payload. A second construction from the same
    payload would agree today and drift the first time one of them learned a
    field, which is ADR 0003 with a file format attached.

    It is written to accept either provenance dataclass: the Antimony
    exporter and the SBML exporter carry different shapes on purpose (the
    SBML one holds a reason per reliability axis, the Antimony one does
    not), and `getattr` with a default reads what is there without
    demanding one of them grow a field it has no use for.

    `sort_keys` and one field per line because Eduard Kerkhoven, asked
    whether provenance belongs per-parameter or in Git history, said both,
    with a condition (personal communication, 2026-08-25): "It is essential
    though that the metadata is provided in flat-text format, so that Git
    can easily diff any changes that are made, instead of recording the
    whole set of metadata anew with each release."

    WHAT THIS IS NOT
    ----------------
    Not a standard. No schema in the COMBINE world describes this shape, and
    Bergmann was explicit that there is currently no good machine-readable
    place for source disagreement. It is named `application/json` in the
    manifest rather than dressed up as a specification it does not implement.
    """
    import json

    payload: dict[str, object] = {
        "_format": "terrium-parameter-provenance/1",
        "_note": (
            "Not a COMBINE standard. A structured rendering of the same "
            "facts carried in the SBML notes of the model in this archive, "
            "so they can be read without parsing prose."
        ),
        "parameters": {
            name: {
                "origin": entry.origin,
                "citation": entry.citation,
                "citationStatus": getattr(entry, "citation_status", None),
                "citationSource": getattr(entry, "citation_source", None),
                "referenceId": getattr(entry, "reference_id", None),
                "taxonId": getattr(entry, "taxon_id", None),
                "organism": entry.organism,
                "source": entry.source,
                "crossSpecies": entry.cross_species,
                # Two shapes: (axis, grade) from the Antimony exporter,
                # (axis, grade, reason) from the SBML one. Unpacked by
                # length rather than by assuming, because assuming produces
                # a ValueError on the shape that is actually used here.
                "reliability": {
                    axis[0]: (
                        {"grade": axis[1], "reason": axis[2]}
                        if len(axis) > 2 and axis[2] else axis[1]
                    )
                    for axis in entry.reliability
                },
                "note": entry.note,
                "assayConditions": {
                    "ph": entry.assay_ph,
                    "temperatureC": entry.assay_temperature_c,
                    "buffer": entry.assay_buffer,
                    # Kept as an explicit list rather than dropped. "The
                    # source did not state the pH" is a finding about the
                    # measurement; an absent key would read as "nobody
                    # looked", which is a different thing.
                    "unreported": list(entry.assay_unreported),
                },
            }
            for name, entry in sorted(provenance.items())
        },
    }
    if rate_law is not None:
        payload["rateLaw"] = rate_law
    if code_version is not None:
        payload["codeVersion"] = code_version
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
