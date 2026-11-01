#!/usr/bin/env python3
"""Build the gene-symbol table and the protein-name file the enzyme finder ships with.

WHY THIS EXISTS
---------------
The finder (caterva/enzymes/finder.py) reads the IUBMB nomenclature, which
has enzyme names and UniProt ENTRY NAMES, and entry names are mnemonics, not
gene symbols (ACES_HUMAN is ACHE; SYK_HUMAN is a lysine--tRNA ligase). People
type gene symbols and lab abbreviations. This script writes the two committed
files that bridge that, from UniProtKB and from the enzyme index itself:

* `caterva/enzymes/data/protein_names.json.gz`: for every protein the index
  lists for human, mouse, yeast and E. coli K-12, the gene symbol and the
  names UniProtKB gives it. Read once, here, through the EBI Proteins API
  (https://www.ebi.ac.uk/proteins/api), which serves UniProtKB.
* `caterva/enzymes/data/symbols.json`: a SMALL curated table (symbols.py
  explains it). Gene rows are built by finding each seed symbol among those
  proteins' gene names, so a symbol is only ever attached to a reviewed entry
  that UniProt itself gives that gene name, and the EC numbers are the ones
  that entry's recommended name carries (or, if it carries none, the ones the
  enzyme index lists the entry under). Abbreviation rows are written below by
  hand, each with the basis for it; the build checks every claim it can
  (the EC exists and is active, the cited alternative name is listed under
  that EC, the cited accession has that EC in UniProtKB).

USAGE
-----
    python scripts/build_enzyme_symbols.py                  # fetch UniProtKB, then build
    python scripts/build_enzyme_symbols.py --cache c.json   # read/write the fetched names here

`make enzyme-symbols` runs the first form. Like `make enzyme-index` it is run
by a person refreshing the data, never by a test or by the application. The
output is deterministic for one UniProtKB state: sorted keys, a zeroed gzip
timestamp. The date UniProtKB was read is inside the files.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from caterva.enzymes.index import ACTIVE, load_index  # noqa: E402

DATA = REPO / "caterva" / "enzymes" / "data"
API = "https://www.ebi.ac.uk/proteins/api/proteins"
#: The organisms the file covers; the codes are the index's.
ORGANISMS = ("HUMAN", "MOUSE", "YEAST", "ECOLI")
MAX_ALTERNATIVE_NAME = 60

#: Gene symbols to look for among those proteins (human spelling; the mouse,
#: yeast and E. coli spelling is found by comparing without case).
GENE_SEEDS = """
HK1 HK2 HK3 GCK HKDC1 GPI PFKM PFKL PFKP ALDOA ALDOB ALDOC TPI1 GAPDH GAPDHS PGK1 PGK2 PGAM1 PGAM2 ENO1 ENO2 ENO3
PKM PKLR LDHA LDHB LDHC LDHD LDHAL6A LDHAL6B PDHA1 PDHB DLAT DLD CS ACO1 ACO2 IDH1 IDH2 IDH3A OGDH SUCLG1 SUCLA2
SDHA SDHB FH MDH1 MDH2 ACLY G6PD PGLS PGD TKT TALDO1 RPE RPIA FBP1 FBP2 PCK1 PCK2 GYS1 GYS2 PYGL PYGM PYGB PGM1
UGP2 GBE1 ACHE BCHE DHFR TYMS HMGCR MAOA MAOB CA1 CA2 CA3 CA4 CA5A CA5B CA6 CA7 CA9 CA12 CA13 CA14 SOD1 SOD2 SOD3
CAT GPX1 GSR NOS1 NOS2 NOS3 ACE ACE2 DPP4 PDE4A PDE4B PDE4C PDE4D PDE5A CYP3A4 CYP2C9 CYP2D6 CYP1A2 CYP2C19 CYP2E1
COMT PARP1 CDK2 CDK1 EGFR ABL1 SRC SYK BTK JAK2 MAPK1 MAPK3 PIK3CA HDAC1 HDAC2 HDAC3 HDAC4 HDAC5 HDAC6 HDAC7 HDAC8
BACE1 CASP3 CASP1 F2 F10 PTPN1 GSTP1 GSTA1 GSTM1 GSTT1 MMP9 MMP2 AKT1 MTOR IDO1 ARG1 ARG2 ODC1 ADA PNP PRSS1 CTSB
CTSL LYZ ELANE REN DNMT1 PTGS1 PTGS2 ALDH1A1 ALDH2 ADH1A ADH1B ADH1C ADH4 ADH5 ADH6 ADH7 ALPL ASS1 GLS GLUD1 PRKACA
PRKCA AMY2A GAA
ADH1 ADH2 CDC19 PYK2 HXK1 HXK2 GLK1 PFK1 PFK2 FBA1 TDH1 TDH2 TDH3 GPM1 CIT1 CIT2 ZWF1 CTT1 DFR1 CDC21 HMG1 HMG2 PDC1
gapA pykF pykA pfkA pfkB glk fbaA tpiA pgk eno gltA mdh icd zwf sodA sodB katE katG folA thyA lacZ ldhA ppc
""".split()

#: Other spellings of a gene symbol, from UniProtKB's own names for the entry
#: where it has one (checked below) or the common way people write it.
#: symbol -> (aliases, basis). Aliases that are the symbol itself in another
#: case or punctuation need no entry: symbols are compared without either.
GENE_ALIASES: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "PKM": (("PKM1", "PKM2", "PK-M1", "PK-M2", "M2-PK", "PKM-2"), "UniProtKB P14618 names PKM2 and Tumor M2-PK; PKM1 and PKM2 are its two splice forms"),
    "DPP4": (("DPP-IV", "DPP IV", "DPP-4", "CD26"), "UniProtKB P27487 short name DPP IV, alternative name T-cell activation antigen CD26"),
    "PTPN1": (("PTP1B", "PTP-1B"), "UniProtKB P18031 short name PTP-1B"),
    "ALDOA": (("aldolase A",), "UniProtKB P04075 'Fructose-bisphosphate aldolase A', also known as aldolase A"),
    "ALDOB": (("aldolase B",), "UniProtKB P05062 'Fructose-bisphosphate aldolase B', also known as aldolase B"),
    "ALDOC": (("aldolase C",), "UniProtKB P09972 'Fructose-bisphosphate aldolase C', also known as aldolase C"),
    "ACHE": (("AChE",), "common abbreviation of acetylcholinesterase"),
    "BCHE": (("BuChE", "BChE"), "common abbreviations of butyrylcholinesterase"),
    "MTOR": (("mTOR", "FRAP1"), "UniProtKB P42345 'Serine/threonine-protein kinase mTOR'; the mammalian target of rapamycin"),
    "TYMS": (("TS",), "common abbreviation of thymidylate synthase"),
    "F2": (("THR", "thrombin"), "UniProtKB P00734 'Prothrombin' is cleaved to thrombin (EC 3.4.21.5); THR is the abbreviation used for it"),
    "F10": (("FXa", "factor Xa", "factor X"), "UniProtKB P00742 'Coagulation factor X'; its active form is factor Xa (EC 3.4.21.6)"),
    "CASP3": (("caspase 3",), "UniProtKB P42574 'Caspase-3'"),
    "SRC": (("c-Src", "Src"), "UniProtKB P12931 'Proto-oncogene tyrosine-protein kinase Src'"),
    "ABL1": (("c-Abl", "Abl"), "UniProtKB P00519 'Tyrosine-protein kinase ABL1'"),
    "PRKACA": (("PKA",), "UniProtKB P17612 'cAMP-dependent protein kinase catalytic subunit alpha'; PKA is cAMP-dependent protein kinase"),
    "PRKCA": (("PKC-alpha", "PKCa"), "UniProtKB P17252 'Protein kinase C alpha type'"),
    "GAPDHS": (("GAPDH2", "GAPDS"), "UniProtKB O14556 'Glyceraldehyde-3-phosphate dehydrogenase, testis-specific'"),
    "G6PD": (("G6PDH", "G-6-PD"), "UniProtKB P11413 'Glucose-6-phosphate 1-dehydrogenase'"),
    "LDHAL6A": (("LDH6A",), "the entry-name stem of the UniProtKB entry (LDH6A_HUMAN)"),
    "LDHAL6B": (("LDH6B",), "the entry-name stem of the UniProtKB entry (LDH6B_HUMAN)"),
}

#: Activities UniProt lists on many entries besides the enzyme's own.
GENERIC_ACTIVITIES = ("2.7.11.1", "2.7.10.2")

#: Roman-numeral forms people write for the carbonic anhydrases.
_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5A": "VA", "5B": "VB", "6": "VI", "7": "VII", "9": "IX",
          "12": "XII", "13": "XIII", "14": "XIV"}

#: Lab abbreviations and names written another way, independent of organism.
#: (symbols, ecs, what they mean, basis). `basis` is "name" (the abbreviation is the initialism of
#: the accepted name or a common name for it), or "alt:<name>" (the enzyme index lists <name> as
#: another name of the first EC; the build checks it), or "uniprot:<accession>" (that reviewed entry
#: carries the first EC and is the protein people mean; the build checks it).
ABBREVIATIONS: List[Tuple[Tuple[str, ...], Tuple[str, ...], str, str]] = [
    (("PK",), ("2.7.1.40",), "pyruvate kinase", "name"),
    (("CK", "CPK"), ("2.7.3.2",), "creatine kinase", "name"),
    (("HK",), ("2.7.1.1", "2.7.13.3"), "hexokinase and histidine kinase", "name"),
    (("PFK",), ("2.7.1.11",), "6-phosphofructokinase", "name"),
    (("LDH",), ("1.1.1.27", "1.1.1.28"), "L-lactate dehydrogenase and D-lactate dehydrogenase", "name"),
    (("MDH",), ("1.1.1.37", "1.1.1.82"), "malate dehydrogenase (NAD(+)) and (NADP(+))", "name"),
    (("ADH",), ("1.1.1.1", "1.1.1.2"), "alcohol dehydrogenase (NAD(+)) and (NADP(+))", "name"),
    (("ALDH",), ("1.2.1.3", "1.2.1.4", "1.2.1.5"), "aldehyde dehydrogenase", "name"),
    (("COX",), ("7.1.1.9", "1.14.99.1"), "cytochrome-c oxidase and, as COX-1 and COX-2, cyclooxygenase", "name"),
    (("cyclooxygenase", "COX-1", "COX-2", "COX1", "COX2"), ("1.14.99.1",),
     "prostaglandin-endoperoxide synthase (cyclooxygenase)", "uniprot:P35354"),
    (("SOD",), ("1.15.1.1",), "superoxide dismutase", "name"),
    (("CAT",), ("1.11.1.6", "2.3.1.28"), "catalase and chloramphenicol acetyltransferase", "name"),
    (("AK",), ("2.7.4.3", "2.7.1.20"), "adenylate kinase and adenosine kinase", "name"),
    (("PEPC", "PEPCase"), ("4.1.1.31",), "phosphoenolpyruvate carboxylase", "name"),
    (("SDH",), ("1.3.5.1", "1.1.1.14"), "succinate dehydrogenase and sorbitol (L-iditol) dehydrogenase", "name"),
    (("NOS",), ("1.14.13.39", "1.14.14.47"), "nitric-oxide synthase", "alt:NO synthase"),
    (("AST", "GOT"), ("2.6.1.1",), "aspartate transaminase (aspartate aminotransferase)", "name"),
    (("ALT", "GPT"), ("2.6.1.2",), "alanine transaminase (alanine aminotransferase)", "name"),
    (("GPI", "PGI"), ("5.3.1.9",), "glucose-6-phosphate isomerase", "name"),
    (("TPI",), ("5.3.1.1",), "triose-phosphate isomerase", "name"),
    (("PGK",), ("2.7.2.3",), "phosphoglycerate kinase", "name"),
    (("PGM",), ("5.4.2.2", "5.4.2.11", "5.4.2.12"), "phosphoglucomutase and phosphoglycerate mutase", "name"),
    (("ENO",), ("4.2.1.11",), "phosphopyruvate hydratase (enolase)", "name"),
    (("FBPase", "FBP"), ("3.1.3.11",), "fructose-bisphosphatase", "name"),
    (("FBA",), ("4.1.2.13",), "fructose-bisphosphate aldolase", "name"),
    (("PEPCK",), ("4.1.1.32", "4.1.1.49"), "phosphoenolpyruvate carboxykinase (GTP) and (ATP)", "name"),
    (("G6Pase",), ("3.1.3.9",), "glucose-6-phosphatase", "name"),
    (("PDH", "PDC"), ("1.2.4.1",), "pyruvate dehydrogenase (acetyl-transferring)", "name"),
    (("CS",), ("2.3.3.1",), "citrate (Si)-synthase", "name"),
    (("IDH",), ("1.1.1.42", "1.1.1.41"), "isocitrate dehydrogenase (NADP(+)) and (NAD(+))", "name"),
    (("GAPDH",), ("1.2.1.12",), "glyceraldehyde-3-phosphate dehydrogenase (phosphorylating)", "alt:GAPDH"),
    (("ACE",), ("3.4.15.1",), "angiotensin-converting enzyme (peptidyl-dipeptidase A)", "alt:ACE"),
    (("PKA",), ("2.7.11.11",), "cAMP-dependent protein kinase", "alt:PKA"),
    (("PKC",), ("2.7.11.13",), "protein kinase C", "alt:PKC"),
    (("HDAC",), ("3.5.1.98",), "histone deacetylase", "alt:HDAC"),
    (("BACE1", "BACE"), ("3.4.23.46",), "beta-secretase 1 (memapsin 2)", "alt:BACE1"),
    (("PARP", "PARP1", "PARP-1", "poly(ADP-ribose) polymerase", "poly(ADP-ribose) polymerase 1"), ("2.4.2.30",),
     "poly(ADP-ribose) polymerase 1", "uniprot:P09874"),
    (("HK1", "HK2", "HK3"), ("2.7.1.1",), "hexokinase 1, 2 or 3 (a mammalian hexokinase isozyme)", "name"),
    (("angiotensin converting enzyme", "angiotensin-converting enzyme", "ACE1"), ("3.4.15.1",),
     "angiotensin-converting enzyme (peptidyl-dipeptidase A)", "uniprot:P12821"),
    (("COMT",), ("2.1.1.6",), "catechol O-methyltransferase", "name"),
    (("DHFR",), ("1.5.1.3",), "dihydrofolate reductase", "name"),
    (("TS",), ("2.1.1.45",), "thymidylate synthase", "name"),
    (("HMG-CoA reductase", "HMGR"), ("1.1.1.34", "1.1.1.88"),
     "hydroxymethylglutaryl-CoA reductase (NADPH) and (NAD(+))", "name"),
    (("AChE",), ("3.1.1.7",), "acetylcholinesterase", "name"),
    (("BChE", "BuChE"), ("3.1.1.8",), "cholinesterase (butyrylcholinesterase)", "name"),
    (("MAO",), ("1.4.3.4",), "monoamine oxidase", "name"),
    (("CA",), ("4.2.1.1",), "carbonic anhydrase", "name"),
    (("PDE4",), ("3.1.4.53",), "cAMP-specific 3',5'-cyclic phosphodiesterase", "name"),
    (("PDE5",), ("3.1.4.35",), "3',5'-cyclic-GMP phosphodiesterase", "name"),
    (("HIV protease", "HIV-1 protease", "HIV PR", "HIV-1 PR", "HIV-1 retropepsin"), ("3.4.23.16",),
     "HIV-1 retropepsin", "alt:human immunodeficiency virus type 1 protease"),
    (("T4 lysozyme", "T4L", "phage T4 lysozyme"), ("3.2.1.17",), "lysozyme of bacteriophage T4", "uniprot:P00720"),
    (("HEWL", "hen egg white lysozyme", "hen egg-white lysozyme"), ("3.2.1.17",), "hen egg-white lysozyme",
     "uniprot:P00698"),
    (("Taq", "Taq polymerase", "Taq DNA polymerase"), ("2.7.7.7",), "Thermus aquaticus DNA polymerase I",
     "uniprot:P19821"),
    (("DNA polymerase I", "Pol I", "Klenow fragment", "Klenow"), ("2.7.7.7",), "DNA polymerase I",
     "uniprot:P00582"),
    (("HRP", "horseradish peroxidase"), ("1.11.1.7",), "horseradish peroxidase", "uniprot:P00433"),
    (("GST", "glutathione S-transferase"), ("2.5.1.18",), "glutathione transferase", "name"),
    (("RNase A", "ribonuclease A", "bovine pancreatic ribonuclease"), ("4.6.1.18",), "pancreatic ribonuclease",
     "alt:RNase A"),
    (("lacZ",), ("3.2.1.23",), "beta-galactosidase (the lacZ gene product)", "uniprot:P00722"),
    (("ALP",), ("3.1.3.1",), "alkaline phosphatase", "name"),
    (("XO",), ("1.17.3.2",), "xanthine oxidase", "name"),
    (("ODC",), ("4.1.1.17",), "ornithine decarboxylase", "name"),
    (("ATCase",), ("2.1.3.2",), "aspartate carbamoyltransferase", "alt:ATCase"),
    (("RuBisCO",), ("4.1.1.39",), "ribulose-bisphosphate carboxylase", "alt:RuBisCO"),
    (("PNP",), ("2.4.2.1",), "purine-nucleoside phosphorylase", "name"),
    (("ADA",), ("3.5.4.4",), "adenosine deaminase", "name"),
    (("PLA2",), ("3.1.1.4",), "phospholipase A2", "name"),
]


def _get(url: str, retries: int = 6) -> object:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - fixed https URL above
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
            time.sleep(2 + 2 * attempt)
    raise SystemExit(f"UniProtKB (EBI Proteins API) did not answer {url[:120]}: {last}")


def _record(entry: Dict[str, object]) -> Dict[str, object]:
    protein = entry["protein"]  # type: ignore[index]
    recommended = protein.get("recommendedName") or {}  # type: ignore[union-attr]
    submitted = protein.get("submittedName") or []  # type: ignore[union-attr]
    name = (recommended.get("fullName") or (submitted[0].get("fullName") if submitted else {}) or {}).get("value")
    genes = entry.get("gene") or []
    return {
        "id": entry["id"],
        "genes": [g["name"]["value"] for g in genes if g.get("name")],  # type: ignore[union-attr]
        "syn": [s["value"] for g in genes for s in g.get("synonyms", [])],  # type: ignore[union-attr]
        "name": name,
        "short": [s["value"] for s in recommended.get("shortName", [])],
        "alt": [a["fullName"]["value"] for a in protein.get("alternativeName", []) if a.get("fullName")],  # type: ignore[union-attr]
        "altshort": [s["value"] for a in protein.get("alternativeName", []) for s in a.get("shortName", [])],  # type: ignore[union-attr]
        "ec": [x["value"] for x in recommended.get("ecNumber", [])],
    }


def fetch(accessions: Sequence[str], chunk_size: int = 100) -> Dict[str, Dict[str, object]]:
    chunks = [list(accessions[i:i + chunk_size]) for i in range(0, len(accessions), chunk_size)]

    def one(chunk: List[str]) -> Dict[str, Dict[str, object]]:
        url = API + "?" + urllib.parse.urlencode({"accession": ",".join(chunk), "size": 100})
        return {e["accession"]: _record(e) for e in _get(url)}  # type: ignore[union-attr]

    out: Dict[str, Dict[str, object]] = {}
    with ThreadPoolExecutor(5) as pool:
        for part in pool.map(one, chunks):
            out.update(part)
    return out


def _extras() -> List[str]:
    return sorted({b.split(":", 1)[1] for *_x, b in ABBREVIATIONS if b.startswith("uniprot:")})


_NUMBERED = re.compile(r"(?:\s|-)(?:[IVX]{1,4}|\d{1,2}[A-Za-z]?|[A-Z])$")


def _numbered_names(records: Sequence[Dict[str, object]]) -> List[str]:
    """Names UniProtKB gives these entries that end in an isozyme number or letter
    ("Hexokinase-2", "Hexokinase type II", "Carbonic anhydrase II"): the forms papers
    write, which are what a person types for one isozyme."""
    out: List[str] = []
    for rec in records:
        stem = re.match(r"[A-Za-z]+", str(rec["name"] or ""))
        for name in [rec["name"], *rec["alt"]]:  # type: ignore[misc]
            # Only names of the same protein family as the recommended name: its first word.
            same_family = stem and re.match(r"[A-Za-z]+", name or "") and \
                re.match(r"[A-Za-z]+", name).group().lower() == stem.group().lower()  # type: ignore[union-attr]
            if name and same_family and len(name) <= 45 and _NUMBERED.search(name) and name not in out:
                out.append(name)
    return out


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.lower())


def names_file(records: Dict[str, Dict[str, object]], today: str) -> Dict[str, object]:
    entries: Dict[str, object] = {}
    for accession in sorted(records):
        rec = records[accession]
        gene = (rec["genes"] or [None])[0]  # type: ignore[index]
        others: List[str] = []
        for text in [*rec["syn"], *rec["short"], *rec["altshort"],  # type: ignore[misc]
                     *[a for a in rec["alt"] if len(a) <= MAX_ALTERNATIVE_NAME]]:  # type: ignore[union-attr]
            if text and text != gene and text not in others:
                others.append(text)
        entries[accession] = [gene, rec["name"] or "", others]
    return {
        "format": 1,
        "source": "UniProtKB, read through the EBI Proteins API (https://www.ebi.ac.uk/proteins/api)",
        "licence": "CC BY 4.0 (UniProt)",
        "fetched": today,
        "organisms": list(ORGANISMS),
        "entries": entries,
    }


def symbols_file(records: Dict[str, Dict[str, object]], extras: Dict[str, Dict[str, object]], today: str) -> Dict[str, object]:
    index = load_index()
    # (organism, compact gene symbol) -> accessions
    by_gene: Dict[Tuple[str, str], List[str]] = {}
    for accession, rec in sorted(records.items()):
        organism = str(rec["id"]).rpartition("_")[2]
        for gene in rec["genes"]:  # type: ignore[union-attr]
            by_gene.setdefault((organism, _compact(gene)), []).append(accession)
    listed_under: Dict[str, List[str]] = {}
    for ec, entry in index.entries.items():
        if entry.status != ACTIVE:
            continue
        for proteins in entry.proteins.values():
            for protein in proteins:
                listed_under.setdefault(protein.accession, []).append(ec)

    def active(ec: str) -> bool:
        item = index.get(ec)
        return item is not None and item.status == ACTIVE

    genes: Dict[str, Dict[str, object]] = {}
    for seed in GENE_SEEDS:
        key = _compact(seed)
        by_org: Dict[str, Dict[str, object]] = {}
        sources: List[str] = []
        label = None
        for organism in ORGANISMS:
            for accession in by_gene.get((organism, key), ()):
                rec = records[accession]
                ecs = [e for e in rec["ec"] if re.fullmatch(r"\d+\.\d+\.\d+\.n?\d+", e) and active(e)]  # type: ignore[union-attr]
                if not ecs:
                    ecs = sorted(listed_under.get(accession, ()))
                if not ecs:
                    continue
                # A generic protein-kinase activity UniProt adds to an enzyme's own comes last.
                ecs = sorted(ecs, key=lambda e: e in GENERIC_ACTIVITIES)
                if organism in by_org:
                    continue  # two entries with one gene name: keep the first, by accession
                gene_name = (rec["genes"] or [seed])[0]  # type: ignore[index]
                if organism == "HUMAN" or label is None:
                    label = gene_name
                by_org[organism] = {"accession": accession, "name": rec["name"] or "", "ecs": ecs}
                sources.append(f"{accession} ({rec['id']})")
        if not by_org:
            continue
        aliases, alias_basis = GENE_ALIASES.get(seed.upper(), ((), ""))
        if seed.upper().startswith("CA") and seed[2:].upper() in _ROMAN:
            roman = _ROMAN[seed[2:].upper()]
            aliases = (f"CA {roman}", f"CA-{roman}", f"carbonic anhydrase {roman}")
            alias_basis = f"the Roman-numeral name of carbonic anhydrase {seed[2:]}"
        named = _numbered_names([records[v["accession"]] for v in by_org.values()])  # type: ignore[index]
        if named:
            aliases = tuple(aliases) + tuple(n for n in named if n not in aliases)
            alias_basis = (alias_basis + "; " if alias_basis else "") + "the entry's own UniProtKB names ending in a number or letter"
        row = genes.setdefault(key, {"symbol": label or seed, "organisms": {}, "source": ""})
        row["organisms"].update(by_org)  # type: ignore[union-attr]
        row["source"] = "UniProtKB " + ", ".join(sources) + (f"; aliases: {alias_basis}" if aliases else "")
        if aliases:
            seen = {key}
            kept: List[str] = []
            for alias in aliases:
                if _compact(alias) not in seen:
                    seen.add(_compact(alias))
                    kept.append(alias)
            if kept:
                row["aliases"] = kept
    rows = [genes[k] for k in sorted(genes)]

    abbreviations: List[Dict[str, object]] = []
    for symbols, ecs, meaning, basis in ABBREVIATIONS:
        for ec in ecs:
            if not active(ec):
                raise SystemExit(f"{symbols}: EC {ec} is not an active EC number in the index")
        names = "; ".join(f"EC {ec} {index.get(ec).name}" for ec in ecs)  # type: ignore[union-attr]
        if basis == "name":
            why = "an abbreviation or common name of the accepted name"
        elif basis.startswith("alt:"):
            wanted = basis[4:]
            if wanted not in index.get(ecs[0]).alternative_names:  # type: ignore[union-attr]
                raise SystemExit(f"{symbols}: ENZYME does not list {wanted!r} as another name of EC {ecs[0]}")
            why = f"ENZYME lists '{wanted}' as another name of EC {ecs[0]}"
        else:
            accession = basis.split(":", 1)[1]
            record = extras.get(accession) or records.get(accession)
            if not record or ecs[0] not in record["ec"]:  # type: ignore[operator]
                raise SystemExit(f"{symbols}: UniProtKB {accession} does not carry EC {ecs[0]}")
            why = f"UniProtKB {accession} ({record['id']}), '{record['name']}', carries EC {ecs[0]}"
        abbreviations.append({
            "symbols": list(symbols), "ecs": list(ecs), "meaning": meaning,
            "source": f"{why}; accepted name in ExPASy ENZYME release {index.release}: {names}",
        })
    return {
        "format": 1,
        "fetched": today,
        "sources": {
            "uniprot": "UniProtKB reviewed entries, read through the EBI Proteins API. A gene row's source "
                       "names the entries; the EC numbers are those of each entry's recommended name or, "
                       "where it has none, those ENZYME lists the entry under",
            "enzyme": f"ExPASy ENZYME release {index.release} (IUBMB nomenclature), caterva/enzymes/data/enzyme_index.json.gz",
        },
        "genes": rows,
        "abbreviations": abbreviations,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", type=Path, help="a JSON file of fetched UniProtKB records (read if present, else written)")
    parser.add_argument("--today", default=None, help="the fetch date to record (default: today)")
    args = parser.parse_args(argv)

    index = load_index()
    accessions = sorted({p.accession for e in index.entries.values() for c in ORGANISMS for p in e.proteins.get(c, ())})
    extra_accessions = _extras()
    today = args.today or date.today().isoformat()
    if args.cache and args.cache.exists():
        cached = json.loads(args.cache.read_text(encoding="utf-8"))
        records, extras = cached["records"], cached["extras"]
        today = args.today or cached.get("fetched", today)
    else:
        records = fetch(accessions)
        extras = fetch(extra_accessions, 1)
        if args.cache:
            args.cache.write_text(json.dumps({"fetched": today, "records": records, "extras": extras}), encoding="utf-8")
    missing = [a for a in accessions if a not in records]
    print(f"{len(records)} of {len(accessions)} proteins read; {len(missing)} not answered")

    names = names_file(records, today)
    payload = json.dumps(names, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    (DATA / "protein_names.json.gz").write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    symbols = symbols_file(records, extras, today)
    (DATA / "symbols.json").write_text(
        json.dumps(symbols, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"protein_names.json.gz: {len(names['entries'])} entries, {len(payload):,} bytes before gzip")
    print(f"symbols.json: {len(symbols['genes'])} gene symbols, {len(symbols['abbreviations'])} abbreviation rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
