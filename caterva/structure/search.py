"""Find the experimental structures of an enzyme, and say which protein each is.

WHY THIS EXISTS
---------------
Caterva's kinetics name an enzyme by EC number and organism. A structure
belongs to one PROTEIN, and an EC number in one organism is often several:
EC 1.1.1.27 in human is LDHA, LDHB, LDHC and two LDHAL6 proteins, with 55
PDB entries between them (measured 2026-09-27). Picking "the" structure for
1.1.1.27 would silently pick an isoform, and a model built on LDHB's pocket
with LDHA's Km describes no enzyme that exists. So the search groups entries
by UniProt accession and refuses to choose between proteins unless told.

WHAT EACH ENTRY CARRIES
-----------------------
Method and resolution, the primary citation (DOI and PubMed id where the
entry records them), the source organism, and every bound small molecule
sorted into what it is:

    ligand      the chemistry the question is probably about
    cofactor    NAD(H), FAD, PLP, heme, ATP ...
    metal       an ion whose role the entry does not state
    additive    glycerol, sulfate, acetate, PEG: there because of how the
                crystal was grown, not because the enzyme binds them

A report that listed "bound: glycerol" as though it were a substrate would
be the structural version of an uncited number.

NETWORK
-------
UniProt REST and RCSB's search and GraphQL APIs, through an injectable
`Http`, so the tests replay recorded responses rather than calling out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

UNIPROT = "https://rest.uniprot.org/uniprotkb/search"
RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_GRAPHQL = "https://data.rcsb.org/graphql"

#: Components present because of crystallisation or cryoprotection. Kept as
#: a short explicit list: an unknown component is reported as a ligand, so
#: the error this list can make is under-labelling an additive, never
#: hiding a ligand.
ADDITIVES = frozenset({
    "GOL", "EDO", "PEG", "PG4", "PGE", "1PE", "P6G", "MPD", "DMS", "SO4",
    "PO4", "ACT", "ACY", "FMT", "CIT", "TRS", "MES", "EPE", "IMD", "BME",
    "DTT", "IOD", "CL", "BR", "NO3", "SCN", "NH4", "UNX", "MLI", "MLA",
})
COFACTORS = frozenset({
    "NAD", "NAI", "NAP", "NDP", "NADH", "FAD", "FMN", "ATP", "ADP", "AMP",
    "ANP", "GTP", "GDP", "HEM", "HEC", "PLP", "TPP", "COA", "SAM", "SAH",
    "BTN", "H4B", "MTE", "CLA",
})
METALS = frozenset({
    "MG", "ZN", "MN", "FE", "FE2", "CA", "CU", "CU1", "CO", "NI", "NA", "K",
    "CD", "HG", "MO", "W",
})
#: How far an entry's method ranks above another, best first.
METHOD_RANK = {"X-RAY DIFFRACTION": 0, "ELECTRON MICROSCOPY": 1,
               "SOLUTION NMR": 2, "SOLID-STATE NMR": 2, "NEUTRON DIFFRACTION": 0}


@dataclass(frozen=True)
class BoundMolecule:
    component: str
    name: str
    role: str  # ligand | cofactor | metal | additive


def _name_forms(text: str) -> Tuple[str, ...]:
    """The spellings one molecule goes by: `oxamate` is `OXAMIC ACID` in the PDB.

    Only the carboxylate/acid pair is folded, because it is the one naming
    difference that is purely a protonation state. Anything further (a
    stereoisomer, an ester) is a different molecule and is not matched.
    """
    t = text.strip().lower()
    forms = {t}
    if t.endswith("ate"):
        forms.add(t[:-3] + "ic acid")
    if t.endswith("ic acid"):
        forms.add(t[: -len("ic acid")] + "ate")
    return tuple(forms)


def matches(bound: "BoundMolecule", text: str) -> bool:
    forms = _name_forms(text)
    name = bound.name.lower()
    return bound.component.lower() in forms or any(f in name for f in forms)


@dataclass(frozen=True)
class Citation:
    title: Optional[str]
    journal: Optional[str]
    year: Optional[int]
    doi: Optional[str]
    pubmed: Optional[int]
    first_author: Optional[str]

    def short(self) -> str:
        who = f"{self.first_author} et al." if self.first_author else "unattributed"
        where = f" {self.journal}" if self.journal else ""
        link = f", doi:{self.doi}" if self.doi else (f", PMID {self.pubmed}" if self.pubmed else "")
        return f"{who} ({self.year or 'n.d.'}){where}{link}"


@dataclass(frozen=True)
class Structure:
    pdb_id: str
    title: str
    method: str
    resolution: Optional[float]
    organisms: Tuple[str, ...]
    uniprot: Tuple[str, ...]
    bound: Tuple[BoundMolecule, ...]
    citation: Citation

    @property
    def entry_doi(self) -> str:
        """Every PDB entry has its own DOI, whether or not a paper exists."""
        return f"10.2210/pdb{self.pdb_id.lower()}/pdb"

    @property
    def published(self) -> bool:
        journal = (self.citation.journal or "").strip().lower()
        return bool(self.citation.doi or self.citation.pubmed) and "to be published" not in journal

    def cite(self) -> str:
        """The paper when there is one; otherwise say so, and cite the entry.

        12 of human LDHA's 46 entries (2026-09-27) record "To Be Published"
        as their primary citation. Printing that as though it were a paper
        would be an uncited structure wearing a citation's clothes.
        """
        if self.published:
            return self.citation.short()
        who = f" ({self.citation.first_author} et al.)" if self.citation.first_author else ""
        return f"unpublished deposition{who}; entry doi:{self.entry_doi}"

    def with_role(self, role: str) -> Tuple[BoundMolecule, ...]:
        return tuple(b for b in self.bound if b.role == role)

    def binds(self, text: str) -> bool:
        """Does a non-additive component match `text` by id or name?"""
        return any(matches(b, text) for b in self.bound if b.role != "additive")


@dataclass(frozen=True)
class Protein:
    accession: str
    gene: Optional[str]
    name: str
    organism: str
    structures: Tuple[Structure, ...] = ()


@dataclass
class StructureSearch:
    ec: str
    organism: Optional[str]
    proteins: List[Protein] = field(default_factory=list)
    #: The protein the caller chose, or the only one with structures.
    chosen: Optional[Protein] = None
    #: Why no protein was chosen, when none was.
    undecided: Optional[str] = None
    ligand: Optional[str] = None

    def ranked(self) -> Tuple[Structure, ...]:
        """The chosen protein's structures, best evidence first.

        Ligand match first when a ligand was asked for (a pocket with the
        molecule in it answers a different question from an empty one),
        then method, then resolution. Resolution is a number a reader can
        check; "best" is not claimed beyond that ordering.
        """
        if self.chosen is None:
            return ()

        def key(s: Structure):
            wanted = 0 if (self.ligand and s.binds(self.ligand)) else 1
            return (wanted, METHOD_RANK.get(s.method, 3),
                    s.resolution if s.resolution is not None else 99.0, s.pdb_id)
        return tuple(sorted(self.chosen.structures, key=key))


@dataclass
class Http:
    """The two calls the search makes. Swapped for recorded data in tests."""
    get_json: Callable[[str, Dict[str, Any]], Any]
    post_json: Callable[[str, Dict[str, Any]], Any]


def live_http(timeout: float = 30.0) -> Http:
    import requests

    from caterva import netuse

    def reached(call: Callable[[], Any], url: str) -> Any:
        try:
            r = call()
        except (requests.ConnectionError, requests.Timeout) as exc:
            netuse.failed(url, exc)
            raise
        netuse.answered(url)
        return r

    def get_json(url: str, params: Dict[str, Any]) -> Any:
        r = reached(lambda: requests.get(url, params=params, timeout=timeout), url)
        r.raise_for_status()
        return r.json()

    def post_json(url: str, body: Dict[str, Any]) -> Any:
        r = reached(lambda: requests.post(url, json=body, timeout=timeout), url)
        if r.status_code == 204:  # RCSB: the query matched nothing
            return {}
        r.raise_for_status()
        return r.json()

    return Http(get_json, post_json)


class StructureSearchError(Exception):
    """The search could not be run, as distinct from finding nothing."""


def _role(component: str) -> str:
    c = component.upper()
    if c in ADDITIVES:
        return "additive"
    if c in COFACTORS:
        return "cofactor"
    if c in METALS:
        return "metal"
    return "ligand"


def _proteins(ec: str, organism: Optional[str], http: Http) -> List[Protein]:
    query = f"ec:{ec} AND reviewed:true"
    if organism:
        query += f' AND organism_name:"{organism}"'
    data = http.get_json(UNIPROT, {
        "query": query, "format": "json", "size": 50,
        "fields": "accession,protein_name,gene_primary,organism_name",
    })
    found = []
    for row in data.get("results", []):
        genes = row.get("genes") or [{}]
        name = (row.get("proteinDescription", {}).get("recommendedName", {})
                .get("fullName", {}).get("value") or row["primaryAccession"])
        found.append(Protein(
            accession=row["primaryAccession"],
            gene=(genes[0].get("geneName") or {}).get("value"),
            name=name,
            organism=row.get("organism", {}).get("scientificName", organism or ""),
        ))
    return found


_ENTRY_QUERY = """query($ids:[String!]!){entries(entry_ids:$ids){rcsb_id
 struct{title} exptl{method} rcsb_entry_info{resolution_combined}
 rcsb_primary_citation{title year pdbx_database_id_DOI pdbx_database_id_PubMed
   rcsb_authors journal_abbrev}
 nonpolymer_entities{nonpolymer_comp{chem_comp{id name}}}
 polymer_entities{rcsb_polymer_entity_container_identifiers{uniprot_ids}
   rcsb_entity_source_organism{scientific_name}}}}"""


def _entries_for(accessions: Sequence[str], http: Http) -> List[Dict[str, Any]]:
    hits = http.post_json(RCSB_SEARCH, {
        "query": {"type": "terminal", "service": "text", "parameters": {
            "attribute": "rcsb_polymer_entity_container_identifiers."
                         "reference_sequence_identifiers.database_accession",
            "operator": "in", "value": list(accessions)}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": 500}},
    })
    ids = [h["identifier"] for h in (hits or {}).get("result_set", [])]
    entries: List[Dict[str, Any]] = []
    for start in range(0, len(ids), 100):
        batch = http.post_json(RCSB_GRAPHQL, {
            "query": _ENTRY_QUERY, "variables": {"ids": ids[start:start + 100]}})
        entries.extend((batch.get("data") or {}).get("entries") or [])
    return entries


def _structure(entry: Dict[str, Any]) -> Structure:
    info = entry.get("rcsb_entry_info") or {}
    res = info.get("resolution_combined") or []
    pc = entry.get("rcsb_primary_citation") or {}
    authors = pc.get("rcsb_authors") or []
    bound = []
    for ent in entry.get("nonpolymer_entities") or []:
        comp = ((ent or {}).get("nonpolymer_comp") or {}).get("chem_comp") or {}
        if comp.get("id"):
            bound.append(BoundMolecule(comp["id"], (comp.get("name") or "").strip(),
                                       _role(comp["id"])))
    uniprot, organisms = set(), set()
    for poly in entry.get("polymer_entities") or []:
        ids = (poly.get("rcsb_polymer_entity_container_identifiers") or {}).get("uniprot_ids") or []
        uniprot.update(ids)
        for src in poly.get("rcsb_entity_source_organism") or []:
            if src.get("scientific_name"):
                organisms.add(src["scientific_name"])
    pubmed = pc.get("pdbx_database_id_PubMed")
    return Structure(
        pdb_id=entry["rcsb_id"],
        title=((entry.get("struct") or {}).get("title") or "").strip(),
        method=((entry.get("exptl") or [{}])[0].get("method") or "UNKNOWN"),
        resolution=float(res[0]) if res else None,
        organisms=tuple(sorted(organisms)),
        uniprot=tuple(sorted(uniprot)),
        bound=tuple(sorted(set(bound), key=lambda b: (b.role, b.component))),
        citation=Citation(
            title=pc.get("title"), journal=pc.get("journal_abbrev"),
            year=pc.get("year"), doi=pc.get("pdbx_database_id_DOI"),
            pubmed=int(pubmed) if pubmed else None,
            first_author=authors[0].split(",")[0].strip() if authors else None,
        ),
    )


def find_structures(
    ec: str,
    *,
    organism: Optional[str] = None,
    gene: Optional[str] = None,
    uniprot: Optional[str] = None,
    ligand: Optional[str] = None,
    http: Optional[Http] = None,
) -> StructureSearch:
    """Every experimental structure of this enzyme, grouped by protein."""
    http = http or live_http()
    search = StructureSearch(ec=ec, organism=organism, ligand=ligand)
    try:
        proteins = _proteins(ec, organism, http)
        if not proteins:
            search.undecided = (
                f"UniProt has no reviewed protein with EC {ec}"
                + (f" in {organism}" if organism else "")
                + ". Check the EC number, or drop --organism to search every organism."
            )
            return search
        entries = _entries_for([p.accession for p in proteins], http)
    except StructureSearchError:
        raise
    except Exception as exc:  # noqa: BLE001 - a network failure is a refusal with a reason
        raise StructureSearchError(f"the structure search could not run: {type(exc).__name__}: {exc}") from exc

    structures = [_structure(e) for e in entries]
    grouped = []
    for p in proteins:
        mine = tuple(s for s in structures if p.accession in s.uniprot)
        grouped.append(Protein(p.accession, p.gene, p.name, p.organism, mine))
    grouped.sort(key=lambda p: (-len(p.structures), p.gene or p.accession))
    search.proteins = grouped

    if uniprot or gene:
        want = (uniprot or gene or "").upper()
        match = [p for p in grouped if p.accession.upper() == want or (p.gene or "").upper() == want]
        if not match:
            search.undecided = (
                f"{uniprot or gene!r} is not one of the proteins with EC {ec}"
                + (f" in {organism}" if organism else "") + ": "
                + ", ".join(f"{p.gene or '?'} ({p.accession})" for p in grouped) + "."
            )
            return search
        search.chosen = match[0]
    else:
        with_structures = [p for p in grouped if p.structures]
        if len(with_structures) == 1:
            search.chosen = with_structures[0]
        elif not with_structures:
            search.undecided = (
                f"none of the {len(grouped)} protein(s) with EC {ec}"
                + (f" in {organism}" if organism else "")
                + " has an experimental structure in the PDB."
            )
        else:
            search.undecided = (
                f"EC {ec}" + (f" in {organism}" if organism else "")
                + f" is {len(with_structures)} different proteins with structures, and "
                "a structure belongs to one of them. Choose with --gene or --uniprot: "
                + ", ".join(f"{p.gene or '?'} ({p.accession}, {len(p.structures)} entries)"
                            for p in with_structures) + "."
            )
    return search


__all__ = [
    "ADDITIVES", "COFACTORS", "METALS", "BoundMolecule", "matches", "Citation", "Http",
    "Protein", "Structure", "StructureSearch", "StructureSearchError",
    "find_structures", "live_http",
]
