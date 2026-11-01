"""Vmax is the one required input a student cannot produce. Derive it.

WHY THIS FILE EXISTS
--------------------
`report` required `--vmax`. Vmax is a property of the student's *tube* — how
much enzyme they put in — and no database reports it. BRENDA does report
kcat, and `Vmax = kcat x [E]0` has been the documented bridge since ADR 0012
and ADR 0013, wired into `simulate --resolve` since ADR 0019.

So the one command built for teaching labs was demanding a number it could
have computed, from a citation it could already fetch. Recorded as the
largest remaining barrier at the end of ADR 0141 and built here.

THE PART THAT IS NOT PLUMBING
-----------------------------
A bridged Vmax is neither `literature` nor `yours`, and calling it either is
a lie in a specific direction:

  * `literature` claims BRENDA reports a Vmax for this assay. It reports a
    kcat. The Vmax depends on a number the student chose.
  * `yours` throws away the citation for the kcat, which is the entire
    reason the value is defensible.

So it is a third origin — **derived** — carrying both halves, and these
tests are mostly about that. A reader must be able to check the cited part
against the paper and see that the other part was chosen.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

from fixture_lineages import fixture_lineage_provider  # noqa: E402
from test_fallback_logic import (  # noqa: E402
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
)

LDH = "1.1.1.27"


def load_script():
    for path in (str(REPO), str(REPO / "Tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "report_lab_vmax", REPO / "scripts" / "report_lab.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(monkeypatch):
    """The real script and the real resolver; only the network is replaced.

    The kcat fixture is BRENDA's Turnover Numbers table, so the kcat this
    derives from is one the real parser actually read.
    """
    module = load_script()
    real = module.resolve_kinetic_value

    def offline(ec, organism, substrate, **kwargs):
        kwargs.setdefault("uniprot_provider", fake_uniprot_provider)
        kwargs.setdefault("taxon_id_provider", fake_taxon_id_provider)
        kwargs.setdefault("lineage_provider", fixture_lineage_provider)
        kwargs.setdefault("search_literature", False)
        return real(ec, organism, substrate, **kwargs)

    # BRENDA serves km, ki and kcat as separate TABLES ON ONE PAGE. The
    # fixtures are split per table, so they are concatenated here to stand in
    # for the real page — otherwise a kcat lookup against the km fixture
    # correctly finds nothing, and the test measures the fixture rather than
    # the bridge.
    combined = (
        load_fixture("brenda_ldh_fixture.html")
        + "\n"
        + load_fixture("brenda_ldh_kcat_fixture.html")
    )
    fetches: list[str] = []

    def fetch(ec, timeout=15):
        fetches.append(str(ec))
        return combined

    monkeypatch.setattr(module, "fetch_brenda_html", fetch)
    monkeypatch.setattr(module, "resolve_kinetic_value", offline)
    module.fetches = fetches  # type: ignore[attr-defined]
    return module


def run(script, payload, monkeypatch) -> dict:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    code = script.main()
    monkeypatch.undo()
    return {"exit": code, **json.loads(captured.getvalue())}


def payload(**overrides) -> dict:
    merged = {
        "title": "Human LDH",
        "question": "How fast is lactate consumed?",
        "ec": LDH,
        # Mus musculus / pyruvate is the system this fixture pair reports
        # BOTH a km and a kcat for, which is what the bridge needs.
        "organism": "Mus musculus",
        "parameters": [
            {
                "name": "km",
                "substrate": "pyruvate",
                "quantity": "km",
                "allowCrossSpecies": True,
            }
        ],
        "supplied": [{"name": "s0", "value": 10.0, "unit": "mM"}],
    }
    merged.update(overrides)
    return merged


# ---------------------------------------------------------------------------
# The bridge itself, as a unit -- no network, no fixture
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, value, unit="1/s", citation=None, found=True):
        self.value, self.unit, self.citation, self.found = value, unit, citation, found


class FakeCitation:
    def __init__(self, source="BRENDA", reference_id="740253"):
        self.source, self.reference_id = source, reference_id


def test_the_bridge_multiplies_kcat_by_the_enzyme_concentration(script):
    value, warnings = script.bridge_vmax(
        FakeResult(100.0, citation=FakeCitation()), 0.001, 10.73
    )
    # 100 /s * 0.001 mM = 0.1 mM/s
    assert value.value == pytest.approx(0.1)
    assert value.unit == "mM/s"


def test_the_derived_value_carries_the_citation_for_the_cited_half(script):
    value, _ = script.bridge_vmax(
        FakeResult(100.0, citation=FakeCitation(reference_id="740253")), 0.001, 10.73
    )
    assert "740253" in value.from_cited
    assert "kcat" in value.from_cited


def test_the_derived_value_marks_the_chosen_half_as_chosen(script):
    """Without this the document implies BRENDA reported the [E]0."""
    value, _ = script.bridge_vmax(
        FakeResult(100.0, citation=FakeCitation()), 0.001, 10.73
    )
    assert "yours" in value.from_chosen
    assert "0.001" in value.from_chosen


def test_the_relation_is_stated_so_the_number_can_be_checked(script):
    value, _ = script.bridge_vmax(
        FakeResult(100.0, citation=FakeCitation()), 0.001, 10.73
    )
    assert "kcat" in value.relation and "[E]0" in value.relation


def test_a_missing_kcat_is_a_refusal_that_names_what_was_missing(script):
    value, reason = script.bridge_vmax(FakeResult(None, found=False), 0.001, 10.73)
    assert value is None
    assert "kcat" in reason


def test_a_rejected_bridge_returns_no_value_at_all(script):
    """A zero [E]0 gives Vmax = 0, a model that provably cannot turn over.

    Returning it anyway would put an unrunnable number in the table with a
    real citation beside it — worse than refusing, because it looks sourced.
    """
    value, reason = script.bridge_vmax(
        FakeResult(100.0, citation=FakeCitation()), 0.0, 10.73
    )
    assert value is None
    assert "vmax could not be derived" in reason


# ---------------------------------------------------------------------------
# Through the whole command
# ---------------------------------------------------------------------------


def test_enzyme_conc_alone_is_enough_to_run_the_model(script, monkeypatch):
    """The point of the whole change: no --vmax, and the model still runs."""
    out = run(script, payload(enzymeConc=0.001), monkeypatch)

    assert out["ok"] is True
    assert out["derived"] == ["vmax"], (
        "a vmax was not derived from the literature kcat and the given [E]0"
    )
    assert "## Result" in out["markdown"]


def test_the_document_calls_it_derived_and_not_literature(script, monkeypatch):
    out = run(script, payload(enzymeConc=0.001), monkeypatch)

    row = next(
        line for line in out["markdown"].splitlines()
        if line.startswith("| vmax |")
    )
    assert "**derived**" in row
    # The two lies this origin exists to prevent, asserted on the ROW rather
    # than the document: prose elsewhere explains what derived means and
    # would satisfy a document-wide `in` check for free (ADR 0133).
    assert "literature" not in row
    assert "**yours**" not in row


def test_the_row_shows_both_halves_so_a_reader_can_check_it(script, monkeypatch):
    out = run(script, payload(enzymeConc=0.001), monkeypatch)

    row = next(
        line for line in out["markdown"].splitlines()
        if line.startswith("| vmax |")
    )
    assert "kcat" in row          # the cited half
    assert "yours" in row          # the chosen half
    assert "BRENDA" in row or "no citation recorded" in row


def test_a_supplied_vmax_is_never_overruled_by_a_derived_one(
    script, monkeypatch
):
    """A flag the student typed is a decision, not a suggestion.

    Silently replacing it with a computed number they cannot see is the same
    defect as discarding their --vmax in a suggested command (ADR 0116).
    """
    out = run(
        script,
        payload(
            enzymeConc=0.001,
            supplied=[
                {"name": "s0", "value": 10.0, "unit": "mM"},
                {"name": "vmax", "value": 0.25, "unit": "mM/s"},
            ],
        ),
        monkeypatch,
    )

    assert out["derived"] == []
    assert "vmax" in out["supplied"]
    # And it says so, rather than ignoring the flag in silence.
    assert any("not used" in r for r in out["refusals"])


def test_without_enzyme_conc_the_old_refusal_still_stands(script, monkeypatch):
    """The guard against overcorrecting.

    Deriving a vmax whenever one is missing — with no [E]0 to derive it from
    — would mean inventing the enzyme concentration, which is the one thing
    this bridge must never do.
    """
    out = run(script, payload(), monkeypatch)

    assert out["derived"] == []
    assert any("vmax" in r and "simulation was not run" in r
               for r in out["refusals"])


def test_a_derived_vmax_still_counts_as_defensible(script, monkeypatch):
    """`is_defensible` knew two origins. A third must not read as unaccounted."""
    out = run(script, payload(enzymeConc=0.001), monkeypatch)
    assert out["defensible"] is True


def test_one_report_fetches_the_brenda_page_once(script, monkeypatch):
    """Lisa Jeske asked directly that tools be gentle with BRENDA's servers.

    km, ki and kcat are separate tables on ONE page, but
    `resolve_kinetic_value` fetches inside itself — so a two-parameter report
    already fetched the same page twice, and adding the kcat lookup for this
    bridge would have made it three. The page is fetched once per run and
    reused.

    Asserted as a COUNT rather than "a cache exists", because a cache that is
    built and not consulted passes every test that checks for its presence.
    """
    run(
        script,
        payload(
            enzymeConc=0.001,
            parameters=[
                {"name": "km", "substrate": "pyruvate", "quantity": "km",
                 "allowCrossSpecies": True},
                {"name": "ki", "substrate": "pyruvate", "quantity": "ki",
                 "allowCrossSpecies": True},
            ],
        ),
        monkeypatch,
    )

    # Two parameters plus the kcat bridge = three lookups, one page.
    assert len(script.fetches) == 1, (
        f"the same BRENDA page was fetched {len(script.fetches)} times in one "
        "report"
    )
