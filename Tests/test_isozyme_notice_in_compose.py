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
    # And no longer unqualified. Since the third round's review the notice
    # says whose constants these are -- every cited row names GCK -- instead
    # of "may belong to any of them", and the K0.5 is a concern of its own.
    assert "Qualified: EC 2.7.1.1 is 5 proteins in human and no --isoform was given" in verdict
    assert "every cited row names GCK, so these are GCK's constants" in verdict
    assert "2 concern(s), worst first:" in verdict
    assert "[isozymes] EC 2.7.1.1 is 5 human proteins" in verdict
    assert "[row_scope] `reaction_Km` carries a K0.5 with a Hill coefficient of 1.8 (GCK's)" in verdict
    # By gene symbol, which is what a paper and a person write, not by UniProt entry-name mnemonic.
    for symbol in ("HKDC1", "HK1", "HK2", "HK3", "GCK"):
        assert symbol in verdict
    assert "HXK1" not in verdict
    assert "may belong to any of them" not in verdict
    assert "--isoform" in verdict.split("Do this next:")[1].split("\n")[0]


def test_the_notice_is_also_beside_the_constants(compose):
    _, out = compose("--organism", "human")
    section = out.split("### Which isozyme")[1].split("###")[0]
    assert "5 human proteins" in section and "every cited row names GCK" in section
    assert "Pass --isoform" in section
    assert out.index("### Which isozyme") > out.index("## Where the numbers come from")


def test_the_notice_does_not_change_what_was_measured(compose):
    """The constants are the resolver's picks, notice or no notice. Since
    2026-11-11 a Km and a kcat come from one paper when one holds both
    (ADR 0182, resolve_kinetic_pair): ref 739603, a glucokinase study, Km
    6.3 mM and kcat 40.1 1/s. Picked apart they were HK-I's 0.06 mM beside
    another paper's 60.4 1/s, and before the median 6.0 mM and 40.1 1/s.
    That the pick moves from one isozyme to another is the notice's whole
    point."""
    _, out = compose("--organism", "human")
    assert "| `reaction_Km` | 6.3 mM | literature (Homo sapiens) | BRENDA ref 739603 |" in out
    assert "| `reaction_kcat` | 40.1 1/s | literature (Homo sapiens) | BRENDA ref 739603 |" in out


def test_typing_an_isoform_does_not_carry_another_isozymes_row(compose):
    """`--isoform HK-1` takes the Km from the row that says "hexokinase I" (ref 640237). The kcat row
    "wild type enzyme" of ref 703624 names no isozyme in its commentary, but its UniProt cell is P35557,
    glucokinase: a row BRENDA itself files under another protein of the EC is that protein's, and is not
    carried (compose/protein_rows.py; the resolver reads the row's own cell too, fallback_logic
    `_row_isoform`). Since the merge of the rows and names rounds (2026-11-12) the resolver sets the
    P35557 rows aside itself. It then carried a row naming no isoform and carrying no accession (38 1/s,
    ref 672188) -- a glucokinase Y214C paper's wild-type row, among human D-glucose kcat rows every one of
    which that names a protein names GCK. Since the third round's review (fallback_logic._isoform_tiers)
    rows naming none among more rows naming only another protein are that protein's field, and the kcat
    is a placeholder saying so."""
    code, out = compose("--organism", "human", "--isoform", "HK-1")
    assert code == 0
    assert "| `reaction_Km` | 0.06 mM | literature (Homo sapiens) | BRENDA ref 640237 |" in out
    kcat = next(line for line in out.splitlines() if line.startswith("| `reaction_kcat` |"))
    assert "BRENDA ref 703624" not in kcat and "60.4 1/s" not in kcat
    assert "672188" not in kcat and "**placeholder**" in kcat
    assert "naming none sit among them" in kcat and "GCK" in kcat


@pytest.mark.parametrize(
    "label, km_ref, km_value",
    [("HK1", "640237", "0.06"), ("HXK1", "640237", "0.06"), ("hexokinase 1", "640237", "0.06"), ("hexokinase I", "640237", "0.06"),
     ("HK2", "702867", "0.37"), ("HXK2", "702867", "0.37"), ("hexokinase II", "702867", "0.37"), ("hexokinase type II", "702867", "0.37")],
)
def test_a_label_the_chooser_offers_takes_the_row_that_states_that_isozyme(compose, label, km_ref, km_value):
    """Before: `--isoform HK1` left the Km at 6.0 mM (ref 641068, a row naming no isozyme) and the notice went
    quiet, because the engine knew the papers' spelling "hexokinase II" and not the gene symbol it offered."""
    code, out = compose("--organism", "human", "--isoform", label)
    assert code == 0
    assert f"| `reaction_Km` | {km_value} mM | literature (Homo sapiens) | BRENDA ref {km_ref} |" in out
    assert f"--isoform '{label}' was read as" in out and "a row is taken as measuring it when its commentary names it" in out


@pytest.mark.parametrize("label", ["GCK", "glucokinase", "HXK4", "hexokinase IV"])
def test_an_isozyme_named_only_by_its_rows_uniprot_cell_is_that_isozyme(compose, label):
    """No Km row's words name glucokinase; ref 739603's row names it by its UniProt cell (P35557).
    Until ADR 0182's second round only the words were read, and the Km was 6.0 mM (ref 641068, a row
    naming no isozyme) under "the row names no isoform". The accession is the row's statement, so the
    glucokinase row is carried, and what it is -- a K0.5 with a Hill coefficient of 1.8 -- is said."""
    code, out = compose("--organism", "human", "--isoform", label)
    assert code == 0
    assert "| `reaction_Km` | 6.3 mM | literature (Homo sapiens) | BRENDA ref 739603 |" in out
    assert "the row is **a K0.5 with a Hill coefficient of 1.8**, not a Michaelis-Menten Km" in out
    assert f"`reaction_Km`: the row names no isoform, so whether it measured **{label}**" not in out


def test_a_label_no_protein_carries_says_it_matched_nothing(compose):
    code, out = compose("--organism", "human", "--isoform", "HK9")
    assert code == 0
    assert "--isoform 'HK9' is not a gene symbol or name the enzyme nomenclature's UniProt entries give" in out
    # No row names HK9. Rows naming none were used until the third round's review; they sit among
    # more rows naming HK-I, HK-II, HK-III and GCK, so they are those proteins' field and are not
    # taken as HK9's (fallback_logic._isoform_tiers).
    km = next(line for line in out.splitlines() if line.startswith("| `reaction_Km` |"))
    assert "**placeholder**" in km and "641067" not in km
    assert "naming none sit among them" in km


def _model_whose_rows_say(*commentaries):
    """A model with the cited rows' own commentary, copied from the recorded BRENDA page for EC 2.7.1.1."""
    from types import SimpleNamespace

    measured = {f"c{i}": SimpleNamespace(commentary=text) for i, text in enumerate(commentaries)}
    return SimpleNamespace(subject="2.7.1.1", organism="human", isoform="HK1", measured=measured)


def test_the_notice_goes_quiet_only_when_every_cited_constants_row_states_the_isoform():
    from caterva.enzymes.isozyme import notice_for_model

    states = "hexokinase I, at 37\u00b0C, pH 8.1"      # ref 640237, as the page writes it
    silent = "wild type enzyme, in 25 mM HEPES (pH 7.4), at 37\u00b0C"  # ref 703624
    assert notice_for_model(_model_whose_rows_say(states, states)) is None
    one = notice_for_model(_model_whose_rows_say(states, silent))
    assert one is not None and one.unstated == ("c1",) and one.isoform == "HK1"
    both = notice_for_model(_model_whose_rows_say(silent, silent))
    assert both.unstated == ("c0", "c1")
    other = notice_for_model(_model_whose_rows_say("hexokinase II, at 37\u00b0C", states))
    assert other.unstated == ("c0",), "a row naming another isozyme is not a row that states this one"


def test_it_does_not_fire_when_the_nomenclature_lists_no_protein_for_the_organism(compose):
    # The nomenclature's UniProt entries for EC 2.7.1.1 name no E. coli
    # protein, so there is no isozyme to name. (A pig case used here needed
    # a UniProt query no recording holds; the one-protein case is pinned
    # below on the function itself.)
    #
    # This asserted an E. coli Km "resolved from the literature" until
    # 2026-11-11. The recorded page holds no E. coli hexokinase row: the
    # parser matched "Escherichia coli" anywhere in a row, and Trypanosoma
    # cruzi's hexokinase, "expressed in Escherichia coli" (ref 640265), was
    # carried as E. coli's. Matched on the organism cell, nothing is found,
    # and the Km stays a placeholder naming the organisms that do have one.
    code, out = compose("--organism", "Escherichia coli")
    assert code == 0
    assert "resolved from the literature: reaction_Km" not in out
    assert "| `reaction_Km` | 0.1 mM | **placeholder** |" in out
    assert "isozyme" not in out and "Qualified:" not in out


def test_it_does_not_fire_when_nothing_was_measured_from_the_literature(monkeypatch, capsys):
    from caterva.compose.__main__ import main

    code = main(["Michaelis Menten", "--no-simulate", "--no-ranking", "--no-analysis"])
    out = capsys.readouterr().out
    assert code == 0 and "isozyme" not in out


def test_the_guard_for_each_quiet_case_is_the_notice_function_itself():
    from caterva.enzymes.isozyme import isozyme_notice

    assert isozyme_notice("2.7.1.1", "human", None).count == 5
    assert isozyme_notice("2.7.1.1", "human", "HK-1", unstated=[]) is None, "every cited row states it"
    assert isozyme_notice("2.7.1.1", "human", "HK-1", unstated=["reaction_kcat"]).unstated == ("reaction_kcat",)
    assert isozyme_notice("2.7.1.1", "human", "HK-1").unstated is None, "nobody checked: said, not assumed"
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
    assert "[isozymes] EC 2.7.1.1 is 5 human proteins" in out
