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
    # By gene symbol, which is what a paper and a person write, not by UniProt entry-name mnemonic.
    for symbol in ("HKDC1", "HK1", "HK2", "HK3", "GCK"):
        assert symbol in verdict
    assert "HXK1" not in verdict
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


def test_typing_an_isoform_does_not_silence_the_notice_while_a_cited_row_names_no_isozyme(compose):
    """`--isoform HK-1` takes the Km from the row that says "hexokinase I" (ref 640237). The kcat's row says
    "wild type enzyme" and names no isozyme, so whether it measured hexokinase 1 is unknown: the notice stays,
    names that constant, and GROUNDED stays qualified."""
    code, out = compose("--organism", "human", "--isoform", "HK-1")
    assert code == 0
    verdict = _verdict_block(out)
    assert "VERDICT: GROUNDED" in verdict
    assert "Qualified: HK-1 was asked for, but the row for `reaction_kcat` does not state which isozyme" in verdict
    assert "--isoform HK-1 was given for EC 2.7.1.1" in verdict and "`reaction_kcat` comes from a row" in verdict
    assert "reaction_Km" not in verdict.split("[isozymes]")[1].split("\n")[0].split("but")[1]
    assert "| `reaction_Km` | 0.06 mM | literature (Homo sapiens) | BRENDA ref 640237 |" in out
    assert "### Which isozyme" in out


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
def test_an_isozyme_no_km_row_names_visibly_says_so_and_keeps_the_notice(compose, label):
    code, out = compose("--organism", "human", "--isoform", label)
    assert code == 0
    assert "| `reaction_Km` | 6.0 mM | literature (Homo sapiens) | BRENDA ref 641068 |" in out
    assert f"the row names no isoform, so whether it measured **{label}**, the one asked for, is unknown" in out
    verdict = _verdict_block(out)
    assert f"Qualified: {label} was asked for, but" in verdict and "reaction_Km" in verdict


def test_a_label_no_protein_carries_says_it_matched_nothing(compose):
    code, out = compose("--organism", "human", "--isoform", "HK9")
    assert code == 0
    assert "--isoform 'HK9' is not a gene symbol or name the enzyme nomenclature's UniProt entries give" in out
    assert "| `reaction_Km` | 6.0 mM |" in out or "refused" in out


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


def test_it_does_not_fire_when_the_organism_has_one_protein_for_the_ec(compose):
    # The nomenclature lists one pig protein for EC 2.7.1.1, and the recorded
    # page holds a pig Km.
    code, out = compose("--organism", "pig")
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
    assert "[isozymes] EC 2.7.1.1 has 5 human isozymes" in out
