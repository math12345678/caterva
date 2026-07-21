"""
Full-text check for PMID 41187334, the one abstract in this project
whose hardcoded excerpt (in big_test2.py / big_test3.py) quotes specific
numbers - kcat/Km = 1.5 x 10^4 M-1 s-1, Km = 0.49 +/- 0.07 mM, G6P
inhibition constant above 1 mM. The earlier check only fetched the first
600 characters (which showed the title and opening sentence matched);
this fetches the FULL abstract so those specific numbers can be checked
against the real source instead of assumed correct because the opening
matched.
"""

import httpx

r = httpx.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
    params={"db": "pubmed", "id": "41187334", "rettype": "abstract", "retmode": "text"},
    timeout=15,
)
r.raise_for_status()
print(r.text)
