"""Parameterize a whole model from the literature, and say whether it holds.

THE JOB
-------
A researcher building a kinetic model spends days doing this by hand: for
each constant the model needs, search BRENDA and the literature, pick a
value, record where it came from, and -- the part that is easy to forget --
check that the values chosen are mutually usable.

Caterva already does the per-parameter half well. `fallback_logic` resolves
one constant with its organism, its assay conditions and a citation, and
`provenance.ts` refuses anything unsourced. What has never existed is the
whole-model half: resolve everything the model needs, judge the set, and
say plainly what is missing.

This module is that. It is deliberately thin, because the two hard pieces
already exist and this composes them:

    resolve each quantity        <- the caller's resolver (injected)
    judge whether they compose   <- model_compatibility.assess
    report gaps and findings     <- here

WHY THE RESOLVER IS INJECTED
----------------------------
`resolve` is a callable the caller supplies, not an import. Three reasons,
in increasing order of importance:

  * the real one needs BRENDA and a network, and a module that could only
    be exercised online is a module nobody exercises;
  * different quantities resolve through different machinery today
    (BRENDA for kinetics, a registry for epidemiology, stdpopsim for
    population genetics), and hard-coding one would quietly make the others
    second-class;
  * it makes the ORDER of operations testable, which is where the
    interesting failure lives -- a version that judged compatibility before
    all resolutions had returned would report a coherent model on partial
    data.

WHAT IT REFUSES TO DO
---------------------
It does not fill a gap. A quantity nothing could resolve comes back in
`missing`, named, with whatever the resolver said about why. That list is
the useful output: it is the set of measurements that would complete the
model, which is a better answer than a model with an invented number in it.

It also does not rank or choose between candidate values beyond what the
resolver returned. Picking among conflicting literature values is a
scientific judgement with a real methodology behind it, and doing it by a
heuristic here would be the kind of invisible decision this codebase spends
its time removing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from model_compatibility import (
        CompatibilityReport,
        ParameterSource,
        assess,
    )
except ImportError:  # pragma: no cover - package-style import
    from Tests.model_compatibility import (  # type: ignore[no-redef]
        CompatibilityReport,
        ParameterSource,
        assess,
    )


@dataclass(frozen=True)
class ParameterRequest:
    """One quantity a model needs, and enough context to look it up."""

    quantity: str
    #: What the quantity belongs to: an enzyme name, a disease, a species.
    subject: Optional[str] = None
    #: The substrate, for a kinetic constant that has one.
    substrate: Optional[str] = None
    #: The organism asked about. Absent means "whatever the resolver's
    #: documented default is", which the resolver states, not this module.
    organism: Optional[str] = None
    #: EC number, when the quantity resolves through BRENDA. Carried here
    #: rather than looked up per-scout so one enzyme identification serves
    #: every constant the model needs from it.
    ec_number: Optional[str] = None
    #: Which BRENDA table to read: "km" | "ki" | "kcat". Distinct from
    #: `quantity`, which is the model's own name for the symbol -- a
    #: network may call it `Km_glucose` while the table is still "km".
    table: Optional[str] = None
    #: The unit the model expects this constant in, when the caller knows.
    #: Checked at substitution; nothing is converted. Absent means no unit
    #: check is possible, and the report says so rather than implying one.
    expected_unit: Optional[str] = None
    #: What the model is OF, for the resolver to rank rows by before it
    #: chooses one (fallback_logic.resolve_kinetic_value's `isoform`,
    #: `inhibition_mode` and `model_substrate`): the isoform the model is
    #: about, the inhibition mode of the motif this constant belongs to (a Ki
    #: only), and the model's substrate, which for a Ki is not `substrate`
    #: (BRENDA files a Ki under the inhibitor). Absent means the resolver
    #: ranks on evidence alone, as it did for every request before
    #: 2026-09-30, when `caterva compose` ranked afterwards, among the rows
    #: the evidence had already narrowed to, and could carry another row than
    #: the API for the same model (caterva/compose/narrowed.py).
    isoform: Optional[str] = None
    inhibition_mode: Optional[str] = None
    model_substrate: Optional[str] = None
    #: The model's inhibition mode, sent WITHOUT ranking by it
    #: (`resolve_kinetic_value`'s `compare_mode`), with `model_substrate`:
    #: the resolver answers as if asked for no mode and says what it would
    #: have returned for this one. `caterva compose --any-mode` sends it in
    #: place of `inhibition_mode`, so it carries the row the API and the
    #: TypeScript CLI return when no mode is sent, and its report can still
    #: name the row the default would carry.
    compare_mode: Optional[str] = None


@dataclass(frozen=True)
class Resolution:
    """What a resolver came back with for one request."""

    request: ParameterRequest
    source: Optional[ParameterSource] = None
    #: Why nothing was found, in the resolver's own words. Never
    #: paraphrased here: "no BRENDA entry for this substrate" and "found,
    #: in a rabbit, and you did not ask for rabbit data" are different
    #: facts and a summary of both would be neither.
    reason: Optional[str] = None
    #: The resolver's word for what happened when nothing is used
    #: (`KineticResult.source`: "isoform_withheld", "mode_withheld", ...),
    #: so a caller can tell values found and refused from values not found
    #: without reading `reason`. None when a value was used, or when the
    #: resolver gave no word.
    outcome: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.source is not None


@dataclass(frozen=True)
class ParameterizationReport:
    resolutions: Tuple[Resolution, ...]
    compatibility: CompatibilityReport

    @property
    def resolved(self) -> Tuple[Resolution, ...]:
        return tuple(r for r in self.resolutions if r.found)

    @property
    def missing(self) -> Tuple[Resolution, ...]:
        return tuple(r for r in self.resolutions if not r.found)

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def usable(self) -> bool:
        """Every quantity found AND the set holds together.

        Both halves, deliberately. A complete model assembled from
        incompatible sources is not usable, and it is the case that looks
        most like success -- every parameter present, every citation real.
        """
        return self.complete and self.compatibility.coherent

    def summary(self) -> str:
        total = len(self.resolutions)
        found = len(self.resolved)
        lines = [f"Parameterized {found} of {total} quantities from literature."]

        if self.missing:
            lines.append(
                "Could not resolve: "
                + "; ".join(
                    f"{r.request.quantity}"
                    + (f" ({r.reason})" if r.reason else "")
                    for r in self.missing
                )
                + ". Those are the measurements that would complete this "
                "model; Caterva does not fill them in."
            )

        lines.append(self.compatibility.summary())

        if self.usable:
            lines.append(
                "This set is complete and mutually compatible: it can be "
                "simulated as it stands."
            )
        elif self.complete:
            lines.append(
                "Every quantity was found, and the set does NOT hold "
                "together -- which is the case that most resembles success: "
                "every value present, every citation real."
            )
        return " ".join(lines)


def parameterize(
    requests: Sequence[ParameterRequest],
    resolve: Callable[[ParameterRequest], Resolution],
) -> ParameterizationReport:
    """Resolve every quantity a model needs, then judge the set.

    Order matters and is the reason this is a function rather than a
    comprehension: compatibility is assessed ONCE, over everything that
    resolved, after every resolution has returned. Judging incrementally
    would report a coherent model on partial data -- true of the first
    value and meaningless about the model.
    """
    resolutions = tuple(resolve(request) for request in requests)
    sources = [r.source for r in resolutions if r.source is not None]
    return ParameterizationReport(
        resolutions=resolutions,
        compatibility=assess(sources),
    )


def requests_for_network(
    quantity_ids: Sequence[str],
    subject: Optional[str] = None,
    organism: Optional[str] = None,
    skip: Sequence[str] = (),
) -> List[ParameterRequest]:
    """Turn a model's own quantity list into lookup requests.

    Pairs with `caterva/core/network.py`'s `quantity_ids()`, so a
    constructed model can be handed straight to the literature layer
    without anyone re-listing what it needs -- the list that used to be
    re-typed per domain, and drifted.

    `skip` is for quantities the caller already has: their own bench
    measurements, and scenario choices that no literature could supply.
    """
    skipped = set(skip)
    return [
        ParameterRequest(quantity=q, subject=subject, organism=organism)
        for q in quantity_ids
        if q not in skipped
    ]


__all__ = [
    "ParameterRequest",
    "Resolution",
    "ParameterizationReport",
    "parameterize",
    "requests_for_network",
]
