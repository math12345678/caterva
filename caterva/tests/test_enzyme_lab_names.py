"""Run the 169 names a reviewer typed, in 4 organisms, through the finder, and hold every outcome to a hand-checked class.

WHY THIS EXISTS
---------------
An adversarial science review ran the enzyme finder on 169 names a lab types
(GAPDH, HK2, SDH, NOS, glycogen synthase, ...) in human, mouse, yeast and
E. coli, 676 outcomes. It found names RESOLVED to the wrong enzyme: HK1, HK2
and HK3 to histidine kinases, SDH to L-sorbose 1-dehydrogenase, NOS to
D-nopaline dehydrogenase, AST to arginine N-succinyltransferase, SYK to a
lysine--tRNA ligase, PEPC to gastricsin, AK to acetate kinase, glycogen synthase
to the bacterial starch synthase. A wrong EC number is a real, correctly
formatted citation for a different protein (ADR 0126), so that is the one
failure this project cannot have.

`fixtures/enzymes/lab_names.json` holds, for each name, the EC numbers it may
legitimately resolve or be recommended as (`verified`, read against the
IUBMB nomenclature and UniProtKB by hand) and the outcome class expected in
each organism. The finder runs offline on the committed index and the
committed symbol table, so nothing here is mocked and nothing is invented.
These tests assert, for every name in every organism:

* it never resolves to an EC number outside its verified set;
* it is never recommended an EC number outside that set, and a recommendation
  is only made where it is the one listed enzyme with a protein from the
  organism;
* it lands in the expected class, and never lists a candidate it was told to
  exclude (IDH1 in yeast is not the human enzyme).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from caterva.enzymes.__main__ import find_payload

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "enzymes" / "lab_names.json").read_text(encoding="utf-8"))
ORGANISMS = FIXTURE["organisms"]
NAMES = FIXTURE["names"]
CASES = [(n["query"], organism) for n in NAMES for organism in ORGANISMS]
BY_QUERY = {n["query"]: n for n in NAMES}


@pytest.fixture(scope="module")
def answers():
    return {}


def answer(cache, query, organism):
    key = (query, organism)
    if key not in cache:
        cache[key] = find_payload(query, organism, 500)
    return cache[key]


def expectation(entry, organism):
    return dict(entry, **entry.get("by_organism", {}).get(organism, {}))


def test_the_fixture_covers_every_name_the_reviewer_ran_in_every_organism():
    assert len(NAMES) >= 169
    assert ORGANISMS == ["human", "mouse", "yeast", "E. coli"]
    assert len({n["query"] for n in NAMES}) == len(NAMES)
    right = ["GAPDH", "trypsin", "thrombin", "cathepsin B", "caspase-3", "beta-lactamase", "lysozyme", "hexokinase",
             "pyruvate kinase", "catalase", "SOD", "acetylcholinesterase", "monoamine oxidase", "creatine kinase", "COMT",
             "PARP1", "ACE", "BACE1", "PKA", "PKC", "HDAC"]
    assert all(name in BY_QUERY for name in right)


def test_every_ec_the_fixture_names_is_an_active_enzyme_of_the_nomenclature():
    """A typo in the hand-checked table would defeat it: each number must be a real, current EC number."""
    from caterva.enzymes import load_index

    entries = load_index().entries
    named = set()
    for entry in NAMES:
        named.update(entry["verified"], entry.get("include", ()), entry.get("exclude", ()))
        for override in entry.get("by_organism", {}).values():
            named.update(override.get("include", ()), override.get("exclude", ()), [override["ec"]] if "ec" in override else [])
        for listed in entry.get("verified_by_organism", {}).values():
            named.update(listed)
        if "ec" in entry:
            named.add(entry["ec"])
    assert len(named) > 100
    gone = sorted(ec for ec in named if ec not in entries or entries[ec].status != "active")
    assert gone == []


@pytest.mark.parametrize("query, organism", CASES)
def test_no_name_resolves_or_is_recommended_to_an_enzyme_outside_its_verified_set(answers, query, organism):
    entry = BY_QUERY[query]
    payload = answer(answers, query, organism)
    verified = set(entry.get("verified_by_organism", {}).get(organism, entry["verified"]))
    assert verified, "every name has the set of enzymes it may mean"
    resolved = payload.get("resolved_ec")
    assert resolved is None or resolved in verified, (
        f"{query!r} in {organism} resolved to EC {resolved}, which is not one of {sorted(verified)}")
    recommended = payload.get("recommended_ec")
    assert recommended is None or recommended in verified, (
        f"{query!r} in {organism} recommends EC {recommended}, outside {sorted(verified)}")
    with_protein = [c["ec"] for c in payload["candidates"] if c["has_organism_protein"]]
    assert recommended is None or with_protein == [recommended], (
        f"{query!r} in {organism} recommends EC {recommended} but {with_protein} have a protein there")
    chosen = next((c for c in payload["candidates"] if c["ec"] == recommended), None)
    assert recommended is None or chosen["matched_by"] in ("name", "ec"), "only a name match is evidence for a recommendation"


@pytest.mark.parametrize("query, organism", CASES)
def test_each_name_lands_in_the_class_checked_by_hand(answers, query, organism):
    entry = BY_QUERY[query]
    want = expectation(entry, organism)
    payload = answer(answers, query, organism)
    listed = [c["ec"] for c in payload["candidates"]]
    kind = want["expect"]
    if kind == "resolved":
        assert payload["outcome"] == "resolved" and payload["resolved_ec"] == want["ec"], (
            f"{query!r} in {organism}: {payload['outcome']} {payload.get('resolved_ec')} {listed[:6]}")
    elif kind == "candidates":
        assert payload["outcome"] != "resolved", f"{query!r} in {organism} was resolved to {payload['resolved_ec']}"
        include = want["include"]
        assert include, f"{query!r}: a candidates class names the enzymes it must offer"
        missing = [ec for ec in include if ec not in listed]
        assert not missing, f"{query!r} in {organism} does not offer {missing}; it lists {listed[:10]}"
    elif kind == "resolved-or-candidates":
        assert (payload.get("resolved_ec") == want["ec"]) or want["ec"] in listed, (query, organism, listed[:10])
    elif kind == "none-honest":
        assert payload["outcome"] != "resolved"
        stray = [ec for ec in listed if ec not in set(entry.get("verified_by_organism", {}).get(organism, entry["verified"]))]
        assert not stray, f"{query!r} in {organism} offers {stray}, none of them an enzyme this name means"
    elif kind == "unresolved":
        assert payload["outcome"] != "resolved", f"{query!r} in {organism} was resolved to {payload['resolved_ec']}"
    elif kind == "suggestions-only":
        assert payload["outcome"] != "resolved"
        assert all(c["partial_match"] or c["tier"] == 9 for c in payload["candidates"]), (
            f"{query!r} in {organism} lists a confirmed reading: {listed[:6]}")
    else:  # pragma: no cover - a typo in the fixture
        raise AssertionError(f"unknown class {kind!r} for {query!r}")
    for ec in want.get("exclude", []):
        assert ec not in listed, f"{query!r} in {organism} offers EC {ec}, which is another organism's enzyme"


def test_counts_for_the_report(answers):
    """Not a check: the counts the change reports, kept where they can be rerun."""
    resolved = wrong = recommended = honest_none = 0
    for query, organism in CASES:
        payload = answer(answers, query, organism)
        verified = set(BY_QUERY[query].get("verified_by_organism", {}).get(organism, BY_QUERY[query]["verified"]))
        if payload["outcome"] == "resolved":
            resolved += 1
            wrong += payload["resolved_ec"] not in verified
        recommended += payload.get("recommended_ec") is not None
        honest_none += payload["outcome"] == "none"
    assert wrong == 0
    assert resolved > 0 and honest_none > 0
