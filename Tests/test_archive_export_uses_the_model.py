"""The export script must derive the recorded species, not restate them.

A mutation survived the unit suite: putting `recorded = ["S", "P"]` back
into `scripts/export_annotated_model.py` broke nothing, because every test
in `caterva/tests/test_combine_archive.py` calls `build_sedml()` directly and
passes its own list. The unit tests pin the *builder*; nothing pinned the
*call site*.

That is the parity-test lesson in its exact form — "a parity test pins two
implementations against a shared fixture; it says nothing about a call site
that hands one of them different arguments" — and it recurred inside the
work that was fixing a hardcoded list.

So this drives the real `build_archive()` on competitive inhibition, whose
species are S and P and whose inhibitor is a fixed parameter. A hardcoded
list naming the inhibitor produces a report naming a species the model does
not have, and the archive still opens and still runs. (It drove SIR until
that domain was archived on 2026-09-27.)
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
libsedml = pytest.importorskip("libsedml")


def load_exporter():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(
        "export_annotated_model", REPO / "scripts" / "export_annotated_model.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exporter():
    return load_exporter()


# Competitive inhibition rather than plain Michaelis-Menten: a model whose
# report is not the one a hardcoded MM list would produce. (These tests used
# SIR until it was archived on 2026-09-27.)
MMCI_PAYLOAD = {
    "domain": "mm_competitive_inhibition",
    "format": "omex",
    "parameters": {"km": 2.5, "vmax": 5.0, "ki": 1.2, "s0": 10.0, "i": 0.5},
    "endTime": 20.0,
    "points": 101,
    "provenance": {},
}


def report_labels(archive_bytes: bytes, tmp_path: Path) -> set[str]:
    destination = tmp_path / "run.omex"
    destination.write_bytes(archive_bytes)
    with zipfile.ZipFile(destination) as opened:
        document = libsedml.readSedMLFromString(
            opened.read("simulation.sedml").decode()
        )
    report = document.getOutput(0)
    return {report.getDataSet(i).getLabel() for i in range(report.getNumDataSets())}


class TestTheExportScriptReadsTheModel:
    def test_an_inhibition_archive_reports_the_model_species_and_flux(self, exporter, tmp_path):
        code, data, detail = exporter.build_archive(dict(MMCI_PAYLOAD))
        assert code == 0, detail.get("error")

        # J0 is the model's one reaction; its flux is recorded alongside the
        # species. The inhibitor is a fixed parameter, not a species, so it
        # must NOT appear -- a list written at the call site would add it.
        labels = report_labels(data, tmp_path)
        assert labels == {"time", "S", "P", "J0"}, (
            "the SED-ML report does not match the model; a hardcoded list at "
            "the call site would look exactly like this"
        )

    def test_the_payload_cannot_override_the_model(self, exporter, tmp_path):
        """A caller-supplied list must not be honoured.

        Two statements of one fact is the duplicate-source-of-truth defect,
        and here the model is unambiguously the authority: it is the thing
        being simulated. Passing `recorded` is now ignored rather than
        obeyed, and this pins that.
        """
        payload = dict(MMCI_PAYLOAD)
        payload["recorded"] = ["S", "I"]  # wrong: I is not a species here

        code, data, detail = exporter.build_archive(payload)
        assert code == 0, detail.get("error")
        assert report_labels(data, tmp_path) == {"time", "S", "P", "J0"}

    def test_the_archive_still_replays(self, exporter, tmp_path):
        # Deriving the list must not break the property the archive exists
        # for, on a domain that is not Michaelis-Menten.
        roadrunner = pytest.importorskip("roadrunner")

        code, data, detail = exporter.build_archive(dict(MMCI_PAYLOAD))
        assert code == 0, detail.get("error")
        destination = tmp_path / "mmci.omex"
        destination.write_bytes(data)

        with zipfile.ZipFile(destination) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
            model_text = opened.read("model.xml").decode()

        simulation = document.getSimulation(0)
        result = roadrunner.RoadRunner(model_text).simulate(
            simulation.getOutputStartTime(),
            simulation.getOutputEndTime(),
            simulation.getNumberOfPoints() + 1,
        )
        assert len(result) == 101
        # Substrate that is never consumed would mean the parameters did not
        # survive the trip. Columns: time, S, P.
        assert float(result[-1][1]) < float(result[0][1])
        assert float(result[-1][2]) > float(result[0][2])


class TestWhatTheExportRefuses:
    def test_no_time_course_means_no_archive(self, exporter):
        payload = dict(MMCI_PAYLOAD)
        del payload["endTime"]

        code, _, detail = exporter.build_archive(payload)
        assert code == 1
        assert "endTime" in detail["error"]
        # The reason matters: guessing would produce a file that reproduces
        # an experiment nobody performed.
        assert "will not guess" in detail["error"]

    def test_a_domain_with_no_builder_is_refused_not_improvised(self, exporter):
        payload = dict(MMCI_PAYLOAD)
        payload["domain"] = "not-a-domain"

        code, _, detail = exporter.build_archive(payload)
        assert code == 1
        assert "not-a-domain" in detail["error"]
