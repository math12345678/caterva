"""Relatedness policy — ADR 0024, Lisa Jeske's third recommendation.

Every lineage here is captured NCBI Taxonomy data (see the header of each
fixture). The assertions are therefore about real organisms, and a change
in NCBI's tree would legitimately break them -- which is what you want from
a test of a biological policy.
"""
from __future__ import annotations

import pathlib

import pytest

import taxonomy as tx
from fixture_lineages import fixture_lineage_provider

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "taxonomy"


def lineage(slug: str) -> tx.Lineage:
    path = sorted(FIXTURES.glob(f"taxonomy_{slug}_*.xml"))
    assert path, f"no fixture for {slug}"
    parsed = tx.parse_taxon_lineage(path[0].read_text(encoding="utf-8"))
    assert parsed is not None
    return parsed


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parses_a_real_ncbi_lineage():
    human = lineage("homo_sapiens")
    assert human.self_node.taxon_id == "9606"
    assert human.self_node.name == "Homo sapiens"
    assert human.self_node.rank == "species"
    assert len(human.nodes) == 30
    assert human.nodes[0].name == "cellular organisms"
    assert human.nodes[-1].name == "Homo"
    assert human.nodes[-1].rank == "genus"


def test_the_organism_is_not_in_its_own_ancestry():
    """If self_node leaked into nodes, comparing an organism with itself
    would report a shared rank of 'species' via the ancestry path rather
    than via the identity check -- and, worse, comparing two members of one
    genus would report a shared species."""
    human = lineage("homo_sapiens")
    assert "9606" not in {node.taxon_id for node in human.nodes}


def test_unknown_taxon_parses_to_none_rather_than_raising():
    """NCBI answers an unknown id with a well-formed empty TaxaSet."""
    assert tx.parse_taxon_lineage("<TaxaSet/>") is None
    assert tx.parse_taxon_lineage("<TaxaSet></TaxaSet>") is None


def test_malformed_xml_parses_to_none_rather_than_raising():
    """A truncated response is a failed lookup, not a crash -- and not a
    pass. assess_relatedness turns the None into a refusal."""
    assert tx.parse_taxon_lineage("<TaxaSet><Taxon><TaxId>96") is None
    assert tx.parse_taxon_lineage("") is None
    assert tx.parse_taxon_lineage("not xml at all") is None


def test_taxon_without_a_name_is_rejected():
    """An id with no scientific name cannot be reported to a user, and a
    verdict naming an empty string is worse than no verdict."""
    assert tx.parse_taxon_lineage(
        "<TaxaSet><Taxon><TaxId>9606</TaxId></Taxon></TaxaSet>"
    ) is None


# ---------------------------------------------------------------------------
# The policy — Jeske's own example, in both directions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a,b,expected_rank,expected_name",
    [
        # "two different mammals" -- the case she says is acceptable
        ("homo_sapiens", "sus_scrofa", "class", "Mammalia"),
        ("mus_musculus", "sus_scrofa", "class", "Mammalia"),
        ("homo_sapiens", "mus_musculus", "superorder", "Euarchontoglires"),
        ("mus_musculus", "oryctolagus_cuniculus", "superorder", "Euarchontoglires"),
    ],
)
def test_mammals_are_close_enough(a, b, expected_rank, expected_name):
    verdict = tx.assess_relatedness(lineage(a), lineage(b))
    assert verdict.status == "close_enough"
    assert verdict.shared_rank == expected_rank
    assert verdict.shared_name == expected_name
    assert verdict.permits_transfer is True


@pytest.mark.parametrize(
    "a,b",
    [
        ("homo_sapiens", "plasmodium_falciparum"),
        ("mus_musculus", "plasmodium_falciparum"),
        ("mus_musculus", "cryptosporidium_parvum"),
        ("homo_sapiens", "thermus_thermophilus"),
        ("plasmodium_falciparum", "thermus_thermophilus"),
    ],
)
def test_non_mammals_are_too_distant(a, b):
    verdict = tx.assess_relatedness(lineage(a), lineage(b))
    assert verdict.status == "too_distant"
    assert verdict.permits_transfer is False


def test_the_bacterium_and_the_human_share_no_ranked_ancestor_at_all():
    """Jeske's exact counterexample. Human and Thermus thermophilus meet
    only at 'cellular organisms', whose NCBI rank is 'cellular root' --
    which carries no position in the hierarchy, so there is no shared
    ranked ancestor to report."""
    verdict = tx.assess_relatedness(
        lineage("homo_sapiens"), lineage("thermus_thermophilus")
    )
    assert verdict.status == "too_distant"
    assert verdict.shared_rank is None
    assert "share no ranked ancestor" in verdict.reason


def test_relatedness_is_symmetric():
    """A verdict that depends on argument order would give two users
    different answers about the same pair -- the bug already found once in
    result-comparator.ts's confidence comparison."""
    for a, b in [
        ("homo_sapiens", "sus_scrofa"),
        ("homo_sapiens", "plasmodium_falciparum"),
        ("mus_musculus", "thermus_thermophilus"),
    ]:
        forward = tx.assess_relatedness(lineage(a), lineage(b))
        backward = tx.assess_relatedness(lineage(b), lineage(a))
        assert forward.status == backward.status
        assert forward.shared_rank == backward.shared_rank
        assert forward.shared_name == backward.shared_name


def test_same_organism_is_not_a_transfer():
    verdict = tx.assess_relatedness(lineage("homo_sapiens"), lineage("homo_sapiens"))
    assert verdict.status == "close_enough"
    assert "not a cross-species transfer" in verdict.reason


# ---------------------------------------------------------------------------
# The third state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query,candidate",
    [(None, "homo_sapiens"), ("homo_sapiens", None), (None, None)],
)
def test_an_unresolvable_lineage_never_permits(query, candidate):
    """A check that cannot run must not read as a check that passed.

    This is the assertion the whole three-state design exists for. With a
    boolean, the natural implementation of "we could not look it up" is
    False-meaning-not-close, which is right by accident; the moment anyone
    writes `if not too_distant:` it inverts, and an NCBI outage silently
    re-enables unrestricted cross-species substitution."""
    verdict = tx.assess_relatedness(
        lineage(query) if query else None,
        lineage(candidate) if candidate else None,
        query_name="Mus musculus",
        candidate_name="Plasmodium falciparum",
    )
    assert verdict.status == "unknown"
    assert verdict.permits_transfer is False
    assert "could not be checked" in verdict.reason


def test_unknown_is_distinct_from_too_distant():
    """Three states, three meanings. Collapsing 'we do not know' into
    'too distant' would tell a user their organisms are unrelated when the
    truth is that NCBI was unreachable."""
    unknown = tx.assess_relatedness(None, lineage("homo_sapiens"))
    distant = tx.assess_relatedness(
        lineage("homo_sapiens"), lineage("thermus_thermophilus")
    )
    assert unknown.status != distant.status
    assert unknown.reason != distant.reason


# ---------------------------------------------------------------------------
# Matching on ids, not names
# ---------------------------------------------------------------------------

def test_shared_ancestry_is_matched_on_taxon_id_not_name():
    """The mouse lineage contains 'Mus' twice -- genus 10088 and subgenus
    862507. Scientific names are also reused across kingdoms outright.
    Name matching would manufacture relatedness, and it errs toward
    PERMITTING a transfer, which is the direction that hurts."""
    mouse = lineage("mus_musculus")
    mus_nodes = [n for n in mouse.nodes if n.name == "Mus"]
    assert len(mus_nodes) == 2
    assert mus_nodes[0].taxon_id != mus_nodes[1].taxon_id

    fake = tx.Lineage(
        self_node=tx.TaxonNode(taxon_id="999999", name="Fictus namesake", rank="species"),
        nodes=[
            # Same NAME as a real mouse ancestor, different id.
            tx.TaxonNode(taxon_id="888888", name="Mus", rank="genus"),
            tx.TaxonNode(taxon_id="777777", name="Mammalia", rank="class"),
        ],
    )
    verdict = tx.assess_relatedness(mouse, fake)
    assert verdict.status == "too_distant"
    assert verdict.shared_rank is None


def test_unranked_nodes_are_never_the_answer():
    """Human and pig share many unranked nodes below Mammalia (Theria,
    Eutheria, Boreoeutheria). Reporting one of those would give a verdict
    the threshold cannot be compared against."""
    verdict = tx.assess_relatedness(lineage("homo_sapiens"), lineage("sus_scrofa"))
    assert verdict.shared_rank in tx.RANK_ORDER
    assert verdict.shared_rank != "no rank"


def test_a_fish_is_too_distant_from_a_mammal():
    """Danio rerio pins the threshold from the other side.

    Human and zebrafish are both chordates -- they share the phylum
    Chordata and even the subphylum Craniata -- but they are in different
    CLASSES (Mammalia vs Actinopteri), so their deepest shared ranked
    ancestor is the subphylum, which sits above the threshold.

    Without this pair every non-mammal in the fixture set also fails at the
    domain level, so loosening MINIMUM_SHARED_RANK from "class" all the way
    to "phylum" changed no observed verdict and was caught only by the
    assertion that literally reads the constant. A threshold whose value
    nothing depends on is a threshold that will drift.
    """
    verdict = tx.assess_relatedness(lineage("homo_sapiens"), lineage("danio_rerio"))
    assert verdict.status == "too_distant"
    assert verdict.shared_rank == "subphylum"
    assert verdict.shared_name == "Craniata"


def test_threshold_is_the_class_rank_and_is_load_bearing():
    """If MINIMUM_SHARED_RANK drifted, the human/pig case is the one that
    would break first -- they share Mammalia and nothing ranked below it."""
    assert tx.MINIMUM_SHARED_RANK == "class"
    verdict = tx.assess_relatedness(lineage("homo_sapiens"), lineage("sus_scrofa"))
    assert verdict.shared_rank == "class"
    assert verdict.status == "close_enough", (
        "human/pig sits exactly on the threshold; if this fails the "
        "threshold moved and Jeske's own example no longer passes"
    )


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------

def test_fixture_provider_returns_none_for_an_unlisted_organism():
    assert fixture_lineage_provider("Gallus gallus") is None
    assert fixture_lineage_provider("") is None


def test_fixture_provider_resolves_every_organism_the_brenda_fixtures_use():
    """The BRENDA fixtures name these organisms; if a lineage is missing,
    the relatedness check silently degrades to 'unknown' for that organism
    and the tests above would be asserting the wrong mechanism."""
    for organism in [
        "Homo sapiens", "Sus scrofa", "Mus musculus",
        "Plasmodium falciparum", "Cryptosporidium parvum",
    ]:
        assert fixture_lineage_provider(organism) is not None, organism


# ---------------------------------------------------------------------------
# The format production actually consumes
#
# Every fixture above was assembled from the NCBI Taxonomy BROWSER. The
# runtime path calls E-utilities eFetch, whose rank vocabulary differs: the
# browser says "no rank" where eFetch says "clade".
#
# That difference had never been exercised. The parser was written against a
# reconstructed wrapper and tested against browser vocabulary while
# production consumed something else -- the exact shape of a bug that only
# appears off the test machine.
#
# It turns out the two behave identically, because neither "clade" nor
# "no rank" is in RANK_ORDER. That was luck rather than design. These tests
# convert it into design.
# ---------------------------------------------------------------------------

EFETCH_FIXTURE = FIXTURES / "efetch_homo_sapiens_9606.xml"


def test_the_real_efetch_response_parses():
    """Captured verbatim from the endpoint fetch_taxon_lineage_xml calls."""
    parsed = tx.parse_taxon_lineage(EFETCH_FIXTURE.read_text(encoding="utf-8"))
    assert parsed is not None
    assert parsed.self_node.taxon_id == "9606"
    assert parsed.self_node.name == "Homo sapiens"
    assert parsed.self_node.rank == "species"
    assert len(parsed.nodes) == 30


def test_efetch_says_clade_where_the_browser_says_no_rank():
    """Documents the vocabulary difference as a fact, not a footnote.

    If NCBI ever gives "clade" a position in the hierarchy, or if someone
    adds it to RANK_ORDER thinking it harmless, this is the test that says
    what that would change.
    """
    parsed = tx.parse_taxon_lineage(EFETCH_FIXTURE.read_text(encoding="utf-8"))
    assert parsed is not None

    clades = [node for node in parsed.nodes if node.rank == "clade"]
    assert len(clades) == 14, "the real response uses 'clade' extensively"
    assert "clade" not in tx.RANK_ORDER
    assert all(node.rank_index is None for node in clades)

    # And the browser vocabulary this repository's other fixtures use.
    browser = lineage("homo_sapiens")
    assert any(node.rank == "no rank" for node in browser.nodes)
    assert all(
        node.rank_index is None for node in browser.nodes if node.rank == "no rank"
    )


def test_both_vocabularies_give_the_same_verdict():
    """The property that made the untested difference harmless.

    Same organism, two rank vocabularies, one answer. If they ever diverge,
    relatedness would mean something different in production than in the
    tests -- which is the failure this file now prevents rather than
    survives.
    """
    efetch = tx.parse_taxon_lineage(EFETCH_FIXTURE.read_text(encoding="utf-8"))
    assert efetch is not None

    for other in ("sus_scrofa", "mus_musculus", "plasmodium_falciparum", "danio_rerio"):
        from_efetch = tx.assess_relatedness(efetch, lineage(other))
        from_browser = tx.assess_relatedness(lineage("homo_sapiens"), lineage(other))
        assert from_efetch.status == from_browser.status, other
        assert from_efetch.shared_rank == from_browser.shared_rank, other
        assert from_efetch.shared_name == from_browser.shared_name, other


def test_a_doctype_declaration_does_not_defeat_the_parser():
    """The live response carries one. ElementTree ignores it, but that is a
    property of the library rather than something this code arranged, and a
    library swap would make it a silent production-only failure."""
    with_doctype = (
        '<?xml version="1.0" ?>\n'
        '<!DOCTYPE TaxaSet PUBLIC "-//NLM//DTD Taxon, 14th January 2002//EN" '
        '"https://www.ncbi.nlm.nih.gov/entrez/query/DTD/taxon.dtd">\n'
        "<TaxaSet><Taxon><TaxId>9606</TaxId>"
        "<ScientificName>Homo sapiens</ScientificName><Rank>species</Rank>"
        "<LineageEx><Taxon><TaxId>40674</TaxId>"
        "<ScientificName>Mammalia</ScientificName><Rank>class</Rank></Taxon>"
        "</LineageEx></Taxon></TaxaSet>"
    )
    parsed = tx.parse_taxon_lineage(with_doctype)
    assert parsed is not None
    assert parsed.self_node.name == "Homo sapiens"
