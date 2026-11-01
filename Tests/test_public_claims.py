"""Public pages must not contradict the implementation.

Wraps `scripts/check_public_claims.py` and replays each of the four real
drifted claims, so the guard is shown to fire on the things it was written
for rather than merely passing on a tree that has already been cleaned.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_public_claims as guard  # noqa: E402


def test_no_public_page_contradicts_the_code() -> None:
    assert guard.main() == 0


def test_it_catches_the_adaptive_label_that_was_live(tmp_path) -> None:
    """`InteractiveShell.tsx` said "rk4 (adaptive)". It is fixed-step."""
    page = tmp_path / "InteractiveShell.tsx"
    page.write_text('        <span className="x">rk4 (adaptive)</span>\n')
    problems = guard.find_claims([page])
    assert problems and "adaptive" in problems[0]


def test_it_catches_the_stale_domain_list(tmp_path) -> None:
    """Four shipped domains were listed as "Planned"."""
    page = tmp_path / "FAQSection.tsx"
    page.write_text('a: "Planned: PCR amplification, Monte Carlo simulation."\n')
    assert guard.find_claims([page])


def test_it_catches_the_hardcoded_test_count(tmp_path) -> None:
    page = tmp_path / "FAQSection.tsx"
    page.write_text('a: "304+ tests and counting."\n')
    assert guard.find_claims([page])


def test_it_catches_the_blanket_tolerance_claim(tmp_path) -> None:
    """This one appeared in THREE components, not one.

    I fixed the FAQ by hand and believed I was done; the guard found the
    same sentence in TrustSection and WorkflowCompare. Fixing the instance
    you happened to read is not fixing the claim.
    """
    page = tmp_path / "TrustSection.tsx"
    page.write_text('desc: "solve the system to 1e-10 tolerance."\n')
    assert guard.find_claims([page])


def test_matching_ignores_case(tmp_path) -> None:
    """A capitalised variant is the same claim.

    A mutation making the match case-sensitive passed all twelve tests,
    because every replay used the exact casing that happened to be in the
    source. "RK4 (Adaptive)" in a heading would then sail through -- and
    headings are exactly where marketing copy gets title-cased.
    """
    for variant in ("RK4 (Adaptive)", "rk4 (ADAPTIVE)", "Rk4 (Adaptive)"):
        page = tmp_path / "h.tsx"
        page.write_text(f"  <h3>{variant}</h3>\n")
        assert guard.find_claims([page]), f"{variant!r} was not caught"


def test_honest_copy_is_not_flagged(tmp_path) -> None:
    """Crying wolf on accurate copy is how a guard gets deleted."""
    page = tmp_path / "ok.tsx"
    page.write_text(
        'desc: "RK4 with 200 substeps per output point. Tolerances are '
        'per-domain, from 1e-10 on analytic cases to 1e-4 on stochastic ones."\n'
    )
    assert guard.find_claims([page]) == []


def test_the_integrator_predicate_reads_the_real_file() -> None:
    """The reason behind the rule, re-derived rather than asserted."""
    holds, detail = guard._integrator_is_fixed_step()
    assert holds, detail
    assert "constant h" in detail


def test_the_predicate_fails_when_its_evidence_disappears(monkeypatch) -> None:
    """A check whose evidence has vanished has not passed."""
    monkeypatch.setattr(guard, "SIMULATE_TS", pathlib.Path("/nonexistent/x.ts"))
    holds, detail = guard._integrator_is_fixed_step()
    assert not holds
    assert "missing" in detail


def test_a_predicate_that_stops_holding_fails_the_guard(monkeypatch, capsys) -> None:
    """If the code gains real adaptation, the rule must be revisited.

    Continuing to forbid an accurate word is its own kind of wrong, and it
    is the kind that makes people delete guards.
    """
    monkeypatch.setitem(
        guard.CLAIMS, "rk4 (adaptive)",
        ("stale reason", lambda: (False, "the integrator now adapts")),
    )
    assert guard.main() == 1
    assert "no longer holds" in capsys.readouterr().out


def test_the_domains_predicate_checks_files_that_exist() -> None:
    holds, detail = guard._four_domains_are_archived()
    assert holds, detail


def test_every_claim_records_why_it_is_forbidden() -> None:
    for phrase, (why, predicate) in guard.CLAIMS.items():
        assert len(why) > 30, (
            f"CLAIMS[{phrase!r}] forbids a phrase without saying what makes "
            "it wrong. A rule nobody can evaluate gets removed."
        )
        assert callable(predicate)


def test_the_floor_fires_when_the_scan_finds_nothing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard, "PUBLIC_TREES", ("no/such/tree",))
    assert guard.main() == 1
    assert "below the floor" in capsys.readouterr().out
