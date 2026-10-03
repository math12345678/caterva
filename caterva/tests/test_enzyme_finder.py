"""The finder ranks by NAME, resolves only when the answer is not a choice.

WHY THIS EXISTS
---------------
Measured before the finder, with `caterva compose --subject NAME`:

    "lactate dehydrogenase"  refused: 1.1.98.-, 1.1.1.27, 1.1.1.28, 1.1.-.-,
                             1.1.5.12, 1.1.2.4   (bare numbers, no names)
    "pyruvate kinase"        refused: 2.7.1.40, 2.7.11.1, 2.7.10.2 (the last
                             two are protein kinases that merely mention it)
    "glucokinase"            refused with 8 EC numbers; "LDH" with 4

Every case below is one of those names, or one a research group types, run
against the REAL enzyme index built from the ExPASy ENZYME release it names.
Where the data makes a name unique the test asserts it resolves; where the
data makes it a choice, the test asserts the candidates are named and that
nothing was picked. Nothing is mocked and no data is invented: a changed
release that changes an outcome should fail here and be read by a person.
"""
from __future__ import annotations

import pytest

from caterva.enzymes import (
    Ambiguous, Resolved, find, isozymes, load_index, organism_code, read_ec,
    refusal_text, resolve,
)
from caterva.enzymes.finder import (
    TIER_ACCEPTED_EXACT, TIER_ACCEPTED_TOLERANT, TIER_EC, TIER_TYPO, loose_key, strict_key,
)


def ecs(candidates):
    return [c.ec for c in candidates]


# --- the owner's complaint, one name at a time -----------------------------


def test_lactate_dehydrogenase_lists_both_stereo_enzymes_by_name_with_the_human_entries():
    result = resolve("lactate dehydrogenase", "human")
    assert isinstance(result, Ambiguous)
    assert ecs(result.candidates[:2]) == ["1.1.1.27", "1.1.1.28"]
    l_ldh, d_ldh = result.candidates[:2]
    assert (l_ldh.name, d_ldh.name) == ("L-lactate dehydrogenase", "D-lactate dehydrogenase")
    assert {p.symbol for p in l_ldh.organism_proteins} >= {"LDHA", "LDHB", "LDHC"}
    assert l_ldh.organism_protein_count == len(l_ldh.organism_proteins) == 5
    assert l_ldh.has_organism_protein and not d_ldh.has_organism_protein
    # Neither of the bare class numbers the old lookup returned.
    assert not any(c.ec.endswith(".-") for c in result.candidates)


def test_lactate_dehydrogenase_recommends_the_human_one_and_still_picks_nothing():
    result = resolve("lactate dehydrogenase", "human")
    assert isinstance(result, Ambiguous), "a recommendation is not a resolution"
    assert result.recommended is not None and result.recommended.ec == "1.1.1.27"
    text = refusal_text(result)
    assert "recommended" in text
    assert text.endswith("--subject 1.1.1.27")


def test_without_an_organism_there_is_nothing_to_recommend():
    result = resolve("lactate dehydrogenase")
    assert isinstance(result, Ambiguous)
    assert result.recommended is None
    assert ecs(result.candidates[:2]) == ["1.1.1.27", "1.1.1.28"]
    assert refusal_text(result).endswith("for example --subject 1.1.1.27")


def test_a_recommendation_needs_exactly_one_tied_enzyme_with_the_organisms_protein():
    # Both of these are exact alternative names for two enzymes, and both
    # enzymes have human proteins: nothing may be recommended.
    result = resolve("aldehyde reductase", "human")
    assert isinstance(result, Ambiguous)
    assert set(ecs(result.candidates[:2])) == {"1.1.1.1", "1.1.1.21"}
    assert all(c.has_organism_protein for c in result.candidates[:2])
    assert result.recommended is None


def test_l_lactate_dehydrogenase_resolves_to_the_l_enzyme():
    result = resolve("L-lactate dehydrogenase", "human")
    assert isinstance(result, Resolved) and result.ec == "1.1.1.27"
    assert result.how == "accepted name matches exactly"


def test_ldh_is_not_resolved_because_the_data_only_ever_uses_it_inside_a_longer_name():
    """What the data really says: "LDH" is an alternative-name FRAGMENT of
    EC 1.1.1.436 ("electron bifurcating LDH/Etf complex") and a UniProt
    symbol (LDH_BACSU) under EC 1.1.1.27. No name is "LDH". It must not
    resolve to the one that happens to contain the letters."""
    result = resolve("LDH", "human")
    assert isinstance(result, Ambiguous)
    assert result.suggestions_only
    by_ec = {c.ec: c for c in result.candidates}
    assert by_ec["1.1.1.436"].partial and by_ec["1.1.1.27"].partial
    assert "LDH/Etf" in by_ec["1.1.1.436"].why
    assert all(c.name for c in result.candidates)


def test_pyruvate_kinase_resolves_and_ranks_first_with_no_protein_kinase_above_it():
    result = resolve("pyruvate kinase", "human")
    assert isinstance(result, Resolved) and result.ec == "2.7.1.40"
    ranked = find("pyruvate kinase", "human", limit=None)
    assert ranked[0].ec == "2.7.1.40" and ranked[0].tier == TIER_ACCEPTED_EXACT
    # The two protein kinases the old lookup returned are absent: they were
    # only ever linked to pyruvate kinase by a comment.
    assert "2.7.11.1" not in ecs(ranked) and "2.7.10.2" not in ecs(ranked)
    assert all(c.tier > ranked[0].tier for c in ranked[1:])


def test_hexokinase_resolves_to_2_7_1_1_and_names_its_five_human_proteins():
    result = resolve("hexokinase", "human")
    assert isinstance(result, Resolved) and result.ec == "2.7.1.1"
    found = isozymes("2.7.1.1", "human")
    assert found.count == 5
    assert set(found.symbols) == {"HKDC1", "HXK1", "HXK2", "HXK3", "HXK4"}


def test_glucokinase_resolves_to_the_enzyme_named_that_and_warns_it_has_no_human_protein():
    """The data: EC 2.7.1.2 is named glucokinase and lists no human protein;
    human glucokinase (HXK4_HUMAN) is filed under EC 2.7.1.1 as
    'hexokinase type IV (glucokinase)'. Both facts are surfaced."""
    result = resolve("glucokinase", "human")
    assert isinstance(result, Resolved) and result.ec == "2.7.1.2"
    assert result.candidate.organism_protein_count == 0
    (caution,) = result.cautions
    assert "lists no human protein" in caution
    assert "EC 2.7.1.1 (hexokinase)" in caution and "HXK4" in caution
    ranked = find("glucokinase", "human")
    by_ec = {c.ec: c for c in ranked}
    assert by_ec["2.7.1.1"].alternative_names == ("hexokinase type IV (glucokinase)",)
    assert by_ec["2.7.1.1"].has_organism_protein
    assert ranked[0].ec == "2.7.1.2"


def test_alcohol_dehydrogenase_is_unique_at_the_best_tier():
    result = resolve("alcohol dehydrogenase", "human")
    assert isinstance(result, Resolved) and result.ec == "1.1.1.1"
    assert {p.symbol for p in result.candidate.organism_proteins} >= {"ADH1A", "ADH1G", "ADH6", "ADH7"}


@pytest.mark.parametrize(
    "name, ec, accepted",
    [
        ("acetylcholinesterase", "3.1.1.7", "acetylcholinesterase"),
        ("carbonic anhydrase", "4.2.1.1", "carbonic anhydrase"),
        ("dihydrofolate reductase", "1.5.1.3", "dihydrofolate reductase"),
        ("cytochrome c oxidase", "7.1.1.9", "cytochrome-c oxidase"),
    ],
)
def test_common_enzymes_resolve_to_their_accepted_names(name, ec, accepted):
    result = resolve(name, "human")
    assert isinstance(result, Resolved) and result.ec == ec
    assert result.candidate.name == accepted
    assert result.candidate.has_organism_protein


# --- EC numbers ------------------------------------------------------------


@pytest.mark.parametrize("text", ["EC 1.1.1.27", "E.C. 1.1.1.27", "ec:1.1.1.27", " 1.1.1.27 ", "EC1.1.1.27", "1.1.1.27."])
def test_an_ec_number_is_read_however_it_is_written(text):
    result = resolve(text)
    assert isinstance(result, Resolved) and result.ec == "1.1.1.27"
    assert result.how == "you gave this EC number"
    assert find(text)[0].tier == TIER_EC


def test_a_partial_ec_number_is_a_class_and_lists_its_members():
    result = resolve("1.1.1.-")
    assert isinstance(result, Ambiguous)
    assert "class of enzymes" in result.reason
    members = find("1.1.1.-", limit=None)
    assert len(members) > 100 and all(c.ec.startswith("1.1.1.") for c in members)
    assert all("a member of EC 1.1.1.-" in c.why for c in members)
    assert find("1.1.1.-", limit=3).__len__() == 3
    assert read_ec("1.1.-.-") == ("1", "1") and read_ec("2.7.1") == ("2", "7", "1")


def test_a_number_that_is_not_an_ec_number_is_not_read_as_one():
    assert read_ec("pyruvate kinase") is None
    assert read_ec("42") is None
    assert read_ec("1,1,1,27") is None


def test_a_transferred_ec_number_resolves_to_its_replacement_and_says_so():
    result = resolve("1.1.1.32")
    assert isinstance(result, Resolved) and result.ec == "1.1.1.1"
    assert "was transferred" in result.how and "EC 1.1.1.1 (alcohol dehydrogenase)" in result.how
    assert result.cautions and "transferred" in result.cautions[0]
    ranked = find("1.1.1.32")
    assert ranked[0].ec == "1.1.1.32" and ranked[0].status == "transferred"
    assert ranked[0].superseded_by == ("1.1.1.1",)
    assert ranked[1].ec == "1.1.1.1" and "replaces EC 1.1.1.32" in ranked[1].why


def test_an_ec_number_transferred_to_several_enzymes_names_them_and_picks_none():
    result = resolve("1.1.1.5")
    assert isinstance(result, Ambiguous)
    assert ecs(result.candidates) == ["1.1.1.303", "1.1.1.304"]
    assert "transferred to 2 enzymes" in result.reason
    assert refusal_text(result).endswith("for example --subject 1.1.1.303")


def test_a_deleted_ec_number_resolves_to_nothing_and_says_it_was_deleted():
    result = resolve("1.1.1.74")
    assert isinstance(result, Ambiguous) and not result.candidates
    assert "deleted" in result.reason and "no replacement" in result.reason
    assert find("1.1.1.74")[0].status == "deleted"


def test_an_ec_number_the_nomenclature_does_not_hold_is_said_not_guessed():
    result = resolve("9.9.9.9")
    assert isinstance(result, Ambiguous) and not result.candidates
    assert "is not in the enzyme nomenclature" in result.reason


# --- tolerance, and where it ranks -----------------------------------------


def test_case_punctuation_hyphens_and_spacing_do_not_matter():
    assert resolve("  l-LACTATE   dehydrogenase ").ec == "1.1.1.27"
    assert resolve("L lactate dehydrogenase").ec == "1.1.1.27"
    assert resolve("cytochrome-c oxidase").ec == "7.1.1.9"
    assert resolve("CYTOCHROME C OXIDASE").ec == "7.1.1.9"
    # Without the L- it is the tolerant reading, so it is a choice again.
    assert isinstance(resolve("Lactate-Dehydrogenase"), Ambiguous)


def test_stereo_labels_are_tolerated_but_rank_below_an_exact_match():
    exact = find("L-lactate dehydrogenase", limit=None)
    tolerant = find("lactate dehydrogenase", limit=None)
    assert exact[0].ec == "1.1.1.27" and exact[0].tier == TIER_ACCEPTED_EXACT
    assert {c.ec: c.tier for c in tolerant}["1.1.1.27"] == TIER_ACCEPTED_TOLERANT
    assert TIER_ACCEPTED_TOLERANT > TIER_ACCEPTED_EXACT
    # An exact alternative name outranks a tolerant accepted name.
    assert find("aldehyde reductase")[0].tier < TIER_ACCEPTED_TOLERANT


def test_a_greek_letter_is_read_as_its_name_and_ranks_below_the_spelled_name():
    spelled, greek = find("alpha-amylase")[0], find("α-amylase")[0]
    assert spelled.ec == greek.ec == "3.2.1.1"
    assert spelled.tier == TIER_ACCEPTED_EXACT and greek.tier == TIER_ACCEPTED_TOLERANT
    assert loose_key("α-amylase") == loose_key("alpha-amylase") == "alpha amylase"
    assert strict_key("α-amylase") != strict_key("alpha-amylase")


def test_a_stereo_prefix_never_changes_which_words_are_compared():
    assert loose_key("(S)-lactate dehydrogenase") == "lactate dehydrogenase"
    assert loose_key("D-glucose 6-phosphate") == "glucose 6 phosphate"
    # "l-" inside a word is not a configuration label.
    assert loose_key("cell-wall hydrolase") == "cell wall hydrolase"


# --- typos -----------------------------------------------------------------


@pytest.mark.parametrize(
    "typo, expected",
    [("lactat dehydrogenase", {"1.1.1.27", "1.1.1.28"}), ("hexokinse", {"2.7.1.1"}),
     ("pyruvat kinase", {"2.7.1.40"}), ("acetylcholinesteras", {"3.1.1.7"})],
)
def test_a_typo_gives_a_did_you_mean_and_never_resolves(typo, expected):
    result = resolve(typo, "human")
    assert isinstance(result, Ambiguous)
    assert result.suggestions_only
    assert expected <= set(ecs(result.candidates))
    assert all(c.tier == TIER_TYPO and "did you mean" in c.why for c in result.candidates)
    assert "Did you mean" in refusal_text(result)


def test_a_typo_is_offered_only_when_nothing_better_matched():
    assert all(c.tier != TIER_TYPO for c in find("pyruvate kinase", limit=None))
    assert all(c.tier != TIER_TYPO for c in find("kinase", limit=None))


def test_a_short_abbreviation_is_never_offered_close_spellings():
    result = resolve("DHFR", "human")
    assert isinstance(result, Ambiguous) and not result.candidates


def test_nothing_matching_says_so_and_offers_nothing():
    result = resolve("xyzzy plugh")
    assert isinstance(result, Ambiguous) and not result.candidates
    assert "matches 'xyzzy plugh'" in result.reason
    assert find("xyzzy plugh") == []
    assert find("") == [] and find("   ") == []


# --- order within a tier, and the invariants -------------------------------


def test_within_a_tier_the_organisms_enzymes_come_first_then_the_shorter_name_then_the_ec():
    ranked = find("kinase", "human", limit=None)
    tier = [c for c in ranked if c.tier == ranked[0].tier]
    keys = [(not c.has_organism_protein, len(c.name)) for c in tier]
    assert keys == sorted(keys)
    same = [c for c in tier if (c.has_organism_protein, len(c.name)) == (tier[0].has_organism_protein, len(tier[0].name))]
    numeric = [tuple(int(p) if p.isdigit() else 10**6 for p in c.ec.split(".")) for c in same]
    assert numeric == sorted(numeric)


def test_tiers_never_decrease_down_a_result_list():
    for query in ["lactate dehydrogenase", "kinase", "glucokinase", "amylase", "hexokinase", "1.1.1.-", "LDH"]:
        tiers = [c.tier for c in find(query, "human", limit=None)]
        assert tiers == sorted(tiers), query


def test_the_same_query_gives_the_same_answer_every_time():
    assert find("dehydrogenase", "human", limit=50) == find("dehydrogenase", "human", limit=50)
    assert ecs(find("kinase", limit=30)) == ecs(find("kinase", limit=30))


def test_every_name_tier_match_has_the_query_words_in_that_enzymes_own_names():
    """The point of ranking by name: no enzyme is listed because of what
    somebody else's comment or name says."""
    index = load_index()
    for query in ["pyruvate kinase", "glucokinase", "lactate dehydrogenase", "hexokinase"]:
        words = set(loose_key(query).split())
        for candidate in find(query, limit=None):
            if candidate.tier == TIER_TYPO or candidate.tier == 8:
                continue
            entry = index.get(candidate.ec)
            names = [entry.name, *entry.alternative_names]
            assert any(words <= set(loose_key(n).split()) for n in names), (query, candidate.ec)


def test_an_organism_the_index_does_not_know_ranks_nothing_by_organism():
    with_org = find("hexokinase", "Thermus aquaticus")[0]
    assert with_org.organism is None and with_org.organism_protein_count == 0
    assert organism_code("Thermus aquaticus") is None
    assert isozymes("2.7.1.1", "Thermus aquaticus").organism is None


def test_organism_names_are_read_as_the_uniprot_codes():
    for typed in ["human", "Homo sapiens", "HUMAN", "  Human "]:
        assert organism_code(typed) == "HUMAN"
    assert organism_code("E. coli") == organism_code("Escherichia coli") == "ECOLI"
    assert organism_code("cow") == "BOVIN" and organism_code("baker's yeast") == "YEAST"
    assert organism_code("monkey") is None


def test_isozymes_counts_each_organisms_entries_for_an_ec():
    assert isozymes("2.7.1.1", "human").count == 5
    assert isozymes("2.7.1.1", "pig").count == 1
    assert isozymes("2.7.1.1", "pig").symbols == ("HXK2",)
    assert isozymes("2.7.1.1", None).count == 0
    # An organism the index holds a count for but no list: the count stands.
    fission = isozymes("2.7.1.1", "fission yeast")
    assert fission.count == 2 and fission.proteins == ()
    assert set(isozymes("1.1.1.27", "Homo sapiens").symbols) >= {"LDHA", "LDHB", "LDHC"}


def test_the_candidate_carries_everything_the_command_prints():
    candidate = find("L-lactate dehydrogenase", "human")[0]
    assert candidate.reaction == "(S)-lactate + NAD(+) = pyruvate + NADH + H(+)."
    assert candidate.class_path.startswith("Oxidoreductases > acting on the CH-OH group of donors")
    assert candidate.label().startswith("EC 1.1.1.27 L-lactate dehydrogenase (human: ")
    as_dict = candidate.to_dict()
    assert as_dict["ec"] == "1.1.1.27" and as_dict["has_organism_protein"] is True
    assert as_dict["organism_proteins"][0]["accession"]
