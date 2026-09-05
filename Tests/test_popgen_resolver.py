"""Tests for popgen_resolver.py - population genetics parameter resolution.

Golden tuple: Homo sapiens mutation_rate
- Value: ~1.29e-8 per bp per generation (stdpopsim HomSap)
- Source: stdpopsim catalog (compiled from published literature)
- Citation FOR THE RATE: Tian, Browning & Browning (2019),
  Am J Hum Genet 105(5):883-893, doi 10.1016/j.ajhg.2019.09.012 --
  the HomSap citation stdpopsim tags with reason 'mutation rate'.
  This docstring previously named IHGSC (2001) and Jónsson et al. (2017);
  checked against stdpopsim 0.3.0 on 2026-09-05, IHGSC is bundled for the
  GENOME ASSEMBLY and Jónsson is not in the HomSap catalog at all.

This test suite follows the Constitution's Section 6 verification procedure:
1. Golden tuple test: verify exact value against hand-verified citation
2. Edge cases: organism not in database, empty string, case insensitivity
3. Mutation test: break the resolver and confirm test catches it
"""

import pytest

# stdpopsim is a heavy, compiled-dependency optional package (declared in
# requirements.txt, but slow/nontrivial to install -- it pulls in msprime/
# tskit). Its absence is a legitimate, recoverable environment state, not a
# code bug: popgen_resolver.resolve_mutation_rate() already degrades
# gracefully at runtime (returns found=False with a clear search_log
# message) when the import fails. Without this guard, every test below
# hard-fails instead of skipping when the environment simply hasn't
# installed the optional dependency yet -- indistinguishable, from a CI
# summary, from an actual regression. Skip the whole module cleanly instead.
pytest.importorskip("stdpopsim", reason="stdpopsim not installed; see requirements.txt")

from popgen_resolver import resolve_mutation_rate, PopgenResult, _normalise_doi


class TestMutationRateGoldenTuple:
    """Golden tuple: Homo sapiens mutation rate from literature."""

    def test_human_mutation_rate_value(self):
        """Verify exact value against hand-verified citation."""
        result = resolve_mutation_rate("Homo sapiens")
        assert result.found is True
        assert result.value is not None
        # stdpopsim HomSap genome mean_mutation_rate: ~1.29e-8
        # Allow some tolerance since stdpopsim may update values
        assert 1.0e-8 <= result.value <= 2.0e-8, (
            f"Human mutation rate {result.value} is outside expected range"
        )

    def test_human_mutation_rate_organism(self):
        """Verify organism name is preserved."""
        result = resolve_mutation_rate("Homo sapiens")
        assert result.found is True
        assert result.organism is not None
        assert "Homo sapiens" in result.organism or "sapiens" in result.organism.lower()

    def test_human_mutation_rate_citation(self):
        """Verify citation is present."""
        result = resolve_mutation_rate("Homo sapiens")
        assert result.found is True
        assert result.citation is not None
        assert len(result.citation) > 0

    def test_human_mutation_rate_source(self):
        """Verify source is stdpopsim."""
        result = resolve_mutation_rate("Homo sapiens")
        assert result.found is True
        assert result.source == "stdpopsim"

    def test_structured_doi_is_the_paper_that_reports_the_rate(self):
        """The locator must point at the mutation-rate paper.

        This resolver used to surface the FIRST bundled DOI, which for
        HomSap is IHGSC (2001) -- bundled by stdpopsim for the GENOME
        ASSEMBLY, and reporting no mutation rate anywhere. That DOI became
        the structured locator for `mutation_rate`: the link a reader
        clicks to check 1.29e-8, landing them on a paper that does not
        contain it. "A real reference for a number it does not report" is
        the defect ADR 0162 is named after; this pins the second module it
        appeared in.

        Asserted both ways on purpose. Checking only that the DOI is
        Tian et al. would still pass if the selection logic were replaced
        by a hardcoded string, so the assembly paper is named explicitly
        as something the locator must NOT be.
        """
        result = resolve_mutation_rate("Homo sapiens")
        assert result.found is True
        # Tian, Browning & Browning (2019) -- stdpopsim's 'mutation rate'
        # citation for HomSap.
        assert result.doi == "10.1016/j.ajhg.2019.09.012"
        # IHGSC (2001), bundled for 'genome assembly'.
        assert result.doi != "10.1038/35057062"
        # HapMap (2007), bundled for 'recombination rate'.
        assert result.doi != "10.1038/nature06258"

    def test_doi_is_chosen_by_reason_not_by_position(self):
        """The mutation-rate citation is not first in stdpopsim's list.

        If it were, position-based selection would pass the test above by
        accident and the guard would prove nothing. This asserts the
        ordering that makes the previous test meaningful: the assembly
        paper genuinely comes first.
        """
        import stdpopsim

        citations = stdpopsim.get_species("HomSap").genome.citations
        assert len(citations) >= 2, "HomSap should bundle several citations"
        first_reasons = " ".join(str(r).lower() for r in citations[0].reasons)
        assert "mutation rate" not in first_reasons, (
            "stdpopsim's first HomSap citation now IS the mutation-rate "
            "paper, so this guard no longer distinguishes reason-based "
            "selection from first-wins. Re-point it at a species where it "
            "still does."
        )


class TestMutationRateOtherOrganisms:
    """Test other organisms in the database."""

    def test_mouse_mutation_rate(self):
        """Verify Mus musculus mutation rate."""
        result = resolve_mutation_rate("Mus musculus")
        assert result.found is True
        assert result.value is not None
        # Mouse mutation rate is typically lower than human
        assert 1.0e-9 <= result.value <= 1.0e-8

    def test_drosophila_mutation_rate(self):
        """Verify Drosophila melanogaster mutation rate."""
        result = resolve_mutation_rate("Drosophila melanogaster")
        assert result.found is True
        assert result.value is not None
        # Drosophila mutation rate
        assert 1.0e-9 <= result.value <= 1.0e-8

    def test_human_via_common_name(self):
        """Verify human can be looked up via common name."""
        result = resolve_mutation_rate("human")
        assert result.found is True
        assert result.value is not None


class TestMutationRateEdgeCases:
    """Edge cases and error handling."""

    def test_unknown_organism_returns_not_found(self):
        """Organism not in database returns found=False, not a fabricated value."""
        result = resolve_mutation_rate("Escherichia coli")
        # E. coli might or might not be in stdpopsim
        # The important thing is it doesn't crash
        assert isinstance(result, PopgenResult)

    def test_empty_string_returns_not_found(self):
        """Empty string returns found=False."""
        result = resolve_mutation_rate("")
        assert result.found is False

    def test_case_insensitive(self):
        """Lookup is case-insensitive."""
        result = resolve_mutation_rate("homo sapiens")
        assert result.found is True
        assert result.value is not None

    def test_whitespace_handling(self):
        """Leading/trailing whitespace is stripped."""
        result = resolve_mutation_rate("  Homo sapiens  ")
        assert result.found is True
        assert result.value is not None

    def test_result_is_valid_model(self):
        """Result is a valid Pydantic model."""
        result = resolve_mutation_rate("Homo sapiens")
        assert isinstance(result, PopgenResult)
        # Should be JSON-serializable
        json_str = result.model_dump_json()
        assert len(json_str) > 0


class TestNormaliseDoi:
    """stdpopsim bundles its reference DOIs in inconsistent shapes; the
    normaliser must strip every URL prefix so the emitted locator is a
    single resolvable DOI -- never a double-prefixed
    ``https://doi.org/http://dx.doi.org/...`` string (literature locators
    must be verifiable, Constitution Rule 2)."""

    def test_bare_doi_passes_through(self):
        assert _normalise_doi("10.1038/35057062") == "10.1038/35057062"

    def test_https_doi_org_prefix_is_stripped(self):
        assert _normalise_doi("https://doi.org/10.1016/j.ajhg.2019.09.012") == "10.1016/j.ajhg.2019.09.012"

    def test_http_dx_doi_org_prefix_is_stripped(self):
        assert _normalise_doi("http://dx.doi.org/10.1038/nature06258") == "10.1038/nature06258"

    def test_non_doi_string_returns_none(self):
        assert _normalise_doi("Smith, J. (2020) Some paper") is None

    def test_empty_string_returns_none(self):
        assert _normalise_doi("") is None


class TestMutationRateMutationTest:
    """Mutation test: break the resolver and confirm test catches it."""

    def test_mutation_rate_is_positive(self):
        """All mutation rates must be positive (biological constraint)."""
        result = resolve_mutation_rate("Homo sapiens")
        if result.found:
            assert result.value > 0, "Mutation rate must be positive"

    def test_mutation_rate_is_plausible(self):
        """Mutation rate must be in plausible range (1e-10 to 1e-6 per bp per generation)."""
        result = resolve_mutation_rate("Homo sapiens")
        if result.found:
            assert 1e-10 <= result.value <= 1e-6, (
                f"Mutation rate {result.value} is outside plausible range"
            )
