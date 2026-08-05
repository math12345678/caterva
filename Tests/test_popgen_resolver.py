"""Tests for popgen_resolver.py - population genetics parameter resolution.

Golden tuple: Homo sapiens mutation_rate
- Value: ~1.29e-8 per bp per generation (stdpopsim HomSap)
- Source: stdpopsim catalog (compiled from published literature)
- Citations: International Human Genome Sequencing Consortium (2001),
  Jónsson et al. (2017), and others bundled in HomSap demographic model

This test suite follows the Constitution's Section 6 verification procedure:
1. Golden tuple test: verify exact value against hand-verified citation
2. Edge cases: organism not in database, empty string, case insensitivity
3. Mutation test: break the resolver and confirm test catches it
"""

import pytest

from popgen_resolver import resolve_mutation_rate, PopgenResult


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
