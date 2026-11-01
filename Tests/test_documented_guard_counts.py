"""check_documented_counts.py reads "<N> guards" as well as "<N> guard scripts".

Until 2026-11-01 it read only "guard scripts", so "22 guards run on every
build" and "## The 21 guards" stood in docs/readmes/ beside 79 guard
scripts, and a release note said no hand-typed count was left.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_documented_counts import documented_guard_counts  # noqa: E402


def test_both_spellings_are_claims() -> None:
    text = "22 guards run on every build.\n## The 21 guards\n35 guard scripts\n"
    assert documented_guard_counts(text) == [(1, 22), (2, 21), (3, 35)]


def test_an_approximate_count_is_kept_as_approximate() -> None:
    assert documented_guard_counts("about ~80 guards") == [(1, -80)]


def test_a_quoted_count_is_a_quote_not_a_claim() -> None:
    # INTERN_ONBOARDING.md quotes the stale figure it corrects.
    text = 'It stated *"22 guards"* and `21 guards`.'
    assert documented_guard_counts(text) == []


def test_a_word_that_only_starts_with_guard_is_not_a_count() -> None:
    assert documented_guard_counts("3 guardrails and 4 guarded paths") == []
