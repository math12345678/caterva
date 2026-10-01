"""Kind `structure` and the 3D viewer's coordinates: `caterva structure` (owner: sci-structure).

WHAT THE KIND CALLS
-------------------
`caterva structure` itself (caterva/structure/__main__.py `run`): the
organism normalised, `find_structures` against UniProt and the RCSB,
`StructureSearch.ranked()`, each entry's `Structure.cite()`, and, when
asked, `chimerax.script`. The adapter passes `write=False` and keeps the
script as a run artifact instead of a file at a path from the request, so
the command line recorded on the run (`--chimerax <run dir>/artifacts/
structure.cxc`) names the same file the run stored. The report is the
command's own stdout, captured; every row of the result is read from the
same StructureSearch the report was printed from.

Exit 3 has three causes, all the command's: the search could not run (no
network: no result), the EC number is several proteins and none was chosen
(the protein table is still a result, so the page can offer the choice),
and a ChimeraX script was asked for a protein with no entry (a gap the
command used to crash on; fixed in the command, not here).

WHY THE COORDINATES GO THROUGH `caterva prepare`'S FETCH AND AUDIT
-----------------------------------------------------------------
The viewer draws an entry's atoms and marks its catalytic residues. The
atoms are the entry's mmCIF as `caterva prepare` downloads and caches it
(`fetcher()`: RCSB, cached under ~/.cache/caterva/prepare), read with
caterva/prepare/cif.py; the catalytic residues are the ones the audit places
on each chain (M-CSA's reference residues carried over by global
alignment), with where that placement came from. A viewer that picked "the
active site" itself (residues near a ligand, say) would show a second
answer to a question the tools already answer, and the two would disagree
on exactly the entries where it matters. When the audit cannot place them
(no M-CSA mechanism for the EC number, a twilight-zone alignment, UniProt
unreachable) the response says so in the audit's words and draws none.

Coordinates are sent as the file gives them, in angstroms, unrounded,
column by column (one list per field) so a 50,000-atom entry is one compact
JSON document rather than 50,000 objects.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Artifact, EndpointRequest, RunContext, cli_parser
from caterva.studio.adapters.md import RUN_DIR_PLACEHOLDER, checked, first_line

PROG = "caterva structure"

#: The artifact the ChimeraX script is stored as, and where the recorded
#: command line says it was written.
CHIMERAX_ARTIFACT = "structure.cxc"

REQUEST_KEYS: Mapping[str, type] = {
    "subject": str, "organism": str, "gene": str, "uniprot": str, "ligand": str, "top": int, "chimerax": bool,
}

RCSB_ENTRY = "https://www.rcsb.org/structure/{id}"
UNIPROT_ENTRY = "https://www.uniprot.org/uniprotkb/{acc}"


# ---------------------------------------------------------------------------
# Citations, shared with the prepare adapter
# ---------------------------------------------------------------------------


def method_citation(key: str) -> contract.Citation:
    """A method of caterva/methods.py as a Citation: its own `cite()` text
    and its DOI link."""
    from caterva.methods import METHODS

    m = METHODS[key]
    return {"text": m.cite(), "registry": None, "doi": m.doi, "url": f"https://doi.org/{m.doi}", "title": m.what}


def entry_citation(pdb_id: str, text: Optional[str] = None) -> contract.Citation:
    """A PDB entry as a citation of itself: its page at the RCSB and its own DOI."""
    pid = pdb_id.upper()
    return {"text": text or f"PDB {pid}, doi:10.2210/pdb{pid.lower()}/pdb", "registry": "PDB",
            "reference_id": pid, "url": RCSB_ENTRY.format(id=pid), "doi": f"10.2210/pdb{pid.lower()}/pdb"}


def structure_citation(s: Any) -> contract.Citation:
    """`Structure.cite()` with the parts it was built from. The link is the
    paper's DOI or PubMed page when the entry records a published paper,
    else the entry's own page (a deposition cites itself)."""
    c = s.citation
    out: contract.Citation = {"text": s.cite(), "registry": "PDB", "reference_id": s.pdb_id}
    if s.published and c.doi:
        out["url"] = f"https://doi.org/{c.doi}"
    elif s.published and c.pubmed:
        out["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{c.pubmed}/"
    else:
        out["url"] = RCSB_ENTRY.format(id=s.pdb_id)
    out.update({"title": c.title, "journal": c.journal, "year": c.year, "doi": c.doi if s.published else s.entry_doi,
                "pubmed": None if c.pubmed is None else str(c.pubmed)})
    return out


def reported(value: Optional[float], unit: str, citation: contract.Citation, organism: Optional[str],
             label: str, note: Optional[str] = None) -> Optional[contract.SourcedValue]:
    """A number an entry reports about itself (resolution, R-free): a
    measurement whose citation is the entry. None when the entry gives none."""
    if value is None:
        return None
    prov: contract.Provenance = {
        "kind": "measured", "citation": citation, "organism": organism, "cross_species": False,
        "conditions": {"ph": None, "temperature_c": None, "buffer": None, "unreported": []},
        "commentary": None, "scope": [],
    }
    if note:
        prov["note"] = note
    return contract.sourced(value, unit, prov, label=label)


# ---------------------------------------------------------------------------
# The kind
# ---------------------------------------------------------------------------


def structure_argv(request: Mapping[str, Any]) -> List[str]:
    from caterva.structure.__main__ import build_parser

    r = checked(request, REQUEST_KEYS, required=("subject",))
    argv = ["--subject", r["subject"]]
    for key in ("organism", "gene", "uniprot", "ligand"):
        if key in r:
            argv += ["--" + key, r[key]]
    if "top" in r:
        argv += ["--top", str(r["top"])]
    if r.get("chimerax"):
        argv += ["--chimerax", f"{RUN_DIR_PLACEHOLDER}/artifacts/{CHIMERAX_ARTIFACT}"]
    cli_parser(build_parser, PROG).parse_args(argv)
    return argv


def _describe(request: Mapping[str, Any]) -> str:
    what = f"Structures of EC {request.get('subject', '?')}"
    for key in ("organism", "gene", "uniprot"):
        if request.get(key):
            what += f", {request[key]}"
    if request.get("ligand"):
        what += f", with {request['ligand']}"
    return what


def _protein_rows(search: Any) -> List[contract.ProteinRow]:
    chosen = search.chosen.accession if search.chosen else None
    return [{"accession": p.accession, "gene": p.gene, "name": p.name, "organism": p.organism,
             "entries": len(p.structures), "chosen": p.accession == chosen,
             "url": UNIPROT_ENTRY.format(acc=p.accession)} for p in search.proteins]


def structure_row(s: Any, ligand: Optional[str]) -> contract.StructureRow:
    citation = structure_citation(s)
    organism = s.organisms[0] if len(s.organisms) == 1 else None
    return {
        "pdb_id": s.pdb_id,
        "title": s.title,
        "method": s.method,
        "resolution": reported(s.resolution, "Å", entry_citation(s.pdb_id), organism, "resolution",
                               note="the entry's resolution_combined, as the RCSB reports it"),
        "organisms": list(s.organisms),
        "uniprot": list(s.uniprot),
        "bound": [{"component": b.component, "name": b.name, "role": b.role} for b in s.bound],
        "citation": citation,
        "binds_ligand": s.binds(ligand) if ligand else None,
        "entry_doi": s.entry_doi,
        "entry_url": RCSB_ENTRY.format(id=s.pdb_id),
        "published": s.published,
    }


def structure_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.structure.__main__ import build_parser, run as run_structure

    argv = [a.replace(RUN_DIR_PLACEHOLDER, str(ctx.run_dir)) for a in structure_argv(request)]
    args = cli_parser(build_parser, PROG).parse_args(argv)
    ctx.progress.stage("search", f"Searching UniProt and the PDB for EC {args.subject}"
                       + (f" in {args.organism}" if args.organism else ""))
    ctx.progress.check_cancelled()
    out, err = io.StringIO(), io.StringIO()
    done = run_structure(args, out, err, write=False)
    if done.search is None:
        return AdapterOutcome(3, None, first_line(done.refusal), done.refusal)
    ctx.progress.stage("rank", "Ranking the chosen protein's entries by ligand, method and resolution")
    search = done.search
    ranked = search.ranked()
    artifacts = ()
    if done.chimerax is not None:
        artifacts = (Artifact(CHIMERAX_ARTIFACT, done.chimerax.encode("utf-8"), "text/plain; charset=utf-8",
                              f"ChimeraX script for PDB {done.best.pdb_id}: run it with `chimerax {CHIMERAX_ARTIFACT}`"),)
    result: contract.StructureResult = {
        "ec": search.ec,
        "organism": search.organism,
        "ligand": search.ligand,
        "proteins": _protein_rows(search),
        "chosen": search.chosen.accession if search.chosen else None,
        "undecided": search.undecided,
        "entries": [structure_row(s, search.ligand) for s in ranked],
        "total": len(ranked),
        "report_markdown": out.getvalue(),
        "chimerax_artifact": CHIMERAX_ARTIFACT if artifacts else None,
        "organism_note": done.organism_note,
        "top": args.top,
        "sources": [method_citation("pdb"),
                    {"text": "UniProt for the protein grouping", "registry": "UniProt", "url": None}],
    }
    if search.chosen is not None:
        who = f"{search.chosen.gene or search.chosen.accession} ({search.chosen.accession})"
        summary = f"EC {search.ec}: {who}, {len(ranked)} entries" + (f", best {ranked[0].pdb_id}" if ranked else "")
    else:
        summary = f"EC {search.ec}: {len(search.proteins)} proteins, none chosen"
    return AdapterOutcome(done.code, result, summary, done.refusal if done.code == 3 else None, artifacts)


# ---------------------------------------------------------------------------
# GET /api/structure/{pdb_id}/coordinates
# ---------------------------------------------------------------------------


def _fetch_cif(pdb_id: str, fetch) -> str:
    from caterva.prepare.__main__ import RCSB_CIF, PrepareError

    try:
        return fetch(RCSB_CIF.format(id=pdb_id))
    except PrepareError as e:
        raise contract.NotFound(f"caterva prepare: {e}") from None
    except Exception as e:  # noqa: BLE001 - a network failure is unavailability, said with its reason
        if type(e).__module__.startswith(("requests", "urllib3", "socket", "ssl")) or isinstance(e, OSError):
            raise contract.Unavailable(f"could not reach the PDB ({type(e).__name__}: {e})") from None
        raise


def atom_columns(rows: Sequence[Mapping[str, str]]) -> contract.AtomColumns:
    """The atom_site rows as columns, values as the file gives them."""
    cols: contract.AtomColumns = {"x": [], "y": [], "z": [], "element": [], "atom_name": [], "resname": [],
                                  "chain": [], "resseq": [], "hetero": []}
    for a in rows:
        cols["x"].append(float(a["Cartn_x"]))
        cols["y"].append(float(a["Cartn_y"]))
        cols["z"].append(float(a["Cartn_z"]))
        cols["element"].append(a.get("type_symbol", "?"))
        cols["atom_name"].append(a.get("auth_atom_id") or a.get("label_atom_id", "?"))
        cols["resname"].append(a.get("auth_comp_id") or a.get("label_comp_id", "?"))
        cols["chain"].append(a.get("auth_asym_id") or a.get("label_asym_id", "?"))
        seq = a.get("auth_seq_id", "?")
        cols["resseq"].append(int(seq) if seq.lstrip("-").isdigit() else 0)
        cols["hetero"].append(a.get("group_PDB") == "HETATM")
    return cols


def _primary_citation(parsed: Mapping[str, Any], pdb_id: str, title: str, method: str) -> contract.Citation:
    """The entry's primary citation, worded by `Structure.cite()` from the
    mmCIF's own citation and citation_author categories."""
    from caterva.prepare.cif import missing
    from caterva.structure.search import Citation, Structure

    primary = next((c for c in parsed.get("citation", []) if c.get("id") == "primary"), None)
    if primary is None:
        return entry_citation(pdb_id)

    def value(key: str) -> Optional[str]:
        v = primary.get(key)
        return None if v is None or missing(v) else v

    authors = [a.get("name", "") for a in parsed.get("citation_author", []) if a.get("citation_id") == "primary"]
    year, pubmed = value("year"), value("pdbx_database_id_PubMed")
    cit = Citation(title=value("title"), journal=value("journal_abbrev"),
                   year=int(year) if year and year.isdigit() else None, doi=value("pdbx_database_id_DOI"),
                   pubmed=int(pubmed) if pubmed and pubmed.isdigit() else None,
                   first_author=authors[0].split(",")[0].strip() if authors else None)
    return structure_citation(Structure(pdb_id, title, method, None, (), (), (), cit))


def _catalytic(a: Any) -> List[contract.CatalyticSite]:
    return [{"chain": c.chain, "resseq": c.auth_seq_id, "resname": c.found, "expected": c.expected,
             "conserved": c.found == c.expected, "roles": c.roles, "reference": c.reference} for c in a.catalytic]


def catalytic_reference(a: Any) -> Optional[contract.CatalyticReference]:
    """Which M-CSA mechanism the audit took the catalytic residues from."""
    r = a.reference
    if r is None:
        return None
    first = a.chains[0] if a.chains else "?"
    identity = contract.sourced(r.identity, "", contract.computed(
        "global alignment (Needleman-Wunsch, BLOSUM62) of the M-CSA reference sequence against chain "
        f"{first}: identical positions over aligned positions", [r.uniprot, f"chain {first}"]),
        label="sequence identity")
    return {"mcsa_id": r.mcsa_id, "enzyme": r.enzyme, "uniprot": r.uniprot, "how": r.how, "identity": identity,
            "citation": {**method_citation("mcsa"), "registry": "M-CSA", "reference_id": str(r.mcsa_id)},
            "rejected": [f"{mid} {name} ({ident:.0%})" for mid, name, ident in r.rejected]}


def _no_catalytic_reason(a: Any) -> str:
    """The audit's own sentence for why it placed no catalytic residue."""
    for line in a.not_checked:
        if line.startswith("catalytic residues"):
            return line
    return "the audit placed no catalytic residue on this entry"


def coordinates(req: EndpointRequest) -> contract.CoordinatesResponse:
    """GET /api/structure/{pdb_id}/coordinates (CoordinatesResponse)."""
    from caterva.prepare.__main__ import PrepareError, fetcher
    from caterva.prepare.audit import _first_model, audit
    from caterva.prepare.cif import parse
    from caterva.prepare.__main__ import sequence_fetcher

    if req.query:
        raise contract.Malformed(f"this endpoint takes no query; got {', '.join(sorted(req.query))}",
                                 field=sorted(req.query)[0])
    pdb_id = req.params["pdb_id"].upper()
    fetch = fetcher()
    text = _fetch_cif(pdb_id, fetch)
    parsed = parse(text)
    title = (parsed.get("struct") or [{}])[0].get("title", "")
    method = (parsed.get("exptl") or [{}])[0].get("method", "?")
    atoms = _first_model(parsed.get("atom_site", []))
    count_all = len(atoms)
    truncated, omitted = False, None
    if count_all > contract.MAX_VIEWER_ATOMS:
        types = {e.get("id"): e.get("type") for e in parsed.get("entity", [])}
        kept = [a for a in atoms if types.get(a.get("label_entity_id")) in ("polymer", "non-polymer")]
        dropped_solvent = count_all - len(kept)
        truncated = True
        omitted = f"{dropped_solvent} water and solvent atoms of model 1 (the entry has {count_all} atoms in model 1)"
        if len(kept) > contract.MAX_VIEWER_ATOMS:
            omitted += (f"; and {len(kept) - contract.MAX_VIEWER_ATOMS} polymer and ligand atoms after the first "
                        f"{contract.MAX_VIEWER_ATOMS} in file order")
            kept = kept[:contract.MAX_VIEWER_ATOMS]
        atoms = kept
    response: contract.CoordinatesResponse = {
        "pdb_id": pdb_id,
        "citation": _primary_citation(parsed, pdb_id, title, method),
        "atoms": atom_columns(atoms),
        "count": len(atoms),
        "truncated": truncated,
        "title": title,
        "method": method,
        "resolution": None,
        "omitted": omitted,
        "chains": [],
        "catalytic": [],
        "catalytic_reference": None,
        "catalytic_reason": None,
    }
    try:
        a = audit(text, sequence_fetcher(fetch))
    except PrepareError as e:
        response["catalytic_reason"] = f"caterva prepare: {e}"
        return response
    except ValueError as e:
        response["catalytic_reason"] = f"caterva prepare: {e}"
        return response
    except Exception as e:  # noqa: BLE001 - UniProt unreachable: the atoms still stand, the residues are unknown
        if type(e).__module__.startswith("requests") or isinstance(e, OSError):
            response["catalytic_reason"] = f"caterva prepare: could not reach the PDB or UniProt ({e})"
            return response
        raise
    organism = None
    response["resolution"] = reported(a.resolution, "Å", entry_citation(pdb_id), organism, "resolution",
                                      note="refine.ls_d_res_high of the entry's mmCIF")
    response["chains"] = list(a.chains)
    response["catalytic"] = _catalytic(a)
    response["catalytic_reference"] = catalytic_reference(a)
    if a.reference is None:
        response["catalytic_reason"] = _no_catalytic_reason(a)
    return response


def register(registry) -> None:
    registry.register(AdapterSpec(
        kind="structure",
        title="Find structures",
        command="structure",
        needs=("network",),
        argv=structure_argv,
        run=structure_run,
        describe=_describe,
        cli_prefix=("caterva", "structure"),
    ))
    registry.add_endpoint("structure_coordinates", coordinates, owner="structure")


__all__ = ["CHIMERAX_ARTIFACT", "PROG", "atom_columns", "catalytic_reference", "coordinates", "entry_citation",
           "method_citation", "register", "reported", "structure_argv", "structure_citation", "structure_row",
           "structure_run"]
