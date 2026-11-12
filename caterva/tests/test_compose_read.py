"""One reading of a sentence for every front end: `python -m caterva.compose.read`.

WHY THESE TESTS
---------------
The adversarial round of 2026-11-11 found the HTTP API and the TypeScript
CLI reading sentences that compose and Studio read right, each with a reader
of its own: chymotrypsin as trypsin, "Michaelis-Menten" as a substrate,
allopurinol (the inhibitor) as the substrate, HK2 without its isoform, the
organism a default instead of a choice. Both now ask this module, which is
compose's own reading (`read_description`, the enzyme policy, the ADR 0182
choosers) printed as JSON. These pin that it IS compose's reading, and the
shape the two front ends parse.

Offline: the committed BRENDA page for EC 2.7.1.1 with every real send made
impossible, or `defaults.table_rows` answering from rows written here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from caterva.compose import defaults, read

RECORDED = Path(__file__).resolve().parents[2] / "Tests" / "fixtures" / "recorded"
KEYS = {"description", "enzyme_text", "ec", "isoform", "organism", "organism_text", "substrate",
        "inhibitor", "rule", "tables", "named", "choices", "notes", "refusal"}


@pytest.fixture
def offline(monkeypatch):
    """BRENDA's hexokinase page from the recording, and no network at all."""
    import httpx

    attempts = []

    def refuse(self, request):
        attempts.append(str(request.url))
        raise httpx.ConnectError("network disabled in this test", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    return attempts


def _rows(monkeypatch, tables, reaction=(frozenset(), frozenset())):
    def table_rows(ec, table, organism):
        out = []
        for (t, org), counts in tables.items():
            if t != table or (organism is not None and org != organism):
                continue
            out += [defaults._Row(name, org, "") for name, n in counts.items() for _ in range(n)]
        return tuple(out)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: reaction)


@pytest.mark.parametrize("sentence", [
    "hexokinase Michaelis-Menten kinetics",
    "hexokinase Michaelis Menten kinetics",
    "hexokinase in human Michaelis-Menten",
    "hexokinase kinetics",
])
def test_the_model_s_name_is_never_the_substrate_and_the_substrate_is_chosen_out_loud(offline, sentence):
    got = read.read(sentence)
    assert offline == []
    assert set(got) == KEYS
    assert (got["ec"], got["rule"], got["organism"], got["substrate"]) == (
        "2.7.1.1", "michaelis_menten", "Homo sapiens", "D-glucose")
    substrate = [c for c in got["choices"] if c["role"] == "substrate"]
    assert substrate and substrate[0]["chosen"] == "D-glucose"
    assert substrate[0]["note"].startswith("No substrate was named, so Caterva used D-glucose:")
    assert {"role", "chosen", "why", "alternatives", "considered", "note"} <= set(substrate[0])


def test_a_named_organism_is_named_not_chosen(offline):
    got = read.read("hexokinase in human Michaelis-Menten")
    assert got["named"] == {"organism": "Homo sapiens"}
    assert [c["role"] for c in got["choices"]] == ["substrate"]


def test_no_organism_is_a_choice_with_its_reason(offline):
    got = read.read("hexokinase kinetics")
    organism = got["choices"][0]
    assert organism["role"] == "organism" and organism["chosen"] == "Homo sapiens"
    assert "Homo sapiens is used when it has rows for every constant this model needs" in organism["why"]
    assert organism["alternatives"]


def test_a_gene_symbol_is_its_isoform(offline):
    got = read.read("HK2 with glucose")
    assert (got["ec"], got["isoform"], got["substrate"]) == ("2.7.1.1", "HK2", "D-glucose")
    assert any("HK2" in n for n in got["notes"])


def test_chymotrypsin_is_chymotrypsin(monkeypatch):
    _rows(monkeypatch, {("km", "Homo sapiens"): {"Suc-AAPF-pNA": 3},
                        ("kcat", "Homo sapiens"): {"Suc-AAPF-pNA": 2}})
    got = read.read("chymotrypsin follows Michaelis-Menten kinetics", choose=True)
    assert got["ec"] == "3.4.21.1"
    assert got["substrate"] == "Suc-AAPF-pNA"


def test_the_inhibitor_is_the_inhibitor_and_the_organism_is_chosen_for_its_ki(monkeypatch):
    """'xanthine oxidase inhibited by allopurinol': allopurinol is the
    inhibitor, never the Km's substrate, and the organism is the one with an
    allopurinol Ki row, said with why human was not used."""
    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"xanthine": 10, "allopurinol": 1})
    monkeypatch.setattr(defaults, "ki_compounds", lambda ec, org: {"allopurinol": 1})
    _rows(monkeypatch, {
        ("km", "Homo sapiens"): {"xanthine": 6, "allopurinol": 1}, ("kcat", "Homo sapiens"): {"xanthine": 3},
        ("km", "Bos taurus"): {"xanthine": 4}, ("kcat", "Bos taurus"): {"xanthine": 2},
        ("ki", "Bos taurus"): {"allopurinol": 1}, ("ki", "Homo sapiens"): {"febuxostat": 2},
    })
    for sentence in ("xanthine oxidase inhibited by allopurinol",
                     "competitive inhibition of xanthine oxidase by allopurinol"):
        got = read.read(sentence)
        assert (got["ec"], got["rule"], got["inhibitor"], got["substrate"], got["organism"]) == (
            "1.17.3.2", "competitive_inhibition", "allopurinol", "xanthine", "Bos taurus"), sentence
        assert got["tables"] == ["km", "kcat", "ki"]
        assert got["named"] == {"inhibitor": "allopurinol"}
        organism = got["choices"][0]
        assert organism["role"] == "organism"
        assert "Homo sapiens, preferred when it covers them all, does not" in organism["why"]


def test_flags_win_over_the_sentence(offline):
    got = read.read("hexokinase kinetics", organism="Homo sapiens", substrate="D-mannose")
    assert (got["organism"], got["substrate"]) == ("Homo sapiens", "D-mannose")
    assert got["choices"] == []


def test_a_sentence_with_no_enzyme_is_said_and_exits_3(offline, capsys):
    assert read.main(["the spread of measles in a school", "--json"]) == 3
    got = json.loads(capsys.readouterr().out)
    assert got["ec"] is None and got["refusal"]


def test_no_choose_reads_without_choosing(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("BRENDA was read")

    monkeypatch.setattr(defaults, "table_rows", boom)
    got = read.read("chymotrypsin kinetics", choose=False)
    assert got["ec"] == "3.4.21.1" and got["choices"] == [] and got["substrate"] is None
