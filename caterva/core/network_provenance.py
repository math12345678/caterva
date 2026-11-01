"""You cannot compile a model containing a number nobody sourced.

WHY THIS IS THE LOAD-BEARING PIECE
----------------------------------
`network.py` makes a model a value, which makes arbitrary systems
expressible. On its own that is a downgrade: Caterva's whole claim is that
every number is traceable, and the machinery enforcing it -- the hard rule
in `provenance.ts` -- can only judge parameters it already knows about.

Measured, on the TypeScript side: provenance entries are created only for
keys present in the merged ``DOMAIN_DEFAULTS[domain].parameters``, and
`PARAMETER_NAMES` is a regex over 42 fixed names. Those are fine for a
closed catalogue of thirteen domains. For a model constructed on the fly
they fail in the worst possible direction -- **a parameter with no
provenance entry is invisible to the rule, so it is not refused.** Absence
reads as consent.

This module inverts that, and does it in the engine rather than in a
caller:

  * The quantities to be judged come from `network.quantity_ids()` -- the
    model's own species and parameters. Nobody has to enumerate them in
    advance, because the model already did.
  * A quantity with **no** source is refused. Not warned about, not
    defaulted: refused. Silence is the failure mode a closed catalogue
    could afford and an open one cannot.
  * The check sits at the compile boundary, so it holds no matter which
    front end built the network. Today the rule lives only in the
    TypeScript resolver, which means anything reaching the engine another
    way is unjudged. This is strictly stronger.

ORIGINS
-------
Mirrors `ParameterOrigin` in provenance.ts exactly -- ``resolved``,
``user``, ``llm``, ``default`` -- because two systems enforcing the same
rule under different vocabularies is how the rule ends up meaning two
things. ``llm`` and ``default`` are blocked, which is the same pair
`unverifiedOriginKeys` blocks.

``resolved`` additionally requires a citation. An origin claiming
literature backing without naming the literature is the exact defect this
repository has now found seven times in its own citations; a resolved
value with nothing to check is not resolved, it is asserted.
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

try:
    from caterva.core.data_structures import ModelBuildError
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.data_structures import ModelBuildError  # type: ignore[no-redef]

try:
    from caterva.core.network import ReactionNetwork, compile_to_antimony
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        raise
    from core.network import (  # type: ignore[no-redef]
        ReactionNetwork,
        compile_to_antimony,
    )


#: The four origins, spelled as `provenance.ts` spells them.
RESOLVED = "resolved"
USER = "user"
LLM = "llm"
DEFAULT = "default"

VALID_ORIGINS = frozenset({RESOLVED, USER, LLM, DEFAULT})

#: Blocked by the hard rule. Same pair as `unverifiedOriginKeys`.
#:
#: `llm` is blocked because a model proposing its own constants is the
#: thing this product exists to refuse. `default` is blocked because a
#: teaching default is a number chosen by this project, and a number chosen
#: by this project reported as a result is indistinguishable, to a reader,
#: from one measured in a laboratory.
BLOCKED_ORIGINS = frozenset({LLM, DEFAULT})


@dataclass(frozen=True)
class QuantitySource:
    """Where one number in a model came from.

    `citation` is required when `origin` is ``resolved`` and meaningless
    otherwise -- a user's own measurement needs no literature reference,
    and demanding one would push callers toward inventing a plausible
    citation to satisfy a check, which is worse than having no check.
    """

    origin: str
    citation: Optional[str] = None
    note: Optional[str] = None

    def problems(self, quantity: str) -> List[str]:
        if self.origin not in VALID_ORIGINS:
            return [
                f"{quantity}: unknown origin {self.origin!r}. Valid origins "
                f"are {', '.join(sorted(VALID_ORIGINS))}."
            ]
        if self.origin in BLOCKED_ORIGINS:
            return [
                f"{quantity}: origin {self.origin!r} is not a source. "
                + (
                    "A value the model proposed is a guess until literature "
                    "confirms it."
                    if self.origin == LLM
                    else "A teaching default is a number this project chose, "
                    "not one anybody measured."
                )
            ]
        if self.origin == RESOLVED and not (self.citation or "").strip():
            return [
                f"{quantity}: origin 'resolved' claims literature backing "
                f"but names no citation. A resolved value with nothing to "
                f"check is asserted, not resolved."
            ]
        return []


def unsourced_quantities(
    network: ReactionNetwork, sources: Mapping[str, QuantitySource]
) -> List[str]:
    """Every reason this network may not be compiled, or an empty list.

    Enumerates from the NETWORK, never from the sources. That direction is
    the whole design: a quantity the caller forgot to describe is a
    quantity nobody sourced, and iterating the sources instead would let it
    pass by being absent.
    """
    problems: List[str] = []
    for quantity in network.quantity_ids():
        source = sources.get(quantity)
        if source is None:
            problems.append(
                f"{quantity}: no source recorded. Every species initial and "
                f"every parameter needs one -- resolve it from literature, "
                f"or supply it yourself and it will be recorded as yours."
            )
            continue
        problems.extend(source.problems(quantity))

    # Sources for quantities the model does not have are reported too, but
    # as a mismatch rather than a refusal: it usually means a rename landed
    # in one place and not the other, and silently ignoring it is how a
    # value ends up attached to nothing.
    orphans = sorted(set(sources) - set(network.quantity_ids()))
    for orphan in orphans:
        problems.append(
            f"{orphan}: a source was supplied for a quantity this model does "
            f"not contain. Renamed, or attached to the wrong model?"
        )
    return problems


def compile_with_provenance(
    network: ReactionNetwork,
    sources: Mapping[str, QuantitySource],
) -> str:
    """Compile to Antimony, or refuse and name every unsourced quantity.

    Refuses all at once rather than one at a time. A caller assembling a
    model wants the whole list, and reporting the first failure turns a
    single fix into a sequence of them.
    """
    network.validate()
    problems = unsourced_quantities(network, sources)
    if problems:
        raise ModelBuildError(
            f"model {network.name!r} contains {len(problems)} quantity "
            f"problem(s) and will not be compiled:\n  - "
            + "\n  - ".join(problems)
        )
    return compile_to_antimony(network, validate=False)


def provenance_report(
    network: ReactionNetwork, sources: Mapping[str, QuantitySource]
) -> Dict[str, Dict[str, Optional[str]]]:
    """What backs each number, for a caller that wants to show its working.

    Returned in the network's own declaration order so a report reads in
    the same order as the model.
    """
    report: Dict[str, Dict[str, Optional[str]]] = {}
    for quantity in network.quantity_ids():
        source = sources.get(quantity)
        report[quantity] = {
            "origin": source.origin if source else None,
            "citation": source.citation if source else None,
            "note": source.note if source else None,
        }
    return report


__all__ = [
    "QuantitySource",
    "RESOLVED",
    "USER",
    "LLM",
    "DEFAULT",
    "VALID_ORIGINS",
    "BLOCKED_ORIGINS",
    "unsourced_quantities",
    "compile_with_provenance",
    "provenance_report",
]
