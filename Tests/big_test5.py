import httpx
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

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
    return [result[uid]["title"] for uid in result.get("uids", [])]

claim = "GROMACS simulations of protein-ligand binding typically require a minimum equilibration time of 5-10 nanoseconds before production runs"

# The 3 queries Test F actually generated last run
queries = [
    '("GROMACS" OR "molecular dynamics simulation") AND ("protein-ligand binding" OR "protein-ligand interaction") AND ("equilibration time" OR "simulation protocol")',
    '(protein-ligand binding OR docking) AND (molecular dynamics OR MD simulation) AND (equilibration OR convergence) AND (nanosecond OR timescale)',
    '("simulation protocol optimization" OR "molecular dynamics best practices") AND ("protein-ligand complex" OR "biomolecular interaction") AND (GROMACS OR "popular MD engines") AND (equilibration OR "pre-production run")',
]

all_titles = []
for i, q in enumerate(queries, 1):
    print(f"--- Query {i} ---")
    print(q)
    titles = search_pubmed(q)
    if not titles:
        print("  (no results)")
    for t in titles:
        print(" -", t)
        all_titles.append(t)
    print()

# Now judge: do any of these real, returned papers actually verify the claim's
# specific number (5-10 ns)?
if all_titles:
    prompt = f"""Claim: "{claim}"

Real paper titles found via search: {all_titles}

Based ONLY on these titles (no abstracts yet), which if any look genuinely promising for verifying the SPECIFIC claim (5-10 nanosecond equilibration time)? Be honest if none of the titles alone are conclusive - titles often aren't enough to verify a specific number.

Answer format:
PROMISING_TITLES: [list any, or "none - would need abstracts"]
ASSESSMENT: one sentence
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    print("=== TEST H: Does the full pipeline (generate query -> real search -> judge) actually work end to end? ===")
    print(response.choices[0].message.content)
else:
    print("=== TEST H RESULT: All 3 queries returned ZERO real papers ===")
    print("This would be an important negative result - overly complex boolean queries may return nothing on PubMed's actual search syntax.")
