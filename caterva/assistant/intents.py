"""Structured intents: what the assistant may PROPOSE, and the validator that disposes of it.

THE RULE
--------
A model never authors a scientific value that reaches a result. For
"describe it" (Compose) it may return a small structured intent: a shape from
the grammar's own library, a count of steps or a named variant where the
engine would otherwise refuse to choose, and a few names the person's own
words contain. This module turns that into an ordinary compose request, or
rejects it with the reasons. The engine's deterministic grammar then has the
last word twice: the description built here must be recognised as the
proposed shape (so the assistant cannot name a shape the grammar would not
build), and `grammar.recognise` is run on it so the person is shown the
engine's own reading before confirming.

WHAT IS NEVER TAKEN FROM THE MODEL
----------------------------------
The description text sent to compose is BUILT here from the shape's own
`describes` line and a variant word from the table below. Free text from the
model never reaches the engine. A number is accepted only as a step count
within the grammar's own limit. An EC number is accepted only if the
deterministic enzyme finder listed it. An organism is normalised by the
engine's own `normalise_organism`. A substrate or inhibitor name is accepted
only if it appears in the person's own words.

THE VARIANT TABLE
-----------------
Where the grammar branches on a word (competitive or uncompetitive, ordered
or ping-pong, coherent or incoherent) the intent must name the variant: the
engine either refuses to choose (bi-substrate, feed-forward) or silently
defaults (inhibition defaults to competitive), and a silent default chosen on
a person's behalf is exactly what this tool exists to avoid. The table is
checked against the grammar in tests: a variant that does not reach its own
shape is a failing test, not a runtime surprise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

#: shape -> {variant: the words that make the grammar pick it}
VARIANTS: Mapping[str, Mapping[str, str]] = {
    "inhibition": {
        "competitive": "Michaelis-Menten with a competitive inhibitor",
        "uncompetitive": "Michaelis-Menten with an uncompetitive inhibitor",
        "noncompetitive": "Michaelis-Menten with a noncompetitive inhibitor",
        "mixed": "Michaelis-Menten with a mixed inhibitor",
        "substrate": "Michaelis-Menten with substrate inhibition",
        "product": "Michaelis-Menten with product inhibition",
    },
    "feedforward_loop": {
        "coherent": "a coherent feed-forward loop",
        "incoherent": "an incoherent feed-forward loop",
    },
    "bi_substrate": {
        "ordered": "an enzyme with two substrates, ordered mechanism",
        "ping-pong": "an enzyme with two substrates, ping-pong mechanism",
    },
}

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,'()+\-\[\]/.]{0,78}")
_EC = re.compile(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}\.(?:n?[0-9]{1,4})")
_ALLOWED_KEYS = frozenset({"shape", "stages", "variant", "substrate", "inhibitor", "organism", "subject_ec"})


class IntentRejected(ValueError):
    """The proposal cannot be built; `reasons` say why, one per problem."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


@dataclass(frozen=True)
class Shape:
    name: str
    describes: str
    needs_stages: bool
    variants: Tuple[str, ...]


def shape_catalogue() -> List[Shape]:
    """The grammar's shapes as machine-readable definitions, read from the grammar itself."""
    from caterva.compose.grammar import RULES

    return [Shape(r.name, r.describes, r.describes.startswith("N "), tuple(VARIANTS.get(r.name, {})))
            for r in sorted(RULES, key=lambda r: r.name)]


def max_stages() -> int:
    from caterva.compose.grammar import MAX_INFERRED_STAGES

    return int(MAX_INFERRED_STAGES)


def winning_rule(description: str) -> str:
    """The rule the grammar's matcher would pick for `description`, or '' (same logic as grammar.recognise)."""
    from caterva.compose.grammar import RULES

    lowered = description.lower().strip()
    candidates = [r for r in RULES if all(w in lowered for w in r.requires)
                  and (not r.triggers or any(t in lowered for t in r.triggers))]
    return max(candidates, key=lambda r: r.priority).name if candidates else ""


def description_for(shape: Shape, stages: Optional[int], variant: Optional[str]) -> str:
    if variant is not None:
        return VARIANTS[shape.name][variant]
    if shape.needs_stages:
        return re.sub(r"^N ", f"{stages} ", shape.describes)
    return shape.describes


def _in_words(name: str, user_text: str) -> bool:
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()  # noqa: E731
    return bool(norm(name)) and norm(name) in norm(user_text)


@dataclass
class DescribeIntent:
    """A validated proposal, with the compose request it would run and the engine's own reading of it."""

    shape: str
    description: str
    request: Dict[str, Any]
    #: (field, value) the assistant proposed that go into the request: recorded as 'suggested by', confirmed or not.
    suggested: List[Tuple[str, Any]] = field(default_factory=list)
    reading: Optional[str] = None
    organism_note: Optional[str] = None
    stages: Optional[int] = None
    variant: Optional[str] = None


def validate_describe(obj: Any, user_text: str, ec_candidates: Set[str]) -> DescribeIntent:
    """The intent as an engine request, or IntentRejected with every reason found."""
    reasons: List[str] = []
    if not isinstance(obj, dict):
        raise IntentRejected(["the reply was not a JSON object"])
    extra = sorted(set(obj) - _ALLOWED_KEYS)
    if extra:
        reasons.append(f"fields that are not part of an intent: {', '.join(map(str, extra))}")
    shapes = {s.name: s for s in shape_catalogue()}
    name = obj.get("shape")
    shape = shapes.get(name) if isinstance(name, str) else None
    if shape is None:
        reasons.append("the shape is not one of the grammar's shapes" if isinstance(name, str) else
                       "no shape was proposed")
        raise IntentRejected(reasons)

    stages = obj.get("stages")
    if shape.needs_stages:
        limit = max_stages()
        if isinstance(stages, bool) or not isinstance(stages, int) or not 1 <= stages <= limit:
            reasons.append(f"{shape.name} needs a number of steps from 1 to {limit}")
            stages = None
    elif stages is not None:
        reasons.append(f"{shape.name} does not take a number of steps")
        stages = None

    variant = obj.get("variant")
    if shape.variants:
        if not isinstance(variant, str) or variant not in shape.variants:
            reasons.append(f"{shape.name} needs one of these variants, named: {', '.join(shape.variants)}")
            variant = None
    elif variant is not None:
        reasons.append(f"{shape.name} has no variants")
        variant = None

    request: Dict[str, Any] = {}
    suggested: List[Tuple[str, Any]] = [("shape", shape.name)]
    if stages is not None:
        suggested.append(("stages", stages))
    if variant is not None:
        suggested.append(("variant", variant))

    for key in ("substrate", "inhibitor"):
        value = obj.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not _NAME.fullmatch(value.strip()):
            reasons.append(f"{key} is not a plain name")
        elif not _in_words(value, user_text):
            reasons.append(f"{key} {value!r} is not in your own words, so it was not accepted")
        else:
            request[key] = value.strip()
            suggested.append((key, value.strip()))

    organism_note = None
    organism = obj.get("organism")
    if organism is not None:
        from caterva.compose.organisms import normalise_organism

        if not isinstance(organism, str) or not _NAME.fullmatch(organism.strip()):
            reasons.append("organism is not a plain name")
        elif not _in_words(organism, user_text):
            reasons.append(f"organism {organism!r} is not in your own words, so it was not accepted")
        else:
            canonical, organism_note = normalise_organism(organism.strip())
            if canonical:
                request["organism"] = organism.strip()
                suggested.append(("organism", organism.strip()))

    ec = obj.get("subject_ec")
    if ec is not None:
        if not isinstance(ec, str) or not _EC.fullmatch(ec):
            reasons.append("subject_ec is not an EC number")
        elif ec not in ec_candidates:
            reasons.append(f"EC {ec} is not one the enzyme finder listed, so it was not accepted")
        else:
            request["subject"] = ec
            suggested.append(("subject", ec))

    if reasons:
        raise IntentRejected(reasons)

    description = description_for(shape, stages, variant)
    got = winning_rule(description)
    if got != shape.name:
        raise IntentRejected([f"the grammar would read that description as {got or 'nothing'}, not {shape.name}"])
    reading = None
    try:
        from caterva.compose.grammar import UnrecognisedShape, recognise

        try:
            recognition = recognise(description)
            reading = getattr(recognition, "reading", None)
        except UnrecognisedShape as exc:
            raise IntentRejected([f"the engine refused the description: {str(exc).splitlines()[0][:200]}"]) from None
    except ImportError:  # pragma: no cover - the grammar is part of the package
        pass
    request = {"description": description, **request}
    return DescribeIntent(shape=shape.name, description=description, request=request, suggested=suggested,
                          reading=reading, organism_note=organism_note, stages=stages, variant=variant)


__all__ = ["DescribeIntent", "IntentRejected", "Shape", "VARIANTS", "description_for", "max_stages",
           "shape_catalogue", "validate_describe", "winning_rule"]
