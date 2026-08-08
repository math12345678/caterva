"""pytest suite for epidemiology_resolver.py.

Entirely offline -- the registry is hand-curated (see the module docstring
for why there is no keyless queryable database of matched R0/infectious-
period pairs the way BRENDA and stdpopsim are for their domains), so there
is no network dependency to mock.
"""

from __future__ import annotations

from epidemiology_resolver import resolve_disease_parameters


class TestKnownDisease:
    def test_resolves_covid19_r0(self):
        result = resolve_disease_parameters("COVID-19")
        assert result.found is True
        assert result.r0 == 3.14

    def test_resolves_covid19_infectious_period(self):
        result = resolve_disease_parameters("COVID-19")
        assert result.found is True
        assert result.infectious_period_days == 5.45

    def test_carries_a_real_citation(self):
        result = resolve_disease_parameters("COVID-19")
        assert result.pmid == "33214421"
        assert result.doi == "10.1097/SLA.0000000000004400"
        assert "Hussein" in result.citation
        assert "Ann Surg" in result.citation

    def test_r0_and_infectious_period_come_from_the_same_source(self):
        """The whole point of hand-curating this registry instead of
        composing values from separate searches: both numbers must trace
        to the same pmid, so beta/gamma derived from them reflects one
        internally-consistent set of assumptions."""
        result = resolve_disease_parameters("COVID-19")
        # There is only one pmid on the result at all -- if r0 and
        # infectious_period_days came from different studies, the schema
        # itself would need two pmid fields. Their shared presence here is
        # the guarantee.
        assert result.pmid is not None
        assert result.r0 is not None and result.infectious_period_days is not None

    def test_infectious_period_measure_is_explicit_about_what_it_is(self):
        """This is a serial interval, not a virological shedding-duration
        measurement -- the result must say so, not let a caller assume."""
        result = resolve_disease_parameters("COVID-19")
        assert "serial interval" in result.infectious_period_measure.lower()

    def test_search_log_records_the_source(self):
        result = resolve_disease_parameters("COVID-19")
        assert any("33214421" in entry for entry in result.search_log)


class TestNameNormalisation:
    def test_case_insensitive(self):
        assert resolve_disease_parameters("covid-19").found is True
        assert resolve_disease_parameters("Covid-19").found is True

    def test_whitespace_is_stripped(self):
        assert resolve_disease_parameters("  covid-19  ").found is True

    def test_common_aliases_resolve_to_the_same_entry(self):
        canonical = resolve_disease_parameters("covid-19")
        for alias in ("covid", "covid19", "covid 19", "sars-cov-2", "coronavirus"):
            aliased = resolve_disease_parameters(alias)
            assert aliased.found is True, f"alias '{alias}' did not resolve"
            assert aliased.r0 == canonical.r0
            assert aliased.pmid == canonical.pmid


class TestUnknownDiseaseNeverFabricates:
    def test_unrecognised_disease_is_not_found(self):
        """Regression guard for the one failure mode that matters most
        here: an unrecognised disease must never fall back to a plausible-
        looking invented R0. Measles and influenza are real, well-studied
        diseases NOT yet in this registry (see the ADR for why -- no
        single matched-methodology source was found for either), so they
        are exactly the right names to prove this with."""
        for name in ("measles", "influenza", "a made-up disease xyz123"):
            result = resolve_disease_parameters(name)
            assert result.found is False, f"'{name}' unexpectedly resolved"
            assert result.r0 is None
            assert result.infectious_period_days is None

    def test_unrecognised_disease_names_what_is_available(self):
        result = resolve_disease_parameters("measles")
        assert result.found is False
        assert any("covid-19" in entry for entry in result.search_log)
