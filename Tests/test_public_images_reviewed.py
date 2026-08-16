"""Images on public pages are claims no other guard can read.

Wraps `scripts/check_public_images_reviewed.py`. The tests that matter are
the ones proving a *changed* image fails — a new file shows up in a diff,
an edited screenshot does not.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_public_images_reviewed as guard  # noqa: E402


def test_every_public_image_is_registered_and_unchanged() -> None:
    assert guard.check() == []


def test_an_edited_image_fails(tmp_path, monkeypatch) -> None:
    """The case that matters, and the one a diff hides.

    A new file is conspicuous. A screenshot edited to add "10,000
    universities trust Terrium" is one binary blob replacing another.
    """
    img = tmp_path / "mule" / "shot.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"original pixels")
    original = guard.digest(img)

    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "public_images", lambda: ["mule/shot.png"])
    monkeypatch.setattr(guard, "register", lambda: {"mule/shot.png": (original, "reviewed")})
    monkeypatch.setattr(guard, "_MIN_IMAGES", 1)
    assert guard.check() == []

    img.write_bytes(b"edited pixels with a claim in them")
    problems = guard.check()
    assert problems and "changed" in problems[0]


def test_an_unregistered_image_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "public_images", lambda: ["mule/new.png"])
    monkeypatch.setattr(guard, "register", lambda: {})
    monkeypatch.setattr(guard, "_MIN_IMAGES", 1)
    problems = guard.check()
    assert problems and "not in the register" in problems[0]


def test_a_registered_image_that_no_longer_exists_fails(tmp_path, monkeypatch) -> None:
    """A record of a file nobody ships is a record nobody can check."""
    img = tmp_path / "mule" / "kept.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"x")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "public_images", lambda: ["mule/kept.png"])
    monkeypatch.setattr(guard, "register", lambda: {
        "mule/kept.png": (guard.digest(img), "hashed"),
        "mule/deleted.png": ("0" * 16, "hashed"),
    })
    monkeypatch.setattr(guard, "_MIN_IMAGES", 1)
    problems = guard.check()
    assert problems and "not in the tree" in problems[0]


def test_a_missing_register_block_fails_rather_than_passing(tmp_path, monkeypatch) -> None:
    """'No register' must not read as 'no images need review'."""
    stub = tmp_path / "PUBLIC_IMAGES.md"
    stub.write_text("# Images\n\nnothing machine-readable\n")
    monkeypatch.setattr(guard, "REGISTER", stub)
    assert guard.register() is None
    problems = guard.check()
    assert problems and "no PUBLIC-IMAGES-START block" in problems[0]


def test_the_floor_fires_when_the_scan_finds_nothing(monkeypatch) -> None:
    monkeypatch.setattr(guard, "PUBLIC_TREES", ("no/such/tree/",))
    problems = guard.check()
    assert problems and "below the floor" in problems[0]


def test_reviewed_and_hashed_are_kept_distinct() -> None:
    """Collapsing them would let the register claim an audit nobody did.

    All fourteen images are `reviewed` as of 2026-08-15. That is the goal,
    not a reason to delete the `hashed` state: the next image added starts
    unreviewed, and without somewhere to say so it would read as audited
    from the moment it landed.

    The count is deliberately not asserted here; that is
    `test_the_register_prose_matches_the_register`'s job, and duplicating it
    would mean two places to update and one of them going stale.
    """
    recorded = guard.register()
    assert recorded is not None

    # The distinction must remain AVAILABLE. It must not be required to be
    # in use.
    #
    # The first version asserted `"hashed" in states`, which made the test
    # fail the moment every image had actually been reviewed -- punishing
    # the outcome the register exists to reach. "Some row is still
    # unreviewed" and "the unreviewed state is still a state" are different
    # claims, and only the second belongs in a test.
    assert guard._STATES == {"reviewed", "hashed"}, (
        "the two states are what stop this register claiming an audit that "
        "did not happen. Removing `hashed` would make every future image "
        "read as reviewed on the day it was added."
    )

    states = {state for _, state in recorded.values()}
    assert states <= guard._STATES, f"unknown state(s): {states - guard._STATES}"


def test_the_register_prose_matches_the_register() -> None:
    """The document says how many are unreviewed. It must be right.

    The first draft said ten; the guard's output said eleven. A wrong
    number in a document about unchecked numbers is the exact failure this
    project keeps finding, so it is pinned rather than trusted.
    """
    recorded = guard.register()
    hashed = sum(1 for _, s in recorded.values() if s == "hashed")

    # The full range, not just the counts that happened to exist when this
    # was written. The first version covered 10-14 only, on the unexamined
    # assumption that the number would stay there. Reviewing four images
    # took it to 7 and the test raised KeyError instead of failing -- a
    # crash reads as a broken test, not as the clear message this is
    # supposed to give. Zero is included: it is where this should end up.
    words = [
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
        "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
    ]
    assert hashed < len(words), (
        f"{hashed} unreviewed images is more than this table can name; "
        "extend `words` rather than letting the check crash"
    )

    text = guard.REGISTER.read_text()
    assert f"{words[hashed]} images are `hashed`" in text, (
        f"{hashed} images are `hashed` but docs/PUBLIC_IMAGES.md does not "
        f"say so ('{words[hashed]} images are `hashed`' not found). Review "
        "an image and forget the prose, and the document overstates what "
        "is outstanding; review none and it understates."
    )
