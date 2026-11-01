"""What is wrong with a PDB entry as the starting point of a simulation.

Every finding says where in the entry it came from (the mmCIF category),
how much it matters (`blocks`, `decide`, `note`), and how far it sits from
the enzyme's catalytic residues -- because a missing loop on the far side
of the protein and a missing loop over the active site are not the same
defect, and a report that ranks them equally hides the one that matters.

Catalytic residues come from M-CSA's reference enzyme for the entry's EC
number, carried onto each chain by global alignment. The report says which
reference was used, how identical it is, and which candidates were
rejected, so the mapping can be disputed rather than trusted.

Nothing here edits the structure. It reports; fixing is a separate choice.
"""
from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .align import Alignment, align, one_letter
from .cif import Table, missing, parse

#: Within this distance of a catalytic atom a defect is reported as touching
#: the active site. 10 A is a common first-shell-plus-one cutoff; it is a
#: choice, and the report says so.
ACTIVE_SITE_RADIUS = 10.0

#: Below this identity a reference residue position is not transferred.
#: Twilight-zone alignments place residues confidently and wrongly.
MIN_TRANSFER_IDENTITY = 0.30

#: The R-free above which a model is flagged for a second look.
RFREE_REVIEW = 0.30

STANDARD = set("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split())

#: struct_ref_seq_dif details that describe the construct, not the protein.
CONSTRUCT_ADDITIONS = ("expression tag", "cloning artifact", "linker", "initiating methionine",
                       "leader sequence", "insertion")

_DATA = pathlib.Path(__file__).with_name("data") / "mcsa_catalytic.json"


@dataclass
class Finding:
    check: str
    severity: str  # blocks | decide | note
    what: str
    source: str  # the mmCIF category or database the fact came from
    chain: Optional[str] = None
    residues: List[str] = field(default_factory=list)  # author numbering
    distance: Optional[float] = None  # to the nearest catalytic atom in the chain, A
    catalytic: bool = False  # the defect is ON a catalytic residue
    #: label_seq_id range of an unmodelled stretch (internal)
    span: Optional[Tuple[int, int]] = None

    @property
    def near_active_site(self) -> bool:
        return self.distance is not None and self.distance <= ACTIVE_SITE_RADIUS


@dataclass
class CatalyticResidue:
    chain: str
    auth_seq_id: str
    expected: str  # three-letter code in the reference
    found: Optional[str]  # three-letter code in this chain, None if unaligned
    roles: str
    reference: str  # e.g. "His194 of P00341"
    seq_id: Optional[int] = None  # label_seq_id in this chain


@dataclass
class Reference:
    mcsa_id: int
    enzyme: str
    uniprot: str
    identity: float
    how: str  # "same UniProt accession" | "best of N for EC ... by alignment"
    rejected: List[Tuple[int, str, float]] = field(default_factory=list)


@dataclass
class ChainSummary:
    chain: str
    blocks: int
    near_site: int  # findings of any severity within ACTIVE_SITE_RADIUS
    catalytic_intact: bool


@dataclass
class TitratableSite:
    """A titratable residue within ACTIVE_SITE_RADIUS of a catalytic atom (or
    catalytic itself). Its charge at the assay pH is judged in the report."""
    chain: str
    auth_seq_id: str
    resname: str
    distance: float  # to the nearest catalytic atom, A
    catalytic: bool


@dataclass
class Audit:
    pdb_id: str
    title: str
    method: str
    resolution: Optional[float]
    r_free: Optional[float]
    chains: List[str]
    findings: List[Finding]
    catalytic: List[CatalyticResidue]
    reference: Optional[Reference]
    not_checked: List[str]
    chain_summary: List[ChainSummary] = field(default_factory=list)
    titratable: List[TitratableSite] = field(default_factory=list)

    def by_severity(self, severity: str) -> List[Finding]:
        return [f for f in self.findings if f.severity == severity]


# --------------------------------------------------------------------------
# Structure access

@dataclass
class _Res:
    chain: str
    auth_seq_id: str
    comp: str
    label_seq_id: str
    atoms: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    alt_ids: set = field(default_factory=set)


def _first_model(atom_site: Table) -> Table:
    if not atom_site:
        return []
    first = atom_site[0].get("pdbx_PDB_model_num", "1")
    return [a for a in atom_site if a.get("pdbx_PDB_model_num", "1") == first]


def _residues(atoms: Table, entity: str) -> Dict[Tuple[str, str], _Res]:
    out: Dict[Tuple[str, str], _Res] = {}
    for a in atoms:
        if a.get("label_entity_id") != entity or a.get("group_PDB") not in ("ATOM", "HETATM"):
            continue
        ins = a.get("pdbx_PDB_ins_code", "?")
        key = (a["auth_asym_id"], a["auth_seq_id"] + ("" if missing(ins) else ins))
        r = out.get(key)
        if r is None:
            r = out[key] = _Res(a["auth_asym_id"], key[1], a["label_comp_id"], a.get("label_seq_id", "."))
        if not missing(a.get("label_alt_id", ".")):
            r.alt_ids.add(a["label_alt_id"])
        r.atoms.setdefault(a["label_atom_id"],
                           (float(a["Cartn_x"]), float(a["Cartn_y"]), float(a["Cartn_z"])))
    return out


def _min_distance(a: _Res, bs: Sequence[_Res]) -> Optional[float]:
    best: Optional[float] = None
    for b in bs:
        for p in a.atoms.values():
            for q in b.atoms.values():
                d = math.dist(p, q)
                if best is None or d < best:
                    best = d
    return best


def _label(r: _Res) -> str:
    return f"{r.comp.title()}{r.auth_seq_id}"


# --------------------------------------------------------------------------
# Catalytic residues

def load_mcsa() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def _chain_sequence(scheme: Table, asym: str) -> Tuple[str, List[dict]]:
    rows = [r for r in scheme if r["asym_id"] == asym]
    rows.sort(key=lambda r: int(r["seq_id"]))
    return "".join(one_letter(r["mon_id"]) for r in rows), rows


def choose_reference(accessions: Sequence[str], ec: Optional[str], chain_seq: str,
                     sequence_of: Callable[[str], str], mcsa: dict
                     ) -> Tuple[Optional[dict], Optional[Reference], Optional[Alignment], str]:
    """The M-CSA entry whose catalytic residues apply here, and why.

    Same UniProt accession wins outright. Otherwise every entry sharing the
    EC number is aligned and the most identical is kept -- the others are
    reported, because an EC number is a reaction, not a mechanism, and
    unrelated families share them (EC 3.2.1.17 is three lysozyme families).
    """
    entries = mcsa["entries"]
    for e in entries:
        if e["uniprot"] in accessions:
            aln = align(sequence_of(e["uniprot"]), chain_seq)
            return e, Reference(e["mcsa_id"], e["enzyme"], e["uniprot"], aln.identity,
                                "same UniProt accession"), aln, ""
    if not ec:
        return None, None, None, "the entry names no EC number, so no M-CSA mechanism could be matched"
    candidates = [e for e in entries if ec in e["ecs"]]
    if not candidates:
        return None, None, None, f"M-CSA has no mechanism for EC {ec}"
    scored = []
    for e in candidates:
        aln = align(sequence_of(e["uniprot"]), chain_seq)
        scored.append((aln.identity, e, aln))
    scored.sort(key=lambda t: -t[0])
    ident, best, aln = scored[0]
    if ident < MIN_TRANSFER_IDENTITY:
        return None, None, None, (
            f"M-CSA's references for EC {ec} are at most {ident:.0%} identical to this chain; "
            f"below {MIN_TRANSFER_IDENTITY:.0%} residue positions are not transferred")
    ref = Reference(best["mcsa_id"], best["enzyme"], best["uniprot"], ident,
                    f"best of {len(scored)} for EC {ec} by alignment",
                    [(e["mcsa_id"], e["enzyme"], i) for i, e, _ in scored[1:]])
    return best, ref, aln, ""


# --------------------------------------------------------------------------
# The audit

def audit(cif_text: str, sequence_of: Callable[[str], str],
          mcsa: Optional[dict] = None) -> Audit:
    c = parse(cif_text)
    mcsa = mcsa or load_mcsa()
    entry_id = c.get("entry", [{}])[0].get("id", "?")
    title = c.get("struct", [{}])[0].get("title", "")
    method = c.get("exptl", [{}])[0].get("method", "?")
    refine = c.get("refine", [{}])[0]
    res = refine.get("ls_d_res_high")
    rfree = refine.get("ls_R_factor_R_free")
    resolution = None if res is None or missing(res) else float(res)
    r_free = None if rfree is None or missing(rfree) else float(rfree)

    findings: List[Finding] = []
    not_checked: List[str] = []

    # The enzyme entity: the first polypeptide carrying an EC number, else
    # the first polypeptide.
    polys = [e for e in c.get("entity", []) if e.get("type") == "polymer"]
    enz = next((e for e in polys if not missing(e.get("pdbx_ec", "?"))), polys[0] if polys else None)
    if enz is None:
        raise ValueError(f"{entry_id} has no polymer entity to audit")
    ent = enz["id"]
    ec = None if missing(enz.get("pdbx_ec", "?")) else enz["pdbx_ec"].split(",")[0].strip()
    accessions = sorted({r["pdbx_db_accession"] for r in c.get("struct_ref_seq", [])})

    atoms = _first_model(c.get("atom_site", []))
    residues = _residues(atoms, ent)
    scheme = [r for r in c.get("pdbx_poly_seq_scheme", []) if r["entity_id"] == ent]
    asyms = sorted({r["asym_id"] for r in scheme})
    auth_of_asym = {r["asym_id"]: r["pdb_strand_id"] for r in scheme}
    chains = [auth_of_asym[a] for a in asyms]

    # --- entry quality -------------------------------------------------------
    if "X-RAY" in method and r_free is not None and r_free > RFREE_REVIEW:
        findings.append(Finding("model quality", "decide",
                                f"R-free is {r_free:.3f}, above {RFREE_REVIEW}: the model fits its own data "
                                "loosely; prefer another entry if one exists", "refine"))
    if "NMR" in method or len({a.get("pdbx_PDB_model_num") for a in c.get("atom_site", [])}) > 1:
        findings.append(Finding("model choice", "decide",
                                "the entry holds several models; this audit read model 1, and which model "
                                "starts a simulation is a choice to record", "atom_site"))

    # --- assembly --------------------------------------------------------------
    asm = c.get("pdbx_struct_assembly", [])
    if asm:
        count = asm[0].get("oligomeric_count", "?")
        details = asm[0].get("oligomeric_details", "?")
        if not missing(count) and int(count) != len(chains):
            findings.append(Finding("biological assembly", "decide",
                                    f"the deposited coordinates hold {len(chains)} copies of the enzyme; "
                                    f"assembly 1 is {details} ({count} chains). Simulating one chain, or the "
                                    "asymmetric unit, is a choice about the protein's state, and should be "
                                    "recorded as one", "pdbx_struct_assembly"))

    # --- sequence differences --------------------------------------------------
    for d in c.get("struct_ref_seq_dif", []):
        detail = d.get("details", "?")
        where = f"{d.get('db_mon_id', '?').title()}{d.get('pdbx_seq_db_seq_num', '?')}" \
            f"->{d.get('mon_id', '?').title()}"
        chain = d.get("pdbx_pdb_strand_id")
        auth = d.get("pdbx_auth_seq_num", "?")
        if any(k in detail.lower() for k in CONSTRUCT_ADDITIONS):
            findings.append(Finding("construct", "note",
                                    f"{d.get('mon_id', '?').title()}{auth}: {detail} (not part of the "
                                    "natural protein)", "struct_ref_seq_dif", chain, [auth]))
        else:
            findings.append(Finding("sequence differs from UniProt", "blocks",
                                    f"{where} at residue {auth}, which the depositors call '{detail}'. "
                                    "Whatever the label, this chain is not the natural sequence: simulating it "
                                    "as the wild type describes a different protein", "struct_ref_seq_dif",
                                    chain, [auth]))

    # --- unobserved residues and atoms ----------------------------------------
    unobs = [r for r in c.get("pdbx_unobs_or_zero_occ_residues", [])
             if r.get("polymer_flag") == "Y" and r.get("PDB_model_num", "1") == "1"]
    by_chain: Dict[str, List[dict]] = {}
    for r in unobs:
        by_chain.setdefault(r["auth_asym_id"], []).append(r)
    for chain, rows in by_chain.items():
        auth_at = {int(r["label_seq_id"]): r["auth_seq_id"] for r in rows
                   if not missing(r.get("label_seq_id", "?"))}
        seq_ids = sorted(auth_at)
        last = max((int(r["seq_id"]) for r in scheme if auth_of_asym[r["asym_id"]] == chain), default=0)
        runs: List[Tuple[int, int]] = []
        for s in seq_ids:
            if runs and s == runs[-1][1] + 1:
                runs[-1] = (runs[-1][0], s)
            else:
                runs.append((s, s))
        for a, b in runs:
            terminal = a == 1 or b == last
            n = b - a + 1
            findings.append(Finding(
                "unmodelled residues", "note" if terminal else "blocks",
                (f"{n} residue{'s' if n > 1 else ''} at the {'N' if a == 1 else 'C'} terminus not modelled"
                 if terminal else
                 f"{n} residue{'s' if n > 1 else ''} missing inside the chain: a chain break. pdb2gmx will "
                 "either refuse or join the ends across the gap; the loop must be modelled or the break "
                 "capped, and either is a choice to record"),
                "pdbx_unobs_or_zero_occ_residues", chain,
                [auth_at[a] if a == b else f"{auth_at[a]}-{auth_at[b]}"], span=(a, b)))
    atoms_missing: Dict[Tuple[str, str], List[str]] = {}
    for r in c.get("pdbx_unobs_or_zero_occ_atoms", []):
        if r.get("polymer_flag") != "Y" or r.get("PDB_model_num", "1") != "1":
            continue
        atoms_missing.setdefault((r["auth_asym_id"], r["auth_seq_id"]), []).append(r["auth_atom_id"])
    for (chain, seq), names in sorted(atoms_missing.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        r = residues.get((chain, seq))
        label = _label(r) if r else seq
        findings.append(Finding("incomplete side chain", "decide",
                                f"{label} lacks {', '.join(names)}; pdb2gmx rebuilds nothing, so the side "
                                "chain must be completed (and how, recorded) before setup",
                                "pdbx_unobs_or_zero_occ_atoms", chain, [seq]))

    # --- alternate conformations and non-standard residues ---------------------
    for key, r in sorted(residues.items(), key=lambda kv: (kv[0][0], kv[1].label_seq_id)):
        if len(r.alt_ids) > 1:
            findings.append(Finding("alternate conformations", "decide",
                                    f"{_label(r)} is modelled in {len(r.alt_ids)} conformations "
                                    f"({', '.join(sorted(r.alt_ids))}); a simulation starts from one, and "
                                    "which one is a choice", "atom_site.label_alt_id", r.chain, [r.auth_seq_id]))
        if r.comp not in STANDARD:
            findings.append(Finding("non-standard residue", "blocks",
                                    f"{r.comp} at {r.auth_seq_id} is not one of the twenty standard amino "
                                    "acids (selenomethionine, a modified residue, or a ligand in the chain); "
                                    "the force field has no parameters for it as deposited",
                                    "atom_site", r.chain, [r.auth_seq_id]))

    # --- catalytic residues ------------------------------------------------------
    catalytic: List[CatalyticResidue] = []
    reference: Optional[Reference] = None
    cat_res: Dict[str, List[_Res]] = {}
    if asyms:
        seq0, _ = _chain_sequence(scheme, asyms[0])
        entry, reference, _, why = choose_reference(accessions, ec, seq0, sequence_of, mcsa)
        if entry is None:
            not_checked.append(f"catalytic residues: {why}")
        else:
            ref_seq = sequence_of(entry["uniprot"])
            for asym in asyms:
                chain = auth_of_asym[asym]
                seq, rows = _chain_sequence(scheme, asym)
                aln = align(ref_seq, seq)
                for cr in entry["residues"]:
                    if cr.get("uniprot", entry["uniprot"]) != entry["uniprot"]:
                        continue  # a residue on a partner subunit; see not_checked
                    pos = aln.target_of(int(cr["resid"]))
                    row = rows[pos - 1] if pos else None
                    auth = row["auth_seq_num"] if row and not missing(row.get("auth_seq_num", "?")) \
                        else (row["pdb_seq_num"] if row else "?")
                    found = row["mon_id"] if row else None
                    catalytic.append(CatalyticResidue(
                        chain, auth, cr["code"].upper(), found, cr.get("roles", ""),
                        f"{cr['code']}{cr['resid']} of {entry['uniprot']}",
                        int(row["seq_id"]) if row else None))
                    live = residues.get((chain, auth))
                    if live is not None and live.atoms:
                        cat_res.setdefault(chain, []).append(live)
                    elif found is not None:
                        findings.append(Finding(
                            "catalytic residue", "blocks",
                            f"{found.title()}{auth} ({cr['code']}{cr['resid']} of {entry['uniprot']}; "
                            f"{cr.get('roles') or 'catalytic'}) is not modelled at all in chain {chain}",
                            "M-CSA + pdbx_poly_seq_scheme", chain, [auth], 0.0))
            if any(r.get("uniprot", entry["uniprot"]) != entry["uniprot"] for r in entry["residues"]):
                not_checked.append("catalytic residues on partner subunits (the M-CSA reference is a "
                                   "complex); only this entity's residues were mapped")

    for cr in catalytic:
        if cr.found is None:
            findings.append(Finding("catalytic residue", "blocks",
                                    f"{cr.reference} has no counterpart in chain {cr.chain}",
                                    "M-CSA + alignment", cr.chain, [cr.reference]))
        elif cr.found != cr.expected:
            findings.append(Finding("catalytic residue", "blocks",
                                    f"{cr.found.title()}{cr.auth_seq_id} sits where {cr.reference} "
                                    f"({cr.expected.title()}, {cr.roles or 'catalytic'}) is expected: the "
                                    "catalytic residue is not conserved here, or has been mutated",
                                    "M-CSA + alignment", cr.chain, [cr.auth_seq_id], 0.0))

    # --- place every located finding relative to its own chain's active site ----
    for f in findings:
        if f.chain is None or not f.residues or f.distance is not None:
            continue
        cats = cat_res.get(f.chain, [])
        if not cats:
            continue
        if f.span is not None:  # an unmodelled run: measure from its observed flanks
            a, b = f.span
            flanks = [r for r in residues.values() if r.chain == f.chain and r.label_seq_id.isdigit()
                      and int(r.label_seq_id) in (a - 1, b + 1)]
            ds = [d for d in (_min_distance(r, cats) for r in flanks) if d is not None]
            f.distance = min(ds) if ds else None
        else:
            r = residues.get((f.chain, f.residues[0]))
            if r is not None:
                f.distance = _min_distance(r, cats)
        if f.near_active_site and f.severity == "note":
            f.severity = "decide"

    # A defect ON a catalytic residue is never a detail.
    cat_keys = {(cr.chain, cr.auth_seq_id): cr for cr in catalytic}
    for f in findings:
        if f.check == "catalytic residue" or f.chain is None:
            continue
        hits = [cat_keys.get((f.chain, tag)) for tag in f.residues]
        if f.span is not None:
            hits += [cr for cr in catalytic if cr.chain == f.chain and cr.seq_id is not None
                     and f.span[0] <= cr.seq_id <= f.span[1]]
        for cr in hits:
            if cr is not None:
                f.distance = 0.0
                f.catalytic = True
                f.severity = "blocks"
                f.what = (f"CATALYTIC RESIDUE {(cr.found or cr.expected).title()}{cr.auth_seq_id} "
                          f"({cr.reference}; {cr.roles or 'catalytic'}). " + f.what)

    # --- titratable residues at the active site (judged against a pH in the report)
    from caterva.prepare.protonation import TITRATABLE
    titratable: List[TitratableSite] = []
    for chain, cats in cat_res.items():
        cat_ids = {(r.chain, r.auth_seq_id) for r in cats}
        for r in residues.values():
            if r.chain != chain or r.comp.upper() not in TITRATABLE or not r.atoms:
                continue
            is_cat = (r.chain, r.auth_seq_id) in cat_ids
            d = 0.0 if is_cat else _min_distance(r, cats)
            if d is not None and d <= ACTIVE_SITE_RADIUS:
                titratable.append(TitratableSite(chain, r.auth_seq_id, r.comp.upper(), d, is_cat))
    titratable.sort(key=lambda t: (t.chain, t.distance))

    summary: List[ChainSummary] = []
    for chain in chains:
        mine = [f for f in findings if f.chain == chain]
        intact = all(cr.found == cr.expected for cr in catalytic if cr.chain == chain) and \
            not any(f.catalytic or f.check == "catalytic residue" for f in mine)
        summary.append(ChainSummary(chain, sum(f.severity == "blocks" for f in mine),
                                    sum(f.near_active_site for f in mine), intact))

    not_checked.append("structure-based pKa values: PROPKA is not run, so the protonation section judges "
                       "each active-site residue only by how far folded proteins typically move its group's pKa")
    not_checked.append("ligand and cofactor parameters (caterva md strips ligands; see MD_ROADMAP M4)")

    return Audit(entry_id, title, method, resolution, r_free, chains, findings, catalytic,
                 reference, not_checked, summary, titratable)


__all__ = ["Audit", "ChainSummary", "Finding", "CatalyticResidue", "Reference", "TitratableSite", "audit",
           "choose_reference", "load_mcsa", "ACTIVE_SITE_RADIUS", "MIN_TRANSFER_IDENTITY"]
