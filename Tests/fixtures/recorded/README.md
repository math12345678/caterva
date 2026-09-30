# Recorded answers from BRENDA, NCBI, UniProt and PubChem

Real responses, fetched from the services and stored unmodified (gzipped),
so that tests which exercise the whole literature path do not fail when a
database is slow or down. They are read only when the API server's test
configuration (`Science-Agent-Pipeline/artifacts/api-server/vitest.config.ts`)
or a test names this directory. Nothing else sets the variables, and
`Tests/test_recorded_env_is_test_only.py` fails if anything outside test
configuration does: the product always fetches live, because a recorded
answer served to a user would be presented as the database's current one.

Two layers, one policy: a request with a recording is answered from it; a
request with none goes live exactly as it would without this directory.

## BRENDA pages (`CATERVA_BRENDA_RECORDED`)

Read by `Tests/brenda_client.py` `fetch_brenda_html` when
`CATERVA_BRENDA_RECORDED` names this directory.

| file | source | fetched | sha256 of the uncompressed page |
|---|---|---|---|
| brenda_2.7.1.1.html.gz | https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1 | 2026-09-28 | 3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91 |

Recorded after BRENDA returned HTTP 500 for this page in three CI runs on
2026-09-28 (five hexokinase tests failed on an outage, not a defect). BRENDA
data are licensed CC BY 4.0; cite BRENDA (Chang et al. 2021, Nucleic Acids
Res. 49:D498, doi:10.1093/nar/gkaa1025) with any value taken from them.
To refresh: fetch the URL again, gzip it here, update the hash and date.

Every API-test payload is hexokinase, EC 2.7.1.1, or has no EC number at
all, so this one page is the only BRENDA page the API tests read. The
recorder below refuses to finish if a payload fetched any BRENDA page live.

## Everything else the runner asks (`CATERVA_HTTP_RECORDED`, `http/`)

Read by `Tests/http_retry.py` `retry_get`, the one function every other
literature-layer GET goes through, when `CATERVA_HTTP_RECORDED` names
`http/`. One human hexokinase Km lookup makes 15 distinct requests of three
services (recorded 2026-09-30 UTC): two NCBI Taxonomy esearches (the
organism, and "lymphocytes" read from a row's commentary), one UniProt
search for the accession, and twelve PubChem name-to-CID and parent-CID
lookups for the compounds and names in the rows' commentary. Those tests timed out in CI whenever
NCBI or PubChem was slow.

| service | host | what is recorded | licence |
|---|---|---|---|
| NCBI Taxonomy | eutils.ncbi.nlm.nih.gov | esearch for Homo sapiens, Escherichia coli, Saccharomyces cerevisiae (`[Scientific Name]`) and "lymphocytes" | US Government work, public domain within the US |
| UniProt | rest.uniprot.org | the reviewed accession for EC 2.7.1.1 in taxa 9606, 562 and 4932; name searches for "hexokinase" and for the eight non-enzyme names the tests send, each answered with no results | CC BY 4.0 (https://www.uniprot.org/help/license); cite The UniProt Consortium, Nucleic Acids Res. 53:D609 (2025), doi:10.1093/nar/gkae1010 |
| PubChem | pubchem.ncbi.nlm.nih.gov | name-to-CID for 13 names (eight of them 404, "No CID found") and parent-CID for 5 CIDs (one 404) | public domain within the US; NOTICE |

42 files, 15,672 bytes, all fetched 2026-09-30 (UTC); UniProt release
2026_03 was current. The per-file detail is in the files themselves.

**Format.** One gzipped JSON file per request, named by the sha256 of the
request's key: the method, the URL, the query parameters as httpx sends
them, sorted, every request header except `User-Agent`, `Accept-Encoding`
and `Connection`, and whether redirects were followed. The file holds that
key, the fetch date, the status, the content-type, the final URL and the
body. On replay the stored key must equal the computed one, or the file is
ignored. gzip's timestamp is zeroed, so re-recording an unchanged answer
changes no bytes.

**What is never recorded.** A request that carries a credential is neither
written here nor answered from here: an NCBI `api_key` parameter (attached
when `NCBI_API_KEY` is set), CORE's `Authorization: Bearer` header, or any
other key, token, cookie or password (`CREDENTIAL_PARAMS` and
`CREDENTIAL_HEADERS` in `http_retry.py`). So a developer who runs the API
tests with `NCBI_API_KEY` set gets live NCBI calls, by design: a request
that carries a key is a different request, and the key must not reach a
file in a public repository. Throttles (429) and server errors (5xx) are
never recorded either, so a refresh cannot commit an outage.

**Which requests, and why.** `MANIFEST.json` lists the 13 runner payloads
the API tests send, the test files that send each one, the recordings each
one needs and the answer the live run gave (value, citation, taxon id).
They were found by running every API test file with `CATERVA_PYTHON` pointed
at a wrapper that logged each payload, and, for the route tests that need a
listening socket, by calling `resolveQuery` and `groundAnnotatedModel` with
the queries and models those tests post. `Tests/test_http_replay.py` runs
each payload through the real runner with every network send made
impossible and holds it to the recorded answer.

### Refreshing, or adding a payload

1. If an API test starts sending a new payload, add it to `PAYLOADS` in
   `scripts/record_http_fixtures.py`, with a comment naming the test.
2. Run, from the repository root, with the network available:

       python scripts/record_http_fixtures.py

   It unsets `NCBI_API_KEY`, `CORE_API_KEY` and `CATERVA_ENABLE_KEGG` for
   the runs, records each payload live into its own directory, then runs
   every payload again from the recordings with every proxy variable
   pointed at a closed port, and requires the same answer as the live run.
   Only then does it replace `http/` with exactly that set and rewrite
   `MANIFEST.json`.
3. If it stops because a payload fetched a BRENDA page live, record that
   page as `brenda_<ec>.html.gz` (above), add its row, and run it again.
4. Update the counts and dates in this file, and commit `http/` together
   with it.

`python scripts/record_http_fixtures.py --check` fetches nothing and
verifies the committed recordings the same way.
