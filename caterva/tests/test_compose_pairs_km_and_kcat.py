"""A composed model's Km and kcat come from one paper when one holds both (ADR 0182).

`fallback_logic.resolve_kinetic_pair` resolves a Km and a kcat together and,
when their papers differ but some paper holds a row of each among the rows
each choice was made from, takes both from that paper: two papers mean two
preparations and often two temperatures. `caterva compose` asked the
resolver for each constant on its own, so on the committed human hexokinase
page it carried HK-I's Km (0.06 mM, ref 640237, 37 C) beside another paper's
kcat (60.4 1/s, ref 703624). These hold the wiring: the model marks the two
requests `paired`, the live resolver answers both from one pair, and the
report says why each row was carried instead of "the resolver's pick, not a
verdict".
"""
from __future__ import annotations

from types import SimpleNamespace

from caterva.agents import scouts
from caterva.compose.export import Measurement, Spread
from caterva.compose.pipeline import compose


def _literature(monkeypatch):
    """The literature layer the live resolver imports, as it imports it: the
    checkout's Tests/ as flat modules (caterva.checkout), with the package
    form made to fail first exactly as it does from an ordinary interpreter."""
    import sys

    from caterva.checkout import literature_module

    monkeypatch.setitem(sys.modules, "Tests.fallback_logic", None)
    return literature_module("fallback_logic")


def _requests(description, **kwargs):
    model = compose(description, subject="2.7.1.1", organism="Homo sapiens", **kwargs)
    return {r.quantity: r for r in model.parameter_requests()}


def test_a_km_and_a_kcat_of_one_substrate_are_marked_as_a_pair():
    requests = _requests("Michaelis Menten", substrate="D-glucose")
    assert requests["reaction_Km"].paired is True
    assert requests["reaction_kcat"].paired is True


def test_an_inhibitors_ki_is_never_part_of_the_pair():
    requests = _requests("Michaelis-Menten with a competitive inhibitor", substrate="D-glucose",
                         compounds={"@inhibitor": "atorvastatin"})
    assert requests["reaction_Km"].paired is True and requests["reaction_kcat"].paired is True
    assert requests["reaction_Ki"].paired is False


def test_the_live_resolver_answers_both_halves_from_one_pair(monkeypatch):
    calls = []
    km = SimpleNamespace(found=True, quantity="km")
    kcat = SimpleNamespace(found=True, quantity="kcat")

    def pair(ec, organism, substrate, **kwargs):
        calls.append((ec, organism, substrate, kwargs.get("allow_cross_species")))
        return km, kcat

    def single(**kwargs):
        raise AssertionError("a paired request must not be resolved on its own")

    fallback_logic = _literature(monkeypatch)
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_pair", pair)
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", single)
    resolve = scouts.brenda_resolver()
    requests = _requests("Michaelis Menten", substrate="D-glucose")
    got_km = resolve(requests["reaction_Km"], organism="Homo sapiens", allow_cross_species=False)
    got_kcat = resolve(requests["reaction_kcat"], organism="Homo sapiens", allow_cross_species=False)
    assert got_km is km and got_kcat is kcat
    assert calls == [("2.7.1.1", "Homo sapiens", "D-glucose", False)], "one pair, asked once"


def test_an_unpaired_request_is_resolved_on_its_own(monkeypatch):
    fallback_logic = _literature(monkeypatch)
    seen = []
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_pair",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("not a pair")))
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value",
                        lambda **k: seen.append(k["quantity"]) or SimpleNamespace(found=False))
    request = SimpleNamespace(quantity="reaction_Km", ec_number="2.7.1.1", substrate="D-glucose",
                              subject="2.7.1.1", table="km", paired=False)
    scouts.brenda_resolver()(request, organism="Homo sapiens", allow_cross_species=False)
    assert seen == ["km"]


def test_the_report_says_why_the_row_was_carried():
    spread = Measurement(
        6.3, "mM", "BRENDA ref 739603",
        alternatives=({"value": 0.06, "reference_id": "640237"}, {"value": 6.3, "reference_id": "739603"}),
        resolver_because="6.3 mM (BRENDA ref 739603) is the one remaining row from BRENDA ref 739603, "
                         "the paper the paired constant came from",
    ).spread
    assert spread is not None
    assert spread.carried_as.startswith("chosen because 6.3 mM (BRENDA ref 739603) is the one remaining row")
    assert "the resolver's pick, not a verdict" not in spread.sentence()


def test_a_reselection_s_reason_wins_over_the_resolver_s():
    spread = Spread(low=1, high=2, unit="mM", carried=2, n_values=2, references=("1", "2"),
                    chosen_because="the row for LDH-A, as --isoform asked",
                    resolver_because="1 mM (BRENDA ref 1) is the median")
    assert spread.carried_as == "the row for LDH-A, as --isoform asked"
    assert Spread(low=1, high=2, unit="mM", carried=2, n_values=2,
                  references=()).carried_as == "the resolver's pick, not a verdict"
