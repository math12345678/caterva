"""The sixth adversarial round of the real-values work (2026-11-13), the
names half that lives in the literature layer: a drug under its INN, its
development code or its usual abbreviation is the compound BRENDA files
under a research name or a full chemical name (`compound_names.ALIASES`,
the one curated table of such names). Offline.

Each Ki was a placeholder that said BRENDA had no row for the drug, and
listed the same compound under its other name as "another inhibitor":
forodesine (immucillin-H, PNP), nor-NOHA (Nomega-hydroxy-nor-L-arginine,
arginase), terbinafine (its systematic name, squalene epoxidase).
"""
from __future__ import annotations

import pytest

from compound_names import identity_key, same_compound

TERBINAFINE_AS_FILED = ("(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine "
                        "hydrochloride")


@pytest.mark.parametrize("typed, filed", [
    ("forodesine", "immucillin-H"),
    ("BCX-1777", "immucillin-H"),
    ("ulodesine", "DADMe-immucillin-H"),
    ("nor-NOHA", "Nomega-hydroxy-nor-L-arginine"),
    ("norNOHA", "Nomega-hydroxy-nor-L-arginine"),
    ("NOHA", "Nomega-hydroxy-L-arginine"),
    ("terbinafine", TERBINAFINE_AS_FILED),
    ("terbinafine hydrochloride", TERBINAFINE_AS_FILED),
])
def test_a_drug_is_the_compound_brenda_files_it_as(typed, filed):
    assert same_compound(typed, filed), (identity_key(typed), identity_key(filed))


@pytest.mark.parametrize("a, b", [
    # nor-NOHA is one carbon shorter than NOHA: two compounds.
    ("nor-NOHA", "Nomega-hydroxy-L-arginine"),
    ("NOHA", "Nomega-hydroxy-nor-L-arginine"),
    # Forodesine is not its second-generation successor.
    ("forodesine", "DADMe-immucillin-H"),
    ("immucillin-H", "immucillin-G"),
    ("terbinafine", "naftifine"),
])
def test_two_drugs_stay_two(a, b):
    assert not same_compound(a, b), (identity_key(a), identity_key(b))


# -- NEW-02's Ki: a mutant's row entered twice ------------------------------------

def _mura(compound, value, status, kind=None):
    return {"reference": "637598", "compound": compound, "organism": "Escherichia coli",
            "value": value, "status": status, "kind": kind}


def test_a_row_repeating_a_mutant_rows_value_is_the_mutants():
    """BRENDA files MurA's fosfomycin Ki (EC 2.5.1.7, ref 637598) as 0.0086
    mM "wild-type enzyme", 1 mM "mutant C115D" and again 1 mM "at pH 8.0".
    Once MurA was read, the "at pH 8.0" row was carried as the enzyme's Ki:
    a hundred times the wild type's, and the resistant mutant's."""
    from row_form import mutant_twins

    rows = [_mura("fosfomycin", 0.0086, "wild_type"),
            _mura("fosfomycin", 1.0, "variant", "mutant"), _mura("fosfomycin", 1.0, "unstated"),
            _mura("fosfomycin", 2.0, "variant", "mutant"), _mura("fosfomycin", 2.0, "unstated"),
            # The wild type's own value repeated stays the wild type's.
            _mura("(Z)-3-fluorophosphoenolpyruvate", 0.04, "wild_type"),
            _mura("(Z)-3-fluorophosphoenolpyruvate", 0.04, "unstated"),
            _mura("(Z)-3-fluorophosphoenolpyruvate", 0.08, "variant", "mutant"),
            _mura("(Z)-3-fluorophosphoenolpyruvate", 0.08, "unstated")]
    assert mutant_twins(rows) == {2, 4, 8}


def test_an_unlabelled_row_is_not_a_twin_without_a_stated_wild_type():
    """Most wild-type values are filed with no word about the enzyme form.
    A mutant that happens to share one is no reason to withhold it."""
    from row_form import mutant_twins

    assert mutant_twins([_mura("fosfomycin", 1.0, "variant", "mutant"),
                         _mura("fosfomycin", 1.0, "unstated")]) == set()
    # Another paper's row, another compound's row, an isozyme's row: no twin.
    other = dict(_mura("fosfomycin", 1.0, "unstated"), reference="637593")
    assert mutant_twins([_mura("fosfomycin", 0.0086, "wild_type"),
                         _mura("fosfomycin", 1.0, "variant", "mutant"), other,
                         _mura("phosphoenolpyruvate", 1.0, "unstated"),
                         _mura("fosfomycin", 3.0, "variant", "isozyme"),
                         _mura("fosfomycin", 3.0, "unstated")]) == set()
    # One mutant row accounts for one twin, not two.
    assert len(mutant_twins([_mura("fosfomycin", 0.0086, "wild_type"),
                             _mura("fosfomycin", 1.0, "variant", "mutant"),
                             _mura("fosfomycin", 1.0, "unstated"),
                             _mura("fosfomycin", 1.0, "unstated")])) == 1


def test_the_resolver_withholds_the_twin_as_a_variants_row():
    from types import SimpleNamespace

    import fallback_logic
    from protein_variant import VariantVerdict

    def entry(conditions, value, status, kind=None):
        return SimpleNamespace(reference_id="637598", substrate="fosfomycin", organism="Escherichia coli",
                               km_value=value, conditions=conditions, ec_number="2.5.1.7",
                               variant=VariantVerdict(status=status, kind=kind, reason="as BRENDA wrote it"))
    entries = [entry("wild-type enzyme", 0.0086, "wild_type"), entry("mutant C115D", 1.0, "variant", "mutant"),
               entry("at pH 8.0", 1.0, "unstated")]
    fallback_logic._mark_mutant_twins(entries)
    usable, withheld = fallback_logic._partition_variants(entries)
    assert [e.km_value for e in usable] == [0.0086]
    assert "entered the mutant's measurement twice" in entries[2].variant.reason
