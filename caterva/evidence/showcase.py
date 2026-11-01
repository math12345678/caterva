"""The hexokinase bundle, built offline from the recorded page.

WHY THIS EXISTS
---------------
ADR 0179's mutation tests (`caterva/tests/test_verify_mutations.py`) need
one bundle whose every claim is known to the byte, so that one changed byte
can be shown to fail exactly one check. The ADR itself shows the same bundle.
So this builds, with no network and no environment variable, from the
recorded human hexokinase page (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz,
fetched 2026-09-28, CC BY 4.0; read directly, not through
`fetch_brenda_html`):

    reaction_Km   cited   Km(2.7.1.1, D-glucose, Homo sapiens) = 6 mM
                          the row with reference 641068 and commentary
                          "30°C, pH 7.5, wild-type"
    reaction_kcat cited   kcat(2.7.1.1, D-glucose, Homo sapiens) = 40.1 1/s
                          the row with reference 739603, "wild-type, pH 7.6, 25 °C"
    reaction_S    chosen  a starting amount, 1 mM
    model         computed, rule compile.model, from the three

Both cited rows are the resolver's answers for this page, as
Tests/fixtures/recorded/http/MANIFEST.json records them (Km 6.0 mM ref
641068; kcat 40.1 1/s ref 739603) and Tests/test_http_replay.py holds the
runner to them. The showcase does not re-run the resolver (fifteen seconds
on this page); it re-finds the rows with `find_row`, under the identity rule
the compose layer uses, and cites them under the resolver's rule.

WHAT IS A STAND-IN
------------------
The model claim's `settings["ir"]` is the sha256 of the string
"michaelis_menten". In a real run (`caterva compose --claims`) it is the
digest of the annotation-free Antimony source; the showcase builds no model,
so it names a stand-in and this docstring says so.

ORDINALS
--------
The Km claim's `settings["ordinals"]` are computed from
Tests/evidence_rank.py's `profile()` for the cited row and for the rows of
the non-dominated frontier of the human D-glucose Km pool with protein
variants set aside (the two steps the resolver takes before it chooses). That
frontier is narrower than the resolver's own, whose "glucose" request also
matched the 2-deoxyglucose rows; it is the D-glucose frontier the subject
names. The kcat claim's ordinals are computed the same way.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from typing import Any

try:
    from caterva.checkout import literature_module, tests_directory
    from caterva.evidence.capture import BRENDA_LICENCE, enzyme_page_url
    from caterva.evidence.claims import (
        CHOSEN_STARTING_AMOUNT,
        COMPILE_MODEL,
        PARSE_BRENDA_REFERENCE,
        SELECT_RESOLVER,
        Claim,
        Derivation,
        EvidenceRefused,
        Row,
        make_claim,
        ordinals_json,
    )
    from caterva.evidence.references import reference_url
    from caterva.evidence.rows import certificates_for, find_row, ordinals_from_profile, parsed_rows
    from caterva.evidence.store import EvidenceStore
except ImportError:  # pragma: no cover - flat layout
    from checkout import literature_module, tests_directory  # type: ignore[no-redef]
    from evidence.capture import BRENDA_LICENCE, enzyme_page_url  # type: ignore[no-redef]
    from evidence.claims import (  # type: ignore[no-redef]
        CHOSEN_STARTING_AMOUNT,
        COMPILE_MODEL,
        PARSE_BRENDA_REFERENCE,
        SELECT_RESOLVER,
        Claim,
        Derivation,
        EvidenceRefused,
        Row,
        make_claim,
        ordinals_json,
    )
    from evidence.references import reference_url  # type: ignore[no-redef]
    from evidence.rows import certificates_for, find_row, ordinals_from_profile, parsed_rows  # type: ignore[no-redef]
    from evidence.store import EvidenceStore  # type: ignore[no-redef]

EC = "2.7.1.1"
ORGANISM = "Homo sapiens"
SUBSTRATE = "D-glucose"
PAGE_NAME = "brenda_2.7.1.1.html.gz"
PAGE_FETCHED = "2026-09-28"
REFERENCE_FETCHED = "2026-10-17"

#: The two cited rows: (table, value, commentary, reference).
KM_ROW = ("km", 6.0, "30°C, pH 7.5, wild-type", "641068")
KCAT_ROW = ("kcat", 40.1, "wild-type, pH 7.6, 25 °C", "739603")

#: The stand-in for the compiled source's digest (module docstring).
IR_STAND_IN = "michaelis_menten"


def recorded_dir() -> Path:
    tests = tests_directory()
    if tests is None:
        raise EvidenceRefused(
            "the showcase bundle is built from Tests/fixtures/recorded/, which this "
            "installation does not have (the recorded pages are not shipped, ADR 0177)"
        )
    return tests / "fixtures" / "recorded"


def _label(row: Row) -> str:
    return f"{row.value_text} {row.unit} ref {row.reference or 'none'}"


def _frontier_ordinals(evidence_rank: Any, pool: list[tuple[Any, Row]], chosen: Row) -> str:
    """settings["ordinals"]: the chosen row and the non-dominated rows of the
    pool with variants set aside, each as profile() ordinals."""
    kept_entries = [
        entry for entry, _ in pool
        if getattr(getattr(entry, "variant", None), "status", None) != "variant"
    ]
    frontier = evidence_rank.frontier(kept_entries, ORGANISM)
    by_entry = {id(entry): row for entry, row in pool}
    chosen_entry = next(entry for entry, row in pool if row.id == chosen.id)
    alternatives = {}
    for entry in frontier:
        row = by_entry[id(entry)]
        if row.id != chosen.id:
            alternatives[_label(row)] = ordinals_from_profile(evidence_rank.profile(entry, ORGANISM))
    return ordinals_json(ordinals_from_profile(evidence_rank.profile(chosen_entry, ORGANISM)), alternatives)


def _cited(
    store: EvidenceStore, evidence_rank: Any, page: bytes, pool: list[tuple[Any, Row]],
    *, identifier: str, quantity: str, spec: tuple, unit: str,
) -> Claim:
    table, value, commentary, reference = spec
    rows = [row for _, row in pool]
    row = find_row(rows, value=value, commentary=commentary, reference=reference)
    if row is None:
        raise EvidenceRefused(
            f"the recorded page holds no human {SUBSTRATE} {table} row with value {value}, "
            f"reference {reference} and commentary {commentary!r}; the showcase cites nothing else"
        )
    store.put_row(row)
    certificates = certificates_for(row, page)
    settings = {"ordinals": _frontier_ordinals(evidence_rank, pool, row)}
    if row.unit != unit:
        raise EvidenceRefused(f"the {table} row is in {row.unit}, not {unit}")
    return store.put_claim(make_claim(
        "cited", f"{identifier} = {quantity}({EC}, {SUBSTRATE}, {ORGANISM})",
        row.value_text, unit, None,
        Derivation(SELECT_RESOLVER, inputs=(row.ref,), certificates=certificates, settings=settings),
    ))


def _pin_reference_pages(store: EvidenceStore, directory: Path) -> None:
    """The recorded literature pages for the cited references, when present,
    so `caterva why` can name the papers from the bundle alone."""
    for ref in (KM_ROW[3], KCAT_ROW[3]):
        path = directory / f"brenda_reference_{EC}_{ref}.html.gz"
        if path.is_file():
            store.put_snapshot(
                gzip.decompress(path.read_bytes()), source="brenda_reference",
                locator=reference_url(EC, ref), retrieved_at=REFERENCE_FETCHED,
                licence=BRENDA_LICENCE, served_from=f"Tests/fixtures/recorded/{path.name}",
            )


def showcase_bundle(out_dir: str | Path) -> str:
    """Build the showcase bundle in `out_dir` (store at `out_dir/store`); the root claim ref."""
    directory = recorded_dir()
    page_path = directory / PAGE_NAME
    if not page_path.is_file():
        raise EvidenceRefused(f"{page_path} is missing; the showcase is built from it")
    page = gzip.decompress(page_path.read_bytes())
    html = page.decode("utf-8")
    evidence_rank = literature_module("evidence_rank")

    out = Path(out_dir)
    store = EvidenceStore(out / "store")
    try:
        snapshot = store.put_snapshot(
            page, source="brenda_enzyme", locator=enzyme_page_url(EC), retrieved_at=PAGE_FETCHED,
            licence=BRENDA_LICENCE, served_from=f"Tests/fixtures/recorded/{PAGE_NAME}",
        )
        _pin_reference_pages(store, directory)

        km_pool = [
            (entry, row) for entry, row in parsed_rows(
                html, ec=EC, table="km", organism=ORGANISM, snapshot_ref=snapshot.ref,
            ) if row.substrate == SUBSTRATE
        ]
        kcat_pool = [
            (entry, row) for entry, row in parsed_rows(
                html, ec=EC, table="kcat", organism=ORGANISM, snapshot_ref=snapshot.ref,
            ) if row.substrate == SUBSTRATE
        ]
        km = _cited(store, evidence_rank, page, km_pool,
                    identifier="reaction_Km", quantity="Km", spec=KM_ROW, unit="mM")
        kcat = _cited(store, evidence_rank, page, kcat_pool,
                      identifier="reaction_kcat", quantity="kcat", spec=KCAT_ROW, unit="1/s")
        starting = store.put_claim(make_claim(
            "chosen", "reaction_S = starting amount of D-glucose", "1", "mM", None,
            Derivation(CHOSEN_STARTING_AMOUNT, settings={"chosen_by": "the showcase; nobody measured it"}),
        ))
        ir = "sha256:" + hashlib.sha256(IR_STAND_IN.encode("utf-8")).hexdigest()
        model = store.put_claim(make_claim(
            "computed", f"model = michaelis_menten({EC}, {SUBSTRATE}, {ORGANISM})", None, None, None,
            Derivation(
                COMPILE_MODEL, inputs=(km.ref, kcat.ref, starting.ref, f"ir:{ir}"),
                settings={"ir": ir, "ir_is": f"a stand-in: sha256 of the text {IR_STAND_IN!r}, not of a compiled source"},
            ),
        ))
        store.export_bundle(model.ref, out)
    finally:
        store.close()
    return model.ref


__all__ = [
    "EC",
    "IR_STAND_IN",
    "KCAT_ROW",
    "KM_ROW",
    "ORGANISM",
    "PAGE_FETCHED",
    "PAGE_NAME",
    "PARSE_BRENDA_REFERENCE",
    "REFERENCE_FETCHED",
    "SUBSTRATE",
    "recorded_dir",
    "showcase_bundle",
]
