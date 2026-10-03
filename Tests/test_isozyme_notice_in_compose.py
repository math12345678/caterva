"""`caterva compose` says when one EC number is several proteins in the organism.

WHY THIS EXISTS
---------------
`caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human
--substrate glucose` reported verdict GROUNDED with Km 6 mM and kcat 40.1 1/s.
Both constants came from glucokinase (hexokinase IV) papers; the same BRENDA
page holds hexokinase I and III rows 80 to 190 times lower, and nothing in
the report said an isozyme was in play. The enzyme nomenclature lists five
human proteins under EC 2.7.1.1.

These tests run the real compose command, in-process, against the committed
recording of BRENDA's real page for EC 2.7.1.1 and the recorded NCBI and
UniProt answers (Tests/fixtures/recorded/README.md): no network, no invented
data. They check the notice appears with the verdict and beside the
constants, that GROUNDED is neither changed nor left unqualified, and that
it stays quiet when it should.
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
RECORDED = REPO / "Tests" / "fixtures" / "recorded"

BASE = ["Michaelis Menten", "--subject", "2.7.1.1", "--substrate", "glucose",
        "--no-simulate", "--no-ranking"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every request these tests make is answered from a recording, or the test fails.

    The literature layer's GETs go through httpx (Tests/http_retry.py), which
    is replaced here by a function that records the URL and refuses, so an
    organism or enzyme the recordings do not cover cannot reach UniProt, NCBI
    or PubChem and pass or fail with their mood. Every proxy points at a
    closed port as well, for any client that does not go through httpx. The
    test then asserts that nothing was attempted.
    """
    import httpx

    attempted: list[str] = []

    def refuse(url, *args, **kwargs):
        attempted.append(str(url))
        raise httpx.ConnectError(f"no recording answers {url}; this test does not go live")

    monkeypatch.setattr(httpx, "get", refuse)
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    yield attempted
    assert attempted == [], f"a request had no recording and was refused: {attempted}"


@pytest.fixture()
def compose(monkeypatch, capsys):
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    monkeypatch.setenv("CATERVA_HTTP_RECORDED", str(RECORDED / "http"))
    from caterva.compose.__main__ import main

    def run(*extra):
        code = main(BASE + list(extra))
        return code, capsys.readouterr().out

    return run


def _verdict_block(out):
    return out.split("```")[1]


def test_the_notice_names_the_isozymes_and_qualifies_the_verdict(compose):
    code, out = compose("--organism", "human")
    assert code == 0
    verdict = _verdict_block(out)
    # Still GROUNDED: every constant is measured and cited.
    assert "VERDICT: GROUNDED" in verdict
    assert "What this supports: Questions about the system whose constants these are" in verdict
    # And no longer unqualified.
    assert "Qualified: EC 2.7.1.1 is 5 proteins in human and no --isoform was given" in verdict
    assert "1 concern(s), worst first:" in verdict
    assert "[isozymes] EC 2.7.1.1 has 5 human isozymes" in verdict
    for symbol in ("HKDC1", "HXK1", "HXK2", "HXK3", "HXK4"):
        assert symbol in verdict
    assert "may belong to any of them" in verdict
    assert "--isoform" in verdict.split("Do this next:")[1].split("\n")[0]


def test_the_notice_is_also_beside_the_constants(compose):
    _, out = compose("--organism", "human")
    section = out.split("### Which isozyme")[1].split("###")[0]
    assert "5 human isozymes" in section and "Pass --isoform" in section
    assert out.index("### Which isozyme") > out.index("## Where the numbers come from")


def test_the_notice_does_not_change_what_was_measured(compose):
    _, out = compose("--organism", "human")
    assert "| `reaction_Km` | 6.0 mM | literature (Homo sapiens) | BRENDA ref 641068 |" in out
    assert "| `reaction_kcat` | 40.1 1/s | literature (Homo sapiens) | BRENDA ref 739603 |" in out


def test_it_does_not_fire_when_an_isoform_is_given(compose):
    code, out = compose("--organism", "human", "--isoform", "HK-1")
    assert code == 0
    assert "isozyme" not in out and "Qualified:" not in out
    assert "VERDICT: GROUNDED" in _verdict_block(out)


def test_it_does_not_fire_when_the_nomenclature_lists_no_protein_for_the_organism(compose):
    # The nomenclature's UniProt entries for EC 2.7.1.1 name no E. coli
    # protein, so there is no isozyme to name; the recorded page holds an
    # E. coli Km, and the recorded NCBI and UniProt answers cover E. coli.
    # (A pig case used here needed a UniProt query no recording holds; the
    # one-protein case is pinned below on the function itself.)
    code, out = compose("--organism", "Escherichia coli")
    assert code == 0
    assert "resolved from the literature: reaction_Km" in out
    assert "isozyme" not in out and "Qualified:" not in out


def test_it_does_not_fire_when_nothing_was_measured_from_the_literature(monkeypatch, capsys):
    from caterva.compose.__main__ import main

    code = main(["Michaelis Menten", "--no-simulate", "--no-ranking", "--no-analysis"])
    out = capsys.readouterr().out
    assert code == 0 and "isozyme" not in out


def test_the_guard_for_each_quiet_case_is_the_notice_function_itself():
    from caterva.enzymes.isozyme import isozyme_notice

    assert isozyme_notice("2.7.1.1", "human", None).count == 5
    assert isozyme_notice("2.7.1.1", "human", "HK-1") is None
    assert isozyme_notice("2.7.1.1", "pig", None) is None
    assert isozyme_notice("2.7.1.1", None, None) is None
    assert isozyme_notice("2.7.1.1", "Thermus aquaticus", None) is None
    assert isozyme_notice(None, "human", None) is None
    assert isozyme_notice("1.1.1", "human", None) is None


def test_a_name_read_as_an_ec_number_gets_the_notice_too(compose, monkeypatch, capsys):
    from caterva.compose.__main__ import main

    code = main(["Michaelis Menten", "--subject", "hexokinase", "--organism", "human", "--substrate", "glucose",
                 "--no-simulate", "--no-ranking"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Read 'hexokinase' as EC 2.7.1.1 (hexokinase): accepted name matches exactly." in out
    assert "[isozymes] EC 2.7.1.1 has 5 human isozymes" in out
