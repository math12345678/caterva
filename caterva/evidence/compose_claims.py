"""`caterva compose --claims DIR`: the claims a composed model's numbers rest on.

WHY THIS IS GLUE AND NOT PART OF COMPOSE
----------------------------------------
`caterva compose` already knows where each number came from: a
`ParameterOrigin` per quantity, measured, placeholder or chosen, with the
resolver's Measurement beside the measured ones (caterva/compose/export.py).
What it does not know is the page the resolver read, the row on it, or the
byte spans that hold the reference id, the value and the commentary. The
evidence layer (claims.py, rows.py, capture.py, store.py) knows those. This
module joins the two for one run and nothing else: compose is unchanged
without `--claims`, and nothing under caterva/compose imports this package
except inside that flag's branch (ADR 0179).

WHAT ONE RUN DOES
-----------------
`ClaimsRun(DIR)` opens the store at `DIR/store` and, for the length of the
literature search, a `capture.Recorder`, so every BRENDA page the resolver
reads is pinned as it is read. After the search, `claims_for_model` builds:

  * for each measured quantity, a CITED claim: the page pinned for the EC,
    the rows of the quantity's table on it as the literature layer's own
    parser yields them, the row the resolver's Measurement names (its value,
    its commentary verbatim, its reference id), the certificates for that
    row's bytes, rule `select.resolver` v1 (ADR 0047), the evidence ordinals
    of the chosen row and the frontier when the resolver carried them, and
    a unit factor when the row's unit is not the claim's;
  * a REFUSED claim, never a citation, when no page was pinned, no row on
    the pinned page matches, or the row's bytes cannot be certified; the
    refusal names the candidate rows with the same reference id and why
    each was not the one;
  * a PLACEHOLDER claim per unmeasured constant, naming the table that
    would supply it and the search's own reason it did not;
  * a CHOSEN claim per starting amount and exponent;
  * the COMPUTED model claim, rule `compile.model`, whose inputs are every
    claim above and the digest of the annotation-free Antimony source
    (`export._antimony_source`), which is also `settings["ir"]`.

Then the literature page of every cited reference is captured through
`http_retry.retry_get` (so a test's recordings answer it), and the closure
of the model claim is written to DIR as a bundle for `caterva verify`.

WHAT IS REFUSED, AND WHAT IS ONLY NOTED
---------------------------------------
A measured value whose row is not on the pinned page gets a refused claim:
the model still carries the number the resolver returned, and the claim
says, re-checkably, that the page does not hold what the resolver reported.
A reference page that could not be captured (no network, no recording) is a
note in the report's `## Claims` section and a refused claim in the store,
not a failure of the run: the paper's page is a convenience for `caterva
why`, not an input of any derivation, and making it one would make the
model claim's id depend on whether the network answered that day.

Identity is deterministic: two runs over the same pages give the same root
id, because nothing time-dependent enters a claim (a snapshot's
`retrieved_at` sits beside its id, not inside it).
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from caterva.evidence.capture import (
        BRENDA_LICENCE,
        Recorder,
        capture_reference,
        enzyme_page_url,
    )
    from caterva.evidence.claims import (
        CHOSEN_STARTING_AMOUNT,
        COMPILE_MODEL,
        PLACEHOLDER_MOTIF_LIBRARY,
        SELECT_RESOLVER,
        Claim,
        Derivation,
        Refusal,
        Row,
        make_claim,
        now_utc,
        ordinals_json,
    )
    from caterva.evidence.rows import (
        certificates_for,
        find_row,
        ordinals_from_grades,
        rows_from_page,
        value_text_of,
    )
    from caterva.evidence.store import EvidenceStore
except ImportError:  # pragma: no cover - flat layout
    from evidence.capture import (  # type: ignore[no-redef]
        BRENDA_LICENCE,
        Recorder,
        capture_reference,
        enzyme_page_url,
    )
    from evidence.claims import (  # type: ignore[no-redef]
        CHOSEN_STARTING_AMOUNT,
        COMPILE_MODEL,
        PLACEHOLDER_MOTIF_LIBRARY,
        SELECT_RESOLVER,
        Claim,
        Derivation,
        Refusal,
        Row,
        make_claim,
        now_utc,
        ordinals_json,
    )
    from evidence.rows import (  # type: ignore[no-redef]
        certificates_for,
        find_row,
        ordinals_from_grades,
        rows_from_page,
        value_text_of,
    )
    from evidence.store import EvidenceStore  # type: ignore[no-redef]

#: Where a run's store lives under the bundle directory.
STORE_DIR = "store"

#: How a quantity's table is named in a claim's subject.
QUANTITY_NAMES = {"km": "Km", "kcat": "kcat", "ki": "Ki"}

#: `Refusal.kind` for each way a measured value gets no citation.
PAGE_NOT_PINNED = "page_not_pinned"
ROW_NOT_FOUND = "row_not_found_on_pinned_page"
ROW_NOT_CERTIFIED = "row_not_certified_on_pinned_page"
REFERENCE_NOT_CAPTURED = "reference_page_not_captured"

#: `settings["dominance"]` when the resolver's frontier did not carry the
#: chosen row's grades, so no ordinals can be stated for it.
ORDINALS_NOT_CARRIED = "not certified: chosen row's ordinals not carried"

#: The line the report's `## Claims` section ends with, with the directory.
RECHECK_LINE = "Re-check offline: caterva verify {directory}"


@dataclass(frozen=True)
class ClaimSet:
    """What one run wrote: every claim, by quantity, and the root.

    `by_identifier` maps each quantity's identifier (species and parameters,
    as the exports name them) to its claim ref, cited or not; that mapping
    is what the exports take as `claim_ids`. `notes` are the things that
    could not be done, in the words the `## Claims` section prints.
    """

    root: str
    claims: tuple[Claim, ...]
    by_identifier: Mapping[str, str]
    notes: tuple[str, ...] = ()
    directory: Path | None = None
    store: Path | None = None
    rows: int = 0
    snapshots: int = 0

    def counts(self) -> dict[str, int]:
        """How many claims of each kind, in KINDS order, zeros included."""
        try:
            from caterva.evidence.claims import KINDS
        except ImportError:  # pragma: no cover - flat layout
            from evidence.claims import KINDS  # type: ignore[no-redef]
        out = dict.fromkeys(KINDS, 0)
        for claim in self.claims:
            out[claim.kind] = out.get(claim.kind, 0) + 1
        return out

    def section(self, directory: str) -> str:
        """The body of the report's `## Claims` section, with `directory` as
        the user typed it so the closing line can be pasted."""
        counts = self.counts()
        root = next((c for c in self.claims if c.ref == self.root), None)
        lines = [
            f"Root claim: `{self.root}`"
            + (f" ({root.kind}; {root.subject})" if root is not None else ""),
            f"Claims written: {len(self.claims)} -- "
            + ", ".join(f"{n} {kind}" for kind, n in counts.items())
            + f"; {self.rows} row(s) and {self.snapshots} pinned page(s) in the bundle.",
            "",
        ]
        for claim in self.claims:
            if claim.ref == self.root:
                continue
            identifier = _identifier_of(claim)
            what = f"{claim.kind}"
            if claim.kind == "refused" and claim.refusal is not None:
                what += f" ({claim.refusal.kind})"
            elif claim.value_text is not None:
                what += f", {claim.value_text} {claim.unit or ''}".rstrip()
            lines.append(f"- `{identifier}`: {what} -- `{claim.ref}`")
        lines.extend(f"- {note}" for note in self.notes)
        lines += [
            "",
            f"Bundle: {directory}",
            RECHECK_LINE.format(directory=directory),
            "",
            "A claim is a derivation, not a verdict: `caterva verify` re-checks "
            "that each stated reason still holds against the pinned bytes, not "
            "whether the paper was right.",
        ]
        return "\n".join(lines)


def _identifier_of(claim: Claim) -> str:
    """The quantity a claim's subject starts with (`reaction_Km = ...`)."""
    return claim.subject.split(" = ", 1)[0]


def _subject(identifier: str, origin: Any, model: Any, *, substrate: str | None,
             organism: str | None) -> str:
    """`<identifier> = <quantity>(<ec>, <substrate>, <organism>)` for a
    resolvable constant, the form ADR 0179 gives; the description for a
    chosen value, which no table and no organism would qualify."""
    if not getattr(origin, "resolvable", False):
        what = getattr(origin, "description", "") or (
            "a starting amount" if getattr(origin, "role", "") != "parameter"
            else f"a {str(getattr(origin, 'kind', 'value')).replace('_', ' ')}"
        )
        return f"{identifier} = {what}"
    table = getattr(origin, "table", None)
    quantity = QUANTITY_NAMES.get(table or "", table or getattr(origin, "kind", "value"))
    ec = _ec_of(model) or "no subject"
    return f"{identifier} = {quantity}({ec}, {substrate or 'no compound'}, {organism or 'no organism'})"


def _ec_of(model: Any) -> str | None:
    """The EC number the search ran for: the model's, read the way the
    resolver was told it (`ComposedModel.ec_number`), else its subject."""
    ec = getattr(model, "ec_number", None)
    if ec:
        return str(ec)
    subject = getattr(model, "subject", None)
    return str(subject) if subject else None


def _compound_of(model: Any, identifier: str) -> str | None:
    """The compound the search looked this constant up under, when the
    model knows one (`ComposedModel.compound_for`)."""
    for quantity in getattr(model, "resolvable", ()) or ():
        if getattr(quantity, "parameter_id", None) == identifier:
            try:
                return model.compound_for(quantity)
            except Exception:  # noqa: BLE001 - a model without the method or the compound
                return getattr(model, "substrate", None)
    return getattr(model, "substrate", None)


def _reference_of(measurement: Any) -> str | None:
    """The BRENDA reference id the measurement cites, read as compose reads
    it everywhere (`ki_mode._reference`: the `reference_id` field, else
    "BRENDA ref N" in the citation text)."""
    try:
        from caterva.compose.ki_mode import _reference
    except ImportError:  # pragma: no cover - flat layout
        from compose.ki_mode import _reference  # type: ignore[no-redef]
    return _reference(measurement)


def _own_row(measurement: Any) -> dict[str, Any]:
    """The measurement as the dicts the resolver's frontier holds, for
    finding it among `alternatives` under `narrowed.same_row`."""
    return {
        "value": float(measurement.value),
        "reference_id": _reference_of(measurement),
        "conditions": getattr(measurement, "commentary", None),
    }


def _label(row: Mapping[str, Any], unit: str | None) -> str:
    value = row.get("value")
    try:
        text = value_text_of(float(value))
    except (TypeError, ValueError):
        text = str(value)
    return f"{text} {unit or row.get('unit') or ''} ref {row.get('reference_id') or 'none'}".replace("  ", " ")


def _ordinals_settings(measurement: Any, unit: str) -> dict[str, str]:
    """`{"ordinals": ...}` from the frontier dicts' grades when the chosen row
    is among them with grades, else `{"dominance": ORDINALS_NOT_CARRIED}`.

    The frontier (`ParameterSource.candidates`, `Measurement.alternatives`)
    carries each row's reliability grades; `rows.ordinals_from_grades` turns
    them into ordinals a checker can compare, with a grade it cannot rank
    (not_assessed) as null, which the checker skips. A selection that moved
    the carried row (isoform, mode) rebuilds the alternatives without the
    grades on the chosen one, and then nothing can be stated: the claim says
    so rather than inventing ordinals.
    """
    try:
        from caterva.compose.narrowed import same_row
    except ImportError:  # pragma: no cover - flat layout
        from compose.narrowed import same_row  # type: ignore[no-redef]
    mine = _own_row(measurement)
    chosen: Mapping[str, Any] | None = None
    others: list[Mapping[str, Any]] = []
    for row in getattr(measurement, "alternatives", ()) or ():
        if not isinstance(row, Mapping):
            continue
        if chosen is None and same_row(row, mine):
            chosen = row
        else:
            others.append(row)
    grades = chosen.get("grades") if chosen is not None else None
    if not isinstance(grades, Mapping):
        return {"dominance": ORDINALS_NOT_CARRIED}
    alternatives: dict[str, dict[str, str | None]] = {}
    for row in others:
        theirs = row.get("grades")
        if not isinstance(theirs, Mapping):
            continue
        label = _label(row, unit)
        n = 2
        while label in alternatives:
            label = f"{_label(row, unit)} #{n}"
            n += 1
        alternatives[label] = ordinals_from_grades(theirs)
    return {"ordinals": ordinals_json(ordinals_from_grades(grades), alternatives)}


class _Pages:
    """The rows of each (EC, table, organism) on the pinned page, parsed once."""

    def __init__(self, store: EvidenceStore, recorder: Any) -> None:
        self.store = store
        self.recorder = recorder
        self._html: dict[str, str] = {}
        self._bytes: dict[str, bytes] = {}
        self._rows: dict[tuple[str, str, str | None], list[Row]] = {}

    def snapshot(self, ec: str) -> Any | None:
        return self.recorder.snapshot_for(ec) if self.recorder is not None else None

    def page_bytes(self, snapshot: Any) -> bytes:
        if snapshot.ref not in self._bytes:
            self._bytes[snapshot.ref] = self.store.snapshot_bytes(snapshot.ref)
        return self._bytes[snapshot.ref]

    def rows(self, snapshot: Any, *, ec: str, table: str, organism: str | None) -> list[Row]:
        key = (snapshot.ref, table, organism)
        if key not in self._rows:
            html = self.page_bytes(snapshot).decode("utf-8")
            self._rows[key] = rows_from_page(
                html, ec=ec, table=table, organism=organism, snapshot_ref=snapshot.ref,
            )
        return self._rows[key]


def _refused(store: EvidenceStore, subject: str, unit: str | None, *, requested: str,
             kind: str, candidates: tuple[str, ...] = (), inputs: tuple[str, ...] = (),
             settings: Mapping[str, str] | None = None) -> Claim:
    """A refused claim, stored, with the candidate rows (already stored) as
    inputs so the bundle carries them for `caterva why`."""
    return store.put_claim(make_claim(
        "refused", subject, None, unit, None,
        Derivation(SELECT_RESOLVER, inputs=inputs, settings=dict(settings or {})),
        refusal=Refusal(requested=requested, kind=kind, candidates=candidates),
    ))


def _cited_or_refused(store: EvidenceStore, pages: _Pages, origin: Any, model: Any) -> Claim:
    """The claim for one measured quantity: cited from the pinned page's
    row, or refused with the reason and the candidates."""
    measurement = origin.measurement
    identifier = origin.identifier
    table = str(origin.table or "")
    organism = getattr(measurement, "organism", None) or None
    reference = _reference_of(measurement)
    requested = (
        f"{value_text_of(measurement.value)} {measurement.unit}, reference "
        f"{reference or 'none'}, commentary {measurement.commentary!r}, from the "
        f"{table or 'unknown'} table for {organism or 'any organism'}"
    )
    ec = _ec_of(model)
    subject = _subject(identifier, origin, model, substrate=_compound_of(model, identifier),
                       organism=organism)
    snapshot = pages.snapshot(ec) if ec else None
    if snapshot is None or table not in QUANTITY_NAMES:
        why = (
            f"no BRENDA page for EC {ec or 'none'} was pinned during the search"
            if table in QUANTITY_NAMES
            else f"{table or 'no'} is not a table this slice reads"
        )
        return _refused(store, subject, measurement.unit, requested=requested,
                        kind=PAGE_NOT_PINNED, settings={"why": why})

    rows = pages.rows(snapshot, ec=ec, table=table, organism=organism)
    row = find_row(rows, value=measurement.value, commentary=measurement.commentary,
                   reference=reference)
    if row is None:
        same_reference = [r for r in rows if reference and r.reference == reference]
        for candidate in same_reference:
            store.put_row(candidate)
        candidates = tuple(
            f"{r.ref} | value {r.value_text} {r.unit}, commentary {r.commentary!r}: not the "
            f"value and commentary the resolver reported"
            for r in same_reference
        )
        return _refused(
            store, subject, measurement.unit, requested=requested, kind=ROW_NOT_FOUND,
            candidates=candidates, inputs=tuple(r.ref for r in same_reference),
            settings={"why": (
                f"the page pinned for EC {ec} ({snapshot.ref}) holds {len(rows)} "
                f"{table} row(s) for {organism or 'every organism'} and none has this "
                f"value, commentary and reference; {len(same_reference)} share the reference"
            )},
        )

    store.put_row(row)
    certificates = certificates_for(row, pages.page_bytes(snapshot))
    if not certificates:
        return _refused(
            store, subject, measurement.unit, requested=requested, kind=ROW_NOT_CERTIFIED,
            candidates=(f"{row.ref} | the parser yields it, and no one table row in the "
                        "pinned bytes holds its reference, value and commentary together",),
            inputs=(row.ref,),
        )
    subject = _subject(identifier, origin, model, substrate=row.substrate,
                       organism=organism or row.organism)
    settings = _ordinals_settings(measurement, row.unit)
    unit = str(origin.unit)
    if row.unit.strip() != unit.strip():
        # compose converts nothing (`export._check_unit` refuses a mismatch),
        # so the only factor that can be true here is 1: the number was
        # carried as read, under the model's spelling of the unit.
        settings["unit_factor"] = "1"
    return store.put_claim(make_claim(
        "cited", subject, row.value_text, unit, None,
        Derivation(SELECT_RESOLVER, inputs=(row.ref,), certificates=certificates,
                   settings=settings),
    ))


def _placeholder(store: EvidenceStore, origin: Any, model: Any) -> Claim:
    identifier = origin.identifier
    settings = {
        "table": str(origin.table) if origin.table else "none",
        "motif": str(origin.motif or ""),
        "symbol": str(origin.symbol or ""),
    }
    why = (getattr(model, "not_found", None) or {}).get(identifier)
    if why:
        settings["why"] = str(why)
    subject = _subject(identifier, origin, model, substrate=_compound_of(model, identifier),
                       organism=getattr(model, "organism", None))
    return store.put_claim(make_claim(
        "placeholder", subject, value_text_of(origin.value), str(origin.unit), None,
        Derivation(PLACEHOLDER_MOTIF_LIBRARY, settings=settings),
    ))


def _chosen(store: EvidenceStore, origin: Any, model: Any) -> Claim:
    settings = {
        "role": str(origin.role), "kind": str(origin.kind),
        "motif": str(origin.motif or ""), "symbol": str(origin.symbol or ""),
    }
    return store.put_claim(make_claim(
        "chosen", _subject(origin.identifier, origin, model, substrate=None, organism=None),
        value_text_of(origin.value), str(origin.unit), None,
        Derivation(CHOSEN_STARTING_AMOUNT, settings=settings),
    ))


def ir_digest(provenanced: Any) -> str:
    """`sha256:<hex>` of the annotation-free Antimony source of the model,
    `export._antimony_source`, which is what `compile.model` consumed."""
    try:
        from caterva.compose.export import _antimony_source
    except ImportError:  # pragma: no cover - flat layout
        from compose.export import _antimony_source  # type: ignore[no-redef]
    source = _antimony_source(provenanced)
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def claims_for_model(provenanced: Any, model: Any, store: EvidenceStore, recorder: Any) -> ClaimSet:
    """Build and store the claims of `provenanced` (the ProvenancedModel the
    exports are written from) for `model` (the ComposedModel after the
    search), from the pages `recorder` pinned. Returns the ClaimSet, whose
    root is the computed model claim. Nothing is written to the bundle
    directory here; `write_bundle_for` does that."""
    pages = _Pages(store, recorder)
    claims: list[Claim] = []
    by_identifier: dict[str, str] = {}
    for origin in provenanced.origins:
        if origin.measured:
            claim = _cited_or_refused(store, pages, origin, model)
        elif origin.placeholder:
            claim = _placeholder(store, origin, model)
        else:
            claim = _chosen(store, origin, model)
        claims.append(claim)
        by_identifier[origin.identifier] = claim.ref
    ir = ir_digest(provenanced)
    ec = _ec_of(model) or "no subject"
    name = getattr(provenanced, "name", None) or getattr(getattr(model, "network", None), "name", "model")
    model_claim = store.put_claim(make_claim(
        "computed",
        f"model = {name}({ec}, {getattr(model, 'substrate', None) or 'no compound'}, "
        f"{getattr(model, 'organism', None) or 'no organism'})",
        None, None, None,
        Derivation(
            COMPILE_MODEL, inputs=(*(c.ref for c in claims), f"ir:{ir}"),
            settings={
                "ir": ir,
                "ir_is": "sha256 of the annotation-free Antimony source the exports compile "
                         "(caterva.compose.export._antimony_source)",
            },
        ),
    ))
    claims.append(model_claim)
    return ClaimSet(root=model_claim.ref, claims=tuple(claims), by_identifier=by_identifier,
                    store=store.path)


def capture_references(claim_set: ClaimSet, store: EvidenceStore) -> tuple[str, ...]:
    """Pin the literature page of every reference the cited claims name,
    through `capture_reference`; a page that could not be captured is a
    refused claim in the store and a note returned here, never a failure
    of the run (module docstring)."""
    notes: list[str] = []
    seen: set[tuple[str, str]] = set()
    for claim in claim_set.claims:
        if claim.kind != "cited":
            continue
        for ref in claim.derivation.row_inputs():
            try:
                row = store.get(ref)
            except KeyError:
                continue
            try:
                from caterva.evidence.rows import locator_ec
            except ImportError:  # pragma: no cover - flat layout
                from evidence.rows import locator_ec  # type: ignore[no-redef]
            ec = locator_ec(row.locator)
            if not row.reference or not ec or (ec, row.reference) in seen:
                continue
            seen.add((ec, row.reference))
            try:
                capture_reference(ec, row.reference, store)
            except Exception as exc:  # noqa: BLE001 - said in the report, not raised
                why = f"{type(exc).__name__}: {exc}".strip()
                note = (f"reference page not captured for BRENDA ref {row.reference} of EC "
                        f"{ec}: {why}. `caterva why` will name the reference id, not the paper.")
                notes.append(note)
                _refused(
                    store, f"reference {row.reference} = paper({ec}, {row.reference})", None,
                    requested=f"the literature page for reference {row.reference} of EC {ec}",
                    kind=REFERENCE_NOT_CAPTURED, settings={"why": why},
                )
    return tuple(notes)


def write_bundle_for(claim_set: ClaimSet, store: EvidenceStore, directory: str | Path) -> ClaimSet:
    """Write the closure of the root claim to `directory` and return the
    ClaimSet with the bundle's counts filled in."""
    try:
        from caterva.evidence.bundle import read_bundle
    except ImportError:  # pragma: no cover - flat layout
        from evidence.bundle import read_bundle  # type: ignore[no-redef]
    target = store.export_bundle(claim_set.root, directory)
    bundle = read_bundle(target)
    return ClaimSet(
        root=claim_set.root, claims=claim_set.claims, by_identifier=claim_set.by_identifier,
        notes=claim_set.notes, directory=target, store=claim_set.store,
        rows=len(bundle.rows), snapshots=len(bundle.snapshots),
    )


class SearchRecorder(Recorder):
    """A Recorder that takes each page as the search reads it and stores
    them when the search is over.

    The search's parameter scouts run on worker threads (caterva/agents/
    scheduler.py), so `fetch_brenda_html` calls the observer off the thread
    that opened the store, and the store's SQLite connection refuses a call
    from another thread. Storing at once from the observer therefore
    stopped every fetch, and the search reported itself unable to run. So
    the observer only keeps the page, with the moment it was read and the
    recording it came from, under a lock; `flush`, on the opening thread,
    stores each in the order it was read. The same page read twice (one
    scout per constant) is one snapshot, whose record is the first read's.
    """

    def __init__(self, store: EvidenceStore) -> None:
        """`store` is the EvidenceStore every observed page is flushed into."""
        super().__init__(store)
        self._pending: list[tuple[str, str, str | None, str]] = []
        self._lock = threading.Lock()

    def _observe(self, ec_number: str, html: str, served_from: str | None) -> None:
        with self._lock:
            self._pending.append(
                (str(ec_number), html, str(served_from) if served_from else None, now_utc()),
            )

    def flush(self) -> None:
        """Store every page kept since the last flush; `snapshots` fills here."""
        with self._lock:
            pending, self._pending = self._pending, []
        for ec, html, served_from, read_at in pending:
            self.snapshots[ec] = self.store.put_snapshot(
                html.encode("utf-8"), source="brenda_enzyme", locator=enzyme_page_url(ec),
                retrieved_at=read_at, licence=BRENDA_LICENCE, served_from=served_from,
            )


@dataclass
class ClaimsRun:
    """One `--claims DIR` run, from the store's opening to the bundle.

    `start_recording` before the literature search and `stop_recording`
    after it bound the Recorder to the search alone: pages read outside it
    (there are none today) would otherwise be pinned as the search's.
    `finish` builds the claims, captures the references and writes the
    bundle; `close` releases the store. A `with` block closes on exit.
    """

    directory: Path
    store: EvidenceStore = field(init=False)
    recorder: SearchRecorder = field(init=False)
    _recording: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.store = EvidenceStore(self.directory / STORE_DIR)
        self.recorder = SearchRecorder(self.store)

    def start_recording(self) -> None:
        if not self._recording:
            self.recorder.__enter__()
            self._recording = True

    def stop_recording(self) -> None:
        if self._recording:
            self.recorder.__exit__(None, None, None)
            self._recording = False
        self.recorder.flush()

    def finish(self, provenanced: Any, model: Any) -> ClaimSet:
        """The claims of `provenanced`/`model`, stored, referenced and bundled."""
        self.stop_recording()
        claim_set = claims_for_model(provenanced, model, self.store, self.recorder)
        notes = capture_references(claim_set, self.store)
        claim_set = ClaimSet(root=claim_set.root, claims=claim_set.claims,
                             by_identifier=claim_set.by_identifier, notes=notes,
                             store=claim_set.store)
        return write_bundle_for(claim_set, self.store, self.directory)

    def close(self) -> None:
        self.stop_recording()
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def manifest_root(directory: str | Path) -> str:
    """The root claim ref a bundle's manifest names (for a test or a script
    that has the directory and not the ClaimSet)."""
    try:
        from caterva.evidence.bundle import MANIFEST
    except ImportError:  # pragma: no cover - flat layout
        from evidence.bundle import MANIFEST  # type: ignore[no-redef]
    manifest = json.loads((Path(directory) / MANIFEST).read_text(encoding="utf-8"))
    return str(manifest["root"])


__all__ = [
    "ORDINALS_NOT_CARRIED",
    "PAGE_NOT_PINNED",
    "QUANTITY_NAMES",
    "RECHECK_LINE",
    "REFERENCE_NOT_CAPTURED",
    "ROW_NOT_CERTIFIED",
    "ROW_NOT_FOUND",
    "STORE_DIR",
    "ClaimSet",
    "ClaimsRun",
    "SearchRecorder",
    "capture_references",
    "claims_for_model",
    "ir_digest",
    "manifest_root",
    "write_bundle_for",
]
