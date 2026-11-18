"""An `--ec` option read by the one enzyme-name policy.

WHY THIS EXISTS
---------------
`caterva bind --ec hexokinase --organism human --list` sent the word
"hexokinase" to BRENDA as though it were an EC number, got back a page with
no Ki rows for it, and printed "No Ki rows for EC hexokinase in Homo
sapiens." -- a statement about the literature that was really a statement
about the flag. The same input with `--ec 2.7.1.1` lists seven compounds.
`caterva rates --ec` and `caterva fep --ec` passed the text on the same way.
`compose --subject` and `structure --subject` had long read a name through
`caterva.enzymes.policy`; the `--ec` commands had never been routed there.
Found 2026-11-02 by typing an enzyme's name where its number goes.

WHAT IT DOES
------------
Hands the text to `resolve_enzyme_name`, the function every command that
reads an enzyme name uses. An EC number comes back as itself (a transferred
one as its successor, said so; one this nomenclature release does not list
is used as given, because BRENDA may know it). A name that is exactly one
enzyme comes back as that enzyme's number with a "Read 'hexokinase' as EC
2.7.1.1" sentence the command prints, so the reader sees what was searched.
A name that is several enzymes, none, an EC class ("2.7.1") or a deleted
number is a refusal naming the candidates and the `--ec` line that would
accept each: nothing is fetched, because a search for the wrong thing that
finds nothing reads as a fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from caterva.enzymes.policy import NameNotResolved, literature_uniprot_lookup, resolve_enzyme_name

_DEFAULT = object()


@dataclass(frozen=True)
class EcOption:
    """What `--ec TEXT` came to.

    `ec` is the number to search, None when refused; `notes` are the
    sentences to print before the result (empty when the text was an EC
    number used unchanged); `refusal` the sentence to print instead of a
    result; `why` the policy's `NameNotResolved`, so a caller that renders
    candidates (the studio) has them as data."""

    ec: Optional[str]
    notes: List[str] = field(default_factory=list)
    refusal: Optional[str] = None
    why: Optional[NameNotResolved] = None

    @property
    def note(self) -> Optional[str]:
        return " ".join(self.notes) or None


def read_ec_option(
    text: Optional[str],
    organism: Optional[str] = None,
    *,
    flag: str = "--ec",
    uniprot: Optional[Callable[[str], Sequence[str]]] = _DEFAULT,  # type: ignore[assignment]
) -> EcOption:
    """`--ec TEXT` as an EC number, or a refusal naming the candidates.

    `organism` ranks the candidates and names their proteins (anything
    `caterva.enzymes.index.organism_code` reads); it is never assumed.
    `uniprot` is the policy's step-4 lookup for a protein name the
    nomenclature does not hold; by default the literature layer's, when the
    checkout has it."""
    typed = " ".join(str(text or "").split())
    if not typed:
        return EcOption(None, refusal=f"{flag} is empty: give an EC number such as 2.7.1.1, or an enzyme name")
    lookup = literature_uniprot_lookup() if uniprot is _DEFAULT else uniprot
    try:
        resolution = resolve_enzyme_name(
            typed, organism, uniprot=lookup, rerun=flag + " {ec}", allow_unlisted_ec=True)
    except NameNotResolved as exc:
        return EcOption(None, refusal=f"Nothing was searched: {exc}", why=exc)
    return EcOption(resolution.ec, notes=resolution.notes(typed))


__all__ = ["EcOption", "read_ec_option"]
