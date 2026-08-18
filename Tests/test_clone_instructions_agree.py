"""Every document that tells someone to clone must say the same thing.

WHAT THIS COMES FROM
--------------------
`CONTRIBUTING.md` opens with "New here? Read START_HERE.md first."
`START_HERE.md` line 44 said:

    git clone --recursive https://github.com/Terrium-sim/main.git
    cd main

`README.md` said:

    git clone https://github.com/Terrium-sim/terrium.git
    cd terrium

`git remote get-url origin` says neither — it says
`math12345678/terrium.git`.

**Three answers to the first command a newcomer runs**, in the two files
they are told to read first. A newcomer following START_HERE and one
following README end up in differently-named directories, and neither URL
matches the repository they are actually in.

`--recursive` was wrong on its own terms: there is no `.gitmodules` here,
so it did nothing. It was presumably left over from the six-repository
split described in `docs/PUBLISHING.md`, which has not happened.

This went unnoticed for a long time while CONTRIBUTING and README were
audited repeatedly, because nobody opened the file they both point at.

WHAT THIS CHECKS
----------------
1. Every clone command across the entry-point documents uses one URL.
2. The directory each tells you to `cd` into matches that URL's repo name.
3. `--recursive` is not used while there are no submodules.

WHAT IT DOES NOT CHECK
----------------------
Whether the URL is *correct*. That needs network access this environment
does not have, and `docs/RENAME_PLAN.md` has carried it as an open question
since the naming review. Agreement is checkable; truth is not, from here.

Agreement is still worth enforcing: three different answers is a worse
failure than one unverified answer, because it guarantees at least two are
wrong.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The documents a newcomer is routed to first.
ENTRY_POINTS = ("README.md", "START_HERE.md", "CONTRIBUTING.md")

#: Everywhere else this repository names itself.
#:
#: Three files was not the scope of the problem. Making ENTRY_POINTS agree
#: settled 3 references and left 126 saying something else, including all
#: five links on `.github/ISSUE_TEMPLATE/config.yml` -- the GitHub "New
#: issue" page, which a newcomer reaches *before* they ever clone -- and
#: the clone command in `docs/REPO_MAP.md`, which still carried the
#: `--recursive` flag that had just been removed from START_HERE for doing
#: nothing.
#:
#: `.github/ISSUE_TEMPLATE/config.yml` is not a document, which is part of
#: why it was missed: the audit was looking at markdown.
SELF_REFERENCES = ENTRY_POINTS + (
    "SUPPORT.md",
    "SECURITY.md",
    "docs/REPO_MAP.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

#: A link into this repository's own files on GitHub.
_BLOB_RE = re.compile(
    r"https://github\.com/(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"/blob/[A-Za-z0-9_.-]+/(?P<path>[A-Za-z0-9_./-]+)"
)

_CLONE_RE = re.compile(r"git clone\s+(?P<flags>(?:--\S+\s+)*)(?P<url>https://\S+?\.git)")


def clone_commands() -> list[tuple[str, str, str]]:
    """(document, flags, url) for every clone instruction found.

    Reads SELF_REFERENCES, not ENTRY_POINTS. Scoping this to three files is
    how `docs/REPO_MAP.md` kept `git clone --recursive .../main.git` --
    both halves of a defect that had just been fixed two files away -- in a
    document `DOCUMENTATION_INDEX.md` routes newcomers to.
    """
    found = []
    for name in SELF_REFERENCES:
        path = ROOT / name
        if not path.exists():
            continue
        for m in _CLONE_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            found.append((name, m.group("flags").strip(), m.group("url")))
    return found


def self_links() -> list[tuple[str, str, str]]:
    """(surface, slug, path) for links into files that exist in this tree.

    The test for "is this a reference to *us*" is evidence rather than a
    name: a `blob` URL whose path resolves to a file here is a claim about
    this repository, whoever it says owns it. `Terrium-sim/frontend-main`
    and the other planned split repos are not caught by that, correctly --
    they name repositories whose contents are not these files.
    """
    found = []
    for name in SELF_REFERENCES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found.extend((name, slug, p) for slug, p in extract_self_links(text))
    return found


def extract_self_links(text: str) -> list[tuple[str, str]]:
    """(slug, path) for blob URLs whose path resolves in this tree.

    Split out from `self_links` to be testable on synthetic input. It was
    not, and the mutation that deletes the existence check passed all 23
    tests: every blob URL in the real files happens to point at a file that
    exists, so the rule was doing its job invisibly and could have been
    removed without anything objecting.
    """
    return [
        (m.group("slug"), m.group("path"))
        for m in _BLOB_RE.finditer(text)
        if (ROOT / m.group("path")).exists()
    ]


def test_every_link_into_our_own_files_names_one_repository() -> None:
    """The New Issue page, which is reached before anything is cloned.

    Its five `contact_links` pointed at `Terrium-sim/main` while the clone
    command said `Terrium-sim/terrium`. Whichever is right, they could not
    both be, and a broken link on that page is the first thing a would-be
    contributor sees.
    """
    links = self_links()
    assert links, (
        "no self-referencing GitHub links found at all. Either they moved "
        "or _BLOB_RE broke; a scan that finds nothing must not pass."
    )
    slugs = {slug for _, slug, _ in links}
    assert len(slugs) == 1, (
        "these link into this repository's files under different names: "
        + "; ".join(f"{s} -> {slug}" for s, slug, _ in links if len(slugs) > 1)
        + ". Every one of them 404s except at most one."
    )


def test_the_scan_reaches_past_the_three_entry_points() -> None:
    """The widened scope, asserted rather than assumed.

    Narrowing `clone_commands()` back to ENTRY_POINTS passed every other
    test in this file. That is an honest result and a bad one: once
    `docs/REPO_MAP.md` was corrected there was nothing left for the wider
    scope to catch, so the scope could be quietly reverted and the suite
    would agree.

    Coverage that only exists while a defect exists is not coverage. This
    fails the moment the scan stops reading a surface it is supposed to
    read, defect or no defect.
    """
    cloned = {doc for doc, _, _ in clone_commands()}
    linked = {surface for surface, _, _ in self_links()}

    # Asserted separately. The first version took the union of the two, so
    # narrowing either scan on its own still left the other supplying a
    # surface beyond ENTRY_POINTS and the assertion passed -- satisfied by
    # the half that had not been broken.
    assert cloned - set(ENTRY_POINTS), (
        "every clone command found came from one of the three entry points "
        f"{ENTRY_POINTS}. clone_commands() has narrowed back to where it was "
        "when docs/REPO_MAP.md kept `git clone --recursive .../main.git` "
        "unnoticed, two files from where that had just been fixed."
    )
    assert ".github/ISSUE_TEMPLATE/config.yml" in linked, (
        "the GitHub New Issue page is no longer being read. Its five links "
        "are what a newcomer reaches before cloning anything, and they were "
        "most of the 126 references the first repair did not look at."
    )


def test_a_link_to_another_repository_is_not_treated_as_a_self_reference() -> None:
    """Evidence, not a name.

    `docs/PUBLISHING.md` plans eighteen repositories. Their READMEs link to
    each other — `Terrium-sim/frontend-main`, `Terrium-sim/terium` and the
    rest — and those are correct references to different repositories. A
    rule that demanded every `Terrium-sim/*` URL match the clone URL would
    fail on documents that are right, and a guard that fails on correct
    work gets deleted.

    The discriminator is whether the linked path resolves *here*.
    """
    ours = "see https://github.com/Terrium-sim/main/blob/main/SECURITY.md"
    theirs = "see https://github.com/Terrium-sim/frontend-main/blob/main/src/no/such/file.tsx"

    assert extract_self_links(ours) == [("Terrium-sim/main", "SECURITY.md")]
    assert extract_self_links(theirs) == [], (
        "a link to a file that does not exist in this tree was read as a "
        "claim about this repository"
    )


def test_the_links_and_the_clone_command_agree() -> None:
    """Two surfaces, one answer.

    Splitting these into separate tests is deliberate: a failure here means
    the links are internally consistent but point somewhere other than the
    place the README tells you to clone, which is a different repair from
    the links disagreeing among themselves.
    """
    links = self_links()
    commands = clone_commands()
    if not links or not commands:
        raise AssertionError("both surfaces must be present for this to mean anything")

    linked = {slug for _, slug, _ in links}
    cloned = {url.removeprefix("https://github.com/").removesuffix(".git")
              for _, _, url in commands}
    assert linked == cloned, (
        f"links point at {sorted(linked)} and the clone command at "
        f"{sorted(cloned)}. A newcomer who clicks and a newcomer who clones "
        "end up in different repositories."
    )


def test_the_entry_points_all_use_one_clone_url() -> None:
    """Three different URLs guarantees at least two are wrong."""
    commands = clone_commands()
    assert commands, (
        "no clone instruction found in any entry-point document. Either they "
        "moved or this regex broke; both need a person."
    )
    urls = {url for _, _, url in commands}
    assert len(urls) == 1, (
        "the entry points disagree on where to clone from: "
        + "; ".join(f"{doc} -> {url}" for doc, _, url in commands)
        + ". A newcomer reading one and a newcomer reading another end up in "
        "different repositories."
    )


def test_the_cd_target_matches_the_url() -> None:
    """`clone .../main.git` followed by `cd terrium` leaves you nowhere."""
    commands = clone_commands()
    repo = {url.rsplit("/", 1)[-1].removesuffix(".git") for _, _, url in commands}
    assert len(repo) == 1
    expected = repo.pop()

    for name in ENTRY_POINTS:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"git clone\s+\S*\s*https://\S+\.git\s*\n\s*cd\s+(\S+)", text):
            assert m.group(1) == expected, (
                f"{name} clones a repository named {expected!r} and then "
                f"`cd {m.group(1)}`. One of the two is wrong and the reader "
                "finds out at the second command."
            )


def test_recursive_is_not_promised_without_submodules() -> None:
    """`--recursive` with no `.gitmodules` is a flag that does nothing.

    Harmless in effect, misleading in what it implies: a reader takes it to
    mean the project has submodules and that omitting it would break their
    checkout.
    """
    has_submodules = (ROOT / ".gitmodules").exists()
    recursive = [(doc, flags) for doc, flags, _ in clone_commands()
                 if "--recursive" in flags or "--recurse-submodules" in flags]
    # Stated as an implication rather than a branch: the flag may be
    # promised ONLY IF submodules exist. Unconditional, so it holds in both
    # worlds and cannot skip.
    #
    # The first version wrapped the assertion in `if not has_submodules`,
    # which means that the day a `.gitmodules` appears the test passes
    # having checked nothing, while its name still claims something. Caught
    # by `check_no_vacuous_tests.py` once it learned to read Python
    # (ADR 0089) — this is the first new test it has stopped.
    assert not recursive or has_submodules, (
        f"{recursive} promises submodules, but there is no .gitmodules "
        "in this repository. Either the split described in "
        "docs/PUBLISHING.md happened and this file needs updating, or "
        "the flag should go."
    )


def test_the_url_disagreement_with_origin_is_recorded_somewhere() -> None:
    """Unverified is acceptable; unrecorded is not.

    The entry points cannot be checked against reality from here — no
    network. What can be checked is that the discrepancy with `origin` is
    written down where somebody with network access will find it.
    """
    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not origin:
        return  # no remote configured; nothing to disagree with

    urls = {url for _, _, url in clone_commands()}
    if origin in urls:
        return  # they agree; nothing to record

    plan = (ROOT / "docs" / "RENAME_PLAN.md")
    assert plan.exists(), "docs/RENAME_PLAN.md is where this is tracked"
    text = plan.read_text(encoding="utf-8", errors="replace")
    assert "origin" in text and "Terrium-sim" in text, (
        "the documented clone URL differs from `git remote get-url origin` "
        "and docs/RENAME_PLAN.md no longer records that. An unverified URL "
        "is survivable; an unrecorded one is how a newcomer's first command "
        "fails with nobody knowing why."
    )
