"""Which BRENDA row a constant carries: the second adversarial round (2026-11-11).

Every case here is a real BRENDA row set, its cells copied from the live page
on 2026-11-11 (EC, reference and commentary as BRENDA writes them), placed in
a page of BRENDA's own markup so the test runs offline. Each pins a number a
professor would have found wrong, and the rule that now prevents it:

- an apparent Km with an inhibitor in the assay (xanthine oxidase, ref 766313);
- a K0.5 with a Hill coefficient carried as a Michaelis-Menten Km;
- a Km and a kcat "paired" from one paper at different pH, with different
  salts, from rows that cannot be told apart, or at a value 13-fold off the
  constant's own median (acetylcholinesterase, ref 749746);
- constants of an isolated domain, a chimera, a modified enzyme, a cosolvent;
- the minus-K+ control of pyruvate kinase carried as its kcat;
- a glucokinase row carried for HK2 and a CYP3A5 row for CYP2B6, because
  only the commentary was read and BRENDA's UniProt column was not;
- a tight-binding Ki (hirudin, 2.37e-10 mM) flagged implausible;
- a Ki versus 6-mercaptopurine carried over the same paper's Ki versus
  xanthine, because "versus substrate xanthine" was not read as xanthine.
"""
from __future__ import annotations

import pytest

import row_form
from brenda_client import parse_brenda_ki_html
from effector import extract_effectors
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page

TABLE = {"km": "KM Values", "kcat": "Turnover Numbers", "ki": "Ki Values"}


def row(value, compound, organism, commentary, ref, uniprot="-"):
    text = value if isinstance(value, str) else format(value, ".15f").rstrip("0").rstrip(".")
    return [text, compound, organism, uniprot, commentary, ref]


def kw(html, organism):
    return dict(html_provider=lambda ec: html, uniprot_provider=lambda ec, org: None,
                taxon_id_provider={organism: "1"}.get, search_literature=False)


def value(ec, organism, substrate, quantity, html, **extra):
    return resolve_kinetic_value(ec, organism, substrate, quantity=quantity, **kw(html, organism),
                                 **extra)


def pair(ec, organism, substrate, html, **extra):
    return resolve_kinetic_pair(ec, organism, substrate, **kw(html, organism), **extra)


# -- Xanthine oxidase, Bos taurus, xanthine (EC 1.17.3.2) ------------------------

XO_KM = [
    row(0.01208, "xanthine", "Bos taurus", "in the absence of inhibitor, at pH 7.4 and 25°C",
        "766313", "P80457"),
    row(0.01435, "xanthine", "Bos taurus", "in the presence of 0.00025 mM (E)-5-(3-nitrophenyl)"
        "-2-hydroxycyclohepta-2,4,6-trienone , at pH 7.4 and 25°C", "766313", "P80457"),
    row(0.0167, "xanthine", "Bos taurus", "in the presence of 0.0005 mM (E)-5-(3-nitrophenyl)"
        "-2-hydroxycyclohepta-2,4,6-trienone , at pH 7.4 and 25°C", "766313", "P80457"),
    row(0.02014, "xanthine", "Bos taurus", "in the presence of 0.001 mM (E)-5-(3-nitrophenyl)"
        "-2-hydroxycyclohepta-2,4,6-trienone , at pH 7.4 and 25°C", "766313", "P80457"),
    row(0.017, "xanthine", "Bos taurus", "pH 7.4, 37°C", "745461", "P80457"),
    row(0.088, "xanthine", "Bos taurus", "cofactor 2,6-dichlorophenolindophenol", "644648"),
]


class TestAnInhibitorInTheAssayMakesAnApparentConstant:
    def test_a_compound_named_with_a_stereo_descriptor_is_read_as_present(self):
        found = extract_effectors(XO_KM[2][4])
        assert [(e.compound_text, e.presence) for e in found] == [
            ("(E)-5-(3-nitrophenyl)-2-hydroxycyclohepta-2,4,6-trienone", "present")]
        assert [e.compound_text for e in extract_effectors(
            "in presence of 0.5 mM 2,3-dihydroxybenzaldehyde")] == ["2,3-dihydroxybenzaldehyde"]

    def test_the_inhibitor_free_row_of_the_same_paper_is_carried(self):
        """The median of the five rows stating conditions was 0.0167, an
        inhibited assay; the enzyme's own Km is 0.01208."""
        html = page({"KM Values": XO_KM})
        r = value("1.17.3.2", "Bos taurus", "xanthine", "km", html)
        assert (r.value, r.citation.reference_id) == (0.01208, "766313")
        assert "inhibitor or effector present" in r.chosen_because

    def test_a_compound_the_ki_table_lists_is_an_inhibitor_without_a_control_row(self):
        html = page({
            "KM Values": [XO_KM[2], XO_KM[4]],
            "Ki Values": [row(0.0001, "(E)-5-(3-nitrophenyl)-2-hydroxycyclohepta-2,4,6-trienone",
                              "Bos taurus", "pH 7.4, 25°C", "766313")],
        })
        r = value("1.17.3.2", "Bos taurus", "xanthine", "km", html)
        assert r.value == 0.017

    def test_a_pair_never_trades_a_described_row_for_an_undescribed_one(self):
        html = page({"KM Values": XO_KM, "Turnover Numbers": [
            row(5.25, "xanthine", "Bos taurus", "cofactor 2,6-dichlorophenolindophenol", "644648"),
            row(16.2, "xanthine", "Bos taurus", "pH 7.5, 25°C", "393008")]})
        km, kcat = pair("1.17.3.2", "Bos taurus", "xanthine", html)
        assert (km.value, kcat.value) == (0.01208, 16.2)
        assert "chosen independently" in km.chosen_because


# -- K0.5 ---------------------------------------------------------------------------

GCK_K05 = row(6.3, "D-glucose", "Homo sapiens",
              "wild-type, K0.5 value, Hill coefficient 1.8, pH 7.6, 25 °C", "739603", "P35557")


class TestAK05IsNotAMichaelisConstant:
    def test_read(self):
        assert row_form.half_saturation(GCK_K05[4]) == "a K0.5 with a Hill coefficient of 1.8"
        assert row_form.half_saturation("S0.5 value, pH 7") is not None
        assert row_form.half_saturation("pH 7.5, 25°C, wild-type") is None

    def test_a_true_km_is_carried_before_a_k05(self):
        html = page({"KM Values": [GCK_K05, row(6.0, "D-glucose", "Homo sapiens",
                                                "30°C, pH 7.5, wild-type", "641068")]})
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "km", html)
        assert r.value == 6.0 and "K0.5 / Hill" in r.chosen_because

    def test_a_k05_carried_alone_says_so_and_names_its_isozyme(self):
        html = page({"KM Values": [GCK_K05]})
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "km", html)
        assert r.value == 6.3
        assert any("K0.5 with a Hill coefficient of 1.8" in n for n in r.row_notes)
        assert any("(P35557) is GCK" in n for n in r.row_notes)


# -- Pairing a Km with a kcat --------------------------------------------------------


class TestAPairIsOneMeasurementOrNoPair:
    def test_rows_of_one_paper_at_different_ph_are_not_a_pair(self):
        """Fumarase, ref 771047: the Km at pH 9.0 was paired with the kcat at
        pH 6.5; the paper's matched pH 7.0 and pH 7.5 rows were passed over."""
        km = [row(v, "fumarate", "Homo sapiens", f"at pH {ph} and 25°C", "771047", "P07954")
              for v, ph in ((0.31, "9.0"), (0.27, "7.0"), (0.37, "7.5"), (0.12, "6.5"))]
        kcat = [row(v, "fumarate", "Homo sapiens", f"at pH {ph} and 25°C", "771047", "P07954")
                for v, ph in ((175, "6.5"), (202, "7.0"), (370, "7.5"))]
        k, c = pair("4.2.1.2", "Homo sapiens", "fumarate",
                    page({"KM Values": km, "Turnover Numbers": kcat}))
        assert k.assay_ph == c.assay_ph
        assert (k.value, c.value) in {(0.27, 202), (0.37, 370), (0.12, 175)}
        assert "one measurement" in k.chosen_because

    def test_a_pair_is_not_taken_ten_fold_off_the_constants_own_median(self):
        """Human AChE: the Km paper's one kcat row, 7.18 1/s, was carried
        over the wild-type 93 1/s; 6500 is a third paper's."""
        km = [row(0.11, "acetylthiocholine", "Homo sapiens", "recombinant enzyme, pH 8.0, 22°C",
                  "749746", "P22303"),
              row(0.086, "acetylthiocholine", "Homo sapiens", "wild-type, pH 8, 25°C", "775647")]
        kcat = [row(7.18, "acetylthiocholine", "Homo sapiens", "recombinant enzyme, pH 8.0, 22°C",
                    "749746", "P22303"),
                row(93, "acetylthiocholine", "Homo sapiens", "wild-type, pH 8, 25°C", "775647"),
                row(6500, "acetyl thiocholine", "Homo sapiens", "pH 8, 27°C", "649716")]
        k, c = pair("3.1.1.7", "Homo sapiens", "acetylthiocholine",
                    page({"KM Values": km, "Turnover Numbers": kcat}))
        assert (k.value, c.value) == (0.086, 93)

    def test_the_salt_of_the_km_row_is_the_salt_of_the_kcat_row(self):
        """Thrombin, ref 709074: Km of the Na+-bound fast form (NaCl) was
        paired with the Na+-free slow form's kcat (choline chloride)."""
        base = "wild type enzyme, in 5 mM Tris, 0.1% (w/v) PEG 8000, pH 8.0, 25°C, 200 mM "
        sub = "D-Phe-Pro-Arg-4-nitroanilide"
        km = [row(0.00033, sub, "Homo sapiens", base + "NaCl", "709074"),
              row(0.00088, sub, "Homo sapiens", base + "choline chloride", "709074")]
        kcat = [row(29, sub, "Homo sapiens", base + "NaCl", "709074"),
                row(3.5, sub, "Homo sapiens", base + "choline chloride", "709074")]
        k, c = pair("3.4.21.5", "Homo sapiens", sub, page({"KM Values": km, "Turnover Numbers": kcat}))
        assert (k.value, c.value) == (0.00033, 29)
        assert not any("PEG" in n for n in k.row_notes)

    def test_rows_that_cannot_be_told_apart_are_not_a_pair_and_it_is_said(self):
        """TEM-1 and ampicillin, ref 734041: seven Km and seven kcat rows with
        one commentary and one accession list."""
        same = "pH 7.2, 25°C, recombinant enzyme"
        acc = "I3VKD5,H6WZS9"
        km = [row(v, "ampicillin", "Escherichia coli", same, "734041", acc)
              for v in (0.156, 0.207, 0.229, 0.258, 0.305)]
        kcat = [row(v, "ampicillin", "Escherichia coli", same, "734041", acc)
                for v in (273, 408, 477, 724, 900)]
        k, c = pair("3.5.2.6", "Escherichia coli", "ampicillin",
                    page({"KM Values": km, "Turnover Numbers": kcat}))
        assert "cannot be told" in k.chosen_because and "cannot be told" in c.chosen_because
        assert "one measurement" not in k.chosen_because


# -- Constructs and preparations -------------------------------------------------------


class TestConstructsAreSetAsideAndNamed:
    @pytest.mark.parametrize("commentary, what", [
        ("pH 8.0, 37°C, C-domain, hydrolysis of o-aminobenzoyl-FRK-(dinitrophenyl)-P-OH",
         "an isolated domain"),
        ("37°C, pH 8.3, chimeric enzyme C1163Ndom-ACE", "a chimeric construct"),
        ("benzoate-modified enzyme, pH 5.1, 37°C", "a chemically modified enzyme"),
        ("in presence of 20% methanol", "an assay with a cosolvent or denaturant added"),
        ("immobilized enzyme, pH 7.5, 25°C", "an immobilised enzyme"),
        ("37°C, pH 4.7, HIV-1 subtype C protease", "a named subtype or variant of the enzyme"),
        # Bovine trypsin and BAEE, ref 668032, beside its "wild-type" row
        # (review of the second round, 2026-11-12).
        ("enzyme with O-carboxymethyl-poly-beta-cyclodextrin attached to surface, pH 8.0, 25°C",
         "a chemically modified enzyme"),
        ("enzyme conjugated to gold nanoparticles, pH 7.0", "a chemically modified enzyme"),
        # Triosephosphate isomerase, T. brucei, ref 682787, beside its
        # "wild-type, pH 7.4, 25°C" pair (review of the second round).
        ("in complex with monomer from Trypanosoma cruzi, pH 7.4, 25°C",
         "a hybrid enzyme (subunits of two proteins)"),
        ("in complex with mutant C15A of Trypanosoma cruzi enzyme, pH 7.4, 25°C",
         "a hybrid enzyme (subunits of two proteins)"),
    ])
    def test_read(self, commentary, what):
        assert row_form.construct_of(commentary).startswith(what)

    @pytest.mark.parametrize("commentary", [
        "without addition of methanol", "tACE, 37°C, pH 8.3", "pH 8, 0.1% (w/v) PEG 8000",
        "wild-type enzyme, pH 7.5", "coupled assay with lactate dehydrogenase, pH 7.5",
        "substrate: conjugated bile acid, pH 7.0", "bile acids conjugated to taurine, pH 7.0",
        "in complex with calmodulin, pH 7.5", "enzyme in complex with NADH, 25°C"])
    def test_not_a_construct(self, commentary):
        assert row_form.construct_of(commentary) is None

    def test_ace_captopril_ki_is_the_full_enzymes(self):
        ki = [row(0.000016, "captopril", "Homo sapiens", "pH 8.0, 37°C, C-domain, hydrolysis of "
                  "o-aminobenzoyl-FRK-(dinitrophenyl)-P-OH", "650001"),
              row(0.0000005, "captopril", "Homo sapiens", "pH 8.0, 37°C, N-domain", "650001"),
              row(0.00001, "captopril", "Homo sapiens", "pH 8.0, 37°C, wild-type enzyme",
                  "650001")]
        r = value("3.4.15.1", "Homo sapiens", "captopril", "ki", page({"Ki Values": ki}))
        assert r.value == 0.00001

    def test_a_construct_carried_because_nothing_else_exists_is_named(self):
        kcat = [row(15.1, "hippuryl-His-Leu", "Homo sapiens",
                    "37°C, pH 8.3, chimeric enzyme C1163Ndom-ACE", "678511", "P12821")]
        r = value("3.4.15.1", "Homo sapiens", "hippuryl-His-Leu", "kcat",
                  page({"Turnover Numbers": kcat}))
        assert r.value == 15.1 and any("chimeric" in n for n in r.row_notes)

    def test_an_interspecies_heterodimer_is_passed_over_for_the_wild_type_pair(self):
        """Triosephosphate isomerase, T. brucei, D-glyceraldehyde 3-phosphate
        (live, 2026-11-12): Km 0.31 mM and kcat 5000 1/s were carried, the
        rows "in complex with monomer from Trypanosoma cruzi"; the same
        paper's wild-type pair is 0.46 mM and 5170 1/s."""
        s, org = "D-glyceraldehyde 3-phosphate", "Trypanosoma brucei"
        km = [row(0.31, s, org, "in complex with monomer from Trypanosoma cruzi, pH 7.4, 25°C",
                  "682787"),
              row(0.28, s, org, "in complex with mutant C15A of Trypanosoma cruzi enzyme, pH 7.4, "
                  "25°C", "682787"),
              row(0.46, s, org, "wild-type, pH 7.4, 25°C", "682787"),
              row(0.38, s, org, "wild-type, 25°C, pH 7.4", "690940")]
        kcat = [row(5000, s, org, "in complex with monomer from Trypanosoma cruzi, pH 7.4, 25°C",
                    "682787"),
                row(2170, s, org, "in complex with mutant C15A of Trypanosoma cruzi enzyme, pH "
                    "7.4, 25°C", "682787"),
                row(5170, s, org, "wild-type, pH 7.4, 25°C", "682787"),
                row(4183, s, org, "wild-type, 25°C, pH 7.4", "690940")]
        k, c = pair("5.3.1.1", org, s, page({"KM Values": km, "Turnover Numbers": kcat}))
        assert (k.value, c.value) in {(0.46, 5170), (0.38, 4183)}
        assert not any("hybrid" in n for n in k.row_notes + c.row_notes)

    def test_a_cosolvent_row_is_passed_over_for_its_control(self):
        km = [row(0.0096, "Nalpha-benzoyl-L-arginine ethyl ester", "Bos taurus",
                  "in presence of 20% methanol, pH 8, 25°C", "95437"),
              row(0.0012, "Nalpha-benzoyl-L-arginine ethyl ester", "Bos taurus",
                  "without addition of methanol, pH 8, 25°C", "95437")]
        r = value("3.4.21.4", "Bos taurus", "Nalpha-benzoyl-L-arginine ethyl ester", "km",
                  page({"KM Values": km}))
        assert r.value == 0.0012


# -- Activating ions ---------------------------------------------------------------------


class TestAnEssentialActivatorIsNotAnAddition:
    def test_pyruvate_kinase_kcat_is_the_row_with_k_plus(self):
        kcat = [row(3.2, "phosphoenolpyruvate", "Homo sapiens",
                    "wild type enzyme, in the absence of K+, pH 7.5, 25°C", "674499"),
                row(1182, "phosphoenolpyruvate", "Homo sapiens",
                    "wild type enzyme, in the presence of K+, pH 7.5, 25°C", "674499")]
        r = value("2.7.1.40", "Homo sapiens", "phosphoenolpyruvate", "kcat",
                  page({"Turnover Numbers": kcat}))
        assert r.value == 1182 and "minus-activator control" in r.chosen_because

    @pytest.mark.parametrize("ion", ["K+", "Mg2+", "NaCl", "MgCl2", "(NH4)2SO4", "Zn2+"])
    def test_ions(self, ion):
        assert row_form.is_ion(ion)

    @pytest.mark.parametrize("compound", ["NADH", "ATP", "timolol", "Tris"])
    def test_not_ions(self, compound):
        assert not row_form.is_ion(compound)


# -- Isoform from the UniProt column ---------------------------------------------------------


class TestTheUniprotColumnSaysWhichIsozyme:
    def test_accessions_are_read_as_the_index_names_them(self):
        assert row_form.isoforms_of_accessions("2.7.1.1", "P35557") == ("GCK",)
        assert row_form.isoforms_of_accessions("1.14.14.1", "P20815,Q9HB55") == ("CYP3A5", "CYP3A43")
        assert row_form.isoforms_of_accessions("2.7.1.1", "Z9ZZZ9") == ()

    def test_hk2_never_carries_a_glucokinase_kcat(self):
        """'HK2 with glucose' carried 60.4 1/s, ref 703624, whose accession
        is P35557 (glucokinase), as 'naming no isoform'."""
        kcat = [row(60.4, "D-glucose", "Homo sapiens",
                    "wild type enzyme, in 25 mM HEPES (pH 7.4), at 37°C", "703624", "P35557")]
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "kcat", page({"Turnover Numbers": kcat}),
                  isoform="HK2")
        assert not r.found and r.source == "isoform_withheld" and r.isoforms_available == ["GCK"]

    def test_a_row_whose_accession_is_the_isoform_counts_as_naming_it(self):
        kcat = [row(60.4, "D-glucose", "Homo sapiens", "wild type enzyme, pH 7.4, 37°C",
                    "703624", "P35557"),
                row(20.0, "D-glucose", "Homo sapiens", "pH 7.4, 37°C", "700002", "P52789"),
                row(40.0, "D-glucose", "Homo sapiens", "pH 7.4, 37°C", "700003")]
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "kcat", page({"Turnover Numbers": kcat}),
                  isoform="HK2")
        assert r.value == 20.0

    def test_a_row_naming_none_is_its_papers_isoform(self):
        """Ref 722237's "67.6 | D-glucose | Homo sapiens | - | wild-type,
        37°C" names no isoform, and was carried as HK1's and HK2's kcat; the
        page's synonyms give that paper "hGK" and "glucokinase" (review of
        the second round, 2026-11-12)."""
        kcat = [row(67.6, "D-glucose", "Homo sapiens",
                    "wild-type, 37°C, pH not specified in the puclication", "722237")]
        synonyms = [["hGK", "Homo sapiens", "-", "-", "722237"],
                    ["glucokinase", "Homo sapiens", "-", "-", "672225 , 702116 , 722237"]]
        html = page({"Turnover Numbers": kcat, "Synonyms": synonyms})
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "kcat", html, isoform="HK2")
        assert not r.found and r.source == "isoform_withheld" and r.isoforms_available == ["GCK"]
        unasked = value("2.7.1.1", "Homo sapiens", "D-glucose", "kcat", html)
        assert unasked.row_isoform == "GCK"
        assert any("its paper (BRENDA ref 722237) names only GCK" in n for n in unasked.row_notes)

    def test_a_paper_naming_two_isoforms_names_none(self):
        kcat = [row(67.6, "D-glucose", "Homo sapiens", "wild-type, 37°C", "722237")]
        synonyms = [["glucokinase", "Homo sapiens", "-", "-", "722237"],
                    ["hexokinase II", "Homo sapiens", "-", "-", "722237"]]
        html = page({"Turnover Numbers": kcat, "Synonyms": synonyms})
        r = value("2.7.1.1", "Homo sapiens", "D-glucose", "kcat", html, isoform="HK2")
        assert r.found and r.value == 67.6 and r.row_isoform is None

    def test_a_paper_naming_only_other_isoforms_is_theirs(self):
        """"beta lactamase TEM-1 with ampicillin" in E. coli (live,
        2026-11-12): no ampicillin row of EC 3.5.2.6 names TEM-1. Ref
        775641's synonyms say NDM-4, ref 771150's CTX-M-15 (which the isoform
        reader did not read), and ref 734041's seven indistinguishable rows
        belong to a paper naming only NDM variants; each was carried in turn
        as a TEM-1 row "naming no isoform"."""
        km = [row(0.03172, "ampicillin", "Escherichia coli", "pH 7.5, 25°C, wild-type enzyme",
                  "771150"),
              row(0.127, "ampicillin", "Escherichia coli", "pH 7.5, 25°C, wild-type enzyme",
                  "775641"),
              # Its own cell lists seven accessions the enzyme index does not
              # file under EC 3.5.2.6, which say nothing; its paper does.
              row(0.207, "ampicillin", "Escherichia coli", "pH 7.2, 25°C, recombinant enzyme",
                  "734041", "I3VKD5 , H6WZS9 , A0A0F6N6D4")]
        synonyms = [["CTX-M-15", "Escherichia coli", "-", "-", "771150"],
                    ["NDM-4", "Escherichia coli", "-", "-", "775641 , 734041"],
                    ["NDM-12", "Escherichia coli", "-", "-", "734041"]]
        html = page({"KM Values": km, "Synonyms": synonyms})
        r = value("3.5.2.6", "Escherichia coli", "ampicillin", "km", html, isoform="TEM-1")
        assert not r.found and r.source == "isoform_withheld"
        assert set(r.isoforms_available) >= {"CTX-M-15", "NDM-4"}
        ctx = value("3.5.2.6", "Escherichia coli", "ampicillin", "km", html, isoform="CTX-M-15")
        assert ctx.found and ctx.value == 0.03172
        # A request for one NDM variant: ref 734041 names it among others,
        # so its row names none of them, as a cell listing several does.
        ndm = value("3.5.2.6", "Escherichia coli", "ampicillin", "km", html, isoform="NDM-12")
        assert ndm.found and ndm.value == 0.207 and ndm.row_isoform is None

    def test_a_mutant_naming_the_isoform_does_not_shut_out_wild_type_rows(self):
        """PKM2's kcat was refused as "every row measured a variant": the one
        row whose cell names PKM (P14618) is the mutant PKM2 G415R, and ref
        674499's wild-type rows name no isoform."""
        kcat = [row(0.57, "phosphoenolpyruvate", "Homo sapiens", "mutant PKM2G415R, pH 7.6, 37°C",
                    "760578", "P14618"),
                row(1182, "phosphoenolpyruvate", "Homo sapiens",
                    "wild type enzyme, in the presence of K+, in 50 mM Mes-Tris, pH 6.0, at 25°C",
                    "674499")]
        r = value("2.7.1.40", "Homo sapiens", "phosphoenolpyruvate", "kcat",
                  page({"Turnover Numbers": kcat}), isoform="PKM2")
        assert r.found and r.value == 1182

    def test_cyp2b6_never_carries_a_cyp3a5_ki(self):
        ki = [row(0.004, "erdafitinib", "Homo sapiens", "substrate rivaroxaban, pH 7.4, 37°C",
                  "764467", "P20815 , Q9HB55")]
        r = value("1.14.14.1", "Homo sapiens", "erdafitinib", "ki", page({"Ki Values": ki}),
                  isoform="CYP2B6")
        assert not r.found and r.source == "isoform_withheld"

    def test_a_fallback_accession_is_not_the_rows_statement(self):
        kcat = [row(60.4, "D-glucose", "Homo sapiens", "pH 7.4, 37°C", "703624")]
        html = page({"Turnover Numbers": kcat})
        r = resolve_kinetic_value("2.7.1.1", "Homo sapiens", "D-glucose", quantity="kcat",
                                  html_provider=lambda ec: html,
                                  uniprot_provider=lambda ec, org: "P35557",
                                  taxon_id_provider={"Homo sapiens": "1"}.get,
                                  search_literature=False, isoform="HK2")
        assert r.found and r.value == 60.4


# -- Ki ---------------------------------------------------------------------------------------


class TestKi:
    def test_a_tight_binding_ki_is_a_ki(self):
        ki = [row("0.000000000237", "Hirudin", "Homo sapiens", "pH 8.0, 37°C", "652618")]
        html = page({"Ki Values": ki})
        assert [e.flagged for e in parse_brenda_ki_html(html, "3.4.21.5", ["hirudin"],
                                                         "Homo sapiens")] == [False]
        r = value("3.4.21.5", "Homo sapiens", "hirudin", "ki", html)
        assert r.found and r.value == pytest.approx(2.37e-10)

    def test_versus_substrate_x_is_versus_x(self):
        from caterva.bind.core import read_mode
        assert read_mode("pH 7.4, noncompetitive versus substrate xanthine") == (
            "noncompetitive", "xanthine")

    def test_the_ki_against_the_models_substrate_is_carried(self):
        ki = [row(0.00098, "2-amino-6-hydroxy-8-mercaptopurine", "Bos taurus",
                  "pH 7.4, noncompetitive versus substrate 6-mercaptopurine", "685804"),
              row(0.00624, "2-amino-6-hydroxy-8-mercaptopurine", "Bos taurus",
                  "pH 7.4, noncompetitive versus substrate xanthine", "685804")]
        r = value("1.17.3.2", "Bos taurus", "2-amino-6-hydroxy-8-mercaptopurine", "ki",
                  page({"Ki Values": ki}), inhibition_mode="noncompetitive",
                  model_substrate="xanthine")
        assert r.value == 0.00624

    def test_a_virus_is_not_an_isoform(self):
        from caterva.bind.core import read_isoform
        assert read_isoform("37°C, pH 4.7, HIV-1 subtype C protease") is None


# -- A mutant asked for ----------------------------------------------------------------------

IDH_KM = [
    row(0.042, "isocitrate", "Homo sapiens", "wild type enzyme, in Bis-Tris, pH 6.2, 37°C",
        "760535", "O75874"),
    row(1.5, "isocitrate", "Homo sapiens", "mutant enzyme R132H, pH 7.5 and 37°C", "760535",
        "O75874"),
]


class TestAMutantAskedForUsesTheMutantsRowsOrNone:
    def test_the_mutants_row_is_carried(self):
        r = value("1.1.1.42", "Homo sapiens", "isocitrate", "km", page({"KM Values": IDH_KM}),
                  mutation="R132H")
        assert r.value == 1.5

    def test_no_mutant_row_is_a_placeholder_never_the_wild_type(self):
        r = value("1.1.1.42", "Homo sapiens", "isocitrate", "km", page({"KM Values": IDH_KM[:1]}),
                  mutation="R132H")
        assert not r.found and r.source == "mutant_not_found"
        from caterva.agents.adapters import to_parameter_source
        source, reason = to_parameter_source("Km", r)
        assert source is None and "R132H" in reason and "wild-type" in reason

    def test_without_a_mutation_the_wild_type_is_carried(self):
        r = value("1.1.1.42", "Homo sapiens", "isocitrate", "km", page({"KM Values": IDH_KM}))
        assert r.value == 0.042


# -- Labels ------------------------------------------------------------------------------------


class TestLabels:
    def test_a_plasmid_enzyme_is_not_given_k12_isozymes(self):
        from caterva.enzymes.isozyme import isozyme_notice
        notice = isozyme_notice("3.5.2.6", "Escherichia coli", "TEM-1", unstated=["reaction_Ki"])
        assert notice is not None and not notice.isoform_listed
        assert "not in that reference proteome" in notice.detail
        assert "which is 2" not in notice.detail

    def test_a_listed_isoform_keeps_the_ordinary_notice(self):
        from caterva.enzymes.isozyme import isozyme_notice
        notice = isozyme_notice("2.7.1.1", "Homo sapiens", "HK2", unstated=["reaction_kcat"])
        assert notice.isoform_listed and "HKDC1, HK1, HK2, HK3, GCK" in notice.detail

    def test_spellings_differing_only_by_a_space_are_one_compound(self):
        from caterva.compose.defaults import _key, is_cofactor
        assert _key("acetyl thiocholine") == _key("Acetylthiocholine")
        assert is_cofactor("coenzyme A") and is_cofactor("Mg2+") and not is_cofactor("D-glucose")


class TestABareCompoundAtAConcentrationIsAnAddition:
    def test_hydroxyurea_listed_in_the_ki_table_is_an_inhibitor_in_the_assay(self):
        """Human CA I and 4-nitrophenyl acetate, ref 650526: 15.3 mM "hCA I,
        25 mM hydroxyurea" was carried beside the plain "hCA I" 15.4 mM."""
        sub = "4-nitrophenyl acetate"
        html = page({
            "KM Values": [row(15.3, sub, "Homo sapiens", "pH 7.8, 25°C, hCA I, 25 mM hydroxyurea",
                              "650526"),
                          row(15.4, sub, "Homo sapiens", "pH 7.8, 25°C, hCA I", "650526"),
                          row(3.025, sub, "Homo sapiens", "pH 7.8, 25°C, hCA I", "700009")],
            "Ki Values": [row(0.5, "hydroxyurea", "Homo sapiens", "pH 7.8, 25°C", "650526")],
        })
        r = value("4.2.1.1", "Homo sapiens", sub, "km", html)
        assert r.value == 3.025 and "hydroxyurea" in r.chosen_because


# -- Resumed round: one isozyme per pair, pairs as described as their picks,
#    assay temperature, fusion constructs, and what the report is told ---------------------


class TestAPairIsOneIsozymes:
    def test_hk1s_km_is_not_put_beside_glucokinases_kcat(self):
        """Human hexokinase and D-glucose carried HK-I's Km (0.06 mM, ref
        640237, "hexokinase I") with glucokinase's kcat (60.4 1/s, ref 703624,
        UniProt P35557). Every kcat row is glucokinase's, so the Km is taken
        from glucokinase's rows, and the K0.5 it is says so."""
        html = page({
            "KM Values": [
                row(0.06, "D-glucose", "Homo sapiens", "hexokinase I, pH 7.5, 30°C", "640237"),
                GCK_K05],
            "Turnover Numbers": [
                row(60.4, "D-glucose", "Homo sapiens",
                    "wild type enzyme, in 25 mM HEPES (pH 7.4), at 37°C", "703624", "P35557"),
                row(40.1, "D-glucose", "Homo sapiens", "wild-type, pH 7.6, 25 °C", "739603",
                    "P35557")],
        })
        km, kcat = pair("2.7.1.1", "Homo sapiens", "D-glucose", html)
        assert km.row_isoform == kcat.row_isoform == "GCK"
        assert (km.value, kcat.value) == (6.3, 40.1)
        assert "K0.5 with a Hill coefficient of 1.8" in km.chosen_because
        assert "measured HK-I" in km.chosen_because


class TestAPairIsAsDescribedAsItsLessDescribedPick:
    def test_one_papers_undescribed_pair_beats_two_papers_when_a_pick_is_undescribed(self):
        """Mouse hexokinase: Km 0.42 (ref 758915, Hk2, no pH or temperature)
        was carried with another paper's kcat 53.2 (ref 674800), though ref
        758915 gives kcat 93.39 for the same protein, stated alike."""
        nothing = "pH and temperature not specified in the publication"
        html = page({
            "KM Values": [row(0.42, "D-glucose", "Mus musculus", nothing, "758915", "O08528")],
            "Turnover Numbers": [
                row(53.2, "D-glucose", "Mus musculus", "37°C, pH 7.4, wild-type enzyme", "674800"),
                row(93.39, "D-glucose", "Mus musculus", nothing, "758915", "O08528")],
        })
        km, kcat = pair("2.7.1.1", "Mus musculus", "D-glucose", html)
        assert (km.value, kcat.value) == (0.42, 93.39)
        assert "one measurement" in kcat.chosen_because


class TestATemperatureSeriesPairsAtAnAssayTemperature:
    def test_trypsin_bapna_is_paired_at_25_not_15(self):
        """Bovine trypsin and BAPNA, ref 678548, at 5, 15, 25 and 35 °C: the
        medians fell on Km at 25 °C and kcat at 15 °C, and the 15 °C pair was
        carried as the nearer."""
        s = "benzoyl-L-arginine-p-nitroanilide"
        km_rows = [(0.2, 5), (0.26, 25), (0.27, 15), (0.44, 35)]
        kcat_rows = [(0.3, 5), (0.76, 15), (0.94, 25), (2.43, 35)]
        html = page({
            "KM Values": [row(v, s, "Bos taurus", f"at {t}°C", "678548") for v, t in km_rows],
            "Turnover Numbers": [row(v, s, "Bos taurus", f"at {t}°C", "678548")
                                 for v, t in kcat_rows],
        })
        km, kcat = pair("3.4.21.4", "Bos taurus", s, html)
        assert (km.value, kcat.value) == (0.26, 0.94)


class TestAFusionForSurfaceDisplayIsAConstruct:
    def test_read(self):
        assert row_form.construct_of(
            "recombinant wild-type enzyme in fusion with Aga2, pH 5.5, 25°C").startswith(
            "a fusion construct")

    def test_the_native_recombinant_pair_is_carried(self):
        """Glucose oxidase, A. niger, beta-D-glucose: the yeast-surface-displayed
        Aga2 fusion (ref 743744) was carried over the soluble enzyme's rows."""
        s = "beta-D-glucose"
        aga2 = "recombinant wild-type enzyme in fusion with Aga2, pH 5.5, 25°C"
        soluble = "recombinant wild-type enzyme expressed in Saccharomyces cerevisiae, pH 5.5, 25°C"
        html = page({
            "KM Values": [row(33.4, s, "Aspergillus niger", aga2, "743744"),
                          row(22.0, s, "Aspergillus niger", soluble, "743277")],
            "Turnover Numbers": [row(33.3, s, "Aspergillus niger", aga2, "743744"),
                                 row(54.8, s, "Aspergillus niger", soluble, "743277")],
        })
        km, kcat = pair("1.1.3.4", "Aspergillus niger", s, html)
        assert (km.value, kcat.value) == (22.0, 54.8)
        assert "fusion construct" in km.chosen_because


class TestTheReportIsToldWhatTheRowIs:
    def test_a_mutant_row_carried_says_it_is_a_mutants(self):
        r = value("1.1.1.42", "Homo sapiens", "isocitrate", "km", page({"KM Values": IDH_KM}),
                  mutation="R132H")
        assert r.row_isoform == "IDH1"
        assert any("mutant enzyme ('R132H')" in n for n in r.row_notes)

    def test_the_row_isoform_reaches_the_measurement(self):
        from caterva.agents.adapters import to_parameter_source
        r = value("1.1.1.42", "Homo sapiens", "isocitrate", "km", page({"KM Values": IDH_KM}),
                  mutation="R132H")
        source, _ = to_parameter_source("Km", r)
        assert source.row_isoform == "IDH1"
        assert any(row_dict.get("isoform") == "IDH1" for row_dict in r.pairable)

    def test_a_row_naming_idh1_by_accession_is_not_said_to_name_no_isoform(self):
        from caterva.compose.row_scope import read_scope
        scope = read_scope("mutant enzyme R132H, at pH 7.5 and 21°C", table="km",
                           isoform="IDH1", row_isoform="IDH1")
        assert scope.isoform == "IDH1" and scope.concerns == ()
        # Without an isoform asked for, the isozyme the accession names is said.
        scope = read_scope("wild-type, pH 7.6, 25 °C", table="km", row_isoform="GCK")
        assert "isoform GCK" in scope.concerns[0].text

    def test_the_resolvers_reason_survives_being_carried(self):
        """compose carried the resolver's row with only "the resolver's row
        for this model": the K0.5, the Hill coefficient and GCK were lost."""
        from caterva.compose.export import Measurement
        from caterva.compose.narrowed import carry, evidence_view
        answer = Measurement(6.3, "mM", "BRENDA ref 739603", organism="Homo sapiens",
                             commentary=GCK_K05[4],
                             resolver_because="what the carried row is: the row is a K0.5")
        other = {"value": 0.06, "unit": "mM", "reference_id": "640237",
                 "conditions": "hexokinase I, pH 7.5, 30°C"}
        narrowed = evidence_view({"reaction_Km": answer}, {"reaction_Km": (other,)})
        measured, _, _ = carry({"reaction_Km": narrowed.measured["reaction_Km"]}, {}, narrowed,
                               {}, None)
        assert measured["reaction_Km"].chosen_because.endswith(
            "what the carried row is: the row is a K0.5")


class TestConstantsOfTwoVariantsAreSaidToBe:
    def test_hiv_subtype_c_km_beside_a_lai_ki(self):
        from caterva.compose.row_scope import variant_mix
        said = variant_mix({
            "reaction_Km": "37°C, pH 4.7, HIV-1 subtype C protease",
            "reaction_kcat": "37°C, pH 4.7, HIV-1 subtype C protease",
            "reaction_Ki": "pH 4.7, 37°C, recombinant LAI wild-type enzyme"})
        assert said.startswith("the constants' rows are not all of one variant")
        assert "`reaction_Km`, `reaction_kcat` measured subtype C" in said
        assert "`reaction_Ki` names no subtype" in said
        assert variant_mix({"reaction_Km": "subtype C", "reaction_kcat": "HIV-1 subtype C"}) is None
        assert variant_mix({"reaction_Km": "pH 7", "reaction_kcat": "pH 7"}) is None


class TestTheOneProteinOfAnEcIsNotAnIsoform:
    def test_ache_is_the_enzyme_not_an_isoform_of_it(self):
        """Human EC 3.1.1.7 is one protein (ACHE, P22303); its row was reported
        as "the row measured isoform ACHE; if the enzyme you mean is another
        isoform ...". An accession names an isoform only among several."""
        km = [row(0.086, "acetylthiocholine", "Homo sapiens", "wild-type, pH 8, 25°C", "775647",
                  "P22303")]
        r = value("3.1.1.7", "Homo sapiens", "acetylthiocholine", "km", page({"KM Values": km}))
        assert r.found and r.row_isoform is None
        assert not any("UniProt accession" in n for n in r.row_notes)


class TestAK05IsSaidWhereverItIsCarried:
    def test_the_rows_own_words_say_k05_in_the_report(self):
        """`--isoform GCK` carries the glucokinase row through compose's own
        isoform selection, whose reason replaced the resolver's: the K0.5 is
        read off the row by row_scope, on every path."""
        from caterva.compose.row_scope import HALF_SATURATION, read_scope
        scope = read_scope(GCK_K05[4], table="km", isoform="GCK", row_isoform="GCK")
        assert [c.kind for c in scope.concerns] == [HALF_SATURATION]
        assert "a K0.5 with a Hill coefficient of 1.8" in scope.concerns[0].text
        assert read_scope(GCK_K05[4], table="kcat") is None or not any(
            c.kind == HALF_SATURATION for c in read_scope(GCK_K05[4], table="kcat").concerns)
