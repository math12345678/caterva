"""`caterva why CLAIM_REF --bundle DIR`: a number's derivation, down to the pinned bytes.

    caterva why claim:sha256:<hex> --bundle ./claims
    caterva why claim:sha256:<hex> --store ./claims/store

WHY THIS EXISTS
---------------
A bundle (bundle.py) is for a program: one JSON record per line, bytes by
digest. The person who asked where a number came from wants the claim, the
rule that produced it with the ADR that set the rule, each certificate's
text, the row's own fields, the page's URL, date, hash and licence, and,
when the bundle holds BRENDA's literature page for the row's reference, the
paper's title and PubMed id read from that page (references.py), not typed
in. ADR 0179 shows the layout; this prints it. A computed claim is printed
with each input claim under it, one indent deeper, so the root claim's
`why` is the whole model's.

WHAT IS REFUSED
---------------
A ref that is not in the bundle or store named: exit 3 with `Refused:` and
the ref, because a derivation that is not there cannot be shown and must
not be made up; so is a record that, read back, does not produce its own id
(exit 3, `Refused:` and why), since printing it would show a derivation
that is not the one the id names. A directory that is not a bundle, or
holds no store (no index.sqlite, or one that is not an evidence store's:
not SQLite, or without its tables): exit 2, the question could not be read.
The store is opened read only, so asking changes nothing on disk.
`--bundle` and `--store` together, or neither: a malformed question, exit 2.

This module reads the producer's records through `caterva.evidence`; it is
not the checker. `caterva verify` (caterva/check/) is the program that
imports none of this and re-derives what it prints.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from caterva.evidence.bundle import Bundle, BundleUnreadable, read_bundle
    from caterva.evidence.claims import Claim, EvidenceRefused, Row, Snapshot, ref_kind
    from caterva.evidence.references import parse_reference_page, reference_url
    from caterva.evidence.rows import ANY_ORGANISM, locator_ec
    from caterva.evidence.store import EvidenceStore, StoreUnreadable
except ImportError:  # pragma: no cover - flat layout
    from evidence.bundle import Bundle, BundleUnreadable, read_bundle  # type: ignore[no-redef]
    from evidence.claims import Claim, EvidenceRefused, Row, Snapshot, ref_kind  # type: ignore[no-redef]
    from evidence.references import parse_reference_page, reference_url  # type: ignore[no-redef]
    from evidence.rows import ANY_ORGANISM, locator_ec  # type: ignore[no-redef]
    from evidence.store import EvidenceStore, StoreUnreadable  # type: ignore[no-redef]

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3

#: What each rule warrants, in the words of ADR 0179's table. A rule this
#: table does not know is printed with its id and ADR and no gloss.
RULE_MEANINGS = {
    "parse.brenda_table": "a row read from a BRENDA enzyme page by the literature layer's parser",
    "parse.brenda_reference": "authors, title, journal, year and PMID read from BRENDA's literature page",
    "select.resolver": "the row the resolver carried: weight-free dominance, then the minimum",
    "placeholder.motif_library": "an illustrative value from the motif library, labelled as such",
    "chosen.starting_amount": "a starting amount or exponent somebody chose",
    "compile.model": "the composed model: every parameter claim plus the digest of the annotation-free Antimony source",
}

_LABEL = 12


class _Source:
    """One face over a Bundle and an EvidenceStore: records by ref, bytes, reference pages."""

    def __init__(self, inner: Bundle | EvidenceStore, where: str) -> None:
        self.inner = inner
        self.where = where

    def get(self, ref: str) -> Any:
        return self.inner.get(ref)

    def snapshot_bytes(self, ref: str) -> bytes:
        return self.inner.snapshot_bytes(ref)

    def reference_snapshots(self) -> list[Snapshot]:
        if isinstance(self.inner, EvidenceStore):
            return self.inner.snapshots(source="brenda_reference")
        return [s for s in self.inner.snapshots.values() if s.source == "brenda_reference"]


def _row_line(label: str, text: str, indent: int) -> str:
    return " " * indent + f"{label:<{_LABEL}} {text}"


def _rule_text(rule: Any) -> str:
    gloss = RULE_MEANINGS.get(rule.rule_id)
    text = f"{rule.rule_id} v{rule.version} ({rule.adr})"
    return f"{text}: {gloss}" if gloss else text


def _settings_lines(settings: dict[str, str], indent: int) -> list[str]:
    lines = []
    for key in sorted(settings):
        value = settings[key]
        if key == "ordinals":
            lines.extend(_ordinals_lines(value, indent))
        else:
            lines.append(_row_line("settings", f"{key} = {value}", indent))
    return lines


def _axes(axes: dict) -> str:
    return "  ".join(f"{name}={'none' if v is None else v}" for name, v in sorted(axes.items()))


def _ordinals_lines(text: str, indent: int) -> list[str]:
    try:
        ordinals = json.loads(text)
        chosen, alternatives = ordinals["chosen"], ordinals["alternatives"]
    except (ValueError, KeyError, TypeError):
        return [_row_line("settings", f"ordinals = {text}", indent)]
    lines = [_row_line("ordinals", f"chosen row  {_axes(chosen)}  (higher is better)", indent)]
    lines.extend(
        _row_line("", f"alternative {label}: {_axes(axes)}", indent)
        for label, axes in sorted(alternatives.items())
    )
    if not alternatives:
        lines.append(_row_line("", "no alternative on the frontier", indent))
    return lines


def _row_lines(row: Row, indent: int) -> list[str]:
    lines = [
        _row_line("parser", _rule_text(row.parser), indent),
        _row_line("locator", row.locator, indent),
        _row_line("value", f"{row.value_text} {row.unit}   substrate {row.substrate}   organism "
                  + ("not read from the row" if row.organism == ANY_ORGANISM else row.organism), indent),
    ]
    if row.accession:
        lines.append(_row_line("accession", row.accession, indent))
    lines.append(_row_line("commentary", row.commentary if row.commentary else "none on the row", indent))
    lines.append(_row_line("reference", row.reference if row.reference else "none on the row", indent))
    return lines


def _snapshot_lines(snapshot: Snapshot, indent: int) -> list[str]:
    return [
        _row_line("snapshot", f"{snapshot.ref}  {snapshot.source}", indent),
        _row_line("locator", snapshot.locator, indent + 2),
        _row_line("retrieved", f"{snapshot.retrieved_at}   licence {snapshot.licence}   release "
                  + (snapshot.release if snapshot.release else "none stated"), indent + 2),
        _row_line("served from", snapshot.served_from if snapshot.served_from else "the live service", indent + 2),
    ]


def _reference_lines(source: _Source, row: Row, indent: int) -> list[str]:
    """The paper, from the brenda_reference snapshot whose locator is the row's reference page."""
    if not row.reference:
        return []
    ec = locator_ec(row.locator)
    if ec is None:
        return [_row_line("reference", f"{row.reference}  (the locator names no EC number, so no reference page can be matched)", indent)]
    wanted = reference_url(ec, row.reference)
    page = next((s for s in source.reference_snapshots() if s.locator == wanted), None)
    if page is None:
        return [_row_line("reference", f"{row.reference}  (the paper's page {wanted} is not in {source.where})", indent)]
    try:
        data = source.snapshot_bytes(page.ref)
    except EvidenceRefused as exc:
        # Bytes that are not the snapshot's (bundle and store both hold a blob
        # to its id) are not the paper, so none is printed; the reason is.
        return [_row_line("reference", f"{row.reference}  page {page.ref} pinned but unreadable: {exc}", indent)]
    try:
        found = parse_reference_page(data.decode("utf-8", errors="replace"))
    except EvidenceRefused as exc:
        return [_row_line("reference", f"{row.reference}  page {page.ref} pinned but holds no reference block: {exc}", indent)]
    head = f"{row.reference}  PMID {found.pmid}" if found.pmid else f"{row.reference}  no PubMed id on the page"
    citation = found.authors
    if found.year:
        citation += f" ({found.year})"
    if found.journal:
        citation += f" {found.journal}"
    return [
        _row_line("reference", head, indent),
        _row_line("", citation, indent + 2),
        _row_line("", found.title, indent + 2),
        _row_line("", f"read from {page.ref}, retrieved {page.retrieved_at}", indent + 2),
    ]


def _value_line(claim: Claim) -> str:
    if claim.kind == "computed":
        tolerance = f"tolerance {claim.tolerance}" if claim.tolerance else "tolerance (none stated)"
        return f"not part of the identity: a computed claim is held to a {tolerance}, not to a number"
    if claim.kind == "refused":
        return "none: refused"
    text = f"{claim.value_text} {claim.unit}" if claim.unit else str(claim.value_text)
    if claim.tolerance:
        text += f"   tolerance {claim.tolerance}"
    return text


def explain(source: _Source, ref: str, indent: int = 0) -> list[str]:
    """The lines for one claim and, recursively, its input claims."""
    claim = source.get(ref)
    lines = [" " * indent + f"{claim.ref}  {claim.kind}  {claim.subject}"]
    inner = indent + 2
    lines.append(_row_line("value", _value_line(claim), inner))
    lines.append(_row_line("rule", _rule_text(claim.derivation.rule), inner))
    lines.extend(_settings_lines(dict(claim.derivation.settings), inner))
    if claim.refusal is not None:
        lines.append(_row_line("refusal", f"{claim.refusal.kind}: requested {claim.refusal.requested}", inner))
        lines.extend(_row_line("candidate", c, inner + 2) for c in claim.refusal.candidates)
        if not claim.refusal.candidates:
            lines.append(_row_line("candidate", "none", inner + 2))
    snapshots: list[str] = []
    rows: list[Row] = []
    for input_ref in claim.derivation.inputs:
        kind = ref_kind(input_ref)
        if kind == "row":
            row = source.get(input_ref)
            rows.append(row)
            lines.append(_row_line("input", input_ref, inner))
            lines.extend(_row_lines(row, inner + 2))
            if row.snapshot not in snapshots:
                snapshots.append(row.snapshot)
        elif kind == "ir":
            lines.append(_row_line("input", f"{input_ref}  the compiled source, named by digest; not stored, so not shown", inner))
        elif kind == "snapshot":
            lines.append(_row_line("input", input_ref, inner))
            if input_ref not in snapshots:
                snapshots.append(input_ref)
    certificates = claim.derivation.certificates
    if certificates:
        lines.append(_row_line("certificates", f"{len(certificates)}, each a byte span of the snapshot that reads as its text", inner))
        lines.extend(_row_line("", f"[{c.span[0]}, {c.span[1]})  {c.matched!r}", inner + 2) for c in certificates)
        for certificate in certificates:
            if certificate.snapshot not in snapshots:
                snapshots.append(certificate.snapshot)
    for snapshot_ref in snapshots:
        lines.extend(_snapshot_lines(source.get(snapshot_ref), inner))
    for row in rows:
        lines.extend(_reference_lines(source, row, inner))
    for input_ref in claim.derivation.inputs:
        if ref_kind(input_ref) == "claim":
            lines.append(_row_line("input", "", inner).rstrip())
            lines.extend(explain(source, input_ref, inner + 2))
    return lines


def build_parser(prog: str = "caterva why") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Print why a number is what it is: the claim, the rule that produced it with "
            "the decision record behind the rule, each certified byte span and its text, "
            "the row's own fields, the page's URL, date, hash and licence, and the paper "
            "when its BRENDA literature page is in the bundle. A computed claim is printed "
            "with every input claim under it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} claim:sha256:<hex> --bundle ./claims\n"
            f"  {prog} claim:sha256:<hex> --store ./claims/store\n"
            "\n"
            "Take the ref from the report's `## Claims` section or from an export's claim_id.\n"
            "Exit codes: 0 printed, 2 malformed question or a directory that is not a bundle "
            "(or not a store), 3 refused: the ref is not in the bundle, or a record read does not "
            "produce its own id (Refused: and why), 1 a crash."
        ),
    )
    parser.add_argument("ref", help="a claim ref, claim:sha256:<64 hex>")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--bundle", metavar="DIR", help="a bundle directory written by `caterva compose --claims DIR`")
    where.add_argument("--store", metavar="DIR", help="an evidence store directory (index.sqlite and blobs/)")
    return parser


def _open(args: argparse.Namespace) -> _Source:
    if args.bundle:
        return _Source(read_bundle(args.bundle), f"the bundle {args.bundle}")
    return _Source(EvidenceStore(Path(args.store), read_only=True), f"the store {args.store}")


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    parser = build_parser(prog) if prog else build_parser()
    args = parser.parse_args(argv)
    try:
        if ref_kind(args.ref) != "claim":
            parser.error(f"{args.ref!r} is not a claim ref (claim:sha256:<64 hex>)")
    except EvidenceRefused as exc:
        parser.error(str(exc))
    try:
        source = _open(args)
    except (BundleUnreadable, StoreUnreadable) as exc:
        print(f"Not a claims bundle: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        try:
            lines = explain(source, args.ref)
        except KeyError as exc:
            print(f"Refused: {exc.args[0]} is not in {source.where}", file=sys.stderr)
            return EXIT_REFUSED
        except EvidenceRefused as exc:
            # A store record whose fields do not produce its id, or that is not
            # JSON: a bundle's records are checked when it is read, a store's
            # one by one as they are met, here. (A blob that is not its
            # snapshot's bytes is reported in the reference line instead.)
            print(f"Refused: {exc}", file=sys.stderr)
            return EXIT_REFUSED
    finally:
        if isinstance(source.inner, EvidenceStore):
            source.inner.close()
    print("\n".join(lines))
    return EXIT_OK


def console_main() -> int:
    return main()


__all__ = ["EXIT_CRASH", "EXIT_OK", "EXIT_REFUSED", "EXIT_USAGE", "RULE_MEANINGS", "build_parser", "explain", "main"]

if __name__ == "__main__":
    sys.exit(main())
