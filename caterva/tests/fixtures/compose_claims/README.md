# Recorded BRENDA literature pages behind the `--claims` tests

`caterva/tests/test_compose_claims.py` runs the real command

    caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose --claims DIR

offline, against the committed recording of BRENDA's page for EC 2.7.1.1
(`Tests/fixtures/recorded/`, README there) and the 15 NCBI, UniProt and
PubChem answers one human hexokinase Km lookup makes (`Tests/fixtures/
recorded/http/`). With `--claims` the run also captures the literature page
of every reference it cites (`caterva/evidence/capture.py`,
`capture_reference`), through `http_retry.retry_get`, so those two requests
need recordings too. They are here and not in `Tests/fixtures/recorded/http/`
because that directory's `MANIFEST.json` must list exactly the recordings the
API runner's payloads read (`Tests/test_http_replay.py`), and the runner never
asks for a literature page. The test copies both directories into one
replay directory before it runs.

| file | request | status |
|---|---|---|
| 11561a53bfa9cac5a9b098d212382114146e3f4116ce4bf32fe8d235f218bdc8.json.gz | https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068 | 200 |
| 3aa4b36c3cb88132b26a80e335692301e8d1f91b9fb138d65510803301b629ec.json.gz | https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=739603 | 200 |

Reference 641068 is the paper behind the cited human D-glucose Km (6 mM);
739603 the one behind the cited kcat (40.1 1/s). Both fetched 2026-10-17
(UTC), `text/html; charset=UTF-8`. BRENDA data are CC BY 4.0; cite BRENDA
(Chang et al. 2021, Nucleic Acids Res. 49:D498, doi:10.1093/nar/gkaa1025)
with any value taken from them.

**Format.** Exactly the format of `Tests/fixtures/recorded/http/` (its
README): one gzipped JSON file per request, named by the sha256 of the
request's key, written by `Tests/http_retry.py` under `CATERVA_HTTP_RECORD`
and read under `CATERVA_HTTP_RECORDED`. No request here carries a
credential (`http_retry` refuses to record one).

**How they were made.** From the repository root, with the network
available and `CATERVA_HTTP_RECORD` naming a scratch directory,
`http_retry.retry_get` was called for the two URLs above with
`params={"e": "2.7.1.1", "r": <ref>}`, the call `capture_reference` makes;
the two files it wrote were copied here unchanged. The page bytes differ
from `Tests/fixtures/recorded/brenda_reference_2.7.1.1_<ref>.html.gz`
(fetched the same day by hand) only in the cache-busting query strings on
BRENDA's stylesheet and script links and in the name of the server node
that answered (checked line by line for 641068: the reference block is
identical), which is why a bundle built from these recordings pins a
different digest for the same paper's page than the showcase bundle does.

**To refresh**: delete the two files, repeat the two calls with
`CATERVA_HTTP_RECORD` naming this `http/`, and update the date here.
