"""The dependency checker must not invent missing dependencies.

Two tests in `make test` failed for a whole session with messages that named
the wrong problem — the citation guard, and a zod load check — when the real
cause was that `cffconvert` and a workspace's `node_modules` were never
installed. `scripts/check_dev_dependencies.py` exists to say that in terms of
the thing to install.

Its first version reported **five** packages missing when **two** were. It
mapped a distribution name to a module name with ``s/-/_/`` and a small
override table, so `libroadrunner` (imports as ``roadrunner``),
`python-libsbml` (``libsbml``) and `beautifulsoup4` (``bs4``) all looked
absent.

That failure is worse than the one it was written to fix. A missing
dependency reported with a confusing message costs somebody an hour; a
checker that invents three missing dependencies makes its own output
untrustworthy, and buries the two real ones in noise. So the tests below
weigh false positives at least as heavily as false negatives.
"""

from __future__ import annotations

import importlib.util
import subprocess
from importlib import metadata
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
GUARD = REPO / "scripts" / "check_dev_dependencies.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_dev_dependencies", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


class TestItResolvesRealDistributionNames:
    """The regression that motivated using installed metadata."""

    @pytest.mark.parametrize(
        "distribution",
        ["libroadrunner", "python-libsbml", "beautifulsoup4", "pytest-timeout"],
    )
    def test_a_package_whose_import_name_differs_is_not_reported_missing(
        self, distribution
    ):
        # Each of these imports under a name the distribution name does not
        # predict. If any is installed and still reported missing, the checker
        # has gone back to guessing.
        #
        # The precondition is asked of `importlib.metadata` DIRECTLY, not of
        # `guard.is_installed`. The first version of this test used the
        # guard's own function, so the mutation that breaks name resolution
        # also broke the precondition and every case skipped itself -- a test
        # that disables itself under exactly the defect it exists to catch.
        # The mutation harness reported it NOT CAUGHT, which is how it was
        # found.
        try:
            metadata.distribution(distribution)
        except metadata.PackageNotFoundError:
            pytest.skip(f"{distribution} is not installed here; nothing to assert")
        assert guard.missing_python([distribution]) == []

    def test_a_package_that_cannot_exist_is_reported_missing(self):
        assert guard.missing_python(["terrium-not-a-real-package"]) == [
            "terrium-not-a-real-package"
        ]


class TestTheManifestParser:
    def test_it_reads_names_without_versions_or_extras(self, tmp_path):
        manifest = tmp_path / "reqs.txt"
        manifest.write_text(
            "# comment\n\npytest==9.1.1\nsome-extra[all]>=1.0\n--index-url http://x\n",
            encoding="utf-8",
        )
        names, problem = guard.parse_requirements(manifest)
        assert problem is None
        assert names == ["pytest", "some-extra"]

    def test_it_follows_an_include(self, tmp_path):
        (tmp_path / "base.txt").write_text("numpy==2.0\n", encoding="utf-8")
        manifest = tmp_path / "dev.txt"
        manifest.write_text("-r base.txt\npytest==9.1.1\n", encoding="utf-8")
        names, problem = guard.parse_requirements(manifest)
        assert problem is None
        assert names == ["numpy", "pytest"]

    def test_an_absent_manifest_is_a_problem_not_an_empty_list(self, tmp_path):
        """The vacuous-pass shape this repository keeps finding.

        An unreadable manifest yielding `[]` would report every dependency
        satisfied — most confidently exactly when it knows least.
        """
        names, problem = guard.parse_requirements(tmp_path / "absent.txt")
        assert names == []
        assert problem is not None
        assert "does not exist" in problem

    def test_an_absent_include_is_a_problem_too(self, tmp_path):
        manifest = tmp_path / "dev.txt"
        manifest.write_text("-r missing-base.txt\npytest==9.1.1\n", encoding="utf-8")
        names, problem = guard.parse_requirements(manifest)
        assert problem is not None
        # And it must not quietly return the names it managed to read.
        assert names == []


class TestExitCodes:
    def test_the_selftest_passes(self):
        result = subprocess.run(
            [sys.executable, str(GUARD), "--selftest"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_it_exits_3_when_the_manifest_cannot_be_read(self, tmp_path, monkeypatch):
        """Could-not-determine is its own state, not a pass and not a failure.

        Run with REPO_ROOT pointed at an empty directory, so
        `requirements-dev.txt` is absent and nothing can be checked.
        """
        result = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys,pathlib;"
             f"spec=importlib.util.spec_from_file_location('g',{str(GUARD)!r});"
             "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
             f"m.REPO_ROOT=pathlib.Path({str(tmp_path)!r});"
             "sys.argv=['g'];sys.exit(m.main())"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 3, result.stdout + result.stderr
        assert "UNDETERMINED" in result.stdout
        # It must say plainly that nothing was checked, or a reader takes the
        # absence of reported problems for their absence.
        assert "not a clean result" in result.stdout
