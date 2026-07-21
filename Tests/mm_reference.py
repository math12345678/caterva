import httpx

def search_pubmed(query, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    r = httpx.get(url, params=params)
    ids = r.json()["esearchresult"]["idlist"]
    if not ids:
        return []
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    fetch_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    r2 = httpx.get(fetch_url, params=fetch_params)
    result = r2.json()["result"]
    return [(uid, result[uid]["title"]) for uid in result.get("uids", [])]

enzymes = ["hexokinase", "chymotrypsin", "lactate dehydrogenase", "acetylcholinesterase"]

for enzyme in enzymes:
    print(f"=== {enzyme} Km Vmax ===")
    for uid, title in search_pubmed(f"{enzyme} Km Vmax kinetics"):
        print(f"  PMID {uid}: {title}")
    print()
