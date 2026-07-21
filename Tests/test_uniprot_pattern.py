"""
Unit tests for UNIPROT_CELL_PATTERN, which replaced an overly narrow
"^[A-Z]\\d{5}$" pattern. That pattern matched simple accessions like
"P17538" but silently missed real UniProt accessions that mix letters
into the middle positions - caught live via a real chymotrypsin row
carrying the accession "Q6GPI1" (confirmed real, not invented - see
brenda_chymotrypsin_debug.py output). The new pattern implements
UniProt's actual accession syntax (both the [OPQ]-prefixed and other-
letter-prefixed 6-character shapes), not a guessed simplification.
"""

from brenda_client import UNIPROT_CELL_PATTERN


def matches(text: str) -> bool:
    return UNIPROT_CELL_PATTERN.match(text.strip()) is not None


def test_matches_opq_prefixed_accessions():
    """[OPQ][0-9][A-Z0-9]{3}[0-9] shape - covers most human enzyme
    accessions seen live this session."""
    for acc in ["P17538", "P07864", "P00338", "P22303", "P19367", "P07477", "Q9GT92", "Q6GPI1"]:
        assert matches(acc), f"expected {acc!r} to match"


def test_matches_other_letter_prefixed_accessions():
    """[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2} shape - the OTHER valid
    UniProt accession shape (doesn't start with O/P/Q), per UniProt's
    published accession-number syntax. NOTE: unlike every other value in
    this test suite, these three strings are NOT accessions captured
    from a live BRENDA/UniProt response - they're hand-constructed to
    match the documented syntax shape, purely to test the regex branch
    itself (no [OPQ]-prefixed accession seen live this session exercises
    this branch). This is a format/syntax check, not a claim about any
    specific real protein."""
    for acc in ["A0AVT1", "C9J2L5", "G3V0H0"]:
        assert matches(acc), f"expected {acc!r} to match"


def test_matches_multi_accession_cells():
    """Real multi-isozyme rows carry comma-separated accessions in one
    cell (LDH's "P00339,P00336", chymotrypsin's "Q6GPI1,P17538") - both
    accessions must be recognized as a valid whole cell."""
    assert matches("P00339,P00336")
    assert matches("Q6GPI1,P17538")


def test_does_not_match_non_accession_text():
    for text in ["-", "", "740253", "Homo sapiens", "pH 7.4, 25°C", "lactate"]:
        assert not matches(text), f"expected {text!r} to NOT match"


def test_does_not_match_partial_accession_shapes():
    """Guards against the pattern being too permissive - these look
    accession-ish but aren't valid shapes."""
    assert not matches("P1753")  # too short
    assert not matches("P175388")  # too long for 6-char form
    assert not matches("p17538")  # lowercase
