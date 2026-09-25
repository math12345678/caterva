"""The join between the live resolver and the compatibility judge.

`fallback_logic.resolve_kinetic_value` already returns everything needed to
judge whether a value belongs in a model -- the organism, the assay pH and
temperature, the buffer, the citation, and whether it was transferred from
another species. Nothing had ever read those fields together. This converts
one `KineticResult` into one `ParameterSource` so the set can be assessed.

WHY A "NOT FOUND" NEEDS SIX DIFFERENT SENTENCES
-----------------------------------------------
`KineticResult.source` distinguishes six outcomes and they are not
interchangeable to the person reading the report:

    brenda_exact             found, in the organism asked for (or, when no
                             organism was asked for, the best-evidenced row
                             of any, named with its real organism)
    brenda_cross_species     found, in another organism, opted into
    cross_species_withheld   exists, in another organism, NOT opted into
    cross_species_too_distant exists, too far away to offer
    literature_candidates    no database value; papers that may hold one
    not_found                nothing anywhere that was searched

"Nothing exists" and "a rabbit measurement exists and you did not ask for
rabbit data" lead to different next actions -- the second is an opt-in away
from an answer. Collapsing them into "not found" is the failure ADR 0024
describes, so each keeps its own sentence and its own available organisms.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

def _parameter_source_cls():
    """Import `ParameterSource` from wherever the checkout has it.

    `Tests/` is a flat module directory rather than a package, so this
    resolves both layouts instead of assuming one.
    """
    try:
        from Tests.model_compatibility import ParameterSource  # type: ignore
        return ParameterSource
    except ImportError:
        from Terium.checkout import literature_module
        ParameterSource = literature_module("model_compatibility").ParameterSource
        return ParameterSource


#: Maps `KineticResult.source` to what the reader should do about it.
#: Every value the resolver can emit appears here; `unknown_source` below
#: fires if the resolver grows a seventh and this is not updated, rather
#: than the new outcome silently reading as "not found".
NOT_FOUND_REASONS = {
    "cross_species_withheld": (
        "no value in the organism requested; measurements exist in other "
        "organisms, and one is never substituted for yours (ADR 0024) -- "
        "re-run with --organism set to one of them to build the model there"
    ),
    "cross_species_too_distant": (
        "values exist only in organisms too distantly related to offer"
    ),
    "literature_candidates": (
        "no database value; candidate papers were found but a number was "
        "not extracted from free text"
    ),
    "not_found": "nothing found in BRENDA or the literature search",
}

FOUND_SOURCES = frozenset({"brenda_exact", "brenda_cross_species"})


def citation_text(citation: Any) -> Optional[str]:
    """A one-line human-readable citation, or None.

    THE FIELD NAME THAT WAS NEVER THERE (ADR 0178)
    ----------------------------------------------
    This tried `reference` first and `Citation` declares `reference_id`
    (`Tests/citation.py`). The attribute never existed, so every BRENDA
    citation fell through to `url` and every artefact built from the agent
    stack printed

        url:https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27

    which names the ENZYME PAGE and not the reference. Two different
    measurements from two different papers produced the identical string,
    and BRENDA has no working per-reference deep link (`citation.py` says
    so at length, having live-checked it), so the reference_id is the only
    thing that identifies which row a number came from. It was the one
    field being dropped.

    The form matches `Tests/lab_report.py`'s, which had it right all along:
    "BRENDA ref 286469". The two are deliberately the same so a reader
    cannot tell from a citation which of Terrium's two paths produced it.

    Kept tolerant: `Citation` has grown fields over time and a formatting
    change there must not break model assembly.
    """
    if citation is None:
        return None

    source = getattr(citation, "source", None)
    reference = getattr(citation, "reference_id", None) or getattr(citation, "reference", None)
    if source and reference:
        text = f"{source} ref {reference}"
        title = getattr(citation, "title", None)
        return f"{text} — “{title}”" if title else text
    if reference:
        return f"ref {reference}"

    for attribute in ("pmid", "doi", "url", "title"):
        value = getattr(citation, attribute, None)
        if value:
            return f"{attribute}:{value}"
    if source:
        return str(source)
    return str(citation)


def to_parameter_source(
    quantity: str,
    result: Any,
) -> Tuple[Optional[Any], Optional[str]]:
    """`(ParameterSource, None)` when found, `(None, reason)` when not.

    A tuple rather than an exception or a sentinel because both halves are
    ordinary outcomes here: a model with a gap in it is the normal result of
    asking the literature for something nobody measured.
    """
    ParameterSource = _parameter_source_cls()

    if not getattr(result, "found", False):
        source = getattr(result, "source", "not_found")
        reason = NOT_FOUND_REASONS.get(source)
        if reason is None:
            reason = (
                f"resolver returned an outcome this adapter does not know "
                f"how to explain ({source!r})"
            )
        available = list(getattr(result, "cross_species_organisms_available", []) or [])
        if available:
            reason += f" -- available in: {', '.join(sorted(available))}"
        return None, reason

    return (
        ParameterSource(
            quantity=quantity,
            value=getattr(result, "value", None),
            unit=getattr(result, "unit", None),
            organism=getattr(result, "organism", None),
            ph=getattr(result, "assay_ph", None),
            temperature_c=getattr(result, "assay_temperature_c", None),
            buffer=getattr(result, "assay_buffer", None),
            citation=citation_text(getattr(result, "citation", None)),
            cross_species=bool(getattr(result, "cross_species_flag", False)),
            origin="literature",
            explicitly_unreported=tuple(
                getattr(result, "assay_unreported", []) or []
            ),
            candidates=tuple(getattr(result, "ensemble_candidates", []) or []),
        ),
        None,
    )


__all__ = [
    "to_parameter_source",
    "citation_text",
    "NOT_FOUND_REASONS",
    "FOUND_SOURCES",
]


# ---------------------------------------------------------------------------
# Putting resolved values back into the model
# ---------------------------------------------------------------------------


class UnresolvedQuantity(ValueError):
    """A quantity the model needs has no measured value."""


class UnitMismatch(ValueError):
    """A resolved value's unit is not the one the model was built in."""


def with_resolved_values(network: Any, resolutions: Any) -> Any:
    """Return `network` with every resolved constant substituted in.

    STRICT ON PURPOSE
    -----------------
    A network is constructed with placeholder values -- `mm_competitive_network(
    km=0.1, ki=0.5, ...)` -- so that its structure can be checked before any
    literature is searched. If Km resolves and Ki does not, substituting only
    Km leaves 0.5 sitting in the model: a number nobody measured, in a
    simulation that runs and plots and looks exactly like a sourced one.

    So this raises rather than partially substituting. The caller decides
    what to do about a gap; it must not be decided by omission.

    UNITS
    -----
    `ReactionNetwork` carries no units -- it is a structure, and the values
    in it are whatever the constructor was given. That means substitution
    crosses a boundary this module cannot check on its own, so it checks the
    only thing it can: if a request declared `expected_unit`, the resolved
    unit must match it. When no unit was declared nothing is verified, and
    the unit that was substituted is returned so the caller can say so
    rather than implying a check that did not happen.
    """
    from dataclasses import replace

    values: dict = {}
    units: dict = {}
    for quantity, resolution in resolutions.items():
        source = getattr(resolution, "source", None)
        if source is None:
            raise UnresolvedQuantity(
                f"{quantity} has no measured value, so the model cannot be "
                f"materialised: substituting the others would leave "
                f"{quantity} at the placeholder the network was constructed "
                f"with, and it would simulate"
            )
        expected = getattr(getattr(resolution, "request", None), "expected_unit", None)
        if expected and source.unit and expected.strip() != source.unit.strip():
            raise UnitMismatch(
                f"{quantity} was resolved in {source.unit!r} and this model "
                f"was built in {expected!r}. Terrium does not convert: the "
                f"conversion factor is not always dimensionless (mM to mg/mL "
                f"needs a molecular weight) and guessing one would invent a "
                f"quantity."
            )
        values[quantity] = source.value
        units[quantity] = source.unit

    parameters = tuple(
        replace(p, value=values[p.id]) if p.id in values else p
        for p in network.parameters
    )
    species = tuple(
        replace(s, initial=values[s.id]) if s.id in values else s
        for s in network.species
    )
    unknown = set(values) - {p.id for p in network.parameters} - {
        s.id for s in network.species
    }
    if unknown:
        raise UnresolvedQuantity(
            f"resolved {sorted(unknown)}, which this network does not "
            f"contain -- the request and the model disagree about what is "
            f"being built"
        )
    return replace(network, parameters=parameters, species=species)
