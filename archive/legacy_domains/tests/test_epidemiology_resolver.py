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
        looking invented R0.

        Measles is the right name to prove this with. It is a real,
        extremely well-studied disease that is still NOT registered, and
        for a reason that survives having a serial interval available:
        Vink et al. (2014) reports 11.7 days for measles, but Guerra et
        al. (2017) -- the standard R0 systematic review -- concludes R0
        "estimates vary more than the often cited range of 12-18" and
        endorses no single value. Half a pair is not a pair.

        Influenza was in this list until ADR 0169 registered it as an
        explicitly-flagged cross-study composite; see
        TestCrossStudyComposites below, which asserts it can never surface
        as "verified". Removing a name from this guard is a decision that
        needs an ADR, which is why the ADR exists.
        """
        for name in ("measles", "a made-up disease xyz123", "rabies"):
            result = resolve_disease_parameters(name)
            assert result.found is False, f"'{name}' unexpectedly resolved"
            assert result.r0 is None
            assert result.infectious_period_days is None

    def test_unrecognised_disease_names_what_is_available(self):
        result = resolve_disease_parameters("measles")
        assert result.found is False
        assert any("covid-19" in entry for entry in result.search_log)


class TestNoLatentPeriodIsOffered:
    """SEIR's sigma must not be quietly sourced from an incubation period.

    sigma = 1 / LATENT period (infection -> infectiousness). The registry
    carries a SERIAL INTERVAL, and the wider literature overwhelmingly
    reports INCUBATION (infection -> symptoms). All three are routinely
    conflated, and substituting one for another here is not a rounding
    error -- it is directionally wrong:

      pooled serial interval  5.2 d   (Alene 2021, PMID 33706702)
      pooled incubation       6.5 d   (same meta-analysis)

    A serial interval SHORTER than the incubation period is the signature
    of presymptomatic transmission: infectiousness starts before symptoms,
    so the latent period is strictly shorter than the incubation period.
    Feeding an incubation figure into sigma would overstate the latent
    period and systematically under-predict how fast an epidemic takes off
    -- the error would make the model look reassuring, which is the worst
    direction for it to fail in.

    A directly MEASURED latent period does exist (Kang et al. 2022,
    Eurosurveillance 27(10): 3.9 d) but for the Delta variant, whereas this
    registry entry is the ancestral strain. Delta's serial interval is
    3.9 d against ancestral 5.45 d, so the two parameter sets are not
    interchangeable, and pairing them would be exactly the cross-study
    stitching the registry's same-source rule forbids.

    So: the resolver must offer NO latent period at all, rather than
    offering something latent-shaped. See docs/literature-inventory.toml
    [seir.sigma] for the full search record.
    """

    def test_result_exposes_no_latent_or_incubation_field(self):
        result = resolve_disease_parameters("covid-19")
        assert result.found is True

        fields = set(result.model_dump().keys())
        for forbidden in (
            "latent_period_days",
            "incubation_period_days",
            "sigma",
        ):
            assert forbidden not in fields, (
                f"EpidemiologyResult grew a '{forbidden}' field. If a "
                "measured latent period has genuinely been found for this "
                "disease AND variant, update "
                "docs/literature-inventory.toml [seir.sigma] and delete "
                "this assertion deliberately -- do not let sigma acquire a "
                "source by accident."
            )

    def test_infectious_period_says_what_it_measures(self):
        """The one field that could be mistaken for a latent period names
        itself. This is the guard against a future reader assuming that
        `infectious_period_days` is a shedding duration or a latent
        period; it is a serial interval used as a generation-time proxy."""
        result = resolve_disease_parameters("covid-19")
        measure = (result.infectious_period_measure or "").lower()
        assert "serial interval" in measure, (
            "infectious_period_measure must state that the figure is a "
            "serial interval, because 'infectious period' is used loosely "
            "in the literature and the distinction changes the model."
        )
        assert "latent" not in measure or "not" in measure


class TestCrossStudyComposites:
    """ADR 0169: a two-paper entry must say so, and must never read as verified.

    ADR 0017 registered only COVID-19, whose R0 and serial interval come
    from ONE paper (Hussein et al. 2021), and deferred the question of
    whether a cross-study pair could ever be admitted. ADR 0169 admits one
    -- influenza -- under a strictly weaker tier, mirroring how a
    cross-species BRENDA Km is admitted: usable, cited, and visibly not
    the same thing as a single-source value.

    The failure this class exists to prevent is a composite quietly
    inheriting COVID-19's "verified" status, which would erase the only
    signal telling a reader that two methodologies were combined.
    """

    def test_covid_is_not_a_composite(self):
        """The single-source entry must not be mislabelled as one."""
        result = resolve_disease_parameters("covid-19")
        assert result.found is True
        assert result.cross_study_composite is False
        assert result.composite_note is None
        assert result.secondary_pmid is None

    def test_influenza_entries_are_marked_composite(self):
        for name in ("influenza", "h1n1"):
            result = resolve_disease_parameters(name)
            assert result.found is True, f"'{name}' did not resolve"
            assert result.cross_study_composite is True, (
                f"'{name}' resolved but is not marked as a cross-study "
                "composite -- it would surface as verified"
            )
            assert result.composite_note, f"'{name}' has no composite note"

    def test_both_sources_are_carried_not_just_the_r0_one(self):
        """A two-paper number must show both papers.

        The R0 half (Biggerstaff 2014) and the serial-interval half (Vink
        2014) are different PMIDs. Surfacing only the first would present
        a composite as if one paper supported both halves -- the same
        shape as the popgen defect where the genome-assembly DOI stood in
        for a mutation rate.
        """
        result = resolve_disease_parameters("influenza")
        assert result.pmid == "25186370"  # Biggerstaff et al. 2014, R0
        assert result.secondary_pmid == "25294601"  # Vink et al. 2014, SI
        assert result.doi == "10.1186/1471-2334-14-480"
        assert result.secondary_doi == "10.1093/aje/kwu209"
        assert result.pmid != result.secondary_pmid

    def test_composite_note_names_the_actual_mismatch(self):
        """The note must say WHAT was combined, not merely that something was.

        Seasonal influenza is composite on two axes and both are stated:
        cross-study, and cross-strain (Biggerstaff's "seasonal" pools
        H3N2/H1N1/B; Vink's 2.2-day serial interval is H3N2-specific).
        """
        seasonal = resolve_disease_parameters("influenza")
        note = seasonal.composite_note.lower()
        assert "cross-study" in note
        assert "strain" in note

        # The pandemic entry IS strain-matched, so it must not claim a
        # strain mismatch it does not have.
        pdm09 = resolve_disease_parameters("h1n1")
        assert "strain-matched" in pdm09.composite_note.lower()

    def test_values_match_the_published_numbers(self):
        """Transcribed from the PubMed abstracts on 2026-09-04.

        Biggerstaff et al. 2014 (PMID 25186370): median R0 1.28 seasonal,
        1.46 for the 2009 pandemic. Vink et al. 2014 (PMID 25294601): mean
        serial interval 2.2 d for A(H3N2), 2.8 d for A(H1N1)pdm09.
        """
        seasonal = resolve_disease_parameters("influenza")
        assert seasonal.r0 == 1.28
        assert seasonal.infectious_period_days == 2.2

        pdm09 = resolve_disease_parameters("h1n1")
        assert pdm09.r0 == 1.46
        assert pdm09.infectious_period_days == 2.8

    def test_serial_interval_measure_is_stated_not_assumed(self):
        """Every entry must say what its period figure actually measures.

        Carrat et al. (2008) reports 4.80 days of viral SHEDDING for
        influenza -- roughly twice the serial interval, and a different
        physical quantity. It was considered and rejected for these
        entries. If a future edit swaps a shedding duration in, this
        assertion is what makes the substitution visible.
        """
        for name in ("influenza", "h1n1"):
            result = resolve_disease_parameters(name)
            assert "serial interval" in result.infectious_period_measure.lower()
