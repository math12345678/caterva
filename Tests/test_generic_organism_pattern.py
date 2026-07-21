"""
Unit tests for GENERIC_ORGANISM_PATTERN, which replaced the old
KNOWN_ORGANISM_PATTERN enumerated organism list (Homo sapiens, Sus
scrofa, ... - about 10 names) with a generic binomial-nomenclature
regex. The old list silently missed any organism outside it (confirmed
live: Cryptosporidium parvum, Epidalea calamita). The new pattern must
work for arbitrary organisms while not misfiring on non-organism cell
text - it's matched with fullmatch() against a single cell's full text,
never substring-searched across a whole row, specifically to avoid
picking up organism-shaped fragments buried inside long condition
sentences (e.g. "Wild type, pH 7.4, 37°C" should NOT fullmatch since it
contains punctuation/numbers beyond the pattern).
"""

from brenda_client import GENERIC_ORGANISM_PATTERN


def fullmatches(text: str) -> bool:
    return GENERIC_ORGANISM_PATTERN.fullmatch(text.strip()) is not None


def test_matches_common_organisms():
    for name in [
        "Homo sapiens",
        "Sus scrofa",
        "Cryptosporidium parvum",
        "Epidalea calamita",
        "Geobacillus stearothermophilus",
        "Priestia megaterium",
        "Lactococcus cremoris",
    ]:
        assert fullmatches(name), f"expected {name!r} to match"


def test_matches_trinomial_names():
    assert fullmatches("Bacillus subtilis natto")


def test_does_not_match_sentences_with_punctuation_or_numbers():
    """Real BRENDA condition-text cells - must not be mistaken for an
    organism, even though they contain organism-shaped word pairs."""
    non_organisms = [
        "Wild type, pH 7.4, 37°C",
        "in the presence of 20-30% glycerol, pH and temperature not specified",
        "recombinant enzyme, pH 5.5, 25°C",
        "mutant W99R/W257F",
        "-",
        "",
        "740541",
    ]
    for text in non_organisms:
        assert not fullmatches(text), f"expected {text!r} to NOT match"


def test_does_not_match_single_word():
    assert not fullmatches("Lactate")
    assert not fullmatches("ATP")
