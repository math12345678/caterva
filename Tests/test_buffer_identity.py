"""Tests for buffer_identity.py.

Every PubChem response below is a fixture. The network is never touched:
providers are injected, exactly as taxonomy.py's lineage provider is.

The CIDs used are the real ones (Tris 6503, Tris hydrochloride 93573,
phosphate 1061, MOPS 70807), so the fixtures describe the API this code
actually talks to rather than a convenient invention. They are not asserted
as chemistry — nothing in the module depends on WHICH number comes back,
only on whether two lookups agree.
"""
from __future__ import annotations

import pytest

from buffer_identity import (
    BufferIdentity,
    compare_buffers,
    extract_species,
    parse_cid_json,
    resolve_identity,
)


# ---------------------------------------------------------------------------
# Fixture providers
# ---------------------------------------------------------------------------

CID_BY_NAME = {
    "tris": 6503,
    "tris-hcl": 93573,
    "phosphate": 1061,
    "mops": 70807,
    "hepes": 23831,
}

#: Tris-HCl's parent is Tris. That single fact is the reason this module
#: goes to PubChem twice instead of once.
PARENT_BY_CID = {93573: 6503}


def fake_cid_provider(name: str) -> str:
    cid = CID_BY_NAME.get(name.strip().lower())
    if cid is None:
        # PubChem's real shape for an unknown name.
        return '{"Fault": {"Code": "PUGREST.NotFound"}}'
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def fake_parent_provider(cid: int) -> str:
    parent = PARENT_BY_CID.get(cid, cid)
    return '{"IdentifierList": {"CID": [%d]}}' % parent


def resolve(raw: str | None) -> BufferIdentity:
    return resolve_identity(raw, fake_cid_provider, fake_parent_provider)


# ---------------------------------------------------------------------------
# Extraction: string handling, no chemistry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,species,concentration",
    [
        # The three shapes that actually appear in this repository's fixtures.
        ("0.5 M Tris-HCl buffer", "Tris-HCl", "0.5 M"),
        ("0.1 M MOPS buffer", "MOPS", "0.1 M"),
        ("phosphate", "phosphate", None),
        # Shapes BRENDA commentary produces elsewhere.
        ("in 50 mM HEPES buffer", "HEPES", "50 mM"),
        ("Tris buffer system", "Tris", None),
        ("100 mM phosphate buffered", "phosphate", "100 mM"),
    ],
)
def test_extracts_species_and_keeps_the_concentration(raw, species, concentration):
    assert extract_species(raw) == (species, concentration)


def test_concentration_is_kept_not_silently_dropped():
    """The comparison ignores concentration; the record must not.

    0.5 M Tris-HCl and 10 mM Tris-HCl compare as the same buffer, and that
    is a real limitation. Keeping the text is what lets a reader see the
    limitation instead of inferring agreement the check never established.
    """
    identity = resolve("0.5 M Tris-HCl buffer")
    assert identity.concentration_text == "0.5 M"
    assert identity.raw == "0.5 M Tris-HCl buffer"


@pytest.mark.parametrize("raw", ["buffer", "  ", "buffer system", "-"])
def test_nothing_recognisable_is_unresolvable_not_a_lookup(raw):
    """An empty species must never reach PubChem.

    `.../compound/name//cids/JSON` is a different request with a different
    meaning, and guessing what it returns is not a risk worth taking.
    """
    called = []

    def spy(name: str) -> str:
        called.append(name)
        return fake_cid_provider(name)

    identity = resolve_identity(raw, spy, fake_parent_provider)
    assert identity.status in {"unresolvable", "not_reported"}
    assert called == []


# ---------------------------------------------------------------------------
# Parsing PubChem
# ---------------------------------------------------------------------------

def test_unknown_name_parses_cleanly_rather_than_raising():
    # PubChem answers an unknown name with a well-formed Fault document.
    # "Parsed fine, found nothing" is a real case.
    assert parse_cid_json('{"Fault": {"Code": "PUGREST.NotFound"}}') is None


@pytest.mark.parametrize("payload", ["", "not json", "null", "[]", "{}"])
def test_malformed_payloads_return_none(payload):
    assert parse_cid_json(payload) is None


def test_a_non_integer_cid_is_rejected():
    # Defends the comparison: `"6503" == 6503` is False in Python, so a
    # string cid would silently turn every match into a mismatch.
    assert parse_cid_json('{"IdentifierList": {"CID": ["6503"]}}') is None


# ---------------------------------------------------------------------------
# The case this module exists for
# ---------------------------------------------------------------------------

def test_the_same_buffer_written_two_ways_compares_as_same():
    """The false positive that would have made the check useless.

    "0.5 M Tris-HCl buffer" against "Tris-HCl" is a string difference and
    not a chemistry difference. If this reported `different`, the warning
    would fire on the common case and be ignored by the third run.
    """
    result = compare_buffers(resolve("0.5 M Tris-HCl buffer"), resolve("Tris-HCl"))
    assert result.status == "same"
    assert result.is_same


def test_salt_and_free_base_are_one_buffer_system():
    """Tris-HCl and Tris: different compounds, one buffer.

    This is the whole reason identity is compared at the PubChem PARENT
    rather than at the compound. Comparing on `cid` alone would call these
    different, which is true as chemistry and wrong as biochemistry.
    """
    left, right = resolve("Tris-HCl"), resolve("Tris")
    assert left.cid != right.cid, "fixture no longer exercises the salt case"
    assert left.parent_cid == right.parent_cid
    assert compare_buffers(left, right).status == "same"


def test_genuinely_different_buffers_are_reported_as_different():
    result = compare_buffers(resolve("phosphate"), resolve("0.5 M Tris-HCl buffer"))
    assert result.status == "different"
    assert not result.is_same
    # The reader needs both names to judge; a bare "different" is unactionable.
    assert "phosphate" in result.reason
    assert "Tris-HCl" in result.reason


def test_a_same_verdict_admits_it_ignored_concentration():
    result = compare_buffers(resolve("0.5 M Tris-HCl buffer"), resolve("Tris-HCl"))
    assert "NOT compared" in result.reason
    assert "0.5 M" in result.reason


# ---------------------------------------------------------------------------
# The three states never collapse into a pass
# ---------------------------------------------------------------------------

def test_an_unknown_buffer_is_not_a_match():
    result = compare_buffers(resolve("Tris"), resolve("Wittigs Reagent Buffer XYZ"))
    assert result.status == "unknown"
    assert not result.is_same
    assert "not evidence that the buffers agree" in result.reason


def test_a_failed_lookup_is_not_a_match():
    def exploding(_name: str) -> str:
        raise TimeoutError("PubChem unreachable")

    left = resolve("Tris")
    right = resolve_identity("MOPS", exploding, fake_parent_provider)
    assert right.status == "unresolvable"
    assert compare_buffers(left, right).status == "unknown"


def test_an_unreported_buffer_is_not_a_match():
    result = compare_buffers(resolve("Tris"), resolve(None))
    assert result.status == "not_reported"
    assert not result.is_same


def test_is_same_is_a_positive_test_not_a_negative_one():
    """`is_same` must be `status == "same"`, never `status != "different"`.

    With the negative form, every `unknown` and `not_reported` reads as
    agreement -- the exact inversion the three states exist to prevent, and
    the one a reviewer skims past.
    """
    for status in ("unknown", "not_reported", "different"):
        comparison = compare_buffers(resolve("Tris"), resolve("Tris"))
        comparison.status = status
        assert comparison.is_same is False, f"{status} must not read as a match"


def test_a_parent_lookup_failure_degrades_to_the_compound_id():
    """Losing the parent must not lose the whole identity.

    Comparing on `cid` is still better than comparing on strings; only the
    salt/free-base case is given up. Failing the identity entirely would
    turn a partial outage into "no buffer check at all".
    """
    def exploding_parent(_cid: int) -> str:
        raise TimeoutError("PubChem unreachable")

    identity = resolve_identity("Tris-HCl", fake_cid_provider, exploding_parent)
    assert identity.status == "resolved"
    assert identity.parent_cid == identity.cid == 93573
    # And the consequence is visible: the salt case now reads as different.
    assert compare_buffers(identity, resolve("Tris")).status == "different"


def test_resolution_is_case_and_whitespace_insensitive():
    assert resolve("  TRIS  ").parent_cid == resolve("tris").parent_cid


# ---------------------------------------------------------------------------
# The concentration must survive the BRENDA parser, not just this module
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary,expected_buffer",
    [
        ("in 0.5 M Tris-HCl buffer, pH 8.0", "0.5 M Tris-HCl buffer"),
        ("in 0.1 M MOPS buffer (pH 7.4), at 37°C", "0.1 M MOPS buffer"),
        ("in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C", "10 mM Tris"),
    ],
)
def test_molar_concentrations_reach_the_buffer_string(commentary, expected_buffer):
    """`concentration_text` is only honest if the concentration arrives.

    `assay_conditions._BUFFER_RE` matched "mM" and "mK" but not a bare "M",
    so "0.5 M Tris-HCl buffer" was captured as "Tris-HCl buffer" and the
    molarity was dropped before this module ever saw it.

    The consequence was quiet and specific: `BufferIdentity.concentration_text`
    exists so a reader can see that 0.5 M and 10 mM were treated as the same
    buffer, and it was empty for exactly the molar strings that motivated it.
    A disclosure mechanism, blind to the case it was written for.

    This test lives here rather than in test_assay_conditions.py because the
    consumer is what makes the gap matter, and a test beside the regex would
    read as a formatting preference.
    """
    from assay_conditions import parse_assay_conditions

    parsed = parse_assay_conditions(commentary)
    assert parsed.buffer == expected_buffer


def test_a_molar_buffer_records_its_concentration_end_to_end():
    from assay_conditions import parse_assay_conditions

    parsed = parse_assay_conditions("in 0.5 M Tris-HCl buffer, pH 8.0")
    identity = resolve(parsed.buffer)
    assert identity.concentration_text == "0.5 M", (
        "the concentration reached the buffer string but not the identity"
    )
