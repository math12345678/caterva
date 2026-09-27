"""The packaged data copies must equal their originals, byte for byte.

`caterva/core/data/` carries copies of `docs/data-sources.json` and
`Tests/fixtures/identifiers/identifiers_org_namespaces.json` so an installed
wheel and the app folder can read them (ADR 0177). Two copies of one fact
drift unless something compares them; this does, on every run.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGED = REPO / "caterva" / "core" / "data"

PAIRS = [
    (PACKAGED / "data-sources.json", REPO / "docs" / "data-sources.json"),
    (
        PACKAGED / "identifiers_org_namespaces.json",
        REPO / "Tests" / "fixtures" / "identifiers" / "identifiers_org_namespaces.json",
    ),
]


@pytest.mark.parametrize("packaged, original", PAIRS, ids=[p.name for p, _ in PAIRS])
def test_the_packaged_copy_equals_the_original(packaged: Path, original: Path) -> None:
    assert original.is_file(), f"the original {original} is gone; the packaged copy would be orphaned"
    assert packaged.is_file(), f"{packaged} is missing; an installed wheel would crash at import"
    assert packaged.read_bytes() == original.read_bytes(), (
        f"{packaged.name} differs from {original.relative_to(REPO)}; "
        "copy the original over the packaged copy (the original is authoritative)"
    )


def test_the_loaders_prefer_the_checkout_and_fall_back_to_the_package(monkeypatch, tmp_path) -> None:
    """In a checkout both resolve to the originals; with the originals gone,
    to the packaged copies, and the packaged copies load."""
    from caterva.core import data_sources, miriam

    assert data_sources.SOURCES_FILE == data_sources._CHECKOUT_COPY
    assert miriam._FIXTURE == miriam._CHECKOUT_COPY
    # The packaged copies must be loadable on their own, which is what an
    # installed wheel does.
    sources = data_sources._load_sources(data_sources._PACKAGED_COPY)
    assert sources and sources == data_sources.SOURCES
    packaged_namespaces, captured = miriam._load_from(miriam._PACKAGED_COPY)
    assert captured == miriam.PATTERNS_CAPTURED_ON
    assert set(packaged_namespaces) == set(miriam.NAMESPACES)
