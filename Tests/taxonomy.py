"""
taxonomy.py

Organism relatedness, from NCBI Taxonomy lineages.

WHY THIS EXISTS
---------------
Lisa Jeske of the BRENDA curation team (Leibniz Institute DSMZ), asked how
a tool should choose between kinetic values measured in different
organisms, wrote:

    "Enzyme kinetics are species-specific: An enzyme from a thermophilic
     bacterium (which lives at high temperatures) has completely different
     km or kcat values than the same enzyme in a mammal. Transferring a
     value from one species to another is not recommended from a
     biochemical standpoint. [...] The software should at least check
     whether the organisms are closely related enough (e.g., two different
     mammals instead of a bacterium and a human)."

ADR 0024 made cross-species resolution opt-in. This module implements the
second half of her recommendation: even WITH the opt-in, a value should
not be transferred between organisms that are not plausibly comparable.

WHAT THIS IS NOT
----------------
Relatedness is not kinetic similarity. Two mammals can have genuinely
different Km values for the same enzyme and substrate, and this check
cannot tell you they do not. It removes the most indefensible transfers
-- a thermophile's enzyme standing in for a human's -- and nothing more.
A value that passes this check is still a cross-species value, still
flagged, and still not a measurement of the organism the user asked about.

Saying that plainly matters, because the risk of adding a check is that
its existence gets read as an endorsement of whatever survives it.

WHY A RANK THRESHOLD AND NOT A DISTANCE
---------------------------------------
Counting shared lineage nodes looks more precise and is not. NCBI's tree
is far denser in some clades than others -- the human lineage passes
through thirty nodes, the Thermus thermophilus lineage through eight -- so
"shares 20 nodes" means something different depending on where you are in
the tree. Node counts measure how well-studied a clade is at least as much
as they measure relatedness.

The named ranks are stable across clades because they are defined
independently of how finely anyone has subdivided a branch. So the
question this module asks is: *what is the deepest RANKED node the two
organisms share?* Human and pig share the class Mammalia. Human and
Plasmodium falciparum share only the domain Eukaryota. That distinction is
exactly the one Jeske drew.

THE THRESHOLD IS HERS, NOT OURS
-------------------------------
`MINIMUM_SHARED_RANK = "class"`.

Her example -- "two different mammals instead of a bacterium and a human"
-- names Mammalia, which is a class. The threshold is that sentence
translated into code, and it is the only defensible place to put it: any
stricter and two mammals fail, which she explicitly permits; any looser and
a human/Plasmodium transfer passes, which she explicitly forbids.

NETWORK, AND THE THIRD OUTCOME
------------------------------
`fetch_*` touches the network, `parse_*` is pure and is what the test
suite exercises against fixtures -- the same split as brenda_client.py and
enzyme_lookup.py.

A lineage lookup that FAILS is not the same as organisms that are too
distant, and neither is the same as organisms that are close enough. All
three are distinct return states. A failed lookup must never read as
permission: the whole point of the check is that it is load-bearing, and a
check that passes when it could not run is a check that cannot fail.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from pydantic import BaseModel

from http_retry import retry_get

NCBI_TAXONOMY_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

#: The standard Linnaean ranks, ordered from broadest to narrowest, plus
#: the intermediate ranks NCBI actually emits.
#:
#: This is a definition, not data. It encodes the conventional ordering of
#: taxonomic ranks -- the fact that a class contains orders and an order
#: contains families -- which is a naming convention, not a measurement.
#: Nothing here is a scientific claim that could be sourced to a paper,
#: and nothing here is a value used in a simulation. Contrast with
#: ADR 0012/0013: those forbid inventing a *measured quantity*. An
#: ordering of rank labels is neither measured nor invented.
#:
#: Ranks NCBI emits that are absent here (notably "no rank", "clade",
#: "cellular root") are deliberately absent: they carry no position in the
#: hierarchy, so a node bearing one cannot serve as evidence of relatedness
#: at any particular depth. They are still traversed, just never used as
#: the answer.
RANK_ORDER: dict[str, int] = {
    "domain": 0,
    "superkingdom": 0,  # NCBI's older name for the same level
    "kingdom": 1,
    "subkingdom": 2,
    "superphylum": 3,
    "phylum": 4,
    "subphylum": 5,
    "superclass": 6,
    "class": 7,
    "subclass": 8,
    "infraclass": 9,
    "superorder": 10,
    "order": 11,
    "suborder": 12,
    "infraorder": 13,
    "parvorder": 14,
    "superfamily": 15,
    "family": 16,
    "subfamily": 17,
    "tribe": 18,
    "subtribe": 19,
    "genus": 20,
    "subgenus": 21,
    "species group": 22,
    "species subgroup": 23,
    "species": 24,
    "subspecies": 25,
}

#: See "THE THRESHOLD IS HERS, NOT OURS" above. Changing this value changes
#: a scientific policy and belongs in an ADR, not in a commit message.
MINIMUM_SHARED_RANK = "class"
MINIMUM_SHARED_RANK_INDEX = RANK_ORDER[MINIMUM_SHARED_RANK]


class TaxonNode(BaseModel):
    taxon_id: str
    name: str
    rank: str

    @property
    def rank_index(self) -> int | None:
        """Position in the standard hierarchy, or None for unranked nodes."""
        return RANK_ORDER.get(self.rank.lower())


class Lineage(BaseModel):
    """An organism and its ancestry, root first.

    ``nodes`` excludes the organism itself; ``self_node`` is the organism.
    Keeping them separate stops a comparison of an organism with its own
    genus from reporting a shared rank of "species".
    """

    self_node: TaxonNode
    nodes: list[TaxonNode] = []

    @property
    def full_path(self) -> list[TaxonNode]:
        return [*self.nodes, self.self_node]


class Relatedness(BaseModel):
    """The verdict on one organism pair.

    ``status`` is one of:

      "close_enough"  -- shared ranked ancestor at or below MINIMUM_SHARED_RANK
      "too_distant"   -- both lineages known, nearest shared rank is too broad
      "unknown"       -- at least one lineage could not be resolved

    Three states rather than a boolean, because "we could not check" must
    not be representable as "it is fine". That collapse is how a check
    stops being able to fail.
    """

    status: str
    shared_rank: str | None = None
    shared_name: str | None = None
    query_organism: str | None = None
    candidate_organism: str | None = None
    reason: str = ""

    @property
    def permits_transfer(self) -> bool:
        return self.status == "close_enough"


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def fetch_taxon_lineage_xml(taxon_id: str, timeout: float = 15) -> str:
    """Raw NCBI eFetch XML for one taxon. Network only; no parsing."""
    from enzyme_lookup import _ncbi_params  # local import: avoids a cycle

    response = retry_get(
        NCBI_TAXONOMY_EFETCH_URL,
        params=_ncbi_params(db="taxonomy", id=taxon_id, retmode="xml"),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

def parse_taxon_lineage(xml_text: str) -> Lineage | None:
    """NCBI eFetch taxonomy XML in, Lineage out. None if the XML holds no
    taxon -- NCBI answers an unknown id with a well-formed empty TaxaSet
    rather than an error, so "parsed fine, found nothing" is a real case
    and must not raise.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    taxon = root.find("Taxon")
    if taxon is None:
        return None

    def _text(element: ET.Element, tag: str) -> str:
        found = element.find(tag)
        return (found.text or "").strip() if found is not None else ""

    taxon_id = _text(taxon, "TaxId")
    name = _text(taxon, "ScientificName")
    if not taxon_id or not name:
        return None

    nodes: list[TaxonNode] = []
    lineage_ex = taxon.find("LineageEx")
    if lineage_ex is not None:
        for entry in lineage_ex.findall("Taxon"):
            entry_id = _text(entry, "TaxId")
            entry_name = _text(entry, "ScientificName")
            if not entry_id or not entry_name:
                continue
            nodes.append(
                TaxonNode(
                    taxon_id=entry_id,
                    name=entry_name,
                    rank=_text(entry, "Rank") or "no rank",
                )
            )

    return Lineage(
        self_node=TaxonNode(
            taxon_id=taxon_id, name=name, rank=_text(taxon, "Rank") or "no rank"
        ),
        nodes=nodes,
    )


def deepest_shared_ranked_node(a: Lineage, b: Lineage) -> TaxonNode | None:
    """The narrowest ancestor both organisms share that carries a standard rank.

    Matching is on taxon ID, never on name. Scientific names are reused
    across kingdoms (Mus the mammal genus and Mus the subgenus both appear
    in the mouse lineage above, with different ids) and a name collision
    would silently manufacture relatedness between unrelated clades -- the
    worst possible failure for this function, because it errs toward
    permitting a transfer.
    """
    shared_ids = {node.taxon_id for node in a.nodes} & {node.taxon_id for node in b.nodes}
    if not shared_ids:
        return None

    ranked = [
        node
        for node in a.nodes
        if node.taxon_id in shared_ids and node.rank_index is not None
    ]
    if not ranked:
        return None
    return max(ranked, key=lambda node: node.rank_index or -1)


def assess_relatedness(
    query: Lineage | None,
    candidate: Lineage | None,
    query_name: str | None = None,
    candidate_name: str | None = None,
) -> Relatedness:
    """Decide whether a value measured in `candidate` may stand in for `query`.

    Passing None for either lineage yields "unknown", never a pass.
    """
    query_label = query.self_node.name if query else (query_name or "unknown organism")
    candidate_label = (
        candidate.self_node.name if candidate else (candidate_name or "unknown organism")
    )

    if query is None or candidate is None:
        missing = []
        if query is None:
            missing.append(query_label)
        if candidate is None:
            missing.append(candidate_label)
        return Relatedness(
            status="unknown",
            query_organism=query_label,
            candidate_organism=candidate_label,
            reason=(
                f"Could not resolve an NCBI Taxonomy lineage for "
                f"{' and '.join(missing)}, so relatedness could not be checked. "
                "The value is withheld: a check that could not run must not "
                "read as a check that passed."
            ),
        )

    if query.self_node.taxon_id == candidate.self_node.taxon_id:
        return Relatedness(
            status="close_enough",
            shared_rank=query.self_node.rank,
            shared_name=query.self_node.name,
            query_organism=query_label,
            candidate_organism=candidate_label,
            reason="Same organism; not a cross-species transfer at all.",
        )

    shared = deepest_shared_ranked_node(query, candidate)
    if shared is None:
        return Relatedness(
            status="too_distant",
            query_organism=query_label,
            candidate_organism=candidate_label,
            reason=(
                f"{candidate_label} and {query_label} share no ranked ancestor "
                "in NCBI Taxonomy at all. Kinetic parameters are not "
                "transferable across that distance."
            ),
        )

    index = shared.rank_index
    assert index is not None  # deepest_shared_ranked_node only returns ranked nodes

    if index >= MINIMUM_SHARED_RANK_INDEX:
        return Relatedness(
            status="close_enough",
            shared_rank=shared.rank,
            shared_name=shared.name,
            query_organism=query_label,
            candidate_organism=candidate_label,
            reason=(
                f"{candidate_label} and {query_label} share the {shared.rank} "
                f"{shared.name}. This is close enough to be worth offering, and "
                "is still not a measurement of "
                f"{query_label}."
            ),
        )

    return Relatedness(
        status="too_distant",
        shared_rank=shared.rank,
        shared_name=shared.name,
        query_organism=query_label,
        candidate_organism=candidate_label,
        reason=(
            f"{candidate_label} and {query_label} diverge above the "
            f"{MINIMUM_SHARED_RANK} level -- their nearest shared ranked "
            f"ancestor is the {shared.rank} {shared.name}. Enzyme kinetics are "
            "species-specific, and a transfer across that distance produces a "
            "number that describes neither organism."
        ),
    )
