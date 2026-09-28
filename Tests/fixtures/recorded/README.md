# Recorded BRENDA pages

Real pages, fetched from BRENDA and stored unmodified (gzipped), so that
tests which exercise the whole literature path do not fail when BRENDA is
down. They are read only when `CATERVA_BRENDA_RECORDED` names this
directory, which the API server's test config sets and nothing else does:
the product always fetches live.

| file | source | fetched | sha256 of the uncompressed page |
|---|---|---|---|
| brenda_2.7.1.1.html.gz | https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1 | 2026-09-28 | 3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91 |

Recorded after BRENDA returned HTTP 500 for this page in three CI runs on
2026-09-28 (five hexokinase tests failed on an outage, not a defect). BRENDA
data are licensed CC BY 4.0; cite BRENDA (Chang et al. 2021, Nucleic Acids
Res. 49:D498, doi:10.1093/nar/gkaa1025) with any value taken from them.
To refresh: fetch the URL again, gzip it here, update the hash and date.
