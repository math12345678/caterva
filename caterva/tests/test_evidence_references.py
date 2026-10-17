"""BRENDA's literature pages for six references of EC 2.7.1.1, read offline.

The pages are Tests/fixtures/recorded/brenda_reference_2.7.1.1_<ref>.html.gz,
fetched 2026-10-17 from literature.php?e=2.7.1.1&r=<ref> (CC BY 4.0), each
rowed in Tests/fixtures/recorded/README.md with the sha256 of its bytes. This
test holds the files to those rows and the parser to what the pages say.
"""
from __future__ import annotations

import gzip
import hashlib
import re
from pathlib import Path

import pytest

from caterva.checkout import literature_module
from caterva.evidence.claims import EvidenceRefused
from caterva.evidence.references import LITERATURE_URL, ReferencePage, parse_reference_page, reference_url

REPO = Path(__file__).resolve().parents[2]
RECORDED = REPO / "Tests" / "fixtures" / "recorded"
README = RECORDED / "README.md"

#: reference id -> (PMID, year, journal, first author)
EXPECTED = {
    "641068": ("7730377", "1995", "J. Biol. Chem.", "Xu, L.Z."),
    "739603": ("24723372", "2014", "Protein Sci.", "Martinez, J.A."),
    "640237": ("3341751", "1988", "Arch. Biochem. Biophys.", "Magnani, M."),
    "674942": ("17080299", "2007", "J. Biomed. Sci.", "Tsai, H.J."),
    "702867": ("19558793", "2009", "BMB Rep.", "Ahn, K.J."),
    "640261": ("8717435", "1996", "Mol. Cell. Biochem.", "Palma, F."),
}


def page(ref: str) -> bytes:
    return gzip.decompress((RECORDED / f"brenda_reference_2.7.1.1_{ref}.html.gz").read_bytes())


def readme_rows() -> dict[str, tuple[str, str, str]]:
    """file -> (url, date, sha256) from the README's table."""
    rows = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\| (brenda_\S+\.html\.gz) \| (\S+) \| (\d{4}-\d{2}-\d{2}) \| ([0-9a-f]{64}) \|", line)
        if match:
            rows[match.group(1)] = (match.group(2), match.group(3), match.group(4))
    return rows


class TestTheFixtures:
    def test_the_six_pages_are_rowed_in_the_readme_with_their_hash_and_date(self):
        rows = readme_rows()
        assert len(rows) >= 7, rows
        for ref in EXPECTED:
            name = f"brenda_reference_2.7.1.1_{ref}.html.gz"
            assert name in rows, f"{name} has no README row"
            url, date, sha = rows[name]
            assert url == reference_url("2.7.1.1", ref)
            assert date == "2026-10-17"
            assert hashlib.sha256(page(ref)).hexdigest() == sha

    def test_every_page_is_strict_utf8_and_names_its_reference(self):
        for ref in EXPECTED:
            html = page(ref).decode("utf-8")
            assert f"Reference to 2.7.1.1; Id = {ref}" in html


class TestParseReferencePage:
    def test_641068_is_the_glucokinase_paper(self):
        found = parse_reference_page(page("641068").decode("utf-8"))
        assert isinstance(found, ReferencePage)
        assert found.title == "Human beta-cell glucokinase. Dual role of Ser-151 in catalysis and hexose affinity"
        assert found.pmid == "7730377"
        assert found.authors == "Xu, L.Z.; Harrison, R.W.; Weber, I.T.; Pilkis, S.J."
        assert found.journal == "J. Biol. Chem."
        assert found.year == "1995"
        assert found.ec == "2.7.1.1"
        assert found.reference == "641068"

    def test_739603_is_the_connecting_loop_paper(self):
        found = parse_reference_page(page("739603").decode("utf-8"))
        assert found.title == "Role of connecting loop I in catalysis and allosteric regulation of human glucokinase"
        assert found.pmid == "24723372"

    @pytest.mark.parametrize("ref", sorted(EXPECTED))
    def test_each_page_gives_its_pmid_year_journal_and_first_author(self, ref):
        pmid, year, journal, first_author = EXPECTED[ref]
        found = parse_reference_page(page(ref).decode("utf-8"))
        assert found.pmid == pmid
        assert found.year == year
        assert found.journal == journal
        assert found.authors.startswith(first_author)
        assert found.title
        assert found.reference == ref

    def test_the_isozyme_titles_the_labelled_set_was_read_from(self):
        """The hand-labelled set (plan M3) names isozymes from these titles."""
        assert "hexokinase type I" in parse_reference_page(page("640237").decode("utf-8")).title
        assert "human brain hexokinase" in parse_reference_page(page("674942").decode("utf-8")).title
        assert "hexokinase II" in parse_reference_page(page("702867").decode("utf-8")).title
        assert "hexokinase type III" in parse_reference_page(page("640261").decode("utf-8")).title

    def test_a_page_without_a_reference_block_is_refused(self):
        html = page("641068").decode("utf-8")
        template = html.replace('class="reference__title"', 'class="gone"')
        with pytest.raises(EvidenceRefused, match="no reference block"):
            parse_reference_page(template)
        with pytest.raises(EvidenceRefused, match="no reference block"):
            parse_reference_page("<html><body>Reference for EC = </body></html>")

    def test_entities_and_tags_are_unescaped_in_what_is_read(self):
        html = ('<title>Reference to 1.1.1.1; Id = 7</title><div class="reference__authors">A &amp; B</div>'
                '<div><span class="reference__title">K<sub>m</sub> of &quot;x&quot;</span> (2001), <em>J.</em>, 1.</div>')
        found = parse_reference_page(html)
        assert found.authors == "A & B"
        assert found.title == 'Km of "x"'
        assert found.pmid is None
        assert found.year == "2001"


class TestUrls:
    def test_reference_url_is_the_e_and_r_form(self):
        assert reference_url("2.7.1.1", "641068") == "https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068"
        assert LITERATURE_URL == "https://www.brenda-enzymes.org/literature.php"
        with pytest.raises(EvidenceRefused):
            reference_url("", "641068")

    def test_citation_py_offers_the_same_form_and_keeps_the_pinned_citation_link(self):
        citation = literature_module("citation")
        assert citation.brenda_literature_url("2.7.1.1", "641068") == reference_url("2.7.1.1", "641068")
        assert citation.brenda_literature_url(None, "641068") is None
        assert citation.brenda_literature_url("2.7.1.1", None) is None
        assert citation.brenda_reference_url("641068", "2.7.1.1") == "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1"
        doc = citation.brenda_reference_url.__doc__
        assert "refid=" in doc and "e=<EC>&r=<reference_id>" in doc, "the docstring names which form is broken and which works"
