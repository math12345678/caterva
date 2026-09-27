"""No published document may claim Caterva is built on Tellurium.

WHAT THIS COMES FROM
--------------------
`NOTICE` and `README.md` state that Caterva is unaffiliated with Tellurium
and does not depend on it. `scripts/check_no_tellurium_integration_claims.py`
exists so no other published file can say otherwise while those stand.

It had no test. This module is that, plus a replay of the false positive
that took `make guards` down.

THE FALSE POSITIVE
------------------
`docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md` is the remediation plan for the
offending `.docx` files. Its inventory reads:

    Docw/caterva_full.docx     also: claims "Tellurium integration"

The guard matched `tellurium integration`, found no denial word in the
line, and failed the build. **The document planning the cleanup was the one
blocking CI**, and the only way to go green would have been to describe the
offending files too vaguely for anyone to act on.

The guard already had the mechanism for this — `DISCUSSES`, for documents
whose subject *is* the contradiction — so the repair was one entry with a
written reason, not a new rule.

WHY THE EXEMPTIONS ARE PINNED
-----------------------------
`HISTORICAL` and `DISCUSSES` exempt whole documents. That is a real cost: a
genuine new claim inside one of them goes unseen. Three entries is where
that starts to matter, so the sets are pinned here — they can still grow,
but only deliberately.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_no_tellurium_integration_claims as guard  # noqa: E402


def test_no_published_document_claims_tellurium_integration() -> None:
    problems = guard.check()
    assert problems == [], (
        "a published document contradicts the non-affiliation notice:\n"
        + "\n".join(problems)
    )


def test_the_matcher_still_fires_on_a_real_claim() -> None:
    """Verbatim from `Docw/caterva_spec.docx`, the document that started this."""
    for sentence in (
        "plots render using the Tellurium toolkit",
        "Tellurium integration, file handling",
        "the engine is built on Tellurium",
        "powered by Tellurium",
    ):
        assert guard.CLAIM.search(sentence), f"stopped matching: {sentence!r}"
        assert not guard.DENIAL.search(sentence), f"wrongly read as a denial: {sentence!r}"


def test_the_notice_itself_is_not_a_claim() -> None:
    """`NOTICE` says the opposite and must never trip this."""
    for sentence in (
        "Caterva is not built on Tellurium",
        "Caterva is unaffiliated with Tellurium",
        "does not depend on the tellurium package",
        "uses libroadrunner directly rather than Tellurium",
    ):
        assert guard.DENIAL.search(sentence), f"denial not recognised: {sentence!r}"


def test_each_denial_word_carries_its_own_weight() -> None:
    """One marker per sentence, so removing one is not covered by another.

    The four sentences above each contain two or three denial markers —
    "is not" and "not", "does not" and "not", "unaffiliated" and "rather
    than". Deleting `not` from the alternation left all four still
    matching, so the mutation that removes it passed the whole suite.

    A test whose inputs are over-specified proves less than it appears to.
    """
    only_not = {
        "not": "Caterva was not, and will not be, a Tellurium product",
        "never": "Caterva has never shipped a Tellurium dependency",
        "unaffiliated": "Caterva: unaffiliated, separate project, separate authors",
        "without": "Caterva runs without Tellurium",
    }
    for marker, sentence in only_not.items():
        assert guard.DENIAL.search(sentence), (
            f"{marker!r} is no longer recognised as a denial. NOTICE and "
            f"README rely on it: {sentence!r}"
        )


def test_the_remediation_plan_is_not_accused_of_the_thing_it_removes() -> None:
    """The false positive, replayed against the live document.

    Written the way round that keeps working: it fails if the exemption is
    removed *while the line is still there*, and it also fails if the line
    disappears — because at that point the exemption is dead weight
    covering a whole document for no reason, and should go.
    """
    rel = "docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md"
    path = guard.REPO_ROOT / rel
    assert path.exists(), f"{rel} is gone; drop its DISCUSSES entry"

    text = path.read_text(encoding="utf-8", errors="replace")
    cites = any(
        guard.CLAIM.search(s) and not guard.DENIAL.search(s)
        for s in guard._sentences(text)
    )
    assert cites, (
        f"{rel} no longer quotes a Tellurium claim, so its DISCUSSES entry "
        "now exempts a whole document for nothing. Remove the entry."
    )
    assert rel in guard.DISCUSSES, (
        f"{rel} quotes 'Tellurium integration' as the phrase it is planning "
        "to remove, and is not exempt. The guard will fail the build on the "
        "document that plans the cleanup."
    )


def test_every_exemption_carries_a_reason() -> None:
    """An exemption without a reason is a hole with paperwork."""
    for name, entries in (("HISTORICAL", guard.HISTORICAL), ("DISCUSSES", guard.DISCUSSES)):
        assert entries, f"{name} is empty; if that is real, delete the mechanism"
        for rel, reason in entries.items():
            assert len(reason) > 40, f"{name}[{rel!r}] has no real explanation"


def test_the_exempt_set_cannot_grow_quietly() -> None:
    """Pinned, because each entry blinds the guard to a whole file.

    Not a ban on growth — a requirement that growth is a decision. Adding a
    document here means editing this list too, which is the moment to ask
    whether the file should be exempt or fixed.
    """
    assert set(guard.DISCUSSES) == {
        "Business/LEGAL_BRIEF_NAMING.md",
        "docs/PRIVACY.md",
        "docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md",
    }, "the DISCUSSES set changed; confirm each entry quotes rather than claims"
    assert set(guard.HISTORICAL) == {
        "Docw/caterva_spec.docx",
        "Docw/caterva_full.docx",
    }, "the HISTORICAL set changed; confirm each is a dated record, not live copy"


def test_the_floor_stops_a_blind_scan_reporting_clean() -> None:
    """A scan that matches nothing must not read as a clean bill of health.

    This guard's own history is the argument: the first version globbed one
    directory, and the copies under `Science-Agent-Pipeline/attached_assets/`
    went unread while it reported success.
    """
    problems = guard.check(docs=[])
    assert problems and "blind, not" in problems[0]
