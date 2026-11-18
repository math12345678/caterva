"""The fifth adversarial round of the real-values work (2026-11-12), the
names half that lives in the literature layer: one compound under the
spellings a page lists it by (`compound_names.identity_key`). Offline.

The review found one compound listed as two alternatives with split row
counts: carboxypeptidase A's "hippuryl-L-phenylalanine" (10 Km, 8 kcat) and
"hippuryl-L-Phe" (3 Km, 3 kcat); pyruvate decarboxylase's "2-Ketobutyrate"
and "2-ketobutanoic acid"; triose-phosphate isomerase's "dihydroxyacetone
phosphate" and "dihydroxyacetone 3-phosphate".
"""
from __future__ import annotations

import pytest

from compound_names import identity_key, same_compound


@pytest.mark.parametrize("a, b", [
    ("hippuryl-L-Phe", "hippuryl-L-phenylalanine"),
    ("Hip-L-Phe", "hippuryl-L-phenylalanine"),
    ("2-Ketobutyrate", "2-ketobutanoic acid"),
    ("alpha-ketobutyrate", "2-oxobutanoate"),
    ("2-ketovalerate", "2-ketopentanoic acid"),
    ("alpha-ketoglutarate", "2-oxoglutarate"),
    ("dihydroxyacetone phosphate", "dihydroxyacetone 3-phosphate"),
    ("glycerone phosphate", "dihydroxyacetone phosphate"),
    ("DHAP", "dihydroxyacetone phosphate"),
    ("butyric acid", "butanoate"),
    ("Suc-Ala-Ala-Ala-pNA", "succinyl-L-Ala-L-Ala-L-Ala-4-nitroanilide"),
])
def test_one_compound_under_two_spellings_is_one(a, b):
    assert same_compound(a, b), (identity_key(a), identity_key(b))


@pytest.mark.parametrize("a, b", [
    ("hippuryl-L-Phe", "hippuryl-D-Phe"),
    ("hippuryl-L-Phe", "hippuryl-L-Arg"),
    ("2-oxobutanoate", "2-oxopentanoate"),
    ("isobutyrate", "butyrate"),
    ("butyryl-CoA", "butyrate"),
    ("dihydroxyacetone phosphate", "D-glyceraldehyde 3-phosphate"),
    ("3-ketoacyl-CoA", "2-oxoacyl-CoA"),
])
def test_two_compounds_stay_two(a, b):
    assert not same_compound(a, b), identity_key(a)
