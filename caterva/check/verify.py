"""Re-check a claims bundle against its own pinned bytes, with the standard library only.

WHY A SECOND IMPLEMENTATION
---------------------------
`caterva/evidence/` writes a bundle: claims whose ids are digests of their
derivations, rows whose ids are digests of their fields, and the raw bytes
of every page they were read from. This module reads one back and re-derives
everything it can from the stored fields and the stored bytes. It imports
nothing from `caterva/evidence/` (a guard, `scripts/
check_checker_independence.py`, keeps it so) and so repeats two definitions
word for word rather than importing them:

  * canonical JSON: `json.dumps(obj, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False, allow_nan=False).encode("utf-8")`, floats refused,
    and a digest is `"sha256:" + hexdigest` of those bytes;
  * the identity dicts: a row's is `{"parser", "locator", "fields"}` with
    fields snapshot, quantity, value_text, unit, substrate, organism,
    accession, commentary, reference; a claim's is `{"kind", "subject",
    "unit", "tolerance", "derivation"}`, plus `value_text` for every kind
    but `computed`, plus `refusal` when the claim is one.

If the two implementations ever disagree, `caterva verify` fails on every
bundle, which is the right failure: the format has two readings and one of
them is wrong.

THE EIGHT CHECKS, BY NAME
-------------------------
  snapshot bytes   each blob under snapshots/<hex>.gz gunzips to at most
                   MAX_PAGE_BYTES and its sha256 is the snapshot's id
  identity         every row id and claim id recomputes from the stored
                   fields; a mismatch names the claim (for a row, the claims
                   that cite it)
  row locator      a cited claim's single input is a row in rows.jsonl, the
                   row's snapshot is in snapshots.jsonl, the reference id,
                   the value, the substrate, the organism (unless "any") and
                   (when present) the commentary are cells of ONE TABLE ROW
                   of the page, and the claim's value and unit are the row's
                   (a stated unit factor moves that comparison to "unit
                   arithmetic")
  certificate      each certificate's [start, end) lies inside its snapshot
                   and the bytes there decode to `matched`; for a cited
                   claim, every span also lies inside ONE table row, that row
                   holds the cited row's five texts as the row locator finds
                   them, and the spans certify its reference, value and
                   commentary
  dominance        with settings["ordinals"], the chosen row is not strictly
                   dominated by an alternative; without, "not certified": the
                   check did not run, and the report says so (status "not
                   run", printed `n/a`), never that it passed
  unit arithmetic  with settings["unit_factor"], value == row value × factor
                   within the claim's tolerance, in Decimal
  inputs           a computed claim's inputs exist (an `ir:` input is the
                   digest settings["ir"] names); a chosen or placeholder claim
                   cites no row; a refusal's candidates are rows in the bundle
  root             the manifest's root is a claim in the bundle, and computed

and anything the checker cannot do -- regenerate the Antimony, replay the
integration -- is listed under "not checked" with the reason, never left out.

THREE STATES, NOT TWO
---------------------
A check held, failed, or did not run (`Check.status`: "ok", "failed", "not
run"). The third is its own state because the alternative is a lie in one
direction or the other: counted as ok, a dominance check that had no
ordinals to compare reads as a pick that was compared and survived; counted
as failed, a bundle that states honestly that it carried no ordinals could
never be re-checked at all. A check that did not run does not fail the
bundle (`Report.ok` is "nothing failed"), is printed `n/a` with its reason,
and is counted apart from the checks that held.

WHY A CERTIFICATE IS HELD TO THE CITED ROW
------------------------------------------
A span that reads as its text proves only that the page holds the text
somewhere. Without the row tie, a claim could cite row B and carry row A's
spans: on the recorded hexokinase page a Km claim citing the 0.63 mM
D-glucose row of reference 702314 with the five spans of the 0.63 mM ATP
row of reference 641068 passed every check (found 2026-10-24), because the
value matched and every span read. `caterva why` shows those spans as "the
bytes that say it", so they must be the cited row's bytes.

Reference, value and commentary are not enough to name the row. One paper
often reports several substrates, or species, under the same conditions
with the same value: on the same page reference 674800 gives kcat 53.2 1/s
at "37°C, pH 7.4, wild-type enzyme" for ATP and for D-glucose in Mus
musculus, two table rows, and a claim citing the D-glucose row with the ATP
row's five spans (one of them reading 'ATP') passed while the tie looked at
three texts (found 2026-10-24). So the substrate and the organism are
cells of the one row too, for the row locator and for the tie alike.
Counted 2026-10-24 over the Km, kcat and Ki tables of the two recorded
pages: every one of the 1,681 rows the producer can certify and whose
texts the page holds (718 on hexokinase's, 963 on EC 1.4.3.4's) has a
table row holding all five, so no honest citation is refused; and for 60
of them (14 and 46) the producer's
spans lie in a neighbour that shares the three texts, which the tie now
refuses rather than passes.

WHAT "ONE TABLE ROW" IS
-----------------------
No HTML parser. On a BRENDA enzyme page every data row opens with a div
whose id is `tab<N>r<N>` or `tab<N>r<N>sr<N>` (a table header row is
`tab<N>_head`) and whose class starts with "row" or "hidden" (hidden until
the reader expands the group); cells are divs whose ids end in `c<N>`, so
the id alone tells a row from a cell. Looked at in the recorded hexokinase
page (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz, fetched 2026-09-28,
sha256 3a69b492…5060ef91) around the 6 mM row of reference 641068:

    <div id="tab12r13sr112" class="hidden rgrey1">
    <div id="tab12r13sr112c0" class="cell"><span>6
    </span></div>...<span>30°C, pH 7.5, wild-type
    </span></div>...<a href="./literature.php?e=2.7.1.1&r=641068" target="_blank">641068</a>

so a row is the bytes from one such opening (ROW_OPENING below; 4,615 of
them on that page, counted 2026-10-17) to the next, or to the end of the
page. Within a row a text counts only as a whole cell text: right after a
`>` and right before the cell's newline or closing tag, so a reference id
inside an href, or a number inside a longer one, is not the row saying it.
The value is matched as a number, not as characters: the row records the
parser's float with fifteen significant digits and the cell may spell the
same number differently, so two cell texts are the same value when they are
equal as Decimals.

WHAT IS NOT CHECKED, AND WHY
----------------------------
Position: a certificate and a row locator prove that the bytes hold the
texts, within one row, not that the row is the n-th duplicate the locator
names. Whether the paper was right, or the resolver's rule was a good rule:
the checker holds a bundle to its own derivations and stated reasons.
"""
from __future__ import annotations

import hashlib
import json
import re
import zlib
from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

FORMAT = "caterva-claims/1"
MANIFEST = "manifest.json"
CLAIMS = "claims.jsonl"
ROWS = "rows.jsonl"
SNAPSHOTS = "snapshots.jsonl"
BLOBS = "snapshots"

DIGEST_PREFIX = "sha256:"
KINDS = ("cited", "chosen", "placeholder", "refused", "computed")
REF_KINDS = ("snapshot", "row", "claim", "ir")

#: The opening of a row on a BRENDA enzyme page (module docstring).
ROW_OPENING = re.compile(rb'<div id="tab\d+(?:_head|r\d+(?:sr\d+)?)" class="(?:row|hidden)[ "]')

#: A number standing as a whole cell text.
_CELL_NUMBER = re.compile(rb">(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?:\n|<)")

#: The most a pinned page may inflate to. A bundle is the thing people share
#: and re-check without having written it, and gzip lets a 200 KB blob
#: inflate to gigabytes before its hash can be compared (a 203,860-byte blob
#: of 200 MiB of zeros grew the process by 200 MB, measured 2026-10-24). The
#: largest BRENDA enzyme page the repository records is 5.8 MB (EC 1.4.3.4,
#: Tests/fixtures/ki_mode/brenda_1.4.3.4.html.gz; hexokinase's is 3.7 MB),
#: so 64 MiB is eleven times the largest real page and still a bound on
#: what a stranger's bundle can make this process hold.
MAX_PAGE_BYTES = 64 * 1024 * 1024

#: How much of a blob is read from disk at once: the compressed file is not
#: read whole either.
_READ_CHUNK = 1024 * 1024

#: The organism of a row read for every organism (caterva/evidence/rows.py
#: ANY_ORGANISM, repeated rather than imported).
ANY_ORGANISM = "any"

#: `Check.status`: the check held, failed, or did not run ("THREE STATES").
STATUS_OK, STATUS_FAILED, STATUS_NOT_RUN = "ok", "failed", "not run"
STATUSES = (STATUS_OK, STATUS_FAILED, STATUS_NOT_RUN)

#: What the checker cannot do, listed so the report says so.
NOT_CHECKED = (
    (
        "Antimony regeneration",
        'the computed claim names its compiled source by digest (settings["ir"]); '
        "regenerating the source needs the composer, which this checker does not "
        "import, so the digest is read and not reproduced",
    ),
    (
        "ODE replay",
        "a computed value is held to the claim's tolerance by whoever re-integrates "
        "the model; this checker imports no integrator and replays nothing",
    ),
)


class BundleMalformed(ValueError):  # noqa: N818 - a refusal, named as the repository names them (ExportRefused, ADR 0024)
    """The directory is not a bundle of this format: nothing in it was checked.

    Distinct from a failed check on purpose. A file that is not a bundle has
    not been checked and found wanting; it has not been checked. `caterva
    verify` reports this as exit 2, a failed check as exit 3.
    """


@dataclass(frozen=True)
class Check:
    """One line of the report: which check, about which claim, and what it found.

    `claim` is the claim ref the check is about, or None for a check about a
    snapshot or a row, whose `detail` then starts with that record's ref.

    `ok` is "did not fail"; `ran` False marks a check that did not run (its
    `detail` says why), which is never a failure and never a pass: `status`
    is the one answer to read ("THREE STATES" in the module docstring).
    """

    name: str
    claim: str | None
    ok: bool
    detail: str
    ran: bool = True

    def __post_init__(self) -> None:
        if not self.ran and not self.ok:
            raise ValueError(f"{self.name}: a check that did not run cannot have failed")

    @property
    def status(self) -> str:
        """STATUS_OK, STATUS_FAILED or STATUS_NOT_RUN."""
        if not self.ran:
            return STATUS_NOT_RUN
        return STATUS_OK if self.ok else STATUS_FAILED


@dataclass
class Report:
    """Every check, and whether none of them failed.

    `ok` is "nothing failed", which is what exit 0 means: a check that did
    not run does not make a bundle unreadable, and it is not counted as one
    that held either (`held()`, `not_run()`).
    """

    ok: bool
    checks: list[Check] = field(default_factory=list)

    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == STATUS_FAILED]

    def held(self) -> list[Check]:
        return [c for c in self.checks if c.status == STATUS_OK]

    def not_run(self) -> list[Check]:
        return [c for c in self.checks if c.status == STATUS_NOT_RUN]

    def to_dict(self) -> dict:
        """The `--json` report. `status` is the three-way answer; `ok` stays,
        meaning "did not fail", for readers that predate `status`."""
        return {
            "ok": self.ok,
            "checks": [
                {"name": c.name, "claim": c.claim, "ok": c.ok, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Canonical JSON and digests: the definition, repeated, not imported
# ---------------------------------------------------------------------------

def refuse_floats(obj: Any, path: str = "$") -> None:
    """Raise TypeError naming the first float (or non-string key) in `obj`."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return
    if isinstance(obj, float):
        raise TypeError(f"{path} is a float ({obj!r}); every number in an identity is a decimal string")
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a key that is not a string: {key!r}")
            refuse_floats(value, f"{path}.{key}")
        return
    if isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            refuse_floats(value, f"{path}[{index}]")
        return
    raise TypeError(f"{path} is a {type(obj).__name__}, which canonical JSON does not carry")


def canonical_bytes(obj: Any) -> bytes:
    """The one serialisation of `obj`; floats are refused (TypeError)."""
    refuse_floats(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def digest(data: bytes) -> str:
    """`"sha256:<64 hex>"` of `data`."""
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def is_digest(text: Any) -> bool:
    return (
        isinstance(text, str)
        and text.startswith(DIGEST_PREFIX)
        and len(text) == len(DIGEST_PREFIX) + 64
        and all(c in "0123456789abcdef" for c in text[len(DIGEST_PREFIX):])
    )


def ref_kind(ref: Any) -> str | None:
    """The kind a reference names, or None when the string is not a reference."""
    if not isinstance(ref, str):
        return None
    kind, _, rest = ref.partition(":")
    return kind if kind in REF_KINDS and is_digest(rest) else None


def ref_digest(ref: str) -> str:
    return ref.partition(":")[2]


# ---------------------------------------------------------------------------
# Records, read with their types held to the format
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotRecord:
    id: str
    source: str
    locator: str
    retrieved_at: str
    licence: str
    release: str | None
    served_from: str | None

    @property
    def ref(self) -> str:
        return f"snapshot:{self.id}"


@dataclass(frozen=True)
class RowRecord:
    id: str
    snapshot: str
    parser: dict
    locator: str
    quantity: str
    value_text: str
    unit: str
    substrate: str
    organism: str
    accession: str | None
    commentary: str | None
    reference: str | None

    @property
    def ref(self) -> str:
        return f"row:{self.id}"


@dataclass(frozen=True)
class ClaimRecord:
    id: str
    kind: str
    subject: str
    value_text: str | None
    unit: str | None
    tolerance: str | None
    rule: dict
    inputs: list[str]
    certificates: list[dict]
    settings: dict[str, str]
    refusal: dict | None

    @property
    def ref(self) -> str:
        return f"claim:{self.id}"

    @property
    def identifier(self) -> str:
        """The model identifier a subject starts with (`reaction_Km = Km(...)` -> `reaction_Km`)."""
        return self.subject.split(" = ", 1)[0]

    def row_inputs(self) -> list[str]:
        return [r for r in self.inputs if ref_kind(r) == "row"]


@dataclass
class BundleFiles:
    """What the directory holds, keyed by ref, before any check runs."""

    directory: Path
    manifest: dict
    claims: dict[str, ClaimRecord] = field(default_factory=dict)
    rows: dict[str, RowRecord] = field(default_factory=dict)
    snapshots: dict[str, SnapshotRecord] = field(default_factory=dict)

    @property
    def root(self) -> str:
        return str(self.manifest["root"])

    def blob_path(self, snapshot_id: str) -> Path:
        return self.directory / BLOBS / (snapshot_id[len(DIGEST_PREFIX):] + ".gz")


def _need(record: dict, name: str, where: str, types: tuple, *, optional: bool = False) -> Any:
    """A field of the right type, or BundleMalformed naming it."""
    if name not in record:
        if optional:
            return None
        raise BundleMalformed(f"{where} has no {name!r}")
    value = record[name]
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, types):
        wanted = " or ".join(t.__name__ for t in types)
        raise BundleMalformed(f"{where}: {name!r} is {type(value).__name__}, not {wanted}")
    return value


def _decimal(text: str, what: str) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BundleMalformed(f"{what} {text!r} is not a decimal number") from exc
    if not value.is_finite():
        raise BundleMalformed(f"{what} {text!r} is not finite")
    return value


def _rule(record: Any, where: str) -> dict:
    if not isinstance(record, dict):
        raise BundleMalformed(f"{where}: the rule is not an object")
    rule = {
        "rule_id": _need(record, "rule_id", where + " rule", (str,)),
        "version": _need(record, "version", where + " rule", (int,)),
        "adr": _need(record, "adr", where + " rule", (str,)),
    }
    if rule["version"] < 1:
        raise BundleMalformed(f"{where}: rule version {rule['version']} is not a positive integer")
    return rule


def _snapshot(record: Any, where: str) -> SnapshotRecord:
    if not isinstance(record, dict):
        raise BundleMalformed(f"{where} is not an object")
    snapshot = SnapshotRecord(
        id=_need(record, "id", where, (str,)),
        source=_need(record, "source", where, (str,)),
        locator=_need(record, "locator", where, (str,)),
        retrieved_at=_need(record, "retrieved_at", where, (str,)),
        licence=_need(record, "licence", where, (str,)),
        release=_need(record, "release", where, (str,), optional=True),
        served_from=_need(record, "served_from", where, (str,), optional=True),
    )
    if not is_digest(snapshot.id):
        raise BundleMalformed(f"{where}: id {snapshot.id!r} is not of the form sha256:<64 hex>")
    return snapshot


def _row(record: Any, where: str) -> RowRecord:
    if not isinstance(record, dict):
        raise BundleMalformed(f"{where} is not an object")
    row = RowRecord(
        id=_need(record, "id", where, (str,)),
        snapshot=_need(record, "snapshot", where, (str,)),
        parser=_rule(_need(record, "parser", where, (dict,)), where),
        locator=_need(record, "locator", where, (str,)),
        quantity=_need(record, "quantity", where, (str,)),
        value_text=_need(record, "value_text", where, (str,)),
        unit=_need(record, "unit", where, (str,)),
        substrate=_need(record, "substrate", where, (str,)),
        organism=_need(record, "organism", where, (str,)),
        accession=_need(record, "accession", where, (str,), optional=True),
        commentary=_need(record, "commentary", where, (str,), optional=True),
        reference=_need(record, "reference", where, (str,), optional=True),
    )
    if not is_digest(row.id):
        raise BundleMalformed(f"{where}: id {row.id!r} is not of the form sha256:<64 hex>")
    if ref_kind(row.snapshot) != "snapshot":
        raise BundleMalformed(f"{where}: snapshot {row.snapshot!r} is not a snapshot ref")
    _decimal(row.value_text, f"{where}: value_text")
    return row


def _certificate(record: Any, where: str) -> dict:
    if not isinstance(record, dict):
        raise BundleMalformed(f"{where} is not an object")
    span = _need(record, "span", where, (list,))
    if len(span) != 2 or any(isinstance(s, bool) or not isinstance(s, int) for s in span):
        raise BundleMalformed(f"{where}: span {span!r} is not [start, end]")
    certificate = {
        "snapshot": _need(record, "snapshot", where, (str,)),
        "span": [span[0], span[1]],
        "matched": _need(record, "matched", where, (str,)),
    }
    if ref_kind(certificate["snapshot"]) != "snapshot":
        raise BundleMalformed(f"{where}: snapshot {certificate['snapshot']!r} is not a snapshot ref")
    return certificate


def _claim(record: Any, where: str) -> ClaimRecord:
    if not isinstance(record, dict):
        raise BundleMalformed(f"{where} is not an object")
    derivation = _need(record, "derivation", where, (dict,))
    inputs = _need(derivation, "inputs", where + " derivation", (list,), optional=True) or []
    certificates = _need(derivation, "certificates", where + " derivation", (list,), optional=True) or []
    settings = _need(derivation, "settings", where + " derivation", (dict,), optional=True) or {}
    for key, value in settings.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise BundleMalformed(f"{where}: setting {key!r} -> {value!r} is not a string")
    for ref in inputs:
        if ref_kind(ref) is None:
            raise BundleMalformed(f"{where}: input {ref!r} is not a reference")
    refusal_record = _need(record, "refusal", where, (dict,), optional=True)
    refusal = None
    if refusal_record is not None:
        candidates = _need(refusal_record, "candidates", where + " refusal", (list,), optional=True) or []
        if any(not isinstance(c, str) for c in candidates):
            raise BundleMalformed(f"{where}: a refusal candidate is not a string")
        refusal = {
            "requested": _need(refusal_record, "requested", where + " refusal", (str,)),
            "kind": _need(refusal_record, "kind", where + " refusal", (str,)),
            "candidates": list(candidates),
        }
    claim = ClaimRecord(
        id=_need(record, "id", where, (str,)),
        kind=_need(record, "kind", where, (str,)),
        subject=_need(record, "subject", where, (str,)),
        value_text=_need(record, "value_text", where, (str,), optional=True),
        unit=_need(record, "unit", where, (str,), optional=True),
        tolerance=_need(record, "tolerance", where, (str,), optional=True),
        rule=_rule(_need(derivation, "rule", where + " derivation", (dict,)), where),
        inputs=list(inputs),
        certificates=[_certificate(c, f"{where} certificate {i}") for i, c in enumerate(certificates)],
        settings=dict(settings),
        refusal=refusal,
    )
    if not is_digest(claim.id):
        raise BundleMalformed(f"{where}: id {claim.id!r} is not of the form sha256:<64 hex>")
    if claim.kind not in KINDS:
        raise BundleMalformed(f"{where}: kind {claim.kind!r} is not one of {KINDS}")
    if claim.value_text is not None:
        _decimal(claim.value_text, f"{where}: value_text")
    if claim.tolerance is not None:
        _decimal(claim.tolerance, f"{where}: tolerance")
    return claim


def _lines(path: Path, reader, what: str) -> list:
    if not path.is_file():
        raise BundleMalformed(f"{path} is missing")
    out = []
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError as exc:
            raise BundleMalformed(f"{path}:{number} is not JSON: {exc}") from exc
        out.append(reader(data, f"{what} at {path.name}:{number}"))
    return out


def read_bundle_files(directory: str | Path) -> BundleFiles:
    """Read the manifest and the three record files; BundleMalformed when they are not a bundle."""
    target = Path(directory)
    manifest_path = target / MANIFEST
    if not target.is_dir():
        raise BundleMalformed(f"{target} is not a directory")
    if not manifest_path.is_file():
        raise BundleMalformed(f"{manifest_path} is missing: {target} is not a claims bundle")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BundleMalformed(f"{manifest_path} is not JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BundleMalformed(f"{manifest_path} is not an object")
    if manifest.get("format") != FORMAT:
        raise BundleMalformed(f"{manifest_path} declares format {manifest.get('format')!r}, not {FORMAT!r}")
    if ref_kind(manifest.get("root")) != "claim":
        raise BundleMalformed(f"{manifest_path}: root {manifest.get('root')!r} is not a claim ref")
    bundle = BundleFiles(directory=target, manifest=manifest)
    for claim in _lines(target / CLAIMS, _claim, "claim"):
        bundle.claims[claim.ref] = claim
    for row in _lines(target / ROWS, _row, "row"):
        bundle.rows[row.ref] = row
    for snapshot in _lines(target / SNAPSHOTS, _snapshot, "snapshot"):
        bundle.snapshots[snapshot.ref] = snapshot
    return bundle


# ---------------------------------------------------------------------------
# Identity, from the stored fields
# ---------------------------------------------------------------------------

def row_identity(row: RowRecord) -> dict:
    """The dict whose canonical bytes a row's id digests (module docstring)."""
    return {
        "parser": dict(row.parser),
        "locator": row.locator,
        "fields": {
            "snapshot": row.snapshot,
            "quantity": row.quantity,
            "value_text": row.value_text,
            "unit": row.unit,
            "substrate": row.substrate,
            "organism": row.organism,
            "accession": row.accession,
            "commentary": row.commentary,
            "reference": row.reference,
        },
    }


def claim_identity(claim: ClaimRecord) -> dict:
    """The dict whose canonical bytes a claim's id digests (module docstring)."""
    identity: dict[str, Any] = {
        "kind": claim.kind,
        "subject": claim.subject,
        "unit": claim.unit,
        "tolerance": claim.tolerance,
        "derivation": {
            "rule": dict(claim.rule),
            "inputs": list(claim.inputs),
            "certificates": [
                {"snapshot": c["snapshot"], "span": list(c["span"]), "matched": c["matched"]}
                for c in claim.certificates
            ],
            "settings": dict(claim.settings),
        },
    }
    if claim.kind != "computed":
        identity["value_text"] = claim.value_text
    if claim.refusal is not None:
        identity["refusal"] = {
            "requested": claim.refusal["requested"],
            "kind": claim.refusal["kind"],
            "candidates": list(claim.refusal["candidates"]),
        }
    return identity


def row_id(row: RowRecord) -> str:
    return digest(canonical_bytes(row_identity(row)))


def claim_id(claim: ClaimRecord) -> str:
    return digest(canonical_bytes(claim_identity(claim)))


# ---------------------------------------------------------------------------
# Finding a row in the bytes
# ---------------------------------------------------------------------------

def row_regions(page: bytes) -> list[int]:
    """Offsets of every row opening, in page order."""
    return [m.start() for m in ROW_OPENING.finditer(page)]


def region_of(offset: int, starts: list[int], length: int) -> tuple[int, int] | None:
    """The [start, end) of the row holding byte `offset`, or None outside every row."""
    index = bisect_right(starts, offset) - 1
    if index < 0:
        return None
    end = starts[index + 1] if index + 1 < len(starts) else length
    return starts[index], end


def _cell_pattern(text: str) -> re.Pattern:
    return re.compile(rb">" + re.escape(text.encode("utf-8")) + rb"(?:\n|<)")


def _value_in(page: bytes, value_text: str, start: int, end: int) -> bool:
    """A cell in [start, end) spells `value_text`, as characters or as the same Decimal."""
    if _cell_pattern(value_text).search(page, start, end):
        return True
    wanted = Decimal(value_text)
    for match in _CELL_NUMBER.finditer(page, start, end):
        try:
            if Decimal(match.group(1).decode("ascii")) == wanted:
                return True
        except InvalidOperation:
            continue
    return False


def _cell_patterns(*texts: str | None) -> list[re.Pattern]:
    return [_cell_pattern(text) for text in texts if text]


def _holds(page: bytes, start: int, end: int, cells: list[re.Pattern], value_text: str) -> bool:
    return all(cell.search(page, start, end) for cell in cells) and _value_in(page, value_text, start, end)


def row_holds(
    page: bytes, region: tuple[int, int], *, reference: str | None, value_text: str,
    commentary: str | None, substrate: str | None = None, organism: str | None = None,
) -> bool:
    """The table row at `region` has cells holding the reference id, the value,
    the commentary, the substrate and the organism (each that is given), by
    the rules find_row_region uses."""
    cells = _cell_patterns(reference, commentary, substrate, organism)
    return _holds(page, region[0], region[1], cells, value_text)


def find_row_region(
    page: bytes, *, reference: str | None, value_text: str, commentary: str | None,
    substrate: str | None = None, organism: str | None = None,
) -> tuple[int, int] | None:
    """The first table row whose cells hold the reference id, the value, the
    commentary, the substrate and the organism (each that is given), or None
    when no row holds all of them.

    The substrate and organism are cells of the row as the other three are:
    one paper often reports several substrates (or species) under the same
    conditions with the same value, so reference, value and commentary alone
    can name a neighbour ("WHY A CERTIFICATE IS HELD TO THE CITED ROW").
    """
    starts = row_regions(page)
    cells = _cell_patterns(reference, commentary, substrate, organism)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page)
        if _holds(page, start, end, cells, value_text):
            return start, end
    return None


def row_cells(row: RowRecord) -> dict[str, str | None]:
    """The texts a row is found by in its page, as find_row_region and
    row_holds take them. The organism is left out for a row read for any
    organism: no cell says "any"."""
    return {
        "reference": row.reference,
        "value_text": row.value_text,
        "commentary": row.commentary,
        "substrate": row.substrate,
        "organism": row.organism if row.organism != ANY_ORGANISM else None,
    }


def _described(row: RowRecord) -> str:
    """The row's texts as a report line names them: reference '…', value '…', …"""
    return ", ".join(f"{what} {text!r}" for what, text in (
        ("reference", row.reference), ("value", row.value_text), ("commentary", row.commentary),
        ("substrate", row.substrate), ("organism", row_cells(row)["organism"]),
    ) if text)


def same_number(text: str, value_text: str) -> bool:
    """`text` spells the number `value_text` names, compared as Decimals."""
    try:
        return Decimal(text) == Decimal(value_text)
    except (InvalidOperation, ValueError):
        # Not a number, or a signalling NaN, which refuses to be compared.
        return False


def occurs(page: bytes, text: str) -> bool:
    """`text` occurs in the page, as the UTF-8 bytes of the decoded page would hold it."""
    return page.find(text.encode("utf-8")) >= 0


# ---------------------------------------------------------------------------
# Dominance and unit arithmetic
# ---------------------------------------------------------------------------

def _ordinal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    # NaN cannot be compared and Infinity is not an ordinal: neither ranks.
    return number if number.is_finite() else None


def dominated(chosen: dict, alternative: dict) -> bool:
    """`alternative` strictly dominates `chosen`: at least as good on every
    COMPARABLE axis and better on one, higher being better.

    The order semantics of Tests/evidence_rank.py `dominates`, restated: an
    axis where either side is None is skipped, not scored (an axis that
    could not be assessed neither supports nor blocks dominance), and when
    no axis is comparable nothing dominates.
    """
    pairs = []
    for axis in sorted(set(chosen) | set(alternative)):
        mine, theirs = _ordinal(chosen.get(axis)), _ordinal(alternative.get(axis))
        if mine is not None and theirs is not None:
            pairs.append((theirs, mine))
    if not pairs:
        return False
    return all(theirs >= mine for theirs, mine in pairs) and any(theirs > mine for theirs, mine in pairs)


def within_tolerance(actual: Decimal, expected: Decimal, tolerance: str | None) -> bool:
    """`actual` equals `expected`, or lies within the relative `tolerance` of it."""
    if tolerance is None:
        return actual == expected
    return abs(actual - expected) <= Decimal(tolerance) * abs(expected)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

class PageTooLarge(ValueError):  # noqa: N818 - a refusal, named as BundleMalformed is
    """A blob inflates past the bound it is read under (MAX_PAGE_BYTES)."""


def _inflate(inflater: Any, data: bytes, out: bytearray, limit: int) -> None:
    """Feed `data` to one member's inflater, taking the output a piece of at
    most _READ_CHUNK bytes at a time into `out`; PageTooLarge past `limit`.

    A piece shorter than asked for means zlib took all the input and has
    nothing pending; a full one may leave output inside zlib, so it is asked
    again (with the unconsumed tail, possibly empty) until it runs dry or the
    member ends. Asking for whole remaining room at once would hand back one
    `limit`-sized object beside `out` and double what is held.
    """
    while True:
        # Never 0, which zlib reads as "no limit": len(out) <= limit here.
        want = min(_READ_CHUNK, limit + 1 - len(out))
        piece = inflater.decompress(data, want)
        out += piece
        if len(out) > limit:
            raise PageTooLarge(
                f"inflates past {limit:,} bytes (MAX_PAGE_BYTES) and was not read further: "
                "no page this format pins is that large"
            )
        if inflater.eof or len(piece) < want:
            return
        data = inflater.unconsumed_tail


def gunzip_bounded(path: Path, limit: int = MAX_PAGE_BYTES) -> bytes:
    """The bytes the gzip file at `path` holds, read the way `gzip.decompress`
    reads them (every member in turn, zero padding after a member allowed),
    a piece at a time: the file is read _READ_CHUNK bytes at once and the
    output is taken in pieces and stops one byte past `limit`, so a small
    blob cannot make this process hold more than the bound before the hash
    is compared.

    PageTooLarge once the output would pass `limit`; EOFError when the
    stream ends before its end-of-stream marker; zlib.error for a corrupt
    stream, header, CRC or length. The CRC and length are zlib's own checks
    (wbits 16 + MAX_WBITS reads the gzip wrapper).
    """
    out = bytearray()
    inflater = None  # the current member's, or None between members
    members = 0
    with path.open("rb") as handle:
        pending = b""
        while True:
            if not pending:
                pending = handle.read(_READ_CHUNK)
                if not pending:
                    break
            if inflater is None:
                if members:
                    # gzip.decompress strips zero padding after a member.
                    pending = pending.lstrip(b"\x00")
                    if not pending:
                        continue
                inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
            _inflate(inflater, pending, out, limit)
            if inflater.eof:
                # What follows a member's trailer: padding, another member, or nothing.
                pending = inflater.unused_data
                inflater = None
                members += 1
            else:
                pending = b""
    if inflater is not None:
        raise EOFError("Compressed file ended before the end-of-stream marker was reached")
    return bytes(out)


class _Pages:
    """Snapshot bytes, read once each; None when the blob is missing or wrong."""

    def __init__(self, bundle: BundleFiles) -> None:
        self.bundle = bundle
        self.bytes: dict[str, bytes | None] = {}
        self.problems: dict[str, str] = {}

    def load(self, snapshot: SnapshotRecord) -> bytes | None:
        if snapshot.ref in self.bytes:
            return self.bytes[snapshot.ref]
        path = self.bundle.blob_path(snapshot.id)
        data: bytes | None = None
        if not path.is_file():
            self.problems[snapshot.ref] = f"{path.name} is missing under {BLOBS}/"
        else:
            try:
                data = gunzip_bounded(path)
            except PageTooLarge as exc:
                self.problems[snapshot.ref] = f"{path.name} {exc}"
            except (OSError, EOFError, ValueError, zlib.error) as exc:
                self.problems[snapshot.ref] = f"{path.name} does not gunzip: {exc}"
        if data is not None and digest(data) != snapshot.id:
            self.problems[snapshot.ref] = (
                f"{path.name} gunzips to {len(data):,} bytes whose sha256 is {digest(data)}, not the snapshot's id"
            )
        self.bytes[snapshot.ref] = data
        return data

    def get(self, ref: str) -> bytes | None:
        snapshot = self.bundle.snapshots.get(ref)
        return None if snapshot is None else self.load(snapshot)


def _claims_holding(bundle: BundleFiles, snapshot_ref: str) -> list[ClaimRecord]:
    """Claims that depend on a snapshot, through a cited row or a certificate."""
    rows = {ref for ref, row in bundle.rows.items() if row.snapshot == snapshot_ref}
    return [
        claim for claim in bundle.claims.values()
        if any(ref in rows for ref in claim.inputs)
        or any(c["snapshot"] == snapshot_ref for c in claim.certificates)
    ]


def _names(claims: list[ClaimRecord]) -> str:
    return ", ".join(f"{c.identifier} ({c.ref})" for c in claims) or "no claim"


def _check_snapshots(bundle: BundleFiles, pages: _Pages, out: list[Check]) -> None:
    for snapshot in bundle.snapshots.values():
        data = pages.load(snapshot)
        held = _claims_holding(bundle, snapshot.ref)
        if data is None or snapshot.ref in pages.problems:
            out.append(Check(
                "snapshot bytes", None, False,
                f"{snapshot.ref}: {pages.problems[snapshot.ref]}; held by {_names(held)}",
            ))
        else:
            out.append(Check(
                "snapshot bytes", None, True,
                f"{snapshot.ref}: {len(data):,} bytes, {snapshot.source}, retrieved {snapshot.retrieved_at}",
            ))


def _check_row_identity(bundle: BundleFiles, out: list[Check]) -> None:
    for row in bundle.rows.values():
        try:
            expected = row_id(row)
        except TypeError as exc:
            expected = None
            why = f"its fields cannot be serialised canonically: {exc}"
        else:
            why = f"its fields digest to {expected}"
        if expected == row.id:
            out.append(Check("identity", None, True, f"{row.ref}: recomputes from its fields; {row.locator}"))
            continue
        citing = [c for c in bundle.claims.values() if row.ref in c.inputs]
        detail = f"{row.ref} ({row.locator}): stored id does not recompute, {why}"
        if citing:
            out.extend(Check("identity", c.ref, False, f"{c.identifier} cites {detail}") for c in citing)
        else:
            out.append(Check("identity", None, False, detail))


def _check_claim_identity(claim: ClaimRecord, out: list[Check]) -> None:
    try:
        expected = claim_id(claim)
    except TypeError as exc:
        out.append(Check(
            "identity", claim.ref, False,
            f"{claim.identifier}: the stored fields cannot be serialised canonically: {exc}",
        ))
        return
    if expected == claim.id:
        out.append(Check("identity", claim.ref, True, f"{claim.identifier}: recomputes from its derivation"))
    else:
        out.append(Check(
            "identity", claim.ref, False,
            f"{claim.identifier}: stored id does not recompute; the stored fields digest to {expected}",
        ))


def _check_row_locator(bundle: BundleFiles, pages: _Pages, claim: ClaimRecord, out: list[Check]) -> None:
    name = "row locator"
    who = claim.identifier
    rows = claim.row_inputs()
    if len(claim.inputs) != 1 or len(rows) != 1:
        out.append(Check(name, claim.ref, False, f"{who}: a cited claim has one input, a row; this one has {claim.inputs}"))
        return
    row = bundle.rows.get(rows[0])
    if row is None:
        out.append(Check(name, claim.ref, False, f"{who}: cites {rows[0]}, which is not in {ROWS}"))
        return
    if row.snapshot not in bundle.snapshots:
        out.append(Check(name, claim.ref, False, f"{who}: row {row.locator} was read from {row.snapshot}, which is not in {SNAPSHOTS}"))
        return
    foreign = [c["snapshot"] for c in claim.certificates if c["snapshot"] != row.snapshot]
    if foreign:
        out.append(Check(name, claim.ref, False, f"{who}: certifies spans in {foreign[0]}, not in the row's snapshot {row.snapshot}"))
        return
    page = pages.get(row.snapshot)
    if page is None:
        out.append(Check(name, claim.ref, False, f"{who}: the bytes of {row.snapshot} are not available to search ({pages.problems.get(row.snapshot)})"))
        return
    missing = [
        # The value is held to the row numerically by find_row_region: its
        # printed form ("2.3e-07") is not how BRENDA spells the cell.
        text for text in (row.reference, row.commentary, row.substrate,
                          row.organism if row.organism != "any" else None)
        if text and not occurs(page, text)
    ]
    if missing:
        out.append(Check(name, claim.ref, False, f"{who}: the page does not hold {missing[0]!r} (row {row.locator})"))
        return
    region = find_row_region(page, **row_cells(row))
    if region is None:
        out.append(Check(
            name, claim.ref, False,
            f"{who}: no one table row holds {_described(row)} together (row {row.locator})",
        ))
        return
    if "unit_factor" in claim.settings:
        value_note = "value compared under unit arithmetic"
    else:
        if claim.value_text is None or Decimal(claim.value_text) != Decimal(row.value_text) or claim.unit != row.unit:
            out.append(Check(
                name, claim.ref, False,
                f"{who}: cites {claim.value_text} {claim.unit} but the row holds {row.value_text} {row.unit} "
                f"and no unit factor is stated (row {row.locator})",
            ))
            return
        value_note = f"value {claim.value_text} {claim.unit} is the row's"
    out.append(Check(
        name, claim.ref, True,
        f"{who}: row {row.locator} found in bytes [{region[0]}, {region[1]}) of {row.snapshot}; {value_note}",
    ))


def _row_tie(bundle: BundleFiles, pages: _Pages, claim: ClaimRecord) -> tuple[str | None, str]:
    """(problem, where) for a cited claim with at least one span that reads.

    `problem` says why the spans are not the cited row's (module docstring,
    "WHY A CERTIFICATE IS HELD TO THE CITED ROW"), or is None when they are;
    `where` then names the table row they lie in, for the report line.
    """
    rows = claim.row_inputs()
    row = bundle.rows.get(rows[0]) if len(claim.inputs) == 1 and len(rows) == 1 else None
    if row is None:
        return f"no one cited row in {ROWS} to hold the spans to (see row locator)", ""
    page = pages.get(row.snapshot)
    if page is None:
        return f"the bytes of the row's snapshot {row.snapshot} are not available to hold the spans to", ""
    starts = row_regions(page)
    regions: set[tuple[int, int]] = set()
    for certificate in claim.certificates:
        start, end = certificate["span"]
        if certificate["snapshot"] != row.snapshot:
            return f"span [{start}, {end}) is in {certificate['snapshot']}, not in the row's snapshot {row.snapshot}", ""
        region = region_of(start, starts, len(page))
        if region is None:
            return f"span [{start}, {end}) ({certificate['matched']!r}) lies outside every table row of the page", ""
        if end > region[1]:
            return f"span [{start}, {end}) ({certificate['matched']!r}) runs past the end of the table row at bytes [{region[0]}, {region[1]})", ""
        regions.add(region)
    if len(regions) > 1:
        listed = ", ".join(f"[{a}, {b})" for a, b in sorted(regions))
        return f"the spans lie in {len(regions)} different table rows ({listed}); one row's texts lie in one", ""
    (region,) = regions
    if not row_holds(page, region, **row_cells(row)):
        return (
            f"the spans lie in the table row at bytes [{region[0]}, {region[1]}), which does not hold "
            f"the cited row {row.locator} ({_described(row)})", ""
        )
    matched = [c["matched"] for c in claim.certificates]
    for what, text in (("reference", row.reference), ("commentary", row.commentary)):
        if text and text not in matched:
            return f"no span certifies the cited row's {what} {text!r} (row {row.locator})", ""
    if not any(same_number(text, row.value_text) for text in matched):
        return f"no span certifies the cited row's value {row.value_text!r} (row {row.locator})", ""
    return None, f"all within the table row at bytes [{region[0]}, {region[1]}) that holds row {row.locator}"


def _check_certificates(bundle: BundleFiles, pages: _Pages, claim: ClaimRecord, out: list[Check]) -> None:
    if claim.kind == "cited" and not claim.certificates:
        out.append(Check(
            "certificate", claim.ref, False,
            f"{claim.identifier}: certifies no span; a cited claim's spans are its row's reference, "
            "value and commentary in the pinned bytes",
        ))
        return
    for certificate in claim.certificates:
        start, end = certificate["span"]
        page = pages.get(certificate["snapshot"])
        if page is None:
            out.append(Check("certificate", claim.ref, False, f"{claim.identifier}: span [{start}, {end}) of {certificate['snapshot']}, whose bytes are not available"))
            return
        if not (0 <= start < end <= len(page)):
            out.append(Check("certificate", claim.ref, False, f"{claim.identifier}: span [{start}, {end}) lies outside the {len(page):,} bytes of {certificate['snapshot']}"))
            return
        found = page[start:end].decode("utf-8", errors="replace")
        if found != certificate["matched"]:
            out.append(Check("certificate", claim.ref, False, f"{claim.identifier}: span [{start}, {end}) reads {found!r}, not {certificate['matched']!r}"))
            return
    read = (
        f"{len(claim.certificates)} span(s) read as their text: "
        + ", ".join(repr(c["matched"]) for c in claim.certificates)
    )
    where = ""
    if claim.kind == "cited":
        problem, where = _row_tie(bundle, pages, claim)
        if problem is not None:
            out.append(Check("certificate", claim.ref, False, f"{claim.identifier}: {read}, but {problem}"))
            return
    out.append(Check("certificate", claim.ref, True, f"{claim.identifier}: {read}" + (f", {where}" if where else "")))


def _check_dominance(claim: ClaimRecord, out: list[Check]) -> None:
    text = claim.settings.get("ordinals")
    if text is None:
        # Nothing to compare: the check did not run, and says so in its own
        # state rather than as a pass ("THREE STATES").
        reason = claim.settings.get("dominance", "not certified: no ordinals were carried")
        out.append(Check("dominance", claim.ref, True, f"{claim.identifier}: {reason}", ran=False))
        return
    try:
        ordinals = json.loads(text)
    except ValueError as exc:
        out.append(Check("dominance", claim.ref, False, f'{claim.identifier}: settings["ordinals"] is not JSON: {exc}'))
        return
    chosen = ordinals.get("chosen") if isinstance(ordinals, dict) else None
    alternatives = ordinals.get("alternatives") if isinstance(ordinals, dict) else None
    if not isinstance(chosen, dict) or not isinstance(alternatives, dict):
        out.append(Check("dominance", claim.ref, False, f'{claim.identifier}: settings["ordinals"] is not {{"chosen": {{...}}, "alternatives": {{...}}}}'))
        return
    beaten = [label for label, axes in alternatives.items() if isinstance(axes, dict) and dominated(chosen, axes)]
    if beaten:
        out.append(Check("dominance", claim.ref, False, f"{claim.identifier}: the chosen row is strictly dominated by {beaten[0]!r} on the stated ordinals"))
    else:
        out.append(Check("dominance", claim.ref, True, f"{claim.identifier}: not strictly dominated by any of {len(alternatives)} alternative(s)"))


def _check_unit_arithmetic(bundle: BundleFiles, claim: ClaimRecord, out: list[Check]) -> None:
    factor_text = claim.settings.get("unit_factor")
    if factor_text is None:
        return
    rows = [bundle.rows[r] for r in claim.row_inputs() if r in bundle.rows]
    if len(rows) != 1 or claim.value_text is None:
        out.append(Check("unit arithmetic", claim.ref, False, f"{claim.identifier}: a unit factor needs one row and a value to multiply"))
        return
    try:
        factor = Decimal(factor_text)
    except InvalidOperation:
        out.append(Check("unit arithmetic", claim.ref, False, f"{claim.identifier}: unit_factor {factor_text!r} is not a decimal number"))
        return
    expected = Decimal(rows[0].value_text) * factor
    actual = Decimal(claim.value_text)
    if within_tolerance(actual, expected, claim.tolerance):
        out.append(Check("unit arithmetic", claim.ref, True, f"{claim.identifier}: {rows[0].value_text} {rows[0].unit} × {factor_text} = {actual} {claim.unit}"))
    else:
        out.append(Check(
            "unit arithmetic", claim.ref, False,
            f"{claim.identifier}: {rows[0].value_text} {rows[0].unit} × {factor_text} is {expected}, "
            f"not the cited {actual} {claim.unit}" + (f" (tolerance {claim.tolerance})" if claim.tolerance else ""),
        ))


def _exists(bundle: BundleFiles, ref: str) -> bool:
    kind = ref_kind(ref)
    table = {"claim": bundle.claims, "row": bundle.rows, "snapshot": bundle.snapshots}.get(kind or "")
    return table is not None and ref in table


def _check_inputs(bundle: BundleFiles, claim: ClaimRecord, out: list[Check]) -> None:
    who = claim.identifier
    if claim.kind == "computed":
        if not claim.inputs:
            out.append(Check("inputs", claim.ref, False, f"{who}: a computed claim has at least one input"))
            return
        for ref in claim.inputs:
            if ref_kind(ref) == "ir":
                if claim.settings.get("ir") != ref_digest(ref):
                    out.append(Check("inputs", claim.ref, False, f"{who}: input {ref} is not the digest settings[\"ir\"] names ({claim.settings.get('ir')!r})"))
                    return
            elif not _exists(bundle, ref):
                out.append(Check("inputs", claim.ref, False, f"{who}: input {ref} is not in the bundle"))
                return
        out.append(Check("inputs", claim.ref, True, f"{who}: {len(claim.inputs)} input(s) present"))
    elif claim.kind in ("chosen", "placeholder"):
        rows = claim.row_inputs()
        if rows:
            out.append(Check("inputs", claim.ref, False, f"{who}: a {claim.kind} value cites a row ({rows[0]}); nobody measured it"))
        else:
            out.append(Check("inputs", claim.ref, True, f"{who}: cites no row, as a {claim.kind} value must not"))
    elif claim.kind == "refused":
        if claim.refusal is None:
            out.append(Check("inputs", claim.ref, False, f"{who}: a refused claim carries its refusal"))
            return
        candidates = [c.split(" | ", 1)[0] for c in claim.refusal["candidates"]]
        absent = [c for c in candidates if not _exists(bundle, c)]
        if absent:
            out.append(Check("inputs", claim.ref, False, f"{who}: refusal candidate {absent[0]} is not in the bundle"))
        else:
            out.append(Check("inputs", claim.ref, True, f"{who}: refused ({claim.refusal['kind']}); {len(candidates)} candidate row(s) present"))


def _check_root(bundle: BundleFiles, out: list[Check]) -> None:
    root = bundle.root
    claim = bundle.claims.get(root)
    if claim is None:
        out.append(Check("root", root, False, f"the manifest's root {root} is not among the claims"))
    elif claim.kind != "computed":
        out.append(Check("root", root, False, f"{claim.identifier}: the root is {claim.kind}, not computed"))
    else:
        out.append(Check("root", root, True, f"{claim.identifier}: the root is a computed claim with {len(claim.inputs)} input(s)"))


def verify_bundle(directory: str | Path) -> Report:
    """Every check the module docstring names, in order; BundleMalformed when
    the directory cannot be read as a bundle at all."""
    bundle = read_bundle_files(directory)
    pages = _Pages(bundle)
    checks: list[Check] = []
    _check_snapshots(bundle, pages, checks)
    _check_row_identity(bundle, checks)
    for claim in bundle.claims.values():
        _check_claim_identity(claim, checks)
        if claim.kind == "cited":
            _check_row_locator(bundle, pages, claim, checks)
        # A cited claim is held to certifying its row even when it carries no
        # span: `compose --claims` refuses (row not certified) rather than
        # cite a row whose bytes it cannot point at.
        if claim.certificates or claim.kind == "cited":
            _check_certificates(bundle, pages, claim, checks)
        if claim.kind == "cited":
            _check_dominance(claim, checks)
            _check_unit_arithmetic(bundle, claim, checks)
        else:
            _check_inputs(bundle, claim, checks)
    _check_root(bundle, checks)
    root = bundle.root if bundle.root in bundle.claims else None
    checks.extend(Check("not checked", root, True, f"{what}: {why}", ran=False) for what, why in NOT_CHECKED)
    return Report(ok=not any(c.status == STATUS_FAILED for c in checks), checks=checks)


__all__ = [
    "ANY_ORGANISM",
    "BLOBS",
    "CLAIMS",
    "FORMAT",
    "KINDS",
    "MANIFEST",
    "MAX_PAGE_BYTES",
    "NOT_CHECKED",
    "REF_KINDS",
    "ROWS",
    "ROW_OPENING",
    "SNAPSHOTS",
    "STATUSES",
    "STATUS_FAILED",
    "STATUS_NOT_RUN",
    "STATUS_OK",
    "BundleFiles",
    "BundleMalformed",
    "Check",
    "ClaimRecord",
    "PageTooLarge",
    "Report",
    "RowRecord",
    "SnapshotRecord",
    "canonical_bytes",
    "claim_id",
    "claim_identity",
    "digest",
    "dominated",
    "find_row_region",
    "gunzip_bounded",
    "is_digest",
    "occurs",
    "read_bundle_files",
    "ref_digest",
    "ref_kind",
    "refuse_floats",
    "region_of",
    "row_cells",
    "row_holds",
    "row_id",
    "row_identity",
    "row_regions",
    "same_number",
    "verify_bundle",
    "within_tolerance",
]
