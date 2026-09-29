"""Minting identifiers.org URIs, and refusing to when none exists.

WHY THIS MODULE EXISTS
----------------------
Caterva writes each parameter's provenance into the generated Antimony as a
trailing comment (`model_provenance.py`, Sauro's suggestion). That works
right up until the model is translated to SBML, at which point **every
trace is destroyed** -- comments are not part of the SBML data model.
Measured, not assumed:

    annotate_antimony(...) -> antimony.getSBMLString(...)
      'BRENDA'        in SBML: False
      '649716'        in SBML: False
      'Homo sapiens'  in SBML: False

SBML is the format every other tool reads. Provenance that survives only
inside Caterva's own text file is provenance that does not leave Caterva.

The standard mechanism is MIRIAM annotation (Le Novère et al. 2005, *Nature
Biotechnology* 23:1509-1515): an RDF block on the element, with a BioModels
qualifier and one or more identifiers.org URIs. COPASI, Tellurium, libSBML
and JWS Online all read it.

THE PART THAT MATTERS
---------------------
A MIRIAM URI is a *promise that the accession resolves*. Minting one for an
accession that does not resolve is worse than adding no annotation: it
manufactures a machine-actionable citation pointing at nothing, and machine
-actionable is exactly the property that stops anyone checking it by hand.

That is Katz's objection in its most literal form -- a citation you cannot
act on is not a citation -- and this project's whole claim is that its
numbers are traceable.

So every namespace here carries the **pattern** from the identifiers.org
registry, and `mint()` refuses any accession the pattern rejects.

THE CASE THAT PROVES THE POINT
------------------------------
BRENDA has an identifiers.org namespace, `brenda`, MIR:00000071. It would
have been entirely natural to write:

    https://identifiers.org/brenda:649716        # WRONG

But the registry says that namespace's pattern is

    ^((\\d+\\.-\\.-\\.-)|(\\d+\\.\\d+\\.-\\.-)|(\\d+\\.\\d+\\.\\d+\\.-)|(\\d+\\.\\d+\\.\\d+\\.\\d+))$

with sample id `1.1.1.1`. It covers **EC numbers**, not BRENDA's internal
reference ids. `brenda:649716` matches nothing and resolves nowhere.

A BRENDA reference id therefore gets **no URI**. It travels as a plain-text
note in the RDF description instead, which is honest about being a pointer
a human must follow. `mint()` returning None is a feature.

WHAT IS NOT CHECKED HERE
------------------------
That the accession *exists* -- only that it is well-formed for its
namespace. `pubmed:99999999999` is well-formed and probably fictional. This
module cannot tell the difference offline, and says so rather than implying
a liveness check it does not perform. Confirming existence is
`verify_golden_against_live.py`'s kind of job, not a formatter's.

The patterns are a dated capture, not a live lookup:
`Tests/fixtures/identifiers/identifiers_org_namespaces.json`, captured
2026-08-15. A registry change would make this module wrong in the silent
direction, which is why the capture carries its date and why
`check_identifier_patterns_fresh.py` exists.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

#: Where the dated capture lives. Read at import; a missing or malformed
#: file is a hard error rather than a fallback to built-in defaults --
#: built-in defaults are how a stale pattern survives a deleted fixture.
_CHECKOUT_COPY = (
    Path(__file__).resolve().parent.parent.parent
    / "Tests"
    / "fixtures"
    / "identifiers"
    / "identifiers_org_namespaces.json"
)
#: An installed wheel and the app folder have no `Tests/`; the same capture
#: ships inside the package, kept identical by `test_packaged_data.py`
#: (ADR 0177).
_PACKAGED_COPY = Path(__file__).resolve().parent / "data" / "identifiers_org_namespaces.json"
_FIXTURE = _CHECKOUT_COPY if _CHECKOUT_COPY.is_file() else _PACKAGED_COPY

BASE = "https://identifiers.org"


@dataclass(frozen=True)
class Namespace:
    prefix: str
    name: str
    mir_id: str
    pattern: re.Pattern[str]
    sample_id: str


def _load_from(path: Path) -> tuple[dict[str, Namespace], str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Namespace] = {}
    for prefix, spec in raw["namespaces"].items():
        out[prefix] = Namespace(
            prefix=prefix,
            name=spec["name"],
            mir_id=spec["mirId"],
            pattern=re.compile(spec["pattern"]),
            sample_id=spec["sampleId"],
        )
    return out, raw["_captured_on"]


def _load() -> tuple[dict[str, Namespace], str]:
    return _load_from(_FIXTURE)


NAMESPACES, PATTERNS_CAPTURED_ON = _load()

#: Namespaces Caterva is willing to mint URIs in. `brenda` is deliberately
#: ABSENT even though it loads above: the only BRENDA accession Caterva
#: holds is a reference id, which that namespace does not cover. Listing it
#: here would let a future caller pass an EC number and a reference id to
#: the same function and get a URI for both.
MINTABLE = ("pubmed", "doi", "taxonomy", "ec-code", "eco")

#: Namespaces whose accessions already carry the prefix, e.g. `ECO:0000269`.
#:
#: identifiers.org resolves those with a SLASH, not a colon. Measured, not
#: assumed:
#:
#:     https://identifiers.org/eco:ECO:0000269   -> 404
#:     https://identifiers.org/eco/ECO:0000269   -> 200
#:
#: The colon form is correct for every namespace Terrium already mints --
#: pubmed, taxonomy, doi and ec-code all resolve, checked at the same time --
#: so this is an exception, not a correction. ECO is the exception because
#: `eco:ECO:0000269` is a double prefix and the resolver rejects it.
#:
#: Worth stating plainly: adding `eco` to MINTABLE without this would have
#: emitted a link that 404s, into an SBML annotation whose whole purpose is
#: to be followable. `mint()`'s own refusal message already names that
#: outcome -- "minting it anyway would produce a link that does not
#: resolve" -- about a case it could not yet detect.
_PREFIX_EMBEDDED_IN_ACCESSION = frozenset({"eco"})


@dataclass(frozen=True)
class MintResult:
    """Three outcomes, never two.

    `uri` set               -> a resolvable identifiers.org URI.
    `uri` None, reason set  -> Caterva refuses; the reason names why.

    The caller must not treat a refusal as "no provenance". The accession is
    still real; it simply has no URI form, and belongs in the human-readable
    part of the annotation.
    """

    uri: str | None
    reason: str | None = None

    @property
    def minted(self) -> bool:
        return self.uri is not None


def mint(prefix: str, accession: str) -> MintResult:
    """A resolvable identifiers.org URI, or a stated refusal."""
    accession = (accession or "").strip()

    if prefix not in MINTABLE:
        known = prefix in NAMESPACES
        if known and prefix == "brenda":
            return MintResult(
                None,
                "BRENDA's identifiers.org namespace covers EC numbers, not "
                "reference ids. A BRENDA reference id has no URI form, so "
                "it travels as text rather than as a link that would not "
                "resolve.",
            )
        return MintResult(
            None,
            f"'{prefix}' is not a namespace Caterva mints URIs in"
            + (" (it is known but not mintable)." if known else " (unknown to the registry capture)."),
        )

    if not accession:
        return MintResult(None, f"No {prefix} accession was supplied.")

    namespace = NAMESPACES[prefix]
    if not namespace.pattern.fullmatch(accession):
        return MintResult(
            None,
            f"'{accession}' does not match the {namespace.name} accession "
            f"pattern from the identifiers.org registry (e.g. "
            f"'{namespace.sample_id}'). Minting it anyway would produce a "
            f"link that does not resolve.",
        )

    if prefix in _PREFIX_EMBEDDED_IN_ACCESSION:
        return MintResult(f"{BASE}/{prefix}/{accession}")
    return MintResult(f"{BASE}/{prefix}:{accession}")


#: `PMID 12345678`, `pmid:12345678`, `PubMed 12345678`, `PubMed ref 12345678`.
#:
#: The gap allowance was 4 and the CLI formats `"PubMed ref 12345678"` --
#: five characters -- so a real run produced zero annotations while every
#: unit test passed, because the tests used the shorter spelling. Widened to
#: 10, which covers `ref`, `ref.`, `id`, `:` and a bracket, and still cannot
#: leap a word boundary into an unrelated number.
#:
#: The regex is now the FALLBACK. Callers that already hold the registry and
#: accession pass them structurally; parsing a string Caterva formatted is a
#: guess about your own output format.
_PMID_RE = re.compile(r"\bpub\s*med\b\D{0,10}?(\d+)|\bpmid\b\D{0,10}?(\d+)", re.I)
#: A DOI anywhere in free text. Stops at whitespace; trailing sentence
#: punctuation is trimmed, because `10.1038/nbt1156.` is a real DOI
#: followed by a full stop and `10.1038/nbt1156.` is not a real DOI.
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;]+)", re.I)


def identifiers_in(citation: str) -> list[tuple[str, str]]:
    """(prefix, accession) pairs found in a free-text citation string.

    Caterva's citations arrive as human strings -- `"BRENDA ref 649716"`,
    `"PMID 12345678"` -- because that is what the resolvers produce. This
    pulls out only the parts that can become URIs, and finds nothing in a
    BRENDA reference, correctly.
    """
    if not citation:
        return []

    found: list[tuple[str, str]] = []

    for match in _PMID_RE.finditer(citation):
        accession = match.group(1) or match.group(2)
        if accession:
            found.append(("pubmed", accession))

    for match in _DOI_RE.finditer(citation):
        doi = match.group(1).rstrip(".,;)")
        found.append(("doi", doi))

    # Deduplicate, preserving order. A citation naming the same PMID twice
    # must not produce the annotation twice; duplicate CVTerms are legal
    # SBML and make a reader wonder which one is authoritative.
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for pair in found:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique