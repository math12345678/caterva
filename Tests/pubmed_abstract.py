import httpx

def search_pubmed(query, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    r = httpx.get(url, params=params)
    return r.json()["esearchresult"]["idlist"]

def fetch_abstract(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"}
    r = httpx.get(url, params=params)
    return r.text

ids = search_pubmed("hexokinase Km kinetics")
print("PMIDs found:", ids)
print("\n--- Fetching abstract for each ---\n")

for pmid in ids:
    print(f"=== PMID {pmid} ===")
    print(fetch_abstract(pmid))
    print("\n" + "="*60 + "\n")
