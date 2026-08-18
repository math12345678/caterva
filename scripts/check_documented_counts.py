"""
Documented-counts guard for Terrium.

Verifies that the test counts and domain count printed in README.md match
what the repository actually contains.

Why this exists
---------------
Three README numbers had drifted silently and were found by hand during the
Stage 7 audit:

    make test           claimed   524 tests   actual 1,040
    Terium/tests/    claimed   833 tests   actual   858
    Tests/              claimed   124 tests   actual   182

and the domain count was stated twice in the same file with two different
values ("Eight" in the prose, "Ten" in the detailed list).

These are exactly the class of claim Rule 1 governs: a factual assertion
that no executable check covered, so nothing objected as it went stale. The
Stage 4 amendment applies -- *a guard is not delivered until something runs
it unasked* -- so this is wired into verify_domain.sh and CI rather than
being a script someone remembers to run.

The counts are collected from pytest itself (--collect-only), not
recomputed by a parallel implementation that could drift in its own way.

Usage:
    python scripts/check_documented_counts.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

# Every document a newcomer is told to trust, checked for stale counts.
#
# WHY THIS IS A LIST AND NOT JUST README.md
# -----------------------------------------
# It was just README.md for months, and it worked -- it caught the drift it
# was written for, repeatedly. Meanwhile three other documents rotted beside
# it, unwatched:
#
#     docs/INTERN_ONBOARDING.md   "roughly 1,291 tests"   actual 1,684
#                                 "22 guards"             actual 35
#                                 "23 decision records"   actual 56
#     docs/AGENT_BRIEFING.md      "22 guards", "1,291 tests"
#     docs/AGENT_BRIEF.md         "13 guards"
#     docs/REPO_MAP.md            "22 guards" x3, "1,014 tests", "277 tests"
#
# The onboarding document is the worst possible place for this. It is the
# one file a newcomer has no way to check, read at the exact moment they are
# deciding whether the project's claims about rigour are worth believing.
#
# A correct guard on too narrow a scope. Same shape as ADR 0055, where
# check_no_unsourced_ui_numbers.py scanned HTML only and a forbidden `km:
# 5.2` sat in TypeScript for months, and as ADR 0027 before it. Third time.
PRESENT_TENSE_DOCS = [
    "README.md",
    "START_HERE.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/REPO_MAP.md",
    "docs/AGENT_BRIEF.md",
    "docs/AGENT_BRIEFING.md",
    "docs/INTERN_ONBOARDING.md",
    "docs/FIRST_TASKS.md",
    "docs/CONSTITUTION.md",
    "docs/API.md",
] + sorted(
    # The drafted public READMEs for the 18-repository split in
    # `docs/PUBLISHING.md`. They are not live *yet*, which is why nothing
    # checked them -- and they are the file GitHub renders first on every
    # repository the split would create, which is why that was backwards.
    #
    # `docs/readmes/main.md` advertised "1,291 tests (1,014 engine + 277
    # literature)" when the real figures were 1,982 / 1,142 / 840, and
    # "23 ADRs" against 94. Publishing that is a worse failure than a stale
    # internal document: it is the first paragraph a stranger reads.
    str(p.relative_to(REPO_ROOT))
    for p in (REPO_ROOT / "docs" / "readmes").glob("*.md")
)

# NOT checked, deliberately.
#
# These describe what was true on a date. `EXPERT_FEEDBACK.md` says "46 ADRs"
# in the record of a pass when there were 46, and that sentence is correct
# and must stay. Business/build-stages/ is the same. An accepted ADR is
# superseded by a new ADR, never edited.
#
# Flagging those would be flagging the truth, and the pressure it would
# create -- rewrite the record so the build goes green -- is exactly the
# failure mode this project exists to avoid. Naming them here rather than
# relying on them not matching the pattern, so the exclusion is a decision
# somebody made rather than an accident of a regex.
HISTORICAL_DOCS_NOT_CHECKED = [
    "docs/EXPERT_FEEDBACK.md",
    "docs/ARCHIVE_TRIAGE.md",
    "docs/ARCHITECTURE_RIGOR.md",
    "docs/adr/",
    "Business/build-stages/",
]

# Suites `make test` runs, in the order it runs them.
SUITES = [
    ("engine", REPO_ROOT / "Terium" / "tests"),
    ("literature", REPO_ROOT / "Tests"),
]


def collect_count(path: Path) -> int | None:
    """Number of tests pytest collects under `path`.

    Returns None (rather than raising or guessing) when collection cannot
    run -- a missing dependency must not be reported as a count mismatch.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(path), "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  ! could not collect {path.name}: {exc}")
        return None

    # `-q` prints "path/to/test_file.py: N" per file, then a summary line.
    total = 0
    seen = False
    for line in proc.stdout.splitlines():
        match = re.match(r"^\S+\.py:\s*(\d+)\s*$", line.strip())
        if match:
            total += int(match.group(1))
            seen = True

    if not seen:
        # Fall back to the summary line ("182 tests collected in 0.31s").
        match = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
        if match:
            return int(match.group(1))
        print(f"  ! no collectable tests found under {path}")
        return None

    return total


def documented_numbers(text: str) -> dict:
    """Pull the claimed counts out of README.md."""
    found = {}

    # "make test      # runs all 1,040 tests (858 engine + 182 literature)"
    m = re.search(r"make test\s+#\s*runs all ([\d,]+) tests", text)
    if m:
        found["make_test"] = int(m.group(1).replace(",", ""))

    # Repo-structure block: "└── tests/              858 tests"
    m = re.search(r"tests/\s+([\d,]+) tests", text)
    if m:
        found["engine"] = int(m.group(1).replace(",", ""))

    # "└── ...                 182 tests"
    m = re.search(r"\.\.\.\s+([\d,]+) tests", text)
    if m:
        found["literature"] = int(m.group(1).replace(",", ""))

    return found


def documented_guard_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> guard scripts" claim in the README, with its line number.

    Added after the README was found claiming "all 14 guard scripts" and
    "~20 guard scripts" on two different lines while `scripts/` held 21.
    Both numbers had been true once. Neither was checked by anything, so
    both rotted quietly — and a stale count in the one file newcomers read
    is a small lie that makes every other number in it less trustworthy.

    Constitution Rule 1: every factual claim is checked, not only numerical
    ones about science. A count of files in this repository is about as
    checkable as a claim gets.

    "~20" is accepted as approximate: the tilde is a claim about the order
    of magnitude, and holding it to exactness would push people toward
    vaguer wording rather than truer wording.
    """
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(r"(~)?\s*(\d+)\s+guard scripts?\b", re.IGNORECASE)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            approximate = match.group(1) is not None
            value = int(match.group(2))
            claims.append((lineno, -value if approximate else value))
    return claims


def documented_domain_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> simulation domains" claim, with its line number.

    Returned as a list so that two claims disagreeing with *each other* is
    detectable, which is how the original defect presented.
    """
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    }
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(r"\b([A-Za-z]+|\d+)\s+simulation domains\b", re.IGNORECASE)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            token = match.group(1).lower()
            value = words.get(token)
            if value is None and token.isdigit():
                value = int(token)
            if value is not None:
                claims.append((lineno, value))
    return claims


def is_quoted(line: str, start: int, end: int) -> bool:
    """True when the span sits inside backticks or quotation marks.

    A quoted count is an EXAMPLE, not an assertion. `docs/README.md` explains
    the historical-document exclusion by quoting the sentence it must not
    flag -- *"46 ADRs"* -- and the first version of this matcher flagged
    that sentence. The guard failed the document explaining the guard.

    Cheap and slightly over-permissive on purpose: a writer who wants a count
    checked writes it plainly, and one who wants to quote a stale figure as
    an example needs a way to say so. Over-permissive here costs a missed
    stale count; over-strict costs a build that cannot go green without
    corrupting an explanation. The first is recoverable.
    """
    for opener, closer in (("`", "`"), ('"', '"'), ("“", "”"), ("'", "'")):
        before = line[:start]
        after = line[end:]
        if opener in before and closer in after:
            # Odd number of openers before means we are inside one.
            if before.count(opener) % 2 == 1 or (opener != closer and closer in after):
                return True
    return False


def documented_adr_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> ADRs" / "<N> decision records" claim, with its line number.

    Added because `docs/INTERN_ONBOARDING.md` pointed newcomers at
    "`docs/adr/` -- 23 decision records" when there were 56. Undercounting is
    worse than overcounting here: it tells a reader the project has thought
    about less than it has, in the document written to convince them it
    thinks carefully.
    """
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(
        r"(~)?\s*(\d+)\s+(?:ADRs?|decision records?|architecture decision records?)\b",
        re.IGNORECASE,
    )
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            if is_quoted(line, match.start(), match.end()):
                continue
            approximate = match.group(1) is not None
            value = int(match.group(2))
            claims.append((lineno, -value if approximate else value))
    return claims


#: "275 tests failed" is a report of an event, not a claim about the suite.
#: `docs/readmes/business.md` says exactly that about a real incident, and
#: rewriting it would falsify a record to make a build go green -- the
#: failure mode this project exists to avoid, performed by a tool.
_OUTCOME_WORDS = ("failed", "passed", "broke", "were", "did", "ran", "collected")


def documented_test_counts(text: str) -> List[Tuple[int, int]]:
    """Every "<N> tests" claim about the size of a suite, with its line.

    Deliberately does NOT try to work out *which* suite each refers to.
    `docs/readmes/terium.md` says "1,014 tests." with no antecedent on the
    line, and guessing would be inventing an attribution. What is checkable
    without guessing is that the number is one the repository can currently
    produce; a figure matching no suite is stale whatever it meant.
    """
    claims: List[Tuple[int, int]] = []
    pattern = re.compile(r"\b([\d,]+)\s+tests\b(?!\s+(?:" + "|".join(_OUTCOME_WORDS) + r")\b)")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            if is_quoted(line, match.start(), match.end()):
                continue
            claims.append((lineno, int(match.group(1).replace(",", ""))))
    return claims


def test_count_failures(relative: str, text: str, actual: dict) -> List[str]:
    """Test-suite sizes named in `relative` that no suite currently has."""
    if not actual:
        return []  # nothing collected; see rewrite() on inventing numbers
    real = set(actual.values())
    return [
        f"{relative}:{lineno} claims {value:,} tests; no suite has that many "
        f"({', '.join(f'{k} {v:,}' for k, v in sorted(actual.items()))})"
        for lineno, value in documented_test_counts(text)
        if value not in real
    ]


def count_adrs() -> int:
    return len(
        [p for p in (REPO_ROOT / "docs" / "adr").glob("[0-9]*.md")
         if p.stat().st_size > 0]
    )


def adr_failures(relative: str, text: str, actual: int) -> List[str]:
    """ADR-count claims in one document that disagree with `docs/adr/`.

    Split out of `check_other_docs` so the README can be held to the same
    rule. It was not: `check_other_docs` skipped it as "already checked
    above, in more detail", and the detailed check covered test counts,
    domain counts and guard counts -- never ADRs. So `README.md:449` said
    "23 decision records" while `docs/adr/` held 93, in the one document
    every newcomer opens.

    The matcher was never the problem. `selftest` asserts it catches
    "`docs/adr/` — 23 decision records", verbatim, and passed the whole
    time. The guard proved it could find this sentence and was never
    pointed at the file containing it.

    That is the fourth instance of the shape named at the top of this file:
    a correct check on too narrow a scope. The previous three were found by
    widening scope to more documents. This one was an exemption inside the
    widening -- justified by a claim about other coverage that was not
    true.
    """
    failures: List[str] = []
    for lineno, claimed in documented_adr_counts(text):
        approximate = claimed < 0
        value = abs(claimed)
        tolerance = 3 if approximate else 0
        if abs(value - actual) > tolerance:
            failures.append(
                f"{relative}:{lineno} claims "
                f"{'~' if approximate else ''}{value} ADRs; "
                f"docs/adr/ contains {actual}"
            )
    return failures


#: Counts this guard derives from the tree, and can therefore correct.
#:
#: `simulation domains` is deliberately absent. The comment in `main`
#: explains why the true number is not derived: `DISPATCH` includes a
#: run-mode and a generic ingest path that are not teaching domains, so any
#: automatic count would encode a judgment call. A `--write` that guessed at
#: it would put that judgment in a script and hide it. Conflicts between the
#: domain claims are still reported; a person resolves them.
_REWRITABLE = ("test counts", "guard scripts", "ADRs")


#: A thousands-formatted number welded directly onto a word: `ADRs1,129`.
#:
#: WHY THIS IS CHECKED AT ALL
#: --------------------------
#: `README.md` acquired exactly that string. HEAD reads
#: `ADRs, engineering constitution, API docs`; the working tree read
#: `ADRs1,129 engineering constitution, API docs` -- an ENGINE TEST COUNT
#: written over the comma in a sentence that was never about tests.
#:
#: Replaying `rewrite()` against HEAD does not reproduce it, so the
#: intermediate state that did is gone and the culprit is not proven. That is
#: the reason this is a CHECK rather than only a fix: a corruption whose
#: cause cannot be reconstructed will happen again, and the guard whose job
#: is the accuracy of these documents could not see it. It counted the
#: numbers and never looked at what they were glued to.
#:
#: Deliberately narrow -- a comma-formatted number, immediately after a
#: letter. Measured against every markdown file in the repository: one hit,
#: the real one. `SBML2`, `CC BY 4.0`, `ADR 0055` and version strings do not
#: match, which is what keeps this from becoming a warning people learn to
#: scroll past (ADR 0028).
_MANGLED_NUMBER = re.compile(r"(?<=[A-Za-z])\d{1,3},\d{3}")


def _splice(match: re.Match[str], group: int, shown: str) -> str:
    """`match.group(0)` with `group` replaced, located BY POSITION.

    A named function rather than two lines inside `rewrite`, because the
    obvious spelling is wrong in a way no current caller can reveal:

        match.group(0).replace(match.group(2), shown, 1)

    replaces the first occurrence of the group's *text* anywhere in the
    match. That is the right place only while no pattern can see those same
    characters earlier in its own match. None can today -- every prefix here
    is a literal with no digits in it -- so reverting this function to
    `.replace` breaks no test that goes through `rewrite`.

    Which is the reason it is a function with its own case below. A fix
    whose absence nothing detects is indistinguishable from no fix, and this
    project has shipped that mistake often enough to stop arguing with it.
    """
    start, end = match.start(group) - match.start(0), match.end(group) - match.start(0)
    return match.group(0)[:start] + shown + match.group(0)[end:]


def mangled_numbers(text: str) -> List[Tuple[int, str]]:
    """Every line where a formatted number is glued to a word."""
    found = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _MANGLED_NUMBER.search(line)
        if match:
            found.append((lineno, match.group(0)))
    return found


def rewrite(text: str, actual: dict, guards: int, adrs: int) -> Tuple[str, List[str]]:
    """README text with every derivable count corrected, and what changed.

    WHY THIS EXISTS
    ---------------
    Five counts drifted in one hour of concurrent work. The failure message
    said "Update README.md", which means a contributor whose change adds a
    test gets a red build and a hand-edit across two files and six lines,
    for numbers a script already knows. That is a contribution barrier
    built out of a correct check.

    Only what is derived is written. An approximate claim (`~20 guard
    scripts`) inside its tolerance is left alone: the tilde is a claim
    about magnitude, and rewriting it to an exact figure would silently
    convert a deliberately loose statement into a precise one.
    """
    changed: List[str] = []

    def apply(body: str, pattern: re.Pattern, value: int, label: str) -> str:
        """Rewrite group 2 of every match to `value`, line by line.

        Line by line so `is_quoted` and the reported line number both see
        the line the match sits on. Group 1 is the optional tilde.
        """
        out = []
        for lineno, line in enumerate(body.splitlines(keepends=True), start=1):

            def repl(m: re.Match[str], _n: int = lineno, _l: str = line) -> str:
                was = int(m.group(2).replace(",", ""))
                tolerance = 3 if m.group(1) else 0
                if abs(was - value) <= tolerance or is_quoted(_l, m.start(), m.end()):
                    return m.group(0)
                changed.append(f"line {_n}: {label} {was} -> {value}")
                shown = f"{value:,}" if "," in m.group(2) else str(value)
                # Spliced BY POSITION, not by `m.group(0).replace(m.group(2),
                # shown, 1)`. That replaced the first occurrence of the
                # group's TEXT anywhere in the match, which is the right
                # place only as long as no pattern can see those same
                # characters earlier. None can today. But `[\d,]+` matches a
                # bare comma, every pattern here is one edit away from
                # admitting digits into its prefix, and the failure mode is
                # a number written into the middle of a sentence -- which is
                # exactly the shape of the corruption `mangled_numbers` now
                # detects. Position is knowable, so it is used.
                return _splice(m, 2, shown)

            out.append(pattern.sub(repl, line))
        return "".join(out)

    # Test counts, only when every suite was actually collected. Writing a
    # number derived from a partial collection would be worse than leaving
    # a stale one: it would look freshly verified.
    if {"make_test", "engine", "literature"} <= set(actual):
        for pattern, key, label in (
            (r"(~)?runs all ([\d,]+) tests", "make_test", "make test total"),
            (r"(~)?tests/\s+([\d,]+) tests", "engine", "engine tests"),
            (r"(~)?\.\.\.\s+([\d,]+) tests", "literature", "literature tests"),
            (r"(~)?\(([\d,]+) engine", "engine", "engine tests (inline)"),
            (r"(~)?\+ ([\d,]+) literature", "literature", "literature tests (inline)"),
        ):
            text = apply(text, re.compile(pattern), actual[key], label)

    text = apply(
        text, re.compile(r"(~)?\s*(\d+) guard scripts?\b", re.IGNORECASE),
        guards, "guard scripts",
    )
    text = apply(
        text,
        re.compile(
            r"(~)?\s*(\d+)\s+(?=ADRs?\b|decision records?\b"
            r"|architecture decision records?\b)",
            re.IGNORECASE,
        ),
        adrs, "ADRs",
    )
    return text, changed


def check_other_docs(actual: dict | None = None) -> List[str]:
    """Guard-, ADR- and test-count claims in every present-tense doc."""
    actual = actual or {}
    failures: List[str] = []
    actual_guards = len(list((REPO_ROOT / "scripts").glob("check_*.py")))
    actual_adrs = count_adrs()
    checked = 0

    for relative in PRESENT_TENSE_DOCS:
        path = REPO_ROOT / relative
        if relative == "README.md":
            # main() runs the README's own checks, including ADR counts via
            # adr_failures(). Skipping it here avoids reporting the same
            # line twice -- it is NOT a statement that the README is
            # checked more thoroughly. That is what this comment used to
            # say, and it was how "23 decision records" survived.
            continue
        if not path.exists():
            # A doc named here and missing is itself a finding: the list is
            # how the project says which documents it promises to keep true.
            failures.append(
                f"{relative} is listed as a present-tense contributor doc but "
                "does not exist. Remove it from PRESENT_TENSE_DOCS or restore it."
            )
            continue
        text = path.read_text(encoding="utf-8")
        checked += 1

        for lineno, claimed in documented_guard_counts(text):
            approximate = claimed < 0
            value = abs(claimed)
            tolerance = 3 if approximate else 0
            if abs(value - actual_guards) > tolerance:
                failures.append(
                    f"{relative}:{lineno} claims "
                    f"{'~' if approximate else ''}{value} guard scripts; "
                    f"scripts/ contains {actual_guards}"
                )

        failures.extend(adr_failures(relative, text, actual_adrs))
        failures.extend(test_count_failures(relative, text, actual))

    if not failures:
        print(
            f"  contributor docs  {checked} scanned for guard/ADR counts "
            f"(guards {actual_guards}, ADRs {actual_adrs})"
        )
    return failures


def selftest() -> int:
    """Prove the two new matchers can fail.

    Without this the addition is unfalsifiable in the way ADR 0034 describes:
    every contributor doc is currently correct, so the new code path reports
    zero findings -- and a matcher that matched nothing would report zero too.
    That is precisely how this guard's original scope went unnoticed.
    """
    guard_cases = [
        ("22 guards run on every build", []),          # "guards" != "guard scripts"
        ("all 14 guard scripts", [14]),
        ("~20 guard scripts", [-20]),
        ("35 guard scripts pass", [35]),
    ]
    adr_cases = [
        ("`docs/adr/` — 23 decision records", [23]),
        ("56 ADRs, all unique", [56]),
        ("~50 architecture decision records", [-50]),
        ("ADR 0055 says so", []),                      # a reference, not a count
        # Quoted counts are examples. This exact sentence lives in
        # docs/README.md and the first version of this matcher flagged it.
        ('flagging *"46 ADRs"* in a record would be flagging the truth', []),
        ("the README once said `23 decision records`", []),
    ]

    # The real corruption, and the near-misses that must NOT fire. If this
    # matcher flagged version strings it would be suppressed within a week,
    # and then it would catch nothing (ADR 0028).
    mangle_cases = [
        ("├── docs/     ADRs1,129 engineering constitution", ["1,129"]),
        ("├── docs/     ADRs, engineering constitution", []),
        ("runs all 2,019 tests", []),          # a number where one belongs
        ("SBML2 and CC BY 4.0 and ADR 0055", []),
        ("Python3.11", []),                    # glued, but not a count
        ("see tests/1,014 tests", []),         # after a slash, not a word
    ]

    failures = []
    for text, expected in mangle_cases:
        got = [t for _, t in mangled_numbers(text)]
        if got != expected:
            failures.append(
                f"mangle matcher on {text!r}: expected {expected}, got {got}"
            )

    # `rewrite` must only ever change digits. This is the property the
    # positional splice exists to hold, and asserting the property rather
    # than one example is what makes it survive a new pattern being added to
    # the list above it.
    sample = (
        "├── tests/                       1,014 tests\n"
        "├── docs/                       ADRs, engineering constitution\n"
        "│   └── adr/                    23 decision records\n"
        "└── scripts/                    20 guard scripts\n"
    )
    written, _ = rewrite(
        sample, {"make_test": 2019, "engine": 1129, "literature": 875}, 63, 100
    )
    # The case that actually distinguishes `_splice` from `.replace`. No
    # pattern in `rewrite` can currently produce a match whose group-2 text
    # occurs earlier inside the same match, so the property check below
    # passes either way -- verified by reverting the function and watching
    # it stay green. This one does not.
    collision = re.compile(r"(~)?12 x (\d+)").search("12 x 12")
    assert collision is not None
    spliced = _splice(collision, 2, "99")
    if spliced != "12 x 99":
        failures.append(
            f"_splice landed in the wrong place: expected '12 x 99', got "
            f"{spliced!r}. Replacing by TEXT rather than POSITION rewrites "
            "the first matching characters in the match, not the group."
        )

    strip_digits = lambda s: re.sub(r"[\d,]+", "", s)  # noqa: E731
    if strip_digits(sample) != strip_digits(written):
        failures.append(
            "rewrite() changed non-numeric text:\n"
            f"    before {strip_digits(sample)!r}\n"
            f"    after  {strip_digits(written)!r}"
        )
    if mangled_numbers(written):
        failures.append(f"rewrite() produced a welded number: {written!r}")

    for text, expected in guard_cases:
        got = [v for _, v in documented_guard_counts(text)]
        if got != expected:
            failures.append(f"guard matcher on {text!r}: expected {expected}, got {got}")
    for text, expected in adr_cases:
        got = [v for _, v in documented_adr_counts(text)]
        if got != expected:
            failures.append(f"ADR matcher on {text!r}: expected {expected}, got {got}")

    # The exclusion list must not silently overlap the checked list, or a
    # historical doc would be rewritten to satisfy a build.
    overlap = set(PRESENT_TENSE_DOCS) & set(HISTORICAL_DOCS_NOT_CHECKED)
    if overlap:
        failures.append(f"a doc is in both lists: {sorted(overlap)}")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(guard_cases)} guard-count, {len(adr_cases)} "
        f"ADR-count and {len(mangle_cases)} welded-number forms matched as "
        "intended; rewrite() changed digits and nothing else; the two doc "
        "lists are disjoint."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not README.exists():
        print(f"FAIL: {README} not found")
        return 1

    text = README.read_text(encoding="utf-8")
    claimed = documented_numbers(text)
    failures: List[str] = []
    skipped = False

    print("Collecting actual test counts...")
    actual = {}
    for name, path in SUITES:
        count = collect_count(path)
        if count is None:
            skipped = True
            continue
        actual[name] = count
        print(f"  {name:<12} {count}")

    if "engine" in actual and "literature" in actual:
        actual["make_test"] = actual["engine"] + actual["literature"]

    for key in ("make_test", "engine", "literature"):
        if key not in claimed:
            failures.append(f"README no longer states a '{key}' test count")
            continue
        if key not in actual:
            continue
        if claimed[key] != actual[key]:
            failures.append(
                f"{key}: README says {claimed[key]:,}, actual is {actual[key]:,}"
            )

    # Domain counts must agree with each other. The true number is not
    # derived here: `DISPATCH` includes a run-mode (ssa_replicates) and a
    # generic ingest path (sbml) that are not teaching domains, so any
    # automatic count would encode a judgment call. Internal consistency is
    # checkable without making that call, and it is what actually broke.
    claims = documented_domain_counts(text)
    if len(claims) < 2:
        failures.append(
            f"expected at least 2 'N simulation domains' claims in README, found {len(claims)}"
        )
    else:
        values = {value for _, value in claims}
        if len(values) > 1:
            detail = ", ".join(f"line {ln}: {v}" for ln, v in claims)
            failures.append(f"README states conflicting domain counts ({detail})")
        else:
            print(f"  domains      {claims[0][1]} (consistent across {len(claims)} claims)")

    actual_guards = len(list((REPO_ROOT / "scripts").glob("check_*.py")))
    guard_claims = documented_guard_counts(text)
    if not guard_claims:
        failures.append(
            "README no longer states a guard-script count. It stated two, "
            "and both had gone stale; removing the claim rather than fixing "
            "it is not the intended resolution."
        )
    else:
        for lineno, claimed_guards in guard_claims:
            approximate = claimed_guards < 0
            value = abs(claimed_guards)
            # An approximate claim is allowed to be off by a couple; an
            # exact one is not allowed to be off at all.
            tolerance = 3 if approximate else 0
            if abs(value - actual_guards) > tolerance:
                failures.append(
                    f"README line {lineno} claims "
                    f"{'~' if approximate else ''}{value} guard scripts; "
                    f"scripts/ contains {actual_guards}"
                )
        if not any("guard scripts" in f for f in failures):
            print(f"  guards       {actual_guards} (matches {len(guard_claims)} README claim(s))")

    # The README is held to the ADR rule too. It was the only present-tense
    # document exempt from it, and the only one that was wrong.
    actual_adrs = count_adrs()
    adr_claims = documented_adr_counts(text)
    if not adr_claims:
        failures.append(
            "README no longer states an ADR count. It stated one, and it "
            "was wrong by seventy; removing the claim rather than fixing it "
            "is not the intended resolution."
        )
    else:
        readme_adr = adr_failures("README", text, actual_adrs)
        failures.extend(readme_adr)
        if not readme_adr:
            print(f"  ADRs         {actual_adrs} (matches {len(adr_claims)} README claim(s))")

    # ---- Every other present-tense contributor document -----------------
    #
    # Only guard-script counts and ADR counts are checked across these. Test
    # counts are not: the README states them in a specific tree-diagram form
    # this parser understands, and demanding that form everywhere would make
    # the guard a style rule. Guard and ADR counts are plain countable
    # claims wherever they appear.
    failures.extend(check_other_docs(actual))

    # ---- Numbers welded into prose --------------------------------------
    #
    # Not a count check. This asks whether a number landed somewhere a
    # number does not belong, which is the one failure mode a guard about
    # documented counts is uniquely placed to catch and had no opinion
    # about. `--write` cannot repair these: the original wording is gone, so
    # a person has to restore it.
    mangled = 0
    for relative in PRESENT_TENSE_DOCS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        for lineno, text_found in mangled_numbers(
            path.read_text(encoding="utf-8")
        ):
            mangled += 1
            failures.append(
                f"{relative}:{lineno} has {text_found!r} welded onto the "
                "preceding word. A count was written into prose; --write "
                "cannot undo it, restore the wording by hand"
            )
    if not mangled:
        print(f"  prose         no counts welded into words "
              f"({len(PRESENT_TENSE_DOCS)} docs)")

    print()
    if failures and "--write" in sys.argv:
        # No wholesale refusal when a suite fails to collect. The rule that
        # matters -- never write a number nobody measured -- belongs to
        # `rewrite`, which skips test counts whenever any suite is missing
        # from `actual`. Guard and ADR counts come from file globs and are
        # unaffected by pytest, so blocking those on an unrelated
        # collection failure would leave a contributor unable to fix the
        # thing they actually broke.
        #
        # It is said out loud instead: written, not written because
        # unknown, or nothing to write.
        if skipped:
            print(
                "NOTE: at least one suite could not be collected, so the "
                "test counts are\n      unknown and will NOT be written. "
                "Guard and ADR counts still will be."
            )
        updated, changed = rewrite(text, actual, actual_guards, actual_adrs)
        if changed:
            README.write_text(updated, encoding="utf-8")
            changed = [f"README.md {c}" for c in changed]

        # Every other present-tense document, for the counts that are
        # unambiguous. Adding 17 drafted public READMEs to the guard and
        # leaving them out of the fixer would have turned one hand-edit
        # into eighteen -- the barrier this flag exists to remove,
        # reintroduced by widening the check.
        #
        # Test counts are NOT written outside the README. `1,014 tests.`
        # in docs/readmes/terium.md has no antecedent on the line, so which
        # suite it means is a judgement, and a fixer that picked one would
        # be inventing an attribution. Those are reported and left.
        for relative in PRESENT_TENSE_DOCS:
            if relative == "README.md":
                continue
            path = REPO_ROOT / relative
            if not path.exists():
                continue
            before = path.read_text(encoding="utf-8")
            after, edits = rewrite(before, {}, actual_guards, actual_adrs)
            if edits:
                path.write_text(after, encoding="utf-8")
                changed.extend(f"{relative} {e}" for e in edits)

        if changed:
            print(f"WROTE {len(changed)} count(s):")
            for line in changed:
                print(f"  - {line}")
            print(
                "\nRe-run without --write to confirm. Anything still failing "
                "is not derived\nfrom the tree and needs a person: "
                f"everything outside {_REWRITABLE} is\nleft alone on purpose."
            )
            return 1 if skipped else 0
        print(
            "NOTHING TO WRITE: every remaining failure is a count this guard "
            "does not\nderive. See the list below."
        )

    if failures:
        print("FAIL: documented counts do not match reality")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nRun `python3 scripts/check_documented_counts.py --write` to "
            "correct the\ncounts derived from the tree "
            f"({', '.join(_REWRITABLE)}), or edit README.md by hand."
        )
        return 1

    if skipped:
        print("OK (partial): every count that could be collected matches README.")
        return 0

    print("OK: README test counts and domain counts match the repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
