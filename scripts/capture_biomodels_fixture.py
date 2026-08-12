"""Capture curated BioModels SBML as offline fixtures, for verifying that
Terrium's hardcoded ODE-oscillator constants match the published models.

Why this exists
---------------
`test_cell_cycle_oscillator_correctness.py` and
`test_repressilator_correctness.py` currently assert their parameter
constants against literals:

    assert TYSON_KAPPA == 0.015
    assert REPRESSILATOR_ALPHA == 216.0

That checks the code against itself. It catches an accidental edit, which
is worth something, but it is not verification: if the value was wrong when
it was first typed in, the assertion is wrong in exactly the same way and
passes forever. Every other numeric claim in this project is checked
against a primary source (BRENDA pages, stdpopsim, a closed form); these
two are not.

BioModels is the primary source available for both. It is EMBL-EBI's
curated repository of published models, and each curated entry is
manually checked against the paper it cites and annotated with that paper's
PMID. The relevant entries:

    BIOMD0000000005  Tyson (1991), 6-variable cdc2/cyclin model      PMID 1831270
    BIOMD0000000006  Tyson (1991), 2-variable reduction (used here)  PMID 1831270
    BIOMD0000000012  Elowitz & Leibler (2000), repressilator         PMID 10659856

Tyson (1991) is a 1991 scan with no machine-readable text in PMC, so the
parameter table cannot be extracted from the paper itself -- the curated
SBML is the practical primary source, and it carries the curators' own
verification against that table.

Why a capture script rather than a live test
--------------------------------------------
Same reasoning as `Tests/brenda_kcat_capture.py`: a test that reaches the
network fails for reasons that have nothing to do with the code, and the
suite must stay offline and deterministic. So the fixture is captured once,
committed, and the tests read it from disk. `scripts/verify_citations_live.py`
is the opt-in place for re-checking that captured sources still resolve.

This script also cannot run from the review sandbox, whose proxy blocks
outbound HTTPS (403 on CONNECT) -- the same reason BRENDA fixtures are
captured on a developer machine.

Usage
-----
    python3 scripts/capture_biomodels_fixture.py

Writes Tests/fixtures/biomodels_<id>.xml for each model above, then prints
the parameter values it found so they can be compared by eye against the
constants in Terium/continuous/model_building.py before anything is
committed.
"""

from __future__ import annotations

import io
import pathlib
import sys
import xml.etree.ElementTree as ET
import zipfile

try:
    import httpx
except ImportError:  # pragma: no cover - dependency is in requirements.txt
    print("httpx is required: pip install httpx", file=sys.stderr)
    raise SystemExit(1) from None

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "Tests" / "fixtures"

DOWNLOAD_URL = "https://www.ebi.ac.uk/biomodels/model/download/{model_id}"

#: model id -> (what it is, the PMID BioModels annotates it with)
MODELS = {
    "BIOMD0000000005": ("Tyson 1991, 6-variable cdc2/cyclin", "1831270"),
    "BIOMD0000000006": ("Tyson 1991, 2-variable reduction", "1831270"),
    "BIOMD0000000012": ("Elowitz & Leibler 2000, repressilator", "10659856"),
}

SBML_NS = {"sbml": "http://www.sbml.org/sbml/level2"}


def _sbml_from_response(payload: bytes, model_id: str) -> str:
    """Return SBML text from a BioModels download.

    `/model/download/<id>` does NOT serve raw XML: it serves an OMEX/ZIP
    archive (magic bytes `PK\\x03\\x04`) containing the SBML alongside the
    model's metadata. The first version of this script wrote
    `response.text` straight to disk, which decoded those bytes as UTF-8
    and corrupted the archive -- a 170 KB download became a 327 KB
    unreadable file, and every parse failed with "not well-formed (invalid
    token): line 1, column 2", which is an XML parser meeting `PK`.

    Binary is therefore read from `.content`, and a ZIP is unpacked to find
    the SBML member. A plain-XML response is still handled, so this keeps
    working if the endpoint's behaviour changes.
    """
    if payload[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            # Prefer the entry named after the model; otherwise the first
            # .xml that is not the OMEX manifest.
            candidates = [n for n in names if n.endswith(".xml")]
            preferred = [n for n in candidates if model_id in n]
            chosen = None
            for name in preferred + candidates:
                if name.rsplit("/", 1)[-1] == "manifest.xml":
                    continue
                chosen = name
                break
            if chosen is None:
                raise ValueError(f"no SBML member found in archive: {names}")
            return archive.read(chosen).decode("utf-8")
    return payload.decode("utf-8")


def _parameters(xml_text: str) -> dict[str, float]:
    """Every <parameter id=... value=...> in the document, at any level.

    Namespace-agnostic: BioModels entries span SBML L2V1 through L2V4 and
    the exact namespace URI differs between them, so matching on the local
    tag name is more robust than pinning one schema version.
    """
    root = ET.fromstring(xml_text)
    found: dict[str, float] = {}
    for element in root.iter():
        if not element.tag.endswith("}parameter") and element.tag != "parameter":
            continue
        pid = element.get("id")
        value = element.get("value")
        if pid is None or value is None:
            continue
        try:
            found[pid] = float(value)
        except ValueError:
            continue
    return found


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for model_id, (description, pmid) in MODELS.items():
        url = DOWNLOAD_URL.format(model_id=model_id)
        print(f"\n{model_id}  ({description}, PMID {pmid})")
        print(f"  GET {url}")
        try:
            response = httpx.get(url, timeout=60.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"  FAILED: {exc}")
            failures += 1
            continue

        try:
            sbml_text = _sbml_from_response(response.content, model_id)
        except (zipfile.BadZipFile, ValueError, UnicodeDecodeError) as exc:
            print(f"  FAILED to extract SBML: {exc}")
            failures += 1
            continue

        destination = FIXTURES_DIR / f"biomodels_{model_id}.xml"
        destination.write_text(sbml_text, encoding="utf-8")
        print(f"  wrote {destination.relative_to(REPO_ROOT)} "
              f"({len(sbml_text)} chars of SBML, from a "
              f"{len(response.content)}-byte download)")

        try:
            params = _parameters(sbml_text)
        except ET.ParseError as exc:
            print(f"  WARNING: could not parse SBML: {exc}")
            failures += 1
            continue

        if not params:
            print("  WARNING: no <parameter> elements found -- the download "
                  "may be an error page rather than SBML.")
            failures += 1
            continue

        print("  parameters:")
        for name in sorted(params):
            print(f"    {name:16} = {params[name]!r}")

    print(
        "\nCompare the values above against the constants in "
        "Terium/continuous/model_building.py\n"
        "(TYSON_KAPPA / TYSON_K6 / TYSON_K4 / TYSON_K4PRIME, "
        "REPRESSILATOR_ALPHA / _BETA / _N / _ALPHA0).\n"
        "Any disagreement is a real finding: the constants are currently "
        "asserted only against\nthemselves, so a value that was wrong when "
        "first typed in has never been challenged."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
