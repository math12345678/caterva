"""`compose --subject` searches the literature, and says what it found.

WHY THESE TESTS
---------------
Terrium's claim is that every number traces to where it came from, and
until ADR 0178 a composed model could not carry a measured value at all:
`parameter_requests()` built requests without the `ec_number`, `substrate`
and `organism` fields BRENDA requires, and the scouts that would have used
them failed on an import while the search reported `converged=True`.

What these pin is the join, offline. The resolver is replaced with a stub,
so no network is touched and no BRENDA row is asserted here -- the live
values and their reference numbers are recorded in ADR 0178. What must not
regress is the wiring and, above all, the HONESTY of a partial result:
BRENDA has a Km for acetylcholinesterase and no kcat, so a model whose Km
resolved and whose kcat did not is the normal case, and it must never
present the placeholder as though a paper stood behind it.
"""
from __future__ import annotations

import pytest

from Terium.compose.export import Measurement
from Terium.compose.pipeline import compose

QUERY = "Michaelis-Menten with a competitive inhibitor"


def test_a_model_with_no_subject_asks_for_nothing():
    """No subject means no search, and an empty request list is a decision."""
    model = compose(QUERY)
    assert model.structure_only is True
    assert model.parameter_requests() == []
    assert model.searched is False


def test_the_requests_carry_what_brenda_requires():
    """The three fields that used to be left empty (ADR 0178)."""
    model = compose(QUERY, subject="1.1.1.27", organism="Homo sapiens",
                    substrate="pyruvate")
    requests = model.parameter_requests()
    assert requests, "a named subject with resolvable constants must ask for them"
    for request in requests:
        assert request.ec_number == "1.1.1.27", "the scout cannot reach BRENDA without it"
        assert request.substrate == "pyruvate", "km and ki are per-substrate"
        assert request.organism == "Homo sapiens"
        assert request.table in ("km", "ki", "kcat")
        assert request.expected_unit, "no unit means no unit check at substitution"


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("1.1.1.27", "1.1.1.27"),
        ("  1.1.1.27  ", "1.1.1.27"),
        ("1.1.1.-", "1.1.1.-"),
        ("lactate dehydrogenase", None),
        ("1.1.1", None),
        ("1.1.1.27.4", None),
        ("", None),
    ],
)
def test_only_an_ec_number_is_treated_as_one(subject, expected):
    """A NAME IS NOT AN ENZYME.

    'lactate dehydrogenase' is EC 1.1.1.27 and 1.1.1.28 and four more.
    Resolving it here would attach a citation to the wrong protein, so a
    name returns None and the caller asks the literature layer, which
    refuses ambiguity by naming every candidate.
    """
    assert compose(QUERY, subject=subject or None).ec_number == expected


def test_a_partial_search_stays_partial():
    """THE CASE THAT ACTUALLY OCCURS.

    BRENDA has a Km for acetylcholinesterase and no kcat. A model that
    substituted the Km and left kcat at the library's placeholder without
    saying so would simulate, plot, and look exactly like a sourced one.
    """
    model = compose(QUERY, subject="1.1.1.27", substrate="pyruvate")
    measured = {
        "reaction_Km": Measurement(
            value=0.03, unit="mM", citation="BRENDA ref 286469",
            organism="Homo sapiens",
        ),
    }
    sourced = model.with_measured(measured)

    assert sourced.searched is True
    assert "reaction_Km" not in sourced.unmeasured, "it was measured"
    assert "reaction_kcat" in sourced.unmeasured, "it was not, and must still say so"
    values = {p.id: p.value for p in sourced.network.parameters}
    assert values["reaction_Km"] == 0.03, "the literature's value must reach the network"
    assert values["reaction_kcat"] == 100.0, "the placeholder must be left alone, not invented"


def test_the_original_model_is_not_mutated():
    """`with_measured` returns a new model; the unsourced one stays unsourced."""
    model = compose(QUERY, subject="1.1.1.27", substrate="pyruvate")
    before = {p.id: p.value for p in model.network.parameters}
    model.with_measured(
        {"reaction_Km": Measurement(value=0.03, unit="mM", citation="BRENDA ref 286469")}
    )
    assert {p.id: p.value for p in model.network.parameters} == before
    assert model.searched is False


def test_an_empty_search_result_changes_nothing():
    """A search that found nothing must not look like a search that was not run."""
    model = compose(QUERY, subject="1.1.1.27", substrate="pyruvate")
    assert model.with_measured({}) is model


def test_the_report_names_every_source_and_every_remaining_placeholder():
    """The reader must never have to work out which numbers a paper backs."""
    from Terium.compose.report import dossier

    model = compose(QUERY, subject="1.1.1.27", organism="Homo sapiens",
                    substrate="pyruvate").with_measured({
        "reaction_Km": Measurement(
            value=0.03, unit="mM", citation="BRENDA ref 286469",
            organism="Homo sapiens",
        ),
    })
    report = dossier(QUERY, subject="1.1.1.27", model=model,
                     analyse_stability=False, simulate=False,
                     rank_unmeasured=False)
    text = "\n".join(report.provenance_section())

    assert "came from the literature" in text
    assert "BRENDA ref 286469" in text, "a value without its citation is not a measurement"
    assert "0.03 mM" in text
    assert "**placeholder**" in text, "the unresolved constant must be marked"
    assert "reaction_kcat" in text
    assert "searched the kcat table and found nothing" in text, (
        "'looked for and not found' and 'not looked for' are different facts"
    )
    assert "no search was run" not in text


class TestTheCitationTheAgentStackProduces:
    """`citation_text` read a field the `Citation` class does not have.

    THE DEFECT (ADR 0178). It looked for `reference`; `Tests/citation.py`
    declares `reference_id`. The attribute never existed, so every BRENDA
    citation fell through to `url` -- which names the ENZYME PAGE, not the
    reference. Two measurements from two different papers produced the
    identical string, and BRENDA has no working per-reference deep link, so
    the reference id was the only thing identifying which row a number came
    from. The test fixtures invented the same non-existent field, so the
    stub and the bug agreed and the suite stayed green.
    """

    @staticmethod
    def _citation(**fields):
        return type("Citation", (), {
            "source": None, "reference_id": None, "url": None, "title": None,
            **fields,
        })()

    def test_two_papers_do_not_produce_one_string(self):
        from Terium.agents.adapters import citation_text

        page = "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"
        first = citation_text(self._citation(source="BRENDA", reference_id="286469", url=page))
        second = citation_text(self._citation(source="BRENDA", reference_id="739793", url=page))
        assert first == "BRENDA ref 286469"
        assert second == "BRENDA ref 739793"
        assert first != second, (
            "both rows are on the same enzyme page; the reference id is the "
            "only thing that tells them apart"
        )

    def test_it_matches_the_lab_report_s_form(self):
        """Terrium has two paths to a citation and they must read alike."""
        from Terium.agents.adapters import citation_text

        assert citation_text(
            self._citation(source="BRENDA", reference_id="286469")
        ) == "BRENDA ref 286469"

    def test_a_title_is_kept_when_there_is_one(self):
        from Terium.agents.adapters import citation_text

        text = citation_text(
            self._citation(source="PubMed", reference_id="12345", title="A paper")
        )
        assert "PubMed ref 12345" in text and "A paper" in text

    def test_it_still_falls_back_rather_than_losing_the_citation(self):
        from Terium.agents.adapters import citation_text

        assert citation_text(self._citation(url="https://example.org")) == "url:https://example.org"
        assert citation_text(None) is None


class TestTheRowsTheResolverDidNotPick:
    """A model must carry the values its own resolver ranked equal.

    THE GAP (found after the wiring landed). BRENDA holds two equally well
    evidenced values of Km for EC 1.1.1.27 and pyruvate in Homo sapiens:
    0.03 mM and 0.398 mM, a 13-fold range. The resolver picks the lower and
    says the evidence does not justify picking. The composed report printed
    the winner with its citation and stopped -- presenting one paper's
    number as THE value, with a reference attached to make it look more
    settled than the placeholder case, not less.

    The lab-report path had printed this since it was written. These pin
    that the composed model does too, and that it does not invent a
    controversy where one paper reports two rows.
    """

    @staticmethod
    def _measurement(value, alternatives, unit="mM"):
        return Measurement(
            value=value, unit=unit, citation="BRENDA ref 286469",
            organism="Homo sapiens", alternatives=tuple(alternatives),
        )

    def test_agreement_is_not_reported_as_disagreement(self):
        assert self._measurement(0.03, []).disagreement is None
        assert self._measurement(
            0.03, [{"value": 0.03, "reference_id": "1"}]
        ).disagreement is None

    def test_the_span_covers_the_chosen_value_and_every_alternative(self):
        record = self._measurement(0.03, [
            {"value": 0.03, "reference_id": "286469"},
            {"value": 0.398, "reference_id": "286442"},
        ])
        assert record.disagreement == (0.03, 0.398)

    def test_a_malformed_row_does_not_lose_the_others(self):
        """A resolver row with no value must not silence the disagreement."""
        record = self._measurement(0.03, [
            {"organism": "Homo sapiens"},
            {"value": "not a number"},
            {"value": 0.398, "reference_id": "286442"},
        ])
        assert record.disagreement == (0.03, 0.398)

    def _section(self, measured):
        from Terium.compose.report import dossier

        model = compose(QUERY, subject="1.1.1.27", organism="Homo sapiens",
                        substrate="pyruvate").with_measured(measured)
        report = dossier(QUERY, subject="1.1.1.27", model=model,
                         analyse_stability=False, simulate=False,
                         rank_unmeasured=False)
        return "\n".join(report.provenance_section())

    def test_two_papers_are_reported_as_two_papers(self):
        text = self._section({"reaction_Km": self._measurement(0.03, [
            {"value": 0.03, "reference_id": "286469"},
            {"value": 0.398, "reference_id": "286442"},
        ])})
        assert "did not settle on one value" in text
        assert "2 sources report 2 values" in text
        assert "0.03 to 0.398 mM" in text and "13.3-fold" in text
        assert "not an uncertainty estimate" in text
        assert "286442" in text and "286469" in text

    def test_one_paper_with_two_rows_is_not_called_a_disagreement(self):
        """Sending a reader to one paper to adjudicate itself is nonsense."""
        text = self._section({"reaction_Km": self._measurement(0.00059, [
            {"value": 0.00059, "reference_id": "739793"},
            {"value": 0.00252, "reference_id": "739793"},
        ])})
        assert "one source (BRENDA ref 739793) reports 2 values" in text
        assert "which one is right is a question about the papers" not in text
        assert "read that paper before choosing" in text

    def test_a_settled_value_gets_no_section_at_all(self):
        text = self._section({"reaction_Km": self._measurement(0.03, [])})
        assert "did not settle on one value" not in text
        assert "BRENDA ref 286469" in text, "the measurement is still reported"

    def test_the_conversion_carries_them_off_the_resolver(self):
        """The boundary the rows were actually being dropped at.

        Every other test in this class builds a `Measurement` by hand with
        `alternatives=` already set, so they pin the RENDERING and would all
        pass with the conversion returning nothing -- which is precisely the
        defect. Measured: emptying `alternatives` in `measured_from_search`
        failed none of them. This one goes through the conversion.
        """
        from Terium.compose.export import measured_from_search

        rows = (
            {"value": 0.03, "unit": "mM", "organism": "Homo sapiens", "reference_id": "286469"},
            {"value": 0.398, "unit": "mM", "organism": "Homo sapiens", "reference_id": "286442"},
        )
        source = type("ParameterSource", (), {
            "value": 0.03, "unit": "mM", "organism": "Homo sapiens",
            "citation": "BRENDA ref 286469", "origin": "literature",
            "cross_species": False, "ph": None, "temperature_c": None,
            "buffer": None, "explicitly_unreported": (),
            "candidates": rows,
        })()
        resolution = type("Resolution", (), {"source": source})()
        build = type("Build", (), {"resolutions": {"reaction_Km": resolution}})()

        measured = measured_from_search(build)
        record = measured["reaction_Km"]
        assert record.alternatives == rows, (
            "the rows the resolver ranked and did not pick must survive the "
            "conversion, or the report has nothing to disagree about"
        )
        assert record.disagreement == (0.03, 0.398)
