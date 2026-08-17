"""The golden set: Terrium's ground truth, as DATA.

WHY THIS IS NOT IN THE TEST FILE
--------------------------------
It was, and that broke the one procedure that needs it most.

`scripts/verify_golden_against_live.py` re-resolves every golden tuple
against BRENDA as it is today. It loaded them by importing
`Tests/test_golden_set.py`, whose docstring said it did so "without
importing pytest" -- which was false, because that module imports pytest at
the top. Run outside a test environment, the verifier died on
`ModuleNotFoundError: No module named 'pytest'`.

So `scripts/check_golden_freshness.py` told people to run a script that
could not run. An alarm with a procedure attached is only better than an
alarm without one if the procedure works.

Ground truth is data. It should be readable by anything that needs it --
a test, a guard, a verifier, a human -- without dragging in a test
framework. That is what this module is.
"""
from __future__ import annotations

#: When the BRENDA fixtures these tuples were verified against were captured.
#: Stated once because all of them came from the same capture session; a
#: tuple verified separately should carry its own date instead.
FIXTURES_CAPTURED = "2026-07-01"

GOLDEN = [
    {
        "id": "G1: LDH/lactate/Homo sapiens",
        "verified_on": FIXTURES_CAPTURED,
        "ec": "1.1.1.27",
        "substrate": "lactate",
        "organism": "Homo sapiens",
        "fixture": "brenda_ldh_fixture.html",
        "expected": {
            "km": 10.73,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "740253",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G2: AChE/acetyl thiocholine/Homo sapiens",
        "verified_on": FIXTURES_CAPTURED,
        "ec": "3.1.1.7",
        "substrate": "acetyl thiocholine",
        "organism": "Homo sapiens",
        "fixture": "brenda_ache_fixture.html",
        "expected": {
            "km": 0.09,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "649716",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G3: LDH/lactate/Mus musculus (cross-species fallback)",
        "verified_on": FIXTURES_CAPTURED,
        "ec": "1.1.1.27",
        "substrate": "lactate",
        "organism": "Mus musculus",
        "fixture": "brenda_ldh_fixture.html",
        "expected": {
            "km": 0.0026,
            "unit": "mM",
            "organism": "Sus scrofa",
            "source": "brenda_cross_species",
            "ref": "740001",
            "cross_species_flag": True,
        },
        #: Cross-species is opt-in since ADR 0024. The golden VALUE is still
        #: a true fact about BRENDA; what changed is that reaching it now
        #: requires asking. test_cross_species_golden_tuples_withhold_by_default
        #: below asserts the other half.
        "allow_cross_species": True,
        #: And this row is `isozyme H4` (ADR 0029). LDH's H4 and M4 isozymes
        #: have genuinely different kinetics, so a request for "lactate
        #: dehydrogenase" did not ask for this one.
        #:
        #: Worth pausing on: the golden set — the hand-verified record of
        #: what the resolver SHOULD return — had an isozyme measurement
        #: pinned as the expected answer, and every test passed. The
        #: classifier is what made it visible.
        "allow_variants": True,
    },
    {
        "id": "G4: LDH/gossypol/Homo sapiens (Ki)",
        "verified_on": FIXTURES_CAPTURED,
        "ec": "1.1.1.27",
        "substrate": "gossypol",
        "organism": "Homo sapiens",
        "fixture": "brenda_ldh_ki_fixture.html",
        "quantity": "ki",
        "expected": {
            "km": 0.0014,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "711801",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G5: LDH/gossypol/Mus musculus (Ki cross-species, relatedness-filtered)",
        "verified_on": FIXTURES_CAPTURED,
        "ec": "1.1.1.27",
        "substrate": "gossypol",
        "organism": "Mus musculus",
        "fixture": "brenda_ldh_ki_fixture.html",
        "quantity": "ki",
        "expected": {
            #: WAS 0.0007 mM / Plasmodium falciparum / ref 654758.
            #:
            #: That is the lowest gossypol Ki in the fixture, and until the
            #: relatedness check existed it is what a MOUSE query returned:
            #: an apicomplexan parasite's inhibition constant, offered as a
            #: rodent's, because "minimum value" was the tie-break and
            #: minimum value is not a scientific criterion.
            #:
            #: Plasmodium falciparum and Cryptosporidium parvum share only
            #: the domain Eukaryota with Mus musculus and are now excluded.
            #: The surviving candidate is Homo sapiens -- still
            #: cross-species, still flagged, but two mammals sharing the
            #: superorder Euarchontoglires.
            #:
            #: This tuple is Jeske's own example made concrete, and the
            #: before/after is the clearest evidence in the repository that
            #: her third recommendation was worth implementing.
            "km": 0.0014,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_cross_species",
            "ref": "711801",
            "cross_species_flag": True,
            "rejected_organisms": {"Plasmodium falciparum", "Cryptosporidium parvum"},
        },
        "allow_cross_species": True,
    },
]
