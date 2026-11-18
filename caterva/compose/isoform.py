"""Keep the constants that were measured on the isoform a model is about.

Human lactate dehydrogenase is three proteins. BRENDA 711801 gives gossypol's
Ki for each: 0.0014 mM for LDH-B, 0.0019 mM for LDH-A, 0.0042 mM for LDH-C,
from one paper, in three rows. The resolver ranks them as equally well
evidenced and returns the first, LDH-B's. A model of LDH-A, the isoform
cancer glycolysis runs through, then carries LDH-B's constant; the report says
so (row_scope), and until now there was nothing the user could do about it.

`caterva compose --isoform LDH-A` asks for the isoform. The resolver is told
it with every constant's request and ranks every row it holds by it before it
chooses (narrowed.py); its row is carried. This then says, for each measured
constant, what that did, against the row the evidence alone would take, by
these three cases:

1. a row that names the isoform asked for is used;
2. failing that, a row that names no isoform is used, and the report says
   whether it measured that isoform is unknown;
3. failing that, every row measured another isoform, and the constant is
   refused rather than filled with a different protein's value.

A row is read by `caterva.bind.core.read_isoform`, the reader `caterva bind
--isoform` uses, so the two commands agree about what a row measured, and
names are compared by `caterva.bind.core.same_isoform`, which the literature
layer's resolver uses too (Tests/fallback_logic.py, `_same_isoform`). Names
compare without case, spaces or hyphens: "LDH-A", "ldha" and "LDH A" are one,
as are "MAO B", "MAO-B" and "MAOB"; a row naming two isoforms ("isoenzyme I
and isoenzyme II") is the same as either. There was a second copy of that
comparison here and a third in the resolver; one function now, so the two
cannot disagree about whether a row measured the isoform asked for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional

try:
    from caterva.bind.core import same_isoform
except ImportError:  # pragma: no cover - flat layout
    from bind.core import same_isoform  # type: ignore[no-redef]


def _read_isoform(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    try:
        from caterva.bind.core import read_isoform
    except ImportError:  # pragma: no cover - flat layout
        from bind.core import read_isoform  # type: ignore[no-redef]
    return read_isoform(text)


@dataclass
class IsoformSelection:
    #: The measured constants to build the model from.
    measured: Dict[str, Any]
    #: Constants refused because every row measured another isoform: id -> why.
    refused: Dict[str, str] = field(default_factory=dict)
    #: What was changed or could not be told, one sentence per constant.
    notes: List[str] = field(default_factory=list)


def _from_row(m: Any, row: Mapping[str, Any], because: str) -> Any:
    """The same Measurement, taken from another of its own ranked rows."""
    conditions = row.get("conditions") or None
    unreported = tuple(
        what for what, word in (("pH", "ph"), ("temperature", "temperature"))
        if conditions and re.search(rf"\b{word}\b[^,]*not specified", conditions, re.IGNORECASE)
    )
    ref = row.get("reference_id")
    return replace(
        m,
        value=float(row["value"]),
        citation=f"BRENDA ref {ref}" if ref else m.citation,
        reference_id=str(ref) if ref else m.reference_id,
        organism=row.get("organism") or m.organism,
        commentary=conditions,
        assay_ph=row.get("ph"),
        assay_temperature_c=row.get("temperature_c"),
        assay_buffer=row.get("buffer"),
        assay_unreported=unreported,
        chosen_because=because,
        **({"row_isoform": row.get("isoform")}
           if "row_isoform" in getattr(m, "__dataclass_fields__", {}) else {}),
    )


#: The resolver's words for a Km carried as the pair of a kcat that names
#: no isoform (fallback_logic `_pair_across_isoform_tiers`): one paper's
#: measurement, kept over another paper's row naming the isoform.
PAIRED_ACROSS_TIERS = "is carried as its pair over the row naming"


def _isolated(values: List[float]) -> List[int]:
    try:
        from caterva.checkout import literature_module

        return list(literature_module("fallback_logic").isolated(values))
    except Exception:  # noqa: BLE001
        return []


def _outlying(matching: List[float], unnamed: List[float]) -> bool:
    try:
        from caterva.checkout import literature_module

        return bool(literature_module("fallback_logic").isoform_rows_outlying(matching, unnamed))
    except Exception:  # noqa: BLE001 - without the literature layer, no such check
        return False


#: What asked for the isoform, for the notes ("as --isoform asked", "as your
#: description asked"); compose's DESCRIPTION_ASKED is the second.
ASKED_BY_FLAG = "--isoform"
ASKED_BY_WORDS = "your description"


def _discredited_papers(measured: Mapping[str, Any]) -> set:
    """The papers one of whose rows, of any constant, lies more than 100-fold
    from every other row of that constant (`_isolated`): a probable error.
    DPP4 and Gly-Pro-4-nitroanilide, ref 665551: kcat 279000 1/s against
    20-87 1/s for every other row; its Km of 1.43 mM, ~10-fold above every
    other wild-type human row, was then carried as "the row for DPP4" (fifth
    round of the real-values review). A paper whose paired constant is a
    probable error does not supply the other one."""
    out = set()
    for m in measured.values():
        # In the constant's own unit: a row written in uM is not an outlier
        # of rows in mM.
        rows = [r for r in getattr(m, "alternatives", ()) or ()
                if isinstance(r, dict) and r.get("value") is not None
                and r.get("unit") in (None, getattr(m, "unit", None))]
        for i in _isolated([float(r["value"]) for r in rows]):
            if rows[i].get("reference_id"):
                out.add(str(rows[i]["reference_id"]))
    return out


def _same_paper_partner(rows: List[Mapping[str, Any]], partner: Mapping[str, Any]):
    """The row of `rows` measured with `partner` (one paper, the same stated
    conditions), or None."""
    try:
        from caterva.checkout import literature_module

        same = literature_module("row_form").same_measurement
    except Exception:  # noqa: BLE001 - without the literature layer, by paper alone
        def same(a, b, substrate=None):
            return a.get("conditions") == b.get("conditions")
    ref = str(partner.get("reference_id") or "")
    for r in rows:
        if ref and str(r.get("reference_id") or "") == ref and same(r, partner):
            return r
    return None


_PH = re.compile(r"\bpH\s*\d")
_TEMPERATURE = re.compile(r"\d\s*°\s*C\b|\d\s*(?:degrees?|deg)\s*C\b", re.IGNORECASE)


def _states_both(text: Optional[str]) -> bool:
    return bool(text and _PH.search(text) and _TEMPERATURE.search(text))


def _conditions_lost(pick: Any, row: Mapping[str, Any], isoform: str) -> str:
    """"; that row states no pH or temperature ...": said when the row for
    the isoform states neither while the resolver's pick states both.
    DPP4: ref 678195's "dimeric rDPP-IV" (Km 0.09 mM, kcat 87 1/s, its
    UniProt cell P27487) replaced the pick 0.165 mM (pH 7.6, 30°C) and 20.3
    1/s (pH 8.0); its kcat is 3.6 to 4.4 times every wild-type row stating
    conditions, and the report gave no reason to doubt it (sixth round,
    XS5R2-06)."""
    theirs = str(row.get("conditions") or "")
    mine = str(getattr(pick, "commentary", None) or "")
    if _PH.search(theirs) or _TEMPERATURE.search(theirs) or not _states_both(mine):
        return ""
    return (f"; that row states no pH or temperature ({theirs!r}), while the resolver's pick states "
            f"both ({' '.join(mine.split())!r}): it is taken because it names {isoform}"
            ", not because it is the better-described measurement")


def _own_accession_of(m: Any, isoform: str) -> Optional[str]:
    """The one UniProt accession of the carried row's own cell, when UniProt
    names that protein `isoform` (`protein_names`); else None. The carried
    row is found among the measurement's ranked rows by its value and
    reference."""
    try:
        from caterva.enzymes.protein_names import info
    except ImportError:  # pragma: no cover
        return None
    cited = getattr(m, "reference_id", None) or "".join(
        re.findall(r"BRENDA ref (\d+)", str(getattr(m, "citation", None) or ""))[:1])
    for r in getattr(m, "alternatives", ()) or ():
        if not isinstance(r, dict) or r.get("value") is None or not r.get("uniprot"):
            continue
        if (float(r["value"]) != float(m.value)
                or not cited or str(r.get("reference_id") or "") != str(cited)
                or (r.get("conditions") or None) != (getattr(m, "commentary", None) or None)):
            continue
        found = info(str(r["uniprot"]))
        if found is not None and any(same_isoform(name, isoform) for name in found.names or ()):
            return str(r["uniprot"])
    return None


def select_isoform(measured: Mapping[str, Any], isoform: str,
                   asked: str = ASKED_BY_FLAG) -> IsoformSelection:
    """Each measured constant, taken from a row that measured `isoform` where
    the resolver ranked one. See the module docstring for the three cases.

    A Km and a kcat are taken from one paper's matched rows when it holds
    both, and a paper one of whose rows is a probable error
    (`_discredited_papers`) supplies neither (fifth round's review: DPP4's
    Km of 1.43 mM came from the paper of the 279000 1/s kcat).
    `asked` is what asked for the isoform, for the notes: "--isoform", or
    "your description" when it was read from the sentence (DPP4, CA2, NOS2:
    fifth round's review, V5-5)."""
    out = IsoformSelection(measured={})
    discredited = _discredited_papers(measured)
    taken: Dict[str, Mapping[str, Any]] = {}
    matching_of: Dict[str, List[Mapping[str, Any]]] = {}
    moved_from_unnamed: Dict[str, Any] = {}
    unnamed_kept: set = set()
    for identifier in sorted(measured):
        m = measured[identifier]
        # The words first, then the isoform the resolver read off the row's
        # own UniProt cell (ADR 0182, second round): an O75874 row measured
        # IDH1 whether or not its words say so.
        chosen = (_read_isoform(getattr(m, "commentary", None))
                  or getattr(m, "row_isoform", None))
        if same_isoform(chosen, isoform):
            out.measured[identifier] = m
            continue
        accession = _own_accession_of(m, isoform) if chosen is None else None
        if accession:
            # The protein asked for is the only one the EC number lists in
            # the organism, so the resolver reads no isoform off the cell
            # (it is the enzyme itself): AKR1C3's P42330 rows under EC
            # 1.1.1.188 were said to be rows of which "whether it measured
            # AKR1C3 is unknown" (sixth round of the real-values review).
            out.measured[identifier] = m
            out.notes.append(f"`{identifier}`: the row's UniProt accession ({accession}) is {isoform}")
            continue
        because = (getattr(m, "chosen_because", None) or "") + (getattr(m, "resolver_because", None) or "")
        if chosen is None and PAIRED_ACROSS_TIERS in because:
            # Human pyruvate kinase, "muscle" read as PKM: ref 674499's Km
            # and kcat, measured together, both naming no isoform, over
            # another paper's PKM row (fourth round of the real-values review).
            out.measured[identifier] = m
            # Said of the constant it is: the kcat is the one measured with
            # the Km (fifth round's review, V5-4).
            this, other = (("kcat", "Km") if "kcat" in identifier.lower().split("_")[-1]
                           else ("Km", "kcat"))
            out.notes.append(
                f"`{identifier}`: the row names no isoform; it is the {this} measured with the "
                f"{other} the model carries (one paper, the same stated conditions), kept over a row "
                f"naming {isoform} from another paper, so whether it measured {isoform} is unknown")
            continue
        rows = [r for r in getattr(m, "alternatives", ()) or ()
                if isinstance(r, dict) and r.get("value") is not None
                and (r.get("unit") in (None, m.unit))]
        named = [(r, _read_isoform(r.get("conditions")) or r.get("isoform")) for r in rows]
        lone = _isolated([float(r["value"]) for r, _ in named])
        named = [x for i, x in enumerate(named) if i not in lone]
        matching = [r for r, iso in named if same_isoform(iso, isoform)]
        set_aside = [r for r in matching if str(r.get("reference_id") or "") in discredited]
        matching = [r for r in matching if r not in set_aside]
        if set_aside and not matching:
            out.notes.append(
                f"`{identifier}`: the rows naming {isoform} ("
                + ", ".join(f"{float(r['value']):g} {m.unit}, BRENDA ref {r.get('reference_id')}"
                            for r in set_aside)
                + ") come from a paper whose other constant lies more than 100-fold from every "
                  "other row, a probable error, so they were not used")
        unnamed_values = [float(r["value"]) for r, iso in named if iso is None]
        if chosen is None:
            unnamed_values.append(float(m.value))
        if matching and _outlying([float(r["value"]) for r in matching], unnamed_values):
            # The resolver's rule (fallback_logic.isoform_rows_outlying): DPP4's
            # one paper naming P27487 gave kcat 279000 1/s against 20-87 1/s.
            out.measured[identifier] = m
            out.notes.append(
                f"`{identifier}`: the rows naming {isoform} ("
                + ", ".join(f"{float(r['value']):g} {m.unit}, BRENDA ref {r.get('reference_id')}"
                            for r in matching)
                + f") lie more than 100-fold outside every row naming no isoform, so they were set "
                  f"aside as a probable error; the row used names no isoform, so whether it "
                  f"measured {isoform} is unknown")
            continue
        if matching:
            # The resolver ranked the rows; its first row naming the isoform
            # is the one it would carry asked for it (`carry` keeps them one).
            row = matching[0]
            out.measured[identifier] = _from_row(m, row, f"the row for {isoform}, as {asked} asked")
            taken[identifier] = row
            matching_of[identifier] = matching
            if chosen is None:
                moved_from_unnamed[identifier] = m
            was = f"measured {chosen}" if chosen else "named no isoform"
            out.notes.append(
                f"`{identifier}`: the resolver's pick ({m.value:g} {m.unit}) {was}; the row for "
                f"{isoform} ({float(row['value']):g} {m.unit}, BRENDA ref {row.get('reference_id')}) "
                f"is used instead, as {asked} asked" + _conditions_lost(m, row, isoform))
            continue
        if chosen is None:
            out.measured[identifier] = m
            unnamed_kept.add(identifier)
            out.notes.append(
                f"`{identifier}`: no ranked row names {isoform}; the one used names no isoform, "
                f"so whether it measured {isoform} is unknown")
            continue
        # A row listing several proteins' accessions beside its paper's rows
        # naming one each is no protein's (fallback_logic _mark_unattributed):
        # CYP2D6's fenthion Km was such a row (fifth round's review).
        unattributed = [r for r, iso in named if iso is None and r.get("unattributed")]
        unnamed = [r for r, iso in named if iso is None and not r.get("unattributed")]
        if not unnamed and unattributed:
            refs = sorted({str(r.get("reference_id")) for r in unattributed})
            out.refused[identifier] = (
                f"no row for {isoform}: the rows BRENDA holds measured {chosen}, or list several "
                f"proteins' accessions and name none in their words (BRENDA ref {', '.join(refs)}, "
                f"whose other rows name other isoforms), so they cannot be taken as {isoform}'s "
                f"(--isoform {isoform})")
            continue
        if unnamed:
            row = unnamed[0]
            out.measured[identifier] = _from_row(
                m, row, f"a row naming no isoform, used because none names {isoform}")
            out.notes.append(
                f"`{identifier}`: the resolver's pick measured {chosen}, not {isoform}; a row naming "
                f"no isoform ({float(row['value']):g} {m.unit}) is used instead, and whether it "
                f"measured {isoform} is unknown")
            continue
        seen = sorted({iso for _, iso in named if iso} | {chosen})
        out.refused[identifier] = (
            f"no row for {isoform}: the rows BRENDA holds measured {', '.join(seen)}, and a constant "
            f"of another isoform is a different protein's (--isoform {isoform})")
    _pair_within_isoform(measured, out, taken, matching_of, isoform, asked)
    _move_both_or_neither(out, taken, moved_from_unnamed, unnamed_kept, isoform)
    return out


def _move_both_or_neither(out, taken, moved_from_unnamed, unnamed_kept, isoform) -> None:
    """A Km and a kcat move to rows naming the isoform together or not at
    all. When rows naming it give only one constant, and both of the
    resolver's picks named no isoform, moving that one alone sets one paper's
    named row beside another paper's unnamed row: no more the isoform's
    model than the resolver's two picks, and a mix of two preparations.
    DPP4: with ref 665551 set aside, only the kcat had a row naming DPP4
    (87 1/s, "dimeric rDPP-IV"), 4-fold above the wild-type rows the Km
    (0.165 mM) sat among (fifth round of the real-values review)."""
    ids = sorted(set(moved_from_unnamed) | unnamed_kept)
    km_id = next((i for i in ids if i.endswith("_Km")), None)
    kcat_id = next((i for i in ids if i.endswith("_kcat")), None)
    if not (km_id and kcat_id):
        return
    for moved, kept in ((km_id, kcat_id), (kcat_id, km_id)):
        if moved in moved_from_unnamed and kept in unnamed_kept:
            original = moved_from_unnamed[moved]
            row = taken[moved]
            out.measured[moved] = original
            prefix = f"`{moved}`: "
            out.notes[:] = [n for n in out.notes if not n.startswith(prefix)]
            out.notes.append(
                f"`{moved}`: a row naming {isoform} exists ({float(row['value']):g} "
                f"{original.unit}, BRENDA ref {row.get('reference_id')}), but no row naming "
                f"{isoform} gives the {kept.split('_')[-1]}, so the resolver's pick, which names "
                f"no isoform, is kept beside it: one evidence rule for both constants rather than "
                f"one paper's named row beside another's unnamed one; whether either measured "
                f"{isoform} is unknown")
            return


def _pair_within_isoform(measured, out, taken, matching_of, isoform, asked) -> None:
    """A Km and a kcat both re-taken from rows naming the isoform come from
    one paper's matched rows when the kcat's paper (else the Km's) holds
    them: the resolver's rule that a kcat's paper gives its Km pair, kept
    here (fifth round's review: DPP4's Km from ref 665551 beside a kcat from
    ref 678195, which holds the Km measured with it, 0.09 mM)."""
    km_id = next((i for i in taken if i.endswith("_Km")), None)
    kcat_id = next((i for i in taken if i.endswith("_kcat")), None)
    if not (km_id and kcat_id):
        return
    km_row, kcat_row = taken[km_id], taken[kcat_id]
    if str(km_row.get("reference_id")) == str(kcat_row.get("reference_id")):
        return
    for moved, partner_id in ((km_id, kcat_id), (kcat_id, km_id)):
        row = _same_paper_partner(matching_of[moved], taken[partner_id])
        if row is None:
            continue
        ref = row.get("reference_id")
        out.measured[moved] = _from_row(
            measured[moved], row,
            f"the row for {isoform}, as {asked} asked, measured with the {partner_id.split('_')[-1]} "
            f"carried (BRENDA ref {ref}, the same stated conditions)")
        prefix = f"`{moved}`: "
        out.notes[:] = [n for n in out.notes if not n.startswith(prefix)]
        m = measured[moved]
        out.notes.append(
            f"`{moved}`: the resolver's pick ({m.value:g} {m.unit}) named no isoform or another; "
            f"the row for {isoform} measured with the carried {partner_id.split('_')[-1]} "
            f"({float(row['value']):g} {m.unit}, BRENDA ref {ref}, one paper and the same stated "
            f"conditions) is used instead, as {asked} asked")
        return


__all__ = ["ASKED_BY_FLAG", "ASKED_BY_WORDS", "IsoformSelection", "select_isoform", "same_isoform"]
