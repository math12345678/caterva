"""Claims over pinned evidence: the records every number in a model can be traced to.

WHY THIS EXISTS
---------------
`caterva compose` tells the reader where each constant came from, in prose:
"LITERATURE-DERIVED: BRENDA ref 641068; measured in Homo sapiens". That is
a label. It cannot be re-checked, because nothing records which bytes the
resolver read, which row on that page it took, or what the rule was that
made it take that row and not the one above it. ADR 0179 replaces the label
with a derivation: a Claim names its rule (with the ADR that set the rule),
its inputs (rows, other claims), the certificates (byte spans in a pinned
page that really hold the reference id, the value and the commentary) and
its settings; and its identity is the digest of exactly that, so a claim
cannot be altered and keep its id. An independent checker (`caterva/check/`)
then re-derives every id and re-finds every certificate from the pinned
bytes without importing a line of this package.

WHAT A WARRANT IS, AND WHAT IT IS NOT
-------------------------------------
A Claim is a statement that a derivation was applied, with everything needed
to apply it again. It says nothing about the biology: `caterva verify` finds
whether a stated reason still holds against the pinned bytes, not whether the
paper was right. The words in this package are "re-checkable" and "pinned",
never "verified" or "correct".

IDENTITY FOLLOWS THE DERIVATION
-------------------------------
  * a cited, chosen or placeholder claim's id covers its value text: the
    number IS what was read or chosen, so a different number is a different
    claim;
  * a computed claim's id excludes its value: the same model compiled from
    the same inputs is the same claim whether the solver printed 0.3000000001
    or 0.3; the value is held to the claim's tolerance instead;
  * a refusal is a claim too, with its candidates and the reason each was
    not taken, so "no row matched" is as re-checkable as a citation.

Every number inside an identity is a decimal string (canonical.py), and the
dataclass cannot hold a lying id: `__post_init__` recomputes it. Construct
through `make_claim`, `make_row`, `make_snapshot`.

WHAT IS NOT HERE
----------------
Readings (several interpretations of one row), labels, defeats-as-data and
the persistent engine are later milestones of the plan (M3, M4) and are not
built. This slice records the resolver's pick as rule `select.resolver` v1
and does not enumerate the other readings.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    from caterva.evidence.canonical import Digest, canonical_bytes, digest, is_digest
except ImportError:  # pragma: no cover - flat layout
    from evidence.canonical import Digest, canonical_bytes, digest, is_digest  # type: ignore[no-redef]


class EvidenceRefused(ValueError):  # noqa: N818 - a refusal, named as the repository names them (ExportRefused, ADR 0024)
    """A record that would lie about its own derivation is not constructed."""


# ---------------------------------------------------------------------------
# References: "<kind>:sha256:<hex>"
# ---------------------------------------------------------------------------

#: Kinds of stored object a reference can name. "ir" is not stored: it names
#: the compiled source of a computed model by digest (settings["ir"] holds the
#: same digest), so a checker can hold the model to its source without the
#: bundle carrying the source.
REF_KINDS = ("snapshot", "row", "claim", "ir")


def make_ref(kind: str, value: Digest) -> str:
    if kind not in REF_KINDS:
        raise EvidenceRefused(f"{kind!r} is not a reference kind; one of {REF_KINDS}")
    if not is_digest(value):
        raise EvidenceRefused(f"{value!r} is not a digest of the form sha256:<64 hex>")
    return f"{kind}:{value}"


def ref_kind(ref: str) -> str:
    """The kind of a reference, refusing a string that is not one."""
    kind, _, rest = str(ref).partition(":")
    if kind not in REF_KINDS or not is_digest(rest):
        raise EvidenceRefused(f"{ref!r} is not a reference of the form <kind>:sha256:<hex>")
    return kind


def ref_digest(ref: str) -> Digest:
    """The digest a reference names."""
    ref_kind(ref)
    return str(ref).partition(":")[2]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleRef:
    """Which rule derived a record, which version of it, and the ADR that set it."""

    rule_id: str
    version: int
    adr: str

    def __post_init__(self) -> None:
        if not self.rule_id or not isinstance(self.rule_id, str):
            raise EvidenceRefused("a rule needs an id")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise EvidenceRefused(f"rule {self.rule_id!r} version must be a positive integer")
        if not self.adr or not isinstance(self.adr, str):
            raise EvidenceRefused(f"rule {self.rule_id!r} must name the ADR that set it")


#: The rules this slice uses. A new rule, or a change in what one does, is a
#: new entry with a bumped version and the ADR that made the change: an old
#: bundle keeps meaning what it meant.
PARSE_BRENDA_TABLE = RuleRef("parse.brenda_table", 1, "ADR 0179")
PARSE_BRENDA_REFERENCE = RuleRef("parse.brenda_reference", 1, "ADR 0179")
SELECT_RESOLVER = RuleRef("select.resolver", 1, "ADR 0047")
PLACEHOLDER_MOTIF_LIBRARY = RuleRef("placeholder.motif_library", 1, "ADR 0013")
CHOSEN_STARTING_AMOUNT = RuleRef("chosen.starting_amount", 1, "ADR 0044")
COMPILE_MODEL = RuleRef("compile.model", 1, "ADR 0179")

RULES = {
    rule.rule_id: rule
    for rule in (
        PARSE_BRENDA_TABLE, PARSE_BRENDA_REFERENCE, SELECT_RESOLVER,
        PLACEHOLDER_MOTIF_LIBRARY, CHOSEN_STARTING_AMOUNT, COMPILE_MODEL,
    )
}


# ---------------------------------------------------------------------------
# Snapshot: the bytes the resolver read, dated
# ---------------------------------------------------------------------------

#: What this slice pins.
SNAPSHOT_SOURCES = ("brenda_enzyme", "brenda_reference", "paper_table")


@dataclass(frozen=True)
class Snapshot:
    """A dated record of what was read: never a cache served as current.

    `id` is the digest of the raw bytes and nothing else, so the same page
    fetched twice is one snapshot; `retrieved_at` sits beside the id. The
    product always fetches live (Tests/fixtures/recorded/README.md); when a
    test replayed a recording, `served_from` says which file, so a bundle
    built offline cannot pass as one built from the database that day.
    """

    id: Digest
    source: str
    locator: str
    retrieved_at: str
    licence: str
    release: str | None = None
    served_from: str | None = None

    def __post_init__(self) -> None:
        if not is_digest(self.id):
            raise EvidenceRefused(f"snapshot id {self.id!r} is not a digest")
        if self.source not in SNAPSHOT_SOURCES:
            raise EvidenceRefused(
                f"snapshot source {self.source!r} is not one of {SNAPSHOT_SOURCES}"
            )
        for name in ("locator", "retrieved_at", "licence"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise EvidenceRefused(f"snapshot {name} must be a non-empty string")

    @property
    def ref(self) -> str:
        return make_ref("snapshot", self.id)


def make_snapshot(
    data: bytes,
    *,
    source: str,
    locator: str,
    retrieved_at: str,
    licence: str,
    release: str | None = None,
    served_from: str | None = None,
) -> Snapshot:
    """A Snapshot whose id is the digest of `data`."""
    if not isinstance(data, (bytes, bytearray)):
        raise EvidenceRefused("a snapshot is made from bytes, not text: the digest is of the wire")
    return Snapshot(
        id=digest(bytes(data)), source=source, locator=locator, retrieved_at=retrieved_at,
        licence=licence, release=release, served_from=served_from,
    )


# ---------------------------------------------------------------------------
# Row: one line of a table, as the parser read it
# ---------------------------------------------------------------------------

QUANTITIES = ("km", "kcat", "ki")


def _decimal_text(text: Any, what: str) -> None:
    """Refuse a value text that Decimal cannot read exactly, or that is not finite."""
    if not isinstance(text, str) or not text.strip():
        raise EvidenceRefused(f"{what} must be a decimal string, not {text!r}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise EvidenceRefused(f"{what} {text!r} is not a decimal number") from exc
    if not value.is_finite():
        raise EvidenceRefused(f"{what} {text!r} is not finite")


@dataclass(frozen=True)
class Row:
    """A table row read from a snapshot by a parser rule.

    `value_text` is the decimal string of the value the parser yielded,
    `format(v, ".15g")`: the literature layer's parser returns a float, and
    this slice records what the parser yielded and says so, rather than
    re-reading the cell. The locator is for people and for re-finding:
    `brenda:<ec>:<table>:<organism>:<substrate>:<reference>:<value_text>:<n>`
    where n is the index among rows sharing all the preceding fields, in
    parse order. The fields themselves are the structured form.
    """

    id: Digest
    snapshot: str
    parser: RuleRef
    locator: str
    quantity: str
    value_text: str
    unit: str
    substrate: str
    organism: str
    accession: str | None = None
    commentary: str | None = None
    reference: str | None = None

    def __post_init__(self) -> None:
        if ref_kind(self.snapshot) != "snapshot":
            raise EvidenceRefused(f"a row's snapshot must be a snapshot ref, not {self.snapshot!r}")
        if not isinstance(self.parser, RuleRef):
            raise EvidenceRefused("a row's parser must be a RuleRef")
        if self.quantity not in QUANTITIES:
            raise EvidenceRefused(f"quantity {self.quantity!r} is not one of {QUANTITIES}")
        _decimal_text(self.value_text, "a row's value_text")
        for name in ("locator", "unit", "substrate", "organism"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise EvidenceRefused(f"a row's {name} must be a non-empty string")
        for name in ("accession", "commentary", "reference"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise EvidenceRefused(f"a row's {name} must be a string or None")
        expected = row_id(self)
        if self.id != expected:
            raise EvidenceRefused(
                f"row id {self.id} is not the digest of its fields ({expected}); a row "
                "cannot hold an id its contents do not produce"
            )

    @property
    def ref(self) -> str:
        return make_ref("row", self.id)


def row_identity(row: Row) -> dict:
    """The dict whose canonical bytes a row's id digests. Named so the
    independent checker can repeat it: {"parser", "locator", "fields"} with
    fields = snapshot, quantity, value_text, unit, substrate, organism,
    accession, commentary, reference."""
    return {
        "parser": to_dict(row.parser),
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


def row_id(row: Row) -> Digest:
    return digest(canonical_bytes(row_identity(row)))


def make_row(
    *,
    snapshot: str,
    parser: RuleRef,
    locator: str,
    quantity: str,
    value_text: str,
    unit: str,
    substrate: str,
    organism: str,
    accession: str | None = None,
    commentary: str | None = None,
    reference: str | None = None,
) -> Row:
    """A Row whose id is computed from its fields."""
    draft = _Draft(
        snapshot=snapshot, parser=parser, locator=locator, quantity=quantity,
        value_text=value_text, unit=unit, substrate=substrate, organism=organism,
        accession=accession, commentary=commentary, reference=reference,
    )
    return Row(id=row_id(draft), **draft.__dict__)  # type: ignore[arg-type]


class _Draft:
    """A bag of fields with the same attribute names as the record it drafts,
    so `row_id` and `claim_id` can run before the frozen record exists."""

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


# ---------------------------------------------------------------------------
# Certificates, derivations, refusals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Certificate:
    """A byte span in a snapshot that decodes to `matched`.

    Issued only from bytes that were found (rows.py); a text the page does
    not hold gets no certificate, never an invented span.
    """

    snapshot: str
    span: tuple[int, int]
    matched: str

    def __post_init__(self) -> None:
        if ref_kind(self.snapshot) != "snapshot":
            raise EvidenceRefused(f"a certificate's snapshot must be a snapshot ref, not {self.snapshot!r}")
        span = tuple(self.span)
        object.__setattr__(self, "span", span)
        if (
            len(span) != 2
            or any(isinstance(s, bool) or not isinstance(s, int) for s in span)
            or span[0] < 0
            or span[1] <= span[0]
        ):
            raise EvidenceRefused(f"a certificate's span must be [start, end) with end > start >= 0, not {span!r}")
        if not isinstance(self.matched, str) or not self.matched:
            raise EvidenceRefused("a certificate must say what text its span holds")
        if len(self.matched.encode("utf-8")) != span[1] - span[0]:
            raise EvidenceRefused(
                f"certificate span {span!r} covers {span[1] - span[0]} bytes but "
                f"{self.matched!r} is {len(self.matched.encode('utf-8'))} bytes of UTF-8"
            )


def _strings_only(settings: Mapping[str, Any], what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in dict(settings).items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise EvidenceRefused(
                f"{what} settings are strings only (a number is a decimal string, a "
                f"structure is JSON text); {key!r} -> {value!r} is not"
            )
        out[key] = value
    return out


@dataclass(frozen=True)
class Derivation:
    """The rule applied, to which inputs, with which certificates and settings."""

    rule: RuleRef
    inputs: tuple[str, ...] = ()
    certificates: tuple[Certificate, ...] = ()
    settings: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.rule, RuleRef):
            raise EvidenceRefused("a derivation's rule must be a RuleRef")
        inputs = tuple(self.inputs)
        for ref in inputs:
            ref_kind(ref)
        object.__setattr__(self, "inputs", inputs)
        certificates = tuple(self.certificates)
        for certificate in certificates:
            if not isinstance(certificate, Certificate):
                raise EvidenceRefused("a derivation's certificates must be Certificates")
        object.__setattr__(self, "certificates", certificates)
        object.__setattr__(self, "settings", _strings_only(self.settings, "a derivation's"))

    def row_inputs(self) -> tuple[str, ...]:
        return tuple(ref for ref in self.inputs if ref_kind(ref) == "row")


@dataclass(frozen=True)
class Refusal:
    """What was asked for, why it was not supplied, and the candidates not taken.

    `candidates` are `"<row ref> | <reason>"` strings, so a reader sees both
    the row and why it was not the one.
    """

    requested: str
    kind: str
    candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.requested or not isinstance(self.requested, str):
            raise EvidenceRefused("a refusal must say what was requested")
        if not self.kind or not isinstance(self.kind, str):
            raise EvidenceRefused("a refusal must name its kind")
        candidates = tuple(self.candidates)
        for candidate in candidates:
            if not isinstance(candidate, str):
                raise EvidenceRefused("a refusal's candidates are 'ref | reason' strings")
        object.__setattr__(self, "candidates", candidates)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

KINDS = ("cited", "chosen", "placeholder", "refused", "computed")


@dataclass(frozen=True)
class Claim:
    """A derivation, with the number it produced (when it produced one)."""

    id: Digest
    kind: str
    subject: str
    value_text: str | None
    unit: str | None
    tolerance: str | None
    derivation: Derivation
    refusal: Refusal | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise EvidenceRefused(f"claim kind {self.kind!r} is not one of {KINDS}")
        if not self.subject or not isinstance(self.subject, str):
            raise EvidenceRefused("a claim needs a subject")
        if not isinstance(self.derivation, Derivation):
            raise EvidenceRefused("a claim's derivation must be a Derivation")
        if self.value_text is not None:
            _decimal_text(self.value_text, "a claim's value_text")
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit):
            raise EvidenceRefused("a claim's unit must be a non-empty string or None")
        if self.tolerance is not None:
            _decimal_text(self.tolerance, "a claim's tolerance")
        rows = self.derivation.row_inputs()
        if self.kind == "cited":
            if len(self.derivation.inputs) != 1 or len(rows) != 1:
                raise EvidenceRefused(
                    f"a cited claim ({self.subject}) has exactly one input, a row; "
                    f"this one has {list(self.derivation.inputs)}"
                )
            if not self.derivation.certificates:
                raise EvidenceRefused(
                    f"a cited claim ({self.subject}) needs at least one certificate: a "
                    "citation with no span in the pinned bytes is a label, not a derivation"
                )
            if self.value_text is None:
                raise EvidenceRefused(f"a cited claim ({self.subject}) carries the value it cites")
        elif self.kind == "placeholder":
            if rows:
                raise EvidenceRefused(f"a placeholder ({self.subject}) cites no row; it is not measured")
            if "table" not in self.derivation.settings:
                raise EvidenceRefused(
                    f"a placeholder ({self.subject}) names the table that would supply "
                    'it in settings["table"], or "none"'
                )
            if self.value_text is None:
                raise EvidenceRefused(f"a placeholder ({self.subject}) carries its value")
        elif self.kind == "chosen":
            if rows:
                raise EvidenceRefused(f"a chosen value ({self.subject}) cites no row; nobody measured it")
            if self.value_text is None:
                raise EvidenceRefused(f"a chosen value ({self.subject}) carries its value")
        elif self.kind == "refused":
            if self.refusal is None:
                raise EvidenceRefused(f"a refused claim ({self.subject}) carries its Refusal")
            if self.value_text is not None:
                raise EvidenceRefused(f"a refused claim ({self.subject}) has no value")
        elif self.kind == "computed" and not self.derivation.inputs:
            raise EvidenceRefused(f"a computed claim ({self.subject}) has at least one input")
        if self.kind != "refused" and self.refusal is not None:
            raise EvidenceRefused(f"only a refused claim carries a Refusal ({self.subject})")
        expected = claim_id(self)
        if self.id != expected:
            raise EvidenceRefused(
                f"claim id {self.id} is not the digest of its derivation ({expected}); a "
                "claim cannot hold an id its contents do not produce"
            )

    @property
    def ref(self) -> str:
        return make_ref("claim", self.id)


def claim_identity(claim: Any) -> dict:
    """The dict whose canonical bytes a claim's id digests. Named so the
    independent checker can repeat it:

        {"kind", "subject", "unit", "tolerance", "derivation"}
        + "value_text"  for every kind but computed
        + "refusal"     when the claim is a refusal

    A computed claim's value is excluded on purpose (module docstring).
    """
    identity: dict[str, Any] = {
        "kind": claim.kind,
        "subject": claim.subject,
        "unit": claim.unit,
        "tolerance": claim.tolerance,
        "derivation": to_dict(claim.derivation),
    }
    if claim.kind != "computed":
        identity["value_text"] = claim.value_text
    if claim.refusal is not None:
        identity["refusal"] = to_dict(claim.refusal)
    return identity


def claim_id(claim: Any) -> Digest:
    return digest(canonical_bytes(claim_identity(claim)))


def make_claim(
    kind: str,
    subject: str,
    value_text: str | None,
    unit: str | None,
    tolerance: str | None,
    derivation: Derivation,
    refusal: Refusal | None = None,
) -> Claim:
    """A Claim whose id is computed from its derivation (and value, by kind)."""
    draft = _Draft(
        kind=kind, subject=subject, value_text=value_text, unit=unit,
        tolerance=tolerance, derivation=derivation, refusal=refusal,
    )
    return Claim(id=claim_id(draft), **draft.__dict__)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Serialisation: plain JSON, every field
# ---------------------------------------------------------------------------

def to_dict(obj: Any) -> Any:
    """A plain-JSON dict of a record: tuples as lists, mappings as dicts."""
    if isinstance(obj, (Snapshot, Row, Certificate, Derivation, Refusal, Claim, RuleRef)):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Mapping):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def _rule_from_dict(data: Mapping[str, Any]) -> RuleRef:
    return RuleRef(rule_id=data["rule_id"], version=data["version"], adr=data["adr"])


def _certificate_from_dict(data: Mapping[str, Any]) -> Certificate:
    return Certificate(snapshot=data["snapshot"], span=tuple(data["span"]), matched=data["matched"])


def _derivation_from_dict(data: Mapping[str, Any]) -> Derivation:
    return Derivation(
        rule=_rule_from_dict(data["rule"]),
        inputs=tuple(data.get("inputs", ())),
        certificates=tuple(_certificate_from_dict(c) for c in data.get("certificates", ())),
        settings=dict(data.get("settings", {})),
    )


def _refusal_from_dict(data: Mapping[str, Any] | None) -> Refusal | None:
    if data is None:
        return None
    return Refusal(requested=data["requested"], kind=data["kind"], candidates=tuple(data.get("candidates", ())))


def claim_from_dict(data: Mapping[str, Any]) -> Claim:
    """A Claim from its JSON; the stored id must equal the recomputed one."""
    try:
        return Claim(
            id=data["id"], kind=data["kind"], subject=data["subject"],
            value_text=data.get("value_text"), unit=data.get("unit"),
            tolerance=data.get("tolerance"),
            derivation=_derivation_from_dict(data["derivation"]),
            refusal=_refusal_from_dict(data.get("refusal")),
        )
    except (KeyError, TypeError) as exc:
        raise EvidenceRefused(f"not a claim record: {exc!r}") from exc


def row_from_dict(data: Mapping[str, Any]) -> Row:
    try:
        return Row(
            id=data["id"], snapshot=data["snapshot"], parser=_rule_from_dict(data["parser"]),
            locator=data["locator"], quantity=data["quantity"], value_text=data["value_text"],
            unit=data["unit"], substrate=data["substrate"], organism=data["organism"],
            accession=data.get("accession"), commentary=data.get("commentary"),
            reference=data.get("reference"),
        )
    except (KeyError, TypeError) as exc:
        raise EvidenceRefused(f"not a row record: {exc!r}") from exc


def snapshot_from_dict(data: Mapping[str, Any]) -> Snapshot:
    try:
        return Snapshot(
            id=data["id"], source=data["source"], locator=data["locator"],
            retrieved_at=data["retrieved_at"], licence=data["licence"],
            release=data.get("release"), served_from=data.get("served_from"),
        )
    except (KeyError, TypeError) as exc:
        raise EvidenceRefused(f"not a snapshot record: {exc!r}") from exc


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def now_utc() -> str:
    """The moment, as an ISO-8601 UTC string with second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ordinals_json(
    chosen: Mapping[str, str | None], alternatives: Mapping[str, Mapping[str, str | None]],
) -> str:
    """The text of settings["ordinals"]: where the chosen row and each
    alternative sit on each evidence axis, higher is better.

    Values are decimal strings of the ordinal (or null where an axis could
    not be assessed for that row, which a checker skips rather than scores,
    as Tests/evidence_rank.py `dominates` does). The checker holds the chosen
    row to being not strictly dominated: no alternative at least as good on
    every comparable axis and better on one. Keys are sorted so the text,
    which enters the claim's identity, has one spelling.
    """
    for name, value in chosen.items():
        if value is not None and not isinstance(value, str):
            raise EvidenceRefused(f"ordinal {name!r} must be a decimal string or None")
    for label, axes in alternatives.items():
        for name, value in axes.items():
            if value is not None and not isinstance(value, str):
                raise EvidenceRefused(f"ordinal {name!r} of {label!r} must be a decimal string or None")
    return json.dumps(
        {"chosen": dict(chosen), "alternatives": {k: dict(v) for k, v in alternatives.items()}},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


__all__ = [
    "CHOSEN_STARTING_AMOUNT",
    "COMPILE_MODEL",
    "KINDS",
    "PARSE_BRENDA_REFERENCE",
    "PARSE_BRENDA_TABLE",
    "PLACEHOLDER_MOTIF_LIBRARY",
    "QUANTITIES",
    "REF_KINDS",
    "RULES",
    "SELECT_RESOLVER",
    "SNAPSHOT_SOURCES",
    "Certificate",
    "Claim",
    "Derivation",
    "Digest",
    "EvidenceRefused",
    "Refusal",
    "Row",
    "RuleRef",
    "Snapshot",
    "claim_from_dict",
    "claim_id",
    "claim_identity",
    "make_claim",
    "make_ref",
    "make_row",
    "make_snapshot",
    "now_utc",
    "ordinals_json",
    "ref_digest",
    "ref_kind",
    "row_from_dict",
    "row_id",
    "row_identity",
    "snapshot_from_dict",
    "to_dict",
]
