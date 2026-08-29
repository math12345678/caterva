#!/usr/bin/env python3
"""Emit a runnable Antimony model with its provenance written inside it.

Reads a JSON payload on stdin, writes Antimony on stdout.

WHY IT IS A SEPARATE PROCESS
----------------------------
The model builders and the annotator are Python; the provenance is assembled
in TypeScript. Rather than reimplement either side in the other language,
this script is the one seam: JSON in, model out.

Reimplementing the builders in TypeScript would create a second definition
of what a Michaelis-Menten model *is*, and the two would drift. ADR 0003
exists because two copies of a single numeric bound drifted; two copies of a
rate law would be worse.

WHAT IT IS FOR
--------------
Professor Herbert Sauro's answer on unsourced parameters contained a
mechanism as well as a policy:

    "...and write a warning comment in the antimony file you generate."

Terrium generated Antimony and never handed it to anyone, so there was
nowhere for that comment to live. This is the export that gives it one. The
resulting file is loadable by Tellurium, libRoadRunner, COPASI or anything
else that reads Antimony — and it carries, in comments, where every number
came from.

Exit codes match the rest of the CLI:
    0  a model was written
    1  the request could not be served
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Terium.core.model_provenance import (  # noqa: E402
    ParameterProvenance,
    annotate_antimony,
    unsourced_parameters,
)

#: domain -> (builder import path, ordered parameter names)
#:
#: The names are the builder's OWN keyword arguments, so a payload is
#: checked against the real signature rather than against a second list that
#: could fall behind it.
#: resolver parameter name -> the symbol the builder actually writes.
#:
#: The resolver speaks `s0`; the Antimony says `S`. Without this map the
#: provenance for `s0` matched nothing, `S` was annotated
#: "NO PROVENANCE RECORDED", and `s0` was reported as an orphan -- all three
#: symptoms of one mismatch, and all three visible only because
#: annotate_antimony reports orphans instead of dropping them. A version
#: that silently dropped unmatched provenance would have shipped a model
#: claiming no source for a value that had one.
#:
#: Names not listed here map to themselves.
SYMBOLS = {
    "s0": "S",
    "i0": "I",
    "e0": "E",
    "r0_recovered": "R",
    "i": "I",
}

BUILDERS = {
    "mm": ("build_michaelis_menten_antimony", ("km", "vmax", "s0")),
    "mm_competitive_inhibition": (
        "build_mm_competitive_antimony",
        ("km", "vmax", "ki", "s0", "i"),
    ),
    "sir": ("build_sir_antimony", ("beta", "gamma", "s0", "i0", "r0_recovered")),
    "seir": (
        "build_seir_antimony",
        ("beta", "sigma", "gamma", "s0", "e0", "i0", "r0_recovered"),
    ),
}


def _assay_number(raw) -> float | None:
    """A reported condition as a number, or None.

    None for anything that is not one -- including the string "unknown",
    which is a real value in payloads assembled by hand. `float("unknown")`
    raises, and a crashing export is a worse answer than an omitted pH; but
    silently coercing something unparseable to 0.0 would be worse still,
    because pH 0 is a legal number and would read as a measurement.
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


def build(payload: dict) -> tuple[int, str]:
    domain = payload.get("domain")
    if domain not in BUILDERS:
        return 1, (
            f"No model builder for domain {domain!r}. "
            f"Known: {', '.join(sorted(BUILDERS))}."
        )

    builder_name, required = BUILDERS[domain]

    parameters = payload.get("parameters") or {}
    missing = [name for name in required if name not in parameters]
    if missing:
        # Refusing rather than defaulting, exactly as the resolver does.
        # An export that quietly filled a gap would produce a file whose
        # comments claim full provenance for a value nobody supplied --
        # the worst possible output of a provenance feature.
        return 1, (
            f"Cannot build a {domain} model: {', '.join(missing)} "
            f"{'were' if len(missing) > 1 else 'was'} not supplied. "
            "Nothing is defaulted here."
        )

    from Terium.continuous import model_building

    builder = getattr(model_building, builder_name)
    try:
        antimony_text = builder(**{name: float(parameters[name]) for name in required})
    except (TypeError, ValueError) as exc:
        return 1, f"Model builder rejected the parameters: {exc}"
    except Exception as exc:  # engine validation errors carry the real reason
        return 1, f"Model builder rejected the parameters: {exc}"

    # Symbols the builder writes that are NOT among its arguments are model
    # structure, not unsourced parameters. `P = 0` in a Michaelis-Menten
    # model says "no product at t=0" -- part of what the model IS, not a
    # number anyone should be asked to cite.
    #
    # Derived from the builder's own signature rather than listed, so a new
    # builder cannot introduce a structural symbol that gets reported as an
    # unsourced measurement.
    structural: dict[str, ParameterProvenance] = {}
    argument_symbols = {SYMBOLS.get(name, name).lower() for name in required}
    from Terium.core.model_provenance import parameters_in

    for symbol in parameters_in(antimony_text):
        if symbol.lower() not in argument_symbols:
            structural[symbol] = ParameterProvenance(
                origin="user",
                note="model structure: fixed by the model definition, not measured",
            )

    provenance: dict[str, ParameterProvenance] = dict(structural)
    for name, entry in (payload.get("provenance") or {}).items():
        reliability = tuple(
            (str(axis), str(grade))
            for axis, grade in (entry.get("reliability") or {}).items()
        )
        assay = entry.get("assayConditions") or {}
        provenance[SYMBOLS.get(name, name)] = ParameterProvenance(
            origin=str(entry.get("origin", "unknown")),
            citation=entry.get("citation"),
            organism=entry.get("organism"),
            source=entry.get("source"),
            citation_status=entry.get("citationStatus"),
            cross_species=bool(entry.get("crossSpecies")),
            reliability=reliability,
            note=entry.get("note"),
            # Read from the SAME payload key as the SBML path below, so the
            # two exports cannot disagree about what a reader is told. A
            # fact present in one artifact and missing from the other makes
            # the omission look like a property of the measurement.
            assay_ph=_assay_number(assay.get("ph")),
            assay_temperature_c=_assay_number(assay.get("temperatureC")),
            assay_buffer=assay.get("buffer"),
            assay_unreported=tuple(assay.get("unreported") or ()),
        )

    result = annotate_antimony(
        antimony_text,
        provenance,
        run_id=payload.get("runId"),
        query=payload.get("query"),
        generated_at=payload.get("generatedAt"),
    )
    return 0, result.text


def build_sbml(payload: dict) -> tuple[int, str, dict]:
    """The same model as `build()`, as SBML with MIRIAM annotations.

    Deliberately built on top of `build()` rather than beside it. Two
    export paths that each construct their own model is the
    duplicate-source-of-truth defect (ADR 0003) with a file format
    attached: they would agree today and drift the first time a builder
    changed. Here the Antimony IS the source, and SBML is a translation of
    it, so the two exports cannot describe different models.

    The provenance is re-derived from the same payload for the same reason
    -- it is read twice from one input, never copied between two.
    """
    code, antimony_or_error = build(payload)
    if code != 0:
        return code, antimony_or_error, {}

    from Terium.core.model_provenance import strip_annotations
    from Terium.core.sbml_provenance import SbmlParameterProvenance, annotate_sbml

    import antimony as antimony_lib

    # Comments are stripped first. Antimony parses them fine, but leaving
    # them in means the same facts exist in two encodings inside one file,
    # and a reader who fixes one has silently not fixed the other.
    plain = strip_annotations(antimony_or_error)
    antimony_lib.clearPreviousLoads()
    if antimony_lib.loadAntimonyString(plain) < 0:
        return 1, f"Antimony rejected the generated model: {antimony_lib.getLastError()}", {}
    sbml_text = antimony_lib.getSBMLString(antimony_lib.getMainModuleName())

    provenance: dict[str, SbmlParameterProvenance] = {}
    for name, entry in (payload.get("provenance") or {}).items():
        # (axis, grade, reason). The reason comes from a SECOND map keyed
        # the same way, rather than a nested object, because the Antimony
        # exporter above consumes the grades alone and reshaping the payload
        # for one consumer would break the other.
        reasons = entry.get("reliabilityReasons") or {}
        reliability = tuple(
            (str(axis), str(grade), str(reasons.get(axis, "")))
            for axis, grade in (entry.get("reliability") or {}).items()
        )
        assay = entry.get("assayConditions") or {}
        provenance[SYMBOLS.get(name, name)] = SbmlParameterProvenance(
            origin=str(entry.get("origin", "unknown")),
            citation=entry.get("citation"),
            citation_source=entry.get("citationSource"),
            reference_id=entry.get("referenceId"),
            organism=entry.get("organism"),
            # Never inferred from the organism NAME. Absent means the taxon
            # was not resolved, and the annotation is then omitted rather
            # than guessed.
            taxon_id=entry.get("taxonId"),
            source=entry.get("source"),
            cross_species=bool(entry.get("crossSpecies")),
            reliability=reliability,
            note=entry.get("note"),
            assay_ph=_assay_number(assay.get("ph")),
            assay_temperature_c=_assay_number(assay.get("temperatureC")),
            assay_buffer=assay.get("buffer"),
            assay_unreported=tuple(assay.get("unreported") or ()),
        )

    # ---- units, before annotation (ADR 0150's claimed and missing work).
    #
    # `declare_units` owns the whole decision: which domains have
    # concentration semantics, whether every model parameter has a stated
    # unit, whether the stated units agree on one scale. A refusal returns
    # the SBML unchanged with per-symbol reasons, and those ride out in
    # the detail dict as `unitsRefused`, so a consumer can tell "declared"
    # from "could not be declared" without diffing the XML.
    #
    # The per-parameter strings come from the same provenance entries as
    # everything else -- the CLI writes each value's normalised unit onto
    # its row (ADR 0146). The one fact only the payload-level `units` key
    # carries is the TIME base of the system; the declarations hard-code
    # per-second rates, so any other base refuses here, before the call,
    # rather than being reinterpreted inside it.
    from Terium.core.sbml_units import UnitsOutcome, declare_units

    # ---- units, before annotation (ADR 0150's claimed and missing work).
    #
    # The module owns the whole judgement: vocabulary, rate detection from
    # the unit string itself (`mM` vs `mM/s`), the case fold shared with
    # annotate_sbml, the one-system check, per-parameter completeness, the
    # domain gate, and the kinetic-law x compartment fix. This block only
    # gathers what the caller SAID -- the per-row units ADR 0146 normalised
    # everything into -- and one fact no row carries: the time base from
    # `units: {concentration, time}`, sent since ADR 0146 and read by
    # nothing until this pass. Per-second is the only base the
    # declarations can state, so any other refuses here, before the call.
    #
    # (This file was, for one evening, the site of a two-agent collision:
    # both authors built this feature at once and the exporter briefly
    # carried each signature against the other's module. The resolution is
    # this split -- the module is the other author's, verbatim; the wiring
    # honours its contract and adds nothing it already owns.)
    parameter_units = {
        SYMBOLS.get(name, name): str(entry["unit"])
        for name, entry in (payload.get("provenance") or {}).items()
        if isinstance(entry, dict) and entry.get("unit")
    }
    stated_time = (payload.get("units") or {}).get("time")
    if stated_time is not None and stated_time != "s":
        units_outcome = UnitsOutcome(
            sbml=sbml_text,
            refusals=[(
                "time",
                f"the caller's time base {stated_time!r} is not seconds; "
                "the declarations state per-second rates, so writing them "
                "for another base would be wrong rather than incomplete",
            )],
        )
    else:
        units_outcome = declare_units(
            sbml_text, parameter_units, domain=str(payload.get("domain"))
        )
    sbml_text = units_outcome.sbml

    outcome = annotate_sbml(
        sbml_text,
        provenance,
        ec_number=payload.get("ecNumber"),
        model_taxon_id=payload.get("modelTaxonId"),
    )
    return 0, outcome.sbml, {
        "unitsDeclared": units_outcome.declared,
        "unitsRefused": [
            {"symbol": symbol, "reason": reason}
            for symbol, reason in units_outcome.refusals
        ],
        "annotated": outcome.annotated,
        "unannotated": outcome.unannotated,
        "cvterms": outcome.cvterms_written,
        # Both numbers, because they answer different questions: what the
        # writer intended, and what an independent parser finds in the bytes
        # this export actually hands over. `annotate_sbml` refuses to return
        # when the second is smaller, so reporting only the first would not
        # mislead -- but it would leave the reader trusting the producer's
        # word for the producer's own output, which is the arrangement the
        # audit exists to replace.
        "triplesReadBack": outcome.triples_read_back,
        "refusedUris": [
            {"parameter": n, "accession": a, "reason": w}
            for n, a, w in outcome.refused_uris
        ],
    }


def build_archive(payload: dict) -> tuple[int, bytes, dict]:
    """The whole run as a COMBINE archive: model + experiment + sources.

    Built on `build_sbml()` for the same reason `build_sbml()` is built on
    `build()`: one model definition, translated, never re-derived. Three
    export paths each constructing their own model is ADR 0003 with file
    formats attached.

    The experiment settings come from the run that actually happened --
    `endTime` and `points` are the ones the CLI reports, not defaults. A
    SED-ML describing a time course nobody ran would be reproducible and
    wrong, which is worse than absent.
    """
    code, sbml_text, detail = build_sbml(payload)
    if code != 0:
        return code, b"", {"error": sbml_text}

    from Terium.core.combine_archive import (
        BIBTEX,
        CFF,
        SBML_L3V2,
        SEDML_L1V3,
        ArchiveEntry,
        build_sedml,
        write_archive,
    )


    end_time = payload.get("endTime")
    points = payload.get("points")
    if not isinstance(end_time, (int, float)) or not isinstance(points, int):
        return 1, b"", {
            "error": (
                "A COMBINE archive needs the time course that was run "
                "(endTime, points). Terrium will not guess them: the archive's "
                "whole purpose is that someone else re-runs the SAME experiment."
            )
        }

    # Read from the MODEL, not from the caller. The call site used to pass
    # `["S", "P"]`, which is right for Michaelis-Menten and silently wrong
    # for a competitively-inhibited model, whose inhibitor would be missing
    # from the report of the very experiment it was the point of.
    from Terium.core.combine_archive import recorded_quantities

    # Everything that VARIES, not just the species. Identical output for
    # every domain today; the difference appears the day a model gains a
    # rule or a non-constant parameter, and the alternative failure is a
    # report quietly missing a curve.
    recorded = recorded_quantities(sbml_text)
    if not recorded:
        return 1, b"", {
            "error": (
                "The model declares no species, so the SED-ML would produce "
                "an empty report -- an archive that runs and reports nothing."
            )
        }

    sedml_text, sedml_errors = build_sedml(
        model_location="model.xml",
        model_id="terrium_model",
        end_time=float(end_time),
        points=int(points),
        recorded=recorded,
    )
    # Every target must select exactly one element in the model that ships
    # beside it. libSEDML validates the document's SHAPE and never resolves
    # the XPaths -- it does not have the model -- so a generated path that
    # points at nothing passes validation, opens fine, and produces a report
    # of empty columns. Checked here, at the one place both halves exist.
    if not sedml_errors:
        from Terium.core.combine_archive import resolve_targets

        resolution = resolve_targets(sbml_text, sedml_text)
        if not resolution.ok:
            broken = "; ".join(
                f"{identifier} selects {count} element(s): {target}"
                for identifier, target, count in resolution.unresolved
            )
            return 1, b"", {
                "error": (
                    "SED-ML targets do not resolve against the model in the "
                    f"same archive: {broken}. An archive whose report columns "
                    "select nothing opens, runs, and reports nothing -- which "
                    "is worse than failing here."
                )
            }

    if sedml_errors:
        # Refusing rather than shipping it. An invalid experiment inside a
        # well-formed archive is the worst shape this feature can take: the
        # file opens, looks complete, and fails at the moment someone is
        # trying to reproduce a result.
        return 1, b"", {"error": "SED-ML failed validation: " + "; ".join(sedml_errors)}

    files = {
        "model.xml": (
            sbml_text,
            ArchiveEntry("model.xml", SBML_L3V2, description="SBML with MIRIAM provenance"),
        ),
        "simulation.sedml": (
            sedml_text,
            ArchiveEntry("simulation.sedml", SEDML_L1V3, master=True),
        ),
    }
    bibtex = payload.get("bibtex")
    if bibtex:
        files["citations.bib"] = (
            bibtex,
            ArchiveEntry("citations.bib", BIBTEX, description="sources behind the values"),
        )

    # How to cite the TOOL, not just the data.
    #
    # Katz's objection was that per-constant citation is confusing; the
    # deeper half of his field's answer (FORCE11 Software Citation
    # Principles, Smith et al. 2016) is that the software producing a result
    # is itself citable and usually goes uncited. Terrium exported a
    # bibliography of everyone else's measurements and no way to cite the
    # thing that assembled them.
    #
    # Verbatim, not regenerated: CITATION.cff is the repository's own
    # statement of how to be cited, and a second rendering of it here would
    # be a second source of truth able to disagree with the first.
    citation_cff = REPO_ROOT / "CITATION.cff"
    if citation_cff.exists():
        files["CITATION.cff"] = (
            citation_cff.read_text(encoding="utf-8"),
            ArchiveEntry("CITATION.cff", CFF, description="how to cite Terrium itself"),
        )

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".omex", delete=False) as handle:
        temporary = pathlib.Path(handle.name)
    try:
        write_archive(temporary, files)
        data = temporary.read_bytes()
    finally:
        temporary.unlink(missing_ok=True)

    return 0, data, {
        **detail,
        "entries": sorted(files) + ["manifest.xml"],
        "hasCitations": bool(bibtex),
    }


def main(argv: list[str] | None = None) -> int:
    # This script is configured entirely through the JSON payload on stdin
    # and takes no command-line arguments. Ignoring them silently is not
    # neutral: `--format sbml` looks exactly like it should work, and
    # running it returns exit 0 with `"format": "antimony"` and a model
    # that is not what was asked for.
    #
    # That is not hypothetical -- it produced a wrong measurement during the
    # ADR 0063 work, where the Antimony export was read as evidence about
    # the SBML one. Same class as `claim_adr.py --help` writing
    # `0044---help.md`: an argument nobody parses is an argument that means
    # whatever the reader hoped.
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        return _fail(
            f"This script takes no command-line arguments (got "
            f"{' '.join(arguments)}). It is configured by the JSON payload "
            f'on stdin; for SBML send {{"format": "sbml", ...}}.'
        )

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")

    if payload.get("format") == "omex":
        code, data, detail = build_archive(payload)
        if code != 0:
            return _fail(detail.get("error", "archive export failed"))
        import base64

        print(
            json.dumps(
                {
                    "ok": True,
                    # Binary, so it crosses the process boundary base64'd.
                    # The TypeScript side writes bytes, never text -- writing
                    # a zip as a utf-8 string corrupts it silently.
                    "modelBase64": base64.b64encode(data).decode("ascii"),
                    "format": "omex",
                    **detail,
                }
            )
        )
        return 0

    if payload.get("format") == "sbml":
        code, text, detail = build_sbml(payload)
        if code != 0:
            return _fail(text)
        print(json.dumps({"ok": True, "model": text, "format": "sbml", **detail}))
        return 0

    code, text = build(payload)
    if code != 0:
        return _fail(text)

    flagged = unsourced_parameters(text)
    print(
        json.dumps(
            {
                "ok": True,
                "model": text,
                "format": "antimony",
                # Reported so the CLI can print a one-line summary without
                # re-parsing the file it just received.
                "unsourced": flagged,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
