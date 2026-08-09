"""Verify the ODE-oscillator constants against curated BioModels SBML.

This is the test the two oscillator suites were missing. They asserted
their constants against literal copies of themselves:

    assert TYSON_KAPPA == 0.015
    assert REPRESSILATOR_ALPHA == 216.0

which cannot detect a value that was mistranscribed on the day it was
typed in -- the assertion carries the same error and passes forever. The
Lotka-Volterra domain shipped in the same batch with its `gamma`/`delta`
defaults transposed for exactly that reason (ADR 0023).

Here the constants are compared against EMBL-EBI's **curated** BioModels
encodings, captured offline by `scripts/capture_biomodels_fixture.py`:

    BIOMD0000000006  Tyson (1991) 2-variable reduction   PMID 1831270
    BIOMD0000000012  Elowitz & Leibler (2000)            PMID 10659856

Curated (rather than auto-generated) entries are manually checked by BioModels
curators against the paper they cite and annotated with its PMID, which is
what makes them usable as a stand-in primary source. That matters most for
Tyson (1991): it is a 1991 scan with no machine-readable text in PMC, so
the paper's own parameter table cannot be read programmatically at all.

The fixtures are committed and read from disk. The suite never touches the
network -- same discipline as the captured BRENDA pages.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from continuous.model_building import (  # noqa: E402
    REPRESSILATOR_ALPHA,
    REPRESSILATOR_ALPHA0,
    REPRESSILATOR_BETA,
    REPRESSILATOR_N,
    TYSON_K4,
    TYSON_K4PRIME,
    TYSON_K6,
    TYSON_KAPPA,
)

FIXTURES_DIR = _HERE.parent.parent / "Tests" / "fixtures"


def _biomodels_parameters(model_id: str) -> dict[str, float]:
    """Every <parameter id= value=> in a captured BioModels fixture.

    Matched on the local tag name because the curated entries span several
    SBML Level 2 versions with different namespace URIs.
    """
    path = FIXTURES_DIR / f"biomodels_{model_id}.xml"
    if not path.is_file():
        raise AssertionError(
            f"missing fixture {path}. Capture it with:\n"
            f"    python3 scripts/capture_biomodels_fixture.py\n"
            "The constants under test are unverified without it."
        )
    raw = path.read_bytes()
    if raw[:4] == b"PK\x03\x04":
        raise AssertionError(
            f"{path.name} is a ZIP/OMEX archive, not SBML. The capture "
            "script must unpack the archive before writing the fixture."
        )
    root = ET.fromstring(raw.decode("utf-8"))
    found: dict[str, float] = {}
    for element in root.iter():
        if not element.tag.endswith("}parameter") and element.tag != "parameter":
            continue
        pid, value = element.get("id"), element.get("value")
        if pid is None or value is None:
            continue
        try:
            found[pid] = float(value)
        except ValueError:
            continue
    if not found:
        raise AssertionError(f"no parameters parsed from {path.name}")
    return found


class TestTysonAgainstBiomodels:
    """Tyson (1991) 2-variable reduction, BIOMD0000000006.

    Verified 2026-08-09: all four constants match the curated encoding
    exactly.
    """

    @pytest.fixture(scope="class")
    def curated(self):
        return _biomodels_parameters("BIOMD0000000006")

    @pytest.mark.parametrize(
        ("constant", "sbml_id"),
        [
            (TYSON_KAPPA, "kappa"),
            (TYSON_K6, "k6"),
            (TYSON_K4, "k4"),
            (TYSON_K4PRIME, "k4prime"),
        ],
    )
    def test_constant_matches_curated_encoding(self, curated, constant, sbml_id):
        assert sbml_id in curated, (
            f"{sbml_id} absent from BIOMD0000000006; the curated encoding "
            f"defines {sorted(curated)}"
        )
        assert constant == pytest.approx(curated[sbml_id], rel=1e-9), (
            f"engine constant for {sbml_id} is {constant}, curated "
            f"BioModels value is {curated[sbml_id]}"
        )

    def test_alpha_is_the_documented_ratio_of_two_curated_values(self):
        # The reduction defines alpha = k4'/k4; both are curated, so the
        # derived quantity is checked against the source rather than
        # against a remembered result.
        curated = _biomodels_parameters("BIOMD0000000006")
        assert TYSON_K4PRIME / TYSON_K4 == pytest.approx(
            curated["k4prime"] / curated["k4"], rel=1e-9
        )


class TestRepressilatorAgainstBiomodels:
    """Elowitz & Leibler (2000), BIOMD0000000012.

    This comparison found a real discrepancy. The engine originally used
    `alpha=216.0`, `alpha0/alpha=1e-3` and **`beta=5.0`**; the curated
    encoding gives `alpha=216.404`, `alpha0=0.2164` and **`beta=0.2`**.

    `beta` was not a rounding difference but a reciprocal (1/0.2 = 5).
    BioModels annotates the parameter in the model itself:

        <parameter id="beta" value="0.2">
          <notes>ratio of protein to mRNA decay rates</notes>

    and the same encoding carries `tau_prot = 10` and `tau_mRNA = 2`, so
    the protein decays five times *slower* than the mRNA and the ratio is
    0.2. In the paper's dimensionless form -- which is what this engine
    integrates, `p' = -beta*(p - m)` -- a `beta` of 5 would make the
    protein equilibrate five times *faster* than the mRNA, contradicting
    those half-lives.

    The constants have since been corrected to the curated values. This
    test is what keeps them there.
    """

    @pytest.fixture(scope="class")
    def curated(self):
        return _biomodels_parameters("BIOMD0000000012")

    @pytest.mark.parametrize(
        ("constant", "sbml_id"),
        [
            (REPRESSILATOR_ALPHA, "alpha"),
            (REPRESSILATOR_ALPHA0, "alpha0"),
            (REPRESSILATOR_BETA, "beta"),
            (REPRESSILATOR_N, "n"),
        ],
    )
    def test_constant_matches_curated_encoding(self, curated, constant, sbml_id):
        assert sbml_id in curated, (
            f"{sbml_id} absent from BIOMD0000000012; the curated encoding "
            f"defines {sorted(curated)}"
        )
        assert constant == pytest.approx(curated[sbml_id], rel=1e-9), (
            f"engine constant for {sbml_id} is {constant}, curated "
            f"BioModels value is {curated[sbml_id]}"
        )

    def test_beta_is_consistent_with_the_curated_half_lives(self):
        """The check that would have caught the reciprocal directly.

        beta is defined as the ratio of protein to mRNA decay rates.
        Decay rate is inversely proportional to half-life, so

            beta = (1/tau_prot) / (1/tau_mRNA) = tau_mRNA / tau_prot

        Both half-lives are in the same curated encoding, so this derives
        beta from the model's own physical constants rather than trusting
        the stored value -- and it is dimensionally impossible to satisfy
        with the reciprocal.
        """
        curated = _biomodels_parameters("BIOMD0000000012")
        derived = curated["tau_mRNA"] / curated["tau_prot"]
        assert REPRESSILATOR_BETA == pytest.approx(derived, rel=1e-6), (
            f"beta={REPRESSILATOR_BETA} but tau_mRNA/tau_prot="
            f"{curated['tau_mRNA']}/{curated['tau_prot']}={derived}. "
            "A beta above 1 would mean the protein decays faster than the "
            "mRNA, which these half-lives contradict."
        )

    def test_leakiness_ratio_matches_the_curated_pair(self):
        """alpha0/alpha, checked against the curated pair, not against 1e-3.

        The paper quotes a leakiness of 10^-3; the curated values give
        0.2164/216.404 = 0.00099998, which is that number rounded rather
        than a different claim. Asserting the exact 1e-3 with a tight
        absolute tolerance fails on the real values -- so the ratio is
        compared against the source pair, with a separate loose check that
        it is still the paper's stated order of magnitude.
        """
        curated = _biomodels_parameters("BIOMD0000000012")
        assert REPRESSILATOR_ALPHA0 / REPRESSILATOR_ALPHA == pytest.approx(
            curated["alpha0"] / curated["alpha"], rel=1e-9
        )
        assert REPRESSILATOR_ALPHA0 / REPRESSILATOR_ALPHA == pytest.approx(
            1e-3, rel=1e-3
        )


class TestFixtureProvenance:
    """The fixtures must stay real SBML from the curated entries."""

    @pytest.mark.parametrize(
        "model_id", ["BIOMD0000000005", "BIOMD0000000006", "BIOMD0000000012"]
    )
    def test_fixture_is_parseable_sbml_naming_its_model(self, model_id):
        params = _biomodels_parameters(model_id)
        assert params, f"{model_id} fixture parsed to no parameters"
        text = (FIXTURES_DIR / f"biomodels_{model_id}.xml").read_text(
            encoding="utf-8"
        )
        assert "sbml" in text[:300].lower(), "fixture is not an SBML document"
        assert model_id in text, (
            f"{model_id} fixture does not name the model it claims to be"
        )
