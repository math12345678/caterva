"""The fifth adversarial round of the real-values work (2026-11-12), the
advice half that lives in the literature layer and the runner both front ends
read: what a refusal offers must lead to a run that succeeds.

Rows are BRENDA's own, copied from the live page into a page of BRENDA's
markup, so the tests run offline:

- potato acid phosphatase (EC 3.1.3.2): kcat rows of "Phenolphthalein
  diphosphate" and "Sodium diphosphate" were read as rows in organisms of
  those names, and the advice listed them as organisms to re-run in (N10);
- human COX-2 (EC 1.14.99.1): the only other organism's kcat row is the
  N580A mutant's, and the advice was --allow-cross-species, refused again
  (V7-04);
- the API offered "Celecoxib is an inhibitor of enzyme acetylcholinesterase"
  as a paper that may report COX-2's Ki (V7-08).
"""
from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace

from fallback_logic import resolve_kinetic_value
from test_literature_quality import page
from test_third_round_review import kw, row

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB_DIR = str(REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import science_agent_runner  # noqa: E402

ACP_KCAT = [row(109, "Phenolphthalein diphosphate", "Homo sapiens", "-", "134695"),
            row(2042, "Sodium diphosphate", "Blastobotrys adeninivorans",
                "recombinant enzyme, in 100 mM sodium acetate buffer (pH 4.5), at 60°C", "677611")]


def test_a_compound_named_like_a_binomial_is_not_an_organism_nor_the_substrate():
    """'diphosphate' is neither compound, and neither compound is an organism."""
    html = page({"Turnover Numbers": ACP_KCAT})
    r = resolve_kinetic_value("3.1.3.2", "Solanum tuberosum", "diphosphate", quantity="kcat",
                              **kw(html, "Solanum tuberosum"))
    assert not r.found
    assert r.source != "cross_species_withheld"
    assert "Phenolphthalein diphosphate" not in r.cross_species_organisms_available


def test_a_compound_named_like_a_binomial_keeps_its_rows_under_its_own_name():
    html = page({"Turnover Numbers": ACP_KCAT})
    r = resolve_kinetic_value("3.1.3.2", "Solanum tuberosum", "Sodium diphosphate", quantity="kcat",
                              **kw(html, "Solanum tuberosum"))
    assert r.source == "cross_species_withheld"
    assert r.cross_species_organisms_available == ["Blastobotrys adeninivorans"]


COX_KCAT = [row(22, "arachidonate", "Mus musculus", "mutant N580A, pH 8.0, 37°C", "675123")]
COX_KM = [row(0.005, "arachidonate", "Homo sapiens", "pH 8.0, 37°C", "675100")]


def test_an_organism_whose_rows_are_all_a_variants_is_said_to_be_one():
    html = page({"KM Values": COX_KM, "Turnover Numbers": COX_KCAT})
    r = resolve_kinetic_value("1.14.99.1", "Homo sapiens", "arachidonate", quantity="kcat",
                              **kw(html, "Homo sapiens"))
    assert r.source == "cross_species_withheld"
    assert r.cross_species_organisms_available == ["Mus musculus"]
    assert r.cross_species_variant_only == ["Mus musculus"]
    # With variants allowed, the organism's rows are usable and none is said to be a variant's.
    allowed = resolve_kinetic_value("1.14.99.1", "Homo sapiens", "arachidonate", quantity="kcat",
                                    allow_variants=True, **kw(html, "Homo sapiens"))
    assert allowed.cross_species_variant_only == []


def test_a_wild_type_row_elsewhere_is_not_said_to_be_a_variants():
    html = page({"Turnover Numbers": COX_KCAT + [
        row(30, "arachidonate", "Ovis aries", "wild-type, pH 8.0, 37°C", "675124")]})
    r = resolve_kinetic_value("1.14.99.1", "Homo sapiens", "arachidonate", quantity="kcat",
                              **kw(html, "Homo sapiens"))
    assert r.cross_species_organisms_available == ["Mus musculus", "Ovis aries"]
    assert r.cross_species_variant_only == ["Mus musculus"]


def _paper(title):
    return SimpleNamespace(title=title, pmid="1", url=None, source="pubmed", doi=None)


def test_papers_offered_for_a_missing_constant_name_the_enzyme():
    papers = [_paper("Potent Phenylpyridine Inhibitors of Cyclooxygenase-2: Optimization toward a Long "
                     "Residence Time"),
              _paper("Celecoxib is an inhibitor of enzyme acetylcholinesterase."),
              _paper("The effects of COX-2 inhibitor during osteogenic differentiation."),
              _paper("Aldosterone glucuronidation inhibition as a potential mechanism.")]
    kept = science_agent_runner._naming_the_enzyme(papers, "COX-2", "1.14.99.1", "PTGS2", "Homo sapiens")
    titles = [p.title for p in kept]
    assert len(titles) == 2
    assert not any("acetylcholinesterase" in t or "Aldosterone" in t for t in titles)


def test_the_organism_scoped_list_is_composes_and_only_for_a_name_miss(monkeypatch):
    calls = []

    def holds(ec, table, compound, organism, role, isoform=None):
        calls.append((ec, table, compound, organism, role, isoform))
        return (" -- BRENDA has no Ki row for celecoxib under EC 1.14.99.1 in Homo sapiens; the "
                "inhibitors it lists Ki rows for there: nimesulide (1 row)")

    import caterva.compose.__main__ as compose_main

    monkeypatch.setattr(compose_main, "_what_the_organism_holds", holds)
    missed = SimpleNamespace(source="not_found", substrates_available=["indomethacin", "nimesulide"])
    said = science_agent_runner._available_in_the_organism(
        missed, "1.14.99.1", "ki", "celecoxib", "Homo sapiens", "PTGS2")
    assert said.startswith("BRENDA has no Ki row for celecoxib") and "nimesulide (1 row)" in said
    assert calls == [("1.14.99.1", "ki", "celecoxib", "Homo sapiens", "inhibitor", "PTGS2")]
    withheld = SimpleNamespace(source="cross_species_withheld", substrates_available=["x"])
    assert science_agent_runner._available_in_the_organism(
        withheld, "1.14.99.1", "ki", "celecoxib", "Homo sapiens", None) is None
    assert science_agent_runner._available_in_the_organism(
        missed, "1.14.99.1", "ki", "celecoxib", "", None) is None
