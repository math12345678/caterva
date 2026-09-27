#!/usr/bin/env python3
"""How much of BRENDA's commentary can Caterva actually read?

WHY THIS EXISTS
---------------
BRENDA puts one free-text cell beside every kinetic value. Caterva mines it
for pH, temperature, buffer, and (since ADR 0029) whether the row measured a
sequence variant. Everything else in that string is discarded silently.

That silence is where two real defects lived:

  * ADR 0029. "F295A/Y337A mutant" sat in the commentary of 35 of 72 rows in
    the AChE turnover fixture, unread, while selection took the minimum --
    and active-site substitutions sit at the tail a minimum reaches into.

  * ADR 0028 claimed the fixtures contained no cofactor mentions. They do:
    trypsin rows read "in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C", and
    calcium is not incidental to trypsin. The claim was made from a grep for
    NAD/NADH/Mg2+ that missed CaCl2 -- a search that found nothing, reported
    as an absence.

Both were invisible because nothing measured the gap. A parser that ignores
text does not report how much it ignored, so "we read the commentary" and
"we read a third of the commentary" look identical from outside.

This turns that into a number.

WHAT IT DOES
------------
For every commentary in the fixtures, it removes the spans the pipeline's own
extractors match, and reports what is left. The leftovers are, precisely,
what Caterva cannot read.

THE PATTERNS ARE IMPORTED, NOT RE-LISTED
----------------------------------------
Every regex below comes from the module that uses it in production. A guard
that re-declared them would be a second source of truth for what "understood"
means, and would keep reporting full coverage after the real parser regressed
-- the exact false-green shape catalogued in ADR 0024 and ADR 0027.

If an extractor's pattern changes, this guard's numbers change with it. That
coupling is the point.

WHAT A FAILURE MEANS
--------------------
Not "fix the parser". A rising residue is a prompt to decide, deliberately,
whether the newly-visible text changes what a value means -- and to record
the decision either way. `docs/commentary-residue-baseline.txt` holds the
reviewed leftovers; anything not in it is new and unreviewed.

Usage:
    python3 scripts/check_commentary_coverage.py
    python3 scripts/check_commentary_coverage.py --update-baseline
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = REPO_ROOT / "Tests"
FIXTURES = TESTS / "fixtures"
BASELINE = REPO_ROOT / "docs" / "commentary-residue-baseline.txt"

sys.path.insert(0, str(TESTS))

try:
    import assay_conditions
    import effector
    import form_mixture
    import protein_variant
    import source_context
    from brenda_client import (
        KI_TABLE_LABEL,
        KM_TABLE_LABEL,
        TURNOVER_TABLE_LABEL,
        parse_brenda_km_html,
    )
except ImportError as exc:  # pragma: no cover - environment problem, not a finding
    print(f"Could not import the parsers this guard measures: {exc}")
    print("This is an environment failure, not a coverage result. Not reporting a number.")
    raise SystemExit(1)


#: Which fixture is which table. A fixture parsed with the wrong label yields
#: zero rows, and zero rows would be reported as perfect coverage -- so the
#: run asserts it saw rows before reporting anything.
FIXTURE_TABLES = [
    ("brenda_ache_kcat_fixture.html", "3.1.1.7", TURNOVER_TABLE_LABEL),
    ("brenda_ache_fixture.html", "3.1.1.7", KM_TABLE_LABEL),
    ("brenda_ldh_fixture.html", "1.1.1.27", KM_TABLE_LABEL),
    ("brenda_ldh_ki_fixture.html", "1.1.1.27", KI_TABLE_LABEL),
    ("brenda_ldh_kcat_fixture.html", "1.1.1.27", TURNOVER_TABLE_LABEL),
    ("brenda_hexokinase_fixture.html", "2.7.1.1", KM_TABLE_LABEL),
    ("brenda_trypsin_fixture.html", "3.4.21.4", KM_TABLE_LABEL),
    ("brenda_chymotrypsin_fixture.html", "3.4.21.1", KM_TABLE_LABEL),
    ("brenda_ache_kcat_fixture.html", "3.1.1.7", KM_TABLE_LABEL),
]

#: The production patterns, imported. See the module docstring.
CONSUMING_PATTERNS = [
    ("pH", assay_conditions._PH_RE),
    ("pH-unreported", assay_conditions._PH_UNREPORTED_RE),
    ("temperature", assay_conditions._TEMP_RE),
    ("temp-unreported", assay_conditions._TEMP_UNREPORTED_RE),
    ("buffer", assay_conditions._BUFFER_RE),
    ("mutant-word", protein_variant._MUTANT_WORD_RE),
    ("point-mutation", protein_variant._POINT_MUTATION_RE),
    ("wild-type", protein_variant._WILD_TYPE_RE),
    ("isozyme", protein_variant._ISOZYME_RE),
    ("recombinant", protein_variant._RECOMBINANT_RE),
    # ADR 0032. Added when effector extraction shipped -- without these the
    # guard kept reporting "absence fructose 1 6 bisphosphate" as unread
    # text that nothing understood, which had stopped being true.
    #
    # A coverage guard that does not know about a new parser understates
    # coverage, and an understated number is not the safe direction here:
    # it is a standing work item for something already done, which is how a
    # real remaining gap gets lost in the noise.
    ("effector-clause", effector._EFFECTOR_RE),
    ("bare-salt", effector._BARE_SALT_RE),
    # ADR 0035. Positional form names -- "LDHB", "LDH-1", "hexokinase Ia" --
    # which protein_variant deliberately does not classify per-row.
    #
    # Registered here for the reason the ADR 0032 entries above give: a
    # coverage guard that does not know about a new parser understates
    # coverage, and an understated number is a standing work item for
    # something already done.
    ("acronym-form", form_mixture._ACRONYM_FORM_RE),
    ("word-roman-form", form_mixture._WORD_ROMAN_RE),
    # ADR 0037. "enzyme from heart", "healthy breast tissue", and the
    # commentary-names-an-organism case. Registered for the reason the ADR
    # 0032 and 0035 entries give: an unaware guard understates coverage, and
    # an understated number is a standing work item for something done.
    ("source-from", source_context._FROM_RE),
    ("tissue-state", source_context._TISSUE_STATE_RE),
]

#: Connective tissue. Removing these is not a claim to understand anything --
#: it stops "in", "and", "at" dominating the residue list and hiding the
#: content words that matter.
_FILLER_RE = re.compile(
    r"\b(?:in|at|with|using|the|of|and|or|a|an|for|from|to|by|on|per|"
    r"enzyme|assay|value|values|publication)\b",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[\s,;:.()\[\]\-/]+")

#: Below four characters is not a word worth reviewing.
_MIN_RESIDUE = 4


def collect_commentaries() -> list[str]:
    out: list[str] = []
    for name, ec, label in FIXTURE_TABLES:
        path = FIXTURES / name
        if not path.exists():
            continue
        rows = parse_brenda_km_html(
            path.read_text(errors="replace"),
            ec,
            [],
            target_organism=None,
            require_substrate_match=False,
            table_label=label,
        )
        out.extend((r.conditions or "").strip() for r in rows if (r.conditions or "").strip())
    return out


def residue_of(commentary: str) -> str:
    """What remains after every production extractor has taken its span."""
    text = commentary
    for _name, pattern in CONSUMING_PATTERNS:
        text = pattern.sub(" ", text)
    text = _FILLER_RE.sub(" ", text)
    return _PUNCT_RE.sub(" ", text).strip()


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in BASELINE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def residue_counts(commentaries: "list[str]") -> "collections.Counter[str]":
    """Unread fragments and how often each occurs.

    EXTRACTED so it can be called rather than reimplemented.

    `scripts/evidence_table.py` needed this number and computed it itself
    with `residue_of(c).strip()`, omitting the `_MIN_RESIDUE` floor. The two
    disagreed on their first run -- 242 fully parsed here, 230 there, 92%
    against 87% -- and both were printed under the same words. Two figures
    for one fact, either of which could have reached a paper.

    That is this repository's most-repeated defect, committed inside the
    function whose docstring said it was avoiding it. The floor exists
    because a two-character residue is punctuation, not unread meaning; a
    caller that does not know that is not a caller that should be counting.
    """
    residues: "collections.Counter[str]" = collections.Counter()
    for commentary in commentaries:
        left = residue_of(commentary)
        if len(left) >= _MIN_RESIDUE:
            residues[left] += 1
    return residues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    commentaries = collect_commentaries()
    if not commentaries:
        # A guard that measured nothing must never report success. Zero rows
        # divided by zero rows is 100% coverage, and that is the most
        # reassuring possible wrong answer.
        print("No commentaries parsed from any fixture.")
        print("This guard cannot report coverage it did not measure. Failing.")
        return 1

    residues = residue_counts(commentaries)
    covered = len(commentaries) - sum(residues.values())
    pct = 100.0 * covered / len(commentaries)

    print(f"Commentaries measured:      {len(commentaries)}")
    print(f"Fully understood:           {covered} ({pct:.0f}%)")
    print(f"Carrying unread text:       {sum(residues.values())}")
    print(f"Distinct unread fragments:  {len(residues)}")

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# Commentary text Caterva cannot read, reviewed and accepted.\n"
            "#\n"
            "# Regenerate: python3 scripts/check_commentary_coverage.py --update-baseline\n"
            "#\n"
            "# Adding a line here is a DECISION that the text does not change what\n"
            "# the value means. It is not a way to silence the guard. Two entries\n"
            "# below are on the record as unresolved rather than accepted -- see\n"
            "# ADR 0028 (cofactors) and the tissue-provenance note in ADR 0029.\n"
            "\n"
        )
        body = "\n".join(f"{txt}  # x{n}" for txt, n in sorted(residues.items()))
        BASELINE.write_text(header + body + "\n")
        print(f"\nBaseline written: {BASELINE.relative_to(REPO_ROOT)} ({len(residues)} fragments)")
        return 0

    baseline = load_baseline()
    unreviewed = {t: n for t, n in residues.items() if t not in baseline}

    if unreviewed:
        print(f"\nUnreviewed commentary text ({len(unreviewed)} fragment(s)):\n")
        for txt, n in sorted(unreviewed.items(), key=lambda kv: -kv[1]):
            print(f"  x{n:<3} {txt!r}")
        print(
            "\nEach of these is text beside a kinetic value that Caterva does not\n"
            "read. Some will be irrelevant. Some will change what the number means --\n"
            "that is how the mutant rows in ADR 0029 and the CaCl2 in the trypsin\n"
            "rows were both missed.\n"
            "\nDecide, then record the decision:\n"
            "  python3 scripts/check_commentary_coverage.py --update-baseline\n"
        )
        return 1

    print("\nOK: every unread commentary fragment has been reviewed and recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
