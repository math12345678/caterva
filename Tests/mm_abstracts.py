# The 4 PMIDs/labels below re-verified live 2026-07 via
# verify_hardcoded_abstracts_debug.py: real papers, titles match labels
# (31520487 hexokinase/diabetes, 34962677 LDH/silica, 41373466
# AChE/creatine-taurine, 40900406 AChE/biopesticide).
import httpx

def fetch_abstract(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"}
    r = httpx.get(url, params=params)
    return r.text

candidates = {
    "31520487": "hexokinase - diabetes substrate saturation",
    "34962677": "LDH - immobilized on silica",
    "41373466": "AChE - creatine/taurine inhibitors",
    "40900406": "AChE - biopesticide inhibition",
}

for pmid, label in candidates.items():
    print(f"=== PMID {pmid} ({label}) ===")
    print(fetch_abstract(pmid))
    print("\n" + "="*60 + "\n")
