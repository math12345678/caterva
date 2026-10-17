"""The exports carry claim ids when given them, and not one byte otherwise.

`caterva compose --claims DIR` hands the writers an identifier -> claim ref
map (ADR 0179). The CSV then gains a final `claim_id` column, the SBML
notes a `CLAIM <ref>` line per quantity, the Antimony a `# claim: <ref>`
comment on each assignment's trailer, the methods paragraph a closing
list. With `claim_ids=None`, the default, each writer must emit exactly
what it emitted before claims existed: the first test here pins that, and
the others show the ids are the ONLY difference by removing them from the
with-ids artefact and comparing.

The claim refs here are stand-ins of the right shape (a digest of the
identifier), because these tests are about the writers, not the bundle;
`test_compose_claims.py` runs the real thing.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re

import pytest

from caterva.compose.__main__ import export_texts
from caterva.compose.export import (
    CLAIM_COLUMN,
    CLAIM_NOTE,
    CSV_COLUMNS,
    Measurement,
    _antimony_source,
    provenance_of,
    to_antimony,
    to_methods_paragraph,
    to_parameter_csv,
    to_sbml,
)
from caterva.compose.pipeline import compose
from caterva.core.model_provenance import strip_annotations
from caterva.core.sbml_provenance import audit_annotations

WRITERS = (to_parameter_csv, to_antimony, to_sbml, to_methods_paragraph)

#: What a claim ref looks like in the artefacts, for stripping it back out.
_REF = r"claim:sha256:[0-9a-f]{64}"


def _stand_in(identifier: str) -> str:
    return "claim:sha256:" + hashlib.sha256(identifier.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def model():
    """A Michaelis-Menten model with one measured constant, one placeholder
    and three chosen starting amounts, so every origin is exported."""
    composed = compose("Michaelis Menten", subject="2.7.1.1", organism="Homo sapiens",
                       substrate="glucose")
    provenanced = provenance_of(composed, measured={
        "reaction_Km": Measurement(
            value=6.0, unit="mM", citation="BRENDA ref 641068", organism="Homo sapiens",
            source="literature", assay_ph=7.5, assay_temperature_c=30.0,
            commentary="30°C, pH 7.5, wild-type",
        ),
    })
    assert {o.origin for o in provenanced.origins} == {"measured", "placeholder", "chosen"}
    return provenanced


@pytest.fixture(scope="module")
def ids(model):
    return {o.identifier: _stand_in(o.identifier) for o in model.origins}


# ---------------------------------------------------------------------------
# Without ids, nothing changes
# ---------------------------------------------------------------------------

class TestWithoutIdsEveryByteIsWhatItWas:
    @pytest.mark.parametrize("writer", WRITERS, ids=lambda w: w.__name__)
    def test_none_is_the_default_and_means_the_old_artefact(self, model, writer):
        plain = writer(model)
        assert plain == writer(model, claim_ids=None)
        assert "claim:sha256:" not in plain

    def test_the_csv_columns_constant_is_untouched(self):
        assert len(CSV_COLUMNS) == 27
        assert CSV_COLUMNS[-1] == "provenance"
        assert CLAIM_COLUMN not in CSV_COLUMNS

    def test_the_csv_with_ids_is_the_plain_csv_plus_one_column(self, model, ids):
        plain = list(csv.reader(io.StringIO(to_parameter_csv(model))))
        with_ids = list(csv.reader(io.StringIO(to_parameter_csv(model, claim_ids=ids))))
        assert [row[:-1] for row in with_ids] == plain
        assert len(with_ids) == len(plain) >= 5

    def test_the_antimony_with_ids_is_the_plain_antimony_plus_the_comments(self, model, ids):
        with_ids = to_antimony(model, claim_ids=ids)
        assert with_ids != to_antimony(model)
        assert re.sub(rf"  # claim: {_REF}", "", with_ids) == to_antimony(model)

    def test_the_sbml_with_ids_is_the_plain_sbml_plus_the_claim_lines(self, model, ids):
        with_ids = to_sbml(model, claim_ids=ids)
        lines = [line for line in with_ids.splitlines() if f"{CLAIM_NOTE} claim:sha256:" not in line]
        assert "\n".join(lines) + "\n" == to_sbml(model)
        assert len(with_ids.splitlines()) - len(lines) == len(ids)

    def test_the_methods_with_ids_is_the_plain_paragraph_plus_a_closing_one(self, model, ids):
        plain = to_methods_paragraph(model)
        with_ids = to_methods_paragraph(model, claim_ids=ids)
        assert with_ids.startswith(plain)
        assert "re-checkable offline with `caterva verify`" in with_ids[len(plain):]


# ---------------------------------------------------------------------------
# With ids, each artefact carries them where its format can
# ---------------------------------------------------------------------------

class TestTheCsv:
    def test_the_header_gains_one_final_claim_id_column(self, model, ids):
        rows = list(csv.reader(io.StringIO(to_parameter_csv(model, claim_ids=ids))))
        assert rows[0] == [*CSV_COLUMNS, CLAIM_COLUMN]
        assert len(rows[0]) == 28

    def test_every_row_carries_its_quantity_s_ref(self, model, ids):
        rows = list(csv.DictReader(io.StringIO(to_parameter_csv(model, claim_ids=ids))))
        assert {row["identifier"] for row in rows} == set(ids)
        for row in rows:
            assert row[CLAIM_COLUMN] == ids[row["identifier"]]

    def test_a_quantity_the_map_does_not_name_gets_an_empty_cell_not_an_invented_ref(self, model, ids):
        partial = {"reaction_Km": ids["reaction_Km"]}
        rows = list(csv.DictReader(io.StringIO(to_parameter_csv(model, claim_ids=partial))))
        cells = {row["identifier"]: row[CLAIM_COLUMN] for row in rows}
        assert cells["reaction_Km"] == ids["reaction_Km"]
        assert cells["reaction_kcat"] == ""
        assert cells["reaction_S"] == ""


class TestTheAntimony:
    def test_each_assignment_s_trailer_ends_with_its_claim(self, model, ids):
        text = to_antimony(model, claim_ids=ids)
        found = {}
        for line in text.splitlines():
            match = re.match(r"^\s*([A-Za-z_]\w*)\s*=\s*[^;]+;\s+//.*  # claim: (\S+)$", line)
            if match:
                found[match.group(1)] = match.group(2)
        assert found == ids

    def test_the_comments_change_no_value(self, model, ids):
        assert strip_annotations(to_antimony(model, claim_ids=ids)) == _antimony_source(model)

    def test_the_comment_carries_none_of_the_unsourced_markers(self, model, ids):
        from caterva.core.model_provenance import unsourced_parameters

        plain = to_antimony(model)
        with_ids = to_antimony(model, claim_ids=ids)
        assert unsourced_parameters(with_ids) == unsourced_parameters(plain)


class TestTheSbml:
    def test_each_parameter_s_notes_carry_one_claim_line(self, model, ids):
        import libsbml

        document = libsbml.readSBMLFromString(to_sbml(model, claim_ids=ids))
        sbml_model = document.getModel()
        parameters = [sbml_model.getParameter(i) for i in range(sbml_model.getNumParameters())]
        assert {p.getId() for p in parameters} == {"reaction_Km", "reaction_kcat"}
        for parameter in parameters:
            notes = parameter.getNotesString()
            assert notes.count(f"{CLAIM_NOTE} {ids[parameter.getId()]}") == 1
            # Inside the notes the annotator wrote, not in place of them.
            assert "Source: BRENDA ref 641068" in notes or "Default, not sourced" in notes

    def test_each_species_notes_carry_one_claim_line(self, model, ids):
        import libsbml

        document = libsbml.readSBMLFromString(to_sbml(model, claim_ids=ids))
        sbml_model = document.getModel()
        species = [sbml_model.getSpecies(i) for i in range(sbml_model.getNumSpecies())]
        assert {s.getId() for s in species} == {"reaction_S", "reaction_P", "reaction_E"}
        for one in species:
            assert one.getNotesString().count(f"{CLAIM_NOTE} {ids[one.getId()]}") == 1

    def test_the_ids_are_notes_and_mint_no_rdf(self, model, ids):
        plain = audit_annotations(to_sbml(model))
        with_ids = audit_annotations(to_sbml(model, claim_ids=ids))
        assert with_ids.ok
        assert len(with_ids.triples) == len(plain.triples)


class TestTheMethodsParagraph:
    def test_the_closing_paragraph_names_every_quantity_s_ref(self, model, ids):
        text = to_methods_paragraph(model, claim_ids=ids)
        for identifier, ref in ids.items():
            assert f"`{identifier}` {ref}" in text


class TestExportTexts:
    def test_the_ids_reach_every_format_through_the_one_function(self, model, ids):
        texts = export_texts(model, claim_ids=ids)
        assert set(texts) == {"sbml", "antimony", "csv", "methods"}
        for fmt, (text, refused) in texts.items():
            assert refused is None, (fmt, refused)
            assert ids["reaction_Km"] in text, fmt

    def test_without_ids_the_one_function_gives_the_old_artefacts(self, model):
        texts = export_texts(model)
        assert texts["csv"][0] == to_parameter_csv(model)
        assert texts["antimony"][0] == to_antimony(model)
