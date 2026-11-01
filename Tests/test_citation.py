"""
pytest suite for citation.py

Small module, but it's the thing every downstream consumer (UI, exports,
the product's eventual Citation display) will depend on, so it gets its
own coverage rather than being tested only incidentally through
test_fallback_logic.py.
"""


from brenda_client import BRENDAKmEntry
from citation import (
    Citation,
    brenda_literature_url,
    brenda_reference_url,
    citation_from_brenda_entry,
    pubmed_url,
)


def test_brenda_reference_url_builds_expected_link():
    # literature.php?refid=... was confirmed live (2026-07) to return an
    # identical broken generic template for every reference_id, not a
    # real per-reference page - see citation.py's docstring. The only
    # confirmed-real page is the parent enzyme page, which requires
    # ec_number.
    url = brenda_reference_url("740253", "1.1.1.27")
    assert url == "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"


def test_brenda_reference_url_handles_missing_id():
    assert brenda_reference_url(None, "1.1.1.27") is None
    assert brenda_reference_url("", "1.1.1.27") is None


def test_brenda_reference_url_returns_none_without_ec_number():
    """No confirmed-working link exists without an ec_number to build the
    enzyme-page fallback from - must return None rather than fabricate
    something else."""
    assert brenda_reference_url("740253", None) is None
    assert brenda_reference_url("740253") is None


def test_pubmed_url_builds_expected_link():
    assert pubmed_url("34962677") == "https://pubmed.ncbi.nlm.nih.gov/34962677/"


def test_pubmed_url_handles_missing_id():
    assert pubmed_url(None) is None
    assert pubmed_url("") is None


def _make_entry(**overrides) -> BRENDAKmEntry:
    from typing import Any
    base: dict[str, Any] = dict(
        km_value=0.6,
        unit="mM",
        substrate="lactate",
        organism="Homo sapiens",
        uniprot="P07864",
        conditions="pH 8.0, 25°C",
        reference_id="740253",
        ec_number="1.1.1.27",
        flagged=False,
        flag_reason=None,
    )
    base.update(overrides)
    return BRENDAKmEntry(**base)


def test_citation_from_brenda_entry_maps_fields_correctly():
    entry = _make_entry()
    citation = citation_from_brenda_entry(entry)

    assert isinstance(citation, Citation)
    assert citation.source == "BRENDA"
    assert citation.reference_id == "740253"
    assert citation.organism == "Homo sapiens"
    assert citation.url == "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"


def test_citation_from_flagged_entry_carries_flag_reason_as_notes():
    entry = _make_entry(
        km_value=6500.0,
        flagged=True,
        flag_reason="Km value 6500.0 mM is outside plausible range",
    )
    citation = citation_from_brenda_entry(entry)
    assert citation.notes == "Km value 6500.0 mM is outside plausible range"


def test_citation_from_entry_with_no_reference_id_has_no_url():
    entry = _make_entry(reference_id=None)
    citation = citation_from_brenda_entry(entry)
    assert citation.reference_id is None
    assert citation.url is None


def test_citation_is_json_serializable():
    entry = _make_entry()
    citation = citation_from_brenda_entry(entry)
    # Downstream code (API responses, exports) needs this to just work.
    payload = citation.model_dump_json()
    assert "BRENDA" in payload


def test_brenda_literature_url_builds_the_per_reference_page():
    # literature.php?e=<EC>&r=<ref> is the per-reference form that returns
    # the reference (checked 2026-10-17; six pages of EC 2.7.1.1 are
    # recorded under Tests/fixtures/recorded/). The refid form tested
    # above is the one that does not.
    url = brenda_literature_url("2.7.1.1", "641068")
    assert url == "https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068"


def test_brenda_literature_url_needs_both_ids():
    # Half a locator is no locator: None rather than a page that is not
    # the reference.
    assert brenda_literature_url(None, "641068") is None
    assert brenda_literature_url("2.7.1.1", None) is None
    assert brenda_literature_url("", "") is None


def test_the_citation_link_is_still_the_enzyme_page():
    """The per-reference form exists, and the Citation's url does not move
    to it: that output is pinned across the TypeScript contract
    (citeVerify.ts, the runner contract test)."""
    citation = citation_from_brenda_entry(_make_entry())
    assert citation.url == brenda_reference_url("740253", "1.1.1.27")
    assert citation.url != brenda_literature_url("1.1.1.27", "740253")
