"""Numbers shown to investors must match the repository.

Wraps `scripts/check_investor_claims.py`. The interesting tests are the
ones that exercise the Office-file reader on real files and on broken
ones -- a zip parser that silently returns "" makes this guard report a
clean deck it never opened.
"""
from __future__ import annotations

import pathlib
import sys
import zipfile

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_investor_claims as guard  # noqa: E402



# `check()` iterates (*INVESTOR_DOCS, *PUBLIC_MARKETING). A test that
# narrows only the first still walks the second against a monkeypatched
# ROOT, and every marketing page then reports as missing -- a failure that
# looks like a real finding and is not. Tests below clear both.
#
# That warning was right and did not go far enough, which is why six tests
# here failed with FileNotFoundError on README.md.
#
# Narrowing the DOCS does not narrow the CLAIMS. `check()` evaluates every
# resolver in CLAIMS, and the domain-count resolver reads
# `ROOT / "README.md"` -- so pointing ROOT at a tmp_path makes it read a
# README that is not there. The failure is in the harness, not the guard:
# the same shape as the comment above, one level deeper.
#
# `isolated_root` supplies the one file every claim resolver needs. It is
# deliberately a REAL sentence in the README's own format rather than an
# empty file, because a resolver that finds no match raises rather than
# returning a number, and a stub that fails differently is not isolation.


def isolated_root(tmp_path, monkeypatch, *, docs=("FAKE.md",)):
    """Point the guard at `tmp_path` with everything it reads present."""
    (tmp_path / "README.md").write_text(
        "Fifteen simulation domains built so far.\n", encoding="utf-8"
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "PUBLIC_MARKETING", ())
    monkeypatch.setattr(guard, "INVESTOR_DOCS", docs)


def test_investor_numbers_match_the_repository() -> None:
    assert guard.check() == []


def test_the_private_documents_stay_out_of_the_public_repository() -> None:
    """The deck and Business/ left on 2026-09-27, scrubbed from history too.

    Two tests used to read the real pitch deck, which was right while it was
    tracked. It is not any more: the repository is public and the deck named
    investors. This pins the opposite fact, so re-adding it -- the easy
    accident, `git add .` in a folder that still has it -- fails here and is
    blocked by .gitignore first. The Office reader itself is still tested
    below, against files built in the test.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "--", "*pitch_deck*", "Business"],
        capture_output=True, text=True, cwd=guard.ROOT, check=True,
    ).stdout.split()
    assert tracked == [], f"private documents are tracked again: {tracked}"
    assert guard.INVESTOR_DOCS == ()
    ignored = (guard.ROOT / ".gitignore").read_text()
    assert "/Business/" in ignored and "*pitch_deck*" in ignored


def test_a_stale_number_is_caught(tmp_path, monkeypatch) -> None:
    """The failing branch, run rather than assumed."""
    doc = tmp_path / "FAKE.md"
    doc.write_text("We have 382 automated tests passing.\n")
    isolated_root(tmp_path, monkeypatch)
    monkeypatch.setitem(guard.CLAIMS, "automated tests passing",
                        (r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", lambda: 1800, 0.15))
    problems = guard.check()
    assert problems and "382" in problems[0]


def test_a_number_within_tolerance_is_not_flagged(tmp_path, monkeypatch) -> None:
    """The tree moves hourly. Flagging a drift of three trains people to ignore this."""
    doc = tmp_path / "FAKE.md"
    doc.write_text("1,850 automated tests passing.\n")
    isolated_root(tmp_path, monkeypatch)
    monkeypatch.setitem(guard.CLAIMS, "automated tests passing",
                        (r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", lambda: 1852, 0.15))
    assert guard.check() == []


def test_the_configured_tolerances_can_actually_fail() -> None:
    """A tolerance is a threshold; a large enough one is an off switch.

    `test_a_number_within_tolerance_is_not_flagged` injects its own
    tolerance via monkeypatch, so widening the REAL one to 99.0 -- meaning
    a claim of 5 tests would pass against a suite of 1,852 -- was invisible
    to all ten tests. A test that supplies its own configuration cannot
    check the configuration that ships.
    """
    for label, (_, _, tol) in guard.CLAIMS.items():
        # `0 <= tol`, not `0 < tol`. The bound was strict and the docstring
        # above says why it should not be: the failure being hunted is a
        # tolerance so LARGE it is an off switch. Zero is the opposite --
        # maximally strict, failing on any drift at all — and it is the
        # right setting for `live simulation domains`, a discrete count read
        # straight out of the README and cross-checked by two other guards.
        # There is no "within 15%" of fifteen domains.
        #
        # As written, this test rejected the strictest configuration in the
        # file while accepting anything up to 50%.
        assert 0 <= tol <= 0.5, (
            f"CLAIMS[{label!r}] has tolerance {tol}, which cannot fail on any "
            "realistic drift. The tree moves hourly so some slack is right, "
            "but 50% is already generous for a number in a pitch deck."
        )


def test_a_broken_office_file_fails_rather_than_reading_as_empty(tmp_path, monkeypatch) -> None:
    """A zip that will not open must not read as a clean deck."""
    bad = tmp_path / "broken.pptx"
    bad.write_bytes(b"not a zip file at all")
    isolated_root(tmp_path, monkeypatch, docs=("broken.pptx",))
    problems = guard.check()
    assert problems and "below the floor" in problems[0]


def test_an_empty_deck_fails_rather_than_passing(tmp_path, monkeypatch) -> None:
    """A valid zip with no slides is the silent-no-op case."""
    empty = tmp_path / "empty.pptx"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("ppt/slides/slide1.xml", "<p:sld/>")
    isolated_root(tmp_path, monkeypatch, docs=("empty.pptx",))
    problems = guard.check()
    assert problems and "extraction is broken" in problems[0]


def test_a_missing_document_fails_rather_than_skips(tmp_path, monkeypatch) -> None:
    isolated_root(tmp_path, monkeypatch, docs=("nope.pptx",))
    problems = guard.check()
    assert problems and "does not exist" in problems[0]


def test_an_underivable_live_value_fails(tmp_path, monkeypatch) -> None:
    """No evidence is not the same as agreement."""
    doc = tmp_path / "FAKE.md"
    doc.write_text("5 automated tests passing.\n")
    isolated_root(tmp_path, monkeypatch)
    monkeypatch.setattr(guard, "CLAIMS", {
        "automated tests passing": (r"(\d+)\s*automated tests", lambda: -1, 0.15),
    })
    problems = guard.check()
    assert problems and "has not passed" in problems[0]


def test_a_dated_number_is_not_treated_as_a_stale_claim(tmp_path, monkeypatch) -> None:
    """A number that says when it was true ages honestly.

    `Docw/caterva_mvp_timeline.docx` says the literature layer "already
    exists and passes 124 tests **as of this session**". That was true when
    written and says so. The pitch deck's "382 automated tests passing"
    carried no qualifier and therefore read as a claim about now.

    Flagging the timeline would punish the document that did the right
    thing, and a guard that penalises good practice gets switched off.
    """
    doc = tmp_path / "TIMELINE.md"
    doc.write_text("the layer already exists and passes 124 automated tests "
                   "as of this session, a real head start\n")
    isolated_root(tmp_path, monkeypatch, docs=("TIMELINE.md",))
    monkeypatch.setitem(guard.CLAIMS, "automated tests passing",
                        (r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", lambda: 1863, 0.15))
    assert guard.check() == []


def test_an_undated_number_is_still_caught(tmp_path, monkeypatch) -> None:
    """The other half: the exemption must not swallow everything."""
    doc = tmp_path / "DECK.md"
    doc.write_text("382 automated tests passing\n")
    isolated_root(tmp_path, monkeypatch, docs=("DECK.md",))
    monkeypatch.setitem(guard.CLAIMS, "automated tests passing",
                        (r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", lambda: 1863, 0.15))
    assert guard.check(), "an undated stale number was exempted"


def test_the_timestamp_window_is_narrow_enough_to_mean_something(tmp_path, monkeypatch) -> None:
    """A wide enough window exempts the whole document.

    Widening `_TIMESTAMP_WINDOW` to 100,000 makes one "as of" anywhere in a
    file excuse every number in it -- an off switch wearing a qualifier.
    """
    assert guard._TIMESTAMP_WINDOW <= 400, (
        f"_TIMESTAMP_WINDOW is {guard._TIMESTAMP_WINDOW}; at that distance a "
        "single date excuses numbers it has nothing to do with"
    )
    doc = tmp_path / "FAR.md"
    doc.write_text("as of this session, things were fine.\n" + ("filler. " * 120)
                   + "382 automated tests passing\n")
    isolated_root(tmp_path, monkeypatch, docs=("FAR.md",))
    monkeypatch.setitem(guard.CLAIMS, "automated tests passing",
                        (r"(\d[\d,]*)\s*(?:\|\s*)?automated tests", lambda: 1863, 0.15))
    assert guard.check(), "a distant timestamp excused an unrelated number"


def test_the_reader_handles_a_plain_markdown_file(tmp_path) -> None:
    md = tmp_path / "x.md"
    md.write_text("plain text\n")
    assert guard.office_text(md) == "plain text\n"
