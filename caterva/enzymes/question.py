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
  * the SUBSTRATE is what is left, which must be non-empty, and must not
    itself hold an enzyme name or a word that joins two steps ("then",
    "and"): "hexokinase glucose phosphoglucose isomerase human" is a
    cascade, and reading "glucose phosphoglucose isomerase" as one
    substrate would have been a wrong reading shown for confirmation.

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

#: Words that join two steps or two substrates. A substrate holding one is
#: a cascade or a mixture, which is two systems, not one to confirm.
_STEP_WORDS = {"then", "and", "+", "->", "plus", "followed"}

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


def _holds_enzyme_name(words: Sequence[str], organism: Optional[str]) -> bool:
    """Any run of `words` the nomenclature reads as an enzyme name (see _is_enzyme_name)."""
    return any(_is_enzyme_name(words[i:j], organism)
               for i in range(len(words)) for j in range(i + 1, len(words) + 1))


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
            # A second step in the substrate part ("glucose then pyruvate
            # kinase", "glucose phosphoglucose isomerase") makes the whole
            # question two systems. Refused here rather than read as one
            # enzyme with a junk substrate, which is what it used to be read
            # as (found 2026-11-03).
            if any(w.lower() in _STEP_WORDS for w in substrate) or _holds_enzyme_name(substrate, typed):
                return None
            reading = {"enzyme": " ".join(enzyme), "substrate": " ".join(substrate),
                       **canonical_organism(typed)}
            readings[(reading["enzyme"], reading["substrate"], reading["organism"])] = reading
    # One reading or none. Two are two systems, and choosing between them
    # is the guess this module exists not to make.
    return next(iter(readings.values())) if len(readings) == 1 else None


def enzyme_identity(enzyme: str, organism: Optional[str]) -> Optional[Dict[str, str]]:
    """{"ec", "name"} when the nomenclature resolves `enzyme` to ONE enzyme, else None.

    The confirmation used to show only the words: "enzyme enzyme / substrate
    maltotriose", while the citation that followed was for EC 2.4.1.25,
    4-alpha-glucanotransferase. A person agreeing to a system has to see the
    enzyme the citation will be about, and this is the same decision the
    runner makes first (policy.resolve_enzyme_name asks finder.resolve and
    uses its EC unchanged when it resolves). None is "not decided offline":
    the runner may still find it through UniProt, or refuse, and says which.
    """
    from .finder import Resolved, resolve

    try:
        result = resolve(enzyme, organism)
    except Exception:  # an unreadable index is "not decided", never a guess
        return None
    if isinstance(result, Resolved) and result.candidate is not None:
        return {"ec": result.ec, "name": result.candidate.name}
    return None


def main() -> None:
    """stdin {"query"} -> {"system", "identity"}; {"organism"[, "enzyme"]} -> canonical_organism (+ "identity")."""
    payload = json.loads(sys.stdin.read() or "{}")
    if isinstance(payload.get("organism"), str):
        out: Dict[str, object] = dict(canonical_organism(payload["organism"]))
        if isinstance(payload.get("enzyme"), str):
            out["identity"] = enzyme_identity(payload["enzyme"], str(out["organism"]))
    else:
        system = read_system(str(payload.get("query") or ""))
        out = {"system": system,
               "identity": enzyme_identity(system["enzyme"], system["organism"]) if system else None}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    main()
