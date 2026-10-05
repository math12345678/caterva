"""One run of `caterva rates` as a library call: what the command and Caterva Studio share.

`caterva rates` reads a file, checks that the question is well formed,
fits, and compares with the literature. Studio asks the same question from a
request body and must not copy that sequence, so it lives here once: the
command's `main` and the Studio adapter both call `validate_question` and
`execute`, and the report they print or serialise is a view of the one
`Analysis` that returns. Nothing in this module prints, exits or reads a
file; the command turns its exceptions into exit codes and Studio turns them
into a refusal with the same words.

`on_step` is the one addition for a caller that wants progress and a way to
stop: it is called with (stage key, label, steps done, steps in all) before
each law is fitted, and an exception it raises ends the run at that point.
The command passes none, so its behaviour and output are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from caterva.rates.analysis import Analysis, Options, analyse, compare_literature
from caterva.rates.literature import LiteratureUnavailable
from caterva.rates.table import Dataset
from caterva.rates.uncertainty import resolve

#: (key, label, steps done, steps in all): see the module docstring.
StepCallback = Callable[[str, str, int, int], None]


class QuestionError(ValueError):
    """The question was not well formed: the command's exit code 2."""


@dataclass(frozen=True)
class LiteratureQuery:
    ec: str
    organism: Optional[str] = None
    substrate: Optional[str] = None
    inhibitor: Optional[str] = None
    isoform: Optional[str] = None


@dataclass
class Execution:
    analysis: Analysis
    #: A comparison with the literature was asked for and declined.
    refused: bool = False
    #: Why, one entry per declined comparison.
    refusal_reasons: List[str] = field(default_factory=list)


def validate_question(*, level: float, significance: float, ec: Optional[str] = None,
                      organism: Optional[str] = None, substrate: Optional[str] = None,
                      inhibitor: Optional[str] = None, isoform: Optional[str] = None) -> None:
    """Raise QuestionError for a combination of options that has no meaning,
    in the words `caterva rates` prints before exit 2."""
    if not 0.0 < level < 1.0:
        raise QuestionError(f"--level is a probability between 0 and 1 (0.95, not 95); got {level:g}")
    if not 0.0 < significance < 1.0:
        raise QuestionError(f"--significance is a probability between 0 and 1; got {significance:g}")
    wants_literature = bool(substrate or inhibitor or isoform)
    if wants_literature and not ec:
        raise QuestionError("--substrate, --inhibitor and --isoform name what to look up in the "
                            "literature, and need --ec to say which enzyme")
    if ec and not (substrate or inhibitor):
        raise QuestionError("--ec compares the fitted constants with cited ones, and needs "
                            "--substrate (for Km) or --inhibitor (for Ki) to say which")
    if ec and not organism:
        raise QuestionError("--ec needs --organism: a Km or a Ki is a property of one organism's "
                            "enzyme, and borrowing another's would compare different proteins")


def check_inhibitor_asked(data: Dataset, inhibitor: Optional[str]) -> None:
    if inhibitor and not data.has_inhibitor:
        raise QuestionError("--inhibitor names the inhibitor whose Ki to look up, and the file has "
                            "no rate measured with an inhibitor")


def execute(data: Dataset, *, sigma_from: Optional[str] = None, error_model: Optional[str] = None,
            model: str = "auto", level: float = 0.95, significance: float = 0.05,
            linearizations: bool = False, literature: Optional[LiteratureQuery] = None,
            resolver: Any = None, on_step: Optional[StepCallback] = None) -> Execution:
    """Resolve the uncertainty, fit, test and (when asked) compare with the
    literature. Raises what the command turns into exit 3: NoUncertainty,
    analysis.Refused, fit.FitRefused."""
    uncertainty = resolve(data, sigma_from, error_model)
    options = Options(model=model, level=level, significance=significance,
                      linearizations=linearizations)
    analysis = analyse(data, uncertainty, options, on_step=on_step)
    refused = False
    reasons: List[str] = []
    if literature is not None and literature.ec:
        from caterva.compose.organisms import normalise_organism

        organism, read_as = normalise_organism(literature.organism)
        if read_as:
            analysis.notes.append(read_as)
        try:
            compare_literature(analysis, ec=literature.ec.strip(), organism=organism,
                               substrate=literature.substrate, inhibitor=literature.inhibitor,
                               isoform=literature.isoform, resolver=resolver)
        except LiteratureUnavailable as exc:
            analysis.literature = []
            analysis.literature_refused = str(exc)
        except Exception as exc:  # noqa: BLE001 - a failed search is a refusal with a reason, as in compose
            analysis.literature = []
            analysis.literature_refused = f"the literature search failed: {type(exc).__name__}: {exc}"
        # A comparison this command declined is a refusal (exit 3); a
        # resolver that ran and found no row has answered, as in compose.
        refused = analysis.literature_refused is not None or any(
            c.declined for c in analysis.literature)
        if refused:
            reasons = ([analysis.literature_refused] if analysis.literature_refused else
                       [f"{c.constant}" + (f" [{c.group}]" if c.group else "") + f": {c.refused}"
                        for c in analysis.literature if c.declined])
    return Execution(analysis, refused, reasons)


__all__ = ["Execution", "LiteratureQuery", "QuestionError", "StepCallback", "check_inhibitor_asked",
           "execute", "validate_question"]
