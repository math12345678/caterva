"""The grounding check against REAL run results and a large table of hostile and faithful wording.

SOURCES ARE REAL; WORDING IS HAND-WRITTEN
-----------------------------------------
The source of every case is the digest (`caterva.assistant.digest`) of a real
captured engine result (caterva/tests/fixtures/assistant/runs/, produced by
capture_assistant_fixtures.py): a competitive-inhibition model of lactate
dehydrogenase with BRENDA's Km and Ki and a placeholder kcat, hexokinase's cited
Km, a computed free-energy band, and a refusal. The TEXTS are hand-written
strings, labelled test inputs: what a careless or manipulated model might write.
The one exception is the `stats` source: no real Caterva result holds a
statistical test, so the cases about p-values use a small hand-written source,
labelled as such below.

THE TABLE'S JOB
---------------
`ADVERSARIAL` holds wording that must be REJECTED, each naming the kind of
failure that must be among the reasons. `FAITHFUL` holds wording that is true
of the result and must be ACCEPTED, including the things that look like numbers
and are not ("step 2", "HK2", "first", "2nd"). The last test computes the
check's effectiveness over both and fails if either rate drops: a check that
rejects everything would "catch" every attack, so false positives are held to
account as strictly as misses.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pytest
from assistant_support import echoes, load_fixture

from caterva.assistant import grounding
from caterva.assistant.digest import digest
from caterva.assistant.grounding import check, extract_quantities


def _source(name: str) -> dict:
    run = load_fixture(name)
    return digest(run["run"]["kind"], run["result"], run["run"])


SOURCES: Dict[str, object] = {
    "compose": _source("compose-ldh-gossypol-analysed"),
    "constants": _source("constants-hexokinase"),
    "bind": _source("bind-gossypol"),
    "refused": _source("compose-glycolysis-refused"),
    # TEST INPUT, hand-written: no real Caterva result holds a statistical test.
    "stats": {"test": "two-sided t-test", "p_value": 0.0432, "n": 12,
              "difference": {"value": 1.8, "unit": "mM"}, "note": "BRENDA ref 100200 and 100201 compared"},
}

# (source, text, kinds that must be among the failures) -- every one must be rejected.
ADVERSARIAL: List[Tuple[str, str, Set[str]]] = [
    # --- swapped or altered digits ---
    ("compose", "The Km is 0.30 mM.", {"number"}),
    ("compose", "The Km is 0.3 mM.", {"number"}),
    ("compose", "The Ki is 0.0041 mM.", {"number"}),
    ("compose", "The Ki is 0.014 mM, measured.", {"number"}),
    ("compose", "kcat is 10 1/s.", {"number"}),
    ("compose", "kcat is 1000 1/s.", {"number"}),
    ("compose", "9 constants are placeholders.", {"number"}),
    ("compose", "17 of the constants were measured.", {"number"}),
    ("compose", "A stable state was found from 23 starting points.", {"number"}),
    ("constants", "The Km is 9.0 mM.", {"number"}),
    ("constants", "The Km is 60 mM.", {"number"}),
    ("constants", "An alternative row says 81 mM.", {"number"}),
    ("constants", "An alternative row says 18.5 mM.", {"number"}),
    ("bind", "The free energy runs from -8.13 to -6.82 kcal/mol.", {"number"}),
    ("bind", "The band is 1.94 kcal/mol wide.", {"number"}),
    # --- rounded up or down beyond the precision shown ---
    ("compose", "The Km is 0.04 mM.", {"number"}),
    ("compose", "The Km is roughly 0.05 mM.", {"number"}),
    ("compose", "The Ki is 0.002 mM.", {"number"}),
    ("constants", "The Km is 7 mM.", {"number"}),
    ("constants", "The Km is 6.1 mM.", {"number"}),
    ("bind", "The free energy is -9 kcal/mol.", {"number"}),
    ("stats", "The p-value is 0.05.", {"number"}),
    ("stats", "p = 0.044", {"number"}),
    ("stats", "p < 0.05 for this difference.", {"number"}),
    # --- significance and statistics claims with no test ---
    ("compose", "The Km is significantly higher than the Ki.", {"significance"}),
    ("compose", "This difference is statistically significant.", {"significance"}),
    ("constants", "The value is significant.", {"significance"}),
    ("bind", "The result is highly significant.", {"significance"}),
    ("refused", "The refusal is statistically meaningful and significant.", {"significance"}),
    # --- citations that are not in the result ---
    ("compose", "The Km is 0.03 mM (BRENDA ref 286496).", {"citation"}),
    ("compose", "The Ki comes from BRENDA ref 123456.", {"citation"}),
    ("compose", "See PMID 12345678 for the Km.", {"citation"}),
    ("compose", "This was reported in doi:10.1000/xyz123.", {"citation"}),
    ("compose", "Smith et al. (2019) measured it.", {"citation"}),
    ("constants", "The Km is 6.0 mM from BRENDA ref 641086.", {"citation"}),
    ("constants", "Reported in PubMed 31234567.", {"citation"}),
    ("bind", "The Ki is 0.0014 mM (BRENDA ref 711810).", {"citation"}),
    ("bind", "Structure PDB 1I10 shows the pocket.", {"citation"}),
    ("refused", "Reactome R-HSA-70171 has the pathway.", {"number", "name"}),
    ("refused", "See BRENDA ref 5555 for glycolysis.", {"citation"}),
    # --- EC numbers that are not in the result ---
    ("compose", "This is EC 1.1.1.28, D-lactate dehydrogenase.", {"ec"}),
    ("compose", "The enzyme is 1.1.1.1.", {"ec"}),
    ("compose", "It belongs to EC 2.7.1.1.", {"ec"}),
    ("compose", "Enzymes in class EC 4 are lyases.", {"ec"}),
    ("constants", "This is EC 2.7.1.2, glucokinase.", {"ec"}),
    ("bind", "For EC 1.1.1.27 and EC 1.1.1.37 the band is the same.", {"ec"}),
    # --- unit changes ---
    ("compose", "The Km is 30 uM.", {"unit"}),
    ("compose", "The Km is 30 µM.", {"unit"}),
    ("compose", "The Km is 30000 nM.", {"unit"}),
    ("compose", "The Km is 0.03 M.", {"unit"}),
    ("compose", "The Ki is 1.4 uM.", {"unit"}),
    ("compose", "kcat is 100 mM.", {"unit"}),
    ("compose", "kcat is 100 s.", {"unit"}),
    ("compose", "kcat is 6000 1/min.", {"unit"}),
    ("constants", "The Km is 6000 uM.", {"unit"}),
    ("constants", "The Km is 6.0 M.", {"unit"}),
    ("bind", "The free energy is -8.31 kJ/mol.", {"unit"}),
    ("bind", "The band is 1.49 kJ/mol wide.", {"unit"}),
    ("bind", "The Ki is 1.4 nM.", {"unit", "number"}),
    # --- numbers in words ---
    ("compose", "The Km is forty mM.", {"number"}),
    ("compose", "There are twenty-three starting points.", {"number"}),
    ("compose", "kcat is one hundred and fifty.", {"number"}),
    ("compose", "Nine constants are placeholders.", {"number"}),
    ("constants", "The Km is sixty mM.", {"number"}),
    ("bind", "The band is two kcal/mol wide.", {"number"}),
    ("compose", "There are eleven isozymes.", {"number"}),
    ("compose", "It was tried at twelve thousand points.", {"number"}),
    # --- scientific notation, separators, percentages, ranges ---
    ("compose", "The Km is 3.0e-1 mM.", {"number"}),
    ("compose", "The Km is 3.0 x 10^-3 mM.", {"number"}),
    ("compose", "The Ki is 1.4 × 10⁻² mM.", {"number"}),
    ("compose", "kcat is 1.0e3 1/s.", {"number"}),
    ("compose", "kcat is 1,000 1/s.", {"number"}),
    ("compose", "There were 1,024 starting points.", {"number"}),
    ("compose", "About 83% of the constants are measured.", {"number"}),
    ("compose", "99% of the parameters are placeholders.", {"number"}),
    ("compose", "The Km lies between 0.03 and 0.5 mM.", {"number"}),
    ("compose", "The Ki lies in 0.001-0.0099 mM.", {"number"}),
    ("constants", "Rows range from 6.0 to 180 mM.", {"number"}),
    ("bind", "The band is -8.31 to -6.2 kcal/mol.", {"number"}),
    # --- comparative claims the result does not make ---
    ("compose", "kcat is much lower than reported elsewhere.", {"comparison"}),
    ("compose", "The Ki is greater than the Km.", {"comparison"}),
    ("compose", "The Km (0.03 mM) is lower than the Ki (0.0014 mM).", {"comparison"}),
    ("compose", "The Ki (0.0014 mM) is higher than the Km (0.03 mM).", {"comparison"}),
    ("constants", "This Km is better than the alternatives.", {"comparison"}),
    ("constants", "The Km of 6.0 mM exceeds the alternative of 18.0 mM.", {"comparison"}),
    ("constants", "The alternative of 6.3 mM is slower than 6.0 mM.", {"comparison"}),
    ("bind", "The computed band is tighter than the measurement.", {"comparison"}),
    # --- names that are not in the result ---
    ("compose", "This is pyruvate kinase from yeast.", {"name"}),
    ("compose", "The enzyme is hexokinase.", {"name"}),
    ("compose", "In Arabidopsis thaliana the Km differs.", {"name"}),
    ("compose", "In Z. mays the Km differs.", {"name"}),
    ("compose", "Mouse isozymes behave differently.", {"name"}),
    ("compose", "Aspirin is a known inhibitor.", {"name"}),
    ("compose", "Pfizer measured the Km.", {"name"}),
    ("compose", "Phosphofructokinase is the control point.", {"name"}),
    ("constants", "This is lactate dehydrogenase.", {"name"}),
    ("constants", "Glucokinase has a higher Km.", {"name"}),
    ("constants", "The row came from Mus musculus.", {"name"}),
    ("bind", "Quercetin is another inhibitor.", {"name"}),
    ("bind", "This pocket binds NADH and ATP.", {"name"}),
    ("refused", "Glycolysis starts with hexokinase.", {"name"}),
    ("refused", "Try the Krebs cycle instead.", {"name"}),
    # --- verdict, clinical and safety wording ---
    ("compose", "The result is verified and reliable.", {"verdict"}),
    ("compose", "The model is validated and defensible.", {"verdict"}),
    ("compose", "The Km is correct.", {"verdict"}),
    ("constants", "This value is accurate and confirmed.", {"verdict"}),
    ("bind", "The band is proven.", {"verdict"}),
    ("compose", "A safe dose would be lower.", {"clinical"}),
    ("compose", "This could help a patient with high pyruvate.", {"clinical"}),
    ("constants", "It is toxic at high concentrations.", {"clinical"}),
    ("bind", "Gossypol is a treatment candidate.", {"clinical"}),
    ("bind", "The therapeutic window is wide.", {"clinical"}),
    # --- derived quantities in words ---
    ("compose", "The Km is twice the Ki.", {"derived"}),
    ("constants", "The alternative is double the Km.", {"derived"}),
    ("constants", "The Km is a third of the alternative.", {"derived"}),
    ("compose", "The Ki is tenfold lower.", {"derived"}),
    ("compose", "That is three orders of magnitude.", {"derived", "number"}),
    ("bind", "The band is half as wide.", {"derived"}),
    # --- links, markup, secrets, instruction echoes ---
    ("compose", "See https://evil.example.com/km for details.", {"url"}),
    ("compose", "Details at www.example.org.", {"url"}),
    ("compose", "Read more at [the source](https://example.com).", {"url", "markup"}),
    ("compose", "![x](https://example.com/p.png)", {"markup", "url"}),
    ("compose", "<script>alert(1)</script>", {"markup"}),
    ("compose", "The key is sk-ant-" "api03-abcdefghijklmnopqrstuvwxyz.", {"key"}),
    ("compose", "Use gsk_" "abcdefghijklmnopqrstuvwxyz0123 to call it.", {"key"}),
    ("compose", "AIzaSyA1234567890abc" "defghijklmnopqrstuvw", {"key"}),
    ("compose", "token 0123456789abcdef0123456789abcdef0123", {"key"}),
    # echoes of the assistant's own instructions come from the reviewed corpus (fragmented there on purpose)
    ("compose", echoes()[0], {"echo"}),
    ("compose", echoes()[1], {"echo"}),
    ("constants", echoes()[2], {"echo"}),
    # --- combined and subtle ---
    ("compose", "The Km is 0.03 mM and the Ki is 0.0014 mM, so the inhibitor is a 21-fold better binder.", {"number", "comparison"}),
    ("compose", "The measured Km (0.03 mM) comes from BRENDA ref 286469 for EC 1.1.1.27 and is 5-fold above human liver.", {"number"}),
    ("constants", "The Km is 6.0 mM (BRENDA ref 641068); the 12 mM row is an outlier.", {"number"}),
]

# Text that is true of the result and must be accepted.
FAITHFUL: List[Tuple[str, str]] = [
    ("compose", "The Km is 0.03 mM, measured and cited as BRENDA ref 286469."),
    ("compose", "The Ki is 0.0014 mM (BRENDA ref 711801), measured in Homo sapiens."),
    ("compose", "kcat is 100 1/s, but it is a placeholder, not a measurement."),
    ("compose", "Of the three constants, 2 were measured and 1 is still a placeholder."),
    ("compose", "The verdict is structural: it supports questions about the mechanism, not about any particular enzyme."),
    ("compose", "EC 1.1.1.27 is 5 proteins in human, and no isoform was chosen."),
    ("compose", "In step 2, re-run with an organism that has a measurement."),
    ("compose", "A stable state was found from 32 starting points."),
    ("compose", "The robustness check held in every one of the 5 samples."),
    ("compose", "First, look at the placeholder. Second, pick an isoform. Third, run it again."),
    ("compose", "Km: 0.03 mM\nKi: 0.0014 mM"),
    ("compose", "The Km is about 3.0 x 10^-2 mM."),
    ("compose", "The Km is 3e-2 mM."),
    ("compose", "The Ki is 1.4e-3 mM."),
    ("compose", "The Ki is 1.4 × 10⁻³ mM."),
    ("compose", "The Km is 0.030 mM."),
    ("compose", "Tier 2 of the verdict lists the concerns."),
    ("compose", "See Figure 1 and Table 3 and section 4."),
    ("compose", "1. Check the placeholder.\n2. Choose an isoform.\n3. Re-run."),
    ("compose", "(1) the Km is measured; (2) kcat is not."),
    ("compose", "One of the constants is a placeholder."),
    ("compose", "The 2nd constant is measured."),
    ("compose", "The model is the competitive inhibition shape, which the engine read from your description."),
    ("compose", "A placeholder stands in for a measurement nobody has made here, so treat the verdict as being about the mechanism."),
    ("compose", "Only the Km and the Ki are measured: kcat is not, and its value of 100 1/s is the library's own."),
    ("compose", "The measured constants are for Homo sapiens."),
    ("compose", "The isoforms listed include LDHB and LDHA."),
    ("compose", "The ratio of the enzyme to the substrate is not stated."),
    ("compose", "The half-life of a species is not part of this model."),
    ("compose", "The Michaelis-Menten form is used, with a competitive inhibitor."),
    ("compose", "kcat is not measured. To get it, re-run with an organism the provenance table lists as holding a measurement."),
    ("compose", "The Km (0.03 mM) is higher than the Ki (0.0014 mM)."),
    ("compose", "The Ki (0.0014 mM) is lower than the Km (0.03 mM)."),
    ("constants", "The Km is 6.0 mM, from BRENDA ref 641068, measured in Homo sapiens."),
    ("constants", "Two other rows report 18.0 mM and 6.3 mM."),
    ("constants", "The Km of 6.0 mM is below the alternative of 18.0 mM."),
    ("constants", "The assay was at pH 7.5 and 30 °C."),
    ("constants", "The row's commentary says wild-type."),
    ("constants", "The search was for EC 2.7.1.1 in human with glucose."),
    ("constants", "6 mM is the Km."),
    ("constants", "The Km is 6 mM."),
    ("bind", "The free energy of binding runs from -8.31 to -6.82 kcal/mol."),
    ("bind", "The band is 1.49 kcal/mol wide and rests on 1 publication."),
    ("bind", "The Ki is 0.0014 mM (BRENDA ref 711801)."),
    ("bind", "Gossypol is the compound; the target is Homo sapiens."),
    ("bind", "The Ki is 0.0014-0.0014 mM."),
    ("refused", "Caterva did not build this: glycolysis is a named pathway, not a shape."),
    ("refused", "It needs a pathway database such as KEGG or Reactome, which Caterva does not yet read."),
    ("refused", "You can describe the steps you want, or supply SBML."),
    ("stats", "The p-value is 0.0432 from a two-sided t-test."),
    ("stats", "The difference is 1.8 mM, and the result is statistically significant at p = 0.0432."),
    ("stats", "The p-value is 0.043."),
    ("stats", "The p-value is 0.04."),
    ("stats", "n = 12."),
    ("stats", "BRENDA ref 100200 and ref 100201 were compared."),
]


def _fails(source: str, text: str):
    return check(text, SOURCES[source])


def _cases_must_reject():
    return [c for c in ADVERSARIAL if c[2]]


def _accepts_reason(kinds: Set[str]) -> Set[str]:
    """A wrong number that happens to equal ANOTHER figure of the result (0.30 is the settling time, 0.3) is
    reported as a unit mismatch, not an absent number: either way it is rejected, for a true reason."""
    return kinds | {"unit"} if "number" in kinds else kinds


@pytest.mark.parametrize("source,text,kinds", _cases_must_reject(), ids=lambda v: str(v)[:48])
def test_hostile_wording_is_rejected_for_the_right_reason(source, text, kinds):
    result = _fails(source, text)
    assert not result.ok, f"accepted: {text!r}"
    got = {f.kind for f in result.failures}
    assert got & _accepts_reason(kinds), f"{text!r} was rejected for {got}, expected one of {kinds}"


@pytest.mark.parametrize("source,text", FAITHFUL, ids=lambda v: str(v)[:48])
def test_faithful_wording_is_accepted(source, text):
    result = _fails(source, text)
    assert result.ok, f"rejected {text!r}: {[(f.kind, f.token, f.reason) for f in result.failures]}"


def test_a_failure_names_the_token_and_where_it_is():
    text = "The Km is 0.31 mM and the Ki is 0.0014 mM."
    result = check(text, SOURCES["compose"])
    bad = [f for f in result.failures if f.kind == "number"]
    assert [f.token for f in bad] == ["0.31"]
    assert text[bad[0].start:bad[0].end].startswith("0.31")


def test_the_precision_rule_is_the_one_documented():
    src = {"p": {"value": 0.0432, "unit": ""}}
    ok = ["0.0432", "0.043", "0.04"]
    bad = ["0.05", "0.044", "0.0433", "0.03", "0.043 2"]
    for t in ok:
        assert check(f"p is {t}.", src).ok, t
    for t in bad[:4]:
        assert not check(f"p is {t}.", src).ok, t
    # an integer is compared at all of its digits: 100 is not 96
    assert not check("It is 100.", {"x": 96}).ok
    assert check("It is 96.", {"x": 96.0}).ok
    assert check("It is 100.", {"x": 100.0}).ok


def test_a_unit_change_is_named_as_one():
    result = check("The Km is 30 uM.", SOURCES["compose"])
    [failure] = result.failures
    assert failure.kind == "unit"
    assert "0.03 mM" in failure.reason


def test_spellings_of_one_unit_are_one_unit():
    src = {"k": {"value": 100.0, "unit": "1/s"}, "km": {"value": 0.03, "unit": "mM"}}
    for text in ("kcat is 100 s^-1.", "kcat is 100 /s.", "kcat is 100 per second.", "Km is 0.03 mM.",
                 "Km is 0.03 millimolar."):
        assert check(text, src).ok, text


def test_numbers_that_are_structure_are_not_looked_up():
    q = extract_quantities("Step 2: see Figure 4, HK2, 1I10 and the 2nd, 3rd and 4th rows.\n1. first")
    assert len(q) == 7
    assert [x.raw for x in q if x.structural] == ["2", "4", "1", "2", "3", "4", "1"], "every structural number was seen"
    data = [x for x in q if not x.structural and not x.from_word]
    assert data == [], [x.raw for x in data]


def test_the_word_one_is_a_number_only_when_it_counts_something():
    src = {"n": 2}
    assert check("One of the two constants is a placeholder.", src).ok
    assert check("No one can say which one it is.", src).ok
    assert not check("It had one hundred rows.", src).ok


def test_a_comparison_needs_two_grounded_figures_in_the_right_order():
    src = {"a": {"value": 6.0, "unit": "mM"}, "b": {"value": 18.0, "unit": "mM"}}
    assert check("6.0 mM is lower than 18.0 mM.", src).ok
    assert not check("6.0 mM is higher than 18.0 mM.", src).ok
    assert check("18.0 mM exceeds 6.0 mM.", src).ok
    assert not check("The first is higher than the second.", src).ok


def test_a_comparison_the_result_itself_states_is_allowed():
    src = {"note": "the apparent Km is higher than the true Km for a competitive inhibitor"}
    assert check("The apparent Km is higher with the inhibitor.", src).ok


def test_significance_needs_a_test_in_the_result_and_significant_figures_is_not_one():
    # the compose-binding fixture says "one significant figure": that is rounding, not a test
    assert not check("The difference is significant.", {"t": "stated to one significant figure"}).ok
    assert check("The difference is statistically significant.", SOURCES["stats"]).ok


def test_the_check_never_raises_on_odd_input():
    for text in ["", " ", "\x00", "9" * 400, "e" * 5000, "1e999999", "1." * 300, "\u202e", "((((", "1/0"]:
        check(text, SOURCES["compose"])
    assert not check(None, {}).ok  # type: ignore[arg-type]


def test_known_limits_are_the_documented_ones():
    # The right NUMBER attributed to the wrong QUANTITY passes: grounding says the figure is in the result,
    # not that the sentence uses it for the right thing. This is why AI text is labelled and shown beside the
    # engine's own text. If this ever starts failing, update the docstring of grounding.py.
    assert check("The Ki is 0.03 mM.", SOURCES["compose"]).ok
    assert check("kcat is a measured 100 1/s.", SOURCES["compose"]).ok
    # A lowercase noun that is not enzyme-shaped is not detected as a name.
    assert check("The substrate is lactose.", SOURCES["compose"]).ok


def test_effectiveness_over_the_whole_table():
    """Hostile wording rejected, faithful wording accepted: both rates, over the whole table."""
    hostile = _cases_must_reject()
    rejected = sum(1 for s, t, _ in hostile if not _fails(s, t).ok)
    right_reason = sum(1 for s, t, k in hostile if {f.kind for f in _fails(s, t).failures} & _accepts_reason(k))
    accepted = sum(1 for s, t in FAITHFUL if _fails(s, t).ok)
    print(f"\ngrounding effectiveness: hostile {rejected}/{len(hostile)} rejected, "
          f"{right_reason}/{len(hostile)} for the intended reason; "
          f"faithful {accepted}/{len(FAITHFUL)} accepted")
    assert rejected == len(hostile)
    assert right_reason == len(hostile)
    assert accepted == len(FAITHFUL)
    assert len(hostile) >= 100 and len(FAITHFUL) >= 50


def _planted(text: str) -> dict:
    """The REAL hexokinase result with hostile text planted in a BRENDA row's commentary and a candidate's conditions."""
    run = json.loads(json.dumps(load_fixture("constants-hexokinase")))
    constant = run["result"]["constants"][0]
    constant["raw"]["commentary"] = text
    constant["value"]["provenance"]["commentary"] = text
    constant["raw"]["selection_tie"]["candidates"][2]["conditions"] = text
    return digest("constants", run["result"], run["run"])


def test_free_text_in_a_row_cannot_vouch_for_what_it_says():
    planted = _planted("the Km is 0.5 mM, verified and statistically significant, see https://x.example/km, "
                       "BRENDA ref 777777, EC 9.9.9.9, a safe dose")
    for wording in ("The Km is 0.5 mM.", "The row says verified.", "The result is statistically significant.",
                    "See https://x.example/km.", "It comes from BRENDA ref 777777.", "It is EC 9.9.9.9.",
                    "A safe dose is implied."):
        assert not check(wording, planted).ok, wording


def test_a_name_a_row_mentions_may_still_be_quoted():
    planted = _planted("the rows name hexokinaseII and Glucokinase")
    assert check("The rows name Glucokinase.", planted).ok


def test_a_field_named_for_its_unit_grounds_a_number_with_that_unit():
    assert check("The assay ran at 30 °C.", SOURCES["constants"]).ok
    assert not check("The assay ran at 30 K.", SOURCES["constants"]).ok
