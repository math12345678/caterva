"""A compound named for a mechanism that has no step for it is said to be unused, not searched for.

`caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose --inhibitor gossypol`
printed "searched for 2.7.1.1 ... inhibitor gossypol", though a Michaelis-Menten model has a Km and a kcat and
no inhibition step, so only those two were looked up. The report now says the inhibitor was not used, why, and
how to ask for one; the Studio's structured result does not echo it as a searched compound.

These run the real compose command in-process against the committed recording of BRENDA's page for EC 2.7.1.1
(Tests/fixtures/recorded/README.md): no network, no invented data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RECORDED = REPO / "Tests" / "fixtures" / "recorded"


@pytest.fixture()
def compose(monkeypatch, capsys):
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    monkeypatch.setenv("CATERVA_HTTP_RECORDED", str(RECORDED / "http"))
    from caterva.compose.__main__ import main

    def run(description, *extra):
        code = main([description, "--subject", "2.7.1.1", "--organism", "human", "--substrate", "glucose",
                     "--no-simulate", "--no-ranking", "--no-analysis", *extra])
        return code, capsys.readouterr().out

    return run


def test_an_inhibitor_given_to_a_mechanism_with_no_inhibition_step_is_reported_as_not_used(compose):
    code, out = compose("Michaelis Menten", "--inhibitor", "gossypol")
    assert code == 0
    searched = out.split("came from the literature**, searched for")[1].split("\n")[0]
    assert "gossypol" not in searched and "substrate glucose" in searched
    assert "**Not used: --inhibitor gossypol.**" in out
    assert "has no step that compound could belong to, so no constant was looked up for it" in out
    assert "ask for a mechanism with an inhibition step (for example `competitive inhibition`)" in out


def test_without_an_unused_compound_the_report_says_nothing_about_one(compose):
    code, out = compose("Michaelis Menten")
    assert code == 0 and "Not used:" not in out


def test_the_model_says_which_named_compounds_it_has_a_step_for():
    from caterva.compose.pipeline import compose

    plain = compose("Michaelis Menten", subject="2.7.1.1", organism="human", substrate="glucose",
                    compounds={"@inhibitor": "gossypol"})
    assert plain.unused_compounds() == {"@inhibitor": "gossypol"} and plain.used_compounds() == {}
    inhibited = compose("competitive inhibition", subject="2.7.1.1", organism="human", substrate="glucose",
                        compounds={"@inhibitor": "gossypol"})
    assert inhibited.unused_compounds() == {} and inhibited.used_compounds() == {"@inhibitor": "gossypol"}
    both = compose("competitive inhibition", subject="2.7.1.1", organism="human", substrate="glucose",
                   compounds={"@inhibitor": "gossypol", "@product": "glucose 6-phosphate"})
    assert both.unused_compounds() == {"@product": "glucose 6-phosphate"}
