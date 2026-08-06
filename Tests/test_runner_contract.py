"""
Stage 5 Part 4: the runner-boundary contract, Python side.

Runs the real science_agent_runner.main() in-process with a golden
KineticResult substituted for the lookup, and pins the exact JSON the
runner emits. Together with the TS-side contract test
(api-server/src/lib/scienceAgent.test.ts) the boundary is pinned from
both directions: a field renamed or dropped on either side fails
immediately, so the value and its citation cannot silently drift apart.
"""

import io
import json
import os
import sys

import pytest

LIB_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "Science-Agent-Pipeline",
    "artifacts",
    "api-server",
    "src",
    "lib",
)
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import fallback_logic  # noqa: E402
import science_agent_runner  # noqa: E402
from citation import Citation  # noqa: E402
from fallback_logic import KineticResult  # noqa: E402


def golden_result(cross_species: bool = False) -> KineticResult:
    """The golden G1 record, as the Python layer hands it to the runner."""
    return KineticResult(
        found=True,
        value=10.73,
        unit="mM",
        organism="Sus scrofa" if cross_species else "Homo sapiens",
        source="brenda_cross_species" if cross_species else "brenda_exact",
        citation=Citation(
            source="BRENDA",
            reference_id="740001" if cross_species else "740253",
            url="https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            organism="Sus scrofa" if cross_species else "Homo sapiens",
            notes=None,
        ),
        cross_species_flag=cross_species,
        search_log=["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    )


def run_main(monkeypatch, fake_resolve, payload):
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", fake_resolve)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    return json.loads(stdout.getvalue())


def test_golden_found_output_shape(monkeypatch):
    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(),
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": True,
        "km": 10.73,
        "unit": "mM",
        "organism": "Homo sapiens",
        "source": "brenda_exact",
        "crossSpecies": False,
        "citation": {
            "source": "BRENDA",
            "referenceId": "740253",
            "url": "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            "title": None,
            "organism": "Homo sapiens",
            "notes": None,
        },
        # STRENDA assay conditions (ADR 0010). This golden KineticResult
        # carries none, so every field crosses as null -- absence is
        # transmitted as absence. The TypeScript side reads that as
        # "incomplete" and degrades the citation to flagged, which is the
        # honest outcome for a value whose conditions were never reported.
        "assayConditions": {
            "ph": None,
            "temperatureC": None,
            "buffer": None,
            "unreported": [],
        },
        "literatureCandidates": [],
        "logs": ["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    }


def test_assay_conditions_cross_the_boundary(monkeypatch):
    """A populated set of conditions must survive the JSON boundary.

    The null-valued golden case above cannot distinguish "transmitted
    correctly" from "dropped and defaulted to null", so it is paired with
    a populated case that can.
    """
    populated = golden_result()
    populated.assay_ph = 8.5
    populated.assay_temperature_c = 25.0
    populated.assay_buffer = "phosphate buffer"
    populated.assay_unreported = []

    result = run_main(
        monkeypatch,
        lambda *a, **k: populated,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result["assayConditions"] == {
        "ph": 8.5,
        "temperatureC": 25.0,
        "buffer": "phosphate buffer",
        "unreported": [],
    }


def test_explicitly_unreported_field_crosses_the_boundary(monkeypatch):
    """BRENDA stating "temperature not specified in the publication" is a
    fact about the literature, not a parse failure, and must reach the
    API distinguishable from a silent absence."""
    partial = golden_result()
    partial.assay_ph = 8.0
    partial.assay_temperature_c = None
    partial.assay_unreported = ["temperature"]

    result = run_main(
        monkeypatch,
        lambda *a, **k: partial,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result["assayConditions"]["ph"] == 8.0
    assert result["assayConditions"]["temperatureC"] is None
    assert result["assayConditions"]["unreported"] == ["temperature"]


def test_cross_species_flag_crosses_the_boundary(monkeypatch):
    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(cross_species=True),
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Mus musculus", "ecNumber": "1.1.1.27"},
    )
    assert result["crossSpecies"] is True
    assert result["source"] == "brenda_cross_species"
    assert result["citation"]["referenceId"] == "740001"
    assert result["organism"] == "Sus scrofa"


def test_ki_quantity_emits_ki_key(monkeypatch):
    """quantity="ki" must flow to the resolver and the value must be
    emitted under the "ki" key (never "km"), so the TypeScript side can
    never mistake a resolved Ki for a Km."""
    captured = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured["quantity"] = kwargs.get("quantity")
        result = golden_result()
        result.value = 0.0014
        return result

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki"},
    )
    assert captured["quantity"] == "ki"
    assert result["ok"] is True
    assert result["found"] is True
    assert result["ki"] == 0.0014
    assert "km" not in result


def test_quantity_defaults_to_km(monkeypatch):
    """A payload with no quantity keeps the Km contract intact: the value
    is emitted under "km" and the resolver is told quantity="km"."""
    captured = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured["quantity"] = kwargs.get("quantity", "km")
        return golden_result()

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert captured["quantity"] == "km"
    assert result["km"] == 10.73
    assert "ki" not in result


def test_not_found_output_shape(monkeypatch):
    def not_found(*a, **k):
        return KineticResult(
            found=False,
            source="literature_candidates",
            literature_candidates=[
                fallback_logic.LiteratureCandidate(
                    pmid="34962677",
                    title="Some paper",
                    url="https://pubmed.ncbi.nlm.nih.gov/34962677/",
                )
            ],
            search_log=["genuine gap"],
        )

    result = run_main(
        monkeypatch,
        not_found,
        {"enzymeName": "lactate dehydrogenase", "substrate": "x",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": False,
        "source": "literature_candidates",
        "literatureCandidates": [
            {"pmid": "34962677", "title": "Some paper",
             "url": "https://pubmed.ncbi.nlm.nih.gov/34962677/"}
        ],
        "logs": ["genuine gap"],
    }


def test_missing_ec_and_name_reports_an_error(monkeypatch):
    """With neither an EC number nor an enzyme name, there is nothing to
    search for -- this must still be a hard error, not a network attempt."""
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"substrate": "x"})))
    monkeypatch.setattr(sys, "stdout", stdout)
    with pytest.raises(SystemExit):
        science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result["ok"] is False
    assert "enzymeName or ecNumber is required" in result["error"]


def test_missing_ec_number_resolves_it_live_via_uniprot(monkeypatch):
    """The behaviour this replaces: previously, any query without an
    explicit EC number was an unrecoverable error, which meant only the
    hardcoded pattern list in enzymes.ts could ever reach a real lookup.
    Now, an enzyme name with no EC number attempts a live UniProt
    name search first (mocked here to stay offline) and, if that
    succeeds, proceeds through the normal BRENDA chain using the
    resolved EC number."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: "9606")
    monkeypatch.setattr(
        enzyme_lookup,
        "fetch_ec_number_by_name",
        lambda name, taxon_id: "3.2.1.1" if name == "alpha-amylase" else None,
    )

    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(),
        {"enzymeName": "alpha-amylase", "substrate": "starch", "organism": "Homo sapiens"},
    )
    assert result["ok"] is True
    assert result["found"] is True
    assert result["km"] == 10.73
    # The live resolution step's own log line must survive alongside
    # whatever fallback_logic.resolve_kinetic_value itself logged.
    assert any("Resolved EC 3.2.1.1" in line for line in result["logs"])


def test_missing_ec_number_also_resolves_substrate_via_kegg(monkeypatch):
    """A live-resolved enzyme has no substrate name from the (unused)
    enzymes.ts entry, and BRENDA's Km table is dominated by noise without
    one (see enzyme_lookup.py's module docstring). This confirms the
    KEGG substrate lookup actually reaches fallback_logic.resolve_kinetic_value,
    not just that the runner doesn't crash without one."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: "9606")
    monkeypatch.setattr(
        enzyme_lookup, "fetch_ec_number_by_name", lambda name, taxon_id: "3.2.1.1"
    )
    monkeypatch.setattr(
        enzyme_lookup,
        "fetch_kegg_enzyme_text",
        lambda ec_number: "SUBSTRATE   starch [CPD:C00369]",
    )

    captured_args = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured_args["substrate"] = substrate
        captured_args["enzyme_ec"] = enzyme_ec
        captured_args["quantity"] = kwargs.get("quantity", "km")
        return golden_result()

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "alpha-amylase", "organism": "Homo sapiens"},
    )
    assert result["ok"] is True
    assert captured_args["substrate"] == "starch"
    assert captured_args["enzyme_ec"] == "3.2.1.1"
    assert any(
        "Resolved substrate 'starch'" in line for line in result["logs"]
    )


def test_missing_ec_number_exhausted_uniprot_lookup_reports_not_found(monkeypatch):
    """When UniProt has nothing indexed under the given name, this must be
    an honest 'not found' -- never a fabricated EC number or Km, and never
    a crash."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: None)
    monkeypatch.setattr(
        enzyme_lookup, "fetch_ec_number_by_name", lambda name, taxon_id: None
    )

    stdout = io.StringIO()
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"enzymeName": "not a real enzyme name"})),
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result == {
        "ok": True,
        "found": False,
        "source": "ec_not_resolved",
        "literatureCandidates": [],
        "logs": [
            ("Could not resolve an EC number for 'not a real enzyme name' via "
             "UniProt; no BRENDA/KEGG/PubMed lookup is possible without one.")
        ],
    }
