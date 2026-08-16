#!/usr/bin/env python3
"""The decision record must be unambiguous.

WHY THIS EXISTS
---------------
Several agents work on this repository at once, and each one writing an ADR
takes "the next free number" by looking at the directory. Two agents looking
at the same moment take the same number.

That is not hypothetical. When this guard was written the directory held:

    0030-codegen-emitted-a-contract-that-could-not-load.md
    0030-the-generated-contract-is-now-checked.md
    0031-measuring-what-the-parser-cannot-read.md
    0031-the-committed-contract-must-match-codegen.md
    0034-a-pool-that-mixes-enzyme-forms.md
    0034-the-committed-contract-must-match-codegen.md

Three collisions. Two of the files had no `**Status:**` line at all, because
they were tombstones — an agent that discovered the clash mid-write left a
note saying "rm this", could not unlink the file from its sandbox, and
emptied it instead.

**A collision is worse here than in most places.** ADR numbers are how this
codebase cites its own reasoning: `taxonomy.py` says "see ADR 0024",
`queryResolver.ts` says "ADR 0026". A reader following "ADR 0031" to a
directory with two of them has no way to know which decision the code meant,
and the two documents said different things.

WHAT IT CHECKS
--------------
1. Every ADR number is used exactly once.
2. Every ADR states a status. A decision with no status is a draft
   somebody left, and it reads as settled.

   TWO SPELLINGS ARE ACCEPTED, because the first version of this check
   accepted one and immediately produced a false positive. ADR 0008 -- the
   oldest, cited by six files -- writes `- **Status**: Accepted` as a bullet;
   everything since writes `**Status:** Accepted`. The guard reported it as
   status-less, which was a claim about the guard rather than the document.

   A guard that enforces a SPELLING is expressing a formatting opinion. This
   one is meant to ask whether a reader can tell where a decision stands, and
   both forms answer that.
3. Every ADR appears in `docs/adr/README.md`. The index is how anyone finds
   these; a decision missing from it is one nobody will read.
4. The index has no entries for files that do not exist.

WHAT IT DOES NOT CHECK
----------------------
Whether an ADR is any good, whether its status is honest, or whether the
decision was followed. Those need a reader. This checks that the record is
navigable, which is the precondition for anyone reading it at all.

Exit 0 = the record is unambiguous. Exit 1 = it is not.
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
ADR_DIR = REPO / "docs" / "adr"
INDEX = ADR_DIR / "README.md"

#: `0024-refusing-versus-defaulting-an-unsourced-parameter.md`
_NUMBERED = re.compile(r"^(\d{4})-.+\.md$")

#: A markdown link to a sibling ADR file, as the index writes them.
_INDEX_LINK = re.compile(r"\((\d{4}-[^)]+\.md)\)")

#: The start of a status line, up to and including its punctuation.
#:
#: TWO SPELLINGS, because ADR 0008 -- the oldest, cited by six files --
#: writes `- **Status**: Accepted` as a bullet and everything since writes
#: `**Status:** Accepted`. A guard that enforced one would be expressing a
#: formatting opinion; this one asks whether a reader can tell where the
#: decision stands, and both forms answer that.
_STATUS_MARKER = re.compile(r"^[-*\s]*\*\*status\b[:*\s]*", re.I)


def _states_a_status(text: str) -> bool:
    """True when some line names a status AND says what it is.

    The second half is the part two regexes got wrong: `**Status:**` with
    nothing after it names the field and answers nothing, and a reader
    meeting it learns exactly as much as from a document with no status
    line at all.
    """
    for line in text.splitlines():
        match = _STATUS_MARKER.match(line)
        if match and line[match.end():].strip():
            return True
    return False


def main() -> int:
    if not ADR_DIR.is_dir():
        print(f"{ADR_DIR} is missing; refusing to report on an empty record.")
        return 1

    files = sorted(
        path for path in ADR_DIR.glob("*.md") if _NUMBERED.match(path.name)
    )
    if not files:
        # An empty result means the naming convention changed or the
        # directory moved, not that the record is fine. This project has
        # repeatedly found checks that examined nothing and printed OK.
        print(
            f"No numbered ADRs found in {ADR_DIR.relative_to(REPO)}. Either "
            "the naming convention changed or this reader is broken; either "
            "way, refusing to report success on an empty set."
        )
        return 1

    problems: list[str] = []

    # --- 1. numbers are unique -----------------------------------------
    by_number: dict[str, list[str]] = collections.defaultdict(list)
    for path in files:
        match = _NUMBERED.match(path.name)
        assert match is not None
        by_number[match.group(1)].append(path.name)

    for number, names in sorted(by_number.items()):
        if len(names) > 1:
            problems.append(
                f"ADR {number} names {len(names)} different documents: "
                + ", ".join(names)
                + ". Code that cites 'ADR "
                + number
                + "' no longer identifies one."
            )

    # --- 2. tombstones and statuses --------------------------------------
    #
    # A file with no content at all is the tombstone case this module's
    # docstring already describes: an agent that could not unlink a file
    # emptied it instead. Before this branch existed the guard reported such
    # a file TWICE -- once for having no status, once for not being indexed
    # -- and both messages gave the wrong instruction. "Add a status line"
    # and "link it from the index" are not what you do with a tombstone;
    # you remove it, because the number is still claimed while it sits there
    # and the next agent scanning for a free number will skip it.
    #
    # Reported separately, and excluded from the index check below, so the
    # red says the one true thing instead of two misleading ones.
    tombstones = {
        path.name for path in files if not path.read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    }
    for name in sorted(tombstones):
        problems.append(
            f"{name} is empty. It claims ADR number {name[:4]} without "
            "recording a decision, so the next agent looking for a free "
            "number will skip it and no reader can learn anything from it. "
            "Delete the file, or write the decision."
        )

    for path in files:
        if path.name in tombstones:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # `**Status:** Accepted` (current) or `- **Status**: Accepted`
        # (ADR 0008). Both state a status; neither is more true than the
        # other.
        # Line-based, deliberately, after two regex attempts were wrong in
        # two different ways:
        #
        #   `...:?\s*\S`        `\s` matches newlines regardless of re.M, so
        #                       `**Status:**` + blank line matched the first
        #                       word of the BODY.
        #   `...:?[^\S\n]*\S`   the optional `\*?\*?:?` groups can match
        #                       NOTHING and let `\S` match the `:` inside
        #                       `**Status:**` itself.
        #
        # Both accepted an empty status line. Splitting the line and asking
        # whether anything follows the marker cannot backtrack into the
        # marker, so it has no third version of this bug available.
        if not _states_a_status(text):
            problems.append(
                f"{path.name} has no '**Status:**' line. A decision with no "
                "status reads as settled whether or not it is."
            )

    # --- 3 & 4. the index and the directory agree ------------------------
    if not INDEX.is_file():
        problems.append(f"{INDEX.relative_to(REPO)} is missing.")
    else:
        index_text = INDEX.read_text(encoding="utf-8", errors="replace")
        all_links = _INDEX_LINK.findall(index_text)
        linked = set(all_links)
        on_disk = {path.name for path in files}

        # Two rows for one ADR.
        #
        # Invisible to the set comparison below, which is how a real one
        # survived: several agents write this index at once, and two adding
        # the same ADR produce two rows with DIFFERENT descriptions. A
        # reader then gets two summaries of one decision with nothing to say
        # which is current, and the guard reported the record as clean.
        for name, count in sorted(collections.Counter(all_links).items()):
            if count > 1:
                problems.append(
                    f"README.md links {name} {count} times. Two rows for one "
                    "ADR give a reader two summaries of one decision with "
                    "no way to tell which is current."
                )

        # Tombstones are excluded: telling someone to index an empty file
        # would be telling them to advertise a decision that is not there.
        for name in sorted(on_disk - linked - tombstones):
            problems.append(
                f"{name} is not linked from README.md. The index is how "
                "anyone finds these; an unlisted decision is one nobody "
                "will read."
            )
        # ...but a tombstone that IS linked is worse than one that is not,
        # so that stays reported.
        for name in sorted(linked & tombstones):
            problems.append(
                f"README.md links {name}, which is empty. The index "
                "promises a decision the file does not contain."
            )
        for name in sorted(linked - on_disk):
            problems.append(
                f"README.md links {name}, which does not exist. A dead link "
                "in the index is worse than a missing entry: it looks like "
                "the decision is recorded."
            )

    print(
        f"Checked {len(files)} ADR(s) in {ADR_DIR.relative_to(REPO)} "
        f"({len(by_number)} distinct number(s))."
    )

    if problems:
        print()
        print(f"The decision record is ambiguous ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print(
            "ADR numbers are how this codebase cites its own reasoning. "
            "Several agents write here at once, and each takes 'the next "
            "free number' by looking at the directory -- so two looking at "
            "the same moment take the same one. Renumber the later "
            "document, update README.md, and update any code comment that "
            "cites it."
        )
        return 1

    print("OK: every ADR number is unique, carries a status, and is indexed.")
    return 0


def _selftest() -> int:
    """Prove each branch fires, on a record this function builds.

    WHY: this guard had none. It reported the real directory as clean or
    dirty and nobody had shown it could tell the difference -- the same
    "a check that cannot fail is worse than no check" shape it exists to
    protect the ADRs from. It also caught a genuine bug on first run: the
    status regex matched `**Status:**` with nothing after it, so a document
    with an empty status line passed.

    Each case asserts on the MESSAGE, not merely on the exit code. A guard
    that fails for the wrong reason is a guard that sends the next reader to
    the wrong place, which is exactly the defect the tombstone branch above
    was written to fix.
    """
    import tempfile

    global ADR_DIR, INDEX, REPO
    saved = (ADR_DIR, INDEX, REPO)
    failures: list[str] = []

    def run(files: dict[str, str], index: str | None) -> tuple[int, str]:
        global ADR_DIR, INDEX, REPO
        import io
        import contextlib

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            REPO, ADR_DIR = root, root / "docs" / "adr"
            ADR_DIR.mkdir(parents=True)
            INDEX = ADR_DIR / "README.md"
            for name, body in files.items():
                (ADR_DIR / name).write_text(body, encoding="utf-8")
            if index is not None:
                INDEX.write_text(index, encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main()
            return code, buffer.getvalue()

    def expect(label: str, code: int, out: str, want_code: int, want: str = "") -> None:
        if code != want_code or (want and want.lower() not in out.lower()):
            failures.append(
                f"{label}: exit {code} (wanted {want_code})"
                + (f", message did not mention {want!r}" if want else "")
                + f"\n      output: {' '.join(out.split())[:220]}"
            )

    good = "# ADR 0001: A\n\n**Status:** Accepted\n\nBody.\n"
    good_index = "| [0001](0001-a.md) | ADR 0001: A |\n"

    try:
        # The negative case FIRST. If a clean record does not pass, every
        # positive below is meaningless -- they would fire on anything.
        expect("a clean record passes", *run({"0001-a.md": good}, good_index), 0, "OK")

        expect(
            "an empty ADR is named as a tombstone",
            *run({"0001-a.md": good, "0002-b.md": "  \n\n"}, good_index),
            1, "0002-b.md is empty",
        )

        # The point of the tombstone branch: ONE message, not three.
        code, out = run({"0001-a.md": good, "0002-b.md": ""}, good_index)
        if out.count("0002-b.md") != 1:
            failures.append(
                "a tombstone is reported more than once: "
                + f"{out.count('0002-b.md')} mentions. The branch exists so "
                "the red says one true thing instead of several misleading "
                "ones."
            )

        expect(
            "a duplicate number is caught",
            *run({"0001-a.md": good, "0001-b.md": good}, good_index),
            1, "names 2 different documents",
        )
        expect(
            "a missing status is caught",
            *run({"0001-a.md": "# ADR 0001\n\nBody with no status.\n"}, good_index),
            1, "no '**Status:**' line",
        )
        expect(
            "an empty status is caught",
            *run({"0001-a.md": "# ADR 0001\n\n**Status:**\n\nBody.\n"}, good_index),
            1, "no '**Status:**' line",
        )
        expect(
            "ADR 0008's bullet spelling is accepted",
            *run({"0001-a.md": "# ADR 0001\n\n- **Status**: Accepted\n\nB.\n"}, good_index),
            0, "OK",
        )
        expect(
            "an unindexed ADR is caught",
            *run({"0001-a.md": good, "0002-b.md": good}, good_index),
            1, "0002-b.md is not linked",
        )
        expect(
            "a duplicated index row is caught",
            *run({"0001-a.md": good}, good_index + good_index),
            1, "links 0001-a.md 2 times",
        )
        expect(
            "a dead index link is caught",
            *run({"0001-a.md": good}, good_index + "| [0009](0009-gone.md) | x |\n"),
            1, "which does not exist",
        )
        expect(
            "an indexed tombstone is caught",
            *run(
                {"0001-a.md": good, "0002-b.md": ""},
                good_index + "| [0002](0002-b.md) | ADR 0002: B |\n",
            ),
            1, "which is empty",
        )
        expect(
            "an empty directory is refused, not passed",
            *run({}, good_index),
            1, "refusing to report success on an empty set",
        )
        expect(
            "a missing index is caught",
            *run({"0001-a.md": good}, None),
            1, "is missing",
        )
    finally:
        ADR_DIR, INDEX, REPO = saved

    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELFTEST OK: every branch fires, and a clean record still passes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    sys.exit(main())
