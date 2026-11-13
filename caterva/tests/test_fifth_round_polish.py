"""The fifth round's polish (2026-11-13), the compose half: what the report
and its advice say. Offline: BRENDA's tables are stubbed where they are read.
Each test names the finding it holds to.
"""
from __future__ import annotations

from types import SimpleNamespace

from caterva.compose import __main__ as compose_main
from caterva.compose import defaults, narrowed
from caterva.compose.export import Measurement
from caterva.compose.report import ModelDossier, _passed_over_far
from caterva.enzymes import finder
from caterva.enzymes.isozyme import IsozymeNotice, _subunits_of_one_complex, isozyme_notice


def _m(value, unit, citation, commentary, ph=None, t=None, **kw):
    return Measurement(value=value, unit=unit, citation=citation, commentary=commentary,
                       assay_ph=ph, assay_temperature_c=t, **kw)


# -- R5V1-1, R5B-04, R5V1-20: an unreadable pH is not its units digit --------------------

def test_an_unreadable_ph_is_read_as_its_paired_rows_and_raises_no_false_mismatch():
    measured = {
        "reaction_Ki": _m(2e-07, "mM", "BRENDA ref 648142", "pH 5.0, 37°C, wild-type enzyme", 5.0, 37.0),
        "reaction_Km": _m(0.0152, "mM", "BRENDA ref 648156", "pH 4.u, 0.1 M NaCl", 4.0),
        "reaction_kcat": _m(5.8, "1/s", "BRENDA ref 648156", "pH 4.8, 0.1 M NaCl", 4.8),
    }
    dossier = ModelDossier(query="q", model=SimpleNamespace())
    text = "\n".join(dossier._condition_lines(measured))
    assert "a pH BRENDA prints unreadably ('pH 4.u'), read as pH 4.8 from the same paper's " \
           "`reaction_kcat` row" in text
    assert "measured at pH 4," not in text
    assert "differ by 1 pH unit" not in text
    assert "No two of the 3 constants above differ" in text


# -- R5V1-2: only the rows actually far are listed as far ----------------------------------

def test_only_rows_more_than_threefold_away_are_listed_as_far():
    record = SimpleNamespace(value=1.4e6, resolver_because=(
        "x; of the 9 candidate rows (after the organism, substrate, isoform and variant checks): "
        "4 row(s) not stating both pH and temperature passed over (15200, 16700, 600000, 1.4e+06 1/s)"))
    (said,) = _passed_over_far(record)
    assert said == ("4 row(s) not stating both pH and temperature passed over, 2 of them more than "
                    "3-fold from it (15200, 16700 1/s)")
    near = SimpleNamespace(value=0.052, resolver_because="2 row(s) not stating both pH and "
                                                          "temperature passed over (0.062, 0.067 mM)")
    assert _passed_over_far(near) == []


# -- R5V1-7, S5-07: the example isoform is the lowest-numbered -------------------------------

def test_the_isoform_example_is_the_lowest_numbered_name():
    notice = IsozymeNotice(ec="3.4.21.4", organism="HUMAN", count=5,
                           symbols=("PRSS58", "PRSS1", "PRSS2", "PRSS3", "PRSS3P2"))
    assert "for example --isoform PRSS1)" in notice.remedy


# -- S5-02: the subunits of one complex are not isozymes -------------------------------------

def test_subunits_of_one_complex_are_not_called_isozymes():
    assert _subunits_of_one_complex(("SDHA", "SDHB"))
    assert not _subunits_of_one_complex(("LDHA", "LDHB"))
    assert isozyme_notice("1.3.5.1", "cow") is None


# -- R5V1-05: two proteins' constants are named in the notice --------------------------------

def test_a_km_and_a_kcat_of_two_proteins_are_said_in_the_isozyme_notice():
    notice = IsozymeNotice(ec="1.14.18.1", organism="AGABI", count=4, symbols=(),
                           two_proteins=("C7FF04", "C7FF05"))
    assert "the Km's row names C7FF04 and the kcat's row names C7FF05: two different proteins" \
        in notice.headline
    assert "supply C7FF04's kcat or C7FF05's Km yourself" in notice.remedy


# -- R5V1-3: the advice says which isozymes have a measured pair -----------------------------

def test_the_remedy_says_which_isozymes_have_a_measured_pair():
    notice = IsozymeNotice(ec="2.7.1.1", organism="HUMAN", count=5,
                           symbols=("HKDC1", "HK1", "HK2", "HK3", "GCK"), measured_as="GCK",
                           measured_pairs=("GCK",), substrate="D-glucose")
    assert "only GCK has both a Km and a kcat row naming it for D-glucose" in notice.remedy
    assert "gives no measured pair" in notice.remedy


# -- R5V1-13: a genus is a choice among its species ------------------------------------------

def test_a_genus_chooses_its_best_measured_species(monkeypatch):
    monkeypatch.setattr(compose_main, "_km_organisms_usable", lambda ec: {
        "Streptomyces pseudogriseolus": 8, "Streptomyces albus": 4, "Actinoplanes missouriensis": 22})
    chosen = compose_main._species_of_genus("5.3.1.5", "Streptomyces")
    assert chosen.chosen == "Streptomyces pseudogriseolus"
    assert "Actinoplanes" not in chosen.note()
    assert chosen.note().startswith("Your description names the genus 'Streptomyces', not a species")
    assert compose_main._species_of_genus("5.3.1.5", "Thermus") is None


# -- R5V1-07: a word of an organism's name is not a substrate candidate ----------------------

def test_a_word_of_an_organisms_name_is_not_a_substrate_candidate(monkeypatch):
    monkeypatch.setattr(defaults, "km_organisms", lambda ec, substrate=None: {
        "influenza A virus": 11, "Glycine max": 3})
    kept = compose_main._not_organism_words("3.2.1.18", ("influenza", "glycine", "fetuin"),
                                            {"glycine": 2, "fetuin": 4})
    assert kept == ("glycine", "fetuin")


# -- R5V1-25: a typo is answered with a command that runs ------------------------------------

def test_a_typo_suggestion_gives_a_command_that_runs():
    from caterva.enzymes.policy import NameNotResolved, resolve_enzyme_name

    try:
        resolve_enzyme_name("urokinse", "human")
    except NameNotResolved as exc:
        text = str(exc)
    else:  # pragma: no cover
        raise AssertionError("urokinse resolved")
    assert "<its EC number>" not in text
    assert "--subject 3.4.21.73" in text


# -- R5V1-03: a family name is settled by the organism ---------------------------------------

def test_a_family_name_ambiguity_is_marked_as_one():
    found = finder.resolve("dihydroorotate dehydrogenase", "human")
    assert isinstance(found, finder.Ambiguous) and found.class_word and found.family


# -- R5V1-6, R5B-06: what the evidence-only row was ------------------------------------------

def test_the_evidence_only_row_is_said_to_be_wild_type_or_another_protein():
    assert "a wild-type row, set aside because a mutant was asked for" in narrowed._what_it_was(
        {"conditions": "wild type enzyme, pH 7.5, 37°C"}, {"conditions": "mutant enzyme R132H"})
    assert "another protein" in narrowed._what_it_was(
        {"conditions": "hexokinase I, at 37°C, pH 8.1"}, {"conditions": "-", "isoform": "GCK"})


# -- R5V1-30: a chromogenic peptide is never called natural ----------------------------------

def test_a_chromogenic_assay_substrate_is_recognised():
    assert defaults.is_chromogenic("methoxysuccinyl-Ala-Ala-Pro-Val-4-nitroanilide")
    assert defaults.is_chromogenic("Z-Gly-Pro-Arg-pNA")
    assert not defaults.is_chromogenic("Na+") and not defaults.is_chromogenic("elastin")


# -- R5V1-16: a mutant with no row is said to be the gap -------------------------------------

def test_a_mutant_with_no_row_is_the_gap_not_the_organism(monkeypatch):
    chosen = defaults.Choice("substrate", "CO2", "it has the most rows")

    def choose_substrate(ec, organism, *, needs_kcat=True, strict=False, among=None, isoform=None,
                         mutation=None):
        return None if mutation else chosen

    monkeypatch.setattr(defaults, "choose_substrate", choose_substrate)
    model = SimpleNamespace(ec_number="4.2.1.1", choices=())
    args = SimpleNamespace(organism="Homo sapiens", substrate=None, inhibitor=None, isoform=None,
                           mutation="H64A", organism_unread=None, substrate_unread=None)
    monkeypatch.setattr(compose_main, "_not_named", lambda model, args: (("km", "kcat"), True, False))
    monkeypatch.setattr(compose_main, "compounds_from", lambda args: {})
    monkeypatch.setattr(compose_main, "_organism_has_no_rows", lambda *a, **k: None)
    monkeypatch.setattr(compose_main, "replace", lambda m, **kw: m)
    _, refusal = compose_main._choose_what_was_not_named(model, args)
    assert "measures the mutant H64A" in refusal
    assert "re-run without H64A" in refusal and "Caterva would then use CO2" in refusal
    assert "Re-run with --substrate NAME" not in refusal


# -- XS5-01: the every-organism parse is kept, so an organism is filtered, not reparsed --------

def _name(i: int) -> str:
    return f"Genus species{chr(97 + i % 26)}{chr(97 + i // 26)}"


def test_choosing_among_many_organisms_parses_each_table_once(monkeypatch):
    calls = []

    class Client:
        def fetch_brenda_html(self, ec, timeout=None):
            return "<html>one page</html>"

        def parse_brenda_km_html(self, html, ec, names, organism, require_substrate_match=False):
            calls.append(organism)
            return [SimpleNamespace(substrate="X", organism=_name(i), conditions="",
                                    km_value=1.0, reference_id=str(i)) for i in range(80)]

    client = Client()
    monkeypatch.setattr(defaults, "_client", lambda: client)
    monkeypatch.setattr(defaults, "_assay_effector_keys", lambda ec, html: frozenset())
    defaults._PARSED.clear()
    defaults.table_rows("9.9.9.9", "km", None)
    for i in range(80):
        assert len(defaults.table_rows("9.9.9.9", "km", _name(i))) == 1
    assert calls == [None]


# -- R5B-08: which reaction of the substrate the carried row measured ------------------------

def test_the_reaction_a_row_measured_is_read_from_its_twin_row():
    from caterva.compose.report import _reaction_of

    record = _m(0.089, "mM", "BRENDA ref 706823", "CYP3A4, at pH 7.4 and 37°C", alternatives=(
        {"value": 0.089, "reference_id": "706823",
         "conditions": "CYP3A4, desulfuration by recombinant human CYPs to fenthion-oxon"},
        {"value": 0.131, "reference_id": "706823", "conditions": "CYP3A4, sulfoxidation to fenthion-sulfoxide"}))
    assert _reaction_of(record).group(0) == "desulfuration by recombinant human CYPs to fenthion-oxon"


# -- S5-03: the carried row's own paper is among the spread's sources -----------------------

def test_the_carried_rows_paper_is_one_of_the_spreads_sources():
    record = _m(0.1, "mM", "BRENDA ref 2877", "-", alternatives=(
        {"value": 0.303, "reference_id": "699137", "conditions": "succinate alone, pH 7.4, 25°C"},))
    assert record.spread.references == ("2877", "699137")
    assert record.spread.what.startswith("2 sources report 2 values (BRENDA ref 2877, 699137)")


# -- R5V1-06: a carried row naming the isoform is not said to name none ----------------------

def test_a_carried_row_that_names_the_isoform_is_recognised():
    adult = _m(7.7, "mM", "BRENDA ref 641070", "31°C and pH 7.7, adult glucokinase", row_isoform="HXK4")
    assert narrowed._names(adult, "HXK4")
    assert not narrowed._names(_m(0.05, "mM", "BRENDA ref 640207", "at 30°C, pH 7.5"), "HXK4")


def test_the_reaction_is_read_from_the_page_when_no_ranked_row_carries_it(monkeypatch):
    from caterva.compose.report import _reaction_on_the_page

    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: (
        defaults._Row("fenthion", organism, "CYP3A4, at pH 7.4 and 37°C", 0.089, "706823"),
        defaults._Row("fenthion", organism, "CYP3A4, desulfuration by recombinant human CYPs to "
                      "fenthion-oxon", 0.089, "706823"),
        defaults._Row("fenthion", organism, "CYP3A4, sulfoxidation to fenthion-sulfoxide", 0.131,
                      "706823")))
    model = SimpleNamespace(subject="1.14.14.1", organism="Homo sapiens")
    record = _m(0.089, "mM", "BRENDA ref 706823", "CYP3A4, at pH 7.4 and 37°C")
    assert _reaction_on_the_page(model, record, "km").group(0).startswith("desulfuration")
