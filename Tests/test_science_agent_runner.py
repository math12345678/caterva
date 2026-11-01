"""Regression tests for science_agent_runner.py.

These verify that network-lookup failures in the KEGG substrate resolver
degrade gracefully (return None) rather than crashing the whole resolution,
and that genuine programming errors are NOT swallowed by the same handler.
The mutation_rate (population-genetics) path is covered end-to-end so a
wrong dict-field access like the ``popgen_result['doi']`` KeyError -- caught
by the runner's broad except and degraded to a cryptic ``{'ok': false}``
error -- cannot silently land again (ADR 0008: literature provenance must
surface or fail loudly, never silently).
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# The runner lives under Science-Agent-Pipeline/, not Tests/. Derive the
# path from this file's location so the import works regardless of the
# working directory pytest happens to be invoked from.
_RUNNER_DIR = (
    Path(__file__).resolve().parents[1]
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
)
sys.path.insert(0, str(_RUNNER_DIR))

import science_agent_runner  # noqa: E402
from science_agent_runner import resolve_substrate_from_kegg  # noqa: E402


class TestResolveSubstrateFromKegg:
    """Edge cases for the KEGG substrate lookup."""

    def test_http_error_returns_none(self):
        """An HTTP error (e.g. 404 for an unknown EC number) must degrade to
        None, not crash the resolution."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = __import__("httpx").HTTPStatusError(
                "404 Not Found",
                request=None,
                response=__import__("httpx").Response(404, request=None),
            )
            result = resolve_substrate_from_kegg("1.1.1.1")
        assert result is None

    def test_timeout_returns_none(self):
        """A network timeout must degrade to None."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = __import__("httpx").TimeoutException("timeout")
            result = resolve_substrate_from_kegg("1.1.1.1")
        assert result is None

    def test_programming_error_is_not_swallowed(self):
        """A genuine programming error (e.g. AttributeError from a typo)
        must surface, not be silently caught by the broad except."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = AttributeError("typo in internal code")
            with pytest.raises(AttributeError, match="typo"):
                resolve_substrate_from_kegg("1.1.1.1")


class TestPopgenMutationRateResolution:
    """The mutation_rate path of the runner's main() end-to-end.

    Regression: main() read ``popgen_result['doi']`` from a dict that had no
    ``doi`` key. On the first successful stdpopsim hit the KeyError was caught
    by the broad except and returned as ``{"ok": false, "error": "'doi'"}`` --
    every Wright-Fisher literature mutation_rate call failed with a cryptic
    error instead of a value. These tests drive main() with a mocked resolver
    so they stay offline and pin the success and not-found shapes.
    """

    @staticmethod
    def _run_with_capsys(capsys, payload: dict) -> dict:
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            science_agent_runner.main()
        finally:
            sys.stdin = old_stdin
        return json.loads(capsys.readouterr().out)

    def test_success_path_returns_value_and_doi_locator(self, capsys, monkeypatch):
        """A found mutation rate must come back with the value and a citation
        carrying a resolvable DOI -- not crash on a missing dict field."""
        from popgen_resolver import PopgenResult

        fake = PopgenResult(
            found=True,
            value=1.29e-8,
            organism="Homo sapiens",
            source="stdpopsim",
            citation="International Human Genome Sequencing Consortium (2001)",
            doi="10.1038/35057062",
        )
        monkeypatch.setattr(
            science_agent_runner.popgen_resolver,
            "resolve_mutation_rate",
            lambda organism: fake,
        )

        out = self._run_with_capsys(
            capsys, {"parameterType": "mutation_rate", "organism": "Homo sapiens"}
        )

        assert out["ok"] is True
        assert out["found"] is True
        assert out["km"] == pytest.approx(1.29e-8)
        assert out["citation"]["referenceId"] == "10.1038/35057062"
        assert out["citation"]["url"] == "https://doi.org/10.1038/35057062"

    def test_not_found_path_returns_honest_found_false(self, capsys, monkeypatch):
        """An organism stdpopsim has nothing for degrades to found:false --
        never a fabricated value, never a crash."""
        from popgen_resolver import PopgenResult

        monkeypatch.setattr(
            science_agent_runner.popgen_resolver,
            "resolve_mutation_rate",
            lambda organism: PopgenResult(found=False, search_log=["not in catalog"]),
        )

        out = self._run_with_capsys(
            capsys, {"parameterType": "mutation_rate", "organism": "Unknownus"}
        )

        assert out["ok"] is True
        assert out["found"] is False
        assert out["source"] == "popgen_not_found"


# ---------------------------------------------------------------------------
# A name beside a number: the number is used only if the name does not
# contradict it (science_agent_runner.check_ec_against_name, 2026-10-17).
#
# Why this exists. llmResolver.ts used to ask the language model for an "EC
# number if known or inferable" and forward it under `ecNumber`, and a
# supplied `ecNumber` skips the enzyme finder entirely -- so a model that
# wrote 1.1.1.27 for "lactate dehydrogenase" chose between the L- and D-
# enzymes silently, the pick ADR 0126/0127 took out of the Python finder.
# The TypeScript side now drops any EC number the query text does not
# contain (ADR 0011: a model may propose, never supply); this is the
# runner's own half, for every caller: a number the NAME contradicts is a
# citation for the wrong protein, so it is refused and both numbers named.
#
# Every test is offline. The enzyme nomenclature answers for the names it
# holds; UniProt and NCBI are stubbed, and the kinetic lookup is a golden
# record or an assertion that it was never reached.
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

import enzyme_lookup  # noqa: E402
import fallback_logic  # noqa: E402
from citation import Citation  # noqa: E402
from fallback_logic import KineticResult  # noqa: E402


def _golden() -> KineticResult:
    """The golden G1 record, as test_runner_contract.py builds it."""
    return KineticResult(
        found=True,
        value=10.73,
        unit="mM",
        organism="Homo sapiens",
        source="brenda_exact",
        citation=Citation(
            source="BRENDA",
            reference_id="740253",
            url="https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            organism="Homo sapiens",
            notes=None,
        ),
        cross_species_flag=False,
        search_log=["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    )


def _no_uniprot(name, taxon_id):
    raise AssertionError(f"UniProt must not be asked for {name!r}")


def _offline(monkeypatch, uniprot=_no_uniprot):
    """NCBI finds nothing; UniProt answers `uniprot` (a function), which by
    default fails the test -- a name the nomenclature holds must never
    reach the network."""
    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda *a, **k: None)
    monkeypatch.setattr(enzyme_lookup, "fetch_ec_numbers_by_name", uniprot)


def _run_main(monkeypatch, payload, *, resolve, uniprot=_no_uniprot):
    """The real main(), offline, with the kinetic lookup replaced by `resolve`."""
    _offline(monkeypatch, uniprot)
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", resolve)
    monkeypatch.setattr(science_agent_runner, "resolve_substrate_from_kegg", lambda ec: None)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    return json.loads(stdout.getvalue())


def _never(*a, **k):
    raise AssertionError("the kinetic lookup must not run when the name contradicts the number")


class TestCheckEcAgainstName:
    """The decision, by the one finder, in its three outcomes."""

    def test_a_name_that_resolves_to_the_number_confirms_it(self, monkeypatch):
        _offline(monkeypatch)
        verdict = science_agent_runner.check_ec_against_name("hexokinase", "Homo sapiens", "2.7.1.1")
        assert verdict.agrees is True
        assert verdict.checked is True
        assert "confirmed" in verdict.note
        assert "2.7.1.1" in verdict.note

    def test_a_name_that_resolves_to_another_number_contradicts_it(self, monkeypatch):
        # "hexokinase" is EC 2.7.1.1 by the nomenclature's accepted name. A
        # request pairing it with the lactate dehydrogenase number is two
        # enzymes, and the refusal has to name both so the person can tell
        # which half of their request was wrong.
        _offline(monkeypatch)
        verdict = science_agent_runner.check_ec_against_name("hexokinase", "Homo sapiens", "1.1.1.27")
        assert verdict.agrees is False
        assert verdict.checked is True
        assert verdict.candidates == ["2.7.1.1"]
        assert verdict.named[0]["ec"] == "2.7.1.1"
        assert set(verdict.named[0]) >= {"ec", "name", "label", "why"}
        assert "1.1.1.27" in verdict.note and "2.7.1.1" in verdict.note
        assert "ecNumber 2.7.1.1" in verdict.note, "the re-run that would accept the name"
        assert "wrong protein" in verdict.note

    def test_a_number_among_an_ambiguous_names_readings_is_the_disambiguation(self, monkeypatch):
        # "lactate dehydrogenase" is twelve enzymes to the finder, and its
        # ambiguity refusal ends "re-run with ecNumber 1.1.1.27". That re-run
        # sends both; refusing it again would hand the person the same wall
        # they were just told how to get past. Equality with
        # `resolve_ec_number` (None for an ambiguous name) would do exactly
        # that, which is why the policy is membership.
        _offline(monkeypatch)
        for ec in ("1.1.1.27", "1.1.1.28"):
            verdict = science_agent_runner.check_ec_against_name("lactate dehydrogenase", "Homo sapiens", ec)
            assert verdict.agrees is True, ec
            assert verdict.checked is True
            assert ec in verdict.note

    def test_a_number_outside_an_ambiguous_names_readings_contradicts_it(self, monkeypatch):
        _offline(monkeypatch)
        verdict = science_agent_runner.check_ec_against_name("lactate dehydrogenase", "Homo sapiens", "2.7.1.1")
        assert verdict.agrees is False
        assert verdict.checked is True
        assert verdict.candidates[:2] == ["1.1.1.27", "1.1.1.28"]
        assert "2.7.1.1" not in verdict.candidates
        assert "2.7.1.1" in verdict.note and "1.1.1.27" in verdict.note
        assert "ecNumber 1.1.1.27" in verdict.note, "the finder's recommendation, for the re-run"

    def test_a_name_the_nomenclature_lacks_is_checked_against_uniprot(self, monkeypatch):
        # The same policy the name-only path uses: UniProt is asked only for
        # a name the nomenclature does not hold. "phosphofructokinase-1" is
        # the one such name in the API server's own enzyme table.
        _offline(monkeypatch, lambda name, taxon_id: ["2.7.1.11"])
        verdict = science_agent_runner.check_ec_against_name("phosphofructokinase-1", "Homo sapiens", "2.7.1.11")
        assert verdict.agrees is True
        assert verdict.checked is True

        _offline(monkeypatch, lambda name, taxon_id: ["3.1.1.7"])
        verdict = science_agent_runner.check_ec_against_name("phosphofructokinase-1", "Homo sapiens", "2.7.1.11")
        assert verdict.agrees is False
        assert verdict.candidates == ["3.1.1.7"]
        assert "2.7.1.11" in verdict.note and "3.1.1.7" in verdict.note

    def test_a_name_that_cannot_be_checked_does_not_contradict(self, monkeypatch):
        # A network failure is not evidence that the EC number is wrong. The
        # number stands, and the note says it was not checked rather than
        # saying nothing -- the reader can tell "confirmed" from "unchecked".
        def down(name, taxon_id):
            raise httpx.ConnectError("UniProt unreachable")

        _offline(monkeypatch, down)
        verdict = science_agent_runner.check_ec_against_name("not a real enzyme name", "", "2.7.1.1")
        assert verdict.agrees is True
        assert verdict.checked is False
        assert "unchecked" in verdict.note
        assert "lookup_failed" in verdict.note
        assert verdict.candidates == []

    def test_a_name_uniprot_does_not_know_does_not_contradict(self, monkeypatch):
        _offline(monkeypatch, lambda name, taxon_id: [])
        verdict = science_agent_runner.check_ec_against_name("not a real enzyme name", "", "2.7.1.1")
        assert verdict.agrees is True
        assert verdict.checked is False
        assert "unchecked" in verdict.note


class TestMainWithBothNameAndNumber:
    """The wire: what the TypeScript side receives for each outcome."""

    def test_agreement_is_silent_and_the_number_is_used(self, monkeypatch):
        # The common case: the golden request every contract test sends. Its
        # output must not change -- no new log line, the number as sent --
        # or every caller pays for a check that found nothing.
        seen = {}

        def resolve(*args, **kwargs):
            seen["ec"] = kwargs.get("enzyme_ec", args[3] if len(args) > 3 else None)
            return _golden()

        result = _run_main(
            monkeypatch,
            {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
             "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
            resolve=resolve,
        )
        assert result["found"] is True
        assert result["km"] == 10.73
        assert seen["ec"] == "1.1.1.27"
        assert result["logs"] == ["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"]

    def test_a_contradicting_name_is_refused_naming_both_numbers(self, monkeypatch):
        result = _run_main(
            monkeypatch,
            {"enzymeName": "hexokinase", "substrate": "lactate",
             "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
            resolve=_never,
        )
        assert result["ok"] is True
        assert result["found"] is False
        assert result["source"] == "ec_mismatch"
        # The golden SHAPE: the keys the ambiguity refusal already uses, so
        # the TypeScript side receives it with no new wire key (ADR 0027's
        # boundary guard reads every emitted key).
        assert set(result) == {
            "ok", "found", "source", "ecCandidates", "ecCandidateNames", "ecRefusal",
            "literatureCandidates", "logs",
        }
        assert result["ecCandidates"] == ["2.7.1.1"]
        assert result["ecCandidateNames"][0]["ec"] == "2.7.1.1"
        assert "1.1.1.27" in result["ecRefusal"] and "2.7.1.1" in result["ecRefusal"]
        assert result["ecRefusal"].endswith("or with the name of the enzyme EC 1.1.1.27 is.")
        assert result["logs"] == [result["ecRefusal"]]
        assert result["literatureCandidates"] == []

    def test_a_number_outside_an_ambiguous_name_is_refused_with_the_readings(self, monkeypatch):
        result = _run_main(
            monkeypatch,
            {"enzymeName": "lactate dehydrogenase", "organism": "Homo sapiens",
             "ecNumber": "2.7.1.1"},
            resolve=_never,
        )
        assert result["source"] == "ec_mismatch"
        assert result["ecCandidates"][:2] == ["1.1.1.27", "1.1.1.28"]
        assert len(result["ecCandidates"]) >= 2
        assert result["ecCandidateNames"][0]["ec"] == "1.1.1.27"
        assert "2.7.1.1" in result["ecRefusal"]
        assert "ecNumber 1.1.1.27" in result["ecRefusal"]

    def test_an_uncheckable_name_proceeds_and_says_so(self, monkeypatch):
        result = _run_main(
            monkeypatch,
            {"enzymeName": "not a real enzyme name", "substrate": "lactate",
             "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
            resolve=lambda *a, **k: _golden(),
            uniprot=lambda name, taxon_id: [],
        )
        assert result["found"] is True
        assert result["logs"][0].startswith("EC 1.1.1.27 is used as given, unchecked against the name")
        assert result["logs"][1] == "BRENDA exact: 1.1.1.27, Homo sapiens, lactate"

    def test_a_number_alone_asks_no_finder(self, monkeypatch):
        # Nothing to check a bare number against, and nothing is: the
        # check is replaced by an assertion that it was never called.
        monkeypatch.setattr(
            science_agent_runner, "check_ec_against_name",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no name, no check")),
        )
        result = _run_main(
            monkeypatch,
            {"ecNumber": "1.1.1.27", "substrate": "lactate", "organism": "Homo sapiens"},
            resolve=lambda *a, **k: _golden(),
        )
        assert result["found"] is True
        assert result["km"] == 10.73
