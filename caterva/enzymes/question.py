"""Read enzyme, substrate and organism out of a short question, or refuse.

WHY THIS EXISTS
---------------
`scientific simulate "<question>" --resolve` reads the system out of the
question and asks the reader to confirm it before anything is cited
(src/cli/suggestResolveCommand.ts, src/cli/confirmSystem.ts). That parser is
anchored on prepositions -- "X on Y in Z", "of X with Y in Z" -- and a
student who typed "hexokinase glucose human" or "human hexokinase on
glucose" was told the question named no system, then shown a template with
three blanks to fill in with the three words they had just typed.

Without prepositions the boundaries have to come from somewhere, and a
guessed boundary is a guessed enzyme. So this reads only what the shared
tables already hold exactly:

  * the ORGANISM is a name `organism_code` reads (the one normaliser every
    Caterva command uses), at the start or the end of the question;
  * the ENZYME is the leading words that the nomenclature finder matches by
    name -- accepted or alternative name, exact or with stereo labels set
    aside (tiers 1-4 of finder.py), never a phrase inside a longer name or
    a typo;
  * the SUBSTRATE is what is left, which must be non-empty.

When more than one split satisfies that, or none does, the answer is None.
Nothing here resolves or cites anything: the CLI still prints what it read
and waits for a person to say yes.

The organism comes back as the binomial BRENDA indexes ("humans" ->
"Homo sapiens", see index.organism_binomial), with what was typed beside it
so the confirmation can show both.
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional, Sequence

from .finder import TIER_ALTERNATIVE_TOLERANT, find
from .index import organism_binomial, organism_code

#: Leading words that are never part of the system: the command's own
#: vocabulary, as NOISE in suggestResolveCommand.ts.
_PREAMBLE = {"simulate", "simulation", "run", "the", "a", "an", "model", "kinetics",
             "michaelis", "menten", "mm", "please", "of", "for"}

#: Words that join the parts. "in" only ever introduces the organism.
_JOINERS = ("on", "with")

#: The longest organism name in index.ORGANISMS is four words
#: ("escherichia coli k 12" normalises to five tokens, but is typed as four).
_MAX_ORGANISM_WORDS = 5


def canonical_organism(typed: str) -> Dict[str, str]:
    """{"organism": binomial-or-typed, "typed": typed}."""
    binomial = organism_binomial(typed)
    return {"organism": binomial or typed, "typed": typed}


def _is_enzyme_name(words: Sequence[str], organism: Optional[str]) -> bool:
    text = " ".join(words)
    return any(c.tier <= TIER_ALTERNATIVE_TOLERANT for c in find(text, organism, None))


def _split_organism(words: List[str]) -> List[tuple]:
    """Every ("start"|"end", organism words, rest) with an organism name there."""
    found = []
    for n in range(1, min(_MAX_ORGANISM_WORDS, len(words) - 1) + 1):
        tail, head = words[-n:], words[:-n]
        if organism_code(" ".join(tail)):
            if head and head[-1].lower() == "in":
                head = head[:-1]
            found.append(("end", tail, head))
        lead, rest = words[:n], words[n:]
        if organism_code(" ".join(lead)):
            found.append(("start", lead, rest))
    return found


def read_system(query: str) -> Optional[Dict[str, str]]:
    """{"enzyme", "substrate", "organism", "typed"} or None. See module doc."""
    words = query.strip().rstrip(".?!").split()
    while words and words[0].lower() in _PREAMBLE:
        words = words[1:]
    readings: Dict[tuple, Dict[str, str]] = {}
    placed = _split_organism(words)
    # An organism at each end ("human hexokinase glucose mouse") is two
    # questions; reading the other one as part of the substrate would hide it.
    if len({where for where, _, _ in placed}) > 1:
        return None
    for _, organism_words, rest in placed:
        typed = " ".join(organism_words)
        joins = [i for i, w in enumerate(rest) if w.lower() in _JOINERS]
        if len(joins) > 1:
            continue
        if joins:
            i = joins[0]
            splits = [(rest[:i], rest[i + 1:])]
        else:
            splits = [(rest[:k], rest[k:]) for k in range(1, len(rest))]
        for enzyme, substrate in splits:
            if not enzyme or not substrate or "in" in (w.lower() for w in enzyme + substrate):
                continue
            if not _is_enzyme_name(enzyme, typed):
                continue
            reading = {"enzyme": " ".join(enzyme), "substrate": " ".join(substrate),
                       **canonical_organism(typed)}
            readings[(reading["enzyme"], reading["substrate"], reading["organism"])] = reading
    # One reading or none. Two are two systems, and choosing between them
    # is the guess this module exists not to make.
    return next(iter(readings.values())) if len(readings) == 1 else None


def main() -> None:
    """stdin {"query"} -> {"system": ...|null}; {"organism"} -> canonical_organism."""
    payload = json.loads(sys.stdin.read() or "{}")
    if isinstance(payload.get("organism"), str):
        out: object = canonical_organism(payload["organism"])
    else:
        out = {"system": read_system(str(payload.get("query") or ""))}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()
