"""Kind `compose`: `caterva compose DESCRIPTION [...]`, as a run (owner: sci-kinetics).

WHAT IT WILL CALL (caterva/compose/__main__.py), in the CLI's order
    pipeline.compose(...)                        the model, or UnrecognisedShape (exit 3)
    __main__._search_the_literature(model, args) when a subject is named (network,
                                                 literature layer; seconds to a minute)
    __main__._precompute_for_verdict(args, model) validate / robustness before the verdict
    report.dossier(...)                          stability, time course, ranking, sweeps, verdict
    __main__._analyses(args, model, precomputed) the analysis sections (robustness can take
                                                 minutes: N full steady-state searches)
    export.provenance_of(model, measured=...)    every number's origin, and the four exports
                                                 (to_sbml, to_antimony, to_parameter_csv,
                                                 to_methods_paragraph), each ExportRefused-able

WHAT HAS NO STRUCTURED FORM YET (add an accessor beside the renderer, never a
second computation; see CONTRACT.md "Gaps")
    `_analyses` builds `Sections()` on stdout and each section's report object
    (ScaleReport, RobustnessReport, DesignReport, ...) is made inside a closure
    and dropped once its text is printed. The adapter needs the stream and the
    objects: give `_analyses` a `stream` argument and return the section
    records alongside the exit code.
    `_search_the_literature` and `_precompute_for_verdict` are private and
    `caterva md` already imports the first; make both public under the
    same behaviour rather than copying them. The CLI writes exports in a
    separate run (`--export` refuses the analysis flags); the studio
    writes all four from the one composed model with `export.provenance_of`
    and the same writers, each as an artifact, and records an
    ExportRefused as ExportInfo.refused.

Registers the kind (serial=True: it drives roadrunner) and the two
endpoints it owns, compose_shapes and normalise_organism
(`registry.add_endpoint(..., owner="compose")`).
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-kinetics builds this adapter."""
