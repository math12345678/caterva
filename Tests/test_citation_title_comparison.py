"""Whether two titles name the same paper — checked without a network.

WHY THIS EXISTS
---------------
`verify_citations_live.py` decides, for every DOI Caterva cites, whether
CrossRef's registered title matches the title our own source claims. That
comparison is the strongest citation check in the project: it is what
distinguishes "the DOI resolves" from "the DOI is the paper we said it was",
and the script's own history records three citations it exists to catch —
a fabricated Michaelis-Menten DOI, a recombination-rate DOI cited for a
mutation rate, and an Elowitz DOI that was wrong in five files at once.

**Nothing tested it.** The comparison lived behind a `--live` flag, so it
ran only with a network and only when someone remembered, and no test
anywhere exercised the logic itself.

These tests need no network. The titles are real ones this repository cites,
recorded here as fixtures.

THE CASE THE BOOLEAN VERSION MISSED
-----------------------------------
The old `_titles_overlap` returned True on two shared content words. That
catches a DOI swapped for a paper on an unrelated subject. It cannot catch
the swap that actually happens: nobody mis-cites a paper about something
else, they mis-cite the ADJACENT paper — same author, same topic, a year
apart — and those share vocabulary by construction.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_citations_live.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("verify_citations_live", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_citations_live"] = module
    spec.loader.exec_module(module)
    return module


verify = _load()

# Real titles, from papers this repository cites.
GILLESPIE_1976 = (
    "A general method for numerically simulating the stochastic time "
    "evolution of coupled chemical reactions"
)
GILLESPIE_1977 = "Exact stochastic simulation of coupled chemical reactions"
MM_TRANSLATION = (
    "The original Michaelis constant: translation of the 1913 "
    "Michaelis-Menten paper"
)
MM_AS_WE_STORE_IT = (
    "The original Michaelis constant: translation of the 1913 "
    "Michaelis-Menten paper [Michaelis & Menten (1913) Die Kinetik der "
    "Invertinwirkung, Biochem. Z. 49, 333-369]. Biochemistry 50(39), "
    "8264-8269"
)
RECOMBINATION = "Variation and heritability of recombination rate in humans"


def test_two_adjacent_papers_are_not_called_the_same_work() -> None:
    """The finding that motivated the three-state version.

    Gillespie 1976 and Gillespie 1977 share four content words -- chemical,
    coupled, reactions, stochastic -- which cleared the old threshold of
    two. Same author, same algorithm, one year apart, and the check waved
    the swap through.
    """
    assert verify.compare_titles(GILLESPIE_1976, GILLESPIE_1977) == "ambiguous"
    assert verify.compare_titles(GILLESPIE_1977, GILLESPIE_1976) == "ambiguous"


def test_the_old_boolean_could_not_see_it() -> None:
    """Pins the gap rather than merely describing it in a docstring.

    If a future change makes `_titles_overlap` strict, this fails and the
    reasoning above gets re-read instead of silently outliving its cause.
    """
    shared = verify._words(GILLESPIE_1976) & verify._words(GILLESPIE_1977)
    assert len(shared) >= 2, (
        "the premise: these titles DO share enough vocabulary to pass a "
        "two-word threshold"
    )
    assert verify._titles_overlap(GILLESPIE_1976, GILLESPIE_1977) is True


def test_an_unrelated_paper_is_still_a_mismatch() -> None:
    """The defect the check was originally written for must still fail.

    A recombination-rate paper was once cited for a mutation rate. Adding
    the ambiguous state must not soften that into a shrug.
    """
    assert verify.compare_titles(MM_TRANSLATION, RECOMBINATION) == "mismatch"
    assert verify._titles_overlap(MM_TRANSLATION, RECOMBINATION) is False


def test_our_decorated_title_still_matches_the_registered_one() -> None:
    """Leniency where leniency is correct.

    Stored titles append journal and volume text and bracket the translated
    original, so the registered title is a subset of ours. One distinctive
    side is a decorated match, not two papers -- and calling it ambiguous
    would flood the report and get it ignored.
    """
    assert verify.compare_titles(MM_AS_WE_STORE_IT, MM_TRANSLATION) == "match"


def test_an_exact_match_is_a_match() -> None:
    assert verify.compare_titles(GILLESPIE_1977, GILLESPIE_1977) == "match"


@pytest.mark.parametrize(
    "claimed,registered",
    [("", "Exact stochastic simulation"), ("Exact stochastic simulation", ""),
     ("", ""), ("the of and", "Exact stochastic simulation")],
)
def test_nothing_to_compare_is_unknown_not_a_pass(
    claimed: str, registered: str
) -> None:
    """`unknown` is a fourth state on purpose.

    The old code returned True here -- "we could not compare" rendering
    identically to "we compared and it was fine". That inversion is the
    single defect class this repository has found most often, and it was
    sitting in the citation checker.
    """
    assert verify.compare_titles(claimed, registered) == "unknown"


def test_ambiguity_needs_distinctive_words_on_both_sides() -> None:
    """One extra word is punctuation or a subtitle, not a second paper."""
    base = "Exact stochastic simulation of coupled chemical reactions"
    assert verify.compare_titles(base + " revisited", base) == "match"


def test_the_threshold_is_named_not_scattered() -> None:
    """A magic 2 in three places is three different decisions waiting to
    drift apart."""
    assert verify._DISTINCTIVE_THRESHOLD == 2
    source = _SCRIPT.read_text(encoding="utf-8")
    body = source[source.index("def compare_titles") : source.index("def _titles_overlap")]
    assert "_DISTINCTIVE_THRESHOLD" in body
