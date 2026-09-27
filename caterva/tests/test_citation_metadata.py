"""Caterva has to be citable, and every exported run has to say how.

`CITATION.cff` sat in the repository validated by nothing and referenced by
nothing. A Caterva result could cite every measurement it used and not the
tool that produced them — the converse of Katz's objection, and the point of
the FORCE11 Software Citation Principles (Smith et al. 2016) he co-authored:
software behind a result is citable and routinely goes uncited.

The failure mode is why this needs a test rather than a glance. An invalid
CITATION.cff does not error anywhere: GitHub's "Cite this repository" button
simply stops appearing, and nobody notices an absence.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
GUARD = REPO / "scripts" / "check_citation_cff.py"
CFF = REPO / "CITATION.cff"


class TestTheCitationFileItself:
    def test_the_guard_passes(self):
        result = subprocess.run(
            [sys.executable, str(GUARD)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_guard_reports_an_absent_validator_as_unreachable(self):
        """`cffconvert` missing must not read as a pass.

        The guard's own three-outcome discipline: "could not check" and
        "checked and fine" are different facts, and only one of them means
        the file is valid.
        """
        source = GUARD.read_text(encoding="utf-8")
        assert "UNREACHABLE" in source
        assert "This is not a pass" in source

    def test_it_is_valid_cff(self):
        pytest.importorskip("cffconvert")
        from cffconvert.cli.create_citation import create_citation

        create_citation(str(CFF), None).validate()


class TestEveryArchiveCarriesIt:
    """A citation nobody receives is a citation nobody makes."""

    def test_the_export_bundles_the_citation_file(self, tmp_path):
        pytest.importorskip("libsedml")
        import importlib.util

        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        spec = importlib.util.spec_from_file_location(
            "export_annotated_model", REPO / "scripts" / "export_annotated_model.py"
        )
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)

        code, data, detail = exporter.build_archive(
            {
                "domain": "mm",
                "format": "omex",
                "parameters": {"km": 2.5, "vmax": 0.25, "s0": 10},
                "endTime": 10.0,
                "points": 101,
                "provenance": {},
            }
        )
        assert code == 0, detail.get("error")

        destination = tmp_path / "run.omex"
        destination.write_bytes(data)
        with zipfile.ZipFile(destination) as opened:
            assert "CITATION.cff" in opened.namelist()
            bundled = opened.read("CITATION.cff").decode("utf-8")

        # Verbatim, not regenerated. A second rendering inside the exporter
        # would be a second source of truth able to disagree with the file
        # the repository actually publishes.
        assert bundled == CFF.read_text(encoding="utf-8")

    def test_the_bundled_citation_is_listed_in_the_manifest(self, tmp_path):
        pytest.importorskip("libsedml")
        from caterva.core.combine_archive import CFF as CFF_FORMAT
        from caterva.core.combine_archive import verify_archive

        import importlib.util

        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        spec = importlib.util.spec_from_file_location(
            "export_annotated_model", REPO / "scripts" / "export_annotated_model.py"
        )
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)

        code, data, _ = exporter.build_archive(
            {
                "domain": "mm",
                "format": "omex",
                "parameters": {"km": 2.5, "vmax": 0.25, "s0": 10},
                "endTime": 10.0,
                "points": 101,
                "provenance": {},
            }
        )
        assert code == 0

        destination = tmp_path / "run.omex"
        destination.write_bytes(data)

        # An unlisted entry is one a strict reader ignores, so bundling it
        # without listing it would be the same as not bundling it.
        outcome = verify_archive(destination)
        assert outcome.ok, outcome.problems
        assert "CITATION.cff" in outcome.listed

        with zipfile.ZipFile(destination) as opened:
            manifest = opened.read("manifest.xml").decode()
        assert CFF_FORMAT in manifest
        # No invented COMBINE specification for a format that has none.
        assert "combine.specifications/cff" not in manifest
