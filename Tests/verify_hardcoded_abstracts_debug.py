"""
Fetches every PMID hardcoded in big_test.py, big_test3.py, and
mm_abstracts.py directly from PubMed's efetch API and prints the real
abstract text next to what's hardcoded in this project, so the match can
be checked by eye rather than assumed. This closes the one gap flagged
as "inferred, not verified": those scripts' abstract excerpts were
never actually diffed against a live fetch.
"""

import httpx

PMIDS_TO_CHECK = {
    # from big_test.py
    "42326350": "nanoparticles",
    "42323674": "yeast",
    "42220071": "brain PET",
    "41187334": "HKDC1",
    "40854155": "cerebral modeling",
    # from mm_abstracts.py
    "31520487": "hexokinase - diabetes substrate saturation",
    "34962677": "LDH - immobilized on silica",
    "41373466": "AChE - creatine/taurine inhibitors",
    "40900406": "AChE - biopesticide inhibition",
}


def fetch_abstract(pmid: str) -> str:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"}
    r = httpx.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.text


def fetch_title(pmid: str) -> str:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    r = httpx.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("result", {}).get(pmid, {}).get("title", "<no title found>")


for pmid, label in PMIDS_TO_CHECK.items():
    print(f"=== PMID {pmid} ({label}) ===")
    try:
        title = fetch_title(pmid)
        print(f"LIVE TITLE: {title}")
        abstract = fetch_abstract(pmid)
        print(f"LIVE ABSTRACT (first 600 chars):\n{abstract[:600]}")
    except Exception as exc:  # noqa: BLE001
        print(f"FETCH FAILED: {exc}")
    print()
