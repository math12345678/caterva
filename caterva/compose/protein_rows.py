"""A value carried for a named protein must be a row of that protein.

WHY THIS EXISTS
---------------
Reviewing the names a professor types (ADR 0182, round 2), five readings
that looked right carried another protein's measurement:

* "SIRT1 kinetics in human", GROUNDED: Km 0.019 mM and kcat 0.275 1/s,
  BRENDA ref 739668, whose row is UniProt Q8IXJ6 -- sirtuin-2.
* "HER2 kinase in human": Km 0.0051 mM, ref 722195, UniProt P08069 -- the
  IGF-1 receptor.
* "NDM-1 hydrolysis of meropenem": Km 0.008 mM, kcat 7 1/s, ref 718584,
  UniProt Q8KRJ3 -- VIM-4, another metallo-beta-lactamase.
* "KPC-2 with imipenem": ref 696320, rows of the L1 metallo-beta-lactamase
  substituted with iron and cobalt ("lactamase ZnFe-L1", "CoCo-L1").
* "ERK2 kinetics in human": ref 663620, whose commentary says "activated
  p38 MAPKalpha".

Each was reported as "the row names no isoform, so whether it measured X is
unknown". The engine reads a row's isoform from its commentary
(`bind.core.read_isoform`), which knows "hexokinase II" and "LDH-A" but not
"p38 MAPKalpha", "ZnFe-L1" or a UniProt accession, so a row of another
protein looked like a row of none.

WHAT THIS DOES
--------------
After the search, each carried Km, kcat and Ki is traced back to its BRENDA
row by reference and value (`defaults.rows_of_value`), and withheld -- a
labelled placeholder whose reason names the protein the row measured --

1. when the row's own UniProt accession is another protein of the EC number
   in that organism, as the enzyme index lists it (SIRT2's for SIRT1, IGF1R's
   for HER2), whatever the isoform was asked by; and
2. for a curated name whose rows must name it (`rows_must_name_it` in
   enzymes/data/aliases.json: a protein filed under an EC number of many
   distinct proteins -- KPC-2 under the beta-lactamases, ERK2 under the MAP
   kinases, EcoRI under the restriction enzymes), when the row neither has
   one of the row's curated accessions nor names it in its commentary.

A row whose accession IS the protein asked for is kept. A value whose row
cannot be found is not judged: an unverifiable check is not a failed one,
and the page the search read is the one read here.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple


@lru_cache(maxsize=1)
def _alias_rows() -> Tuple[Dict[str, Any], ...]:
    from caterva.enzymes.symbols import ALIASES_PATH

    try:
        with open(ALIASES_PATH, encoding="utf-8") as handle:
            return tuple(json.load(handle).get("aliases", []))
    except (OSError, ValueError):
        return ()


def strict_alias(ec: Optional[str], isoform: Optional[str]) -> Optional[Dict[str, Any]]:
    """The curated alias row for `isoform` under `ec` whose rows must name it, or None."""
    if not ec or not isoform:
        return None
    want = isoform.strip().casefold()
    for row in _alias_rows():
        if not row.get("rows_must_name_it") or row.get("ec") != ec:
            continue
        labels = [row.get("isoform") or "", *row.get("names", [])]
        if any(want == str(label).casefold() for label in labels if label):
            return row
    return None


def _names_it(text: Optional[str], names: Sequence[str]) -> bool:
    """Whether a row's commentary names one of `names` as a word of its own:
    "activated p38 MAPKalpha" names p38; "MAPK14" does not name MAPK1."""
    if not text:
        return False
    for name in names:
        if len(name) < 3:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name).replace(r"\-", r"[-\s]?").replace(r"\ ", r"[-\s]?") \
            + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _states_isoform(text: Optional[str], isoform: str) -> bool:
    """Whether a row's commentary names `isoform` as the engine reads it ("MAO-A")."""
    if not text:
        return False
    try:
        from caterva.bind.core import read_isoform, same_isoform
    except ImportError:  # pragma: no cover - flat layout
        return False
    return same_isoform(read_isoform(text), isoform)


def _accessions(row: Any) -> Tuple[str, ...]:
    """A row's UniProt accessions: BRENDA joins several with commas."""
    return tuple(a.strip() for a in re.split(r"[,;\s]+", str(getattr(row, "uniprot", "") or "")) if a.strip())


def _where_rows_are(ec: str, table: str, accessions: Set[str]) -> str:
    """", where BRENDA's rows for these accessions are" -- a clause naming the
    organisms of this table's rows that carry one of `accessions`, or ""."""
    from collections import Counter

    from caterva.compose import defaults

    if not accessions:
        return ""
    try:
        rows = defaults.table_rows(ec, table, None)
    except Exception:  # noqa: BLE001
        return ""
    where = Counter(r.organism or "an organism BRENDA names otherwise" for r in rows
                    if set(_accessions(r)) & accessions)
    if not where:
        return (f"; BRENDA's {table} rows under EC {ec} carry no row with UniProt "
                f"{', '.join(sorted(accessions))}")
    return ("; BRENDA's rows with UniProt " + ", ".join(sorted(accessions)) + " are in "
            + ", ".join(f"{o} ({n} {table} row{'s' if n != 1 else ''})" for o, n in where.most_common(3))
            + ", and the search did not rank one of them for this constant")


def _proteins(ec: str, organism: Optional[str], isoform: str) -> Tuple[Set[str], Dict[str, str]]:
    """(accessions of the protein `isoform` names, {accession: label} of the
    organism's other proteins of `ec`), from the enzyme index."""
    from caterva.enzymes.finder import isozymes
    from caterva.enzymes.isoforms import keys_of, names_for

    found = isozymes(ec, organism)
    wanted_keys = keys_of(isoform)
    wanted: Set[str] = set()
    others: Dict[str, str] = {}
    for protein in found.proteins:
        have: Set[str] = set()
        for name in names_for(protein.accession, protein.symbol):
            have |= keys_of(name)
        if wanted_keys & have:
            wanted.add(protein.accession)
        else:
            others[protein.accession] = protein.label
    if not wanted:
        # An isoform the index cannot place among the organism's proteins
        # names no "other" protein either: nothing is known to differ.
        return set(), {}
    return wanted, others


def other_protein_withheld(model: Any, measured: Mapping[str, Any], ec: Optional[str],
                           isoform: Optional[str], organism: Optional[str]) -> Dict[str, str]:
    """parameter id -> why its value is withheld, for each carried value whose
    BRENDA row measured another protein than `isoform` (module docstring)."""
    if not ec or not isoform or not measured:
        return {}
    from caterva.compose import defaults

    strict = strict_alias(ec, isoform)
    curated = {str(a) for a in (strict or {}).get("accessions", [])}
    names = [n for n in ([(strict or {}).get("isoform") or "", *(strict or {}).get("names", [])]
                         + list((strict or {}).get("row_names", []))) if n]
    try:
        wanted, others = _proteins(ec, organism, isoform)
    except Exception:  # noqa: BLE001 - an index that cannot be read judges nothing
        wanted, others = set(), {}
    wanted |= curated
    out: Dict[str, str] = {}
    for q in getattr(model, "resolvable", ()) or ():
        m = measured.get(q.parameter_id)
        if m is None or q.table not in ("km", "kcat", "ki"):
            continue
        ref = getattr(m, "reference_id", None)
        if ref is None:
            cited = re.search(r"BRENDA ref (\d+)", str(getattr(m, "citation", "") or ""))
            ref = cited.group(1) if cited else None
        try:
            rows = defaults.rows_of_value(ec, q.table, getattr(m, "organism", None) or organism,
                                          m.value, ref)
        except Exception:  # noqa: BLE001 - unverifiable is not wrong
            rows = ()
        if not rows:
            continue
        accessions = {a for r in rows for a in _accessions(r)}
        if accessions & wanted:
            continue
        # A row whose own commentary names the isoform asked for measured it,
        # whatever its accession cell says: BRENDA ref 702238 files its
        # "MAO-A" benzylhydrazine Ki under P27338, MAO-B's accession.
        if any(_states_isoform(r.conditions, isoform) or _names_it(r.conditions, names) for r in rows):
            continue
        head = f"withheld: the value the search returned ({m.value:g} {m.unit}, BRENDA ref {ref})"
        if accessions and all(a in others for a in accessions):
            what = ", ".join(f"UniProt {a} ({others[a]})" for a in sorted(accessions))
            out[q.parameter_id] = (
                f"{head} is BRENDA's row for {what}, another protein of EC {ec} than {isoform}, "
                f"and a constant of another protein is never carried under this one's name. "
                f"Pass --isoform with that protein to model it, or supply this constant yourself")
            continue
        if strict is None:
            continue
        if any(_names_it(r.conditions, names) for r in rows):
            continue
        said = "; ".join(sorted({f"'{r.conditions}'" for r in rows if r.conditions})) or "no commentary"
        acc = (f", UniProt {', '.join(sorted(accessions)[:3])}"
               + (f" and {len(accessions) - 3} more" if len(accessions) > 3 else "") if accessions else "")
        known = (f" ({isoform} is UniProt {', '.join(sorted(curated))})" if curated else "")
        out[q.parameter_id] = (
            f"{head} comes from a row ({said}{acc}) that does not say it measured {isoform}{known}. "
            f"EC {ec} holds many distinct proteins, so a row that does not name {isoform} is not taken "
            f"as its measurement{_where_rows_are(ec, q.table, curated)}. Supply this constant "
            f"yourself, or model the protein the row names with --subject {ec} and no {isoform}")
    return out


__all__ = ["other_protein_withheld", "strict_alias"]
